"""test_ca_core.py — Hız-tabanlı çarpışma önleme çekirdeği birim testleri."""

import math

import pytest

from swarm_core.collision_avoidance.ca_core import (
    CaParams,
    CollisionAvoidanceCore,
    NeighborObs,
    clamp_speed_xy,
)


def _obs(rel_x, rel_y, rel_vx=0.0, rel_vy=0.0, rel_z=0.0,
         rel_vz=0.0, distance=None):
    """NeighborObs kısayolu (distance verilmezse XY mesafesinden)."""
    if distance is None:
        distance = math.sqrt(rel_x * rel_x + rel_y * rel_y + rel_z * rel_z)
    return NeighborObs(rel_x, rel_y, rel_z, rel_vx, rel_vy, rel_vz, distance)


# Slew'i devre dışı bırakan gevşek paramlar (tek-tick davranışını izole et).
def _loose_params(**kw):
    base = dict(slew_normal=1e6, slew_emergency=1e6, dt=1.0)
    base.update(kw)
    return CaParams(**base)


# --------------------------------------------------------------------------- #
# 1. Risk yok → pass-through
# --------------------------------------------------------------------------- #
def test_no_neighbor_passthrough():
    core = CollisionAvoidanceCore(_loose_params())
    v_form = (1.0, 0.5, -0.2)
    v_cmd, risk = core.compute(v_form, [])
    assert risk is False
    assert v_cmd == pytest.approx(v_form)


def test_neighbor_outside_d0_passthrough():
    core = CollisionAvoidanceCore(_loose_params(d0=3.5))
    # 5 m uzakta komşu → d0 (3.5) dışında → CA uyur.
    v_cmd, risk = core.compute((1.0, 0.0, 0.0), [_obs(5.0, 0.0)])
    assert risk is False
    assert v_cmd == pytest.approx((1.0, 0.0, 0.0))


# --------------------------------------------------------------------------- #
# 2. Z pass-through + dikey ayrım
# --------------------------------------------------------------------------- #
def test_vertical_separation_no_repulsion():
    core = CollisionAvoidanceCore(_loose_params(d0=3.5))
    # Komşu yatayda 2.0 m (d0 içinde) AMA 5 m yukarıda → 3D mesafe ≈ 5.4 m > d0.
    # Dikey ayrım → çatışma yok → CA tepki vermemeli (risk False, ham hız geçer).
    v_form = (1.0, 0.0, 0.0)
    v_cmd, risk = core.compute(v_form, [_obs(2.0, 0.0, rel_z=5.0)])
    assert risk is False
    assert v_cmd == pytest.approx(v_form)


def test_z_always_passthrough():
    core = CollisionAvoidanceCore(_loose_params())
    # Yaklaşan komşu (itki tetiklenir) ama Z bileşeni dokunulmamalı.
    v_form = (0.0, 0.0, -1.3)
    v_cmd, risk = core.compute(v_form, [_obs(2.5, 0.0, rel_vx=-1.0)])
    assert risk is True
    assert v_cmd[2] == pytest.approx(-1.3)


# --------------------------------------------------------------------------- #
# 3. Yaklaşan komşu → itki komşudan uzağa
# --------------------------------------------------------------------------- #
def test_approaching_neighbor_pushes_away():
    core = CollisionAvoidanceCore(_loose_params())
    # Komşu +X'te, üstüme geliyor (rel_vx<0 → kapanıyor). Kaçış −X olmalı.
    v_cmd, risk = core.compute((1.0, 0.0, 0.0), [_obs(2.5, 0.0, rel_vx=-1.0)])
    assert risk is True
    # İtki −X yönünde → toplam X hızı formasyon hızından (1.0) düşük olmalı.
    assert v_cmd[0] < 1.0


# --------------------------------------------------------------------------- #
# 4. KAPI: uzaklaşan komşu → itki yok (anti-osilasyon)
# --------------------------------------------------------------------------- #
def test_receding_neighbor_no_repulsion():
    core = CollisionAvoidanceCore(_loose_params(hard=2.0))
    # Komşu +X'te 2.5 m (hard üstünde), UZAKLAŞIYOR (rel_vx>0 → kapanma<0).
    # Kapı kapalı + r_min dışı → müdahale yok → risk False, ham hız geçer.
    # (Bu, kapanma kapısının anti-osilasyon çekirdek davranışıdır.)
    v_form = (1.0, 0.0, 0.0)
    v_cmd, risk = core.compute(v_form, [_obs(2.5, 0.0, rel_vx=+1.5)])
    assert risk is False
    assert v_cmd == pytest.approx(v_form)


def test_stationary_neighbor_above_hard_no_push():
    core = CollisionAvoidanceCore(_loose_params(hard=2.0))
    # Komşu 2.5 m'de, göreli hız 0 → kapanma 0 → kapı kapalı (hard üstü).
    # r_min dışı → müdahale yok → risk False (formasyon serbest, salınım yok).
    v_cmd, risk = core.compute((0.0, 1.0, 0.0), [_obs(2.5, 0.0)])
    assert risk is False
    assert v_cmd == pytest.approx((0.0, 1.0, 0.0))


# --------------------------------------------------------------------------- #
# 5. Hard altında kapı zorla açık
# --------------------------------------------------------------------------- #
def test_inside_hard_pushes_even_without_closing():
    core = CollisionAvoidanceCore(_loose_params(hard=2.0, f_sat=6.0))
    # Komşu 1.8 m'de (hard altı), göreli hız 0 (yaklaşma yok). Kapı yine de
    # açık → güçlü itki (doygunluk). Kaçış −X.
    v_cmd, risk = core.compute((0.0, 0.0, 0.0), [_obs(1.8, 0.0)])
    assert risk is True
    assert v_cmd[0] < 0.0   # komşudan uzağa (−X) itiliyor


# --------------------------------------------------------------------------- #
# 6. r_min projeksiyonu → kapanma hızı garantili sıfırlanır
# --------------------------------------------------------------------------- #
def test_safety_projection_zeros_closing_velocity():
    core = CollisionAvoidanceCore(_loose_params(
        r_min=1.5, hard=2.0, f_sat=0.0))
    # f_sat=0 → hiç itki üretilmez. Formasyon hızı komşuya DOĞRU
    # (1.0,0) ve komşu 1.2 m'de (+X, r_min altı). Projeksiyon kapanma
    # bileşenini sıfırlamalı → X hızı 0.
    v_cmd, risk = core.compute((1.0, 0.0, 0.0), [_obs(1.2, 0.0)])
    assert risk is True
    assert v_cmd[0] == pytest.approx(0.0, abs=1e-6)


def test_safety_projection_keeps_separating_velocity():
    core = CollisionAvoidanceCore(_loose_params(
        r_min=1.5, hard=2.0, f_sat=0.0))
    # Komşu +X 1.2 m'de ama formasyon hızı −X (uzaklaşıyor) → projeksiyon
    # dokunmaz (zaten ayrışıyor).
    v_cmd, _ = core.compute((-1.0, 0.0, 0.0), [_obs(1.2, 0.0)])
    assert v_cmd[0] == pytest.approx(-1.0, abs=1e-6)


# --------------------------------------------------------------------------- #
# 7. Teğet → kafa-kafaya yanal bileşen
# --------------------------------------------------------------------------- #
def test_tangent_breaks_head_on():
    core = CollisionAvoidanceCore(_loose_params(k_tan=0.9))
    # Formasyon hızı +X (komşuya doğru), komşu tam önde +X 2.5 m, üstüme
    # geliyor. Saf itki −X (zıt) → deadlock. Teğet yanal (±Y) bileşen üretmeli.
    v_cmd, risk = core.compute((1.5, 0.0, 0.0), [_obs(2.5, 0.0, rel_vx=-1.0)])
    assert risk is True
    assert abs(v_cmd[1]) > 1e-3   # yanal kaçış var


# --------------------------------------------------------------------------- #
# 8. v_max clamp + slew
# --------------------------------------------------------------------------- #
def test_vmax_clamp():
    core = CollisionAvoidanceCore(_loose_params(v_max=2.0, f_sat=6.0))
    # Çok güçlü itki → XY büyüklük v_max'e kırpılmalı.
    v_cmd, _ = core.compute((3.0, 3.0, 0.0), [_obs(1.5, 0.0, rel_vx=-2.0)])
    xy = math.hypot(v_cmd[0], v_cmd[1])
    assert xy <= 2.0 + 1e-6


def test_slew_limits_step():
    # Slew sıkı: bir tick'te hız büyük sıçrayamaz.
    core = CollisionAvoidanceCore(CaParams(
        slew_normal=4.0, slew_emergency=4.0, dt=0.05, hard=2.0))
    core.reset((0.0, 0.0, 0.0))
    v_cmd, _ = core.compute((4.0, 0.0, 0.0), [_obs(2.5, 0.0, rel_vx=-1.0)])
    # max_delta = 4.0 * 0.05 = 0.2 m/s
    assert math.hypot(v_cmd[0], v_cmd[1]) <= 0.2 + 1e-6


# --------------------------------------------------------------------------- #
# Yardımcı: clamp_speed_xy
# --------------------------------------------------------------------------- #
def test_clamp_speed_xy():
    vx, vy = clamp_speed_xy(3.0, 4.0, 2.5)   # büyüklük 5 → 2.5
    assert math.hypot(vx, vy) == pytest.approx(2.5)
    vx, vy = clamp_speed_xy(1.0, 0.0, 2.5)   # zaten altında → değişmez
    assert (vx, vy) == pytest.approx((1.0, 0.0))


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
