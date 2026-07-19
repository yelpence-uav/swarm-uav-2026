# Copyright 2026 Yelpence
"""ROS 2 dogrusal rota planlama dugumu."""

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_interfaces.msg import FormationCommand
from .linear_trajectory import LinearTrajectoryPlanner

_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


class PathPlannerNode(Node):
    """Dogrusal yoringe ureterek FormationCommand yayinlayan dugum."""

    def __init__(self) -> None:
        super().__init__('path_planner_node')

        self.declare_parameter('max_speed_mps', 3.0)
        self.declare_parameter('control_rate_hz', 5.0)

        self._max_speed_mps = float(
            self.get_parameter('max_speed_mps').value
        )
        self._control_rate_hz = float(
            self.get_parameter('control_rate_hz').value
        )

        self._planner = LinearTrajectoryPlanner(
            max_speed_mps=self._max_speed_mps,
            control_rate_hz=self._control_rate_hz
        )

        self._waypoints: list[tuple[float, float, float]] = []
        self._current_cmd = None
        self._last_pos = None

        self.create_subscription(
            FormationCommand,
            '/swarm/path_planning/target',
            self._on_target_received,
            _RELIABLE_QOS
        )

        self._cmd_pub = self.create_publisher(
            FormationCommand,
            '/swarm/internal/formation/target',
            _RELIABLE_QOS
        )

        self._timer = self.create_timer(
            1.0 / self._control_rate_hz,
            self._timer_callback
        )

        self.get_logger().info('Path Planner Node baslatildi.')

    def _on_target_received(self, msg: FormationCommand) -> None:
        """Yeni bir hedef rota komutu alindiginda tetiklenir."""
        if self._last_pos is None:
            self._last_pos = (msg.center_x, msg.center_y, msg.center_z)

        target_pos = (msg.center_x, msg.center_y, msg.center_z)

        self._waypoints = self._planner.generate_waypoints(
            self._last_pos, target_pos
        )
        self._current_cmd = msg
        self.get_logger().info(
            f'Yeni rota olusturuldu: {len(self._waypoints)} adim.'
        )

    def _timer_callback(self) -> None:
        """Duzenli araliklarla sonraki ara noktayi yayinlar."""
        if not self._waypoints or self._current_cmd is None:
            return

        next_pos = self._waypoints.pop(0)
        self._last_pos = next_pos

        out_msg = FormationCommand()
        out_msg.stamp = self.get_clock().now().to_msg()
        out_msg.sequence_num = self._current_cmd.sequence_num
        out_msg.formation_type = self._current_cmd.formation_type
        out_msg.center_x = float(next_pos[0])
        out_msg.center_y = float(next_pos[1])
        out_msg.center_z = float(next_pos[2])
        out_msg.heading_deg = float(self._current_cmd.heading_deg)
        out_msg.spacing_m = float(self._current_cmd.spacing_m)
        out_msg.use_current_centroid = self._current_cmd.use_current_centroid
        out_msg.use_current_altitude = self._current_cmd.use_current_altitude
        out_msg.rotate_towards_target = (
            self._current_cmd.rotate_towards_target
        )
        out_msg.hold_after_reached = self._current_cmd.hold_after_reached
        out_msg.agent_ids = self._current_cmd.agent_ids
        out_msg.offset_x = self._current_cmd.offset_x
        out_msg.offset_y = self._current_cmd.offset_y
        out_msg.offset_z = self._current_cmd.offset_z
        out_msg.position_tolerance_m = float(
            self._current_cmd.position_tolerance_m
        )
        out_msg.heading_tolerance_deg = float(
            self._current_cmd.heading_tolerance_deg
        )
        out_msg.timeout_sec = float(self._current_cmd.timeout_sec)
        out_msg.max_speed_mps = float(self._current_cmd.max_speed_mps)
        out_msg.source_module = 'path_planning'

        self._cmd_pub.publish(out_msg)

        if not self._waypoints:
            self.get_logger().info('Rota tamamlandi, hedefe ulasildi.')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PathPlannerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:  # noqa: BLE001
            pass


if __name__ == '__main__':
    main()
