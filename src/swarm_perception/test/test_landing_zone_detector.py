# Copyright 2026 Yelpence

"""LandingZoneDetector birim testleri."""

import unittest

import cv2
import numpy as np

from swarm_perception.vision_node.landing_zone_detector import (
    LandingZoneDetector,
)


class TestLandingZoneDetector(unittest.TestCase):
    """LandingZoneDetector sınıfı için birim testler."""

    def setUp(self) -> None:
        config = {
            'min_zone_area_px': 100.0,
            'gaussian_blur_kernel': 0,  # Test için kapalı
            'color_ranges': {
                'red_lower_1': [0, 100, 100],
                'red_upper_1': [10, 255, 255],
                'red_lower_2': [160, 100, 100],
                'red_upper_2': [180, 255, 255],
                'blue_lower': [100, 100, 100],
                'blue_upper': [140, 255, 255],
            },
        }
        self.detector = LandingZoneDetector(config)

    def test_empty_image(self) -> None:
        """Boş görüntü verildiğinde boş liste dönmeli."""
        self.assertEqual(self.detector.detect(None), [])
        self.assertEqual(self.detector.detect(np.array([])), [])

    def test_detect_blue_zone(self) -> None:
        """Sentetik mavi bir çember oluşturup tespitini doğrulama."""
        # 100x100 siyah zemin
        img = np.zeros((100, 100, 3), dtype=np.uint8)

        # Mavi çember (BGR formatında Mavi = [255, 0, 0])
        cv2.circle(img, (50, 50), 10, (255, 0, 0), -1)

        results = self.detector.detect(img)

        self.assertEqual(len(results), 1)
        zone = results[0]

        # Beklenen: Mavi ID = 2, Merkez = (0.5, 0.5)
        self.assertEqual(zone['color'], 2)
        self.assertAlmostEqual(zone['image_x'], 0.5, delta=0.05)
        self.assertAlmostEqual(zone['image_y'], 0.5, delta=0.05)
        self.assertGreater(zone['confidence'], 0.8)

    def test_detect_red_zone(self) -> None:
        """Sentetik kırmızı bir çember oluşturup tespitini doğrulama."""
        img = np.zeros((100, 100, 3), dtype=np.uint8)

        # Kırmızı çember (BGR formatında Kırmızı = [0, 0, 255])
        cv2.circle(img, (25, 75), 15, (0, 0, 255), -1)

        results = self.detector.detect(img)

        self.assertEqual(len(results), 1)
        zone = results[0]

        # Beklenen: Kırmızı ID = 1, Merkez = (0.25, 0.75)
        self.assertEqual(zone['color'], 1)
        self.assertAlmostEqual(zone['image_x'], 0.25, delta=0.05)
        self.assertAlmostEqual(zone['image_y'], 0.75, delta=0.05)

    def test_ignore_small_zones(self) -> None:
        """min_zone_area_px altındaki piksellerin elenmesi."""
        img = np.zeros((100, 100, 3), dtype=np.uint8)

        # Çok küçük bir mavi çember (Alan < 100)
        cv2.circle(img, (50, 50), 2, (255, 0, 0), -1)

        results = self.detector.detect(img)
        self.assertEqual(len(results), 0)


if __name__ == '__main__':
    unittest.main()
