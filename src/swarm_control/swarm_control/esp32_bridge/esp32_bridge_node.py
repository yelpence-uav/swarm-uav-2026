r"""esp32_bridge.py — ESP32 mesh ↔ ROS2 köprüsü (ana node).

Gerçek donanımda network_proxy'nin yerini alır: komşu drone'lardan
ESP-NOW mesh üzerinden gelip ESP32'nin UART'a yazdığı paketleri çözer,
ROS2 topic'lerine yayınlar. Ters yönde, bu drone'dan çıkması gereken
mesajları (origin, kendi pozisyonu) ESP32'ye UART üzerinden gönderir.

SÜRÜ BOYUTU: Şartname §5/§6.1 en az 3 İHA istiyor; üst sınır
belirtilmemiş. Yelpençe takımı 3 drone (1 lider + 2 follower) ile
yarışacak. Kod 1-254 ID aralığında esnek (test/yedek için).

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

from swarm_interfaces.msg import (
    AgentStatus,
    ElectionResult,
    LeaderHeartbeat,
    SwarmControlCommand,
    SwarmOrigin,
    SystemEvent,
)

from . import packet_parser as pp
from .cobs import cobs_decode, cobs_encode
from .crc16 import crc16

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

# LeaderHeartbeat: RELIABLE + VOLATILE, depth=5 (contract madde 3.1)
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

_FRAME_DELIM = 0x00

# Firmware durum_veri_t.durum -> AgentStatus.state eşleşmesi.
# ORCA/APF, state 7/8/13/14 olan komşuları avoidance hesabından çıkarır
# (INTERFACE_CONTRACT madde 8). Şartname §8.4: çarpışma cezası -20*N.
#
# ŞARTNAME BAĞLAMI: 2026 Sürü İHA Şartnamesi §5.1 (Dinamik Görev) ve
# §5.2 (Yarı Otonom) tüm senaryoları kapsar. AgentStatus enum'ı zaten
# §5.1 madde 15-16-18'i tam destekliyor. Aşağıdaki firmware durum
# kodları Büşra ile koordine edilmek üzere ÖNERİDİR; nihai değerler
# mesh_config.h ile birebir tutulmalıdır.
_DURUM_BILINMIYOR = 0
_DURUM_BOSTA = 1         # yerde, arm değil (§5.1 başlangıç, §5.1 yedek)
_DURUM_KALKIS = 2        # §5.1 m.3 kalkış (TAKEOFF)
_DURUM_SURUDE = 3        # §5.1 m.4 sürüde uçuş (IN_SWARM)
_DURUM_GOREV = 4         # §5.1 m.6-9 formasyon/manevra/irtifa
_DURUM_AYRILDI = 5       # §5.1 m.15 sürüden ayrıldı
_DURUM_HASSAS_INIS = 6   # §5.1 m.15 renkli alana iniyor
_DURUM_KATILMA = 7       # §5.1 m.15 yeniden katılma (kalkış sonrası)
_DURUM_BEKLIYOR = 8      # §5.1 m.15-16 yerde disarm, bekleme süresi
_DURUM_RTL = 9           # §5.4 RTL failsafe / §5.1 m.17 home dönüş
_DURUM_INIS = 10         # §5.1 m.18 home iniş (LANDING)
_DURUM_INDI = 11         # §5.1 m.19 disarm, görev tamam
_DURUM_FAILSAFE = 12     # §5.4 failsafe (kumanda kaybı, vs.)
_DURUM_STANDBY = 13      # §5.1 m.16 yedek ajan (yerde, katılmaya hazır)
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

# Ters yön: AgentStatus.state -> firmware durum kodu.
# DURUM mesh paketi gönderirken agent_fsm'in atadığı state'i
# 14 firmware koduna eşliyoruz. AgentStatus'ın ARMING(2)/ARMED(3)
# state'leri firmware'de ayrı kod taşımıyor → DURUM_KALKIS'a eşlenir
# (kalkış öncesi/sırası birleşik).
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
        self.declare_parameter('baud', 115200)
        self._agent_id = int(self.get_parameter('agent_id').value)
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

        # Mesh sağlık sayaçları (şartname §5.4 failsafe gözlemi için).
        # swarm_fsm, bridge bu sayaçları durdurursa mesh kopuk sanar ve
        # RTL/Land tetikleyebilir.
        self._alim_ok = 0          # COBS+CRC doğrulanmış paket sayısı
        self._crc_fail = 0         # CRC eşleşmemiş paket sayısı
        self._gonderim_ok = 0      # UART'a başarılı yazılan paket sayısı
        self._gonderim_drop = 0    # port kapalı/hata ile düşürülen
        # Mesh'ten gelen KOMUT için bridge-tarafı sequence sayacı;
        # firmware payload'ında seq alanı eklenene kadar 0 yerine monoton
        # değer üretir, downstream dedup yapabilir.
        self._komut_rx_seq = 0
        # Header iha_id ile payload drone_id uyumsuzluk sayacı
        self._id_uyumsuz = 0
        # En son bilinen SwarmOrigin (GPS→NED dönüşümü için gerekli).
        # Origin liderden /swarm/internal/origin'a veya mesh'ten
        # _isle_origin yoluyla gelir; iki yolda da kaydedilir.
        # Beyza inceleme #1: bridge mesh GPS'i NED'e çevirmezse
        # kinematic_fusion ve swarm_fsm pos_x/y/z=0.0 görür.
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

        # Seri okuma thread'i
        self._calisiyor = True
        self._okuma_thread = threading.Thread(
            target=self._seri_oku_dongusu, daemon=True
        )
        self._okuma_thread.start()

        # Mesh sağlık raporu: her 1 sn'de bir SystemEvent ile yayın.
        # Şartname §5.4 failsafe: mesh kopuksa swarm_fsm görür.
        self._diag_timer = self.create_timer(1.0, self._diag_yayinla)

        self.get_logger().info(
            f'Esp32BridgeNode başlatıldı: agent_id={self._agent_id}'
        )

    # =================================================================
    # MESH SAĞLIK RAPORLAMA
    # =================================================================
    def _diag_yayinla(self) -> None:
        """Her saniye mesh diagnostik sayaçlarını SystemEvent yayar.

        Şartname §5.4: GPS/mesh güvenilir olmayabilir, failsafe kritik.
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

        NOT: swarm_interfaces'te EVENT_MESH_LINK_LOST/RESTORED yok.
        EVENT_UNKNOWN ile gönderilir, mesaj string'i ayırt edici.
        TODO: Beyza'nın branch'ine EVENT_MESH_LINK_LOST=60,
        EVENT_MESH_LINK_RESTORED=61 sabitleri eklenebilir.
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
                veri = self._ser.read(64)
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
                    if len(tampon) > 64:  # taşma koruması
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
        self._son_alim_ts = time.monotonic()
        # _cache_lock: bu metod seri okuma thread'inden cagrilir; ayni
        # dict'i _diag_yayinla (ROS timer thread'i) itere eder. Kilitsiz
        # yazma, iterasyon sirasinda "dict changed size" cokmesine yol acar.
        with self._cache_lock:
            self._komsu_son_goruldu[cerceve.iha_id] = self._son_alim_ts

        # Defansif: firmware kendi paketlerini ISR'da filtreler ama
        # bir hata olur da kendi paketimiz geri gelirse komşu yayını
        # yapmayalım (kendi pose'umuz px4_bridge'den geliyor).
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
        elif cerceve.tip == pp.TIP_LEADER_HB:
            self._isle_leader_hb(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_ELECTION:
            self._isle_election(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_RENK:
            self._isle_renk(cerceve.iha_id, cerceve.payload)
        elif cerceve.tip == pp.TIP_GOREV:
            self._isle_gorev(cerceve.iha_id, cerceve.payload)

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

        Beyza inceleme #1, #2, #3: NED + validity + origin_synced
        eskiden hiç set edilmiyordu, hepsi burada düzelir.

        vel_z mesh protokolünde yok (POSE 16 byte dolu). Bu kısıt
        Büşra ile koordine edilecek; şimdilik vel_z=0.0 (v_xy_valid
        sadece yatay hızı kapsar, contract ile uyumlu).
        """
        pose = pp.pose_coz(payload)
        lat_deg = pose.lat / 1e7
        lon_deg = pose.lon / 1e7
        alt_amsl_m = pose.alt_cm / 100.0
        vel_x_ned, vel_y_ned = pose.vx / 100.0, pose.vy / 100.0
        with self._cache_lock:
            status = self._komsu_status_al(drone_id)
            # GPS alanları (her durumda doldur)
            status.lat_deg = lat_deg
            status.lon_deg = lon_deg
            status.alt_amsl_m = alt_amsl_m
            status.heading_deg = pose.heading / 10.0
            status.vel_x = vel_x_ned
            status.vel_y = vel_y_ned
            status.vel_z = 0.0  # mesh protokolünde vz yok (Büşra TODO)
            # GPS→NED dönüşümü ve validity bayrakları
            ned = self._gps_ned_cevir(lat_deg, lon_deg, alt_amsl_m)
            if ned is not None:
                status.pos_x = ned[0]
                status.pos_y = ned[1]
                status.pos_z = ned[2]
                status.origin_synced = True
                status.xy_valid = True
                status.z_valid = True
                status.v_xy_valid = True
                # v_z_valid YOK çünkü vz mesh'te taşınmıyor;
                # AgentStatus.msg'de v_z_valid alanı varsa false kalır
            else:
                # Origin yok → NED hesaplanamaz, downstream skipler
                status.pos_x = 0.0
                status.pos_y = 0.0
                status.pos_z = 0.0
                status.origin_synced = False
                status.xy_valid = False
                status.z_valid = False
                status.v_xy_valid = False
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
        FSM state'ine eşleştirilir. ORCA/APF için kritik: AYRILDI/INDI
        olan komşulara avoidance hesabı yapılmamalı.
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
            # mesh_link_ok ve mesh_komsu_sayisi henüz AgentStatus.msg'ye
            # eklenmedi (Beyza listesinde). Eklenince hasattr otomatik
            # set eder; o zamana kadar status_text üzerinden taşınır.
            if hasattr(status, 'mesh_link_ok'):
                status.mesh_link_ok = bool(durum.mesh_link_ok)
            if hasattr(status, 'mesh_node_count'):
                status.mesh_node_count = int(durum.mesh_komsu_sayisi)
            status.status_text = (
                f'mesh durum={durum.durum} rssi={durum.rssi} '
                f'link={durum.mesh_link_ok} komsu={durum.mesh_komsu_sayisi}'
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
        # NED frame'e çevirebilelim (Beyza inceleme #1).
        self._son_origin = msg
        self._origin_pub.publish(msg)

    def _isle_komut(self, source_id: int, payload: bytes) -> None:
        """TIP_KOMUT -> /swarm/public/control/command'a SwarmControlCommand.

        Joystick float32 değerleri int16*100 ile taşındığı için 100'e
        bölünerek geri çevrilir. deadman_pressed mesh'te bayrak biti
        olarak taşınır; aksi halde downstream motion'u sessizce reddeder.
        sequence_num bridge tarafında üretilir (firmware payload'da
        sequence yok henüz; Büşra ile koordine edilecek).
        """
        k = pp.komut_coz(payload)
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
        msg.formation_change_requested = bool(
            k.flags & pp.KOMUT_FLAG_FORMATION_CHANGE
        )
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
        # 0 dolgu ID'lerini at — gerçekte onay verenler bunlar
        msg.confirmed_by_agent_ids = [
            i for i in e.confirmed_ids if i != 0
        ]
        self._election_pub.publish(msg)

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

    # =================================================================
    # ROS2 -> MESH İŞLEYİCİLERİ (UART'a yaz)
    # =================================================================
    def _uart_yaz(self, tip: int, iha_id: int, payload: bytes) -> None:
        """Bir paketi çerçeveleyip (CRC+COBS) seri porta yazar.

        Args:
            tip (int): Paket tipi (TIP_*).
            iha_id (int): Kaynak drone kimliği.
            payload (bytes): 16 baytlık payload.
        """
        if len(payload) != 16:
            self.get_logger().warning('UART payload 16 byte değil, atlandı')
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
            payload = pp.pose_paketle(
                lat=int(msg.lat_deg * 1e7),
                lon=int(msg.lon_deg * 1e7),
                alt_cm=int(msg.alt_amsl_m * 100.0),
                heading=int(msg.heading_deg * 10.0),
                vx=int(msg.vel_x * 100.0),
                vy=int(msg.vel_y * 100.0),
            )
            self._uart_yaz(pp.TIP_POSE, self._agent_id, payload)

        # --- DURUM 1Hz ---
        # Şartname §5.1 m.15 ayrılma akışı için kritik: komşular bizim
        # state'imizi bilmeli. ORCA da DETACHED/LANDED komşulara
        # avoidance hesaplamaz (şartname §8.4 -20*N).
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
        paketleri NED'e çevrilebilsin (Beyza inceleme #1).
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

        payload = pp.komut_paketle(
            alt_tip=msg.mode,
            flags=flags,
            roll_x100=_kirp_int16(msg.roll_cmd * 100.0),
            pitch_x100=_kirp_int16(msg.pitch_cmd * 100.0),
            yaw_x100=_kirp_int16(msg.yaw_cmd * 100.0),
            throttle_x100=_kirp_int16(msg.throttle_cmd * 100.0),
        )
        self._uart_yaz(pp.TIP_KOMUT, self._agent_id, payload)

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

    def _on_election_out(self, msg: ElectionResult) -> None:
        """ElectionResult'ı TIP_ELECTION olarak ESP32'ye gönderir."""
        payload = pp.election_paketle(
            new_leader_id=msg.new_leader_id,
            election_round=msg.election_round,
            reason=msg.reason,
            triggered_by=msg.triggered_by_agent_id,
            sequence_num=msg.sequence_num,
            confirmed_ids=tuple(msg.confirmed_by_agent_ids),
        )
        self._uart_yaz(pp.TIP_ELECTION, self._agent_id, payload)

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
