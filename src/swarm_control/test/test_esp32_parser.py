"""test_esp32_parser.py — UART çerçeve çözümleme birim testleri."""

import struct

from swarm_control.esp32_bridge import packet_parser as pp
from swarm_control.esp32_bridge.cobs import cobs_decode, cobs_encode
from swarm_control.esp32_bridge.crc16 import crc16


def _cerceve_uret(tip: int, iha_id: int, payload: bytes) -> bytes:
    """Firmware uart_gonder'ı taklit eder: CRC + COBS, 0x00 hariç döner."""
    govde = bytes([tip, iha_id]) + payload
    crc = crc16(govde)
    ham = govde + bytes([(crc >> 8) & 0xFF, crc & 0xFF])
    return cobs_encode(ham)[:-1]  # sondaki 0x00 ayracı atılır


def test_pose_round_trip():
    """TIP_POSE çerçevesi doğru çözülmeli."""
    payload = struct.pack('<iihhhh', 411234567, 291234567, 1500, 900, 5, -5)
    decoded = cobs_decode(_cerceve_uret(pp.TIP_POSE, 2, payload))
    cerceve = pp.cerceve_coz(decoded)
    assert cerceve is not None
    assert cerceve.tip == pp.TIP_POSE
    assert cerceve.iha_id == 2
    pose = pp.pose_coz(cerceve.payload)
    assert pose.lat == 411234567
    assert pose.vy == -5


def test_durum_round_trip():
    """TIP_DURUM çerçevesi tüm sağlık alanlarıyla çözülmeli."""
    payload = struct.pack(
        '<BBBBBfBBBBbBB', 3, 1, 1, 6, 87, 16.8, 1, 1, 1, 1, -65, 1, 0
    )
    decoded = cobs_decode(_cerceve_uret(pp.TIP_DURUM, 3, payload))
    cerceve = pp.cerceve_coz(decoded)
    durum = pp.durum_coz(cerceve.payload)
    assert durum.drone_id == 3
    assert durum.gps_fix_type == 6
    assert durum.rssi == -65
    assert abs(durum.battery_volt - 16.8) < 0.01


def test_origin_paketle_coz():
    """origin_paketle -> origin_coz alanları korumalı."""
    payload = pp.origin_paketle(411234567, 291234567, 15000, 7)
    origin = pp.origin_coz(payload)
    assert origin.lat_1e7 == 411234567
    assert origin.alt_mm == 15000
    assert origin.sequence == 7


def test_bozuk_crc_reddedilir():
    """CRC bozulursa cerceve_coz None döner."""
    payload = struct.pack('<iihhhh', 1, 2, 3, 4, 5, 6)
    decoded = bytearray(cobs_decode(_cerceve_uret(pp.TIP_POSE, 1, payload)))
    decoded[-1] ^= 0xFF  # CRC'yi boz
    assert pp.cerceve_coz(bytes(decoded)) is None


def test_kisa_cerceve_reddedilir():
    """20 bayttan kısa çerçeve None döner."""
    assert pp.cerceve_coz(b'\x04\x02\x00') is None
