"""mode_manager_node.py — Görev 2 yarı otonom sürü kontrol koordinatörü.

Şartname §5.2 — Yarı Otonom Sürü Kontrolü Görevi:
  Sürüyü tek bir joystick/kumandadan yönlendirme; sürüdeki tüm
  İHA'lar kumandadan gelen girdilere senkronize cevap verir.

Bu node:
  1. mission_fsm'den SEMI_AUTONOMOUS state'ini takip eder.
  2. SwarmControlCommand (joystick) mesajlarını alır.
  3. Deadman safety kontrolü yapar.
  4. Aktif moda göre movement_mode veya maneuver_mode'u çağırır.
  5. FormationCommand veya AgentSetpoint yayınlar.
  6. SystemEvent yaşam döngüsü olayları yayınlar.

Proxy kuralı:
  Publisher  -> /swarm/internal/...
  Subscriber <- /swarm/public/...
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
from std_msgs.msg import UInt8

from swarm_interfaces.msg import (
    AgentSetpoint,
    AgentStatus,
    FormationCommand,
    SwarmControlCommand,
    SwarmState,
    SystemEvent,
)

from .mode_context import ModeContext
from .mode_states import ACTIVE_CONTROL_STATES, ControlMode, ModeState
from .mode_transitions import evaluate_transitions
from .movement_mode import compute_formation_command, compute_hold_command
from .maneuver_mode import compute_agent_setpoints, compute_hold_setpoints

_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_BEST_EFFORT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


class ModeManagerNode(Node):
    """Görev 2 yarı otonom sürü kontrol koordinatörü.

    Lider drone üzerinde çalışır. mission_fsm SEMI_AUTONOMOUS
    state'ine geçtiğinde aktifleşir.
    """

    def __init__(self) -> None:
        super().__init__('mode_manager_node')

        self._declare_params()

        self._ctx = ModeContext(
            agent_ids=self._agent_ids,
            sitl_mode=self._sitl_mode,
        )

        self._last_tick_time = time.monotonic()

        # Formasyon ofsetleri — formation_geometry'den veya config'den
        # yüklenecek. Şimdilik varsayılan Ok Başı (3 drone).
        self._formation_offsets: dict[int, tuple[float, float, float]] = {}
        self._init_default_offsets()

        self._setpoint_sequence: int = 0

        self._setup_publishers()
        self._setup_subscribers()

        self._timer = self.create_timer(
            1.0 / self._tick_hz, self._tick
        )

        self.get_logger().info(
            f'ModeManagerNode başladı: ajanlar={self._agent_ids} '
            f'tick={self._tick_hz}Hz sitl={self._sitl_mode}'
        )

    # ═════════════════════════════════════════════════════════════════
    # BAŞLATMA
    # ═════════════════════════════════════════════════════════════════

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanımlar ve okur."""
        self.declare_parameter('agent_ids', [1, 2, 3])
        self.declare_parameter('tick_hz', 20.0)
        self.declare_parameter('sitl_mode', False)
        self.declare_parameter('default_spacing_m', 5.0)

        self._agent_ids = list(
            self.get_parameter('agent_ids').value
        )
        self._tick_hz = float(
            self.get_parameter('tick_hz').value
        )
        self._sitl_mode = bool(
            self.get_parameter('sitl_mode').value
        )
        self._default_spacing_m = float(
            self.get_parameter('default_spacing_m').value
        )

    def _init_default_offsets(self) -> None:
        """Varsayılan formasyon ofsetlerini başlatır.

        Ok Başı formasyonu, 3 drone:
          Drone 1 (lider): ileri (forward)
          Drone 2: sol arka
          Drone 3: sağ arka
        """
        s = self._default_spacing_m
        if len(self._agent_ids) >= 3:
            self._formation_offsets = {
                self._agent_ids[0]: (s, 0.0, 0.0),       # ileri
                self._agent_ids[1]: (-s / 2, -s, 0.0),   # sol arka
                self._agent_ids[2]: (-s / 2, s, 0.0),    # sağ arka
            }
        elif len(self._agent_ids) == 2:
            self._formation_offsets = {
                self._agent_ids[0]: (0.0, -s / 2, 0.0),
                self._agent_ids[1]: (0.0, s / 2, 0.0),
            }
        else:
            for aid in self._agent_ids:
                self._formation_offsets[aid] = (0.0, 0.0, 0.0)

    def _setup_publishers(self) -> None:
        """Yayıncı kanallarını oluşturur."""
        self._formation_pub = self.create_publisher(
            FormationCommand,
            '/swarm/internal/formation/target',
            _RELIABLE_QOS,
        )

        self._event_pub = self.create_publisher(
            SystemEvent,
            '/swarm/internal/events/system',
            _RELIABLE_QOS,
        )

        # Per-drone AgentSetpoint publisher'ları (manevra modu için)
        self._setpoint_pubs: dict[int, rclpy.publisher.Publisher] = {}
        for aid in self._agent_ids:
            pub = self.create_publisher(
                AgentSetpoint,
                f'/drone_{aid}/control/setpoint',
                _BEST_EFFORT_QOS,
            )
            self._setpoint_pubs[aid] = pub

    def _setup_subscribers(self) -> None:
        """Abone kanallarını oluşturur."""
        # Her drone'un durumu
        for aid in self._agent_ids:
            self.create_subscription(
                AgentStatus,
                f'/swarm/public/drone{aid}/status',
                lambda msg, a=aid: self._on_agent_status(msg, a),
                _BEST_EFFORT_QOS,
            )

        # Joystick komutu
        self.create_subscription(
            SwarmControlCommand,
            '/swarm/public/control/command',
            self._on_control_command,
            _BEST_EFFORT_QOS,
        )

        # mission_fsm durumu
        self.create_subscription(
            UInt8,
            '/swarm/internal/mission/state',
            self._on_mission_state,
            _RELIABLE_QOS,
        )

        # Sürü durumu (centroid, formasyon)
        self.create_subscription(
            SwarmState,
            '/swarm/public/state',
            self._on_swarm_state,
            _RELIABLE_QOS,
        )

        # Sistem olayları
        self.create_subscription(
            SystemEvent,
            '/swarm/public/events/system',
            self._on_event,
            _RELIABLE_QOS,
        )

    # ═════════════════════════════════════════════════════════════════
    # FSM ANA DÖNGÜSÜ
    # ═════════════════════════════════════════════════════════════════

    def _tick(self) -> None:
        """Tick döngüsü — FSM geçişleri ve aktif mod dispatch.

        20 Hz varsayılan hızda çalışır.
        """
        now = time.monotonic()
        dt = now - self._last_tick_time
        self._last_tick_time = now
        ctx = self._ctx

        # 1. FSM geçişlerini değerlendir
        next_state = evaluate_transitions(ctx)
        if next_state is not None and next_state != ctx.state:
            self._transition(next_state)

        # 2. Aktif moda göre komut üret
        if ctx.state == ModeState.MOVEMENT:
            self._dispatch_movement(dt)
        elif ctx.state == ModeState.MANEUVER:
            self._dispatch_maneuver(dt)
        elif ctx.state == ModeState.HOLD:
            self._dispatch_hold()
        elif ctx.state == ModeState.READY:
            self._dispatch_hold()

        # 3. Formasyon değişikliği talebi
        if ctx.formation_change_requested and (
            ctx.state in ACTIVE_CONTROL_STATES
        ):
            self._handle_formation_change()

        # 4. Geçici bayrakları temizle
        ctx.takeoff_requested = False
        ctx.land_requested = False
        ctx.rtl_requested = False
        ctx.emergency_stop_requested = False
        ctx.formation_change_requested = False

    def _transition(self, new_state: ModeState) -> None:
        """Durum geçişini uygular.

        Args:
            new_state: Geçilecek hedef durum.
        """
        old = self._ctx.state
        self._ctx.set_state(new_state)

        self.get_logger().info(
            f'[mode_manager] {old.name} -> {new_state.name}'
        )

        self._on_state_entry(new_state, old)

    def _on_state_entry(
        self, state: ModeState, old_state: ModeState
    ) -> None:
        """Yeni state giriş eylemlerini çalıştırır.

        Args:
            state: Yeni girilen state.
            old_state: Önceki state.
        """
        if state == ModeState.TAKEOFF:
            self._pub_event(
                SystemEvent.EVENT_MISSION_STARTED,
                SystemEvent.SEVERITY_INFO,
                'Görev 2 (Yarı Otonom) kalkış başlıyor',
            )

        elif state == ModeState.READY:
            self._pub_event(
                SystemEvent.EVENT_FORMATION_REACHED,
                SystemEvent.SEVERITY_INFO,
                'Sürü hazır, joystick komutu bekleniyor',
            )

        elif state == ModeState.MOVEMENT:
            self.get_logger().info(
                '[mode_manager] Sürü Hareket Modu aktif'
            )

        elif state == ModeState.MANEUVER:
            self.get_logger().info(
                '[mode_manager] Manevra Modu aktif'
            )

        elif state == ModeState.HOLD:
            self.get_logger().info(
                '[mode_manager] HOLD — deadman bırakıldı'
            )

        elif state == ModeState.LANDING:
            self._pub_event(
                SystemEvent.EVENT_EMERGENCY_LAND,
                SystemEvent.SEVERITY_INFO,
                'Görev 2 iniş komutu',
            )

        elif state == ModeState.RTL:
            self._pub_event(
                SystemEvent.EVENT_RTL_TRIGGERED,
                SystemEvent.SEVERITY_WARNING,
                'Görev 2 RTL',
            )

        elif state == ModeState.EMERGENCY:
            self._pub_event(
                SystemEvent.EVENT_EMERGENCY_LAND,
                SystemEvent.SEVERITY_EMERGENCY,
                'Görev 2 ACIL DURUM',
            )

        elif state == ModeState.COMPLETED:
            self._pub_event(
                SystemEvent.EVENT_MISSION_COMPLETED,
                SystemEvent.SEVERITY_INFO,
                'Görev 2 tamamlandı',
            )

    # ═════════════════════════════════════════════════════════════════
    # MOD DISPATCH
    # ═════════════════════════════════════════════════════════════════

    def _dispatch_movement(self, dt: float) -> None:
        """Sürü Hareket Modu: centroid translasyonu.

        FormationCommand yayınlar.

        Args:
            dt: Zaman adımı (saniye).
        """
        params = compute_formation_command(self._ctx, dt)
        self._publish_formation_command(params)

        # Centroid'i güncelle (sonraki tick'te referans olarak kullan)
        self._ctx.centroid_x = params['center_x']
        self._ctx.centroid_y = params['center_y']
        self._ctx.centroid_z = params['center_z']
        self._ctx.formation_heading_deg = params['heading_deg']

    def _dispatch_maneuver(self, dt: float) -> None:
        """Manevra Modu: formasyon eğme/döndürme.

        Her drone için AgentSetpoint yayınlar.

        Args:
            dt: Zaman adımı (saniye).
        """
        result = compute_agent_setpoints(
            self._ctx, dt, self._formation_offsets,
        )
        setpoints, new_heading, pitch_deg, roll_deg = result

        for sp in setpoints:
            self._publish_agent_setpoint(sp)

        # Context güncelle
        self._ctx.formation_heading_deg = new_heading
        self._ctx.maneuver_pitch_deg = pitch_deg
        self._ctx.maneuver_roll_deg = roll_deg

    def _dispatch_hold(self) -> None:
        """HOLD/READY: mevcut konumu koruma.

        Önceki mod MANEUVER idiyse son eğim açılarını korur.
        MOVEMENT idiyse mevcut centroid'i korur.
        """
        # Manevra eğim açıları varsa onları koru
        if (self._ctx.maneuver_pitch_deg != 0.0
                or self._ctx.maneuver_roll_deg != 0.0):
            setpoints = compute_hold_setpoints(
                self._ctx, self._formation_offsets,
            )
            for sp in setpoints:
                self._publish_agent_setpoint(sp)
        else:
            params = compute_hold_command(self._ctx)
            self._publish_formation_command(params)

    def _handle_formation_change(self) -> None:
        """Formasyon değişikliği talebini işler."""
        ctx = self._ctx
        self.get_logger().info(
            f'[mode_manager] Formasyon değişikliği: '
            f'tip={ctx.requested_formation} '
            f'mesafe={ctx.requested_spacing_m}m'
        )
        ctx.active_formation = ctx.requested_formation
        ctx.requested_spacing_m = ctx.requested_spacing_m

        # FormationCommand ile formasyon değişikliğini bildir
        params = {
            'center_x': ctx.centroid_x,
            'center_y': ctx.centroid_y,
            'center_z': ctx.centroid_z,
            'heading_deg': ctx.formation_heading_deg,
            'formation_type': ctx.requested_formation,
            'spacing_m': ctx.requested_spacing_m,
            'max_speed_mps': ctx.max_speed_mps,
            'use_current_centroid': False,
            'use_current_altitude': True,
        }
        self._publish_formation_command(params)

    # ═════════════════════════════════════════════════════════════════
    # ABONELİK CALLBACK'LERİ
    # ═════════════════════════════════════════════════════════════════

    def _on_agent_status(
        self, msg: AgentStatus, agent_id: int
    ) -> None:
        """Ajan durum mesajını depolar.

        Args:
            msg: AgentStatus mesajı.
            agent_id: Bildiren ajanın ID'si.
        """
        self._ctx.agent_statuses[agent_id] = msg

    def _on_control_command(self, msg: SwarmControlCommand) -> None:
        """SwarmControlCommand (joystick) mesajını ctx'e yazar.

        Deadman ve komut geçerliliğini burada depolar; transition
        mantığı _tick'te çalışır.

        Args:
            msg: Gelen joystick komutu.
        """
        ctx = self._ctx

        ctx.command_valid = msg.command_valid
        ctx.deadman_pressed = msg.deadman_pressed
        ctx.deadman_timeout_s = msg.deadman_timeout_s

        try:
            ctx.control_mode = ControlMode(msg.mode)
        except ValueError:
            ctx.control_mode = ControlMode.UNKNOWN

        ctx.pitch_cmd = msg.pitch_cmd
        ctx.roll_cmd = msg.roll_cmd
        ctx.yaw_cmd = msg.yaw_cmd
        ctx.throttle_cmd = msg.throttle_cmd

        if msg.takeoff:
            ctx.takeoff_requested = True
        if msg.land:
            ctx.land_requested = True
        if msg.rtl:
            ctx.rtl_requested = True
        if msg.emergency_stop:
            ctx.emergency_stop_requested = True

        if msg.formation_change_requested:
            ctx.formation_change_requested = True
            ctx.requested_formation = msg.requested_formation
            ctx.requested_spacing_m = msg.requested_spacing_m

        if msg.max_speed_mps > 0.0:
            ctx.max_speed_mps = msg.max_speed_mps
        if msg.max_yaw_rate_deg_s > 0.0:
            ctx.max_yaw_rate_deg_s = msg.max_yaw_rate_deg_s
        if msg.max_tilt_deg > 0.0:
            ctx.max_tilt_deg = msg.max_tilt_deg

        ctx.command_sequence_num = msg.sequence_num

        if msg.command_valid and msg.deadman_pressed:
            ctx.last_valid_command_time = time.monotonic()

    def _on_mission_state(self, msg: UInt8) -> None:
        """mission_fsm durumunu depolar.

        Args:
            msg: MissionState UInt8 mesajı.
        """
        self._ctx.mission_state = msg.data

    def _on_swarm_state(self, msg: SwarmState) -> None:
        """Sürü durumunu (centroid, formasyon) depolar.

        Yalnızca IDLE veya PREFLIGHT'ta centroid'i SwarmState'ten alır.
        Aktif kontrol sırasında centroid mode_manager tarafından
        hesaplanır.

        Args:
            msg: SwarmState mesajı.
        """
        ctx = self._ctx

        # Centroid'i sadece pasif state'lerde SwarmState'ten al
        if ctx.state in (
            ModeState.IDLE, ModeState.PREFLIGHT,
            ModeState.TAKEOFF, ModeState.READY,
        ):
            ctx.centroid_x = msg.centroid_x
            ctx.centroid_y = msg.centroid_y
            ctx.centroid_z = msg.centroid_z
            ctx.formation_heading_deg = msg.formation_heading_deg

        ctx.active_formation = msg.active_formation
        ctx.formation_reached = msg.formation_reached
        ctx.formation_stable = msg.formation_stable

    def _on_event(self, msg: SystemEvent) -> None:
        """Sistem olaylarını işler.

        Args:
            msg: SystemEvent mesajı.
        """
        eid = msg.event_type

        if eid == SystemEvent.EVENT_EMERGENCY_LAND:
            self._ctx.emergency_stop_requested = True

        elif eid == SystemEvent.EVENT_RTL_TRIGGERED:
            self._ctx.rtl_requested = True

    # ═════════════════════════════════════════════════════════════════
    # YAYIN YARDIMCILARI
    # ═════════════════════════════════════════════════════════════════

    def _publish_formation_command(self, params: dict) -> None:
        """FormationCommand mesajı oluşturup yayınlar.

        Args:
            params: FormationCommand alanları dict'i.
        """
        msg = FormationCommand()
        msg.stamp = self.get_clock().now().to_msg()
        msg.sequence_num = self._ctx.command_sequence_num

        msg.formation_type = params.get('formation_type', 0)
        msg.center_x = params.get('center_x', 0.0)
        msg.center_y = params.get('center_y', 0.0)
        msg.center_z = params.get('center_z', 0.0)
        msg.heading_deg = params.get('heading_deg', 0.0)
        msg.spacing_m = params.get('spacing_m', 5.0)
        msg.use_current_centroid = params.get(
            'use_current_centroid', False
        )
        msg.use_current_altitude = params.get(
            'use_current_altitude', False
        )
        msg.hold_after_reached = True
        msg.max_speed_mps = params.get('max_speed_mps', 0.0)
        msg.source_module = 'mode_manager'

        self._formation_pub.publish(msg)

    def _publish_agent_setpoint(self, sp: dict) -> None:
        """Per-drone AgentSetpoint mesajı oluşturup yayınlar.

        Args:
            sp: AgentSetpoint alanları dict'i.
        """
        agent_id = sp['agent_id']
        pub = self._setpoint_pubs.get(agent_id)
        if pub is None:
            return

        self._setpoint_sequence += 1

        msg = AgentSetpoint()
        msg.stamp = self.get_clock().now().to_msg()
        msg.sequence_num = self._setpoint_sequence
        msg.agent_id = agent_id

        msg.source = AgentSetpoint.SOURCE_MANEUVER_EXECUTOR
        msg.priority = AgentSetpoint.PRIORITY_MANEUVER

        msg.x = sp['x']
        msg.y = sp['y']
        msg.z = sp['z']
        msg.heading_deg = sp['heading_deg']

        msg.position_valid = True
        msg.heading_valid = True

        msg.max_speed_mps = self._ctx.max_speed_mps

        msg.source_module = 'mode_manager'

        pub.publish(msg)

    def _pub_event(
        self,
        event_type: int,
        severity: int,
        message: str = '',
    ) -> None:
        """SystemEvent mesajı oluşturur ve yayınlar.

        Args:
            event_type: SystemEvent.EVENT_* sabiti.
            severity: SystemEvent.SEVERITY_* seviyesi.
            message: İsteğe bağlı açıklama metni.
        """
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = event_type
        m.severity = severity
        m.source_agent_id = 0
        m.source_module = 'mode_manager'
        m.message = message
        self._event_pub.publish(m)


# ═════════════════════════════════════════════════════════════════════
# GİRİŞ NOKTASI
# ═════════════════════════════════════════════════════════════════════

def main(args=None) -> None:
    """ros2 run tarafından çağrılan giriş noktası."""
    rclpy.init(args=args)
    node = ModeManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
