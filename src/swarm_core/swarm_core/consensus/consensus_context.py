"""Consensus durumu — ajan cache ve lider state (saf veri).

swarm_context.py muadili: yalnızca durum + minimal yardımcılar tutar.
Karar mantığı election.py'de, ROS bağlantısı consensus_node.py'de.
"""

from swarm_interfaces.msg import AgentStatus


class AgentRec:
    """Bir ajanın consensus için gereken minimal durumu."""

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

    def is_stale(self, now: float, timeout_s: float) -> bool:
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
        # Parametreler
        self.agent_id = agent_id
        self.agent_count = agent_count
        self.stale_s = stale_s
        self.hb_timeout_s = hb_timeout_s
        self.battery_min_v = battery_min_v
        self.grace_s = grace_s        # bootstrap grace süresi

        # Ajan cache
        self.agents: dict[int, AgentRec] = {}

        # Lider durumu (non-preemptive: lider düşene kadar değişmez)
        self.leader_id = 0
        self.is_leader = False
        self.election_round = 0
        self.last_hb_time = 0.0       # liderden son heartbeat (follower)
        self.bootstrap_since = 0.0    # lider yokken ilk uygun görülme anı

        # Mesaj sayaçları / stale filtresi
        self.max_seen_seq = 0         # gelen ElectionResult stale filtresi
        self.out_seq = 0              # giden ElectionResult sayacı
        self.hb_seq = 0               # giden heartbeat sayacı

        # Uygulanan rol (tekrar AssignRole çağrısını önlemek için)
        self.applied_role = AgentStatus.ROLE_UNKNOWN

        # Heartbeat bağlamı (placeholder — kritik değil; ileride SwarmState'ten).
        self.mission_active = False

    def update_status(
        self, agent_id: int, msg: AgentStatus, now: float,
    ) -> None:
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
        return self.agents.get(self.agent_id)
