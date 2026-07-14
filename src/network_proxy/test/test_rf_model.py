"""test_rf_model.py — ESP-NOW RF modeli birim testleri (ROS'suz, saf matematik)."""

import math

from network_proxy.rf_model import ESPNowRFModel


def test_kayip_yakin_sifir():
    """Yakın mesafede (<=50 m) kayıp olasılığı ~0 (KTR §4.4.2)."""
    rf = ESPNowRFModel(seed=1)
    assert rf._get_drop_probability(0.0) == 0.0
    assert rf._get_drop_probability(50.0) == 0.0
    assert rf._get_drop_probability(30.0) == 0.0


def test_kayip_egrisi_monoton_artar():
    """Eğri mesafeyle artar; 150/450 m saha değerleriyle birebir."""
    rf = ESPNowRFModel(seed=1)
    p150 = rf._get_drop_probability(150.0)
    p300 = rf._get_drop_probability(300.0)
    p450 = rf._get_drop_probability(450.0)
    assert 0.0 < p150 < p300 < p450
    assert math.isclose(p150, 0.005, abs_tol=1e-6)
    assert math.isclose(p450, 0.051, abs_tol=1e-6)


def test_cutoff_tam_kopma():
    """cutoff_m (450 m) ötesi tam kopma (%100)."""
    rf = ESPNowRFModel(seed=1)
    assert rf._get_drop_probability(451.0) == 1.0
    assert rf._get_drop_probability(1000.0) == 1.0


def test_yakinda_asla_dusmez():
    """0 m'de should_drop hep False (prob 0)."""
    rf = ESPNowRFModel(seed=1)
    assert all(not rf.should_drop_packet(0.0) for _ in range(200))


def test_uzakta_hep_duser():
    """cutoff ötesinde should_drop hep True (prob 1)."""
    rf = ESPNowRFModel(seed=1)
    assert all(rf.should_drop_packet(1000.0) for _ in range(200))


def test_jitter_araligi():
    """Jitter 5–50 ms arasında kalır."""
    rf = ESPNowRFModel(seed=1)
    for _ in range(200):
        j = rf.get_jitter()
        assert 0.005 <= j <= 0.050


def test_seed_tekrarlanabilir():
    """Aynı seed → aynı jitter dizisi (deterministik koşu)."""
    a = ESPNowRFModel(seed=42)
    b = ESPNowRFModel(seed=42)
    assert [a.get_jitter() for _ in range(10)] == [b.get_jitter() for _ in range(10)]


def test_haversine_bilinen_deger():
    """0.001° enlem ≈ 111 m (referans)."""
    rf = ESPNowRFModel(seed=1)
    d = rf.haversine_m(0.0, 0.0, 0.001, 0.0)
    assert 110.0 < d < 112.0


def test_distance_3d_irtifa_farki():
    """Aynı yatay konum, 10 m irtifa farkı → 3D mesafe ~10 m."""
    rf = ESPNowRFModel(seed=1)
    d = rf.distance_m((41.0, 29.0, 100.0), (41.0, 29.0, 110.0))
    assert math.isclose(d, 10.0, abs_tol=0.5)
