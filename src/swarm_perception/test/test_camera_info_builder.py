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
test_camera_info_builder.py

camera_info_builder modülü birim testleri.

test_telemetry_mapper.py deseni takip edilir:
- unittest.TestCase yapısı
- Saf fonksiyon testleri (ROS 2 gerektirmez)
"""

import math
import unittest

from swarm_perception.camera_driver.camera_info_builder import (
    build_camera_info,
    compute_focal_length,
    compute_fov_deg,
)


class TestComputeFovDeg(unittest.TestCase):
    """FOV hesaplama testleri."""

    def test_bilinen_fov(self):
        """Gazebo FOV 1.047 rad (~60°) ile tutarlılık."""
        # 1280 genişlik, 1.047 rad FOV → fx ≈ 1108.5
        fx = 1108.5
        fov = compute_fov_deg(fx, 1280)
        # 60° civarı bekliyoruz
        self.assertAlmostEqual(fov, 60.0, delta=0.5)

    def test_90_derece_fov(self):
        """90° FOV: fx = width/2 olmalı."""
        # tan(45°) = 1 → fx = width/2
        fx = 640.0  # width=1280 için fx=640 → 90° FOV
        fov = compute_fov_deg(fx, 1280)
        self.assertAlmostEqual(fov, 90.0, delta=0.1)

    def test_sifir_focal_length(self):
        """Sıfır odak uzaklığı için 0.0 dönmeli."""
        self.assertEqual(compute_fov_deg(0.0, 1280), 0.0)

    def test_negatif_focal_length(self):
        """Negatif odak uzaklığı için 0.0 dönmeli."""
        self.assertEqual(compute_fov_deg(-100.0, 1280), 0.0)


class TestComputeFocalLength(unittest.TestCase):
    """Odak uzaklığı hesaplama testleri."""

    def test_gazebo_fov(self):
        """Gazebo model.sdf FOV (1.047 rad) için fx hesapla."""
        fx = compute_focal_length(1.047, 1280)
        # (1280/2) / tan(1.047/2) = 640 / tan(0.5235) ≈ 1108.5
        self.assertAlmostEqual(fx, 1108.5, delta=1.0)

    def test_90_derece(self):
        """90° FOV: fx = width/2."""
        fx = compute_focal_length(math.pi / 2, 1280)
        self.assertAlmostEqual(fx, 640.0, delta=0.1)

    def test_sifir_fov(self):
        """Sıfır FOV için 0.0 dönmeli."""
        self.assertEqual(compute_focal_length(0.0, 1280), 0.0)

    def test_tersine_cevrim(self):
        """compute_focal_length ↔ compute_fov_deg ters dönüşümü."""
        fov_rad = 1.047
        width = 1280
        fx = compute_focal_length(fov_rad, width)
        fov_deg = compute_fov_deg(fx, width)
        self.assertAlmostEqual(fov_deg, math.degrees(fov_rad), delta=0.1)


class TestBuildCameraInfo(unittest.TestCase):
    """CameraInfo dict oluşturma testleri."""

    def test_varsayilan_boyut(self):
        info = build_camera_info()
        self.assertEqual(info['width'], 1280)
        self.assertEqual(info['height'], 720)

    def test_ozel_boyut(self):
        info = build_camera_info(width=640, height=480)
        self.assertEqual(info['width'], 640)
        self.assertEqual(info['height'], 480)

    def test_distortion_model(self):
        info = build_camera_info()
        self.assertEqual(info['distortion_model'], 'plumb_bob')

    def test_varsayilan_distortion_sifir(self):
        """Gazebo'da distortion yok — varsayılan sıfır olmalı."""
        info = build_camera_info()
        self.assertEqual(len(info['d']), 5)
        for d in info['d']:
            self.assertEqual(d, 0.0)

    def test_ozel_distortion(self):
        d = [0.1, -0.2, 0.001, 0.002, 0.05]
        info = build_camera_info(distortion_coeffs=d)
        self.assertEqual(info['d'], d)

    def test_k_matrisi_boyut(self):
        """K matrisi 9 elemanlı olmalı (3x3 düzleştirilmiş)."""
        info = build_camera_info()
        self.assertEqual(len(info['k']), 9)

    def test_k_matrisi_degerleri(self):
        """K matrisinde fx, fy, cx, cy doğru yerde olmalı."""
        info = build_camera_info(fx=100.0, fy=200.0, cx=300.0, cy=400.0)
        k = info['k']
        # K = [[fx, 0, cx], [0, fy, cy], [0, 0, 1]]
        self.assertEqual(k[0], 100.0)   # fx
        self.assertEqual(k[1], 0.0)
        self.assertEqual(k[2], 300.0)   # cx
        self.assertEqual(k[3], 0.0)
        self.assertEqual(k[4], 200.0)   # fy
        self.assertEqual(k[5], 400.0)   # cy
        self.assertEqual(k[6], 0.0)
        self.assertEqual(k[7], 0.0)
        self.assertEqual(k[8], 1.0)

    def test_p_matrisi_boyut(self):
        """P matrisi 12 elemanlı olmalı (3x4 düzleştirilmiş)."""
        info = build_camera_info()
        self.assertEqual(len(info['p']), 12)

    def test_p_matrisi_fx_fy(self):
        """P matrisinde fx ve fy doğru yerde olmalı."""
        info = build_camera_info(fx=500.0, fy=600.0)
        p = info['p']
        self.assertEqual(p[0], 500.0)   # fx
        self.assertEqual(p[5], 600.0)   # fy

    def test_r_matrisi_birim(self):
        """Mono kamera için R matrisi birim matris olmalı."""
        info = build_camera_info()
        r = info['r']
        # Birim matris
        self.assertEqual(r[0], 1.0)
        self.assertEqual(r[4], 1.0)
        self.assertEqual(r[8], 1.0)
        self.assertEqual(r[1], 0.0)
        self.assertEqual(r[3], 0.0)

    def test_gazebo_uyumluluk(self):
        """Varsayılan parametreler Gazebo model.sdf ile tutarlı olmalı.

        Gazebo: 1280x720, horizontal_fov=1.047 rad
        → fx = (1280/2) / tan(1.047/2) ≈ 1108.5
        """
        info = build_camera_info()
        self.assertEqual(info['width'], 1280)
        self.assertEqual(info['height'], 720)
        # FOV kontrolü: varsayılan fx ile hesaplanan FOV ~60°
        fov = compute_fov_deg(info['k'][0], info['width'])
        self.assertAlmostEqual(fov, 60.0, delta=0.5)


if __name__ == '__main__':
    unittest.main()
