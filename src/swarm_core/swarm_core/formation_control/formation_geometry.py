"""Formasyon geometrisi — saf matematik, ROS yok.

Ok Başı, V, Çizgi formasyonları için slot offsetleri, Macar ataması,
shared NED dönüşümü. N'den bağımsız (jenerik).

Frame: +X = North, +Y = East, +Z = Down (NED).
Rank=0 daima merkez/lider. Kanatlar sağ-sol alternasyonla açılır.
"""

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


def compute_slot_offsets(
    formation_type: int,
    total: int,
    spacing: float,
    alpha_rad: float,
) -> list[Offset]:
    """N drone için heading=0 varsayımıyla slot offsetlerini döndürür.

    Returns:
        Uzunluğu total olan (dx, dy, dz) listesi. Index = rank.

    Raises:
        ValueError: Geçersiz parametreler veya desteklenmeyen tip.
    """
    if total <= 0:
        raise ValueError(f'total >= 1 olmali, geldi: {total}')
    if spacing <= 0.0:
        raise ValueError(f'spacing > 0 olmali, geldi: {spacing}')

    if formation_type in (FORMATION_OKBASI, FORMATION_V):
        if alpha_rad < _MIN_ALPHA_RAD or alpha_rad > _MAX_ALPHA_RAD:
            raise ValueError(
                f'alpha {math.degrees(alpha_rad):.1f}° araligin disinda '
                f'({math.degrees(_MIN_ALPHA_RAD):.0f}°-'
                f'{math.degrees(_MAX_ALPHA_RAD):.0f}°). '
                'Ok Basi/V kanat acisi bu sinirlar icinde olmali.'
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
    """Formasyondaki en yakın iki drone arasındaki mesafeyi döner."""
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
    """Minimum drone mesafesini doğrular; eşiğin altındaysa ValueError fırlatır."""
    actual = compute_min_drone_distance(formation_type, spacing, alpha_rad)
    if actual < min_distance_m:
        raise ValueError(
            f'Guvensiz formasyon: en yakin drone arasi mesafe '
            f'{actual:.2f}m, minimum {min_distance_m:.2f}m olmali. '
            f'spacing veya alpha artirilmali.'
        )


def _slots_cizgi(total: int, spacing: float) -> list[Offset]:
    """Çizgi: merkez (rank 0) + sağ-sol simetrik Y ekseninde dizilim."""
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
    """Ok Başı: merkez önde, kanatlar arka (−X) tarafa açılır."""
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
    """V: merkez geride, kanatlar ön (+X) tarafa açılır."""
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


# Düz-dünya yaklaşımı; sürü ölçeğinde (onlarca metre) hata ihmal edilebilir.
_M_PER_DEG_LAT = 111_320.0


def latlon_to_ned(
    lat_deg: float,
    lon_deg: float,
    ref_lat_deg: float,
    ref_lon_deg: float,
) -> tuple[float, float]:
    """GPS koordinatını referans noktasına göre NED metreye çevirir."""
    north = (lat_deg - ref_lat_deg) * _M_PER_DEG_LAT
    east = (
        (lon_deg - ref_lon_deg)
        * _M_PER_DEG_LAT
        * math.cos(math.radians(ref_lat_deg))
    )
    return north, east


def hungarian_assignment(cost: list[list[float]]) -> list[int]:
    """O(N³) Macar algoritması — kare maliyet matrisi için optimal atama.

    Saf Python, ek bağımlılık yok. RPi'de çalışır.
    Returns: assignment[i] = i. satıra atanan sütun indeksi.
    """
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


def rotate_offset(
    dx: float,
    dy: float,
    heading_rad: float,
) -> tuple[float, float]:
    """Body frame offsetini heading açısı kadar Z ekseninde döndürür (NED)."""
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
    """Tek drone'un formasyon setpoint'ini NED frame'de hesaplar.

    Raises:
        ValueError: rank aralık dışında veya parametreler geçersiz.
    """
    if rank < 0 or rank >= total:
        raise ValueError(f'rank {rank} aralik disi (0..{total - 1})')

    offsets = compute_slot_offsets(formation_type, total, spacing, alpha_rad)
    dx, dy, dz = offsets[rank]
    rx, ry = rotate_offset(dx, dy, heading_rad)
    return center_x + rx, center_y + ry, center_z + dz
