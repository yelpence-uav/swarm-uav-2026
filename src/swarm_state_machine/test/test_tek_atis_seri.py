# Copyright 2026 Yelpence
"""TEK ATIŞLIK bayrak serisi — 31 Ağustos uçuşunun kusurunu kilitler.

Ölçülen: komut ~46 Hz yayınlanıyor, komşuya mesh'ten 12,6 Hz varıyor
(~4'te 1). Tek çerçeve süren kalkış isteği ~%75 düşüyordu ve ilk pervaneli
denemede YALNIZ pilot uçağı kalktı.
"""

import unittest

from swarm_state_machine.mode_manager.tek_atis_seri import (
    TekAtisSeri,
    VARSAYILAN_SURE_MS,
)

HZ = 46.0                 # joystick_interpreter ölçülen yayın hızı
ADIM = 1.0 / HZ
MESH_GECIS = 4            # ölçülen: ~4 çerçeveden 1'i komşuya varıyor


class TestTekAtisSeri(unittest.TestCase):

    def test_kenar_TEK_CERCEVE_DEGIL_seri_uretir(self):
        """🔴 Kusurun özü: tek çerçeve mesh'te kayboluyordu."""
        s = TekAtisSeri()
        t = 0.0
        s.tetikle(t)
        cerceve = 0
        while s.aktif(t):
            cerceve += 1
            t += ADIM
        self.assertGreater(cerceve, 20, 'seri en az ~20 çerçeve sürmeli')

    def test_MESH_KAYBINA_dayaniyor(self):
        """4'te 1 geçen kanalda bile birden çok kopya varmalı."""
        s = TekAtisSeri()
        t = 0.0
        s.tetikle(t)
        gecen, i = 0, 0
        while s.aktif(t):
            if i % MESH_GECIS == 0:
                gecen += 1
            i += 1
            t += ADIM
        self.assertGreaterEqual(gecen, 5, f'yalnız {gecen} kopya geçiyor')

    def test_MANDAL_DEGIL_kendiliginden_duser(self):
        """Mandal olsaydı sürü inip PREFLIGHT'a dönünce kendiliğinden kalkardı."""
        s = TekAtisSeri()
        s.tetikle(0.0)
        self.assertTrue(s.aktif(0.1))
        self.assertFalse(s.aktif(VARSAYILAN_SURE_MS / 1000.0 + 0.01))

    def test_tetiklenmeden_ASLA_aktif_degil(self):
        s = TekAtisSeri()
        self.assertFalse(s.aktif(0.0))
        self.assertFalse(s.aktif(1000.0))

    def test_sifirla_seriyi_KESER(self):
        """Emniyet kapanınca bekleyen istek mesh'e akmaya devam etmemeli."""
        s = TekAtisSeri()
        s.tetikle(0.0)
        self.assertTrue(s.aktif(0.1))
        s.sifirla()
        self.assertFalse(s.aktif(0.11))

    def test_yeniden_tetikleme_SUREYI_UZATIR(self):
        s = TekAtisSeri()
        s.tetikle(0.0)
        s.tetikle(0.5)
        self.assertTrue(s.aktif(1.0))
        self.assertFalse(s.aktif(1.2))

    def test_sure_sifir_HIC_aktif_olmaz(self):
        """Kapatma yolu: 0 ms = eski (tek atış) davranış."""
        s = TekAtisSeri(sure_ms=0.0)
        s.tetikle(0.0)
        self.assertFalse(s.aktif(0.0))


if __name__ == '__main__':
    unittest.main()
