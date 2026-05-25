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


def test_komut_round_trip():
    """TIP_KOMUT joystick komutu alanları korumalı."""
    payload = pp.komut_paketle(
        alt_tip=pp.KOMUT_MODE_SWARM_MOVEMENT,
        flags=pp.KOMUT_FLAG_TAKEOFF | pp.KOMUT_FLAG_FORMATION_CHANGE,
        roll_x100=50, pitch_x100=-25, yaw_x100=100, throttle_x100=0,
    )
    assert len(payload) == 16
    k = pp.komut_coz(payload)
    assert k.alt_tip == pp.KOMUT_MODE_SWARM_MOVEMENT
    assert k.flags & pp.KOMUT_FLAG_TAKEOFF
    assert k.flags & pp.KOMUT_FLAG_FORMATION_CHANGE
    assert not k.flags & pp.KOMUT_FLAG_LAND
    assert k.roll_x100 == 50
    assert k.pitch_x100 == -25


def test_leader_hb_round_trip():
    """LeaderHeartbeat alanları 16 bayta sığar ve geri çözülür."""
    payload = pp.leader_hb_paketle(
        leader_id=2, sequence_num=1234567,
        election_round=3, active_agent_count=4, mission_active=1,
    )
    assert len(payload) == 16
    hb = pp.leader_hb_coz(payload)
    assert hb.leader_id == 2
    assert hb.sequence_num == 1234567
    assert hb.election_round == 3
    assert hb.active_agent_count == 4
    assert hb.mission_active == 1


def test_election_round_trip():
    """ElectionResult alanları 16 bayta sığar; confirmed_ids 4 ile padle."""
    payload = pp.election_paketle(
        new_leader_id=2, election_round=4, reason=1,
        triggered_by=0, sequence_num=42, confirmed_ids=(1, 2, 3),
    )
    assert len(payload) == 16
    e = pp.election_coz(payload)
    assert e.new_leader_id == 2
    assert e.reason == 1
    assert e.sequence_num == 42
    # 3 onay verildi, 4. slot 0 ile dolduruldu
    assert e.confirmed_ids == (1, 2, 3, 0)


def test_election_kirpma_4ten_fazla_id():
    """4'ten fazla confirmed_id verilirse ilk 4 alınır."""
    payload = pp.election_paketle(
        new_leader_id=1, election_round=1, reason=2,
        triggered_by=3, sequence_num=10, confirmed_ids=(1, 2, 3, 4, 5),
    )
    e = pp.election_coz(payload)
    assert e.confirmed_ids == (1, 2, 3, 4)


def test_yeni_tipler_cerceve_uyumlu():
    """Yeni paket tipleri tam çerçevede taşınabilir (POSE/DURUM gibi)."""
    payload = pp.komut_paketle(
        pp.KOMUT_MODE_MANEUVER, 0, 10, 20, 30, -40,
    )
    decoded = cobs_decode(_cerceve_uret(pp.TIP_KOMUT, 1, payload))
    c = pp.cerceve_coz(decoded)
    assert c is not None and c.tip == pp.TIP_KOMUT


def test_durum_paketle_round_trip():
    """durum_paketle -> durum_coz tüm alanları korumalı."""
    payload = pp.durum_paketle(
        drone_id=2, durum=5, armed=1, gps_fix_type=6,
        battery_pct=78, battery_volt=16.5,
        ekf_ok=1, imu_ok=1, mag_ok=1, baro_ok=0,
        rssi=-72, mesh_link_ok=1,
    )
    assert len(payload) == 16
    d = pp.durum_coz(payload)
    assert d.drone_id == 2
    assert d.durum == 5
    assert d.armed == 1
    assert d.gps_fix_type == 6
    assert d.battery_pct == 78
    assert abs(d.battery_volt - 16.5) < 0.01
    assert d.ekf_ok == 1 and d.baro_ok == 0
    assert d.rssi == -72
    assert d.mesh_link_ok == 1


def test_renk_round_trip():
    """TIP_RENK paketle -> çöz alanları korumalı (şartname §5.1 m.15)."""
    payload = pp.renk_paketle(renk=1, lat=411234567, lon=291234567)
    assert len(payload) == 16
    r = pp.renk_coz(payload)
    assert r.renk == 1
    assert r.lat == 411234567
    assert r.lon == 291234567


def test_gorev_round_trip():
    """TIP_GOREV paketle -> çöz alanları korumalı."""
    payload = pp.gorev_paketle(
        tip=2, param1=180, param2=-15, bekleme_suresi_s=3,
    )
    assert len(payload) == 16
    g = pp.gorev_coz(payload)
    assert g.tip == 2
    assert g.param1 == 180
    assert g.param2 == -15
    assert g.bekleme_suresi_s == 3
