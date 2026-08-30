"""SwD kalkis/inis salteri — kenar ve mandal davranisi.

🔴 BU TESTLER 30 AGUSTOS 2026 SAHA OLAYINDAN DOGDU. Pilot SwD'yi kalkisa
alinca uc ucak ARM oldu ve "kumandanin hicbir tusuyla inis veremedim".
Iptal yolunun HER KOSULDA calistigi burada kanitlanir.
"""

import unittest

from swarm_state_machine.mode_manager.swd_mandal import SwdMandal


UST = 1000    # SwD yukari (PWM 2000 -> aux +1000) = KALKIS
ALT = -1000   # SwD asagi  (PWM 1000 -> aux -1000) = INIS


class TestIlkCerceve(unittest.TestCase):
    """Ilk cerceve kenar SAYILMAZ — sahte kalkis uretmemeli."""

    def test_ilk_cerceve_UST_kalkis_URETMEZ(self):
        # Kumanda SwD YUKARIDA ve SwA ACIK ikenki `docker restart`.
        m = SwdMandal()
        m.guncelle(UST, emniyet_acik=True)
        self.assertFalse(m.kalkisi_tuket())
        self.assertFalse(m.inis_mandali)

    def test_ilk_cerceve_ALT_inis_URETMEZ(self):
        m = SwdMandal()
        m.guncelle(ALT, emniyet_acik=True)
        self.assertFalse(m.inis_mandali)

    def test_ilk_cerceveden_SONRA_kenar_calisir(self):
        m = SwdMandal()
        m.guncelle(ALT, emniyet_acik=True)   # tohum
        m.guncelle(UST, emniyet_acik=True)   # gercek kenar
        self.assertTrue(m.kalkisi_tuket())


class TestKalkisTekAtis(unittest.TestCase):
    """Kalkis MANDAL DEGIL: salter yukarida kalinca tekrar uretmemeli."""

    def test_kalkis_bir_kez_tuketilir(self):
        m = SwdMandal()
        m.guncelle(ALT, emniyet_acik=True)
        m.guncelle(UST, emniyet_acik=True)
        self.assertTrue(m.kalkisi_tuket())
        self.assertFalse(m.kalkisi_tuket())

    def test_salter_ustte_KALINCA_tekrar_uretmez(self):
        m = SwdMandal()
        m.guncelle(ALT, emniyet_acik=True)
        m.guncelle(UST, emniyet_acik=True)
        m.kalkisi_tuket()
        for _ in range(50):
            m.guncelle(UST, emniyet_acik=True)
            self.assertFalse(m.kalkisi_tuket())

    def test_emniyet_KAPALIYKEN_kalkis_URETILMEZ(self):
        m = SwdMandal()
        m.guncelle(ALT, emniyet_acik=False)
        m.guncelle(UST, emniyet_acik=False)
        self.assertFalse(m.kalkisi_tuket())

    def test_emniyet_kapali_gecis_SAHTE_KENAR_biriktirmez(self):
        """Kapaliyken yapilan gecis, acildiginda patlamamali."""
        m = SwdMandal()
        m.guncelle(ALT, emniyet_acik=False)
        m.guncelle(UST, emniyet_acik=False)   # kenar yutuldu
        m.guncelle(UST, emniyet_acik=True)    # emniyet acildi, deger ayni
        self.assertFalse(m.kalkisi_tuket())


class TestInisMandali(unittest.TestCase):
    """🔴 Inis MANDAL — tek tick'lik kenar mesh kapisinda kaybolurdu."""

    def test_inis_kenarda_kurulur(self):
        m = SwdMandal()
        m.guncelle(UST, emniyet_acik=True)
        m.guncelle(ALT, emniyet_acik=True)
        self.assertTrue(m.inis_mandali)

    def test_inis_SALTER_ALTTA_KALDIKCA_basili_kalir(self):
        """200 ms'lik mesh joystick kapisi tek tick'lik bayragi yutardi."""
        m = SwdMandal()
        m.guncelle(UST, emniyet_acik=True)
        m.guncelle(ALT, emniyet_acik=True)
        for _ in range(200):
            m.guncelle(ALT, emniyet_acik=True)
            self.assertTrue(m.inis_mandali)

    def test_inis_EMNIYET_KAPALIYKEN_DE_uretilir(self):
        """G2-K7: "SwA kapat -> HOLD" ve "SwD -> inis" BAGIMSIZ."""
        m = SwdMandal()
        m.guncelle(UST, emniyet_acik=False)
        m.guncelle(ALT, emniyet_acik=False)
        self.assertTrue(m.inis_mandali)

    def test_pilot_ONCE_SwA_kapatip_SONRA_SwD_ile_inebilir(self):
        """Iki kademeli iptalin gercek sirasi."""
        m = SwdMandal()
        m.guncelle(UST, emniyet_acik=True)    # ucus
        m.guncelle(UST, emniyet_acik=False)   # SwA kapatildi -> HOLD
        m.guncelle(ALT, emniyet_acik=False)   # SwD inise alindi
        self.assertTrue(m.inis_mandali)

    def test_mandali_dusuren_TEK_sey_salteri_yukari_almak(self):
        m = SwdMandal()
        m.guncelle(UST, emniyet_acik=True)
        m.guncelle(ALT, emniyet_acik=True)
        self.assertTrue(m.inis_mandali)
        m.guncelle(UST, emniyet_acik=True)
        self.assertFalse(m.inis_mandali)

    def test_kalkis_mandali_dusurur_ve_yeni_kalkis_verir(self):
        m = SwdMandal()
        m.guncelle(UST, emniyet_acik=True)
        m.guncelle(ALT, emniyet_acik=True)
        m.guncelle(UST, emniyet_acik=True)
        self.assertFalse(m.inis_mandali)
        self.assertTrue(m.kalkisi_tuket())


class TestOluBolge(unittest.TestCase):
    """Esikler arasi (-300..300) hicbir kenar uretmez."""

    def test_orta_bolgede_kenar_yok(self):
        m = SwdMandal()
        m.guncelle(ALT, emniyet_acik=True)
        for v in (-299, -100, 0, 100, 299):
            m.guncelle(v, emniyet_acik=True)
            self.assertFalse(m.kalkisi_tuket())
        self.assertFalse(m.inis_mandali)

    def test_ortadan_uste_gecis_kalkis_verir(self):
        m = SwdMandal()
        m.guncelle(0, emniyet_acik=True)
        m.guncelle(301, emniyet_acik=True)
        self.assertTrue(m.kalkisi_tuket())

    def test_ortadan_alta_gecis_inis_verir(self):
        m = SwdMandal()
        m.guncelle(0, emniyet_acik=True)
        m.guncelle(-301, emniyet_acik=True)
        self.assertTrue(m.inis_mandali)


class TestOzelEsikler(unittest.TestCase):
    """Node kendi sabitlerini gecirir — tek kaynak orada kalsin."""

    def test_esikler_disaridan_verilebilir(self):
        m = SwdMandal(takeoff_esik=500, land_esik=-500)
        m.guncelle(0, emniyet_acik=True)
        m.guncelle(400, emniyet_acik=True)
        self.assertFalse(m.kalkisi_tuket())
        m.guncelle(600, emniyet_acik=True)
        self.assertTrue(m.kalkisi_tuket())


if __name__ == '__main__':
    unittest.main()
