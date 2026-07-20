# Copyright 2026 Yelpence
"""Kamera erisim katmani."""

import time

import cv2
import numpy as np


class FrameGrabber:
    """Fiziksel kamera erisim katmani."""

    def __init__(
        self,
        device_id: int,
        width: int,
        height: int,
        fps: float,
        flip_vertical: bool = False,
        flip_horizontal: bool = False,
    ) -> None:
        self._device_id = device_id
        self._width = width
        self._height = height
        self._fps = fps
        self._flip_v = flip_vertical
        self._flip_h = flip_horizontal

        self._cap = None
        self._last_grab_time = 0.0
        self._frame_count = 0

    def open_camera(self) -> bool:
        """Kamerayi acar ve cozunurluk/fps ayarlarini uygular."""
        self._cap = cv2.VideoCapture(self._device_id)
        if not self._cap.isOpened():
            return False

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._cap.set(cv2.CAP_PROP_FPS, self._fps)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._frame_count = 0
        self._last_grab_time = time.monotonic()
        return True

    def grab(self) -> tuple[bool, np.ndarray | None]:
        """Tek bir frame yakalar."""
        if self._cap is None or not self._cap.isOpened():
            return False, None

        ret, frame = self._cap.read()
        if not ret or frame is None:
            return False, None

        if self._flip_v and self._flip_h:
            frame = cv2.flip(frame, -1)
        elif self._flip_v:
            frame = cv2.flip(frame, 0)
        elif self._flip_h:
            frame = cv2.flip(frame, 1)

        self._last_grab_time = time.monotonic()
        self._frame_count += 1
        return True, frame

    def release(self) -> None:
        """Kamera kaynagini serbest birakir."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def is_opened(self) -> bool:
        """Kamera acik ve erisilebilirlik durumu."""
        return self._cap is not None and self._cap.isOpened()

    @property
    def actual_fps(self) -> float:
        """Kameradan raporlanan gercek FPS degeri."""
        if self._cap is None:
            return 0.0
        return float(self._cap.get(cv2.CAP_PROP_FPS))

    @property
    def actual_resolution(self) -> tuple[int, int]:
        """Kameradan raporlanan gercek cozunurluk."""
        if self._cap is None:
            return 0, 0
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return w, h

    @property
    def frame_count(self) -> int:
        """Toplam yakalanan frame sayisi."""
        return self._frame_count

    @property
    def last_grab_time(self) -> float:
        """Son basarili frame yakalama zamani."""
        return self._last_grab_time


class SimFrameGrabber:
    """SITL/Gazebo modu icin sentetik frame ureticisi."""

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
    ) -> None:
        self._width = width
        self._height = height
        self._opened = False
        self._frame_count = 0
        self._last_grab_time = 0.0

    def open_camera(self) -> bool:
        """Sentetik kaynak acar."""
        self._opened = True
        self._last_grab_time = time.monotonic()
        return True

    def grab(self) -> tuple[bool, np.ndarray | None]:
        """Sentetik test frame'i uretir."""
        if not self._opened:
            return False, None

        frame = np.full(
            (self._height, self._width, 3),
            fill_value=40,
            dtype=np.uint8,
        )

        self._frame_count += 1
        cv2.putText(
            frame,
            f'SIM FRAME #{self._frame_count}',
            (50, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            2.0,
            (0, 255, 0),
            3,
        )

        self._last_grab_time = time.monotonic()
        return True, frame

    def release(self) -> None:
        """Sentetik kaynagi kapatir."""
        self._opened = False

    def is_opened(self) -> bool:
        """Kaynak acik olma durumu."""
        return self._opened

    @property
    def actual_fps(self) -> float:
        """Sabit 0.0 doner."""
        return 0.0

    @property
    def actual_resolution(self) -> tuple[int, int]:
        """Yapilandirilmis cozunurluk."""
        return self._width, self._height

    @property
    def frame_count(self) -> int:
        """Toplam uretilen frame sayisi."""
        return self._frame_count

    @property
    def last_grab_time(self) -> float:
        """Son frame uretim zamani."""
        return self._last_grab_time
