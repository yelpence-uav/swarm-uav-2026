import math
from types import SimpleNamespace

from swarm_control.px4_interface.telemetry_mapper import (
    map_attitude,
    map_battery,
    map_estimator,
    map_global_position,
    map_gps,
    map_home_position,
    map_local_position,
    map_manual_control,
    map_vehicle_status,
)


def _status():
    return SimpleNamespace(
        battery_voltage_v=0.0, battery_current_a=0.0, battery_percent=0.0,
        armed=False, failsafe_active=False, rc_signal_failsafe_active=False,
        px4_link_ok=False, flight_mode=0, offboard_active=False,
        offboard_enabled=False, pilot_override_active=False,
        pos_x=0.0, pos_y=0.0, pos_z=0.0,
        vel_x=0.0, vel_y=0.0, vel_z=0.0,
        xy_valid=False, z_valid=False, v_xy_valid=False,
        imu_healthy=False, estimator_ok=False, mag_healthy=False, baro_healthy=False,
        gps_fix_type=0, gps_hdop=0.0, gps_satellites=0,
        lat_deg=0.0, lon_deg=0.0, alt_amsl_m=0.0,
        home_set=False, home_lat_deg=0.0, home_lon_deg=0.0, home_alt_amsl_m=0.0,
        roll_deg=0.0, pitch_deg=0.0, heading_deg=0.0,
        rc_link_ok=False,
    )


# --- map_battery ---

def test_battery_0_1_format():
    s = _status()
    map_battery(SimpleNamespace(voltage_v=16.0, current_a=2.0, remaining=0.75), s)
    assert s.battery_voltage_v == 16.0
    assert s.battery_percent == 75.0


def test_battery_yuzde_format():
    s = _status()
    map_battery(SimpleNamespace(voltage_v=16.0, current_a=1.0, remaining=80.0), s)
    assert s.battery_percent == 80.0


def test_battery_sinir_degerler():
    s = _status()
    map_battery(SimpleNamespace(voltage_v=0.0, current_a=0.0, remaining=0.0), s)
    assert s.battery_percent == 0.0
    map_battery(SimpleNamespace(voltage_v=0.0, current_a=0.0, remaining=1.0), s)
    assert s.battery_percent == 100.0


# --- map_vehicle_status ---

def test_vehicle_status_armed_offboard():
    s = _status()
    map_vehicle_status(SimpleNamespace(arming_state=2, failsafe=False, nav_state=14), s)
    assert s.armed is True
    assert s.offboard_active is True
    assert s.px4_link_ok is True


def test_vehicle_status_auto_takeoff_offboard_sayilir():
    s = _status()
    map_vehicle_status(SimpleNamespace(arming_state=2, failsafe=False, nav_state=17), s)
    assert s.offboard_active is True


def test_vehicle_status_manual_pilot_override():
    s = _status()
    map_vehicle_status(SimpleNamespace(arming_state=1, failsafe=False, nav_state=0), s)
    assert s.pilot_override_active is True
    assert s.offboard_active is False


def test_vehicle_status_bilinmeyen_nav_state():
    s = _status()
    map_vehicle_status(SimpleNamespace(arming_state=1, failsafe=False, nav_state=99), s)
    assert s.flight_mode == 0


# --- map_local_position ---

def test_local_position():
    s = _status()
    map_local_position(SimpleNamespace(
        x=1.0, y=2.0, z=-5.0, vx=0.1, vy=0.2, vz=0.0,
        xy_valid=True, z_valid=True, v_xy_valid=True,
    ), s)
    assert s.pos_x == 1.0 and s.pos_z == -5.0
    assert s.xy_valid is True and s.z_valid is True


# --- map_estimator ---

def test_estimator_tilt_yaw_ok():
    s = _status()
    map_estimator(SimpleNamespace(cs_tilt_align=True, cs_yaw_align=True, cs_baro_fault=False), s)
    assert s.imu_healthy is True
    assert s.estimator_ok is True
    assert s.baro_healthy is True


def test_estimator_tilt_yok():
    s = _status()
    map_estimator(SimpleNamespace(cs_tilt_align=False, cs_yaw_align=True, cs_baro_fault=False), s)
    assert s.imu_healthy is False
    assert s.estimator_ok is False


def test_estimator_baro_fault():
    s = _status()
    map_estimator(SimpleNamespace(cs_tilt_align=True, cs_yaw_align=True, cs_baro_fault=True), s)
    assert s.baro_healthy is False


# --- map_gps ---

def test_gps():
    s = _status()
    map_gps(SimpleNamespace(fix_type=3, hdop=0.9, satellites_used=12), s)
    assert s.gps_fix_type == 3 and s.gps_satellites == 12


# --- map_global_position ---

def test_global_position():
    s = _status()
    map_global_position(SimpleNamespace(lat=41.0, lon=29.0, alt=50.0), s)
    assert s.lat_deg == 41.0 and s.alt_amsl_m == 50.0


# --- map_home_position ---

def test_home_position_set():
    s = _status()
    map_home_position(SimpleNamespace(valid_hpos=True, valid_alt=True, lat=41.0, lon=29.0, alt=50.0), s)
    assert s.home_set is True


def test_home_position_set_degil():
    s = _status()
    map_home_position(SimpleNamespace(valid_hpos=False, valid_alt=True, lat=0.0, lon=0.0, alt=0.0), s)
    assert s.home_set is False


# --- map_attitude ---

def test_attitude_kuzey_bakan():
    s = _status()
    map_attitude(SimpleNamespace(q=[1.0, 0.0, 0.0, 0.0]), s)
    assert abs(s.roll_deg) < 0.01
    assert abs(s.pitch_deg) < 0.01
    assert abs(s.heading_deg) < 0.01 or abs(s.heading_deg - 360.0) < 0.01


def test_attitude_heading_normalize_0_360():
    yaw = -math.pi / 2
    q = [math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]
    s = _status()
    map_attitude(SimpleNamespace(q=q), s)
    assert 269.0 < s.heading_deg < 271.0


# --- map_manual_control ---

def test_manual_control_valid():
    s = _status()
    map_manual_control(SimpleNamespace(valid=True), s)
    assert s.rc_link_ok is True


def test_manual_control_invalid():
    s = _status()
    map_manual_control(SimpleNamespace(valid=False), s)
    assert s.rc_link_ok is False
