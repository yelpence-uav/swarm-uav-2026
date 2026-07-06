#!/usr/bin/env python3
"""trajectory_logger.py — Dron-başına Kuzey/Doğu GPS yörünge kaydedici.

safety_monitor min-mesafe (skaler) loglar; bu ise HER dronun KONUMUNU
(kuzey, doğu) zaman serisi olarak yazar → sağ-el yaylanmasını GÖRSEL
kanıtlamak için (plot_trajectory.py bunu çizer): drone1 batıya, drone2
doğuya büker mi? "Çarpışmadan geçtiler"in resmi budur.

KOORDİNAT: GPS lat/lon → ortak referansa göre (kuzey, doğu) metre
([[mesafe-olcumu-gps-ile-local-degil]] — pos_x/pos_y drone'lar arası
kıyaslanamaz). Referans = görülen ilk geçerli fix (0,0 noktası).

CA İŞARETİ: /drone_N/control/setpoint'in source_module'üne bakar; CA
aktifse o örnek ca=1 işaretlenir → plot avoidance segmentini renklendirir.

ÇIKTI (uzun format, plot_trajectory.py pivotlar):
    {run}_traj.csv:  t_s,drone,north_m,east_m,alt_m,ca

KULLANIM:
    python3 trajectory_logger.py --ros-args \\
        -p agent_ids:="[1,2,3]" -p run_label:=headon -p out_dir:=...
"""

import math
import os
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

from swarm_interfaces.msg import AgentSetpoint, AgentStatus


_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)

_M_PER_DEG_LAT = 111320.0   # safety_monitor ile AYNI düz-dünya yaklaşımı


class TrajectoryLogger(Node):
    """Tüm dronların (kuzey, doğu, irtifa, CA) zaman serisini CSV'ye yazar."""

    def __init__(self) -> None:
        super().__init__('trajectory_logger')
        self.declare_parameter('agent_ids', [1, 2, 3])
        self.declare_parameter('rate_hz', 10.0)
        self.declare_parameter('stale_s', 1.0)
        self.declare_parameter(
            'out_dir', os.path.expanduser('~/ros2_ws/analysis/collision_sitl'),
        )
        self.declare_parameter('run_label', '')

        gp = self.get_parameter
        self._ids = [int(x) for x in gp('agent_ids').value]
        rate = float(gp('rate_hz').value)
        self._stale = float(gp('stale_s').value)
        out_dir = str(gp('out_dir').value)
        run = str(gp('run_label').value) or time.strftime('run_%Y%m%d_%H%M%S')

        os.makedirs(out_dir, exist_ok=True)
        self._csv_path = os.path.join(out_dir, f'{run}_traj.csv')

        self._pos: dict[int, tuple] = {}      # did -> (lat, lon, alt)
        self._rx: dict[int, float] = {}
        self._ca: dict[int, bool] = {i: False for i in self._ids}
        self._ref: tuple | None = None        # (lat0, lon0) sabit referans
        self._t0 = time.monotonic()

        for did in self._ids:
            self.create_subscription(
                AgentStatus,
                f'/swarm/agent/drone{did}/telemetry',
                lambda msg, d=did: self._on_status(d, msg),
                _QOS,
            )
            self.create_subscription(
                AgentSetpoint,
                f'/drone_{did}/control/setpoint',
                lambda msg, d=did: self._on_setpoint(d, msg),
                _QOS,
            )

        self._csv = open(self._csv_path, 'w')
        self._csv.write('t_s,drone,north_m,east_m,alt_m,ca\n')
        self.create_timer(1.0 / rate, self._tick)
        self.get_logger().info(
            f'trajectory_logger [{run}]: agent_ids={self._ids} '
            f'rate={rate}Hz csv={self._csv_path}'
        )

    def _on_status(self, did: int, msg: AgentStatus) -> None:
        if not (msg.xy_valid and msg.z_valid):
            return
        if msg.lat_deg == 0.0 and msg.lon_deg == 0.0:
            return
        self._pos[did] = (
            float(msg.lat_deg), float(msg.lon_deg), -float(msg.pos_z),
        )
        self._rx[did] = time.monotonic()
        if self._ref is None:
            self._ref = (float(msg.lat_deg), float(msg.lon_deg))

    def _on_setpoint(self, did: int, msg: AgentSetpoint) -> None:
        self._ca[did] = getattr(msg, 'source_module', '') == 'collision_avoidance'

    def _tick(self) -> None:
        if self._ref is None:
            return
        now = time.monotonic()
        lat0, lon0 = self._ref
        t = now - self._t0
        for did in self._ids:
            if now - self._rx.get(did, 0.0) > self._stale:
                continue
            lat, lon, alt = self._pos[did]
            north = (lat - lat0) * _M_PER_DEG_LAT
            east = (lon - lon0) * _M_PER_DEG_LAT * math.cos(math.radians(lat0))
            self._csv.write(
                f'{t:.3f},{did},{north:.3f},{east:.3f},{alt:.2f},'
                f'{int(self._ca[did])}\n'
            )
        self._csv.flush()

    def close(self) -> None:
        try:
            self._csv.close()
        except Exception:  # noqa: BLE001
            pass
        self.get_logger().info(f'yörünge CSV: {self._csv_path}')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TrajectoryLogger()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:  # noqa: BLE001
            pass


if __name__ == '__main__':
    main()
