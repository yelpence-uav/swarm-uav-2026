import sys
from unittest.mock import MagicMock

sys.modules.setdefault('swarm_interfaces', MagicMock())
sys.modules.setdefault('swarm_interfaces.msg', MagicMock())


class DummyNode:
    """rclpy.node.Node yerine gecen kabuk (swarm_control/test/conftest.py
    ile ayni desen).

    Node bir MagicMock olsaydi ondan TUREYEN sinif da mock olurdu ve
    `object.__new__(MissionFsmNode)` "X is not a type object" ile
    patlardi. Dugum siniflarini __init__ CAGIRMADAN kurup metotlarini tek
    tek sinayabilmek icin gercek bir sinif gerekiyor.
    """

    def __init__(self, *args, **kwargs):
        pass

    def declare_parameter(self, *a, **k): pass

    def get_parameter(self, name):
        class _P:
            value = None
        return _P()

    def get_logger(self): return MagicMock()

    def create_publisher(self, *a, **k): return MagicMock()

    def create_subscription(self, *a, **k): return MagicMock()

    def create_timer(self, *a, **k): return MagicMock()

    def create_client(self, *a, **k): return MagicMock()

    def create_service(self, *a, **k): return MagicMock()


_rclpy_node = MagicMock()
_rclpy_node.Node = DummyNode
sys.modules.setdefault('rclpy', MagicMock())
sys.modules['rclpy.node'] = _rclpy_node

# 4 Eylul 2026: asagidakiler eklenene kadar `mission_fsm_node` HIC birim
# testine sokulamiyordu — modul `from rclpy.qos import ...` yaptigi anda
# "No module named 'rclpy.qos'" ile patliyordu. Yalniz `rclpy`'yi taklit
# etmek yetmiyor: MagicMock bir PAKET degil, alt modul cozumlemesi
# yapilamiyor. Dugum sinifi `object.__new__` ile kurulup metotlari tek tek
# sinanabilsin diye alt moduller de tabloya konuyor.
sys.modules.setdefault('rclpy.qos', MagicMock())
sys.modules.setdefault('rclpy.action', MagicMock())
sys.modules.setdefault('rclpy.duration', MagicMock())
sys.modules.setdefault('std_msgs', MagicMock())
sys.modules.setdefault('std_msgs.msg', MagicMock())
sys.modules.setdefault('geometry_msgs', MagicMock())
sys.modules.setdefault('geometry_msgs.msg', MagicMock())
sys.modules.setdefault('swarm_interfaces.action', MagicMock())
sys.modules.setdefault('swarm_interfaces.srv', MagicMock())
