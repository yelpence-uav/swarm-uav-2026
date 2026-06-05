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
camera_info_builder.py.

sensor_msgs/CameraInfo mesajı oluşturan yardımcı modül.

telemetry_mapper.py deseni gibi ROS 2'den bağımsız saf fonksiyonlar.
Kamera intrinsic parametrelerini alır ve CameraInfo mesajını doldurur.

GERÇEK DONANIM NOTLARI:
─────────────────────────────────────────────────────────────────────
1. Aşağıdaki varsayılan fx/fy/cx/cy değerleri Gazebo model.sdf'teki
   horizontal_fov (1.047 rad) ile hesaplanmış yaklaşık değerlerdir.

2. Sahaya çıkmadan önce mutlaka OpenCV checkerboard kalibrasyonu
   yapılmalıdır:
       ros2 run camera_calibration cameracalibrator \
           --size 9x6 --square 0.025 \
           image:=/drone_1/camera/image_raw
   Kalibrasyon sonucunda elde edilen K matrisi ve distortion
   katsayıları bu modüldeki build_camera_info() fonksiyonuna
   veya camera_params.yaml'a girilmelidir.

3. Arducam HQ + 6mm CS lens kombinasyonunda barrel distortion
   olabilir. Kalibrasyon sonucundaki D (distortion) katsayılarını
   camera_params.yaml'a ekleyip buradaki fonksiyona geçirebilirsiniz.
   Şu anda distortion sıfır varsayılmıştır.
─────────────────────────────────────────────────────────────────────
"""

import math


def compute_fov_deg(focal_length_px: float, image_size_px: int) -> float:
    """Odak uzaklığı ve görüntü boyutundan FOV (derece) hesaplar.

    Args:
        focal_length_px: Piksel cinsinden odak uzaklığı (fx veya fy).
        image_size_px: Piksel cinsinden görüntü boyutu (width veya height).

    Returns:
        FOV değeri derece cinsinden.
    """
    if focal_length_px <= 0.0:
        return 0.0
    return math.degrees(2.0 * math.atan2(image_size_px / 2.0, focal_length_px))


def compute_focal_length(fov_rad: float, image_size_px: int) -> float:
    """FOV (radyan) ve görüntü boyutundan odak uzaklığı (piksel) hesaplar.

    Args:
        fov_rad: FOV değeri radyan cinsinden.
        image_size_px: Piksel cinsinden görüntü boyutu.

    Returns:
        Odak uzaklığı piksel cinsinden.
    """
    if fov_rad <= 0.0:
        return 0.0
    return (image_size_px / 2.0) / math.tan(fov_rad / 2.0)


def build_camera_info(
    width: int = 1280,
    height: int = 720,
    fx: float = 1108.5,
    fy: float = 1108.5,
    cx: float = 640.0,
    cy: float = 360.0,
    distortion_coeffs: list[float] | None = None,
) -> dict:
    """Camerainfo mesajı için alan sözlüğü oluşturur.

    ROS 2 sensor_msgs/CameraInfo mesaj formatına uygun bir dict döner.
    camera_driver_node.py bu dict'i doğrudan CameraInfo mesajına aktarır.

    Args:
        width: Görüntü genişliği (piksel).
        height: Görüntü yüksekliği (piksel).
        fx: Yatay odak uzaklığı (piksel).
        fy: Dikey odak uzaklığı (piksel).
        cx: Optik merkez x (piksel).
        cy: Optik merkez y (piksel).
        distortion_coeffs: Radyal/tanjansiyel katsayılar [k1, k2, p1, p2, k3].
            None ise sıfır distortion varsayılır.

    Returns:
        CameraInfo alanlarını içeren dict.

    GERÇEK DONANIM: Kalibrasyon sonrasında fx, fy, cx, cy ve
    distortion_coeffs değerlerini güncelleyin. Özellikle:
    - fx/fy: Kalibrasyon K matrisinin [0,0] ve [1,1] elemanları
    - cx/cy: Kalibrasyon K matrisinin [0,2] ve [1,2] elemanları
    - distortion_coeffs: cv2.calibrateCamera() çıktısı
    """
    if distortion_coeffs is None:
        # Sıfır distortion — Gazebo'da distortion yok.
        # GERÇEK DONANIM: Kalibrasyon sonuçlarını buraya girin.
        distortion_coeffs = [0.0, 0.0, 0.0, 0.0, 0.0]

    # 3x3 intrinsic (K) matris — row-major düzleştirilmiş
    k_matrix = [
        fx,  0.0, cx,
        0.0, fy,  cy,
        0.0, 0.0, 1.0,
    ]

    # 3x4 projection (P) matris — mono kamera için R = I
    p_matrix = [
        fx,  0.0, cx,  0.0,
        0.0, fy,  cy,  0.0,
        0.0, 0.0, 1.0, 0.0,
    ]

    # 3x3 rectification matris — mono kamera için birim matris
    r_matrix = [
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0,
    ]

    return {
        'width': width,
        'height': height,
        'distortion_model': 'plumb_bob',
        'd': distortion_coeffs,
        'k': k_matrix,
        'r': r_matrix,
        'p': p_matrix,
    }
