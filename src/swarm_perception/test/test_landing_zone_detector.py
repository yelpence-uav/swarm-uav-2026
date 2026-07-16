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
test_landing_zone_detector.py

LandingZoneDetector birim testleri.
OpenCV fonksiyonları üzerinde renk filtrelemesi simüle edilir.
"""

import unittest

import cv2
import numpy as np

from swarm_perception.vision_node.landing_zone_detector import (
    LandingZoneDetector,
    ensure_bgr,
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

    def test_rgb8_kare_bgr_ye_cevrilir(self) -> None:
        """rgb8 yayınlayan kamera KIRMIZI pedi kırmızı olarak verdirmeli.

        Dedektör BGR bekler. Kamera rgb8 yayınlarken ham tampon doğrudan
        verilirse kırmızı ile mavi kanalı yer değiştirir: kırmızı ped "mavi",
        mavi ped "kırmızı" etiketlenir ve "kırmızıya in" emrini alan dron MAVİ
        pede iner (yaşanan bug). ensure_bgr bunu formatı okuyarak önler.
        """
        # RGB düzeninde kırmızı çember: R kanalı dolu -> (255, 0, 0)
        rgb = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.circle(rgb, (50, 50), 15, (255, 0, 0), -1)

        # Ham (çevrilmemiş) kare: dedektör bunu MAVİ sanır -> hatanın ta kendisi
        ham = self.detector.detect(rgb)
        self.assertEqual(len(ham), 1)
        self.assertEqual(ham[0]['color'], 2, 'cevrilmemis rgb8 mavi gorunur')

        # ensure_bgr ile: doğru şekilde KIRMIZI
        duzeltilmis = self.detector.detect(ensure_bgr(rgb, 'rgb8'))
        self.assertEqual(len(duzeltilmis), 1)
        self.assertEqual(duzeltilmis[0]['color'], 1)

    def test_bgr8_kare_dokunulmadan_gecer(self) -> None:
        """Zaten BGR olan kare ensure_bgr'den değişmeden geçer."""
        bgr = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.circle(bgr, (50, 50), 15, (0, 0, 255), -1)   # BGR'de kırmızı

        sonuc = self.detector.detect(ensure_bgr(bgr, 'bgr8'))
        self.assertEqual(len(sonuc), 1)
        self.assertEqual(sonuc[0]['color'], 1)


if __name__ == '__main__':
    unittest.main()
