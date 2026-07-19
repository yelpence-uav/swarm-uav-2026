import math
import unittest
from unittest.mock import MagicMock

# mavros_msgs modul seviyesinde import edildigi icin (telemetry_mapper'in
# aksine) bu testler ROS ortami olmadan calisamaz; yoksa atlanir.
try:
    from builtin_interfaces.msg import Time
    from mavros_msgs.msg import PositionTarget

    from swarm_control.px4_interface.mavros_command_sender import (
        _MASK_POS_VEL,
        _MASK_POSITION,
        _MASK_VELOCITY,
        MavrosCommandSender,
        _ned_to_enu,
        _yaw_ned_to_enu,
    )
    _ROS_VAR = True
except ImportError:
    _ROS_VAR = False


def _mock_node():
    """create_client/create_publisher'i MagicMock donduren sahte node."""
    node = MagicMock()
    node.get_clock.return_value.now.return_value.to_msg.return_value = (
        Time()
    )
    return node


@unittest.skipUnless(_ROS_VAR, 'mavros_msgs/ROS ortami yok')
class TestNedToEnu(unittest.TestCase):

    def test_swap_and_negate(self):
        # NED (Kuzey, Dogu, Asagi) -> ENU (Dogu, Kuzey, Yukari)
        self.assertEqual(_ned_to_enu(1.0, 2.0, 3.0), (2.0, 1.0, -3.0))

    def test_involutif(self):
        # Ayni formul iki kez -> baslangica doner
        once = _ned_to_enu(4.0, -5.0, 6.0)
        twice = _ned_to_enu(*once)
        self.assertEqual(twice, (4.0, -5.0, 6.0))


@unittest.skipUnless(_ROS_VAR, 'mavros_msgs/ROS ortami yok')
class TestYawNedToEnu(unittest.TestCase):

    def test_north(self):
        # NED yaw 0 (Kuzey) -> ENU'da Kuzey = +pi/2
        self.assertAlmostEqual(_yaw_ned_to_enu(0.0), math.pi / 2.0)

    def test_east(self):
        # NED yaw +90 (Dogu) -> ENU'da Dogu = 0
        self.assertAlmostEqual(
            _yaw_ned_to_enu(math.pi / 2.0), 0.0, places=9
        )

    def test_wrap_range(self):
        # Sonuc her zaman [-pi, pi] araliginda kalmali
        for deg in range(-360, 361, 30):
            yaw = _yaw_ned_to_enu(math.radians(deg))
            self.assertGreaterEqual(yaw, -math.pi)
            self.assertLessEqual(yaw, math.pi)


@unittest.skipUnless(_ROS_VAR, 'mavros_msgs/ROS ortami yok')
class TestMasks(unittest.TestCase):

    def test_position_mask_ignores_velocity(self):
        pt = PositionTarget
        self.assertTrue(_MASK_POSITION & pt.IGNORE_VX)
        self.assertFalse(_MASK_POSITION & pt.IGNORE_PX)
        self.assertFalse(_MASK_POSITION & pt.IGNORE_YAW)

    def test_velocity_mask_ignores_position(self):
        pt = PositionTarget
        self.assertTrue(_MASK_VELOCITY & pt.IGNORE_PX)
        self.assertFalse(_MASK_VELOCITY & pt.IGNORE_VX)

    def test_pos_vel_mask_keeps_both(self):
        pt = PositionTarget
        self.assertFalse(_MASK_POS_VEL & pt.IGNORE_PX)
        self.assertFalse(_MASK_POS_VEL & pt.IGNORE_VX)
        self.assertTrue(_MASK_POS_VEL & pt.IGNORE_AFX)


@unittest.skipUnless(_ROS_VAR, 'mavros_msgs/ROS ortami yok')
class TestNamespaceWiring(unittest.TestCase):

    def test_client_and_topic_names(self):
        node = _mock_node()
        MavrosCommandSender(node, namespace='/drone_1')

        client_names = [
            c.args[1] for c in node.create_client.call_args_list
        ]
        self.assertIn('/drone_1/mavros/cmd/arming', client_names)
        self.assertIn('/drone_1/mavros/set_mode', client_names)

        pub_names = [
            c.args[1] for c in node.create_publisher.call_args_list
        ]
        self.assertIn('/drone_1/mavros/setpoint_raw/local', pub_names)
        self.assertIn(
            '/drone_1/mavros/global_position/set_gp_origin', pub_names
        )


@unittest.skipUnless(_ROS_VAR, 'mavros_msgs/ROS ortami yok')
class TestArming(unittest.TestCase):

    def test_arm_calls_service(self):
        node = _mock_node()
        sender = MavrosCommandSender(node)
        sender._arm_client.service_is_ready.return_value = True
        sender.arm()
        req = sender._arm_client.call_async.call_args.args[0]
        self.assertTrue(req.value)

    def test_disarm_calls_service(self):
        node = _mock_node()
        sender = MavrosCommandSender(node)
        sender._arm_client.service_is_ready.return_value = True
        sender.disarm()
        req = sender._arm_client.call_async.call_args.args[0]
        self.assertFalse(req.value)

    def test_service_not_ready_no_call(self):
        # Servis hazir degilse cagri YAPILMAZ, sadece uyari loglanir
        node = _mock_node()
        sender = MavrosCommandSender(node)
        sender._arm_client.service_is_ready.return_value = False
        sender.arm()
        sender._arm_client.call_async.assert_not_called()


@unittest.skipUnless(_ROS_VAR, 'mavros_msgs/ROS ortami yok')
class TestModes(unittest.TestCase):

    def _mode_of(self, method_name):
        node = _mock_node()
        sender = MavrosCommandSender(node)
        sender._mode_client.service_is_ready.return_value = True
        getattr(sender, method_name)()
        return sender._mode_client.call_async.call_args.args[0].custom_mode

    def test_offboard(self):
        self.assertEqual(self._mode_of('set_offboard_mode'), 'OFFBOARD')

    def test_land(self):
        self.assertEqual(self._mode_of('land'), 'AUTO.LAND')

    def test_return_home(self):
        self.assertEqual(self._mode_of('return_home'), 'AUTO.RTL')

    def test_offboard_mode_notifiers_are_noop(self):
        # MAVROS'ta OffboardControlMode yok; bu metotlar no-op olmali
        node = _mock_node()
        sender = MavrosCommandSender(node)
        sender.publish_offboard_position_mode()
        sender.publish_offboard_velocity_mode()
        sender.publish_offboard_position_velocity_mode()
        sender._setpoint_pub.publish.assert_not_called()


@unittest.skipUnless(_ROS_VAR, 'mavros_msgs/ROS ortami yok')
class TestSetpoints(unittest.TestCase):

    def test_position_setpoint_ned_to_enu(self):
        node = _mock_node()
        sender = MavrosCommandSender(node)
        # NED: 10m Kuzey, 5m Dogu, 20m irtifa (z=-20)
        sender.publish_position_setpoint(10.0, 5.0, -20.0, yaw_rad=0.0)
        msg = sender._setpoint_pub.publish.call_args.args[0]
        self.assertAlmostEqual(msg.position.x, 5.0)   # ENU x = Dogu
        self.assertAlmostEqual(msg.position.y, 10.0)  # ENU y = Kuzey
        self.assertAlmostEqual(msg.position.z, 20.0)  # ENU z = Yukari
        self.assertEqual(msg.type_mask, _MASK_POSITION)
        self.assertEqual(
            msg.coordinate_frame, PositionTarget.FRAME_LOCAL_NED
        )
        self.assertAlmostEqual(msg.yaw, math.pi / 2.0)

    def test_velocity_setpoint_ned_to_enu(self):
        node = _mock_node()
        sender = MavrosCommandSender(node)
        # NED hiz: 1 Kuzey, 2 Dogu, 0.5 asagi
        sender.publish_velocity_setpoint(1.0, 2.0, 0.5)
        msg = sender._setpoint_pub.publish.call_args.args[0]
        self.assertAlmostEqual(msg.velocity.x, 2.0)
        self.assertAlmostEqual(msg.velocity.y, 1.0)
        self.assertAlmostEqual(msg.velocity.z, -0.5)
        self.assertEqual(msg.type_mask, _MASK_VELOCITY)

    def test_position_velocity_setpoint(self):
        node = _mock_node()
        sender = MavrosCommandSender(node)
        sender.publish_position_velocity_setpoint(
            10.0, 5.0, -20.0, 1.0, 2.0, 0.5
        )
        msg = sender._setpoint_pub.publish.call_args.args[0]
        self.assertAlmostEqual(msg.position.x, 5.0)
        self.assertAlmostEqual(msg.velocity.x, 2.0)
        self.assertEqual(msg.type_mask, _MASK_POS_VEL)


@unittest.skipUnless(_ROS_VAR, 'mavros_msgs/ROS ortami yok')
class TestGlobalOrigin(unittest.TestCase):

    def test_origin_publish(self):
        node = _mock_node()
        sender = MavrosCommandSender(node)
        sender.set_gps_global_origin(41.0441269, 29.0016997, 0.48)
        msg = sender._origin_pub.publish.call_args.args[0]
        self.assertAlmostEqual(msg.position.latitude, 41.0441269)
        self.assertAlmostEqual(msg.position.longitude, 29.0016997)
        self.assertAlmostEqual(msg.position.altitude, 0.48)


if __name__ == '__main__':
    unittest.main()
