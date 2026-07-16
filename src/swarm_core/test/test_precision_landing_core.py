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

"""test_precision_landing_core.py — hassas iniş durum makinesi testleri."""

from swarm_core.precision_landing.precision_landing_core import (
    COLOR_BLUE,
    COLOR_RED,
    PHASE_ABORT,
    PHASE_APPROACH,
    PHASE_DESCEND,
    PHASE_DONE,
    PHASE_TOUCHDOWN,
    PrecisionLandingCore,
)

# Örnek harita: kırmızı iki kayıt (biri çok görülmüş = gerçek), bir mavi.
_MAP = [
    {'color': COLOR_RED, 'x': 10.0, 'y': 0.0, 'count': 2.0},    # false pos
    {'color': COLOR_RED, 'x': 20.0, 'y': 5.0, 'count': 40.0},   # gerçek
    {'color': COLOR_BLUE, 'x': -5.0, 'y': 3.0, 'count': 30.0},
]


def _pose(x, y, alt, heading=0.0):
    """alt = AGL irtifa (m). NED z = -alt."""
    return (x, y, -alt, heading)


def test_inaktifken_yayin_yok():
    """active=False iken setpoint yayınlanmaz, state resetlenir."""
    core = PrecisionLandingCore()
    cmd = core.update(False, _pose(0, 0, 15), COLOR_RED, _MAP, None, 0.0)
    assert cmd.publish is False


def test_en_cok_gorulen_bolge_secilir():
    """SELECT en çok gözlemlenen kırmızıyı (false positive değil) seçer."""
    core = PrecisionLandingCore()
    cmd = core.update(True, _pose(0, 0, 15), COLOR_RED, _MAP, None, 0.0)
    assert cmd.phase == PHASE_APPROACH
    # Gerçek kırmızı (20, 5) seçilmeli, (10, 0) değil.
    assert abs(cmd.target_x - 20.0) < 1e-6
    assert abs(cmd.target_y - 5.0) < 1e-6


def test_yaklasma_hedefe_dogru_hiz_uretir():
    """APPROACH hedefe doğru, cap'li hız üretir."""
    core = PrecisionLandingCore(approach_speed_mps=1.5)
    cmd = core.update(True, _pose(0, 0, 15), COLOR_RED, _MAP, None, 0.0)
    assert cmd.velocity_valid is True
    speed = (cmd.vx ** 2 + cmd.vy ** 2) ** 0.5
    assert speed <= 1.5 + 1e-6
    # Hedef +x,+y yönünde olduğundan hız bileşenleri pozitif.
    assert cmd.vx > 0.0 and cmd.vy > 0.0


def test_hedef_renk_yoksa_iptal():
    """target_color UNKNOWN ise iniş iptal edilir (bekleme)."""
    core = PrecisionLandingCore()
    cmd = core.update(True, _pose(0, 0, 15), 0, _MAP, None, 0.0)
    assert cmd.phase == PHASE_ABORT
    assert cmd.disarm is False


def test_harita_bossa_iptal():
    """İstenen renk haritada yoksa iptal edilir."""
    core = PrecisionLandingCore()
    only_blue = [{'color': COLOR_BLUE, 'x': 1.0, 'y': 1.0, 'count': 5.0}]
    cmd = core.update(True, _pose(0, 0, 15), COLOR_RED, only_blue, None, 0.0)
    assert cmd.phase == PHASE_ABORT


def test_hedef_uzerinde_descend_e_gecer():
    """Hedefe yatay hizalanınca DESCEND'e geçer ve aşağı hız verir."""
    core = PrecisionLandingCore(xy_align_tol_m=0.5)
    # Hedefin tam üstünde başla (20, 5), 15 m irtifa.
    core.update(True, _pose(20.0, 5.0, 15.0), COLOR_RED, _MAP, None, 0.0)
    cmd = core.update(True, _pose(20.0, 5.0, 15.0), COLOR_RED, _MAP, None,
                      0.1)
    assert cmd.phase == PHASE_DESCEND
    assert cmd.vz > 0.0  # NED'de pozitif = aşağı


def test_touchdown_da_disarm():
    """Touchdown irtifasının altında disarm istenir."""
    core = PrecisionLandingCore(xy_align_tol_m=0.5, touchdown_alt_m=0.3)
    core.update(True, _pose(20.0, 5.0, 15.0), COLOR_RED, _MAP, None, 0.0)
    core.update(True, _pose(20.0, 5.0, 15.0), COLOR_RED, _MAP, None, 0.1)
    cmd = core.update(True, _pose(20.0, 5.0, 0.2), COLOR_RED, _MAP, None, 0.2)
    assert cmd.phase == PHASE_TOUCHDOWN
    assert cmd.disarm is True
    # Sonraki döngü DONE ve yayın yok.
    nxt = core.update(True, _pose(20.0, 5.0, 0.1), COLOR_RED, _MAP, None, 0.3)
    assert nxt.phase == PHASE_DONE
    assert nxt.publish is False


def test_zaman_asimi_iptal():
    """Hesaplanan süre bütçesi aşılınca güvenli bekleme (disarm yok)."""
    core = PrecisionLandingCore(
        landing_timeout_s=1.0, landing_time_margin_s=0.0
    )
    core.update(True, _pose(0, 0, 15), COLOR_RED, _MAP, None, 0.0)
    # Hedef bölge (20, 5) → 20.6 m yatay, 15 m irtifa.
    # Bütçe ≈ 20.6/1.5 + 15/0.4 ≈ 51 s; 60 s'te aşılmış olur.
    cmd = core.update(True, _pose(0, 0, 15), COLOR_RED, _MAP, None, 60.0)
    assert cmd.phase == PHASE_ABORT
    assert cmd.disarm is False
    assert cmd.velocity_valid is True


def test_uzak_bolgede_erken_iptal_yok():
    """Bütçe geometriden türetilir: uzak pede iniş sabit sınırla kesilmez.

    Sabit bir süre sınırı (eskiden 45 s) ayrılma noktası pede uzak düştüğünde
    inişi tam alçalma sırasında iptal ediyordu: dron pedin üstünde havada
    kalıyor, ardından failsafe devralıp rastgele bir yere indiriyordu.
    """
    core = PrecisionLandingCore()
    core.update(True, _pose(0, 0, 15), COLOR_RED, _MAP, None, 0.0)
    cmd = core.update(True, _pose(0, 0, 15), COLOR_RED, _MAP, None, 50.0)
    assert cmd.phase != PHASE_ABORT


def test_canli_kamera_merkezde_hedef_dron_altinda():
    """Kamera merkezinde bölge → projekte hedef dronun altına düşer."""
    core = PrecisionLandingCore()
    core.update(True, _pose(0, 0, 15), COLOR_RED, _MAP, None, 0.0)
    live = {'valid': True, 'color': COLOR_RED, 'frac_fwd': 0.0,
            'frac_right': 0.0, 'fov_deg': 60.0}
    cmd = core.update(True, _pose(3.0, 4.0, 15.0), COLOR_RED, _MAP, live, 0.1)
    assert cmd.in_view is True
    # Merkez tespit → hedef ~dron konumu → çok küçük hız.
    speed = (cmd.vx ** 2 + cmd.vy ** 2) ** 0.5
    assert speed < 0.1
