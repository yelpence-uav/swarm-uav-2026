#!/usr/bin/env python3
"""ESP-NOW radyo (RF) fizik ve gecikme modeli.

ROS 2'den bağımsız, saf matematik:
  - mesafe: GPS/haversine (yatay) ⊕ irtifa farkı (dikey)
  - kayıp: mesafeye bağlı eğri (0–50 m ~%0 … >450 m kopma)
  - gecikme: 5–50 ms jitter
  - tekrarlanabilirlik: tohumlanabilir RNG (seed)
"""

import math
import random
from typing import List, Optional, Tuple

# WGS84 ortalama Dünya yarıçapı (haversine için)
_EARTH_R_M = 6_371_000.0


class ESPNowRFModel:
    """Mesafeye bağlı paket kaybı + jitter üreten saf model."""

    def __init__(self, seed: Optional[int] = None) -> None:
        # --- Mesafeye bağlı kayıp eğrisi — (mesafe_m, kayıp_olasılığı) ---
        # 0–50 m ~%0 · 50–150 m %0→%0.5 · 150–300 m %0.5→%2.3
        # 300–450 m %2.3→%5.1 · >450 m kopma
        self._curve: List[Tuple[float, float]] = [
            (0.0, 0.000),
            (50.0, 0.000),
            (150.0, 0.005),
            (300.0, 0.023),
            (450.0, 0.051),
        ]
        self.cutoff_m = 450.0  # bu mesafenin ötesi tam kopma sayılır

        # --- Gecikme (jitter) ---
        self.min_latency_s = 0.005  # 5 ms
        self.max_latency_s = 0.050  # 50 ms

        # Tohumlanabilir RNG — aynı seed = aynı kayıp/jitter dizisi
        self._rng = random.Random(seed)

    # ------------------------------------------------------------------
    # Mesafe (GPS/haversine)
    # ------------------------------------------------------------------
    def haversine_m(
        self, lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """İki GPS noktası arası yatay büyük-daire mesafesi (metre)."""
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlmb = math.radians(lon2 - lon1)
        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
        )
        return 2.0 * _EARTH_R_M * math.asin(math.sqrt(a))

    def distance_m(
        self,
        gps1: Tuple[float, float, float],
        gps2: Tuple[float, float, float],
    ) -> float:
        """3D mesafe: yatay (haversine) ⊕ dikey (irtifa farkı).

        gps = (lat_deg, lon_deg, alt_m)
        """
        horiz = self.haversine_m(gps1[0], gps1[1], gps2[0], gps2[1])
        dz = gps1[2] - gps2[2]
        return math.hypot(horiz, dz)

    # ------------------------------------------------------------------
    # Kayıp / jitter
    # ------------------------------------------------------------------
    def _get_drop_probability(self, distance: float) -> float:
        """Mesafeye karşılık kayıp olasılığı (0..1), parçalı-doğrusal eğri."""
        if distance > self.cutoff_m:
            return 1.0
        # Parçalı-doğrusal interpolasyon
        for (d0, p0), (d1, p1) in zip(self._curve, self._curve[1:]):
            if distance <= d1:
                if d1 == d0:
                    return p0
                t = (distance - d0) / (d1 - d0)
                return p0 + t * (p1 - p0)
        return self._curve[-1][1]

    def should_drop_packet(self, distance: float) -> bool:
        """Mesafeye göre zar at; paket düşecekse True, iletilecekse False."""
        return self._rng.random() < self._get_drop_probability(distance)

    def get_jitter(self) -> float:
        """Paket başına gecikme (saniye), 5–50 ms."""
        return self._rng.uniform(self.min_latency_s, self.max_latency_s)


# --- Hızlı manuel kontrol (ROS 2 olmadan) ---
if __name__ == "__main__":
    rf = ESPNowRFModel(seed=42)
    print("Kayıp eğrisi:")
    for d in (0, 50, 100, 150, 300, 450, 451, 500):
        print(f"  {d:>4} m -> %{rf._get_drop_probability(float(d)) * 100:.2f}")
    # 0.001 derece enlem ~ 111.32 m
    print(f"\nhaversine (0,0)->(0.001,0): {rf.haversine_m(0, 0, 0.001, 0):.1f} m")
    print(f"jitter örnek: {rf.get_jitter() * 1000:.1f} ms")
