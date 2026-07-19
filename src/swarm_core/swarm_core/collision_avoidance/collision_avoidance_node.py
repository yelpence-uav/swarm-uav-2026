# Copyright 2026 Yelpence
"""Hiz tabanli carpisma onleme filtresi."""

import copy

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_interfaces.msg import (
    AgentSetpoint,
    AgentStatus,
    FormationCommand,
    NeighborInfo,
)

from .ca_core import CaParams, CollisionAvoidanceCore, NeighborObs

_AVOIDANCE_DISI_STATELER = frozenset({
    AgentStatus.STATE_DETACHED,
    AgentStatus.STATE_PRECISION_LANDING,
    AgentStatus.STATE_LANDED,
    AgentStatus.STATE_FAILSAFE,
})

_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_BEST_EFFORT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


class CollisionAvoidanceNode(Node):
    """Hiz tabanli carpisma onleme filtre node'u."""

    def __init__(self) -> None:
        super().__init__('collision_avoidance')

        self._declare_params()

        self._raw = None
        self._raw_stamp = 0.0

        self._cur_z = 0.0
        self._cur_vx = 0.0
        self._cur_vy = 0.0
        self._cur_vz = 0.0
        self._pos_ok = False

        self._neighbors: dict[int, NeighborInfo] = {}
        self._neighbor_rx: dict[int, float] = {}
        self._neighbor_subs = {}

        self._sequence_num = 0

        self._n_passthrough = 0
        self._n_avoid = 0
        self._n_skip_state = 0
        self._n_skip_stale = 0
        self._n_gate_alt = 0
        self._last_active_log = 0.0

        self._ca = CollisionAvoidanceCore(CaParams(
            dt=1.0 / self._publish_rate_hz,
            d0=self._d0_m,
            hard=self._hard_m,
            r_min=self._r_min_m,
            f_sat=self._f_sat,
            c_dead=self._c_dead_mps,
            c_ref=self._c_ref_mps,
            c_damp=self._c_damp,
            damp_band=self._damp_band_m,
            k_tan=self._k_tan,
            v_max=self._v_max_mps,
            slew_normal=self._slew_normal,
            slew_emergency=self._slew_emergency,
        ))

        self._setup_io()

        self._timer = self.create_timer(
            1.0 / self._publish_rate_hz, self._tick,
        )
        self.create_timer(5.0, self._diag_tick)

        self.get_logger().info(
            f'collision_avoidance baslatildi: agent_id={self._agent_id}'
        )

    def _declare_params(self) -> None:
        """ROS 2 parametrelerini tanimlar ve okur."""
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('neighbor_ids', [0])
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('raw_timeout_s', 0.5)
        self.declare_parameter('neighbor_stale_ms', 500)
        self.declare_parameter('neighbor_rx_stale_s', 0.5)
        self.declare_parameter('altitude_gate_m', 3.0)
        self.declare_parameter('d0_m', 4.5)
        self.declare_parameter('hard_m', 2.0)
        self.declare_parameter('r_min_m', 1.5)
        self.declare_parameter('f_sat', 6.0)
        self.declare_parameter('c_dead_mps', 0.2)
        self.declare_parameter('c_ref_mps', 1.0)
        self.declare_parameter('c_damp', 0.7)
        self.declare_parameter('damp_band_m', 0.5)
        self.declare_parameter('k_tan', 0.9)
        self.declare_parameter('v_max_mps', 4.0)
        self.declare_parameter('slew_normal_mps2', 4.0)
        self.declare_parameter('slew_emergency_mps2', 30.0)

        gp = self.get_parameter
        self._agent_id = int(gp('agent_id').value)
        self._static_neighbor_ids = [
            int(x) for x in gp('neighbor_ids').value if int(x) > 0
        ]
        self._publish_rate_hz = float(gp('publish_rate_hz').value)
        self._raw_timeout_s = float(gp('raw_timeout_s').value)
        self._neighbor_stale_ms = int(gp('neighbor_stale_ms').value)
        self._neighbor_rx_stale_s = float(gp('neighbor_rx_stale_s').value)
        self._altitude_gate_m = float(gp('altitude_gate_m').value)
        self._d0_m = float(gp('d0_m').value)
        self._hard_m = float(gp('hard_m').value)
        self._r_min_m = float(gp('r_min_m').value)
        self._f_sat = float(gp('f_sat').value)
        self._c_dead_mps = float(gp('c_dead_mps').value)
        self._c_ref_mps = float(gp('c_ref_mps').value)
        self._c_damp = float(gp('c_damp').value)
        self._damp_band_m = float(gp('damp_band_m').value)
        self._k_tan = float(gp('k_tan').value)
        self._v_max_mps = float(gp('v_max_mps').value)
        self._slew_normal = float(gp('slew_normal_mps2').value)
        self._slew_emergency = float(gp('slew_emergency_mps2').value)

        if not 1 <= self._agent_id <= 254:
            raise ValueError(f'agent_id 1-254 olmalı: {self._agent_id}')
        if self._publish_rate_hz <= 0.0:
            raise ValueError('publish_rate_hz pozitif olmalı')
        if not (self._r_min_m < self._hard_m < self._d0_m):
            raise ValueError('r_min < hard < d0 olmalı')

    def _setup_io(self) -> None:
        """Yayıncıları ve aboneleri oluşturur."""
        self._setpoint_pub = self.create_publisher(
            AgentSetpoint,
            f'/drone_{self._agent_id}/control/setpoint',
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            AgentSetpoint,
            f'/drone_{self._agent_id}/control/setpoint/raw',
            self._on_raw_setpoint,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            AgentStatus,
            f'/swarm/agent/drone{self._agent_id}/telemetry',
            self._on_agent_status,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            FormationCommand,
            '/swarm/public/formation/target',
            self._on_formation_command,
            _RELIABLE_QOS,
        )
        self._ensure_neighbor_subs(self._static_neighbor_ids)

    def _ensure_neighbor_subs(self, agent_ids) -> None:
        """Komşu telemetri aboneliklerini garanti eder."""
        for nid in agent_ids:
            nid = int(nid)
            if nid == self._agent_id or nid <= 0 or nid in self._neighbor_subs:
                continue
            topic = (
                f'/swarm/agent/drone{self._agent_id}/neighbor/drone{nid}'
            )
            self._neighbor_subs[nid] = self.create_subscription(
                NeighborInfo,
                topic,
                lambda m, n=nid: self._on_neighbor(n, m),
                _BEST_EFFORT_QOS,
            )
            self.get_logger().info(f'NeighborInfo aboneliği: drone{nid}')

    def _on_raw_setpoint(self, msg: AgentSetpoint) -> None:
        self._raw = msg
        self._raw_stamp = self.get_clock().now().nanoseconds * 1e-9

    def _on_agent_status(self, msg: AgentStatus) -> None:
        self._cur_z = float(msg.pos_z)
        self._cur_vx = float(msg.vel_x)
        self._cur_vy = float(msg.vel_y)
        self._cur_vz = float(msg.vel_z)
        self._pos_ok = bool(msg.xy_valid and msg.z_valid)

    def _on_formation_command(self, msg: FormationCommand) -> None:
        self._ensure_neighbor_subs(msg.agent_ids)

    def _on_neighbor(self, nid: int, msg: NeighborInfo) -> None:
        self._neighbors[nid] = msg
        self._neighbor_rx[nid] = self.get_clock().now().nanoseconds * 1e-9

    def _gather_obstacles(self, now: float) -> list[NeighborObs]:
        """Geçerli komşulardan gözlem listesi toplar."""
        obs: list[NeighborObs] = []
        for nid, info in self._neighbors.items():
            if not info.link_active:
                self._n_skip_stale += 1
                continue
            if info.data_age_ms > self._neighbor_stale_ms:
                self._n_skip_stale += 1
                continue
            rx = self._neighbor_rx.get(nid, 0.0)
            if now - rx > self._neighbor_rx_stale_s:
                self._n_skip_stale += 1
                continue
            if info.neighbor_state in _AVOIDANCE_DISI_STATELER:
                self._n_skip_state += 1
                continue
            obs.append(NeighborObs(
                rel_x=float(info.relative_x),
                rel_y=float(info.relative_y),
                rel_z=float(info.relative_z),
                rel_vx=float(info.relative_vx),
                rel_vy=float(info.relative_vy),
                rel_vz=float(info.relative_vz),
                distance=float(info.distance_m),
            ))
        return obs

    def _tick(self) -> None:
        """ROS timer tetiklemesiyle ana döngüyü işletir."""
        try:
            self._tick_inner()
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(
                f'_tick hata: {type(e).__name__}: {e}'
            )

    def _tick_inner(self) -> None:
        raw = self._raw
        if raw is None:
            return
        now = self.get_clock().now().nanoseconds * 1e-9
        if now - self._raw_stamp > self._raw_timeout_s:
            return

        if (raw.priority >= AgentSetpoint.PRIORITY_FAILSAFE
                or raw.hold_position or raw.land_now or raw.rtl_now):
            self._relay(raw)
            return

        if not self._pos_ok:
            self._relay(raw)
            return

        if (self._altitude_gate_m > 0.0
                and (-self._cur_z) < self._altitude_gate_m):
            self._n_gate_alt += 1
            self._relay(raw)
            return

        obstacles = self._gather_obstacles(now)

        base = (
            (float(raw.vx), float(raw.vy), float(raw.vz))
            if raw.velocity_valid else (0.0, 0.0, 0.0)
        )
        v_cmd, risk = self._ca.compute(base, obstacles)

        if not risk:
            self._relay(raw, reset_core=False)
            return

        out = copy.deepcopy(raw)
        out.stamp = self.get_clock().now().to_msg()
        out.sequence_num = self._sequence_num
        self._sequence_num += 1
        out.source = AgentSetpoint.SOURCE_COLLISION_AVOIDANCE
        out.priority = AgentSetpoint.PRIORITY_COLLISION_AVOIDANCE
        out.position_valid = False
        out.vx = float(v_cmd[0])
        out.vy = float(v_cmd[1])
        out.vz = float(v_cmd[2])
        out.velocity_valid = True
        out.acceleration_valid = False
        out.max_speed_mps = self._v_max_mps
        out.source_module = 'collision_avoidance'

        self._setpoint_pub.publish(out)
        self._n_avoid += 1

        if now - self._last_active_log > 1.0:
            self.get_logger().warn(
                f'CA kacis aktif: v=({v_cmd[0]:.2f},{v_cmd[1]:.2f},'
                f'{v_cmd[2]:.2f}) m/s, {len(obstacles)} komsu etkide',
            )
            self._last_active_log = now

    def _relay(self, raw: AgentSetpoint, reset_core: bool = True) -> None:
        """Ham setpoint verisini doğrudan geçirir."""
        if reset_core:
            self._ca.reset((self._cur_vx, self._cur_vy, self._cur_vz))
        self._n_passthrough += 1
        self._setpoint_pub.publish(raw)

    def _diag_tick(self) -> None:
        """Tani verilerini loglar."""
        try:
            self.get_logger().info(
                f'tani: passthrough={self._n_passthrough} '
                f'avoid={self._n_avoid} '
                f'gate_alt={self._n_gate_alt} '
                f'skip_state={self._n_skip_state} '
                f'skip_stale={self._n_skip_stale} '
                f'komsu_sub={len(self._neighbor_subs)}'
            )
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(f'tani log hata: {e}')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CollisionAvoidanceNode()
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
