#!/usr/bin/env python3
# Copyright 2026 Yelpence
"""KARA KUTU DINLEYICI — ucaklardan gelen hayati degerleri laptopta tutar.

Ucak olse bile son saniyeler BURADA kalir; teshis artik "reboot sonrasi
temiz gorunuyor"a mahkum degil.

    python3 deploy/rpi/teshis/kara_kutu_dinle.py [--kayit dosya.csv]

Ekrana yalniz DIKKAT CEKEN satirlar duser (cekirdek mesaji, I/O tikanmasi,
bellek dususu, ROS dugum kaybi); hepsi dosyaya yazilir.
"""

import argparse
import socket
import sys
import time

PORT = 9931
IO_TIKANMA_MS = 900          # 1 sn'nin %90'i I/O bekleyerek gectiyse
BOS_MB_ESIK = 300


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=PORT)
    ap.add_argument('--kayit', default='/tmp/kara_kutu.csv')
    a = ap.parse_args()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('', a.port))
    f = open(a.kayit, 'a', buffering=1)
    f.write('# ad,t,yuk,bos_mb,surec,io_ms,io_ucusta,ros,kisik,v5,kmsg\n')
    print(f'KARA KUTU dinleniyor :{a.port} — kayit {a.kayit}')
    print('Ekrana yalniz dikkat ceken satirlar duser.\n')

    son_gorulme = {}
    while True:
        try:
            veri, _ = s.recvfrom(2048)
        except KeyboardInterrupt:
            return 0
        satir = veri.decode('utf-8', 'replace')
        f.write(satir + '\n')
        p = satir.split(',', 8)
        if len(p) < 9:
            continue
        ad, t, yuk, bos, surec, io_ms, ucusta, ros, kmsg = p
        son_gorulme[ad] = time.time()
        onemli = []
        if kmsg.strip():
            onemli.append(f'KMSG: {kmsg.strip()}')
        try:
            if int(io_ms) >= IO_TIKANMA_MS:
                onemli.append(f'I/O TIKANMASI {io_ms}ms/sn (ucusta {ucusta})')
            if 0 <= int(bos) < BOS_MB_ESIK:
                onemli.append(f'BELLEK {bos} MB')
            if int(ros) == 0:
                onemli.append('ROS DUGUMU YOK')
        except ValueError:
            pass
        if onemli:
            print(f'{ad} {time.strftime("%H:%M:%S")} yuk={yuk} '
                  f'bos={bos}MB ros={ros} — ' + ' · '.join(onemli))
            sys.stdout.flush()


if __name__ == '__main__':
    raise SystemExit(main())
