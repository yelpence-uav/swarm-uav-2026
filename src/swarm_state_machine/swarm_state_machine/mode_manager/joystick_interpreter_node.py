"""MAVROS RC girdisini SwarmControlCommand mesajına dönüştüren düğüm.

MAVROS'un /mavros/manual_control/control mesajını okur, normalize
ederek SwarmControlCommand mesajına dönüştürür ve
/swarm/internal/control/command'a yayınlar.

Contract (§4.2):
  joystick_interpreter_node.py → /swarm/internal/control/command
    [SwarmControlCommand.msg]
  → proxy → /swarm/public/control/command
  → mode_manager/movement_mode.py / mode_manager/maneuver_mode.py

Yayın frekansı: 20-50 Hz (contract'ta belirtilmiş).

GCS arayüzünden gelen mod değişimleri ve formasyon komutları bu
node tarafından SwarmControlCommand'a gömülür.
"""

from collections import namedtuple

from mavros_msgs.msg import ManualControl

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_interfaces.msg import SwarmControlCommand

_MavrosManual = namedtuple('_MavrosManual', [
    'pitch', 'roll', 'yaw', 'throttle',
    'aux1', 'aux2', 'aux3', 'aux4', 'aux5', 'aux6',
])

_PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


class JoystickInterpreterNode(Node):
    """MAVROS ManualControl - SwarmControlCommand dönüştürücü."""

    def __init__(self) -> None:
        super().__init__('joystick_interpreter_node')

        self._declare_params()

        self._sequence_num = 0
        self._active_mode = SwarmControlCommand.MODE_SWARM_MOVEMENT
        self._formation_change_requested = False
        self._requested_formation = 0
        self._requested_spacing_m = 5.0

        self._setup_publishers()
        self._setup_subscribers()

        self.get_logger().info(
            f'JoystickInterpreterNode basladi: {self._deadman_channel}'
        )

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanımlar ve okur."""
        self.declare_parameter('publish_hz', 30.0)
        self.declare_parameter('deadman_channel', 'aux1')
        self.declare_parameter('deadman_threshold', 0.5)
        self.declare_parameter('deadman_timeout_s', 0.5)
        self.declare_parameter('max_speed_mps', 2.0)
        self.declare_parameter('max_yaw_rate_deg_s', 30.0)
        self.declare_parameter('max_tilt_deg', 15.0)

        self._publish_hz = float(
            self.get_parameter('publish_hz').value
        )
        self._deadman_channel = str(
            self.get_parameter('deadman_channel').value
        )
        self._deadman_threshold = float(
            self.get_parameter('deadman_threshold').value
        )
        self._deadman_timeout_s = float(
            self.get_parameter('deadman_timeout_s').value
        )
        self._max_speed_mps = float(
            self.get_parameter('max_speed_mps').value
        )
        self._max_yaw_rate_deg_s = float(
            self.get_parameter('max_yaw_rate_deg_s').value
        )
        self._max_tilt_deg = float(
            self.get_parameter('max_tilt_deg').value
        )

    def _setup_publishers(self) -> None:
        """Aciklama: SwarmControlCommand publisher'ını oluşturur."""
        self._cmd_pub = self.create_publisher(
            SwarmControlCommand,
            '/swarm/internal/control/command',
            10,
        )

    def _setup_subscribers(self) -> None:
        """MAVROS joystick girdi aboneliğini oluşturur."""
        self.create_subscription(
            ManualControl,
            '/mavros/manual_control/control',
            self._on_mavros_manual_control,
            _PX4_QOS,
        )

    def _on_manual_control(self, msg: '_MavrosManual') -> None:
        """Normalize girdiyi SwarmControlCommand'a cevirir."""
        cmd = SwarmControlCommand()
        cmd.stamp = self.get_clock().now().to_msg()
        self._sequence_num += 1
        cmd.sequence_num = self._sequence_num

        deadman_value = self._read_aux_channel(msg)
        deadman_pressed = deadman_value > self._deadman_threshold
        cmd.command_valid = True
        cmd.deadman_pressed = deadman_pressed
        cmd.deadman_timeout_s = self._deadman_timeout_s

        cmd.mode = self._active_mode

        cmd.pitch_cmd = self._clamp(msg.pitch)
        cmd.roll_cmd = self._clamp(msg.roll)
        cmd.yaw_cmd = self._clamp(msg.yaw)
        cmd.throttle_cmd = self._clamp(msg.throttle * 2.0 - 1.0)

        cmd.takeoff = False
        cmd.land = False
        cmd.rtl = False
        cmd.emergency_stop = False

        cmd.formation_change_requested = self._formation_change_requested
        cmd.requested_formation = self._requested_formation
        cmd.requested_spacing_m = self._requested_spacing_m

        if self._formation_change_requested:
            self._formation_change_requested = False

        cmd.max_speed_mps = self._max_speed_mps
        cmd.max_yaw_rate_deg_s = self._max_yaw_rate_deg_s
        cmd.max_tilt_deg = self._max_tilt_deg
        cmd.source_module = 'joystick_interpreter'

        self._cmd_pub.publish(cmd)

    def _on_mavros_manual_control(self, msg: ManualControl) -> None:
        """MAVROS ManualControl'u normalize edip _on_manual_control'a verir.

        MAVLink MANUAL_CONTROL aralığı [-1000, 1000]; sürü [-1, 1].
        x=pitch, y=roll, r=yaw, z=throttle(0..1000). aux1..aux6 doğrudan.
        Aux aralıkları gerçek kumandayla kontrol edilmeli.
        """
        norm = _MavrosManual(
            pitch=self._clamp(msg.x / 1000.0),
            roll=self._clamp(msg.y / 1000.0),
            yaw=self._clamp(msg.r / 1000.0),
            throttle=self._clamp(msg.z / 1000.0, 0.0, 1.0),
            aux1=msg.aux1, aux2=msg.aux2, aux3=msg.aux3,
            aux4=msg.aux4, aux5=msg.aux5, aux6=msg.aux6,
        )
        self._on_manual_control(norm)

    def _read_aux_channel(self, msg: '_MavrosManual') -> float:
        """Yapılandırılmış deadman kanalını okur."""
        channel_map = {
            'aux1': getattr(msg, 'aux1', 0.0),
            'aux2': getattr(msg, 'aux2', 0.0),
            'aux3': getattr(msg, 'aux3', 0.0),
            'aux4': getattr(msg, 'aux4', 0.0),
            'aux5': getattr(msg, 'aux5', 0.0),
            'aux6': getattr(msg, 'aux6', 0.0),
        }
        return channel_map.get(self._deadman_channel, 0.0)

    @staticmethod
    def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
        """Değeri sınırlandırır."""
        return max(lo, min(hi, value))

    def set_control_mode(self, mode: int) -> None:
        """GCS mod değişimi."""
        self._active_mode = mode
        self.get_logger().info(
            f'Mod degisti: {mode}'
        )

    def set_formation(
        self, formation_type: int, spacing_m: float = 5.0
    ) -> None:
        """GCS formasyon değişimi."""
        self._formation_change_requested = True
        self._requested_formation = formation_type
        self._requested_spacing_m = spacing_m
        self.get_logger().info(
            f'Formasyon degisikligi: {formation_type}'
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = JoystickInterpreterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
