# Copyright 2026 Yelpence
"""LIDER MERKEZ + YER BASLIGI + EN YAKIN SLOT — 5 Eylul 2026.

Ucu de ayni saha gozleminden cikti: "cizgi halinde dizip takeoff verince
ucaklar hafif sola donuyor" ve devaminda "cizgi halinde kalksin".

Kullanilan gercek olcumler (5 Eylul, ylp00 + ylp01, yerde):
    ylp00 konum (8.79, 4.32)   yaw 331.16 (12 sn boyunca +-0.03)
    ylp01 konum (3.95, -3.79)  yaw 323.57 (12 sn boyunca +-0.05)
    fiziksel ayrim 9.44 m
Bag izinden (tirmanis): ylp00 yaw 331.2 -> 335.9 -> 303.8 -> kapida 314.2.
Yani kapi anindaki olcum yerdekinden 17.4 derece SOLDA.
"""

import unittest

from swarm_core.formation_control.formation_geometry import (
    compute_slot_offsets,
    FORMATION_CIZGI,
)

from swarm_state_machine.mode_manager import slot_atama
from swarm_state_machine.mode_manager.mode_context import ModeContext

YLP00 = (8.79, 4.32)
YLP01 = (3.95, -3.79)
YER_YAW_00 = 331.16
YER_YAW_01 = 323.57
KAPI_YAW = 314.23      # tirmanis salinimi sirasinda olculen
ALFA = 0.7853981633974483


class _SahteDurum:
    """AgentStatus yerine yerel sahte durum nesnesi.

    conftest gercegini MagicMock'luyor ve MagicMock her cagrida AYNI
    nesneyi donduruyor; iki ucak tek nesneye cakisirdi (TUZAKLAR §1).
    """

    def __init__(self, x, y, yaw, z=-1.3):
        self.pos_x, self.pos_y, self.pos_z = x, y, z
        self.heading_deg = yaw
        self.state = 5
        self.healthy = True
        self.armed = True


def _ctx(lider=1):
    c = ModeContext(agent_ids=[1, 2], lider_id=lider)
    c.agent_statuses[1] = _SahteDurum(*YLP00, YER_YAW_00)
    c.agent_statuses[2] = _SahteDurum(*YLP01, YER_YAW_01)
    return c


class TestMerkezLider(unittest.TestCase):
    """Merkez = liderin konumu; lider kimildamaz."""

    def test_merkez_LIDERIN_konumu(self):
        c = _ctx()
        self.assertTrue(c.konumdan_tohumla())
        self.assertAlmostEqual(c.centroid_x, YLP00[0], places=4)
        self.assertAlmostEqual(c.centroid_y, YLP00[1], places=4)

    def test_ORTALAMA_DEGIL(self):
        """Eski davranis orta noktayi verirdi; lider oraya UCARDI (4.72 m)."""
        c = _ctx()
        c.konumdan_tohumla()
        orta_x = (YLP00[0] + YLP01[0]) / 2
        self.assertNotAlmostEqual(c.centroid_x, orta_x, places=2)

    def test_lider_YOKSA_ortalamaya_dusulur(self):
        c = _ctx(lider=0)
        c.konumdan_tohumla()
        self.assertAlmostEqual(c.centroid_x, (YLP00[0] + YLP01[0]) / 2, 4)


class TestYerBasligi(unittest.TestCase):
    """Baslik kalkis kapisinda DEGIL, yerdeyken mandallanir."""

    def test_mandal_liderin_YER_yaw_ini_alir(self):
        c = _ctx()
        self.assertTrue(c.yer_basligini_mandalla())
        self.assertAlmostEqual(c.yer_heading_deg, YER_YAW_00, places=4)

    def test_mandal_varsa_TIRMANIS_SALINIMI_yansimaz(self):
        """🔴 Belirtinin kendisi: kapida 314.2 okunsa da 331.16 kalir."""
        c = _ctx()
        c.yer_basligini_mandalla()
        c.agent_statuses[1].heading_deg = KAPI_YAW      # tirmanista savruldu
        c.konumdan_tohumla()
        self.assertAlmostEqual(c.formation_heading_deg, YER_YAW_00, places=4)

    def test_mandal_YOKSA_eski_yol(self):
        c = _ctx()
        c.agent_statuses[1].heading_deg = KAPI_YAW
        c.konumdan_tohumla()
        self.assertAlmostEqual(c.formation_heading_deg, KAPI_YAW, places=4)

    def test_B19_sifirlamasi_mandali_TEMIZLER(self):
        """Ikinci kalkista ucak baska yone dizilmis olabilir."""
        c = _ctx()
        c.yer_basligini_mandalla()
        c.ucus_durumunu_sifirla()
        self.assertFalse(c.yer_heading_var)

    def test_eksik_ajan_varken_mandallamaz(self):
        c = ModeContext(agent_ids=[1, 2], lider_id=1)
        c.agent_statuses[1] = _SahteDurum(*YLP00, YER_YAW_00)
        self.assertFalse(c.yer_basligini_mandalla())


class TestEnYakinSlot(unittest.TestCase):
    """Lider slot 0'da sabit, kalanlar en yakin slota."""

    def _slotlar(self, n, aralik, merkez, heading):
        off = compute_slot_offsets(FORMATION_CIZGI, n, aralik, ALFA)
        return slot_atama.slot_dunya_konumlari(
            off, merkez[0], merkez[1], heading)

    def test_lider_HER_ZAMAN_slot0(self):
        xy = self._slotlar(2, 7.0, YLP00, YER_YAW_00)
        sira = slot_atama.slot_sirasi(1, [1, 2], {1: YLP00, 2: YLP01}, xy)
        self.assertEqual(sira[0], 1)

    def test_CAPRAZ_GECIS_engellenir(self):
        """🔴 Asil kazanc: takipci karsi tarafa GECMEZ.

        Uc ucakli cizgide slotlar merkez, +s ve -s. ylp01 fiziksel olarak
        -s tarafinda; kimlik sirasi onu +s'ye gonderirdi (lider uzerinden
        gecis). En yakin atama -s'yi verir.
        """
        u3 = {1: YLP00, 2: YLP01, 3: (13.6, 12.4)}
        xy = self._slotlar(3, 9.44, YLP00, YER_YAW_00)
        sira = slot_atama.slot_sirasi(1, [1, 2, 3], u3, xy)
        self.assertEqual(sira[0], 1)
        # her ucak kendine EN YAKIN slotu almis olmali
        import math
        toplam = sum(math.dist(u3[a], xy[i]) for i, a in enumerate(sira))
        kimlik = sum(math.dist(u3[a], xy[i]) for i, a in enumerate([1, 2, 3]))
        self.assertLessEqual(toplam, kimlik)

    def test_konum_EKSIKSE_kimlik_sirasina_dusulur(self):
        """Eksik veriyle 'en yakin' hesaplamak sessizce yanlis atar."""
        xy = self._slotlar(2, 7.0, YLP00, YER_YAW_00)
        sira = slot_atama.slot_sirasi(1, [1, 2], {1: YLP00}, xy)
        self.assertEqual(sira, [1, 2])

    def test_lider_kadroda_yoksa_hepsi_en_yakina(self):
        xy = self._slotlar(2, 7.0, YLP00, YER_YAW_00)
        sira = slot_atama.slot_sirasi(9, [1, 2], {1: YLP00, 2: YLP01}, xy)
        self.assertEqual(sorted(sira), [1, 2])


if __name__ == '__main__':
    unittest.main()
