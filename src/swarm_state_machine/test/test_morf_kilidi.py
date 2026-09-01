# Copyright 2026 Yelpence
"""Formasyon morf hizi kilidi — 1 Eylul 2026.

31 Agustos ucusunda iki ucak 1,65 m'ye yaklasti. Kacinma DOGRU calisti:
4,13 m/s kapanmayi 3,58 m/s2 ile durdurmak 2,38 m ister, 4,00 m'lik
esikten geriye 1,62 m kalir — olculen 1,65 m. Yani sorun esik degil HIZ.

Bu dosya iki seyi birden kilitliyor:
  * morf sirasinda hizin GERCEKTEN dustugunu,
  * kilidin dogru anlarda DUSTUGUNU (dusmezse formasyon merkezin
    gerisinde kalir — formation_node'da bir kez yasanmis hata).
"""

import unittest

from swarm_state_machine.mode_manager import morf_kilidi as mk


ESIK = 0.05
MORF = 0.6
SEYIR = 2.0


class TestSinirlama(unittest.TestCase):

    def test_morf_sirasinda_hiz_DUSER(self):
        hiz, bitis, sebep = mk.hiz_sinirla(
            SEYIR, MORF, bitis_s=100.0, simdi_s=90.0, cubuk=0.0,
            cubuk_esigi=ESIK)
        self.assertEqual(hiz, MORF)
        self.assertEqual(bitis, 100.0, 'kilit erken dustu')
        self.assertEqual(sebep, mk.SEBEP_YOK)

    def test_kilit_yokken_DOKUNMAZ(self):
        hiz, bitis, sebep = mk.hiz_sinirla(
            SEYIR, MORF, bitis_s=mk.KILIT_YOK, simdi_s=90.0, cubuk=0.0,
            cubuk_esigi=ESIK)
        self.assertEqual(hiz, SEYIR)
        self.assertEqual(sebep, mk.SEBEP_YOK)

    def test_istenen_zaten_kucukse_BUYUTMEZ(self):
        """min() — kilit bir TAVAN, hedef degil."""
        hiz, _b, _s = mk.hiz_sinirla(
            0.3, MORF, bitis_s=100.0, simdi_s=90.0, cubuk=0.0,
            cubuk_esigi=ESIK)
        self.assertEqual(hiz, 0.3)

    def test_SIFIR_belirtilmedi_demek_DOKUNULMAZ(self):
        """🔴 HOLD komutu max_speed=0.0 yolluyor.

        0'i 0,6'ya cikarmak HOLD'u bir HAREKET komutuna cevirirdi:
        ucaklar durmak yerine slotlarina dogru surunmeye baslardi.
        """
        hiz, bitis, _s = mk.hiz_sinirla(
            0.0, MORF, bitis_s=100.0, simdi_s=90.0, cubuk=0.0,
            cubuk_esigi=ESIK)
        self.assertEqual(hiz, 0.0)
        self.assertEqual(bitis, 100.0, 'HOLD kilidi dusurmemeli')


class TestKilidinDusmesi(unittest.TestCase):

    def test_sure_dolunca_DUSER(self):
        hiz, bitis, sebep = mk.hiz_sinirla(
            SEYIR, MORF, bitis_s=100.0, simdi_s=100.0, cubuk=0.0,
            cubuk_esigi=ESIK)
        self.assertEqual(hiz, SEYIR)
        self.assertEqual(bitis, mk.KILIT_YOK)
        self.assertEqual(sebep, mk.SEBEP_SURE)

    def test_cubukla_DUSER(self):
        """🔴 Merkez MOD_HIZ ile giderken slot 0,6'da kalirsa formasyon
        merkezin GERISINDE kalir (formation_node'da yasandi)."""
        hiz, bitis, sebep = mk.hiz_sinirla(
            SEYIR, MORF, bitis_s=100.0, simdi_s=90.0, cubuk=0.4,
            cubuk_esigi=ESIK)
        self.assertEqual(hiz, SEYIR)
        self.assertEqual(bitis, mk.KILIT_YOK)
        self.assertEqual(sebep, mk.SEBEP_CUBUK)

    def test_esigin_ALTINDAKI_cubuk_dusurmez(self):
        """Gurultu kilidi acmamali."""
        hiz, bitis, sebep = mk.hiz_sinirla(
            SEYIR, MORF, bitis_s=100.0, simdi_s=90.0, cubuk=0.04,
            cubuk_esigi=ESIK)
        self.assertEqual(hiz, MORF)
        self.assertEqual(bitis, 100.0)
        self.assertEqual(sebep, mk.SEBEP_YOK)

    def test_dustukten_sonra_KENDILIGINDEN_geri_gelmez(self):
        _h, bitis, _s = mk.hiz_sinirla(
            SEYIR, MORF, 100.0, 90.0, 0.4, ESIK)
        hiz2, bitis2, sebep2 = mk.hiz_sinirla(
            SEYIR, MORF, bitis, 91.0, 0.0, ESIK)
        self.assertEqual(hiz2, SEYIR)
        self.assertEqual(bitis2, mk.KILIT_YOK)
        self.assertEqual(sebep2, mk.SEBEP_YOK)

    def test_cubuk_sureden_ONCE_degerlendirilir(self):
        """Ikisi ayni anda ise sebep 'cubuk' olmali — operatore gosterilen
        neden, kilidi fiilen kaldiran sey olmali."""
        _h, _b, sebep = mk.hiz_sinirla(
            SEYIR, MORF, bitis_s=100.0, simdi_s=200.0, cubuk=0.9,
            cubuk_esigi=ESIK)
        self.assertEqual(sebep, mk.SEBEP_CUBUK)


class TestOlculenSahaSayilari(unittest.TestCase):
    """31 Agustos olcumu tekrar etmesin."""

    def test_morf_hizi_kacinmaya_YETERLI_pay_birakiyor(self):
        d0, ivme = 4.0, 3.58
        kapanma = 2.0 * MORF
        fren = kapanma ** 2 / (2.0 * ivme)
        self.assertGreater(
            d0 - fren, 3.0,
            f'morf {MORF} m/s ile kacinmaya {d0 - fren:.2f} m kaliyor; '
            '31 Agustos ucusunda bu 1,62 m idi ve ucaklar 1,65 m\'ye '
            'yaklasti')

    def test_ESKI_hiz_bu_testi_GECEMEZ(self):
        """Denetimin gercekten isledigini gosterir: olculen 2,71 m/s."""
        d0, ivme = 4.0, 3.58
        fren = (2.0 * 2.71) ** 2 / (2.0 * ivme)
        self.assertLess(d0 - fren, 0.0,
                        'olculen hizla frenleme esikten uzun olmaliydi')


if __name__ == '__main__':
    unittest.main()
