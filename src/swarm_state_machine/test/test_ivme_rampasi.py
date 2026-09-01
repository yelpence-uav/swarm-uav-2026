# Copyright 2026 Yelpence
"""B6 — HAREKET modunda ivme rampasi. 31 Agustos 2026'da baglandi.

ONCEDEN RAMPA YOKTU: `compute_centroid_delta` cubugu ANINDA hiza
ceviriyordu, yani tam basildiginda komut bir tick'te 0 -> 2 m/s.
Sartname osilasyonu -10 ile cezalandiriyor ve cok rotorlu ucak o
basamagi ancak sertce egilerek takip edebilir.

Ivme sinirli surum (`manual_kinematics.swarm_movement_step`) YAZILMIS ve
TEST EDILMISTI ama HICBIR YERDEN CAGRILMIYORDU.

🔴 O FONKSIYON OLDUGU GIBI KULLANILAMADI — heading ile DONDURMUYOR,
pitch'i dogrudan KUZEY sayiyor. mode_manager govde cercevesinde calisiyor
(cubuk ileri = surunun BAKTIGI yon). Korlemesine degistirmek "ileri"nin
anlamini kuzeye cevirirdi: sessiz ve tehlikeli bir davranis degisikligi.
Bu yuzden ivme siniri MEVCUT yola eklendi, `slew` tek kaynaktan alindi.
Asagidaki testler ikisini birden kilitliyor.
"""

import math
import unittest

from swarm_state_machine.mode_manager.mode_context import ModeContext


def _ctx(**kw):
    c = ModeContext(agent_ids=[1, 2, 3])
    c.max_speed_mps = 2.0
    c.max_accel_mps2 = 1.3
    c.max_accel_z_mps2 = 1.0
    for k, v in kw.items():
        setattr(c, k, v)
    return c


class TestRampaVar(unittest.TestCase):
    """Tek tick'te tam hiza SICRAMAMALI."""

    def test_ilk_tick_ivmeyle_sinirli(self):
        c = _ctx()
        dt = 0.05
        c.compute_centroid_delta(1.0, 0.0, 0.0, dt)
        # Bir tick'te en fazla a*dt = 1.3*0.05 = 0.065 m/s
        self.assertAlmostEqual(c.v_ileri, 1.3 * dt, places=6)
        self.assertLess(c.v_ileri, 0.1,
                        'tek tick ile tam hiza siciradi — rampa yok')

    def test_tam_hiza_ulasma_suresi(self):
        """2.0 m/s'e 1.3 m/s2 ile ~1.54 sn'de ulasilmali."""
        c = _ctx()
        dt, t = 0.02, 0.0
        while c.v_ileri < 2.0 - 1e-6 and t < 5.0:
            c.compute_centroid_delta(1.0, 0.0, 0.0, dt)
            t += dt
        self.assertAlmostEqual(t, 2.0 / 1.3, delta=0.05)

    def test_cubuk_birakilinca_YAVASLAR(self):
        """MOVEMENT'tan cikmadan durus: cubuk merkeze donunce rampa iner.

        MOVEMENT -> HOLD yalniz SwA birakilinca oluyor
        (mode_transitions._from_movement), yani cubuk merkeze donunce
        MOVEMENT'ta KALINIYOR ve yavaslamayi rampa yapiyor.
        """
        c = _ctx()
        dt = 0.02
        for _ in range(200):
            c.compute_centroid_delta(1.0, 0.0, 0.0, dt)
        self.assertAlmostEqual(c.v_ileri, 2.0, places=3)
        t = 0.0
        while c.v_ileri > 1e-6 and t < 5.0:
            c.compute_centroid_delta(0.0, 0.0, 0.0, dt)
            t += dt
        self.assertAlmostEqual(t, 2.0 / 1.3, delta=0.05)

    def test_dikey_AYRI_ivme(self):
        c = _ctx()
        dt = 0.05
        c.compute_centroid_delta(0.0, 0.0, 1.0, dt)
        self.assertAlmostEqual(c.v_yukari, 1.0 * dt, places=6)


class TestGovdeCercevesi(unittest.TestCase):
    """🔴 Rampa GOVDE cercevesini BOZMAMALI — en buyuk risk buydu."""

    def test_heading_0_ileri_KUZEY(self):
        c = _ctx(formation_heading_deg=0.0)
        c.v_ileri = 2.0          # rampayi doymus varsay
        dx, dy, _dz = c.compute_centroid_delta(1.0, 0.0, 0.0, 0.1)
        self.assertGreater(dx, 0.0)
        self.assertAlmostEqual(dy, 0.0, places=6)

    def test_heading_90_ileri_DOGU(self):
        """Heading 90 iken 'ileri' DOGU olmali — kuzey DEGIL."""
        c = _ctx(formation_heading_deg=90.0)
        c.v_ileri = 2.0
        dx, dy, _dz = c.compute_centroid_delta(1.0, 0.0, 0.0, 0.1)
        self.assertAlmostEqual(dx, 0.0, places=6)
        self.assertGreater(dy, 0.0)

    def test_roll_saga_heading_0(self):
        c = _ctx(formation_heading_deg=0.0)
        c.v_sag = 2.0
        dx, dy, _dz = c.compute_centroid_delta(0.0, 1.0, 0.0, 0.1)
        self.assertAlmostEqual(dx, 0.0, places=6)
        self.assertGreater(dy, 0.0, 'roll>0 saga (dogu) olmali')

    def test_gaz_yukari_NEGATIF_dz(self):
        """NED: yukari = z KUCULUR."""
        c = _ctx()
        c.v_yukari = 1.0
        _dx, _dy, dz = c.compute_centroid_delta(0.0, 0.0, 1.0, 0.1)
        self.assertLess(dz, 0.0)


class TestSifirlama(unittest.TestCase):
    """MOVEMENT disina cikarken hiz BAYATLAMAMALI."""

    def test_sifirlama_hizi_siler(self):
        c = _ctx()
        for _ in range(200):
            c.compute_centroid_delta(1.0, 1.0, 1.0, 0.02)
        self.assertGreater(c.v_ileri, 1.0)
        c.hiz_rampasini_sifirla()
        self.assertEqual((c.v_ileri, c.v_sag, c.v_yukari), (0.0, 0.0, 0.0))

    def test_ucus_defteri_sifirlamasi_rampayi_da_siler(self):
        """B19 donusu: ikinci denemede eski hizdan devam ETMEMELI."""
        c = _ctx()
        for _ in range(200):
            c.compute_centroid_delta(1.0, 0.0, 0.0, 0.02)
        c.ucus_durumunu_sifirla()
        self.assertEqual(c.v_ileri, 0.0,
                         'ucus defteri sifirlanirken rampa kaldi — '
                         'ikinci kalkista suru SICRAR')


class TestSinirlar(unittest.TestCase):

    def test_hiz_tavani_asilmaz(self):
        c = _ctx()
        for _ in range(500):
            c.compute_centroid_delta(1.0, 1.0, 0.0, 0.02)
        self.assertLessEqual(c.v_ileri, 2.0 + 1e-6)
        self.assertLessEqual(c.v_sag, 2.0 + 1e-6)

    def test_negatif_dt_cokturmez(self):
        c = _ctx()
        c.compute_centroid_delta(1.0, 0.0, 0.0, -1.0)
        self.assertEqual(c.v_ileri, 0.0)

    def test_ivme_egim_tavaniyla_TUTARLI(self):
        """a = g*tan(egim); pay kati 2 ile 15 deg -> en fazla 1.31 m/s2."""
        g, egim, pay = 9.81, 15.0, 2.0
        izin = g * math.tan(math.radians(egim)) / pay
        self.assertLessEqual(_ctx().max_accel_mps2, izin + 1e-6)


if __name__ == '__main__':
    unittest.main()
