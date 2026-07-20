"""formation_geometry modulu icin birim testler."""

import math
import unittest

from swarm_core.formation_control.formation_geometry import (
    FORMATION_CIZGI,
    FORMATION_OKBASI,
    FORMATION_V,
    compute_min_drone_distance,
    compute_setpoint,
    compute_slot_offsets,
    rotate_offset,
    validate_formation_safety,
)


class TestSlotOffsetsCizgi(unittest.TestCase):
    """Cizgi formasyonu slot offsetlerini dogrular."""

    def test_uc_drone_simetrik(self):
        """3 drone heading=0: lider merkez, sag/sol simetrik acilim."""
        offsets = compute_slot_offsets(FORMATION_CIZGI, 3, 5.0, 0.0)
        self.assertEqual(len(offsets), 3)
        # rank 0 = lider, merkez
        self.assertAlmostEqual(offsets[0][0], 0.0)
        self.assertAlmostEqual(offsets[0][1], 0.0)
        # rank 1 = sag slot
        self.assertAlmostEqual(offsets[1][1], +5.0)
        # rank 2 = sol slot
        self.assertAlmostEqual(offsets[2][1], -5.0)

    def test_lider_merkezde(self):
        """rank 0 her N icin daima (0, 0, 0) olmali."""
        for n in (1, 2, 3, 4, 5, 8):
            offsets = compute_slot_offsets(FORMATION_CIZGI, n, 5.0, 0.0)
            self.assertEqual(offsets[0], (0.0, 0.0, 0.0))

    def test_z_daima_sifir(self):
        """Cizgi formasyonu sadece XY duzleminde olusur."""
        offsets = compute_slot_offsets(FORMATION_CIZGI, 5, 3.0, 0.0)
        for off in offsets:
            self.assertAlmostEqual(off[2], 0.0)

    def test_bes_drone_aralik(self):
        """5 drone, 3m aralik. Fiziksel komsular (Y siralamasinda) 3m."""
        offsets = compute_slot_offsets(FORMATION_CIZGI, 5, 3.0, 0.0)
        ys = sorted(off[1] for off in offsets)
        for i in range(len(ys) - 1):
            self.assertAlmostEqual(ys[i + 1] - ys[i], 3.0)


class TestSlotOffsetsOkBasi(unittest.TestCase):
    """Ok Basi formasyonu slot offsetlerini dogrular."""

    def test_lider_merkezde(self):
        """rank 0 daima (0, 0, 0) olmalı."""
        offsets = compute_slot_offsets(
            FORMATION_OKBASI, 3, 5.0, math.radians(30)
        )
        self.assertEqual(offsets[0], (0.0, 0.0, 0.0))

    def test_kanatlar_arkada(self):
        """Tum kanat drone'larinin x bileseni negatif (arkada)."""
        offsets = compute_slot_offsets(
            FORMATION_OKBASI, 5, 5.0, math.radians(30)
        )
        for off in offsets[1:]:
            self.assertLess(off[0], 0.0)

    def test_kanatlar_simetrik(self):
        """Sag-sol kanat ciftleri y ekseninde aynaya simetrik."""
        offsets = compute_slot_offsets(
            FORMATION_OKBASI, 3, 5.0, math.radians(30)
        )
        self.assertAlmostEqual(offsets[1][0], offsets[2][0])
        self.assertAlmostEqual(offsets[1][1], -offsets[2][1])


class TestSlotOffsetsV(unittest.TestCase):
    """V formasyonu slot offsetlerini dogrular."""

    def test_lider_merkezde(self):
        """rank 0 daima (0, 0, 0) olmalı."""
        offsets = compute_slot_offsets(
            FORMATION_V, 3, 5.0, math.radians(30)
        )
        self.assertEqual(offsets[0], (0.0, 0.0, 0.0))

    def test_kanatlar_onde(self):
        """Tum kanat drone'larinin x bileseni pozitif (onde)."""
        offsets = compute_slot_offsets(
            FORMATION_V, 5, 5.0, math.radians(30)
        )
        for off in offsets[1:]:
            self.assertGreater(off[0], 0.0)

    def test_kanatlar_simetrik(self):
        """Sag-sol kanat ciftleri y ekseninde aynaya simetrik."""
        offsets = compute_slot_offsets(
            FORMATION_V, 3, 5.0, math.radians(30)
        )
        self.assertAlmostEqual(offsets[1][0], offsets[2][0])
        self.assertAlmostEqual(offsets[1][1], -offsets[2][1])


class TestSlotOffsetsHatalar(unittest.TestCase):
    """compute_slot_offsets hata durumlarini dogrular."""

    def test_negatif_total(self):
        """total <= 0 icin ValueError."""
        with self.assertRaises(ValueError):
            compute_slot_offsets(FORMATION_OKBASI, 0, 5.0, 0.0)

    def test_negatif_spacing(self):
        """spacing <= 0 icin ValueError."""
        with self.assertRaises(ValueError):
            compute_slot_offsets(FORMATION_OKBASI, 3, -1.0, 0.0)

    def test_bilinmeyen_tip(self):
        """Bilinmeyen formation_type icin ValueError."""
        with self.assertRaises(ValueError):
            compute_slot_offsets(999, 3, 5.0, 0.0)

    def test_alpha_cok_kucuk_okbasi(self):
        """alpha=0 Ok Basi'nda kanatlari ust uste koyar -> ValueError."""
        with self.assertRaises(ValueError):
            compute_slot_offsets(FORMATION_OKBASI, 3, 5.0, 0.0)

    def test_alpha_cok_buyuk_v(self):
        """alpha=89° V'de formasyonu dejenere eder -> ValueError."""
        with self.assertRaises(ValueError):
            compute_slot_offsets(
                FORMATION_V, 3, 5.0, math.radians(89)
            )

    def test_alpha_cizgi_icin_yok_sayilir(self):
        """Cizgi formasyonu alpha'yi kullanmaz -> 0 alpha sorun olmamali."""
        offsets = compute_slot_offsets(FORMATION_CIZGI, 3, 5.0, 0.0)
        self.assertEqual(len(offsets), 3)


class TestOlcekJenerikN(unittest.TestCase):
    """Algoritmanin N'den bagimsiz oldugunu dogrular.

    Sartname jenerik gereksinimi ve birey ayrilma sonrasi
    N degisikliklerinde dogru calistigini dogrular.
    """

    def test_tek_drone_N1(self):
        """N=1: tek drone (lider) merkezde, tum formasyonlar."""
        for ftype in (FORMATION_OKBASI, FORMATION_V, FORMATION_CIZGI):
            offsets = compute_slot_offsets(
                ftype, 1, 5.0, math.radians(30)
            )
            self.assertEqual(len(offsets), 1)
            self.assertEqual(offsets[0], (0.0, 0.0, 0.0))

    def test_iki_drone_N2(self):
        """N=2: lider + 1 kanat (asimetrik ama gecerli)."""
        for ftype in (FORMATION_OKBASI, FORMATION_V, FORMATION_CIZGI):
            offsets = compute_slot_offsets(
                ftype, 2, 5.0, math.radians(30)
            )
            self.assertEqual(len(offsets), 2)
            self.assertEqual(offsets[0], (0.0, 0.0, 0.0))

    def test_birey_ayrildiktan_sonra_N4(self):
        """5 -> 4 drone gecisi: kalan ranker'ler tutarli dizilir.

        Bu test, sartnamenin birey ayrilma gorevi sirasinda kalan
        sürünün formasyonu koruyabildigini dogrular.
        """
        # 5 drone V formasyonu
        full = compute_slot_offsets(
            FORMATION_V, 5, 5.0, math.radians(30)
        )
        # Drone ayrilinca 4 drone
        reduced = compute_slot_offsets(
            FORMATION_V, 4, 5.0, math.radians(30)
        )
        # Her ikisinde de rank 0 lider merkezde
        self.assertEqual(full[0], (0.0, 0.0, 0.0))
        self.assertEqual(reduced[0], (0.0, 0.0, 0.0))
        # Rank 1-3 ayni pozisyonda kalir (ilk 4 slot)
        for i in range(4):
            self.assertEqual(full[i], reduced[i])

    def test_buyuk_N_lider_merkez(self):
        """N=10 ve 20 icin rank 0 daima merkez (jenerik test)."""
        for n in (10, 15, 20):
            for ftype in (FORMATION_OKBASI, FORMATION_V, FORMATION_CIZGI):
                offsets = compute_slot_offsets(
                    ftype, n, 5.0, math.radians(30)
                )
                self.assertEqual(len(offsets), n)
                self.assertEqual(offsets[0], (0.0, 0.0, 0.0))

    def test_v_okbasi_x_aynasi(self):
        """V, Ok Basi'nin X ekseni aynasidir.

        Ayni parametrelerde dx isareti tersi, dy/dz ayni olmali.
        """
        okbasi = compute_slot_offsets(
            FORMATION_OKBASI, 5, 5.0, math.radians(30)
        )
        v = compute_slot_offsets(
            FORMATION_V, 5, 5.0, math.radians(30)
        )
        for o, w in zip(okbasi, v):
            self.assertAlmostEqual(o[0], -w[0])
            self.assertAlmostEqual(o[1], w[1])
            self.assertAlmostEqual(o[2], w[2])


class TestMinDroneDistance(unittest.TestCase):
    """compute_min_drone_distance ve guvenlik dogrulamasi testleri."""

    def test_cizgi_spacing_dogru(self):
        """Cizgi'de min mesafe = spacing."""
        d = compute_min_drone_distance(FORMATION_CIZGI, 5.0, 0.0)
        self.assertAlmostEqual(d, 5.0)

    def test_okbasi_alpha_30_spacing_dogru(self):
        """Ok Basi alpha=30, spacing=5: min mesafe = 5m.

        Lider-kanat veya sag-sol = 2*5*0.5 = 5.
        """
        d = compute_min_drone_distance(
            FORMATION_OKBASI, 5.0, math.radians(30)
        )
        self.assertAlmostEqual(d, 5.0, places=5)

    def test_okbasi_dusuk_alpha_dar(self):
        """Ok Basi alpha=10: sag-sol kanat dar olur.

        2*5*sin(10) = 1.74m < spacing 5m.
        """
        d = compute_min_drone_distance(
            FORMATION_OKBASI, 5.0, math.radians(10)
        )
        self.assertLess(d, 5.0)
        self.assertAlmostEqual(d, 2 * 5.0 * math.sin(math.radians(10)))

    def test_v_ile_okbasi_ayni_mesafe(self):
        """V ve Ok Basi simetrik oldugu icin min mesafeleri ayni."""
        d_okbasi = compute_min_drone_distance(
            FORMATION_OKBASI, 5.0, math.radians(30)
        )
        d_v = compute_min_drone_distance(
            FORMATION_V, 5.0, math.radians(30)
        )
        self.assertAlmostEqual(d_okbasi, d_v)

    def test_validate_guvensiz_konfigurasyon(self):
        """spacing=1, alpha=10°: 2*1*sin(10°)=0.35m < 1.5m -> hata."""
        with self.assertRaises(ValueError):
            validate_formation_safety(
                FORMATION_OKBASI, 1.0, math.radians(10)
            )

    def test_validate_guvenli_konfigurasyon(self):
        """spacing=5, alpha=30°: 5m >> 1.5m -> hata yok."""
        validate_formation_safety(
            FORMATION_OKBASI, 5.0, math.radians(30)
        )

    def test_validate_ozel_esik(self):
        """Ozel min_distance_m esigi ile dogrulama."""
        # spacing=3, alpha=30° -> min=3m, esik=2m geçer
        validate_formation_safety(
            FORMATION_OKBASI, 3.0, math.radians(30), min_distance_m=2.0
        )
        # Ayni konfigurasyon esik=4m'de hata verir
        with self.assertRaises(ValueError):
            validate_formation_safety(
                FORMATION_OKBASI, 3.0, math.radians(30),
                min_distance_m=4.0,
            )


class TestRotateOffset(unittest.TestCase):
    """rotate_offset fonksiyonunu dogrular."""

    def test_sifir_donme(self):
        """heading=0'da offset degismez."""
        rx, ry = rotate_offset(3.0, 4.0, 0.0)
        self.assertAlmostEqual(rx, 3.0)
        self.assertAlmostEqual(ry, 4.0)

    def test_doksan_derece(self):
        """heading=90 icin (1,0) -> (0,1)."""
        rx, ry = rotate_offset(1.0, 0.0, math.radians(90))
        self.assertAlmostEqual(rx, 0.0, places=5)
        self.assertAlmostEqual(ry, 1.0, places=5)

    def test_yuz_seksen_derece(self):
        """heading=180 icin offset isaret degisir."""
        rx, ry = rotate_offset(2.0, 3.0, math.radians(180))
        self.assertAlmostEqual(rx, -2.0, places=5)
        self.assertAlmostEqual(ry, -3.0, places=5)


class TestComputeSetpoint(unittest.TestCase):
    """compute_setpoint entegre testleri."""

    def test_lider_merkez_uzerinde(self):
        """rank=0 daima formasyon merkezinde."""
        x, y, z = compute_setpoint(
            center_x=10.0, center_y=20.0, center_z=-15.0,
            formation_type=FORMATION_OKBASI,
            rank=0, total=3, spacing=5.0,
            alpha_rad=math.radians(30),
            heading_rad=0.0,
        )
        self.assertAlmostEqual(x, 10.0)
        self.assertAlmostEqual(y, 20.0)
        self.assertAlmostEqual(z, -15.0)

    def test_z_merkez_z_si(self):
        """Cikis z'si daima merkez z'sine esit (3B yok)."""
        _, _, z = compute_setpoint(
            center_x=0.0, center_y=0.0, center_z=-20.0,
            formation_type=FORMATION_V,
            rank=1, total=3, spacing=5.0,
            alpha_rad=math.radians(30),
            heading_rad=math.radians(45),
        )
        self.assertAlmostEqual(z, -20.0)

    def test_rank_arali_disinda(self):
        """rank >= total icin ValueError."""
        with self.assertRaises(ValueError):
            compute_setpoint(
                center_x=0.0, center_y=0.0, center_z=0.0,
                formation_type=FORMATION_CIZGI,
                rank=5, total=3, spacing=5.0,
                alpha_rad=0.0, heading_rad=0.0,
            )

    def test_heading_donmesi(self):
        """Heading=90 icin Ok Basi rank=1 offseti dogrulamasi.

        NED'de beklenen yerde olmasi.
        """
        # Body frame'de rank 1: (-4.33, +2.50). heading=90 donmesi:
        # rx = -4.33*cos(90) - 2.50*sin(90) = 0 - 2.50 = -2.50
        # ry = -4.33*sin(90) + 2.50*cos(90) = -4.33 + 0 = -4.33
        x, y, z = compute_setpoint(
            center_x=0.0, center_y=0.0, center_z=0.0,
            formation_type=FORMATION_OKBASI,
            rank=1, total=3, spacing=5.0,
            alpha_rad=math.radians(30),
            heading_rad=math.radians(90),
        )
        self.assertAlmostEqual(x, -2.50, places=2)
        self.assertAlmostEqual(y, -4.33, places=2)


if __name__ == '__main__':
    unittest.main()
