# Copyright 2026 Yelpence
"""SwC debounce birim testleri — madde 26.

Buradaki sayılar UYDURMA DEĞİL: 30 Ağustos 2026'da ylp00 üzerinde,
FS-i6X #2 ile, iki ayrı kayıtta ölçülen 11 geçişin gerçek süreleri.
Ölçüm aracı: src/gcs/kumanda_olc.py --swc
"""

import unittest

from swarm_state_machine.mode_manager.swc_debounce import (
    SwcDebounce,
    VARSAYILAN_ESIK_MS,
)

# SwarmControlCommand.FORMATION_* karşılıkları (mesaj import etmeden).
OKBASI, V, CIZGI = 1, 2, 3

# 🔴 SAHA ÖLÇÜMÜ — 31 Ağustos 2026, YENİ KUMANDA, iki kayıt.
# 852 ile 321 arasındaki çelişki çözülmedi; eşik en kötüye göre konuldu.
OLCULEN_GECISLER_MS = [92, 100, 120, 158, 162, 200, 214, 215, 321, 364, 852]

HZ = 32.5           # rc_ibus_kopru ölçülen yayın hızı
ADIM = 1.0 / HZ


def _besle(d: SwcDebounce, bolge, sure_s, t0):
    """Bölgeyi verilen süre boyunca 32,5 Hz'de besler; (tetik, t) döner."""
    tetik, t = 0, t0
    bitis = t0 + sure_s
    while t < bitis:
        if d.guncelle(bolge, t):
            tetik += 1
        t += ADIM
    return tetik, t


class TestSwcDebounce(unittest.TestCase):
    """Ölçülen geçişlerle debounce davranışı."""

    def test_esik_olculen_tavanin_USTUNDE(self):
        """500 ms, ölçülen en uzun geçişten (342) belirgin büyük olmalı."""
        self.assertGreater(VARSAYILAN_ESIK_MS, max(OLCULEN_GECISLER_MS))
        pay = VARSAYILAN_ESIK_MS - max(OLCULEN_GECISLER_MS)
        self.assertGreaterEqual(pay, 300.0, 'pay 300 ms altina dusmus')

    def test_OLCULEN_HICBIR_GECIS_tetiklemiyor(self):
        """🔴 Maddenin bütün amacı bu: geçerken V morfu BAŞLAMAMALI."""
        for ms in OLCULEN_GECISLER_MS:
            with self.subTest(gecis_ms=ms):
                d = SwcDebounce()
                t = 0.0
                _, t = _besle(d, OKBASI, 2.0, t)      # bir uçta otur
                d.kararli = OKBASI                     # kararlı hâl
                tetik_orta, t = _besle(d, V, ms / 1000.0, t)
                self.assertEqual(tetik_orta, 0, f'{ms} ms geçiş TETİKLEDİ')
                tetik_uc, t = _besle(d, CIZGI, 2.0, t)
                self.assertEqual(tetik_uc, 1, 'çizgi bir kez tetiklemeli')
                self.assertEqual(d.kararli, CIZGI)

    def test_KASITLI_V_secimi_tetikler(self):
        """Ortada kalınırsa V seçilmeli — yoksa şartname direktifi karşılanmaz."""
        d = SwcDebounce()
        t = 0.0
        _, t = _besle(d, OKBASI, 2.0, t)
        d.kararli = OKBASI
        tetik, t = _besle(d, V, 3.0, t)
        self.assertEqual(tetik, 1)
        self.assertEqual(d.kararli, V)

    def test_esikten_hemen_ONCE_tetiklemez_SONRA_tetikler(self):
        d = SwcDebounce()
        d.kararli = OKBASI
        d.guncelle(V, 0.0)
        self.assertFalse(d.guncelle(V, 1.29))
        self.assertTrue(d.guncelle(V, 1.31))

    def test_TEK_ATIS_her_tick_tetiklemez(self):
        """Salter V'de dururken 30 Hz'de değişim yağmazdı."""
        d = SwcDebounce()
        d.kararli = OKBASI
        tetik, _ = _besle(d, V, 6.0, 0.0)
        self.assertEqual(tetik, 1)

    def test_ortada_DURAKLAYIP_devam_V_secer(self):
        """Ayırt edilemez ve doğrusu bu: 500 ms detentte durmak = V seçmek."""
        d = SwcDebounce()
        t = 0.0
        _, t = _besle(d, OKBASI, 2.0, t)
        d.kararli = OKBASI
        tetik_orta, t = _besle(d, V, 2.0, t)
        self.assertEqual(tetik_orta, 1)
        tetik_uc, t = _besle(d, CIZGI, 2.0, t)
        self.assertEqual(tetik_uc, 1)

    def test_ileri_geri_OYNAMA_tetiklemez(self):
        """Sınırda titreşen bir salter değişim yağdırmamalı."""
        d = SwcDebounce()
        d.kararli = OKBASI
        t, tetik = 0.0, 0
        for _ in range(40):
            for bolge in (V, OKBASI):
                for _ in range(6):          # ~185 ms
                    if d.guncelle(bolge, t):
                        tetik += 1
                    t += ADIM
        self.assertEqual(tetik, 0)

    def test_acilista_ilk_karar_URETILIR(self):
        """Açılışta pilotun SwC seçimi sürüye bildirilmeli (eski davranış)."""
        d = SwcDebounce()
        self.assertIsNone(d.kararli)
        tetik, _ = _besle(d, CIZGI, 2.0, 0.0)
        self.assertEqual(tetik, 1)
        self.assertEqual(d.kararli, CIZGI)

    def test_esitle_SAHTE_DEGISIM_uretmez(self):
        """SwA kapalıyken salter oynadıysa, açılınca değişim tetiklenmemeli."""
        d = SwcDebounce()
        d.kararli = OKBASI
        d.esitle(CIZGI, 0.0)                 # emniyet kapalıyken oynadı
        tetik, _ = _besle(d, CIZGI, 3.0, 0.1)
        self.assertEqual(tetik, 0)
        self.assertEqual(d.kararli, CIZGI)

    def test_esitle_sonrasi_GERCEK_degisim_hala_calisir(self):
        d = SwcDebounce()
        d.esitle(CIZGI, 0.0)
        tetik, t = _besle(d, V, 2.0, 0.1)
        self.assertEqual(tetik, 1)
        self.assertEqual(d.kararli, V)

    def test_esik_sifir_ANINDA_tetikler(self):
        """Kapatma yolu: 0 ms = debounce yok (eski davranış)."""
        d = SwcDebounce(esik_ms=0.0)
        d.kararli = OKBASI
        d.guncelle(V, 0.0)
        self.assertTrue(d.guncelle(V, 0.0))

    def test_negatif_esik_SIFIRA_kirpilir(self):
        self.assertEqual(SwcDebounce(esik_ms=-100.0).esik_s, 0.0)


if __name__ == '__main__':
    unittest.main()
