# Copyright 2026 Yelpence
"""Renkli inis/ayrilma bolgelerinin global haritasi."""

import math
from typing import Dict, List, Optional, Tuple

COLOR_UNKNOWN = 0
COLOR_RED = 1
COLOR_BLUE = 2


def zone_offset_ned_m(
    u_px: float,
    v_px: float,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
    height_m: float,
    heading_deg: float,
) -> Tuple[float, float]:
    """Görüntüdeki bölge merkezinin drona göre NED ofseti (metre)."""
    right_m = height_m * (u_px - cx) / fx
    fwd_m = -height_m * (v_px - cy) / fy

    hd = math.radians(heading_deg)
    ned_x = fwd_m * math.cos(hd) - right_m * math.sin(hd)
    ned_y = fwd_m * math.sin(hd) + right_m * math.cos(hd)
    return ned_x, ned_y


class ZoneMapCore:
    """Renkli bolgeleri global NED'de biriktiren hafiza ve projeksiyon."""

    def __init__(
        self,
        merge_dist_m: float = 2.0,
        min_height_m: float = 0.5,
        confidence_obs_full: int = 5,
    ) -> None:
        """Bolge haritasini ilklendirir."""
        self._merge_dist_m = float(merge_dist_m)
        self._min_height_m = float(min_height_m)
        self._obs_full = max(1, int(confidence_obs_full))
        self._zones: List[Dict[str, float]] = []

    def project(
        self,
        image_x: float,
        image_y: float,
        fov_deg: float,
        pose: Tuple[float, float, float, float],
    ) -> Tuple[float, float, float]:
        """Goruntudeki bolge merkezini global NED konumuna projekte eder."""
        px, py, pz, heading_deg = pose
        fov = fov_deg if fov_deg > 1.0 else 60.0

        height = max(-pz, self._min_height_m)

        fwd_frac = image_y - 0.5
        right_frac = image_x - 0.5

        off_fwd = height * math.tan(math.radians(fwd_frac * fov))
        off_right = height * math.tan(math.radians(right_frac * fov))

        hd = math.radians(heading_deg)
        gx = px + off_fwd * math.cos(hd) - off_right * math.sin(hd)
        gy = py + off_fwd * math.sin(hd) + off_right * math.cos(hd)
        gz = pz + height
        return gx, gy, gz

    def add(
        self,
        color: int,
        gx: float,
        gy: float,
        gz: float = 0.0,
        detection_confidence: float = 1.0,
    ) -> None:
        """Gozlemi haritaya ekler veya birlestirir."""
        if color not in (COLOR_RED, COLOR_BLUE):
            return

        existing = self._find_existing(color, gx, gy)
        if existing is None:
            self._zones.append({
                'color': float(color),
                'x': float(gx),
                'y': float(gy),
                'z': float(gz),
                'count': 1.0,
                'confidence': float(_clamp01(detection_confidence)),
            })
            return

        n = existing['count']
        existing['x'] = (existing['x'] * n + gx) / (n + 1.0)
        existing['y'] = (existing['y'] * n + gy) / (n + 1.0)
        existing['z'] = (existing['z'] * n + gz) / (n + 1.0)
        existing['count'] = n + 1.0
        obs_conf = min(1.0, existing['count'] / self._obs_full)
        existing['confidence'] = _clamp01(
            max(obs_conf, detection_confidence)
        )

    def _find_existing(
        self, color: int, gx: float, gy: float
    ) -> Optional[Dict[str, float]]:
        """Mevcut kayitlar arasinda en yakini bulur."""
        best = None
        best_d = self._merge_dist_m
        for z in self._zones:
            if int(z['color']) != color:
                continue
            d = math.hypot(z['x'] - gx, z['y'] - gy)
            if d <= best_d:
                best_d = d
                best = z
        return best

    def nearest(
        self, color: int, x: float, y: float
    ) -> Optional[Dict[str, float]]:
        """Verilen konuma en yakin bolgeyi bulur."""
        best = None
        best_d = float('inf')
        for z in self._zones:
            if int(z['color']) != color:
                continue
            d = math.hypot(z['x'] - x, z['y'] - y)
            if d < best_d:
                best_d = d
                best = z
        return dict(best) if best is not None else None

    @property
    def zones(self) -> List[Dict[str, float]]:
        """Haritadaki bolgelerin kopyasini doner."""
        return [dict(z) for z in self._zones]

    def zone_count(self) -> int:
        """Benzersiz bolge sayisini doner."""
        return len(self._zones)


def _clamp01(value: float) -> float:
    """Değeri [0.0, 1.0] aralığına kırpar."""
    return max(0.0, min(1.0, float(value)))
