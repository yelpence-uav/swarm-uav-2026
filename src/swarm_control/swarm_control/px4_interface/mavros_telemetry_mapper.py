"""
mavros_telemetry_mapper.py

MAVROS mesajlarını AgentStatus'a çeviren saf fonksiyonlar (ROS2 node'u
değil; her fonksiyon AgentStatus'u yerinde günceller).

MAVROS ENU yayınlar, AgentStatus NED saklar; dönüşüm _enu_to_ned ile
tek noktada yapılır.
"""

import math

# PX4 uçuş modu metni (State.mode) -> AgentStatus flight_mode kodu.
MODE_STR_TO_FLIGHT_MODE: dict[str, int] = {
    'MANUAL': 1,
    'ALTCTL': 2,
    'POSCTL': 3,
    'OFFBOARD': 4,
    'AUTO.MISSION': 5,
    'AUTO.LOITER': 6,
    'AUTO.RTL': 7,
    'AUTO.LAND': 8,
    'AUTO.TAKEOFF': 5,
    'ACRO': 9,
    'STABILIZED': 10,
}

# Pilot override sayılan flight mode kodları (telemetry_mapper ile aynı).
PILOT_FLIGHT_MODES: frozenset[int] = frozenset({1, 2, 3, 9, 10})

# Failsafe proxy: MAV_STATE (system_status) değerleri.
# CRITICAL/EMERGENCY gelirse failsafe aktif kabul ediyoruz (temkinli).
_MAV_STATE_CRITICAL = 5
_MAV_STATE_EMERGENCY = 6


def _enu_to_ned(x: float, y: float, z: float) -> tuple:
    """ENU konumu NED'e çevirir.

    x/y yer değiştirir, z işaret değiştirir; aynı formül ters yönde de
    çalışır.

    Args:
        x (float): ENU X (Doğu).
        y (float): ENU Y (Kuzey).
        z (float): ENU Z (Yukarı).

    Returns:
        tuple: (x_ned, y_ned, z_ned).
    """
    return y, x, -z


def _quat_to_heading_ned_deg(qx: float, qy: float, qz: float,
                             qw: float) -> float:
    """ENU quaternion'dan NED heading (derece) çıkarır.

    Önce ENU yaw hesaplanır, sonra heading = (90 - yaw_enu) mod 360.

    Args:
        qx, qy, qz, qw (float): ENU quaternion bileşenleri.

    Returns:
        float: NED heading, 0-360 derece.
    """
    siny = 2.0 * (qw * qz + qx * qy)
    cosy = 1.0 - 2.0 * (qy * qy + qz * qz)
    yaw_enu = math.degrees(math.atan2(siny, cosy))
    heading = (90.0 - yaw_enu) % 360.0
    return heading


def _quat_to_roll_pitch_deg(qx: float, qy: float, qz: float,
                            qw: float) -> tuple:
    """Quaternion'dan roll ve pitch (derece) cikarir (ZYX Euler).

    ENU-FLU ile NED-FRD govde cerceveleri arasindaki isaret farki
    gercek donanimda mutlaka bir kez daha kontrol edilmeli.

    Args:
        qx, qy, qz, qw (float): quaternion bilesenleri.

    Returns:
        tuple: (roll_deg, pitch_deg).
    """
    sinr = 2.0 * (qw * qx + qy * qz)
    cosr = 1.0 - 2.0 * (qx * qx + qy * qy)
    roll = math.degrees(math.atan2(sinr, cosr))

    sinp = 2.0 * (qw * qy - qz * qx)
    sinp = max(-1.0, min(1.0, sinp))  # gimbal lock guard
    pitch = math.degrees(math.asin(sinp))
    return roll, pitch


def map_state(msg, status) -> None:
    """mavros_msgs/State -> armed, flight_mode, offboard, failsafe (proxy).

    Args:
        msg: mavros_msgs/State.
        status: AgentStatus (yerinde güncellenir).
    """
    status.px4_link_ok = bool(msg.connected)
    status.armed = bool(msg.armed)

    fm = MODE_STR_TO_FLIGHT_MODE.get(msg.mode, 0)  # 0 = UNKNOWN
    status.flight_mode = fm
    status.offboard_active = (msg.mode == 'OFFBOARD')
    status.offboard_enabled = status.offboard_active
    status.pilot_override_active = (fm in PILOT_FLIGHT_MODES)

    # Failsafe proxy: system_status CRITICAL/EMERGENCY ise aktif kabul.
    ss = int(getattr(msg, 'system_status', 0))
    status.failsafe_active = ss in (
        _MAV_STATE_CRITICAL, _MAV_STATE_EMERGENCY
    )


def map_battery(msg, status) -> None:
    """sensor_msgs/BatteryState -> voltage, current, percent.

    percentage 0-1 aralığında; current deşarjda negatif (mutlak alınır).
    NaN gelirse 0 kabul edilir.

    Args:
        msg: sensor_msgs/BatteryState.
        status: AgentStatus.
    """
    v = float(msg.voltage)
    status.battery_voltage_v = 0.0 if math.isnan(v) else v

    c = float(msg.current)
    status.battery_current_a = 0.0 if math.isnan(c) else abs(c)

    pct = float(msg.percentage)
    if math.isnan(pct):
        pct = 0.0
    status.battery_percent = max(0.0, min(100.0, pct * 100.0))


def map_odometry(msg, status) -> None:
    """nav_msgs/Odometry -> pos (NED), heading.

    Hız buradan OKUNMAZ: odom.twist gövde (base_link) çerçevesinde
    gelir; hız map_velocity_local'dan (dünya-ENU) okunur. Konum ENU
    gelir, NED'e çevrilir.

    Args:
        msg: nav_msgs/Odometry.
        status: AgentStatus.
    """
    p = msg.pose.pose.position
    nx, ny, nz = _enu_to_ned(float(p.x), float(p.y), float(p.z))
    status.pos_x = nx
    status.pos_y = ny
    status.pos_z = nz

    q = msg.pose.pose.orientation
    status.heading_deg = _quat_to_heading_ned_deg(
        float(q.x), float(q.y), float(q.z), float(q.w)
    )
    status.roll_deg, status.pitch_deg = _quat_to_roll_pitch_deg(
        float(q.x), float(q.y), float(q.z), float(q.w)
    )

    # Odometry'de ayrı valid bayrağı yok; mesaj geldiyse geçerli kabul.
    # (Kesin geçerlilik covariance'tan çıkarılabilir — sim'de doğrulanacak.)
    status.xy_valid = True
    status.z_valid = True
    status.v_xy_valid = True


def map_velocity_local(msg, status) -> None:
    """geometry_msgs/TwistStamped -> vel (NED).

    velocity_local dünya-ENU hız verir; odom.twist gövde (base_link)
    çerçevesinde olduğu için hız buradan okunur.

    Args:
        msg: geometry_msgs/TwistStamped.
        status: AgentStatus.
    """
    v = msg.twist.linear
    vnx, vny, vnz = _enu_to_ned(float(v.x), float(v.y), float(v.z))
    status.vel_x = vnx
    status.vel_y = vny
    status.vel_z = vnz


def map_global_position(msg, status) -> None:
    """sensor_msgs/NavSatFix -> lat_deg, lon_deg, alt_amsl_m.

    Args:
        msg: sensor_msgs/NavSatFix.
        status: AgentStatus.
    """
    status.lat_deg = float(msg.latitude)
    status.lon_deg = float(msg.longitude)
    status.alt_amsl_m = float(msg.altitude)


def map_gps_raw(msg, status) -> None:
    """mavros_msgs/GPSRAW -> gps_fix_type, gps_satellites, gps_hdop.

    eph, HDOP*100 taşır (MAVLink GPS_RAW_INT); bilinmiyorsa UINT16_MAX.
    Bilinmiyorsa gps_hdop temkinli olarak yüksek (kötü) bırakılır ki
    ön-uçuş GPS kontrolü açık kalsın.

    Args:
        msg: mavros_msgs/GPSRAW.
        status: AgentStatus.
    """
    status.gps_fix_type = int(msg.fix_type)
    status.gps_satellites = int(msg.satellites_visible)
    eph = int(msg.eph)
    status.gps_hdop = 99.9 if eph == 65535 else eph / 100.0


def map_home(msg, status) -> None:
    """mavros_msgs/HomePosition -> home_set + home lat/lon/alt.

    Args:
        msg: mavros_msgs/HomePosition.
        status: AgentStatus.
    """
    status.home_set = True
    status.home_lat_deg = float(msg.geo.latitude)
    status.home_lon_deg = float(msg.geo.longitude)
    status.home_alt_amsl_m = float(msg.geo.altitude)


def map_estimator_status(msg, status) -> None:
    """mavros_msgs/EstimatorStatus -> imu/mag/baro/estimator saglik.

    NOT (kayipli soyutlama): MAVROS EstimatorStatus, PX4'un ic EKF2
    bayraklariyla bire bir ortusmez. En yakin karsiliklar kullanildi;
    kesin esdegerlik degil, makul yaklasim.

    Args:
        msg: mavros_msgs/EstimatorStatus.
        status: AgentStatus (yerinde guncellenir).
    """
    att_ok = bool(msg.attitude_status_flag)
    pos_ok = bool(msg.pos_horiz_abs_status_flag)
    vert_ok = bool(msg.pos_vert_abs_status_flag)
    status.imu_healthy = att_ok
    status.mag_healthy = att_ok      # yon tahmini mag'e dayanir (dolayli)
    status.baro_healthy = vert_ok    # dikey konum baro'ya dayanir (dolayli)
    status.estimator_ok = att_ok and pos_ok


def _switch_aktif(kanallar, kanal_1tabanli: int, esik: int, ters: bool) -> bool:
    """Bir RC anahtar kanalinin aktif olup olmadigini soyler.

    Args:
        kanallar: RCIn.channels (PWM mikrosaniye, tipik 1000-2000).
        kanal_1tabanli: Kanal numarasi, kumandadaki gibi 1'den baslar.
        esik: Bu degerin ustu "aktif" sayilir (ters=True ise alti).
        ters: Polarite cevirme.

    Returns:
        bool: Anahtar aktifse True. Kanal yoksa veya 0 (sinyal yok) ise False.
    """
    i = kanal_1tabanli - 1
    if i < 0 or i >= len(kanallar):
        return False
    v = kanallar[i]
    if v == 0:          # 0 = o kanalda sinyal yok, hukum verme
        return False
    return (v < esik) if ters else (v > esik)


def map_rc_in(msg, status, kill_kanal: int = 5, kill_esik: int = 1500,
              kill_ters: bool = False, arm_kanal: int = 8,
              arm_esik: int = 1500, arm_ters: bool = False) -> None:
    """mavros_msgs/RCIn -> rc_link_ok, kill_switch_active.

    Eskiden yalnizca kanal SAYISINA bakip rc_link_ok set ediyordu; kanal
    DEGERLERI hic okunmuyordu. Sonucu: kill_switch_active'i dolduran tek yol
    EVENT_KILL_SWITCH_ACTIVATED olayiydi ve o olayi hicbir dugum uretmiyordu.
    Yani kill switch acikken drone bunu bilmiyor, YKİ de "bosta" gosteriyordu.

    Kanal/esik/polarite parametre: kumanda degisirse ya da polarite ters
    cikarsa yeniden derleme degil, baslat.sh'de tek satir degisir. Saha
    olcumu (2026-07-22, FLYSKY): ch5 kill, 2000 = AKTIF; ch8 arm,
    1000 = disarm / 2000 = arm (PX4'un armed bayragiyla dogrulandi).

    Args:
        msg: mavros_msgs/RCIn.
        status: AgentStatus (yerinde guncellenir).
        kill_kanal: Kill switch RC kanali (1-tabanli).
        kill_esik: Bu PWM degerinin ustu kill aktif sayilir.
        kill_ters: True ise esigin ALTI kill aktif demektir.
        arm_kanal: Arm switch RC kanali (1-tabanli).
        arm_esik: Arm esigi.
        arm_ters: Arm polarite cevirme.
    """
    kanallar = msg.channels
    status.rc_link_ok = len(kanallar) > 0
    if not status.rc_link_ok:
        # RC yoksa kill hakkinda hukum verme: "bilmiyorum" ile "aktif degil"
        # farkli seyler. Onceki degeri koruyoruz.
        return
    status.kill_switch_active = _switch_aktif(
        kanallar, kill_kanal, kill_esik, kill_ters
    )
    if hasattr(status, 'arm_switch_active'):
        status.arm_switch_active = _switch_aktif(
            kanallar, arm_kanal, arm_esik, arm_ters
        )


# MAVLink SYS_STATUS sensor bitmask: "arm on-kontrolleri gecti" biti.
# https://mavlink.io/en/messages/common.html#MAV_SYS_STATUS_PREARM_CHECK
_MAV_SYS_STATUS_PREARM_CHECK = 0x10000000


def map_diagnostics(msg, status) -> bool:
    """MAVROS /diagnostics -> ready_to_arm.

    PX4, emniyet anahtarinin (SWITCH portundaki kirmizi LED'li buton)
    durumunu MAVLink'te AYRI bir alanda bildirmiyor. Ama etkisi
    SYS_STATUS'un PREARM_CHECK bitinde gorunuyor: buton basili degilken
    bit temiz, basilinca kalkiyor.

    Saha olcumu (2026-07-22): butona basildigi an
        Sensor health: 0x0321C83F -> 0x1321C83F
    yani tam olarak 0x10000000 biti degisti.

    ONEMLI: bu bit YALNIZCA emniyet anahtarini degil, TUM arm on-kontrollerini
    kapsar (kalibrasyon, GPS kalitesi, batarya...). Yani "emniyet acik" degil
    "arm edilemez" anlamina gelir. Sebebi ayirt etmek icin PX4'un statustext
    mesajlari gerekir; bu fonksiyon yalnizca "ucabilir mi" sorusunu cevaplar.

    MAVROS'un diagnostic anahtar adlarina bagimliyiz ("mavros: System" ->
    "Sensor health"). Anahtar bulunamazsa status'a DOKUNULMAZ: "bilmiyorum"
    ile "arm edilemez" farkli seylerdir, ikincisini uydurmak yaniltir.

    Args:
        msg: diagnostic_msgs/DiagnosticArray.
        status: AgentStatus (yerinde guncellenir).

    Returns:
        bool: Alan guncellendiyse True, ilgili anahtar bulunamadiysa False.
    """
    for st in msg.status:
        if 'System' not in st.name:
            continue
        for kv in st.values:
            if kv.key != 'Sensor health':
                continue
            try:
                saglik = int(kv.value, 16)
            except (ValueError, TypeError):
                return False
            status.ready_to_arm = bool(saglik & _MAV_SYS_STATUS_PREARM_CHECK)
            return True
    return False
