"""PX4 ↔ FSM köprüsü — ana ROS2 node.

İŞLEYİŞ:
1. MAVROS topic'lerini dinler (/{drone_ns}/mavros/...)
   → mavros_telemetry_mapper ile (ENU→NED) AgentStatus'a çevirir
   → /swarm/agent/drone{id}/telemetry'ye yayınlar (FSM okuyacak)

2. FSM komut topic'ini dinler (/swarm/agent/drone{id}/commands)
   → mavros_command_sender ile (NED→ENU) MAVROS'a iletir

3. OFFBOARD heartbeat (50 Hz) — PX4 offboard modda sürekli sinyal bekler.
   xy_valid + z_valid varsa mevcut konum hold setpoint'i olarak gönderilir.

KULLANIM:
    ros2 run swarm_control px4_bridge --ros-args -p agent_id:=1
"""

import math

from mavros_msgs.msg import EstimatorStatus, GPSRAW, RCIn, RTCM, State
from mavros_msgs.msg import HomePosition as MavHomePosition

from nav_msgs.msg import Odometry

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
    qos_profile_sensor_data,
)

from sensor_msgs.msg import BatteryState, NavSatFix

from std_msgs.msg import String, UInt8MultiArray

from swarm_interfaces.msg import AgentSetpoint, AgentStatus, SwarmOrigin

from .mavros_command_sender import MavrosCommandSender
from .mavros_telemetry_mapper import (
    map_battery as mav_map_battery,
    map_estimator_status as mav_map_estimator,
    map_global_position as mav_map_global,
    map_gps_raw as mav_map_gps,
    map_home as mav_map_home,
    map_odometry as mav_map_odom,
    map_rc_in as mav_map_rc,
    map_state as mav_map_state,
)
from .rtcm_packing import iter_rtcm_messages

_PX4_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=5,
)

_RTCM_MAX_FRAME = 1029
_RTK_MAX_TAMPON_BYTE = 2 * _RTCM_MAX_FRAME
_RTK_MAKUL_PAYLOAD = 768
_GPS_INJECT_QOS_DEPTH = 10
_RTK_DIAG_PERIOD_S = 1.0


class Px4BridgeNode(Node):
    """PX4 ve FSM arasındaki köprü düğümü."""

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
        self._takeoff_anchor_x: float | None = None
        self._takeoff_anchor_y: float | None = None
        self._was_offboard: bool = False

        self._cached_pos_x: float = 0.0
        self._cached_pos_y: float = 0.0
        self._cached_pos_z: float = 0.0
        self._cached_yaw_rad: float = 0.0

        self._latest_setpoint: AgentSetpoint | None = None
        self._setpoint_stamp: float = 0.0
        self._setpoint_timeout_s: float = 0.5
        self._applied_origin_seq: int = -1

        self._cmd_sender = MavrosCommandSender(
            self,
            namespace=self._fmu_ns,
        )

        self._setup_mavros_subscriptions()

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
        """RTCM aboneliği ve MAVROS RTCM yayıncısı kurar."""
        self.declare_parameter('rtk_makul_payload', _RTK_MAKUL_PAYLOAD)
        self._rtk_makul_payload = int(
            self.get_parameter('rtk_makul_payload').value
        )

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
        self._rtcm_pub = self.create_publisher(
            RTCM,
            f'{ns}/mavros/gps_rtk/send_rtcm',
            _GPS_INJECT_QOS_DEPTH,
        )
        self.create_timer(
            _RTK_DIAG_PERIOD_S, self._rtk_tani_yayinla
        )

    def _on_rtcm(self, msg: UInt8MultiArray) -> None:
        """Gelen RTCM mesajını işler."""
        try:
            self._on_rtcm_inner(msg)
        except Exception as e:  # noqa: BLE001
            self._rtk_cb_hata += 1
            self.get_logger().error(
                f'_on_rtcm hata: {type(e).__name__}: {e}'
            )

    def _on_rtcm_inner(self, msg: UInt8MultiArray) -> None:
        """RTCM tamponundaki verileri ayıklar ve fragmentler."""
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

    def _rtk_yayinla_fragmenler(self, rtcm_msg: bytes) -> None:
        """RTCM mesajını MAVROS'a bütün olarak yayınlar."""
        out = RTCM()
        out.header.stamp = self.get_clock().now().to_msg()
        out.data = list(rtcm_msg)
        self._rtcm_pub.publish(out)
        self._rtk_yayinlanan_frag += 1

    def _rtk_tani_yayinla(self) -> None:
        """RTK sağlık verilerini loglar."""
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

    def _setup_mavros_subscriptions(self) -> None:
        """MAVROS telemetri topic'lerine abone olur."""
        ns = self._fmu_ns
        self.create_subscription(
            State, f'{ns}/mavros/state', self._on_mav_state, 10
        )
        self.create_subscription(
            BatteryState, f'{ns}/mavros/battery',
            self._on_mav_battery, qos_profile_sensor_data
        )
        self.create_subscription(
            MavHomePosition, f'{ns}/mavros/home_position/home',
            self._on_mav_home, 10
        )
        self.create_subscription(
            Odometry, f'{ns}/mavros/local_position/odom',
            self._on_mav_odom, qos_profile_sensor_data
        )
        self.create_subscription(
            NavSatFix, f'{ns}/mavros/global_position/global',
            self._on_mav_global, qos_profile_sensor_data
        )
        self.create_subscription(
            GPSRAW, f'{ns}/mavros/gpsstatus/gps1/raw',
            self._on_mav_gps, qos_profile_sensor_data
        )
        self.create_subscription(
            EstimatorStatus, f'{ns}/mavros/estimator_status',
            self._on_mav_estimator, 10
        )
        self.create_subscription(
            RCIn, f'{ns}/mavros/rc/in',
            self._on_mav_rc, qos_profile_sensor_data
        )

    def _on_mav_state(self, msg: State) -> None:
        """MAVROS State -> AgentStatus."""
        mav_map_state(msg, self._status)

    def _on_mav_battery(self, msg: BatteryState) -> None:
        """MAVROS BatteryState -> AgentStatus batarya."""
        mav_map_battery(msg, self._status)

    def _on_mav_odom(self, msg: Odometry) -> None:
        """MAVROS Odometry -> AgentStatus konum/hız (ENU->NED)."""
        mav_map_odom(msg, self._status)

    def _on_mav_global(self, msg: NavSatFix) -> None:
        """MAVROS NavSatFix -> AgentStatus lat/lon/alt."""
        mav_map_global(msg, self._status)

    def _on_mav_gps(self, msg: GPSRAW) -> None:
        """MAVROS GPSRAW -> AgentStatus fix_type/satellites."""
        mav_map_gps(msg, self._status)

    def _on_mav_home(self, msg: MavHomePosition) -> None:
        """MAVROS HomePosition -> AgentStatus home."""
        mav_map_home(msg, self._status)

    def _on_mav_estimator(self, msg: EstimatorStatus) -> None:
        """MAVROS EstimatorStatus -> AgentStatus kestirici sağlık."""
        mav_map_estimator(msg, self._status)

    def _on_mav_rc(self, msg: RCIn) -> None:
        """MAVROS RCIn -> AgentStatus rc_link_ok."""
        mav_map_rc(msg, self._status)

    def _offboard_tick(self) -> None:
        """50 Hz tick: Offboard heartbeat ve setpoint gönderimi."""
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
            if (self._offboard_streaming
                    and not self._status.offboard_active
                    and self._status.armed):
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
        """FSM komutunu çevirip MAVROS'a iletir."""
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
            self._target_altitude_ned = self._cached_pos_z - altitude
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
        """Status durumunu yayınlar."""
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
