"""Tek bir drone'un FSM'ini çalıştıran ROS2 node."""

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from std_msgs.msg import String
from swarm_interfaces.msg import AgentStatus, SwarmOrigin, SystemEvent
from swarm_interfaces.srv import AssignRole

from .agent_context import AgentContext
from .agent_health_monitor import HealthCheckResult, check as health_check
from .agent_states import AgentRole, AgentState, FlightMode
from .agent_transitions import evaluate_transitions
from .preflight_checker import run_preflight_checks


_ORIGIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

# Yere değme tespiti için dikey hız eşiği (m/s)
_GROUND_VEL_THR = 0.3


class AgentFsmNode(Node):
    """
    Tek bir drone'un FSM node'u.

    PX4 telemetrisini ve swarm event'lerini dinler, FSM geçişlerini
    değerlendirir ve AgentStatus yayınlar.
    """

    def __init__(self) -> None:
        super().__init__('agent_fsm_node')

        self._declare_params()

        self._ctx = AgentContext(
            agent_id=self._agent_id,
            sitl_mode=self._sitl_mode,
            battery_critical_voltage_v=self._batt_crit_v,
            target_altitude_m=self._target_altitude_m,
        )

        self._px4_landed: bool = False
        self._prev_pilot_override: bool = False

        self._setup_publishers()
        self._setup_subscribers()
        self._setup_services()

        self._timer = self.create_timer(
            1.0 / self._tick_hz, self._tick
        )

        self.get_logger().info(
            f'AgentFsmNode başlatıldı: agent_id={self._agent_id}'
        )

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanımlar ve okur."""
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('sitl_mode', False)
        self.declare_parameter('battery_critical_voltage_v', 13.6)
        self.declare_parameter('tick_hz', 10.0)
        self.declare_parameter('target_altitude_m', 10.0)

        self._agent_id: int = self.get_parameter('agent_id').value
        self._sitl_mode: bool = self.get_parameter('sitl_mode').value
        self._batt_crit_v: float = (
            self.get_parameter('battery_critical_voltage_v').value
        )
        self._tick_hz: float = self.get_parameter('tick_hz').value
        self._target_altitude_m: float = (
            self.get_parameter('target_altitude_m').value
        )

    def _setup_publishers(self) -> None:
        """AgentStatus, SystemEvent ve komut publisher'larını oluşturur."""
        aid = self._agent_id
        self._status_pub = self.create_publisher(
            AgentStatus,
            f'/swarm/agent/drone{aid}/status',
            10,
        )
        self._event_pub = self.create_publisher(
            SystemEvent,
            '/swarm/events/system',
            10,
        )
        self._command_pub = self.create_publisher(
            String,
            f'/swarm/agent/drone{aid}/commands',
            10,
        )

    def _setup_subscribers(self) -> None:
        """Telemetri, event ve origin aboneliklerini oluşturur."""
        aid = self._agent_id

        self.create_subscription(
            AgentStatus,
            f'/swarm/agent/drone{aid}/telemetry',
            self._on_telemetry,
            10,
        )
        self.create_subscription(
            SystemEvent,
            '/swarm/events/system',
            self._on_event,
            10,
        )
        self.create_subscription(
            SwarmOrigin,
            '/swarm/origin',
            self._on_origin,
            _ORIGIN_QOS,
        )

    def _setup_services(self) -> None:
        """AssignRole servisini oluşturur."""
        aid = self._agent_id
        self.create_service(
            AssignRole,
            f'/swarm/agent/drone{aid}/assign_role',
            self._handle_assign_role,
        )

    def _tick(self) -> None:
        """FSM ana döngüsü — sağlık kontrolü ve geçiş değerlendirmesi."""
        ctx = self._ctx

        result: HealthCheckResult = health_check(ctx)

        if result.critical_fault and ctx.state != AgentState.FAILSAFE:
            self._transition(AgentState.FAILSAFE)
            self._pub_event(
                result.event_type,
                SystemEvent.SEVERITY_EMERGENCY,
                result.reason,
            )
        elif result.safety_hold and not ctx.hold_active:
            ctx.hold_active = True
            ctx.status_text = 'Safety hold active'
            self._pub_event(
                SystemEvent.EVENT_SAFETY_HOLD,
                SystemEvent.SEVERITY_WARNING,
                result.reason,
            )
        elif result.warning:
            ctx.status_text = result.reason
            self.get_logger().warn(result.reason)

        next_s = evaluate_transitions(ctx)
        if next_s is not None and next_s != ctx.state:
            self._transition(next_s)

        if (
            ctx.state == AgentState.FAILSAFE
            and ctx.kill_switch_active
            and not ctx.armed
            and self._px4_landed
            and abs(ctx.vel_z) < _GROUND_VEL_THR
            and ctx.attitude_stable
        ):
            self._transition(AgentState.LANDED)
            self._pub_event(
                SystemEvent.EVENT_AGENT_LANDED,
                SystemEvent.SEVERITY_INFO,
                'Kill switch: landed+disarmed+stable doğrulandı',
            )

        ctx.pending_state = None
        self._publish_status()

    def _transition(self, new_state: AgentState) -> None:
        """
        State geçişini uygular ve loglar.

        Args:
            new_state (AgentState): Geçilecek hedef state.
        """
        old = self._ctx.state
        self._ctx.set_state(new_state)

        if old == AgentState.ARMED and new_state == AgentState.TAKEOFF:
            self._ctx.mission_start_sequence_active = False

        self.get_logger().info(
            f'[agent {self._ctx.agent_id}] '
            f'{old.name} -> {new_state.name}'
        )

    def _on_event(self, msg: SystemEvent) -> None:
        """
        Swarm event bus'tan gelen olayları işler.

        Args:
            msg (SystemEvent): Gelen SystemEvent mesajı.
        """
        ctx = self._ctx
        aid = ctx.agent_id
        eid = msg.event_type
        tgt = msg.target_agent_id
        is_mine = tgt == 0 or tgt == aid

        if eid == SystemEvent.EVENT_MISSION_STARTED:
            if ctx.state == AgentState.IDLE:
                ctx.mission_start_sequence_active = True
                ctx.pending_state = AgentState.ARMING
            elif ctx.state == AgentState.ARMED:
                ctx.mission_start_sequence_active = True

        elif eid == SystemEvent.EVENT_RTL_TRIGGERED and is_mine:
            ctx.pending_state = AgentState.RETURN_HOME

        elif eid == SystemEvent.EVENT_EMERGENCY_LAND and is_mine:
            ctx.pending_state = AgentState.LANDING

        elif eid == SystemEvent.EVENT_SAFETY_HOLD:
            ctx.hold_active = True
            ctx.status_text = 'Safety hold active'

        elif eid == SystemEvent.EVENT_FAILSAFE_CLEARED:
            ctx.hold_active = False
            self._handle_failsafe_cleared()

        elif eid == SystemEvent.EVENT_PX4_LINK_LOST:
            ctx.px4_link_ok = False

        elif eid == SystemEvent.EVENT_OFFBOARD_LOST:
            ctx.offboard_active = False

        elif eid == SystemEvent.EVENT_GCS_LINK_LOST:
            ctx.gcs_link_ok = False
            ctx.status_text = 'GCS link lost'

        elif eid == SystemEvent.EVENT_GCS_LINK_RESTORED:
            ctx.gcs_link_ok = True
            ctx.status_text = ''

        elif eid == SystemEvent.EVENT_MEMBER_DETACH_STARTED:
            if tgt == aid:
                ctx.pending_state = AgentState.DETACHED

        elif eid == SystemEvent.EVENT_MEMBER_REJOIN_STARTED:
            if tgt == aid:
                passed, failures = run_preflight_checks(ctx)
                if passed:
                    ctx.pending_state = AgentState.REJOINING
                else:
                    ctx.status_text = (
                        'Rejoin preflight failed: '
                        + '; '.join(failures[:2])
                    )
                    self.get_logger().warn(
                        f'[agent {aid}] Rejoin preflight başarısız: '
                        + ', '.join(failures)
                    )

        elif eid in (
            SystemEvent.EVENT_MANEUVER_STARTED,
            SystemEvent.EVENT_ROTATION_STARTED,
        ):
            if is_mine and ctx.state == AgentState.IN_SWARM:
                ctx.pending_state = AgentState.EXECUTING_TASK

        elif eid in (
            SystemEvent.EVENT_MANEUVER_COMPLETED,
            SystemEvent.EVENT_ROTATION_COMPLETED,
            SystemEvent.EVENT_FORMATION_REACHED,
        ):
            if is_mine and ctx.state == AgentState.EXECUTING_TASK:
                ctx.pending_state = AgentState.IN_SWARM

        elif eid == SystemEvent.EVENT_MANEUVER_FAILED and is_mine:
            if ctx.state == AgentState.EXECUTING_TASK:
                ctx.status_text = 'Manevra başarısız, sürüye dönülüyor'
                ctx.pending_state = AgentState.IN_SWARM

        elif eid == SystemEvent.EVENT_AGENT_JOIN_REQUEST and is_mine:
            ctx.wants_to_join = True

        elif eid == SystemEvent.EVENT_KILL_SWITCH_ACTIVATED:
            ctx.kill_switch_active = True

        elif eid == SystemEvent.EVENT_RC_LINK_LOST:
            ctx.rc_link_ok = False

        elif eid == SystemEvent.EVENT_OSCILLATION_DETECTED:
            ctx.oscillation_detected = True

        elif eid == SystemEvent.EVENT_UNSTABLE_FLIGHT:
            ctx.unstable_flight = True

        elif eid == SystemEvent.EVENT_MISSION_COMPLETED:
            if ctx.state == AgentState.LANDED:
                ctx.pending_state = AgentState.IDLE

        elif eid == SystemEvent.EVENT_ORIGIN_SYNCED:
            ctx.origin_synced = True

        elif eid == SystemEvent.EVENT_GEOFENCE_VIOLATION:
            ctx.geofence_violated = True

    def _handle_failsafe_cleared(self) -> None:
        """
        EVENT_FAILSAFE_CLEARED alındığında drone'un fiziksel durumuna
        göre hedef state belirler.
        """
        ctx = self._ctx
        ctx.geofence_violated = False

        if not ctx.armed:
            ctx.pending_state = AgentState.IDLE
        elif self._px4_landed:
            ctx.pending_state = AgentState.LANDING
        else:
            ctx.pending_state = AgentState.RETURN_HOME

    def _on_origin(self, msg: SwarmOrigin) -> None:
        """
        Lider drone'un yayınladığı referans koordinat sistemini işler.

        Args:
            msg (SwarmOrigin): Gelen SwarmOrigin mesajı.
        """
        if msg.valid and msg.gps_fix_type >= 3:
            self._ctx.origin_synced = True
            self._ctx.origin_sequence = msg.sequence

    def _handle_assign_role(
        self,
        request: AssignRole.Request,
        response: AssignRole.Response,
    ) -> AssignRole.Response:
        """
        Swarm manager'dan gelen rol atama isteğini işler.

        Args:
            request: Rol atama isteği.
            response: Servis yanıtı.

        Returns:
            AssignRole.Response: İşlem sonucu.
        """
        ctx = self._ctx

        role_map = {
            AssignRole.Request.ROLE_LEADER:   AgentRole.LEADER,
            AssignRole.Request.ROLE_FOLLOWER: AgentRole.FOLLOWER,
            AssignRole.Request.ROLE_STANDBY:  AgentRole.STANDBY,
            AssignRole.Request.ROLE_DETACHED: AgentRole.DETACHED,
        }
        new_role = role_map.get(request.role)

        if new_role is None:
            response.success = False
            response.message = f'Bilinmeyen rol: {request.role}'
            return response

        ctx.role = new_role

        if new_role == AgentRole.STANDBY:
            ctx.set_state(AgentState.STANDBY)

        response.success = True
        response.message = f'Rol atandı: {ctx.role.name}'
        self.get_logger().info(
            f'[agent {ctx.agent_id}] Rol: {ctx.role.name}'
        )
        return response

    def _on_telemetry(self, msg: AgentStatus) -> None:
        """
        px4_bridge'den gelen AgentStatus'u AgentContext'e kopyalar.

        Args:
            msg: px4_bridge'in yayınladığı AgentStatus mesajı.
        """
        ctx = self._ctx
        prev_pilot = ctx.pilot_override_active

        ctx.px4_link_ok = msg.px4_link_ok
        ctx.armed = msg.armed
        ctx.offboard_enabled = msg.offboard_enabled
        ctx.offboard_active = msg.offboard_active
        ctx.flight_mode = FlightMode(msg.flight_mode)
        ctx.pilot_override_active = msg.pilot_override_active
        ctx.failsafe_active = msg.failsafe_active
        ctx.rc_signal_failsafe_active = msg.rc_signal_failsafe_active
        ctx.rc_link_ok = msg.rc_link_ok

        ctx.battery_voltage_v = msg.battery_voltage_v
        ctx.battery_current_a = msg.battery_current_a
        ctx.battery_percent = msg.battery_percent

        ctx.pos_x = msg.pos_x
        ctx.pos_y = msg.pos_y
        ctx.pos_z = msg.pos_z
        ctx.vel_x = msg.vel_x
        ctx.vel_y = msg.vel_y
        ctx.vel_z = msg.vel_z

        ctx.roll_deg = msg.roll_deg
        ctx.pitch_deg = msg.pitch_deg
        ctx.heading_deg = msg.heading_deg

        ctx.gps_fix_type = msg.gps_fix_type
        ctx.gps_hdop = msg.gps_hdop
        ctx.gps_satellites = msg.gps_satellites
        ctx.lat_deg = msg.lat_deg
        ctx.lon_deg = msg.lon_deg
        ctx.alt_amsl_m = msg.alt_amsl_m

        ctx.home_set = msg.home_set
        ctx.home_lat_deg = msg.home_lat_deg
        ctx.home_lon_deg = msg.home_lon_deg
        ctx.home_alt_amsl_m = msg.home_alt_amsl_m

        ctx.imu_healthy = msg.imu_healthy
        ctx.mag_healthy = msg.mag_healthy
        ctx.baro_healthy = msg.baro_healthy

        ctx.estimator_ok = msg.estimator_ok
        ctx.xy_valid = msg.xy_valid
        ctx.z_valid = msg.z_valid
        ctx.v_xy_valid = msg.v_xy_valid

        self._px4_landed = (
            not ctx.armed and abs(ctx.vel_z) < _GROUND_VEL_THR
        )

        if ctx.pilot_override_active and not prev_pilot:
            ctx.autonomous_control_paused = True
            ctx.status_text = (
                'Pilot override active, autonomous control paused'
            )
            self._pub_event(
                SystemEvent.EVENT_AGENT_PILOT_OVERRIDE,
                SystemEvent.SEVERITY_WARNING,
                'Manuel mod tespit edildi',
            )
        elif not ctx.pilot_override_active:
            ctx.autonomous_control_paused = False

        self._prev_pilot_override = ctx.pilot_override_active

    def _publish_status(self) -> None:
        """AgentContext'i AgentStatus mesajına dönüştürüp yayınlar."""
        ctx = self._ctx
        m = AgentStatus()
        m.stamp = self.get_clock().now().to_msg()

        m.agent_id = ctx.agent_id
        m.role = int(ctx.role)
        m.state = int(ctx.state)

        m.px4_link_ok = ctx.px4_link_ok
        m.gcs_link_ok = ctx.gcs_link_ok

        m.armed = ctx.armed
        m.offboard_enabled = ctx.offboard_enabled
        m.offboard_active = ctx.offboard_active
        m.flight_mode = int(ctx.flight_mode)
        m.pilot_override_active = ctx.pilot_override_active

        m.failsafe_active = ctx.failsafe_active
        m.healthy = ctx.healthy

        m.battery_percent = ctx.battery_percent
        m.battery_voltage_v = ctx.battery_voltage_v
        m.battery_current_a = ctx.battery_current_a

        m.pos_x = ctx.pos_x
        m.pos_y = ctx.pos_y
        m.pos_z = ctx.pos_z
        m.vel_x = ctx.vel_x
        m.vel_y = ctx.vel_y
        m.vel_z = ctx.vel_z

        m.heading_deg = ctx.heading_deg
        m.roll_deg = ctx.roll_deg
        m.pitch_deg = ctx.pitch_deg

        m.gps_fix_type = ctx.gps_fix_type
        m.gps_hdop = ctx.gps_hdop
        m.gps_satellites = ctx.gps_satellites

        m.lat_deg = ctx.lat_deg
        m.lon_deg = ctx.lon_deg
        m.alt_amsl_m = ctx.alt_amsl_m

        m.home_set = ctx.home_set
        m.home_lat_deg = ctx.home_lat_deg
        m.home_lon_deg = ctx.home_lon_deg
        m.home_alt_amsl_m = ctx.home_alt_amsl_m

        m.imu_healthy = ctx.imu_healthy
        m.mag_healthy = ctx.mag_healthy
        m.baro_healthy = ctx.baro_healthy

        m.estimator_ok = ctx.estimator_ok
        m.xy_valid = ctx.xy_valid
        m.z_valid = ctx.z_valid
        m.v_xy_valid = ctx.v_xy_valid

        m.origin_synced = ctx.origin_synced
        m.origin_sequence = ctx.origin_sequence

        m.rc_link_ok = ctx.rc_link_ok
        m.kill_switch_active = ctx.kill_switch_active
        m.rc_signal_failsafe_active = ctx.rc_signal_failsafe_active

        m.oscillation_detected = ctx.oscillation_detected
        m.unstable_flight = ctx.unstable_flight

        m.wants_to_join = ctx.wants_to_join
        m.ready_to_arm = ctx.ready_to_arm

        m.status_text = ctx.status_text

        self._status_pub.publish(m)

    def _pub_event(
        self,
        event_type: int,
        severity: int,
        message: str = '',
    ) -> None:
        """
        SystemEvent yayınlar.

        Args:
            event_type: SystemEvent.EVENT_* sabiti.
            severity: SystemEvent.SEVERITY_* seviyesi.
            message: İsteğe bağlı açıklama metni.
        """
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = event_type
        m.severity = severity
        m.source_agent_id = self._ctx.agent_id
        m.source_module = 'agent_fsm'
        m.message = message
        self._event_pub.publish(m)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AgentFsmNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
