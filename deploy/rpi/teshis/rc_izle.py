#!/usr/bin/env python3
"""RC kanal araligi izleyici — "kumanda hangi ucaga bagli" OLCEREK kapanir.

NEDEN VAR: kumanda-ucak eslesmesi tahminle degil olcumle bilinmeli
(YAPILACAKLAR 6). Yontem: yalniz sinanan kumanda ACIKKEN bu betik
kosturulur; operator SAG cubugu saga-sola oynatir. Bagli ucakta ch1/ch2
tam menzil gezer (fark ~1000), digerlerinde HIC mesaj akmaz.

24 Agustos 2026, ylp00'da olculdu: 383 mesaj/20 sn (19 Hz), cubukla
ch1 1011-2001; ayni anda ylp02'de sifir mesaj -> kumanda ylp00'un.

⚠️ Operatore GAZ ve YAW'a dokunmamasini soyle — gaz-alt + yaw
kombinasyonu ARM edebilir ve pervaneler takili.

Kullanim (YKI'den, konteynere stdin ile):
    ./deploy/yki/drone_bul.sh ylp00 'docker exec -i drone1 bash -lc \
        "source /opt/ros/jazzy/setup.bash && python3 - drone_1"' \
        < deploy/rpi/teshis/rc_izle.py
Argumanlar: [1] ros ad alani (varsayilan drone_1), [2] sure sn (20).
"""
import sys
import time

import rclpy
from mavros_msgs.msg import RCIn
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

NS = sys.argv[1] if len(sys.argv) > 1 else 'drone_1'
SURE_S = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
# Cubuk tam menzili ~1000 birim; 80 esigi el titremesi ile bilincli
# hareketi ayirir (olculen: dokunulmayan kanal farki 1-2 birim).
OYNADI_ESIK = 80

rclpy.init()
n = Node('rc_izle')
kanallar: dict[int, tuple[int, int]] = {}
sayac = [0]


def cb(m: RCIn) -> None:
    sayac[0] += 1
    for i, v in enumerate(m.channels[:6]):
        lo, hi = kanallar.get(i, (v, v))
        kanallar[i] = (min(lo, v), max(hi, v))


# mavros rc/in SENSOR QoS (best-effort) yayinlar; varsayilan guvenilir
# abonelik eslesmez ve SESSIZCE hic mesaj gelmez — o yuzden sensor_data.
n.create_subscription(RCIn, f'/{NS}/mavros/rc/in', cb,
                      qos_profile_sensor_data)
t0 = time.time()
while time.time() - t0 < SURE_S:
    rclpy.spin_once(n, timeout_sec=0.5)

print(f'mesaj: {sayac[0]} ({SURE_S:.0f} sn, /{NS}/mavros/rc/in)')
if not sayac[0]:
    print('RC VERISI YOK — bu ucak acik kumandayi GORMUYOR '
          '(ya kumanda kapali ya baska ucagin)')
for i, (lo, hi) in sorted(kanallar.items()):
    isaret = '  <-- OYNADI' if hi - lo > OYNADI_ESIK else ''
    print(f'ch{i + 1}: {lo}-{hi}  fark={hi - lo}{isaret}')
