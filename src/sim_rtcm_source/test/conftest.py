"""pytest paylasilan hazirlik dosyasi.

Birim testler ROS2 ortami olmadan koshturulabilsin diye rclpy ve
std_msgs MagicMock ile yer degistirilir. swarm_control paketinin
rtk_bridge.rtcm_packing modulu cross-validation icin sys.path'e
eklenir (Faz 1 crc24q'sini kullanmak istiyoruz).
"""

import os
import sys
from unittest.mock import MagicMock


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# swarm_control sister paketten rtk_bridge.rtcm_packing icin sys.path
_SWARM_CONTROL_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), '..', '..',
        'swarm_control',
    )
)
sys.path.insert(0, _SWARM_CONTROL_PATH)

# rclpy + std_msgs mock (sim_rtcm_source_node import edilirse)
sys.modules.setdefault('rclpy', MagicMock())
sys.modules.setdefault('rclpy.node', MagicMock())
sys.modules.setdefault('std_msgs', MagicMock())
sys.modules.setdefault('std_msgs.msg', MagicMock())
