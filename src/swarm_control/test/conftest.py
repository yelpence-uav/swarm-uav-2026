import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# KARDES PAKETLER de yola ekleniyor (20 Agustos 2026). esp32_bridge
# swarm_core.formation_control.formation_geometry'yi import ediyor; colcon
# ortaminda ikisi de kurulu ama duz `pytest` ile kosulunca
# "No module named 'swarm_core'" cikiyordu. test_formasyon_montaj.py bu
# yuzden yerelde HIC kosmuyordu.
_src = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
for _paket in ('swarm_core', 'swarm_interfaces', 'swarm_state_machine'):
    _yol = os.path.join(_src, _paket)
    if os.path.isdir(_yol) and _yol not in sys.path:
        sys.path.append(_yol)


class DummyNode:
    """rclpy.node.Node yerine gecen kabuk (swarm_core/test/conftest.py ile ayni).

    Dugum siniflarini `object.__new__` ile kurup metotlarini tek tek test
    edebilmek icin gerekli — __init__ hic cagrilmiyor, ama sinifin MIRAS
    ALDIGI Node'un import edilebilmesi gerekiyor.
    """

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

    def create_service(self, *args, **kwargs):
        return MagicMock()


# swarm_interfaces taklit ediliyor: birim testler ROS ortami kurmadan kossun.
#
# ENTEGRASYON TESTINDE TAKLIT EDILMEZ. test_entegrasyon_formasyon.py gercek
# ROS dugumu baslatip GERCEK mesaj yayinliyor; MagicMock ile
# create_publisher() "_TYPE_SUPPORT yok" diye patliyor (yasandi). O yuzden
# YELPENCE_ENTEGRASYON=1 iken gercek paketler kullanilir.
#
# `setdefault` bilincli: swarm_interfaces zaten import edilmisse ustune
# yazmiyoruz.
if not os.environ.get('YELPENCE_ENTEGRASYON'):
    sys.modules.setdefault('swarm_interfaces', MagicMock())
    sys.modules.setdefault('swarm_interfaces.msg', MagicMock())
    sys.modules.setdefault('swarm_interfaces.srv', MagicMock())

    # rclpy de taklit ediliyor (20 Agustos 2026). Oncesinde YALNIZ
    # swarm_interfaces taklit ediliyordu, yani rclpy import eden dugum
    # dosyalari (esp32_bridge_node, px4_bridge) birim testten HIC
    # gecirilemiyordu — P0.12(b) duzeltmesi testi yazilirken cikti.
    _rclpy_node = MagicMock()
    _rclpy_node.Node = DummyNode
    sys.modules.setdefault('rclpy', MagicMock())
    sys.modules['rclpy.node'] = _rclpy_node
    sys.modules.setdefault('rclpy.qos', MagicMock())
    sys.modules.setdefault('rclpy.time', MagicMock())
    sys.modules.setdefault('rclpy.duration', MagicMock())
    sys.modules.setdefault('rclpy.callback_groups', MagicMock())
    sys.modules.setdefault('std_msgs', MagicMock())
    sys.modules.setdefault('std_msgs.msg', MagicMock())
    sys.modules.setdefault('geometry_msgs', MagicMock())
    sys.modules.setdefault('geometry_msgs.msg', MagicMock())
    sys.modules.setdefault('mavros_msgs', MagicMock())
    sys.modules.setdefault('mavros_msgs.msg', MagicMock())
    sys.modules.setdefault('mavros_msgs.srv', MagicMock())
    sys.modules.setdefault('sensor_msgs', MagicMock())
    sys.modules.setdefault('sensor_msgs.msg', MagicMock())
