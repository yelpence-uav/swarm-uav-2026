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
    qos_profile_sensor_data,
)

# PX4 mesaj tipleri
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

# Komut için basit string (FSM) ve RTCM bayt akışı (mesh -> RTK)
from std_msgs.msg import String, UInt8MultiArray

# Bizim mesaj formatımız
from swarm_interfaces.msg import AgentSetpoint, AgentStatus, SwarmOrigin

# MAVROS telemetri mesaj tipleri (use_mavros yolu)
from mavros_msgs.msg import EstimatorStatus, GPSRAW, RCIn, RTCM, State
from mavros_msgs.msg import HomePosition as MavHomePosition
from nav_msgs.msg import Odometry
from sensor_msgs.msg import BatteryState, NavSatFix

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

# RTK: RTCM3 framer + GpsInjectData fragmenter (saf modül, ROS bağımsız).
# Ayrı node yerine bu köprünün içine alındı — ayrı process/DDS/px4_msgs
# yükünü (~66 MB) ikinci kez ödememek için. Parse mantığı yine ayrı
# modülde (test edilebilir kalsın); RTK callback'i hızlı (~38 µs) olduğu
# için tek thread'de offboard heartbeat'i etkilemez.
from .rtcm_packing import fragment_for_inject, iter_rtcm_messages


# PX4 BEST_EFFORT QoS — PX4 telemetri bu profili kullanır
_PX4_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=5,
)

# --- RTK / RTCM sabitleri (eski rtk_bridge'den taşındı) ---
_GPS_INJECT_DATA_SIZE = 300      # px4_msgs/GpsInjectData.data uzunluğu
_RTK_DEFAULT_MAX_PAYLOAD = 300   # tek GpsInjectData fragmanı
_RTK_GPS_DEVICE_ID = 0           # ground injector standardı
# RTCM3 tek frame en fazla: header(3) + payload(<=1023) + crc(3) = 1029 B.
_RTCM_MAX_FRAME = 1029
# Tampon iki frame'i aşarsa sync kaybı/bozuk akış kabul edilir; biriken
# çöp atılır (yoksa her çağrı tüm tamponu yeniden tarar -> O(n^2)).
_RTK_MAX_TAMPON_BYTE = 2 * _RTCM_MAX_FRAME
# RTK düzeltme paketleri pratikte küçüktür (<500 B). Bunu aşan uzunluk
# iddia eden preamble, fail-fast ile (CRC'siz) sahte sayılır.
_RTK_MAKUL_PAYLOAD = 768
_GPS_INJECT_QOS_DEPTH = 10       # command_sender deseni
_RTK_DIAG_PERIOD_S = 1.0         # RTK tanı log periyodu


class Px4BridgeNode(Node):
    """PX4 ↔ FSM ortadaki köprü node."""

    def __init__(self) -> None:
        """
        PX4 ↔ FSM köprüsünü başlatır, arayüzleri kurar.

        ROS2 parametrelerini okur, PX4 topic aboneliklerini,
        AgentStatus publisher'ını ve OFFBOARD timer'ı oluşturur.
        """
        super().__init__('px4_bridge')

        # ROS2 parametreleri
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('publish_rate_hz', 10.0)
        self.declare_parameter('sitl_mode', False)
        # velocity_only (B mimarisi): True → PX4'e pozisyon GÖNDERİLMEZ
        # (sadece hız). Pozisyon kontrolü ROS'taki SVT'ye ait. False → A
        # (pozisyon+hız feedforward, PX4 pozisyon kontrolcüsü sahibi).
        self.declare_parameter('velocity_only', False)
        # use_mavros: True → komutlar MAVROS (MavrosCommandSender) üzerinden
        # gider; False → eski uXRCE-DDS (CommandSender). Strangler-fig geçişi.
        self.declare_parameter('use_mavros', False)
        self._agent_id: int = int(
            self.get_parameter('agent_id').value
        )
        publish_rate = float(
            self.get_parameter('publish_rate_hz').value
        )
        self._sitl_mode: bool = bool(
            self.get_parameter('sitl_mode').value
        )
        self._velocity_only: bool = bool(
            self.get_parameter('velocity_only').value
        )
        self._use_mavros: bool = bool(
            self.get_parameter('use_mavros').value
        )

        # Micro-XRCE-DDS-Agent'ın PX4 namespace'i — /fmu/... topic'leri
        self._fmu_ns = f'/drone_{self._agent_id}'

        # Drone'un anlık durumu — callback'ler bunu doldurur
        self._status = AgentStatus()
        self._status.agent_id = self._agent_id

        # OFFBOARD streaming aktif mi — FSM "offboard" gönderince True olur
        self._offboard_streaming: bool = False

        # SITL: offboard yeniden-talep sayacı (50Hz tick'te rate-limit için)
        self._offboard_rearm_counter: int = 0

        # Hedef kalkış irtifası (NED: negatif=yukarı) — None ise hold modu
        self._target_altitude_ned: float | None = None

        # Kalkış yatay çapası — takeoff anında bir kez dondurulur.
        # Tırmanış boyunca x,y bu sabit noktada tutulur (anlık konumu
        # takip etmez); PX4 pozisyon kontrolcüsü drift'i bu çapaya göre
        # düzeltir. None ise henüz kalkış komutu gelmedi.
        self._takeoff_anchor_x: float | None = None
        self._takeoff_anchor_y: float | None = None

        # SITL: offboard mod takibi için önceki durum
        self._was_offboard: bool = False

        # Son geçerli konum cache'i — xy/z_valid false olsa bile
        # setpoint akışını sürdür
        self._cached_pos_x: float = 0.0
        self._cached_pos_y: float = 0.0
        self._cached_pos_z: float = 0.0
        self._cached_yaw_rad: float = 0.0

        # formation_node'dan gelen son AgentSetpoint — None ise hold modu
        self._latest_setpoint: AgentSetpoint | None = None
        self._setpoint_stamp: float = 0.0
        # Bu kadar süredir setpoint gelmezse hold'a düş (saniye)
        self._setpoint_timeout_s: float = 0.5

        # SwarmOrigin — uygulanmış sequence takibi (tekrar göndermemek için)
        self._applied_origin_seq: int = -1

        # SITL: sahte RC publisher — gerçek donanımda oluşturulmaz
        if self._sitl_mode:
            self._fake_rc_pub = self.create_publisher(
                ManualControlSetpoint,
                f'{self._fmu_ns}/fmu/in/manual_control_input',
                10,
            )

        # PX4'e komut gönderen yardımcı — namespace ile doğru topic'lere yazar.
        # use_mavros: yeni MAVROS yolu; aksi halde eski uXRCE-DDS yolu.
        # İkisi de AYNI arayüzü sunar (strangler-fig), gerisi değişmez.
        if self._use_mavros:
            self._cmd_sender = MavrosCommandSender(
                self,
                namespace=self._fmu_ns,
            )
        else:
            self._cmd_sender = CommandSender(
                self,
                system_id=self._agent_id,
                namespace=self._fmu_ns,
            )

        # Telemetri abonelikleri — use_mavros'a göre kaynak seç.
        if self._use_mavros:
            self._setup_mavros_subscriptions()
        else:
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

        # Formation setpoint aboneliği — lokal, proxy'den geçmez
        self.create_subscription(
            AgentSetpoint,
            f'/drone_{self._agent_id}/control/setpoint',
            self._on_agent_setpoint,
            _PX4_QOS,
        )

        # SwarmOrigin — ortak NED referansını PX4'e ilet
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

        # AgentStatus'u periyodik yayınla — varsayılan 10 Hz
        self.create_timer(1.0 / publish_rate, self._publish_status)

        # OFFBOARD heartbeat — PX4 min 2 Hz sinyal ister, 50 Hz gönderiyoruz.
        # OffboardControlMode her zaman yayınlanır (diğer modlarda yoksayılır).
        # TrajectorySetpoint sadece konum geçerliyken gönderilir.
        self.create_timer(1.0 / 50.0, self._offboard_tick)

        # RTK/RTCM köprüsü (eski rtk_bridge node'undan taşındı)
        self._setup_rtk()

        self.get_logger().info(
            f'Px4BridgeNode başlatıldı: agent_id={self._agent_id}, '
            f'fmu_ns={self._fmu_ns}, publish_rate={publish_rate} Hz'
        )

    # =================================================================
    # RTK / RTCM KÖPRÜSÜ (eski rtk_bridge node'undan taşındı)
    # Ayrı sorumluluk olduğu için kod burada bir arada tutulur; parse
    # mantığı rtcm_packing modülünde (ROS bağımsız, test edilebilir).
    # =================================================================
    def _setup_rtk(self) -> None:
        """RTCM aboneliği + GpsInjectData publisher + tanı timer kurar."""
        # RTK parametreleri — sahada yeniden derlemeden ayarlanabilsin diye
        # declare_parameter ile dışa açık (eski rtk_bridge node'unda da
        # parametreydi; gömülürken korunması için geri eklendi).
        self.declare_parameter('rtk_max_payload', _RTK_DEFAULT_MAX_PAYLOAD)
        self.declare_parameter('rtk_gps_device_id', _RTK_GPS_DEVICE_ID)
        self.declare_parameter('rtk_makul_payload', _RTK_MAKUL_PAYLOAD)
        self._rtk_max_payload = int(
            self.get_parameter('rtk_max_payload').value
        )
        self._rtk_device_id = int(
            self.get_parameter('rtk_gps_device_id').value
        )
        self._rtk_makul_payload = int(
            self.get_parameter('rtk_makul_payload').value
        )
        # Güvenlik: tek fragman GpsInjectData.data (300 B) sınırını aşamaz.
        if not 1 <= self._rtk_max_payload <= _GPS_INJECT_DATA_SIZE:
            self.get_logger().warning(
                f'rtk_max_payload={self._rtk_max_payload} gecersiz '
                f'(1..{_GPS_INJECT_DATA_SIZE}); varsayilan kullanilacak'
            )
            self._rtk_max_payload = _RTK_DEFAULT_MAX_PAYLOAD

        # iter_rtcm_messages yarım kuyruğu (bytearray: extend ile O(1)).
        self._rtk_tampon = bytearray()
        # Tanı sayaçları
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
        # RTK çıkışı: MAVROS'ta /mavros/gps_rtk/send_rtcm (parçalamayı
        # MAVROS yapar, ~720B/mesaj); DDS'te GpsInjectData (300B parça bizde).
        if self._use_mavros:
            self._rtcm_pub = self.create_publisher(
                RTCM,
                f'{ns}/mavros/gps_rtk/send_rtcm',
                _GPS_INJECT_QOS_DEPTH,
            )
        else:
            self._gps_inject_pub = self.create_publisher(
                GpsInjectData,
                f'{ns}/fmu/in/gps_inject_data',
                _GPS_INJECT_QOS_DEPTH,
            )
        self.create_timer(_RTK_DIAG_PERIOD_S, self._rtk_tani_yayinla)

    def _on_rtcm(self, msg: UInt8MultiArray) -> None:
        """RTCM callback'i (try'lı, exception node'u çökertmez)."""
        try:
            self._on_rtcm_inner(msg)
        except Exception as e:  # noqa: BLE001
            self._rtk_cb_hata += 1
            self.get_logger().error(
                f'_on_rtcm hata: {type(e).__name__}: {e}'
            )

    def _on_rtcm_inner(self, msg: UInt8MultiArray) -> None:
        """RTCM akışını işleyip tam mesajları fragmenter'a yollar.

        RTCM düşük hızlıdır (tipik 1 Hz) ve her epoch'ta birden fazla
        mesaj bundle olarak gelir; rate-limit'e gerek yoktur.
        """
        if not msg.data:
            return
        # Yeni veriyi tampona YERİNDE ekle (O(1) amortized; kopya yok).
        self._rtk_tampon.extend(msg.data)
        mesajlar, kalan = iter_rtcm_messages(
            self._rtk_tampon, self._rtk_makul_payload
        )
        # Tüketilen baş kısmı at; geriye yalnız yarım kuyruk kalır.
        del self._rtk_tampon[:len(self._rtk_tampon) - len(kalan)]
        # Bozuk akışta geçerli frame çıkmaz, tampon birikir; iki frame'i
        # aşarsa sync kaybı kabul edilir, çöp atılır (O(n^2) önlenir).
        if len(self._rtk_tampon) > _RTK_MAX_TAMPON_BYTE:
            del self._rtk_tampon[
                :len(self._rtk_tampon) - _RTCM_MAX_FRAME
            ]
            self._rtk_sync_kayip += 1
        if not mesajlar:
            return  # yarım kuyruk biriktiriyoruz, bekle
        for rtcm_msg in mesajlar:
            self._rtk_alinan_msg += 1
            self._rtk_yayinla_fragmenler(rtcm_msg)

    def _rtk_yayinla_fragmenler(self, rtcm_msg: bytes) -> None:
        """RTCM mesajını PX4'e yayınlar (MAVROS: bütün; DDS: parçalı)."""
        if self._use_mavros:
            # MAVROS bütün RTCM mesajını alır ve GPS_RTCM_DATA'ya kendi
            # parçalar (max ~720B/mesaj). Bizim parçalamamıza gerek yok.
            out = RTCM()
            out.header.stamp = self.get_clock().now().to_msg()
            out.data = list(rtcm_msg)
            self._rtcm_pub.publish(out)
            self._rtk_yayinlanan_frag += 1
            return
        parcalar = fragment_for_inject(
            rtcm_msg, max_payload=self._rtk_max_payload
        )
        for chunk, fragmented in parcalar:
            inject = GpsInjectData()
            inject.timestamp = int(
                self.get_clock().now().nanoseconds / 1000
            )
            inject.device_id = self._rtk_device_id
            inject.len = len(chunk)
            inject.flags = 1 if fragmented else 0
            # data alanı uint8[300] sabit; chunk'u 0 ile padle
            dolgu = _GPS_INJECT_DATA_SIZE - len(chunk)
            inject.data = list(chunk) + [0] * dolgu
            self._gps_inject_pub.publish(inject)
            self._rtk_yayinlanan_frag += 1

    def _rtk_tani_yayinla(self) -> None:
        """1 Hz RTK tanı log'u; köprü sağlığını dışarıya bildirir."""
        try:
            self.get_logger().info(
                f'rtk: msg={self._rtk_alinan_msg} '
                f'frag={self._rtk_yayinlanan_frag} '
                f'tampon={len(self._rtk_tampon)}B '
                f'sync_kayip={self._rtk_sync_kayip} '
                f'cb_hata={self._rtk_cb_hata}'
            )
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(f'rtk tani log hata: {e}')

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
            (BatteryStatus,
             f'{ns}/fmu/out/battery_status', self._on_battery),
            (VehicleStatus,
             f'{ns}/fmu/out/vehicle_status_v1', self._on_vehicle_status),
            (VehicleLocalPosition,
             f'{ns}/fmu/out/vehicle_local_position', self._on_local_pos),
            (EstimatorStatusFlags,
             f'{ns}/fmu/out/estimator_status_flags', self._on_estimator),
            (SensorGps,
             f'{ns}/fmu/out/vehicle_gps_position', self._on_gps),
            (VehicleGlobalPosition,
             f'{ns}/fmu/out/vehicle_global_position',
             self._on_global_pos),
            (HomePosition,
             f'{ns}/fmu/out/home_position', self._on_home),
            (VehicleAttitude,
             f'{ns}/fmu/out/vehicle_attitude', self._on_attitude),
            (ManualControlSetpoint,
             f'{ns}/fmu/out/manual_control_setpoint',
             self._on_manual_control),
        ]
        for msg_type, topic, cb in subs:
            self.create_subscription(msg_type, topic, cb, _PX4_QOS)

    # =================================================================
    # PX4 CALLBACKS — sadece mapper'ı çağırırlar
    # =================================================================
    def _on_battery(self, msg: BatteryStatus) -> None:
        """Batarya telemetrisini AgentStatus'a işler."""
        map_battery(msg, self._status)

    def _on_vehicle_status(self, msg: VehicleStatus) -> None:
        """Araç durumunu işler; SITL'de offboard kaybını yakalar."""
        prev_offboard = self._status.offboard_active
        map_vehicle_status(msg, self._status)

        # SITL: RC kaybı nedeniyle PX4 offboard'dan çıkarsa hemen yeniden iste.
        # Gerçek uçuşta bu blok hiç çalışmaz (sitl_mode=False).
        if (self._sitl_mode
                and prev_offboard
                and not self._status.offboard_active
                and self._status.armed):
            self.get_logger().warn(
                'SITL: Offboard kayboldu, yeniden isteniyor...'
            )
            self._cmd_sender.set_offboard_mode()

        self.get_logger().info(
            f'[DBG] nav_state={msg.nav_state} armed={self._status.armed} '
            f'offboard_active={self._status.offboard_active}',
            throttle_duration_sec=1.0,
        )

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
    # MAVROS ABONELİKLERİ + CALLBACKS (use_mavros yolu)
    # =================================================================
    def _setup_mavros_subscriptions(self) -> None:
        """MAVROS telemetri topic'lerine abone ol.

        Topic'ler mavros_node namespace'i altinda: /drone_{id}/mavros/...
        Durum/olay topic'leri reliable; sensor-tipi topic'ler best_effort.
        NOT: Kesin QoS profilleri sim'de 'ros2 topic info --verbose' ile
        dogrulanmalidir.
        """
        ns = self._fmu_ns
        # Durum/olay topic'leri — reliable (varsayilan depth=10)
        self.create_subscription(
            State, f'{ns}/mavros/state', self._on_mav_state, 10
        )
        # battery: mavros sys plugin'i BEST_EFFORT yayinlar (sim'de 'topic
        # info -v' ile dogrulandi, 2026-07-16). Reliable abonelik QoS
        # uyusmazligindan HIC veri almiyordu (batarya 0.0 gorunuyordu).
        self.create_subscription(
            BatteryState, f'{ns}/mavros/battery',
            self._on_mav_battery, qos_profile_sensor_data
        )
        self.create_subscription(
            MavHomePosition, f'{ns}/mavros/home_position/home',
            self._on_mav_home, 10
        )
        # Sensor-tipi yuksek hizli topic'ler — best_effort
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
        """MAVROS State -> AgentStatus (armed, mode, failsafe proxy)."""
        mav_map_state(msg, self._status)

    def _on_mav_battery(self, msg: BatteryState) -> None:
        """MAVROS BatteryState -> AgentStatus batarya."""
        mav_map_battery(msg, self._status)

    def _on_mav_odom(self, msg: Odometry) -> None:
        """MAVROS Odometry -> AgentStatus konum/hiz/heading (ENU->NED)."""
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
        """MAVROS EstimatorStatus -> AgentStatus kestirici saglik."""
        mav_map_estimator(msg, self._status)

    def _on_mav_rc(self, msg: RCIn) -> None:
        """MAVROS RCIn -> AgentStatus rc_link_ok."""
        mav_map_rc(msg, self._status)

    # =================================================================
    # OFFBOARD HEARTBEAT (50 Hz)
    # =================================================================
    def _publish_fake_rc(self) -> None:
        """SITL modunda PX4'e sahte RC sinyali gönderir.

        Gerçek donanımda bu metot hiç çağrılmaz (_fake_rc_pub oluşturulmaz).
        PX4'ün RC kaybı failsafe'ini tetiklememesi için neutral stick pozisyonu
        ile valid=True gönderilir. Offboard modda stick değerleri
        PX4 tarafından yok sayılır; sadece 'RC bağlı' bilgisi önemli.
        """
        msg = ManualControlSetpoint()
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        msg.roll = 0.0
        msg.pitch = 0.0
        msg.throttle = 0.0
        msg.yaw = 0.0
        msg.valid = True
        self._fake_rc_pub.publish(msg)

    def _offboard_tick(self) -> None:
        """50 Hz'de çalışır.

        OffboardControlMode her zaman yayınlanır — PX4 moda geçiş için bunu
        görmek ister, diğer modlarda yoksayar.

        TrajectorySetpoint sadece offboard aktifken ve konum geçerliyken
        gönderilir; bu sayede drone mevcut konumda bekler (hold).
        """
        # Konum geçerliyken cache'i güncelle
        if self._status.xy_valid and self._status.z_valid:
            self._cached_pos_x = self._status.pos_x
            self._cached_pos_y = self._status.pos_y
            self._cached_pos_z = self._status.pos_z
            _yaw = math.radians(self._status.heading_deg)
            self._cached_yaw_rad = (_yaw + math.pi) % (2 * math.pi) - math.pi

        # Formation setpoint tazeyse kullan; eskimişse hold'a düş.
        now = self.get_clock().now().nanoseconds * 1e-9
        setpoint_fresh = (
            self._latest_setpoint is not None
            and (now - self._setpoint_stamp) < self._setpoint_timeout_s
        )

        # offboard_streaming kapalıysa (land/rtl/disarm sonrası)
        # offboard mode ve setpoint yayınlama — yoksa PX4 sürekli
        # offboard'a geri zorlanır ve land/rtl modu tutmaz.
        if not self._offboard_streaming:
            if self._sitl_mode:
                self._publish_fake_rc()
            return

        use_velocity = setpoint_fresh and self._latest_setpoint.velocity_valid

        if use_velocity and self._velocity_only:
            # B: saf hız modu (PX4 pozisyon yapmaz, SVT ROS'ta tutar)
            self._cmd_sender.publish_offboard_velocity_mode()
        elif use_velocity:
            # A: pozisyon + hız feedforward (PX4 pozisyon sahibi)
            self._cmd_sender.publish_offboard_position_velocity_mode()
        else:
            # Setpoint stale/yok → pozisyon-hold (velocity_only'de bile GÜVENLİ:
            # flyaway yerine konum tutar → failsafe).
            self._cmd_sender.publish_offboard_position_mode()

        # SITL: sahte RC sinyali — gerçek donanımda çalışmaz
        if self._sitl_mode:
            self._publish_fake_rc()
            # Offboard isteniyorsa ama aktif değilse 2Hz'de yeniden talep et.
            # NOT: 10Hz denendi ama mode komutunu (DO_SET_MODE) flood'lamak arm
            # geçişinde çakışma yaratıp bir drone'un disarm olmasına yol açtı.
            # 2Hz kanıtlanmış güvenli değer — sync için sync_takeoff zaten
            # 3/3 offboard'ı bekliyor, bu yeterli.
            if (self._offboard_streaming
                    and not self._status.offboard_active
                    and self._status.armed):
                self._offboard_rearm_counter += 1
                if self._offboard_rearm_counter >= 25:  # 50Hz / 25 = 2Hz
                    self._offboard_rearm_counter = 0
                    self.get_logger().warn(
                        'SITL: Offboard yeniden talep ediliyor...',
                        throttle_duration_sec=1.0,
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
            target_yaw = (_yaw + math.pi) % (2 * math.pi) - math.pi
        elif self._target_altitude_ned is not None:
            # Kalkış/irtifa-hold: yatayda dondurulmuş çapa,
            # dikeyde hedef irtifa.
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
            # Yerde/komut yok: anlık konumda bekle.
            target_x = self._cached_pos_x
            target_y = self._cached_pos_y
            target_z = self._cached_pos_z
            target_yaw = self._cached_yaw_rad

        if use_velocity and self._velocity_only:
            # B: SADECE hız (pozisyon=NaN). Konum kontrolü SVT'de.
            sp = self._latest_setpoint
            self._cmd_sender.publish_velocity_setpoint(
                float(sp.vx), float(sp.vy), float(sp.vz),
                yaw_rad=target_yaw,
            )
        elif use_velocity:
            # A: pozisyon + hız feedforward
            sp = self._latest_setpoint
            self._cmd_sender.publish_position_velocity_setpoint(
                target_x, target_y, target_z,
                float(sp.vx), float(sp.vy), float(sp.vz),
                yaw_rad=target_yaw,
            )
        else:
            # Stale/yok → pozisyon-hold (failsafe, flyaway önler)
            self._cmd_sender.publish_position_setpoint(
                target_x, target_y, target_z,
                yaw_rad=target_yaw,
            )

    def _on_swarm_origin(self, msg: SwarmOrigin) -> None:
        """Ortak NED origin'i PX4'e gönderir.

        Lider drone bu mesajı yayınlar; diğer drone'lar (ve lider kendi
        kendine) SET_GPS_GLOBAL_ORIGIN komutuyla PX4'ü senkronize eder.
        Aynı sequence tekrar gönderilmez.
        """
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
        # Ortak origin PX4'e uygulandı: telemetride bildir ki formation_node
        # (ve diğer tüketiciler) shared→local dönüşümünü güvenle yapabilsin.
        # Bu flag true olmadan formation_node setpoint üretmez.
        self._status.origin_synced = True
        self._status.origin_sequence = msg.sequence
        self.get_logger().info(
            f'GPS origin set: lat={msg.origin_lat_deg:.6f}, '
            f'lon={msg.origin_lon_deg:.6f}, '
            f'alt={msg.origin_alt_amsl_m:.1f}m (seq={msg.sequence})'
        )

    def _on_agent_setpoint(self, msg: AgentSetpoint) -> None:
        """
        formation_node'dan gelen setpoint'i saklar.

        Args:
            msg (AgentSetpoint): Hedef pozisyon ve hız bilgisi.
        """
        # C MODU (saf hız): setpoint position_valid=False, velocity_valid=True
        # gelir. Eskiden "not position_valid → return" idi; bu saf-hız komutunu
        # ÇÖPE atıp _latest_setpoint'i bayatlatıyor, bridge position-hold'a
        # düşüyordu (dron kıpırdamıyor). Doğru kontrol: İKİSİ de geçersizse
        # (gerçekten boş setpoint) reddet; biri geçerliyse kabul et.
        if not (msg.position_valid or msg.velocity_valid):
            return
        self._latest_setpoint = msg
        self._setpoint_stamp = self.get_clock().now().nanoseconds * 1e-9

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
            # NED: yukarı = negatif Z. Hedef, MEVCUT konuma görelidir:
            # origin SET_GPS_GLOBAL_ORIGIN ile dünya orijinine senkron
            # olduğunda yer seviyesi z=0 DEĞİLDİR (örn. z=-37). Mutlak
            # -altitude vermek "aşağı in" komutuna dönüşür (SITL'de
            # yakalandı: drone arm oldu, kalkmadı). Bu yüzden mevcut
            # z'den altitude kadar TIRMAN.
            self._target_altitude_ned = self._cached_pos_z - altitude
            # Yatay çapayı şimdi dondur — tırmanış boyunca sabit kalsın.
            self._takeoff_anchor_x = self._cached_pos_x
            self._takeoff_anchor_y = self._cached_pos_y
            self.get_logger().info(
                f'Offboard kalkış hedefi: {altitude:.1f}m '
                f'(NED z={self._target_altitude_ned:.1f}) '
                f'çapa=({self._takeoff_anchor_x:.2f}, '
                f'{self._takeoff_anchor_y:.2f})'
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
