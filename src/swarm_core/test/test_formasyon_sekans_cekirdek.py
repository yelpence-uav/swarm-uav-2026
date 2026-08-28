# Copyright 2026 Yelpence
"""formasyon_sekans_cekirdek birim testleri (ROS'suz, dizüstünde koşar).

NEDEN BU TESTLER VAR
Sekans düğümü ilk kez 28 Ağustos geçiş testinde havaya kalkacak ve
hataları havada görmek kabul edilemez. Burada kilitlenenler:

  1. Faz planı doğrulaması — bozuk parametre uçakta sessizce boş
     koşmasın, açılışta patlasın.
  2. 7 m geometrisinin SAYILARI — geçişlerdeki en yakın mesafeler
     (6,47 / 4,95 m) plan sunumunda operatöre verilen değerlerle aynı.
     Kod değişir de sayılar kayarsa bu test onu yakalar.
  3. Atama sözleşmesi — agent_ids SLOT SIRASINDA (mesh slot_ajan[]
     bu sırayı taşıyor) ve Macar ataması en yakın uçağı slota koyuyor.
  4. Heading türetmesi — çizgi, uçakların yerdeki ana eksenine oturuyor
     (deterministik; kuru test ile uçak aynı sonucu hesaplar).
  5. Kalkış kapısı — bayat/eksik/alçak uçak varken sekans başlamaz.
"""

import math
import unittest

from swarm_core.formation_control import formasyon_sekans_cekirdek as cek
from swarm_core.formation_control.formation_geometry import (
    FORMATION_CIZGI,
    FORMATION_OKBASI,
    FORMATION_V,
    compute_slot_offsets,
)


class TestFazPlani(unittest.TestCase):
    def test_varsayilan_sekans(self):
        plan = cek.faz_plani(['cizgi', 'okbasi', 'v'], [40.0, 30.0, 30.0])
        self.assertEqual(
            [t for t, _s in plan],
            [FORMATION_CIZGI, FORMATION_OKBASI, FORMATION_V],
        )
        self.assertAlmostEqual(cek.toplam_sure_s(plan), 100.0)

    def test_kisa_sure_listesi_son_deger_tekrarlanir(self):
        plan = cek.faz_plani(['cizgi', 'okbasi', 'v'], [40.0])
        self.assertEqual([s for _t, s in plan], [40.0, 40.0, 40.0])

    def test_uzun_sure_listesi_hata(self):
        with self.assertRaises(ValueError):
            cek.faz_plani(['cizgi'], [10.0, 20.0])

    def test_bilinmeyen_faz_hata(self):
        with self.assertRaises(ValueError):
            cek.faz_plani(['cizgi', 'daire'], [10.0])

    def test_ardisik_ayni_faz_hata(self):
        # formation_node atamayı tipe donduruyor; aynı tip reshape üretmez.
        with self.assertRaises(ValueError):
            cek.faz_plani(['cizgi', 'cizgi'], [10.0])

    def test_sifir_sure_hata(self):
        with self.assertRaises(ValueError):
            cek.faz_plani(['cizgi', 'v'], [10.0, 0.0])


class TestGecisMesafeleri(unittest.TestCase):
    """7 m aralık, 45° kanat — plan sunumundaki sayıların kilidi."""

    def test_sabit_hallerde_7m(self):
        for tip in (FORMATION_CIZGI, FORMATION_OKBASI, FORMATION_V):
            slots = compute_slot_offsets(tip, 3, 7.0, math.radians(45.0))
            dmin = min(
                math.dist(slots[i][:2], slots[j][:2])
                for i in range(3) for j in range(i + 1, 3)
            )
            self.assertAlmostEqual(dmin, 7.0, places=2, msg=f'tip={tip}')

    def test_cizgi_okbasi_gecisi(self):
        d = cek.gecis_min_mesafe(FORMATION_CIZGI, FORMATION_OKBASI, 3,
                                 7.0, 45.0)
        self.assertAlmostEqual(d, 6.47, places=2)

    def test_okbasi_v_gecisi_en_dar_an(self):
        # Kanatlar liderin yanından s·sin(45°) = 4,95 m ile geçer.
        # Kaçınma d0=4,0'ın ÜSTÜNDE ama pay < 1 m — bilinerek uçulacak.
        d = cek.gecis_min_mesafe(FORMATION_OKBASI, FORMATION_V, 3, 7.0, 45.0)
        self.assertAlmostEqual(d, 7.0 * math.sin(math.radians(45.0)),
                               places=2)

    def test_gecis_atamasi_capraz_secmiyor(self):
        # Macar, A slotlarında oturan uçakları B'nin AYNI taraf slotlarına
        # atamalı; çapraz atama (sağ kanat sola) yol kesiştirir ve mesafeyi
        # düşürürdü. 4,95 m sonucu zaten bunu doğruluyor; burada ayrıca
        # simetrik üç tip için de kilitliyoruz.
        for a, b in [(FORMATION_CIZGI, FORMATION_V),
                     (FORMATION_V, FORMATION_CIZGI),
                     (FORMATION_OKBASI, FORMATION_CIZGI)]:
            d = cek.gecis_min_mesafe(a, b, 3, 7.0, 45.0)
            self.assertGreaterEqual(d, 6.4, msg=f'{a}->{b}: {d:.2f}')


class TestAtama(unittest.TestCase):
    def test_agent_ids_slot_sirasinda(self):
        # Uçaklar çizgi slotlarının yakınına konmuş: 1 merkezde, 3 sağda
        # (+y), 2 solda (-y). Beklenen slot sırası [1, 3, 2] — slot 0
        # merkez, slot 1 sağ (+y), slot 2 sol (-y).
        konumlar = {1: (0.0, 0.5), 2: (0.3, -6.8), 3: (-0.2, 7.1)}
        ids, ofsetler = cek.atama(
            FORMATION_CIZGI, konumlar, (0.0, 0.0), 0.0, 7.0, 45.0
        )
        self.assertEqual(ids, [1, 3, 2])
        self.assertEqual(len(ofsetler), 3)
        self.assertAlmostEqual(ofsetler[1][1], +7.0)
        self.assertAlmostEqual(ofsetler[2][1], -7.0)

    def test_heading_donmus_slotlara_atama(self):
        # heading 90° → çizgi slotları dünya x (kuzey) yerine -x/+x değil,
        # (0,±7) gövde → dünyada (∓7, 0)... rotate(0,7,90°) = (-7, 0).
        # Kuzeyde duran uçak slot 1'i (dünya -7 kuzey??) değil; sayısal
        # olarak doğrula: slotların dünya konumuna en yakın uçak atanmış.
        konumlar = {1: (0.0, 0.0), 2: (-6.5, 0.4), 3: (6.9, -0.3)}
        ids, ofsetler = cek.atama(
            FORMATION_CIZGI, konumlar, (0.0, 0.0), 90.0, 7.0, 45.0
        )
        # rotate_offset(0,+7, 90°) = (-7, 0) → slot 1 dünyada kuzey -7
        # tarafında: oraya en yakın uçak 2. Slot 2 (0,-7)→(+7,0): uçak 3.
        self.assertEqual(ids, [1, 2, 3])

    def test_kadro_iki_ucak(self):
        konumlar = {1: (0.0, 3.0), 3: (0.0, -3.0)}
        ids, ofsetler = cek.atama(
            FORMATION_CIZGI, konumlar, (0.0, 0.0), 0.0, 7.0, 45.0
        )
        self.assertEqual(sorted(ids), [1, 3])
        self.assertEqual(len(ofsetler), 2)


class TestHeading(unittest.TestCase):
    def test_dogu_bati_dizilim(self):
        # Uçaklar doğu-batı hattında → eksen 90° (doğu). İşaret kuralı:
        # en küçük kimlik (1) batıda (izdüşüm -10 < 0) → eksen 270'e
        # çevrilir → heading = 270 - 90 = 180. Çizgi yine doğu-batı
        # hattına oturur; kural yalnız yönü DETERMİNİSTİK yapar.
        konumlar = {1: (0.0, -10.0), 2: (0.0, 0.0), 3: (0.0, 10.0)}
        h = cek.otomatik_heading_deg(konumlar)
        self.assertAlmostEqual(h, 180.0, places=1)

    def test_kuzey_guney_dizilim(self):
        # Eksen 0° (kuzey); kimlik 1 güneyde (izdüşüm -8) → eksen 180 →
        # heading = 90.
        konumlar = {1: (-8.0, 0.0), 2: (0.0, 0.0), 3: (9.0, 0.0)}
        h = cek.otomatik_heading_deg(konumlar)
        self.assertAlmostEqual(h, 90.0, places=1)

    def test_isaret_kurali_kimlik1_pozitif_tarafta(self):
        # Aynı hat, kimlik 1 bu kez DOĞUDA → eksen 90 kalır → heading 0.
        # (Üstteki testin aynası: işaret gerçekten konumdan geliyor.)
        konumlar = {1: (0.0, 10.0), 2: (0.0, 0.0), 3: (0.0, -10.0)}
        h = cek.otomatik_heading_deg(konumlar)
        self.assertAlmostEqual(h, 0.0, places=1)

    def test_isaret_kurali_ortadaki_kucuk_kimligi_atlar(self):
        # Kimlik 1 merkezde (izdüşüm ~0) → kural onu atlayıp 2'ye bakar.
        konumlar = {1: (0.0, 0.1), 2: (0.0, 9.8), 3: (0.0, -10.0)}
        h = cek.otomatik_heading_deg(konumlar)
        self.assertAlmostEqual(h, 0.0, places=1)

    def test_cizgi_slotlari_ana_eksene_oturuyor(self):
        # Asıl istenen davranışın uçtan uca kilidi: türetilen heading ile
        # çizgi slotları, uçakların yerdeki hattına paralel açılmalı →
        # atama sonrası toplam yol KISA olmalı (< aralığın yarısı/uçak).
        konumlar = {1: (2.0, -7.2), 2: (1.8, 0.1), 3: (2.2, 7.3)}
        merkez = cek.agirlik_merkezi(konumlar)
        h = cek.otomatik_heading_deg(konumlar)
        ids, ofsetler = cek.atama(
            FORMATION_CIZGI, konumlar, merkez, h, 7.0, 45.0
        )
        from swarm_core.formation_control.formation_geometry import (
            rotate_offset,
        )
        toplam = 0.0
        for k, a in enumerate(ids):
            rx, ry = rotate_offset(
                ofsetler[k][0], ofsetler[k][1], math.radians(h)
            )
            sx, sy = merkez[0] + rx, merkez[1] + ry
            toplam += math.hypot(konumlar[a][0] - sx, konumlar[a][1] - sy)
        self.assertLess(toplam / 3, 1.0)

    def test_yozlasik_durum_sifir(self):
        self.assertEqual(
            cek.otomatik_heading_deg({1: (5.0, 5.0)}), 0.0
        )
        self.assertEqual(
            cek.otomatik_heading_deg(
                {1: (1.0, 1.0), 2: (1.0, 1.0), 3: (1.0, 1.0)}
            ),
            0.0,
        )

    def test_cm_gurultusuyle_kararli(self):
        # Üç uçak aynı diziliş, cm'lik konum farkı (iki uçağın ayrı
        # örneklemesi) → heading derece kesrinden fazla oynamamalı.
        a = {1: (0.0, -10.0), 2: (0.5, 0.0), 3: (0.0, 10.0)}
        b = {1: (0.02, -10.01), 2: (0.49, 0.03), 3: (-0.01, 9.98)}
        self.assertLess(
            abs(cek.otomatik_heading_deg(a) - cek.otomatik_heading_deg(b)),
            0.5,
        )


class TestKalkisKapisi(unittest.TestCase):
    _KADRO = [1, 2, 3]

    def _tam(self):
        return (
            {1: 8.1, 2: 7.9, 3: 8.3},          # irtifalar
            {1: 0.1, 2: 0.2, 3: 0.1},          # yaslar
            {1: True, 2: True, 3: True},        # origin
        )

    def test_hepsi_hazir(self):
        irt, yas, snk = self._tam()
        hazir, eksik = cek.kalkis_hazir_mi(
            self._KADRO, irt, yas, snk, 8.0, 0.8, 2.0
        )
        self.assertTrue(hazir)
        self.assertEqual(eksik, [])

    def test_alcak_ucak_engeller(self):
        irt, yas, snk = self._tam()
        irt[2] = 3.0
        hazir, eksik = cek.kalkis_hazir_mi(
            self._KADRO, irt, yas, snk, 8.0, 0.8, 2.0
        )
        self.assertFalse(hazir)
        self.assertIn('drone2', eksik[0])

    def test_bayat_veri_engeller(self):
        irt, yas, snk = self._tam()
        yas[3] = 5.0
        hazir, eksik = cek.kalkis_hazir_mi(
            self._KADRO, irt, yas, snk, 8.0, 0.8, 2.0
        )
        self.assertFalse(hazir)
        self.assertIn('bayat', eksik[0])

    def test_hic_veri_gelmeyen_engeller(self):
        irt, yas, snk = self._tam()
        del irt[1], yas[1], snk[1]
        hazir, eksik = cek.kalkis_hazir_mi(
            self._KADRO, irt, yas, snk, 8.0, 0.8, 2.0
        )
        self.assertFalse(hazir)
        self.assertIn('HIC', eksik[0])

    def test_origin_senkronsuz_engeller(self):
        irt, yas, snk = self._tam()
        snk[2] = False
        hazir, eksik = cek.kalkis_hazir_mi(
            self._KADRO, irt, yas, snk, 8.0, 0.8, 2.0
        )
        self.assertFalse(hazir)
        self.assertIn('origin', eksik[0])

    def test_g0_irtifa_atlama_yalniz_irtifayi_atlar(self):
        # G0 yer testi: uçaklar yerde (irtifa ~0) → irtifa_sart=False ile
        # kapı açılır; ama bayat veri ve origin şartı AYNEN kalır.
        irt = {1: -0.2, 2: 0.1, 3: 0.0}
        yas = {1: 0.1, 2: 0.2, 3: 0.1}
        snk = {1: True, 2: True, 3: True}
        hazir, eksik = cek.kalkis_hazir_mi(
            self._KADRO, irt, yas, snk, 8.0, 0.8, 2.0, irtifa_sart=False
        )
        self.assertTrue(hazir)
        yas[2] = 9.0
        hazir, eksik = cek.kalkis_hazir_mi(
            self._KADRO, irt, yas, snk, 8.0, 0.8, 2.0, irtifa_sart=False
        )
        self.assertFalse(hazir)
        self.assertIn('bayat', eksik[0])


if __name__ == '__main__':
    unittest.main()
