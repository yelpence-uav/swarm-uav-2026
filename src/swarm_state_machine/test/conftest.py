import sys
from unittest.mock import MagicMock

sys.modules.setdefault('swarm_interfaces', MagicMock())
sys.modules.setdefault('swarm_interfaces.msg', MagicMock())
sys.modules.setdefault('px4_msgs', MagicMock())
sys.modules.setdefault('px4_msgs.msg', MagicMock())
sys.modules.setdefault('rclpy', MagicMock())
sys.modules.setdefault('rclpy.node', MagicMock())
