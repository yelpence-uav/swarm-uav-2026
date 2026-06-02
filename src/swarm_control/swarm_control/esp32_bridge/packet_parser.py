"""packet_parser.py — ESP32 UART paketlerini çözümleme.

UART çerçevesi (COBS çözüldükten sonra):
    [tip 1B][iha_id 1B][payload 16B][crc_hi 1B][crc_lo 1B]  = 20 byte
CRC16-CCITT ilk 18 bayt (tip + iha_id + payload) üzerinden hesaplanır.
CRC big-endian gönderilir: crc_hi = (crc >> 8), crc_lo = (crc & 0xFF).

payload struct'ları firmware'deki mesh_config.h ile BİREBİR aynıdır
(little-endian, packed). Bir alan değişirse iki taraf birlikte
güncellenmelidir.
"""

import struct
from dataclasses import dataclass

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

# ===== Payload struct formatları (little-endian, packed, 16 byte) =====
_POSE_FMT = '<iihhhh'        # lat, lon, alt_cm, heading, vx, vy
_DURUM_FMT = '<BBBBBfBBBBbBB'  # bkz. DurumVeri alanları
_RENK_FMT = '<Bii7x'         # renk, lat, lon, rezerv[7]
_GOREV_FMT = '<BBbB12x'      # tip, param1, param2, bekleme, rezerv[12]
_ORIGIN_FMT = '<iiiI'        # lat_1e7, lon_1e7, alt_mm, sequence
_KOMUT_FMT = '<BBhhhh6x'     # alt_tip, flags, roll/pitch/yaw/throttle x100
_LEADER_HB_FMT = '<BIBBB8x'  # leader_id, seq, round, agent_count, mission
_ELECTION_FMT = '<BBBBIBBBB4x'  # leader, round, reason, trigger, seq, ids

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

# SwarmControlCommand.mode değerleri
KOMUT_MODE_SWARM_MOVEMENT = 1
KOMUT_MODE_MANEUVER = 2

_FRAME_MIN = 20  # 1 + 1 + 16 + 2


@dataclass
class PoseVeri:
    """TIP_POSE payload — komşu drone'un konum/hız verisi."""

    lat: int       # 1e-7 derece
    lon: int       # 1e-7 derece
    alt_cm: int    # santimetre
    heading: int   # 0.1 derece
    vx: int        # cm/s
    vy: int        # cm/s


@dataclass
class DurumVeri:
    """TIP_DURUM payload — komşu drone'un durum/sağlık verisi.

    Firmware'in durum kodu 14 değerli enum'dur (AgentStatus.STATE_*
    ile eşleşir). Bkz. esp32_bridge_node._DURUM_STATE_MAP. Şartname
    §5.1 m.15 ayrılma akışı 14 state üzerinden işler.
    """

    drone_id: int
    durum: int          # 0=BILINMIYOR..13=STANDBY (14 değerli enum)
    armed: int          # 0/1
    gps_fix_type: int   # 0-6
    battery_pct: int    # 0-100
    battery_volt: float
    ekf_ok: int
    imu_ok: int
    mag_ok: int
    baro_ok: int
    rssi: int           # dBm
    mesh_link_ok: int   # 0/1
    mesh_komsu_sayisi: int  # firmware: aktif mesh node sayısı (Büşra)


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

    alt_tip: int        # MODE_SWARM_MOVEMENT=1 / MODE_MANEUVER=2
    flags: int          # bit alanı, KOMUT_FLAG_* bitleri
    roll_x100: int      # roll_cmd * 100  ([-32767, 32767])
    pitch_x100: int
    yaw_x100: int
    throttle_x100: int


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
class Cerceve:
    """COBS+CRC doğrulanmış UART çerçevesi."""

    tip: int
    iha_id: int
    payload: bytes  # 16 byte


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

    return Cerceve(tip=decoded[0], iha_id=decoded[1], payload=govde[2:18])


def pose_coz(payload: bytes) -> PoseVeri:
    """TIP_POSE payload'ını PoseVeri'ye çözer."""
    lat, lon, alt_cm, heading, vx, vy = struct.unpack(_POSE_FMT, payload)
    return PoseVeri(lat, lon, alt_cm, heading, vx, vy)


def durum_coz(payload: bytes) -> DurumVeri:
    """TIP_DURUM payload'ını DurumVeri'ye çözer."""
    alanlar = struct.unpack(_DURUM_FMT, payload)
    return DurumVeri(
        drone_id=alanlar[0],
        durum=alanlar[1],
        armed=alanlar[2],
        gps_fix_type=alanlar[3],
        battery_pct=alanlar[4],
        battery_volt=alanlar[5],
        ekf_ok=alanlar[6],
        imu_ok=alanlar[7],
        mag_ok=alanlar[8],
        baro_ok=alanlar[9],
        rssi=alanlar[10],
        mesh_link_ok=alanlar[11],
        mesh_komsu_sayisi=alanlar[12],
    )


def durum_paketle(drone_id: int, durum: int, armed: int,
                  gps_fix_type: int, battery_pct: int,
                  battery_volt: float, ekf_ok: int, imu_ok: int,
                  mag_ok: int, baro_ok: int, rssi: int,
                  mesh_link_ok: int,
                  mesh_komsu_sayisi: int = 0) -> bytes:
    """DurumVeri alanlarını 16 baytlık mesh payload'ına paketler.

    RPi kendi durumunu (agent_fsm çıktısı) ESP32'ye gönderirken
    kullanır. Sürünün §5.1 m.15 ayrılma akışı için kritik.

    Args:
        drone_id (int): Kendi ID.
        durum (int): _DURUM_* enum kodu (firmware ile aynı).
        armed (int): 0/1.
        gps_fix_type (int): 0-6 (RTK FIX = 6).
        battery_pct (int): 0-100.
        battery_volt (float): Pak voltajı.
        ekf_ok (int): 0/1.
        imu_ok (int): 0/1.
        mag_ok (int): 0/1.
        baro_ok (int): 0/1.
        rssi (int): dBm, -128..127.
        mesh_link_ok (int): 0/1.
        mesh_komsu_sayisi (int): aktif mesh node sayısı (Büşra,
            firmware tarafı sayıyor). Default 0 — RPi tarafı bilmeyebilir.

    Returns:
        bytes: 16 baytlık payload.
    """
    return struct.pack(
        _DURUM_FMT,
        drone_id, durum, armed, gps_fix_type, battery_pct,
        float(battery_volt), ekf_ok, imu_ok, mag_ok, baro_ok,
        rssi, mesh_link_ok, mesh_komsu_sayisi,
    )


def renk_coz(payload: bytes) -> RenkVeri:
    """TIP_RENK payload'ını RenkVeri'ye çözer."""
    renk, lat, lon = struct.unpack(_RENK_FMT, payload)
    return RenkVeri(renk, lat, lon)


def renk_paketle(renk: int, lat: int, lon: int) -> bytes:
    """Renk bölgesi tespitini 16 baytlık mesh payload'a paketler.

    Args:
        renk (int): 1=KIRMIZI, 2=MAVI (şartname §5.1 m.15).
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
    """OriginVeri alanlarını 16 baytlık mesh payload'ına paketler.

    Args:
        lat_1e7 (int): Enlem, 1e-7 derece.
        lon_1e7 (int): Boylam, 1e-7 derece.
        alt_mm (int): Yükseklik, milimetre.
        sequence (int): Origin sıra numarası.

    Returns:
        bytes: 16 baytlık payload.
    """
    return struct.pack(_ORIGIN_FMT, lat_1e7, lon_1e7, alt_mm, sequence)


def pose_paketle(lat: int, lon: int, alt_cm: int, heading: int,
                 vx: int, vy: int) -> bytes:
    """PoseVeri alanlarını 16 baytlık mesh payload'ına paketler.

    RPi kendi RTK konumunu ESP32'ye gönderirken kullanır.

    alt_cm/heading/vx/vy int16 (±327.67 m / 3276.7°/cm·s) aralığında
    kırpılır; sınır dışı değerler struct.error fırlatmak yerine sessizce
    kırpılır. Yarışma sahası 10 m × 10 m, ~30 m irtifa için aralık
    fazlasıyla yeterli; bu kırpma sadece sensör glitch korumasıdır.

    Returns:
        bytes: 16 baytlık payload.
    """
    def _kirp(v: int) -> int:
        return max(-32768, min(32767, int(v)))
    return struct.pack(
        _POSE_FMT, int(lat), int(lon),
        _kirp(alt_cm), _kirp(heading), _kirp(vx), _kirp(vy),
    )


def komut_coz(payload: bytes) -> KomutVeri:
    """TIP_KOMUT payload'ını KomutVeri'ye çözer."""
    alt_tip, flags, roll, pitch, yaw, throttle = struct.unpack(
        _KOMUT_FMT, payload
    )
    return KomutVeri(alt_tip, flags, roll, pitch, yaw, throttle)


def komut_paketle(alt_tip: int, flags: int, roll_x100: int,
                  pitch_x100: int, yaw_x100: int,
                  throttle_x100: int) -> bytes:
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
        roll_x100, pitch_x100, yaw_x100, throttle_x100,
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
    """LeaderHeartbeat alanlarını 16 baytlık payload'a paketler.

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
    """ElectionResult alanlarını 16 baytlık payload'a paketler.

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
