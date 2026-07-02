# Copyright 2026 Yelpence TEKNOFEST 2026
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""test_zone_map_core.py — ZoneMapCore projeksiyon ve kümeleme testleri."""

import math

from swarm_perception.vision_node.zone_map_core import (
    COLOR_BLUE,
    COLOR_RED,
    COLOR_UNKNOWN,
    ZoneMapCore,
)


def test_merkez_tespit_drone_konumuna_projekte_olur():
    """Görüntü merkezindeki bölge, dron konumunun tam altına düşer."""
    zm = ZoneMapCore()
    # Dron (10, 20)'de, 15 m yukarıda (NED z=-15), heading 0.
    gx, gy, gz = zm.project(0.5, 0.5, 60.0, (10.0, 20.0, -15.0, 0.0))
    assert math.isclose(gx, 10.0, abs_tol=1e-6)
    assert math.isclose(gy, 20.0, abs_tol=1e-6)
    assert math.isclose(gz, 0.0, abs_tol=1e-6)


def test_ileri_sapma_heading_sifirda_x_ekseninde():
    """heading=0 iken görüntü dikey sapması NED +x (ileri) yönüne gider."""
    zm = ZoneMapCore()
    height = 10.0
    # image_y > 0.5 -> ileri (fwd_frac > 0); image_x merkez.
    gx, gy, _ = zm.project(0.5, 0.75, 60.0, (0.0, 0.0, -height, 0.0))
    expected_fwd = height * math.tan(math.radians(0.25 * 60.0))
    assert math.isclose(gx, expected_fwd, rel_tol=1e-6)
    assert math.isclose(gy, 0.0, abs_tol=1e-6)


def test_heading_donusu_uygulanir():
    """heading=90° iken ileri ofset NED +y yönüne döner."""
    zm = ZoneMapCore()
    height = 10.0
    gx, gy, _ = zm.project(0.5, 0.75, 60.0, (0.0, 0.0, -height, 90.0))
    expected = height * math.tan(math.radians(0.25 * 60.0))
    assert math.isclose(gx, 0.0, abs_tol=1e-5)
    assert math.isclose(gy, expected, rel_tol=1e-5)


def test_min_irtifa_clamp():
    """Çok alçakta projeksiyon patlamaz, min irtifa kullanılır."""
    zm = ZoneMapCore(min_height_m=0.5)
    gx, gy, _ = zm.project(0.75, 0.5, 60.0, (0.0, 0.0, 0.0, 0.0))
    assert math.isfinite(gx) and math.isfinite(gy)


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
