"""PX4 mesajlarını AgentStatus formatına çeviren dönüştürme fonksiyonları."""

import math


# PX4 nav_state → AgentStatus flight_mode eşleşmesi
NAV_STATE_TO_FLIGHT_MODE: dict[int, int] = {
    0: 1,   # MANUAL
    1: 2,   # ALTCTL
    2: 3,   # POSCTL
    3: 5,   # AUTO_MISSION
    4: 6,   # AUTO_LOITER
    5: 7,   # AUTO_RTL
    6: 9,   # ACRO
    14: 4,   # OFFBOARD
    15: 10,  # STABILIZED
    18: 8,   # AUTO_LAND
}

PILOT_FLIGHT_MODES: frozenset[int] = frozenset({1, 2, 3, 9, 10})


def map_battery(msg, status) -> None:
    """
    BatteryStatus mesajını AgentStatus batarya alanlarına çevirir.

    Args:
        msg: PX4 BatteryStatus mesajı.
        status: Güncellenecek AgentStatus nesnesi.
    """
    status.battery_voltage_v = float(msg.voltage_v)
    status.battery_current_a = float(msg.current_a)
    remaining = float(msg.remaining)
    if remaining > 1.0:
        remaining = remaining / 100.0
    status.battery_percent = max(0.0, min(100.0, remaining * 100.0))


def map_vehicle_status(msg, status) -> None:
    """
    VehicleStatus mesajını AgentStatus durum alanlarına çevirir.

    Args:
        msg: PX4 VehicleStatus mesajı.
        status: Güncellenecek AgentStatus nesnesi.
    """
    status.armed = (msg.arming_state == 2)
    status.failsafe_active = bool(msg.failsafe)
    status.rc_signal_failsafe_active = False
    status.px4_link_ok = True

    fm = NAV_STATE_TO_FLIGHT_MODE.get(msg.nav_state, 0)
    status.flight_mode = fm
    status.offboard_active = (fm == 4)
    status.offboard_enabled = status.offboard_active
    status.pilot_override_active = (fm in PILOT_FLIGHT_MODES)


def map_local_position(msg, status) -> None:
    """
    VehicleLocalPosition mesajını AgentStatus konum alanlarına çevirir.

    Args:
        msg: PX4 VehicleLocalPosition mesajı.
        status: Güncellenecek AgentStatus nesnesi.
    """
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
    """
    EstimatorStatusFlags mesajını AgentStatus sensör sağlığı alanlarına
    çevirir.

    PX4 sürümleri arasında alan adları değişebildiğinden getattr kullanılır.


    Args:
        msg: PX4 EstimatorStatusFlags mesajı.
        status: Güncellenecek AgentStatus nesnesi.
    """
    tilt_ok = bool(getattr(msg, 'cs_tilt_align', False))
    yaw_ok = bool(getattr(msg, 'cs_yaw_align', False))

    status.imu_healthy = tilt_ok
    status.estimator_ok = tilt_ok and yaw_ok

    mag_ok = bool(
        getattr(msg, 'cs_mag_aligned_in_flight', None)
        or getattr(msg, 'cs_yaw_align', False)
    )
    status.mag_healthy = mag_ok

    baro_fault = bool(getattr(msg, 'cs_baro_fault', False))
    status.baro_healthy = not baro_fault


def map_gps(msg, status) -> None:
    """
    SensorGps mesajını AgentStatus GPS alanlarına çevirir.

    Args:
        msg: PX4 SensorGps mesajı.
        status: Güncellenecek AgentStatus nesnesi.
    """
    status.gps_fix_type = int(msg.fix_type)
    status.gps_hdop = float(msg.hdop)
    status.gps_satellites = int(msg.satellites_used)


def map_global_position(msg, status) -> None:
    """
    VehicleGlobalPosition mesajını AgentStatus konum alanlarına çevirir.

    Args:
        msg: PX4 VehicleGlobalPosition mesajı.
        status: Güncellenecek AgentStatus nesnesi.
    """
    status.lat_deg = float(msg.lat)
    status.lon_deg = float(msg.lon)
    status.alt_amsl_m = float(msg.alt)


def map_home_position(msg, status) -> None:
    """
    HomePosition mesajını AgentStatus ev konumu alanlarına çevirir.

    Args:
        msg: PX4 HomePosition mesajı.
        status: Güncellenecek AgentStatus nesnesi.
    """
    status.home_set = bool(msg.valid_hpos and msg.valid_vpos)
    status.home_lat_deg = float(msg.lat)
    status.home_lon_deg = float(msg.lon)
    status.home_alt_amsl_m = float(msg.alt)


def map_attitude(msg, status) -> None:
    """
    VehicleAttitude kuaterniyonunu Euler açılarına çevirir.

    Kuaterniyon [w, x, y, z] formatında gelir (PX4 standardı).
    ZYX Euler dönüşümü uygulanır.

    Args:
        msg: PX4 VehicleAttitude mesajı.
        status: Güncellenecek AgentStatus nesnesi.
    """
    q = msg.q

    sinr = 2.0 * (q[0] * q[1] + q[2] * q[3])
    cosr = 1.0 - 2.0 * (q[1] ** 2 + q[2] ** 2)
    status.roll_deg = math.degrees(math.atan2(sinr, cosr))

    sinp = 2.0 * (q[0] * q[2] - q[3] * q[1])
    sinp = max(-1.0, min(1.0, sinp))
    status.pitch_deg = math.degrees(math.asin(sinp))

    siny = 2.0 * (q[0] * q[3] + q[1] * q[2])
    cosy = 1.0 - 2.0 * (q[2] ** 2 + q[3] ** 2)
    yaw = math.degrees(math.atan2(siny, cosy))
    if yaw < 0:
        yaw += 360.0
    status.heading_deg = yaw


def map_manual_control(msg, status) -> None:
    """
    ManualControlSetpoint mesajını AgentStatus RC bağlantı alanına çevirir.

    Args:
        msg: PX4 ManualControlSetpoint mesajı.
        status: Güncellenecek AgentStatus nesnesi.
    """
    status.rc_link_ok = bool(getattr(msg, 'valid', True))
