"""
camera_driver_node.py

Arducam HQ kameradan görüntü yakalayan ve ROS 2 topic'lerine
yayınlayan ana sürücü düğümü.

Mimari rolü (ARCHITECTURE.md satır 67):
    swarm_perception/camera_driver — Arducam HQ kameradan görüntü
    karelerini (frame) alan ve container içi pointer paylaşımıyla
    bellek yükünü azaltan sürücü.

İŞLEYİŞ:
1. Gerçek donanımda (sitl_mode=false):
   FrameGrabber ile /dev/video0'dan frame yakalar
   → sensor_msgs/Image + CameraInfo olarak yayınlar

2. SITL modunda (sitl_mode=true):
   Gazebo ros_gz_image bridge topic'ine abone olur
   → Gelen frame'i kendi topic'ine re-publish eder
   Veya bridge yoksa SimFrameGrabber ile sentetik frame üretir

KULLANIM:
    # Gerçek donanım
    ros2 run swarm_perception camera_driver \\
        --ros-args -p agent_id:=1

    # SITL / Gazebo
    ros2 run swarm_perception camera_driver \\
        --ros-args -p agent_id:=1 -p sitl_mode:=true

    # Config dosyası ile
    ros2 run swarm_perception camera_driver \\
        --ros-args --params-file config/camera_params.yaml

GERÇEK DONANIM KONTROL LİSTESİ:
─────────────────────────────────────────────────────────────────────
□ RPi /boot/firmware/config.txt'te dtoverlay=imx477 var mı?
□ Docker --device=/dev/video0 ile başlatıldı mı?
□ camera_params.yaml'daki fx/fy/cx/cy kalibrasyon sonuçları mı?
□ flip_vertical/flip_horizontal kamera montaj yönüne göre ayarlı mı?
□ v4l2-ctl --list-devices ile kamera görünüyor mu?
□ Gerekirse fps değerini RPi CPU yüküne göre ayarlayın (15→30 arası)
─────────────────────────────────────────────────────────────────────
"""

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

from sensor_msgs.msg import CameraInfo, Image
from swarm_interfaces.msg import SystemEvent

from .camera_info_builder import build_camera_info, compute_fov_deg
from .frame_grabber import FrameGrabber, SimFrameGrabber


# Görüntü topic'i QoS — abone yetişemezse eski frame düşsün.
# INTERFACE_CONTRACT: LOKAL topic, proxy'den geçmez.
_IMAGE_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=1,
)


class CameraDriverNode(Node):
    """Kamera sürücü ROS 2 düğümü.

    Gerçek donanımda Arducam HQ kameradan, SITL'de Gazebo bridge'den
    veya sentetik frame üreticisinden görüntü yakalar ve yayınlar.
    """

    def __init__(self) -> None:
        super().__init__('camera_driver')

        # ── Parametreler ── (agent_fsm_node._declare_params deseni)
        self._declare_params()

        # ── Publisher'lar ── (agent_fsm_node._setup_publishers deseni)
        self._setup_publishers()

        # ── CameraInfo önbelleği ── (her frame'de aynıdır)
        self._camera_info_msg = self._build_camera_info_msg()

        # ── Kamera erişimi ──
        self._grabber: FrameGrabber | SimFrameGrabber | None = None
        self._sim_subscriber_active: bool = False
        self._last_frame_time: float = time.monotonic()

        if self._sitl_mode:
            self._setup_sitl_mode()
        else:
            self._setup_real_camera()

        # ── Frame yakalama timer'ı ──
        # SITL'de bridge varsa timer devre dışı kalır
        if not self._sim_subscriber_active:
            self._capture_timer = self.create_timer(
                1.0 / self._fps, self._capture_loop,
            )

        # ── Sağlık kontrolü (1 Hz watchdog) ──
        self._health_timer = self.create_timer(
            1.0, self._health_check,
        )

        self.get_logger().info(
            f'CameraDriverNode başlatıldı: agent_id={self._agent_id}, '
            f'sitl_mode={self._sitl_mode}, '
            f'{self._width}x{self._height}@{self._fps}Hz'
        )

    # =================================================================
    # PARAMETRE TANIMLARI
    # =================================================================
    def _declare_params(self) -> None:
        """ROS 2 parametrelerini tanımlar ve okur.

        agent_fsm_node._declare_params() deseni takip edilir.
        """
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('device_id', 0)
        self.declare_parameter('width', 1280)
        self.declare_parameter('height', 720)
        self.declare_parameter('fps', 15.0)
        self.declare_parameter('sitl_mode', False)
        self.declare_parameter('flip_vertical', False)
        self.declare_parameter('flip_horizontal', False)
        self.declare_parameter('health_timeout_sec', 3.0)

        # Intrinsic parametreler
        # GERÇEK DONANIM: Bu değerleri OpenCV kalibrasyondan alın.
        self.declare_parameter('fx', 1108.5)
        self.declare_parameter('fy', 1108.5)
        self.declare_parameter('cx', 640.0)
        self.declare_parameter('cy', 360.0)
        self.declare_parameter('fov_horizontal_rad', 1.047)

        self._agent_id: int = self.get_parameter('agent_id').value
        self._device_id: int = self.get_parameter('device_id').value
        self._width: int = self.get_parameter('width').value
        self._height: int = self.get_parameter('height').value
        self._fps: float = self.get_parameter('fps').value
        self._sitl_mode: bool = self.get_parameter('sitl_mode').value
        self._flip_v: bool = self.get_parameter('flip_vertical').value
        self._flip_h: bool = self.get_parameter('flip_horizontal').value
        self._health_timeout: float = self.get_parameter(
            'health_timeout_sec'
        ).value

        self._fx: float = self.get_parameter('fx').value
        self._fy: float = self.get_parameter('fy').value
        self._cx: float = self.get_parameter('cx').value
        self._cy: float = self.get_parameter('cy').value
        self._fov_h_rad: float = self.get_parameter(
            'fov_horizontal_rad'
        ).value

    # =================================================================
    # PUBLISHER'LAR
    # =================================================================
    def _setup_publishers(self) -> None:
        """Image, CameraInfo ve SystemEvent publisher'larını oluşturur.

        Topic adlandırma: /drone_{id}/camera/...
        INTERFACE_CONTRACT Kural 3: LOKAL topic, proxy'den geçmez.
        """
        aid = self._agent_id

        self._image_pub = self.create_publisher(
            Image,
            f'/drone_{aid}/camera/image_raw',
            _IMAGE_QOS,
        )
        self._info_pub = self.create_publisher(
            CameraInfo,
            f'/drone_{aid}/camera/camera_info',
            _IMAGE_QOS,
        )
        # SystemEvent yayını — kamera arızası bildirmek için
        # agent_fsm_node._pub_event deseni
        self._event_pub = self.create_publisher(
            SystemEvent,
            '/swarm/internal/events/system',
            10,
        )

    # =================================================================
    # KAMERA KURULUMU
    # =================================================================
    def _setup_real_camera(self) -> None:
        """Gerçek donanım: FrameGrabber ile fiziksel kamerayı açar.

        GERÇEK DONANIM: Bu metod /dev/video{device_id} üzerinden
        kameraya erişir. Eğer kamera açılmazsa:
        1. v4l2-ctl --list-devices ile cihazı doğrulayın
        2. dtoverlay=imx477 config.txt'te var mı kontrol edin
        3. Docker --device=/dev/video0 flag'ini kontrol edin
        4. frame_grabber.py'deki GStreamer pipeline alternatifini deneyin
        """
        self._grabber = FrameGrabber(
            device_id=self._device_id,
            width=self._width,
            height=self._height,
            fps=self._fps,
            flip_vertical=self._flip_v,
            flip_horizontal=self._flip_h,
        )
        if not self._grabber.open():
            self.get_logger().error(
                f'Kamera açılamadı: /dev/video{self._device_id}. '
                f'Cihaz bağlı mı? Docker --device flag\'i var mı?'
            )
            # Kamera açılamasa bile düğüm çalışmaya devam eder.
            # health_check watchdog'u hata bildirimi yapacak.
        else:
            actual_w, actual_h = self._grabber.actual_resolution
            actual_fps = self._grabber.actual_fps
            self.get_logger().info(
                f'Kamera açıldı: /dev/video{self._device_id} '
                f'({actual_w}x{actual_h}@{actual_fps:.0f}Hz)'
            )
            # GERÇEK DONANIM: Kameranın raporladığı çözünürlük
            # istenenden farklıysa logda uyarı göreceksiniz.
            if actual_w != self._width or actual_h != self._height:
                self.get_logger().warn(
                    f'İstenen çözünürlük {self._width}x{self._height} '
                    f'!= gerçek {actual_w}x{actual_h}. '
                    f'Kamera sürücüsü en yakın desteklenen '
                    f'çözünürlüğe yuvarlamış olabilir.'
                )

    def _setup_sitl_mode(self) -> None:
        """SITL: Gazebo bridge topic'ine abone ol veya SimFrameGrabber kur.

        Gazebo Harmonic kamera sensörü ros_gz_image bridge ile
        ROS 2 topic'ine köprülenebilir. Bridge aktifse bu topic'e
        abone olarak gelen frame'leri re-publish ederiz.
        Bridge yoksa SimFrameGrabber ile sentetik frame üretiriz.

        GERÇEK DONANIM: Bu metod gerçek donanımda çalışmaz.
        sitl_mode=false olduğunda _setup_real_camera() çağrılır.
        """
        # Gazebo bridge topic adı
        # Gazebo Harmonic'te ros_gz_image bridge varsayılan olarak
        # model adı + sensor adından topic oluşturur.
        # Eğer bridge kuruluysa buradan frame gelir.
        gz_topic = f'/drone_{self._agent_id}/gz_camera/image_raw'

        self.get_logger().info(
            f'SITL modu: Gazebo bridge topic bekleniyor: {gz_topic}. '
            f'Bridge yoksa SimFrameGrabber kullanılacak.'
        )

        # Gazebo bridge aboneliği
        self.create_subscription(
            Image,
            gz_topic,
            self._on_sim_image,
            _IMAGE_QOS,
        )

        # Yedek: SimFrameGrabber — bridge gelmezse 5 saniye sonra
        # sentetik frame üretmeye başlar.
        self._grabber = SimFrameGrabber(
            width=self._width,
            height=self._height,
        )
        self._grabber.open()

        # Bridge'den ilk mesaj gelince _sim_subscriber_active = True
        # olacak ve timer tabanlı capture_loop SimFrameGrabber'ı
        # kullanmak yerine bridge'den gelen frame'leri re-publish edecek.

    def _on_sim_image(self, msg: Image) -> None:
        """Gazebo bridge'den gelen frame'i re-publish eder.

        İlk mesaj geldiğinde SimFrameGrabber devre dışı kalır.
        """
        if not self._sim_subscriber_active:
            self._sim_subscriber_active = True
            self.get_logger().info(
                'Gazebo bridge aktif — SimFrameGrabber devre dışı.'
            )
            # SimFrameGrabber'ı kapat
            if self._grabber is not None:
                self._grabber.release()
                self._grabber = None

        self._last_frame_time = time.monotonic()

        # Frame'i olduğu gibi re-publish et
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = f'drone_{self._agent_id}_camera'
        self._image_pub.publish(msg)

        # CameraInfo ile birlikte yayınla
        self._camera_info_msg.header = msg.header
        self._info_pub.publish(self._camera_info_msg)

    # =================================================================
    # FRAME YAKALAMA DÖNGÜSÜ
    # =================================================================
    def _capture_loop(self) -> None:
        """
        Timer callback: frame yakala, Image yap ve yayınla.

        Bu callback yalnızca şu durumlarda çalışır:
        - Gerçek donanım (sitl_mode=false)
        - SITL'de Gazebo bridge yokken (SimFrameGrabber aktif)
        """
        if self._sim_subscriber_active:
            # Bridge aktif — timer'ı gereksiz çalıştırma
            return

        if self._grabber is None or not self._grabber.is_opened():
            # Kamera kapalı — yeniden açmayı dene
            # GERÇEK DONANIM: Kamera kablosu çıkıp takıldığında
            # otomatik yeniden bağlanma sağlar.
            self._try_reopen_camera()
            return

        success, frame = self._grabber.grab()

        if not success:
            return

        self._last_frame_time = time.monotonic()

        # ── NumPy → sensor_msgs/Image dönüşümü ──
        # cv_bridge kullanılmıyor (kodtabanında mevcut değil).
        # Manuel dönüşüm — sıfır kopya mümkün olduğunca.
        now = self.get_clock().now().to_msg()
        img_msg = Image()
        img_msg.header.stamp = now
        img_msg.header.frame_id = f'drone_{self._agent_id}_camera'
        img_msg.height = frame.shape[0]
        img_msg.width = frame.shape[1]
        img_msg.encoding = 'bgr8'
        img_msg.is_bigendian = False
        img_msg.step = frame.shape[1] * 3  # width * channels
        img_msg.data = frame.tobytes()

        self._image_pub.publish(img_msg)

        # CameraInfo aynı timestamp ile
        self._camera_info_msg.header.stamp = now
        self._camera_info_msg.header.frame_id = (
            f'drone_{self._agent_id}_camera'
        )
        self._info_pub.publish(self._camera_info_msg)

    def _try_reopen_camera(self) -> None:
        """Kapalı kamerayı yeniden açmayı dener.

        GERÇEK DONANIM: Arducam HQ CSI kablosu gevşerse veya
        kamera sürücüsü hata verirse bu metod otomatik olarak
        yeniden bağlanmayı dener. Her denemede 1 saniye beklenir
        (timer frekansı ile kontrol edilir).
        """
        if self._sitl_mode:
            # SITL'de SimFrameGrabber her zaman açılır
            if self._grabber is not None and not self._grabber.is_opened():
                self._grabber.open()
            return

        if self._grabber is None:
            self._grabber = FrameGrabber(
                device_id=self._device_id,
                width=self._width,
                height=self._height,
                fps=self._fps,
                flip_vertical=self._flip_v,
                flip_horizontal=self._flip_h,
            )

        if self._grabber.open():
            self.get_logger().info('Kamera yeniden bağlandı.')
        else:
            self.get_logger().warn(
                f'Kamera yeniden açılamadı: /dev/video{self._device_id}',
                throttle_duration_sec=5.0,
            )

    # =================================================================
    # SAĞLIK KONTROLÜ (1 Hz WATCHDOG)
    # =================================================================
    def _health_check(self) -> None:
        """Kamera sağlık durumunu kontrol eder.

        health_timeout_sec süresi boyunca hiç frame gelmezse
        SystemEvent.EVENT_AGENT_FAULT yayınlar.

        GERÇEK DONANIM: Bu watchdog, uçuş sırasında kamera arızasını
        (kablo gevşemesi, sürücü hatası vb.) tespit eder. Arıza
        durumunda agent_fsm'e bildirim gider ve failsafe akışı
        tetiklenebilir.
        """
        elapsed = time.monotonic() - self._last_frame_time

        if elapsed > self._health_timeout:
            self.get_logger().error(
                f'Kamera sağlık kontrolü BAŞARISIZ: '
                f'{elapsed:.1f}s boyunca frame gelmedi '
                f'(eşik: {self._health_timeout:.1f}s)',
                throttle_duration_sec=3.0,
            )
            self._pub_event(
                SystemEvent.EVENT_AGENT_FAULT,
                SystemEvent.SEVERITY_CRITICAL,
                f'camera: {elapsed:.1f}s no frame',
            )

    # =================================================================
    # CAMERAINFO MESAJI OLUŞTURMA
    # =================================================================
    def _build_camera_info_msg(self) -> CameraInfo:
        """CameraInfo mesajını bir kere oluşturur ve önbelleğe alır.

        Her frame ile birlikte yayınlanır — sadece header güncellenir.

        GERÇEK DONANIM: Kalibrasyon sonrasında fx/fy/cx/cy
        parametrelerini camera_params.yaml'da güncelleyin.
        Distortion katsayıları da eklenmelidir.
        """
        info = build_camera_info(
            width=self._width,
            height=self._height,
            fx=self._fx,
            fy=self._fy,
            cx=self._cx,
            cy=self._cy,
        )

        msg = CameraInfo()
        msg.width = info['width']
        msg.height = info['height']
        msg.distortion_model = info['distortion_model']
        msg.d = info['d']
        msg.k = info['k']
        msg.r = info['r']
        msg.p = info['p']

        return msg

    # =================================================================
    # SYSTEMEVENT YAYINI
    # =================================================================
    def _pub_event(
        self,
        event_type: int,
        severity: int,
        message: str = '',
    ) -> None:
        """SystemEvent yayınlar.

        agent_fsm_node._pub_event() deseni takip edilir.

        Args:
            event_type: SystemEvent.EVENT_* sabiti.
            severity: SystemEvent.SEVERITY_* seviyesi.
            message: İsteğe bağlı açıklama metni.
        """
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = event_type
        m.severity = severity
        m.source_agent_id = self._agent_id
        m.source_module = 'camera_driver'
        m.message = message
        self._event_pub.publish(m)

    # =================================================================
    # SHUTDOWN
    # =================================================================
    def destroy_node(self) -> None:
        """Kamera kaynağını temiz bırakır ve düğümü kapatır."""
        if self._grabber is not None:
            self._grabber.release()
            self.get_logger().info('Kamera kaynağı serbest bırakıldı.')
        super().destroy_node()


def main(args=None) -> None:
    """camera_driver entry point.

    KULLANIM:
        ros2 run swarm_perception camera_driver \\
            --ros-args -p agent_id:=1 -p sitl_mode:=false
    """
    rclpy.init(args=args)
    node = CameraDriverNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()