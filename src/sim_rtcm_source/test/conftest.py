"""pytest hazirlik dosyasi.

ROS2 olmadan test kosmak icin rclpy/std_msgs mock'lanir.
swarm_control cross-validation icin sys.path'e eklenir.
"""

import os
import sys
from unittest.mock import MagicMock


sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), '..')
)

# swarm_control: capraz CRC24Q dogrulamasi icin
_SWARM_CONTROL_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), '..', '..',
        'swarm_control',
    )
)
sys.path.insert(0, _SWARM_CONTROL_PATH)

# ROS2 mock
sys.modules.setdefault('rclpy', MagicMock())
sys.modules.setdefault('rclpy.node', MagicMock())
sys.modules.setdefault('std_msgs', MagicMock())
sys.modules.setdefault('std_msgs.msg', MagicMock())
