"""pytest paylaşılan fixture/konfigürasyon dosyası.

swarm_interfaces gibi ROS2 mesajları test ortamında ham Python ile
sağlanamaz; MagicMock ile yerine geçici nesne koyup birim testlerin
mesaj alanlarını okuyup yazabilmesini sağlıyoruz.
"""

import os
import sys
from unittest.mock import MagicMock


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _agent_status_proxy():
    """Gerçek AgentStatus alan davranışını taklit eden hafif proxy."""
    proxy = MagicMock()
    # Test kodunda struct gibi davranabilsin diye getattr/setattr açık
    proxy.pos_x = 0.0
    proxy.pos_y = 0.0
    proxy.pos_z = 0.0
    proxy.vel_x = 0.0
    proxy.vel_y = 0.0
    proxy.vel_z = 0.0
    proxy.state = 0
    proxy.origin_synced = True
    proxy.xy_valid = True
    proxy.z_valid = True
    proxy.v_xy_valid = True
    return proxy


# AgentStatus için module-level enum sabitlerini de simüle et
_agent_status_class = MagicMock(side_effect=_agent_status_proxy)
_agent_status_class.STATE_UNKNOWN = 0
_agent_status_class.STATE_IDLE = 1
_agent_status_class.STATE_ARMING = 2
_agent_status_class.STATE_ARMED = 3
_agent_status_class.STATE_TAKEOFF = 4
_agent_status_class.STATE_IN_SWARM = 5
_agent_status_class.STATE_EXECUTING_TASK = 6
_agent_status_class.STATE_DETACHED = 7
_agent_status_class.STATE_PRECISION_LANDING = 8
_agent_status_class.STATE_WAITING_REJOIN = 9
_agent_status_class.STATE_REJOINING = 10
_agent_status_class.STATE_RETURN_HOME = 11
_agent_status_class.STATE_LANDING = 12
_agent_status_class.STATE_LANDED = 13
_agent_status_class.STATE_FAILSAFE = 14
_agent_status_class.STATE_STANDBY = 15

_msg_module = MagicMock()
_msg_module.AgentStatus = _agent_status_class
_msg_module.NeighborInfo = MagicMock()

sys.modules.setdefault('swarm_interfaces', MagicMock())
sys.modules.setdefault('swarm_interfaces.msg', _msg_module)

# rclpy modülleri de test ortamında yok; node'u import edebilelim diye mock
sys.modules.setdefault('rclpy', MagicMock())
sys.modules.setdefault('rclpy.node', MagicMock())
sys.modules.setdefault('rclpy.qos', MagicMock())
sys.modules.setdefault('rclpy.time', MagicMock())
