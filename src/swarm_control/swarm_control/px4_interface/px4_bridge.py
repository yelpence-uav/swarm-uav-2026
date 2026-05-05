"""
px4_bridge.py

PX4 ↔ FSM köprüsü — ana ROS2 node.

İŞLEYİŞ:
1. PX4 topic'lerini dinler (/{drone_ns}/fmu/out/...)
   → telemetry_mapper ile AgentStatus'a çevirir
   → /swarm/agent/drone{id}/telemetry'ye yayınlar (FSM okuyacak)

2. FSM komut topic'ini dinler (/swarm/agent/drone{id}/commands)
   → command_sender ile PX4'e iletir (/{drone_ns}/fmu/in/...)

3. OFFBOARD heartbeat (50 Hz) — PX4 offboard modda sürekli sinyal bekler.
   xy_valid + z_valid varsa mevcut konum hold setpoint'i olarak gönderilir.

KULLANIM:
    ros2 run swarm_control px4_bridge --ros-args -p agent_id:=1
"""

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

# PX4 mesaj tipleri
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

# Komut için basit string mesajı (FSM'den gelir)
from std_msgs.msg import String

# Bizim mesaj formatımız
from swarm_interfaces.msg import AgentStatus

# Aynı paket içindeki yardımcılar
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


# PX4 BEST_EFFORT QoS — PX4 telemetri bu profili kullanır
_PX4_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=5,
)


class Px4BridgeNode(Node):
    """PX4 ↔ FSM ortadaki köprü node."""

    def __init__(self) -> None:
        super().__init__('px4_bridge')

        # ROS2 parametreleri
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('publish_rate_hz', 10.0)
        self._agent_id: int = int(
            self.get_parameter('agent_id').value
        )
        publish_rate = float(
            self.get_parameter('publish_rate_hz').value
        )

        # Micro-XRCE-DDS-Agent'ın kullandığı PX4 namespace — tüm /fmu/... topic'leri bu altında
        self._fmu_ns = f'/drone_{self._agent_id}'

        # Drone'un anlık durumu — callback'ler bunu doldurur
        self._status = AgentStatus()
        self._status.agent_id = self._agent_id

        # OFFBOARD streaming aktif mi — FSM "offboard" gönderince True olur
        self._offboard_streaming: bool = False

        # PX4'e komut gönderen yardımcı — namespace ile doğru topic'lere yazar
        self._cmd_sender = CommandSender(
            self,
            system_id=self._agent_id,
            namespace=self._fmu_ns,
        )

        # PX4 telemetri abonelikleri kur
        self._setup_px4_subscriptions()

        # AgentStatus yayıncısı (FSM bunu okur)
        self._status_pub = self.create_publisher(
            AgentStatus,
            f'/swarm/agent/drone{self._agent_id}/telemetry',
            10,
        )

        # FSM komut aboneliği (FSM buraya yazar, biz PX4'e iletiriz)
        self.create_subscription(
            String,
            f'/swarm/agent/drone{self._agent_id}/commands',
            self._on_fsm_command,
            10,
        )

        # AgentStatus'u periyodik yayınla — varsayılan 10 Hz
        self.create_timer(1.0 / publish_rate, self._publish_status)

        # OFFBOARD heartbeat — PX4 offboard modda min 2 Hz sinyal ister, 50 Hz gönderiyoruz.
        # OffboardControlMode her zaman yayınlanır (offboard dışı modlarda PX4 yoksayar).
        # TrajectorySetpoint sadece _offboard_streaming=True ve konum geçerliyken gönderilir.
        self.create_timer(1.0 / 50.0, self._offboard_tick)

        self.get_logger().info(
            f'Px4BridgeNode başlatıldı: agent_id={self._agent_id}, '
            f'fmu_ns={self._fmu_ns}, publish_rate={publish_rate} Hz'
        )

    # =================================================================
    # PX4 ABONELİKLERİ
    # =================================================================
    def _setup_px4_subscriptions(self) -> None:
        """PX4 telemetri topic'lerine abone ol.

        Tüm topic'ler Micro-XRCE-DDS-Agent'ın namespace'i altında gelir:
        /drone_{id}/fmu/out/...
        """
        ns = self._fmu_ns
        subs = [
            (BatteryStatus,        f'{ns}/fmu/out/battery_status',         self._on_battery),
            (VehicleStatus,        f'{ns}/fmu/out/vehicle_status',         self._on_vehicle_status),
            (VehicleLocalPosition, f'{ns}/fmu/out/vehicle_local_position', self._on_local_pos),
            (EstimatorStatusFlags, f'{ns}/fmu/out/estimator_status_flags', self._on_estimator),
            (SensorGps,            f'{ns}/fmu/out/vehicle_gps_position',   self._on_gps),
            (VehicleGlobalPosition,f'{ns}/fmu/out/vehicle_global_position',self._on_global_pos),
            (HomePosition,         f'{ns}/fmu/out/home_position',          self._on_home),
            (VehicleAttitude,      f'{ns}/fmu/out/vehicle_attitude',       self._on_attitude),
            (ManualControlSetpoint,f'{ns}/fmu/out/manual_control_setpoint',self._on_manual_control),
        ]
        for msg_type, topic, cb in subs:
            self.create_subscription(msg_type, topic, cb, _PX4_QOS)

    # =================================================================
    # PX4 CALLBACKS — sadece mapper'ı çağırırlar
    # =================================================================
    def _on_battery(self, msg: BatteryStatus) -> None:
        map_battery(msg, self._status)

    def _on_vehicle_status(self, msg: VehicleStatus) -> None:
        map_vehicle_status(msg, self._status)
        # Offboard'dan çıkıldığında streaming'i durdur
        if self._status.flight_mode != AgentStatus.FLIGHT_MODE_OFFBOARD:
            self._offboard_streaming = False

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

    # =================================================================
    # OFFBOARD HEARTBEAT (50 Hz)
    # =================================================================
    def _offboard_tick(self) -> None:
        """50 Hz'de çalışır.

        OffboardControlMode her zaman yayınlanır — PX4 moda geçiş için bunu
        görmek ister, diğer modlarda yoksayar.

        TrajectorySetpoint sadece offboard aktifken ve konum geçerliyken
        gönderilir; bu sayede drone mevcut konumda bekler (hold).
        """
        self._cmd_sender.publish_offboard_position_mode()

        if self._offboard_streaming and self._status.xy_valid and self._status.z_valid:
            self._cmd_sender.publish_position_setpoint(
                self._status.pos_x,
                self._status.pos_y,
                self._status.pos_z,
                yaw_rad=math.radians(self._status.heading_deg),
            )

    # =================================================================
    # FSM KOMUT KÖPRÜSÜ
    # =================================================================
    def _on_fsm_command(self, msg: String) -> None:
        """FSM'den gelen komutu PX4'e ilet.

        Desteklenen komutlar (basit string formatı):
            "arm", "disarm"
            "takeoff:10.0"   (irtifa parametresi)
            "land", "rtl"
            "offboard"
        """
        cmd = msg.data.strip().lower()

        if cmd == 'arm':
            self._cmd_sender.arm()
        elif cmd == 'disarm':
            self._offboard_streaming = False
            self._cmd_sender.disarm()
        elif cmd.startswith('takeoff'):
            # "takeoff:10.0" → altitude=10.0; sadece "takeoff" → 10.0 default
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
            self._offboard_streaming = False
            self._cmd_sender.land()
        elif cmd == 'rtl':
            self._offboard_streaming = False
            self._cmd_sender.return_home()
        elif cmd == 'offboard':
            # Önce streaming başlar, ardından mod değiştirilir.
            # PX4, OffboardControlMode sinyalini görmeden offboard'a geçmez.
            self._offboard_streaming = True
            self._cmd_sender.set_offboard_mode()
        else:
            self.get_logger().warning(f'Bilinmeyen FSM komutu: {cmd}')

    # =================================================================
    # AGENTSTATUS YAYINLA (10 Hz timer)
    # =================================================================
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
