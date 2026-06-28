"""Sürü seviyesi FSM'i çalıştıran ROS 2 node.

Tüm ajanların AgentStatus mesajlarını toplar, sürü genelinde
sağlık kontrolü ve durum geçişlerini yönetir, SwarmState yayınlar.

Topic adlandırma kuralları (network_proxy uyumlu):
    - Publisher (ağa çıkan): /swarm/internal/...
    - Subscriber (ağdan gelen): /swarm/public/...
    - Lokal iç haberleşme: /swarm/agent/drone{id}/...
"""

import math
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
    SwarmOrigin,
    SwarmState as SwarmStateMsg,
    SystemEvent,
)

_M_PER_DEG_LAT = 111_320.0

from ..agent_fsm.agent_states import AgentState
from .swarm_context import AgentStatusCache, SwarmContext
from .swarm_states import (
    AIRBORNE_SWARM_STATES,
    FormationType,
    SwarmState,
)
from .swarm_transitions import evaluate_transitions


_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_ELECTION_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_ORIGIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

_HEARTBEAT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)

# --- Sağlık eşikleri ---
_AGENT_STALE_TIMEOUT_S = 3.0
_FORMATION_STABLE_THRESHOLD_M = 1.5
_FORMATION_REACHED_THRESHOLD_M = 1.0


class SwarmFsmNode(Node):
    """Sürü seviyesi FSM node'u.

    Tüm ajanların AgentStatus'unu toplar, sürü geneli sağlık
    kontrolü yapar, durum geçişlerini yönetir ve SwarmState yayınlar.

    Sağlık toplulaştırma mantığı bu node'un içinde yer alır.
    Mimarideki paylaşılan events/ ve health_monitor/ modülleri
    ayrı paketler olarak tüm FSM'lere (agent, mission, swarm)
    hizmet verecektir; buradaki kontroller yalnızca swarm_fsm'in
    kendi iç karar mekanizmasıdır.
    """

    def __init__(self) -> None:
        """
        Sürü FSM node'unu başlatır, publisher ve subscriber'ları kurar.
        """
        super().__init__('swarm_fsm_node')

        self._declare_params()

        self._ctx = SwarmContext(
            expected_agent_count=self._agent_count,
            sitl_mode=self._sitl_mode,
            heartbeat_timeout_s=self._heartbeat_timeout_ms / 1000.0,
            min_healthy_ratio=self._min_healthy_ratio,
        )

        self._max_election_seq: int = 0
        self._origin_lat: float | None = None
        self._origin_lon: float | None = None

        self._setup_publishers()
        self._setup_subscribers()

        self._timer = self.create_timer(
            1.0 / self._tick_hz, self._tick
        )

        self.get_logger().info(
            f'SwarmFsmNode başlatıldı: '
            f'agent_count={self._agent_count} '
            f'tick_hz={self._tick_hz}'
        )

    # ==================================================================
    # Parametreler
    # ==================================================================

    def _declare_params(self) -> None:
        """ROS 2 parametrelerini tanımlar ve okur."""
        self.declare_parameter('agent_count', 3)
        self.declare_parameter('tick_hz', 5.0)
        self.declare_parameter('sitl_mode', False)
        self.declare_parameter('heartbeat_timeout_ms', 300.0)
        self.declare_parameter('min_healthy_ratio', 0.5)

        self._agent_count: int = (
            self.get_parameter('agent_count').value
        )
        self._tick_hz: float = (
            self.get_parameter('tick_hz').value
        )
        self._sitl_mode: bool = (
            self.get_parameter('sitl_mode').value
        )
        self._heartbeat_timeout_ms: float = (
            self.get_parameter('heartbeat_timeout_ms').value
        )
        self._min_healthy_ratio: float = (
            self.get_parameter('min_healthy_ratio').value
        )

    # ==================================================================
    # Publisher / Subscriber Kurulumu
    # ==================================================================

    def _setup_publishers(self) -> None:
        """SwarmState ve SystemEvent publisher'larını oluşturur.

        Kural 1: Ağa çıkan veriler /swarm/internal/... ile yayınlanır.
        Network proxy bunları alır, gecikme/kayıp uygulayıp
        /swarm/public/... olarak diğer İHA'lara iletir.
        """
        self._state_pub = self.create_publisher(
            SwarmStateMsg,
            '/swarm/internal/state',
            _RELIABLE_QOS,
        )
        self._event_pub = self.create_publisher(
            SystemEvent,
            '/swarm/internal/events/system',
            _RELIABLE_QOS,
        )

    def _setup_subscribers(self) -> None:
        """Ajan, event, heartbeat ve election aboneliklerini oluşturur.

        Kural 2: Ağdan gelen veriler /swarm/public/... üzerinden
        dinlenir. Bu veriler network proxy'den geçmiş, gecikme ve
        kayıp uygulanmış gerçekçi verilerdir.
        """
        # Her ajan için AgentStatus — public (proxy'den geçmiş)
        for aid in range(1, self._agent_count + 1):
            self.create_subscription(
                AgentStatus,
                f'/swarm/public/drone{aid}/status',
                self._make_agent_cb(aid),
                10,
            )

        # SystemEvent — public (diğer İHA'lardan gelen olaylar)
        self.create_subscription(
            SystemEvent,
            '/swarm/public/events/system',
            self._on_event,
            _RELIABLE_QOS,
        )

        # LeaderHeartbeat — public (liderden gelen sağlık sinyali)
        self.create_subscription(
            LeaderHeartbeat,
            '/swarm/public/leader/heartbeat',
            self._on_heartbeat,
            _HEARTBEAT_QOS,
        )

        # ElectionResult — public (lider seçim sonucu)
        self.create_subscription(
            ElectionResult,
            '/swarm/public/election/result',
            self._on_election,
            _ELECTION_QOS,
        )

        # SwarmOrigin — shared NED frame referansı (transient: geç başlansa da alır)
        self.create_subscription(
            SwarmOrigin,
            '/swarm/public/origin',
            self._on_swarm_origin,
            _ORIGIN_QOS,
        )

    # ==================================================================
    # Ana Döngü (Tick)
    # ==================================================================

    def _tick(self) -> None:
        """FSM ana döngüsü — sağlık kontrolü, geçiş ve yayın."""
        ctx = self._ctx

        # 1. Sürü sağlık kontrolleri (gömülü)
        self._check_health()

        # 2. Geçiş değerlendirme
        next_s = evaluate_transitions(ctx)
        if next_s is not None and next_s != ctx.swarm_state:
            self._transition(next_s)

        # 3. SwarmState yayınla
        self._publish_state()

    # ==================================================================
    # Sağlık Kontrolleri (gömülü — ayrı modül değil)
    # ==================================================================

    def _check_health(self) -> None:
        """Sürü geneli sağlık kontrollerini sırayla çalıştırır.

        Kritik hata bulunursa FAILSAFE tetiklenir ve erken döner.
        Formasyon metrikleri her tick'te güncellenir.
        """
        if self._check_agent_health():
            return

        if self._check_leader_heartbeat():
            return

        self._update_formation_metrics()

    def _check_agent_health(self) -> bool:
        """Tüm ajanların sağlık durumunu kontrol eder.

        Returns:
            True ise kritik hata bulundu ve işlendi.
        """
        ctx = self._ctx
        if not ctx.agents:
            return False

        total = len(ctx.agents)

        # Stale ajan tespiti
        stale = [
            aid for aid, a in ctx.agents.items()
            if a.is_stale(_AGENT_STALE_TIMEOUT_S)
        ]
        ctx.active_agent_count = total - len(stale)

        # Tüm ajanlarla iletişim koptu
        if ctx.active_agent_count == 0 and total > 0:
            if ctx.swarm_state != SwarmState.FAILSAFE:
                reason = 'Tüm ajanlarla iletişim kesildi'
                self.get_logger().error(
                    f'[SWARM FAILSAFE] {reason}'
                )
                self._transition(SwarmState.FAILSAFE)
                self._pub_event(
                    SystemEvent.EVENT_EMERGENCY_LAND,
                    SystemEvent.SEVERITY_EMERGENCY,
                    reason,
                )
            return True

        # Sağlıklı ajan oranı — havadayken kontrol
        if (ctx.swarm_state in AIRBORNE_SWARM_STATES
                and ctx.active_agent_count > 0):
            healthy = ctx.count_healthy_agents()
            ratio = healthy / ctx.expected_agent_count
            if ratio < ctx.min_healthy_ratio:
                if ctx.swarm_state != SwarmState.FAILSAFE:
                    reason = (
                        f'Sağlıklı ajan oranı düşük: '
                        f'{healthy}/{ctx.expected_agent_count} '
                        f'({ratio:.0%} < '
                        f'{ctx.min_healthy_ratio:.0%})'
                    )
                    self.get_logger().error(
                        f'[SWARM FAILSAFE] {reason}'
                    )
                    self._transition(SwarmState.FAILSAFE)
                    self._pub_event(
                        SystemEvent.EVENT_EMERGENCY_LAND,
                        SystemEvent.SEVERITY_EMERGENCY,
                        reason,
                    )
                return True

        # Kill switch — herhangi bir ajanda aktifse
        kill_agents = [
            aid for aid, a in ctx.agents.items()
            if a.kill_switch_active and not a.is_stale()
        ]
        if (kill_agents
                and ctx.swarm_state in AIRBORNE_SWARM_STATES):
            if ctx.swarm_state != SwarmState.FAILSAFE:
                reason = (
                    f'Kill switch aktif: ajan(lar) {kill_agents}'
                )
                self.get_logger().error(
                    f'[SWARM FAILSAFE] {reason}'
                )
                self._transition(SwarmState.FAILSAFE)
                self._pub_event(
                    SystemEvent.EVENT_KILL_SWITCH_ACTIVATED,
                    SystemEvent.SEVERITY_EMERGENCY,
                    reason,
                )
            return True

        # Emergency güncelle
        failsafe_count = ctx.count_agents_in_state(AgentState.FAILSAFE)
        ctx.emergency_active = failsafe_count > 0

        # Stale ajan uyarısı (kritik değil)
        if stale:
            self.get_logger().warn(
                f'[SWARM] Stale ajanlar: {stale}'
            )

        return False

    def _check_leader_heartbeat(self) -> bool:
        """Lider heartbeat timeout kontrolü yapar.

        Lider kaybolduğunda leader_id sıfırlanır ve CRITICAL
        seviyesinde EVENT_LEADER_CHANGED yayınlanır. Consensus
        modülü bu olayı dinleyerek yeni lider seçimi başlatır.

        Returns:
            True ise lider kaybı tespit edildi ve işlendi.
        """
        ctx = self._ctx

        # Havada değilken kontrol gereksiz
        if ctx.swarm_state not in AIRBORNE_SWARM_STATES:
            return False

        # Lider veya heartbeat yoksa atla
        if ctx.leader_id == 0 or ctx.last_heartbeat_time <= 0.0:
            return False

        elapsed = time.monotonic() - ctx.last_heartbeat_time
        if elapsed > ctx.heartbeat_timeout_s:
            lost_leader = ctx.leader_id
            reason = (
                f'Lider heartbeat timeout: '
                f'lider={lost_leader} '
                f'{elapsed * 1000:.0f}ms > '
                f'{ctx.heartbeat_timeout_s * 1000:.0f}ms'
            )
            self.get_logger().error(
                f'[SWARM] {reason}'
            )

            # Lider ID'yi sıfırla — consensus modülü yeni seçim başlatır
            ctx.leader_id = 0
            ctx.last_heartbeat_time = 0.0

            self._pub_event(
                SystemEvent.EVENT_LEADER_CHANGED,
                SystemEvent.SEVERITY_CRITICAL,
                reason,
            )
            return True

        return False

    def _update_formation_metrics(self) -> None:
        """Centroid ve formasyon kalite metriklerini günceller."""
        ctx = self._ctx
        ctx.compute_centroid()

        # Formasyon tipine göre hedef offsetler (placeholder değerler)
        # Gerçek değerler formation_control modülünden gelmelidir.
        offsets = None
        if ctx.active_formation == FormationType.OKBASI:
            offsets = {
                1: (0.0, 0.0, 0.0),
                2: (-3.0, -3.0, 0.0),
                3: (-3.0, 3.0, 0.0),
            }
        elif ctx.active_formation == FormationType.V:
            offsets = {
                1: (0.0, 0.0, 0.0),
                2: (-3.0, -3.0, 0.0),
                3: (-3.0, 3.0, 0.0),
            }
        elif ctx.active_formation == FormationType.CIZGI:
            offsets = {
                1: (0.0, 0.0, 0.0),
                2: (0.0, -4.0, 0.0),
                3: (0.0, 4.0, 0.0),
            }

        ctx.compute_formation_quality(target_offsets=offsets)

        ctx.formation_stable = (
            ctx.formation_max_error_m
            < _FORMATION_STABLE_THRESHOLD_M
        )

        if ctx.swarm_state == SwarmState.FORMING:
            ctx.formation_reached = (
                ctx.formation_max_error_m
                < _FORMATION_REACHED_THRESHOLD_M
                and ctx.formation_stable
                and ctx.active_agent_count
                >= ctx.expected_agent_count
            )

    # ==================================================================
    # State Geçişleri
    # ==================================================================

    def _transition(self, new_state: SwarmState) -> None:
        """State geçişini uygular ve loglar.

        Args:
            new_state: Geçilecek hedef state.
        """
        old = self._ctx.swarm_state
        self._ctx.set_state(new_state)

        # State'e giriş yan etkileri
        if new_state == SwarmState.IDLE:
            self._ctx.mission_active = False
            self._ctx.formation_reached = False
            self._ctx.rotation_active = False
            self._ctx.current_qr_id = 0
            self._ctx.current_qr_seq = 0

        elif new_state == SwarmState.MISSION_COMPLETE:
            self._ctx.mission_active = False
            self._pub_event(
                SystemEvent.EVENT_MISSION_COMPLETED,
                SystemEvent.SEVERITY_INFO,
                'Görev tamamlandı',
            )

        elif new_state == SwarmState.NAVIGATING:
            self._ctx.rotation_active = False

        elif new_state == SwarmState.FAILSAFE:
            self._ctx.emergency_active = True

        self.get_logger().info(
            f'[SWARM] {old.name} -> {new_state.name}'
        )

    # ==================================================================
    # Subscriber Callback'leri
    # ==================================================================

    def _make_agent_cb(self, agent_id: int):
        """Her ajan için kapatma (closure) ile callback oluşturur.

        Args:
            agent_id: Ajanın numarası.

        Returns:
            Callback fonksiyonu.
        """
        def _cb(msg: AgentStatus) -> None:
            self._on_agent_status(agent_id, msg)
        return _cb

    def _on_agent_status(
        self,
        agent_id: int,
        msg: AgentStatus,
    ) -> None:
        """AgentStatus mesajını cache'e kopyalar.

        Args:
            agent_id: Ajanın numarası.
            msg: Gelen AgentStatus mesajı.
        """
        cache = self._ctx.agents.get(agent_id)
        if cache is None:
            cache = AgentStatusCache(agent_id=agent_id)
            self._ctx.agents[agent_id] = cache

        cache.state = msg.state
        cache.role = msg.role
        cache.armed = msg.armed
        cache.healthy = msg.healthy
        cache.px4_link_ok = msg.px4_link_ok
        cache.gcs_link_ok = msg.gcs_link_ok
        cache.offboard_active = msg.offboard_active
        cache.failsafe_active = msg.failsafe_active
        cache.origin_synced = msg.origin_synced

        cache.pos_x = msg.pos_x
        cache.pos_y = msg.pos_y
        cache.pos_z = msg.pos_z
        if msg.lat_deg != 0.0 or msg.lon_deg != 0.0:
            cache.lat_deg = float(msg.lat_deg)
            cache.lon_deg = float(msg.lon_deg)
        cache.vel_x = msg.vel_x
        cache.vel_y = msg.vel_y
        cache.vel_z = msg.vel_z
        cache.heading_deg = msg.heading_deg

        cache.battery_voltage_v = msg.battery_voltage_v
        cache.battery_percent = msg.battery_percent

        cache.oscillation_detected = msg.oscillation_detected
        cache.unstable_flight = msg.unstable_flight
        cache.kill_switch_active = msg.kill_switch_active
        cache.rc_link_ok = msg.rc_link_ok

        cache.last_update = time.monotonic()

    def _on_event(self, msg: SystemEvent) -> None:
        """SystemEvent bus'tan gelen olayları işler.

        Args:
            msg: Gelen SystemEvent mesajı.
        """
        ctx = self._ctx
        eid = msg.event_type

        # Son olay bilgisini güncelle
        ctx.last_event_type = eid
        ctx.last_event_severity = msg.severity
        ctx.last_event_source = msg.source_agent_id
        ctx.last_event_value = msg.value
        ctx.last_event_has_position = msg.has_position
        if msg.has_position:
            ctx.last_event_pos_x = msg.pos_x
            ctx.last_event_pos_y = msg.pos_y
            ctx.last_event_pos_z = msg.pos_z
        ctx.last_event_message = msg.message

        # Formasyon olayları
        if eid == SystemEvent.EVENT_FORMATION_REACHED:
            ctx.formation_reached = True

        elif eid == SystemEvent.EVENT_FORMATION_FAILED:
            ctx.formation_reached = False
            ctx.status_text = 'Formasyon başarısız'

        # Rotasyon — INTERFACE_CONTRACT Kural 21
        elif eid == SystemEvent.EVENT_ROTATION_STARTED:
            ctx.rotation_active = True

        elif eid == SystemEvent.EVENT_ROTATION_COMPLETED:
            ctx.rotation_active = False

        # Görev olayları
        elif eid == SystemEvent.EVENT_MISSION_STARTED:
            ctx.mission_active = True
            ctx.active_mission = msg.message or 'active'

        elif eid == SystemEvent.EVENT_MISSION_COMPLETED:
            ctx.mission_active = False

        # QR olayları
        elif eid == SystemEvent.EVENT_QR_PARSED:
            ctx.current_qr_seq = (
                int(msg.value) if msg.value > 0 else 0
            )

        # Güvenlik olayları
        elif eid == SystemEvent.EVENT_RTL_TRIGGERED:
            if msg.target_agent_id == 0:
                ctx.pending_rtl = True

        elif eid == SystemEvent.EVENT_EMERGENCY_LAND:
            if msg.target_agent_id == 0:
                ctx.pending_land = True

        elif eid == SystemEvent.EVENT_FAILSAFE_CLEARED:
            ctx.emergency_active = False
            ctx.status_text = ''

        elif eid == SystemEvent.EVENT_LEADER_CHANGED:
            ctx.status_text = msg.message or 'Lider değişti'

    def _on_swarm_origin(self, msg: SwarmOrigin) -> None:
        if msg.valid:
            self._origin_lat = float(msg.origin_lat_deg)
            self._origin_lon = float(msg.origin_lon_deg)

    def _to_shared_ned(self, lat: float, lon: float) -> tuple[float, float]:
        """GPS lat/lon → shared NED (north, east) metre."""
        if self._origin_lat is None:
            return 0.0, 0.0
        d_lat = lat - self._origin_lat
        d_lon = lon - self._origin_lon
        north = d_lat * _M_PER_DEG_LAT
        east = d_lon * _M_PER_DEG_LAT * math.cos(math.radians(self._origin_lat))
        return north, east

    def _on_heartbeat(self, msg: LeaderHeartbeat) -> None:
        """Lider heartbeat mesajını işler.

        Args:
            msg: Gelen LeaderHeartbeat mesajı.
        """
        ctx = self._ctx
        ctx.leader_id = msg.leader_id
        ctx.last_heartbeat_time = time.monotonic()

        if msg.election_round > ctx.election_round:
            ctx.election_round = msg.election_round

    def _on_election(self, msg: ElectionResult) -> None:
        """Lider seçimi sonucunu işler.

        Stale mesaj koruması: sequence_num kontrol edilir.

        Args:
            msg: Gelen ElectionResult mesajı.
        """
        ctx = self._ctx

        if msg.sequence_num <= self._max_election_seq:
            self.get_logger().warn(
                f'[SWARM] Stale election mesajı: '
                f'seq={msg.sequence_num} '
                f'<= {self._max_election_seq}'
            )
            return

        self._max_election_seq = msg.sequence_num

        old_leader = ctx.leader_id
        ctx.leader_id = msg.new_leader_id
        ctx.election_round = msg.election_round
        ctx.last_heartbeat_time = time.monotonic()

        if old_leader != msg.new_leader_id:
            self.get_logger().info(
                f'[SWARM] Lider değişti: {old_leader} -> '
                f'{msg.new_leader_id} '
                f'(round={msg.election_round})'
            )
            self._pub_event(
                SystemEvent.EVENT_LEADER_CHANGED,
                SystemEvent.SEVERITY_INFO,
                f'Yeni lider: {msg.new_leader_id} '
                f'(round: {msg.election_round})',
            )

    # ==================================================================
    # Yayıncılar
    # ==================================================================

    def _publish_state(self) -> None:
        """SwarmContext'i SwarmState mesajına dönüştürüp yayınlar.

        NOT: SwarmState.agents[] dizisi ESP-NOW 250 byte limitini
        aşacağı için boş bırakılır. GCS ve diğer dinleyiciler
        ajan detaylarını /swarm/public/drone{id}/status'tan okur.
        """
        ctx = self._ctx
        m = SwarmStateMsg()
        m.stamp = self.get_clock().now().to_msg()

        m.swarm_state = int(ctx.swarm_state)
        m.leader_id = ctx.leader_id
        m.active_agent_count = ctx.active_agent_count
        m.active_formation = int(ctx.active_formation)

        m.mission_active = ctx.mission_active
        m.formation_reached = ctx.formation_reached
        m.formation_stable = ctx.formation_stable
        m.emergency_active = ctx.emergency_active

        m.centroid_x = ctx.centroid_x
        m.centroid_y = ctx.centroid_y
        m.centroid_z = ctx.centroid_z
        m.formation_heading_deg = ctx.formation_heading_deg

        m.formation_max_error_m = ctx.formation_max_error_m
        m.formation_avg_error_m = ctx.formation_avg_error_m
        m.formation_heading_error_deg = (
            ctx.formation_heading_error_deg
        )

        # agents[] boş — 250 byte ESP-NOW limiti (Kural 4)

        # active_agent_ids + paralel pozisyon dizileri.
        # Decision B: a.healthy tek bayrak (agent_fsm aggregate'i).
        _active_states = frozenset({
            AgentState.IN_SWARM, AgentState.EXECUTING_TASK,
        })
        active_agents = [
            a
            for a in sorted(ctx.agents.values(), key=lambda x: x.agent_id)
            if a.healthy
            and a.origin_synced
            and not a.is_stale()
            and a.state in _active_states
        ]
        m.active_agent_ids = [a.agent_id for a in active_agents]
        # Pozisyonlar shared NED'de olmalı (formation_node Macar maliyet matrisi için).
        # Origin geldiyse GPS→shared NED; gelmemişse local NED ile devam (fallback).
        shared_positions = []
        for a in active_agents:
            if self._origin_lat is not None and (a.lat_deg != 0.0 or a.lon_deg != 0.0):
                n, e = self._to_shared_ned(a.lat_deg, a.lon_deg)
                shared_positions.append((n, e, float(a.pos_z)))
            else:
                shared_positions.append((float(a.pos_x), float(a.pos_y), float(a.pos_z)))
        m.agent_pos_x = [p[0] for p in shared_positions]
        m.agent_pos_y = [p[1] for p in shared_positions]
        m.agent_pos_z = [p[2] for p in shared_positions]

        m.active_mission = ctx.active_mission
        m.status_text = ctx.status_text

        m.current_qr_id = ctx.current_qr_id
        m.current_qr_seq = ctx.current_qr_seq

        m.last_event_type = ctx.last_event_type
        m.last_event_severity = ctx.last_event_severity
        m.last_event_source = ctx.last_event_source
        m.last_event_value = ctx.last_event_value
        m.last_event_pos_x = ctx.last_event_pos_x
        m.last_event_pos_y = ctx.last_event_pos_y
        m.last_event_pos_z = ctx.last_event_pos_z
        m.last_event_has_position = ctx.last_event_has_position
        m.last_event_message = ctx.last_event_message

        self._state_pub.publish(m)

    def _pub_event(
        self,
        event_type: int,
        severity: int,
        message: str = '',
    ) -> None:
        """SystemEvent yayınlar.

        Args:
            event_type: SystemEvent.EVENT_* sabiti.
            severity: SystemEvent.SEVERITY_* seviyesi.
            message: İsteğe bağlı açıklama metni.
        """
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = event_type
        m.severity = severity
        m.source_agent_id = 0  # sürü geneli
        m.source_module = 'swarm_fsm'
        m.message = message
        self._event_pub.publish(m)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SwarmFsmNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
