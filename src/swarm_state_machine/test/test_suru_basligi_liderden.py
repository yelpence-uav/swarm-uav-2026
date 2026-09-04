# Copyright 2026 Yelpence
"""SURU BASLIGI LIDERDEN GELIR — 5 Eylul 2026, sahada olculdu.

BELIRTI (operator): "cizgi formasyonunda dizip takeoff verince ucaklar
hafif SOLA donuyor, o sekilde beklemeye geciyor."

KOK NEDEN: `konumdan_tohumla()` suru basligini ucaklarin yaw'larinin
DAIRESEL ORTALAMASI olarak kuruyordu. Ortalama, aradaki fiziksel
hizasizligi ikiye bolup ucaklara PAYLASTIRIR: biri sola, digeri saga
doner. Formasyon secilmemisken konum donduruldugu icin
(_donmus_ofsetler) ucaklar yerinden kaymadan yalnizca DONUYOR — belirti
tam olarak buydu.

SAHA OLCUMU (ylp00 + ylp01, yerde, hizalandiktan SONRA):
    ylp00 yaw = 331.20 deg
    ylp01 yaw = 318.80 deg
    dairesel ortalama = 325.00 deg   tutarlilik = 0.9942
    -> ylp00 ortalamaya donmek icin -6.20 deg (SOL)
    -> ylp01 ortalamaya donmek icin +6.20 deg (SAG)

DUZELTME: baslik LIDERIN pusulasi. Lider hic donmez (operator zaten onu
referans alip diziyor; lider ayni zamanda slot 0 = ortadaki ucak,
KARAR-17), yalniz takipciler ona hizalanir.

YAN KAZANC: ortalama her ucakta YEREL olarak, zaman kaymali durum anlik
goruntulerinden hesaplaniyordu; ucaklar birbirinden biraz FARKLI ortalama
bulup farkli slot rotasyonu uygulayabiliyordu. Tek kaynak bunu kapatir.
"""

import unittest

from swarm_state_machine.mode_manager.mode_context import ModeContext

# Sahada olculen gercek degerler.
YLP00_YAW = 331.20
YLP01_YAW = 318.80
ORTALAMA = 325.00


class _SahteDurum:
    """AgentStatus yerine YEREL sahte — conftest gercegini MagicMock'luyor.

    🔴 GERCEK AgentStatus BU TESTLERDE KULLANILAMAZ: conftest.py
    `swarm_interfaces.msg`'i MagicMock'la degistiriyor ve MagicMock'un
    cagrisi HER SEFERINDE AYNI return_value'yu doner. Yani AgentStatus()
    ile kurulan iki "farkli" ucak TEK NESNE olur, ikinci atama birinciyi
    ezer ve test sessizce YANLIS SEYI olcer (TUZAKLAR §1: olcum aracinin
    kendisi yalan soyluyor). Depodaki diger testler de bu yuzden
    _MockAgentStatus kullaniyor.
    """

    def __init__(self, yaw, x=0.0, y=0.0, z=0.0):
        self.heading_deg = yaw
        self.pos_x, self.pos_y, self.pos_z = x, y, z
        self.state = 5
        self.healthy = True
        self.armed = True


def _st(yaw, x=0.0, y=0.0, z=0.0):
    return _SahteDurum(yaw, x, y, z)


def _ctx(lider_id, yawlar):
    c = ModeContext(agent_ids=sorted(yawlar), lider_id=lider_id)
    for aid, yaw in yawlar.items():
        c.agent_statuses[aid] = _st(yaw)
    return c


class TestBaslikLiderden(unittest.TestCase):

    def test_SAHA_OLCUMU_lider_DONMEZ(self):
        """🔴 Belirtinin kendisi: lider artik ortalamaya cekilmiyor."""
        c = _ctx(1, {1: YLP00_YAW, 2: YLP01_YAW})
        self.assertTrue(c.konumdan_tohumla())
        self.assertAlmostEqual(c.formation_heading_deg, YLP00_YAW, places=4)
        # Eski davranis 325.00 verirdi; lider 6.20 deg SOLA donerdi.
        self.assertNotAlmostEqual(c.formation_heading_deg, ORTALAMA, places=1)

    def test_takipci_LIDERE_hizalanir(self):
        """Donme yuku tek uçakta: takipci 12.40 deg doner, lider 0."""
        c = _ctx(1, {1: YLP00_YAW, 2: YLP01_YAW})
        c.konumdan_tohumla()
        lider_donus = ((c.formation_heading_deg - YLP00_YAW + 180) % 360) - 180
        takipci_donus = ((c.formation_heading_deg - YLP01_YAW + 180) % 360) - 180
        self.assertAlmostEqual(lider_donus, 0.0, places=4)
        self.assertAlmostEqual(takipci_donus, 12.40, places=2)

    def test_lider_ylp01_olsaydi_o_da_DONMEZDI(self):
        """Kural lidere baglidir, kimlige gomulu degil."""
        c = _ctx(2, {1: YLP00_YAW, 2: YLP01_YAW})
        c.konumdan_tohumla()
        self.assertAlmostEqual(c.formation_heading_deg, YLP01_YAW, places=4)

    def test_TUTARLILIK_hala_TUM_filodan_olculur(self):
        """Baslik liderden gelse de hizasizlik olcusu korunmali.

        Kuru test ve operator uyarisi bu sayiya bakiyor (<0.90 uyarir);
        lidere baglansaydi her zaman 1.0 cikar ve uyari OLURDU.
        """
        c = _ctx(1, {1: YLP00_YAW, 2: YLP01_YAW})
        c.konumdan_tohumla()
        self.assertAlmostEqual(c.kalkis_heading_tutarlilik, 0.9942, places=3)

    def test_HIZASIZ_filoda_tutarlilik_DUSER(self):
        """90 derece ayrik iki ucak: tutarlilik belirgin sekilde duser."""
        c = _ctx(1, {1: 0.0, 2: 90.0})
        c.konumdan_tohumla()
        self.assertLess(c.kalkis_heading_tutarlilik, 0.75)
        self.assertAlmostEqual(c.formation_heading_deg, 0.0, places=4)


class TestGeriDusus(unittest.TestCase):
    """Hicbir kosulda basliksiz kalinmaz."""

    def test_lider_BILINMIYORSA_ortalamaya_dusulur(self):
        c = _ctx(0, {1: YLP00_YAW, 2: YLP01_YAW})
        c.konumdan_tohumla()
        self.assertAlmostEqual(c.formation_heading_deg, ORTALAMA, places=2)

    def test_liderin_DURUMU_YOKSA_ortalamaya_dusulur(self):
        """lider_id kadroda ama status hic gelmemis."""
        c = ModeContext(agent_ids=[1, 2], lider_id=1)
        c.agent_statuses[2] = _st(YLP01_YAW)
        # all_agents_seen False -> tohumlama yapilmaz
        self.assertFalse(c.konumdan_tohumla())

    def test_kadro_DISI_lider_ortalamaya_duser(self):
        """lider_id kadroda yoksa (yanlis parametre) sessiz kalinmaz."""
        c = _ctx(9, {1: YLP00_YAW, 2: YLP01_YAW})
        c.konumdan_tohumla()
        self.assertAlmostEqual(c.formation_heading_deg, ORTALAMA, places=2)

    def test_360_SARMASI_ortalama_yolunda_korunur(self):
        """359/1 okuyan filoda ortalama guneyi gostermemeli."""
        c = _ctx(0, {1: 359.0, 2: 1.0})
        c.konumdan_tohumla()
        self.assertLess(abs(((c.formation_heading_deg + 180) % 360) - 180), 1.0)


if __name__ == '__main__':
    unittest.main()
