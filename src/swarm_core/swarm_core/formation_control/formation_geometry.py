# Copyright 2026 Yelpence
"""Formasyon geometrisi ve atama yardimcilari (saf Python)."""

from __future__ import annotations

import math

FORMATION_UNKNOWN = 0
FORMATION_OKBASI = 1
FORMATION_V = 2
FORMATION_CIZGI = 3
FORMATION_CUSTOM = 99

Offset = tuple[float, float, float]
DEFAULT_MIN_DRONE_DISTANCE_M = 1.5

_MIN_ALPHA_RAD = math.radians(5.0)
_MAX_ALPHA_RAD = math.radians(85.0)
_M_PER_DEG_LAT = 111_320.0


def compute_slot_offsets(
    formation_type: int,
    total: int,
    spacing: float,
    alpha_rad: float,
) -> list[Offset]:
    """N drone icin slot offsetlerini doner (heading=0)."""
    if total <= 0:
        raise ValueError(f'total >= 1 olmali: {total}')
    if spacing <= 0.0:
        raise ValueError(f'spacing > 0 olmali: {spacing}')

    if formation_type in (FORMATION_OKBASI, FORMATION_V):
        if alpha_rad < _MIN_ALPHA_RAD or alpha_rad > _MAX_ALPHA_RAD:
            raise ValueError(
                f'alpha {math.degrees(alpha_rad):.1f} aralik disi'
            )

    if formation_type == FORMATION_CIZGI:
        return _slots_cizgi(total, spacing)
    if formation_type == FORMATION_OKBASI:
        return _slots_okbasi(total, spacing, alpha_rad)
    if formation_type == FORMATION_V:
        return _slots_v(total, spacing, alpha_rad)

    raise ValueError(f'Desteklenmeyen formation_type: {formation_type}')


def compute_min_drone_distance(
    formation_type: int,
    spacing: float,
    alpha_rad: float,
) -> float:
    """Formasyondaki en yakin iki drone arasindaki mesafeyi doner."""
    if formation_type == FORMATION_CIZGI:
        return float(spacing)
    if formation_type in (FORMATION_OKBASI, FORMATION_V):
        wing_pair = 2.0 * spacing * math.sin(alpha_rad)
        return float(min(spacing, wing_pair))
    return float(spacing)


def validate_formation_safety(
    formation_type: int,
    spacing: float,
    alpha_rad: float,
    min_distance_m: float = DEFAULT_MIN_DRONE_DISTANCE_M,
) -> None:
    """Minimum drone mesafesini dogrular, guvensizse hata firlatir."""
    actual = compute_min_drone_distance(formation_type, spacing, alpha_rad)
    if actual < min_distance_m:
        raise ValueError(
            f'Guvensiz formasyon: en yakin drone arasi mesafe {actual:.2f}m'
        )


def _slots_cizgi(total: int, spacing: float) -> list[Offset]:
    """Cizgi formasyonu slotlarini uretir."""
    offsets: list[Offset] = [(0.0, 0.0, 0.0)]
    r = 1
    side = +1
    while len(offsets) < total:
        offsets.append((0.0, side * r * spacing, 0.0))
        if side == +1:
            side = -1
        else:
            side = +1
            r += 1
    return offsets


def _slots_okbasi(
    total: int,
    spacing: float,
    alpha_rad: float,
) -> list[Offset]:
    """Okbasi formasyonu slotlarini uretir."""
    offsets: list[Offset] = [(0.0, 0.0, 0.0)]
    r = 1
    side = +1
    while len(offsets) < total:
        dx = -r * spacing * math.cos(alpha_rad)
        dy = side * r * spacing * math.sin(alpha_rad)
        offsets.append((dx, dy, 0.0))
        if side == +1:
            side = -1
        else:
            side = +1
            r += 1
    return offsets


def _slots_v(
    total: int,
    spacing: float,
    alpha_rad: float,
) -> list[Offset]:
    """V formasyonu slotlarini uretir."""
    offsets: list[Offset] = [(0.0, 0.0, 0.0)]
    r = 1
    side = +1
    while len(offsets) < total:
        dx = +r * spacing * math.cos(alpha_rad)
        dy = side * r * spacing * math.sin(alpha_rad)
        offsets.append((dx, dy, 0.0))
        if side == +1:
            side = -1
        else:
            side = +1
            r += 1
    return offsets


def latlon_to_ned(
    lat_deg: float,
    lon_deg: float,
    ref_lat_deg: float,
    ref_lon_deg: float,
) -> tuple[float, float]:
    """GPS koordinatini referans noktasina gore NED metreye cevirir."""
    north = (lat_deg - ref_lat_deg) * _M_PER_DEG_LAT
    east = (
        (lon_deg - ref_lon_deg)
        * _M_PER_DEG_LAT
        * math.cos(math.radians(ref_lat_deg))
    )
    return north, east


def rotate_offset(
    dx: float,
    dy: float,
    heading_rad: float,
) -> tuple[float, float]:
    """Body frame offsetini heading acisi kadar dondurur (NED)."""
    cos_h = math.cos(heading_rad)
    sin_h = math.sin(heading_rad)
    return dx * cos_h - dy * sin_h, dx * sin_h + dy * cos_h


def compute_setpoint(
    center_x: float,
    center_y: float,
    center_z: float,
    formation_type: int,
    rank: int,
    total: int,
    spacing: float,
    alpha_rad: float,
    heading_rad: float,
) -> tuple[float, float, float]:
    """Tek drone'un formasyon setpoint'ini NED frame'de hesaplar."""
    if rank < 0 or rank >= total:
        raise ValueError(f'rank {rank} aralik disi (0..{total - 1})')

    offsets = compute_slot_offsets(formation_type, total, spacing, alpha_rad)
    dx, dy, dz = offsets[rank]
    rx, ry = rotate_offset(dx, dy, heading_rad)
    return center_x + rx, center_y + ry, center_z + dz


def hungarian_assignment(cost: list[list[float]]) -> list[int]:
    """O(N^3) Macar algoritmasi optimal atama."""
    n = len(cost)
    if n == 0:
        return []

    inf = float('inf')
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [inf] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = inf
            j1 = -1
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1

    assignment = [0] * n
    for j in range(1, n + 1):
        assignment[p[j] - 1] = j - 1
    return assignment
