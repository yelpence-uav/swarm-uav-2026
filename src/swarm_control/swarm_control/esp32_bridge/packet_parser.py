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

# Struct formatlari
_POSE_FMT = '<iihhhh'
_DURUM_FMT = '<BBBBBfBBBBbBB'
_RENK_FMT = '<Bii7x'
_GOREV_FMT = '<BBbB12x'
_ORIGIN_FMT = '<iiiI'
_KOMUT_FMT = '<BBhhhh6x'
_LEADER_HB_FMT = '<BIBBB8x'
_ELECTION_FMT = '<BBBBIBBBB4x'

# Joystick komutu bayrak bitleri
KOMUT_FLAG_TAKEOFF = 0x01
KOMUT_FLAG_LAND = 0x02
KOMUT_FLAG_RTL = 0x04
KOMUT_FLAG_EMERGENCY = 0x08
KOMUT_FLAG_FORMATION_CHANGE = 0x10
KOMUT_FLAG_DEADMAN_PRESSED = 0x20

KOMUT_MODE_SWARM_MOVEMENT = 1
KOMUT_MODE_MANEUVER = 2

_FRAME_MIN = 20


@dataclass
class PoseVeri:
    """Konum/hiz verisi (TIP_POSE)."""

    lat: int
    lon: int
    alt_cm: int
    heading: int
    vx: int
    vy: int


@dataclass
class DurumVeri:
    """Durum ve saglik verisi (TIP_DURUM)."""

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
    rssi: int
    mesh_link_ok: int
    mesh_komsu_sayisi: int


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
class Cerceve:
    """Cozulmus ve dogrulanmis cerceve yapisi."""

    tip: int
    iha_id: int
    payload: bytes


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

    return Cerceve(
        tip=decoded[0],
        iha_id=decoded[1],
        payload=govde[2:18]
    )


def pose_coz(payload: bytes) -> PoseVeri:
    """
    Pose verisi payload'ini cozer.

    Args:
        payload (bytes): 16 baytlik ham veri.

    Returns:
        PoseVeri: Cozulmus pose nesnesi.
    """
    lat, lon, alt_cm, heading, vx, vy = struct.unpack(
        _POSE_FMT, payload
    )
    return PoseVeri(lat, lon, alt_cm, heading, vx, vy)


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


def durum_paketle(
    drone_id: int, durum: int, armed: int,
    gps_fix_type: int, battery_pct: int,
    battery_volt: float, ekf_ok: int, imu_ok: int,
    mag_ok: int, baro_ok: int, rssi: int,
    mesh_link_ok: int, mesh_komsu_sayisi: int = 0
) -> bytes:
    """
    Durum verisi alanlarini paketler.

    Args:
        drone_id (int): Ajan kimligi.
        durum (int): Durum kodu.
        armed (int): Motor durumu.
        gps_fix_type (int): GPS fix seviyesi.
        battery_pct (int): Pil yuzdesi.
        battery_volt (float): Pil gerilimi.
        ekf_ok (int): EKF saglik durumu.
        imu_ok (int): IMU saglik durumu.
        mag_ok (int): Pusula saglik durumu.
        baro_ok (int): Barometre saglik durumu.
        rssi (int): Sinyal gucu.
        mesh_link_ok (int): Mesh baglanti durumu.
        mesh_komsu_sayisi (int): Komsu sayisi.

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
        renk (int): Tespit edilen renk kodu.
        lat (int): Enlem koordinati.
        lon (int): Boylam koordinati.

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


def pose_paketle(
    lat: int, lon: int, alt_cm: int, heading: int,
    vx: int, vy: int
) -> bytes:
    """
    Pose verilerini paketler.

    Args:
        lat (int): Enlem.
        lon (int): Boylam.
        alt_cm (int): Irtifa (cm).
        heading (int): Yonelim.
        vx (int): X ekseni hizi.
        vy (int): Y ekseni hizi.

    Returns:
        bytes: 16 baytlik paketlenmis veri.
    """
    def _kirp(v: int) -> int:
        return max(-32768, min(32767, int(v)))

    return struct.pack(
        _POSE_FMT, int(lat), int(lon),
        _kirp(alt_cm), _kirp(heading), _kirp(vx), _kirp(vy),
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
