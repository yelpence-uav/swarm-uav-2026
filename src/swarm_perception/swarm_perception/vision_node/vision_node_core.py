# Copyright 2026 Yelpence
"""Goruntu verilerini dinler ve QR/Inis bolgelerini tespit eder."""

import math
import time
from typing import Any

import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

from sensor_msgs.msg import CameraInfo, Image

from swarm_interfaces.msg import (
    AgentStatus,
    LandingZoneDetection,
    QRMissionData,
    ZoneMap,
)

from .landing_zone_detector import ensure_bgr, LandingZoneDetector
from .qr_detector import QRDetector
from .zone_map_core import zone_offset_ned_m, ZoneMapCore

_BEST_EFFORT_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=1,
)

_RELIABLE_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)


class VisionNode(Node):
    """Goruntuleri isleyip tespit sonuclari yayinlayan dugum."""

    def __init__(self) -> None:
        super().__init__('vision_node')

        self._declare_params()
        self._setup_detectors()
        self._setup_publishers()
        self._setup_subscriptions()

        self._last_qr_time = 0.0
        self._qr_interval = 1.0 / self._qr_rate_hz

        self._last_lz_time = 0.0
        self._lz_interval = 1.0 / self._lz_rate_hz

        # Kamera içsel parametreleri (pinhole). CameraInfo GELENE KADAR None:
        # varsayılan bir odak uzaklığı uydurmak, kamera susarsa sessizce yanlış
        # ölçekte hesap yapmak demektir (bölge metrelerce yanlış yere kaydedilir,
        # dron yanlış pede iner). Kamera konuşmadan projeksiyon yapılmaz.
        self._fx: float | None = None
        self._fy: float | None = None
        self._cx: float | None = None
        self._cy: float | None = None

        self._zone_map = ZoneMapCore(
            merge_dist_m=self._zone_merge_dist_m,
            min_height_m=self._zone_min_height_m,
        )
        self._my_pose = None

        self.create_timer(
            1.0 / self._zonemap_pub_rate_hz, self._publish_zone_map
        )

        self.get_logger().info(
            f'VisionNode baslatildi: agent_id={self._agent_id}'
        )

    def _declare_params(self) -> None:
        """ROS 2 parametrelerini tanimlar ve okur."""
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('qr_processing_rate_hz', 5.0)
        self.declare_parameter('qr_min_confidence', 0.5)
        self.declare_parameter('landing_zone_rate_hz', 15.0)
        self.declare_parameter('min_zone_area_px', 500.0)
        self.declare_parameter('gaussian_blur_kernel', 5)
        self.declare_parameter('sitl_mode', False)

        self.declare_parameter('zone_merge_dist_m', 2.0)
        self.declare_parameter('zone_min_height_m', 0.5)
        self.declare_parameter('zonemap_publish_rate_hz', 2.0)

        self.declare_parameter('color_ranges.red_lower_1', [0, 100, 100])
        self.declare_parameter('color_ranges.red_upper_1', [10, 255, 255])
        self.declare_parameter('color_ranges.red_lower_2', [160, 100, 100])
        self.declare_parameter('color_ranges.red_upper_2', [180, 255, 255])
        self.declare_parameter('color_ranges.blue_lower', [100, 150, 50])
        self.declare_parameter('color_ranges.blue_upper', [140, 255, 255])

        self._agent_id = self.get_parameter('agent_id').value
        self._qr_rate_hz = self.get_parameter('qr_processing_rate_hz').value
        self._lz_rate_hz = self.get_parameter('landing_zone_rate_hz').value
        self._sitl_mode = self.get_parameter('sitl_mode').value
        self._zone_merge_dist_m = self.get_parameter(
            'zone_merge_dist_m'
        ).value
        self._zone_min_height_m = self.get_parameter(
            'zone_min_height_m'
        ).value
        self._zonemap_pub_rate_hz = self.get_parameter(
            'zonemap_publish_rate_hz'
        ).value

    def _setup_detectors(self) -> None:
        """Tespit algoritmalarini baslatir."""
        qr_conf = self.get_parameter('qr_min_confidence').value
        self._qr_detector = QRDetector(min_confidence=qr_conf)
        # QR içeriği her değiştiğinde artan sıra numarası. Aynı QR'ın ardışık
        # kareleri aynı seq'i taşır; mission_fsm bu sayede her kareyi değil,
        # yalnızca yeni okunan QR'ı işler.
        self._qr_seq_counter = 0
        self._last_qr_raw = None

        lz_config = {
            'min_zone_area_px': self.get_parameter('min_zone_area_px').value,
            'gaussian_blur_kernel': self.get_parameter(
                'gaussian_blur_kernel'
            ).value,
            'color_ranges': {
                'red_lower_1': self.get_parameter(
                    'color_ranges.red_lower_1'
                ).value,
                'red_upper_1': self.get_parameter(
                    'color_ranges.red_upper_1'
                ).value,
                'red_lower_2': self.get_parameter(
                    'color_ranges.red_lower_2'
                ).value,
                'red_upper_2': self.get_parameter(
                    'color_ranges.red_upper_2'
                ).value,
                'blue_lower': self.get_parameter(
                    'color_ranges.blue_lower'
                ).value,
                'blue_upper': self.get_parameter(
                    'color_ranges.blue_upper'
                ).value,
            },
        }
        self._lz_detector = LandingZoneDetector(config=lz_config)

    def _setup_publishers(self) -> None:
        """Publisher'lari olusturur."""
        self._qr_pub = self.create_publisher(
            QRMissionData,
            '/swarm/internal/perception/qr_data',
            _RELIABLE_QOS,
        )

        self._lz_pub = self.create_publisher(
            LandingZoneDetection,
            f'/drone_{self._agent_id}/perception/landing_zone',
            _BEST_EFFORT_QOS,
        )

        self._zonemap_pub = self.create_publisher(
            ZoneMap,
            '/swarm/perception/zone_map',
            _RELIABLE_QOS,
        )

    def _setup_subscriptions(self) -> None:
        """Abonelikleri kurar."""
        self.create_subscription(
            Image,
            f'/drone_{self._agent_id}/camera/image_raw',
            self._image_callback,
            _BEST_EFFORT_QOS,
        )

        self.create_subscription(
            CameraInfo,
            f'/drone_{self._agent_id}/camera/camera_info',
            self._camera_info_callback,
            _BEST_EFFORT_QOS,
        )

        self.create_subscription(
            AgentStatus,
            f'/swarm/internal/drone{self._agent_id}/status',
            self._on_status,
            _BEST_EFFORT_QOS,
        )

    def _on_status(self, msg: AgentStatus) -> None:
        """Kendi konum verimizi saklar."""
        self._my_pose = (
            float(msg.pos_x),
            float(msg.pos_y),
            float(msg.pos_z),
            float(msg.heading_deg),
        )

    def _camera_info_callback(self, msg: CameraInfo) -> None:
        """Kamera içsel parametrelerini (pinhole) günceller."""
        if len(msg.k) == 9:
            self._fx = msg.k[0]
            self._fy = msg.k[4]
            self._cx = msg.k[2]
            self._cy = msg.k[5]

    def _image_callback(self, msg: Image) -> None:
        """Görüntü karesini isler."""
        now = time.monotonic()
        run_qr = (now - self._last_qr_time) >= self._qr_interval
        run_lz = (now - self._last_lz_time) >= self._lz_interval

        if not run_qr and not run_lz:
            return

        frame = np.ndarray(
            shape=(msg.height, msg.width, 3),
            dtype=np.uint8,
            buffer=msg.data,
        )

        # Dedektörler BGR bekler; kamera rgb8 yayınlarsa kırmızı/mavi kanalları
        # yer değiştirir ve pedler birbirinin yerine etiketlenir.
        enc = msg.encoding
        if enc not in ('rgb8', 'bgr8'):
            self.get_logger().warn(
                f'beklenmeyen görüntü formatı: {enc} '
                '(bgr8/rgb8 bekleniyor) — renk tespiti güvenilmez',
                throttle_duration_sec=10.0,
            )
        frame = ensure_bgr(frame, enc)

        if run_qr:
            self._process_qr(frame, msg.header.stamp)
            self._last_qr_time = now

        if run_lz:
            self._process_lz(frame, msg.header.stamp)
            self._last_lz_time = now

    def _process_qr(self, frame: np.ndarray, stamp: Any) -> None:
        """QR kodlarini bulup yayinlar."""
        results = self._qr_detector.detect(frame)

        for res in results:
            msg = QRMissionData()
            msg.stamp = stamp
            msg.detector_agent_id = self._agent_id
            msg.detected = True
            msg.decoded = True
            msg.valid = res.get('valid', False)
            msg.raw_text = res.get('raw_text', '')
            msg.error_message = res.get('error_message', '')
            msg.confidence = 1.0

            msg.image_x = res.get('image_x', 0.0)
            msg.image_y = res.get('image_y', 0.0)
            msg.image_width = res.get('image_width', 0.0)
            msg.image_height = res.get('image_height', 0.0)

            msg.team_id = res.get('team_id', '')
            msg.qr_id = res.get('qr_id', 0)
            raw = res.get('raw_text', '')
            if res.get('valid', False) and raw != self._last_qr_raw:
                self._qr_seq_counter += 1
                self._last_qr_raw = raw
            msg.qr_seq = self._qr_seq_counter
            msg.next_qr = res.get('next_qr', 0)
            msg.formation_type = res.get('formation_type', 0)
            msg.spacing_m = res.get('spacing_m', 0.0)
            msg.altitude_agl_m = res.get('altitude_agl_m', 0.0)
            msg.pitch_deg = res.get('pitch_deg', 0.0)
            msg.roll_deg = res.get('roll_deg', 0.0)
            msg.yaw_deg = res.get('yaw_deg', 0.0)
            msg.wait_s = res.get('wait_s', 0.0)
            msg.target_agent_id = res.get('target_agent_id', 0)
            msg.detach_color = res.get('detach_color', 0)
            msg.detach_wait_s = res.get('detach_wait_s', 0.0)

            msg.formation_active = res.get('formation_active', False)
            msg.target_active = res.get('target_active', False)
            msg.maneuver_active = res.get('maneuver_active', False)
            msg.altitude_active = res.get('altitude_active', False)
            msg.detach_active = res.get('detach_active', False)
            msg.complete_mission = res.get('complete_mission', False)

            self._qr_pub.publish(msg)

    def _process_lz(self, frame: np.ndarray, stamp: Any) -> None:
        """İniş bölgesini işler ve sonuçları yayınlar."""
        zones = self._lz_detector.detect(frame)

        msg = LandingZoneDetection()
        msg.stamp = stamp
        msg.detector_agent_id = self._agent_id
        msg.zone_detected = len(zones) > 0
        msg.zone_count = len(zones)

        # Bölgenin metrik konumu için İKİ girdi de zorunludur:
        #   - poz (irtifa/heading): aynı piksel sapması 5 m'de 1 m, 20 m'de 4 m eder
        #   - kamera odak uzaklığı: piksel→metre kuru odak uzaklığından gelir
        # Biri eksikken konum üretmek, uydurma bir kurla bölgeyi metrelerce yanlış
        # yere kaydetmektir (dron yanlış pede iner). Tespit yine duyurulur; yalnız
        # konum üretilmez ve eksiklik logda görünür.
        if not msg.zone_detected:
            self._lz_pub.publish(msg)
            return
        if self._my_pose is None or self._fx is None:
            self.get_logger().warn(
                'bölge konumu üretilemiyor: '
                f'poz={"VAR" if self._my_pose else "YOK"} '
                f'kamera_odak={"VAR" if self._fx else "YOK (CameraInfo gelmedi)"}',
                throttle_duration_sec=5.0,
            )
            self._lz_pub.publish(msg)
            return

        px, py, pz, heading_deg = self._my_pose
        height_m = max(-pz, self._zone_min_height_m)
        h_px, w_px = frame.shape[0], frame.shape[1]

        for z in zones:
            ned_x, ned_y = zone_offset_ned_m(
                float(z['image_x']) * w_px, float(z['image_y']) * h_px,
                self._fx, self._fy, self._cx, self._cy,
                height_m, heading_deg,
            )
            msg.zone_colors.append(z['color'])
            msg.zone_x.append(float(ned_x))
            msg.zone_y.append(float(ned_y))
            msg.zone_z.append(float(height_m))
            msg.zone_confidence.append(z['confidence'])
            # Yarıçap da aynı pinhole ölçeğiyle metreye çevrilir.
            msg.zone_radius_m.append(
                float(height_m * z['radius_px'] / self._fx)
            )

        msg.primary_valid = True
        msg.primary_color = msg.zone_colors[0]
        msg.primary_x = msg.zone_x[0]
        msg.primary_y = msg.zone_y[0]
        msg.primary_z = msg.zone_z[0]
        msg.primary_confidence = msg.zone_confidence[0]
        msg.primary_radius_m = msg.zone_radius_m[0]

        msg.image_x = zones[0]['image_x']
        msg.image_y = zones[0]['image_y']
        # Teşhis alanı: fiilen kullanılan yatay görüş açısı, odak uzaklığından
        # türetilir (sabit bir varsayım değil).
        msg.fov_deg = float(
            math.degrees(2.0 * math.atan(w_px / (2.0 * self._fx)))
        )

        self._lz_pub.publish(msg)

        # Kalıcı haritaya yaz: göreli ofset + kendi konumumuz = global NED.
        for color, dx, dy, conf in zip(
            msg.zone_colors, msg.zone_x, msg.zone_y, msg.zone_confidence
        ):
            self._zone_map.add(
                int(color), px + dx, py + dy, pz + height_m, conf
            )

    def _publish_zone_map(self) -> None:
        """Birlestirilmis bolge haritasini yayinlar."""
        zones = self._zone_map.zones
        msg = ZoneMap()
        msg.stamp = self.get_clock().now().to_msg()
        msg.publisher_agent_id = self._agent_id
        msg.zone_count = len(zones)
        for z in zones:
            msg.zone_colors.append(int(z['color']))
            msg.zone_x.append(float(z['x']))
            msg.zone_y.append(float(z['y']))
            msg.zone_z.append(float(z['z']))
            msg.observation_count.append(int(z['count']))
            msg.zone_confidence.append(float(z['confidence']))
        self._zonemap_pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
