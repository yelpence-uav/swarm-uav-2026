"""qr_geo birim testleri — QR numarası → NED çözümü."""

from swarm_missions.mission1_dynamic_swarm.qr_geo import QrGeoResolver


def test_not_ready_without_origin():
    """Origin gelmeden ready False ve çözüm None döner."""
    r = QrGeoResolver()
    r.set_table([1], [41.0], [29.0], [20.0])
    assert not r.ready
    assert r.resolve_ned(1) is None


def test_not_ready_without_table():
    """Tablo gelmeden ready False'tur."""
    r = QrGeoResolver()
    r.set_origin(41.0, 29.0)
    assert not r.ready


def test_resolves_origin_qr_to_zero():
    """Origin ile aynı konumdaki QR (0, 0, alt)'a çözülür."""
    r = QrGeoResolver()
    r.set_origin(41.0, 29.0)
    r.set_table([1, 4], [41.0, 41.001], [29.0, 29.0], [20.0, 25.0])
    assert r.ready
    assert r.has(4)
    north, east, alt = r.resolve_ned(1)
    assert abs(north) < 1e-6
    assert abs(east) < 1e-6
    assert alt == 20.0


def test_north_positive_for_higher_lat():
    """Origin'den kuzeydeki QR pozitif north verir."""
    r = QrGeoResolver()
    r.set_origin(41.0, 29.0)
    r.set_table([4], [41.001], [29.0], [25.0])
    north, east, alt = r.resolve_ned(4)
    assert north > 0.0
    assert abs(east) < 1e-3
    assert alt == 25.0


def test_unknown_qr_returns_none():
    """Tabloda olmayan QR numarası None döner."""
    r = QrGeoResolver()
    r.set_origin(41.0, 29.0)
    r.set_table([1], [41.0], [29.0], [20.0])
    assert r.resolve_ned(99) is None
