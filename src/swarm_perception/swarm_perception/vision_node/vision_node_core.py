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
vision_node_core.py.

Ana Vision ROS 2 Düğümü.
Görüntü verilerini dinler, qr_detector ve landing_zone_detector modüllerini
çalıştırarak sonuçları swarm_interfaces formatında yayınlar.
"""

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
from swarm_interfaces.msg import LandingZoneDetection, QRMissionData

from .landing_zone_detector import LandingZoneDetector
from .qr_detector import QRDetector

# QoS Profilleri
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
    """Görüntüleri işleyip tespit sonuçları yayınlayan düğüm."""

    def __init__(self) -> None:
        """Initialize."""
        super().__init__('vision_node')

        self._declare_params()
        self._setup_detectors()
        self._setup_publishers()
        self._setup_subscriptions()

        # Performans Throttling
        self._last_qr_time = 0.0
        self._qr_interval = 1.0 / self._qr_rate_hz

        self._last_lz_time = 0.0
        self._lz_interval = 1.0 / self._lz_rate_hz

        # Kamera Intrinsics (Pinhole) - CameraInfo'dan güncellenecek
        self._fx = 1108.5
        self._fy = 1108.5

        self.get_logger().info(
            f'VisionNode başlatıldı: agent_id={self._agent_id}, '
            f'QR Rate: {self._qr_rate_hz}Hz, LZ Rate: {self._lz_rate_hz}Hz'
        )

    def _declare_params(self) -> None:
        """ROS 2 parametrelerini tanımlar ve okur."""
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('qr_processing_rate_hz', 5.0)
        self.declare_parameter('qr_min_confidence', 0.5)
        self.declare_parameter('landing_zone_rate_hz', 15.0)
        self.declare_parameter('min_zone_area_px', 500.0)
        self.declare_parameter('gaussian_blur_kernel', 5)
        self.declare_parameter('sitl_mode', False)

        # Renk Eşikleri
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

    def _setup_detectors(self) -> None:
        """Saf Python tespit algoritmalarını başlatır."""
        qr_conf = self.get_parameter('qr_min_confidence').value
        self._qr_detector = QRDetector(min_confidence=qr_conf)

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
        """Dışa aktarılacak tespit kanallarını ayarlar."""
        # QR Mission Data -> Sürü geneli, GCS ve Görev FSM'sine
        self._qr_pub = self.create_publisher(
            QRMissionData,
            '/swarm/internal/perception/qr_data',
            _RELIABLE_QOS,
        )

        # Landing Zone Data -> Lokal hassas iniş algoritmasına
        self._lz_pub = self.create_publisher(
            LandingZoneDetection,
            f'/drone_{self._agent_id}/perception/landing_zone',
            _BEST_EFFORT_QOS,
        )

    def _setup_subscriptions(self) -> None:
        """Kamera kanallarını dinlemeye başlar."""
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

    def _camera_info_callback(self, msg: CameraInfo) -> None:
        """Kamera fokal uzaklık (Pinhole) parametrelerini günceller."""
        if len(msg.k) == 9:
            # K matrisi: [fx, 0, cx, 0, fy, cy, 0, 0, 1]
            self._fx = msg.k[0]
            self._fy = msg.k[4]

    def _image_callback(self, msg: Image) -> None:
        """Gelen çerçeveyi işler ve frekanslarına göre böler."""
        now = time.monotonic()
        run_qr = (now - self._last_qr_time) >= self._qr_interval
        run_lz = (now - self._last_lz_time) >= self._lz_interval

        if not run_qr and not run_lz:
            return

        # sensor_msgs/Image -> numpy matrisi
        # cv_bridge kullanmadan sıfır kopya dönüşüm.
        frame = np.ndarray(
            shape=(msg.height, msg.width, 3),
            dtype=np.uint8,
            buffer=msg.data,
        )

        if run_qr:
            self._process_qr(frame, msg.header.stamp)
            self._last_qr_time = now

        if run_lz:
            self._process_lz(frame, msg.header.stamp)
            self._last_lz_time = now

    def _process_qr(self, frame: np.ndarray, stamp: Any) -> None:
        """QR kodunu işler ve sonuçları yayınlar."""
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
            msg.confidence = 1.0  # pyzbar güven skoru vermez

            # Bounding box
            msg.image_x = res.get('image_x', 0.0)
            msg.image_y = res.get('image_y', 0.0)
            msg.image_width = res.get('image_width', 0.0)
            msg.image_height = res.get('image_height', 0.0)

            # Parsed Data
            msg.team_id = res.get('team_id', '')
            msg.qr_id = res.get('qr_id', 0)
            msg.qr_seq = res.get('qr_seq', 0)
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

            # Active Flags
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
        msg.fov_deg = 60.0  # Varsayılan FOV

        if not msg.zone_detected:
            self._lz_pub.publish(msg)
            return

        # Pinhole formülüyle yaklaşık metrik dönüşüm:
        # X_m = (X_px - w/2) * Z_m / f_x
        # İrtifa (Z_m) burada bilinmiyor, göreceli değer basıyoruz
        # Ancak precision_landing.py gerçek irtifa ile çarparak kullanır.
        # Burada sadece birim düzleme göre (Z=1m) yansıtıyoruz.
        for z in zones:
            msg.zone_colors.append(z['color'])
            # Normalized [-0.5, 0.5] pixel coordinate
            nx = z['image_x'] - 0.5
            ny = z['image_y'] - 0.5

            # NED frame'de x ileri, y sağdır.
            # Görüntüde y aşağı doğrudur, NED x ekseniyle örtüşür.
            msg.zone_x.append(float(ny))
            msg.zone_y.append(float(nx))
            msg.zone_z.append(1.0)
            msg.zone_confidence.append(z['confidence'])

            # Normalize edilmiş yarıçap
            msg.zone_radius_m.append(z['radius_px'] / frame.shape[1])

        # En iyi bölge seçimi (Şimdilik ilk bölge)
        msg.primary_valid = True
        msg.primary_color = msg.zone_colors[0]
        msg.primary_x = msg.zone_x[0]
        msg.primary_y = msg.zone_y[0]
        msg.primary_z = msg.zone_z[0]
        msg.primary_confidence = msg.zone_confidence[0]
        msg.primary_radius_m = msg.zone_radius_m[0]

        msg.image_x = zones[0]['image_x']
        msg.image_y = zones[0]['image_y']

        self._lz_pub.publish(msg)


def main(args=None) -> None:
    """Entry point."""
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
