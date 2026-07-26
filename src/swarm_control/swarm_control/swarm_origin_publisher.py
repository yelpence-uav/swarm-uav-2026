"""Suru ortak referans noktasini (SwarmOrigin) yayinlayan dugum."""

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSPresetProfiles,
    QoSProfile,
    ReliabilityPolicy,
)

from sensor_msgs.msg import NavSatFix, NavSatStatus
from swarm_interfaces.msg import AgentStatus, SwarmOrigin

_RELIABLE_TRANSIENT = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


class SwarmOriginPublisher(Node):
    """Ortak referans noktasi yayincisi."""

    def __init__(self):
        super().__init__('swarm_origin_publisher')

        self.declare_parameter('origin_source', 'fixed')
        self.declare_parameter('rate_hz', 1.0)
        self.declare_parameter('fixed_lat', 0.0)
        self.declare_parameter('fixed_lon', 0.0)
        self.declare_parameter('fixed_alt', 0.0)
        self.declare_parameter('rtk_base_topic', '/rtk/base/fix')
        # first_fix mod: hangi dronun GPS'i yakalanır.
        self.declare_parameter('first_fix_agent_id', 1)

        _src_param = self.get_parameter('origin_source')
        self._origin_source = (
            _src_param.get_parameter_value().string_value or 'fixed'
        )
        rate_hz = float(
            self.get_parameter('rate_hz')
            .get_parameter_value().double_value
        )

        # /internal/origin'e yazılır — network_proxy bunu /public/origin'e
        # taşır (diğer tüm kanallarla aynı internal->proxy->public akışı;
        # önceden /public'e doğrudan basılıp proxy hop'u atlanıyordu).
        self._origin_pub = self.create_publisher(
            SwarmOrigin, '/swarm/internal/origin', _RELIABLE_TRANSIENT
        )

        self._lat = None
        self._lon = None
        self._alt = None
        self._gps_fix = 6
        self._gps_hdop = 0.5
        self._locked = False

        if self._origin_source == 'rtk_base':
            self._setup_rtk_base()
        elif self._origin_source == 'first_fix':
            self._setup_first_fix()
        else:
            self._setup_fixed()

        self.create_timer(1.0 / rate_hz, self._publish)

    def _setup_fixed(self) -> None:
        """Sabit referans noktasi modunu kurar."""
        lat = float(
            self.get_parameter('fixed_lat')
            .get_parameter_value().double_value
        )
        lon = float(
            self.get_parameter('fixed_lon')
            .get_parameter_value().double_value
        )
        alt = float(
            self.get_parameter('fixed_alt')
            .get_parameter_value().double_value
        )

        if lat == 0.0 and lon == 0.0:
            self.get_logger().error(
                'fixed_lat/fixed_lon parametreleri eksik!'
            )
            return

        self._lat, self._lon, self._alt = lat, lon, alt
        self._locked = True
        self.get_logger().info(
            f'Sabit origin kilitlendi: '
            f'lat={lat:.7f} lon={lon:.7f} alt={alt:.1f}m'
        )

    def _setup_rtk_base(self) -> None:
        """RTK baz istasyonu modunu kurar."""
        _topic_param = self.get_parameter('rtk_base_topic')
        topic = _topic_param.get_parameter_value().string_value
        self.create_subscription(
            NavSatFix, topic, self._on_rtk_base,
            QoSPresetProfiles.SENSOR_DATA.value,
        )
        self.get_logger().info(
            f'RTK baz aboneligi kuruldu: topic={topic}'
        )

    def _on_rtk_base(self, msg: NavSatFix) -> None:
        """RTK baz verisinden konumu kilitler."""
        if self._locked:
            return
        if msg.status.status < NavSatStatus.STATUS_FIX:
            return
        if msg.latitude == 0.0 and msg.longitude == 0.0:
            return
        self._lat = float(msg.latitude)
        self._lon = float(msg.longitude)
        self._alt = float(msg.altitude)
        self._locked = True
        self.get_logger().info(
            f'RTK origin kilitlendi: '
            f'lat={self._lat:.7f} lon={self._lon:.7f} alt={self._alt:.1f}m'
        )

    # ------------------------------------------------------------------ #
    # first_fix modu (donanım, RTK yoksa) — seçilen dronun ilk iyi fix'i
    # ------------------------------------------------------------------ #
    def _setup_first_fix(self) -> None:
        self._ff_agent_id = int(
            self.get_parameter('first_fix_agent_id').value
        )
        topic = f'/swarm/public/drone{self._ff_agent_id}/status'
        self.create_subscription(
            AgentStatus, topic, self._on_agent_status,
            QoSPresetProfiles.SENSOR_DATA.value,
        )
        self.get_logger().info(
            f'SwarmOriginPublisher (mod=first_fix): drone{self._ff_agent_id} '
            f'ilk GPS değeri bekleniyor'
        )

    def _on_agent_status(self, msg: AgentStatus) -> None:
        if self._locked:
            return
        # GPS henüz gelmemişken lat/lon 0 gelir; ilk GERÇEK değeri bekle.
        if msg.lat_deg == 0.0 and msg.lon_deg == 0.0:
            return
        # İlk gerçek GPS değerini origin olarak dondur — bir daha değişmez.
        self._lat = float(msg.lat_deg)
        self._lon = float(msg.lon_deg)
        self._alt = float(msg.alt_amsl_m)
        self._gps_fix = int(msg.gps_fix_type)
        self._gps_hdop = float(msg.gps_hdop)
        self._locked = True
        self.get_logger().info(
            f'Origin kilitlendi (first_fix, drone{self._ff_agent_id}): '
            f'lat={self._lat:.7f} lon={self._lon:.7f} alt={self._alt:.1f}m'
        )

    # ------------------------------------------------------------------ #
    # Yayın
    # ------------------------------------------------------------------ #
    def _publish(self) -> None:
        """Origin verisini periyodik olarak yayinlar."""
        if not self._locked:
            self.get_logger().info(
                'Origin referansi bekleniyor...',
                throttle_duration_sec=5.0
            )
            return

        msg = SwarmOrigin()
        msg.stamp = self.get_clock().now().to_msg()
        msg.leader_agent_id = 0
        msg.origin_lat_deg = self._lat
        msg.origin_lon_deg = self._lon
        msg.origin_alt_amsl_m = self._alt
        msg.valid = True
        msg.gps_fix_type = self._gps_fix
        msg.gps_hdop = self._gps_hdop
        msg.sequence = 1
        self._origin_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = SwarmOriginPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
