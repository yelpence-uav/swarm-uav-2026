"""
telemetry_mapper.py

PX4 mesajlarını AgentStatus formatına çevirir.

Bu modül SAF — ROS2 ile alakası yok, sadece veri dönüştürme fonksiyonları.
Test edilmesi kolay, başka yerlerde de kullanılabilir.

Her PX4 mesaj tipi için ayrı bir map_* fonksiyonu var.
Fonksiyonlar AgentStatus nesnesini in-place günceller.
"""

import math


# PX4 nav_state → AgentStatus FLIGHT_MODE_* eşleşmesi
# PX4'ün sayısal kodları AgentStatus.msg'deki sayısal kodlardan farklı.
NAV_STATE_TO_FLIGHT_MODE: dict[int, int] = {
    0: 1,   # MANUAL       → FLIGHT_MODE_MANUAL
    1: 2,   # ALTCTL       → FLIGHT_MODE_ALTCTL
    2: 3,   # POSCTL       → FLIGHT_MODE_POSCTL
    3: 5,   # AUTO_MISSION → FLIGHT_MODE_AUTO_MISSION
    4: 6,   # AUTO_LOITER  → FLIGHT_MODE_AUTO_LOITER
    5: 7,   # AUTO_RTL     → FLIGHT_MODE_AUTO_RTL
    6: 9,   # ACRO         → FLIGHT_MODE_ACRO
    14: 4,   # OFFBOARD     → FLIGHT_MODE_OFFBOARD
    15: 10,  # STABILIZED   → FLIGHT_MODE_STABILIZED
    18: 8,   # AUTO_LAND    → FLIGHT_MODE_AUTO_LAND
}

# Pilot override olarak sayılan AgentStatus flight mode kodları
PILOT_FLIGHT_MODES: frozenset[int] = frozenset({
    1,   # MANUAL
    2,   # ALTCTL
    3,   # POSCTL
    9,   # ACRO
    10,  # STABILIZED
})


def map_battery(msg, status) -> None:
    """BatteryStatus → battery_voltage_v, battery_current_a,
    battery_percent."""
    status.battery_voltage_v = float(msg.voltage_v)
    status.battery_current_a = float(msg.current_a)
    remaining = float(msg.remaining)
    if remaining > 1.0:
        remaining = remaining / 100.0
    status.battery_percent = max(0.0, min(100.0, remaining * 100.0))


def map_vehicle_status(msg, status) -> None:
    """VehicleStatus → armed, flight_mode, failsafe_active,
    pilot_override_active vs."""
    # ARMING_STATE_ARMED = 2
    status.armed = (msg.arming_state == 2)
    status.failsafe_active = bool(msg.failsafe)
    status.rc_signal_failsafe_active = bool(getattr(msg, 'rc_signal_lost', False))
    status.px4_link_ok = True  # Bu mesaj geliyorsa PX4 bağlı

    # nav_state → AgentStatus flight_mode
    fm = NAV_STATE_TO_FLIGHT_MODE.get(msg.nav_state, 0)  # 0 = UNKNOWN
    status.flight_mode = fm
    status.offboard_active = (fm == 4)   # FLIGHT_MODE_OFFBOARD
    status.offboard_enabled = status.offboard_active
    status.pilot_override_active = (fm in PILOT_FLIGHT_MODES)


def map_local_position(msg, status) -> None:
    """VehicleLocalPosition → pos_x/y/z, vel_x/y/z, valid flag'ler."""
    status.pos_x = float(msg.x)
    status.pos_y = float(msg.y)
    status.pos_z = float(msg.z)
    status.vel_x = float(msg.vx)
    status.vel_y = float(msg.vy)
    status.vel_z = float(msg.vz)
    status.xy_valid = bool(msg.xy_valid)
    status.z_valid = bool(msg.z_valid)
    status.v_xy_valid = bool(msg.v_xy_valid)


def map_estimator(msg, status) -> None:
    """EstimatorStatusFlags → imu/mag/baro/estimator sağlığı.

    PX4 sürümleri arasında alan adları değişebilir.
    Bu yüzden getattr ile güvenli okuma yapıyoruz.
    """
    tilt_ok = bool(getattr(msg, 'cs_tilt_align', False))
    yaw_ok = bool(getattr(msg, 'cs_yaw_align', False))

    status.imu_healthy = tilt_ok
    status.estimator_ok = tilt_ok and yaw_ok

    # Mag — alan adı PX4 sürümüne göre değişir
    mag_ok = bool(
        getattr(msg, 'cs_mag_aligned_in_flight', None)
        or getattr(msg, 'cs_yaw_align', False)
    )
    status.mag_healthy = mag_ok

    # Baro — fault yoksa sağlıklı
    baro_fault = bool(getattr(msg, 'cs_baro_fault', False))
    status.baro_healthy = not baro_fault


def map_gps(msg, status) -> None:
    """SensorGps → gps_fix_type, gps_hdop, gps_satellites."""
    status.gps_fix_type = int(msg.fix_type)
    status.gps_hdop = float(msg.hdop)
    status.gps_satellites = int(msg.satellites_used)


def map_global_position(msg, status) -> None:
    """VehicleGlobalPosition → lat_deg, lon_deg, alt_amsl_m."""
    status.lat_deg = float(msg.lat)
    status.lon_deg = float(msg.lon)
    status.alt_amsl_m = float(msg.alt)


def map_home_position(msg, status) -> None:
    """HomePosition → home_set + home_lat/lon/alt."""
    status.home_set = bool(msg.valid_hpos and msg.valid_alt)
    status.home_lat_deg = float(msg.lat)
    status.home_lon_deg = float(msg.lon)
    status.home_alt_amsl_m = float(msg.alt)


def map_attitude(msg, status) -> None:
    """VehicleAttitude quaternion → roll_deg, pitch_deg, heading_deg.

    Quaternion [w, x, y, z] formatında geliyor (PX4 standardı).
    ZYX Euler dönüşümüyle açılara çeviriyoruz.
    """
    q = msg.q  # [w, x, y, z]

    # Roll (x ekseni etrafında dönüş)
    sinr = 2.0 * (q[0] * q[1] + q[2] * q[3])
    cosr = 1.0 - 2.0 * (q[1] ** 2 + q[2] ** 2)
    status.roll_deg = math.degrees(math.atan2(sinr, cosr))

    # Pitch (y ekseni)
    sinp = 2.0 * (q[0] * q[2] - q[3] * q[1])
    sinp = max(-1.0, min(1.0, sinp))  # gimbal lock guard
    status.pitch_deg = math.degrees(math.asin(sinp))

    # Yaw / heading (z ekseni)
    siny = 2.0 * (q[0] * q[3] + q[1] * q[2])
    cosy = 1.0 - 2.0 * (q[2] ** 2 + q[3] ** 2)
    yaw = math.degrees(math.atan2(siny, cosy))
    if yaw < 0:
        yaw += 360.0  # 0-360 arası normalize et
    status.heading_deg = yaw


def map_manual_control(msg, status) -> None:
    """ManualControlSetpoint → rc_link_ok."""
    status.rc_link_ok = bool(getattr(msg, 'valid', True))
