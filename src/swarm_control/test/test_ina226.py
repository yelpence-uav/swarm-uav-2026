# Copyright 2026 Yelpence
"""INA226 cevrim mantigi — donanimsiz kilitleme.

Bu sinifin hatalari HATA VERMEZ: yanlis olcek "pil dolu" der, yanlis
isaret "sarj oluyor" der. Ikisi de ucusta pahali. Sayilar veri sayfasindan
(INA226 Rev. B) alindi ve elle dogrulandi.
"""

import math
import unittest

from swarm_control.pil import ina226 as IN


class TestKimlik(unittest.TestCase):
    """Adres taramasi yetmez — kimlik yazmaci tek kesin ayirt edici."""

    def test_dogru_kimlik_KABUL(self):
        self.assertTrue(IN.kimlik_dogru(0x5449, 0x2260))

    def test_baska_cihaz_RED(self):
        # Ayni adreste baska bir I2C cihazi olabilir; yazmaclari anlamsiz
        # sayilar donduru ve "olcum" sanilirdi.
        self.assertFalse(IN.kimlik_dogru(0x0000, 0x0000))
        self.assertFalse(IN.kimlik_dogru(0xFFFF, 0xFFFF))
        self.assertFalse(IN.kimlik_dogru(0x5449, 0x2261))   # INA228
        self.assertFalse(IN.kimlik_dogru(0x5448, 0x2260))


class TestBaraGerilimi(unittest.TestCase):
    """0x02 — 1.25 mV/LSB, ISARETSIZ."""

    def test_sifir(self):
        self.assertAlmostEqual(IN.bara_gerilimi_v(0), 0.0)

    def test_tek_lsb(self):
        self.assertAlmostEqual(IN.bara_gerilimi_v(1), 0.00125)

    def test_6S_dolu_paket(self):
        # 25.2 V (6S x 4.20) -> 25.2 / 0.00125 = 20160 sayim
        self.assertAlmostEqual(IN.bara_gerilimi_v(20160), 25.2, places=4)

    def test_4S_bos_paket(self):
        # 13.2 V (4S x 3.30) -> 10560 sayim
        self.assertAlmostEqual(IN.bara_gerilimi_v(10560), 13.2, places=4)

    def test_ust_bit_ISARET_DEGIL(self):
        """Bara gerilimi isaretsiz — 0x8000 negatif SAYILMAMALI."""
        self.assertGreater(IN.bara_gerilimi_v(0x8000), 40.0)


class TestKalibrasyon(unittest.TestCase):
    """Varsayilan NO-OP olmali; aksi halde sessizce olcegi kaydirir."""

    def test_varsayilan_HAM_degeri_degistirmez(self):
        for ham in (0, 1, 10560, 20160, 0xFFFF):
            self.assertAlmostEqual(IN.bara_gerilimi_kalibre_v(ham),
                                   IN.bara_gerilimi_v(ham), places=9)

    def test_ofset_uygulaniyor(self):
        ham = round(15.89 / IN.BARA_LSB_V)
        self.assertAlmostEqual(
            IN.bara_gerilimi_kalibre_v(ham, ofset_v=-0.22), 15.67, places=2)

    def test_carpan_uygulaniyor(self):
        ham = round(15.89 / IN.BARA_LSB_V)
        self.assertAlmostEqual(
            IN.bara_gerilimi_kalibre_v(ham, carpan=15.67 / 15.89),
            15.67, places=2)

    def test_carpan_ve_ofset_FARKLI_sonuc_verir(self):
        """Tek noktadan kalibrasyon ikisini AYIRAMAZ — bu test o tuzagi
        belgeliyor: ayni noktada esitler, BASKA noktada ayrisirlar.
        """
        ham_dusuk = round(12.00 / IN.BARA_LSB_V)
        ofsetli = IN.bara_gerilimi_kalibre_v(ham_dusuk, ofset_v=-0.22)
        carpanli = IN.bara_gerilimi_kalibre_v(ham_dusuk,
                                              carpan=15.67 / 15.89)
        self.assertGreater(abs(ofsetli - carpanli), 0.05)


class TestSontVeAkim(unittest.TestCase):
    """0x01 — 2.5 uV/LSB, ISARETLI (iki tumleyen)."""

    def test_isaretli16_pozitif(self):
        self.assertEqual(IN.isaretli16(0x0001), 1)
        self.assertEqual(IN.isaretli16(0x7FFF), 32767)

    def test_isaretli16_negatif(self):
        self.assertEqual(IN.isaretli16(0xFFFF), -1)
        self.assertEqual(IN.isaretli16(0x8000), -32768)

    def test_sont_gerilimi_olcek(self):
        self.assertAlmostEqual(IN.sont_gerilimi_v(1), 2.5e-6)
        self.assertAlmostEqual(IN.sont_gerilimi_v(1000), 2.5e-3)

    def test_akim_2mohm_sontta(self):
        # 20 A x 0.002 ohm = 40 mV -> 40e-3 / 2.5e-6 = 16000 sayim
        self.assertAlmostEqual(IN.akim_a(16000, 0.002), 20.0, places=3)

    def test_akim_ISARETLI_sarj_negatif(self):
        """Isaret KORUNMALI — sarj yonunde akim negatiftir.

        Isaretsiz okunsa 65535 civari sayilar cikar ve "binlerce amper"
        gorunurdu — sessiz-yanlis.
        """
        self.assertAlmostEqual(IN.akim_a(0xFFFF & -16000, 0.002), -20.0,
                               places=3)

    def test_sont_bilinmiyorsa_akim_SIFIR(self):
        """Sont bilinmiyorsa akim 0.0 kalir.

        Uydurma bir sont degeri yerine 0.0: gerilim dogru okunur, akim
        "bilinmiyor" olur. AgentStatus.battery_current_a yorumu da 0.0'i
        boyle tanimliyor.
        """
        self.assertEqual(IN.akim_a(16000, 0.0), 0.0)
        self.assertEqual(IN.akim_a(16000, -1.0), 0.0)


class TestDoyma(unittest.TestCase):
    """Sont tavani +-81.92 mV — ustunde yazmac DOYAR, akim KUCUK okunur."""

    def test_azami_akim_2mohm(self):
        self.assertAlmostEqual(IN.azami_akim_a(0.002), 40.96, places=2)

    def test_azami_akim_1mohm(self):
        self.assertAlmostEqual(IN.azami_akim_a(0.001), 81.92, places=2)

    def test_azami_akim_100mohm_DRONE_ICIN_YETERSIZ(self):
        """0.1 ohm sont bir dron icin YETERSIZ.

        Hazir modullerin cogu 0.1 ohm ile gelir: 0.82 A tavan. Bir dronun
        cektigi akimin yanindan bile gecmez.
        """
        self.assertLess(IN.azami_akim_a(0.1), 1.0)

    def test_sont_yoksa_tavan_sifir(self):
        self.assertEqual(IN.azami_akim_a(0.0), 0.0)


class TestYuzdeKestirimi(unittest.TestCase):
    """KESTIRIM, yakit olceri DEGIL — failsafe icin gerilim kullanilir."""

    def test_6S_dolu(self):
        self.assertAlmostEqual(IN.yuzde_kestir(25.2, 6), 100.0, places=1)

    def test_6S_bos(self):
        self.assertAlmostEqual(IN.yuzde_kestir(19.8, 6), 0.0, places=1)

    def test_6S_orta(self):
        self.assertAlmostEqual(IN.yuzde_kestir(22.5, 6), 50.0, places=0)

    def test_kirpiliyor(self):
        self.assertEqual(IN.yuzde_kestir(30.0, 6), 100.0)
        self.assertEqual(IN.yuzde_kestir(10.0, 6), 0.0)

    def test_hucre_bilinmiyorsa_SIFIR(self):
        self.assertEqual(IN.yuzde_kestir(22.5, 0), 0.0)

    def test_gerilim_sifirsa_SIFIR(self):
        self.assertEqual(IN.yuzde_kestir(0.0, 6), 0.0)


class TestGercekcilikDenetimi(unittest.TestCase):
    """Uctan uca: 6S paket, 2 mohm sont, 20 A cekiliyor."""

    def test_tipik_ucus_hali(self):
        ham_bara = round(22.2 / IN.BARA_LSB_V)          # 6S nominal 22.2 V
        ham_sont = round((20.0 * 0.002) / IN.SONT_LSB_V)
        gerilim = IN.bara_gerilimi_v(ham_bara)
        akim = IN.akim_a(ham_sont, 0.002)
        self.assertAlmostEqual(gerilim, 22.2, places=2)
        self.assertAlmostEqual(akim, 20.0, places=2)
        yuzde = IN.yuzde_kestir(gerilim, 6)
        self.assertTrue(0.0 < yuzde < 100.0)
        self.assertFalse(math.isnan(yuzde))


if __name__ == '__main__':
    unittest.main()
