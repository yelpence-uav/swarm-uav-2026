# Copyright 2026 Yelpence
"""Dagitik formasyon kontrol node'u."""

import math

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
    SwarmOrigin,
)

from .formation_geometry import (
    latlon_to_ned,
    rotate_offset,
)

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

_ORIGIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


class FormationControlNode(Node):
    """Tek drone icin dagitik formasyon setpoint hesaplayicisi."""

    def __init__(self) -> None:
        super().__init__('formation_control')

        self._declare_params()

        self._current_formation = None
        self._sequence_num = 0

        self._current_pos_x = 0.0
        self._current_pos_y = 0.0
        self._current_pos_z = 0.0
        self._current_vel_x = 0.0
        self._current_vel_y = 0.0
        self._current_vel_z = 0.0
        self._pos_valid = False
        self._oscillating = False

        self._origin_synced = False
        self._estimator_ok = False
        self._xy_valid = False
        self._z_valid = False

        self._current_lat = 0.0
        self._current_lon = 0.0
        self._gps_valid = False

        self._origin_lat = None
        self._origin_lon = None

        self._ramp_x = None
        self._ramp_y = None
        self._ramp_z = None
        self._last_publish_time = None

        self._neighbors = {}
        self._neighbor_rx_time = {}
        self._neighbor_subs = {}

        self._setup_publishers()
        self._setup_subscribers()

        self._timer = self.create_timer(
            1.0 / self._publish_rate_hz,
            self._publish_setpoint,
        )

        self.get_logger().info(
            f'FormationControlNode baslatildi: agent_id={self._agent_id}'
        )

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanimlar ve sınıf degiskenlerine okur."""
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('position_tolerance_m', 0.5)
        self.declare_parameter('heading_tolerance_deg', 5.0)
        self.declare_parameter('max_speed_mps', 3.0)
        self.declare_parameter('svt_k', 0.8)
        self.declare_parameter('svt_threshold_m', 0.1)
        self.declare_parameter('svt_k_z', 2.0)
        self.declare_parameter('svt_threshold_z_m', 0.05)
        self.declare_parameter('svt_damp', 0.35)
        self.declare_parameter('target_ramp_mps', 1.0)
        self.declare_parameter('rel_enable', True)
        self.declare_parameter('rel_k', 0.2)
        self.declare_parameter('rel_threshold_m', 0.2)
        self.declare_parameter('rel_stale_s', 0.5)
        self.declare_parameter('keeping_enter_m', 1.2)
        self.declare_parameter('keeping_exit_m', 1.8)
        self.declare_parameter('vff_lpf_alpha', 0.3)
        self.declare_parameter('sitl_mode', True)

        self._agent_id = int(self.get_parameter('agent_id').value)
        self._sitl_mode = bool(self.get_parameter('sitl_mode').value)
        self._publish_rate_hz = float(
            self.get_parameter('publish_rate_hz').value
        )
        self._position_tolerance_m = float(
            self.get_parameter('position_tolerance_m').value
        )
        self._heading_tolerance_deg = float(
            self.get_parameter('heading_tolerance_deg').value
        )
        self._max_speed_mps = float(
            self.get_parameter('max_speed_mps').value
        )
        self._svt_k = float(self.get_parameter('svt_k').value)
        self._svt_threshold_m = float(
            self.get_parameter('svt_threshold_m').value
        )
        self._svt_k_z = float(self.get_parameter('svt_k_z').value)
        self._svt_threshold_z_m = float(
            self.get_parameter('svt_threshold_z_m').value
        )
        self._svt_damp = float(self.get_parameter('svt_damp').value)
        self._target_ramp_mps = float(
            self.get_parameter('target_ramp_mps').value
        )
        self._rel_enable = bool(
            self.get_parameter('rel_enable').value
        )
        self._rel_k = float(self.get_parameter('rel_k').value)
        self._rel_threshold_m = float(
            self.get_parameter('rel_threshold_m').value
        )
        self._rel_stale_s = float(
            self.get_parameter('rel_stale_s').value
        )
        self._keeping_enter_m = float(
            self.get_parameter('keeping_enter_m').value
        )
        self._keeping_exit_m = float(
            self.get_parameter('keeping_exit_m').value
        )
        self._vff_lpf_alpha = float(
            self.get_parameter('vff_lpf_alpha').value
        )

        self._vff_x = 0.0
        self._vff_y = 0.0
        self._vff_z = 0.0
        self._prev_slot_x = None
        self._prev_slot_y = None
        self._prev_slot_z = None
        self._prev_cmd_time = None

    def _setup_publishers(self) -> None:
        """Setpoint publisher'ini olusturur."""
        self._setpoint_pub = self.create_publisher(
            AgentSetpoint,
            f'/drone_{self._agent_id}/control/setpoint/raw',
            _BEST_EFFORT_QOS,
        )

    def _setup_subscribers(self) -> None:
        """Topic aboneliklerini olusturur."""
        self.create_subscription(
            FormationCommand,
            '/swarm/public/formation/target',
            self._on_formation_command,
            _RELIABLE_QOS,
        )
        self.create_subscription(
            AgentStatus,
            f'/swarm/agent/drone{self._agent_id}/telemetry',
            self._on_agent_status,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            AgentStatus,
            f'/swarm/public/drone{self._agent_id}/status',
            self._on_agent_status,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            AgentStatus,
            f'/swarm/internal/drone{self._agent_id}/status',
            self._on_agent_status,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            SwarmOrigin,
            '/swarm/public/origin',
            self._on_swarm_origin,
            _ORIGIN_QOS,
        )

    def _ensure_neighbor_subs(self, agent_ids) -> None:
        """Atamadaki her komsu icin abonelik kurar."""
        if not self._rel_enable:
            return
        for nid in agent_ids:
            nid = int(nid)
            if nid == self._agent_id or nid in self._neighbor_subs:
                continue
            topic = (
                f'/swarm/agent/drone{self._agent_id}'
                f'/neighbor/drone{nid}'
            )
            self._neighbor_subs[nid] = self.create_subscription(
                NeighborInfo,
                topic,
                lambda m, n=nid: self._on_neighbor(n, m),
                _BEST_EFFORT_QOS,
            )
            self.get_logger().info(
                f'NeighborInfo aboneligi kuruldu: drone{nid}'
            )

    def _on_formation_command(self, msg: FormationCommand) -> None:
        """Gelen FormationCommand'i saklar ve v_ff hesaplar."""
        prev = self._current_formation
        self._current_formation = msg
        type_changed = (
            prev is None or prev.formation_type != msg.formation_type
        )
        if type_changed:
            self._ramp_x = None
            self._ramp_y = None
            self._ramp_z = None

        agent_ids = list(msg.agent_ids)
        if self._agent_id in agent_ids:
            idx = agent_ids.index(self._agent_id)
            if (idx < len(msg.offset_x) and idx < len(msg.offset_y)
                    and idx < len(msg.offset_z)):
                hr = math.radians(msg.heading_deg)
                odx, ody = rotate_offset(
                    msg.offset_x[idx], msg.offset_y[idx], hr
                )
                ssx = float(msg.center_x) + odx
                ssy = float(msg.center_y) + ody
                ssz = float(msg.center_z) + float(msg.offset_z[idx])
                now = self.get_clock().now().nanoseconds * 1e-9
                if (not type_changed and self._prev_slot_x is not None
                        and self._prev_cmd_time is not None):
                    dtc = now - self._prev_cmd_time
                    if dtc > 1e-3:
                        a = self._vff_lpf_alpha
                        self._vff_x = (
                            a * (ssx - self._prev_slot_x) / dtc
                            + (1.0 - a) * self._vff_x
                        )
                        self._vff_y = (
                            a * (ssy - self._prev_slot_y) / dtc
                            + (1.0 - a) * self._vff_y
                        )
                        self._vff_z = (
                            a * (ssz - self._prev_slot_z) / dtc
                            + (1.0 - a) * self._vff_z
                        )
                else:
                    self._vff_x = self._vff_y = self._vff_z = 0.0
                self._prev_slot_x = ssx
                self._prev_slot_y = ssy
                self._prev_slot_z = ssz
                self._prev_cmd_time = now

        self._ensure_neighbor_subs(msg.agent_ids)

    def _on_agent_status(self, msg: AgentStatus) -> None:
        """Drone durumunu gunceller."""
        self._current_pos_x = float(msg.pos_x)
        self._current_pos_y = float(msg.pos_y)
        self._current_pos_z = float(msg.pos_z)
        self._current_vel_x = float(msg.vel_x)
        self._current_vel_y = float(msg.vel_y)
        self._current_vel_z = float(msg.vel_z)
        self._pos_valid = True
        self._oscillating = msg.oscillation_detected

        self._origin_synced = bool(msg.origin_synced)
        self._estimator_ok = bool(msg.estimator_ok)
        self._xy_valid = bool(msg.xy_valid)
        self._z_valid = bool(msg.z_valid)

        if msg.lat_deg != 0.0 or msg.lon_deg != 0.0:
            self._current_lat = float(msg.lat_deg)
            self._current_lon = float(msg.lon_deg)
            self._gps_valid = True

    def _on_neighbor(self, nid: int, msg: NeighborInfo) -> None:
        """Komsu verisini kaydeder."""
        self._neighbors[nid] = msg
        self._neighbor_rx_time[nid] = (
            self.get_clock().now().nanoseconds * 1e-9
        )

    def _on_swarm_origin(self, msg: SwarmOrigin) -> None:
        """Referans baslangic noktasini kaydeder."""
        if not msg.valid:
            return
        self._origin_lat = float(msg.origin_lat_deg)
        self._origin_lon = float(msg.origin_lon_deg)

    def _shared_to_local(
        self, shared_x: float, shared_y: float
    ) -> tuple[float, float]:
        """Shared koordinati local NED frame'e cevirir."""
        if self._origin_lat is None or not self._gps_valid:
            return shared_x, shared_y

        cur_n, cur_e = latlon_to_ned(
            self._current_lat, self._current_lon,
            self._origin_lat, self._origin_lon,
        )
        return (
            shared_x - cur_n + self._current_pos_x,
            shared_y - cur_e + self._current_pos_y,
        )

    def _compute_velocity(
        self,
        target_x: float,
        target_y: float,
        target_z: float,
        max_speed: float,
    ) -> tuple[float, float, float]:
        """SVT duzeltme hizini hesaplar."""
        vx = 0.0
        vy = 0.0
        vz = 0.0

        if self._pos_valid:
            ex = self._current_pos_x - target_x
            ey = self._current_pos_y - target_y
            dist_xy = math.sqrt(ex * ex + ey * ey)
            if dist_xy > self._svt_threshold_m:
                vx -= self._svt_k * ex
                vy -= self._svt_k * ey

            ez = self._current_pos_z - target_z
            if abs(ez) > self._svt_threshold_z_m:
                vz -= self._svt_k_z * ez

            vx -= self._svt_damp * self._current_vel_x
            vy -= self._svt_damp * self._current_vel_y
            vz -= self._svt_damp * self._current_vel_z

        return self._clamp_speed(vx, vy, vz, max_speed)

    def _compute_relative_correction(
        self,
        msg: FormationCommand,
        my_idx: int,
        heading_rad: float,
        now: float,
    ) -> tuple[float, float, float]:
        """Komsulara gore goreli duzeltme hizini hesaplar."""
        if not self._rel_enable or getattr(msg, 'formation_type', 1) == 0:
            return 0.0, 0.0, 0.0

        agent_ids = list(msg.agent_ids)
        my_ox = float(msg.offset_x[my_idx])
        my_oy = float(msg.offset_y[my_idx])
        my_oz = float(msg.offset_z[my_idx])

        sum_ex = 0.0
        sum_ey = 0.0
        sum_ez = 0.0
        count = 0
        for nid in agent_ids:
            nid = int(nid)
            if nid == self._agent_id:
                continue
            info = self._neighbors.get(nid)
            if info is None or not info.link_active:
                continue
            rx = self._neighbor_rx_time.get(nid, 0.0)
            if now - rx > self._rel_stale_s:
                continue
            n_idx = agent_ids.index(nid)
            if (n_idx >= len(msg.offset_x) or n_idx >= len(msg.offset_y)
                    or n_idx >= len(msg.offset_z)):
                continue

            dbx = float(msg.offset_x[n_idx]) - my_ox
            dby = float(msg.offset_y[n_idx]) - my_oy
            dbz = float(msg.offset_z[n_idx]) - my_oz
            des_x, des_y = rotate_offset(dbx, dby, heading_rad)
            des_z = dbz

            sum_ex += float(info.relative_x) - des_x
            sum_ey += float(info.relative_y) - des_y
            sum_ez += float(info.relative_z) - des_z
            count += 1

        if count == 0:
            return 0.0, 0.0, 0.0

        mean_ex = sum_ex / count
        mean_ey = sum_ey / count
        mean_ez = sum_ez / count

        horiz = math.sqrt(mean_ex * mean_ex + mean_ey * mean_ey)
        vx = self._rel_k * mean_ex if horiz > self._rel_threshold_m else 0.0
        vy = self._rel_k * mean_ey if horiz > self._rel_threshold_m else 0.0
        if abs(mean_ez) > self._rel_threshold_m:
            vz = self._rel_k * mean_ez
        else:
            vz = 0.0
        return vx, vy, vz

    @staticmethod
    def _clamp_speed(
        vx: float, vy: float, vz: float, max_speed: float
    ) -> tuple[float, float, float]:
        """Hiz vektorunu max_speed degerine kirpar."""
        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        if speed > max_speed and speed > 0.0:
            scale = max_speed / speed
            return vx * scale, vy * scale, vz * scale
        return vx, vy, vz

    def _resolve_center(
        self, msg: FormationCommand
    ) -> tuple[float, float, float]:
        """Komutla gelen merkezi doner."""
        return (
            float(msg.center_x),
            float(msg.center_y),
            float(msg.center_z),
        )

    def _publish_setpoint(self) -> None:
        """Hedef setpoint'ini hesaplar ve yayinlar."""
        msg = self._current_formation
        if msg is None:
            return

        agent_ids = list(msg.agent_ids)
        if not agent_ids or self._agent_id not in agent_ids:
            return

        if not self._sitl_mode and not self._origin_synced:
            self.get_logger().warn(
                'origin senkronlanmadi; setpoint bekletiliyor',
                throttle_duration_sec=2.0,
            )
            return

        if not self._sitl_mode and not (self._xy_valid and self._z_valid):
            self.get_logger().warn(
                'konum tahmini gecersiz; setpoint bekletiliyor',
                throttle_duration_sec=2.0,
            )
            return

        idx = agent_ids.index(self._agent_id)
        if (idx >= len(msg.offset_x) or idx >= len(msg.offset_y)
                or idx >= len(msg.offset_z)):
            self.get_logger().warn(
                'komuttaki offset dizileri eksik; setpoint atlandi',
                throttle_duration_sec=2.0,
            )
            return

        center_x, center_y, center_z = self._resolve_center(msg)
        heading_rad = math.radians(msg.heading_deg)

        dx, dy = rotate_offset(
            msg.offset_x[idx], msg.offset_y[idx], heading_rad
        )
        x = center_x + dx
        y = center_y + dy
        z = center_z + msg.offset_z[idx]

        x, y = self._shared_to_local(x, y)

        max_speed = (
            float(msg.max_speed_mps)
            if msg.max_speed_mps > 0.0
            else self._max_speed_mps
        )

        now = self.get_clock().now().nanoseconds * 1e-9
        dt = (
            (now - self._last_publish_time)
            if self._last_publish_time is not None
            else 0.0
        )
        self._last_publish_time = now
        ramp_rate = max_speed
        if self._target_ramp_mps > 0.0:
            ramp_rate = min(self._target_ramp_mps, max_speed)
        if self._ramp_x is None:
            self._ramp_x = self._current_pos_x if self._pos_valid else x
            self._ramp_y = self._current_pos_y if self._pos_valid else y
            self._ramp_z = self._current_pos_z if self._pos_valid else z

        if dt > 0.0 and ramp_rate > 0.0:
            max_step = ramp_rate * dt
            for attr, target in [
                ('_ramp_x', x), ('_ramp_y', y), ('_ramp_z', z)
            ]:
                cur = getattr(self, attr)
                diff = target - cur
                step = max(-max_step, min(max_step, diff))
                setattr(self, attr, cur + step)
        x, y, z = self._ramp_x, self._ramp_y, self._ramp_z

        svx, svy, svz = self._compute_velocity(x, y, z, max_speed)
        rvx, rvy, rvz = self._compute_relative_correction(
            msg, idx, heading_rad, now
        )
        vx, vy, vz = self._clamp_speed(
            svx + rvx + self._vff_x,
            svy + rvy + self._vff_y,
            svz + rvz + self._vff_z, max_speed
        )
        out = self._build_setpoint_msg(
            msg, x, y, z, vx, vy, vz,
            position_valid=False,
            velocity_valid=True,
        )
        self._setpoint_pub.publish(out)

    def _build_setpoint_msg(
        self,
        cmd: FormationCommand,
        x: float,
        y: float,
        z: float,
        vx: float,
        vy: float,
        vz: float,
        velocity_valid: bool = False,
        position_valid: bool = True,
    ) -> AgentSetpoint:
        """Hesaplanan veriyle AgentSetpoint mesaji uretir."""
        out = AgentSetpoint()
        out.stamp = self.get_clock().now().to_msg()
        out.sequence_num = self._sequence_num
        self._sequence_num += 1

        out.agent_id = self._agent_id
        out.source = AgentSetpoint.SOURCE_FORMATION_CONTROL
        out.priority = AgentSetpoint.PRIORITY_FORMATION

        out.x = float(x)
        out.y = float(y)
        out.z = float(z)
        out.position_valid = position_valid

        out.vx = float(vx)
        out.vy = float(vy)
        out.vz = float(vz)
        out.velocity_valid = velocity_valid
        out.acceleration_valid = False

        out.heading_deg = float(cmd.heading_deg)
        out.heading_valid = True
        out.yaw_rate_valid = False

        out.hold_position = False
        out.land_now = False
        out.rtl_now = False

        out.position_tolerance_m = self._position_tolerance_m
        out.heading_tolerance_deg = self._heading_tolerance_deg

        if cmd.max_speed_mps > 0.0:
            out.max_speed_mps = float(cmd.max_speed_mps)
        else:
            out.max_speed_mps = self._max_speed_mps
        out.max_acc_mps2 = 0.0

        out.source_module = 'formation_control'
        return out


def main(args=None) -> None:
    rclpy.init(args=args)
    node = FormationControlNode()
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
