# Copyright 2026 Yelpence
"""RC eksen donusumu — SAHA OLCUMUNU kilitleyen birim testler.

30 Agustos 2026, ylp00, FS-i6X #2, i-BUS'tan 3246 cerceve:
    cubuk ILERI -> CH2 pitch 1974 | SAGA -> CH1 roll 1981
    cubuk SAGA  -> CH4 yaw   1014 | gaz YUKARI 1988, dipte 1001

Bu dosya o olcumu kalici hale getiriyor: isaret bir daha degistirilirse
test duser ve kimse "acaba hangisiydi" diye tekrar ucmaz.
"""

import unittest

from swarm_state_machine.mode_manager import rc_eksen as RC


class TestOlculenIsaretler(unittest.TestCase):
    """SwarmControlCommand.msg sozlesmesine gore isaret dogrulamasi."""

    def test_pitch_ILERI_pozitif(self):
        """cubuk ILERI (olculen 1974) -> pitch_cmd > 0 (= ileri hareket)."""
        v = RC.eksen_normalize(1974, RC.TERS_PITCH)
        self.assertGreater(v, 0.9, 'pitch ILERI pozitif olmali')

    def test_pitch_GERI_negatif(self):
        v = RC.eksen_normalize(1026, RC.TERS_PITCH)
        self.assertLess(v, -0.9)

    def test_roll_SAGA_pozitif(self):
        """cubuk SAGA (olculen 1981) -> roll_cmd > 0 (= saga hareket)."""
        v = RC.eksen_normalize(1981, RC.TERS_ROLL)
        self.assertGreater(v, 0.9)

    def test_yaw_SAGA_pozitif(self):
        """🔴 TEK TERS KANAL: saga = ALT uc (1014) ama cmd POZITIF olmali."""
        v = RC.eksen_normalize(1014, RC.TERS_YAW)
        self.assertGreater(v, 0.9, 'yaw SAGA saat yonu = pozitif olmali')

    def test_yaw_SOLA_negatif(self):
        v = RC.eksen_normalize(1986, RC.TERS_YAW)
        self.assertLess(v, -0.9)

    def test_eski_kod_pitch_i_TERS_uretiyordu(self):
        """Regresyon: duzeltmeden onceki davranis yanlisti, geri gelmesin."""
        eski = -((1974 - 1500.0) / 500.0)      # kodun 30 Agu oncesi hali
        yeni = RC.eksen_normalize(1974, RC.TERS_PITCH)
        self.assertLess(eski, 0.0)
        self.assertGreater(yeni, 0.0)


class TestEksenNormalize(unittest.TestCase):

    def test_merkez_sifir(self):
        self.assertAlmostEqual(RC.eksen_normalize(1500), 0.0, places=6)

    def test_uclar(self):
        self.assertAlmostEqual(RC.eksen_normalize(2000), 1.0, places=6)
        self.assertAlmostEqual(RC.eksen_normalize(1000), -1.0, places=6)

    def test_aralik_disi_KIRPILIR(self):
        self.assertEqual(RC.eksen_normalize(2500), 1.0)
        self.assertEqual(RC.eksen_normalize(500), -1.0)

    def test_ters_bayragi_isareti_cevirir(self):
        self.assertAlmostEqual(RC.eksen_normalize(1750, False), 0.5, places=6)
        self.assertAlmostEqual(RC.eksen_normalize(1750, True), -0.5, places=6)


class TestGazNormalize(unittest.TestCase):

    def test_dip_sifir(self):
        """Olculen dinlenme PWM 1001 -> ~0."""
        self.assertLess(RC.gaz_normalize(1001), 0.01)

    def test_tepe_bir(self):
        self.assertGreater(RC.gaz_normalize(1988), 0.98)

    def test_orta_yarim(self):
        self.assertAlmostEqual(RC.gaz_normalize(1500), 0.5, places=6)

    def test_kirpma(self):
        self.assertEqual(RC.gaz_normalize(900), 0.0)
        self.assertEqual(RC.gaz_normalize(2200), 1.0)


class TestGazMerkezKapisi(unittest.TestCase):
    """🔴 Gaz dipteyken suru tam hizla alcalirdi — kapinin sinavi."""

    PAY = 0.2

    @staticmethod
    def _cmd(pwm):
        """joystick_interpreter zinciri: PWM -> [0,1] -> [-1,+1]."""
        return RC.gaz_normalize(pwm) * 2.0 - 1.0

    def test_dipteki_cubuk_TAM_ALCALMA_uretir(self):
        """Kapinin var olma sebebi: dinlenme konumu -1.0 demek."""
        self.assertAlmostEqual(self._cmd(1001), -0.998, places=3)

    def test_dipteki_cubuk_kapiyi_GECEMEZ(self):
        self.assertFalse(RC.gaz_merkezde(self._cmd(1001), self.PAY))

    def test_tepedeki_cubuk_kapiyi_GECEMEZ(self):
        self.assertFalse(RC.gaz_merkezde(self._cmd(1988), self.PAY))

    def test_merkez_GECER(self):
        self.assertTrue(RC.gaz_merkezde(self._cmd(1500), self.PAY))

    def test_merkeze_yakin_GECER(self):
        for pwm in (1450, 1550):
            self.assertTrue(RC.gaz_merkezde(self._cmd(pwm), self.PAY), pwm)

    def test_pay_sinirinda(self):
        self.assertTrue(RC.gaz_merkezde(0.2, 0.2))
        self.assertFalse(RC.gaz_merkezde(0.21, 0.2))


if __name__ == '__main__':
    unittest.main()
