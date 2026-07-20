# Copyright 2026 Yelpence
"""Kameradan goruntu yakalayan ve ROS 2 topic'lerine yayinlayan dugum."""

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

from .camera_info_builder import build_camera_info
from .frame_grabber import FrameGrabber, SimFrameGrabber

_IMAGE_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=1,
)


class CameraDriverNode(Node):
    """Kamera surucu ROS 2 dugumu."""

    def __init__(self) -> None:
        super().__init__('camera_driver')

        self._declare_params()
        self._setup_publishers()
        self._camera_info_msg = self._build_camera_info_msg()

        self._grabber = None
        self._sim_subscriber_active = False
        self._last_frame_time = time.monotonic()

        if self._sitl_mode:
            self._setup_sitl_mode()
        else:
            self._setup_real_camera()

        if not self._sim_subscriber_active:
            self._capture_timer = self.create_timer(
                1.0 / self._fps, self._capture_loop,
            )

        self._health_timer = self.create_timer(
            1.0, self._health_check,
        )

        self.get_logger().info(
            f'CameraDriverNode baslatildi: agent_id={self._agent_id}'
        )

    def _declare_params(self) -> None:
        """ROS 2 parametrelerini tanimlar ve okur."""
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('device_id', 0)
        self.declare_parameter('width', 1280)
        self.declare_parameter('height', 720)
        self.declare_parameter('fps', 15.0)
        self.declare_parameter('sitl_mode', False)
        self.declare_parameter('flip_vertical', False)
        self.declare_parameter('flip_horizontal', False)
        self.declare_parameter('health_timeout_sec', 3.0)

        self.declare_parameter('fx', 1108.5)
        self.declare_parameter('fy', 1108.5)
        self.declare_parameter('cx', 640.0)
        self.declare_parameter('cy', 360.0)
        self.declare_parameter('fov_horizontal_rad', 1.047)

        self._agent_id = self.get_parameter('agent_id').value
        self._device_id = self.get_parameter('device_id').value
        self._width = self.get_parameter('width').value
        self._height = self.get_parameter('height').value
        self._fps = self.get_parameter('fps').value
        self._sitl_mode = self.get_parameter('sitl_mode').value
        self._flip_v = self.get_parameter('flip_vertical').value
        self._flip_h = self.get_parameter('flip_horizontal').value
        self._health_timeout = self.get_parameter(
            'health_timeout_sec'
        ).value

        self._fx = self.get_parameter('fx').value
        self._fy = self.get_parameter('fy').value
        self._cx = self.get_parameter('cx').value
        self._cy = self.get_parameter('cy').value
        self._fov_h_rad = self.get_parameter(
            'fov_horizontal_rad'
        ).value

    def _setup_publishers(self) -> None:
        """Publisher'lari olusturur."""
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
        self._event_pub = self.create_publisher(
            SystemEvent,
            '/swarm/internal/events/system',
            10,
        )

    def _setup_real_camera(self) -> None:
        """Gercek donanim kamerasini baslatir."""
        self._grabber = FrameGrabber(
            device_id=self._device_id,
            width=self._width,
            height=self._height,
            fps=self._fps,
            flip_vertical=self._flip_v,
            flip_horizontal=self._flip_h,
        )
        if not self._grabber.open_camera():
            self.get_logger().error(
                f'Kamera acilamadi: /dev/video{self._device_id}'
            )
        else:
            actual_w, actual_h = self._grabber.actual_resolution
            actual_fps = self._grabber.actual_fps
            self.get_logger().info(
                f'Kamera acildi: /dev/video{self._device_id} '
                f'({actual_w}x{actual_h}@{actual_fps:.0f}Hz)'
            )
            if actual_w != self._width or actual_h != self._height:
                self.get_logger().warn(
                    f'Cozunurluk farkli: gercek={actual_w}x{actual_h}'
                )

    def _setup_sitl_mode(self) -> None:
        """SITL modunu baslatir."""
        gz_topic = f'/drone_{self._agent_id}/gz_camera/image_raw'

        self.get_logger().info(
            f'SITL: Gazebo bridge bekleniyor: {gz_topic}'
        )

        self.create_subscription(
            Image,
            gz_topic,
            self._on_sim_image,
            _IMAGE_QOS,
        )

        self._grabber = SimFrameGrabber(
            width=self._width,
            height=self._height,
        )
        self._grabber.open_camera()

    def _on_sim_image(self, msg: Image) -> None:
        """Gazebo bridge'den gelen goruntuyu re-publish eder."""
        if not self._sim_subscriber_active:
            self._sim_subscriber_active = True
            self.get_logger().info(
                'Gazebo bridge aktif, SimFrameGrabber kapatildi.'
            )
            if self._grabber is not None:
                self._grabber.release()
                self._grabber = None

        self._last_frame_time = time.monotonic()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = f'drone_{self._agent_id}_camera'
        self._image_pub.publish(msg)

        self._camera_info_msg.header = msg.header
        self._info_pub.publish(self._camera_info_msg)

    def _capture_loop(self) -> None:
        """Kameradan goruntu yakalar ve yayinlar."""
        if self._sim_subscriber_active:
            return

        if self._grabber is None or not self._grabber.is_opened():
            self._try_reopen_camera()
            return

        success, frame = self._grabber.grab()
        if not success:
            return

        self._last_frame_time = time.monotonic()
        now = self.get_clock().now().to_msg()
        img_msg = Image()
        img_msg.header.stamp = now
        img_msg.header.frame_id = f'drone_{self._agent_id}_camera'
        img_msg.height = frame.shape[0]
        img_msg.width = frame.shape[1]
        img_msg.encoding = 'bgr8'
        img_msg.is_bigendian = False
        img_msg.step = frame.shape[1] * 3
        img_msg.data = frame.tobytes()

        self._image_pub.publish(img_msg)

        self._camera_info_msg.header.stamp = now
        self._camera_info_msg.header.frame_id = (
            f'drone_{self._agent_id}_camera'
        )
        self._info_pub.publish(self._camera_info_msg)

    def _try_reopen_camera(self) -> None:
        """Kamerayi yeniden baglamayi dener."""
        if self._sitl_mode:
            if self._grabber is not None and not self._grabber.is_opened():
                self._grabber.open_camera()
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

        if self._grabber.open_camera():
            self.get_logger().info('Kamera yeniden baglandi.')
        else:
            self.get_logger().warn(
                f'Kamera acilamadi: /dev/video{self._device_id}',
                throttle_duration_sec=5.0,
            )

    def _health_check(self) -> None:
        """Watchdog saglik kontrolu yapar."""
        elapsed = time.monotonic() - self._last_frame_time

        if elapsed > self._health_timeout:
            self.get_logger().error(
                f'Kamera saglik kontrolu basarisiz: {elapsed:.1f}s'
            )
            self._pub_event(
                SystemEvent.EVENT_AGENT_FAULT,
                SystemEvent.SEVERITY_CRITICAL,
                f'camera: {elapsed:.1f}s no frame',
            )

    def _build_camera_info_msg(self) -> CameraInfo:
        """Önbellek icin CameraInfo hazirlar."""
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

    def _pub_event(
        self, event_type: int, severity: int, message: str = '',
    ) -> None:
        """Sistem olayi yayinlar."""
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = event_type
        m.severity = severity
        m.source_agent_id = self._agent_id
        m.source_module = 'camera_driver'
        m.message = message
        self._event_pub.publish(m)

    def destroy_node(self) -> None:
        """Kamerayi serbest birakir."""
        if self._grabber is not None:
            self._grabber.release()
            self.get_logger().info('Kamera birakildi.')
        super().destroy_node()


def main(args=None) -> None:
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
