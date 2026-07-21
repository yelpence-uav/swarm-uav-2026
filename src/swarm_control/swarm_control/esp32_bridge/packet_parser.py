"""ESP32 UART paketlerini cozumleme yardimcisi.

UART cerceve yapisi ve mesh payload struct'larini cozer ve paketler.
"""

import struct
from dataclasses import dataclass

from .crc16 import crc16

# Paket tipleri
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
_DURUM_FMT = '<BBBBBfBBBBbBB'  # bkz. DurumVeri alanları
_RENK_FMT = '<Bii7x'         # renk, lat, lon, rezerv[7]
_GOREV_FMT = '<BBbB12x'      # tip, param1, param2, bekleme, rezerv[12]
_ORIGIN_FMT = '<iiiI'        # lat_1e7, lon_1e7, alt_mm, sequence
_KOMUT_FMT = '<BBhhhh6x'     # alt_tip, flags, roll/pitch/yaw/throttle x100
_LEADER_HB_FMT = '<BIBBB8x'  # leader_id, seq, round, agent_count, mission
_ELECTION_FMT = '<BBBBIBBBB4x'  # leader, round, reason, trigger, seq, ids
_QR_FMT = '<BIii3x'          # drone_id, action_id, lat, lon, rezerv[3]
_SWARM_STATE_FMT = '<BBBBI8x'  # mission_id, fsm, leader, formation, timestamp
_QR_COORD_FMT = '<BBii6x'    # qr_id, toplam, lat_1e7, lon_1e7, rezerv[6]

# Joystick komutu bayrak bitleri
KOMUT_FLAG_TAKEOFF = 0x01
KOMUT_FLAG_LAND = 0x02
KOMUT_FLAG_RTL = 0x04
KOMUT_FLAG_EMERGENCY = 0x08
KOMUT_FLAG_FORMATION_CHANGE = 0x10
KOMUT_FLAG_DEADMAN_PRESSED = 0x20

KOMUT_MODE_SWARM_MOVEMENT = 1
KOMUT_MODE_MANEUVER = 2

_FRAME_MIN = 4  # tip + iha_id + crc16 (payload değişken)

# F3: mesh-liveness yalnızca bilinen peer'dan bilinen telemetri tipiyle
# tazelenir. RTK (0x0C) ve VERSION dışarıda; RTK ayrı izlenir.
_LIVENESS_TIPLERI = frozenset({
    TIP_KOMUT, TIP_POSE, TIP_GOREV, TIP_RENK, TIP_DURUM, TIP_ORIGIN,
    TIP_LEADER_HB, TIP_ELECTION, TIP_HEARTBEAT, TIP_SWARM_STATE, TIP_QR_DATA,
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
    """Konum/hiz verisi (TIP_POSE)."""

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
    durum: int
    armed: int
    gps_fix_type: int
    battery_pct: int
    battery_volt: float
    ekf_ok: int
    imu_ok: int
    mag_ok: int
    baro_ok: int
    rssi: int           # dBm
    mesh_link_ok: int   # 0/1
    mesh_komsu_sayisi: int  # firmware: aktif mesh node sayısı


@dataclass
class RenkVeri:
    """Renk bolgesi koordinat verisi (TIP_RENK)."""

    renk: int
    lat: int
    lon: int


@dataclass
class GorevVeri:
    """Suru gorev komutu verisi (TIP_GOREV)."""

    tip: int
    param1: int
    param2: int
    bekleme_suresi_s: int


@dataclass
class OriginVeri:
    """NED origin tanimlama verisi (TIP_ORIGIN)."""

    lat_1e7: int
    lon_1e7: int
    alt_mm: int
    sequence: int


@dataclass
class KomutVeri:
    """Joystick/yari otonom suru komut verisi (TIP_KOMUT)."""

    alt_tip: int
    flags: int
    roll_x100: int
    pitch_x100: int
    yaw_x100: int
    throttle_x100: int


@dataclass
class LeaderHbVeri:
    """Lider kalp atisi verisi (TIP_LEADER_HB)."""

    leader_id: int
    sequence_num: int
    election_round: int
    active_agent_count: int
    mission_active: int


@dataclass
class ElectionVeri:
    """Lider secim sonucu verisi (TIP_ELECTION)."""

    new_leader_id: int
    election_round: int
    reason: int
    triggered_by: int
    sequence_num: int
    confirmed_ids: tuple[int, int, int, int]


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
    """Cozulmus ve dogrulanmis cerceve yapisi."""

    tip: int
    iha_id: int
    payload: bytes  # değişken uzunluk


def cerceve_coz(decoded: bytes) -> Cerceve | None:
    """
    COBS cozulmus baytlari dogrular ve cerceveye ayirir.

    Args:
        decoded (bytes): COBS cozulmus ham cerceve baytlari.

    Returns:
        Cerceve: Basarili ise cozulmus cerceve nesnesi, aksi halde None.
    """
    if len(decoded) < _FRAME_MIN:
        return None

    govde = decoded[:-2]
    crc_gelen = (decoded[-2] << 8) | decoded[-1]
    if crc16(govde) != crc_gelen:
        return None

    return Cerceve(tip=decoded[0], iha_id=decoded[1], payload=govde[2:])


def pose_coz(payload: bytes) -> PoseVeri:
    """TIP_POSE payload'ını PoseVeri'ye çözer."""
    lat, lon, alt_dm, heading, vx, vy, vz = struct.unpack(_POSE_FMT, payload)
    return PoseVeri(lat, lon, alt_dm, heading, vx, vy, vz)


def durum_coz(payload: bytes) -> DurumVeri:
    """
    Durum verisi payload'ini cozer.

    Args:
        payload (bytes): 16 baytlik ham veri.

    Returns:
        DurumVeri: Cozulmus durum nesnesi.
    """
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
    """Durum verisi alanlarını 16 baytlık mesh payload'ına paketler.

    RPi kendi durumunu (agent_fsm çıktısı) ESP32'ye gönderirken
    kullanır. Sürüden ayrılma akışı için kritik.

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
        mesh_komsu_sayisi (int): aktif mesh node sayısı (firmware
            tarafı sayıyor). Default 0 — RPi tarafı bilmeyebilir.

    Returns:
        bytes: 16 baytlik paketlenmis veri.
    """
    return struct.pack(
        _DURUM_FMT,
        drone_id, durum, armed, gps_fix_type, battery_pct,
        float(battery_volt), ekf_ok, imu_ok, mag_ok, baro_ok,
        rssi, mesh_link_ok, mesh_komsu_sayisi,
    )


def renk_coz(payload: bytes) -> RenkVeri:
    """
    Renk verisi payload'ini cozer.

    Args:
        payload (bytes): 16 baytlik ham veri.

    Returns:
        RenkVeri: Cozulmus renk nesnesi.
    """
    renk, lat, lon = struct.unpack(_RENK_FMT, payload)
    return RenkVeri(renk, lat, lon)


def renk_paketle(renk: int, lat: int, lon: int) -> bytes:
    """
    Renk verilerini paketler.

    Args:
        renk (int): 1=KIRMIZI, 2=MAVI.
        lat (int): Enlem, 1e-7 derece.
        lon (int): Boylam, 1e-7 derece.

    Returns:
        bytes: 16 baytlik paketlenmis veri.
    """
    return struct.pack(_RENK_FMT, renk, lat, lon)


def gorev_coz(payload: bytes) -> GorevVeri:
    """
    Gorev verisi payload'ini cozer.

    Args:
        payload (bytes): 16 baytlik ham veri.

    Returns:
        GorevVeri: Cozulmus gorev nesnesi.
    """
    tip, param1, param2, bekleme = struct.unpack(
        _GOREV_FMT, payload
    )
    return GorevVeri(tip, param1, param2, bekleme)


def gorev_paketle(
    tip: int, param1: int, param2: int, bekleme_suresi_s: int
) -> bytes:
    """
    Gorev verilerini paketler.

    Args:
        tip (int): Gorev tipi.
        param1 (int): Birinci parametre.
        param2 (int): Ikinci parametre.
        bekleme_suresi_s (int): Bekleme suresi.

    Returns:
        bytes: 16 baytlik paketlenmis veri.
    """
    return struct.pack(
        _GOREV_FMT, tip, param1, param2, bekleme_suresi_s
    )


def origin_coz(payload: bytes) -> OriginVeri:
    """
    Origin verisi payload'ini cozer.

    Args:
        payload (bytes): 16 baytlik ham veri.

    Returns:
        OriginVeri: Cozulmus origin nesnesi.
    """
    lat, lon, alt_mm, seq = struct.unpack(
        _ORIGIN_FMT, payload
    )
    return OriginVeri(lat, lon, alt_mm, seq)


def origin_paketle(
    lat_1e7: int, lon_1e7: int, alt_mm: int, sequence: int
) -> bytes:
    """
    Origin verilerini paketler.

    Args:
        lat_1e7 (int): Baslangic enlemi.
        lon_1e7 (int): Baslangic boylami.
        alt_mm (int): Baslangic yuksekligi.
        sequence (int): Sira numarasi.

    Returns:
        bytes: 16 baytlik paketlenmis veri.
    """
    return struct.pack(
        _ORIGIN_FMT, lat_1e7, lon_1e7, alt_mm, sequence
    )


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
    """
    Komut verisi payload'ini cozer.

    Args:
        payload (bytes): 16 baytlik ham veri.

    Returns:
        KomutVeri: Cozulmus komut nesnesi.
    """
    alt_tip, flags, roll, pitch, yaw, throttle = struct.unpack(
        _KOMUT_FMT, payload
    )
    return KomutVeri(
        alt_tip, flags, roll, pitch, yaw, throttle
    )


def komut_paketle(
    alt_tip: int, flags: int, roll_x100: int,
    pitch_x100: int, yaw_x100: int, throttle_x100: int
) -> bytes:
    """
    Komut verilerini paketler.

    Args:
        alt_tip (int): Komut alt tipi.
        flags (int): Bayraklar.
        roll_x100 (int): Roll degeri (x100).
        pitch_x100 (int): Pitch degeri (x100).
        yaw_x100 (int): Yaw degeri (x100).
        throttle_x100 (int): Gaz degeri (x100).

    Returns:
        bytes: 16 baytlik paketlenmis veri.
    """
    return struct.pack(
        _KOMUT_FMT, alt_tip, flags,
        roll_x100, pitch_x100, yaw_x100, throttle_x100,
    )


def leader_hb_coz(payload: bytes) -> LeaderHbVeri:
    """
    Lider hb verisi payload'ini cozer.

    Args:
        payload (bytes): 16 baytlik ham veri.

    Returns:
        LeaderHbVeri: Cozulmus lider hb nesnesi.
    """
    (leader_id, seq, election_round, agent_count,
     mission) = struct.unpack(_LEADER_HB_FMT, payload)
    return LeaderHbVeri(
        leader_id, seq, election_round, agent_count, mission
    )


def leader_hb_paketle(
    leader_id: int, sequence_num: int,
    election_round: int, active_agent_count: int,
    mission_active: int
) -> bytes:
    """
    Lider hb verilerini paketler.

    Args:
        leader_id (int): Lider kimligi.
        sequence_num (int): Sira numarasi.
        election_round (int): Secim turu.
        active_agent_count (int): Aktif ajan sayisi.
        mission_active (int): Gorev aktiflik durumu.

    Returns:
        bytes: 16 baytlik paketlenmis veri.
    """
    return struct.pack(
        _LEADER_HB_FMT,
        leader_id, sequence_num, election_round,
        active_agent_count, mission_active,
    )


def election_coz(payload: bytes) -> ElectionVeri:
    """
    Secim verisi payload'ini cozer.

    Args:
        payload (bytes): 16 baytlik ham veri.

    Returns:
        ElectionVeri: Cozulmus secim nesnesi.
    """
    (leader, election_round, reason, triggered_by, seq,
     id0, id1, id2, id3) = struct.unpack(
         _ELECTION_FMT, payload
     )
    return ElectionVeri(
        new_leader_id=leader,
        election_round=election_round,
        reason=reason,
        triggered_by=triggered_by,
        sequence_num=seq,
        confirmed_ids=(id0, id1, id2, id3),
    )


def election_paketle(
    new_leader_id: int, election_round: int,
    reason: int, triggered_by: int, sequence_num: int,
    confirmed_ids: tuple
) -> bytes:
    """
    Secim verilerini paketler.

    Args:
        new_leader_id (int): Yeni lider kimligi.
        election_round (int): Secim turu.
        reason (int): Neden kodu.
        triggered_by (int): Baslatan ajan.
        sequence_num (int): Sira numarasi.
        confirmed_ids (tuple): Onaylayan ajan kimlikleri.

    Returns:
        bytes: 16 baytlik paketlenmis veri.
    """
    ids = list(confirmed_ids[:4]) + [0] * (
        4 - len(confirmed_ids[:4])
    )
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
