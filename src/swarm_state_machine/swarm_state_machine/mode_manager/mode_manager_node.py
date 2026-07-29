# Copyright 2026 Yelpence
"""Semi-autonomous suru kontrol koordinator dugumu."""

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

from std_msgs.msg import UInt8

from swarm_core.formation_control.formation_geometry import (
    compute_slot_offsets,
    FORMATION_OKBASI,
    FORMATION_V,
    FORMATION_CIZGI,
)

from swarm_interfaces.msg import (
    AgentSetpoint,
    AgentStatus,
    FormationCommand,
    SwarmControlCommand,
    SwarmState,
    SystemEvent,
)

from .maneuver_mode import compute_agent_setpoints, compute_hold_setpoints
from .mode_context import ModeContext
from .mode_states import ACTIVE_CONTROL_STATES, ControlMode, ModeState
from .mode_transitions import evaluate_transitions
from .movement_mode import compute_formation_command, compute_hold_command

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
    """Gorev 2 yari otonom suru kontrol koordinatoru."""

    def __init__(self) -> None:
        super().__init__('mode_manager_node')

        self._declare_params()

        self._ctx = ModeContext(
            agent_ids=self._agent_ids,
            sitl_mode=self._sitl_mode,
        )

        self._last_tick_time = time.monotonic()
        self._formation_offsets: dict[int, tuple[float, float, float]] = {}
        self._init_default_offsets()

        self._setpoint_sequence = 0

        self._setup_publishers()
        self._setup_subscribers()

        self._timer = self.create_timer(
            1.0 / self._tick_hz, self._tick
        )

        self.get_logger().info(
            f'ModeManagerNode baslatildi: {self._agent_ids}'
        )

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanimlar ve okur."""
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
        """Varsayilan formasyon ofsetlerini olusturur."""
        s = self._default_spacing_m
        if len(self._agent_ids) >= 3:
            self._formation_offsets = {
                self._agent_ids[0]: (s, 0.0, 0.0),
                self._agent_ids[1]: (-s / 2, -s, 0.0),
                self._agent_ids[2]: (-s / 2, s, 0.0),
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
        """Yayinci kanallarini olusturur."""
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

        self._setpoint_pubs: dict[int, rclpy.publisher.Publisher] = {}
        for aid in self._agent_ids:
            pub = self.create_publisher(
                AgentSetpoint,
                f'/drone_{aid}/control/setpoint',
                _BEST_EFFORT_QOS,
            )
            self._setpoint_pubs[aid] = pub

    def _setup_subscribers(self) -> None:
        """Abone kanallarini olusturur."""
        for aid in self._agent_ids:
            self.create_subscription(
                AgentStatus,
                f'/swarm/public/drone{aid}/status',
                lambda msg, a=aid: self._on_agent_status(msg, a),
                _BEST_EFFORT_QOS,
            )

        self.create_subscription(
            SwarmControlCommand,
            '/swarm/public/control/command',
            self._on_control_command,
            _BEST_EFFORT_QOS,
        )

        self.create_subscription(
            UInt8,
            '/swarm/internal/mission/state',
            self._on_mission_state,
            _RELIABLE_QOS,
        )

        self.create_subscription(
            SwarmState,
            '/swarm/public/state',
            self._on_swarm_state,
            _RELIABLE_QOS,
        )

        self.create_subscription(
            SystemEvent,
            '/swarm/internal/events/system',
            self._on_event,
            _RELIABLE_QOS,
        )

    def _tick(self) -> None:
        """Tick dongusu."""
        now = time.monotonic()
        dt = now - self._last_tick_time
        self._last_tick_time = now
        ctx = self._ctx

        next_state = evaluate_transitions(ctx)
        if next_state is not None and next_state != ctx.state:
            self._transition(next_state)

        if ctx.state == ModeState.MOVEMENT:
            self._dispatch_movement(dt)
        elif ctx.state == ModeState.MANEUVER:
            self._dispatch_maneuver(dt)
        elif ctx.state == ModeState.HOLD:
            self._dispatch_hold()
        elif ctx.state == ModeState.READY:
            self._dispatch_hold()

        if ctx.formation_change_requested:
            self._handle_formation_change()

        ctx.takeoff_requested = False
        ctx.land_requested = False
        ctx.rtl_requested = False
        ctx.emergency_stop_requested = False
        ctx.formation_change_requested = False

    def _transition(self, new_state: ModeState) -> None:
        """Durum gecisini uygular."""
        old = self._ctx.state
        self._ctx.set_state(new_state)

        self.get_logger().info(
            f'[mode_manager] {old.name} -> {new_state.name}'
        )

        self._on_state_entry(new_state, old)

    def _on_state_entry(
        self, state: ModeState, old_state: ModeState
    ) -> None:
        """Yeni durum giris eylemlerini calistirir."""
        if state == ModeState.TAKEOFF:
            self._pub_event(
                SystemEvent.EVENT_MISSION_STARTED,
                SystemEvent.SEVERITY_INFO,
                'Görev 2 kalkış başlıyor',
            )

        elif state == ModeState.READY:
            self._pub_event(
                SystemEvent.EVENT_FORMATION_REACHED,
                SystemEvent.SEVERITY_INFO,
                'Sürü hazır, kumanda bekleniyor',
            )

        elif state == ModeState.MOVEMENT:
            self.get_logger().info(
                '[mode_manager] Hareket modu aktif'
            )

        elif state == ModeState.MANEUVER:
            self.get_logger().info(
                '[mode_manager] Manevra modu aktif'
            )

        elif state == ModeState.HOLD:
            self.get_logger().info(
                '[mode_manager] HOLD modu'
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
                'Görev 2 acil durum',
            )

        elif state == ModeState.COMPLETED:
            self._pub_event(
                SystemEvent.EVENT_MISSION_COMPLETED,
                SystemEvent.SEVERITY_INFO,
                'Görev 2 tamamlandı',
            )

    def _dispatch_movement(self, dt: float) -> None:
        """Sürü hareket modunu yurutur."""
        params = compute_formation_command(self._ctx, dt)
        self._publish_formation_command(params)

        self._ctx.centroid_x = params['center_x']
        self._ctx.centroid_y = params['center_y']
        self._ctx.centroid_z = params['center_z']
        self._ctx.formation_heading_deg = params['heading_deg']

    def _dispatch_maneuver(self, dt: float) -> None:
        """Manevra modunu yurutur."""
        result = compute_agent_setpoints(
            self._ctx, dt, self._formation_offsets,
        )
        setpoints, new_heading, pitch_deg, roll_deg = result

        for sp in setpoints:
            self._publish_agent_setpoint(sp)

        self._ctx.formation_heading_deg = new_heading
        self._ctx.maneuver_pitch_deg = pitch_deg
        self._ctx.maneuver_roll_deg = roll_deg

    def _dispatch_hold(self) -> None:
        """HOLD durumunu yurutur."""
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
        """Formasyon degisikligi talebini isler."""
        ctx = self._ctx
        spacing = ctx.requested_spacing_m if ctx.requested_spacing_m > 0.0 else getattr(self, '_default_spacing_m', 5.0)
        self.get_logger().info(
            f'Formasyon degisikligi: {ctx.requested_formation}, spacing: {spacing}m'
        )
        ctx.active_formation = ctx.requested_formation
        ctx.requested_spacing_m = spacing

        params = {
            'center_x': ctx.centroid_x,
            'center_y': ctx.centroid_y,
            'center_z': ctx.centroid_z,
            'heading_deg': ctx.formation_heading_deg,
            'formation_type': ctx.requested_formation,
            'spacing_m': spacing,
            'max_speed_mps': ctx.max_speed_mps,
            'use_current_centroid': False,
            'use_current_altitude': True,
        }
        self._publish_formation_command(params)
        ctx.formation_change_requested = False

    def _on_agent_status(self, msg: AgentStatus, agent_id: int) -> None:
        self._ctx.agent_statuses[agent_id] = msg

    def _on_control_command(self, msg: SwarmControlCommand) -> None:
        ctx = self._ctx

        ctx.command_valid = msg.command_valid
        ctx.deadman_pressed = msg.deadman_pressed
        ctx.deadman_timeout_s = msg.deadman_timeout_s

        ctx.command_valid = bool(msg.command_valid)
        ctx.deadman_pressed = bool(msg.deadman_pressed)

        # SwA YUKARI (deadman_pressed == False): Emniyet kesin olarak kilitli, TÜM istekleri sıfırla!
        if not msg.deadman_pressed:
            ctx.pitch_cmd = 0.0
            ctx.roll_cmd = 0.0
            ctx.yaw_cmd = 0.0
            ctx.throttle_cmd = 0.0
            ctx.takeoff_requested = False
            ctx.land_requested = False
            ctx.rtl_requested = False
            ctx.emergency_stop_requested = False
            ctx.formation_change_requested = False
            return

        # Emniyet açık (deadman_pressed == True), ancak paket geçersiz (örn. GCS heartbeat):
        # Eksenleri sıfırla ama aksiyon isteklerini KORU! (_tick tarafından işlenip temizlenir)
        if not msg.command_valid:
            ctx.pitch_cmd = 0.0
            ctx.roll_cmd = 0.0
            ctx.yaw_cmd = 0.0
            ctx.throttle_cmd = 0.0
            return

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
        ctx.last_valid_command_time = time.monotonic()

    def _on_mission_state(self, msg: UInt8) -> None:
        self._ctx.mission_state = msg.data
        if msg.data == 10:  # MissionState.LANDING
            self._ctx.land_requested = True
        elif msg.data == 9:  # MissionState.RETURN_HOME
            self._ctx.rtl_requested = True

    def _on_swarm_state(self, msg: SwarmState) -> None:
        ctx = self._ctx

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
        eid = msg.event_type

        if eid in (SystemEvent.EVENT_EMERGENCY_LAND, SystemEvent.EVENT_RTL_TRIGGERED):
            self._ctx.emergency_stop_requested = False
            self._ctx.rtl_requested = True
            self._ctx.land_requested = True

    def _publish_formation_command(self, params: dict) -> None:
        msg = FormationCommand()
        msg.stamp = self.get_clock().now().to_msg()
        msg.sequence_num = self._ctx.command_sequence_num

        ftype = params.get('formation_type', 0)
        spacing = float(params.get('spacing_m', 0.0))
        if spacing <= 0.0:
            spacing = float(getattr(self, '_default_spacing_m', 5.0))
        if spacing <= 0.0:
            spacing = 5.0

        msg.formation_type = ftype
        msg.center_x = params.get('center_x', 0.0)
        msg.center_y = params.get('center_y', 0.0)
        msg.center_z = params.get('center_z', 0.0)
        msg.heading_deg = params.get('heading_deg', 0.0)
        msg.spacing_m = spacing
        msg.use_current_centroid = params.get(
            'use_current_centroid', False
        )
        msg.use_current_altitude = params.get(
            'use_current_altitude', False
        )
        msg.hold_after_reached = True
        msg.max_speed_mps = params.get('max_speed_mps', 0.0)
        msg.source_module = 'mode_manager'

        num_agents = len(self._agent_ids)
        msg.agent_ids = [int(a) for a in self._agent_ids]

        if ftype in (FORMATION_OKBASI, FORMATION_V, FORMATION_CIZGI) and num_agents > 0:
            try:
                alpha = math.radians(45.0)
                offsets = compute_slot_offsets(ftype, num_agents, spacing, alpha)
                msg.offset_x = [float(o[0]) for o in offsets]
                msg.offset_y = [float(o[1]) for o in offsets]
                msg.offset_z = [float(o[2]) for o in offsets]
            except Exception as e:
                self.get_logger().error(f'Slot offset hesaplama hatası: {e}')
                msg.offset_x = [0.0] * num_agents
                msg.offset_y = [0.0] * num_agents
                msg.offset_z = [0.0] * num_agents
        else:
            msg.offset_x = [0.0] * num_agents
            msg.offset_y = [0.0] * num_agents
            msg.offset_z = [0.0] * num_agents

        self._formation_pub.publish(msg)

    def _publish_agent_setpoint(self, sp: dict) -> None:
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
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = event_type
        m.severity = severity
        m.source_agent_id = 0
        m.source_module = 'mode_manager'
        m.message = message
        self._event_pub.publish(m)


def main(args=None) -> None:
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
