"""qr_geo birim testleri — güncel hedef GPS → NED çözümü."""

from swarm_missions.mission1_dynamic_swarm.qr_geo import QrGeoResolver


def test_not_ready_without_origin():
    """Origin gelmeden ready False ve çözüm None döner."""
    r = QrGeoResolver()
    r.set_target(True, 41.0, 29.0)
    assert not r.ready
    assert r.resolve_ned() is None


def test_not_ready_without_target():
    """Hedef gelmeden ready False ve çözüm None döner."""
    r = QrGeoResolver()
    r.set_origin(41.0, 29.0)
    assert not r.ready
    assert r.resolve_ned() is None


def test_resolves_origin_target_to_zero():
    """Origin ile aynı konumdaki hedef (0, 0)'a çözülür."""
    r = QrGeoResolver()
    r.set_origin(41.0, 29.0)
    r.set_target(True, 41.0, 29.0)
    assert r.ready
    north, east = r.resolve_ned()
    assert abs(north) < 1e-6
    assert abs(east) < 1e-6


def test_north_positive_for_higher_lat():
    """Origin'den kuzeydeki hedef pozitif north verir."""
    r = QrGeoResolver()
    r.set_origin(41.0, 29.0)
    r.set_target(True, 41.001, 29.0)
    north, east = r.resolve_ned()
    assert north > 0.0
    assert abs(east) < 1e-3


def test_invalid_target_clears():
    """valid=False hedefi temizler → ready False, çözüm None."""
    r = QrGeoResolver()
    r.set_origin(41.0, 29.0)
    r.set_target(True, 41.0, 29.0)
    assert r.ready
    r.set_target(False, 0.0, 0.0)
    assert not r.ready
    assert r.resolve_ned() is None
