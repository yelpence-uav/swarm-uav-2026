# Copyright 2026 Yelpence

"""test_zone_map_core.py - ZoneMapCore projeksiyon ve kümeleme testleri."""

import math

from swarm_perception.vision_node.zone_map_core import (
    COLOR_BLUE,
    COLOR_RED,
    COLOR_UNKNOWN,
    ZoneMapCore,
    zone_offset_ned_m,
)

# Test kamerası: 640x360, görüntü merkezi ortada, fx=fy=400 px.
_FX = 400.0
_FY = 400.0
_CX = 320.0
_CY = 180.0


def test_merkez_tespit_dronun_tam_altina_duser():
    """Görüntü merkezindeki bölge sıfır ofsete düşer (dronun altı)."""
    dx, dy = zone_offset_ned_m(
        _CX, _CY, _FX, _FY, _CX, _CY, height_m=15.0, heading_deg=0.0
    )
    assert math.isclose(dx, 0.0, abs_tol=1e-9)
    assert math.isclose(dy, 0.0, abs_tol=1e-9)


def test_goruntunun_ALTI_gerideki_bolgedir():
    """Görüntüde AŞAĞI = gövdede GERİ."""
    height = 10.0
    v_alt = _CY + 100.0  # merkezin 100 px ALTINDA
    dx, dy = zone_offset_ned_m(
        _CX, v_alt, _FX, _FY, _CX, _CY, height, heading_deg=0.0
    )
    assert dx < 0.0, 'goruntunun alti GERIDE olmali (negatif ileri)'
    assert math.isclose(dx, -height * 100.0 / _FY, rel_tol=1e-9)
    assert math.isclose(dy, 0.0, abs_tol=1e-9)


def test_olcek_odak_uzakligindan_gelir():
    """Ofset, sabit bir görüş açısından değil fx/fy'den ölçeklenir."""
    height = 20.0
    u_sag = _CX + 80.0
    dx, dy = zone_offset_ned_m(
        u_sag, _CY, _FX, _FY, _CX, _CY, height, heading_deg=0.0
    )
    # Pinhole: ofset = irtifa * piksel_sapma / fx
    assert math.isclose(dy, height * 80.0 / _FX, rel_tol=1e-9)
    assert math.isclose(dx, 0.0, abs_tol=1e-9)


def test_dar_ve_genis_kamera_farkli_olcek_verir():
    """Odak uzaklığı büyüyünce (dar açı) aynı piksel sapması daha az metre."""
    args = (_CX + 100.0, _CY, )
    dar = zone_offset_ned_m(*args, 800.0, 800.0, _CX, _CY, 10.0, 0.0)[1]
    genis = zone_offset_ned_m(*args, 400.0, 400.0, _CX, _CY, 10.0, 0.0)[1]
    assert dar < genis
    assert math.isclose(genis / dar, 2.0, rel_tol=1e-9)


def test_heading_donusu_uygulanir():
    """heading=90° iken gövde ileri yönü NED +y'ye (doğuya) döner."""
    height = 10.0
    v_ust = _CY - 100.0  # merkezin ÜSTÜ = ileri
    dx, dy = zone_offset_ned_m(
        _CX, v_ust, _FX, _FY, _CX, _CY, height, heading_deg=90.0
    )
    beklenen = height * 100.0 / _FY
    assert math.isclose(dx, 0.0, abs_tol=1e-6)
    assert math.isclose(dy, beklenen, rel_tol=1e-6)


def test_yeni_bolge_eklenir():
    """İlk gözlem yeni kayıt açar."""
    zm = ZoneMapCore()
    zm.add(COLOR_RED, 1.0, 2.0)
    assert zm.zone_count() == 1


def test_yakin_ayni_renk_birlesir():
    """merge_dist içinde aynı renk yeni kayıt açmaz, kümelenir."""
    zm = ZoneMapCore(merge_dist_m=2.0)
    zm.add(COLOR_RED, 0.0, 0.0)
    zm.add(COLOR_RED, 1.0, 0.0)  # 1 m uzakta -> birleşir
    assert zm.zone_count() == 1
    z = zm.zones[0]
    assert z['count'] == 2.0
    # Konum koşan ortalama: (0 + 1) / 2 = 0.5
    assert math.isclose(z['x'], 0.5, abs_tol=1e-6)


def test_uzak_ayni_renk_ayri_kayit():
    """merge_dist dışındaki aynı renk ayrı kayıt açar."""
    zm = ZoneMapCore(merge_dist_m=2.0)
    zm.add(COLOR_RED, 0.0, 0.0)
    zm.add(COLOR_RED, 5.0, 0.0)
    assert zm.zone_count() == 2


def test_farkli_renk_birlesmez():
    """Aynı konumda farklı renk asla birleşmez."""
    zm = ZoneMapCore(merge_dist_m=2.0)
    zm.add(COLOR_RED, 0.0, 0.0)
    zm.add(COLOR_BLUE, 0.0, 0.0)
    assert zm.zone_count() == 2


def test_bilinmeyen_renk_yoksayilir():
    """COLOR_UNKNOWN haritaya yazılmaz."""
    zm = ZoneMapCore()
    zm.add(COLOR_UNKNOWN, 0.0, 0.0)
    assert zm.zone_count() == 0


def test_nearest_dogru_rengi_secer():
    """nearest, istenen renkten en yakın bölgeyi döndürür."""
    zm = ZoneMapCore(merge_dist_m=1.0)
    zm.add(COLOR_RED, 10.0, 0.0)
    zm.add(COLOR_BLUE, 1.0, 0.0)
    zm.add(COLOR_RED, 3.0, 0.0)
    nearest_red = zm.nearest(COLOR_RED, 0.0, 0.0)
    assert nearest_red is not None
    assert math.isclose(nearest_red['x'], 3.0, abs_tol=1e-6)


def test_nearest_renk_yoksa_none():
    """İstenen renk haritada yoksa None döner."""
    zm = ZoneMapCore()
    zm.add(COLOR_RED, 0.0, 0.0)
    assert zm.nearest(COLOR_BLUE, 0.0, 0.0) is None
