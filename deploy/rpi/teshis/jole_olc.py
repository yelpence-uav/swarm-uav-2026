#!/usr/bin/env python3
"""Rolling shutter (jole) OLCUSU — MJPEG kaydindan, ROS gerekmez.

FIKIR: IMX477 satirlari sirayla okur. Kamera kare okunurken hareket ederse
her SATIR farkli anda pozlanir, yani ust satirla alt satir farkli kadar
kayar. Rijit hareket (uctan uca ayni kayma) jole DEGILDIR; jole, kaymanin
SATIRA GORE DEGISMESIDIR.

OLCUM: ardisik iki kare, yatay bantlara bolunur; her bandin kaymasi faz
korelasyonuyla bulunur. Kayma-satir dogrusunun EGIMI x kare yuksekligi =
ust satir ile alt satir arasindaki kayma farki = JOLE (piksel).

  ./jole_olc.py <kayit.mjpeg> [ornek_sayisi]
"""
import sys, os
import numpy as np, cv2

KUCULT = 4          # 4K icin; 2K kayitlarda 2'ye duser (bkz. _kucultme_sec)
                    # jole oransal oldugu icin kuculmede korunur, sonuc
                    # her zaman TAM COZUNURLUK pikseline geri olceklenir
BANT = 20           # yatay bant sayisi (200 Hz titresim ~7 cevrim/kare)
MIN_STD = 6.0       # bu kadar dokusu olmayan bant elenir
MIN_KONTRAST = 12.0 # 1 Eylul 2026: AKSAM cekilen bir kayitta kare kontrasti
                    # 5,8 idi (gunduz kayitlarinda 19-21). O koşulda faz
                    # korelasyonu ardisik kareler arasinda RASTGELE deger
                    # uretiyor ve metrik 4,02 px "dalgalanma" uydurdu —
                    # operator kaydi izledi, dalgalanma YOKTU. Bu kapi o
                    # hatanin tekrarini engelliyor: karanlik kayitta SAYI
                    # VERILMEZ, gecersiz denir.
MIN_TEPKI = 0.05    # faz korelasyonu guveni


def _kucultme_sec(mjpeg, kayit):
    """Ilk kareye bakip ~1000 px genislik hedefler; bant yuksekligi yeterli kalsin."""
    global KUCULT
    with open(mjpeg, 'rb') as f:
        f.seek(int(kayit[0][2]))
        im = cv2.imdecode(np.frombuffer(f.read(int(kayit[0][3])), np.uint8),
                          cv2.IMREAD_GRAYSCALE)
    KUCULT = 4 if im is not None and im.shape[1] >= 3000 else 2
    return (cv2.IMREAD_REDUCED_GRAYSCALE_4 if KUCULT == 4
            else cv2.IMREAD_REDUCED_GRAYSCALE_2)


def kareleri_oku(mjpeg, idx, ornek):
    kayit = [l.split() for l in open(idx) if not l.startswith('#')]
    n = len(kayit)
    if n < 4:
        sys.exit('yeterli kare yok')
    # kaydin tamamina yayilmis ARDISIK ciftler
    bayrak = _kucultme_sec(mjpeg, kayit)
    # YARIM INDIRILMIS dosya destegi: dosya sonunu asan kareler elenir.
    # Boylece indirme surerken bile olcum yapilabiliyor (1 Eylul).
    boyut = os.path.getsize(mjpeg)
    kayit = [k for k in kayit if int(k[2]) + int(k[3]) <= boyut]
    n = len(kayit)
    if n < 4:
        sys.exit('dosyada yeterli TAM kare yok')
    adim = max(1, n // ornek)
    ciftler = [(i, i + 1) for i in range(0, n - 1, adim)][:ornek]
    with open(mjpeg, 'rb') as f:
        for a, b in ciftler:
            gri = []
            for k in (a, b):
                _, _, ofs, uz = kayit[k][:4]
                f.seek(int(ofs))
                veri = np.frombuffer(f.read(int(uz)), np.uint8)
                im = cv2.imdecode(veri, bayrak)
                if im is None:
                    gri = []
                    break
                gri.append(im.astype(np.float32))
            if len(gri) == 2 and gri[0].shape == gri[1].shape:
                yield float(kayit[a][1]), gri[0], gri[1]


def cift_olc(o, s):
    h, w = o.shape
    bh = h // BANT
    pencere = cv2.createHanningWindow((w, bh), cv2.CV_32F)
    satir, dx_l, dy_l = [], [], []
    for i in range(BANT):
        y = i * bh
        a, b = o[y:y + bh], s[y:y + bh]
        if a.std() < MIN_STD:
            continue
        (dx, dy), tepki = cv2.phaseCorrelate(a.copy(), b.copy(), pencere)
        if tepki < MIN_TEPKI:
            continue
        satir.append(y + bh / 2); dx_l.append(dx); dy_l.append(dy)
    if len(satir) < 5:
        return None
    satir = np.array(satir); dx_a = np.array(dx_l); dy_a = np.array(dy_l)
    # AYRIM (1 Eylul 2026): iki bilesen ayni sayiya karisiyordu.
    #  * DOGRUSAL bilesen  = duzgun hareketin makaslamasi. Kare egrilir ama
    #    izgara korunur; QR cozucu afin bozulmayi tolere eder. ZARARSIZ.
    #  * ARTIK (dogruya uymayan) = motor titresiminin satirlari farkli
    #    yonlere kaydirmasi. Izgarayi bozan, QR'i okutmayan sey BUDUR.
    kat_x = np.polyfit(satir, dx_a, 1)
    kat_y = np.polyfit(satir, dy_a, 1)
    art_x = dx_a - np.polyval(kat_x, satir)
    art_y = dy_a - np.polyval(kat_y, satir)
    return {
        'makas_x': abs(kat_x[0]) * h * KUCULT,   # dogrusal — zararsiz
        'makas_y': abs(kat_y[0]) * h * KUCULT,
        'dalga_x': float(art_x.std()) * KUCULT,  # ARTIK — asil jole
        'dalga_y': float(art_y.std()) * KUCULT,
        'dalga_tepe': float(np.abs(art_x).max()) * KUCULT,
        'rijit': float(np.hypot(dx_a.mean(), dy_a.mean())) * KUCULT,
        'bant': len(satir),
    }


def main():
    yol = sys.argv[1] if len(sys.argv) > 1 else sys.exit(__doc__)
    ornek = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    idx = yol[:-6] + '.idx'
    if not os.path.exists(idx):
        sys.exit(f'.idx yok: {idx}')

    sonuc, kontrast = [], []
    for _, o, s in kareleri_oku(yol, idx, ornek):
        kontrast.append(float(o.std()))
        r = cift_olc(o, s)
        if r:
            sonuc.append(r)

    # GECERLILIK KAPISI — sayidan once
    if kontrast:
        kon = float(np.median(kontrast))
        par = None
        if kon < MIN_KONTRAST:
            print(f'dosya      : {os.path.basename(yol)}')
            print(f'kare kontrasti: {kon:.1f}  (gerekli >= {MIN_KONTRAST:.0f})\n')
            print('  🔴 OLCUM GECERSIZ — sahne cok karanlik/dokusuz.')
            print('     Bu koşulda faz korelasyonu ardisik kareler arasinda')
            print('     RASTGELE deger uretir; cikan sayi jole DEGIL gurultudur.')
            print('     Gunduz cekilmis bir kayitla olcun (kontrast 19-21 tipik).')
            sys.exit(2)
    if not sonuc:
        sys.exit('olculebilir cift yok — sahne dokusuz ya da kamera durgun')

    def med(k):
        return float(np.median([r[k] for r in sonuc]))

    def p90(k):
        return float(np.percentile([r[k] for r in sonuc], 90))

    print(f'dosya      : {os.path.basename(yol)}')
    print(f'olculen    : {len(sonuc)} kare cifti ({BANT} bant)')
    print(f'kare kontrasti: {float(np.median(kontrast)):.1f}  ✅ gecerli\n')
    print(f'  rijit hareket      medyan {med("rijit"):7.2f} px   (kare arasi toplam kayma)')
    print(f'  DOGRUSAL makaslama medyan {med("makas_x"):7.2f} px   (duzgun hareket — ZARARSIZ)')
    print(f'  DALGALANMA (artik) medyan {med("dalga_x"):7.2f} px   p90 {p90("dalga_x"):6.2f}   tepe {med("dalga_tepe"):6.2f}')
    print(f'  DALGALANMA dikey   medyan {med("dalga_y"):7.2f} px')
    print()
    j = med('dalga_x')
    print('  Okunusu: DALGALANMA = satirlarin dogrusal hareketten SAPMASI.')
    print('           QR izgarasini bozan bilesen budur; makaslama degil.')
    if j < 1.0:
        print(f'  ✅ dalgalanma {j:.2f} px — ihmal edilebilir')
    elif j < 2.5:
        print(f'  ⚠️  dalgalanma {j:.2f} px — QR modulu 2,25 px tabanina yakin, sinirda')
    else:
        print(f'  🔴 dalgalanma {j:.2f} px — QR izgarasini bozar')


if __name__ == '__main__':
    main()
