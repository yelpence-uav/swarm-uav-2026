import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

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
