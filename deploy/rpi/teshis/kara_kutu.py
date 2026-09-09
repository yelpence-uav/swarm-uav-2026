#!/usr/bin/env python3
# Copyright 2026 Yelpence
"""KARA KUTU — arıza anını UÇAĞIN DIŞINA yollar.

🔴 8 EYLUL 2026. ylp02 iki kez ayni sekilde oldu: cekirdek ve ag ayakta
(ping %0 kayip, port 22 TCP'yi kabul ediyor) ama diske dokunan HER SEY
oluyor — sshd el sikismayi bitiremiyor, ROS yigini gidiyor, journald
kapanma dizisi yazmadan susuyor.

SORUN SU: kanit da ucakla birlikte oluyor, cunku kanit ONUN DISKINE
yaziliyor. Iki arizadan sonra elimizde sebebi soyleyen tek satir yok;
CPU/bellek/sicaklik/PID'i ancak REBOOT SONRASI olcebildik ve hepsi
temiz cikti — yani ariza anini hic gormedik.

BU BETIK: saniyede bir hayati degerleri UDP ile laptopa yollar.
UDP bilerek secildi — bloklamaz, agda tikanma olsa bile ucagi
yavaslatmaz, ve olmeden onceki son paketler KARSI TARAFTA kalir.

NE TASIR (hepsi tek satir, virgulle):
    t          unix zaman
    yuk        1 dk yuk ortalamasi
    bos_mb     MemAvailable
    surec      toplam surec sayisi
    io_ms      mmcblk0'in son 1 sn'de I/O ile gecirdigi ms (>900 = TIKANMA)
    io_bekle   o an ucusta olan I/O istegi sayisi
    ros        calisan swarm dugumu sayisi
    v5         Pi'nin KENDI 5V GIRISI (PMIC EXT5V_V), son 1 sn'nin EN
               DUSUGU. 🔴 8 Eylul: ylp02'nin Pi'si UCUS SIRASINDA IKI KEZ
               oldu (18:11:55'te 24 m'de, 21:39:31'de 17.3 m'de). Her
               ikisinde de ANA PIL SAGLAMDI (15.0 V / 15.6 V, digerlerinden
               yuksek) — yani sorun paket degil, Pi'ye giden 5 V yolu.
               Nominal 5.1-5.2 V; 4.8'in altina inen her deger suphelidir.
    kisik      vcgencmd get_throttled — 0x50000/0x50005 gibi. BIT 16
               "acilistan beri DUSUK GERILIM OLDU" demektir. 8 Eylul
               21:39'da ylp02'nin Pi'si UCUS SIRASINDA sertce yeniden
               basladi (journal'da kapanma dizisi YOK, 29 sn sonra boot).
               O ani gosteren tek sey besleme gerilimiydi ve olcmuyorduk.
    kmsg       o saniyede cikan YENI cekirdek satiri (varsa) — EN DEGERLISI

KULLANIM
    ucakta:   setsid nohup python3 ~/yelpence_ws/kara_kutu.py \
                  --hedef 10.38.209.115 > /dev/null 2>&1 < /dev/null &
    laptopta: python3 deploy/rpi/teshis/kara_kutu_dinle.py
"""

import argparse
import os
import re
import socket
import subprocess
import time

VARSAYILAN_PORT = 9931


def _diskstats(ad='mmcblk0'):
    """(io_ms_toplam, ucustaki_istek). Cekirdegin kendi sayaclari."""
    try:
        with open('/proc/diskstats') as f:
            for s in f:
                p = s.split()
                if len(p) > 12 and p[2] == ad:
                    # 9: ucustaki istek, 10: io ile gecen toplam ms
                    return int(p[12]), int(p[11])
    except Exception:                                   # noqa: BLE001
        pass
    return 0, 0


def _mem_available_mb():
    try:
        with open('/proc/meminfo') as f:
            for s in f:
                if s.startswith('MemAvailable:'):
                    return int(s.split()[1]) // 1024
    except Exception:                                   # noqa: BLE001
        pass
    return -1


_KISIK_ARALIK_S = 2.0            # vcgencmd surec aciyor; her saniye gerekmez
_V5_ORNEK = 4                    # saniyede kac kez 5V rayina bakilir


def _ext5v():
    """Pi 5'in PMIC'inden 5V giris gerilimi (V); okunamazsa NaN.

    Ariza aninin kendisi hicbir yere yazilamaz (makine gidiyor), ama
    kesintiye giden SARKMA bu degerde gorunur ve UDP ile disari cikar.
    """
    try:
        c = subprocess.run(['vcgencmd', 'pmic_read_adc', 'EXT5V_V'],
                           capture_output=True, timeout=2, text=True)
        # "     EXT5V_V volt(24)=5.17642000V"
        return float(c.stdout.strip().split('=')[-1].rstrip('V'))
    except Exception:                                   # noqa: BLE001
        return float('nan')


class Kisik:
    """`vcgencmd get_throttled` — dusuk gerilim bayragi, onbellekli.

    Bit 0 su an dusuk gerilim, BIT 16 acilistan beri OLDU. Sert kesinti
    (Pi'nin resetlendigi an) hicbir yere yazilamaz; ama kesintiye giden
    SARKMALAR bit 16'yi kaldirir ve iste o, kesinti gelmeden once elimize
    gecen tek uyaridir.
    """

    def __init__(self):
        self._deger = '?'
        self._t = 0.0

    def oku(self):
        simdi = time.monotonic()
        if simdi - self._t < _KISIK_ARALIK_S:
            return self._deger
        self._t = simdi
        try:
            c = subprocess.run(['vcgencmd', 'get_throttled'],
                               capture_output=True, timeout=2, text=True)
            self._deger = c.stdout.strip().split('=')[-1] or '?'
        except Exception:                               # noqa: BLE001
            self._deger = '?'
        return self._deger


def _ros_dugum():
    try:
        cikti = subprocess.run(['ps', '-eo', 'args'], capture_output=True,
                               text=True, timeout=2).stdout
        return sum(1 for s in cikti.splitlines() if '/lib/swarm_' in s)
    except Exception:                                   # noqa: BLE001
        return -1


class Kmsg:
    """Yeni cekirdek satirlarini okur. Ariza anindaki I/O hatalari BURADA."""

    def __init__(self):
        self._f = None
        try:
            # /dev/kmsg blokmasiz: yalniz YENI satirlar (SEEK_END).
            self._f = os.fdopen(os.open('/dev/kmsg',
                                        os.O_RDONLY | os.O_NONBLOCK), 'rb')
            self._f.seek(0, os.SEEK_END)
        except Exception:                               # noqa: BLE001
            self._f = None

    def yeni(self, en_fazla=3):
        if self._f is None:
            return ''
        satirlar = []
        for _ in range(en_fazla):
            try:
                ham = self._f.readline()
            except Exception:                           # noqa: BLE001
                break
            if not ham:
                break
            m = ham.decode('utf-8', 'replace').strip()
            # "6,123,456789,-;metin" -> yalniz metin
            m = m.split(';', 1)[-1]
            m = re.sub(r'[,\n\r]', ' ', m)[:120]
            if m:
                satirlar.append(m)
        return ' | '.join(satirlar)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--hedef', required=True, help='laptop IP')
    ap.add_argument('--port', type=int, default=VARSAYILAN_PORT)
    ap.add_argument('--hz', type=float, default=1.0)
    a = ap.parse_args()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    kmsg = Kmsg()
    kisik = Kisik()
    ad = os.uname().nodename
    onc_io, _ = _diskstats()
    aralik = 1.0 / max(0.1, a.hz)
    v5_min = _ext5v()

    while True:
        io_ms, ucusta = _diskstats()
        d_io = max(0, io_ms - onc_io)
        onc_io = io_ms
        try:
            yuk = open('/proc/loadavg').read().split()[0]
        except Exception:                               # noqa: BLE001
            yuk = '?'
        try:
            surec = len(os.listdir('/proc')) and sum(
                1 for x in os.listdir('/proc') if x.isdigit())
        except Exception:                               # noqa: BLE001
            surec = -1
        # kmsg EN SONDA kalmali: icinde virgul olabilir, ayristirici
        # son alani bolmuyor. Yeni alanlar HEP ondan once eklenir.
        satir = (f'{ad},{time.time():.1f},{yuk},{_mem_available_mb()},'
                 f'{surec},{d_io},{ucusta},{_ros_dugum()},'
                 f'{kisik.oku()},{v5_min:.3f},{kmsg.yeni()}')
        try:
            s.sendto(satir.encode('utf-8', 'replace')[:1400],
                     (a.hedef, a.port))
        except Exception:                               # noqa: BLE001
            pass                      # ag gitse de dongü DURMAZ
        # Bekleme suresi bosa harcanmaz: 5V rayi dilim dilim orneklenir ve
        # SONRAKI pakete EN DUSUGU yazilir. Tek anlik olcum sarkmayi kacirir.
        v5_min = float('inf')
        dilim = aralik / max(1, _V5_ORNEK)
        for _ in range(max(1, _V5_ORNEK)):
            v = _ext5v()
            if v == v and v < v5_min:
                v5_min = v
            time.sleep(dilim)
        if v5_min == float('inf'):
            v5_min = float('nan')


if __name__ == '__main__':
    raise SystemExit(main())
