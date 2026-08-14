"""
px4_bridge.py

PX4 ↔ FSM köprüsü — ana ROS2 node.

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

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
    qos_profile_sensor_data,
)

# Komut için basit string (FSM) ve RTCM bayt akışı (mesh -> RTK)
from rcl_interfaces.msg import SetParametersResult
from std_msgs.msg import String, UInt8MultiArray

# Bizim mesaj formatımız
from swarm_interfaces.msg import AgentSetpoint, AgentStatus, SwarmOrigin

# MAVROS telemetri mesaj tipleri
from diagnostic_msgs.msg import DiagnosticArray
from mavros_msgs.msg import EstimatorStatus, GPSRAW, RCIn, RTCM, State
from mavros_msgs.msg import HomePosition as MavHomePosition
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import BatteryState, NavSatFix

# Aynı paket içindeki yardımcılar (MAVROS yolu)
from .mavros_command_sender import MavrosCommandSender
from .mavros_telemetry_mapper import (
    map_battery as mav_map_battery,
    map_estimator_status as mav_map_estimator,
    map_global_position as mav_map_global,
    map_gps_raw as mav_map_gps,
    map_home as mav_map_home,
    map_odometry as mav_map_odom,
    map_diagnostics as mav_map_diag,
    map_rc_in as mav_map_rc,
    map_state as mav_map_state,
    map_velocity_local as mav_map_velocity,
)

# RTK: RTCM3 framer (saf modül, ROS bağımsız). Ayrı node yerine bu
# köprünün içinde — ayrı process yükünü ödememek için. Parse mantığı
# ayrı modülde (test edilebilir); RTK callback'i hızlı (~38 µs) olduğu
# için tek thread'de offboard heartbeat'i etkilemez.
from .rtcm_packing import iter_rtcm_messages


# PX4 BEST_EFFORT QoS — PX4 telemetri bu profili kullanır
_PX4_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=5,
)

# --- RTK / RTCM sabitleri (eski rtk_bridge'den taşındı) ---
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
# Burun-ileri: hedefe bu mesafeden yakınken dönme (spin/toilet-bowl önle),
# mevcut yönü tut. Uzaktayken hedefe yönelip düz git.
_BURUN_ILERI_MIN_M = 0.8

# ARM, OFFBOARD aktifleşene kadar bu kadar bekler. Süre dolarsa ARM
# GÖNDERİLMEZ ve hata loglanır — FSM'in ARMING timeout'u (15 sn) devreye girip
# temiz şekilde IDLE'a döner. Bilerek 15'ten küçük: hata, FSM pes etmeden
# önce logda görünsün.
_ARM_OFFBOARD_BEKLEME_S = 8.0

# --- Ortak origin dogrulamasi (bkz. _origin_dogrula) ------------------------
# TOLERANS 1.0 m: RTK'da konum hatasi cm mertebesinde, ortak origin oturmussa
# fark santimlerde kalir. 1 Agustos'ta olculen ayrilik 12.1 m idi — yani esik
# gurultuye degil, gercek ayrisma varsa tetiklenir.
_ORIGIN_TOLERANS_M = 1.0
# DIKEY tolerans daha genis: PX4'un yerel z'si baro+GPS fuzyonu, ham GPS
# AMSL'ine gore zamanla birkac on santim gezinir. 1.5 m'lik gercek ayrisma
# (1 Agustos'ta olculen) bunun cok uzerinde, yani esik yine de yakalar.
_ORIGIN_TOLERANS_Z_M = 1.0
# Tekrar gonderim araligi: PX4 kabul edip EKF'i yeniden kurmasi zaman alir,
# saniyede bir bombardiman etmenin anlami yok.
_ORIGIN_TEKRAR_ARALIK_S = 5.0
_ORIGIN_DOGRULAMA_PERIYOT_S = 1.0
_M_PER_DEG_LAT = 111320.0

# --- Yerel yorunge yurutucusu (bkz. _yurutucu_ilerlet) ----------------------
# Yurutucu, setpoint'i hedefe dogru 50 Hz'de KENDI yurutur ve PX4'e hiz
# ileri-beslemesiyle birlikte verir. Amac mesh'i kontrol dongusunden cikarmak.
#
# 2 Agustos'ta olculdu: goto'lar YKI'de 10 Hz uretiliyor ama drone'a 6.6 Hz
# ve DUZENSIZ variyor (103/203/304 ms). Sebep firmware'de yazili
# (mesh_config.h:517): POSE ve GOTO broadcast gidiyor, broadcast'te 802.11
# ACK/retry YOK, havada kaybolan paket telafi edilmiyor. Kayip ~%30.
#
# Laptop yuruyen setpoint gonderdiginde her kayip bir SICRAMA uretiyordu:
# 304 ms'lik bosluktan sonra gelen nokta 0.6 m ileridedir, MPC_XY_P (0.95)
# ile ~0.57 m/s'lik ani hiz talebi demektir. Operatorun "gaz bas-cek" diye
# tarif ettigi sey buydu.
#
# Yurutucuyle laptop yalniz ADIMIN HEDEFINI gonderir. Hedefin bir kez
# ulasmasi yeter: esp32_bridge onu 10 Hz'de YEREL tekrar yayinliyor
# (_guided_hedef_tekrar). Yani paket kaybi zararsizlasir — kaybolan paket
# zaten ayni hedefi tasiyordu.
_YURUTUCU_ADIM_TOLERANS_M = 1e-3   # bu kadar kalinca hedefe oturt





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
        # RC anahtar haritasi. Kumanda degisirse veya polarite ters cikarsa
        # yeniden derleme degil, baslat.sh'de tek satir degisir.
        # Saha olcumu (2026-07-22, FLYSKY): ch5 kill (2000 = AKTIF),
        # ch8 arm (1000 = disarm / 2000 = arm, PX4 armed bayragiyla dogrulandi).
        self.declare_parameter('kill_switch_kanal', 5)
        self.declare_parameter('kill_switch_esik', 1500)
        self.declare_parameter('kill_switch_ters', False)
        self.declare_parameter('arm_switch_kanal', 8)
        self.declare_parameter('arm_switch_esik', 1500)
        self.declare_parameter('arm_switch_ters', False)
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
        self._kill_kanal = int(self.get_parameter('kill_switch_kanal').value)
        self._kill_esik = int(self.get_parameter('kill_switch_esik').value)
        self._kill_ters = bool(self.get_parameter('kill_switch_ters').value)
        self._arm_kanal = int(self.get_parameter('arm_switch_kanal').value)
        self._arm_esik = int(self.get_parameter('arm_switch_esik').value)
        self._arm_ters = bool(self.get_parameter('arm_switch_ters').value)

        # Drone namespace'i — mavros topic'leri /drone_{id}/mavros/...
        self._fmu_ns = f'/drone_{self._agent_id}'

        # Drone'un anlık durumu — callback'ler bunu doldurur
        self._status = AgentStatus()
        self._status.agent_id = self._agent_id

        # OFFBOARD streaming aktif mi — FSM "offboard" gönderince True olur
        self._offboard_streaming: bool = False

        # ARM, OFFBOARD aktifleşmesini bekliyor mu (bkz. _on_fsm_command
        # 'arm' dalı: PX4 ARMLIYKEN yerde OFFBOARD'a geçmiyor).
        self._arm_bekliyor: bool = False
        self._arm_istek_t: float = 0.0

        # SITL: offboard yeniden-talep sayacı (50Hz tick'te rate-limit için)
        self._offboard_rearm_counter: int = 0

        # Hedef kalkış irtifası (NED: negatif=yukarı) — None ise hold modu
        self._target_altitude_ned: float | None = None
        # Kalkis yatay kilidi (bkz. _kalkis_kilidi_aktif): ilk tirmanista
        # yatay KONUM tutulmaz, yatay HIZ SIFIRLANIR.
        self._takeoff_baslangic_z: float | None = None
        self._kalkis_kilidi_acildi = False
        # Yatay kilidin arm anindaki referans irtifasi (NED z). Takeoff
        # komutu gelene kadar kilit BUNU kullanir; bkz. _kalkis_kilidi_aktif.
        self._arm_z: float | None = None
        self.declare_parameter('kalkis_kilit_irtifa_m', 2.5)
        self._kalkis_kilit_irtifa_m = float(
            self.get_parameter('kalkis_kilit_irtifa_m').value)

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
        # ORIGIN DOGRULAMASI (1 Agustos 22:18, ylp01 kacti — bkz.
        # _origin_dogrula). Origin'in SON GONDERILEN degeri burada tutulur;
        # PX4 unutursa (FCU yeniden baslarsa) tekrar gonderilebilsin.
        self._origin_lat: float | None = None
        self._origin_lon: float | None = None
        self._origin_alt: float | None = None
        self._origin_son_gonderim: float = 0.0
        self._origin_uyari_verildi: bool = False

        # --- Yerel yorunge yurutucusu ------------------------------------
        # Hizlar burada, gorev betiginde DEGIL: yorunge artik burada
        # uretiliyor. baslat.sh'den -p ile degistirilebilir.
        self.declare_parameter('guided_hiz_yatay_mps', 2.0)
        self.declare_parameter('guided_hiz_dikey_mps', 1.0)
        # TASMA: yurutulen setpoint ucagin OLCULEN yerinden en fazla bu kadar
        # onde olabilir. Gorev betiginde de vardi ama orada 6.6 Hz'lik ve
        # gecikmeli telemetriye dayaniyordu; burada 50 Hz ve gecikmesiz.
        self.declare_parameter('guided_tasma_m', 3.0)
        # IVME SINIRI — 2 Agustos ucusunda olculdu, ilk surumde YOKTU.
        # Detay _yurutucu_ilerlet'te. MPC_ACC_HOR ucakta 2.0; altinda kaliyoruz.
        self.declare_parameter('guided_ivme_yatay_mps2', 1.5)
        self.declare_parameter('guided_ivme_dikey_mps2', 1.0)
        # GECIKME TELAFISI — bkz. _yurutucu_ilerlet. PX4 konum terimini
        # ileri-beslemenin USTUNE ekliyor; onu kismen geri cikariyoruz.
        # guided_konum_kp UCAKTAKI MPC_XY_P ILE AYNI OLMALI (olculdu: 0.95).
        self.declare_parameter('guided_konum_kp', 0.95)
        self.declare_parameter('guided_telafi_orani', 0.7)
        self._hiz_yatay = float(self.get_parameter('guided_hiz_yatay_mps').value)
        self._hiz_dikey = float(self.get_parameter('guided_hiz_dikey_mps').value)
        self._ivme_yatay = float(
            self.get_parameter('guided_ivme_yatay_mps2').value)
        self._ivme_dikey = float(
            self.get_parameter('guided_ivme_dikey_mps2').value)
        self._konum_kp = float(self.get_parameter('guided_konum_kp').value)
        self._telafi_orani = float(self.get_parameter('guided_telafi_orani').value)
        self._yurutucu_tasma_m = float(self.get_parameter('guided_tasma_m').value)
        self._yurutulen: list | None = None      # [kuzey, dogu, asagi] NED
        self._yurutucu_son_t: float | None = None
        self._yur_v_yatay: float = 0.0           # yurutucunun ANLIK hizi
        self._yur_v_dikey: float = 0.0

        # CANLI PARAMETRE — bkz. _on_parametre_degisti.
        self.add_on_set_parameters_callback(self._on_parametre_degisti)

        # PX4'e komut gönderen yardımcı — MAVROS servis/topic'lerine yazar.
        self._cmd_sender = MavrosCommandSender(
            self,
            namespace=self._fmu_ns,
        )

        # Telemetri abonelikleri (MAVROS)
        self._setup_mavros_subscriptions()

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

        # KURULUM BITTI — canli parametre kapisi BURADAN SONRA acilir.
        # Bunun oncesinde her declare_parameter geri cagriyi tetikliyor ve
        # beyaz listede olmayan her parametre reddedilirdi. Bkz.
        # _on_parametre_degisti.
        self._parametre_kurulumu_bitti = True

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
        """RTCM aboneliği + MAVROS send_rtcm publisher + tanı timer kurar."""
        # Sahada yeniden derlemeden ayarlanabilsin diye parametre.
        self.declare_parameter('rtk_makul_payload', _RTK_MAKUL_PAYLOAD)
        self._rtk_makul_payload = int(
            self.get_parameter('rtk_makul_payload').value
        )

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
        # RTK çıkışı: /mavros/gps_rtk/send_rtcm — parçalamayı MAVROS yapar
        # (GPS_RTCM_DATA, ~720B/mesaj = 4 fragman x 180B).
        self._rtcm_pub = self.create_publisher(
            RTCM,
            f'{ns}/mavros/gps_rtk/send_rtcm',
            _GPS_INJECT_QOS_DEPTH,
        )
        self.create_timer(_RTK_DIAG_PERIOD_S, self._rtk_tani_yayinla)
        # Origin dogrulamasi SUREKLI kosar: FCU ucus ARASINDA da yeniden
        # baslayabilir (pil degisimi) ve o an kimse bakmiyor olabilir.
        self.create_timer(_ORIGIN_DOGRULAMA_PERIYOT_S, self._origin_dogrula)

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
        """RTCM mesajını MAVROS'a bütün olarak yayınlar.

        MAVROS, GPS_RTCM_DATA MAVLink mesajına kendisi parçalar
        (max ~720B/mesaj); bizim parçalamamıza gerek yok.
        """
        out = RTCM()
        out.header.stamp = self.get_clock().now().to_msg()
        out.data = list(rtcm_msg)
        self._rtcm_pub.publish(out)
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
    # MAVROS ABONELİKLERİ + CALLBACKS
    # =================================================================
    def _setup_mavros_subscriptions(self) -> None:
        """MAVROS telemetri topic'lerine abone ol.

        Topic'ler mavros_node namespace'i altinda: /drone_{id}/mavros/...
        Durum/olay topic'leri reliable; sensor-tipi topic'ler best_effort.
        """
        ns = self._fmu_ns
        # Durum/olay topic'leri — reliable (varsayilan depth=10)
        self.create_subscription(
            State, f'{ns}/mavros/state', self._on_mav_state, 10
        )
        # battery BEST_EFFORT yayinlanir; reliable abonelik veri alamaz.
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
            TwistStamped, f'{ns}/mavros/local_position/velocity_local',
            self._on_mav_vel, qos_profile_sensor_data
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
        # /diagnostics namespace ALTINDA DEGIL, kokte yayinlanir (ROS
        # yakinsamasi). PREARM_CHECK biti buradan okunuyor — PX4 emniyet
        # anahtarini ayri bir alanda bildirmedigi icin tek gozlenebilir kaynak.
        self.create_subscription(
            DiagnosticArray, '/diagnostics',
            self._on_diagnostics, qos_profile_sensor_data
        )

    def _on_mav_state(self, msg: State) -> None:
        """MAVROS State -> AgentStatus (armed, mode, failsafe proxy)."""
        mav_map_state(msg, self._status)

    def _on_mav_battery(self, msg: BatteryState) -> None:
        """MAVROS BatteryState -> AgentStatus batarya."""
        mav_map_battery(msg, self._status)

    def _on_mav_odom(self, msg: Odometry) -> None:
        """MAVROS Odometry -> AgentStatus konum/heading (ENU->NED)."""
        mav_map_odom(msg, self._status)

    def _on_mav_vel(self, msg: TwistStamped) -> None:
        """MAVROS velocity_local -> AgentStatus hiz (dunya-ENU->NED)."""
        mav_map_velocity(msg, self._status)

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

    def _on_diagnostics(self, msg: DiagnosticArray) -> None:
        """MAVROS diagnostics -> ready_to_arm (PREARM_CHECK biti)."""
        onceki = self._status.ready_to_arm
        if not mav_map_diag(msg, self._status):
            return
        if self._status.ready_to_arm != onceki:
            if self._status.ready_to_arm:
                self.get_logger().info('[PREARM] arm edilebilir')
            else:
                self.get_logger().warning(
                    '[PREARM] arm ENGELLI (emniyet anahtari / on-kontrol)'
                )

    def _on_mav_rc(self, msg: RCIn) -> None:
        """MAVROS RCIn -> rc_link_ok + kill_switch_active."""
        onceki_kill = self._status.kill_switch_active
        mav_map_rc(
            msg, self._status,
            kill_kanal=self._kill_kanal, kill_esik=self._kill_esik,
            kill_ters=self._kill_ters,
            arm_kanal=self._arm_kanal, arm_esik=self._arm_esik,
            arm_ters=self._arm_ters,
        )
        # Durum degisimini bir kez logla: sahada "kill acik miydi" sorusunun
        # cevabi log'da kalsin. Her mesajda basmak akisi bogar (RC ~20 Hz).
        if self._status.kill_switch_active != onceki_kill:
            if self._status.kill_switch_active:
                self.get_logger().warning('[RC] KILL SWITCH AKTIF')
            else:
                self.get_logger().info('[RC] kill switch birakildi')

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
            return

        # ARM, OFFBOARD'ın aktifleşmesini bekliyor (bkz. 'arm' dalı).
        # Setpoint akışı yukarıdaki return'den sonra başladığı için PX4 modu
        # birkaç tick içinde kabul eder; kabul edilince ARM'i gönderiyoruz.
        if self._arm_bekliyor:
            if self._status.offboard_active:
                self._arm_bekliyor = False
                self._cmd_sender.arm()
                self.get_logger().info('OFFBOARD aktif → ARM gönderildi')
            elif (now - self._arm_istek_t) > _ARM_OFFBOARD_BEKLEME_S:
                # ARM GÖNDERMİYORUZ: OFFBOARD'sız armlamak dronu tam da
                # kaçındığımız "ARMED'da takılı" durumuna sokardı. FSM'in
                # ARMING timeout'u IDLE'a döndürecek.
                self._arm_bekliyor = False
                self._offboard_streaming = False
                self.get_logger().error(
                    f'OFFBOARD {_ARM_OFFBOARD_BEKLEME_S:.0f}s içinde '
                    f'aktifleşmedi (mod={self._status.flight_mode}) — ARM '
                    f'GÖNDERİLMEDİ. Dron yerde ve disarm kalıyor.'
                )

        use_velocity = setpoint_fresh and self._latest_setpoint.velocity_valid

        # YÜRÜTÜCÜ KAPISI — iki şart:
        #   1) Gönderen hız VERMEDİYSE (guided goto yolu böyle: esp32_bridge
        #      yalnız position_valid koyuyor). Hız veren yollara DOKUNMUYORUZ.
        #   2) Setpoint KAÇINMADAN gelmiyorsa. basit_kacinma çıkışını
        #      SOURCE_COLLISION_AVOIDANCE ile etiketliyor ve o bir KAÇIŞ
        #      manevrası — yürütmek tepkiyi 2 m/s'e yavaşlatır. Seyirde
        #      düzgünlük istiyoruz, kaçışta SERTLİK. Takas doğru yönde.
        yurutucu_aktif = (
            setpoint_fresh
            and not self._latest_setpoint.velocity_valid
            and self._latest_setpoint.source
            != AgentSetpoint.SOURCE_COLLISION_AVOIDANCE
        )

        if use_velocity and self._velocity_only:
            # B: saf hız modu (PX4 pozisyon yapmaz, SVT ROS'ta tutar)
            self._cmd_sender.publish_offboard_velocity_mode()
        elif use_velocity or yurutucu_aktif:
            # A: pozisyon + hız feedforward (PX4 pozisyon sahibi)
            self._cmd_sender.publish_offboard_position_velocity_mode()
        else:
            # Setpoint stale/yok → pozisyon-hold (velocity_only'de bile
            # GÜVENLİ: flyaway yerine konum tutar → failsafe).
            self._cmd_sender.publish_offboard_position_mode()

        # SITL: offboard kaybi kurtarmasi — gerçek donanımda çalışmaz
        if self._sitl_mode:
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
            # IRTIFA REFERANSI KALKISLA AYNI OLMALI (2 Agustos).
            #
            # takeoff YERE GORELI calisiyor:
            #     _target_altitude_ned = _cached_pos_z - altitude
            # cunku origin dunya orijinine senkronken zemin z=0 DEGIL.
            # Ama goto MUTLAK geliyordu (sp.z = -irtifa). Ikisi ayni frame'de
            # olmayinca ucak kalkistan sonra aradaki fark kadar ALCALIYOR.
            #
            # OLCULDU (ylp00, 2 Agustos): zemin NED z = -1.4. takeoff 8.0 m ->
            # hedef -9.4 (yerden 8 m, dogru). Ardindan ilk goto mutlak -8.0
            # deyince ucak 1.4 m alcaldi, mesh alt_m 8.0'dan 6.6'ya dustu.
            # YKI'nin plan hedefi 8.0 oldugu icin uzaklik 1.3-1.4 m'de
            # DONDU KALDI (TOLERANS_M=1.0) ve gorev adim 1'de sonsuza kadar
            # bekledi. Operator uc kez elle indirmek zorunda kaldi.
            #
            # Onceki sahada zemin z=0'a denk geliyordu, fark sifirdi ve hata
            # gorunmuyordu — saha degisince ortaya cikti.
            #
            # Kalkis referansi VARSA (takeoff ile land/rtl/disarm arasi) goto
            # da ona gore yorumlanir: "8 m" = kalkis zemininden 8 m. Referans
            # yoksa (havada baslatilan guided) eski mutlak davranis korunur.
            target_z = float(sp.z)
            if self._takeoff_baslangic_z is not None:
                target_z = self._takeoff_baslangic_z + float(sp.z)
            if sp.heading_valid:
                # Yön açıkça verildi (formasyon her zaman verir) → onu kullan.
                _yaw = math.radians(float(sp.heading_deg))
                target_yaw = (_yaw + math.pi) % (2 * math.pi) - math.pi
            else:
                # BURUN-İLERİ: yön verilmedi (guided goto) → hedefe DOĞRU yönel,
                # düz git (yan/geri değil). Her tick'te hedefe bakarak tüm yol
                # boyunca burun ileri. Hedefe çok yakınken dönme (spin önle),
                # mevcut yönü tut. NED: yaw=0 kuzey, +doğu.
                dx = target_x - self._cached_pos_x
                dy = target_y - self._cached_pos_y
                if math.hypot(dx, dy) >= _BURUN_ILERI_MIN_M:
                    target_yaw = math.atan2(dy, dx)
                else:
                    target_yaw = self._cached_yaw_rad
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

        # YATAY KİLİT — ilk tırmanışta yatay KONUM tutma YOK.
        #
        # 1 Ağustos'ta ylp00 kalkışta devrildi ve pervaneleri kırıldı. Sebep,
        # uçak daha YERDEYKEN PX4'ün yatay KONUM tutması: EKF konumu 1.42 m
        # sıçrayınca PX4 gerçek olmayan bir hatayı düzeltmek için ~14° eğildi,
        # pervane yere vurdu. (Ölçüldü: kalkış çapası 6 sn'de 0.90 m kaydı,
        # z hiç değişmedi — uçak yerden hiç kesilmemişti.)
        #
        # Kilit süresince yatayda HIZ SIFIR komutu gider (publish_kalkis_setpoint):
        # "yatayda kımıldama" aynen sağlanır ama kovalanacak birikmiş konum
        # hatası olmadığı için eğim küçük kalır. Kilit irtifasını geçince
        # normal konum kontrolüne dönülür.
        if self._kalkis_kilidi_aktif():
            # Takeoff HENUZ gelmediyse hedef irtifa yok — o zaman MEVCUT
            # irtifayi tut. Yani "arm oldun ama kalkis komutu gelmedi"
            # penceresinde ucak yerde kalir, sadece yatayda konum tutmaz.
            # Buraya self._target_altitude_ned'i dogrudan vermek None
            # yayinlamak olurdu.
            hedef_z = (self._target_altitude_ned
                       if self._target_altitude_ned is not None
                       else self._cached_pos_z)
            self._cmd_sender.publish_kalkis_setpoint(
                hedef_z, yaw_rad=self._cached_yaw_rad)
            # Kilit boyunca yurutucu SIFIRDA tutulur. Kilit acildiginda
            # ucagin O ANKI yerinden baslasin; yoksa kilit oncesindeki
            # bayat bir noktadan devam eder ve kilit biter bitmez sicrama
            # olur. Capa da ayni anda yeniden kuruluyor (bkz.
            # _kalkis_kilidi_aktif), ikisi tutarli kalmali.
            self._yurutucu_sifirla()
            return

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
        elif yurutucu_aktif:
            # C: YEREL YÜRÜTÜCÜ — hedefe 50 Hz'de yürür, PX4'e konum + hız
            # ileri-beslemesi verir. Mesh kontrol döngüsünden çıkar.
            yur, vel = self._yurutucu_ilerlet(
                (target_x, target_y, target_z), now)
            self._cmd_sender.publish_position_velocity_setpoint(
                yur[0], yur[1], yur[2], vel[0], vel[1], vel[2],
                yaw_rad=target_yaw,
            )
        else:
            # Stale/yok → pozisyon-hold (failsafe, flyaway önler).
            # HAT ÖLÜRSE UÇAK PARK EDER özelliği burada yaşıyor: setpoint
            # bayatlayınca yürütücü devreden çıkar ve uçak son yerinde tutar.
            self._yurutucu_sifirla()
            self._cmd_sender.publish_position_setpoint(
                target_x, target_y, target_z,
                yaw_rad=target_yaw,
            )

    # CANLI DEGISTIRILEBILEN PARAMETRELER: ad -> (ornek degiskeni, alt, ust)
    #
    # Yalniz YURUTUCU ayarlari burada. Kimlik (agent_id), guvenlik kablolamasi
    # (kill/arm kanallari) ve kalkis kilidi BILEREK DISARIDA: ucus ortasinda
    # degismeleri ya anlamsiz ya tehlikeli.
    #
    # Sinirlar kaza eseri sifir/negatif/absurt deger girilmesini engelliyor.
    # Ust sinirlar cömert — amac hata yakalamak, ayari kisitlamak degil.
    _CANLI_PARAMETRELER = {
        'guided_hiz_yatay_mps':   ('_hiz_yatay',        0.1, 10.0),
        'guided_hiz_dikey_mps':   ('_hiz_dikey',        0.1,  5.0),
        'guided_ivme_yatay_mps2': ('_ivme_yatay',       0.1,  5.0),
        'guided_ivme_dikey_mps2': ('_ivme_dikey',       0.1,  5.0),
        'guided_tasma_m':         ('_yurutucu_tasma_m', 0.5, 20.0),
        'guided_konum_kp':        ('_konum_kp',         0.1,  3.0),
        'guided_telafi_orani':    ('_telafi_orani',     0.0,  1.0),
    }

    def _on_parametre_degisti(self, parametreler):
        """Yurutucu ayarlarini UCAK HAVADAYKEN degistirebilmek icin.

        NEDEN VAR: bu degerler eskiden yalnizca __init__'te okunuyordu ve
        ornek degiskenine yaziliyordu. 'ros2 param set' calisir gorunuyor
        ("Set parameter successful"), 'ros2 param get' yeni degeri gosteriyor,
        ama ucak ESKI hizda ucmaya devam ediyordu — cunku kod self._hiz_yatay
        okuyor. Komut basarili, gosterge dogru, davranis yanlis: sahada saat
        yakan cinsten bir tuzak.
        Tek cikis yolu baslat.sh'i degistirip konteyneri yeniden baslatmakti
        (~40 sn; MAVROS FCU el sikismasi, EKF oturmasi, RTK yeniden fix).

        ASIL IHTIYAC: kayma olcumu (docs/NAVIGASYON_KAYMA.md Adim 1) ayni
        oturumda 2/3/4 m/s denemeyi gerektiriyor. Canli parametre olmadan her
        hiz icin ucagi indirip yigini yeniden baslatmak gerekirdi.

        HIZ DEGISIMI GUVENLI: yurutucu hedefe dogru IVME SINIRLI ilerliyor,
        yani yeni hiz basamak degil rampa olarak uygulanir. Ivme siniri da
        canli degistirilebilir ve o da yalnizca bir hiz limiti.

        HEPSI YA DA HICBIRI: once tumu dogrulanir, sonra uygulanir. Yarim
        uygulanmis bir kume (orn. hiz gecti ivme reddedildi) tutarsiz bir
        yurutucu birakirdi.

        KURULUM KAPISI — BU GERI CAGRI declare_parameter'DA DA TETIKLENIYOR.
        Ilk surumde kapi yoktu ve dugum ACILISTA COKTU: geri cagri __init__'in
        ortasinda kaydediliyordu, ardindan _setup_rtk() 'rtk_makul_payload'
        tanimliyordu, beyaz listede olmadigi icin reddediliyor ve rclpy
        InvalidParameterValueException atiyordu. Bayrak __init__'in SONUNDA
        aciliyor; boylece ileride biri yeni bir declare_parameter eklerse de
        kirilmaz.
        """
        if not getattr(self, '_parametre_kurulumu_bitti', False):
            return SetParametersResult(successful=True)   # kurulum surüyor

        for p in parametreler:
            if p.name not in self._CANLI_PARAMETRELER:
                return SetParametersResult(
                    successful=False,
                    reason=(f"'{p.name}' ucus sirasinda degistirilemez. "
                            f"Canli olanlar: "
                            f"{', '.join(sorted(self._CANLI_PARAMETRELER))}"))
            _ozellik, alt, ust = self._CANLI_PARAMETRELER[p.name]
            try:
                deger = float(p.value)
            except (TypeError, ValueError):
                return SetParametersResult(
                    successful=False, reason=f"'{p.name}' sayi olmali")
            if not (alt <= deger <= ust):
                return SetParametersResult(
                    successful=False,
                    reason=f"'{p.name}' {alt}-{ust} araliginda olmali "
                           f"(verilen {deger})")

        for p in parametreler:
            ozellik = self._CANLI_PARAMETRELER[p.name][0]
            eski = getattr(self, ozellik)
            setattr(self, ozellik, float(p.value))
            # YUKSEK SESLE: ucus kaydinda bu satir, "o ucusta hiz neydi"
            # sorusunun tek cevabi olacak.
            self.get_logger().warn(
                f'CANLI PARAMETRE: {p.name} {eski} -> {float(p.value)}')
        return SetParametersResult(successful=True)

    def _yurutucu_sifirla(self) -> None:
        """Yürütücüyü sıfırlar; bir sonraki çağrıda uçağın yerinden başlar."""
        self._yurutulen = None
        self._yurutucu_son_t = None
        self._yur_v_yatay = 0.0
        self._yur_v_dikey = 0.0

    def _yurutucu_ilerlet(self, hedef, simdi):
        """Setpoint'i hedefe doğru yürütür. (konum, hız) döndürür — ikisi NED.

        NEDEN BURADA — bkz. dosya başındaki _YURUTUCU_ADIM_TOLERANS_M notu.
        Özeti: yörünge üretimi laptoptaydı ve sonucu %30 kayıplı bir telsiz
        hattından geçiyordu; her kayıp uçakta bir sıçrama üretiyordu. Burada
        50 Hz'de ve kayıpsız üretiliyor.

        HIZ İLERİ-BESLEMESİ asıl kazanç. Bugüne kadar PX4'e yalnız KONUM
        gidiyordu; hız, PX4'ün konum hatasını kapatma çabasından DOLAYLI
        çıkıyordu ve her yeni nokta bir basamak tepkisi üretiyordu. Artık
        "2 m/s şu yöne" doğrudan söyleniyor; konum terimi hareketi üretmiyor,
        yalnız sapmayı düzeltiyor.

        İVME SINIRI — ilk sürümde YOKTU ve bedeli 2 Ağustos uçuşunda ölçüldü.
        Hız ileri-beslemesi BASAMAK olarak veriliyordu: hareket başlarken bir
        tik'te 0'dan tam hıza, biterken tam hızdan 0'a. Uçuş kaydından
        (setpoint_raw/local vs velocity_local):

            13.26  KOMUT yat=0.00  ->  13.52  KOMUT yat=2.00   (tek örnekte)
                   ölçülen: 1.30, 1.82, 2.27, 2.48, 2.57  -> sonra 2.1
            17.02  KOMUT yat=2.00  ->  17.26  KOMUT yat=0.00
                   ölçülen: 2.05, 1.52, 0.75, 0.13, 0.62 (geri sekme)
            22.26  KOMUT dik=0.00  ->  22.52  KOMUT dik=+1.00
                   ölçülen: 0.82, 1.08, 1.18  -> sonra 1.02

        Operatörün tarifi birebir: "ne yaparsa yapsın önce aşırı hızlı, sonra
        olması gereken hızda, saliselik". Yatayda %28, dikeyde %18 aşım.
        Ayrıca navigasyon başlarken bir örneklik dik=-1.00 (aşağı tam gaz)
        gidiyordu — yürütücü uçağın yerinde başlatılırken irtifa farkı
        yüzünden. Rampayla o da kalkıyor.

        Çözüm YAMUK (trapez) HIZ PROFİLİ: hız ivme sınırıyla rampalanır ve
        frene, hedefe v=0 ile varacak mesafede başlanır (v = sqrt(2*a*mesafe)).
        Hem kalkışta hem duruşta basamak yok. PX4'ün Auto modundaki yörünge
        üretecinin yaptığı işin aynısı — OFFBOARD'da o devrede olmadığı için
        burada yapıyoruz.
        """
        if self._yurutulen is None or self._yurutucu_son_t is None:
            self._yurutulen = [self._cached_pos_x, self._cached_pos_y,
                               self._cached_pos_z]
            self._yurutucu_son_t = simdi
        dt = simdi - self._yurutucu_son_t
        self._yurutucu_son_t = simdi
        # Tik atlanirsa (yuk, GC) tek adimda sicramasin diye tavan.
        dt = max(1e-3, min(dt, 0.2))

        hx, hy, hz = hedef

        # --- YATAY: yamuk (trapez) hiz profili -----------------------------
        dx, dy = hx - self._yurutulen[0], hy - self._yurutulen[1]
        yatay = math.hypot(dx, dy)
        # Hedefe v=0 ile varabilmek icin su anki mesafeden cikarilabilecek
        # en yuksek hiz: v = sqrt(2*a*mesafe). Frenlemeye zamaninda baslatir.
        v_fren = math.sqrt(2.0 * self._ivme_yatay * yatay)
        v_hedef = min(self._hiz_yatay, v_fren)
        if self._yur_v_yatay < v_hedef:
            self._yur_v_yatay = min(v_hedef,
                                    self._yur_v_yatay + self._ivme_yatay * dt)
        else:
            self._yur_v_yatay = max(v_hedef,
                                    self._yur_v_yatay - self._ivme_yatay * dt)
        adim = self._yur_v_yatay * dt
        if yatay <= max(adim, _YURUTUCU_ADIM_TOLERANS_M):
            self._yurutulen[0], self._yurutulen[1] = hx, hy
            self._yur_v_yatay = 0.0
            vx = vy = 0.0
        else:
            self._yurutulen[0] += dx * adim / yatay
            self._yurutulen[1] += dy * adim / yatay
            vx = dx / yatay * self._yur_v_yatay
            vy = dy / yatay * self._yur_v_yatay

        # --- DIKEY: ayni profil, isaret ayri tasiniyor ---------------------
        dz = hz - self._yurutulen[2]
        mesafe_z = abs(dz)
        v_fren_z = math.sqrt(2.0 * self._ivme_dikey * mesafe_z)
        v_hedef_z = min(self._hiz_dikey, v_fren_z)
        if self._yur_v_dikey < v_hedef_z:
            self._yur_v_dikey = min(v_hedef_z,
                                    self._yur_v_dikey + self._ivme_dikey * dt)
        else:
            self._yur_v_dikey = max(v_hedef_z,
                                    self._yur_v_dikey - self._ivme_dikey * dt)
        dadim = self._yur_v_dikey * dt
        if mesafe_z <= max(dadim, _YURUTUCU_ADIM_TOLERANS_M):
            self._yurutulen[2] = hz
            self._yur_v_dikey = 0.0
            vz = 0.0
        else:
            self._yurutulen[2] += math.copysign(dadim, dz)
            vz = math.copysign(self._yur_v_dikey, dz)

        # TASMA FRENI — yurutulen setpoint ucaktan kopamaz. Ucak ruzgarda
        # veya itki yetmedigi icin geride kalirsa setpoint onun onunde
        # kacmasin; yoksa ucak onu yakalamak icin hizlanir.
        konum = (self._cached_pos_x, self._cached_pos_y, self._cached_pos_z)
        one = math.dist(tuple(self._yurutulen), konum)
        if one > self._yurutucu_tasma_m:
            o = self._yurutucu_tasma_m / one
            self._yurutulen = [konum[i] + (self._yurutulen[i] - konum[i]) * o
                               for i in range(3)]

        # --- GECIKME TELAFISI (yalniz yatay) -------------------------------
        # PX4 toplam hiz talebini soyle kuruyor:
        #     talep = bizim ileri-besleme + MPC_XY_P x gecikme
        # Gecikme = yurutucu ile ucak arasindaki mesafe ve rampa boyunca
        # kaciniLmaz olarak buyuyor. 2 Agustos'ta olculdu: ~0.5 m gecikme,
        # 0.95 x 0.5 = ~0.48 m/s fazla -> komut 2.00 iken ucak 2.42.
        #
        # IVME BU ISDE KALDIRAC DEGIL, OLCULDU: 1.5 -> 0.8 yapinca asim
        # %25'ten sadece %21'e indi. Sebebi 7 m'lik gecisin neredeyse tamamen
        # gecici rejim olmasi — gecikmenin sonumlenme zaman sabiti
        # 1/MPC_XY_P ~ 1.05 sn ve seyir fazi zaten ~1 sn.
        #
        # Bu yuzden mekanizmayi DOGRUDAN hedefliyoruz: PX4'un ekleyecegi
        # terimi ileri-beslemeden geri cikariyoruz.
        #
        # TAMAMINI DEGIL: tam telafi konum duzeltmesini SIFIRLAR ve kontrol
        # fiilen saf hiza doner — surukleme birikir, tutunacak capa kalmaz.
        # Kodda o dal (_velocity_only) bilerek kacinilan yol. Oranin %70
        # olmasi, duzeltmenin %30'unu yerinde birakiyor.
        if vx or vy:
            gx = self._yurutulen[0] - konum[0]
            gy = self._yurutulen[1] - konum[1]
            tx = self._telafi_orani * self._konum_kp * gx
            ty = self._telafi_orani * self._konum_kp * gy
            nvx, nvy = vx - tx, vy - ty
            # Telafi ileri-beslemeyi TERSINE cevirmesin veya tavani asmasin:
            # gecikme buyukse (ruzgar, itki yetmemesi) isaret degistirebilirdi.
            buyuk = math.hypot(nvx, nvy)
            if buyuk > self._hiz_yatay:
                nvx, nvy = (nvx / buyuk * self._hiz_yatay,
                            nvy / buyuk * self._hiz_yatay)
            elif nvx * vx + nvy * vy < 0.0:
                nvx = nvy = 0.0          # ters yone dondu -> sifirla
            vx, vy = nvx, nvy

        return tuple(self._yurutulen), (vx, vy, vz)

    def _kalkis_kilidi_aktif(self) -> bool:
        """İlk tırmanışta yatay konum kontrolü kilitli mi?

        Kilit yalnız KALKIŞ sırasında ve yalnız kilit irtifasının ALTINDA
        geçerli. Kilit açıldığı anda yatay çapa uçağın O ANKİ yerine BİR KEZ
        yeniden kurulur: kilit boyunca rüzgârla birkaç santim sürüklenmiş
        olabilir ve eski çapaya dönmek sıçrama komutu olurdu.

        Çapanın kilit dışında yenilenmemesi ayrı bir karar — bkz. takeoff
        komutunun işlendiği yer.
        """
        # KILIT ARM'DAN BASLAR, TAKEOFF'TAN DEGIL (2 Agustos).
        #
        # Eski hali "self._target_altitude_ned is None -> return False" idi,
        # yani kilit ancak takeoff komutu islendikten SONRA devreye giriyordu.
        # ARM ile TAKEOFF arasi acikta kaldi ve bu pencere kisa degil: YKI
        # kosucusu once bir ucagi armlayip teyidini bekliyor, sonra digerini
        # armlayip onun teyidini bekliyor, ANCAK ondan sonra takeoff yolluyor.
        # Olculdu (2 Agustos, ylp00): arm 683.76, takeoff 689.93 -> 6.2 saniye
        # boyunca ucak OFFBOARD'da, armli, YERDE ve PX4 yatay KONUM tutuyor.
        # Operator "kalkarken yan yattı" diye bildirdi ve kill switch'e basti.
        #
        # Bu, 1 Agustos'ta pervane kiran arizanin AYNISI — kilit tam onun icin
        # eklenmisti ama deligi kapatmiyordu. Referansi arm irtifasina tasidik:
        # arm anindan itibaren, 2.5 m'yi gecene kadar yatayda konum tutulmaz.
        ref_z = (self._takeoff_baslangic_z if self._takeoff_baslangic_z
                 is not None else self._arm_z)
        if ref_z is None:
            return False
        if self._kalkis_kilidi_acildi:
            return False
        yukseklik = ref_z - self._cached_pos_z
        if yukseklik >= self._kalkis_kilit_irtifa_m:
            self._kalkis_kilidi_acildi = True
            self._takeoff_anchor_x = self._cached_pos_x
            self._takeoff_anchor_y = self._cached_pos_y
            self.get_logger().info(
                f'yatay kilit AÇILDI ({yukseklik:.1f} m) — çapa '
                f'({self._takeoff_anchor_x:.2f}, {self._takeoff_anchor_y:.2f})'
            )
            return False
        return True

    def _on_swarm_origin(self, msg: SwarmOrigin) -> None:
        """Ortak NED origin'i PX4'e gönderir.

        Lider drone bu mesajı yayınlar; diğer drone'lar (ve lider kendi
        kendine) SET_GPS_GLOBAL_ORIGIN komutuyla PX4'ü senkronize eder.

        ORIGIN_SYNCED ARTIK BURADA TRUE YAPILMIYOR — 1 Ağustos'ta bu satır
        yalana dönüştü. Eski hâli komutu gönderip HEMEN 'uygulandı' diyordu;
        PX4 kabul etti mi diye bakmıyordu. Doğrulamayı _origin_dogrula
        yapıyor, bayrağı da o koyuyor.
        """
        if not msg.valid or msg.gps_fix_type < 3:
            return
        self._origin_lat = msg.origin_lat_deg
        self._origin_lon = msg.origin_lon_deg
        self._origin_alt = msg.origin_alt_amsl_m
        self._status.origin_sequence = msg.sequence
        if msg.sequence == self._applied_origin_seq:
            return
        self._applied_origin_seq = msg.sequence
        self._origin_gonder('yeni sequence')

    def _origin_gonder(self, sebep: str) -> None:
        """SET_GPS_GLOBAL_ORIGIN gönderir (hız sınırlı, YALNIZ YERDE).

        ARMLIYKEN GÖNDERİLMEZ. Origin'i havada değiştirmek PX4'ün yerel
        çerçevesini KAYDIRIR: uçağın konumu bir anda sıçrar, kontrolcü o
        sıçramayı gerçek bir hata sanıp düzeltmeye çalışır. Yani tam olarak
        önlemeye çalıştığımız şeyin havada olanı. Doğrulama uçarken de koşar
        ve bayrağı düşürür — ama düzeltme yere inince yapılır.
        """
        if self._origin_lat is None:
            return
        if self._status.armed:
            return
        simdi = self.get_clock().now().nanoseconds * 1e-9
        if simdi - self._origin_son_gonderim < _ORIGIN_TEKRAR_ARALIK_S:
            return
        self._origin_son_gonderim = simdi
        self._cmd_sender.set_gps_global_origin(
            self._origin_lat, self._origin_lon, self._origin_alt)
        self.get_logger().info(
            f'GPS origin GONDERILDI ({sebep}): lat={self._origin_lat:.6f}, '
            f'lon={self._origin_lon:.6f}, alt={self._origin_alt:.1f}m '
            f'(seq={self._applied_origin_seq}) — dogrulama bekleniyor')

    def _origin_dogrula(self) -> None:
        """PX4'ün yerel çerçevesi ORTAK ORIGIN'e oturmuş mu, ÖLÇEREK bakar.

        NEDEN VAR — 1 Ağustos 22:18, ylp01 kalkıştan 1.4 sn sonra hedeften
        UZAKLAŞMAYA başladı ve ~85 m öteye, 21 m irtifaya kadar tam yetkiyle
        uçtu. Sebep ölçüldü: YKİ'nin bildirdiği konum GPS'ten ORTAK origin'e
        göre hesaplanıyor, PX4'ün setpoint'i yorumladığı çerçeve ise KENDİ
        EKF origin'ine göre. İkisi 12.1 m ayrıydı (pusula 20.7°) ve uçağın
        kaçtığı yön tam olarak o yöndü:
          YKİ  : NED (+12.87, +4.05)  irtifa -0.70
          PX4  : NED ( +1.59, -0.22)  irtifa -3.52
        Komut edilen her nokta 12 m yanlış yerdeydi; uçak oraya gidince YKİ
        konumu büyüyor, setpoint yeniden hesaplanıyor ve YİNE 12 m ileriyi
        gösteriyordu. Hata hiç kapanmadı.

        Origin BİR KEZ gönderiliyordu (sequence'e göre) ama PX4 uçuş
        kontrolcüsü her yeniden başlayışta (pil değişimi!) origin'i UNUTUR ve
        GPS fix'i gelince kendi durduğu yerde yenisini kurar. O gece FCU,
        origin gönderildikten sonra en az üç kez yeniden el sıkıştı.

        Ölçüm basit: GPS lat/lon'un ortak origin'e göre olması gereken NED'i
        ile PX4'ün bildirdiği yerel NED'i karşılaştır. Ayrılık varsa origin
        oturmamıştır — origin_synced FALSE olur ve komut yeniden gönderilir.
        """
        if self._origin_lat is None:
            return
        if self._status.gps_fix_type < 3 or not self._status.xy_valid:
            return
        lat, lon = self._status.lat_deg, self._status.lon_deg
        if abs(lat) < 0.001:
            return
        bek_x = (lat - self._origin_lat) * _M_PER_DEG_LAT
        bek_y = ((lon - self._origin_lon) * _M_PER_DEG_LAT
                 * math.cos(math.radians(lat)))
        fark = math.hypot(bek_x - self._status.pos_x, bek_y - self._status.pos_y)

        # DIKEY DE DENETLENIR. Yatay 12.1 m ayrilirken dikey de 1.54 m
        # ayriydi ve ayni sekilde komut edilen irtifayi kaydiriyordu:
        # "irtifa 5 m" komutu ucagi zeminden 3.5 m'ye cikariyordu. Fark
        # kalkis sonrasi olculen irtifa_ofset ile soguruluyordu — yani
        # semptom gizleniyor, sebep duruyordu.
        #
        # GPS'in AMSL'i kullanilabilir oldugu OLCULDU (1216.96 m; elipsoit
        # yukseklik olsaydi bu enlemde ~1250 civari cikardi).
        bek_z_up = self._status.alt_amsl_m - self._origin_alt
        fark_z = abs(bek_z_up - (-self._status.pos_z))

        if fark <= _ORIGIN_TOLERANS_M and fark_z <= _ORIGIN_TOLERANS_Z_M:
            if not self._status.origin_synced:
                self.get_logger().info(
                    f'origin DOGRULANDI (yatay {fark:.2f} m, dikey '
                    f'{fark_z:.2f} m) — cerceveler ortusuyor')
            self._status.origin_synced = True
            self._origin_uyari_verildi = False
            return
        self._status.origin_synced = False
        if not self._origin_uyari_verildi:
            self._origin_uyari_verildi = True
            self.get_logger().error(
                f'ORIGIN OTURMAMIS: yatay sapma {fark:.2f} m (tolerans '
                f'{_ORIGIN_TOLERANS_M:.1f}), dikey sapma {fark_z:.2f} m '
                f'(tolerans {_ORIGIN_TOLERANS_Z_M:.1f}). Beklenen NED '
                f'({bek_x:+.2f},{bek_y:+.2f}) irtifa {bek_z_up:+.2f}, PX4 '
                f'({self._status.pos_x:+.2f},{self._status.pos_y:+.2f}) '
                f'irtifa {-self._status.pos_z:+.2f}. '
                f'UCURMA — setpoint bu kadar yanlis yere gider.')
        self._origin_gonder(
            f'dogrulama basarisiz (yatay {fark:.1f} m, dikey {fark_z:.1f} m)')

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
            # PX4 ARMLIYKEN YERDE OFFBOARD'A GEÇMİYOR — 30 Temmuz'da tek
            # değişkenli deneyle ölçüldü (disarm iken tek talep tutuyor,
            # kumanda açık da olsa kapalı da; armlıyken tutmuyor). FSM sırası
            # ARMING->'arm', ARMED->'offboard' olduğu için önce armlanıyor,
            # sonra mod isteniyordu ve PX4 reddediyordu: dron ARMED'da
            # sonsuza kadar takılıp hiç kalkamıyordu (offboard=False 9.3 sn).
            # Bu yüzden sırayı tersine çeviriyoruz: önce OFFBOARD, aktif
            # olunca ARM (bkz. _offboard_dongusu).
            if self._status.armed:
                # Zaten armlı — uçuyor olabilir. Mod değiştirmek uçuş
                # kontrolünü habersiz devralmak olurdu; hiçbir şey yapma.
                self.get_logger().info(
                    'arm komutu geldi ama dron zaten armlı — yok sayıldı'
                )
                return
            self._offboard_streaming = True
            self._cmd_sender.set_offboard_mode()
            self._arm_bekliyor = True
            self._arm_istek_t = self.get_clock().now().nanoseconds * 1e-9
            # YATAY KILIDIN REFERANSI BURADA KURULUR. Takeoff komutu bundan
            # saniyeler sonra gelebiliyor (kosucu once digerini armliyor) ve o
            # boslukta ucak yerde, armli, konum tutuyor durumda kaliyordu.
            # Bkz. _kalkis_kilidi_aktif.
            self._arm_z = self._cached_pos_z
            self._kalkis_kilidi_acildi = False
            self.get_logger().info(
                f'OFFBOARD isteniyor; aktifleşince ARM gönderilecek '
                f'(yatay kilit kuruldu, arm z={self._arm_z:.2f})'
            )
        elif cmd == 'disarm':
            self._offboard_streaming = False
            self._arm_bekliyor = False
            # Bayat kalkış hedefini TEMİZLE. precision_landing görev sonunda
            # 'land' DEĞİL doğrudan 'disarm' gönderiyor
            # (precision_landing_node.py:214), yani hedef temizlenmeden
            # kalıyordu. Bir sonraki 'offboard'da taze formasyon setpoint'i
            # henüz yokken aşağıdaki "kalkış/irtifa-hold" dalı devreye girip
            # dronu ÖNCEKİ görevin irtifasına ve ÖNCEKİ çapa konumuna
            # sürüyordu — FSM daha TAKEOFF demeden, komut verilmemiş kalkış.
            self._target_altitude_ned = None
            self._takeoff_baslangic_z = None
            self._kalkis_kilidi_acildi = False
            self._takeoff_anchor_x = None
            self._takeoff_anchor_y = None
            self._arm_z = None
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
            # AYNI KALKIŞ TEKRAR GELİRSE ÇAPA YENİLENMEZ.
            #
            # Guided komutlar mesh'e 4 KOPYA gönderiliyor (OTA ACK yok,
            # esp32_bridge_node._guided_gonder) ve YKİ görev koşucusu
            # tırmanış başlamazsa komutu TEKRARLIYOR. Yani tek bir kalkış
            # isteği buraya 4-8 kez gelir. Her gelişte çapayı yeniden
            # dondurmak kalkışı bozuyordu:
            #   * hedef irtifa o anki z'ye göre yeniden hesaplanır — uçak
            #     tırmanmışsa hedef yukarı kayar
            #   * yatay çapa o anki konuma taşınır — uçak sürüklenmişse
            #     tutulacak nokta sürüklenmenin peşinden gider
            # 1 Ağustos ylp00 logu: 8 kalkış çerçevesi, çapa (5.51,3.32)'den
            # (6.04,2.69)'a kaydı, yani uçak yerde kayarken tutması gereken
            # nokta da kaydı. Kalkış BİR KEZ çapalanır; hedefi değiştirmek
            # için önce land/disarm gelir (ikisi de çapayı temizler).
            if self._target_altitude_ned is not None:
                self.get_logger().debug(
                    f'takeoff tekrarı yok sayıldı (çapa zaten kurulu): {cmd}')
            else:
                # Hedef mevcut konuma göreli: origin dünya orijinine
                # senkronken yer z=0 değildir; mutlak -altitude vermek
                # alçalma komutuna dönüşür.
                self._target_altitude_ned = self._cached_pos_z - altitude
                # Yatay çapayı şimdi dondur — tırmanış boyunca sabit kalsın.
                self._takeoff_anchor_x = self._cached_pos_x
                self._takeoff_anchor_y = self._cached_pos_y
                # Yatay kilidin referansı: bu z'den itibaren yükseklik ölçülür.
                self._takeoff_baslangic_z = self._cached_pos_z
                self._kalkis_kilidi_acildi = False
                self.get_logger().info(
                    f'Offboard kalkış hedefi: {altitude:.1f}m '
                    f'(NED z={self._target_altitude_ned:.1f}) '
                    f'çapa=({self._takeoff_anchor_x:.2f}, '
                    f'{self._takeoff_anchor_y:.2f})'
                )
        elif cmd == 'land':
            self._offboard_streaming = False
            self._arm_bekliyor = False   # iniş geldi, bekleyen ARM iptal
            self._target_altitude_ned = None
            self._takeoff_baslangic_z = None
            self._kalkis_kilidi_acildi = False
            self._takeoff_anchor_x = None
            self._takeoff_anchor_y = None
            self._arm_z = None
            self._cmd_sender.land()
        elif cmd == 'rtl':
            self._offboard_streaming = False
            self._arm_bekliyor = False   # RTL geldi, bekleyen ARM iptal
            self._target_altitude_ned = None
            self._takeoff_baslangic_z = None
            self._kalkis_kilidi_acildi = False
            self._takeoff_anchor_x = None
            self._takeoff_anchor_y = None
            self._arm_z = None
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
