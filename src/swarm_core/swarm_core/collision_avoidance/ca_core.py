# Copyright 2026 Yelpence
"""Hiz tabanli carpisma onleme cekirdegi."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class NeighborObs:
    """Tek komsunun CA girdisi."""

    rel_x: float
    rel_y: float
    rel_z: float
    rel_vx: float
    rel_vy: float
    rel_vz: float
    distance: float


@dataclass
class CaParams:
    """CA ayar kumesi."""

    d0: float = 4.5
    hard: float = 2.0
    r_min: float = 1.5
    f_sat: float = 6.0
    c_dead: float = 0.2
    c_ref: float = 1.0
    c_damp: float = 0.7
    damp_band: float = 0.5
    k_tan: float = 0.9
    v_max: float = 4.0
    xy_guard: float = 0.3
    slew_normal: float = 4.0
    slew_emergency: float = 30.0
    hyst_band: float = 0.2
    dt: float = 0.05


def _finite(*vals: float) -> bool:
    """Degerlerin sonlu olup olmadigini denetler."""
    for v in vals:
        if math.isnan(v) or math.isinf(v):
            return False
    return True


def _smoothstep(t: float) -> float:
    """Smoothstep adimini hesaplar."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def clamp_speed_xy(
    vx: float, vy: float, max_speed: float
) -> tuple[float, float]:
    """XY hizini max_speed degerine kirpar."""
    speed = math.sqrt(vx * vx + vy * vy)
    if speed > max_speed and speed > 1e-9:
        s = max_speed / speed
        return vx * s, vy * s
    return vx, vy


class CollisionAvoidanceCore:
    """Model B hiz tabanli carpisma onleme."""

    def __init__(self, params: CaParams | None = None) -> None:
        self.p = params or CaParams()
        self._prev_vx = 0.0
        self._prev_vy = 0.0
        self._emergency = False

    def compute(
        self,
        v_form: tuple[float, float, float],
        neighbors: list[NeighborObs],
    ) -> tuple[tuple[float, float, float], bool]:
        """CA algoritmasini calistirip yeni komut hizini doner."""
        p = self.p
        vfx, vfy, vfz = float(v_form[0]), float(v_form[1]), float(v_form[2])

        active: list[tuple[float, float, float, float, float]] = []
        min_d3 = float('inf')
        any_within_rmin = False

        for n in neighbors:
            if not _finite(n.rel_x, n.rel_y, n.rel_z,
                           n.rel_vx, n.rel_vy, n.rel_vz):
                continue
            away_x = -n.rel_x
            away_y = -n.rel_y
            d_xy = math.sqrt(away_x * away_x + away_y * away_y)
            d3 = math.sqrt(n.rel_x * n.rel_x + n.rel_y * n.rel_y
                           + n.rel_z * n.rel_z)

            if d_xy < p.xy_guard:
                continue
            if d3 >= p.d0:
                continue

            if d3 <= p.r_min:
                any_within_rmin = True
            if d3 < min_d3:
                min_d3 = d3

            ux = away_x / d_xy
            uy = away_y / d_xy

            c = -(n.rel_x * n.rel_vx + n.rel_y * n.rel_vy
                  + n.rel_z * n.rel_vz) / d3

            # KAPI — 22 Agustos 2026'da SUREKLI hale getirildi.
            #
            # ESKI HALI BASAMAKLIYDI:
            #     d3 <= hard  -> gate = 1.0            (tam kuvvet)
            #     d3 >  hard  -> gate = smoothstep(c)  (yavas yaklasmada ~0)
            # `hard` sinirini gecerken kapi ANINDA 0'dan 1'e atliyordu.
            # Ucak itilip disari cikiyor -> kapi kapaniyor -> itme sifir ->
            # geri yaklasiyor -> kapi aciliyor. Hedef hiz zipliyor, ucak
            # surekli hizlanip frenliyor.
            #
            # UCUSTA OLCULDU (ylp00, 22 Agustos): kacis evresinde roll
            # -24.7..+28.3 derece (53 derecelik yalpa), maks egim 34 derece.
            # Asili evrede yalniz 11.6 idi. Operator "devrilecek gibi sag sol
            # yapti" dedi ve haklıydi.
            #
            # YENI HALI: mesafe kapisi ile kapanma hizi kapisinin BUYUGU
            # aliniyor. Mesafe kapisi `hard + damp_band`ta 0, `hard`ta 1 —
            # yani kabuga yaklasirken kapi YUMUSAKCA aciliyor, basamak yok.
            # Icerideki tam kuvvet ve disarideki kapanma hizi mantigi AYNEN
            # korunuyor; yalniz aradaki sicrama gidiyor.
            if p.c_ref > 1e-6:
                gate_c = _smoothstep((c - p.c_dead) / p.c_ref)
            else:
                gate_c = 1.0
            # Rampa genisligi `damp_band`e (0.5 m) baglanmisti; cok dar
            # kaldi ve 0.2 m'de 3.2 m/s'lik sicrama uretti. Etki alaninin
            # DORTTE BIRI daha yumusak: d0=10 hard=6 icin 1.0 m.
            _band = max(0.25 * (p.d0 - p.hard), p.damp_band)
            if _band > 1e-6:
                gate_d = _smoothstep((p.hard + _band - d3) / _band)
            else:
                gate_d = 1.0 if d3 <= p.hard else 0.0
            gate = max(gate_c, gate_d)

            mag = self._repulsion_magnitude(d3) * gate
            dist_scale = (
                _smoothstep((p.d0 - d3) / (p.d0 - p.hard))
                if p.d0 > p.hard + 1e-6 else 1.0
            )
            # SONUMLEME TABANI — 22 Agustos 2026, olculdu ve duzeltildi.
            #
            # `c` kapanma hizi: yaklasirken +, UZAKLASIRKEN -. Tabansiz
            # birakilinca uzaklasan komsuda damp NEGATIF oluyor ve
            # `f_radial = mag + damp` isaret degistirip KOMSUYA DOGRU itiyor.
            #
            # OLCULDU (d0=10 hard=6): komsu 2 m/s uzaklasirken 6.5 m'de CA
            # 1.34 m/s KOMSUYA DOGRU komut veriyordu. Yani carpisma onleme
            # giden komsuyu KOVALIYORDU.
            #
            # Klasik yay-sonumleyicide negatif damp dogrudur (mesafeyi
            # KORUMAK icin), ama burasi mesafe koruma degil CARPISMA
            # ONLEME: uzaklasmanin bir zarari yok, geri cekmenin anlami yok.
            # Aralik korumasi formation_node'un isi.
            #
            # 21 Agustos ucusunda kayittaki ters yonlu kacis satirlari
            # (v=(-0.02,0.15), v=(-0.04,0.29)) bunun sahadaki izidir.
            damp = p.c_damp * max(0.0, c) * dist_scale
            tan_env = (
                _smoothstep((p.d0 - d3) / (0.5 * (p.d0 - p.hard)))
                if p.d0 > p.hard + 1e-6 else 1.0
            )
            mag_tan = p.f_sat * gate * tan_env
            if mag > 1e-9 or abs(damp) > 1e-9 or mag_tan > 1e-9:
                active.append((ux, uy, mag, damp, mag_tan))

        if not active and not any_within_rmin:
            self.reset((vfx, vfy, vfz))
            return (vfx, vfy, vfz), False

        vx, vy = vfx, vfy
        for ux, uy, mag, damp, mag_tan in active:
            f_radial = mag + damp
            vx += f_radial * ux
            vy += f_radial * uy
            tx, ty = self._tangent(vfx, vfy, ux, uy, mag_tan)
            vx += tx
            vy += ty

        vx, vy = clamp_speed_xy(vx, vy, p.v_max)
        vx, vy = self._safety_projection(vx, vy, neighbors)
        vx, vy = self._apply_slew(vx, vy, min_d3)

        if not _finite(vx, vy):
            vx, vy = self._prev_vx, self._prev_vy

        self._prev_vx, self._prev_vy = vx, vy
        return (vx, vy, vfz), True

    def reset(self, v_current: tuple[float, float, float]) -> None:
        """Slew baslangicini son okunan hiza esitler."""
        self._prev_vx = float(v_current[0])
        self._prev_vy = float(v_current[1])
        self._emergency = False

    def _repulsion_magnitude(self, d: float) -> float:
        """Etki alanindaki itme buyuklugunu hesaplar."""
        p = self.p
        if d >= p.d0:
            return 0.0
        if d <= p.hard:
            return p.f_sat
        t = (p.d0 - d) / (p.d0 - p.hard)
        return p.f_sat * _smoothstep(t)

    def _tangent(
        self, vfx: float, vfy: float, ux: float, uy: float, mag_rep: float,
    ) -> tuple[float, float]:
        """Kafa kafaya karsilasma durumunu cozen teget sapmasini doner."""
        vf_h = math.sqrt(vfx * vfx + vfy * vfy)
        if vf_h < 1e-3 or mag_rep < 1e-9:
            return 0.0, 0.0
        cos_a = (vfx * ux + vfy * uy) / vf_h
        w = max(0.0, -cos_a)
        if w < 1e-4:
            return 0.0, 0.0
        tx = uy
        ty = -ux
        f = self.p.k_tan * w * mag_rep
        return f * tx, f * ty

    def _safety_projection(
        self, vx: float, vy: float, neighbors: list[NeighborObs],
    ) -> tuple[float, float]:
        """Emniyet siniri altinda yaklasma hizini sifirlar."""
        p = self.p
        for n in neighbors:
            if not _finite(n.rel_x, n.rel_y, n.rel_z):
                continue
            d3 = math.sqrt(n.rel_x * n.rel_x + n.rel_y * n.rel_y
                           + n.rel_z * n.rel_z)
            if d3 > p.r_min:
                continue
            d_xy = math.sqrt(n.rel_x * n.rel_x + n.rel_y * n.rel_y)
            if d_xy < 1e-3:
                continue
            tx = n.rel_x / d_xy
            ty = n.rel_y / d_xy
            v_close = vx * tx + vy * ty
            if v_close > 0.0:
                vx -= v_close * tx
                vy -= v_close * ty
        return vx, vy

    def _apply_slew(
        self, vx: float, vy: float, min_d3: float,
    ) -> tuple[float, float]:
        """Hiz degisim ivmesini histerezis ile sinirlar."""
        p = self.p
        if not self._emergency and min_d3 < p.hard:
            self._emergency = True
        elif self._emergency and min_d3 > p.hard + p.hyst_band:
            self._emergency = False

        max_delta = (
            p.slew_emergency if self._emergency else p.slew_normal
        ) * p.dt
        dvx = vx - self._prev_vx
        dvy = vy - self._prev_vy
        d = math.sqrt(dvx * dvx + dvy * dvy)
        if d > max_delta and d > 1e-9:
            s = max_delta / d
            return self._prev_vx + dvx * s, self._prev_vy + dvy * s
        return vx, vy
