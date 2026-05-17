#!/usr/bin/env python3
"""
ESP-NOW Radyo Frekansı (RF) Fizik ve Gecikme Modeli
Bu modül ROS 2'den tamamen bağımsızdır ve saf matematiksel hesaplamalar yapar.
"""

import math
import random
from typing import Tuple


class ESPNowRFModel:
    def __init__(self):
        # --- Menzil ve Paket Kaybı Parametreleri ---
        self.perfect_range = 60.0  # 0-60m: %0 - %1 kayıp
        self.good_range = 95.0  # 60-95m: %1 - %5 kayıp
        self.critical_range = 110.0  # 95-110m: %5 - %25 eksponansiyel kayıp
        # 110m+: %100 kayıp (Kopma)

        # --- Gecikme (Latency / Jitter) Parametreleri ---
        self.min_latency_s = 0.005  # 5 ms
        self.max_latency_s = 0.050  # 50 ms

    def calculate_distance(
        self, pos1: Tuple[float, float, float], pos2: Tuple[float, float, float]
    ) -> float:
        """İki 3D koordinat arasındaki Öklid (Euclidean) mesafesini hesaplar."""
        return math.sqrt(
            (pos1[0] - pos2[0]) ** 2
            + (pos1[1] - pos2[1]) ** 2
            + (pos1[2] - pos2[2]) ** 2
        )

    def _get_drop_probability(self, distance: float) -> float:
        """Mesafeye göre paketin düşme İHTİMALİNİ (0.0 ile 1.0 arası) döndürür."""
        if distance <= self.perfect_range:
            # 0-60m arası: %0'dan %1'e doğrusal artış
            return (distance / self.perfect_range) * 0.01

        elif distance <= self.good_range:
            # 60-95m arası: %1'den %5'e doğrusal artış
            ratio = (distance - self.perfect_range) / (
                self.good_range - self.perfect_range
            )
            return 0.01 + (ratio * 0.04)

        elif distance <= self.critical_range:
            # 95-110m arası: %5'ten %25'e EKSPONANSİYEL (katlanarak) artış
            # Radyo sinyallerinin Ters Kare Kanunu'nu simüle eder.
            ratio = (distance - self.good_range) / (
                self.critical_range - self.good_range
            )
            # 0.05 * (5 ^ ratio) -> ratio 0 iken 0.05 (%5), ratio 1 iken 0.25 (%25) olur.
            return 0.05 * (math.pow(5, ratio))

        else:
            # 110m'den uzak: Kesin kopma
            return 1.0

    def should_drop_packet(self, distance: float) -> bool:
        """
        Gelen mesafeye göre sanal bir zar atar.
        Eğer paket düşecekse True, iletilecekse False döndürür.
        """
        probability = self._get_drop_probability(distance)
        roll = random.uniform(0.0, 1.0)
        return roll < probability

    def get_jitter(self) -> float:
        """Her paket için işletim sistemi ve donanım işleme gecikmesini (saniye cinsinden) üretir."""
        return random.uniform(self.min_latency_s, self.max_latency_s)


# --- DOĞRUDAN TEST BLOĞU (ROS 2 Olmadan Çalıştırılabilir) ---
if __name__ == "__main__":
    print("ESP-NOW RF Modeli Test Ediliyor...\n")
    rf = ESPNowRFModel()

    test_distances = [10, 50, 60, 80, 95, 100, 105, 110, 115]

    for dist in test_distances:
        prob = rf._get_drop_probability(dist)

        # O mesafede 1000 paket gönderip kaçının düştüğünü test edelim
        dropped_count = sum(1 for _ in range(1000) if rf.should_drop_packet(dist))

        print(
            f"Mesafe: {dist}m | Teorik Kayıp İhtimali: %{prob*100:.2f} | 1000 Pakette Düşen: {dropped_count}"
        )

    print(f"\nÖrnek Gecikme (Jitter): {rf.get_jitter()*1000:.2f} ms")
