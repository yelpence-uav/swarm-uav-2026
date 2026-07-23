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
    """TIP_POSE (18B, vz dahil) çerçevesi doğru çözülmeli."""
    payload = struct.pack(
        '<iihhhhh', 411234567, 291234567, 1500, 900, 5, -5, 12
    )
    decoded = cobs_decode(_cerceve_uret(pp.TIP_POSE, 2, payload))
    cerceve = pp.cerceve_coz(decoded)
    assert cerceve is not None
    assert cerceve.tip == pp.TIP_POSE
    assert cerceve.iha_id == 2
    pose = pp.pose_coz(cerceve.payload)
    assert pose.lat == 411234567
    assert pose.alt_dm == 1500
    assert pose.vy == -5
    assert pose.vz == 12


def test_durum_round_trip():
    """TIP_DURUM çerçevesi tüm sağlık alanlarıyla çözülmeli (REV C)."""
    payload = pp.durum_paketle(
        drone_id=3, durum=1, armed=1, gps_fix_type=6, battery_pct=87,
        battery_volt=16.8, ekf_ok=1, imu_ok=1, mag_ok=1, baro_ok=1,
        rssi=-65, mesh_link_ok=1, mesh_komsu_sayisi=0,
    )
    assert len(payload) == 16, 'DURUM payload 16 bayt olmalı'
    decoded = cobs_decode(_cerceve_uret(pp.TIP_DURUM, 3, payload))
    cerceve = pp.cerceve_coz(decoded)
    durum = pp.durum_coz(cerceve.payload)
    assert durum.drone_id == 3
    assert durum.gps_fix_type == 6
    assert durum.rssi == -65
    assert abs(durum.battery_volt - 16.8) < 0.06   # 0.1 V çözünürlük
    assert durum.armed and durum.ekf_ok and durum.imu_ok
    assert durum.mag_healthy if hasattr(durum, 'mag_healthy') else durum.mag_ok


def test_durum_kill_switch_ve_rc_link_tasiniyor():
    """Kill switch ve RC link mesh'ten geçmeli.

    Regresyon: bu iki alan drone tarafında doğru hesaplanıyordu ama 16 baytlık
    payload dolu olduğu için YKİ'ye hiç ulaşmıyordu — operatör kill switch
    açıkken drone'u 'boşta' görüyordu (saha, 2026-07-22).
    """
    payload = pp.durum_paketle(
        drone_id=1, durum=1, armed=0, gps_fix_type=4, battery_pct=50,
        battery_volt=15.0, ekf_ok=1, imu_ok=1, mag_ok=1, baro_ok=1,
        rssi=-70, mesh_link_ok=1, kill_switch_active=1, rc_link_ok=1,
    )
    d = pp.durum_coz(payload)
    assert d.kill_switch_active is True
    assert d.rc_link_ok is True
    assert d.armed is False, 'kill biti armed bitine sızmamalı'

    # Kill kapalıyken de doğru okunmalı
    d2 = pp.durum_coz(pp.durum_paketle(
        drone_id=1, durum=1, armed=1, gps_fix_type=4, battery_pct=50,
        battery_volt=15.0, ekf_ok=1, imu_ok=1, mag_ok=1, baro_ok=1,
        rssi=-70, mesh_link_ok=1, kill_switch_active=0, rc_link_ok=1,
    ))
    assert d2.kill_switch_active is False
    assert d2.armed is True


def test_durum_gps_hassasiyeti_ve_mod_tasiniyor():
    """Uydu sayısı, HDOP ve uçuş modu mesh'ten geçmeli.

    Regresyon: YKİ'de 'DGPS 0' görünüyordu; o sıfır '0 uydu' değil
    'veri yok' demekti çünkü alanlar hiç taşınmıyordu.
    """
    d = pp.durum_coz(pp.durum_paketle(
        drone_id=1, durum=1, armed=0, gps_fix_type=4, battery_pct=50,
        battery_volt=15.0, ekf_ok=1, imu_ok=1, mag_ok=1, baro_ok=1,
        rssi=-70, mesh_link_ok=1,
        ucus_modu=6, gps_uydu=17, gps_hdop=0.8,
    ))
    assert d.gps_uydu == 17
    assert abs(d.gps_hdop - 0.8) < 0.06
    assert d.ucus_modu == 6


def test_durum_hdop_bilinmiyor_sentineli():
    """HDOP bilinmiyorsa 255 sentineli gidip 99.9 olarak dönmeli."""
    d = pp.durum_coz(pp.durum_paketle(
        drone_id=1, durum=1, armed=0, gps_fix_type=0, battery_pct=0,
        battery_volt=0.0, ekf_ok=0, imu_ok=0, mag_ok=0, baro_ok=0,
        rssi=0, mesh_link_ok=0, gps_hdop=99.9,
    ))
    assert d.gps_hdop_x10 == 255
    assert d.gps_hdop == 99.9


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
    """4 bayttan kısa çerçeve None döner (tip+id+crc16)."""
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


def test_komut_deadman_flag():
    """KOMUT_FLAG_DEADMAN_PRESSED bit'i ayrı set/test edilebilmeli.

    Beyza inceleme #2: deadman_pressed mesh'te bayrak biti olmazsa
    downstream tüm komutları reddeder. Bu bit eklendi (0x20).
    """
    flags = pp.KOMUT_FLAG_TAKEOFF | pp.KOMUT_FLAG_DEADMAN_PRESSED
    payload = pp.komut_paketle(
        alt_tip=1, flags=flags,
        roll_x100=0, pitch_x100=0, yaw_x100=0, throttle_x100=0,
    )
    k = pp.komut_coz(payload)
    assert k.flags & pp.KOMUT_FLAG_DEADMAN_PRESSED
    assert k.flags & pp.KOMUT_FLAG_TAKEOFF
    assert not k.flags & pp.KOMUT_FLAG_LAND


def test_pose_paketle_int16_kirpma():
    """pose_paketle int16 dışı değer verince crash etmez, kırpar."""
    payload = pp.pose_paketle(
        lat=411234567, lon=291234567,
        alt_dm=50000,    # >32767, kırpılmalı
        heading=99999,   # >32767
        vx=-99999,       # <-32768
        vy=0, vz=0,
    )
    assert len(payload) == 18
    pose = pp.pose_coz(payload)
    assert pose.alt_dm == 32767      # üst sınıra kırpıldı
    assert pose.heading == 32767
    assert pose.vx == -32768          # alt sınıra kırpıldı


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
        rssi=-72, mesh_link_ok=1, mesh_komsu_sayisi=3,
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
    assert d.mesh_komsu_sayisi == 3


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


def test_qr_round_trip():
    """TIP_QR_DATA payload'ı çözülmeli (şartname s.13 puanı)."""
    payload = struct.pack('<BIii3x', 2, 42, 411234567, 291234567)
    q = pp.qr_coz(payload)
    assert q.drone_id == 2
    assert q.action_id == 42
    assert q.lat == 411234567
    assert q.lon == 291234567


def test_swarm_state_round_trip():
    """TIP_SWARM_STATE payload'ı çözülmeli."""
    payload = struct.pack('<BBBBI8x', 1, 3, 2, 1, 123456)
    s = pp.swarm_state_coz(payload)
    assert s.mission_id == 1
    assert s.swarm_fsm_state == 3
    assert s.active_leader == 2
    assert s.formation == 1
    assert s.timestamp == 123456


def test_liveness_whitelist():
    """F3: sadece bilinen peer + bilinen telemetri tipi liveness tazeler."""
    assert pp.liveness_tazeler(2, pp.TIP_POSE) is True
    assert pp.liveness_tazeler(pp.BAZ_MESH_ID, pp.TIP_DURUM) is True
    # RTK sentinel (99) tazelemez — merge günü failsafe körleşmesi buradan
    assert pp.liveness_tazeler(pp.BAZ_ID, pp.TIP_RTK) is False
    # Bilinen tip ama bilinmeyen peer tazelemez
    assert pp.liveness_tazeler(99, pp.TIP_POSE) is False
    # Bilinen peer ama RTK tipi tazelemez
    assert pp.liveness_tazeler(2, pp.TIP_RTK) is False


def test_komut_fmt_layout_sozlesmesi():
    """mesh_config.h static_assert'lerinin Python yakası (offset sözleşmesi).

    Round-trip yakalayamaz: pack/unpack aynı _KOMUT_FMT'i kullandığı için
    alan sırası değişse bile kendi içinde tutarlı kalır.
    """
    assert struct.calcsize(pp._KOMUT_FMT) == 16

    p = pp.komut_paketle(alt_tip=0, flags=0xFF, roll_x100=0,
                         pitch_x100=0, yaw_x100=0, throttle_x100=0)
    assert p[1] == 0xFF                 # flags offset 1 (DEADMAN biti)

    p = pp.komut_paketle(alt_tip=0, flags=0, roll_x100=0x0102,
                         pitch_x100=0, yaw_x100=0, throttle_x100=0)
    assert p[2:4] == b'\x02\x01'        # roll offset 2, little-endian

    p = pp.komut_paketle(alt_tip=0, flags=0, roll_x100=0,
                         pitch_x100=0, yaw_x100=0, throttle_x100=0x0304)
    assert p[8:10] == b'\x04\x03'       # throttle offset 8


def test_komut_arm_disarm_flag():
    """Guided arm/disarm bitleri (0x40/0x80) ayrı set/test edilebilmeli."""
    payload = pp.komut_paketle(
        alt_tip=pp.KOMUT_MODE_GUIDED,
        flags=pp.KOMUT_FLAG_ARM | pp.KOMUT_FLAG_DEADMAN_PRESSED,
        roll_x100=0, pitch_x100=0, yaw_x100=0, throttle_x100=0,
    )
    k = pp.komut_coz(payload)
    assert k.alt_tip == pp.KOMUT_MODE_GUIDED
    assert k.flags & pp.KOMUT_FLAG_ARM
    assert not k.flags & pp.KOMUT_FLAG_DISARM
    assert k.flags & pp.KOMUT_FLAG_DEADMAN_PRESSED


def test_goto_round_trip():
    """TIP_GOTO nokta-git hedefi tüm alanları korumalı + metre dönüşümü."""
    payload = pp.goto_paketle(
        kuzey_dm=1250, dogu_dm=-800, asagi_dm=-150,   # 125m K, 80m B, 15m irtifa
        yaw_ddeg=900, bayraklar=pp.GOTO_BAYRAK_YAW_GECERLI,
    )
    assert len(payload) == 16
    g = pp.goto_coz(payload)
    assert g.kuzey_dm == 1250
    assert g.dogu_dm == -800
    assert g.asagi_dm == -150
    assert g.kuzey_m == 125.0
    assert g.dogu_m == -80.0
    assert g.asagi_m == -15.0
    assert g.yaw_deg == 90.0
    assert g.yaw_gecerli is True


def test_goto_yaw_gecersiz():
    """GOTO_BAYRAK_YAW_GECERLI yoksa yaw_gecerli False dönmeli."""
    g = pp.goto_coz(pp.goto_paketle(kuzey_dm=0, dogu_dm=0, asagi_dm=-100))
    assert g.yaw_gecerli is False


def test_goto_cerceve_uctan_uca():
    """goto_paketle -> firmware çerçevesi -> cerceve_coz -> goto_coz."""
    payload = pp.goto_paketle(kuzey_dm=300, dogu_dm=300, asagi_dm=-200)
    ham = _cerceve_uret(pp.TIP_GOTO, 1, payload)
    c = pp.cerceve_coz(cobs_decode(ham))
    assert c is not None
    assert c.tip == pp.TIP_GOTO
    g = pp.goto_coz(c.payload)
    assert g.kuzey_dm == 300
    assert g.asagi_m == -20.0


def test_goto_fmt_layout_sozlesmesi():
    """mesh_config.h goto_veri_t static_assert'lerinin Python yakası."""
    assert struct.calcsize(pp._GOTO_FMT) == 16

    p = pp.goto_paketle(kuzey_dm=0x0102, dogu_dm=0, asagi_dm=0)
    assert p[0:2] == b'\x02\x01'        # kuzey offset 0, little-endian

    p = pp.goto_paketle(kuzey_dm=0, dogu_dm=0, asagi_dm=0x0304)
    assert p[4:6] == b'\x04\x03'        # asagi offset 4

    p = pp.goto_paketle(kuzey_dm=0, dogu_dm=0, asagi_dm=0, bayraklar=0xAB)
    assert p[8] == 0xAB                 # bayraklar offset 8
