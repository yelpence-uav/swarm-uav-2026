# Copyright 2026 Yelpence
"""sensor_msgs/CameraInfo mesaji olusturan yardimci modul."""

import math


def compute_fov_deg(focal_length_px: float, image_size_px: int) -> float:
    """
    Odak uzakligi ve goruntu boyutundan FOV (derece) hesaplar.

    Args:
        focal_length_px: Piksel cinsinden odak uzakligi (fx veya fy).
        image_size_px: Piksel cinsinden goruntu boyutu.

    Returns:
        float: FOV degeri derece cinsinden.
    """
    if focal_length_px <= 0.0:
        return 0.0
    return math.degrees(
        2.0 * math.atan2(image_size_px / 2.0, focal_length_px)
    )


def compute_focal_length(fov_rad: float, image_size_px: int) -> float:
    """
    FOV (radyan) ve goruntu boyutundan odak uzakligi hesaplar.

    Args:
        fov_rad: FOV degeri radyan cinsinden.
        image_size_px: Piksel cinsinden goruntu boyutu.

    Returns:
        float: Odak uzakligi piksel cinsinden.
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
    """
    Camerainfo mesaji icin alan sozleri olusturur.

    Args:
        width: Goruntu genisligi.
        height: Goruntu yuksekligi.
        fx: Yatay odak uzakligi.
        fy: Dikey odak uzakligi.
        cx: Optik merkez x.
        cy: Optik merkez y.
        distortion_coeffs: Radyal/tanjansiyel katsayilar.

    Returns:
        dict: CameraInfo alanlarini iceren sozluk.
    """
    if distortion_coeffs is None:
        distortion_coeffs = [0.0, 0.0, 0.0, 0.0, 0.0]

    k_matrix = [
        fx,  0.0, cx,
        0.0, fy,  cy,
        0.0, 0.0, 1.0,
    ]

    p_matrix = [
        fx,  0.0, cx,  0.0,
        0.0, fy,  cy,  0.0,
        0.0, 0.0, 1.0, 0.0,
    ]

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
