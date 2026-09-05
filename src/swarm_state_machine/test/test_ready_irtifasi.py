# Copyright 2026 Yelpence
"""READY IRTIFASI: %80 bir GECIS olcutu, SON IRTIFA degil — 5 Eylul 2026.

BELIRTI (operator): "10 m istedim, konuma yerlestikten sonra istenen
degerin ALTINA dustu."

OLCULEN (ylp00 + ylp01 bag, 5 Eylul ucusu):
  kalkis_irtifa_m = 10.0 DOGRU uygulandi (log: GOREV 2 AYARI UYGULANDI)
  READY seed centroid z = -8.2  (yer -1.72 -> 9.9 m AGL, dogru)
  ama ucaklar 8.50 m AGL'de OTURDU ve inise kadar orada kaldi
    ylp00 pos_z -6.77 · ylp01 pos_z -6.78 · yer -1.72
  gaz cubugu ucus boyunca TAM SIFIR -> operator girdisi DEGIL

KOK NEDEN — iki dogru kararin catismasi:
  _KALKIS_ULASMA_ORANI = 0.8 : READY hedefin %80'inde tetiklenir.
      Gerekcesi saglam — PX4 hedefe asimptotik yaklasir, son 20 cm
      dakikalar surer, tam irtifa beklemek yanlis olurdu.
  READY girisi centroid'i O ANKI konumdan tazeler.
      Gerekcesi de saglam — kapi 2 m'de tohumluyor, tazelenmezse suru
      kontrol devralinir alinmaz 2 m'ye GERI DALAR.

Ikisi birlesince %80 yalnizca bir GECIS olcutu olmaktan cikip FIILI SON
IRTIFA oluyor: kalan %20 hic tirmanilmiyor cunku formasyon z hedefini
oraya donduruyor. Hicbir yerde hata yok — istenen 10, ucan 8.5.

DUZELTME: READY'de x/y OLCULENDEN kalir (tirmanista yanal suruklenme
gercek ve bayat merkez sicrama komutu uretir), z ise KOMUT EDILENDEN
gelir (hedefi zaten biliyoruz).
"""

import unittest

from swarm_state_machine.mode_manager.mode_context import ModeContext

YER_Z = 1.72          # ucaklar origin'in 1.72 m ALTINDA duruyordu
HEDEF_M = 10.0


class _SahteDurum:
    """AgentStatus yerine yerel sahte (conftest gercegini MagicMock'luyor)."""

    def __init__(self, x, y, z, yaw=326.8):
        self.pos_x, self.pos_y, self.pos_z = x, y, z
        self.heading_deg = yaw
        self.state = 5
        self.healthy = True
        self.armed = True


def _ctx(lider_z):
    """READY anindaki hal: %80'e ulasilmis, hedefe 1.5 m var."""
    c = ModeContext(agent_ids=[1, 2], lider_id=1)
    c.kalkis_irtifa_m = HEDEF_M
    c.kalkis_zemin_z = {1: YER_Z, 2: YER_Z}
    c.agent_statuses[1] = _SahteDurum(7.2, 0.2, lider_z)
    c.agent_statuses[2] = _SahteDurum(7.2, 6.2, lider_z)
    return c


class TestGecisOlcutu(unittest.TestCase):
    """%80 esigi READY'yi tetikler ama son irtifa OLMAMALI."""

    def test_yuzde_80_de_READY_tetiklenir(self):
        """Esik korunuyor — bekleme gerekcesi hala gecerli."""
        c = _ctx(lider_z=YER_Z - 8.0)          # tam 8.0 m AGL
        c.kalkis_komutu_verildi = True
        self.assertTrue(c.kalkis_irtifasina_ulasildi())

    def test_yuzde_80_ALTINDA_READY_YOK(self):
        c = _ctx(lider_z=YER_Z - 7.5)
        c.kalkis_komutu_verildi = True
        self.assertFalse(c.kalkis_irtifasina_ulasildi())


class TestKomutEdilenIrtifa(unittest.TestCase):
    """Duzeltmenin dayandigi aritmetik: hedef z = zemin - istenen irtifa."""

    def test_hedef_z_dogru_hesaplanir(self):
        c = _ctx(lider_z=YER_Z - 8.5)          # sahada olculen hal
        zeminler = list(c.kalkis_zemin_z.values())
        zemin = sum(zeminler) / len(zeminler)
        hedef_z = zemin - c.kalkis_irtifa_m
        self.assertAlmostEqual(zemin - hedef_z, HEDEF_M, places=6)
        # AGL karsiligi tam 10 m olmali
        self.assertAlmostEqual(-hedef_z + zemin, HEDEF_M, places=6)

    def test_SAHADA_OLCULEN_fark(self):
        """8.50 m'de oturmustu; komut edilen 10.0 -> 1.50 m kayip."""
        c = _ctx(lider_z=YER_Z - 8.5)
        c.konumdan_tohumla()
        olculen_agl = YER_Z - c.centroid_z
        self.assertAlmostEqual(olculen_agl, 8.5, places=6)
        self.assertAlmostEqual(HEDEF_M - olculen_agl, 1.5, places=6)

    def test_merkez_LIDERDEN_geldigi_icin_z_de_liderin(self):
        """Merkez = lider konumu (KARAR-17 uzantisi); z de oradan gelir."""
        c = _ctx(lider_z=YER_Z - 8.5)
        c.agent_statuses[2].pos_z = YER_Z - 12.0     # takipci cok yukarida
        c.konumdan_tohumla()
        self.assertAlmostEqual(c.centroid_z, YER_Z - 8.5, places=6)


class TestGeriDusus(unittest.TestCase):
    """Zemin referansi yoksa eski davranisa dusulur — sessiz yanlis yok."""

    def test_zemin_YOKSA_olculen_kalir(self):
        c = _ctx(lider_z=YER_Z - 8.5)
        c.kalkis_zemin_z = {}
        c.konumdan_tohumla()
        # duzeltme kosulu (zeminler bos) saglanmaz -> olculen z kalir
        self.assertAlmostEqual(c.centroid_z, YER_Z - 8.5, places=6)

    def test_B19_zemin_referansini_siler(self):
        """Ikinci kalkista onceki ucusun zemini tasinmamali."""
        c = _ctx(lider_z=YER_Z - 8.5)
        c.ucus_durumunu_sifirla()
        self.assertEqual(c.kalkis_zemin_z, {})


class TestYerMandaliTuketimi(unittest.TestCase):
    """Mandal KALKISA ait; READY'den sonra yaw donusleri KORUNMALI.

    🔴 5 Eylul'de dagitilmis kodla OLCULDU ve regresyondu:
      yer 330 deg -> MOVEMENT'ta yaw ile 60 deg dondur -> 30 deg
      -> MANEUVER girisi konumdan_tohumla() cagiriyor -> baslik 330'a
      GERI SICRIYOR. Formasyon 60 derece geri doner; ustelik olculen
      ofsetler yanlis baslikla govde cercevesine cevrildigi icin
      "dizilim korunur, ucak kimildamaz" garantisi de bozulur.
    Sartname G3: yaw = merkez sabit formasyon rotasyonu — o donus
    korunmak zorunda.
    """

    def test_mandal_ACIKKEN_baslik_yere_cekilir(self):
        """Kalkis davranisi: tirmanis salinimi yansimasin."""
        c = _ctx(lider_z=YER_Z - 8.5)
        c.yer_basligini_mandalla()
        c.agent_statuses[1].heading_deg = 30.0      # tirmanista savruldu
        c.konumdan_tohumla()
        self.assertAlmostEqual(c.formation_heading_deg, 326.8, places=1)

    def test_mandal_TUKETILINCE_guncel_baslik_kullanilir(self):
        """READY sonrasi: yaw ile yapilan donus KORUNUR."""
        c = _ctx(lider_z=YER_Z - 8.5)
        c.yer_basligini_mandalla()
        c.yer_heading_var = False                   # READY tuketti
        c.agent_statuses[1].heading_deg = 30.0      # yaw ile dondu
        c.konumdan_tohumla()
        self.assertAlmostEqual(c.formation_heading_deg, 30.0, places=1)

    def test_B19_mandali_YENIDEN_kurulabilir_hale_getirir(self):
        c = _ctx(lider_z=YER_Z - 8.5)
        c.yer_basligini_mandalla()
        c.yer_heading_var = False
        c.ucus_durumunu_sifirla()
        self.assertFalse(c.yer_heading_var)
        self.assertTrue(c.yer_basligini_mandalla())


if __name__ == '__main__':
    unittest.main()
