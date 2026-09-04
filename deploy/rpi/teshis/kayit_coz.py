#!/usr/bin/env python3
# Copyright 2026 Yelpence
"""Uçuş kaydından QR ve renk dedektörlerini ÖLÇER — irtifaya göre.

NEDEN VAR (28 Ağustos 2026, operatör isteği)
--------------------------------------------
"Yere bir QR bir de renk sersem, drone'u üzerinde farklı irtifalarda
uçursam, o uçuş sırasında kayıt alsam — kayıttan QR ve renk dedektörünün
çalışıp çalışmayacağını test edebilir miyiz?"

Evet, ve canlı testten iyi: aynı kaydı istediğin kadar farklı eşikle
yeniden işleyebiliriz, ve hangi irtifada bıraktığı KESİN ölçülür.

NASIL ÇALIŞIR
-------------
İki kaynağı ZAMAN DAMGASINDAN eşleştiriyor:
  * `.idx`  — her karenin gerçek epoch damgası (kamera servisi yazıyor)
  * mcap    — `/drone_N/mavros/altitude` telemetrisi (rosbag2 kaydı)

⚠️ İKİSİ DE Pi'nin SİSTEM SAATİNİ kullanıyor. Uçuş sırasında saat sıçrarsa
(bkz. `gps_saat.py`, TUZAKLAR §1.x) eşleşme kayar. Betik zaman aralıklarının
örtüşmesini denetliyor ve örtüşme zayıfsa UYARIYOR.

⚠️ HER KARE İŞLENMİYOR. 4K'da kare başına 200-400 ms; 5 dakikalık kayıtta
3000 kare = 20 dakika. Her irtifa kuşağından `--ornek` kadar kare
örnekleniyor. Örnekleme DÜZGÜN ARALIKLI, baştan değil — bir manevranın
başındaki birkaç kareye takılıp kalmamak için.

KULLANIM (konteynerde)
    python3 /ws/kayit_coz.py \
        --kayit /ws/kayit_disi/ucus.mjpeg \
        --bag   /ws/kayit/ylp00_20260828_101500 \
        --ajan  3
"""

import argparse
import bisect
import collections
import pathlib
import sys
import time

import cv2

import numpy as np


def idx_oku(yol: pathlib.Path):
    """`.idx` dosyasını (kare_no, epoch, ofset, uzunluk) listesine çevirir."""
    satirlar = yol.read_text(encoding='ascii', errors='replace').splitlines()
    kareler = []
    for s in satirlar:
        if not s or s.startswith('#'):
            continue
        p = s.split()
        if len(p) != 4:
            continue
        kareler.append((int(p[0]), float(p[1]), int(p[2]), int(p[3])))
    return kareler


def irtifa_oku(bag_yolu: str, ajan: int):
    """rosbag2'den (epoch, irtifa) çiftleri. ROS ortamı gerektirir.

    ÜÇ GİRDİ BİÇİMİ kabul eder:
      1. metadata.yaml'ı olan bag dizini  — normal kapanmış kayıt
      2. metadata.yaml'ı OLMAYAN dizin    — bag HÂLÂ YAZIYOR
      3. tek .mcap dosyası ya da glob     — yalnız ilgilenilen dilim

    2. madde 28 Ağustos 2026'da gerekti: uçuş kaydı alınırken `ros2 bag
    record` çalışmaya devam ediyordu ve rosbag2 metadata.yaml'ı ancak
    KAPANIŞTA yazıyor. Bag'i durdurmak uçuş loglamasını kesmek demekti;
    onun yerine .mcap parçaları tek tek okunuyor — mcap kendi kendini
    tanımlayan bir biçim, şema ve kanallar dosyanın içinde.
    """
    import glob as _glob
    import os

    import rclpy.serialization as rs
    import rosbag2_py
    from mavros_msgs.msg import Altitude

    konu = f'/drone_{ajan}/mavros/altitude'

    if os.path.isdir(bag_yolu) and os.path.exists(
            os.path.join(bag_yolu, 'metadata.yaml')):
        kaynaklar = [bag_yolu]
    elif os.path.isdir(bag_yolu):
        kaynaklar = sorted(_glob.glob(os.path.join(bag_yolu, '*.mcap')))
    else:
        kaynaklar = sorted(_glob.glob(bag_yolu))
    if not kaynaklar:
        return []

    veri = []
    for kaynak in kaynaklar:
        okur = rosbag2_py.SequentialReader()
        try:
            okur.open(
                rosbag2_py.StorageOptions(uri=kaynak, storage_id='mcap'),
                rosbag2_py.ConverterOptions('', ''))
            okur.set_filter(rosbag2_py.StorageFilter(topics=[konu]))
            while okur.has_next():
                _, ham, t = okur.read_next()
                m = rs.deserialize_message(ham, Altitude)
                veri.append((t / 1e9, float(m.relative)))
        except Exception:                                # noqa: BLE001
            # Tek bozuk/yarım parça tüm çözümlemeyi düşürmemeli — bag
            # yazarken son parça her zaman yarımdır.
            continue
        finally:
            del okur
    veri.sort()
    return veri


def irtifa_csv_oku(yol: str):
    """Irtifa CSV.sini okur: (epoch, irtifa) — ROS GEREKTİRMEZ.

    28 Ağustos 2026: çözümlemeyi laptopta koşabilmek için eklendi. Bag
    yalnız uçakta ve `rosbag2_py` yalnız konteynerde; CSV ikisini de
    gereksiz kılıyor. Uçakta bir kez üretilir, yanında taşınır.
    Biçim: `epoch,irtifa_m` başlıklı iki sütun.
    """
    veri = []
    for satir in open(yol, encoding='utf-8'):
        p = satir.strip().split(',')
        if len(p) != 2:
            continue
        try:
            veri.append((float(p[0]), float(p[1])))
        except ValueError:
            continue                      # başlık satırı
    veri.sort()
    return veri


def irtifa_esle(kareler, irtifalar, tolerans=0.5):
    """Her kareye en yakın irtifa örneğini bağlar."""
    if not irtifalar:
        return []
    zamanlar = [z for z, _ in irtifalar]
    esli = []
    for kare_no, epoch, ofs, uzn in kareler:
        i = bisect.bisect_left(zamanlar, epoch)
        adaylar = [j for j in (i - 1, i) if 0 <= j < len(zamanlar)]
        if not adaylar:
            continue
        en = min(adaylar, key=lambda j: abs(zamanlar[j] - epoch))
        if abs(zamanlar[en] - epoch) <= tolerans:
            esli.append((kare_no, epoch, ofs, uzn, irtifalar[en][1]))
    return esli


def main() -> int:
    a = argparse.ArgumentParser(description='Kayıttan QR/renk ölçümü')
    a.add_argument('--kayit', required=True, help='.mjpeg dosyası')
    a.add_argument('--irtifa-csv', help='epoch,irtifa_m biçiminde CSV — '
                   'ROS gerektirmez, laptopta çalışır (--bag yerine)')
    a.add_argument('--bag', help='rosbag2 dizini (irtifa için); yoksa '
                                 'irtifasız tek grup olarak işlenir')
    a.add_argument('--ajan', type=int, default=3)
    a.add_argument('--kusak', type=float, default=5.0,
                   help='irtifa kuşağı genişliği, metre')
    a.add_argument('--ornek', type=int, default=15,
                   help='kuşak başına işlenecek kare')
    a.add_argument('--team-slot', type=int, default=1)
    d = a.parse_args()

    kayit = pathlib.Path(d.kayit)
    idx = kayit.with_suffix('.idx')
    if not kayit.exists() or not idx.exists():
        print(f'HATA: {kayit} ya da {idx} yok')
        return 1

    from swarm_perception.vision_node.landing_zone_detector import (
        LandingZoneDetector,
    )
    from swarm_perception.vision_node.qr_detector import QRDetector

    kareler = idx_oku(idx)
    if not kareler:
        print('HATA: idx boş')
        return 1
    k0, k1 = kareler[0][1], kareler[-1][1]
    print(f'  kayıt : {kayit.name}  {kayit.stat().st_size/1048576:.0f} MB  '
          f'{len(kareler)} kare  {(k1-k0)/60:.1f} dk')

    if getattr(d, 'irtifa_csv', None):
        irtifalar = irtifa_csv_oku(d.irtifa_csv)
    elif d.bag:
        irtifalar = irtifa_oku(d.bag, d.ajan)
        if not irtifalar:
            print("HATA: bag'de irtifa yok")
            return 1
        b0, b1 = irtifalar[0][0], irtifalar[-1][0]
        ortak = min(k1, b1) - max(k0, b0)
        print(f'  bag   : {len(irtifalar)} irtifa örneği  {(b1-b0)/60:.1f} dk')
        print(f'  örtüşme: {ortak / 60:.1f} dk', end='')
        if ortak <= 0:
            print('  ⚠️ HİÇ ÖRTÜŞMÜYOR — saat kaymış olabilir')
            return 1
        print(f'  ({100 * ortak / (k1 - k0):.0f}% kaydın)')
        esli = irtifa_esle(kareler, irtifalar)
        print(f'  eşleşen kare: {len(esli)}/{len(kareler)}')
    else:
        esli = [(n, e, o, u, -1.0) for n, e, o, u in kareler]
        print('  (bag verilmedi — irtifasız tek grup)')

    if not esli:
        print('HATA: hiçbir kare irtifayla eşleşmedi')
        return 1

    # Kuşaklara ayır
    kusaklar = collections.defaultdict(list)
    for k in esli:
        kusaklar[-1 if k[4] < 0 else int(k[4] / d.kusak)].append(k)

    qr = QRDetector(min_confidence=0.5, team_slot=d.team_slot,
                    iki_asamali=True, olcek=4,
                    tam_tarama_periyodu=5, wechat_yedek=True)
    lz_cfg = {'min_zone_area_px': 40.0, 'min_zone_area_frac': 0.0002,
              'min_circularity': 0.75, 'gaussian_blur_kernel': 5}

    ham = kayit.open('rb')
    print()
    print('  irtifa      kare  islenen  QR okundu   renk bulundu  ort.sure')
    print('  ' + '-' * 72)
    ozet = []
    for anahtar in sorted(kusaklar):
        grup = kusaklar[anahtar]
        etiket = ('irtifasız' if anahtar < 0 else
                  f'{anahtar*d.kusak:.0f}-{(anahtar+1)*d.kusak:.0f} m')
        # DUZGUN ARALIKLI ornekleme: bir manevranin basina takilmamak icin
        adim = max(1, len(grup) // d.ornek)
        secilen = grup[::adim][:d.ornek]
        qr_ok = lz_ok = 0
        sureler = []
        for _, _, ofs, uzn, _ in secilen:
            ham.seek(ofs)
            veri = ham.read(uzn)
            kare = cv2.imdecode(np.frombuffer(veri, np.uint8),
                                cv2.IMREAD_COLOR)
            if kare is None:
                continue
            t = time.perf_counter()
            if any(z.get('valid') for z in qr.detect(kare)):
                qr_ok += 1
            kucuk = cv2.resize(kare,
                               (kare.shape[1] // 2, kare.shape[0] // 2),
                               interpolation=cv2.INTER_AREA)
            if [z for z in LandingZoneDetector(config=lz_cfg).detect(kucuk)
                    if z['confidence'] >= 0.75]:
                lz_ok += 1
            sureler.append(time.perf_counter() - t)
        n = len(secilen)
        ort = sum(sureler) / len(sureler) * 1000 if sureler else 0
        print(f'  {etiket:11s} {len(grup):6d} {n:8d}   '
              f'{qr_ok:3d}/{n:<3d} {100 * qr_ok / max(n, 1):4.0f}%  '
              f'{lz_ok:3d}/{n:<3d} {100 * lz_ok / max(n, 1):4.0f}%  '
              f'{ort:6.0f}ms')
        ozet.append((etiket, qr_ok / max(n, 1), lz_ok / max(n, 1)))
    ham.close()

    print()
    print('  --- SINIRLAR ---')
    for ad, dizi in (('QR', [(e, o) for e, o, _ in ozet]),
                     ('renk', [(e, o) for e, _, o in ozet])):
        calisan = [e for e, o in dizi if o >= 0.8]
        bosa = [e for e, o in dizi if o < 0.2]
        print(f'  {ad:5s} güvenilir: {", ".join(calisan) if calisan else "—"}')
        print(f'  {ad:5s} bulamadı : {", ".join(bosa) if bosa else "—"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
