# Copyright 2026 Yelpence
"""SURU HAREKETINDE SAGA-SOLA YALPA — 5 Eylul 2026, sahada.

BELIRTI (operator): "ileri geri sag sol hareket yaptim, hareketler gayet
iyiydi ve akiciydi ama iki ucak da oldugu yerde az sekilde bir saga bir
sola yatti. Kucuk bir yatis ama sik yasandigi icin salinim gorunuyor."

OLCULEN (ylp00 + ylp01 bag, hareket penceresi t=22..31 sn):

    setpoint dalgasi (RMS)   asili 0.003 m  ->  harekette 0.048 m
    KOMUT roll dalgasi       asili 0.31 deg ->  harekette 2.33 deg (t-t 9.3)
    GERCEK roll dalgasi      asili 0.37 deg ->  harekette 0.71 deg (t-t 3.4)

Komut hizi uc terim: v_svt + v_sonum + v_ff. Aci genligi ayristirmasi:

    SVT (-0.8 * hata)      8.6 deg     <- duzgun
    SONUM (-0.35 * hiz)    2.4 deg     <- duzgun
    GIDEN KOMUT           53.6 deg     <- savruk

Sapmanin tamami v_ff'ten. Kok neden ve tam sayilar: vff_pencere.py.

BU DOSYA SAHADAKI DIZIYI OYNATIYOR — uydurma desen degil. `_OLCUM`,
ylp00'in /drone_1/control/setpoint hedefinden alinmis gercek konum izi
(1 cm cozunurlukte loglandi). Ayni izle:

    eski yol (pencere 0.00)   42.7 deg savrulma   <- kusur ureiyor
    yeni yol (pencere 0.25)   10.7 deg            <- 4 kat dar

42.7 ile sahadaki 53.6 arasindaki fark diger iki terimden ve 1 cm
yuvarlamadan geliyor; kusuru yeniden uretmeye fazlasiyla yetiyor.

Pencere neden 0.25: 0.20 -> 11.0, 0.25 -> 10.7, 0.30 -> 9.9, 0.40 -> 7.8
deg. 0.25'ten sonra kazanc duruyor cunku SVT teriminin kendi tabani
zaten 8.6 deg. Daha genis pencere sadece gecikme ekler.

KUSURUN KENDISI DE TEST EDILIYOR (TestKusurHalaUretiliyor): yoksa
`vff_pencere_s=0.0` geri donus yolu sessizce bozulur ve kimse gormez.
"""

import math
import unittest

from swarm_core.formation_control.vff_pencere import MerkezHiziKestirici

# --- SAHADA OLCULEN IZ ---------------------------------------------------
# (ms, hedef_x, hedef_y) — ylp00, 5 Eylul, ileri hareket.
# Adim dizisi x'te: 0.09 0.09 0.10 0.10 0.00 0.10 0.00 0.08 0.00 ...
# "bir tick 0.10 m, sonraki 0.00" deseni ciplak gozle gorunuyor.
_OLCUM = [
    (36, 7.29, -0.09), (86, 7.38, -0.18), (139, 7.47, -0.24),
    (186, 7.57, -0.24), (238, 7.67, -0.34), (288, 7.67, -0.34),
    (337, 7.77, -0.35), (389, 7.77, -0.45), (437, 7.85, -0.42),
    (486, 7.85, -0.42), (537, 7.94, -0.43), (588, 7.96, -0.53),
    (637, 8.05, -0.53), (689, 8.05, -0.53), (736, 8.07, -0.63),
    (788, 8.17, -0.64), (839, 8.16, -0.64), (886, 8.26, -0.64),
    (937, 8.26, -0.74), (987, 8.36, -0.74), (1038, 8.35, -0.73),
    (1087, 8.35, -0.73), (1140, 8.45, -0.83), (1186, 8.46, -0.84),
    (1236, 8.40, -0.80), (1287, 8.50, -0.80), (1336, 8.52, -0.90),
    (1386, 8.62, -0.90),
]
_IZ_SURE_S = (_OLCUM[-1][0] - _OLCUM[0][0]) / 1000.0
_IZ_DX = _OLCUM[-1][1] - _OLCUM[0][1]
_IZ_DY = _OLCUM[-1][2] - _OLCUM[0][2]
# Izin tasidigi gercek merkez hizi.
_GERCEK_HIZ = math.hypot(_IZ_DX, _IZ_DY) / _IZ_SURE_S

DT = 0.05          # 20 Hz yayin
ADIM = 0.10        # target_ramp_mps=0 -> max_speed 2.0 * 0.05 = 0.10 m


def _saha_oynat(kes, tur=6):
    """Olculen izi ust uste ekleyerek oynatir (ayni desen, surekli hareket).

    Ilk iki tur gecici rejim sayilir ve olcume katilmaz.
    """
    acilar = []
    hizlar = []
    for k in range(tur):
        for ms, x, y in _OLCUM:
            t = k * (_IZ_SURE_S + DT) + ms / 1000.0
            vx, vy, _ = kes.guncelle(t, x + k * _IZ_DX, y + k * _IZ_DY, 0.0)
            if k >= 2:
                acilar.append(math.degrees(math.atan2(vy, vx)))
                hizlar.append(math.hypot(vx, vy))
    return acilar, hizlar


def _genlik(acilar):
    return max(acilar) - min(acilar)


class TestKusurHalaUretiliyor(unittest.TestCase):
    """pencere_s = 0.0 ESKI yol — geri donus yolunun kaniti.

    Bu testler GECMEK zorunda: sahada olculen savrulmayi hala uretiyorlar.
    """

    def test_eski_yol_YONU_savuruyor(self):
        a, _ = _saha_oynat(MerkezHiziKestirici(pencere_s=0.0, lpf_alpha=0.3))
        self.assertGreater(_genlik(a), 35.0)

    def test_eski_yol_IKI_KATI_ve_SIFIR_okuyor(self):
        """Ham turev sirayla IKI KATINI ve SIFIRI okur.

        Hedef 0.10 m ilerledi, payda 0.05 sn -> 2.0 m/s; sonraki tick
        hedef durdu -> 0.0. Gercek merkez hizi ise 1.0 m/s.
        """
        kes = MerkezHiziKestirici(pencere_s=0.0, lpf_alpha=1.0)  # LPF kapali
        t = x = 0.0
        okunan = []
        for k in range(20):
            t += DT
            if k % 2 == 0:
                x += ADIM
            vx, _, _ = kes.guncelle(t, x, 0.0, 0.0)
            okunan.append(vx)
        gercek = ADIM / (2 * DT)
        self.assertAlmostEqual(max(okunan[4:]), 2.0 * gercek, places=6)
        self.assertAlmostEqual(min(okunan[4:]), 0.0, places=6)


class TestPencereliDuzeltme(unittest.TestCase):
    """pencere_s > 0 — pay ile payda YAPISI GEREGI ayni araliktan."""

    def test_yon_savrulmasi_DARALIYOR(self):
        a, _ = _saha_oynat(MerkezHiziKestirici(pencere_s=0.25, lpf_alpha=0.3))
        self.assertLess(_genlik(a), 15.0)

    def test_ESKISINDEN_en_az_3_KAT_dar(self):
        """Ayni iz, iki yol — karsilastirma tek kosuda."""
        eski, _ = _saha_oynat(
            MerkezHiziKestirici(pencere_s=0.0, lpf_alpha=0.3))
        yeni, _ = _saha_oynat(
            MerkezHiziKestirici(pencere_s=0.25, lpf_alpha=0.3))
        self.assertLess(_genlik(yeni) * 3.0, _genlik(eski))

    def test_buyukluk_GERCEK_merkez_hizini_verir(self):
        """Savrulma gitsin ama hiz da dogru olsun — 2x veya 0 degil."""
        _, h = _saha_oynat(MerkezHiziKestirici(pencere_s=0.25, lpf_alpha=0.3))
        self.assertAlmostEqual(sum(h) / len(h), _GERCEK_HIZ, delta=0.10)

    def test_sabit_hizli_hedefte_TAM_dogru(self):
        """Hedef her tick ilerlerse (rampa sinirli hal) turev tam olmali."""
        kes = MerkezHiziKestirici(pencere_s=0.25, lpf_alpha=1.0)
        t = x = 0.0
        for _ in range(40):
            t += DT
            x += 2.0 * DT                      # 2.0 m/s duz
            vx, _, _ = kes.guncelle(t, x, 0.0, 0.0)
        self.assertAlmostEqual(vx, 2.0, places=6)


class TestDurunca(unittest.TestCase):
    """Hedef durunca v_ff KENDILIGINDEN sifira inmeli.

    🔴 Pencereli turevin en riskli tarafi bu: "degismediyse eski degeri
    tut" diye yazilsaydi cubuk birakildiginda suru KAYMAYA DEVAM ederdi.
    Pencere bosaldigi icin oyle olmuyor — ama sozlesme yazili olmali.
    """

    def test_cubuk_birakilinca_soner(self):
        kes = MerkezHiziKestirici(pencere_s=0.25, lpf_alpha=0.3)
        _saha_oynat(kes, tur=4)
        self.assertGreater(math.hypot(kes.vx, kes.vy), 0.5)
        t = 10 * (_IZ_SURE_S + DT)
        son_x = _OLCUM[-1][1] + 3 * _IZ_DX
        son_y = _OLCUM[-1][2] + 3 * _IZ_DY
        for _ in range(40):                    # 2 sn hedef SABIT
            t += DT
            kes.guncelle(t, son_x, son_y, 0.0)
        self.assertLess(math.hypot(kes.vx, kes.vy), 0.02)

    def test_asili_baslangicta_HIC_hiz_uretmez(self):
        """Merkez hic kimildamazsa v_ff sifir kalir.

        Asili haldeki olcum (setpoint dalgasi 0.003 m) bunun sahadaki
        karsiligiydi.
        """
        kes = MerkezHiziKestirici(pencere_s=0.25, lpf_alpha=0.3)
        t = 0.0
        for _ in range(60):
            t += DT
            vx, vy, vz = kes.guncelle(t, 5.0, -2.0, -9.3)
        self.assertAlmostEqual(vx, 0.0, places=9)
        self.assertAlmostEqual(vy, 0.0, places=9)
        self.assertAlmostEqual(vz, 0.0, places=9)


class TestBayatlikKapisi(unittest.TestCase):
    """`vff_hold_s` kapisi sifirla() cagiriyor — gecmis de silinmeli.

    Silinmezse komut akisi geri geldiginde kestirici, kesinti boyunca
    hedefin kimildamadigini "gercek" sanip yanlis bir hiz uretirdi.
    """

    def test_sifirla_hizi_ve_gecmisi_temizler(self):
        kes = MerkezHiziKestirici(pencere_s=0.25, lpf_alpha=0.3)
        _saha_oynat(kes, tur=4)
        self.assertGreater(math.hypot(kes.vx, kes.vy), 0.5)
        kes.sifirla()
        self.assertEqual((kes.vx, kes.vy, kes.vz), (0.0, 0.0, 0.0))
        # Gecmis de bos: ilk ornek yeniden taban olmali, sicrama olmamali.
        vx, vy, _ = kes.guncelle(100.0, 999.0, 999.0, 0.0)
        self.assertEqual((vx, vy), (0.0, 0.0))


class TestZamanSicramasi(unittest.TestCase):
    """dt bozuk gelirse sessizce absurt hiz uretilmemeli."""

    def test_ayni_zaman_damgasi_hiz_uretmez(self):
        kes = MerkezHiziKestirici(pencere_s=0.25, lpf_alpha=0.3)
        kes.guncelle(1.0, 0.0, 0.0, 0.0)
        vx, _, _ = kes.guncelle(1.0, 0.5, 0.0, 0.0)   # dt = 0
        self.assertEqual(vx, 0.0)

    def test_gecmis_sinirsiz_buyumez(self):
        kes = MerkezHiziKestirici(pencere_s=0.25, lpf_alpha=0.3)
        for _ in range(2000):
            kes.guncelle(1.0, 0.0, 0.0, 0.0)          # zaman ilerlemiyor
        self.assertLessEqual(len(kes._gecmis), 400)


if __name__ == '__main__':
    unittest.main()
