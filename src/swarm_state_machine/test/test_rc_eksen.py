# Copyright 2026 Yelpence
"""RC eksen donusumu — SAHA OLCUMUNU kilitleyen birim testler.

🔴 GECERLI OLCUM — 31 Agustos 2026, ylp00, YENI BIND EDILEN KUMANDA:
    cubuk ILERI -> CH2 pitch 2000 | SAGA -> CH1 roll 1998
    cubuk SAGA  -> CH4 yaw   2000 | gaz YUKARI 2000, dipte 1000
    -> DORDU DE UST UC, hicbir kanal cevrilmiyor.

Onceki kumandada (30 Agustos, FS-i6X #2) yaw saga ALT uca (1014)
gidiyordu ve kod onu ceviriyordu. Kumanda degisince olcum de degisti.

Bu dosya olcumu kalici hale getiriyor: isaret bir daha degistirilirse
test duser ve kimse "acaba hangisiydi" diye tekrar ucmaz.
"""

import unittest

from swarm_state_machine.mode_manager import rc_eksen as RC


class TestOlculenIsaretler(unittest.TestCase):
    """SwarmControlCommand.msg sozlesmesine gore isaret dogrulamasi."""

    def test_pitch_ILERI_pozitif(self):
        """cubuk ILERI (olculen 2000) -> pitch_cmd > 0 (= ileri hareket)."""
        v = RC.eksen_normalize(2000, RC.TERS_PITCH)
        self.assertGreater(v, 0.9, 'pitch ILERI pozitif olmali')

    def test_pitch_GERI_negatif(self):
        v = RC.eksen_normalize(1000, RC.TERS_PITCH)
        self.assertLess(v, -0.9)

    def test_roll_SAGA_pozitif(self):
        """cubuk SAGA (olculen 1998) -> roll_cmd > 0 (= saga hareket)."""
        v = RC.eksen_normalize(1998, RC.TERS_ROLL)
        self.assertGreater(v, 0.9)

    def test_yaw_SAGA_pozitif(self):
        """cubuk SAGA (olculen 2000) -> yaw_cmd > 0 (= saat yonu)."""
        v = RC.eksen_normalize(2000, RC.TERS_YAW)
        self.assertGreater(v, 0.9, 'yaw SAGA saat yonu = pozitif olmali')

    def test_yaw_SOLA_negatif(self):
        v = RC.eksen_normalize(1000, RC.TERS_YAW)
        self.assertLess(v, -0.9)

    def test_ESKI_KUMANDA_ceviriminin_geri_gelmemesi(self):
        """🔴 Regresyon: TERS_YAW=True geri gelirse yaw TERS calisir.

        Onceki kumandada saga = 1014 (ALT uc) idi ve cevirmek SARTTI.
        Yeni kumandada saga = 2000; ayni ceviri simdi HATA olur — pilot
        saga cevirir, suru SOLA doner ve hicbir yerde hata gorunmez.
        """
        self.assertFalse(RC.TERS_YAW, 'yeni kumandada yaw CEVRILMEZ')
        cevrilmis = RC.eksen_normalize(2000, True)      # eski davranis
        self.assertLess(cevrilmis, 0.0, 'ceviri saga komutunu SOLA yapar')

    def test_gaz_YUKARI_tam(self):
        """Gaz ORTALANMAZ: dip 1000 -> 0.0, tepe 2000 -> 1.0."""
        self.assertAlmostEqual(RC.gaz_normalize(1000), 0.0, places=3)
        self.assertAlmostEqual(RC.gaz_normalize(2000), 1.0, places=3)


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
        """Testin amaci ISARET; buyukluk olu banda gore olceklenir."""
        ileri = RC.eksen_normalize(1750, False)
        geri = RC.eksen_normalize(1750, True)
        self.assertGreater(ileri, 0.0)
        self.assertAlmostEqual(geri, -ileri, places=9)


class TestOluBant(unittest.TestCase):
    """🔴 31 Agustos 2026 — UCUSTA OLCULDU, ucak "geziyordu".

    Cubuklar merkezde dururken bile PWM tam 1500 degil (olculen dinlenme:
    roll 1501 · pitch 1503 · yaw 1502). Olu bant olmadigi icin bu sapma
    surekli komuta donusuyordu ve ucus kaydinda formasyon heading'i
    13 saniyede 212.7 -> 214.0 kaydi (0.1 deg/s), YAW CUBUGU SIFIRKEN.
    """

    def test_olculen_dinlenme_degerleri_SIFIR_uretir(self):
        for pwm in (1501, 1502, 1503, 1499, 1498, 1497):
            self.assertEqual(
                RC.eksen_normalize(pwm), 0.0,
                f'PWM {pwm} sifir uretmiyor — ucak yavasca kayar')

    def test_merkez_sifir(self):
        self.assertEqual(RC.eksen_normalize(1500), 0.0)

    def test_tam_basildiginda_yine_TAM_skala(self):
        """Olu bant menzili kirpmamali: uc noktalar hala +-1.0."""
        self.assertAlmostEqual(RC.eksen_normalize(2000), 1.0, places=6)
        self.assertAlmostEqual(RC.eksen_normalize(1000), -1.0, places=6)

    def test_olu_bandi_terk_ederken_SICRAMA_YOK(self):
        """Yalnizca sifirlansaydi cikis 0'dan olu banda SICRARDI.

        Yeniden olcekleme sayesinde gecis surekli: esigin hemen ustunde
        cikis sifira yakin olmali.
        """
        esik_pwm = RC.PWM_MERKEZ + RC.OLU_BANT * RC.PWM_YARIM
        hemen_ustu = RC.eksen_normalize(esik_pwm + 1)
        self.assertGreater(hemen_ustu, 0.0)
        self.assertLess(hemen_ustu, 0.01,
                        'olu bant cikisinda sicrama var')

    def test_olu_bant_KAPATILABILIR(self):
        """olu=0 eski dogrusal davranisi verir (kiyas/teshis icin)."""
        self.assertAlmostEqual(RC.eksen_normalize(1750, olu=0.0), 0.5,
                               places=6)
        self.assertNotEqual(RC.eksen_normalize(1503, olu=0.0), 0.0)

    def test_esik_olculen_sapmanin_USTUNDE(self):
        """Olculen en buyuk sapma 3 us = 0.006 normalize; esik ondan
        belirgin olcude buyuk olmali ki trim kaymasi da yutulsun."""
        olculen_en_buyuk = 3.0 / RC.PWM_YARIM
        self.assertGreater(RC.OLU_BANT, olculen_en_buyuk * 3.0)
        # Ama pilotun hissedecegi kadar buyuk de olmamali.
        self.assertLess(RC.OLU_BANT, 0.10)


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
