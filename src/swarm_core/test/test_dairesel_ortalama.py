# Copyright 2026 Yelpence
"""dairesel_ortalama_deg birim testleri (B17, 30 Agustos 2026).

Kapatilan kaza: SwarmState.formation_heading_deg hic hesaplanmiyordu ve
kalici 0.0 idi; Gorev 2'de kontrolun pilota gectigi anda suru kuzeye
donuyordu. Duzeltmenin cekirdegi bu fonksiyon — ve ARITMETIK ortalamayla
yazilsaydi kaza SESSIZCE devam ederdi (359/0/1 -> 240 derece).
"""

import unittest

from swarm_core.formation_control.manual_kinematics import (
    dairesel_ortalama_deg,
)


class TestDaireselOrtalama(unittest.TestCase):

    def test_hepsi_ayni(self):
        h, r = dairesel_ortalama_deg([90.0, 90.0, 90.0])
        self.assertAlmostEqual(h, 90.0, places=6)
        self.assertAlmostEqual(r, 1.0, places=6)

    def test_SARMA_noktasi(self):
        """🔴 Asil sebep: 359/0/1'in ortalamasi 0'dir, 120 DEGIL."""
        h, r = dairesel_ortalama_deg([359.0, 0.0, 1.0])
        self.assertAlmostEqual(h, 0.0, places=4)
        self.assertGreater(r, 0.99)
        # Aritmetik ortalama olsaydi 120 cikardi — kaza tam da buydu.
        self.assertNotAlmostEqual(sum([359.0, 0.0, 1.0]) / 3.0, h, places=1)

    def test_sarma_360_yakininda(self):
        h, _ = dairesel_ortalama_deg([350.0, 10.0])
        self.assertAlmostEqual(h, 0.0, places=4)

    def test_cikti_araligi_0_360(self):
        for aci in (-90.0, -1.0, 0.0, 180.0, 359.9, 720.0):
            h, _ = dairesel_ortalama_deg([aci])
            self.assertGreaterEqual(h, 0.0)
            self.assertLess(h, 360.0)

    def test_dagilmis_acilar_TUTARLILIK_DUSUK(self):
        """Ucaklar farkli yone bakiyorsa ortalama zayif — cagiran uyarmali."""
        _, r = dairesel_ortalama_deg([0.0, 120.0, 240.0])
        self.assertLess(r, 0.1)

    def test_TAM_ZIT_tanimsiz(self):
        """180 derece ayrik iki aci: ortalama TANIMSIZ, (0,0) donmeli."""
        h, r = dairesel_ortalama_deg([0.0, 180.0])
        self.assertEqual((h, r), (0.0, 0.0))

    def test_bos_liste(self):
        self.assertEqual(dairesel_ortalama_deg([]), (0.0, 0.0))

    def test_hafif_dagilim_tutarliligi_yuksek(self):
        """+-5 derece sacilma saglikli sayilmali (esik 0.90)."""
        _, r = dairesel_ortalama_deg([85.0, 90.0, 95.0])
        self.assertGreater(r, 0.99)

    def test_R_yayilmayla_azalir(self):
        _, dar = dairesel_ortalama_deg([88.0, 90.0, 92.0])
        _, genis = dairesel_ortalama_deg([60.0, 90.0, 120.0])
        self.assertGreater(dar, genis)

    def test_kuzeye_bakan_suru_GUNEYE_donmez(self):
        """Uctan uca senaryo: kuzeye dizilmis sürü 0 derece vermeli."""
        h, r = dairesel_ortalama_deg([358.7, 0.4, 1.9])
        self.assertLess(min(abs(h), abs(h - 360.0)), 2.0)
        self.assertGreater(r, 0.99)


if __name__ == '__main__':
    unittest.main()
