import math
import unittest
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
        imu_healthy=False, estimator_ok=False, mag_healthy=False,
        baro_healthy=False,
        gps_fix_type=0, gps_hdop=0.0, gps_satellites=0,
        lat_deg=0.0, lon_deg=0.0, alt_amsl_m=0.0,
        home_set=False, home_lat_deg=0.0, home_lon_deg=0.0,
        home_alt_amsl_m=0.0,
        roll_deg=0.0, pitch_deg=0.0, heading_deg=0.0,
        rc_link_ok=False,
    )


class TestBattery(unittest.TestCase):

    def test_battery_0_1_format(self):
        s = _status()
        map_battery(
            SimpleNamespace(voltage_v=16.0, current_a=2.0, remaining=0.75), s
        )
        self.assertEqual(s.battery_voltage_v, 16.0)
        self.assertEqual(s.battery_percent, 75.0)

    def test_battery_yuzde_format(self):
        s = _status()
        map_battery(
            SimpleNamespace(voltage_v=16.0, current_a=1.0, remaining=80.0), s
        )
        self.assertEqual(s.battery_percent, 80.0)

    def test_battery_sinir_degerler(self):
        s = _status()
        map_battery(
            SimpleNamespace(voltage_v=0.0, current_a=0.0, remaining=0.0), s
        )
        self.assertEqual(s.battery_percent, 0.0)
        map_battery(
            SimpleNamespace(voltage_v=0.0, current_a=0.0, remaining=1.0), s
        )
        self.assertEqual(s.battery_percent, 100.0)


class TestVehicleStatus(unittest.TestCase):

    def test_armed_offboard(self):
        s = _status()
        map_vehicle_status(
            SimpleNamespace(arming_state=2, failsafe=False, nav_state=14), s
        )
        self.assertTrue(s.armed)
        self.assertTrue(s.offboard_active)
        self.assertTrue(s.px4_link_ok)

    def test_auto_takeoff_offboard_sayilir(self):
        s = _status()
        map_vehicle_status(
            SimpleNamespace(arming_state=2, failsafe=False, nav_state=17), s
        )
        self.assertTrue(s.offboard_active)

    def test_manual_pilot_override(self):
        s = _status()
        map_vehicle_status(
            SimpleNamespace(arming_state=1, failsafe=False, nav_state=0), s
        )
        self.assertTrue(s.pilot_override_active)
        self.assertFalse(s.offboard_active)

    def test_bilinmeyen_nav_state(self):
        s = _status()
        map_vehicle_status(
            SimpleNamespace(arming_state=1, failsafe=False, nav_state=99), s
        )
        self.assertEqual(s.flight_mode, 0)


class TestLocalPosition(unittest.TestCase):

    def test_local_position(self):
        s = _status()
        map_local_position(SimpleNamespace(
            x=1.0, y=2.0, z=-5.0, vx=0.1, vy=0.2, vz=0.0,
            xy_valid=True, z_valid=True, v_xy_valid=True,
        ), s)
        self.assertEqual(s.pos_x, 1.0)
        self.assertEqual(s.pos_z, -5.0)
        self.assertTrue(s.xy_valid)
        self.assertTrue(s.z_valid)


class TestEstimator(unittest.TestCase):

    def test_tilt_yaw_ok(self):
        s = _status()
        map_estimator(SimpleNamespace(
            cs_tilt_align=True, cs_yaw_align=True, cs_baro_fault=False
        ), s)
        self.assertTrue(s.imu_healthy)
        self.assertTrue(s.estimator_ok)
        self.assertTrue(s.baro_healthy)

    def test_tilt_yok(self):
        s = _status()
        map_estimator(SimpleNamespace(
            cs_tilt_align=False, cs_yaw_align=True, cs_baro_fault=False
        ), s)
        self.assertFalse(s.imu_healthy)
        self.assertFalse(s.estimator_ok)

    def test_baro_fault(self):
        s = _status()
        map_estimator(SimpleNamespace(
            cs_tilt_align=True, cs_yaw_align=True, cs_baro_fault=True
        ), s)
        self.assertFalse(s.baro_healthy)


class TestGps(unittest.TestCase):

    def test_gps(self):
        s = _status()
        map_gps(SimpleNamespace(fix_type=3, hdop=0.9, satellites_used=12), s)
        self.assertEqual(s.gps_fix_type, 3)
        self.assertEqual(s.gps_satellites, 12)


class TestGlobalPosition(unittest.TestCase):

    def test_global_position(self):
        s = _status()
        map_global_position(SimpleNamespace(lat=41.0, lon=29.0, alt=50.0), s)
        self.assertEqual(s.lat_deg, 41.0)
        self.assertEqual(s.alt_amsl_m, 50.0)


class TestHomePosition(unittest.TestCase):

    def test_home_set(self):
        s = _status()
        map_home_position(SimpleNamespace(
            valid_hpos=True, valid_alt=True, lat=41.0, lon=29.0, alt=50.0
        ), s)
        self.assertTrue(s.home_set)

    def test_home_set_degil(self):
        s = _status()
        map_home_position(SimpleNamespace(
            valid_hpos=False, valid_alt=True, lat=0.0, lon=0.0, alt=0.0
        ), s)
        self.assertFalse(s.home_set)


class TestAttitude(unittest.TestCase):

    def test_kuzey_bakan(self):
        s = _status()
        map_attitude(SimpleNamespace(q=[1.0, 0.0, 0.0, 0.0]), s)
        self.assertAlmostEqual(s.roll_deg, 0.0, places=2)
        self.assertAlmostEqual(s.pitch_deg, 0.0, places=2)
        self.assertTrue(
            abs(s.heading_deg) < 0.01
            or abs(s.heading_deg - 360.0) < 0.01
        )

    def test_heading_normalize_0_360(self):
        yaw = -math.pi / 2
        q = [math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]
        s = _status()
        map_attitude(SimpleNamespace(q=q), s)
        self.assertGreater(s.heading_deg, 269.0)
        self.assertLess(s.heading_deg, 271.0)


class TestManualControl(unittest.TestCase):

    def test_valid(self):
        s = _status()
        map_manual_control(SimpleNamespace(valid=True), s)
        self.assertTrue(s.rc_link_ok)

    def test_invalid(self):
        s = _status()
        map_manual_control(SimpleNamespace(valid=False), s)
        self.assertFalse(s.rc_link_ok)


if __name__ == '__main__':
    unittest.main()
