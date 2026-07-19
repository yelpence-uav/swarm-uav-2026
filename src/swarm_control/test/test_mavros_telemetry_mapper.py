import math
import unittest
from types import SimpleNamespace

from swarm_control.px4_interface.mavros_telemetry_mapper import (
    MODE_STR_TO_FLIGHT_MODE,
    _enu_to_ned,
    _quat_to_heading_ned_deg,
    _quat_to_roll_pitch_deg,
    map_battery,
    map_estimator_status,
    map_gps_raw,
    map_odometry,
    map_rc_in,
    map_state,
)


def _status():
    return SimpleNamespace(
        battery_voltage_v=0.0, battery_current_a=0.0, battery_percent=0.0,
        armed=False, failsafe_active=False, px4_link_ok=False,
        flight_mode=0, offboard_active=False, offboard_enabled=False,
        pilot_override_active=False,
        pos_x=0.0, pos_y=0.0, pos_z=0.0,
        vel_x=0.0, vel_y=0.0, vel_z=0.0,
        xy_valid=False, z_valid=False, v_xy_valid=False,
        imu_healthy=False, estimator_ok=False, mag_healthy=False,
        baro_healthy=False, heading_deg=0.0, roll_deg=0.0, pitch_deg=0.0,
        rc_link_ok=False,
        gps_fix_type=0, gps_satellites=0, gps_hdop=0.0,
    )


class TestGpsRaw(unittest.TestCase):

    def test_hdop_scaled_from_eph(self):
        # eph = HDOP*100 -> hdop = 1.20
        st = _status()
        map_gps_raw(
            SimpleNamespace(fix_type=3, satellites_visible=10, eph=120),
            st,
        )
        self.assertAlmostEqual(st.gps_hdop, 1.2)
        self.assertEqual(st.gps_fix_type, 3)
        self.assertEqual(st.gps_satellites, 10)

    def test_hdop_unknown_is_conservative(self):
        # eph=UINT16_MAX (bilinmiyor) -> yuksek/kotu hdop (kapi acik kalir)
        st = _status()
        map_gps_raw(
            SimpleNamespace(fix_type=0, satellites_visible=0, eph=65535),
            st,
        )
        self.assertGreaterEqual(st.gps_hdop, 1.5)


class TestEnuToNed(unittest.TestCase):

    def test_swap_and_negate(self):
        # ENU (Dogu, Kuzey, Yukari) -> NED (Kuzey, Dogu, Asagi)
        self.assertEqual(_enu_to_ned(1.0, 2.0, 3.0), (2.0, 1.0, -3.0))

    def test_involutif(self):
        # Ayni formul iki kez -> baslangica doner
        once = _enu_to_ned(4.0, -5.0, 6.0)
        twice = _enu_to_ned(*once)
        self.assertEqual(twice, (4.0, -5.0, 6.0))


class TestAttitude(unittest.TestCase):

    def test_north_facing_heading_zero(self):
        # Kuzeye bakan drone: ENU yaw 90 -> NED heading 0
        qz = math.sin(math.radians(90) / 2.0)
        qw = math.cos(math.radians(90) / 2.0)
        h = _quat_to_heading_ned_deg(0.0, 0.0, qz, qw)
        self.assertAlmostEqual(h, 0.0, places=3)

    def test_identity_roll_pitch_zero(self):
        r, p = _quat_to_roll_pitch_deg(0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(r, 0.0, places=3)
        self.assertAlmostEqual(p, 0.0, places=3)


class TestState(unittest.TestCase):

    def test_offboard(self):
        st = _status()
        msg = SimpleNamespace(
            connected=True, armed=True, mode='OFFBOARD', system_status=4,
        )
        map_state(msg, st)
        self.assertTrue(st.px4_link_ok)
        self.assertTrue(st.armed)
        self.assertEqual(st.flight_mode, MODE_STR_TO_FLIGHT_MODE['OFFBOARD'])
        self.assertTrue(st.offboard_active)
        self.assertFalse(st.failsafe_active)

    def test_failsafe_proxy_critical(self):
        st = _status()
        msg = SimpleNamespace(
            connected=True, armed=True, mode='AUTO.LAND', system_status=5,
        )
        map_state(msg, st)
        self.assertTrue(st.failsafe_active)


class TestBattery(unittest.TestCase):

    def test_percentage_and_current(self):
        st = _status()
        msg = SimpleNamespace(voltage=15.2, current=-5.0, percentage=0.8)
        map_battery(msg, st)
        self.assertAlmostEqual(st.battery_voltage_v, 15.2)
        self.assertAlmostEqual(st.battery_current_a, 5.0)  # mutlak
        self.assertAlmostEqual(st.battery_percent, 80.0)

    def test_nan_safe(self):
        st = _status()
        msg = SimpleNamespace(
            voltage=float('nan'), current=float('nan'),
            percentage=float('nan'),
        )
        map_battery(msg, st)
        self.assertEqual(st.battery_voltage_v, 0.0)
        self.assertEqual(st.battery_current_a, 0.0)
        self.assertEqual(st.battery_percent, 0.0)


class TestOdometry(unittest.TestCase):

    def test_enu_to_ned_pos_vel(self):
        st = _status()
        pos = SimpleNamespace(x=1.0, y=2.0, z=3.0)
        orient = SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0)
        lin = SimpleNamespace(x=0.5, y=-0.5, z=1.0)
        msg = SimpleNamespace(
            pose=SimpleNamespace(
                pose=SimpleNamespace(position=pos, orientation=orient)),
            twist=SimpleNamespace(twist=SimpleNamespace(linear=lin)),
        )
        map_odometry(msg, st)
        self.assertEqual((st.pos_x, st.pos_y, st.pos_z), (2.0, 1.0, -3.0))
        self.assertEqual((st.vel_x, st.vel_y, st.vel_z), (-0.5, 0.5, -1.0))
        self.assertTrue(st.xy_valid and st.z_valid and st.v_xy_valid)


class TestEstimator(unittest.TestCase):

    def test_flags(self):
        st = _status()
        msg = SimpleNamespace(
            attitude_status_flag=True,
            pos_horiz_abs_status_flag=True,
            pos_vert_abs_status_flag=False,
        )
        map_estimator_status(msg, st)
        self.assertTrue(st.imu_healthy)
        self.assertTrue(st.estimator_ok)
        self.assertFalse(st.baro_healthy)


class TestRcIn(unittest.TestCase):

    def test_channels_present(self):
        st = _status()
        map_rc_in(SimpleNamespace(channels=[1500, 1500, 1000]), st)
        self.assertTrue(st.rc_link_ok)

    def test_channels_empty(self):
        st = _status()
        map_rc_in(SimpleNamespace(channels=[]), st)
        self.assertFalse(st.rc_link_ok)


if __name__ == '__main__':
    unittest.main()
