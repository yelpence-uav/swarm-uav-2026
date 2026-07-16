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

"""
landing_zone_detector.py.

OpenCV kullanarak HSV uzayında kırmızı/mavi bölgeleri bulur.
PEP 8 ve PEP 257 standartlarına uygundur.
"""

from typing import Any, Dict, List, Tuple

import cv2
import numpy as np


def ensure_bgr(image: np.ndarray, encoding: str) -> np.ndarray:
    """Görüntüyü dedektörlerin beklediği BGR düzenine getirir.

    Bu modül (OpenCV sözleşmesi gereği) BGR bekler. Kamera sürücüleri sık sık
    rgb8 yayınlar; ham tamponu doğrudan vermek kırmızı ile mavi kanalını YER
    DEĞİŞTİRİR. Sonuç sessizdir ve yıkıcıdır: kırmızı ped "mavi", mavi ped
    "kırmızı" etiketlenir; "kırmızıya in" emri alan dron mavi pede iner.

    Format varsayılmaz — sensor_msgs/Image içinde yazar, oradan okunur.

    Args:
        image (np.ndarray): HxWx3 uint8 görüntü.
        encoding (str): sensor_msgs/Image encoding alanı ('rgb8' | 'bgr8').

    Returns:
        np.ndarray: BGR düzenli görüntü. Bilinmeyen formatta girdi olduğu gibi
        döner (çağıran uyarır); sessizce dönüştürmek yeni bir yalan olurdu.
    """
    if encoding == 'rgb8':
        return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    return image


class LandingZoneDetector:
    """Kırmızı/mavi iniş bölgelerini HSV uzayında tespit eder."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Landingzonedetector sınıfını ilklendirir.

        Args:
            config (Dict[str, Any]): vision_params.yaml dosyasından gelen
                konfigürasyon sözlüğü. 'color_ranges', 'min_zone_area_px',
                'gaussian_blur_kernel' anahtarlarını içermelidir.
        """
        self._config = config
        self._min_area = config.get('min_zone_area_px', 500.0)
        self._blur_k = config.get('gaussian_blur_kernel', 5)

        # HSV Eşikleri
        ranges = config.get('color_ranges', {})
        self._red_lower1 = np.array(ranges.get('red_lower_1', [0, 100, 100]))
        self._red_upper1 = np.array(ranges.get('red_upper_1', [10, 255, 255]))
        self._red_lower2 = np.array(ranges.get('red_lower_2', [160, 100, 100]))
        self._red_upper2 = np.array(ranges.get('red_upper_2', [180, 255, 255]))

        self._blue_lower = np.array(ranges.get('blue_lower', [100, 150, 50]))
        self._blue_upper = np.array(ranges.get('blue_upper', [140, 255, 255]))

    def detect(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Verilen BGR görüntü üzerinde kırmızı ve mavi bölgeleri arar.

        Args:
            image (np.ndarray): cv2 formatında BGR görüntü matrisi.

        Returns:
            List[Dict[str, Any]]: Tespit edilen bölgelerin listesi. Her bölge
            renk tipini (1=Kırmızı, 2=Mavi), merkez x-y oranını ve
            güven skorunu içerir.
        """
        if image is None or image.size == 0:
            return []

        # Gürültü azaltma
        if self._blur_k > 0:
            image = cv2.GaussianBlur(
                image, (self._blur_k, self._blur_k), 0
            )

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        results = []

        # Kırmızı tespiti (İki parçalı HSV aralığı)
        mask_red1 = cv2.inRange(hsv, self._red_lower1, self._red_upper1)
        mask_red2 = cv2.inRange(hsv, self._red_lower2, self._red_upper2)
        mask_red = cv2.bitwise_or(mask_red1, mask_red2)
        red_zones = self._find_zones(
            mask_red, color_id=1, image_shape=image.shape
        )
        results.extend(red_zones)

        # Mavi tespiti
        mask_blue = cv2.inRange(hsv, self._blue_lower, self._blue_upper)
        blue_zones = self._find_zones(
            mask_blue, color_id=2, image_shape=image.shape
        )
        results.extend(blue_zones)

        return results

    def _find_zones(
        self, mask: np.ndarray, color_id: int, image_shape: Tuple[int, ...]
    ) -> List[Dict[str, Any]]:
        """
        Maske üzerinde konturları bularak geçerli bölgeleri seçer.

        Args:
            mask (np.ndarray): İlgili renge ait 2D binary maske.
            color_id (int): Tespit edilen renk kimliği (1: Kırmızı).
            image_shape (Tuple[int, ...]): Orijinal görüntünün boyutları
                (height, width, channels).

        Returns:
            List[Dict[str, Any]]: Geçerli bölgelerin sözlük listesi.
        """
        zones = []
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        img_h, img_w = image_shape[:2]

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self._min_area:
                continue

            # Minimum kapsayan çember
            (x, y), radius = cv2.minEnclosingCircle(cnt)

            # Güven skoru: Çember alanı ile gerçek kontur alanı oranı
            circle_area = np.pi * (radius ** 2)
            confidence = float(area / circle_area) if circle_area > 0 else 0.0

            # Filtre: Şekil çok bozuksa (çemberden uzaksa) reddet
            if confidence < 0.4:
                continue

            zone_data = {
                'color': color_id,
                'image_x': float(x) / img_w,
                'image_y': float(y) / img_h,
                'radius_px': float(radius),
                'confidence': confidence,
            }
            zones.append(zone_data)

        return zones
