# Copyright 2026 Yelpence
"""Kamera erisim katmani."""

import threading
import time
import urllib.error
import urllib.request

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


class HttpMjpegGrabber:
    """MJPEG akisindan frame alan erisim katmani.

    NEDEN VAR (27 Agustos 2026, sahada olculdu)
    -------------------------------------------
    `FrameGrabber` `cv2.VideoCapture(device_id)` kullaniyor. Pi 5'te
    IMX477'nin V4L2 dugumu `/dev/video0` = **rp1-cfe-csi2_ch0**, yani ham
    Bayer veren bir CSI yakalama dugumu — UVC kamera DEGIL. cv2 oradan
    kullanilabilir BGR karesi alamaz. Bu, sim doneminden kalan bir
    varsayimdi ve gercek donanimda ilk kez 27 Agustos'ta sinandi.

    Kamerayi `deploy/rpi/kamera_yayin.py` aciyor (libcamera/rpicam-vid) ve
    MJPEG olarak HTTP'den veriyor; bu sinif onu tuketiyor. Konteyner
    `--network host` oldugu icin `127.0.0.1` dogrudan erisilebilir:
    **cihaz gecirme (`--device /dev/video*`) GEREKMIYOR**, konteyner
    yeniden olusturmaya da gerek yok.

    ⚠️ KAMERAYI TEK SUREC ACABILIR. Yayin servisi kosmuyorsa bu da acilmaz;
    `open_camera()` False doner ve dugum saglik olayi uretir.

    ⚠️ RENK SIRASI: `cv2.imdecode` BGR dondurur ve dugum `bgr8` yayinliyor
    — ikisi ayni. JPEG'i baska bir kutuphaneyle (PIL vb.) cozmek RGB verir
    ve kanallar sessizce ters doner; o yuzden burada da cv2 kullaniliyor.
    """

    def __init__(
        self,
        url: str,
        width: int,
        height: int,
        fps: float,
        flip_vertical: bool = False,
        flip_horizontal: bool = False,
        timeout: float = 5.0,
    ) -> None:
        self._url = url
        self._width = width
        self._height = height
        self._fps = fps
        self._flip_v = flip_vertical
        self._flip_h = flip_horizontal
        self._timeout = timeout

        self._akis = None
        self._okuyucu: threading.Thread | None = None
        self._dur = threading.Event()

        self._kilit = threading.Lock()
        self._son_jpeg: bytes | None = None
        self._uretilen = 0          # okuyucunun urettigi kare sayisi
        self._tuketilen = -1        # grab()'in en son aldigi kare

        self._son_boyut = (0, 0)
        self._olculen_fps = 0.0
        self._pencere_kare = 0
        self._pencere_an = 0.0

        self._frame_count = 0
        self._last_grab_time = 0.0

    # -------------------------------------------------------------- acma

    def open_camera(self) -> bool:
        """Akisi acar ve ILK KARE gelene kadar bekler.

        Ilk kareyi beklemek onemli: beklemezsek `open_camera()` True doner
        ama ilk `grab()` bos gelir ve dugum kamerayi acik sanip saglik
        zaman asimina duser.
        """
        self.release()
        self._dur.clear()
        try:
            self._akis = urllib.request.urlopen(
                self._url, timeout=self._timeout)
        except (urllib.error.URLError, OSError):
            self._akis = None
            return False

        self._pencere_an = time.monotonic()
        self._okuyucu = threading.Thread(target=self._akisi_oku, daemon=True)
        self._okuyucu.start()

        bitis = time.monotonic() + self._timeout
        while time.monotonic() < bitis:
            with self._kilit:
                jpeg = self._son_jpeg
            if jpeg is not None:
                # Ilk kareyi COZUP boyutu dolduruyoruz. Yoksa dugum acilista
                # "gercek=0x0" yazip SAHTE bir "Cozunurluk farkli" uyarisi
                # veriyordu — 27 Agustos'ta ilk kosuda goruldu. Kare
                # TUKETILMIYOR (_tuketilen'e dokunulmuyor), grab() yine alir.
                ilk = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8),
                                   cv2.IMREAD_COLOR)
                if ilk is not None:
                    self._son_boyut = (ilk.shape[1], ilk.shape[0])
                self._last_grab_time = time.monotonic()
                return True
            if self._dur.is_set():
                break
            time.sleep(0.05)

        self.release()
        return False

    def _akisi_oku(self) -> None:
        """Akisi FFD8..FFD9 sinirlarindan tek tek karelere boler.

        Yalniz EN SON kare tutuluyor — eski kareler bilerek atiliyor. Bu,
        `FrameGrabber`'daki `CAP_PROP_BUFFERSIZE=1` ile ayni niyet: dugum
        biriktirilmis eski goruntuyu degil, o anki goruntuyu gormeli.
        """
        tampon = bytearray()
        try:
            while not self._dur.is_set():
                parca = self._akis.read(65536)
                if not parca:
                    break
                tampon += parca
                while True:
                    bas = tampon.find(b'\xff\xd8')
                    if bas < 0:
                        tampon.clear()
                        break
                    son = tampon.find(b'\xff\xd9', bas + 2)
                    if son < 0:
                        if bas:
                            del tampon[:bas]
                        break
                    kare = bytes(tampon[bas:son + 2])
                    del tampon[:son + 2]
                    with self._kilit:
                        self._son_jpeg = kare
                        self._uretilen += 1
        except (OSError, ValueError):
            pass                      # akis koptu; is_opened() False donecek
        finally:
            self._dur.set()

    # ------------------------------------------------------------- alma

    def grab(self) -> tuple[bool, np.ndarray | None]:
        """Tek bir frame yakalar. YENI kare yoksa (False, None) doner.

        Ayni kareyi iki kez dondurmek, akis dugumun zamanlayicisindan yavas
        oldugunda topic'e kopya goruntu basardi. Kopya goruntu tespit
        katmaninda "nesne duruyor" gibi gorunur — sessiz ve yaniltici.
        """
        with self._kilit:
            if self._son_jpeg is None or self._uretilen == self._tuketilen:
                return False, None
            jpeg = self._son_jpeg
            self._tuketilen = self._uretilen

        tampon = np.frombuffer(jpeg, dtype=np.uint8)
        frame = cv2.imdecode(tampon, cv2.IMREAD_COLOR)     # BGR doner
        if frame is None:
            return False, None

        if self._flip_v and self._flip_h:
            frame = cv2.flip(frame, -1)
        elif self._flip_v:
            frame = cv2.flip(frame, 0)
        elif self._flip_h:
            frame = cv2.flip(frame, 1)

        self._son_boyut = (frame.shape[1], frame.shape[0])
        self._frame_count += 1
        self._last_grab_time = time.monotonic()

        self._pencere_kare += 1
        gecen = self._last_grab_time - self._pencere_an
        if gecen >= 1.0:
            self._olculen_fps = self._pencere_kare / gecen
            self._pencere_kare = 0
            self._pencere_an = self._last_grab_time

        return True, frame

    def grab_jpeg(self) -> tuple[bool, bytes | None]:
        """Kareyi COZMEDEN, JPEG olarak dondurur.

        NEDEN VAR (28 Agustos 2026, olculdu): 4056x3040 bir kare
        `sensor_msgs/Image` olarak 37 MB eder ve DDS'ten HIC gecmiyor —
        saniyede bir kareye indirmek bile kurtarmadi, sorun hiz degil TEK
        MESAJIN BOYUTU. Ayni kare JPEG olarak 1,4 MB.

        Akistan zaten JPEG geliyor; burada onu cozmeden veriyoruz. Yani bu
        yol `grab()`'ten yalniz daha ucuz degil, JPEG cozme adimini
        TAMAMEN atliyor (olculdu: 4K'da 106 ms).
        """
        with self._kilit:
            if self._son_jpeg is None or self._uretilen == self._tuketilen:
                return False, None
            jpeg = self._son_jpeg
            self._tuketilen = self._uretilen

        self._frame_count += 1
        self._last_grab_time = time.monotonic()
        self._pencere_kare += 1
        gecen = self._last_grab_time - self._pencere_an
        if gecen >= 1.0:
            self._olculen_fps = self._pencere_kare / gecen
            self._pencere_kare = 0
            self._pencere_an = self._last_grab_time
        return True, jpeg

    def release(self) -> None:
        """Akisi kapatir."""
        self._dur.set()
        if self._akis is not None:
            try:
                self._akis.close()
            except OSError:
                pass
            self._akis = None
        with self._kilit:
            self._son_jpeg = None
            self._uretilen = 0
            self._tuketilen = -1

    def is_opened(self) -> bool:
        """Akis acik ve hala kare uretiyor mu."""
        return self._akis is not None and not self._dur.is_set()

    @property
    def actual_fps(self) -> float:
        """Olculen gercek fps — akisin verdigi, istenen degil."""
        return self._olculen_fps

    @property
    def actual_resolution(self) -> tuple[int, int]:
        """Son cozulen karenin gercek cozunurlugu.

        Yayin servisinin onizleme boyutu ne ise odur; dugume verilen
        width/height DEGIL. Dugum bu ikisi farkliysa uyari yaziyor.
        """
        return self._son_boyut

    @property
    def frame_count(self) -> int:
        """Toplam yakalanan frame sayisi."""
        return self._frame_count

    @property
    def last_grab_time(self) -> float:
        """Son basarili frame yakalama zamani."""
        return self._last_grab_time
