"""PX4 ile FSM arasinda haberlesme koprusu kuran dugum.

PX4 telemetri verilerini dinler ve AgentStatus olarak yayinlar.
FSM'den gelen komutlari ise CommandSender ile PX4'e iletir.
Ayni zamanda RTCM verilerini de fragmenter ile bolup enjekte eder.
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

from px4_msgs.msg import (
    BatteryStatus,
    EstimatorStatusFlags,
    GpsInjectData,
    HomePosition,
    ManualControlSetpoint,
    SensorGps,
    VehicleAttitude,
    VehicleGlobalPosition,
    VehicleLocalPosition,
    VehicleStatus,
)

from std_msgs.msg import String, UInt8MultiArray
from swarm_interfaces.msg import AgentSetpoint, AgentStatus, SwarmOrigin

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
from .rtcm_packing import fragment_for_inject, iter_rtcm_messages

_PX4_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=5,
)

_GPS_INJECT_DATA_SIZE = 300
_RTK_DEFAULT_MAX_PAYLOAD = 300
_RTK_GPS_DEVICE_ID = 0
_RTCM_MAX_FRAME = 1029
_RTK_MAX_TAMPON_BYTE = 2 * _RTCM_MAX_FRAME
_RTK_MAKUL_PAYLOAD = 768
_GPS_INJECT_QOS_DEPTH = 10
_RTK_DIAG_PERIOD_S = 1.0


class Px4BridgeNode(Node):
    """PX4 ve FSM arasindaki kopru dugumu."""

    def __init__(self) -> None:
        super().__init__('px4_bridge')

        self.declare_parameter('agent_id', 1)
        self.declare_parameter('publish_rate_hz', 10.0)
        self.declare_parameter('sitl_mode', False)
        self.declare_parameter('velocity_only', False)

        self._agent_id = int(
            self.get_parameter('agent_id').value
        )
        publish_rate = float(
            self.get_parameter('publish_rate_hz').value
        )
        self._sitl_mode = bool(
            self.get_parameter('sitl_mode').value
        )
        self._velocity_only = bool(
            self.get_parameter('velocity_only').value
        )

        self._fmu_ns = f'/drone_{self._agent_id}'
        self._status = AgentStatus()
        self._status.agent_id = self._agent_id

        self._offboard_streaming = False
        self._offboard_rearm_counter = 0
        self._target_altitude_ned = None
        self._takeoff_anchor_x = None
        self._takeoff_anchor_y = None
        self._was_offboard = False

        self._cached_pos_x = 0.0
        self._cached_pos_y = 0.0
        self._cached_pos_z = 0.0
        self._cached_yaw_rad = 0.0

        self._latest_setpoint = None
        self._setpoint_stamp = 0.0
        self._setpoint_timeout_s = 0.5
        self._applied_origin_seq = -1

        if self._sitl_mode:
            self._fake_rc_pub = self.create_publisher(
                ManualControlSetpoint,
                f'{self._fmu_ns}/fmu/in/manual_control_input',
                10,
            )

        self._cmd_sender = CommandSender(
            self,
            system_id=self._agent_id,
            namespace=self._fmu_ns,
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

        self.create_subscription(
            AgentSetpoint,
            f'/drone_{self._agent_id}/control/setpoint',
            self._on_agent_setpoint,
            _PX4_QOS,
        )

        _origin_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.create_subscription(
            SwarmOrigin,
            '/swarm/public/origin',
            self._on_swarm_origin,
            _origin_qos,
        )

        self.create_timer(
            1.0 / publish_rate, self._publish_status
        )
        self.create_timer(1.0 / 50.0, self._offboard_tick)
        self._setup_rtk()

        self.get_logger().info(
            f'Px4BridgeNode baslatildi: agent_id={self._agent_id}'
        )

    def _setup_rtk(self) -> None:
        """RTK baglantilarini ve parametrelerini kurar."""
        self.declare_parameter(
            'rtk_max_payload', _RTK_DEFAULT_MAX_PAYLOAD
        )
        self.declare_parameter(
            'rtk_gps_device_id', _RTK_GPS_DEVICE_ID
        )
        self.declare_parameter(
            'rtk_makul_payload', _RTK_MAKUL_PAYLOAD
        )

        self._rtk_max_payload = int(
            self.get_parameter('rtk_max_payload').value
        )
        self._rtk_device_id = int(
            self.get_parameter('rtk_gps_device_id').value
        )
        self._rtk_makul_payload = int(
            self.get_parameter('rtk_makul_payload').value
        )

        if not 1 <= self._rtk_max_payload <= _GPS_INJECT_DATA_SIZE:
            self._rtk_max_payload = _RTK_DEFAULT_MAX_PAYLOAD

        self._rtk_tampon = bytearray()
        self._rtk_alinan_msg = 0
        self._rtk_yayinlanan_frag = 0
        self._rtk_cb_hata = 0
        self._rtk_sync_kayip = 0

        ns = self._fmu_ns
        self._rtcm_sub = self.create_subscription(
            UInt8MultiArray,
            f'{ns}/rtcm/in',
            self._on_rtcm,
            10,
        )
        self._gps_inject_pub = self.create_publisher(
            GpsInjectData,
            f'{ns}/fmu/in/gps_inject_data',
            _GPS_INJECT_QOS_DEPTH,
        )
        self.create_timer(
            _RTK_DIAG_PERIOD_S, self._rtk_tani_yayinla
        )

    def _on_rtcm(self, msg: UInt8MultiArray) -> None:
        """Gelen RTCM mesajini isler."""
        try:
            self._on_rtcm_inner(msg)
        except Exception as e:  # noqa: BLE001
            self._rtk_cb_hata += 1
            self.get_logger().error(
                f'_on_rtcm hata: {type(e).__name__}: {e}'
            )

    def _on_rtcm_inner(self, msg: UInt8MultiArray) -> None:
        """RTCM tamponundaki verileri ayiklar ve fragmentler."""
        if not msg.data:
            return
        self._rtk_tampon.extend(msg.data)
        mesajlar, kalan = iter_rtcm_messages(
            self._rtk_tampon, self._rtk_makul_payload
        )
        del self._rtk_tampon[
            :len(self._rtk_tampon) - len(kalan)
        ]
        if len(self._rtk_tampon) > _RTK_MAX_TAMPON_BYTE:
            del self._rtk_tampon[
                :len(self._rtk_tampon) - _RTCM_MAX_FRAME
            ]
            self._rtk_sync_kayip += 1
        if not mesajlar:
            return
        for rtcm_msg in mesajlar:
            self._rtk_alinan_msg += 1
            self._rtk_yayinla_fragmenler(rtcm_msg)

    def _rtk_yayinla_fragmenler(
        self, rtcm_msg: bytes
    ) -> None:
        """Cercevelenmis RTCM fragmanlarini PX4'e yayinlar."""
        parcalar = fragment_for_inject(
            rtcm_msg, max_payload=self._rtk_max_payload
        )
        for chunk, fragmented in parcalar:
            inject = GpsInjectData()
            ts = self.get_clock().now().nanoseconds
            inject.timestamp = int(ts / 1000)
            inject.device_id = self._rtk_device_id
            inject.len = len(chunk)
            inject.flags = 1 if fragmented else 0
            dolgu = _GPS_INJECT_DATA_SIZE - len(chunk)
            inject.data = list(chunk) + [0] * dolgu
            self._gps_inject_pub.publish(inject)
            self._rtk_yayinlanan_frag += 1

    def _rtk_tani_yayinla(self) -> None:
        """RTK saglik tanı verilerini loglar."""
        try:
            self.get_logger().info(
                f'rtk: msg={self._rtk_alinan_msg} '
                f'frag={self._rtk_yayinlanan_frag} '
                f'tampon={len(self._rtk_tampon)}B '
                f'sync_kayip={self._rtk_sync_kayip} '
                f'cb_hata={self._rtk_cb_hata}'
            )
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(
                f'rtk tani log hata: {e}'
            )

    def _setup_px4_subscriptions(self) -> None:
        """PX4 telemetri aboneliklerini kurar."""
        ns = self._fmu_ns
        subs = [
            (BatteryStatus,
             f'{ns}/fmu/out/battery_status',
             self._on_battery),
            (VehicleStatus,
             f'{ns}/fmu/out/vehicle_status_v1',
             self._on_vehicle_status),
            (VehicleLocalPosition,
             f'{ns}/fmu/out/vehicle_local_position',
             self._on_local_pos),
            (EstimatorStatusFlags,
             f'{ns}/fmu/out/estimator_status_flags',
             self._on_estimator),
            (SensorGps,
             f'{ns}/fmu/out/vehicle_gps_position',
             self._on_gps),
            (VehicleGlobalPosition,
             f'{ns}/fmu/out/vehicle_global_position',
             self._on_global_pos),
            (HomePosition,
             f'{ns}/fmu/out/home_position',
             self._on_home),
            (VehicleAttitude,
             f'{ns}/fmu/out/vehicle_attitude',
             self._on_attitude),
            (ManualControlSetpoint,
             f'{ns}/fmu/out/manual_control_setpoint',
             self._on_manual_control),
        ]
        for msg_type, topic, cb in subs:
            self.create_subscription(
                msg_type, topic, cb, _PX4_QOS
            )

    def _on_battery(self, msg: BatteryStatus) -> None:
        map_battery(msg, self._status)

    def _on_vehicle_status(self, msg: VehicleStatus) -> None:
        prev_offboard = self._status.offboard_active
        map_vehicle_status(msg, self._status)

        if (self._sitl_mode and
                prev_offboard and
                not self._status.offboard_active and
                self._status.armed):
            self.get_logger().warn(
                'SITL: Offboard kayboldu, yeniden isteniyor'
            )
            self._cmd_sender.set_offboard_mode()

    def _on_local_pos(
        self, msg: VehicleLocalPosition
    ) -> None:
        map_local_position(msg, self._status)

    def _on_estimator(
        self, msg: EstimatorStatusFlags
    ) -> None:
        map_estimator(msg, self._status)

    def _on_gps(self, msg: SensorGps) -> None:
        map_gps(msg, self._status)

    def _on_global_pos(
        self, msg: VehicleGlobalPosition
    ) -> None:
        map_global_position(msg, self._status)

    def _on_home(self, msg: HomePosition) -> None:
        map_home_position(msg, self._status)

    def _on_attitude(self, msg: VehicleAttitude) -> None:
        map_attitude(msg, self._status)

    def _on_manual_control(
        self, msg: ManualControlSetpoint
    ) -> None:
        map_manual_control(msg, self._status)

    def _publish_fake_rc(self) -> None:
        """SITL icin sahte RC sinyali yayinlar."""
        msg = ManualControlSetpoint()
        ts = self.get_clock().now().nanoseconds
        msg.timestamp = int(ts / 1000)
        msg.roll = 0.0
        msg.pitch = 0.0
        msg.throttle = 0.0
        msg.yaw = 0.0
        msg.valid = True
        self._fake_rc_pub.publish(msg)

    def _offboard_tick(self) -> None:
        """50 Hz tick: Offboard heartbeat ve setpoint gonderimi."""
        if self._status.xy_valid and self._status.z_valid:
            self._cached_pos_x = self._status.pos_x
            self._cached_pos_y = self._status.pos_y
            self._cached_pos_z = self._status.pos_z
            _yaw = math.radians(self._status.heading_deg)
            self._cached_yaw_rad = (
                (_yaw + math.pi) % (2 * math.pi) - math.pi
            )

        now = self.get_clock().now().nanoseconds * 1e-9
        setpoint_fresh = (
            self._latest_setpoint is not None
            and (now - self._setpoint_stamp) < (
                self._setpoint_timeout_s
            )
        )

        if not self._offboard_streaming:
            if self._sitl_mode:
                self._publish_fake_rc()
            return

        use_velocity = (
            setpoint_fresh and
            self._latest_setpoint.velocity_valid
        )

        if use_velocity and self._velocity_only:
            self._cmd_sender.publish_offboard_velocity_mode()
        elif use_velocity:
            self._cmd_sender.publish_offboard_position_velocity_mode()
        else:
            self._cmd_sender.publish_offboard_position_mode()

        if self._sitl_mode:
            self._publish_fake_rc()
            if (self._offboard_streaming and
                    not self._status.offboard_active and
                    self._status.armed):
                self._offboard_rearm_counter += 1
                if self._offboard_rearm_counter >= 25:
                    self._offboard_rearm_counter = 0
                    self.get_logger().warn(
                        'SITL: Offboard yeniden isteniyor'
                    )
                    self._cmd_sender.set_offboard_mode()
            else:
                self._offboard_rearm_counter = 0

        if setpoint_fresh:
            sp = self._latest_setpoint
            target_x = float(sp.x)
            target_y = float(sp.y)
            target_z = float(sp.z)
            _yaw = math.radians(float(sp.heading_deg))
            target_yaw = (
                (_yaw + math.pi) % (2 * math.pi) - math.pi
            )
        elif self._target_altitude_ned is not None:
            target_x = (
                self._takeoff_anchor_x
                if self._takeoff_anchor_x is not None
                else self._cached_pos_x
            )
            target_y = (
                self._takeoff_anchor_y
                if self._takeoff_anchor_y is not None
                else self._cached_pos_y
            )
            target_z = self._target_altitude_ned
            target_yaw = self._cached_yaw_rad
        else:
            target_x = self._cached_pos_x
            target_y = self._cached_pos_y
            target_z = self._cached_pos_z
            target_yaw = self._cached_yaw_rad

        if use_velocity and self._velocity_only:
            sp = self._latest_setpoint
            self._cmd_sender.publish_velocity_setpoint(
                float(sp.vx), float(sp.vy), float(sp.vz),
                yaw_rad=target_yaw,
            )
        elif use_velocity:
            sp = self._latest_setpoint
            self._cmd_sender.publish_position_velocity_setpoint(
                target_x, target_y, target_z,
                float(sp.vx), float(sp.vy), float(sp.vz),
                yaw_rad=target_yaw,
            )
        else:
            self._cmd_sender.publish_position_setpoint(
                target_x, target_y, target_z,
                yaw_rad=target_yaw,
            )

    def _on_swarm_origin(self, msg: SwarmOrigin) -> None:
        """Ortak NED origin'i uygular."""
        if not msg.valid or msg.gps_fix_type < 3:
            return
        if msg.sequence == self._applied_origin_seq:
            return
        self._applied_origin_seq = msg.sequence
        self._cmd_sender.set_gps_global_origin(
            msg.origin_lat_deg,
            msg.origin_lon_deg,
            msg.origin_alt_amsl_m,
        )
        self._status.origin_synced = True
        self._status.origin_sequence = msg.sequence
        self.get_logger().info(
            f'GPS origin set: seq={msg.sequence}'
        )

    def _on_agent_setpoint(self, msg: AgentSetpoint) -> None:
        """Setpoint verisini saklar."""
        if not (msg.position_valid or msg.velocity_valid):
            return
        self._latest_setpoint = msg
        self._setpoint_stamp = (
            self.get_clock().now().nanoseconds * 1e-9
        )

    def _on_fsm_command(self, msg: String) -> None:
        """FSM komutunu cevirip PX4'e iletir."""
        cmd = msg.data.strip().lower()

        if cmd == 'arm':
            self._cmd_sender.arm()
        elif cmd == 'disarm':
            self._offboard_streaming = False
            self._cmd_sender.disarm()
        elif cmd.startswith('takeoff'):
            altitude = 10.0
            if ':' in cmd:
                try:
                    altitude = float(cmd.split(':', 1)[1])
                except ValueError:
                    self.get_logger().warning(
                        f'Gecersiz takeoff irtifasi: {cmd}'
                    )
            self._target_altitude_ned = -altitude
            self._takeoff_anchor_x = self._cached_pos_x
            self._takeoff_anchor_y = self._cached_pos_y
            self.get_logger().info(
                f'Takeoff: z={self._target_altitude_ned}'
            )
        elif cmd == 'land':
            self._offboard_streaming = False
            self._target_altitude_ned = None
            self._takeoff_anchor_x = None
            self._takeoff_anchor_y = None
            self._cmd_sender.land()
        elif cmd == 'rtl':
            self._offboard_streaming = False
            self._target_altitude_ned = None
            self._takeoff_anchor_x = None
            self._takeoff_anchor_y = None
            self._cmd_sender.return_home()
        elif cmd == 'offboard':
            self._offboard_streaming = True
            self._cmd_sender.set_offboard_mode()
        else:
            self.get_logger().warning(
                f'Bilinmeyen FSM komutu: {cmd}'
            )

    def _publish_status(self) -> None:
        """Status durumunu yayinlar."""
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
