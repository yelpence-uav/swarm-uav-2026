# Copyright 2026 Yelpence
"""BASLAT paketine eklenen DORT SURU AYARI — 5 Eylul 2026.

Operator: "arayuzdeki ucus ayarlari cok kisir, genisletelim."

Eklenenler: morf hizi · hareket hizi · yaw hizi tavani · egim tavani.
Hepsi _GOREV_FMT'in REZERVINDEN yendi:

    once : '<BBbBBH9x'      7 bayt kullanilan + 9 rezerv
    simdi: '<BBbBBHBBBB5x'  11 bayt kullanilan + 5 rezerv

🔴 PAKET 16 BAYT KALDI. Yeni mesh tipi acilmadi, FIRMWARE degismedi,
mesh yuku artmadi — madde 29'un "degerler BASLAT paketinin icinde gider"
tasariminin butun amaci buydu.

Sozlesme aralik/irtifa ile AYNI: 0 = BELIRTILMEDI, alici kendi
varsayilanini korur.
"""

import unittest

from swarm_control.esp32_bridge import packet_parser as pp


class TestPaketBoyutu(unittest.TestCase):
    """Mesh 16 bayt tasiyor — buyumek firmware degisikligi demek."""

    def test_paket_16_BAYT_kaldi(self):
        b = pp.gorev_paketle(1, 0, 0, 0)
        self.assertEqual(len(b), 16)

    def test_dolu_paket_de_16_bayt(self):
        b = pp.gorev_paketle(
            1, 0, 0, 0, aralik_m=25.5, irtifa_m=30.0,
            morf_hiz_mps=3.0, hareket_hiz_mps=5.0,
            yaw_hiz_deg_s=25.0, egim_tavan_deg=30.0)
        self.assertEqual(len(b), 16)


class TestGidisDonus(unittest.TestCase):
    """Sahadaki gercek varsayilanlarla gidis-donus."""

    def test_dort_alan_korunur(self):
        b = pp.gorev_paketle(
            pp.GOREV_TIP_G2_BASLAT, 0, 0, 0,
            aralik_m=7.0, irtifa_m=8.0,
            morf_hiz_mps=0.6, hareket_hiz_mps=2.0,
            yaw_hiz_deg_s=14.7, egim_tavan_deg=15.0)
        g = pp.gorev_coz(b)
        self.assertAlmostEqual(g.aralik_m, 7.0, places=3)
        self.assertAlmostEqual(g.irtifa_m, 8.0, places=3)
        self.assertAlmostEqual(g.morf_hiz_mps, 0.6, places=3)
        self.assertAlmostEqual(g.hareket_hiz_mps, 2.0, places=3)
        self.assertAlmostEqual(g.yaw_hiz_deg_s, 14.7, places=3)
        self.assertAlmostEqual(g.egim_tavan, 15.0, places=3)

    def test_BOS_paket_sifir_doner(self):
        """0 = belirtilmedi; ucak kendi varsayilanini korur."""
        g = pp.gorev_coz(pp.gorev_paketle(1, 0, 0, 0))
        self.assertEqual(g.morf_hiz_dm, 0)
        self.assertEqual(g.hareket_hiz_dm, 0)
        self.assertEqual(g.yaw_hiz_ddeg, 0)
        self.assertEqual(g.egim_tavan_deg, 0)

    def test_ESKI_alanlar_bozulmadi(self):
        """Aralik/irtifa yerinden kaymamali (offset degisti)."""
        g = pp.gorev_coz(pp.gorev_paketle(
            7, 3, -2, 9, aralik_m=12.0, irtifa_m=100.0))
        self.assertEqual(g.tip, 7)
        self.assertEqual(g.param1, 3)
        self.assertEqual(g.param2, -2)
        self.assertEqual(g.bekleme_suresi_s, 9)
        self.assertAlmostEqual(g.aralik_m, 12.0, places=3)
        self.assertAlmostEqual(g.irtifa_m, 100.0, places=3)


class TestSessizKirpmaYok(unittest.TestCase):
    """Sinir disi deger SESSIZCE kirpilmaz — ValueError atilir.

    Gerekce aralik/irtifa ile ayni: kirpmak "15 derece istedim, 25.5
    uctu" sinifi bir hata uretirdi ve hicbir yerde gorunmezdi.
    """

    def test_morf_hizi_tavani_asarsa_HATA(self):
        with self.assertRaises(ValueError):
            pp.gorev_paketle(1, 0, 0, 0, morf_hiz_mps=30.0)

    def test_yaw_hizi_tavani_asarsa_HATA(self):
        with self.assertRaises(ValueError):
            pp.gorev_paketle(1, 0, 0, 0, yaw_hiz_deg_s=99.0)

    def test_egim_tavani_asarsa_HATA(self):
        with self.assertRaises(ValueError):
            pp.gorev_paketle(1, 0, 0, 0, egim_tavan_deg=300.0)

    def test_negatif_deger_HATA(self):
        with self.assertRaises(ValueError):
            pp.gorev_paketle(1, 0, 0, 0, hareket_hiz_mps=-1.0)

    def test_hata_mesaji_ALAN_ADINI_soyler(self):
        """Sahada hangi alanin reddedildigi gorunmeli."""
        with self.assertRaises(ValueError) as c:
            pp.gorev_paketle(1, 0, 0, 0, yaw_hiz_deg_s=99.0)
        self.assertIn('yaw_hiz_deg_s', str(c.exception))


class TestCozunurluk(unittest.TestCase):
    """1 baytlik kodlamanin cozunurlugu kabul edilen degerleri tasimali."""

    def test_yaw_ondalik_korunur(self):
        """14.7 deg/s turetilmis bir tavan — 0.1 cozunurluk sart."""
        g = pp.gorev_coz(pp.gorev_paketle(1, 0, 0, 0, yaw_hiz_deg_s=14.7))
        self.assertAlmostEqual(g.yaw_hiz_deg_s, 14.7, places=3)

    def test_morf_ondalik_korunur(self):
        g = pp.gorev_coz(pp.gorev_paketle(1, 0, 0, 0, morf_hiz_mps=0.6))
        self.assertAlmostEqual(g.morf_hiz_mps, 0.6, places=3)


if __name__ == '__main__':
    unittest.main()
