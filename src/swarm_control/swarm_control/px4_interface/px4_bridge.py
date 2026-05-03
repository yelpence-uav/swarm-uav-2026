"""PX4 ile FSM arasında köprü kuran ana ROS2 node."""

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

from px4_msgs.msg import (
    BatteryStatus,
    EstimatorStatusFlags,
    HomePosition,
    ManualControlSetpoint,
    SensorGps,
    VehicleAttitude,
    VehicleGlobalPosition,
    VehicleLocalPosition,
    VehicleStatus,
)
from std_msgs.msg import String
from swarm_interfaces.msg import AgentStatus

from .telemetry_mapper import (
    map_attitude,
    map_battery,
    map_estimator,
    map_global_position,
    map_gps,
    map_home_position,
    map_local_position,
    map_manual_control,
    map_vehicle_status,
)
from .command_sender import CommandSender


_PX4_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=5,
)


class Px4BridgeNode(Node):
    """PX4 telemetrisini AgentStatus'a çeviren ve FSM komutlarını ileten."""

    def __init__(self) -> None:
        super().__init__('px4_bridge')

        self.declare_parameter('agent_id', 1)
        self.declare_parameter('publish_rate_hz', 10.0)
        self.declare_parameter('px4_namespace', '')

        self._agent_id: int = int(
            self.get_parameter('agent_id').value
        )
        publish_rate = float(
            self.get_parameter('publish_rate_hz').value
        )
        ns = self.get_parameter('px4_namespace').value
        self._px4_ns = ns if ns else f'drone_{self._agent_id}'

        self._status = AgentStatus()
        self._status.agent_id = self._agent_id

        self._cmd_sender = CommandSender(
            self,
            system_id=self._agent_id,
            px4_namespace=self._px4_ns,
        )

        self._setup_px4_subscriptions()

        self._status_pub = self.create_publisher(
            AgentStatus,
            f'/swarm/agent/drone{self._agent_id}/telemetry',
            10,
        )

        self.create_subscription(
            String,
            f'/swarm/agent/drone{self._agent_id}/commands',
            self._on_fsm_command,
            10,
        )

        self.create_timer(1.0 / publish_rate, self._publish_status)

        self.get_logger().info(
            f'Px4BridgeNode başlatıldı: agent_id={self._agent_id}, '
            f'publish_rate={publish_rate} Hz'
        )

    def _setup_px4_subscriptions(self) -> None:
        """PX4 telemetri topic'lerine abone olur."""
        ns = self._px4_ns
        subs = [
            (BatteryStatus,
             f'/{ns}/fmu/out/battery_status', self._on_battery),
            (VehicleStatus,
             f'/{ns}/fmu/out/vehicle_status', self._on_vehicle_status),
            (VehicleLocalPosition,
             f'/{ns}/fmu/out/vehicle_local_position', self._on_local_pos),
            (EstimatorStatusFlags,
             f'/{ns}/fmu/out/estimator_status_flags', self._on_estimator),
            (SensorGps,
             f'/{ns}/fmu/out/vehicle_gps_position', self._on_gps),
            (VehicleGlobalPosition,
             f'/{ns}/fmu/out/vehicle_global_position', self._on_global_pos),
            (HomePosition,
             f'/{ns}/fmu/out/home_position', self._on_home),
            (VehicleAttitude,
             f'/{ns}/fmu/out/vehicle_attitude', self._on_attitude),
            (ManualControlSetpoint,
             f'/{ns}/fmu/out/manual_control_setpoint',
             self._on_manual_control),
        ]
        for msg_type, topic, cb in subs:
            self.create_subscription(msg_type, topic, cb, _PX4_QOS)

    def _on_battery(self, msg: BatteryStatus) -> None:
        map_battery(msg, self._status)

    def _on_vehicle_status(self, msg: VehicleStatus) -> None:
        map_vehicle_status(msg, self._status)

    def _on_local_pos(self, msg: VehicleLocalPosition) -> None:
        map_local_position(msg, self._status)

    def _on_estimator(self, msg: EstimatorStatusFlags) -> None:
        map_estimator(msg, self._status)

    def _on_gps(self, msg: SensorGps) -> None:
        map_gps(msg, self._status)

    def _on_global_pos(self, msg: VehicleGlobalPosition) -> None:
        map_global_position(msg, self._status)

    def _on_home(self, msg: HomePosition) -> None:
        map_home_position(msg, self._status)

    def _on_attitude(self, msg: VehicleAttitude) -> None:
        map_attitude(msg, self._status)

    def _on_manual_control(self, msg: ManualControlSetpoint) -> None:
        map_manual_control(msg, self._status)

    def _on_fsm_command(self, msg: String) -> None:
        """
        FSM'den gelen string komutu PX4'e iletir.

        Args:
            msg: Komut içeren String mesajı.
                 Desteklenen değerler: arm, disarm, takeoff[:irtifa],
                 land, rtl, offboard.
        """
        cmd = msg.data.strip().lower()

        if cmd == 'arm':
            self._cmd_sender.arm()
        elif cmd == 'disarm':
            self._cmd_sender.disarm()
        elif cmd.startswith('takeoff'):
            altitude = 10.0
            if ':' in cmd:
                try:
                    altitude = float(cmd.split(':', 1)[1])
                except ValueError:
                    self.get_logger().warning(
                        f'Geçersiz takeoff irtifası: {cmd}'
                    )
            self._cmd_sender.takeoff(altitude_m=altitude)
        elif cmd == 'land':
            self._cmd_sender.land()
        elif cmd == 'rtl':
            self._cmd_sender.return_home()
        elif cmd == 'offboard':
            self._cmd_sender.set_offboard_mode()
        else:
            self.get_logger().warning(f'Bilinmeyen FSM komutu: {cmd}')

    def _publish_status(self) -> None:
        self._status.stamp = self.get_clock().now().to_msg()
        self._status_pub.publish(self._status)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Px4BridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
