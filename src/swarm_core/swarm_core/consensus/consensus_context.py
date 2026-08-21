"""Consensus durumu: ajan cache ve lider state."""

from swarm_interfaces.msg import AgentStatus


class AgentRec:
    """Bir ajanin consensus icin gereken durumu."""

    __slots__ = (
        'agent_id', 'state', 'role', 'healthy',
        'estimator_ok', 'battery_v', 'last_update',
    )

    def __init__(self, agent_id: int) -> None:
        self.agent_id = agent_id
        self.state = AgentStatus.STATE_UNKNOWN
        self.role = AgentStatus.ROLE_UNKNOWN
        self.healthy = False
        self.estimator_ok = False
        self.battery_v = 0.0
        self.last_update = 0.0

    def is_stale(
        self, now: float, timeout_s: float
    ) -> bool:
        """Timeout suresi gecmisse True doner."""
        if self.last_update <= 0.0:
            return True
        return (now - self.last_update) > timeout_s


class ConsensusContext:
    """Tek drone'un consensus durumu ve parametreleri."""

    def __init__(
        self,
        agent_id: int,
        agent_count: int,
        stale_s: float,
        hb_timeout_s: float,
        battery_min_v: float,
        grace_s: float,
    ) -> None:
        self.agent_id = agent_id
        self.agent_count = agent_count
        self.stale_s = stale_s
        self.hb_timeout_s = hb_timeout_s
        self.battery_min_v = battery_min_v
        self.grace_s = grace_s

        self.agents: dict[int, AgentRec] = {}

        # Lider durumu
        self.leader_id = 0
        self.is_leader = False
        self.election_round = 0
        self.last_hb_time = 0.0
        self.bootstrap_since = 0.0

        # ONALMA BASTIRMASI — P1.14, 21 Agustos 2026.
        #
        # Rakip bir lidere BILEREK boyun egdikten sonra `decide_change`in
        # kucuk-id onalma dali bizi aninda tekrar lider yapardi ve sistem
        # 10 Hz'de titrerdi. Bu damga dolana kadar onalma yapilmaz.
        # Gercek lider KAYBI (LEADER_FAULT) bundan ETKILENMEZ — orasi
        # bastirilirsa lider olunce kimse devralmaz.
        self.onalma_bastir_until = 0.0

        # Mesaj sayaclari
        # seen_seq: KAYNAK BASINA gorulen son sequence_num.
        #   {triggered_by_agent_id: (incarnation, max_seq)}
        #
        # Onceden tek global max_seen_seq vardi ve iki ayri arizaya yol
        # aciyordu (30 Temmuz, iki kollu deneyle olculdu):
        #   1. Yayinci dugum yeniden baslarsa out_seq 0'a doner; global sayac
        #      yuksek kaldigi icin liderin BUTUN yeni secimleri sessizce
        #      dusuyordu.
        #   2. Lider el degistirirse yeni lider seq=1'den baslar; ayni sekilde
        #      dusuyordu.
        # Kaynak basina tutmak (2)'yi, incarnation karsilastirmasi (1)'i cozer.
        self.seen_seq: dict[int, tuple[int, int]] = {}
        self.out_seq = 0
        self.hb_seq = 0

        self.applied_role = AgentStatus.ROLE_UNKNOWN
        self.mission_active = False

    def update_status(
        self, agent_id: int, msg: AgentStatus,
        now: float,
    ) -> None:
        """Ajan durumunu gunceller."""
        rec = self.agents.get(agent_id)
        if rec is None:
            rec = AgentRec(agent_id)
            self.agents[agent_id] = rec
        rec.state = msg.state
        rec.role = msg.role
        rec.healthy = msg.healthy
        rec.estimator_ok = msg.estimator_ok
        rec.battery_v = float(msg.battery_voltage_v)
        rec.last_update = now

    def own(self) -> AgentRec | None:
        """Kendi ajan kaydimizi doner."""
        return self.agents.get(self.agent_id)
