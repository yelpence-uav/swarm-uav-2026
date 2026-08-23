#!/usr/bin/env python3
"""G0-1 · DIKEY DATUM TESTI — dikey yol vermenin TEK temel varsayimi.

NEDEN VAR (23 Agustos 2026)
Dikey kacis, komsunun irtifasini kendi irtifamla karsilastirarak calisiyor.
Iki taraf AYNI referansi kullanmazsa sonuc sabit bir yanlilik tasir ve ucak
"zaten yeterince yukaridayim" sanip HIC kacmaz — hicbir hata vermeden.

Bir kez tam bu hata vardi ve duzeltildi (komsu_adaptoru.py DIKEY bolumu):
    ben.pos_z   : MAVROS odometry = EKF YEREL NED, boot'a bagli ~10 m kayar
    komsu.pos_z : mesh POSE = -(alt_amsl - home_amsl), komsunun kalkis noktasi
Ikisi cikarilinca ortaya 10 m mertebesinde bir hayalet fark cikiyordu.

BU TEST NE OLCER
Iki ucak da YERDE, kendi kalkis noktalarindayken adaptorun urettigi
`rel_z` SIFIRA yakin olmali. Cikan fark, iki kalkis noktasi arasindaki
KOT FARKIDIR ve kaydedilmelidir: dikey ayrima dogrudan yanlilik olarak
biner (katman 3.0 m; 0.5 m fark %17 demek).

KULLANIM (ucakta, konteyner icinde)
    python3 - <agent_id> <komsu_id> [saniye]  < g0_dikey_datum.py

GECME OLCUTU
    |rel_z| < 0.5 m   -> GECTI
    0.5 - 1.0 m       -> KAYDET, katman payindan dusulur
    > 1.0 m           -> KALDI, sebep bulunmadan dikey kip UCMAZ
"""
import math
import statistics
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile,
                       ReliabilityPolicy)

from swarm_interfaces.msg import AgentStatus
from swarm_core.collision_avoidance.komsu_adaptoru import agent_status_to_obs

BEST_EFFORT = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


class DatumTesti(Node):
    def __init__(self, aid, nid, sure):
        super().__init__('g0_dikey_datum')
        self._aid, self._nid, self._sure = aid, nid, sure
        self._ben = None
        self._komsu = None
        self._rel_z = []
        self._rel_xy = []
        self._neden = {}
        self._t0 = time.monotonic()
        self.create_subscription(
            AgentStatus, f'/swarm/agent/drone{aid}/telemetry',
            self._on_ben, BEST_EFFORT)
        self.create_subscription(
            AgentStatus, f'/swarm/public/drone{nid}/status',
            self._on_komsu, BEST_EFFORT)
        self.create_timer(0.1, self._tik)

    def _on_ben(self, m):
        self._ben = m

    def _on_komsu(self, m):
        self._komsu = m

    def _tik(self):
        if time.monotonic() - self._t0 >= self._sure:
            raise SystemExit
        if self._ben is None or self._komsu is None:
            return
        obs, neden = agent_status_to_obs(
            self._komsu, self._ben, komsu_id=self._nid)
        if obs is None:
            self._neden[neden] = self._neden.get(neden, 0) + 1
            return
        self._rel_z.append(obs.rel_z)
        self._rel_xy.append(math.hypot(obs.rel_x, obs.rel_y))

    def rapor(self):
        print()
        if self._ben is None:
            print('🔴 KENDI telemetrim GELMEDI — agent_fsm kosuyor mu?')
            return 1
        if self._komsu is None:
            print(f'🔴 KOMSU drone{self._nid} verisi GELMEDI — mesh?')
            return 1
        b, k = self._ben, self._komsu
        ben_h = b.alt_amsl_m - b.home_alt_amsl_m
        komsu_h = -k.pos_z
        print(f'  benim  (drone{self._aid}): alt_amsl {b.alt_amsl_m:9.2f}  '
              f'home {b.home_alt_amsl_m:9.2f}  -> irtifa {ben_h:+.2f} m')
        print(f'  komsu  (drone{self._nid}): mesh pos_z {k.pos_z:+9.2f}'
              f'{"":21}-> irtifa {komsu_h:+.2f} m')
        print(f'  gps_fix: ben {b.gps_fix_type}  komsu {k.gps_fix_type}')
        if self._neden:
            print(f'  ⚠ adaptor atlamalari: {self._neden}')
        if not self._rel_z:
            print('🔴 Adaptor HIC gozlem uretmedi — yukaridaki atlama '
                  'nedenine bak.')
            return 1
        ort = statistics.mean(self._rel_z)
        print(f'\n  rel_z  ortalama {ort:+.3f} m  ·  '
              f'min {min(self._rel_z):+.3f}  maks {max(self._rel_z):+.3f}  '
              f'({len(self._rel_z)} ornek)')
        print(f'  yatay ayrim     {statistics.mean(self._rel_xy):.2f} m '
              f'(iki ucagin gercek mesafesiyle karsilastir)')
        m = abs(ort)
        if m < 0.5:
            print(f'\n  ✅ GECTI — datum tutarli (|{ort:+.2f}| < 0.50 m)')
            return 0
        if m < 1.0:
            print(f'\n  🟠 KAYDET — {ort:+.2f} m kot farki var. Katman '
                  f'3.0 m; bu fark dikey ayrima yanlilik olarak biner.')
            return 0
        print(f'\n  🔴 KALDI — {ort:+.2f} m. Iki ucak da yerdeyken bu fark '
              f'OLMAMALI. Sebep bulunmadan dikey kip UCMAZ.')
        return 1


def main():
    aid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    nid = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    sure = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
    print(f'G0-1 DIKEY DATUM · ben drone{aid} · komsu drone{nid} · {sure:.0f} sn')
    rclpy.init()
    d = DatumTesti(aid, nid, sure)
    try:
        rclpy.spin(d)
    except SystemExit:
        pass
    kod = d.rapor()
    d.destroy_node()
    rclpy.shutdown()
    return kod


if __name__ == '__main__':
    sys.exit(main())
