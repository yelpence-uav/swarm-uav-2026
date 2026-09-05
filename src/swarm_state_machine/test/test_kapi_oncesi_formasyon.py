# Copyright 2026 Yelpence
"""KAPI ONCESI VERILEN FORMASYON KAYBOLUYORDU — 5 Eylul 2026, sahada.

BELIRTI (operator): "cizgi formasyonunda yere dizdim, araligi arayuzden
6 verdim. Kalktilar ve KALKTIKLARI YERDE BEKLEDILER. Aralarinda 11 m
vardi ama 6 m'ye dusurmediler."

OLCULEN ZINCIR (ylp00 mode_manager.log):
  1788571789  GOREV 2 AYARI UYGULANDI: aralik=6.0 m      <- ayar geldi
  1788571826  Formasyon degisikligi: 2, spacing: 6.0m    <- ILK komut V
  1788571898  Formasyon degisikligi: 1, spacing: 6.0m
  Kayitta CIZGI (tip 3) komutu HIC YOK.

KOK NEDEN: VrB acik + SwC cizgide iken formasyon_kilidi YENI_ACILDI
doner ve formation_change_requested uretilir. _handle_formation_change
`ctx.active_formation = 3` YAZAR, ama _publish_formation_command
`if not kalkis_tamam: return` ile tarifi DUSURUR (B15 kalkis kapisi).
Istek bir KENAR oldugu icin ayni tick'te temizlenir. Kapi sonradan
acildiginda kimse tarifi yeniden istemiyordu -> suru FORMATION_UNKNOWN'da
kalir ve olculen 11 m dondurulur.

Hicbir yerde hata yoktu — kapi SESSIZCE dusuruyordu.

DUZELTME: kapi acilirken (kalkis_tamam False->True) aktif bir formasyon
kayitliysa tarif YENIDEN istenir; tekrar-yutucu bilerek sifirlanir.

Bu dosya duzeltmenin dayandigi UC sozlesmeyi kilitliyor. Dugumun kendi
tick'i ROS gerektirdigi icin burada saf mantik siniirlaniyor; kapi
blogunun davranisi kod incelemesiyle dogrulandi (mode_manager_node,
"KAPI ONCESI istenen formasyon YENIDEN uygulaniyor").
"""

import unittest

from swarm_state_machine.mode_manager import tek_yayinci
from swarm_state_machine.mode_manager.mode_context import ModeContext


class _SahteDurum:
    """AgentStatus yerine yerel sahte (conftest gercegini MagicMock'luyor)."""

    def __init__(self, x, y, z=-5.0, yaw=0.0):
        self.pos_x, self.pos_y, self.pos_z = x, y, z
        self.heading_deg = yaw
        self.state = 5
        self.healthy = True
        self.armed = True


class TestKapiKapaliBaslar(unittest.TestCase):
    """Sozlesme 1: kalkis kapisi mandali KAPALI baslar."""

    def test_kalkis_tamam_baslangicta_FALSE(self):
        c = ModeContext(agent_ids=[1, 2])
        self.assertFalse(c.kalkis_tamam)

    def test_B19_sifirlamasi_kapiyi_KAPATIR(self):
        """Ikinci kalkista kapi yeniden kapanmali; yoksa yerde tarif cikar."""
        c = ModeContext(agent_ids=[1, 2])
        c.kalkis_tamam = True
        c.ucus_durumunu_sifirla()
        self.assertFalse(c.kalkis_tamam)


class TestTekrarYutucu(unittest.TestCase):
    """Sozlesme 2: ayni tip + ayni aralik ELENIR.

    🔴 Duzeltmenin `_son_islenen_aralik = None` yapmasinin sebebi tam
    bu: kapi acilirken yeniden istenen tarif "ayni tip + ayni aralik"
    oldugu icin yutucu tarafindan elenir ve duzeltme HICBIR SEY yapmazdi.
    """

    def test_ayni_tip_ayni_aralik_ELENIR(self):
        self.assertFalse(tek_yayinci.degisim_islenir_mi(3, 3, 6.0, 6.0))

    def test_ayni_tip_FARKLI_aralik_islenir(self):
        self.assertTrue(tek_yayinci.degisim_islenir_mi(3, 3, 6.0, 7.0))

    def test_FARKLI_tip_islenir(self):
        """Sahada V'ye gecince calismasinin sebebi buydu (tip 3 -> 2)."""
        self.assertTrue(tek_yayinci.degisim_islenir_mi(2, 3, 6.0, 6.0))


class TestOlculenOfsetler(unittest.TestCase):
    """Sozlesme 3: kapi acilirken olculen geometri donduruluyor.

    Duzeltme olmadan sahada olan buydu: 11 m'lik gercek dizilim
    FORMATION_UNKNOWN olarak donduruldu ve suru orada kaldi.
    """

    def test_olculen_ofsetler_GERCEK_dizilimi_verir(self):
        c = ModeContext(agent_ids=[1, 2], lider_id=1)
        c.agent_statuses[1] = _SahteDurum(0.0, 0.0)
        c.agent_statuses[2] = _SahteDurum(0.0, 11.0)
        c.konumdan_tohumla()
        off = c.olculen_ofsetler()
        self.assertEqual(len(off), 2)
        # Lider merkez oldugu icin kendi ofseti sifir olmali.
        self.assertAlmostEqual(off[1][0], 0.0, places=3)
        self.assertAlmostEqual(off[1][1], 0.0, places=3)
        # Takipci 11 m uzakta — yani "6 m'ye dusurmediler" tablosu.
        mesafe = (off[2][0] ** 2 + off[2][1] ** 2) ** 0.5
        self.assertAlmostEqual(mesafe, 11.0, places=2)


if __name__ == '__main__':
    unittest.main()
