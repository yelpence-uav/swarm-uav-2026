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
    """nav_msgs/Odometry -> pos (NED), vel (NED), heading.

    Odometry pose (konum) VE twist (hız) taşır, böylece tek callback
    ile ikisi de doldurulur (şema uyuşmazlığı çözümü). Konum/hız ENU
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

    v = msg.twist.twist.linear
    vnx, vny, vnz = _enu_to_ned(float(v.x), float(v.y), float(v.z))
    status.vel_x = vnx
    status.vel_y = vny
    status.vel_z = vnz

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


def map_rc_in(msg, status) -> None:
    """mavros_msgs/RCIn -> rc_link_ok.

    Kanal verisi geliyorsa RC bagli kabul edilir.

    Args:
        msg: mavros_msgs/RCIn.
        status: AgentStatus (yerinde guncellenir).
    """
    status.rc_link_ok = len(msg.channels) > 0
