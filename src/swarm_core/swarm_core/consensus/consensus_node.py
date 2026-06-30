"""Değişken liderli dağıtık consensus node'u — her drone'da ayrı çalışır.

Tek sorumluluğu: SÜRÜDE KİM LİDER? KTR 5.1'e göre deterministik ve ek
oylama olmadan çözer (lider = güvenli havuzdaki en küçük agent_id,
preemptive), lider ise heartbeat yayınlar, kendi rolünü kendi agent_fsm'ine
yerel AssignRole servisiyle uygular.

SINIR: Bu node SADECE rol arbitrasyonu yapar. Formasyon tipi / QR / manevra
/ standby-join / origin yayını BU NODE'UN İŞİ DEĞİLDİR (mission_fsm,
agent_fsm, swarm_origin_publisher). Consensus yalnızca "leader_id + role"
üretir; diğer katmanlar bunu okur.

Karar/durum ayrımı:
    election.py          → saf seçim mantığı (test edilebilir)
    consensus_context.py → durum (ajan cache + lider state)
    bu dosya             → ROS bağlantısı (pub/sub/srv, timer, yayın)

Topic adlandırma (network_proxy / esp32_bridge uyumlu):
    Yayın (ağa çıkan)  : /swarm/internal/...
    Abone (ağdan gelen): /swarm/public/...
    Kendi durumu       : /swarm/internal/drone{id}/status (yerel, otoriter)
"""

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_interfaces.msg import (
    AgentStatus,
    ElectionResult,
    LeaderHeartbeat,
    SystemEvent,
)
from swarm_interfaces.srv import AssignRole

from . import election
from .consensus_context import ConsensusContext
from .consensus_states import AIRBORNE_STATES, ELIGIBLE_STATES


# --- QoS profilleri (network_proxy tablosuyla birebir) ---
# Heartbeat: BEST_EFFORT + KEEP_LAST(1). Eski heartbeat'in retransmit'i
# "lider hayatta" yanılgısı üretir → reliable OLMAMALI.
_HEARTBEAT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

# ElectionResult: RELIABLE + TRANSIENT_LOCAL. Latched → geç katılan dron
# son lideri alabilmeli (öğren-ve-hatırla).
_ELECTION_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_U32 = 2 ** 32


class ConsensusNode(Node):
    """Tek drone için deterministik, preemptive lider seçim node'u."""

    def __init__(self) -> None:
        super().__init__('consensus_node')

        self._declare_params()

        self._ctx = ConsensusContext(
            agent_id=self._agent_id,
            agent_count=self._agent_count,
            stale_s=self._stale_s,
            hb_timeout_s=self._hb_timeout_s,
            battery_min_v=self._battery_min_v,
            grace_s=self._grace_s,
        )

        self._setup_io()
        self._timer = self.create_timer(1.0 / self._tick_hz, self._tick)

        self.get_logger().info(
            f'ConsensusNode başlatıldı: agent_id={self._agent_id} '
            f'agent_count={self._agent_count} tick_hz={self._tick_hz}'
        )

    # ==================================================================
    # Parametreler
    # ==================================================================

    def _declare_params(self) -> None:
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('agent_count', 3)
        self.declare_parameter('tick_hz', 10.0)
        self.declare_parameter('heartbeat_timeout_ms', 300.0)
        self.declare_parameter('agent_stale_timeout_s', 3.0)
        self.declare_parameter('battery_min_v', 14.0)
        self.declare_parameter('bootstrap_grace_s', 1.5)

        self._agent_id = int(self.get_parameter('agent_id').value)
        self._agent_count = int(self.get_parameter('agent_count').value)
        self._tick_hz = float(self.get_parameter('tick_hz').value)
        self._hb_timeout_s = (
            float(self.get_parameter('heartbeat_timeout_ms').value) / 1000.0
        )
        self._stale_s = float(
            self.get_parameter('agent_stale_timeout_s').value
        )
        self._battery_min_v = float(
            self.get_parameter('battery_min_v').value
        )
        self._grace_s = float(
            self.get_parameter('bootstrap_grace_s').value
        )

    # ==================================================================
    # Publisher / Subscriber / Service
    # ==================================================================

    def _setup_io(self) -> None:
        # Yayıncılar (ağa çıkan → internal)
        self._hb_pub = self.create_publisher(
            LeaderHeartbeat, '/swarm/internal/leader/heartbeat',
            _HEARTBEAT_QOS,
        )
        self._election_pub = self.create_publisher(
            ElectionResult, '/swarm/internal/election/result',
            _ELECTION_QOS,
        )
        self._event_pub = self.create_publisher(
            SystemEvent, '/swarm/internal/events/system', _RELIABLE_QOS,
        )

        # Tüm ajanların durumu — komşular public'ten, kendisi internal'dan.
        for aid in range(1, self._agent_count + 1):
            self.create_subscription(
                AgentStatus, f'/swarm/public/drone{aid}/status',
                self._make_status_cb(aid), 10,
            )
        self.create_subscription(
            AgentStatus, f'/swarm/internal/drone{self._agent_id}/status',
            self._make_status_cb(self._agent_id), 10,
        )

        # Liderden gelen heartbeat ve election ilanı (ağdan → public)
        self.create_subscription(
            LeaderHeartbeat, '/swarm/public/leader/heartbeat',
            self._on_heartbeat, _HEARTBEAT_QOS,
        )
        self.create_subscription(
            ElectionResult, '/swarm/public/election/result',
            self._on_election, _ELECTION_QOS,
        )

        # Kendi rolünü kendi agent_fsm'ine uygulamak için (localhost).
        self._role_client = self.create_client(
            AssignRole, f'/swarm/agent/drone{self._agent_id}/assign_role',
        )

    # ==================================================================
    # Ana döngü
    # ==================================================================

    def _tick(self) -> None:
        now = time.monotonic()
        ctx = self._ctx
        own = ctx.own()
        own_airborne = own is not None and own.state in AIRBORNE_STATES

        elig = election.eligible_ids(ctx, now)
        effective = election.effective_set(ctx, now, own_airborne, elig)

        # Bootstrap grace zamanlayıcısı: lider yokken ilk uygun görülünce başlat.
        if ctx.leader_id == 0 and effective and ctx.bootstrap_since == 0.0:
            ctx.bootstrap_since = now

        change = election.decide_change(ctx, effective, now)
        if change is not None:
            self._set_leader(*change)

        if ctx.is_leader and own_airborne:
            self._publish_heartbeat(len(elig))

    def _set_leader(self, new_id: int, reason: int) -> None:
        ctx = self._ctx
        old = ctx.leader_id
        ctx.election_round = (ctx.election_round + 1) % 256
        ctx.leader_id = new_id
        ctx.is_leader = (new_id == self._agent_id)
        ctx.last_hb_time = time.monotonic()
        ctx.bootstrap_since = 0.0

        self.get_logger().info(
            f'[CONSENSUS] Lider: {old} -> {new_id} '
            f'(round={ctx.election_round}, ben={self._agent_id})'
        )

        if ctx.is_leader:
            self._publish_election_result(new_id, reason)
        self._pub_leader_changed(new_id)
        self._apply_role()

    # ==================================================================
    # Rol uygulama (kendi agent_fsm'ine — localhost)
    # ==================================================================

    def _apply_role(self) -> None:
        """Kendi rolünü kendi agent_fsm'ine yerel AssignRole ile uygular.

        Yalnızca durumum aktif uçuş/armed iken ve rol değiştiğinde çağırır.
        STANDBY/DETACHED/IDLE/LANDED durumlarına dokunmaz (onları agent_fsm
        ve mission yönetir).
        """
        ctx = self._ctx
        own = ctx.own()
        if own is None or own.state not in ELIGIBLE_STATES:
            return

        desired = (
            AssignRole.Request.ROLE_LEADER if ctx.is_leader
            else AssignRole.Request.ROLE_FOLLOWER
        )
        if desired == ctx.applied_role:
            return
        if not self._role_client.service_is_ready():
            return  # servis hazır değilse bir sonraki değişimde tekrar dener

        req = AssignRole.Request()
        req.target_agent_id = self._agent_id
        req.role = desired
        req.reason = 'consensus_election'
        self._role_client.call_async(req)
        ctx.applied_role = desired

    # ==================================================================
    # Subscriber callback'leri
    # ==================================================================

    def _make_status_cb(self, agent_id: int):
        def _cb(msg: AgentStatus) -> None:
            self._ctx.update_status(agent_id, msg, time.monotonic())
        return _cb

    def _on_heartbeat(self, msg: LeaderHeartbeat) -> None:
        """Liderden gelen heartbeat — canlılık, geç-katılım ve split-brain.

        - Mevcut lider ise: canlılığı tazele.
        - Liderim yoksa (bootstrap/geç katılım): ilan edileni benimse.
        - Farklı ve KÜÇÜK ID'li bir lider duyarsam (bölünmüş ağ / iki lider):
          ona çekilirim (küçük ID kazanır) → split-brain kendiliğinden çözülür.
          Lider isem liderlikten çekilirim. Büyük ID'li lider duyarsam yok
          sayarım (benim/mevcut küçük ID kazanır).
        """
        ctx = self._ctx
        if msg.leader_id == self._agent_id:
            return  # kendi yankımız
        now = time.monotonic()
        if msg.leader_id == ctx.leader_id:
            ctx.last_hb_time = now
        elif ctx.leader_id == 0 or msg.leader_id < ctx.leader_id:
            self._adopt_leader(msg.leader_id, msg.election_round, now)

    def _adopt_leader(
        self, leader_id: int, election_round: int, now: float,
    ) -> None:
        """Dışarıdan ilan edilen lideri benimser (gerekirse liderlikten çekil)."""
        ctx = self._ctx
        was_leader = ctx.is_leader
        ctx.leader_id = leader_id
        ctx.is_leader = (leader_id == self._agent_id)
        ctx.election_round = max(ctx.election_round, election_round)
        ctx.last_hb_time = now
        if was_leader and not ctx.is_leader:
            self.get_logger().info(
                f'[CONSENSUS] Split-brain çözüldü: liderliği '
                f'drone{leader_id} lehine bıraktım (küçük ID kazanır).'
            )
        self._apply_role()

    def _on_election(self, msg: ElectionResult) -> None:
        """Latched ElectionResult — stale koruması + lider benimseme."""
        ctx = self._ctx
        if msg.sequence_num <= ctx.max_seen_seq:
            return  # stale (sıra geriye)
        ctx.max_seen_seq = msg.sequence_num
        if msg.election_round < ctx.election_round:
            return  # stale (eski round)

        ctx.election_round = max(ctx.election_round, msg.election_round)
        ctx.leader_id = msg.new_leader_id
        ctx.is_leader = (msg.new_leader_id == self._agent_id)
        ctx.last_hb_time = time.monotonic()
        self._apply_role()

    # ==================================================================
    # Yayıncılar
    # ==================================================================

    def _publish_heartbeat(self, active_count: int) -> None:
        ctx = self._ctx
        m = LeaderHeartbeat()
        m.stamp = self.get_clock().now().to_msg()
        m.leader_id = self._agent_id
        ctx.hb_seq = (ctx.hb_seq + 1) % _U32
        m.sequence_num = ctx.hb_seq
        m.election_round = ctx.election_round
        m.active_agent_count = active_count
        m.mission_active = ctx.mission_active
        self._hb_pub.publish(m)

    def _publish_election_result(self, leader_id: int, reason: int) -> None:
        ctx = self._ctx
        m = ElectionResult()
        m.stamp = self.get_clock().now().to_msg()
        ctx.out_seq = (ctx.out_seq + 1) % _U32
        m.sequence_num = ctx.out_seq
        m.new_leader_id = leader_id
        m.election_round = ctx.election_round
        m.triggered_by_agent_id = self._agent_id
        m.reason = reason
        m.confirmed_by_agent_ids = []  # bilgi amaçlı; bloklayıcı oy değil
        m.message = f'Lider: drone{leader_id} (round {ctx.election_round})'
        self._election_pub.publish(m)

    def _pub_leader_changed(self, leader_id: int) -> None:
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = SystemEvent.EVENT_LEADER_CHANGED
        m.severity = SystemEvent.SEVERITY_INFO
        m.source_agent_id = self._agent_id
        m.source_module = 'consensus'
        m.value = float(leader_id)
        m.message = f'Yeni lider: drone{leader_id}'
        self._event_pub.publish(m)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ConsensusNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
