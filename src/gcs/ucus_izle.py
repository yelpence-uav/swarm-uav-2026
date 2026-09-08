#!/usr/bin/env python3
# Copyright 2026 Yelpence
"""UÇUŞ İZLEYİCİ — uçarken kaydeder, sonra soruyu cevaplar.

NİYE VAR (8 Eylül 2026'da acıyla öğrenildi)
-------------------------------------------
O gün Görev 1'in ilk onboard uçuşunda yalnız `mission_fsm` durum
geçişleri izlendi. Operatör inişten sonra *"kanat dronlar bas-çek yapar
gibi sallandı"* dedi ve elde **hiçbir veri yoktu** — cevap ancak saatler
sonra, uçağın bag'i kazılarak çıktı (formasyon hedefi 0.72 Hz'e düşmüş,
heading tek adımda 32.4° sıçramış).

Bu betik o boşluğu kapatıyor: uçuş boyunca **her şeyi 5 Hz'de CSV'ye**
yazar ve ekrana yalnız DEĞİŞİKLİKLERİ basar. Operatör sonradan "şurada
şöyle oldu" dediğinde kayıt zaten elde olur.

TELEMETRİ MESH'TEN GELİYOR — SSH GEREKMİYOR
`/api/telemetry/snapshot` üç dronu birden veriyor ve yolu
drone → mesh → base ESP → YKİ. 8 Eylül'de SSH dakikalarca cevap
vermezken bu yol çalışıyordu; izleme onun üstüne kuruldu.

KULLANIM
    python3 src/gcs/ucus_izle.py                  # canlı izle (Ctrl-C bitirir)
    python3 src/gcs/ucus_izle.py --coz KAYIT.csv  # kaydı çöz, özet çıkar

NE YAKALAR
    * durum/mod/armed/failsafe geçişleri          -> zaman damgalı
    * uçaklar arası EN DAR AN                     -> hangi çift, ne zaman
    * SALINIM: roll/pitch tepe-tepe genliği       -> "bas-çek" bunun sayısı
    * hız sıçraması (ileribesleme fırlaması)
    * origin/offboard/kill/RC bayrakları
    * pil
"""

import argparse
import csv
import json
import math
import os
import signal
import sys
import time
import urllib.error
import urllib.request

YKI = os.environ.get('YKI_URL', 'http://localhost:8000')
ZAMAN_ASIMI_S = 4.0

# Salınım penceresi: roll/pitch tepe-tepe bu süre içinde ölçülür.
# 2 sn seçildi çünkü operatörün tarif ettiği "bas-çek" 0.5-2 Hz bandında
# (5 Eylül yalpa ölçümü); daha kısa pencere tek salınımı kaçırır, daha
# uzunu manevrayı salınım sanır.
SALINIM_PENCERE_S = 2.0
SALINIM_ESIK_DEG = 8.0          # bunun üstü ekrana basılır

# Bu alanlar DEĞİŞİNCE ekrana olay satırı düşer.
OLAY_ALANLARI = ('state', 'mode', 'armed', 'failsafe_active', 'origin_synced',
                 'offboard_active', 'kill_switch_active', 'rc_link_ok',
                 'ready_to_arm', 'oscillation_detected', 'unstable_flight',
                 'healthy', 'connected')

CSV_ALANLARI = ('t', 'drone_id', 'lat', 'lon', 'alt_m',
                'pos_x', 'pos_y', 'pos_z', 'vel_x', 'vel_y', 'vel_z',
                'roll_deg', 'pitch_deg', 'yaw_deg', 'groundspeed_mps',
                'state', 'mode', 'armed', 'failsafe_active', 'origin_synced',
                'offboard_active', 'kill_switch_active', 'rc_link_ok',
                'ready_to_arm', 'oscillation_detected', 'unstable_flight',
                'healthy', 'connected', 'battery_voltage', 'battery_percent',
                'gps_fix_type', 'gps_satellites')


def _snapshot():
    """YKİ'den anlık telemetri. Hata YUTULMAZ ama izlemeyi de durdurmaz."""
    istek = urllib.request.Request(f'{YKI}/api/telemetry/snapshot',
                                   method='GET')
    with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI_S) as c:
        veri = json.loads(c.read().decode('utf-8'))
    return {int(d['drone_id']): d for d in veri.get('drones', [])}


def _sayi(v, varsayilan=0.0):
    """Telemetri alani sayiya cevrilemiyorsa varsayilan doner.

    Alanlarin tipi kaynaga gore degisiyor (mesh'ten gelen `state` int,
    baska yollarda metin olabiliyor). Izleyici bir tip yuzunden UCUS
    ORTASINDA olmemeli — bugun tam bunu yasadi.
    """
    try:
        return float(v)
    except (TypeError, ValueError):
        return varsayilan


def _mesafe(a, b):
    """İki dron arası 3B mesafe (NED metre). Konum yoksa None."""
    try:
        return math.dist((a['pos_x'], a['pos_y'], a['pos_z']),
                         (b['pos_x'], b['pos_y'], b['pos_z']))
    except (KeyError, TypeError):
        return None


class _Salinim:
    """Kayan pencerede roll/pitch tepe-tepe genliği.

    "Bas-çek gibi sallanma" sözel bir tarif; bu onu SAYIYA çeviriyor.
    Tek bir manevra da genlik üretir, o yüzden pencere kısa tutuldu ve
    eşik (SALINIM_ESIK_DEG) manevra genliğinin üstünde seçildi.
    """

    def __init__(self):
        self._ornekler = []          # (t, roll, pitch)

    def ekle(self, t, roll, pitch):
        self._ornekler.append((t, roll, pitch))
        kes = t - SALINIM_PENCERE_S
        while self._ornekler and self._ornekler[0][0] < kes:
            self._ornekler.pop(0)

    def genlik(self):
        """(roll_tepe_tepe, pitch_tepe_tepe) derece."""
        if len(self._ornekler) < 4:
            return 0.0, 0.0
        r = [o[1] for o in self._ornekler]
        p = [o[2] for o in self._ornekler]
        return max(r) - min(r), max(p) - min(p)


def izle(hz: float, dosya: str) -> int:
    """Canlı izleme: CSV'ye yazar, ekrana yalnız değişiklikleri basar."""
    print(f'UÇUŞ İZLEYİCİ — {hz:.1f} Hz · kayıt: {dosya}')
    print('Ctrl-C ile bitir. Ekrana yalnız DEĞİŞİKLİKLER düşer.\n')

    onceki = {}
    salinim = {}
    en_dar = (float('inf'), '', 0.0)
    t0 = None
    n = 0
    hata = 0

    durduruldu = {'evet': False}

    def _dur(_s, _f):
        durduruldu['evet'] = True
    signal.signal(signal.SIGINT, _dur)
    signal.signal(signal.SIGTERM, _dur)

    with open(dosya, 'w', newline='', encoding='utf-8') as f:
        yaz = csv.DictWriter(f, fieldnames=CSV_ALANLARI, extrasaction='ignore')
        yaz.writeheader()
        while not durduruldu['evet']:
            dongu_bas = time.monotonic()
            try:
                t = _snapshot()
                hata = 0
            except (urllib.error.URLError, OSError, ValueError) as e:
                hata += 1
                # Tek tük hata normal (backend yeniden başlıyor olabilir);
                # ARKA ARKAYA olursa görünür olmalı, sessiz kalmamalı.
                if hata in (3, 30, 300):
                    print(f'  [!] telemetri alınamıyor ({hata}. kez): {e}')
                time.sleep(1.0 / hz)
                continue

            simdi = time.time()
            if t0 is None:
                t0 = simdi
            gecen = simdi - t0
            n += 1

            for did, d in sorted(t.items()):
                satir = {'t': round(gecen, 2), 'drone_id': did}
                satir.update({k: d.get(k) for k in CSV_ALANLARI if k in d})
                yaz.writerow(satir)

                # --- olay: izlenen alanlardan biri değiştiyse ---
                onc = onceki.get(did, {})
                degisen = [(k, onc.get(k), d.get(k)) for k in OLAY_ALANLARI
                           if k in d and onc.get(k, '__yok__') != d.get(k)]
                if degisen and onc:
                    for k, eski, yeni in degisen:
                        print(f'  {gecen:7.1f}s  d{did}  {k}: {eski} -> {yeni}')
                onceki[did] = dict(d)

                # --- salınım ---
                s = salinim.setdefault(did, _Salinim())
                try:
                    s.ekle(gecen, float(d['roll_deg']), float(d['pitch_deg']))
                except (KeyError, TypeError, ValueError):
                    pass
                gr, gp = s.genlik()
                if max(gr, gp) >= SALINIM_ESIK_DEG:
                    print(f'  {gecen:7.1f}s  d{did}  SALINIM  roll t-t '
                          f'{gr:5.1f}°  pitch t-t {gp:5.1f}°')

            # --- en dar an ---
            ids = sorted(t)
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    m = _mesafe(t[ids[i]], t[ids[j]])
                    if m is not None and m < en_dar[0]:
                        en_dar = (m, f'd{ids[i]}-d{ids[j]}', gecen)

            if n % int(max(1, hz * 10)) == 0:      # ~10 sn'de bir nabız
                ozet = '  '.join(
                    f'd{i}:{str(t[i].get("state", "?"))[:9]}'
                    f'/{_sayi(t[i].get("alt_m")):.1f}m'
                    f'/%{_sayi(t[i].get("battery_percent")):.0f}'
                    for i in ids)
                print(f'  {gecen:7.1f}s  {ozet}   en dar: '
                      f'{en_dar[0]:.2f} m ({en_dar[1]})')

            uyku = (1.0 / hz) - (time.monotonic() - dongu_bas)
            if uyku > 0:
                time.sleep(uyku)

    print(f'\nKAYIT BİTTİ: {dosya}  ({n} örnek, {gecen:.0f} sn)')
    print(f'  uçuş boyunca EN DAR AN: {en_dar[0]:.2f} m  ({en_dar[1]}, '
          f't+{en_dar[2]:.1f}s)')
    print(f'  çözümlemek için:  python3 {sys.argv[0]} --coz {dosya}')
    return 0


def coz(dosya: str) -> int:
    """Kaydı çözer: zaman çizgisi, en dar an, salınım, hız sıçraması."""
    with open(dosya, newline='', encoding='utf-8') as f:
        satirlar = list(csv.DictReader(f))
    if not satirlar:
        print('kayıt boş')
        return 1

    def _f(s, k, v=0.0):
        try:
            return float(s.get(k) or v)
        except (TypeError, ValueError):
            return v

    dronelar = sorted({int(s['drone_id']) for s in satirlar})
    print(f'=== {dosya} — {len(satirlar)} örnek, {len(dronelar)} drone ===\n')

    # --- durum zaman cizgisi ---
    print('--- DURUM GEÇİŞLERİ ---')
    onceki = {}
    for s in satirlar:
        did = int(s['drone_id'])
        for k in ('state', 'mode', 'armed', 'failsafe_active', 'origin_synced'):
            y = s.get(k)
            if onceki.get((did, k), '__yok__') not in ('__yok__', y):
                print(f'  t+{_f(s, "t"):7.1f}s  d{did}  {k}: '
                      f'{onceki[(did, k)]} -> {y}')
            onceki[(did, k)] = y

    # --- en dar an ---
    print('\n--- UÇAKLAR ARASI EN DAR AN ---')
    zaman = {}
    for s in satirlar:
        zaman.setdefault(round(_f(s, 't'), 1), {})[int(s['drone_id'])] = s
    en_dar = (float('inf'), '', 0.0)
    for t, d in zaman.items():
        ids = sorted(d)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = d[ids[i]], d[ids[j]]
                m = math.dist((_f(a, 'pos_x'), _f(a, 'pos_y'), _f(a, 'pos_z')),
                              (_f(b, 'pos_x'), _f(b, 'pos_y'), _f(b, 'pos_z')))
                if m < en_dar[0]:
                    en_dar = (m, f'd{ids[i]}-d{ids[j]}', t)
    print(f'  {en_dar[0]:.2f} m   {en_dar[1]}   t+{en_dar[2]:.1f}s')

    # --- salinim ---
    print('\n--- SALINIM (roll/pitch tepe-tepe, 2 sn pencere) ---')
    for did in dronelar:
        ornek = [(_f(s, 't'), _f(s, 'roll_deg'), _f(s, 'pitch_deg'))
                 for s in satirlar if int(s['drone_id']) == did]
        en_kotu = (0.0, 0.0)
        bas = 0
        for i in range(len(ornek)):
            while ornek[i][0] - ornek[bas][0] > SALINIM_PENCERE_S:
                bas += 1
            pen = ornek[bas:i + 1]
            if len(pen) < 4:
                continue
            gr = max(o[1] for o in pen) - min(o[1] for o in pen)
            gp = max(o[2] for o in pen) - min(o[2] for o in pen)
            if max(gr, gp) > max(en_kotu[0], en_kotu[1]):
                en_kotu = (gr, gp)
        isaret = '  🔴' if max(en_kotu) >= SALINIM_ESIK_DEG else ''
        print(f'  d{did}  en kötü roll t-t {en_kotu[0]:5.1f}°   '
              f'pitch t-t {en_kotu[1]:5.1f}°{isaret}')

    # --- hiz sicramasi ---
    print('\n--- HIZ (yer hızı) ---')
    for did in dronelar:
        h = [_f(s, 'groundspeed_mps') for s in satirlar
             if int(s['drone_id']) == did]
        if h:
            h_s = sorted(h)
            print(f'  d{did}  medyan {h_s[len(h_s) // 2]:4.2f}  '
                  f'%95 {h_s[int(len(h_s) * 0.95)]:4.2f}  '
                  f'max {h_s[-1]:4.2f} m/s')

    # --- pil ---
    print('\n--- PİL ---')
    for did in dronelar:
        v = [(_f(s, 't'), _f(s, 'battery_voltage'), _f(s, 'battery_percent'))
             for s in satirlar if int(s['drone_id']) == did]
        if v:
            print(f'  d{did}  {v[0][1]:.2f} V %{v[0][2]:.0f}  ->  '
                  f'{v[-1][1]:.2f} V %{v[-1][2]:.0f}')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--hz', type=float, default=5.0,
                    help='örnekleme hızı (varsayılan 5)')
    ap.add_argument('--kayit', default=None,
                    help='CSV yolu (varsayılan /tmp/yelpence_ucus_<saat>.csv)')
    ap.add_argument('--coz', metavar='CSV',
                    help='canlı izleme yerine bir kaydı çöz')
    a = ap.parse_args()
    if a.coz:
        return coz(a.coz)
    dosya = a.kayit or time.strftime('/tmp/yelpence_ucus_%H%M%S.csv')
    return izle(a.hz, dosya)


if __name__ == '__main__':
    sys.exit(main())
