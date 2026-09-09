#!/usr/bin/env python3
# Copyright 2026 Yelpence
"""BESLEME AVI — Pi'nin elektrigini kesen baglantiyi YERDE bulur.

🔴 8 EYLUL 2026. ylp02'nin Pi'si AYNI GUN IKI KEZ havada oldu:

    18:11:55   ARMED Offboard, 24.0 m,  ana pil 15.0 V
    21:39:31   ARMED Offboard, 17.3 m,  ana pil 15.6 V

Ikisinde de ana pil SAGLAMDI (o an ylp00 14.1 V, ylp01 14.3 V ile daha
kotuydu ve onlara bir sey olmadi). Pixhawk de yasadi — ucus kontrolu
devam etti, OFFBOARD setpoint akisi kesilince PX4 kendi failsafe'ini
uygulayip indirdi. Yani kesilen sey ANA PIL DEGIL, **Pi'ye giden 5 V**.

Ve yalniz HAVADAYKEN oluyor: yerde saatlerdir hic resetlenmiyor. Havada
degisen iki sey var — motor akimi ve TITRESIM. Aralarindaki farki
anlamanin yolu, ikisini yerde AYRI AYRI uygulayip 5 V'a bakmaktir.

NEDEN BU BETIK VAR
------------------
`docs/YLP02_DUSME.md` §6.1 zaten "kablolari tek tek oynat, telemetriyi
izle" diyor. Eksigi su: 200 ms'lik bir cukuru goz yakalayamaz ve
yakalasa bile HANGI konnektore dokunulurken oldugunu kimse not etmez.
Bu betik ikisini de yapar: adimlari sirayla yurutur, her adimin
**en dusuk 5 V'unu** ve kopma olup olmadigini ayri ayri tutar, sonunda
suclu adimi isaretleyen bir tablo basar.

VERI NEREDEN GELIYOR
    kara_kutu.py  ->  UDP  ->  kara_kutu_dinle.py  ->  CSV  ->  BU BETIK
Yani ucaga hicbir yuk binmez ve olcum ucagin diskinden BAGIMSIZDIR.

KULLANIM
    python3 deploy/rpi/teshis/besleme_avi.py --ucak ylp02 --kayit <csv>

    Her adimda ekranda ne yapilacagi yazar, geri sayar, sonra sonucu
    basar. Kablolari oynatmak OPERATORUN isi; betik yalniz olcer.

🔴 PERVANELER SOKULU. Motorlu adim yalniz pervaneler cikarilmis ve
uçak sabitlenmisken yapilir. Burada kanit toplaniyor, ucus denenmiyor.
"""

import argparse
import os
import sys
import time

# Pi 5'in 5 V girisi nominal 5.1-5.2 V. Bunlarin altina inen her sey
# bildirilir; 4.80 altinda Pi'nin resetlenmesi beklenir (PMIC esigi).
_UYARI_V = 4.95
_ALARM_V = 4.80
# Kara kutu 1 Hz. Bu kadar saniye paket gelmezse "KOPTU" sayilir; ylp02
# 8 Eylul'de tam boyle gitti (27 sn sessizlik, sonra acilis).
_KOPMA_S = 4.0


ADIMLAR = [
    ('SAKIN REFERANS — hicbir seye dokunma', 20,
     'Temiz taban cizgisi. Buradaki en dusuk deger, digerlerini '
     'karsilastiracagimiz sayidir.'),
    ('Pi GUC KABLOSU ve SOKETI', 20,
     'Pi\'ye giren 5 V kablosunu soketin dibinden tut, hafifce '
     'cek-birak, saga-sola ve yukari-asagi oynat.'),
    ('Pi\'yi besleyen BEC / REGULATOR', 20,
     'Regulatorun CIKIS konnektorunu ve uzerindeki kablolari oynat. '
     'Modulun kendisini de govdesinden hafifce bastir.'),
    ('BEC GIRISI / PDB baglantisi', 20,
     'Regulatorun PDB\'ye ya da pile baglandigi ucu oynat. Lehimli ise '
     'lehim noktasina tirnakla hafifce bastir.'),
    ('ANA PIL KONNEKTORU (XT60/XT90)', 20,
     'Konnektoru yerinden oynatmadan saga-sola bukmeye calis. '
     'Yanik/kararmis pim varsa SOYLE.'),
    ('GOVDE TITRESIMI', 20,
     'Uçagi govdesinden tut ve kollari tek tek sars; motor kollarina '
     'avucla vur. Havadaki titresimi taklit ediyoruz.'),
    ('MOTORLAR DUSUK GAZDA (PERVANELER SOKULU)', 25,
     '🔴 Pervaneler cikarilmis olmali. Motorlari dusuk gazda dondur, '
     'bu sirada 2. ve 3. adimdaki kablolari tekrar oynat.'),
]


def _oku_son(yol, ucak, t0):
    """`t0` sonrasindaki (t, v5, ros) orneklerini dondurur."""
    ornek = []
    try:
        with open(yol, errors='replace') as f:
            for ln in f:
                if ln.startswith('#') or not ln.strip():
                    continue
                a = ln.rstrip('\n').split(',')
                if len(a) < 11 or a[0] != ucak:
                    continue
                try:
                    t = float(a[1])
                except ValueError:
                    continue
                if t < t0:
                    continue
                try:
                    v = float(a[9])
                except ValueError:
                    v = float('nan')
                ornek.append((t, v, a[7]))
    except FileNotFoundError:
        pass
    return ornek


def _adim_calistir(yol, ucak, ad, sure, aciklama, sira, toplam):
    print(f'\n{"=" * 66}')
    print(f'ADIM {sira}/{toplam} — {ad}   ({sure} sn)')
    print(f'  {aciklama}')
    print(f'{"=" * 66}')
    input('  Hazir oldugunda ENTER... ')
    t0 = time.time()
    en_dusuk = float('inf')
    son_yaz = 0.0
    while time.time() - t0 < sure:
        kalan = sure - (time.time() - t0)
        ornek = _oku_son(yol, ucak, t0)
        if ornek:
            v = min(x[1] for x in ornek if x[1] == x[1]) if any(
                x[1] == x[1] for x in ornek) else float('nan')
            if v == v:
                en_dusuk = min(en_dusuk, v)
        if time.time() - son_yaz >= 1.0:
            son_yaz = time.time()
            g = f'{en_dusuk:.3f}' if en_dusuk != float('inf') else '---'
            im = ''
            if en_dusuk < _ALARM_V:
                im = '   🔴🔴 ALARM'
            elif en_dusuk < _UYARI_V:
                im = '   ⚠️  DUSUK'
            print(f'\r  kalan {kalan:4.0f} sn   en dusuk 5V = {g} V{im}   ',
                  end='', flush=True)
        time.sleep(0.2)

    ornek = _oku_son(yol, ucak, t0)
    print()
    if not ornek:
        print('  🔴 HIC PAKET GELMEDI — kara kutu calismiyor ya da ucak agda degil')
        return {'ad': ad, 'min_v': float('nan'), 'kopma': -1, 'paket': 0}

    # kopma: ardisik paketler arasi bosluk
    kopma = 0
    for i in range(1, len(ornek)):
        if ornek[i][0] - ornek[i - 1][0] > _KOPMA_S:
            kopma += 1
    # reset: ros sayisi sifira dustuyse yigin gitti demektir
    reset = any(x[2] == '0' for x in ornek)
    v_ler = [x[1] for x in ornek if x[1] == x[1]]
    min_v = min(v_ler) if v_ler else float('nan')
    print(f'  sonuc: {len(ornek)} paket · en dusuk 5V {min_v:.3f} V'
          f' · kopma {kopma}' + ('  · 🔴 ROS SIFIRLANDI' if reset else ''))
    return {'ad': ad, 'min_v': min_v, 'kopma': kopma, 'paket': len(ornek),
            'reset': reset}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ucak', default='ylp02', help='hangi ucak (kara kutu adi)')
    ap.add_argument('--kayit', required=True,
                    help='kara_kutu_dinle.py\'nin yazdigi CSV')
    ap.add_argument('--adim', type=int, default=None,
                    help='yalniz bu adimi kosar (1..N)')
    a = ap.parse_args()

    if not os.path.exists(a.kayit):
        print(f'HATA: {a.kayit} yok. Once kara_kutu_dinle.py calistir.')
        return 1

    # Kayit gercekten AKIYOR mu? Akmayan bir dosyaya bakip "5 V temiz"
    # demek, olcmeden teshis koymaktir.
    taze = _oku_son(a.kayit, a.ucak, time.time() - 10)
    if not taze:
        print(f'HATA: son 10 saniyede {a.ucak} paketi yok.')
        print('      kara_kutu.py ucakta kosuyor mu, dinleyici ayakta mi?')
        return 1
    print(f'{a.ucak} akiyor: son 10 sn\'de {len(taze)} paket, '
          f'5V {min(x[1] for x in taze):.3f}-{max(x[1] for x in taze):.3f} V')

    adimlar = ADIMLAR if a.adim is None else [ADIMLAR[a.adim - 1]]
    sonuc = []
    for i, (ad, sure, acik) in enumerate(adimlar, 1):
        sonuc.append(_adim_calistir(a.kayit, a.ucak, ad, sure, acik,
                                    i, len(adimlar)))

    print(f'\n{"=" * 66}\nOZET — en dusuk 5 V (dusuk olan SUCLUDUR)\n{"=" * 66}')
    taban = sonuc[0]['min_v'] if sonuc else float('nan')
    for s in sonuc:
        v = s['min_v']
        fark = (v - taban) if (v == v and taban == taban) else float('nan')
        im = ''
        if v == v and v < _ALARM_V:
            im = '  🔴🔴 SUCLU ADAY'
        elif v == v and v < _UYARI_V:
            im = '  ⚠️'
        elif fark == fark and fark < -0.05:
            im = '  ⚠️  tabandan dusuk'
        if s.get('reset'):
            im += '  🔴 ROS SIFIRLANDI'
        if s['kopma']:
            im += f'  🔴 {s["kopma"]} KOPMA'
        print(f'  {s["ad"][:44]:44s} {v:6.3f} V{im}')
    print('\nHicbir adimda dusus yoksa: ariza yalniz UCUS titresiminde '
          'ortaya cikiyor demektir — sonraki adim Pi beslemesini AYRI bir\n'
          'kaynaga almak (hem kanit hem cozum).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
