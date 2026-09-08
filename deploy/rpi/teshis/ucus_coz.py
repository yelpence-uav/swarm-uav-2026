#!/usr/bin/env python3
# Copyright 2026 Yelpence
"""UÇUŞ SONRASI ÇÖZÜMLEYİCİ — bag'i açar, standart soruları cevaplar.

KONTEYNER İÇİNDE, UÇAĞIN KENDİ BAG'İ ÜZERİNDE koşar:
    docker exec <konteyner> bash -lc \\
        "source /opt/ros/jazzy/setup.bash; source /ws/install/setup.bash; \\
         python3 /ws/ucus_coz.py /ws/kayit/<bag> [t0 t1]"

NİYE VAR (8 Eylül 2026)
-----------------------
O gün operatör iki soru sordu — *"sadece lider irtifa değiştirdi"* ve
*"kanat dronlar bas-çek yaptı"* — ve her ikisi için de bag'i açan
çözümleme betiği ELLE, sıfırdan yazıldı. İkisi de aynı üç şeye bakıyordu.
Bu betik onu kalıcı hale getiriyor: soru gelince tek komut.

O gün bulunanlar ve hangi satırın bulduğu:
    formasyon hedefi 0.72 Hz, aralarında 12.7 sn boşluk   -> HEDEF AKIŞI
    heading tek adımda 32.4 derece sıçradı                -> HEDEF AKIŞI
    setpoint ileribeslemesi |v| 1.22 -> 4.20 m/s          -> SETPOINT
    RETURN_HOME'da 307 sn tek komut yok                   -> KOMUT ARALIĞI

⚠️ BAG HÂLÂ YAZILIYORSA açılmaz ("Could not open ... read failed").
Kopyalayıp yeniden indeksle:
    cp -r <bag> /tmp/b && ros2 bag reindex /tmp/b -s mcap
"""

import math
import sys

import rosbag2_py
from rclpy.serialization import deserialize_message

from swarm_interfaces.msg import AgentSetpoint, AgentStatus, FormationCommand


def _oku(yol, konu, tip, t0, t1):
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=yol, storage_id='mcap'),
           rosbag2_py.ConverterOptions('', ''))
    r.set_filter(rosbag2_py.StorageFilter(topics=[konu]))
    while r.has_next():
        _t, veri, ts = r.read_next()
        t = ts / 1e9
        if t0 <= t <= t1:
            yield t, deserialize_message(veri, tip)


def _yuzde(v, p):
    if not v:
        return float('nan')
    s = sorted(v)
    return s[min(len(s) - 1, int(len(s) * p))]


def hedef_akisi(yol, t0, t1):
    """Formasyon hedefi ne sıklıkla ULAŞTI ve ne kadar sıçradı.

    🔴 EN ÖNEMLİ BÖLÜM. Sürünün takip edebildiği tek şey bu akış; kesilirse
    uçak son hedefte donar (hiçbir yerde hata görünmez) ve hedef yeniden
    gelince ona ATILIR — operatörün "bas-çek" dediği şey budur.
    """
    print('--- FORMASYON HEDEFİ (takipçinin ALDIĞI) ---')
    ts, hdg, mrk = [], [], []
    for t, m in _oku(yol, '/swarm/public/formation/target',
                     FormationCommand, t0, t1):
        ts.append(t)
        hdg.append(float(m.heading_deg))
        mrk.append((float(m.center_x), float(m.center_y), float(m.center_z)))
    if len(ts) < 3:
        print(f'  yalnız {len(ts)} mesaj — akış YOK ya da pencere dar')
        return
    sure = ts[-1] - ts[0]
    dt = sorted(ts[i + 1] - ts[i] for i in range(len(ts) - 1))
    dh = sorted(abs((hdg[i + 1] - hdg[i] + 180) % 360 - 180)
                for i in range(len(hdg) - 1))
    dm = sorted(math.dist(mrk[i], mrk[i + 1]) for i in range(len(mrk) - 1))
    print(f'  {len(ts)} mesaj / {sure:.1f} s = {len(ts) / sure:.2f} Hz')
    print(f'  aralık   medyan {dt[len(dt) // 2] * 1000:6.0f} ms   '
          f'%95 {_yuzde(dt, 0.95) * 1000:6.0f}   MAX {dt[-1] * 1000:7.0f} ms')
    print(f'  heading  medyan {dh[len(dh) // 2]:5.2f}°   '
          f'MAX {dh[-1]:6.2f}°')
    print(f'  merkez   medyan {dm[len(dm) // 2]:5.2f} m   '
          f'MAX {dm[-1]:6.2f} m')
    if dt[-1] > 1.0:
        print(f'  🔴 {dt[-1]:.1f} SANİYELİK BOŞLUK — uçak o süre boyunca son '
              f'hedefte dondu, sonra sıçradı')


def setpoint(yol, ns, t0, t1):
    """Uçağa giden setpoint: adım büyüklüğü ve ileribesleme sıçraması."""
    print(f'\n--- SETPOINT ({ns}) ---')
    sp = list(_oku(yol, f'{ns}/control/setpoint', AgentSetpoint, t0, t1))
    if len(sp) < 3:
        print(f'  yalnız {len(sp)} mesaj')
        return
    adim = sorted(math.hypot(sp[i + 1][1].x - sp[i][1].x,
                             sp[i + 1][1].y - sp[i][1].y)
                  for i in range(len(sp) - 1))
    hiz = sorted(abs(m.vx) + abs(m.vy) for _t, m in sp)
    print(f'  {len(sp)} mesaj, {len(sp) / (sp[-1][0] - sp[0][0]):.1f} Hz')
    print(f'  adım         medyan {adim[len(adim) // 2] * 100:5.1f} cm   '
          f'MAX {adim[-1] * 100:6.1f} cm')
    print(f'  ileribesleme medyan {hiz[len(hiz) // 2]:5.2f}   '
          f'%95 {_yuzde(hiz, 0.95):5.2f}   MAX {hiz[-1]:5.2f} m/s')
    if hiz[-1] > 3 * max(0.1, hiz[len(hiz) // 2]):
        print('  🔴 İLERİBESLEME SIÇRAMASI — hedef büyük adımlarla geliyor '
              '(hedef akışına bak)')


def komsu_mesafe(yol, t0, t1):
    """Uçaklar arası en dar an — mesh'ten gelen komşu durumlarından."""
    print('\n--- UÇAKLAR ARASI EN DAR AN ---')
    izler = {}
    for did in (1, 2, 3):
        for t, m in _oku(yol, f'/swarm/public/drone{did}/status',
                         AgentStatus, t0, t1):
            izler.setdefault(round(t, 1), {})[did] = (
                float(m.pos_x), float(m.pos_y), float(m.pos_z))
    en_dar = (float('inf'), '', 0.0)
    for t, d in izler.items():
        ids = sorted(d)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                m = math.dist(d[ids[i]], d[ids[j]])
                if m < en_dar[0]:
                    en_dar = (m, f'd{ids[i]}-d{ids[j]}', t)
    if en_dar[1]:
        print(f'  {en_dar[0]:.2f} m   {en_dar[1]}   t={en_dar[2]:.1f}')
    else:
        print('  komşu durumu yok (mesh kaydı boş?)')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    yol = sys.argv[1]
    t0 = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    t1 = float(sys.argv[3]) if len(sys.argv) > 3 else float('inf')
    ns = sys.argv[4] if len(sys.argv) > 4 else '/drone_1'
    print(f'=== {yol}   pencere [{t0:.0f}, {t1:.0f}] ===\n')
    hedef_akisi(yol, t0, t1)
    setpoint(yol, ns, t0, t1)
    komsu_mesafe(yol, t0, t1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
