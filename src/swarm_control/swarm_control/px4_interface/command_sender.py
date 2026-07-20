"""FSM kararlarini PX4 komutlarina cevirir ve yayinlar."""

from px4_msgs.msg import (
    OffboardControlMode,
    TrajectorySetpoint,
    VehicleCommand,
)

_NAN = float('nan')

# MAVLink komut kodlari
_CMD_ARM_DISARM = 400
_CMD_NAV_TAKEOFF = 22
_CMD_NAV_LAND = 21
_CMD_NAV_RTL = 20
_CMD_DO_SET_MODE = 176
_CMD_SET_GPS_GLOBAL_ORIGIN = 2015

# PX4 mod degerleri
_MAIN_MODE_OFFBOARD = 6
_MAIN_MODE_AUTO = 4

# AUTO alt modlari
_SUB_AUTO_LOITER = 3
_SUB_AUTO_LAND = 6
_SUB_AUTO_RTL = 5
_SUB_AUTO_TAKEOFF = 2


class CommandSender:
    """FSM -> PX4 komut koprusu."""

    def __init__(
        self,
        node,
        system_id: int = 1,
        component_id: int = 1,
        namespace: str = '',
    ):
        """PX4 publisher'larini olusturur.

        Args:
            node: ROS2 node referansi.
            system_id (int): MAV_SYS_ID.
            component_id (int): MAV_COMP_ID.
            namespace (str): PX4 topic namespace.
        """
        self._node = node
        self._sys_id = system_id
        self._comp_id = component_id

        self._cmd_pub = node.create_publisher(
            VehicleCommand,
            f'{namespace}/fmu/in/vehicle_command',
            10,
        )
        self._offboard_pub = node.create_publisher(
            OffboardControlMode,
            f'{namespace}/fmu/in/offboard_control_mode',
            10,
        )
        self._setpoint_pub = node.create_publisher(
            TrajectorySetpoint,
            f'{namespace}/fmu/in/trajectory_setpoint',
            10,
        )

# VehicleCommand yardimcisi

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
        """VehicleCommand mesaji olusturup yayinlar."""
        msg = VehicleCommand()
        ts = self._node.get_clock().now().nanoseconds
        msg.timestamp = int(ts / 1000)
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

# Arm / Disarm

    def arm(self) -> None:
        """Motorlari arm eder."""
        self._send_vehicle_command(
            _CMD_ARM_DISARM, param1=1.0
        )

    def disarm(self) -> None:
        """Motorlari disarm eder."""
        self._send_vehicle_command(
            _CMD_ARM_DISARM, param1=0.0
        )

# Mod degistirme

    def set_offboard_mode(self) -> None:
        """OFFBOARD moduna gecer."""
        self._send_vehicle_command(
            _CMD_DO_SET_MODE,
            param1=1.0,
            param2=float(_MAIN_MODE_OFFBOARD),
        )

    def set_auto_loiter_mode(self) -> None:
        """AUTO LOITER moduna gecer."""
        self._send_vehicle_command(
            _CMD_DO_SET_MODE,
            param1=1.0,
            param2=float(_MAIN_MODE_AUTO),
            param3=float(_SUB_AUTO_LOITER),
        )

# Kalkis / inis / eve donus

    def takeoff(self, altitude_m: float = 10.0) -> None:
        """Belirtilen irtifaya kalkar.

        Args:
            altitude_m (float): Hedef irtifa (m).
        """
        self._send_vehicle_command(
            _CMD_NAV_TAKEOFF, param7=altitude_m
        )

    def land(self) -> None:
        """Yerinde inis yapar."""
        self._send_vehicle_command(_CMD_NAV_LAND)

    def return_home(self) -> None:
        """Home konumuna doner (RTL)."""
        self._send_vehicle_command(_CMD_NAV_RTL)

# Offboard streaming

    def publish_offboard_position_mode(self) -> None:
        """Pozisyon kontrol modunu PX4'e bildirir."""
        msg = OffboardControlMode()
        ts = self._node.get_clock().now().nanoseconds
        msg.timestamp = int(ts / 1000)
        msg.position = True
        msg.velocity = False
        msg.acceleration = False
        msg.attitude = False
        msg.body_rate = False
        self._offboard_pub.publish(msg)

    def publish_offboard_position_velocity_mode(
        self,
    ) -> None:
        """Pozisyon + hiz feed-forward modunu bildirir."""
        msg = OffboardControlMode()
        ts = self._node.get_clock().now().nanoseconds
        msg.timestamp = int(ts / 1000)
        msg.position = True
        msg.velocity = True
        msg.acceleration = False
        msg.attitude = False
        msg.body_rate = False
        self._offboard_pub.publish(msg)

    def publish_offboard_velocity_mode(self) -> None:
        """Saf hiz kontrol modunu bildirir."""
        msg = OffboardControlMode()
        ts = self._node.get_clock().now().nanoseconds
        msg.timestamp = int(ts / 1000)
        msg.position = False
        msg.velocity = True
        msg.acceleration = False
        msg.attitude = False
        msg.body_rate = False
        self._offboard_pub.publish(msg)

    def publish_velocity_setpoint(
        self,
        vx: float,
        vy: float,
        vz: float,
        yaw_rad: float = 0.0,
    ) -> None:
        """Saf hiz setpoint'i gonderir (pozisyon NaN)."""
        msg = TrajectorySetpoint()
        ts = self._node.get_clock().now().nanoseconds
        msg.timestamp = int(ts / 1000)
        msg.position = [_NAN, _NAN, _NAN]
        msg.velocity = [
            float(vx), float(vy), float(vz),
        ]
        msg.acceleration = [_NAN, _NAN, _NAN]
        msg.yaw = float(yaw_rad)
        msg.yawspeed = _NAN
        self._setpoint_pub.publish(msg)

    def publish_position_setpoint(
        self,
        x: float,
        y: float,
        z: float,
        yaw_rad: float = 0.0,
    ) -> None:
        """Pozisyon setpoint'i gonderir (NED).

        Args:
            x (float): NED X (m).
            y (float): NED Y (m).
            z (float): NED Z (m), asagi pozitif.
            yaw_rad (float): Yaw acisi (rad).
        """
        msg = TrajectorySetpoint()
        ts = self._node.get_clock().now().nanoseconds
        msg.timestamp = int(ts / 1000)
        msg.position = [float(x), float(y), float(z)]
        msg.velocity = [_NAN, _NAN, _NAN]
        msg.acceleration = [_NAN, _NAN, _NAN]
        msg.yaw = float(yaw_rad)
        msg.yawspeed = _NAN
        self._setpoint_pub.publish(msg)

    def publish_position_velocity_setpoint(
        self,
        x: float,
        y: float,
        z: float,
        vx: float,
        vy: float,
        vz: float,
        yaw_rad: float = 0.0,
    ) -> None:
        """Pozisyon + hiz feed-forward setpoint'i gonderir.

        Args:
            x (float): NED X (m).
            y (float): NED Y (m).
            z (float): NED Z (m).
            vx (float): NED X hizi (m/s).
            vy (float): NED Y hizi (m/s).
            vz (float): NED Z hizi (m/s).
            yaw_rad (float): Yaw acisi (rad).
        """
        msg = TrajectorySetpoint()
        ts = self._node.get_clock().now().nanoseconds
        msg.timestamp = int(ts / 1000)
        msg.position = [float(x), float(y), float(z)]
        msg.velocity = [
            float(vx), float(vy), float(vz),
        ]
        msg.acceleration = [_NAN, _NAN, _NAN]
        msg.yaw = float(yaw_rad)
        msg.yawspeed = _NAN
        self._setpoint_pub.publish(msg)

    def set_gps_global_origin(
        self,
        lat_deg: float,
        lon_deg: float,
        alt_amsl_m: float,
    ) -> None:
        """Surumun ortak NED origin'ini PX4'e bildirir."""
        self._send_vehicle_command(
            _CMD_SET_GPS_GLOBAL_ORIGIN,
            param5=lat_deg * 1e7,
            param6=lon_deg * 1e7,
            param7=float(alt_amsl_m),
        )
