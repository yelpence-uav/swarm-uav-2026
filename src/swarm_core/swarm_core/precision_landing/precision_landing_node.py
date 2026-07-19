# Copyright 2026 Yelpence
"""Hassas inis dugumunu ROS 2'ye baglayan per-drone dugum."""

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

from std_msgs.msg import String
from swarm_interfaces.msg import (
    AgentSetpoint,
    AgentStatus,
    LandingZoneDetection,
    QRMissionData,
    SystemEvent,
    ZoneMap,
)

from .precision_landing_core import PrecisionLandingCore

_BEST_EFFORT_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=5,
)

_RELIABLE_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)


class PrecisionLandingNode(Node):
    """Renkli bolgeye hassas inis dugumu."""

    def __init__(self) -> None:
        super().__init__('precision_landing_node')

        self.declare_parameter('agent_id', 1)
        self.declare_parameter('control_rate_hz', 20.0)
        self.declare_parameter('approach_speed_mps', 1.5)
        self.declare_parameter('descend_speed_mps', 0.4)
        self.declare_parameter('xy_align_tol_m', 0.5)
        self.declare_parameter('touchdown_alt_m', 0.3)
        self.declare_parameter('landing_timeout_s', 45.0)

        self._agent_id = self.get_parameter('agent_id').value
        rate = self.get_parameter('control_rate_hz').value

        self._core = PrecisionLandingCore(
            approach_speed_mps=self.get_parameter('approach_speed_mps').value,
            descend_speed_mps=self.get_parameter('descend_speed_mps').value,
            xy_align_tol_m=self.get_parameter('xy_align_tol_m').value,
            touchdown_alt_m=self.get_parameter('touchdown_alt_m').value,
            landing_timeout_s=self.get_parameter('landing_timeout_s').value,
        )

        self._pose = None
        self._active = False
        self._target_color = 0
        self._zone_map = []
        self._live_zone = None

        self._started_emitted = False
        self._disarm_sent = False
        self._seq = 0

        self._setup_io()
        self.create_timer(1.0 / rate, self._on_timer)

        self.get_logger().info(
            f'precision_landing_node baslatildi: agent_id={self._agent_id}'
        )

    def _setup_io(self) -> None:
        """Abonelik ve yayincilari kurar."""
        aid = self._agent_id

        self.create_subscription(
            AgentStatus, f'/swarm/internal/drone{aid}/status',
            self._on_status, _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            ZoneMap, '/swarm/perception/zone_map',
            self._on_zone_map, _RELIABLE_QOS,
        )
        self.create_subscription(
            LandingZoneDetection, f'/drone_{aid}/perception/landing_zone',
            self._on_live_zone, _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            QRMissionData, '/swarm/internal/perception/qr_data',
            self._on_qr, _RELIABLE_QOS,
        )

        self._sp_pub = self.create_publisher(
            AgentSetpoint, f'/drone_{aid}/control/setpoint/raw',
            _BEST_EFFORT_QOS,
        )
        self._cmd_pub = self.create_publisher(
            String, f'/swarm/agent/drone{aid}/commands', _RELIABLE_QOS,
        )
        self._event_pub = self.create_publisher(
            SystemEvent, '/swarm/internal/events/system', _RELIABLE_QOS,
        )

    def _on_status(self, msg: AgentStatus) -> None:
        """Kendi pozumuzu ve aktiflik durumumuzu gunceller."""
        self._pose = (
            float(msg.pos_x), float(msg.pos_y),
            float(msg.pos_z), float(msg.heading_deg),
        )
        self._active = (msg.state == AgentStatus.STATE_PRECISION_LANDING)

    def _on_zone_map(self, msg: ZoneMap) -> None:
        """Birlestirilmis bolge haritasini listeye cevirir."""
        zones = []
        for i in range(msg.zone_count):
            zones.append({
                'color': float(msg.zone_colors[i]),
                'x': float(msg.zone_x[i]),
                'y': float(msg.zone_y[i]),
                'count': float(msg.observation_count[i]),
            })
        self._zone_map = zones

    def _on_live_zone(self, msg: LandingZoneDetection) -> None:
        """Canli kamera tespitini saklar."""
        if not msg.primary_valid:
            self._live_zone = None
            return
        self._live_zone = {
            'valid': True,
            'color': int(msg.primary_color),
            'frac_fwd': float(msg.primary_x),
            'frac_right': float(msg.primary_y),
            'fov_deg': float(msg.fov_deg),
        }

    def _on_qr(self, msg: QRMissionData) -> None:
        """Ayrilma rengini mandallar."""
        if msg.detach_active and msg.target_agent_id == self._agent_id:
            self._target_color = int(msg.detach_color)

    def _on_timer(self) -> None:
        """Saf mantigi calistirir ve ciktilari yayinlar."""
        now = self.get_clock().now().nanoseconds * 1e-9
        cmd = self._core.update(
            self._active, self._pose, self._target_color,
            self._zone_map, self._live_zone, now,
        )

        if not self._active:
            self._started_emitted = False
            self._disarm_sent = False
            return

        if not self._started_emitted:
            self._started_emitted = True
            self._emit_event(
                SystemEvent.EVENT_PRECISION_LANDING_STARTED,
                'hassas iniş başladı',
            )

        if cmd.publish:
            self._publish_setpoint(cmd)

        if cmd.disarm and not self._disarm_sent:
            self._disarm_sent = True
            out = String()
            out.data = 'disarm'
            self._cmd_pub.publish(out)
            self._emit_event(
                SystemEvent.EVENT_PRECISION_LANDING_COMPLETED,
                'hassas iniş tamamlandı: disarm',
            )

    def _publish_setpoint(self, cmd) -> None:
        """Setpoint yayinlar."""
        sp = AgentSetpoint()
        sp.stamp = self.get_clock().now().to_msg()
        sp.sequence_num = self._seq
        self._seq += 1
        sp.agent_id = self._agent_id
        sp.source = AgentSetpoint.SOURCE_POSITION_CONTROLLER
        sp.priority = AgentSetpoint.PRIORITY_POSITION
        sp.vx = cmd.vx
        sp.vy = cmd.vy
        sp.vz = cmd.vz
        sp.heading_deg = cmd.heading_deg
        sp.position_valid = False
        sp.velocity_valid = cmd.velocity_valid
        sp.heading_valid = True
        sp.max_speed_mps = self._core.approach_speed_mps
        sp.source_module = 'precision_landing'
        self._sp_pub.publish(sp)

    def _emit_event(self, event_type: int, message: str) -> None:
        """SystemEvent yayinlar."""
        ev = SystemEvent()
        ev.stamp = self.get_clock().now().to_msg()
        ev.event_type = event_type
        ev.severity = SystemEvent.SEVERITY_INFO
        ev.source_agent_id = self._agent_id
        ev.value = float(self._target_color)
        ev.source_module = 'precision_landing'
        ev.message = message
        self._event_pub.publish(ev)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PrecisionLandingNode()
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
