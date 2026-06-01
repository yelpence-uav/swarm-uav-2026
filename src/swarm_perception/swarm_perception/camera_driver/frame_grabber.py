"""
frame_grabber.py

Kamera erişim katmanı — ROS 2'den bağımsız saf Python modülü.

telemetry_mapper.py ↔ px4_bridge.py ayrışım desenini takip eder:
saf iş mantığı bu dosyada, ROS 2 entegrasyonu camera_driver_node.py'da.

FrameGrabber: Gerçek donanımda OpenCV VideoCapture ile /dev/video0'dan
              görüntü yakalar.
SimFrameGrabber: SITL modunda sentetik test görüntüsü üretir.

GERÇEK DONANIM NOTLARI:
─────────────────────────────────────────────────────────────────────
1. Arducam HQ kamera RPi 5'e CSI ribbon kablo ile bağlanır.
   RPi OS'ta /boot/firmware/config.txt'e şu overlay eklenmeli:
       dtoverlay=imx477
   Bu satır olmadan kamera /dev/video0 olarak görünmez.

2. Docker konteyneri --device=/dev/video0 ile başlatılmalı
   (docker/rpi/INSTRUCTION.md'de zaten mevcut).

3. Eğer OpenCV V4L2 backend kamerayı açamazsa GStreamer pipeline
   denenebilir:
       cap = cv2.VideoCapture(
           'v4l2src device=/dev/video0 ! video/x-raw,width=1280,'
           'height=720,framerate=15/1 ! videoconvert ! appsink',
           cv2.CAP_GSTREAMER
       )
   Bu durumda open() metodunda backend parametresi eklenmeli.

4. Arducam HQ'nun auto-exposure ve white-balance ayarları V4L2
   kontrolleri ile yapılabilir:
       v4l2-ctl -d /dev/video0 --set-ctrl=auto_exposure=0
       v4l2-ctl -d /dev/video0 --set-ctrl=exposure_time_absolute=500
   Veya OpenCV üzerinden:
       cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
       cap.set(cv2.CAP_PROP_EXPOSURE, desired_value)
─────────────────────────────────────────────────────────────────────
"""

import time

import cv2
import numpy as np


class FrameGrabber:
    """OpenCV VideoCapture sarmalayıcı — fiziksel kamera erişim katmanı.

    Gerçek donanımda /dev/video{device_id} üzerinden Arducam HQ kameraya
    erişir. SITL modunda kullanılmaz; yerine SimFrameGrabber tercih edilir.

    GERÇEK DONANIM: Eğer CSI kamera V4L2 üzerinden açılmazsa,
    device_id yerine GStreamer pipeline string'i verilebilir.
    Bu durumda open() metodundaki cv2.VideoCapture çağrısı
    değiştirilmelidir (yukarıdaki docstring'e bakın).
    """

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

        self._cap: cv2.VideoCapture | None = None
        self._last_grab_time: float = 0.0
        self._frame_count: int = 0

    def open(self) -> bool:
        """Kamerayı açar ve çözünürlük/fps ayarlarını uygular.

        Returns:
            True ise kamera başarıyla açıldı.

        GERÇEK DONANIM: cv2.CAP_V4L2 backend'i açıkça belirtmek
        RPi'deki kamera uyumluluğunu artırabilir:
            self._cap = cv2.VideoCapture(
                self._device_id, cv2.CAP_V4L2
            )
        Eğer V4L2 çalışmazsa GStreamer pipeline denenebilir
        (modül docstring'ine bakın).
        """
        # GERÇEK DONANIM: Şu şekilde değiştirmeyi deneyin:
        #   self._cap = cv2.VideoCapture(self._device_id, cv2.CAP_V4L2)
        self._cap = cv2.VideoCapture(self._device_id)

        if not self._cap.isOpened():
            return False

        # Çözünürlük ve FPS ayarları
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._cap.set(cv2.CAP_PROP_FPS, self._fps)

        # GERÇEK DONANIM: Arducam HQ üzerinde buffer boyutunu 1'e
        # düşürmek gecikmeyi azaltır. Kamera sürücüsü destekliyorsa:
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._frame_count = 0
        self._last_grab_time = time.monotonic()
        return True

    def grab(self) -> tuple[bool, np.ndarray | None]:
        """Tek bir frame yakalar.

        Returns:
            (success, bgr_frame) çifti.
            success=False ise frame None döner.
        """
        if self._cap is None or not self._cap.isOpened():
            return False, None

        ret, frame = self._cap.read()

        if not ret or frame is None:
            return False, None

        # Kamera montaj yönü düzeltmesi
        # GERÇEK DONANIM: Kamera drone gövdesine monte edildikten sonra
        # görüntünün doğru yönde olup olmadığını kontrol edin.
        if self._flip_v and self._flip_h:
            frame = cv2.flip(frame, -1)  # Her iki eksen
        elif self._flip_v:
            frame = cv2.flip(frame, 0)   # Dikey
        elif self._flip_h:
            frame = cv2.flip(frame, 1)   # Yatay

        self._last_grab_time = time.monotonic()
        self._frame_count += 1
        return True, frame

    def release(self) -> None:
        """Kamera kaynağını serbest bırakır."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def is_opened(self) -> bool:
        """Kamera açık ve erişilebilir mi."""
        return self._cap is not None and self._cap.isOpened()

    @property
    def actual_fps(self) -> float:
        """Kameradan raporlanan gerçek FPS değeri.

        GERÇEK DONANIM: Bu değer kamera sürücüsünün bildirdiği FPS'dir.
        Arducam HQ'da ayarlanan değerle birebir aynı olmayabilir.
        Gerçek ölçüm için elapsed_time / frame_count kullanın.
        """
        if self._cap is None:
            return 0.0
        return float(self._cap.get(cv2.CAP_PROP_FPS))

    @property
    def actual_resolution(self) -> tuple[int, int]:
        """Kameradan raporlanan gerçek çözünürlük (width, height).

        GERÇEK DONANIM: Kamera sürücüsü istenen çözünürlüğü
        desteklemiyorsa en yakın desteklenen çözünürlüğe yuvarlar.
        Bu property ile gerçekte kullanılan çözünürlüğü doğrulayın.
        """
        if self._cap is None:
            return 0, 0
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return w, h

    @property
    def frame_count(self) -> int:
        """Toplam yakalanan frame sayısı."""
        return self._frame_count

    @property
    def last_grab_time(self) -> float:
        """Son başarılı frame yakalama zamanı (monotonic clock)."""
        return self._last_grab_time


class SimFrameGrabber:
    """SITL/Gazebo modu için sentetik frame üreticisi.

    Gazebo Harmonic'teki kamera sensörü ros_gz_image bridge ile
    ROS 2 topic'ine köprülendiğinde bu sınıf yerine doğrudan
    topic aboneliği kullanılır (camera_driver_node.py'da).

    Bu sınıf yalnızca bridge olmadan çalışan test senaryoları
    veya offline geliştirme için sentetik görüntü üretir.

    GERÇEK DONANIM: Bu sınıf gerçek donanımda kullanılmaz.
    sitl_mode=false olduğunda FrameGrabber aktif olur.
    """

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
    ) -> None:
        self._width = width
        self._height = height
        self._opened = False
        self._frame_count: int = 0
        self._last_grab_time: float = 0.0

    def open(self) -> bool:
        """Sentetik kaynak açar (her zaman başarılı)."""
        self._opened = True
        self._last_grab_time = time.monotonic()
        return True

    def grab(self) -> tuple[bool, np.ndarray | None]:
        """Gri tonlamalı sentetik test frame'i üretir.

        Üretilen frame'in sol üst köşesinde frame sayacı yazılıdır.
        Bu, downstream düğümlerin (vision_node, qr_detector) temel
        bağlantı testlerinde işe yarar.
        """
        if not self._opened:
            return False, None

        # Koyu gri arka planlı test görüntüsü
        frame = np.full(
            (self._height, self._width, 3),
            fill_value=40,
            dtype=np.uint8,
        )

        # Frame sayacı metni — downstream düğüm debug'ı için
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
        """Sentetik kaynağı kapatır."""
        self._opened = False

    def is_opened(self) -> bool:
        """Kaynak açık mı."""
        return self._opened

    @property
    def actual_fps(self) -> float:
        """Sentetik — sabit 0.0 döner."""
        return 0.0

    @property
    def actual_resolution(self) -> tuple[int, int]:
        """Yapılandırılmış çözünürlük."""
        return self._width, self._height

    @property
    def frame_count(self) -> int:
        """Toplam üretilen frame sayısı."""
        return self._frame_count

    @property
    def last_grab_time(self) -> float:
        """Son frame üretim zamanı (monotonic clock)."""
        return self._last_grab_time