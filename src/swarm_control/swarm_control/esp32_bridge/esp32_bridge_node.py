r"""esp32_bridge.py — ESP32 mesh ↔ ROS2 köprüsü (ana node).

Gerçek donanımda network_proxy'nin yerini alır: komşu drone'lardan
ESP-NOW mesh üzerinden gelip ESP32'nin UART'a yazdığı paketleri çözer,
ROS2 topic'lerine yayınlar. Ters yönde, bu drone'dan çıkması gereken
mesajları (origin, kendi pozisyonu) ESP32'ye UART üzerinden gönderir.

Şartname en az 3 İHA istiyor; kod 1-254 ID aralığında çalışır.

UART protokolü (firmware ile AYNI):
    [tip][iha_id][payload 16B][crc16 2B] -> COBS encode -> 0x00 ayraç

İŞLEYİŞ:
1. Arka plan thread'i seri porttan okur, 0x00'da çerçeve keser,
   COBS çözer, CRC doğrular, tipe göre parse eder.
2. Komşu TIP_POSE / TIP_DURUM -> AgentStatus cache güncellenir ve
   /swarm/public/drone{id}/status'a yayınlanır.
3. TIP_ORIGIN -> /swarm/public/origin'e SwarmOrigin yayınlanır.
4. Abonelikler (RPi -> ESP32): /swarm/internal/origin ve kendi
   telemetri topic'i UART'a yazılır.

KULLANIM:
    ros2 run swarm_control esp32_bridge --ros-args \\
        -p agent_id:=1 -p serial_port:=/dev/ttyUSB0
"""

import math
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)
import serial

from std_msgs.msg import String, UInt8MultiArray
from swarm_interfaces.msg import (
    AgentSetpoint,
    AgentStatus,
    ElectionResult,
    FormationCommand,
    GuidedCommand,
    LeaderHeartbeat,
    QRCoordinates,
    QRMissionData,
    SwarmControlCommand,
    SwarmOrigin,
    SystemEvent,
)

from . import packet_parser as pp
from .cobs import cobs_decode, cobs_encode
from .crc16 import crc16
from .formasyon_montaj import FormasyonMontaj, parcala
from swarm_core.formation_control.formation_geometry import FORMATION_CUSTOM

# QR ayrıştırma hatası metnini mesh'te taşınan 1 baytlık koda çevirir.
# qr_detector.py altı ayrı hata üretiyor; metin taşımak yerine kod taşıyoruz
# (KARAR 8). Eşleşme bulunamazsa QR_HATA_KOMUT'a düşer — bilinmeyen bir hata
# da olsa YKİ en azından "ayrıştırma patladı" bilgisini alır.
_QR_HATA_ESLESME = (
    ('JSON', pp.QR_HATA_JSON),
    ('sema', pp.QR_HATA_SEMA),
    ('şema', pp.QR_HATA_SEMA),
    ('slot', pp.QR_HATA_SLOT),
    ('tablo', pp.QR_HATA_TABLO),
    ('Paket', pp.QR_HATA_PAKET),
    ('paket', pp.QR_HATA_PAKET),
)


def _qr_hata_kodu(mesaj: str) -> int:
    """qr_detector hata metnini QR_HATA_* koduna eşler."""
    for parca, kod in _QR_HATA_ESLESME:
        if parca in mesaj:
            return kod
    return pp.QR_HATA_KOMUT


# Mesh telemetrisi için BEST_EFFORT — kayıp paket tolere edilir
_MESH_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)

# Origin için RELIABLE + TRANSIENT_LOCAL — geç katılan da son değeri alır
_ORIGIN_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=1,
)

# LeaderHeartbeat: RELIABLE + VOLATILE, depth=5
_HEARTBEAT_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=5,
)

# ElectionResult: RELIABLE + TRANSIENT_LOCAL, depth=10 (geç gelen alır)
_ELECTION_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)

# SystemEvent: RELIABLE, event tabanlı
_EVENT_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)

# RTCM (YKİ okuyucusu -> baz bridge -> mesh): RELIABLE + VOLATILE.
#
# Spec §1 "ağ seviyesinde retransmisyon YOK, taze veri > eksiksiz veri" kuralı
# HAVA LİNKİ içindir. Burası laptop-içi loopback DDS hop'u; orada kaybetmenin
# hiçbir karşılığı yok — tazelik kazandırmaz, sadece RTCM mesajını öldürür.
# O yüzden yerel hop RELIABLE. Derinlik 10, ~5 msg/s trafikte yayıncıyı
# bloke etme riski yok.
#
# VOLATILE (TRANSIENT_LOCAL değil): geç katılan bir aboneye BAYAT RTCM
# göndermek zararlıdır. Düzeltme verisinin yaşı > 2 sn ise zaten işe yaramaz.
_RTCM_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)

_FRAME_DELIM = 0x00

# --- Guided komut tekrar kuyrugu (bkz. Esp32BridgeNode._guided_gonder) -------
# Broadcast'te OTA ACK yok, cerceve havada kaybolabilir; her komut birkac kez
# gonderilir. Araliklar base ESP'nin TIP BASINA uyguladigi kapilarin USTUNDE
# secildi, cunku iki drone ayni kapiyi paylasiyor:
#     TIP_KOMUT -> RX BASE/src/main.cpp:186  JOYSTICK_MIN_ARALIK_MS = 200
#     TIP_GOTO  -> RX BASE/src/main.cpp:187  MESH_GONDERIM_MIN_MS   =  50
# Bu degerleri firmware'deki sinirin ALTINA cekme: cerceve sessizce duser,
# hicbir hata donmez ve teshis "drone komutu almadi"ya kadar uzar.
_GUIDED_TEKRAR = 4                  # cerceve basina kopya sayisi
_GUIDED_TEKRAR_ARALIK_S = 0.25      # ayni komutun iki kopyasi arasi en az
_GUIDED_TICK_S = 0.05               # kuyruk bosaltma zamanlayicisi
_GUIDED_KUYRUK_MAKS = 64            # tasma sigortasi (normalde <10)
_GUIDED_TIP_ARALIK_S = {
    pp.TIP_KOMUT: 0.30,             # firmware kapisi 0.200
    pp.TIP_GOTO: 0.10,              # firmware kapisi 0.050
}
_GUIDED_TIP_ARALIK_S_VARSAYILAN = 0.30

# Firmware durum kodunu AgentStatus.state'e eşler. Ayrılmış/inmiş
# komşular (7/8/13/14) çarpışma önlemeden çıkarılır. Kodlar
# mesh_config.h ile birebir aynı olmalı.
_DURUM_BILINMIYOR = 0
_DURUM_BOSTA = 1         # yerde, arm değil
_DURUM_KALKIS = 2        # kalkış
_DURUM_SURUDE = 3        # sürüde uçuş
_DURUM_GOREV = 4         # formasyon/manevra/irtifa görevi
_DURUM_AYRILDI = 5       # sürüden ayrıldı
_DURUM_HASSAS_INIS = 6   # renkli alana iniyor
_DURUM_KATILMA = 7       # yeniden katılıyor
_DURUM_BEKLIYOR = 8      # yerde disarm, bekleme süresi
_DURUM_RTL = 9           # RTL failsafe / home dönüş
_DURUM_INIS = 10         # home iniş
_DURUM_INDI = 11         # disarm, görev tamam
_DURUM_FAILSAFE = 12     # failsafe (kumanda kaybı)
_DURUM_STANDBY = 13      # yedek ajan, katılmaya hazır
_DURUM_STATE_MAP = {
    _DURUM_BILINMIYOR:  AgentStatus.STATE_UNKNOWN,            # 0
    _DURUM_BOSTA:       AgentStatus.STATE_IDLE,               # 1
    _DURUM_KALKIS:      AgentStatus.STATE_TAKEOFF,            # 4
    _DURUM_SURUDE:      AgentStatus.STATE_IN_SWARM,           # 5
    _DURUM_GOREV:       AgentStatus.STATE_EXECUTING_TASK,     # 6
    _DURUM_AYRILDI:     AgentStatus.STATE_DETACHED,           # 7
    _DURUM_HASSAS_INIS: AgentStatus.STATE_PRECISION_LANDING,  # 8
    _DURUM_KATILMA:     AgentStatus.STATE_REJOINING,          # 10
    _DURUM_BEKLIYOR:    AgentStatus.STATE_WAITING_REJOIN,     # 9
    _DURUM_RTL:         AgentStatus.STATE_RETURN_HOME,        # 11
    _DURUM_INIS:        AgentStatus.STATE_LANDING,            # 12
    _DURUM_INDI:        AgentStatus.STATE_LANDED,             # 13
    _DURUM_FAILSAFE:    AgentStatus.STATE_FAILSAFE,           # 14
    _DURUM_STANDBY:     AgentStatus.STATE_STANDBY,            # 15
}

# Ters yön: AgentStatus.state -> firmware durum kodu. ARMING ve ARMED
# firmware'de ayrı kod taşımaz, ikisi de KALKIS'a eşlenir.
_STATE_DURUM_MAP = {
    AgentStatus.STATE_UNKNOWN:           _DURUM_BILINMIYOR,
    AgentStatus.STATE_IDLE:              _DURUM_BOSTA,
    AgentStatus.STATE_ARMING:            _DURUM_KALKIS,
    AgentStatus.STATE_ARMED:             _DURUM_KALKIS,
    AgentStatus.STATE_TAKEOFF:           _DURUM_KALKIS,
    AgentStatus.STATE_IN_SWARM:          _DURUM_SURUDE,
    AgentStatus.STATE_EXECUTING_TASK:    _DURUM_GOREV,
    AgentStatus.STATE_DETACHED:          _DURUM_AYRILDI,
    AgentStatus.STATE_PRECISION_LANDING: _DURUM_HASSAS_INIS,
    AgentStatus.STATE_WAITING_REJOIN:    _DURUM_BEKLIYOR,
    AgentStatus.STATE_REJOINING:         _DURUM_KATILMA,
    AgentStatus.STATE_RETURN_HOME:       _DURUM_RTL,
    AgentStatus.STATE_LANDING:           _DURUM_INIS,
    AgentStatus.STATE_LANDED:            _DURUM_INDI,
    AgentStatus.STATE_FAILSAFE:          _DURUM_FAILSAFE,
    AgentStatus.STATE_STANDBY:           _DURUM_STANDBY,
}


def _kirp_int16(deger: float) -> int:
    """Float değeri int16 aralığına (-32768..32767) kırpıp tamsayı döner."""
    return max(-32768, min(32767, int(deger)))


class Esp32BridgeNode(Node):
    """ESP32 mesh ↔ ROS2 köprü node'u."""

    def __init__(self) -> None:
        super().__init__('esp32_bridge')

        self.declare_parameter('agent_id', 1)
        self.declare_parameter('serial_port', '/dev/ttyUSB0')
        self.declare_parameter('baud', 460800)
        # Boş bırakılırsa agent_id'den türetilir: /drone_{id}/rtcm/in
        #
        # Eski varsayılan '/rtcm/in' (mutlak, ad alanısız) idi ve px4_bridge
        # f'{ns}/rtcm/in' = '/drone_{id}/rtcm/in' dinliyordu — İKİSİ HİÇ
        # BAĞLANMIYORDU. baslat.sh de bu parametreyi geçmiyor, yani sahadaki
        # yapılandırmada RTCM esp32_bridge'den çıkıp px4_bridge'e hiç
        # ulaşmıyordu. RTCM daha önce hiç akmadığı için fark edilmemiş;
        # uçtan uca testte yakalandı (baz "185 mesaj gönderdim" derken
        # drone'da rtk sayacı 0 kalıyordu).
        #
        # Varsayılanı türetmek, parametreyi hatırlamak zorunda kalmamak için:
        # px4_bridge ad alanını agent_id'den ürettiği sürece ikisi kendiliğinden
        # eşleşir.
        self.declare_parameter('rtcm_out_topic', '')
        # Baz istasyonunda: YKİ'nin RTK okuyucusundan gelen RTCM3 mesajları.
        # Drone tarafında bu topic'e yayın yapan yok → abonelik boşta durur.
        self.declare_parameter('rtcm_in_topic', '/swarm/internal/rtcm')

        # --- Sürü koordinasyonu (30 Temmuz) --------------------------------
        # team_id: KARAR 7 — QR'ın takım filtresi mesh'te taşınmıyor (metin,
        # 16 bayta sığmaz). QR'ı okuyan drone yerelde filtreliyor, yani mesh'e
        # çıkan her QR zaten bizim takıma ait. Alıcı taraf `team_id` alanını
        # BURADAN doldurmak ZORUNDA: boş bırakılırsa mission_fsm_node:336
        # (`elif msg.team_id != ctx.team_id: return`) ve mission1_node:205
        # gelen HER QR'ı reddeder. Sessiz bir tuzak, o yüzden boşsa uyarıyoruz.
        # Varsayilan mission1_node:122 ve mission_fsm_node:89 ile AYNI
        # ('752825'). Ucu ayrisirsa mission_fsm gelen her QR'i reddeder
        # (msg.team_id != ctx.team_id) ve semptom 'QR gorevleri hic
        # islenmiyor' olur. baslat.sh ucune ayni degeri geciriyor.
        self.declare_parameter('team_id', '752825')
        # wing_alpha_deg: OKBASI/V formasyonunun kanat açısı. FormationCommand
        # bu alanı TAŞIMIYOR, o yüzden gönderen taraf parametreden okur ve
        # pakete koyar; alıcı paketten okur. Böylece bütün sürü LİDERİN
        # değerini kullanır. formation_node ve mission1_node'da da aynı isimli
        # parametre var (ikisinde varsayılan 45.0) ve eşitliği hiçbir şey
        # zorlamıyordu — biri farklı kalırsa slot geometrisi SESSİZCE ayrışır.
        self.declare_parameter('wing_alpha_deg', 45.0)

        self._agent_id = int(self.get_parameter('agent_id').value)
        self._takim_id = str(self.get_parameter('team_id').value)
        self._kanat_alfa_deg = float(
            self.get_parameter('wing_alpha_deg').value
        )
        port = str(self.get_parameter('serial_port').value)
        baud = int(self.get_parameter('baud').value)

        # agent_id: 1-254 (0 = broadcast/invalid, 255 = ESP-NOW broadcast).
        # Bu sınırın dışı sessiz hata üretir, erken patlayalım.
        if not 1 <= self._agent_id <= 254:
            raise ValueError(
                f'agent_id 1-254 arasında olmalı, verilen: {self._agent_id}'
            )
        # baud rate: ESP32 UART için yaygın değerler. 115200 default.
        if baud not in (9600, 19200, 38400, 57600, 115200, 230400, 460800):
            self.get_logger().warning(
                f'Olağandışı baud rate: {baud} (yaygın değil)'
            )

        # Komşu drone başına AgentStatus cache'i (POSE + DURUM birleşir)
        self._komsu_durum: dict[int, AgentStatus] = {}
        self._cache_lock = threading.Lock()

        # Komşu status yayıncıları drone_id'ye göre tembel oluşturulur
        self._status_pubs: dict[int, object] = {}

        # Mesh sağlık sayaçları (failsafe gözlemi için).
        # swarm_fsm, bridge bu sayaçları durdurursa mesh kopuk sanar ve
        # RTL/Land tetikleyebilir.
        self._alim_ok = 0          # COBS+CRC doğrulanmış paket sayısı
        self._crc_fail = 0         # CRC eşleşmemiş paket sayısı
        self._gonderim_ok = 0      # UART'a başarılı yazılan paket sayısı
        self._gonderim_drop = 0    # port kapalı/hata ile düşürülen
        self._rtk_alindi = 0       # alınan RTK/RTCM çerçevesi (liveness değil)
        self._bilinmeyen_tip = 0   # dispatch'te eşleşmeyen tip sayısı
        # --- Sürü koordinasyonu (30 Temmuz) --------------------------------
        # Çok parçalı formasyon montajı (başlık + devam + CUSTOM offsetleri).
        # 3 drone + adlandırılmış formasyonda tek paket, montaj anında biter.
        self._formasyon_montaj = FormasyonMontaj()
        self._formasyon_gonderilen = 0   # mesh'e yazılan formasyon turu (lider)
        self._formasyon_alinan = 0       # montajı tamamlanıp yayınlanan
        self._formasyon_lider_degil = 0  # lider kapısında düşürülen
        self._qr_gorev_gonderilen = 0
        self._qr_gorev_alinan = 0
        # Bilinen lider (KARAR 11 kapısı). 0 = henüz seçim görülmedi.
        # BİLEREK 0 başlıyor: kimse lider değilken formasyon yayınlamak, iki
        # dronun aynı anda yayınlaması riskini doğurur. Ama sessiz kalmasın
        # diye kapıda throttle'lı uyarı basılıyor.
        self._lider_id = 0
        # Baz tarafı RTCM sayaçları. "RTK neden fix vermiyor" sorusunda ilk
        # ayrım: RTCM baz ESP'ye hiç ulaştı mı? Bu iki sayaç olmadan YKİ
        # okuyucusunun sessizce durması ile havada kaybolması ayırt edilemez.
        self._rtcm_gonderilen = 0  # mesh'e yazılan RTCM3 mesajı
        self._rtcm_reddedilen = 0  # geçersiz bulunup atılan (boyut/preamble/uzunluk)
        # KOMUT için bridge-tarafı seq sayacı; firmware payload'a seq
        # eklenene kadar monoton değer üretir. mesh_config.h ile teyit
        # edilmesi gerekir.
        self._komut_rx_seq = 0
        # Header iha_id ile payload drone_id uyumsuzluk sayacı
        self._id_uyumsuz = 0
        # En son bilinen SwarmOrigin (GPS→NED dönüşümü için gerekli).
        # Lider /swarm/internal/origin'a veya mesh _isle_origin yoluyla
        # gelir. Bridge GPS'i NED'e çevirmezse komşu pos_x/y/z=0.0 kalır.
        self._son_origin: SwarmOrigin | None = None
        # NED dönüşüm için: 1 derece enlem ≈ 111.32 km. Saha 10m × 10m
        # için düz-dünya yaklaşımı yeterince doğru (<10 km'de hata
        # cm seviyesinde).
        self._METRE_PER_DERECE_LAT = 111_320.0
        self._son_alim_ts = 0.0    # son başarılı paket zamanı (monotonic)
        # Son N saniyede mesaj duyan komşu ID'leri
        self._komsu_son_goruldu: dict[int, float] = {}
        # POSE giden son zaman — rate limit için (Ö3)
        self._son_pose_gonderim_ts = 0.0
        # Rate-limit eşiği: saniyede 10 POSE = 100ms aralık
        self._pose_periyot_s = 0.1
        # DURUM giden son zaman — 1Hz tavan (state nadiren değişir)
        self._son_durum_gonderim_ts = 0.0
        self._durum_periyot_s = 1.0

        self._origin_pub = self.create_publisher(
            SwarmOrigin, '/swarm/public/origin', _ORIGIN_QOS
        )
        # --- Sürü koordinasyonu yayıncıları (30 Temmuz) ---------------------
        # formation/target: mesh'ten gelen (ya da liderde loopback ile kendi
        # ürettiğimiz) formasyon hedefi. formation_node / collision_avoidance /
        # maneuver_executor üçü de bu topic'i dinliyor.
        self._formation_pub = self.create_publisher(
            FormationCommand, '/swarm/public/formation/target', _MESH_QOS
        )
        # perception/qr_data: QR'ı okuyan dronun çözdüğü görev. mission_fsm,
        # mission1 ve (YKİ'de) ros_bridge dinliyor.
        self._qr_data_pub = self.create_publisher(
            QRMissionData, '/swarm/public/perception/qr_data', _MESH_QOS
        )
        self._control_pub = self.create_publisher(
            SwarmControlCommand,
            '/swarm/public/control/command',
            _MESH_QOS,
        )
        self._leader_hb_pub = self.create_publisher(
            LeaderHeartbeat,
            '/swarm/public/leader/heartbeat',
            _HEARTBEAT_QOS,
        )
        self._election_pub = self.create_publisher(
            ElectionResult,
            '/swarm/public/election/result',
            _ELECTION_QOS,
        )
        # Event yayıncıları iki ayrı topic'e (kontrat 3.1 satır 119):
        #  - _event_pub_internal: BU drone'un kendi ürettiği event'ler
        #    (mesh diag, link lost). Publisher kuralı /internal/'a yazar.
        #  - _event_pub_public: mesh'ten relay edilen komşu event'leri.
        #    Bridge proxy rolünde, başkasının event'ini /public/'a düşürür.
        self._event_pub_internal = self.create_publisher(
            SystemEvent,
            '/swarm/internal/events/system',
            _EVENT_QOS,
        )
        self._event_pub_public = self.create_publisher(
            SystemEvent,
            '/swarm/public/events/system',
            _EVENT_QOS,
        )
        # RTK: mesh'ten gelen RTCM'i px4_interface'e ilet.
        # Boş parametre = agent_id'den türet; px4_bridge'in
        # f'/drone_{agent_id}/rtcm/in' aboneliğiyle eşleşsin (bkz. parametre
        # tanımındaki not).
        _rtcm_cikis = str(self.get_parameter('rtcm_out_topic').value).strip()
        if not _rtcm_cikis:
            _rtcm_cikis = f'/drone_{self._agent_id}/rtcm/in'
        self.get_logger().info(f'RTCM çıkış topic: {_rtcm_cikis}')
        self._rtcm_pub = self.create_publisher(
            UInt8MultiArray,
            _rtcm_cikis,
            10,
        )
        # YKİ'den gelen QR tablosu; son değeri saklarız (latched).
        self._qr_coords_pub = self.create_publisher(
            QRCoordinates, '/swarm/public/mission/qr_coords', _ORIGIN_QOS
        )
        self._qr_koord_toplayici: dict[int, tuple] = {}
        self._qr_koord_toplam = 0

        # === Guided (YKİ tekil komut) ===
        # Drone tarafı: mesh'ten gelen TIP_GOTO / guided TIP_KOMUT'u px4_bridge'in
        # anladığı arayüze çevirir — String komut + AgentSetpoint. Base tarafında
        # bu publisher'lar boşta kalır (guided mesh komutu drone'a iner, base'e değil).
        self._guided_cmd_pub = self.create_publisher(
            String, f'/swarm/agent/drone{self._agent_id}/commands', 10
        )
        self._guided_sp_pub = self.create_publisher(
            AgentSetpoint, f'/drone_{self._agent_id}/control/setpoint', 10
        )
        # Aktif guided hedef; 10 Hz LOKAL tekrar yayınlanır ki px4_bridge OFFBOARD
        # akışı ve FSM offboard-canlılığı bayatlamasın (mesh'e ÇIKMAZ).
        self._guided_hedef: AgentSetpoint | None = None
        self._guided_sp_timer = self.create_timer(0.1, self._guided_hedef_tekrar)
        # Guided komutu güvenilir teslim için birkaç kez aralıklı gönderilir
        # (broadcast'te OTA ACK yok). TEK kuyruk + TEK zamanlayıcı: komut
        # başına ayrı timer, iki drone'un tekrar dizilerini base ESP'nin
        # tip-başına hız limitinde çakıştırıyordu (bkz. _guided_gonder).
        self._guided_kuyruk: list = []
        self._guided_son_gonderim: dict = {}
        self._guided_kuyruk_timer = self.create_timer(
            _GUIDED_TICK_S, self._guided_kuyruk_bosalt)

        # Seri port ayarlarını sakla — kopma sonrası reconnect için
        self._port = port
        self._baud = baud
        self._ser_lock = threading.Lock()  # write/reconnect yarış engeli

        # Seri portu aç (ilk açılış başarısızsa fail-fast yapma; reconnect
        # thread'i sahaya gidip ESP32 sonra takılırsa da yakalar).
        self._ser: serial.Serial | None = None
        self._seri_ac()

        # RPi -> ESP32: kendi otoritatif durumumuzu mesh'e yaymak için.
        # Kontrat 3.1 satır 109: agent_fsm /swarm/internal/drone{id}/status
        # yayınlar (state, armed, battery, GPS, sensör sağlığı dahil).
        # LOKAL /swarm/agent/.../telemetry ham PX4 verisidir; mesh için
        # kullanmamalıyız — state alanı oradan UNKNOWN gelir.
        self.create_subscription(
            AgentStatus,
            f'/swarm/internal/drone{self._agent_id}/status',
            self._on_own_status,
            _MESH_QOS,
        )

        # RPi -> ESP32: lider origin yayınını mesh'e iletmek için
        self.create_subscription(
            SwarmOrigin,
            '/swarm/internal/origin',
            self._on_origin_out,
            _ORIGIN_QOS,
        )

        # RPi -> ESP32: joystick komutu (Görev 2) mesh'e iletilecek
        self.create_subscription(
            SwarmControlCommand,
            '/swarm/internal/control/command',
            self._on_control_out,
            _MESH_QOS,
        )

        # YKİ -> drone: guided tekil komut (arm/takeoff/goto/rtl/land).
        # Base istasyonunda backend yayınlar; bu handler mesh'e iletir
        # (TIP_KOMUT[guided] veya TIP_GOTO). Drone tarafında yayıncı yok → boşta.
        self.create_subscription(
            GuidedCommand,
            '/swarm/internal/guided/command',
            self._on_guided_out,
            _MESH_QOS,
        )

        # RPi -> ESP32: lider kalp atışı (yalnızca aktif lider yayınlar)
        self.create_subscription(
            LeaderHeartbeat,
            '/swarm/internal/leader/heartbeat',
            self._on_leader_hb_out,
            _HEARTBEAT_QOS,
        )

        # RPi -> ESP32: lider seçim sonucu (yeni lider yayınlar)
        self.create_subscription(
            ElectionResult,
            '/swarm/internal/election/result',
            self._on_election_out,
            _ELECTION_QOS,
        )

        # RPi -> ESP32: formasyon hedefi (YALNIZ LİDER gönderir, KARAR 11).
        #
        # path_planner HER dronda koşuyor (sıcak yedek: lider düşünce yeni
        # lider gecikmeden yayına geçer), o yüzden bu abonelik her dronda veri
        # alır. "Şu an lider miyim" kapısı `_on_formation_out` içinde —
        # firmware'e lider bilgisi taşımak lider değişiminde iki tarafı
        # senkron tutmayı gerektirirdi.
        self.create_subscription(
            FormationCommand,
            '/swarm/internal/formation/target',
            self._on_formation_out,
            _MESH_QOS,
        )

        # RPi -> ESP32: çözülmüş QR görevi. Lider kapısı YOK — QR'ı hangi
        # drone okuduysa o yayınlar (şartname: "İHA'lardan en az biri QR
        # kodunu görsel algılama yöntemi ile tespit etmeli").
        self.create_subscription(
            QRMissionData,
            '/swarm/internal/perception/qr_data',
            self._on_qr_data_out,
            _MESH_QOS,
        )

        # YKİ RTK okuyucusu -> ESP32: RTCM3 düzeltme verisi.
        #
        # NEDEN ROS ÜZERİNDEN, doğrudan seri porta değil:
        # Bir seri portu tek süreç açabilir ve bu portun sahibi zaten bu node.
        # yki_rtcm_reader doğrudan yazmaya kalksaydı "Device or resource busy"
        # alırdı (sahada QGC'nin autoconnect'iyle birebir bu yaşandı). RTCM'i
        # topic'ten alarak port sahipliği tek elde kalıyor ve çakışma yapısal
        # olarak imkânsızlaşıyor.
        #
        # Okuyucunun ayrı süreç kalması bilinçli: çökerse telemetri ve komut
        # yolu etkilenmez. Tek süreçte birleştirmek RTCM hatasını tüm YKİ'yi
        # düşüren bir hataya dönüştürürdü.
        self.create_subscription(
            UInt8MultiArray,
            str(self.get_parameter('rtcm_in_topic').value),
            self._on_rtcm_out,
            _RTCM_QOS,
        )

        # Seri okuma thread'i
        self._calisiyor = True
        self._okuma_thread = threading.Thread(
            target=self._seri_oku_dongusu, daemon=True
        )
        self._okuma_thread.start()

        # Mesh sağlık raporu: her 1 sn'de bir SystemEvent ile yayın.
        # Failsafe: mesh kopuksa swarm_fsm görür.
        self._diag_timer = self.create_timer(1.0, self._diag_yayinla)

        self.get_logger().info(
            f'Esp32BridgeNode başlatıldı: agent_id={self._agent_id}'
        )

    # =================================================================
    # MESH SAĞLIK RAPORLAMA
    # =================================================================
    def _diag_yayinla(self) -> None:
        """Her saniye mesh diagnostik sayaçlarını SystemEvent yayar.

        GPS/mesh güvenilir olmayabilir, failsafe kritik.
        swarm_fsm bu mesajı dinler ve son alım zamanına bakarak mesh
        kopukluğunu (>= 2 sn yok ise) algılayabilir.
        """
        now = time.monotonic()
        # Son 5 sn'de mesaj duydugumuz komsu sayisi.
        # _cache_lock + snapshot: seri okuma thread'i ayni dict'e yazarken
        # dogrudan iterasyon "dict changed size" cokmesine yol acar (race).
        # Kilidi sadece kopya alirken tut, sayma disarida yapilir.
        with self._cache_lock:
            komsu_ts = list(self._komsu_son_goruldu.values())
        aktif_komsu = sum(1 for ts in komsu_ts if now - ts < 5.0)
        son_alim_yas = (
            now - self._son_alim_ts if self._son_alim_ts > 0 else -1.0
        )
        link_ok = (
            self._ser is not None and self._ser.is_open
            and son_alim_yas >= 0 and son_alim_yas < 2.0
        )

        msg = SystemEvent()
        msg.stamp = self.get_clock().now().to_msg()
        msg.event_type = SystemEvent.EVENT_UNKNOWN
        msg.severity = (
            SystemEvent.SEVERITY_INFO if link_ok
            else SystemEvent.SEVERITY_WARNING
        )
        msg.source_agent_id = self._agent_id
        msg.source_module = 'esp32_bridge'
        msg.value = float(aktif_komsu)
        msg.has_position = False
        msg.message = (
            f'mesh_diag link_ok={int(link_ok)} '
            f'komsu={aktif_komsu} alim_ok={self._alim_ok} '
            f'crc_fail={self._crc_fail} '
            f'gonderim_ok={self._gonderim_ok} '
            f'gonderim_drop={self._gonderim_drop} '
            f'id_uyumsuz={self._id_uyumsuz} '
            f'rtk={self._rtk_alindi} bilinmeyen={self._bilinmeyen_tip} '
            f'rtcm_tx={self._rtcm_gonderilen} '
            f'rtcm_red={self._rtcm_reddedilen} '
            # Sürü koordinasyonu sayaçları (30 Temmuz). "Formasyon neden
            # gelmiyor" sorusunda ilk ayrım burada yapılabilsin:
            #   form_tx=0 ise lider yayınlamıyor (lider kapısı / path_planner)
            #   form_lider_degil>0 ise bu drone lider değil, normal
            #   form_rx=0 ama form_tx>0 ise mesh/whitelist sorunu
            #   form_yarim>0 ise çok parçalı montaj tamamlanmıyor
            f'lider={self._lider_id} '
            f'form_tx={self._formasyon_gonderilen} '
            f'form_rx={self._formasyon_alinan} '
            f'form_lider_degil={self._formasyon_lider_degil} '
            f'form_yarim={self._formasyon_montaj.zaman_asimi_sayisi} '
            f'form_sahipsiz={self._formasyon_montaj.sahipsiz_parca_sayisi} '
            f'qr_tx={self._qr_gorev_gonderilen} '
            f'qr_rx={self._qr_gorev_alinan} '
            f'son_alim_yas_s={son_alim_yas:.2f}'
        )
        # Mesh diag: bu drone'un kendi gözleminden çıkıyor → /internal/
        self._event_pub_internal.publish(msg)

    # =================================================================
    # SERİ PORT YÖNETİMİ
    # =================================================================
    def _seri_ac(self) -> bool:
        """Seri portu açar. Başarılı ise True, başarısız ise False.

        Saha senaryosu: USB gevşedi, ESP32 reset attı, kablo değişti.
        Hata fırlatmaz; reconnect döngüsü tekrar dener.
        """
        with self._ser_lock:
            if self._ser is not None and self._ser.is_open:
                return True
            try:
                self._ser = serial.Serial(
                    self._port, self._baud, timeout=0.1
                )
                self.get_logger().info(
                    f'Seri port açıldı: {self._port} @ {self._baud}'
                )
                self._mesh_olay_yayinla(
                    SystemEvent.SEVERITY_INFO,
                    f'mesh link restored ({self._port})',
                )
                return True
            except serial.SerialException as exc:
                self._ser = None
                self.get_logger().error(
                    f'Seri port açılamadı ({self._port}): {exc}'
                )
                return False

    def _mesh_olay_yayinla(self, severity: int, mesaj: str) -> None:
        """Mesh link durumu için SystemEvent yayınlar (operatör görür).

        EVENT_MESH_LINK_LOST/RESTORED henüz yok; EVENT_UNKNOWN + string
        kullanılıyor. SystemEvent.msg ile teyit edilmesi gerekir.
        """
        msg = SystemEvent()
        msg.stamp = self.get_clock().now().to_msg()
        msg.event_type = SystemEvent.EVENT_UNKNOWN
        msg.severity = severity
        msg.source_agent_id = self._agent_id
        msg.source_module = 'esp32_bridge'
        msg.message = mesaj
        msg.value = 0.0
        msg.has_position = False
        # Kendi event'imiz: /swarm/internal/events/system
        self._event_pub_internal.publish(msg)

    # =================================================================
    # SERİ OKUMA (arka plan thread)
    # =================================================================
    def _seri_oku_dongusu(self) -> None:
        """Seri porttan sürekli okur, 0x00'da çerçeve keser ve işler.

        Bağlantı koparsa thread ölmez; portu kapatır, 1 saniye bekler,
        yeniden açmayı dener. Saha güvenilirliği için kritik.
        """
        tampon = bytearray()
        while self._calisiyor:
            if self._ser is None or not self._ser.is_open:
                time.sleep(1.0)
                self._seri_ac()
                continue
            try:
                veri = self._ser.read(2048)
            except serial.SerialException as exc:
                self.get_logger().warning(
                    f'Seri okuma hatası, yeniden bağlanılacak: {exc}'
                )
                self._mesh_olay_yayinla(
                    SystemEvent.SEVERITY_WARNING,
                    f'mesh link lost (read): {exc}',
                )
                with self._ser_lock:
                    if self._ser is not None:
                        try:
                            self._ser.close()
                        except Exception:  # noqa: BLE001
                            pass
                    self._ser = None
                tampon.clear()
                continue

            for byte in veri:
                if byte == _FRAME_DELIM:
                    if tampon:
                        self._cerceve_isle(bytes(tampon))
                        tampon.clear()
                else:
                    tampon.append(byte)
                    if len(tampon) > 2048:  # taşma koruması (RTK ~1.6KB)
                        tampon.clear()

    def _cerceve_isle(self, ham: bytes) -> None:
        """Bir COBS çerçevesini çözer, doğrular ve tipe göre yayınlar.

        Args:
            ham (bytes): 0x00 ayracı hariç tek bir COBS çerçevesi.
        """
        decoded = cobs_decode(ham)
        cerceve = pp.cerceve_coz(decoded)
        if cerceve is None:
            # CRC hatası veya eksik veri — sayacı artır, sessizce at
            self._crc_fail += 1
            return
        self._alim_ok += 1
        # F3: mesh-liveness yalnızca bilinen peer + bilinen telemetri tipiyle
        # tazelenir; RTK (99) ve bilinmeyen tip tazelemez.
        if pp.liveness_tazeler(cerceve.iha_id, cerceve.tip):
            now = time.monotonic()
            self._son_alim_ts = now
            # _cache_lock: bu metod seri okuma thread'inden çağrılır; aynı
            # dict'i _diag_yayinla (ROS timer thread'i) itere eder.
            with self._cache_lock:
                self._komsu_son_goruldu[cerceve.iha_id] = now

        # RTK baz sentinel'inden (99) gelir, komşu telemetrisi değil.
        if cerceve.tip == pp.TIP_RTK:
            self._isle_rtk(cerceve.payload)
            return

        # Failsafe herkese yayın (iha_id=0), komşu filtresinden önce al.
        if cerceve.tip == pp.TIP_FAILSAFE:
            self._isle_failsafe(cerceve.payload)
            return

        # QR tablosu baz istasyonundan gelir, komşu drone'dan değil.
        if cerceve.tip == pp.TIP_QR_COORDS:
            self._isle_qr_coords(cerceve.payload)
            return

        # Defansif: kendi/broadcast paketini komşu olarak işleme.
        if cerceve.iha_id == 0 or cerceve.iha_id == self._agent_id:
            return

        if cerceve.tip == pp.TIP_POSE:
            self._isle_pose(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_DURUM:
            self._isle_durum(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_ORIGIN:
            self._isle_origin(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_KOMUT:
            self._isle_komut(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_GOTO:
            self._isle_goto(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_LEADER_HB:
            self._isle_leader_hb(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_ELECTION:
            self._isle_election(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_RENK:
            self._isle_renk(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_GOREV:
            self._isle_gorev(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_QR_DATA:
            self._isle_qr(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_SWARM_STATE:
            self._isle_swarm_state(cerceve.iha_id, cerceve.payload)
        # --- Sürü koordinasyonu (30 Temmuz) ---
        elif cerceve.tip == pp.TIP_FORMASYON:
            self._isle_formasyon(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_FORMASYON_DEVAM:
            self._isle_formasyon_devam(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_FORM_OFSET:
            self._isle_form_ofset(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_QR_GOREV:
            self._isle_qr_gorev(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_QR_HAM:
            self._isle_qr_ham(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip in (pp.TIP_HEARTBEAT, pp.TIP_VERSION):
            pass  # bilinen tip, downstream aksiyonu yok
        else:
            self._bilinmeyen_tip += 1
            self.get_logger().warning(
                f'bilinmeyen tip 0x{cerceve.tip:02X} iha_id={cerceve.iha_id}'
            )

    # =================================================================
    # MESH -> ROS2 İŞLEYİCİLERİ
    # =================================================================
    def _komsu_status_al(self, drone_id: int) -> AgentStatus:
        """Komşu için cache'teki AgentStatus'u döner, yoksa oluşturur."""
        status = self._komsu_durum.get(drone_id)
        if status is None:
            status = AgentStatus()
            status.agent_id = drone_id
            self._komsu_durum[drone_id] = status
        return status

    def _isle_pose(self, drone_id: int, payload: bytes) -> None:
        """TIP_POSE -> komşu AgentStatus konum alanlarını günceller.

        Mesh GPS olarak gelir; kinematic_fusion/swarm_fsm/collision
        NED bekler. Yerel SwarmOrigin'i kullanarak GPS→NED dönüşümü
        burada yapılır. Origin henüz yoksa NED alanları doldurulamaz;
        bu durumda xy/z_valid=false bırakılır → downstream kullanmaz.

        NED + validity + origin_synced burada set edilir.
        """
        pose = pp.pose_coz(payload)
        lat_deg = pose.lat / 1e7
        lon_deg = pose.lon / 1e7
        # NOT: alt_dm artik GORELI irtifa (m, yukari; dm) tasiyor — AMSL DEGIL.
        # Drone kendi EKF goreli irtifasini (-pos_z) POSE'a koyuyor; boylece
        # dikey irtifa origin'den BAGIMSIZ, pürüzsüz ve QGC ile ayni gelir.
        rel_alt_m = pose.alt_dm / 10.0
        vel_x_ned, vel_y_ned = pose.vx / 100.0, pose.vy / 100.0
        with self._cache_lock:
            status = self._komsu_status_al(drone_id)
            # GPS alanları (her durumda doldur)
            status.lat_deg = lat_deg
            status.lon_deg = lon_deg
            status.heading_deg = pose.heading / 10.0
            status.vel_x = vel_x_ned
            status.vel_y = vel_y_ned
            status.vel_z = pose.vz / 100.0
            # DİKEY: goreli irtifadan dogrudan — origin gerekmez, her zaman gecerli.
            status.pos_z = -rel_alt_m
            status.z_valid = True
            # YATAY (pos_x/pos_y): hala origin-tabanli GPS→NED (harita/formasyon).
            # ORIGIN_SYNCED BURADA ARTIK YAZILMIYOR — 1 Ağustos 22:18'de bu
            # satır ylp01'in kaçmasını görünmez kıldı.
            #
            # Eski hâli, BAZ İSTASYONU kendi GPS→NED çevirimini yapabildiği
            # için komşunun origin_synced'ine True yazıyordu. Oysa bayrağın
            # anlamı "O DRONE'UN PX4'ü ortak origin'i uyguladı mı" —
            # bambaşka bir şey. O gece YKİ True gösterirken PX4'ün çerçevesi
            # 12.1 m kayıktı ve komut edilen her nokta o kadar yanlış yere
            # düşüyordu. Bayrağa bakan bir kapı bile kurtarmazdı.
            #
            # Artık drone kendi ölçümünü (px4_bridge._origin_dogrula)
            # TIP_DURUM'un bayraklar2 bitiyle gönderiyor; _isle_durum onu
            # yazıyor. Burada yalnız YATAY NED'in kendi origin'imizle
            # hesaplanabilirliği (xy_valid) belirlenir — o ayrı bir şey.
            ned = self._gps_ned_cevir(lat_deg, lon_deg, 0.0)
            if ned is not None:
                status.pos_x = ned[0]
                status.pos_y = ned[1]
                status.xy_valid = True
                status.v_xy_valid = True
                if hasattr(status, 'v_z_valid'):
                    status.v_z_valid = True
            else:
                # Origin yok → yatay NED yok (dikey irtifa yine de gecerli)
                status.pos_x = 0.0
                status.pos_y = 0.0
                status.xy_valid = False
                status.v_xy_valid = False
                if hasattr(status, 'v_z_valid'):
                    status.v_z_valid = False
            self._yayinla_status(drone_id, status)

    def _gps_ned_cevir(
        self, lat_deg: float, lon_deg: float, alt_amsl_m: float,
    ) -> tuple[float, float, float] | None:
        """GPS koordinatını yerel NED frame'e çevirir.

        Düz-dünya yaklaşımı (flat-earth approximation): saha < 10 km
        olduğunda hatası cm seviyesinde. Yarışma sahası 10m × 10m
        için fazlasıyla yeterli.

        Returns:
            (pos_x, pos_y, pos_z) NED: North, East, Down (m), veya
            origin yoksa None.
        """
        origin = self._son_origin
        if origin is None:
            return None
        olat = float(origin.origin_lat_deg)
        olon = float(origin.origin_lon_deg)
        oalt = float(origin.origin_alt_amsl_m)
        # 1 derece enlem ≈ 111.32 km (sabit); 1 derece boylam ≈
        # 111.32 km × cos(enlem). Origin enlemi referans alınır.
        m_per_deg_lon = self._METRE_PER_DERECE_LAT * math.cos(
            math.radians(olat)
        )
        pos_x = (lat_deg - olat) * self._METRE_PER_DERECE_LAT
        pos_y = (lon_deg - olon) * m_per_deg_lon
        pos_z = oalt - alt_amsl_m  # NED: Down = aşağı pozitif
        return (pos_x, pos_y, pos_z)

    def _isle_durum(self, drone_id: int, payload: bytes) -> None:
        """TIP_DURUM -> komşu AgentStatus sağlık alanlarını günceller.

        Firmware'in 3 seviyeli durum'u (AKTIF/AYRILDI/INDI) AgentStatus
        FSM state'ine eşleştirilir. APF için kritik: AYRILDI/INDI olan
        komşulara avoidance hesabı yapılmamalı.
        """
        durum = pp.durum_coz(payload)
        # Header iha_id ile payload drone_id eşleşmeli; aksi halde
        # paket bozulmuş ya da firmware yanlış kaynak ID yazmış demektir.
        # Frame header (iha_id) gerçek kaynak kabul edilir; sayacı artır,
        # log basarak gözlemleyelim ama paketi düşürme (downstream'in
        # state'i hâlâ değerli olabilir).
        if durum.drone_id != drone_id:
            self._id_uyumsuz += 1
            self.get_logger().warning(
                f'DURUM ID uyumsuz: header={drone_id} '
                f'payload={durum.drone_id} — header esas alındı'
            )
        # Bilinmeyen durum kodları STATE_UNKNOWN (0) olarak bırakılır;
        # contract gereği UNKNOWN, "aktif gibi davran" anlamına gelir.
        state = _DURUM_STATE_MAP.get(durum.durum, AgentStatus.STATE_UNKNOWN)
        with self._cache_lock:
            status = self._komsu_status_al(drone_id)
            status.state = state
            status.armed = bool(durum.armed)
            status.gps_fix_type = durum.gps_fix_type
            status.battery_percent = float(durum.battery_pct)
            status.battery_voltage_v = durum.battery_volt
            status.estimator_ok = bool(durum.ekf_ok)
            status.imu_healthy = bool(durum.imu_ok)
            status.mag_healthy = bool(durum.mag_ok)
            status.baro_healthy = bool(durum.baro_ok)
            # REV C: mesh'ten yeni gelen alanlar.
            status.flight_mode = durum.ucus_modu
            status.gps_satellites = durum.gps_uydu
            status.gps_hdop = durum.gps_hdop
            status.kill_switch_active = durum.kill_switch_active
            status.rc_link_ok = durum.rc_link_ok
            status.ready_to_arm = durum.ready_to_arm
            # ORIGIN_SYNCED ARTIK DRONE'UN KENDI OLCUMUNDEN. Onceden
            # _isle_pose bunu UYDURUYORDU (bkz. oradaki not).
            status.origin_synced = durum.origin_synced

            # HEALTHY TURETILIYOR — mesh'te ayri bit YOK.
            #
            # 15 Agustos, ADIM 1 yer testinde olculdu: ylp00 ARMED iken
            # ylp02 onu mesh'ten `healthy: false` goruyordu, cunku bu alan
            # hic doldurulmuyordu ve AgentStatus varsayilani False.
            # election.is_eligible `healthy` sart kostugu icin HICBIR uzak
            # ajan lider adayi olamiyordu: her ucak yalniz kendini uygun
            # goruyor ve kendini secip SPLIT-BRAIN uretiyordu.
            #
            # Neden bit eklemedik: DURUM paketinin bayrak bayti 8/8 DOLU
            # (ARMED, EKF_OK, IMU_OK, MAG_OK, BARO_OK, MESH_LINK, KILL,
            # RC_LINK). Paketi buyutmek ESP32 firmware'ini de degistirmek
            # demekti. Gerek yok: AgentContext.healthy'nin girdilerinin
            # karsiligi paket icinde ZATEN var —
            #   ¬kill_switch  -> durum.kill_switch_active   (birebir)
            #   ¬failsafe     -> state != STATE_FAILSAFE    (birebir)
            #   konum tahmini -> durum.ekf_ok               (ayni kaynak)
            #   px4_link_ok   -> paketi almis olmamiz ima ediyor
            #
            # ⚠️ Bu bir TURETIM, gonderenin kendi `healthy` degeri degil.
            # Gonderen tarafta pil izleme acilirsa (KARAR-03) ve pil
            # dususu healthy'yi dusururse burasi onu GORMEZ. O gun ya
            # pakete bit eklenmeli ya da pil esigi burada da uygulanmali.
            status.healthy = (
                bool(durum.ekf_ok)
                and not durum.kill_switch_active
                and state != AgentStatus.STATE_FAILSAFE
            )
            # Paketi aldiysak gonderenin PX4 baglantisi calisiyordu.
            status.px4_link_ok = True
            # mesh_link_ok ve mesh_node_count henüz AgentStatus.msg'de yok;
            # eklenince hasattr otomatik doldurur, o zamana kadar
            # status_text taşır. AgentStatus.msg ile teyit edilmesi gerekir.
            if hasattr(status, 'mesh_link_ok'):
                status.mesh_link_ok = bool(durum.mesh_link_ok)
            if hasattr(status, 'mesh_node_count'):
                status.mesh_node_count = int(durum.mesh_komsu_sayisi)
            status.status_text = (
                f'mesh durum={durum.durum} rssi={durum.rssi} '
                f'link={durum.mesh_link_ok} komsu={durum.mesh_komsu_sayisi}'
                + (' KILL' if durum.kill_switch_active else '')
            )
            self._yayinla_status(drone_id, status)

    def _yayinla_status(self, drone_id: int, status: AgentStatus) -> None:
        """Komşu AgentStatus'u /swarm/public/drone{id}/status'a yayınlar.

        Not: _cache_lock tutulurken çağrılır.
        """
        status.stamp = self.get_clock().now().to_msg()
        pub = self._status_pubs.get(drone_id)
        if pub is None:
            pub = self.create_publisher(
                AgentStatus,
                f'/swarm/public/drone{drone_id}/status',
                _MESH_QOS,
            )
            self._status_pubs[drone_id] = pub
        pub.publish(status)

    def _isle_origin(self, leader_id: int, payload: bytes) -> None:
        """TIP_ORIGIN -> /swarm/public/origin'e SwarmOrigin yayınlar.

        Sender (gönderici lider) sadece gps_fix_type>=3 olduğunda ORIGIN
        yayınladığı için (bkz. _on_origin_out), bu pakedi gördüğümüzde
        kalite garantilidir. gps_fix_type=3 (3D fix) varsayılır;
        firmware ileride alanı paketleyebilirse gerçek değer kullanılır.
        """
        origin = pp.origin_coz(payload)
        msg = SwarmOrigin()
        msg.stamp = self.get_clock().now().to_msg()
        msg.leader_agent_id = leader_id
        msg.origin_lat_deg = origin.lat_1e7 / 1e7
        msg.origin_lon_deg = origin.lon_1e7 / 1e7
        msg.origin_alt_amsl_m = origin.alt_mm / 1000.0
        msg.valid = True
        # Sender garantisi: en az 3D fix. Gerçek değer payload'da yok
        # (16 byte dolu); subscriber bu varsayım üzerinden çalışsın.
        msg.gps_fix_type = 3
        msg.sequence = origin.sequence
        # NED dönüşümü için yerel kopya — komşu POSE paketlerini ortak
        # NED frame'e çevirebilelim.
        self._son_origin = msg
        self._origin_pub.publish(msg)

    def _isle_komut(self, source_id: int, payload: bytes) -> None:
        """TIP_KOMUT -> /swarm/public/control/command'a SwarmControlCommand.

        Joystick float32 değerleri int16*100 ile taşındığı için 100'e
        bölünerek geri çevrilir. deadman_pressed mesh'te bayrak biti
        olarak taşınır; aksi halde downstream motion'u sessizce reddeder.
        sequence_num bridge tarafında üretilir; firmware payload'da
        sequence yok, mesh_config.h ile teyit edilmesi gerekir.
        """
        k = pp.komut_coz(payload)
        # Guided (YKİ tekil komut): FSM/mode_manager'ı baypas edip doğrudan
        # px4_bridge'e String komuta çevir. source_id burada HEDEF drone'dur
        # (base gönderirken iha_id'ye hedefi yazar); bize veya broadcast'e
        # yönelikse uygula. Joystick sürü komutu eskisi gibi akar.
        if k.alt_tip == pp.KOMUT_MODE_GUIDED:
            # Hedef payload'da (k.target_id) — mesh çerçeve id'si kaynak MAC'ten
            # üretildiği için base'in id'sini taşır, hedefi DEĞİL.
            self.get_logger().info(
                f'[GUIDED] KOMUT geldi: hedef={k.target_id} bayraklar=0x{k.flags:02X} '
                f'(benim id={self._agent_id}, cerceve_kaynak={source_id})'
            )
            if k.target_id in (self._agent_id, 0):
                self._guided_discrete_uygula(k)
            return
        msg = SwarmControlCommand()
        msg.stamp = self.get_clock().now().to_msg()
        msg.mode = k.alt_tip
        msg.roll_cmd = k.roll_x100 / 100.0
        msg.pitch_cmd = k.pitch_x100 / 100.0
        msg.yaw_cmd = k.yaw_x100 / 100.0
        msg.throttle_cmd = k.throttle_x100 / 100.0
        msg.takeoff = bool(k.flags & pp.KOMUT_FLAG_TAKEOFF)
        msg.land = bool(k.flags & pp.KOMUT_FLAG_LAND)
        msg.rtl = bool(k.flags & pp.KOMUT_FLAG_RTL)
        msg.emergency_stop = bool(k.flags & pp.KOMUT_FLAG_EMERGENCY)
        # FORMASYON TALEBİ (30 Temmuz): bayrak + hangi formasyon + aralık.
        # `formasyon_talebi_gecerli` bayrağın anlamlı bir formasyonla geldiğini
        # doğrular. Bayrak set ama formasyon 0 ise gönderen ESKİ sürümdür (bu
        # alanlar eklenmeden önceki kod); o talebi uygulamak sürüyü
        # FORMATION_UNKNOWN'a ve spacing 0'a göndermek olur. Uygulamak yerine
        # reddediyoruz ve uyarıyoruz — sürüm uyumsuzluğu sessiz kalmamalı.
        if k.flags & pp.KOMUT_FLAG_FORMATION_CHANGE and not k.talep_formasyon:
            self.get_logger().warning(
                f'agent {source_id}: FORMATION_CHANGE bayrağı formasyon=0 ile '
                f'geldi — talep reddedildi. Gönderen eski sürüm olabilir '
                f'(talep_formasyon/talep_spacing_dm alanları 30 Temmuz eklendi).'
            )
        msg.formation_change_requested = k.formasyon_talebi_gecerli
        msg.requested_formation = k.talep_formasyon
        # 0 = "belirtilmedi" olarak yayılıyor. Alıcı taraf (mode_manager) bunu
        # üzerine yazmama kuralıyla ele alıyor — o yüzden burada uydurma bir
        # varsayılan doldurmuyoruz; taşıma katmanı politika üretmemeli.
        msg.requested_spacing_m = k.talep_spacing_m
        msg.deadman_pressed = bool(
            k.flags & pp.KOMUT_FLAG_DEADMAN_PRESSED
        )
        msg.command_valid = True
        # Bridge-tarafı sequence: her alınan KOMUT için +1. Dedup yapan
        # downstream'ler 0 görmek yerine monoton bir sayı görmeli.
        self._komut_rx_seq = (self._komut_rx_seq + 1) & 0xFFFFFFFF
        msg.sequence_num = self._komut_rx_seq
        msg.source_module = f'esp32_bridge_from_agent_{source_id}'
        self._control_pub.publish(msg)

    # =================================================================
    # GUIDED (YKİ tekil komut) — mesh -> px4_bridge çevirisi
    # =================================================================
    def _guided_discrete_uygula(self, k: pp.KomutVeri) -> None:
        """Guided TIP_KOMUT bayraklarını px4_bridge String komutuna çevirir.

        arm/disarm/takeoff/land/rtl. Takeoff irtifası throttle alanında
        (metre*100) taşınır. FSM'i baypas eder — guided modda operatör otoritesi.
        """
        if k.flags & pp.KOMUT_FLAG_ARM:
            # UCAK-ICI KOPRU (19 Agustos 2026, P0.11): YKI'nin guided yolu
            # agent_fsm'i hic gormuyordu ve ajan IDLE'da kaliyordu — G2'de
            # olculdu: 638 sn'de sifir secim. Guided ARM ayni zamanda "gorev
            # basliyor" demek; olay BURADA, ucak icinde uretiliyor ki
            # agent_fsm IDLE->ARMING->ARMED yurusun ve consensus secim
            # yapabilsin (ELIGIBLE_STATES en dusuk ARMED ister). Mesh'e yeni
            # paket tipi eklemek yerine ucak-ici uretim secildi: firmware
            # whitelist'ine carpmaz, teslimati kanitlanmis guided yolun
            # aynisi. ARMED->TAKEOFF'u tetiklemez: agent_fsm gecis doneminde
            # kalkis_olayla=false ile kaliyor, kalkis guided yoldan gelir.
            self._gorev_basladi_olayi_yayinla()
            self._guided_string('arm')
        elif k.flags & pp.KOMUT_FLAG_DISARM:
            self._guided_hedef = None
            self._guided_string('disarm')
        elif k.flags & pp.KOMUT_FLAG_TAKEOFF:
            irtifa = k.throttle_x100 / 100.0
            if irtifa <= 0.0:
                irtifa = 10.0
            # ESKI HEDEFI TEMIZLE — disarm/land/rtl temizliyordu, takeoff
            # TEMIZLEMIYORDU. Kalan bir hedef, yatay kilit acilir acilmaz
            # px4_bridge'e "taze setpoint" gibi gorunup kalkisi ele gecirir:
            # ucak yeni kalkis irtifasina degil ONCEKI gorevin hedefine gider.
            # Kalkis boyunca otorite kalkis komutunda olmali.
            self._guided_hedef = None
            self._guided_string('offboard')
            self._guided_string(f'takeoff:{irtifa:.1f}')
        elif k.flags & pp.KOMUT_FLAG_LAND:
            self._guided_hedef = None
            self._guided_string('land')
        elif k.flags & pp.KOMUT_FLAG_RTL:
            self._guided_hedef = None
            self._guided_string('rtl')

    def _guided_string(self, komut: str) -> None:
        """px4_bridge FSM komut topic'ine String yayınlar (arm/land/takeoff...)."""
        m = String()
        m.data = komut
        self._guided_cmd_pub.publish(m)
        self.get_logger().info(f'[GUIDED] px4 komut: {komut}')

    def _gorev_basladi_olayi_yayinla(self) -> None:
        """Guided ARM'ı EVENT_MISSION_STARTED'a çevirir (uçak-içi köprü).

        target_agent_id = KENDİ kimliğimiz: her uçak yalnız kendi ajanını
        tetikler (guided arm zaten uçak başına geliyor; broadcast arm'da da
        her bridge kendi olayını üretir). Guided komut mesh'te 4 kopya
        geldiği için olay da tekrar üretilebilir — agent_fsm için zararsız:
        IDLE değilse yalnız mission_start bayrağına bakar, o da geçiş
        döneminde kalkis_olayla=false ile kapalı.
        """
        ev = SystemEvent()
        ev.stamp = self.get_clock().now().to_msg()
        ev.event_type = SystemEvent.EVENT_MISSION_STARTED
        ev.severity = SystemEvent.SEVERITY_INFO
        ev.source_agent_id = self._agent_id
        ev.target_agent_id = self._agent_id
        ev.source_module = 'esp32_bridge_guided_koprusu'
        ev.message = 'guided arm -> gorev basladi'
        ev.value = 0.0
        ev.has_position = False
        # Kendi event'imiz: /swarm/internal/events/system (köprü public'e döngüler)
        self._event_pub_internal.publish(ev)
        self.get_logger().info(
            '[GUIDED] gorev-basladi olayi yayinlandi (ucak-ici kopru)'
        )

    def _isle_goto(self, source_id: int, payload: bytes) -> None:
        """TIP_GOTO -> hedef bizsek AgentSetpoint (NED) olarak px4_bridge'e.

        Hedef mesh'ten bir KEZ gelir; 10 Hz LOKAL tekrar (_guided_hedef_tekrar)
        OFFBOARD akışını canlı tutar (mesh'e çıkmaz). 'offboard' idempotent gönderilir.
        Hedef drone payload'da (g.target_id) — çerçeve id'si kaynağı taşır.
        """
        g = pp.goto_coz(payload)
        self.get_logger().info(
            f'[GUIDED] GOTO geldi: hedef={g.target_id} '
            f'(benim id={self._agent_id}, cerceve_kaynak={source_id})'
        )
        if g.target_id not in (self._agent_id, 0):
            return
        sp = AgentSetpoint()
        sp.agent_id = self._agent_id
        sp.source = AgentSetpoint.SOURCE_POSITION_CONTROLLER
        sp.priority = AgentSetpoint.PRIORITY_POSITION
        sp.x = g.kuzey_m
        sp.y = g.dogu_m
        sp.z = g.asagi_m
        sp.position_valid = True
        if g.yaw_gecerli:
            sp.heading_deg = g.yaw_deg
            sp.heading_valid = True
        sp.source_module = 'esp32_bridge_guided'
        self._guided_hedef = sp
        self._guided_string('offboard')
        self._guided_hedef_yayinla()
        self.get_logger().info(
            f'[GUIDED] goto NED=({sp.x:.1f},{sp.y:.1f},{sp.z:.1f}) '
            f'yaw={("%.0f" % sp.heading_deg) if g.yaw_gecerli else "serbest"}'
        )

    def _guided_hedef_yayinla(self) -> None:
        """Aktif guided hedefi güncel zaman damgasıyla px4_bridge'e yayınlar."""
        if self._guided_hedef is not None:
            self._guided_hedef.stamp = self.get_clock().now().to_msg()
            self._guided_sp_pub.publish(self._guided_hedef)

    def _guided_hedef_tekrar(self) -> None:
        """10 Hz timer: aktif guided hedefi LOKAL tekrar yayınla (mesh'e çıkmaz)."""
        self._guided_hedef_yayinla()

    def _isle_leader_hb(self, source_id: int, payload: bytes) -> None:
        """TIP_LEADER_HB -> /swarm/public/leader/heartbeat'e yayın."""
        hb = pp.leader_hb_coz(payload)
        msg = LeaderHeartbeat()
        msg.stamp = self.get_clock().now().to_msg()
        msg.leader_id = hb.leader_id
        msg.sequence_num = hb.sequence_num
        msg.election_round = hb.election_round
        msg.active_agent_count = hb.active_agent_count
        msg.mission_active = bool(hb.mission_active)
        self._leader_hb_pub.publish(msg)
        # Lider takibi (KARAR 11 kapısı): heartbeat en sık gelen lider
        # sinyalidir, seçim mesajı tek atımlık. İkisini de dinliyoruz ki
        # bridge yeniden başlarsa bir sonraki heartbeat'te lideri öğrensin.
        self._lider_kaydet(int(hb.leader_id))

    def _isle_election(self, source_id: int, payload: bytes) -> None:
        """TIP_ELECTION -> /swarm/public/election/result'a yayın."""
        e = pp.election_coz(payload)
        msg = ElectionResult()
        msg.stamp = self.get_clock().now().to_msg()
        msg.sequence_num = e.sequence_num
        msg.new_leader_id = e.new_leader_id
        msg.election_round = e.election_round
        msg.triggered_by_agent_id = e.triggered_by
        msg.reason = e.reason
        msg.incarnation = e.incarnation
        # 0 dolgu ID'lerini at — gerçekte onay verenler bunlar
        msg.confirmed_by_agent_ids = [
            i for i in e.confirmed_ids if i != 0
        ]
        self._election_pub.publish(msg)
        self._lider_kaydet(int(e.new_leader_id))

    def _isle_renk(self, source_id: int, payload: bytes) -> None:
        """TIP_RENK -> SystemEvent.EVENT_COLOR_ZONE_DETECTED olarak yayın.

        Mesh üzerinden komşulardan gelen renk bölgesi tespitleri sürünün
        ortak hafızasına SystemEvent olarak yayımlanır. GPS koordinatları
        1e-7 derece tamsayı olduğu için NED pos_x/y'ye konmaz; mesaj
        string'inde taşınır.
        """
        r = pp.renk_coz(payload)
        msg = SystemEvent()
        msg.stamp = self.get_clock().now().to_msg()
        msg.event_type = SystemEvent.EVENT_COLOR_ZONE_DETECTED
        msg.severity = SystemEvent.SEVERITY_INFO
        msg.source_agent_id = source_id
        msg.value = float(r.renk)
        msg.has_position = False
        msg.source_module = 'esp32_bridge'
        msg.message = f'renk={r.renk} lat_1e7={r.lat} lon_1e7={r.lon}'
        # Komşudan gelen event: bridge proxy rolünde /public/'a düşürür
        self._event_pub_public.publish(msg)

    def _isle_gorev(self, source_id: int, payload: bytes) -> None:
        """TIP_GOREV -> SystemEvent olarak yayınlanır.

        QR çözümleme normalde qr_detector'da yapılır; ancak mesh
        üzerinden komşu drone bir görev paketi (formasyon tipi, irtifa,
        bekleme süresi) iletmek isterse bu handler devreye girer.
        SystemEvent ile downstream (mission_fsm, GCS) haberdar edilir.
        """
        g = pp.gorev_coz(payload)
        msg = SystemEvent()
        msg.stamp = self.get_clock().now().to_msg()
        # GOREV paketi QR çözümünden çıkar, en yakın event QR_PARSED
        msg.event_type = SystemEvent.EVENT_QR_PARSED
        msg.severity = SystemEvent.SEVERITY_INFO
        msg.source_agent_id = source_id
        msg.value = float(g.tip)
        msg.has_position = False
        msg.source_module = 'esp32_bridge'
        msg.message = (
            f'gorev tip={g.tip} p1={g.param1} p2={g.param2} '
            f'bekleme={g.bekleme_suresi_s}s'
        )
        self._event_pub_public.publish(msg)

    def _isle_qr(self, source_id: int, payload: bytes) -> None:
        """TIP_QR_DATA -> SystemEvent.EVENT_QR_PARSED (YKİ görüntülesin).

        Şartname s.13: QR'ın YKİ'de en az bir kez görüntülenmesi zorunlu.
        """
        q = pp.qr_coz(payload)
        msg = SystemEvent()
        msg.stamp = self.get_clock().now().to_msg()
        msg.event_type = SystemEvent.EVENT_QR_PARSED
        msg.severity = SystemEvent.SEVERITY_INFO
        msg.source_agent_id = source_id
        msg.value = float(q.action_id)
        msg.has_position = False
        msg.source_module = 'esp32_bridge'
        msg.message = (
            f'qr drone={q.drone_id} action={q.action_id} '
            f'lat_1e7={q.lat} lon_1e7={q.lon}'
        )
        self._event_pub_public.publish(msg)

    def _isle_swarm_state(self, source_id: int, payload: bytes) -> None:
        """TIP_SWARM_STATE -> SystemEvent (komşunun sürü FSM görünümü)."""
        s = pp.swarm_state_coz(payload)
        msg = SystemEvent()
        msg.stamp = self.get_clock().now().to_msg()
        msg.event_type = SystemEvent.EVENT_UNKNOWN
        msg.severity = SystemEvent.SEVERITY_INFO
        msg.source_agent_id = source_id
        msg.value = float(s.swarm_fsm_state)
        msg.has_position = False
        msg.source_module = 'esp32_bridge'
        msg.message = (
            f'swarm_state mission={s.mission_id} fsm={s.swarm_fsm_state} '
            f'leader={s.active_leader} formation={s.formation}'
        )
        self._event_pub_public.publish(msg)

    def _isle_rtk(self, payload: bytes) -> None:
        """TIP_RTK -> RTCM baytlarını px4_interface'e (rtcm/in) iletir.

        Zincir: baz -> mesh -> ESP -> burası -> px4_bridge -> MAVROS -> PX4.
        """
        self._rtk_alindi += 1
        msg = UInt8MultiArray()
        msg.data = list(payload)
        self._rtcm_pub.publish(msg)

    def _isle_failsafe(self, payload: bytes) -> None:
        """Mesh kopunca gelen 0xFA'yı agent_fsm'e RTL/Land olayına çevirir."""
        if not payload:
            return
        ftip = payload[0]
        if ftip == pp.FAILSAFE_TIP_RTL:
            etype = SystemEvent.EVENT_RTL_TRIGGERED
        elif ftip == pp.FAILSAFE_TIP_LAND:
            etype = SystemEvent.EVENT_EMERGENCY_LAND
        else:
            etype = SystemEvent.EVENT_UNKNOWN

        msg = SystemEvent()
        msg.stamp = self.get_clock().now().to_msg()
        msg.event_type = etype
        msg.severity = SystemEvent.SEVERITY_WARNING
        msg.source_agent_id = self._agent_id
        msg.target_agent_id = self._agent_id
        msg.source_module = 'esp32_bridge'
        msg.message = f'mesh failsafe tip={ftip}'
        self._event_pub_public.publish(msg)

    def _isle_qr_coords(self, payload: bytes) -> None:
        """QR konumlarını tek tek toplar, tablo dolunca yayınlar."""
        q = pp.qr_koord_coz(payload)
        self._qr_koord_toplam = q.toplam
        self._qr_koord_toplayici[q.qr_id] = (q.lat, q.lon)
        if q.toplam > 0 and len(self._qr_koord_toplayici) >= q.toplam:
            self._qr_coords_yayinla()

    def _qr_coords_yayinla(self) -> None:
        """Toplanan QR tablosunu QRCoordinates olarak yayınlar."""
        ids = sorted(self._qr_koord_toplayici.keys())
        msg = QRCoordinates()
        msg.stamp = self.get_clock().now().to_msg()
        msg.qr_ids = ids
        msg.lat_deg = [self._qr_koord_toplayici[i][0] / 1e7 for i in ids]
        msg.lon_deg = [self._qr_koord_toplayici[i][1] / 1e7 for i in ids]
        self._qr_coords_pub.publish(msg)

    # =================================================================
    # ROS2 -> MESH İŞLEYİCİLERİ (UART'a yaz)
    # =================================================================
    def _uart_yaz(self, tip: int, iha_id: int, payload: bytes,
                  maks: int = 18) -> None:
        """Bir paketi çerçeveleyip (CRC+COBS) seri porta yazar.

        Args:
            tip (int): Paket tipi (TIP_*).
            iha_id (int): Kaynak drone kimliği.
            payload (bytes): Gönderilecek yük.
            maks (int): İzin verilen en büyük payload. Varsayılan 18, mesh
                paketlerinin (`mesh_paket_t.veri[18]`) sınırı. TIP_RTK bunun
                istisnası: RTCM3 mesajı 1029 bayta kadar çıkar ve ESP tarafında
                fragmentlenir, `mesh_gonder()` yolunu hiç kullanmaz.

        Not: 18 baytlık varsayılan bir koruma, kısıt değil. Yanlış boyutta bir
        payload ESP'de sessizce yanlış çözülür (alanlar kayar), o yüzden erken
        yakalanıyor. RTCM için sınırı gevşetiyoruz ama KALDIRMIYORUZ — üst sınır
        yine RTCM3'ün kendi tavanı.
        """
        if not 1 <= len(payload) <= maks:
            self.get_logger().warning(
                f'UART payload 1-{maks} byte olmalı ({len(payload)}), atlandı'
            )
            return
        govde = bytes([tip, iha_id]) + payload
        crc = crc16(govde)
        cerceve = govde + bytes([(crc >> 8) & 0xFF, crc & 0xFF])
        with self._ser_lock:
            if self._ser is None or not self._ser.is_open:
                # Port kopuk; okuma thread'i reconnect dener. Drop et.
                self._gonderim_drop += 1
                return
            try:
                self._ser.write(cobs_encode(cerceve))
                self._gonderim_ok += 1
            except serial.SerialException as exc:
                self.get_logger().warning(
                    f'Seri yazma hatası, port kapatılıyor: {exc}'
                )
                try:
                    self._ser.close()
                except Exception:  # noqa: BLE001
                    pass
                self._ser = None
                self._gonderim_drop += 1

    # RTCM3 çerçeve tavanı: uzunluk alanı 10 bit → payload <= 1023,
    # tam çerçeve = 3 (başlık) + 1023 + 3 (CRC24Q) = 1029. Spec §2.6.
    _RTCM_MAKS = 1029
    _RTCM_MIN = 6          # boş payload'lı en küçük geçerli çerçeve

    def _on_rtcm_out(self, msg: UInt8MultiArray) -> None:
        """RTCM3 mesajını TIP_RTK çerçevesi olarak baz ESP'ye yazar.

        Zincir: u-blox -> yki_rtcm_reader -> (bu topic) -> ESP -> mesh -> drone.

        Fragmentleme BURADA YAPILMAZ — tam mesaj gönderilir, parçalama baz
        ESP'nin işi (spec §3.1: "YKİ PARÇALAMA YAPMAZ"). İki yerde parçalarsak
        çift fragmantasyon olur ve drone tarafındaki reassembly bozulur.
        """
        veri = bytes(msg.data)

        # Ucuz savunmalar: okuyucu CRC-24Q'yu zaten doğruluyor, ama bu topic'e
        # başka bir şey yayın yaparsa çöp mesh'e çıkmadan burada dursun.
        if not self._RTCM_MIN <= len(veri) <= self._RTCM_MAKS:
            self._rtcm_reddedilen += 1
            self.get_logger().warning(
                f'RTCM boyutu geçersiz ({len(veri)} byte), atıldı'
            )
            return
        if veri[0] != 0xD3:
            self._rtcm_reddedilen += 1
            self.get_logger().warning('RTCM 0xD3 ile başlamıyor, atıldı')
            return
        beklenen = 3 + (((veri[1] & 0x03) << 8) | veri[2]) + 3
        if beklenen != len(veri):
            self._rtcm_reddedilen += 1
            self.get_logger().warning(
                f'RTCM uzunluğu tutarsız (beklenen {beklenen}, '
                f'gelen {len(veri)}), atıldı'
            )
            return

        # iha_id alanı RTK'de BAZ_ID (99) sentinel'i taşır — mesh kimliği DEĞİL.
        # ESP tarafı (rtk_sender.h) bu değeri birebir bekliyor.
        self._uart_yaz(pp.TIP_RTK, pp.BAZ_ID, veri, maks=self._RTCM_MAKS)
        self._rtcm_gonderilen += 1

    def _on_own_status(self, msg: AgentStatus) -> None:
        """Kendi otoritatif durumumuzu TIP_POSE + TIP_DURUM olarak yayar.

        Kontrat 3.1: agent_fsm'in /swarm/internal/drone{id}/status
        yayınını alıp mesh'e iletiriz. POSE 10Hz tavanında (çarpışma
        önleme için yeterli), DURUM 1Hz tavanında (state değişimi
        nadiren, batarya/sensör 1Hz yeterli). Hem rate-limit hem UART
        akış kontrolü için iki ayrı periyot.
        """
        now = time.monotonic()

        # --- POSE 10Hz ---
        if now - self._son_pose_gonderim_ts >= self._pose_periyot_s:
            self._son_pose_gonderim_ts = now
            # alt_dm: GORELI irtifa (yerden yukseklik, m yukari; dm) — AMSL DEGIL.
            # ONCEDEN -pos_z (EKF yerel Z) kullaniliyordu; ANCAK EKF yerel-Z origin'i
            # boot'a bagli ~10m kayabiliyor VE ucus boyunca suruyor -> yerdeyken YKI
            # 10m gosteriyordu, min-nav guvenlik kilidini bosa cikariyordu (yerde
            # direkt goto -> devrilme). SAGLAM kaynak: AMSL - home_AMSL (PX4 rel_alt
            # ile ayni, QGC ile ayni, ~0 yerde). Home yoksa 0 gonder (guvenli:
            # kilit yerde sayar, oto-kalkis zorlar; yanlislikla yatay nav baslatmaz).
            if msg.home_alt_amsl_m != 0.0 and msg.gps_fix_type >= 3:
                rel_alt_m = msg.alt_amsl_m - msg.home_alt_amsl_m
            else:
                rel_alt_m = 0.0
            payload = pp.pose_paketle(
                lat=int(msg.lat_deg * 1e7),
                lon=int(msg.lon_deg * 1e7),
                alt_dm=int(rel_alt_m * 10.0),
                heading=int(msg.heading_deg * 10.0),
                vx=int(msg.vel_x * 100.0),
                vy=int(msg.vel_y * 100.0),
                vz=int(msg.vel_z * 100.0),
            )
            self._uart_yaz(pp.TIP_POSE, self._agent_id, payload)

        # --- DURUM 1Hz ---
        # Ayrılma akışı için kritik: komşular bizim state'imizi bilmeli.
        # APF de DETACHED/LANDED komşulara avoidance hesaplamaz.
        if now - self._son_durum_gonderim_ts >= self._durum_periyot_s:
            self._son_durum_gonderim_ts = now
            # AgentStatus.state -> firmware DURUM kodu çevir
            durum_kodu = _STATE_DURUM_MAP.get(msg.state, _DURUM_BILINMIYOR)
            # battery_pct'i 0-100 aralığına kırp (negatif veya >100 olabilir)
            batt_pct = max(0, min(100, int(msg.battery_percent)))
            payload = pp.durum_paketle(
                drone_id=self._agent_id,
                durum=durum_kodu,
                armed=1 if msg.armed else 0,
                gps_fix_type=msg.gps_fix_type,
                battery_pct=batt_pct,
                battery_volt=float(msg.battery_voltage_v),
                ekf_ok=1 if msg.estimator_ok else 0,
                imu_ok=1 if msg.imu_healthy else 0,
                mag_ok=1 if msg.mag_healthy else 0,
                baro_ok=1 if msg.baro_healthy else 0,
                rssi=0,        # bizim kendi RSSI yok; firmware doldurur
                mesh_link_ok=1,  # gönderebiliyorsak link kuruluyor
                mesh_komsu_sayisi=len(self._komsu_son_goruldu),
                # REV C alanları — mesh'te yeni açılan yere giriyorlar.
                # ucus_modu: PX4'ün BİLDİRDİĞİ mod (switch pozisyonu değil).
                ucus_modu=int(msg.flight_mode),
                gps_uydu=int(msg.gps_satellites),
                gps_hdop=float(msg.gps_hdop),
                # Güvenlik kritik: kill switch açıkken operatör drone'u
                # "boşta" görüyordu; artık mesh'ten geçiyor.
                kill_switch_active=1 if msg.kill_switch_active else 0,
                rc_link_ok=1 if msg.rc_link_ok else 0,
                # PX4 PREARM_CHECK: emniyet anahtarı dahil tüm ön-kontroller.
                ready_to_arm=1 if msg.ready_to_arm else 0,
                # ORIGIN DOGRULAMASI: px4_bridge bunu GONDERMEKLE degil,
                # GPS ile PX4'un yerel cercevesini KARSILASTIRARAK koyuyor.
                # Mesh'ten gecmedigi surece baz istasyonu uyduruyordu.
                origin_synced=1 if msg.origin_synced else 0,
            )
            self._uart_yaz(pp.TIP_DURUM, self._agent_id, payload)

    def _on_origin_out(self, msg: SwarmOrigin) -> None:
        """Lider origin'ini TIP_ORIGIN olarak ESP32'ye gönderir.

        ORIGIN payload 16 byte (lat+lon+alt+seq) — gps_fix_type ve
        gps_hdop'u taşıyacak yer yok. Bu yüzden örtük kalite garantisi
        uygulanır: SADECE valid=True VE gps_fix_type>=3 (3D fix)
        olduğunda mesh'e yollanır. Aksi halde sürü kötü origin
        uygulamasın diye yayın atlanır (kontrat: 'gps_fix_type>=3
        olana kadar origin uygulanmamalı').

        Yan etki: Origin yerel olarak da kaydedilir → komşu POSE
        paketleri NED'e çevrilebilsin.
        """
        # Bu drone lider ise origin'i kendi GPS'imizden alıyoruz;
        # NED dönüşümü için sakla (mesh'e yayın koşullarından önce,
        # çünkü kendi pos hesaplaması için lokal değer geçerlidir).
        if msg.valid and msg.gps_fix_type >= 3:
            self._son_origin = msg
        if not msg.valid:
            self.get_logger().warning(
                'ORIGIN valid=false, mesh yayını atlandı'
            )
            return
        if msg.gps_fix_type < 3:
            self.get_logger().warning(
                f'ORIGIN gps_fix_type={msg.gps_fix_type} < 3, '
                f'mesh yayını atlandı (kalite yetersiz)'
            )
            return
        payload = pp.origin_paketle(
            lat_1e7=int(msg.origin_lat_deg * 1e7),
            lon_1e7=int(msg.origin_lon_deg * 1e7),
            alt_mm=int(msg.origin_alt_amsl_m * 1000.0),
            sequence=msg.sequence,
        )
        self._uart_yaz(pp.TIP_ORIGIN, self._agent_id, payload)

    def _on_control_out(self, msg: SwarmControlCommand) -> None:
        """SwarmControlCommand'ı TIP_KOMUT olarak ESP32'ye gönderir.

        Görev 2 joystick akışı: int16 ölçeklemesi sınırı dışına çıkan
        değerler kırpılır.
        """
        flags = 0
        if msg.takeoff:
            flags |= pp.KOMUT_FLAG_TAKEOFF
        if msg.land:
            flags |= pp.KOMUT_FLAG_LAND
        if msg.rtl:
            flags |= pp.KOMUT_FLAG_RTL
        if msg.emergency_stop:
            flags |= pp.KOMUT_FLAG_EMERGENCY
        if msg.formation_change_requested:
            flags |= pp.KOMUT_FLAG_FORMATION_CHANGE
        # SwarmControlCommand.deadman_pressed mesh'te bayrak biti olarak
        # taşınır; aksi halde alıcı tarafta downstream motion'u sessizce
        # reddeder ("command_valid AND deadman_pressed" şartı).
        if msg.deadman_pressed:
            flags |= pp.KOMUT_FLAG_DEADMAN_PRESSED

        # FORMASYON TALEBİ — 30 Temmuz kusur düzeltmesi.
        # Önceden yalnız KOMUT_FLAG_FORMATION_CHANGE bayrağı taşınıyordu;
        # requested_formation ve requested_spacing_m mesh'ten GEÇMİYORDU ve
        # alıcıda ROS varsayılanında (0) kalıyordu. Sonuç: "formasyon değiştir"
        # gidiyor, HANGİ formasyon bilgisi kayboluyordu; spacing=0.0 ile
        # compute_slot_offsets() "spacing > 0 olmali" diye ValueError atıyordu.
        # Yani YKİ/kumanda formasyon seçimi sessizce kırıktı.
        #
        # Anlamsal doğrulama BURADA (codec'te değil): bayrak formasyon 0 ile
        # anlamsız, yaymak sürüyü FORMATION_UNKNOWN'a gönderir. Bayrağı düşür
        # ve UYAR — sessiz kalmak bu hatanın tekrar aynı şekilde gizlenmesi olur.
        talep_formasyon = int(msg.requested_formation)
        talep_spacing = float(msg.requested_spacing_m)
        if flags & pp.KOMUT_FLAG_FORMATION_CHANGE:
            if not talep_formasyon:
                self.get_logger().warning(
                    'formation_change_requested=True ama requested_formation=0 '
                    '— bayrak düşürüldü (alıcı FORMATION_UNKNOWN uygulamasın)'
                )
                flags &= ~pp.KOMUT_FLAG_FORMATION_CHANGE
            elif talep_spacing > 25.5:
                self.get_logger().warning(
                    f'requested_spacing_m={talep_spacing:.1f} mesh tavanını '
                    f'(25.5 m) aştı, 25.5 m olarak gönderiliyor'
                )

        payload = pp.komut_paketle(
            alt_tip=msg.mode,
            flags=flags,
            roll_x100=_kirp_int16(msg.roll_cmd * 100.0),
            pitch_x100=_kirp_int16(msg.pitch_cmd * 100.0),
            yaw_x100=_kirp_int16(msg.yaw_cmd * 100.0),
            throttle_x100=_kirp_int16(msg.throttle_cmd * 100.0),
            talep_formasyon=talep_formasyon,
            talep_spacing_m=talep_spacing,
        )
        self._uart_yaz(pp.TIP_KOMUT, self._agent_id, payload)

    def _guided_gonder(self, tip: int, hedef: int, payload: bytes,
                       goto_iptal: bool = False) -> None:
        """Guided komutu tekrar kuyruğuna koyar (4 kopya, TEK ortak zamanlayıcı).

        ESKI HALI IKI DRONE'DA BOZUKTU — 1 Agustos'ta olculdu. Her komut kendi
        timer'iyla 250 ms arayla 4 kez gonderiliyordu ve yorumu "base ESP'nin
        200 ms JOYSTICK limiti var, 250 ms hepsini gecirir" diyordu. Bu TEK
        DRONE icin dogru; IKI drone icin YANLIS, cunku base'deki limit TIP
        BASINA tutuluyor, HEDEF BASINA degil (mesh_config.h:597,
        _son_tip_gonderim_ms[tip]). Iki ucagin tekrar dizileri ayni 200 ms
        kapisini paylasiyor:

            drone1 -> t = 0.00  0.25  0.50  0.75
            drone2 -> t = 0.30  0.55  0.80  1.05      (YKI 300 ms araliklı)
            kapi   ->   gecer gecer  DUSER gecer DUSER gecer DUSER ... gecer
                        (d1#1) (d1#2)(d2#1) (d1#3)(d2#2) (d1#4)(d2#3)  (d2#4)

        Yani ikinci ucak 4 cerceveden 3'unu kaybediyor, elinde tek sans
        kaliyor; o da havada duserse komut hic ulasmiyor. Log bunu birebir
        dogruladi: ylp01, drone 1'in DORT land cercevesini, kendisininse
        TEK tanesini duydu. Kalkista o tek sans da dustu ve ucak ARMLI
        halde yerde kaldi.

        SIMDIKI HALI: tum guided cerceveler TEK kuyruga giriyor ve tek bir
        20 Hz zamanlayici bosaltiyor. Kuyruk, TIP BASINA en az _TIP_ARALIK_S
        birakiyor (base kapilarinin ustunde) ve gonderdigi kaydi kuyrugun
        SONUNA atiyor — boylece ucaklar SIRAYLA gonderiyor. Iki takeoff:

            d1#1 d2#1 d1#2 d2#2 d1#3 d2#3 d1#4 d2#4   (300 ms arayla)

        Her ucak dort cercevenin dordunu de aliyor ve ilkini 300 ms icinde
        aliyor. Cagiranin (YKI gorev kosucusu, arayuz butonlari) araliga
        dikkat etmesi GEREKMIYOR — garanti burada.
        """
        # Ayni hedefe yeni GOTO gelince eskisinin bekleyen tekrarlari
        # anlamsizlasir (yeni hedef eskisini gecersiz kilar) — atilir.
        # TIP_KOMUT'ta genel ayiklama YOK: arm/takeoff/land birbirinin
        # yerine gecmez, her biri ulasmali. TEK ISTISNA goto_iptal, asagida.
        if tip == pp.TIP_GOTO:
            self._guided_kuyruk = [k for k in self._guided_kuyruk
                                   if not (k['tip'] == tip and k['hedef'] == hedef)]
        elif goto_iptal:
            # LAND / RTL / DISARM bekleyen GOTO'lari GECERSIZ KILAR.
            # P0.12(b), 20 Agustos 2026.
            #
            # ESKI HALI UCAGI HEDEFE GERI CEKIYORDU. Zincir:
            #   1. Gorev kosucusu 0.2 sn'de bir goto POST ediyor; her goto
            #      kuyruga 4 KOPYA giriyor (_GUIDED_TEKRAR).
            #   2. Iptal/varis olunca hemen land gonderiliyor. TIP_KOMUT
            #      ayri kapidan (0.30 s) cikiyor, ilk kopyasi ~0.05 sn'de.
            #   3. AMA kuyrukta o hedefe ait 3-4 GOTO kopyasi KALIYOR ve
            #      sonraki ~0.75 sn boyunca ucaga varmaya devam ediyor.
            #   4. Ucakta sira: land -> AUTO.LAND, _guided_hedef=None;
            #      sonra bayat goto -> _isle_goto KOSULSUZ
            #      _guided_string('offboard') yolluyor ve _guided_hedef'i
            #      YENIDEN kuruyor -> PX4 AUTO.LAND'dan cikip OFFBOARD'a
            #      donuyor ve yurutucu ucagi eski hedefe geri suruyor.
            #   5. 10 Hz'lik _guided_hedef_tekrar o hedefi surekli
            #      tazeledigi icin px4_bridge'in 0.5 sn bayatlama korumasi
            #      da HIC tetiklenmiyor — ucak bayat hedefte asili kaliyor.
            #
            # En kotu hali kill/iptal aninda: operator kesmek istiyor, boru
            # hatti ucagi hedefe geri cekiyor.
            #
            # KAPSAM: yalniz AYNI HEDEFE ait GOTO'lar atiliyor. Diger ucagin
            # kuyrugu dokunulmadan kaliyor — bir ucagi indirmek digerinin
            # gorevini kesmez.
            onceki = len(self._guided_kuyruk)
            self._guided_kuyruk = [
                k for k in self._guided_kuyruk
                if not (k['tip'] == pp.TIP_GOTO and k['hedef'] == hedef)
            ]
            dusen = onceki - len(self._guided_kuyruk)
            if dusen:
                self.get_logger().info(
                    f'[GUIDED] iptal komutu: drone{hedef} icin bekleyen '
                    f'{dusen} GOTO cercevesi kuyruktan dusuruldu '
                    f'(bayat hedef inisi iptal etmesin)')
        if len(self._guided_kuyruk) >= _GUIDED_KUYRUK_MAKS:
            atilan = self._guided_kuyruk.pop(0)
            self.get_logger().warning(
                f'guided kuyrugu dolu ({_GUIDED_KUYRUK_MAKS}) — '
                f"tip=0x{atilan['tip']:02X} hedef={atilan['hedef']} atildi")
        self._guided_kuyruk.append({
            'tip': tip, 'hedef': hedef, 'payload': payload,
            'kalan': _GUIDED_TEKRAR, 'en_erken': 0.0,
        })

    def _guided_kuyruk_bosalt(self) -> None:
        """Kuyruktaki guided cerceveleri tip basina aralikla gonderir.

        Tick basina TIP BASINA en fazla bir cerceve: tipler base'de ayri
        kapilar oldugu icin birbirini bekletmelerine gerek yok, ama ayni
        tipteki iki cerceve arasinda _TIP_ARALIK_S korunmali.
        """
        if not self._guided_kuyruk:
            return
        simdi = time.monotonic()
        gonderildi = set()
        for kayit in list(self._guided_kuyruk):
            tip = kayit['tip']
            if tip in gonderildi:
                continue
            aralik = _GUIDED_TIP_ARALIK_S.get(tip, _GUIDED_TIP_ARALIK_S_VARSAYILAN)
            if simdi - self._guided_son_gonderim.get(tip, 0.0) < aralik:
                continue
            if kayit['en_erken'] > simdi:
                continue
            self._uart_yaz(tip, kayit['hedef'], kayit['payload'])
            self._guided_son_gonderim[tip] = simdi
            gonderildi.add(tip)
            kayit['kalan'] -= 1
            self._guided_kuyruk.remove(kayit)
            if kayit['kalan'] > 0:
                # Sona at: sirayi diger hedefe ver (dongusel adalet).
                kayit['en_erken'] = simdi + _GUIDED_TEKRAR_ARALIK_S
                self._guided_kuyruk.append(kayit)

    def _on_guided_out(self, msg: GuidedCommand) -> None:
        """GuidedCommand'ı mesh'e iletir: TIP_GOTO veya guided TIP_KOMUT.

        Çerçeve iha_id'sine HEDEF drone yazılır ama mesh id taşımadığı için
        hedef asıl olarak payload'da (target_id) gider; drone buna göre süzer.
        Base istasyonunda çalışır — drone'da bu topic'e yayın olmadığı için dormant.
        """
        hedef = int(msg.agent_id)
        if msg.action == GuidedCommand.ACTION_GOTO:
            bayraklar = pp.GOTO_BAYRAK_YAW_GECERLI if msg.heading_valid else 0
            payload = pp.goto_paketle(
                kuzey_dm=_kirp_int16(msg.x * 10.0),
                dogu_dm=_kirp_int16(msg.y * 10.0),
                asagi_dm=_kirp_int16(msg.z * 10.0),
                yaw_ddeg=_kirp_int16(msg.heading_deg * 10.0),
                bayraklar=bayraklar,
                target_id=hedef,
            )
            self._guided_gonder(pp.TIP_GOTO, hedef, payload)
            return

        aksiyon_bayrak = {
            GuidedCommand.ACTION_ARM: pp.KOMUT_FLAG_ARM,
            GuidedCommand.ACTION_DISARM: pp.KOMUT_FLAG_DISARM,
            GuidedCommand.ACTION_TAKEOFF: pp.KOMUT_FLAG_TAKEOFF,
            GuidedCommand.ACTION_LAND: pp.KOMUT_FLAG_LAND,
            GuidedCommand.ACTION_RTL: pp.KOMUT_FLAG_RTL,
        }
        flag = aksiyon_bayrak.get(msg.action)
        if flag is None:
            self.get_logger().warning(f'guided: bilinmeyen action {msg.action}')
            return
        # Takeoff hedef irtifası throttle alanında (metre*100) taşınır.
        throttle = (
            _kirp_int16(msg.altitude_m * 100.0)
            if msg.action == GuidedCommand.ACTION_TAKEOFF else 0
        )
        payload = pp.komut_paketle(
            alt_tip=pp.KOMUT_MODE_GUIDED,
            flags=flag,
            roll_x100=0, pitch_x100=0, yaw_x100=0,
            throttle_x100=throttle,
            target_id=hedef,
        )
        # LAND / RTL / DISARM: bu ucagin bekleyen GOTO'lari gecersiz.
        # Ayrinti ve olculen zincir: _guided_gonder icindeki goto_iptal dali.
        #
        # NOT (henuz yapilmadi): ayni mekanizma DISARM icin bekleyen
        # ARM/TAKEOFF kayitlarina da uygulanabilir — 18 Agustos'ta olculen
        # "disarm kavgasi" onlardan geliyor (WORKFLOW_BULGULAR, P1). Bilerek
        # ayri birakildi: o bulgu dogrulanmadi ve bu duzeltmeyle ayni ucusta
        # iki degisiklik denenmesin.
        iptal_eder = bool(flag & (pp.KOMUT_FLAG_LAND
                                  | pp.KOMUT_FLAG_RTL
                                  | pp.KOMUT_FLAG_DISARM))
        self._guided_gonder(pp.TIP_KOMUT, hedef, payload,
                            goto_iptal=iptal_eder)

    # =================================================================
    # SÜRÜ KOORDİNASYONU (30 Temmuz) — docs/MESH_PROTOKOL_KARARLARI.md
    # =================================================================
    def _formasyon_yayinla(self, tam) -> None:
        """TamFormasyon'u FormationCommand'a çevirip yayınlar.

        OFFSETLER BURADA DOLDURULUYOR (KARAR 9). Mesh tarifi taşıyor, offsetleri
        `compute_slot_offsets()` ile geri açıyoruz. Zorunlu, çünkü
        `maneuver_executor_node.py:335-338` offset dizisi boşsa SESSİZCE
        `return` ediyor — boş dizi yayınlasak manevra hiç çalışmaz ve sebebi
        hiçbir logda görünmez. Bu sayede formation_node / collision_avoidance /
        maneuver_executor hiç değişmedi.
        """
        msg = FormationCommand()
        msg.stamp = self.get_clock().now().to_msg()
        self._formasyon_seq = (getattr(self, '_formasyon_seq', 0) + 1) & 0xFFFFFFFF
        msg.sequence_num = self._formasyon_seq
        msg.formation_type = tam.formasyon_tipi
        msg.center_x = float(tam.merkez_kuzey_m)
        msg.center_y = float(tam.merkez_dogu_m)
        msg.center_z = float(tam.merkez_asagi_m)
        msg.heading_deg = float(tam.heading_deg)
        msg.spacing_m = float(tam.spacing_m)
        msg.agent_ids = [int(a) for a in tam.ajan_ids]
        msg.offset_x = [float(o[0]) for o in tam.ofsetler]
        msg.offset_y = [float(o[1]) for o in tam.ofsetler]
        msg.offset_z = [float(o[2]) for o in tam.ofsetler]
        # maks_hiz 0 = "belirtilmedi": alıcı düğümler kendi yerel
        # varsayılanlarını kullanıyor (formation_node:899, maneuver:414).
        # 0.0 yayınlamak o davranışı koruyor.
        msg.max_speed_mps = float(tam.maks_hiz_mps)
        msg.source_module = 'esp32_bridge'
        self._formation_pub.publish(msg)

    def _isle_formasyon(self, source_id: int, payload: bytes) -> None:
        """TIP_FORMASYON -> montaja ekle, tamsa yayınla."""
        veri = pp.formasyon_coz(payload)
        tam = self._formasyon_montaj.baslik_ekle(
            source_id, veri, time.monotonic()
        )
        if tam is None:
            # Devam/offset paketi bekleniyor VEYA başlık geçersizdi
            # (formasyon tipi 0, spacing 0, boş slot). Ayırt edilebilir olsun:
            if not veri.devam_var and veri.formasyon_tipi not in (1, 2, 3, 99):
                self.get_logger().warning(
                    f'agent {source_id}: formasyon tipi '
                    f'{veri.formasyon_tipi} tanınmıyor, tur düşürüldü'
                )
            return
        self._formasyon_alinan += 1
        self._formasyon_yayinla(tam)

    def _isle_formasyon_devam(self, source_id: int, payload: bytes) -> None:
        """TIP_FORMASYON_DEVAM -> slot 4-7 (yalnız 5+ ajanda gelir)."""
        tam = self._formasyon_montaj.devam_ekle(
            source_id, pp.formasyon_devam_coz(payload), time.monotonic()
        )
        if tam is not None:
            self._formasyon_alinan += 1
            self._formasyon_yayinla(tam)

    def _isle_form_ofset(self, source_id: int, payload: bytes) -> None:
        """TIP_FORM_OFSET -> CUSTOM offsetleri (jüri dizilişi)."""
        tam = self._formasyon_montaj.ofset_ekle(
            source_id, pp.form_ofset_coz(payload), time.monotonic()
        )
        if tam is not None:
            self._formasyon_alinan += 1
            self._formasyon_yayinla(tam)

    def _isle_qr_gorev(self, source_id: int, payload: bytes) -> None:
        """TIP_QR_GOREV -> QRMissionData yayını.

        `team_id` mesh'te TAŞINMIYOR (metin, 16 bayta sığmaz — KARAR 7). QR'ı
        okuyan drone yerelde filtrelediği için mesh'e çıkan her QR bizim
        takımımıza ait. Alanı BURADA doldurmak zorunlu: boş bırakılırsa
        mission_fsm_node:336 ve mission1_node:205 gelen her QR'ı reddeder.
        """
        q = pp.qr_gorev_coz(payload)
        msg = QRMissionData()
        msg.stamp = self.get_clock().now().to_msg()
        msg.detector_agent_id = source_id
        msg.qr_id = q.qr_id
        msg.qr_seq = q.qr_seq
        msg.next_qr = q.sonraki_qr
        msg.detected = True
        msg.decoded = q.decoded
        msg.valid = q.valid
        msg.formation_active = q.formasyon_aktif
        msg.maneuver_active = q.manevra_aktif
        msg.altitude_active = q.irtifa_aktif
        msg.detach_active = q.ayrilma_aktif
        msg.complete_mission = q.gorev_bitti
        msg.formation_type = q.formasyon_tipi
        msg.spacing_m = float(q.spacing_m)
        msg.pitch_deg = float(q.pitch_deg)
        msg.roll_deg = float(q.roll_deg)
        msg.yaw_deg = float(q.yaw_deg)
        msg.altitude_agl_m = float(q.irtifa_m)
        msg.wait_s = float(q.bekleme_s)
        msg.target_agent_id = q.ayrilan_ajan
        msg.detach_color = q.ayrilma_renk
        msg.detach_wait_s = float(q.ayrilma_bekleme_s)
        msg.team_id = self._takim_id
        if not self._takim_id:
            self.get_logger().warning(
                'team_id parametresi BOŞ — mission_fsm ve mission1 gelen QR '
                'görevlerini reddeder (msg.team_id != ctx.team_id). '
                'baslat.sh/run_drone.sh üzerinden TAKIM_ID geçilmeli.',
                throttle_duration_sec=30.0,
            )
        self._qr_gorev_alinan += 1
        self._qr_data_pub.publish(msg)

    def _isle_qr_ham(self, source_id: int, payload: bytes) -> None:
        """TIP_QR_HAM -> ayrıştırma hatasının ham metni (SystemEvent olarak).

        Yalnız YKİ'ye iletiliyor (dronların Pi'sine firmware iletmiyor).
        Şartname "QR içeriği ÖRNEKTİR, nihai format sonrasında paylaşılacaktır"
        diyor; şemamız tahmin ve format farklı gelirse yapısal alanlar boş
        kalır. O anda formatı görmenin tek yolu bu.
        """
        h = pp.qr_ham_coz(payload)
        metin = h.dilim.rstrip(b'\x00').decode('utf-8', errors='replace')
        self._mesh_olay_yayinla(
            SystemEvent.SEVERITY_WARNING,
            f'agent {source_id} QR ayrıştırma hatası (kod {h.hata_kodu}) '
            f'parça {h.parca_no + 1}/{h.toplam_parca}: {metin!r}',
        )

    def _on_formation_out(self, msg: FormationCommand) -> None:
        """Formasyon hedefini mesh'e gönderir — YALNIZ LİDER (KARAR 11).

        LOOPBACK: lider kendi paketini codec'ten GERİ GEÇİRİP yerel
        /swarm/public/formation/target'a yayınlıyor. İki sebep:

        1. Zorunlu. Sahada her Pi'nin ROS grafiği ayrı (ROS_LOCALHOST_ONLY=1)
           ve kendi mesh yayınımız dispatch'te filtreleniyor
           (iha_id == agent_id -> return). Yani liderin formation_node'u
           formasyon hedefini BAŞKA HİÇBİR YOLDAN alamaz. Simülasyonda bu
           boşluk görünmüyor: network_proxy tek ROS grafiğinde gönderene de
           geri veriyor.
        2. Doğruluk. Codec int16 desimetre / int8 derece kuantize ediyor.
           Loopback olmadan lider tam hassasiyetli, takipçiler kuantize hedefe
           uçar ve aralarında sistematik kayma olur. Aynı yoldan geçirince
           bütün sürü BİREBİR aynı hedefi görür.
        """
        if not self._lider_miyim():
            self._formasyon_lider_degil += 1
            self.get_logger().debug(
                f'formasyon yayını atlandı: lider={self._lider_id} '
                f'ben={self._agent_id}'
            )
            if self._lider_id == 0:
                self.get_logger().warning(
                    'formasyon hedefi geldi ama LİDER BİLİNMİYOR — seçim '
                    'mesajı hiç görülmedi. consensus_node çalışıyor mu? '
                    'Formasyon mesh e çıkmıyor.',
                    throttle_duration_sec=10.0,
                )
            return

        ajanlar = [int(a) for a in msg.agent_ids]
        if not ajanlar:
            self.get_logger().warning(
                'formasyon hedefi BOŞ agent_ids ile geldi, atlandı',
                throttle_duration_sec=10.0,
            )
            return

        ofsetler = [
            (float(x), float(y), float(z))
            for x, y, z in zip(msg.offset_x, msg.offset_y, msg.offset_z)
        ]
        devam_var, ofset_dilimleri = parcala(
            ajanlar, int(msg.formation_type), ofsetler
        )
        if int(msg.formation_type) == FORMATION_CUSTOM and not ofset_dilimleri:
            self.get_logger().warning(
                'CUSTOM formasyon ama offset YOK — jüri dizilişi taşınamaz, '
                'tur atlandı',
                throttle_duration_sec=10.0,
            )
            return

        payload, uyarilar = pp.formasyon_paketle(
            formasyon_tipi=int(msg.formation_type),
            merkez_kuzey_m=float(msg.center_x),
            merkez_dogu_m=float(msg.center_y),
            merkez_asagi_m=float(msg.center_z),
            heading_deg=float(msg.heading_deg),
            spacing_m=float(msg.spacing_m),
            slot_ajan=ajanlar,
            maks_hiz_mps=float(msg.max_speed_mps),
            kanat_alfa_deg=self._kanat_alfa_deg,
            devam_var=devam_var,
        )
        # Kırpma uyarıları SESSİZ KALMAMALI: kırpılan bir merkez/aralık sürüyü
        # yanlış yere uçurur (KARAR 6). Codec kırpıyor, loglamak bize düşüyor.
        for u in uyarilar:
            self.get_logger().warning(f'formasyon paketleme: {u}',
                                      throttle_duration_sec=5.0)

        self._uart_yaz(pp.TIP_FORMASYON, self._agent_id, payload)
        if devam_var:
            self._uart_yaz(
                pp.TIP_FORMASYON_DEVAM, self._agent_id,
                pp.formasyon_devam_paketle(ajanlar[pp.FORMASYON_SLOT_PAKET:]),
            )
        for slot_bas, dilim in ofset_dilimleri:
            op, ou = pp.form_ofset_paketle(slot_bas, dilim)
            for u in ou:
                self.get_logger().warning(f'formasyon offset: {u}',
                                          throttle_duration_sec=5.0)
            self._uart_yaz(pp.TIP_FORM_OFSET, self._agent_id, op)
        self._formasyon_gonderilen += 1

        # --- LOOPBACK (yukarıdaki docstring'e bkz.) ---
        simdi = time.monotonic()
        tam = self._formasyon_montaj.baslik_ekle(
            self._agent_id, pp.formasyon_coz(payload), simdi
        )
        if devam_var and tam is None:
            tam = self._formasyon_montaj.devam_ekle(
                self._agent_id, ajanlar[pp.FORMASYON_SLOT_PAKET:], simdi
            )
        for slot_bas, dilim in ofset_dilimleri:
            if tam is not None:
                break
            op, _ = pp.form_ofset_paketle(slot_bas, dilim)
            tam = self._formasyon_montaj.ofset_ekle(
                self._agent_id, pp.form_ofset_coz(op), simdi
            )
        if tam is None:
            self.get_logger().warning(
                'LOOPBACK montajı tamamlanmadı — liderin kendi formation_node u '
                'hedefi ALMAYACAK. Paket dilimleme mantığı gözden geçirilmeli.',
                throttle_duration_sec=5.0,
            )
            return
        self._formasyon_yayinla(tam)

    def _on_qr_data_out(self, msg: QRMissionData) -> None:
        """Çözülmüş QR görevini mesh'e gönderir (lider kapısı YOK).

        Şartname: "İHA'lardan en az biri QR kodunu görsel algılama yöntemi ile
        tespit etmeli ve içeriğini çözümlemelidir." Yani QR'ı hangi drone
        okuduysa o yayınlar.

        TAKIM FİLTRESİ BURADA: `team_id` mesh'te taşınmıyor, o yüzden bizim
        takıma ait olmayan QR'ı mesh'e HİÇ ÇIKARMIYORUZ (KARAR 7).
        """
        if self._takim_id and msg.team_id and msg.team_id != self._takim_id:
            self.get_logger().info(
                f'QR takım {msg.team_id} bize ({self._takim_id}) ait değil, '
                f'mesh e çıkarılmadı',
                throttle_duration_sec=10.0,
            )
            return

        payload, uyarilar = pp.qr_gorev_paketle(
            qr_id=int(msg.qr_id), qr_seq=int(msg.qr_seq),
            sonraki_qr=int(msg.next_qr),
            valid=bool(msg.valid), decoded=bool(msg.decoded),
            formasyon_aktif=bool(msg.formation_active),
            manevra_aktif=bool(msg.maneuver_active),
            irtifa_aktif=bool(msg.altitude_active),
            ayrilma_aktif=bool(msg.detach_active),
            gorev_bitti=bool(msg.complete_mission),
            formasyon_tipi=int(msg.formation_type),
            spacing_m=float(msg.spacing_m),
            pitch_deg=float(msg.pitch_deg),
            roll_deg=float(msg.roll_deg),
            yaw_deg=float(msg.yaw_deg),
            irtifa_m=float(msg.altitude_agl_m),
            bekleme_s=float(msg.wait_s),
            ayrilan_ajan=int(msg.target_agent_id),
            ayrilma_renk=int(msg.detach_color),
            ayrilma_bekleme_s=float(msg.detach_wait_s),
        )
        for u in uyarilar:
            self.get_logger().warning(f'QR görev paketleme: {u}',
                                      throttle_duration_sec=5.0)
        self._uart_yaz(pp.TIP_QR_GOREV, self._agent_id, payload)
        self._qr_gorev_gonderilen += 1

        # Ayrıştırma patladıysa ham metnin ilk baytlarını da yolla (KARAR 8).
        # Normal durumda 0 ekstra bayt: YKİ okunabilir metni yapısal
        # alanlardan kendi kuruyor.
        if (not msg.decoded or not msg.valid) and msg.error_message:
            kod = _qr_hata_kodu(str(msg.error_message))
            for p in pp.qr_ham_paketle(kod, str(msg.raw_text)):
                self._uart_yaz(pp.TIP_QR_HAM, self._agent_id, p)
            self.get_logger().warning(
                f'QR ayrıştırılamadı ({msg.error_message}) — ham metnin ilk '
                f'{pp.QR_HAM_DILIM_BOYU * pp.QR_HAM_MAKS_PARCA} baytı '
                f'teşhis için YKİ ye gönderildi'
            )

    def _lider_kaydet(self, lider_id: int) -> None:
        """Bilinen lideri günceller ve değişimi loglar.

        Formasyon yayını buna bağlı (KARAR 11). Lider değişimi sessiz kalmamalı:
        yayının kimden çıktığı değiştiğinde sahada bunu görmek isteriz.
        """
        if lider_id and lider_id != self._lider_id:
            onceki = self._lider_id
            self._lider_id = lider_id
            self.get_logger().info(
                f'lider {onceki} -> {lider_id}'
                + (' (BEN)' if lider_id == self._agent_id else '')
            )

    def _lider_miyim(self) -> bool:
        """Formasyon yayını kapısı (KARAR 11)."""
        return self._lider_id != 0 and self._lider_id == self._agent_id

    def _on_leader_hb_out(self, msg: LeaderHeartbeat) -> None:
        """Lider kalp atışını TIP_LEADER_HB olarak ESP32'ye gönderir."""
        payload = pp.leader_hb_paketle(
            leader_id=msg.leader_id,
            sequence_num=msg.sequence_num,
            election_round=msg.election_round,
            active_agent_count=msg.active_agent_count,
            mission_active=1 if msg.mission_active else 0,
        )
        self._uart_yaz(pp.TIP_LEADER_HB, self._agent_id, payload)
        # Yerel heartbeat'i YALNIZ lider yayınlar; yani bu çağrı geldiyse
        # consensus bu drone'u lider görüyor. Kendi yayınımız mesh'ten geri
        # gelmediği için lideri buradan da öğreniyoruz.
        self._lider_kaydet(int(msg.leader_id))

    def _on_election_out(self, msg: ElectionResult) -> None:
        """ElectionResult'ı TIP_ELECTION olarak ESP32'ye gönderir."""
        payload = pp.election_paketle(
            new_leader_id=msg.new_leader_id,
            election_round=msg.election_round,
            reason=msg.reason,
            triggered_by=msg.triggered_by_agent_id,
            sequence_num=msg.sequence_num,
            confirmed_ids=tuple(msg.confirmed_by_agent_ids),
            # incarnation MESH'TEN GEÇMEK ZORUNDA: eskimiş-mesaj filtresi
            # komşu dronun consensus'unda çalışıyor. Buradan taşımazsak
            # yeniden başlayan liderin seçimleri komşuda sessizce düşer.
            incarnation=msg.incarnation,
        )
        self._uart_yaz(pp.TIP_ELECTION, self._agent_id, payload)
        # Yerel consensus bu drone'u lider seçtiyse mesh'ten geri gelmesini
        # BEKLEMEYELIM: kendi yayınımızı dispatch filtreliyor
        # (iha_id == agent_id -> return), yani mesh yolundan asla öğrenemeyiz.
        self._lider_kaydet(int(msg.new_leader_id))

    # =================================================================
    # KAPANIŞ
    # =================================================================
    def destroy_node(self) -> bool:
        """Thread'i durdurur, seri portu kapatır, son istatistik basar."""
        self.get_logger().info(
            f'Kapanış: alim_ok={self._alim_ok} '
            f'crc_fail={self._crc_fail} '
            f'gonderim_ok={self._gonderim_ok} '
            f'gonderim_drop={self._gonderim_drop}'
        )
        self._calisiyor = False
        if self._okuma_thread.is_alive():
            self._okuma_thread.join(timeout=2.0)
            if self._okuma_thread.is_alive():
                self.get_logger().warning(
                    'UART thread 2 sn içinde durmadı, terk ediliyor'
                )
        with self._ser_lock:
            if self._ser is not None and self._ser.is_open:
                try:
                    self._ser.close()
                except Exception as exc:  # noqa: BLE001
                    self.get_logger().warning(
                        f'Seri port kapatma hatası: {exc}'
                    )
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Esp32BridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
