"""
swarm_origin_publisher.py

Sürü için ORTAK uzamsal referans noktasını (SwarmOrigin) yayınlar. Bu nokta,
tüm drone'ların GPS'lerini aynı shared-NED çerçevesine çevirmek için kullanılan
sıfır noktasıdır (frame'in (0,0)'ı).

TASARIM — drone'dan TAMAMEN BAĞIMSIZ sabit çapa (virtual anchor):
Origin, hiçbir drone'un verisinden TÜRETİLMEZ. Dışarıdan verilen sabit bir
noktadır. Böylece:
  * Her drone açıldığı an, kimseyi beklemeden / kimseye sormadan aynı referansa
    oturur — tam dağıtık (decentralized).
  * Sürüden bir drone ayrılır veya sonradan katılırsa frame değişmez;
    ayrılan drone tek başına da aynı sabit referansı kullanıp konumunu
    hesaplamaya devam eder.
  * SITL ve gerçek donanım kod yolu aynıdır; yalnızca noktanın KAYNAĞI değişir.

İki kaynak modu (origin_source parametresi):

  fixed (SITL varsayılanı):
    config/param'dan verilen sabit lat/lon/alt. Hiçbir drone telemetrisi
    dinlenmez; node açılır açılmaz sabit noktayı yayınlar. Gerçek sahadaki RTK
    baz istasyonunun (harici sabit çapa) SITL karşılığıdır.

  rtk_base (gerçek donanım):
    RTK baz istasyonunun konumunu (RTK sürücüsünün yayınladığı NavSatFix
    topic'inden) origin olarak kilitler. Gerçek harici sabit çapa.

  first_fix (gerçek donanım — RTK yoksa):
    Seçilen bir drone'un (varsayılan drone 1) İLK gerçek GPS değerini origin
    olarak dondurur. Elle koordinat girme derdini ve "sim değerini sahada
    unutup bırakma" riskini kaldırır. Yalnız BU tek düğüm yakalar ve
    /swarm/origin'e basar; 3 drone + director hep bu tek yayından okur →
    herkes aynı sıfır (kayma imkânsız). Kilitlendikten sonra DEĞİŞMEZ.
    Mutlak doğruluk GPS kadardır (~1-3 m); formasyon (relatif) etkilenmez,
    ama mutlak hedef isabeti (QR/renkli ped) için RTK daha güvenlidir.

Origin'in DEĞERİ formasyon şeklini etkilemez (relatif hesapta sadeleşir);
önemli olan tüm drone'ların AYNI değeri kullanmasıdır.
Tüketiciler (formation_node,
bridge) origin'in nereden geldiğini bilmez, sadece /swarm/public/origin
topic'ini dinler.

Kullanım (SITL):
  ros2 run swarm_control swarm_origin_publisher --ros-args \
    -p origin_source:=fixed \
    -p fixed_lat:=41.0441269 -p fixed_lon:=29.0016997 -p fixed_alt:=0.48

Kullanım (donanım — RTK):
  ros2 run swarm_control swarm_origin_publisher --ros-args \
    -p origin_source:=rtk_base -p rtk_base_topic:=/rtk/base/fix

Kullanım (donanım — RTK yoksa, ilk iyi fix'i dondur):
  ros2 run swarm_control swarm_origin_publisher --ros-args \
    -p origin_source:=first_fix -p first_fix_agent_id:=1
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSPresetProfiles,
    QoSProfile,
    ReliabilityPolicy,
    DurabilityPolicy,
    HistoryPolicy,
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
    """Sürü için ortak NED referans noktasını (SwarmOrigin) yayınlar."""

    def __init__(self):
        """Node'u başlatır, modu okur ve origin kilit mantığını kurar."""
        super().__init__('swarm_origin_publisher')

        # fixed | rtk_base | first_fix
        self.declare_parameter('origin_source', 'fixed')
        self.declare_parameter('rate_hz', 1.0)
        # fixed mod referans noktası (SITL — dronların spawn bölgesi):
        self.declare_parameter('fixed_lat', 0.0)
        self.declare_parameter('fixed_lon', 0.0)
        self.declare_parameter('fixed_alt', 0.0)
        # rtk_base mod RTK sürücü topic'i:
        self.declare_parameter('rtk_base_topic', '/rtk/base/fix')
        # first_fix mod: hangi dronun GPS'i yakalanır.
        self.declare_parameter('first_fix_agent_id', 1)

        _src_param = self.get_parameter('origin_source')
        self._origin_source = (
            _src_param.get_parameter_value().string_value or 'fixed'
        )
        rate_hz = float(
            self.get_parameter('rate_hz').get_parameter_value().double_value
        )

        # /internal/origin'e yazılır — network_proxy bunu /public/origin'e
        # taşır (diğer tüm kanallarla aynı internal->proxy->public akışı;
        # önceden /public'e doğrudan basılıp proxy hop'u atlanıyordu).
        self._origin_pub = self.create_publisher(
            SwarmOrigin, '/swarm/internal/origin', _RELIABLE_TRANSIENT
        )

        # Kilitlenmiş origin durumu (tüm modlarda ortak).
        self._lat: float | None = None
        self._lon: float | None = None
        self._alt: float | None = None
        self._gps_fix = 6        # sabit çapa / RTK → yüksek kalite
        self._gps_hdop = 0.5
        self._locked = False

        if self._origin_source == 'rtk_base':
            self._setup_rtk_base()
        elif self._origin_source == 'first_fix':
            self._setup_first_fix()
        else:
            self._setup_fixed()

        self.create_timer(1.0 / rate_hz, self._publish)

    # ------------------------------------------------------------------ #
    # fixed modu (SITL) — config'den sabit çapa, drone'dan bağımsız
    # ------------------------------------------------------------------ #
    def _setup_fixed(self) -> None:
        lat = float(
            self.get_parameter('fixed_lat').get_parameter_value().double_value
        )
        lon = float(
            self.get_parameter('fixed_lon').get_parameter_value().double_value
        )
        alt = float(
            self.get_parameter('fixed_alt').get_parameter_value().double_value
        )

        if lat == 0.0 and lon == 0.0:
            self.get_logger().error(
                'origin_source=fixed ama fixed_lat/fixed_lon verilmedi! '
                'Sabit referans noktası gerekli.'
            )
            return

        self._lat, self._lon, self._alt = lat, lon, alt
        self._locked = True
        self.get_logger().info(
            f'SwarmOriginPublisher (mod=fixed, sabit çapa): '
            f'lat={lat:.7f} lon={lon:.7f} alt={alt:.1f}m — drone-bağımsız'
        )

    # ------------------------------------------------------------------ #
    # rtk_base modu (donanım) — RTK bazının konumu
    # ------------------------------------------------------------------ #
    def _setup_rtk_base(self) -> None:
        _topic_param = self.get_parameter('rtk_base_topic')
        topic = _topic_param.get_parameter_value().string_value
        self.create_subscription(
            NavSatFix, topic, self._on_rtk_base,
            QoSPresetProfiles.SENSOR_DATA.value,
        )
        self.get_logger().info(
            f'SwarmOriginPublisher (mod=rtk_base): topic={topic}'
            f' — RTK bazı bekleniyor'
        )

    def _on_rtk_base(self, msg: NavSatFix) -> None:
        if self._locked:
            return
        # NavSatStatus.STATUS_NO_FIX = -1; >= STATUS_FIX (0) geçerli.
        if msg.status.status < NavSatStatus.STATUS_FIX:
            return
        if msg.latitude == 0.0 and msg.longitude == 0.0:
            return
        self._lat = float(msg.latitude)
        self._lon = float(msg.longitude)
        self._alt = float(msg.altitude)
        self._locked = True
        self.get_logger().info(
            f'Origin kilitlendi (RTK baz): '
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
        if not self._locked:
            self.get_logger().info(
                'Origin referansı bekleniyor...', throttle_duration_sec=5.0
            )
            return

        msg = SwarmOrigin()
        msg.stamp = self.get_clock().now().to_msg()
        msg.leader_agent_id = 0  # sabit çapa / RTK → tek seed yok
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
