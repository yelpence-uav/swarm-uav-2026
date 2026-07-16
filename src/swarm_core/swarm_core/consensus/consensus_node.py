"""Dağıtık consensus düğümü: sürü lideri arbitrasyonu (drone başına bir örnek).

Bu düğümün tek sorumluluğu, sürüde liderin kim olduğunu belirlemektir. Lider,
ek bir oylama turu olmaksızın deterministik biçimde seçilir: uygunluk
koşullarını sağlayan ajanlar arasından en küçük agent_id'ye sahip olan lider
olur (preemptive). Lider seçilen düğüm periyodik heartbeat yayınlar ve kendi
rolünü yerel AssignRole servisi üzerinden kendi agent_fsm'ine uygular.

Kapsam: Bu düğüm yalnızca rol arbitrasyonu yapar. Formasyon tipi, QR görev
akışı, manevra, standby katılımı ve origin yayını bu düğümün kapsamı dışındadır
(sırasıyla mission_fsm, agent_fsm ve swarm_origin_publisher sorumluluğundadır).
Consensus yalnızca "leader_id + role" üretir; üst katmanlar bu çıktıyı tüketir.

Karar / durum / bağlantı ayrımı:
    election.py          - saf seçim mantığı (birim test edilebilir)
    consensus_context.py - durum (komşu cache'i ve lider state'i)
    bu modül             - ROS 2 bağlantısı (pub/sub/srv, timer, yayın)

Topic adlandırma kuralı (network_proxy / esp32_bridge ile uyumlu):
    Yayın (ağa çıkan)   : /swarm/internal/...
    Abone (ağdan gelen) : /swarm/public/...
    Kendi durumu        : /swarm/internal/drone{id}/status (yerel, otoriter)
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


# --- QoS profilleri (network_proxy QoS tablosu ile birebir uyumlu) ---
# Heartbeat RELIABLE + VOLATILE + KEEP_LAST(1). "Broadcast" radyo modelidir;
# DDS reliability AYRI eksendir. Radyo kaybını proxy modelliyor (drop ederek);
# proxy'nin GEÇİRDİĞİ paket DDS bacağında ikinci kez düşmesin diye RELIABLE.
# VOLATILE olduğu için "eski heartbeat replay" olmaz (o yalnız TRANSIENT_LOCAL'de
# olur). consensus + network_proxy + swarm_fsm + LeaderHeartbeat.msg burada hizalı.
_HEARTBEAT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

# ElectionResult RELIABLE + TRANSIENT_LOCAL (latched). Sonradan katılan bir
# drone'un en güncel lider ilanını alabilmesi için kalıcı tutulur.
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

# BEST_EFFORT: komşu status'leri proxy'den (/public) BEST_EFFORT geliyor
# (kayıplı kanal). RELIABLE abone best-effort yayıncıyla eşleşmez.
_STATUS_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_U32 = 2 ** 32


class ConsensusNode(Node):
    """Tek bir drone için deterministik, preemptive lider seçim düğümü."""

    def __init__(self) -> None:
        """Parametreleri, bağlamı, G/Ç'yi ve ana döngü timer'ını başlatır."""
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
        """ROS 2 parametrelerini tanımlar ve örnek alanlarına okur."""
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
        """Yayıncıları, aboneleri ve servis istemcisini oluşturur."""
        # Yayıncılar (ağa çıkan kanallar -> internal)
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

        # Tüm ajanların durumu izlenir: komşular public, kendi
        # durumumuz internal kanaldan alınır.
        for aid in range(1, self._agent_count + 1):
            self.create_subscription(
                AgentStatus, f'/swarm/public/drone{aid}/status',
                self._make_status_cb(aid), _STATUS_QOS,
            )
        self.create_subscription(
            AgentStatus, f'/swarm/internal/drone{self._agent_id}/status',
            self._make_status_cb(self._agent_id), 10,
        )

        # Liderden gelen heartbeat ve seçim sonucu
        # (ağdan gelen -> public).
        self.create_subscription(
            LeaderHeartbeat, '/swarm/public/leader/heartbeat',
            self._on_heartbeat, _HEARTBEAT_QOS,
        )
        self.create_subscription(
            ElectionResult, '/swarm/public/election/result',
            self._on_election, _ELECTION_QOS,
        )

        # Kendi rolünü yerel agent_fsm'e uygulamak için servis istemcisi.
        self._role_client = self.create_client(
            AssignRole, f'/swarm/agent/drone{self._agent_id}/assign_role',
        )

    # ==================================================================
    # Ana döngü
    # ==================================================================

    def _tick(self) -> None:
        """Periyodik değerlendirme: uygunluk, lider değişimi ve heartbeat."""
        now = time.monotonic()
        ctx = self._ctx
        own = ctx.own()
        own_airborne = own is not None and own.state in AIRBORNE_STATES

        elig = election.eligible_ids(ctx, now)
        effective = election.effective_set(ctx, now, own_airborne, elig)

        # Bootstrap bekleme süresi: lider yokken ilk uygun aday
        # görüldüğünde başlatılır.
        if ctx.leader_id == 0 and effective and ctx.bootstrap_since == 0.0:
            ctx.bootstrap_since = now

        change = election.decide_change(ctx, effective, now)
        if change is not None:
            self._set_leader(*change)

        if ctx.is_leader and own_airborne:
            self._publish_heartbeat(len(elig))

    def _set_leader(self, new_id: int, reason: int) -> None:
        """Yeni lideri uygular: round, rol ve yayınları günceller."""
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
        """Kendi rolünü yerel AssignRole servisiyle agent_fsm'e uygular.

        Yalnızca ajan aktif/armed durumdayken ve rol gerçekten değiştiğinde
        çağrı yapar. STANDBY / DETACHED / IDLE / LANDED durumlarına dokunmaz;
        bunları agent_fsm ve mission katmanı yönetir.
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
            # Servis henüz hazır değil; sonraki rol değişiminde
            # yeniden denenir.
            return

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
        """Belirli bir ajan için AgentStatus callback'i üretir (closure)."""
        def _cb(msg: AgentStatus) -> None:
            self._ctx.update_status(agent_id, msg, time.monotonic())
        return _cb

    def _on_heartbeat(self, msg: LeaderHeartbeat) -> None:
        """Liderden gelen heartbeat: canlılık, geç katılım, split-brain.

        - Heartbeat mevcut liderden geliyorsa canlılık zaman damgası tazelenir.
        - Henüz lider bilinmiyorsa (bootstrap / geç katılım) ilan edilen lider
          benimsenir.
        - Daha küçük agent_id'li farklı bir lider duyulursa (ağ bölünmesi) ona
          geçilir; bu düğüm liderse liderliği bırakır. Böylece split-brain
          deterministik olarak çözülür (en küçük ID kazanır). Daha büyük ID'li
          lider yok sayılır.
        """
        ctx = self._ctx
        if msg.leader_id == self._agent_id:
            return  # kendi yayınımızın yankısı
        now = time.monotonic()
        if msg.leader_id == ctx.leader_id:
            ctx.last_hb_time = now
        elif ctx.leader_id == 0 or msg.leader_id < ctx.leader_id:
            self._adopt_leader(msg.leader_id, msg.election_round, now)

    def _adopt_leader(
        self, leader_id: int, election_round: int, now: float,
    ) -> None:
        """İlan edilen lideri benimser; gerekirse liderliği bırakır."""
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
        """Latched ElectionResult: stale koruması + lider benimseme."""
        ctx = self._ctx
        if msg.sequence_num <= ctx.max_seen_seq:
            return  # eski mesaj (sequence geriye gitmiş)
        ctx.max_seen_seq = msg.sequence_num
        if msg.election_round < ctx.election_round:
            return  # eski round

        ctx.election_round = max(ctx.election_round, msg.election_round)
        ctx.leader_id = msg.new_leader_id
        ctx.is_leader = (msg.new_leader_id == self._agent_id)
        ctx.last_hb_time = time.monotonic()
        self._apply_role()

    # ==================================================================
    # Yayıncılar
    # ==================================================================

    def _publish_heartbeat(self, active_count: int) -> None:
        """Lider canlılık heartbeat'ini yayınlar."""
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
        """Latched seçim sonucunu yayınlar (geç katılanlar için kalıcı)."""
        ctx = self._ctx
        m = ElectionResult()
        m.stamp = self.get_clock().now().to_msg()
        ctx.out_seq = (ctx.out_seq + 1) % _U32
        m.sequence_num = ctx.out_seq
        m.new_leader_id = leader_id
        m.election_round = ctx.election_round
        m.triggered_by_agent_id = self._agent_id
        m.reason = reason
        m.confirmed_by_agent_ids = []  # bilgi amaçlı; bloklayıcı bir oy değil
        m.message = f'Lider: drone{leader_id} (round {ctx.election_round})'
        self._election_pub.publish(m)

    def _pub_leader_changed(self, leader_id: int) -> None:
        """Lider değişimini olay veri yoluna (event bus) bildirir."""
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
    """Düğüm giriş noktası."""
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
