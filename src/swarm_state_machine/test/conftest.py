import sys
from unittest.mock import MagicMock

sys.modules.setdefault('swarm_interfaces', MagicMock())
sys.modules.setdefault('swarm_interfaces.msg', MagicMock())
sys.modules.setdefault('rclpy', MagicMock())
sys.modules.setdefault('rclpy.node', MagicMock())
