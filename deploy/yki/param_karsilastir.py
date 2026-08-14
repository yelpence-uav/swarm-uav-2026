#!/usr/bin/env python3
# =============================================================================
# PX4 PARAMETRE KARSILASTIRICI — ucaklar arasi ayrisma denetimi
#
# NEDEN VAR: 2 Agustos'ta d1'in MPC_XY_VEL_MAX'i 12.0, d3'unki 4.0 cikti.
# 12 m/s'te frenleme mesafesi ~24 m, oysa carpisma payimiz 3.07 m'ydi. Bu
# UCUS SIRASINDA anlasildi. Ucmadan yakalanmasi gerekiyordu.
#
# NE YAPAR: agdaki her drone'da px4_param.py'yi kosturur, sonuclari yan yana
# koyar ve FARKLI olanlari isaretler.
#
# KULLANIM
#   ./deploy/yki/param_karsilastir.py              # ucusu etkileyenler (hizli)
#   ./deploy/yki/param_karsilastir.py --hepsi      # 1007 parametrenin tamami
#   ./deploy/yki/param_karsilastir.py --al MPC_XY_VEL_MAX MPC_ACC_HOR
#   ./deploy/yki/param_karsilastir.py --dronelar ylp00 ylp02
#
# NEREDE KOSAR: YKI'de. Drone listesini drone_bul.sh --tablo'dan alir
# (tek kaynak), px4_param.py'yi her ucagin KONTEYNERINE borudan gecirir —
# drone'a dosya kopyalamaya gerek yok.
# =============================================================================

import argparse
import json
import pathlib
import subprocess
import sys

KOK = pathlib.Path(__file__).resolve().parents[2]
DRONE_BUL = KOK / 'deploy' / 'yki' / 'drone_bul.sh'
PARAM_BETIK = KOK / 'src' / 'gcs' / 'px4_param.py'

# Ucaga OZGU olmasi GEREKENLER — fark cikmasi normal, uyari verilmez.
# MAV_SYS_ID ikisinde de ayni olursa QGC iki ucagi TEK arac sanar (30 Tem).
UCAGA_OZGU = {'MAV_SYS_ID'}

K_KIRMIZI = '\033[31m'; K_YESIL = '\033[32m'; K_SARI = '\033[33m'
K_KALIN = '\033[1m'; K_SIFIR = '\033[0m'
if not sys.stdout.isatty():
    K_KIRMIZI = K_YESIL = K_SARI = K_KALIN = K_SIFIR = ''


def dronelari_bul():
    """drone_bul.sh --tablo -> [(isim, ip, kullanici, konteyner, agent_id)]"""
    try:
        cikti = subprocess.run([str(DRONE_BUL), '--tablo'],
                               capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        print('drone_bul.sh zaman asimina ugradi', file=sys.stderr)
        return []
    satirlar = [s for s in cikti.stdout.splitlines() if s.strip()]
    return [tuple(s.split('\t')) for s in satirlar if len(s.split('\t')) == 5]


def parametreleri_al(drone, arglar):
    """px4_param.py'yi drone'un konteynerinde kosturur, JSON doner."""
    isim, ip, kul, kon, aid = drone
    uzak = (f'docker exec -i -e AGENT_ID={aid} {kon} '
            f'bash -lc "source /opt/ros/jazzy/setup.bash && python3 - {arglar}"')
    try:
        with open(PARAM_BETIK, 'rb') as f:
            r = subprocess.run(
                ['ssh', '-o', 'ConnectTimeout=10', f'{kul}@{ip}', uzak],
                stdin=f, capture_output=True, timeout=240)
    except subprocess.TimeoutExpired:
        print(f'  {isim}: zaman asimi', file=sys.stderr)
        return None
    if r.returncode != 0:
        print(f'  {isim}: HATA — {r.stderr.decode(errors="replace")[-300:]}',
              file=sys.stderr)
        return None
    try:
        return json.loads(r.stdout.decode(errors='replace'))['parametreler']
    except (ValueError, KeyError) as exc:
        print(f'  {isim}: cikti cozulemedi ({exc})', file=sys.stderr)
        return None


def bicimle(d):
    if d is None:
        return '?'
    if isinstance(d, float):
        # PX4 float'lari 0.4000000059604645 gibi geliyor; 4 hane yeter ve
        # sahte fark uretmez.
        return f'{d:.4f}'.rstrip('0').rstrip('.')
    return str(d)


def main() -> int:
    ap = argparse.ArgumentParser(description='PX4 parametrelerini ucaklar arasi karsilastir')
    ap.add_argument('--hepsi', action='store_true', help='1007 parametrenin tamami')
    ap.add_argument('--al', nargs='+', metavar='AD', help='belirli parametreler')
    ap.add_argument('--dronelar', nargs='+', metavar='YLP', help='varsayilan: agdaki hepsi')
    a = ap.parse_args()

    if a.al:
        arglar = '--json --al ' + ' '.join(a.al)
    elif a.hepsi:
        arglar = '--json'
    else:
        arglar = '--json --onemli'

    dronelar = dronelari_bul()
    if a.dronelar:
        dronelar = [d for d in dronelar if d[0] in a.dronelar]
    if len(dronelar) < 2:
        print(f'{K_SARI}Karsilastirma icin en az 2 drone gerekiyor; '
              f'{len(dronelar)} bulundu.{K_SIFIR}', file=sys.stderr)
        if not dronelar:
            return 1

    print(f'{K_KALIN}Parametreler okunuyor...{K_SIFIR}', file=sys.stderr)
    veri = {}
    for d in dronelar:
        print(f'  {d[0]} ({d[1]})...', file=sys.stderr)
        p = parametreleri_al(d, arglar)
        if p is not None:
            veri[d[0]] = p
    if not veri:
        print('hicbir ucaktan parametre alinamadi', file=sys.stderr)
        return 1

    isimler = sorted(veri)
    tum_adlar = sorted({k for p in veri.values() for k in p})

    gen = max((len(n) for n in tum_adlar), default=20) + 2
    baslik = f'{K_KALIN}{"PARAMETRE":<{gen}}' + ''.join(
        f'{i:<22}' for i in isimler) + f'{K_SIFIR}'
    print('\n' + baslik)
    print('-' * (gen + 22 * len(isimler)))

    farkli, ozgu, eksik = [], [], []
    for ad in tum_adlar:
        degerler = [veri[i].get(ad) for i in isimler]
        bicimli = [bicimle(d) for d in degerler]
        ayni = len(set(bicimli)) == 1
        if None in degerler:
            eksik.append(ad)
        if ayni:
            continue
        if ad in UCAGA_OZGU:
            ozgu.append((ad, bicimli))
        else:
            farkli.append((ad, bicimli))

    # Once GERCEK farklar — aranan sey bu.
    for ad, bicimli in farkli:
        print(f'{K_KIRMIZI}{ad:<{gen}}{K_SIFIR}'
              + ''.join(f'{K_KIRMIZI}{v:<22}{K_SIFIR}' for v in bicimli))
    for ad, bicimli in ozgu:
        print(f'{K_SARI}{ad:<{gen}}{K_SIFIR}'
              + ''.join(f'{v:<22}' for v in bicimli) + '  (ucaga ozgu, normal)')

    if not farkli and not ozgu:
        print(f'{K_YESIL}(fark yok){K_SIFIR}')

    print()
    if farkli:
        print(f'{K_KIRMIZI}{K_KALIN}!!! {len(farkli)} PARAMETRE AYRISMIS{K_SIFIR}')
        print('    Ucmadan once esitle. Kalkis/hiz parametrelerindeki fark')
        print('    carpisma payini dogrudan yer — bkz. docs/RPI_ESITLEME.md §5')
        print(f'    ros2 param set /drone_<N>/mavros/param <AD> <DEGER>')
    else:
        print(f'{K_YESIL}Ucaklar arasi ayrisma yok.{K_SIFIR} '
              f'({len(tum_adlar)} parametre karsilastirildi)')
    if eksik:
        print(f'{K_SARI}okunamayan {len(eksik)}: '
              f'{", ".join(eksik[:6])}{" ..." if len(eksik) > 6 else ""}{K_SIFIR}')
    return 1 if farkli else 0


if __name__ == '__main__':
    sys.exit(main())
