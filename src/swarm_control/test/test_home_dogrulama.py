"""HOME dogrulamasi — 26 Agustos 2026 saha olayindan dogdu.

RTL uc ucagi da kalkis noktalarina degil UCUNU BIRDEN ayni yanlis noktaya
indirdi (kalkislarin ~9 m KD'si, birbirlerine 1-2 m); PX4 home kayitlari
tam o inis noktalariydi. Yani RTL dogru uctu, HOME'LAR YANLISTI.

Bu testlerin kilitledigi dort davranis:
  1. Home dogruyken "bozuk" DEMEZ  (yanlis alarm ucusu durdurur)
  2. Home yanlisken YAKALAR         (asil is)
  3. Olculemeyen durumda HUKUM VERMEZ (gecerli=False, home_ok=None)
  4. 🔴 CERCEVE FARKI TEK BASINA HUKUM VERMEZ — 2 Eylul regresyonu

Referans sayilar UCAKTA olculdu, uydurma degil:
  1 Eylul, ylp00, yerde, RTK yok : home <-> GPS 0.062 m, cerceve 0.02 m
  2 Eylul, ylp00, acilis sonrasi : HomePosition.position (0,0,0),
                                   ucak yerel (16.12, 10.54) = 19.26 m
"""

import unittest

from swarm_control.px4_interface.home_dogrulama import (
    geodezik_ned,
    home_denetle,
    TOL_YATAY_HAM_M,
    TOL_YATAY_RTK_M,
    yatay_tolerans,
)


# --- 1 Eylul 2026, ylp00, yerde olculen gercek degerler --------------------
ORIGIN = {'origin_lat': 38.6904758, 'origin_lon': 39.1610188,
          'origin_alt_amsl': 1216.96}            # deploy/saha_origin.env
HOME = {'home_lat': 38.6906287, 'home_lon': 39.1611271,
        'home_alt_amsl': 1217.9112329676875}     # PX4 home_position/home
GPS = {'gps_lat': 38.6906291, 'gps_lon': 39.1611266,
       'gps_alt_amsl': 1217.2072347233736}       # anlik global_position
YEREL = {'home_yerel_dogu': 9.406322479248047,
         'home_yerel_kuzey': 17.0025634765625,
         'home_yerel_yukari': 0.952880859375}


def _saglikli(**degisiklik):
    """1 Eylul olcumunun tamami; test istedigi alani ezer."""
    arg = {'home_set': True, 'gps_fix_type': 3, 'yerde': True,
           **ORIGIN, **HOME, **GPS, **YEREL}
    arg.update(degisiklik)
    return arg


class TestGercekOlcum(unittest.TestCase):
    """Sahada olculen gercek durum GECMELI."""

    def test_saha_olcumu_gecer(self):
        s = home_denetle(**_saglikli())
        self.assertTrue(s.gecerli)
        self.assertTrue(s.home_ok, s.sebep)

    def test_olculen_sapmalar_beklenen_mertebede(self):
        s = home_denetle(**_saglikli())
        self.assertLess(s.yatay_m, 0.20)     # olculen 0.062
        self.assertGreater(s.dikey_m, 0.5)   # olculen 0.704
        self.assertLess(s.dikey_m, 1.0)


class TestCerceveFarkiHukumVERMEZ(unittest.TestCase):
    """🔴 2 EYLUL 2026 REGRESYONU — bu testler o hatanin geri gelmesini onler.

    Ilk surumde cerceve farki (home'un global temsili ile PX4'un yerel
    temsili arasindaki fark) HUKUM veriyordu. Ucakta olculdu ve YANLIS
    cikti: PX4 home'u origin push'undan ONCE yaziyor, yerel kaydi
    (0,0,0) kaliyor ve origin uygulaninca cerceve 19 m kayiyor — ama
    home'un GLOBAL kaydi DOGRU kaliyor (ucagin GPS'ine 0.67 m).

    Sonuc: her acilista KRITIK alarm + duzeltemeyecegi bir seyi 30 sn'de
    bir tekrarlayan otomatik duzeltme. RTL'in kullandigi sey home'un
    GLOBAL kaydidir; hukmu veren de o olmali.
    """

    def test_cerceve_19m_ama_home_yerinde_ISE_GECER(self):
        # 2 Eylul'un birebir kurgusu: yerel (0,0,0), global dogru.
        s = home_denetle(**_saglikli(
            home_yerel_dogu=0.0, home_yerel_kuzey=0.0,
            home_yerel_yukari=0.0))
        self.assertTrue(s.gecerli)
        self.assertTrue(s.home_ok, s.sebep)
        # Fark yine de OLCULUYOR ve raporlaniyor — bilgi degerli.
        self.assertGreater(s.cerceve_m, 19.0)
        self.assertLess(s.cerceve_m, 20.0)

    def test_cerceve_olculemezse_hukum_yine_verilir(self):
        # Origin bilinmiyorsa cerceve hesaplanamaz; yer denetimi yeter.
        s = home_denetle(**_saglikli(origin_lat=None, origin_lon=None))
        self.assertTrue(s.gecerli)
        self.assertTrue(s.home_ok)
        self.assertIsNone(s.cerceve_m)


class TestKaymayiYakalar(unittest.TestCase):
    """26 Agustos'un hatasi YAKALANMALI."""

    def test_dokuz_metre_kayma_yakalanir(self):
        # 26 Agustos'ta olculen buyukluk: ~9 m. fix 3'te tolerans 3.0 m.
        s = home_denetle(**_saglikli(
            home_lat=HOME['home_lat'] + 9.0 / 111320.0))
        self.assertTrue(s.gecerli)
        self.assertFalse(s.home_ok)
        self.assertGreater(s.yatay_m, 8.0)

    def test_home_ortak_origine_dusmus(self):
        # "Ucu birden ayni noktaya indi"nin en guclu adayi.
        s = home_denetle(**_saglikli(
            home_lat=ORIGIN['origin_lat'], home_lon=ORIGIN['origin_lon']))
        self.assertFalse(s.home_ok)
        self.assertGreater(s.yatay_m, 19.0)

    def test_dikey_kayma_yakalanir(self):
        s = home_denetle(**_saglikli(
            home_alt_amsl=GPS['gps_alt_amsl'] + 5.0))
        self.assertFalse(s.home_ok)


class TestFixeBagliTolerans(unittest.TestCase):
    """Esik fix kalitesine bagli — RTK'siz gezinme olculdu (1.27 m)."""

    def test_secim(self):
        self.assertEqual(yatay_tolerans(3), TOL_YATAY_HAM_M)
        self.assertEqual(yatay_tolerans(4), TOL_YATAY_HAM_M)
        self.assertEqual(yatay_tolerans(5), TOL_YATAY_RTK_M)
        self.assertEqual(yatay_tolerans(6), TOL_YATAY_RTK_M)

    def test_1_5m_RTKSIZ_gecer_RTKli_kalir(self):
        # 2 Eylul'de RTK'siz 1.17-1.27 m olculdu; bu gezinme YANLIS ALARM
        # uretmemeli. RTK varsa ayni sapma GERCEK bir sorundur.
        arg = _saglikli(home_lat=HOME['home_lat'] + 1.5 / 111320.0)
        self.assertTrue(home_denetle(**{**arg, 'gps_fix_type': 3}).home_ok)
        self.assertFalse(home_denetle(**{**arg, 'gps_fix_type': 6}).home_ok)


class TestHukumVermez(unittest.TestCase):
    """Olculemeyen durumda SAYI URETME — jole_olc.py'nin dersi."""

    def test_home_yazilmadi(self):
        s = home_denetle(**_saglikli(home_set=False))
        self.assertFalse(s.gecerli)
        self.assertIsNone(s.home_ok)

    def test_havada_hukum_yok(self):
        # Ucak home'dan uzaklasir; "home yerinde mi" havada anlamsiz.
        s = home_denetle(**_saglikli(
            yerde=False, gps_lat=HOME['home_lat'] + 200.0 / 111320.0))
        self.assertFalse(s.gecerli)
        self.assertIsNone(s.home_ok)

    def test_gps_fix_yok(self):
        s = home_denetle(**_saglikli(gps_fix_type=0))
        self.assertFalse(s.gecerli)
        self.assertIsNone(s.home_ok)

    def test_sifir_lat_gecersiz_sayilir(self):
        # MAVROS baglanmadan once lat/lon 0.0 gelir; 0,0 Gine Korfezi'dir.
        s = home_denetle(**_saglikli(gps_lat=0.0, gps_lon=0.0))
        self.assertFalse(s.gecerli)

    def test_gecerli_sonucta_yatay_HER_ZAMAN_dolu(self):
        # 🔴 px4_bridge log satiri bu alani bicimliyor; None gelirse
        # TypeError atar ve TIMER geri cagrisi oldugu icin dugumu dusurur.
        for arg in (_saglikli(), _saglikli(origin_lat=None, origin_lon=None),
                    _saglikli(home_yerel_dogu=0.0, home_yerel_kuzey=0.0)):
            s = home_denetle(**arg)
            if s.gecerli:
                self.assertIsNotNone(s.yatay_m)
                self.assertIsNotNone(s.dikey_m)


class TestGeodezik(unittest.TestCase):
    """Geodezik yardimci — px4_bridge._origin_dogrula ile ayni yaklasim."""

    def test_kuzey_dogu_isaretleri(self):
        kuzey, dogu = geodezik_ned(38.70, 39.17, 38.69, 39.16)
        self.assertGreater(kuzey, 0.0)
        self.assertGreater(dogu, 0.0)

    def test_ayni_nokta_sifir(self):
        kuzey, dogu = geodezik_ned(38.69, 39.16, 38.69, 39.16)
        self.assertAlmostEqual(kuzey, 0.0)
        self.assertAlmostEqual(dogu, 0.0)

    def test_home_origin_ofseti_PX4_yereliyle_ortusur(self):
        # 1 Eylul olcumu: iki bagimsiz yoldan ayni sayi cikmisti.
        kuzey, dogu = geodezik_ned(
            HOME['home_lat'], HOME['home_lon'],
            ORIGIN['origin_lat'], ORIGIN['origin_lon'])
        self.assertAlmostEqual(dogu, YEREL['home_yerel_dogu'], delta=0.05)
        self.assertAlmostEqual(kuzey, YEREL['home_yerel_kuzey'], delta=0.05)


if __name__ == '__main__':
    unittest.main()
