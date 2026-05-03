"""FSM komutlarını PX4 VehicleCommand mesajlarına çeviren sınıf."""

from px4_msgs.msg import (
    OffboardControlMode,
    TrajectorySetpoint,
    VehicleCommand,
)


_CMD_ARM_DISARM = 400
_CMD_NAV_TAKEOFF = 22
_CMD_NAV_LAND = 21
_CMD_NAV_RTL = 20
_CMD_DO_SET_MODE = 176

_MAIN_MODE_OFFBOARD = 6
_MAIN_MODE_AUTO = 4

_SUB_AUTO_LOITER = 3
_SUB_AUTO_LAND = 6
_SUB_AUTO_RTL = 5
_SUB_AUTO_TAKEOFF = 2


class CommandSender:
    """FSM kararlarını PX4'e ileten komut gönderici.

    Kullanım:
        sender = CommandSender(node, system_id=1)
        sender.arm()
        sender.takeoff(altitude_m=10.0)
        sender.land()
    """

    def __init__(
        self, node, system_id: int = 1,
        component_id: int = 1, px4_namespace: str = ''
    ):
        """
        Args:
            node: Publisher oluşturmak için kullanılan ROS2 node.
            system_id: PX4 MAV_SYS_ID, drone numarasıyla eşleşir.
            component_id: MAV_COMP_ID, varsayılan 1.
            px4_namespace: PX4 topic namespace (ör. 'drone_1').
        """
        self._node = node
        self._sys_id = system_id
        self._comp_id = component_id
        ns = px4_namespace if px4_namespace else f'drone_{system_id}'

        self._cmd_pub = node.create_publisher(
            VehicleCommand, f'/{ns}/fmu/in/vehicle_command', 10
        )
        self._offboard_pub = node.create_publisher(
            OffboardControlMode,
            f'/{ns}/fmu/in/offboard_control_mode', 10
        )
        self._setpoint_pub = node.create_publisher(
            TrajectorySetpoint,
            f'/{ns}/fmu/in/trajectory_setpoint', 10
        )

    def _send_vehicle_command(
        self,
        command: int,
        param1: float = 0.0,
        param2: float = 0.0,
        param3: float = 0.0,
        param4: float = 0.0,
        param5: float = 0.0,
        param6: float = 0.0,
        param7: float = 0.0,
    ) -> None:
        """
        VehicleCommand mesajı oluşturur ve PX4'e gönderir.

        Args:
            command: MAVLink komut kodu.
            param1-param7: Komuta özgü parametreler.
        """
        msg = VehicleCommand()
        msg.timestamp = int(self._node.get_clock().now().nanoseconds / 1000)
        msg.command = command
        msg.param1 = param1
        msg.param2 = param2
        msg.param3 = param3
        msg.param4 = param4
        msg.param5 = param5
        msg.param6 = param6
        msg.param7 = param7
        msg.target_system = self._sys_id
        msg.target_component = self._comp_id
        msg.source_system = self._sys_id
        msg.source_component = self._comp_id
        msg.from_external = True
        self._cmd_pub.publish(msg)

    def arm(self) -> None:
        """Motorları arm eder."""
        self._send_vehicle_command(_CMD_ARM_DISARM, param1=1.0)

    def disarm(self) -> None:
        """Motorları disarm eder."""
        self._send_vehicle_command(_CMD_ARM_DISARM, param1=0.0)

    def set_offboard_mode(self) -> None:
        """OFFBOARD moduna geçer."""
        self._send_vehicle_command(
            _CMD_DO_SET_MODE,
            param1=1.0,
            param2=float(_MAIN_MODE_OFFBOARD),
        )

    def set_auto_loiter_mode(self) -> None:
        """AUTO LOITER moduna geçer."""
        self._send_vehicle_command(
            _CMD_DO_SET_MODE,
            param1=1.0,
            param2=float(_MAIN_MODE_AUTO),
            param3=float(_SUB_AUTO_LOITER),
        )

    def takeoff(self, altitude_m: float = 10.0) -> None:
        """
        Belirtilen irtifaya kalkış yapar.

        Args:
            altitude_m: Hedef kalkış irtifası (metre).
        """
        self._send_vehicle_command(_CMD_NAV_TAKEOFF, param7=altitude_m)

    def land(self) -> None:
        """Bulunduğu konumda iniş yapar."""
        self._send_vehicle_command(_CMD_NAV_LAND)

    def return_home(self) -> None:
        """Home konumuna döner (RTL)."""
        self._send_vehicle_command(_CMD_NAV_RTL)

    def publish_offboard_position_mode(self) -> None:
        """OFFBOARD modunda pozisyon kontrolü kullandığını bildirir."""
        msg = OffboardControlMode()
        msg.timestamp = int(self._node.get_clock().now().nanoseconds / 1000)
        msg.position = True
        msg.velocity = False
        msg.acceleration = False
        msg.attitude = False
        msg.body_rate = False
        self._offboard_pub.publish(msg)

    def publish_position_setpoint(
        self,
        x: float,
        y: float,
        z: float,
        yaw_rad: float = 0.0,
    ) -> None:
        """
        NED çerçevesinde hedef pozisyon ve yaw gönderir.

        Args:
            x: Kuzey ekseni (metre).
            y: Doğu ekseni (metre).
            z: Aşağı ekseni (metre, pozitif aşağı).
            yaw_rad: Yaw açısı (radyan).
        """
        msg = TrajectorySetpoint()
        msg.timestamp = int(self._node.get_clock().now().nanoseconds / 1000)
        msg.position = [float(x), float(y), float(z)]
        msg.yaw = float(yaw_rad)
        self._setpoint_pub.publish(msg)
