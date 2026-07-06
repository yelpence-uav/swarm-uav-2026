"""manual_command_node.py — Yarı-otonom (Görev 2) joystick yorumlayıcısı.

Operatörün analog komutunu (SwarmControlCommand) sürü-seviyesi
FormationCommand'a çevirir; formation_node bunu her İHA için bireysel hız
komutuna dönüştürür. Yani bu node, Görev 2'de FormationCommand'ın TEK
yazıcısıdır (Görev 1 otonom akışında o rolü mission_fsm üstlenir; iki mod
aynı anda çalışmaz).

ZİNCİR:
    /swarm/public/control/command (SwarmControlCommand, joystick)
        -> manual_kinematics (centroid hız/ivme + tilt)
        -> /swarm/public/formation/target (FormationCommand)
        -> formation_node -> AgentSetpoint (bireysel vx,vy,vz)

EMNİYET (SwarmControlCommand.msg kuralı):
    command_valid AND deadman_pressed AND komut taze (deadman_timeout_s
    içinde) olmadıkça HAREKET YOK -> HOLD: centroid dondurulur, hız 0'a
    sönümlenir, son merkez/heading korunur.

KULLANIM:
    ros2 run swarm_core manual_command_node --ros-args \\
        -p agent_ids:="[1,2,3]" -p formation_type:=2
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

from swarm_interfaces.msg import FormationCommand, SwarmControlCommand

from .formation_geometry import compute_slot_offsets
from .manual_kinematics import (
    CentroidState,
    MotionLimits,
    apply_tilt,
    maneuver_step,
    swarm_movement_step,
)

_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_MESH_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


class ManualCommandNode(Node):
    """Joystick (SwarmControlCommand) -> FormationCommand yorumlayıcısı."""

    def __init__(self) -> None:
        """Parametreler, durum, publisher/subscriber ve döngü kurulur."""
        super().__init__('manual_command_node')

        self._declare_params()

        self._state = CentroidState(
            x=0.0, y=0.0, z=self._initial_alt_down_m, heading_deg=0.0,
        )
        self._last_cmd: SwarmControlCommand | None = None
        self._last_cmd_time: float | None = None
        self._last_step_time: float | None = None
        self._sequence_num = 0
        self._formation_type = self._initial_formation_type
        self._spacing_m = self._initial_spacing_m

        self._cmd_pub = self.create_publisher(
            FormationCommand,
            '/swarm/public/formation/target',
            _RELIABLE_QOS,
        )
        self.create_subscription(
            SwarmControlCommand,
            '/swarm/public/control/command',
            self._on_control_command,
            _MESH_QOS,
        )

        self._timer = self.create_timer(
            1.0 / self._publish_rate_hz, self._on_timer
        )

        self.get_logger().info(
            f'ManualCommandNode baslatildi: agent_ids={self._agent_ids}, '
            f'rate={self._publish_rate_hz}Hz, '
            f'v_max={self._limits.v_max_xy}m/s, '
            f'a_max={self._limits.a_max_xy}m/s^2'
        )

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanımlar ve sınıf alanlarına okur."""
        self.declare_parameter('agent_ids', [1, 2, 3])
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('initial_formation_type', 2)  # V
        self.declare_parameter('initial_spacing_m', 2.0)
        self.declare_parameter('wing_alpha_deg', 45.0)
        self.declare_parameter('initial_alt_down_m', -5.0)  # 5 m irtifa
        self.declare_parameter('deadman_timeout_s', 0.5)
        # Hareket tavanları
        self.declare_parameter('v_max_xy', 3.0)
        self.declare_parameter('v_max_z', 1.5)
        self.declare_parameter('a_max_xy', 2.0)
        self.declare_parameter('a_max_z', 1.0)
        self.declare_parameter('yaw_rate_max_deg_s', 45.0)
        self.declare_parameter('tilt_max_deg', 15.0)

        self._agent_ids = [
            int(a) for a in self.get_parameter('agent_ids').value
        ]
        self._publish_rate_hz = float(
            self.get_parameter('publish_rate_hz').value
        )
        self._initial_formation_type = int(
            self.get_parameter('initial_formation_type').value
        )
        self._initial_spacing_m = float(
            self.get_parameter('initial_spacing_m').value
        )
        self._wing_alpha_rad = math.radians(
            float(self.get_parameter('wing_alpha_deg').value)
        )
        self._initial_alt_down_m = float(
            self.get_parameter('initial_alt_down_m').value
        )
        self._deadman_timeout_s = float(
            self.get_parameter('deadman_timeout_s').value
        )
        self._limits = MotionLimits(
            v_max_xy=float(self.get_parameter('v_max_xy').value),
            v_max_z=float(self.get_parameter('v_max_z').value),
            a_max_xy=float(self.get_parameter('a_max_xy').value),
            a_max_z=float(self.get_parameter('a_max_z').value),
            yaw_rate_max_deg_s=float(
                self.get_parameter('yaw_rate_max_deg_s').value
            ),
            tilt_max_deg=float(self.get_parameter('tilt_max_deg').value),
        )

    def _on_control_command(self, msg: SwarmControlCommand) -> None:
        """Gelen joystick komutunu ve alım zamanını saklar.

        Formasyon değişim isteği gelirse tip/aralık güncellenir.
        """
        self._last_cmd = msg
        self._last_cmd_time = self.get_clock().now().nanoseconds * 1e-9
        if msg.formation_change_requested and msg.requested_formation != 0:
            self._formation_type = int(msg.requested_formation)
            if msg.requested_spacing_m > 0.0:
                self._spacing_m = float(msg.requested_spacing_m)

    def _deadman_ok(self, now: float) -> bool:
        """Hareketin uygulanabilir olup olmadığını döndürür.

        command_valid AND deadman_pressed AND taze (timeout içinde).
        """
        cmd = self._last_cmd
        if cmd is None or self._last_cmd_time is None:
            return False
        if not (cmd.command_valid and cmd.deadman_pressed):
            return False
        timeout = (
            cmd.deadman_timeout_s
            if cmd.deadman_timeout_s > 0.0
            else self._deadman_timeout_s
        )
        return (now - self._last_cmd_time) <= timeout

    def _on_timer(self) -> None:
        """Periyodik kinematik adım + FormationCommand yayını."""
        now = self.get_clock().now().nanoseconds * 1e-9
        if self._last_step_time is None:
            self._last_step_time = now
            return
        dt = now - self._last_step_time
        self._last_step_time = now
        if dt <= 0.0:
            return

        tilt_pitch = 0.0
        tilt_roll = 0.0

        if not self._deadman_ok(now):
            # HOLD: centroid dondur, hızı a_max ile 0'a sönümle (sıfır girdi
            # = sürü hareket modu adımı). Konum efektif olarak donar.
            result = swarm_movement_step(
                self._state, 0.0, 0.0, 0.0, 0.0, dt, self._limits
            )
            self._state = result.state
        else:
            cmd = self._last_cmd
            if cmd.mode == SwarmControlCommand.MODE_MANEUVER:
                result = maneuver_step(
                    self._state, cmd.pitch_cmd, cmd.roll_cmd,
                    cmd.yaw_cmd, cmd.throttle_cmd, dt, self._limits
                )
                tilt_pitch = result.tilt_pitch_deg
                tilt_roll = result.tilt_roll_deg
            else:
                # MODE_SWARM_MOVEMENT (ve bilinmeyen mod güvenli varsayılan).
                result = swarm_movement_step(
                    self._state, cmd.pitch_cmd, cmd.roll_cmd,
                    cmd.yaw_cmd, cmd.throttle_cmd, dt, self._limits
                )
            self._state = result.state

        self._publish_formation(tilt_pitch, tilt_roll)

    def _publish_formation(
        self, tilt_pitch_deg: float, tilt_roll_deg: float
    ) -> None:
        """Mevcut centroid durumundan FormationCommand üretip yayınlar."""
        n = len(self._agent_ids)
        if n == 0:
            return

        offsets = compute_slot_offsets(
            self._formation_type, n, self._spacing_m, self._wing_alpha_rad
        )
        if tilt_pitch_deg != 0.0 or tilt_roll_deg != 0.0:
            offsets = apply_tilt(offsets, tilt_pitch_deg, tilt_roll_deg)

        msg = FormationCommand()
        msg.stamp = self.get_clock().now().to_msg()
        msg.sequence_num = self._sequence_num
        self._sequence_num += 1

        msg.formation_type = self._formation_type
        msg.center_x = float(self._state.x)
        msg.center_y = float(self._state.y)
        msg.center_z = float(self._state.z)
        msg.heading_deg = float(self._state.heading_deg)
        msg.spacing_m = float(self._spacing_m)

        msg.use_current_centroid = False
        msg.use_current_altitude = False
        msg.rotate_towards_target = False
        msg.hold_after_reached = False

        msg.agent_ids = list(self._agent_ids)
        msg.offset_x = [float(o[0]) for o in offsets]
        msg.offset_y = [float(o[1]) for o in offsets]
        msg.offset_z = [float(o[2]) for o in offsets]

        msg.max_speed_mps = float(self._limits.v_max_xy)
        msg.source_module = 'manual_command_node'
        self._cmd_pub.publish(msg)


def main(args=None) -> None:
    """ROS2 entry point."""
    rclpy.init(args=args)
    node = ManualCommandNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
