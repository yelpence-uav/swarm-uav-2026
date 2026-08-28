# Copyright 2026 Yelpence
"""OpenCV kullanarak HSV uzayinda kirmizi/mavi bolgeleri bulur."""

from typing import Any, Dict, List, Tuple

import cv2

import numpy as np


def ensure_bgr(image: np.ndarray, encoding: str) -> np.ndarray:
    """Görüntüyü dedektörlerin beklediği BGR düzenine getirir."""
    if encoding == 'rgb8':
        return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    return image


class LandingZoneDetector:
    """Kirmizi/mavi inis bolgelerini HSV uzayinda tespit eder."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Aciklama: LandingZoneDetector sinifini ilklendirir."""
        self._config = config
        self._min_area = config.get('min_zone_area_px', 500.0)
        # ORANLI ESIK — 27 Agustos 2026.
        # `min_zone_area_px` MUTLAK pikseldir; onizleme cozunurlugu 640'tan
        # 1920'ye cikinca ayni fiziksel nesne 9 KAT daha buyuk goründügü icin
        # esik sessizce 9 kat gevser. Kareye oranli esik cozunurlukten
        # bagimsizdir. Etkin esik ikisinin BUYUGUDUR.
        self._min_area_frac = config.get('min_zone_area_frac', 0.0015)
        # DAIRESELLIK — onceden 0.4 olarak KODA GOMULUYDU ve parametre
        # degildi. 0.4 cok gevsek: bir KARE bile 0.64 verir, yani gecerdi.
        # Sahada 0.44-0.62 arasi duzensiz lekeler "inis bolgesi" sayildi.
        # Not: daire egik bakista elipse doner ve olcu cos(egim)'e duser —
        # 0.75 kabaca 41 dereceye kadar bakisa izin verir.
        self._min_circularity = config.get('min_circularity', 0.75)
        self._blur_k = config.get('gaussian_blur_kernel', 5)

        ranges = config.get('color_ranges', {})
        self._red_lower1 = np.array(
            ranges.get('red_lower_1', [0, 100, 100])
        )
        self._red_upper1 = np.array(
            ranges.get('red_upper_1', [10, 255, 255])
        )
        self._red_lower2 = np.array(
            ranges.get('red_lower_2', [160, 100, 100])
        )
        self._red_upper2 = np.array(
            ranges.get('red_upper_2', [180, 255, 255])
        )

        self._blue_lower = np.array(
            ranges.get('blue_lower', [100, 150, 50])
        )
        self._blue_upper = np.array(
            ranges.get('blue_upper', [140, 255, 255])
        )

    def detect(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """Verilen BGR goruntu uzerinde kirmizi ve mavi bolgeleri arar."""
        if image is None or image.size == 0:
            return []

        if self._blur_k > 0:
            image = cv2.GaussianBlur(
                image, (self._blur_k, self._blur_k), 0
            )

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        results = []

        mask_red1 = cv2.inRange(hsv, self._red_lower1, self._red_upper1)
        mask_red2 = cv2.inRange(hsv, self._red_lower2, self._red_upper2)
        mask_red = cv2.bitwise_or(mask_red1, mask_red2)
        red_zones = self._find_zones(
            mask_red, color_id=1, image_shape=image.shape
        )
        results.extend(red_zones)

        mask_blue = cv2.inRange(hsv, self._blue_lower, self._blue_upper)
        blue_zones = self._find_zones(
            mask_blue, color_id=2, image_shape=image.shape
        )
        results.extend(blue_zones)

        return results

    def _find_zones(
        self, mask: np.ndarray, color_id: int,
        image_shape: Tuple[int, ...]
    ) -> List[Dict[str, Any]]:
        """Maske uzerinde konturlari bularak gecerli bolgeleri secer."""
        zones = []
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        img_h, img_w = image_shape[:2]
        alan_esigi = max(self._min_area, self._min_area_frac * img_h * img_w)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < alan_esigi:
                continue

            (x, y), radius = cv2.minEnclosingCircle(cnt)

            circle_area = np.pi * (radius ** 2)
            confidence = (
                float(area / circle_area) if circle_area > 0 else 0.0
            )

            if confidence < self._min_circularity:
                continue

            zone_data = {
                'color': color_id,
                'image_x': float(x) / img_w,
                'image_y': float(y) / img_h,
                'radius_px': float(radius),
                'confidence': confidence,
                # Ayarlarken NEDEN kabul/red edildigi gorunsun diye:
                'area_px': float(area),
                'area_frac': float(area / (img_h * img_w)),
            }
            zones.append(zone_data)

        return zones
