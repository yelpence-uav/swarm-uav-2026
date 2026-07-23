# Copyright 2026 Yelpence
"""Suru manevra (pitch/roll/yaw) yurutme dugumu."""

import math
import time

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_core.formation_control.formation_geometry import latlon_to_ned

from swarm_interfaces.action import ExecuteManeuver
from swarm_interfaces.msg import (
    AgentSetpoint,
    AgentStatus,
    FormationCommand,
    SwarmControlCommand,
    SwarmOrigin,
    SystemEvent,
)

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

_ORIGIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


def euler_to_matrix(
    roll_rad: float, pitch_rad: float, yaw_rad: float
) -> tuple[tuple[float, float, float], ...]:
    """3D Euler acilarindan rotasyon matrisi uretir."""
    cr = math.cos(roll_rad)
    sr = math.sin(roll_rad)
    cp = math.cos(pitch_rad)
    sp = math.sin(pitch_rad)
    cy = math.cos(yaw_rad)
    sy = math.sin(yaw_rad)

    r00 = cy * cp
    r01 = cy * sp * sr - sy * cr
    r02 = cy * sp * cr + sy * sr

    r10 = sy * cp
    r11 = sy * sp * sr + cy * cr
    r12 = sy * sp * cr - cy * sr

    r20 = -sp
    r21 = cp * sr
    r22 = cp * cr

    return ((r00, r01, r02), (r10, r11, r12), (r20, r21, r22))


class ManeuverExecutorNode(Node):
    """Manevra hedeflerini hesaplayan dagitik ROS 2 dugumu."""

    def __init__(self) -> None:
        super().__init__('maneuver_executor')

        self.declare_parameter('agent_id', 1)
        self.declare_parameter('publish_rate_hz', 50.0)
        self.declare_parameter('max_speed_mps', 3.0)
        self.declare_parameter('max_tilt_deg', 25.0)

        self._agent_id = int(self.get_parameter('agent_id').value)
        hz_val = self.get_parameter('publish_rate_hz').value
        self._publish_rate_hz = float(hz_val)
        spd_val = self.get_parameter('max_speed_mps').value
        self._max_speed_mps = float(spd_val)
        t_val = self.get_parameter('max_tilt_deg').value
        self._max_tilt_deg = float(t_val)

        self._current_formation = None
        self._origin_lat = None
        self._origin_lon = None
        self._current_pos_x = 0.0
        self._current_pos_y = 0.0
        self._current_pos_z = 0.0
        self._current_lat = 0.0
        self._current_lon = 0.0
        self._gps_valid = False
        self._origin_synced = False
        self._xy_valid = False
        self._z_valid = False

        self._sequence_num = 0

        self._publishing_active = False
        self._maneuver_pitch_rad = 0.0
        self._maneuver_roll_rad = 0.0
        self._maneuver_yaw_rad = 0.0

        self._action_cb_group = ReentrantCallbackGroup()
        # Action adı per-drone: node her İHA'da agent_id ile çalışır; global
        # ad kullanılırsa 3 sunucu çakışır. Her drone'un mission1'i kendi
        # lokal maneuver_executor'ını çağırır (action mesh üzerinden gitmez).
        self._action_server = ActionServer(
            self,
            ExecuteManeuver,
            f'/drone_{self._agent_id}/maneuver/execute',
            execute_callback=self.execute_callback,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
            callback_group=self._action_cb_group
        )

        self._setup_publishers()
        self._setup_subscribers()

        self._timer = self.create_timer(
            1.0 / self._publish_rate_hz,
            self._publish_setpoint,
        )

        self.get_logger().info(f'Maneuver Node baslatildi: {self._agent_id}')

    def _setup_publishers(self) -> None:
        """Yerel setpoint yayincisini olusturur."""
        topic = f'/drone_{self._agent_id}/control/setpoint/raw'
        self._setpoint_pub = self.create_publisher(
            AgentSetpoint,
            topic,
            _BEST_EFFORT_QOS,
        )
        # Manevrayı yürüten birim, tamamlanma/başarısızlığı kendi bildirir
        # (precision_landing'in kendi bitişini bildirmesiyle aynı desen).
        # mission_fsm bu olayla QR manevra adımını ilerletir; proxy /public'e taşır.
        self._event_pub = self.create_publisher(
            SystemEvent, '/swarm/internal/events/system', _RELIABLE_QOS,
        )

    def _setup_subscribers(self) -> None:
        """Gerekli ROS 2 topic aboneliklerini kurar."""
        self.create_subscription(
            FormationCommand,
            '/swarm/public/formation/target',
            self._on_formation_command,
            _RELIABLE_QOS,
        )
        self.create_subscription(
            AgentStatus,
            f'/swarm/agent/drone{self._agent_id}/telemetry',
            self._on_agent_status,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            SwarmOrigin,
            '/swarm/public/origin',
            self._on_swarm_origin,
            _ORIGIN_QOS,
        )
        self.create_subscription(
            SwarmControlCommand,
            '/swarm/public/control/command',
            self._on_control_command,
            _BEST_EFFORT_QOS,
        )

    def _on_formation_command(self, msg: FormationCommand) -> None:
        self._current_formation = msg

    def _on_agent_status(self, msg: AgentStatus) -> None:
        self._current_pos_x = float(msg.pos_x)
        self._current_pos_y = float(msg.pos_y)
        self._current_pos_z = float(msg.pos_z)
        self._origin_synced = bool(msg.origin_synced)
        self._xy_valid = bool(msg.xy_valid)
        self._z_valid = bool(msg.z_valid)

        if msg.lat_deg != 0.0 or msg.lon_deg != 0.0:
            self._current_lat = float(msg.lat_deg)
            self._current_lon = float(msg.lon_deg)
            self._gps_valid = True

    def _on_swarm_origin(self, msg: SwarmOrigin) -> None:
        if msg.valid:
            self._origin_lat = float(msg.origin_lat_deg)
            self._origin_lon = float(msg.origin_lon_deg)

    def _on_control_command(self, msg: SwarmControlCommand) -> None:
        mode_m = SwarmControlCommand.MODE_MANEUVER
        if msg.mode != mode_m and self._publishing_active:
            self.get_logger().info('Mod degisti, manevra durdu.')
            self._publishing_active = False

    def goal_callback(self, goal_request):
        self.get_logger().info('Manevra talebi alindi.')
        return GoalResponse.ACCEPT

    def cancel_callback(self, goal_handle):
        self.get_logger().info('Manevra iptal edildi.')
        return CancelResponse.ACCEPT

    def execute_callback(self, goal_handle):
        """Manevrayi enterpolasyonla isletir."""
        goal = goal_handle.request
        target_p = math.radians(goal.pitch_deg)
        target_r = math.radians(goal.roll_deg)
        target_y = math.radians(goal.yaw_deg)

        duration = float(goal.duration_s)
        if duration <= 0.0:
            duration = 3.0

        start_time = time.time()
        feedback = ExecuteManeuver.Feedback()
        self.get_logger().info(f'Manevra basliyor. Sure: {duration}s')

        while rclpy.ok():
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                self._publishing_active = False
                self._pub_event(
                    SystemEvent.EVENT_MANEUVER_FAILED,
                    'Manevra iptal edildi',
                )
                return ExecuteManeuver.Result()

            now = time.time()
            elapsed = now - start_time
            if elapsed >= duration:
                break

            progress = elapsed / duration
            self._maneuver_pitch_rad = target_p * progress
            self._maneuver_roll_rad = target_r * progress
            self._maneuver_yaw_rad = target_y * progress
            self._publishing_active = True

            feedback.progress_percent = progress * 100.0
            feedback.current_pitch_deg = math.degrees(
                self._maneuver_pitch_rad
            )
            feedback.current_roll_deg = math.degrees(
                self._maneuver_roll_rad
            )
            feedback.current_yaw_deg = math.degrees(
                self._maneuver_yaw_rad
            )
            goal_handle.publish_feedback(feedback)
            time.sleep(0.05)

        self._maneuver_pitch_rad = target_p
        self._maneuver_roll_rad = target_r
        self._maneuver_yaw_rad = target_y
        self.get_logger().info('Manevra fazi tamamlandi.')

        if goal.hold_after_complete:
            self._publishing_active = True
        else:
            self._publishing_active = False

        goal_handle.succeed()
        self._pub_event(
            SystemEvent.EVENT_MANEUVER_COMPLETED,
            'Manevra tamamlandı',
        )

        res = ExecuteManeuver.Result()
        res.success = True
        res.result_message = 'Basarili.'
        res.final_pitch_error_deg = 0.0
        res.final_roll_error_deg = 0.0
        res.final_yaw_error_deg = 0.0
        res.final_max_position_error_m = 0.0
        return res

    def _pub_event(self, event_type, message):
        """SystemEvent yayınlar (manevra tamamlanma/başarısızlık bildirimi).

        Args:
            event_type: SystemEvent.EVENT_* sabiti.
            message: İnsan okunabilir açıklama.
        """
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = int(event_type)
        m.severity = SystemEvent.SEVERITY_INFO
        m.source_agent_id = self._agent_id
        m.source_module = 'maneuver_executor'
        m.message = message
        self._event_pub.publish(m)

    def _shared_to_local(
        self, shared_x: float, shared_y: float
    ) -> tuple[float, float]:
        """Shared NED koordinatini local NED'e cevirir."""
        if self._origin_lat is None or not self._gps_valid:
            return shared_x, shared_y

        cur_n, cur_e = latlon_to_ned(
            self._current_lat, self._current_lon,
            self._origin_lat, self._origin_lon,
        )
        lx = shared_x - cur_n + self._current_pos_x
        ly = shared_y - cur_e + self._current_pos_y
        return lx, ly

    def _publish_setpoint(self) -> None:
        """Manevra hedef noktasini hesaplar ve yayinlar."""
        if not self._publishing_active:
            return

        msg = self._current_formation
        if msg is None:
            return

        agent_ids = list(msg.agent_ids)
        if not agent_ids or self._agent_id not in agent_ids:
            return

        if not self._origin_synced or not (self._xy_valid and self._z_valid):
            return

        idx = agent_ids.index(self._agent_id)
        if (idx >= len(msg.offset_x) or
                idx >= len(msg.offset_y) or
                idx >= len(msg.offset_z)):
            return

        cx = float(msg.center_x)
        cy = float(msg.center_y)
        cz = float(msg.center_z)
        heading_rad = math.radians(msg.heading_deg)

        ox = float(msg.offset_x[idx])
        oy = float(msg.offset_y[idx])
        oz = float(msg.offset_z[idx])

        total_yaw = heading_rad + self._maneuver_yaw_rad
        rmat = euler_to_matrix(
            self._maneuver_roll_rad,
            self._maneuver_pitch_rad,
            total_yaw
        )

        dx_rot = rmat[0][0] * ox + rmat[0][1] * oy + rmat[0][2] * oz
        dy_rot = rmat[1][0] * ox + rmat[1][1] * oy + rmat[1][2] * oz
        dz_rot = rmat[2][0] * ox + rmat[2][1] * oy + rmat[2][2] * oz

        # MERKEZ SABİT KALMALI (şartname 5.1.2: "sürü merkezinin konumunu
        # SABİT tutarak eğilme"). Rotasyon sonrası TÜM slotların z değişim
        # ortalaması genelde sıfır DEĞİLDİR (asimetrik formasyonda; örn.
        # okbaşında iki kanat geride, pitch ikisini de aşağı iter) → sürü
        # topluca AŞAĞI kayar. Formasyon tarafındaki eğik poz (apply_tilt)
        # bu ortalamayı çıkarıyor ama maneuver_executor çıkarmıyordu; ikisi
        # devir tesliminde farklı z verince sürü SALINIYORDU (ölçüldü: pitch
        # geçişinde ~0.65 m'lik iki dipli salınım, sonra oturuyor). Buradaki
        # ortalama çıkarma iki tarafı hizalar: geçiş salınımı biter.
        oz_ort = 0.0
        n_slot = min(len(msg.offset_x), len(msg.offset_y), len(msg.offset_z))
        if n_slot > 0:
            for k in range(n_slot):
                zx = float(msg.offset_x[k])
                zy = float(msg.offset_y[k])
                zz = float(msg.offset_z[k])
                oz_ort += (rmat[2][0] * zx + rmat[2][1] * zy
                           + rmat[2][2] * zz)
            oz_ort /= n_slot

        shared_x = cx + dx_rot
        shared_y = cy + dy_rot
        shared_z = cz + (dz_rot - oz_ort)

        local_x, local_y = self._shared_to_local(shared_x, shared_y)

        out = AgentSetpoint()
        out.stamp = self.get_clock().now().to_msg()
        out.sequence_num = self._sequence_num
        self._sequence_num += 1

        out.agent_id = self._agent_id
        out.source = AgentSetpoint.SOURCE_MANEUVER_EXECUTOR
        out.priority = AgentSetpoint.PRIORITY_MANEUVER

        out.x = float(local_x)
        out.y = float(local_y)
        out.z = float(shared_z)
        out.position_valid = True

        out.velocity_valid = False
        out.acceleration_valid = False

        out.heading_deg = float(math.degrees(total_yaw))
        out.heading_valid = True
        out.yaw_rate_valid = False

        out.hold_position = False
        out.land_now = False
        out.rtl_now = False

        out.position_tolerance_m = 0.5
        out.heading_tolerance_deg = 5.0

        if msg.max_speed_mps > 0.0:
            out.max_speed_mps = float(msg.max_speed_mps)
        else:
            out.max_speed_mps = self._max_speed_mps

        out.max_acc_mps2 = 0.0
        out.source_module = 'maneuver_executor'

        self._setpoint_pub.publish(out)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ManeuverExecutorNode()
    try:
        executor = rclpy.executors.MultiThreadedExecutor()
        executor.add_node(node)
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:  # noqa: BLE001
            pass


if __name__ == '__main__':
    main()
