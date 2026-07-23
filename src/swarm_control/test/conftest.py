import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

sys.modules.setdefault('swarm_interfaces', MagicMock())
sys.modules.setdefault('swarm_interfaces.msg', MagicMock())
