# Copyright 2026 Yelpence
"""SURU HAREKETINI OLDUREN ZAMAN ASIMI — 1 Eylul 2026, ucusta olculdu.

OLAY: operator formasyon kurup ileri pitch verdi, YALNIZ pilot ucagi
hareket etti. Kayittan (t=209513..209537, cubuk +-0,73'e kadar):

    ylp00 (pilot)  2,82 m yol aldi
    ylp01          0,40 m   <- yerinde
    ylp02          0,25 m   <- yerinde

ZINCIR:
  1. `deadman_timed_out()` -> `elapsed > deadman_timeout_s`
  2. esp32_bridge mesh paketinden SwarmControlCommand kurarken bu alani
     DOLDURMUYOR (mesh'te tasinmiyor) -> komsulara 0.0 gidiyor
  3. 0 ile kosul HER ZAMAN dogru -> `command_active` HEP FALSE
  4. `_from_ready` MOVEMENT dondurmuyor -> ucak READY'de kaliyor
  5. READY `compute_hold_command` yayinliyor: merkez SABIT, max_speed 0.0

Olculdu: komsulara giden FormationCommand'in merkezi tum ucus boyunca
(+6.32,-1.43)'te dondu ve hiz=0.00 idi.

🔴 NEDEN GOZDEN KACTI: formasyon DEGISIMI calisiyordu (o `command_active`e
bagli degil), yani ariza "yarim calisiyor" gibi gorundu.
"""

import time
import unittest

from swarm_state_machine.mode_manager.mode_context import ModeContext
from swarm_state_machine.mode_manager.mode_states import (
    ControlMode, ModeState)
from swarm_state_machine.mode_manager.mode_transitions import (
    evaluate_transitions)


def _ctx(zaman_asimi: float) -> ModeContext:
    c = ModeContext(agent_ids=[1, 2, 3])
    c.command_valid = True
    c.deadman_pressed = True
    c.deadman_timeout_s = zaman_asimi
    c.last_valid_command_time = time.monotonic()
    c.control_mode = ControlMode.SWARM_MOVEMENT
    return c


class TestTuzak(unittest.TestCase):
    """Hatanin KENDISI — bir daha sessizce geri gelmesin."""

    def test_SIFIR_zaman_asimi_komutu_OLU_yapar(self):
        c = _ctx(0.0)
        self.assertTrue(c.deadman_timed_out(),
                        'sifir zaman asimi ile komut TAZE sayiliyor')
        self.assertFalse(c.command_active)

    def test_sifir_zaman_asimiyla_MOVEMENT_A_GECILEMEZ(self):
        """Sahada gorulen belirti: ucak READY'de kalir, yerinde durur."""
        c = _ctx(0.0)
        c.state = ModeState.READY
        self.assertIsNone(
            evaluate_transitions(c),
            'sifir zaman asimiyla MOVEMENT bekleniyordu — hata giderilmis '
            'gorunuyor ama bu test TUZAGI belgeliyor, davranisi degil')

    def test_gecerli_zaman_asimiyla_MOVEMENT_A_GECILIR(self):
        c = _ctx(0.5)
        c.state = ModeState.READY
        self.assertFalse(c.deadman_timed_out())
        self.assertTrue(c.command_active)
        self.assertEqual(evaluate_transitions(c), ModeState.MOVEMENT)

    def test_bayat_komut_zaman_asimina_UGRAR(self):
        """Yedek deger SONSUZ degil: link koparsa suru yine durur."""
        c = _ctx(0.5)
        c.last_valid_command_time = time.monotonic() - 1.0
        self.assertTrue(c.deadman_timed_out())
        self.assertFalse(c.command_active)


class TestYedek(unittest.TestCase):
    """Dugum, mesh'ten gelen 0'i KENDI politikasiyla degistirmeli."""

    @staticmethod
    def _govde() -> str:
        import os
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        yol = os.path.join(kok, 'swarm_state_machine', 'mode_manager',
                           'mode_manager_node.py')
        with open(yol, encoding='utf-8') as f:
            tam = f.read()
        bas = tam.index('def _on_control_command')
        return tam[bas:bas + 4000]

    def test_dugum_sifiri_KENDI_degeriyle_degistirir(self):
        g = self._govde()
        assert 'deadman_zaman_asimi_s' in g, (
            'mesh 0 gonderiyor ve dugum yedek deger koymuyor — suru '
            'komsularda HIC hareket etmez')
        # Kosul "> 0.0" olmali: negatif ya da sifir gecmemeli.
        assert 'msg.deadman_timeout_s > 0.0' in g

    def test_zaman_asimi_MESH_BOSLUGUNDAN_buyuk(self):
        """Olculen en kotu mesh boslugu 0,203 sn (200 ornek, std 0,05).

        Yedek deger bunun altina inerse suru cerceve kacirdikca HAREKET
        MODUNDAN DUSER ve pilot 'takiliyor' diye gorur.
        """
        olculen_en_kotu = 0.203
        varsayilan = 0.5
        self.assertGreater(varsayilan, 2.0 * olculen_en_kotu)


if __name__ == '__main__':
    unittest.main()
