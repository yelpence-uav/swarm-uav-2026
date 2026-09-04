# Copyright 2026 Yelpence
"""4 Eylul 2026 UCUSUNDA OLCULEN IKI KUSURUN testleri.

Ikisi de 30 saniyelik SwD kalkis-aski-inis ucusunun kaydindan cikti; ikisi
de sessizdi (hata vermiyorlardi, yanlis/gec sonuc uretiyorlardi).

KUSUR 1 — LANDING cikisi ZAMAN ASIMIYLA oluyordu.
  Olcum: LANDING -> COMPLETED iki ucakta da TAM 90,00 sn surdu, yani
  `_LANDING_TIMEOUT_S`. `all_agents_landed()` STATE_LANDED(13) ariyor ama
  Gorev 2'de inisi px4_bridge suruyor ve agent_fsm disarm'da ARMED -> IDLE
  yapip LANDED'a hic ugramiyor (kayit: ylp00 t=86,26 IDLE).
  Zarar ZAMAN: B19 cikisi (ikinci kalkis hakki) 90 sn gecikiyor, gorev
  basina UC hak var.

KUSUR 2 — mode_manager sabit lideri BILMIYORDU.
  Olcum: ylp01 uctan uca `TEK-YAYINCI: ... lider=None` yazdi; ElectionResult
  mesh'ten hic ulasmadi (lider onu yalnizca secim aninda BIR KEZ yayinliyor,
  ESP-NOW kaybi %6,7-21,7). Dogru davrandi ama TESADUFEN: yedek yol
  min(agent_ids)=1 ve sabit lider de 1'di. Kadro (1,3) + sabit lider 3
  olsaydi yanlis ucak yayinci olurdu ve formasyon SESSIZCE kurulmazdi.
"""

import unittest

from swarm_state_machine.mode_manager import tek_yayinci
from swarm_state_machine.mode_manager.mode_context import ModeContext
from swarm_state_machine.mode_manager.mode_states import ModeState
from swarm_state_machine.mode_manager.mode_transitions import (
    evaluate_transitions,
)

_LANDED = 13
_ARMED = 3


class _SahteDurum:
    """AgentStatus yerine YEREL sahte durum nesnesi.

    Gerekce test_suru_basligi_liderden icinde ayrintili: conftest
    AgentStatus'u MagicMock yapiyor ve her cagri AYNI nesneyi donduruyor;
    iki ucak tek nesneye cakisiyordu.
    """

    def __init__(self, state, armed):
        self.state = state
        self.armed = armed
        self.healthy = True
        self.pos_x = self.pos_y = self.pos_z = 0.0
        self.heading_deg = 0.0


def _durum(state, armed):
    return _SahteDurum(state, armed)


def _ctx_landing(kadro, durumlar):
    c = ModeContext(agent_ids=list(kadro))
    c.state = ModeState.LANDING
    for aid, (st, armed) in durumlar.items():
        c.agent_statuses[aid] = _durum(st, armed)
    return c


class TestInisCikisi(unittest.TestCase):
    """KUSUR 1 — disarm da bir inis kanitidir."""

    def test_DISARM_inis_sayilir_zaman_asimi_BEKLENMEZ(self):
        """Sahada olculen hal: LANDED yok ama hepsi disarm."""
        c = _ctx_landing((1, 2), {1: (1, False), 2: (1, False)})  # IDLE+disarm
        self.assertEqual(evaluate_transitions(c), ModeState.COMPLETED)

    def test_LANDED_yolu_KORUNDU(self):
        """Eski cikis yolu bozulmadi."""
        c = _ctx_landing((1, 2), {1: (_LANDED, False), 2: (_LANDED, False)})
        self.assertEqual(evaluate_transitions(c), ModeState.COMPLETED)

    def test_BIRI_HALA_ARMLI_ise_COMPLETED_YOK(self):
        """🔴 Havada ucak varken defter temizlenmez."""
        c = _ctx_landing((1, 2), {1: (1, False), 2: (_ARMED, True)})
        self.assertIsNone(evaluate_transitions(c))

    def test_EKSIK_TELEMETRI_ise_COMPLETED_YOK(self):
        """Bir ucagin durumu hic gelmediyse iki kapi da False donmeli.

        Boylece tek cikis zaman asimi kalir — yedek bilerek duruyor.
        """
        c = _ctx_landing((1, 2), {1: (1, False)})   # ajan 2 hic gorulmedi
        self.assertIsNone(evaluate_transitions(c))


class TestSabitLiderYayinci(unittest.TestCase):
    """KUSUR 2 — yayinci kimligi mesh'e bagimli kalmamali."""

    def test_TESADUF_sabit_lider_min_ise_yedek_yol_dogru_verir(self):
        """4 Eylul'de bizi kurtaran hal: sabit=1 ve min(1,2)=1."""
        self.assertTrue(tek_yayinci.tarif_yayinlanir_mi(1, None, [1, 2]))
        self.assertFalse(tek_yayinci.tarif_yayinlanir_mi(2, None, [1, 2]))

    def test_TESADUF_BOZULDUGUNDA_yedek_yol_YANLIS_ucagi_secer(self):
        """🔴 Kusurun kaniti: sabit lider 3, kadro (1,3), lider bilinmiyor.

        Yedek yol min=1 diyor -> ylp00 tarif basar, gercek lider ylp02
        susar. Bu test yedek yolun NEDEN yetmedigini kilitliyor.
        """
        self.assertTrue(tek_yayinci.tarif_yayinlanir_mi(1, None, [1, 3]))
        self.assertFalse(tek_yayinci.tarif_yayinlanir_mi(3, None, [1, 3]))

    def test_LIDER_VERILDIGINDE_dogru_ucak_secilir(self):
        """Duzeltme: kimlik parametreden gelince tesaduf ortadan kalkar."""
        self.assertFalse(tek_yayinci.tarif_yayinlanir_mi(1, 3, [1, 3]))
        self.assertTrue(tek_yayinci.tarif_yayinlanir_mi(3, 3, [1, 3]))

    def test_iki_ucakli_bugunku_kadro(self):
        """Sahadaki hal: kadro (1,2), sabit lider 1."""
        self.assertTrue(tek_yayinci.tarif_yayinlanir_mi(1, 1, [1, 2]))
        self.assertFalse(tek_yayinci.tarif_yayinlanir_mi(2, 1, [1, 2]))


if __name__ == '__main__':
    unittest.main()
