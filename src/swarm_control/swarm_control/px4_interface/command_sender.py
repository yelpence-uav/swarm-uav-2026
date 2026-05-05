"""
command_sender.py

FSM kararlarını PX4'ün anlayacağı komutlara çevirir ve yayınlar.

Yayınlanan PX4 topic'leri:
- {namespace}/fmu/in/vehicle_command          → arm/disarm/mode/takeoff/land/RTL
- {namespace}/fmu/in/offboard_control_mode    → offboard kontrol türü (pozisyon/hız)
- {namespace}/fmu/in/trajectory_setpoint      → hedef pozisyon ve yaw

Bu sınıf bir node'a bağlıdır (publisher'ları oluşturmak için), ama node mantığı
içermez — px4_bridge çağırır.
"""

from px4_msgs.msg import (
    OffboardControlMode,
    TrajectorySetpoint,
    VehicleCommand,
)


# PX4 VehicleCommand komut kodları (MAVLink standardı)
_CMD_ARM_DISARM = 400          # param1=1.0 arm, 0.0 disarm
_CMD_NAV_TAKEOFF = 22          # param7 = irtifa
_CMD_NAV_LAND = 21
_CMD_NAV_RTL = 20              # Return to Launch
_CMD_DO_SET_MODE = 176         # base_mode + custom_main + custom_sub


# PX4 PX4_CUSTOM_MAIN_MODE değerleri (DO_SET_MODE param2 için)
_MAIN_MODE_OFFBOARD = 6
_MAIN_MODE_AUTO = 4

# AUTO alt modları (DO_SET_MODE param3 için)
_SUB_AUTO_LOITER = 3
_SUB_AUTO_LAND = 6
_SUB_AUTO_RTL = 5
_SUB_AUTO_TAKEOFF = 2


class CommandSender:
    """FSM → PX4 komut köprüsü.

    Kullanım:
        sender = CommandSender(node, system_id=1, namespace='/drone_1')
        sender.arm()
        sender.takeoff(altitude_m=10.0)
        sender.land()
    """

    def __init__(
        self,
        node,
        system_id: int = 1,
        component_id: int = 1,
        namespace: str = '',
    ):
        """
        Args:
            node: ROS2 node (publisher oluşturmak için)
            system_id: PX4 MAV_SYS_ID — drone numarası (default 1)
            component_id: MAV_COMP_ID — onboard bilgisayar (default 1)
            namespace: PX4 topic namespace, örn. '/drone_1'
                       Micro-XRCE-DDS-Agent'ın kullandığı namespace ile eşleşmeli.
        """
        self._node = node
        self._sys_id = system_id
        self._comp_id = component_id

        # PX4'e komut yayınlayan publisher'lar — namespace ile doğru topic'e yazılır
        self._cmd_pub = node.create_publisher(
            VehicleCommand, f'{namespace}/fmu/in/vehicle_command', 10
        )
        self._offboard_pub = node.create_publisher(
            OffboardControlMode, f'{namespace}/fmu/in/offboard_control_mode', 10
        )
        self._setpoint_pub = node.create_publisher(
            TrajectorySetpoint, f'{namespace}/fmu/in/trajectory_setpoint', 10
        )

    # =================================================================
    # YARDIMCI: VehicleCommand mesajı oluştur ve yayınla
    # =================================================================
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
        """Tek bir VehicleCommand mesajı yayınlar."""
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

    # =================================================================
    # ARM / DISARM
    # =================================================================
    def arm(self) -> None:
        """Motorları arm et — drone uçmaya hazır hale gelir."""
        self._send_vehicle_command(_CMD_ARM_DISARM, param1=1.0)

    def disarm(self) -> None:
        """Motorları disarm et — drone yerde güvenli."""
        self._send_vehicle_command(_CMD_ARM_DISARM, param1=0.0)

    # =================================================================
    # MOD DEĞİŞTİRME
    # =================================================================
    def set_offboard_mode(self) -> None:
        """OFFBOARD moduna geç — bizim setpoint'lerimizi takip et."""
        self._send_vehicle_command(
            _CMD_DO_SET_MODE,
            param1=1.0,
            param2=float(_MAIN_MODE_OFFBOARD),
        )

    def set_auto_loiter_mode(self) -> None:
        """AUTO LOITER moduna geç — havada sabit bekle."""
        self._send_vehicle_command(
            _CMD_DO_SET_MODE,
            param1=1.0,
            param2=float(_MAIN_MODE_AUTO),
            param3=float(_SUB_AUTO_LOITER),
        )

    # =================================================================
    # KALKIŞ / İNİŞ / EVE DÖNÜŞ
    # =================================================================
    def takeoff(self, altitude_m: float = 10.0) -> None:
        """Belirtilen irtifaya kalk (AUTO_TAKEOFF modu)."""
        self._send_vehicle_command(_CMD_NAV_TAKEOFF, param7=altitude_m)

    def land(self) -> None:
        """Bulunduğu konumda iniş yap."""
        self._send_vehicle_command(_CMD_NAV_LAND)

    def return_home(self) -> None:
        """Home konumuna dön (RTL)."""
        self._send_vehicle_command(_CMD_NAV_RTL)

    # =================================================================
    # OFFBOARD STREAMING
    # PX4, OFFBOARD modunda sürekli setpoint bekler (min 2 Hz, tipik 50 Hz).
    # Stream kesilirse PX4 failsafe'e geçer. px4_bridge 50 Hz timer ile çağırır.
    # =================================================================
    def publish_offboard_position_mode(self) -> None:
        """OFFBOARD modunda 'pozisyon kontrolü kullanıyorum' sinyali gönderir."""
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
        """Hedef pozisyon (NED) ve yaw gönder.

        UYARI: NED frame — z aşağı pozitif!
        20 metre yükseklik için z = -20.0
        """
        msg = TrajectorySetpoint()
        msg.timestamp = int(self._node.get_clock().now().nanoseconds / 1000)
        msg.position = [float(x), float(y), float(z)]
        msg.yaw = float(yaw_rad)
        self._setpoint_pub.publish(msg)
