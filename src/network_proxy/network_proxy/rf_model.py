#!/usr/bin/env python3
"""ESP-NOW radyo fizik ve gecikme modeli.

Mesafeye bagli paket kaybi ve jitter uretir.
ROS2 bagimliligi yok, saf matematik.
"""

import math
import random
from typing import List, Optional, Tuple

_EARTH_R_M = 6_371_000.0


class ESPNowRFModel:
    """Mesafeye bagli kayip + jitter modeli."""

    def __init__(
        self, seed: Optional[int] = None
    ) -> None:
        # Kayip egrisi: (mesafe_m, kayip_olasiligi)
        self._curve: List[Tuple[float, float]] = [
            (0.0, 0.000),
            (50.0, 0.000),
            (150.0, 0.005),
            (300.0, 0.023),
            (450.0, 0.051),
        ]
        self.cutoff_m = 450.0

        self.min_latency_s = 0.005
        self.max_latency_s = 0.050

        self._rng = random.Random(seed)

    def haversine_m(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """Iki GPS noktasi arasi yatay mesafe (m)."""
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlmb = math.radians(lon2 - lon1)
        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1)
            * math.cos(phi2)
            * math.sin(dlmb / 2) ** 2
        )
        return 2.0 * _EARTH_R_M * math.asin(
            math.sqrt(a)
        )

    def distance_m(
        self,
        gps1: Tuple[float, float, float],
        gps2: Tuple[float, float, float],
    ) -> float:
        """3D mesafe: yatay (haversine) + dikey (irtifa).

        Args:
            gps1: (lat, lon, alt_m).
            gps2: (lat, lon, alt_m).

        Returns:
            float: 3D mesafe (m).
        """
        horiz = self.haversine_m(
            gps1[0], gps1[1], gps2[0], gps2[1]
        )
        dz = gps1[2] - gps2[2]
        return math.hypot(horiz, dz)

    def _get_drop_probability(
        self, distance: float
    ) -> float:
        """Parcali-dogrusal kayip olasiligi (0..1)."""
        if distance > self.cutoff_m:
            return 1.0
        for (d0, p0), (d1, p1) in zip(
            self._curve, self._curve[1:]
        ):
            if distance <= d1:
                if d1 == d0:
                    return p0
                t = (distance - d0) / (d1 - d0)
                return p0 + t * (p1 - p0)
        return self._curve[-1][1]

    def should_drop_packet(
        self, distance: float
    ) -> bool:
        """Mesafeye gore paket dusurulecek mi?"""
        return self._rng.random() < (
            self._get_drop_probability(distance)
        )

    def get_jitter(self) -> float:
        """Rastgele gecikme doner (5-50 ms)."""
        return self._rng.uniform(
            self.min_latency_s, self.max_latency_s
        )


if __name__ == "__main__":
    rf = ESPNowRFModel(seed=42)
    print("Kayip egrisi:")
    for d in (0, 50, 100, 150, 300, 450, 451, 500):
        p = rf._get_drop_probability(float(d))
        print(f"  {d:>4} m -> %{p * 100:.2f}")
    print(
        f"\nhaversine (0,0)->(0.001,0): "
        f"{rf.haversine_m(0, 0, 0.001, 0):.1f} m"
    )
    print(f"jitter: {rf.get_jitter() * 1000:.1f} ms")
