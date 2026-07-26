import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class DummyNode:

    def __init__(self, *args, **kwargs):
        pass

    def declare_parameter(self, *args, **kwargs):
        pass

    def get_parameter(self, name):
        class DummyParam:
            value = None
        return DummyParam()

    def get_logger(self):
        return MagicMock()

    def create_publisher(self, *args, **kwargs):
        return MagicMock()

    def create_subscription(self, *args, **kwargs):
        return MagicMock()

    def create_timer(self, *args, **kwargs):
        return MagicMock()

    def create_client(self, *args, **kwargs):
        return MagicMock()


# Mock rclpy.node
rclpy_node_mock = MagicMock()
rclpy_node_mock.Node = DummyNode

sys.modules.setdefault('swarm_interfaces', MagicMock())
sys.modules.setdefault('swarm_interfaces.msg', MagicMock())
sys.modules.setdefault('swarm_interfaces.srv', MagicMock())
sys.modules.setdefault('swarm_interfaces.action', MagicMock())
sys.modules.setdefault('rclpy', MagicMock())
sys.modules['rclpy.node'] = rclpy_node_mock
sys.modules.setdefault('rclpy.qos', MagicMock())
sys.modules.setdefault('rclpy.time', MagicMock())
sys.modules.setdefault('rclpy.action', MagicMock())
sys.modules.setdefault('std_msgs', MagicMock())
sys.modules.setdefault('std_msgs.msg', MagicMock())
