"""
agent_fsm_node.py

ROS 2 node: FSM tick, PX4/swarm topic yönetimi, AgentStatus yayını.
Her drone için ayrı bir instance çalışır.

Kullanım:
    ros2 run swarm_state_machine agent_fsm_node \
        --ros-args -p agent_id:=1
"""

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from px4_msgs.msg import (
    BatteryStatus,
    EstimatorStatusFlags,
    HomePosition,
    ManualControlSetpoint,
    SensorGps,
    VehicleAttitude,
    VehicleGlobalPosition,
    VehicleLandDetected,
    VehicleLocalPosition,
    VehicleStatus,
)
from swarm_interfaces.msg import AgentStatus, SwarmOrigin, SystemEvent
from swarm_interfaces.srv import AssignRole

from .agent_context import AgentContext
from .agent_health_monitor import HealthCheckResult, check as health_check
from .agent_states import AgentRole, AgentState, FlightMode
from .agent_transitions import evaluate_transitions
from .preflight_checker import run_preflight_checks

# PX4 sensor pipeline: BEST_EFFORT + VOLATILE
_PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

# SwarmOrigin: RELIABLE + TRANSIENT_LOCAL (yeni dronn'lar son değeri alır)
_ORIGIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

# PX4 nav_state → FlightMode (roadmap bölüm 14)
_NAV_STATE_MAP: dict[int, FlightMode] = {
    0: FlightMode.MANUAL,
    1: FlightMode.ALTCTL,
    2: FlightMode.POSCTL,
    3: FlightMode.AUTO_MISSION,
    4: FlightMode.AUTO_LOITER,
    5: FlightMode.AUTO_RTL,
    6: FlightMode.ACRO,
    14: FlightMode.OFFBOARD,
    15: FlightMode.STABILIZED,
    18: FlightMode.AUTO_LAND,
}

# Pilot override olarak değerlendirilen modlar
_PILOT_MODES = frozenset({
    FlightMode.MANUAL,
    FlightMode.ALTCTL,
    FlightMode.POSCTL,
    FlightMode.ACRO,
    FlightMode.STABILIZED,
})

# Kill switch FAILSAFE → LANDED doğrulaması için hız eşiği (m/s)
_GROUND_VEL_THR = 0.3


class AgentFsmNode(Node):
    """
    Tek bir İHA'nın FSM node'u.

    Çıktı: /swarm/agent/{agent_id}/status (AgentStatus)
    Servis: /swarm/agent/{agent_id}/assign_role (AssignRole)
    Dinler: /swarm/events/system, /swarm/origin, PX4 telemetri
    Yayınlar: /swarm/events/system (FSM event'leri için)
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
        self._px4_landed: bool = False       # VehicleLandDetected.landed
        self._prev_pilot_override: bool = False  # edge detection için
        self._setup_publishers()
        self._setup_subscribers()
        self._setup_services()
        self._timer = self.create_timer(
            1.0 / self._tick_hz, self._tick
        )
        self.get_logger().info(
            f'AgentFsmNode başlatıldı: agent_id={self._agent_id}'
        )

    # ------------------------------------------------------------------
    # Init helpers
    # ------------------------------------------------------------------

    def _declare_params(self) -> None:
        """ROS 2 parametrelerini tanımla ve oku."""
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('sitl_mode', False)
        self.declare_parameter('battery_critical_voltage_v', 13.6)
        self.declare_parameter('tick_hz', 10.0)
        self.declare_parameter('target_altitude_m', 10.0)

        self._agent_id: int = (
            self.get_parameter('agent_id').value
        )
        self._sitl_mode: bool = (
            self.get_parameter('sitl_mode').value
        )
        self._batt_crit_v: float = (
            self.get_parameter('battery_critical_voltage_v').value
        )
        self._tick_hz: float = (
            self.get_parameter('tick_hz').value
        )
        self._target_altitude_m: float = (
            self.get_parameter('target_altitude_m').value
        )

    def _setup_publishers(self) -> None:
        aid = self._agent_id
        self._status_pub = self.create_publisher(
            AgentStatus,
            f'/swarm/agent/{aid}/status',
            10,
        )
        self._event_pub = self.create_publisher(
            SystemEvent,
            '/swarm/events/system',
            10,
        )

    def _setup_subscribers(self) -> None:
        aid = self._agent_id
        pfx = f'/px4_{aid}/fmu/out'

        # PX4 telemetri abonelikleri
        px4_subs = [
            (VehicleLocalPosition,
             f'{pfx}/vehicle_local_position',
             self._on_local_pos),
            (VehicleStatus,
             f'{pfx}/vehicle_status',
             self._on_vehicle_status),
            (BatteryStatus,
             f'{pfx}/battery_status',
             self._on_battery),
            (EstimatorStatusFlags,
             f'{pfx}/estimator_status_flags',
             self._on_estimator),
            (SensorGps,
             f'{pfx}/vehicle_gps_position',
             self._on_gps),
            (VehicleGlobalPosition,
             f'{pfx}/vehicle_global_position',
             self._on_global_pos),
            (HomePosition,
             f'{pfx}/home_position',
             self._on_home),
            (VehicleAttitude,
             f'{pfx}/vehicle_attitude',
             self._on_attitude),
            (ManualControlSetpoint,
             f'{pfx}/manual_control_setpoint',
             self._on_manual_control),
            (VehicleLandDetected,
             f'{pfx}/vehicle_land_detected',
             self._on_land_detected),
        ]
        for msg_type, topic, cb in px4_subs:
            self.create_subscription(msg_type, topic, cb, _PX4_QOS)

        # Swarm event bus
        self.create_subscription(
            SystemEvent,
            '/swarm/events/system',
            self._on_event,
            10,
        )

        # Swarm origin
        self.create_subscription(
            SwarmOrigin,
            '/swarm/origin',
            self._on_origin,
            _ORIGIN_QOS,
        )

    def _setup_services(self) -> None:
        aid = self._agent_id
        self.create_service(
            AssignRole,
            f'/swarm/agent/{aid}/assign_role',
            self._handle_assign_role,
        )

    # ------------------------------------------------------------------
    # FSM tick
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        """FSM ana döngüsü. _tick_hz Hz'de çalışır."""
        ctx = self._ctx

        # 1. Sağlık kontrolü
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

        # 2. Geçiş değerlendirmesi
        next_s = evaluate_transitions(ctx)
        if next_s is not None and next_s != ctx.state:
            self._transition(next_s)

        # 3. Kill switch: FAILSAFE → LANDED doğrulaması (roadmap 7.1)
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

        # 4. pending_state sıfırla (tick başına bir kez tüketilir)
        ctx.pending_state = None

        # 5. AgentStatus yayınla
        self._publish_status()

    def _transition(self, new_state: AgentState) -> None:
        """State geçişini uygula ve log at."""
        old = self._ctx.state
        self._ctx.set_state(new_state)
        if old == AgentState.ARMED and new_state == AgentState.TAKEOFF:
            self._ctx.mission_start_sequence_active = False
        self.get_logger().info(
            f'[agent {self._ctx.agent_id}] '
            f'{old.name} -> {new_state.name}'
        )

    # ------------------------------------------------------------------
    # SystemEvent callback
    # ------------------------------------------------------------------

    def _on_event(self, msg: SystemEvent) -> None:
        """
        Gelen SystemEvent'e göre ctx ve pending_state günceller.

        Args:
            msg: Dinlenen SystemEvent mesajı.
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
                # Önceden arm edilmiş drone görev başlangıcını yakalar
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
        EVENT_FAILSAFE_CLEARED alındı.

        can_exit_failsafe koşul kontrolü _from_failsafe() içinde
        yapılır. Burada drone konumuna göre hedef state belirlenir.
        """
        ctx = self._ctx
        ctx.geofence_violated = False
        if not ctx.armed:
            ctx.pending_state = AgentState.IDLE
        elif self._px4_landed:
            # _from_failsafe LANDING'i işler → LANDED'a geçer
            ctx.pending_state = AgentState.LANDING
        else:
            ctx.pending_state = AgentState.RETURN_HOME

    # ------------------------------------------------------------------
    # Swarm callbacks
    # ------------------------------------------------------------------

    def _on_origin(self, msg: SwarmOrigin) -> None:
        """
        SwarmOrigin alındı.

        px4_interface SET_GPS_GLOBAL_ORIGIN uyguladıktan sonra
        origin_synced=True set edilmesi beklenir. Burada sadece
        sequence güncellenir; gerçek senkron px4_interface sorumluluğu.
        """
        if msg.valid and msg.gps_fix_type >= 3:
            self._ctx.origin_synced = True
            self._ctx.origin_sequence = msg.sequence

    # ------------------------------------------------------------------
    # AssignRole service
    # ------------------------------------------------------------------

    def _handle_assign_role(
        self,
        request: AssignRole.Request,
        response: AssignRole.Response,
    ) -> AssignRole.Response:
        """
        /swarm/agent/{id}/assign_role servis handler.

        Args:
            request: AssignRole.Request (role, target_agent_id, reason)
            response: AssignRole.Response (success, message)

        Returns:
            AssignRole.Response
        """
        ctx = self._ctx
        role_map = {
            AssignRole.Request.ROLE_LEADER: AgentRole.LEADER,
            AssignRole.Request.ROLE_FOLLOWER: AgentRole.FOLLOWER,
            AssignRole.Request.ROLE_STANDBY: AgentRole.STANDBY,
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

    # ------------------------------------------------------------------
    # PX4 telemetri callback'leri
    # ------------------------------------------------------------------

    def _on_local_pos(self, msg: VehicleLocalPosition) -> None:
        """VehicleLocalPosition → ctx pozisyon/hız/estimator alanları."""
        ctx = self._ctx
        ctx.pos_x = msg.x
        ctx.pos_y = msg.y
        ctx.pos_z = msg.z
        ctx.vel_x = msg.vx
        ctx.vel_y = msg.vy
        ctx.vel_z = msg.vz
        ctx.heading_deg = math.degrees(msg.heading)
        ctx.xy_valid = msg.xy_valid
        ctx.z_valid = msg.z_valid
        ctx.v_xy_valid = msg.v_xy_valid

    def _on_vehicle_status(self, msg: VehicleStatus) -> None:
        """VehicleStatus → arm, flight_mode, failsafe, RC alanları."""
        ctx = self._ctx
        ctx.px4_link_ok = True  # callback geldiyse link var
        ctx.armed = (
            msg.arming_state == VehicleStatus.ARMING_STATE_ARMED
        )
        ctx.failsafe_active = msg.failsafe
        ctx.ready_to_arm = msg.pre_flight_checks_pass
        ctx.rc_signal_failsafe_active = msg.rc_signal_lost

        fm = _NAV_STATE_MAP.get(msg.nav_state, FlightMode.UNKNOWN)
        ctx.flight_mode = fm
        ctx.offboard_active = fm == FlightMode.OFFBOARD
        # PX4 nav_state ikisini ayırt etmez; offboard_enabled telemetri
        # gelmeden önce False kalır, aktif olunca offboard_active ile eşit.
        ctx.offboard_enabled = ctx.offboard_active

        is_pilot = fm in _PILOT_MODES
        ctx.pilot_override_active = is_pilot
        if is_pilot and not self._prev_pilot_override:
            ctx.autonomous_control_paused = True
            ctx.status_text = (
                'Pilot override active, autonomous control paused'
            )
            self._pub_event(
                SystemEvent.EVENT_AGENT_PILOT_OVERRIDE,
                SystemEvent.SEVERITY_WARNING,
                'Manuel mod tespit edildi',
            )
        elif not is_pilot:
            ctx.autonomous_control_paused = False
        self._prev_pilot_override = is_pilot

    def _on_battery(self, msg: BatteryStatus) -> None:
        """BatteryStatus → batarya alanları."""
        ctx = self._ctx
        ctx.battery_voltage_v = msg.voltage_v
        ctx.battery_current_a = msg.current_a
        ctx.battery_percent = msg.remaining * 100.0

    def _on_estimator(self, msg: EstimatorStatusFlags) -> None:
        """EstimatorStatusFlags → imu/mag/baro sağlığı ve estimator_ok."""
        ctx = self._ctx
        ctx.imu_healthy = msg.cs_tilt_align
        ctx.mag_healthy = msg.cs_mag_consistent
        ctx.baro_healthy = msg.cs_baro_hgt and not msg.cs_baro_fault
        ctx.estimator_ok = msg.cs_tilt_align and msg.cs_yaw_align

    def _on_gps(self, msg: SensorGps) -> None:
        """SensorGps → GPS kalite alanları."""
        ctx = self._ctx
        ctx.gps_fix_type = msg.fix_type
        ctx.gps_hdop = msg.hdop
        ctx.gps_satellites = msg.satellites_used

    def _on_global_pos(self, msg: VehicleGlobalPosition) -> None:
        """VehicleGlobalPosition → global konum alanları."""
        ctx = self._ctx
        ctx.lat_deg = msg.lat
        ctx.lon_deg = msg.lon
        ctx.alt_amsl_m = msg.alt

    def _on_home(self, msg: HomePosition) -> None:
        """HomePosition → home konumu alanları."""
        ctx = self._ctx
        ctx.home_set = msg.valid_hpos and msg.valid_vpos
        ctx.home_lat_deg = msg.lat
        ctx.home_lon_deg = msg.lon
        ctx.home_alt_amsl_m = msg.alt

    def _on_attitude(self, msg: VehicleAttitude) -> None:
        """
        VehicleAttitude quaternion → roll_deg, pitch_deg.

        ZYX Euler dönüşümü: q = [w, x, y, z]
        """
        q = msg.q  # [w, x, y, z]
        sinr = 2.0 * (q[0] * q[1] + q[2] * q[3])
        cosr = 1.0 - 2.0 * (q[1] ** 2 + q[2] ** 2)
        self._ctx.roll_deg = math.degrees(math.atan2(sinr, cosr))

        sinp = 2.0 * (q[0] * q[2] - q[3] * q[1])
        sinp = max(-1.0, min(1.0, sinp))
        self._ctx.pitch_deg = math.degrees(math.asin(sinp))

    def _on_manual_control(self, msg: ManualControlSetpoint) -> None:
        """ManualControlSetpoint → rc_link_ok."""
        self._ctx.rc_link_ok = msg.valid

    def _on_land_detected(self, msg: VehicleLandDetected) -> None:
        """VehicleLandDetected → kill switch ve failsafe çıkış kararı için."""
        self._px4_landed = msg.landed

    # ------------------------------------------------------------------
    # AgentStatus publish
    # ------------------------------------------------------------------

    def _publish_status(self) -> None:
        """AgentContext'i AgentStatus.msg'e dönüştürüp yayınlar."""
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
        SystemEvent yayınla.

        Args:
            event_type: SystemEvent.EVENT_* sabiti.
            severity: SystemEvent.SEVERITY_* sabiti.
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
    """ROS 2 node giriş noktası."""
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
