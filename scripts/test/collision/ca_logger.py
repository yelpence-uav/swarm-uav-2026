#!/usr/bin/env python3
"""ca_logger.py — Yörünge + hız + mesafe verisini CSV'e kaydeder.

ROS2 GEREKTIRIR. SITL çalışırken arka planda başlat:
    python3 ~/ros2_ws/scripts/test/collision/ca_logger.py \
        --ros-args -p agent_ids:="[1,2,3]" -p out_dir:="/tmp/ca_logs"

Üretilen CSV:
    {out_dir}/trajectory.csv   — her drone'un x,y,z konumu (NED, m)
    {out_dir}/velocity.csv     — CA çıkış setpoint vx,vy,vz (m/s)
    {out_dir}/distance.csv     — tüm çift kombinasyonları arası mesafe (m)

Grafik:
    python3 plot_ca_analysis.py /tmp/ca_logs
"""

import csv
import itertools
import math
import os

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSPresetProfiles

from swarm_interfaces.msg import AgentSetpoint, AgentStatus


class CaLogger(Node):

    def __init__(self):
        super().__init__('ca_logger')
        self.declare_parameter('agent_ids', [1, 2, 3])
        self.declare_parameter('out_dir', '/tmp/ca_logs')
        self.declare_parameter('rate_hz', 10.0)

        ids = list(self.get_parameter('agent_ids')
                   .get_parameter_value().integer_array_value)
        out_dir = str(self.get_parameter('out_dir').value)
        rate = float(self.get_parameter('rate_hz').value)

        os.makedirs(out_dir, exist_ok=True)
        self._t0: float | None = None

        # --- CSV dosyaları ---
        def _open(name, header):
            f = open(os.path.join(out_dir, name), 'w', newline='')
            w = csv.writer(f)
            w.writerow(header)
            return f, w

        self._f_traj, self._w_traj = _open(
            'trajectory.csv',
            ['t_s'] + [f'drone{i}_{ax}' for i in ids for ax in ('x', 'y', 'z')],
        )
        self._f_vel, self._w_vel = _open(
            'velocity.csv',
            ['t_s'] + [f'drone{i}_{ax}' for i in ids for ax in ('vx', 'vy', 'vz')],
        )
        pairs = list(itertools.combinations(ids, 2))
        self._f_dist, self._w_dist = _open(
            'distance.csv',
            ['t_s'] + [f'd{a}_{b}' for a, b in pairs],
        )

        self._ids = ids
        self._pairs = pairs

        # pos[id] = (x, y, z)
        self._pos: dict[int, tuple[float, float, float]] = {}
        # vel[id] = (vx, vy, vz)  — CA çıkış setpointi
        self._vel: dict[int, tuple[float, float, float]] = {}

        for aid in ids:
            self.create_subscription(
                AgentStatus,
                f'/swarm/agent/drone{aid}/telemetry',
                lambda m, i=aid: self._on_tel(i, m),
                QoSPresetProfiles.SYSTEM_DEFAULT.value,
            )
            self.create_subscription(
                AgentSetpoint,
                f'/drone_{aid}/control/setpoint',
                lambda m, i=aid: self._on_sp(i, m),
                QoSPresetProfiles.SYSTEM_DEFAULT.value,
            )

        self.create_timer(1.0 / rate, self._tick)
        self.get_logger().info(
            f'ca_logger başladı | drones={ids} | out={out_dir}'
        )

    def _on_tel(self, aid: int, msg: AgentStatus) -> None:
        self._pos[aid] = (float(msg.pos_x), float(msg.pos_y), float(msg.pos_z))

    def _on_sp(self, aid: int, msg: AgentSetpoint) -> None:
        self._vel[aid] = (float(msg.vx), float(msg.vy), float(msg.vz))

    def _tick(self) -> None:
        if len(self._pos) < len(self._ids):
            return  # henüz tüm dronlar görünmedi

        now = self.get_clock().now().nanoseconds * 1e-9
        if self._t0 is None:
            self._t0 = now
        t = now - self._t0

        # Trajectory
        row_t = [round(t, 3)]
        for aid in self._ids:
            x, y, z = self._pos.get(aid, (0.0, 0.0, 0.0))
            row_t += [round(x, 4), round(y, 4), round(z, 4)]
        self._w_traj.writerow(row_t)
        self._f_traj.flush()

        # Velocity
        row_v = [round(t, 3)]
        for aid in self._ids:
            vx, vy, vz = self._vel.get(aid, (0.0, 0.0, 0.0))
            row_v += [round(vx, 4), round(vy, 4), round(vz, 4)]
        self._w_vel.writerow(row_v)
        self._f_vel.flush()

        # Distance
        row_d = [round(t, 3)]
        for a, b in self._pairs:
            pa = self._pos.get(a, (0.0, 0.0, 0.0))
            pb = self._pos.get(b, (0.0, 0.0, 0.0))
            d = math.dist(pa, pb)
            row_d.append(round(d, 4))
        self._w_dist.writerow(row_d)
        self._f_dist.flush()

    def destroy_node(self):
        for f in (self._f_traj, self._f_vel, self._f_dist):
            try:
                f.close()
            except Exception:
                pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CaLogger()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
