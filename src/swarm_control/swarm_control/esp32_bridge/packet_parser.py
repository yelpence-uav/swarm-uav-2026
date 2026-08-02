"""packet_parser.py — ESP32 UART paketlerini çözümleme.

UART çerçevesi (COBS çözüldükten sonra):
    [tip 1B][iha_id 1B][payload 16B][crc_hi 1B][crc_lo 1B]  = 20 byte
CRC16-CCITT ilk 18 bayt (tip + iha_id + payload) üzerinden hesaplanır.
CRC big-endian gönderilir: crc_hi = (crc >> 8), crc_lo = (crc & 0xFF).

payload struct'ları firmware'deki mesh_config.h ile BİREBİR aynıdır
(little-endian, packed). Bir alan değişirse iki taraf birlikte
güncellenmelidir.
"""

from dataclasses import dataclass
import struct

from .crc16 import crc16

# ===== Paket tipleri (firmware mesh_config.h ile aynı) =====
TIP_KOMUT = 0x02
TIP_POSE = 0x04
TIP_GOREV = 0x05
TIP_RENK = 0x06
TIP_DURUM = 0x07
TIP_ORIGIN = 0x08
TIP_LEADER_HB = 0x09
TIP_ELECTION = 0x0A
TIP_HEARTBEAT = 0x03
TIP_VERSION = 0x0B
TIP_RTK = 0x0C
TIP_SWARM_STATE = 0x0D
TIP_QR_DATA = 0x0E
TIP_FAILSAFE = 0xFA  # mesh kopunca gelen failsafe (fail_safe.h)
TIP_QR_COORDS = 0x0F  # YKİ'den gelen QR konumları (her nokta ayrı çerçeve)
TIP_GOTO = 0x10  # YKİ'den gelen guided tekil nokta-git (goto_veri_t)

# Failsafe türleri (fail_safe.h)
FAILSAFE_TIP_UYARI = 0x01
FAILSAFE_TIP_RTL = 0x02
FAILSAFE_TIP_LAND = 0x03

# Mesh kimlik sabitleri (mesh_config.h)
BAZ_ID = 99          # RTK UART sentinel'i, mesh kimliği DEĞİL
BAZ_MESH_ID = 10     # baz istasyonu mesh kimliği
MESH_MAX_NODES = 8

# ===== Payload struct formatları (little-endian, packed) =====
# POSE 18B (vz), diğer tipler 16B.
_POSE_FMT = '<iihhhhh'       # lat, lon, alt_dm, heading, vx, vy, vz
# REV C: firmware mesh_config.h::durum_veri_t ile BİREBİR.
# 16 bayt sabit; float voltaj ve altı ayrı bool bayt sıkıştırılarak
# kill switch / RC link / uçuş modu / uydu / HDOP'a yer açıldı.
_DURUM_FMT = '<BBBBBBBBBbBB4x'  # bkz. DurumVeri alanları

# durum_veri_t.bayraklar bit maskeleri (firmware DURUM_BAYRAK_* ile aynı).
DURUM_BAYRAK_ARMED = 0x01
DURUM_BAYRAK_EKF_OK = 0x02
DURUM_BAYRAK_IMU_OK = 0x04
DURUM_BAYRAK_MAG_OK = 0x08
DURUM_BAYRAK_BARO_OK = 0x10
DURUM_BAYRAK_MESH_LINK = 0x20
DURUM_BAYRAK_KILL = 0x40
DURUM_BAYRAK_RC_LINK = 0x80

# İkinci bayrak baytı (bayraklar2) — ilk bayt 8 bitle doldu.
DURUM2_BAYRAK_READY_TO_ARM = 0x01
_RENK_FMT = '<Bii7x'         # renk, lat, lon, rezerv[7]
_GOREV_FMT = '<BBbB12x'      # tip, param1, param2, bekleme, rezerv[12]
_ORIGIN_FMT = '<iiiI'        # lat_1e7, lon_1e7, alt_mm, sequence
# target_id (offset 10, rezerv[0]): guided komutun HEDEF drone'u. Mesh çerçevesi
# id taşımaz (base düşürür, drone MAC'ten kaynak id üretir), o yüzden hedef
# payload'da gider. Firmware bunu opak rezerv görür — flash gerekmez.
_KOMUT_FMT = '<BBhhhhB5x'    # alt_tip, flags, roll/pitch/yaw/throttle x100, target_id
_LEADER_HB_FMT = '<BIBBB8x'  # leader_id, seq, round, agent_count, mission
_ELECTION_FMT = '<BBBBIBBBB4x'  # leader, round, reason, trigger, seq, ids
_QR_FMT = '<BIii3x'          # drone_id, action_id, lat, lon, rezerv[3]
_SWARM_STATE_FMT = '<BBBBI8x'  # mission_id, fsm, leader, formation, timestamp
_QR_COORD_FMT = '<BBii6x'    # qr_id, toplam, lat_1e7, lon_1e7, rezerv[6]
_GOTO_FMT = '<hhhhBB6x'      # kuzey_dm, dogu_dm, asagi_dm, yaw_ddeg, bayrak, target_id

# Joystick komutu bayrak bitleri (komut_veri_t.flags için).
# DEADMAN_PRESSED: SwarmControlCommand.deadman_pressed mesh üzerinden
# taşınması için. False ise downstream motion uygulamaz (msg dosyası
# kuralı). Bayrak biti olmadığında her komut sessizce reddedilir.
KOMUT_FLAG_TAKEOFF = 0x01
KOMUT_FLAG_LAND = 0x02
KOMUT_FLAG_RTL = 0x04
KOMUT_FLAG_EMERGENCY = 0x08
KOMUT_FLAG_FORMATION_CHANGE = 0x10
KOMUT_FLAG_DEADMAN_PRESSED = 0x20
# Guided (YKİ tekil komut) ek bayrakları — takeoff/land/rtl yukarıdakiyle ortak.
KOMUT_FLAG_ARM = 0x40
KOMUT_FLAG_DISARM = 0x80

# SwarmControlCommand.mode değerleri
KOMUT_MODE_SWARM_MOVEMENT = 1
KOMUT_MODE_MANEUVER = 2
KOMUT_MODE_GUIDED = 3  # YKİ tekil guided komut; drone FSM'i baypas edip px4_bridge'e çevirir

# goto_veri_t.bayraklar bit maskeleri (firmware GOTO_BAYRAK_* ile aynı).
GOTO_BAYRAK_YAW_GECERLI = 0x01

_FRAME_MIN = 4  # tip + iha_id + crc16 (payload değişken)

# F3: mesh-liveness yalnızca bilinen peer'dan bilinen telemetri tipiyle
# tazelenir. RTK (0x0C) ve VERSION dışarıda; RTK ayrı izlenir.
_LIVENESS_TIPLERI = frozenset({
    TIP_KOMUT, TIP_POSE, TIP_GOREV, TIP_RENK, TIP_DURUM, TIP_ORIGIN,
    TIP_LEADER_HB, TIP_ELECTION, TIP_HEARTBEAT, TIP_SWARM_STATE, TIP_QR_DATA,
    TIP_GOTO,
})


def liveness_tazeler(iha_id: int, tip: int) -> bool:
    """Bu (iha_id, tip) mesh-liveness zaman damgasını tazelemeli mi (F3).

    Bilinen peer (1..MESH_MAX_NODES veya BAZ_MESH_ID) VE bilinen telemetri
    tipi gerekir. RTK sentinel'i (99) ve bilinmeyen tipler tazelemez.
    """
    peer_ok = 1 <= iha_id <= MESH_MAX_NODES or iha_id == BAZ_MESH_ID
    return peer_ok and tip in _LIVENESS_TIPLERI


@dataclass
class PoseVeri:
    """TIP_POSE payload — komşu drone'un konum/hız verisi."""

    lat: int       # 1e-7 derece
    lon: int       # 1e-7 derece
    alt_dm: int    # desimetre
    heading: int   # 0.1 derece
    vx: int        # cm/s
    vy: int        # cm/s
    vz: int        # cm/s


@dataclass
class DurumVeri:
    """TIP_DURUM payload — komşu drone'un durum/sağlık verisi.

    Firmware'in durum kodu 14 değerli enum'dur (AgentStatus.STATE_*
    ile eşleşir). Bkz. esp32_bridge_node._DURUM_STATE_MAP.
    """

    drone_id: int
    durum: int              # 0=BILINMIYOR..13=STANDBY (14 değerli enum)
    bayraklar: int          # DURUM_BAYRAK_* bit alanı
    ucus_modu: int          # AgentStatus.FLIGHT_MODE_* (PX4'ün bildirdiği)
    gps_fix_type: int       # 0-6 (4=DGPS, 5=RTK float, 6=RTK fixed)
    gps_uydu: int           # görünen uydu sayısı
    gps_hdop_x10: int       # HDOP*10, 255 = bilinmiyor
    battery_pct: int        # 0-100
    battery_volt_x10: int   # volt*10
    rssi: int               # dBm
    mesh_komsu_sayisi: int  # aktif mesh node sayısı
    bayraklar2: int         # DURUM2_BAYRAK_* bit alanı

    # --- bit alanı okuyucuları: çağıran taraf maskeyle uğraşmasın ---
    @property
    def armed(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_ARMED)

    @property
    def ekf_ok(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_EKF_OK)

    @property
    def imu_ok(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_IMU_OK)

    @property
    def mag_ok(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_MAG_OK)

    @property
    def baro_ok(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_BARO_OK)

    @property
    def mesh_link_ok(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_MESH_LINK)

    @property
    def kill_switch_active(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_KILL)

    @property
    def rc_link_ok(self) -> bool:
        return bool(self.bayraklar & DURUM_BAYRAK_RC_LINK)

    @property
    def ready_to_arm(self) -> bool:
        """PX4 PREARM_CHECK: emniyet anahtarı dahil tüm ön-kontroller geçti mi."""
        return bool(self.bayraklar2 & DURUM2_BAYRAK_READY_TO_ARM)

    @property
    def battery_volt(self) -> float:
        """Voltaj, 0.1 V çözünürlükte."""
        return self.battery_volt_x10 / 10.0

    @property
    def gps_hdop(self) -> float:
        """HDOP; 255 sentineli 99.9 (kötü) olarak döner."""
        return 99.9 if self.gps_hdop_x10 == 255 else self.gps_hdop_x10 / 10.0


@dataclass
class RenkVeri:
    """TIP_RENK payload — tespit edilen renk bölgesi koordinatı."""

    renk: int      # RENK_KIRMIZI=1, RENK_MAVI=2
    lat: int       # 1e-7 derece
    lon: int       # 1e-7 derece


@dataclass
class GorevVeri:
    """TIP_GOREV payload — sürüye gelen görev komutu."""

    tip: int
    param1: int
    param2: int
    bekleme_suresi_s: int


@dataclass
class OriginVeri:
    """TIP_ORIGIN payload — paylaşılan NED origin (SwarmOrigin).

    NOT: firmware tarafında origin 16 bayta sığdırılmıştır. Float64
    lat/lon mesh'e sığmadığı için 1e-7 derece tamsayı kullanılır.
    """

    lat_1e7: int   # 1e-7 derece
    lon_1e7: int   # 1e-7 derece
    alt_mm: int    # milimetre
    sequence: int


@dataclass
class KomutVeri:
    """TIP_KOMUT payload — joystick / yarı otonom sürü komutu.

    SwarmControlCommand'ın 16 bayta sığdırılmış mesh karşılığıdır.
    Float32 komutlar int16 * 100 (×0.01 ölçek) ile taşınır.
    """

    alt_tip: int        # MODE_SWARM_MOVEMENT=1 / MODE_MANEUVER=2 / MODE_GUIDED=3
    flags: int          # bit alanı, KOMUT_FLAG_* bitleri
    roll_x100: int      # roll_cmd * 100  ([-32767, 32767])
    pitch_x100: int
    yaw_x100: int
    throttle_x100: int
    target_id: int = 0  # guided hedef drone (0 = tümü). Joystick modunda kullanılmaz.


@dataclass
class GotoVeri:
    """TIP_GOTO payload — YKİ'den gelen guided tekil nokta-git komutu.

    Hedef, paylaşılan SwarmOrigin'e göre NED (desimetre) taşınır. Yön (yaw)
    yalnızca GOTO_BAYRAK_YAW_GECERLI set ise geçerlidir.
    """

    kuzey_dm: int       # NED kuzey, desimetre
    dogu_dm: int        # NED doğu, desimetre
    asagi_dm: int       # NED aşağı, desimetre (pozitif = aşağı; irtifa = -asagi_dm)
    yaw_ddeg: int       # hedef yaw, desi-derece (0.1°)
    bayraklar: int      # GOTO_BAYRAK_* bitleri
    target_id: int = 0  # hedef drone (0 = tümü). Mesh id taşımadığı için payload'da.

    @property
    def kuzey_m(self) -> float:
        return self.kuzey_dm / 10.0

    @property
    def dogu_m(self) -> float:
        return self.dogu_dm / 10.0

    @property
    def asagi_m(self) -> float:
        return self.asagi_dm / 10.0

    @property
    def yaw_deg(self) -> float:
        return self.yaw_ddeg / 10.0

    @property
    def yaw_gecerli(self) -> bool:
        return bool(self.bayraklar & GOTO_BAYRAK_YAW_GECERLI)


@dataclass
class LeaderHbVeri:
    """TIP_LEADER_HB payload — aktif liderin consensus heartbeat'i."""

    leader_id: int
    sequence_num: int       # her yayında +1
    election_round: int     # mevcut election turu
    active_agent_count: int  # liderin gördüğü aktif ajan sayısı
    mission_active: int      # 0/1


@dataclass
class ElectionVeri:
    """TIP_ELECTION payload — yeni lider seçim sonucu."""

    new_leader_id: int
    election_round: int
    reason: int              # REASON_* (1=TIMEOUT, 2=FAULT, 3=MANUAL)
    triggered_by: int        # election'ı başlatan ajan, 0=sistem
    sequence_num: int
    confirmed_ids: tuple[int, int, int, int]  # max 4 ajan, 0 = boş


@dataclass
class QrVeri:
    """TIP_QR_DATA payload — komşunun çözümlediği QR."""

    drone_id: int
    action_id: int   # çözümlenen QR eylemi
    lat: int         # 1e-7 derece
    lon: int         # 1e-7 derece


@dataclass
class SwarmStateVeri:
    """TIP_SWARM_STATE payload — sürü seviyesi FSM görünümü."""

    mission_id: int
    swarm_fsm_state: int
    active_leader: int
    formation: int
    timestamp: int


@dataclass
class QrKoordVeri:
    """TIP_QR_COORDS payload — YKİ'den gelen tek QR konumu."""

    qr_id: int
    toplam: int      # tablodaki toplam QR sayısı
    lat: int         # 1e-7 derece
    lon: int         # 1e-7 derece


@dataclass
class Cerceve:
    """COBS+CRC doğrulanmış UART çerçevesi."""

    tip: int
    iha_id: int
    payload: bytes  # değişken uzunluk


def cerceve_coz(decoded: bytes) -> Cerceve | None:
    """COBS çözülmüş baytları doğrular ve çerçeveye ayırır.

    Args:
        decoded (bytes): COBS çözülmüş ham çerçeve (>= 20 byte).

    Returns:
        Cerceve: CRC doğru ise tip/iha_id/payload içeren çerçeve.
        None: Uzunluk yetersiz veya CRC uyuşmuyorsa.
    """
    if len(decoded) < _FRAME_MIN:
        return None

    govde = decoded[:-2]  # tip + iha_id + payload (CRC hariç)
    crc_gelen = (decoded[-2] << 8) | decoded[-1]
    if crc16(govde) != crc_gelen:
        return None

    return Cerceve(tip=decoded[0], iha_id=decoded[1], payload=govde[2:])


def pose_coz(payload: bytes) -> PoseVeri:
    """TIP_POSE payload'ını PoseVeri'ye çözer."""
    lat, lon, alt_dm, heading, vx, vy, vz = struct.unpack(_POSE_FMT, payload)
    return PoseVeri(lat, lon, alt_dm, heading, vx, vy, vz)


def durum_coz(payload: bytes) -> DurumVeri:
    """TIP_DURUM payload'ını DurumVeri'ye çözer (REV C, 16 bayt)."""
    alanlar = struct.unpack(_DURUM_FMT, payload)
    return DurumVeri(
        drone_id=alanlar[0],
        durum=alanlar[1],
        bayraklar=alanlar[2],
        ucus_modu=alanlar[3],
        gps_fix_type=alanlar[4],
        gps_uydu=alanlar[5],
        gps_hdop_x10=alanlar[6],
        battery_pct=alanlar[7],
        battery_volt_x10=alanlar[8],
        rssi=alanlar[9],
        mesh_komsu_sayisi=alanlar[10],
        bayraklar2=alanlar[11],
    )


def durum_paketle(drone_id: int, durum: int, armed: int,
                  gps_fix_type: int, battery_pct: int,
                  battery_volt: float, ekf_ok: int, imu_ok: int,
                  mag_ok: int, baro_ok: int, rssi: int,
                  mesh_link_ok: int,
                  mesh_komsu_sayisi: int = 0,
                  ucus_modu: int = 0,
                  gps_uydu: int = 0,
                  gps_hdop: float = 99.9,
                  kill_switch_active: int = 0,
                  rc_link_ok: int = 0,
                  ready_to_arm: int = 0) -> bytes:
    """Durum verisi alanlarını 16 baytlık mesh payload'ına paketler (REV C).

    RPi kendi durumunu (agent_fsm çıktısı) ESP32'ye gönderirken kullanır.

    Bool alanlar tek bayta paketlenir; çağıran taraf yine 0/1 verir, bit
    işini bu fonksiyon yapar. Böylece çağrı yerleri REV B ile aynı kalır ve
    yeni alanlar isteğe bağlı parametre olarak eklenir.

    Args:
        drone_id (int): Kendi ID.
        durum (int): _DURUM_* enum kodu (firmware ile aynı).
        armed (int): 0/1.
        gps_fix_type (int): 0-6 (4=DGPS, 5=RTK float, 6=RTK fixed).
        battery_pct (int): 0-100.
        battery_volt (float): Paket voltajı; 0.1 V çözünürlükte taşınır.
        ekf_ok, imu_ok, mag_ok, baro_ok (int): 0/1 sağlık bayrakları.
        rssi (int): dBm, -128..127.
        mesh_link_ok (int): 0/1.
        mesh_komsu_sayisi (int): aktif mesh node sayısı.
        ucus_modu (int): AgentStatus.FLIGHT_MODE_* — PX4'ün BİLDİRDİĞİ mod.
        gps_uydu (int): görünen uydu sayısı.
        gps_hdop (float): HDOP; bilinmiyorsa 99.9 → 255 sentineli gider.
        kill_switch_active (int): 0/1 — RC kill switch aktif mi.
        rc_link_ok (int): 0/1 — kumanda bağlantısı var mı.

    Returns:
        bytes: 16 baytlık payload.
    """
    bayraklar = 0
    if armed:
        bayraklar |= DURUM_BAYRAK_ARMED
    if ekf_ok:
        bayraklar |= DURUM_BAYRAK_EKF_OK
    if imu_ok:
        bayraklar |= DURUM_BAYRAK_IMU_OK
    if mag_ok:
        bayraklar |= DURUM_BAYRAK_MAG_OK
    if baro_ok:
        bayraklar |= DURUM_BAYRAK_BARO_OK
    if mesh_link_ok:
        bayraklar |= DURUM_BAYRAK_MESH_LINK
    if kill_switch_active:
        bayraklar |= DURUM_BAYRAK_KILL
    if rc_link_ok:
        bayraklar |= DURUM_BAYRAK_RC_LINK

    bayraklar2 = DURUM2_BAYRAK_READY_TO_ARM if ready_to_arm else 0

    # 255 = "bilinmiyor/kötü" sentineli. 25.4'ten büyük HDOP zaten kullanılamaz
    # kalitededir, sentinele kırpmak bilgi kaybetmez.
    hdop_x10 = 255 if gps_hdop >= 25.5 else max(0, int(round(gps_hdop * 10)))
    volt_x10 = max(0, min(255, int(round(battery_volt * 10))))

    return struct.pack(
        _DURUM_FMT,
        drone_id, durum, bayraklar, ucus_modu, gps_fix_type,
        min(255, gps_uydu), hdop_x10, battery_pct, volt_x10,
        rssi, mesh_komsu_sayisi, bayraklar2,
    )


def renk_coz(payload: bytes) -> RenkVeri:
    """TIP_RENK payload'ını RenkVeri'ye çözer."""
    renk, lat, lon = struct.unpack(_RENK_FMT, payload)
    return RenkVeri(renk, lat, lon)


def renk_paketle(renk: int, lat: int, lon: int) -> bytes:
    """Renk bölgesi tespitini 16 baytlık mesh payload'a paketler.

    Args:
        renk (int): 1=KIRMIZI, 2=MAVI.
        lat (int): Enlem, 1e-7 derece.
        lon (int): Boylam, 1e-7 derece.

    Returns:
        bytes: 16 baytlık payload.
    """
    return struct.pack(_RENK_FMT, renk, lat, lon)


def gorev_coz(payload: bytes) -> GorevVeri:
    """TIP_GOREV payload'ını GorevVeri'ye çözer."""
    tip, param1, param2, bekleme = struct.unpack(_GOREV_FMT, payload)
    return GorevVeri(tip, param1, param2, bekleme)


def gorev_paketle(tip: int, param1: int, param2: int,
                  bekleme_suresi_s: int) -> bytes:
    """Sürü görev komutunu 16 baytlık mesh payload'a paketler.

    Args:
        tip (int): Görev tipi (formasyon/irtifa/manevra alt-tipi).
        param1 (int): 0-255 birinci parametre.
        param2 (int): -128..127 ikinci parametre.
        bekleme_suresi_s (int): 0-255 saniye bekleme süresi.

    Returns:
        bytes: 16 baytlık payload.
    """
    return struct.pack(_GOREV_FMT, tip, param1, param2, bekleme_suresi_s)


def origin_coz(payload: bytes) -> OriginVeri:
    """TIP_ORIGIN payload'ını OriginVeri'ye çözer."""
    lat, lon, alt_mm, seq = struct.unpack(_ORIGIN_FMT, payload)
    return OriginVeri(lat, lon, alt_mm, seq)


def origin_paketle(lat_1e7: int, lon_1e7: int, alt_mm: int,
                   sequence: int) -> bytes:
    """Origin verisi alanlarını 16 baytlık mesh payload'ına paketler.

    Args:
        lat_1e7 (int): Enlem, 1e-7 derece.
        lon_1e7 (int): Boylam, 1e-7 derece.
        alt_mm (int): Yükseklik, milimetre.
        sequence (int): Origin sıra numarası.

    Returns:
        bytes: 16 baytlık payload.
    """
    return struct.pack(_ORIGIN_FMT, lat_1e7, lon_1e7, alt_mm, sequence)


def pose_paketle(lat: int, lon: int, alt_dm: int, heading: int,
                 vx: int, vy: int, vz: int) -> bytes:
    """Pose verisi alanlarını 18 baytlık mesh payload'ına paketler.

    int16 alanlar ±327.67 aralığına kırpılır (sensör glitch koruması).

    Returns:
        bytes: 18 baytlık payload.
    """
    def _kirp(v: int) -> int:
        return max(-32768, min(32767, int(v)))
    return struct.pack(
        _POSE_FMT, int(lat), int(lon),
        _kirp(alt_dm), _kirp(heading), _kirp(vx), _kirp(vy), _kirp(vz),
    )


def komut_coz(payload: bytes) -> KomutVeri:
    """TIP_KOMUT payload'ını KomutVeri'ye çözer."""
    alt_tip, flags, roll, pitch, yaw, throttle, target_id = struct.unpack(
        _KOMUT_FMT, payload
    )
    return KomutVeri(alt_tip, flags, roll, pitch, yaw, throttle, target_id)


def komut_paketle(alt_tip: int, flags: int, roll_x100: int,
                  pitch_x100: int, yaw_x100: int,
                  throttle_x100: int, target_id: int = 0) -> bytes:
    """Joystick komutunu 16 baytlık mesh payload'ına paketler.

    Args:
        alt_tip (int): Mod (1=SWARM_MOVEMENT, 2=MANEUVER).
        flags (int): KOMUT_FLAG_* bitleri.
        roll_x100 (int): roll_cmd * 100 (float -> int16 ölçek).
        pitch_x100 (int): pitch_cmd * 100.
        yaw_x100 (int): yaw_cmd * 100.
        throttle_x100 (int): throttle_cmd * 100.

    Returns:
        bytes: 16 baytlık payload.
    """
    return struct.pack(
        _KOMUT_FMT, alt_tip, flags,
        roll_x100, pitch_x100, yaw_x100, throttle_x100, target_id,
    )


def goto_coz(payload: bytes) -> GotoVeri:
    """TIP_GOTO payload'ını GotoVeri'ye çözer."""
    kuzey, dogu, asagi, yaw, bayraklar, target_id = struct.unpack(_GOTO_FMT, payload)
    return GotoVeri(kuzey, dogu, asagi, yaw, bayraklar, target_id)


def goto_paketle(kuzey_dm: int, dogu_dm: int, asagi_dm: int,
                 yaw_ddeg: int = 0, bayraklar: int = 0,
                 target_id: int = 0) -> bytes:
    """Guided nokta-git hedefini 16 baytlık mesh payload'ına paketler.

    Args:
        kuzey_dm (int): NED kuzey, desimetre (int16).
        dogu_dm (int): NED doğu, desimetre (int16).
        asagi_dm (int): NED aşağı, desimetre (int16; irtifa = -asagi_dm).
        yaw_ddeg (int): Hedef yaw, desi-derece (0.1°). bayrak yoksa yok sayılır.
        bayraklar (int): GOTO_BAYRAK_* bitleri.

    Returns:
        bytes: 16 baytlık payload.
    """
    return struct.pack(
        _GOTO_FMT, kuzey_dm, dogu_dm, asagi_dm, yaw_ddeg, bayraklar, target_id,
    )


def leader_hb_coz(payload: bytes) -> LeaderHbVeri:
    """TIP_LEADER_HB payload'ını LeaderHbVeri'ye çözer."""
    leader_id, seq, election_round, agent_count, mission = struct.unpack(
        _LEADER_HB_FMT, payload
    )
    return LeaderHbVeri(leader_id, seq, election_round, agent_count, mission)


def leader_hb_paketle(leader_id: int, sequence_num: int,
                      election_round: int, active_agent_count: int,
                      mission_active: int) -> bytes:
    """Lider kalp atışı alanlarını 16 baytlık payload'a paketler.

    Returns:
        bytes: 16 baytlık payload.
    """
    return struct.pack(
        _LEADER_HB_FMT,
        leader_id, sequence_num, election_round,
        active_agent_count, mission_active,
    )


def election_coz(payload: bytes) -> ElectionVeri:
    """TIP_ELECTION payload'ını ElectionVeri'ye çözer."""
    (leader, election_round, reason, triggered_by, seq,
     id0, id1, id2, id3) = struct.unpack(_ELECTION_FMT, payload)
    return ElectionVeri(
        new_leader_id=leader,
        election_round=election_round,
        reason=reason,
        triggered_by=triggered_by,
        sequence_num=seq,
        confirmed_ids=(id0, id1, id2, id3),
    )


def election_paketle(new_leader_id: int, election_round: int,
                     reason: int, triggered_by: int,
                     sequence_num: int,
                     confirmed_ids: tuple) -> bytes:
    """Seçim sonucu alanlarını 16 baytlık payload'a paketler.

    Args:
        confirmed_ids (tuple): Onay veren ajan ID'leri. 4'ten kısaysa 0
            ile doldurulur, 4'ten uzunsa kırpılır.

    Returns:
        bytes: 16 baytlık payload.
    """
    ids = list(confirmed_ids[:4]) + [0] * (4 - len(confirmed_ids[:4]))
    return struct.pack(
        _ELECTION_FMT,
        new_leader_id, election_round, reason, triggered_by,
        sequence_num, ids[0], ids[1], ids[2], ids[3],
    )


def qr_coz(payload: bytes) -> QrVeri:
    """TIP_QR_DATA payload'ını QrVeri'ye çözer."""
    drone_id, action_id, lat, lon = struct.unpack(_QR_FMT, payload)
    return QrVeri(drone_id, action_id, lat, lon)


def swarm_state_coz(payload: bytes) -> SwarmStateVeri:
    """TIP_SWARM_STATE payload'ını SwarmStateVeri'ye çözer."""
    mission_id, fsm, leader, formation, ts = struct.unpack(
        _SWARM_STATE_FMT, payload
    )
    return SwarmStateVeri(mission_id, fsm, leader, formation, ts)


def qr_koord_coz(payload: bytes) -> QrKoordVeri:
    """TIP_QR_COORDS payload'ını QrKoordVeri'ye çözer."""
    qr_id, toplam, lat, lon = struct.unpack(_QR_COORD_FMT, payload)
    return QrKoordVeri(qr_id, toplam, lat, lon)
