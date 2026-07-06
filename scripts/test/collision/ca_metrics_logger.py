#!/usr/bin/env python3
"""ca_metrics_logger.py — CA katmanına özgü metrik kaydedici.

safety_monitor.py'nin ölçmediklerini tamamlar:
  - CA aktivasyon sayısı / süresi (source_module == 'collision_avoidance')
  - Z sapması per-drone: CA sırasında her dronun irtifası ne kadar kaydı?
  - v_cmd vs v_formation farkı: CA ne kadar modifikasyon yaptı?
  - Slew ihlali: v_cmd adım değişimi max_accel'ı aştı mı?

safety_monitor.py ile PARALEL çalıştırılır — aynı anda iki terminal:
    Terminal 1: python3 safety_monitor.py    --ros-args ...
    Terminal 2: python3 ca_metrics_logger.py --ros-args ...

ÇIKIŞ:
    ~/ros2_ws/analysis/collision_sitl/{run}_ca_metrics.csv
    Ctrl+C → terminal özeti

KULLANIM:
    python3 scripts/test/collision/ca_metrics_logger.py --ros-args \\
        -p agent_ids:="[1,2,3]" -p run_label:=headon_test1
"""

from __future__ import annotations

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


class CaMetricsLogger(Node):

    def __init__(self) -> None:
        super().__init__('ca_metrics_logger')

        self.declare_parameter('agent_ids', [1, 2, 3])
        self.declare_parameter('run_label', '')
        self.declare_parameter('max_accel_mps2', 30.0)
        self.declare_parameter('z_dev_thresh_m', 0.05)
        self.declare_parameter(
            'out_dir',
            os.path.expanduser('~/ros2_ws/analysis/collision_sitl'),
        )

        gp = self.get_parameter
        self._ids       = [int(x) for x in gp('agent_ids').value]
        self._max_accel = float(gp('max_accel_mps2').value)
        self._z_thresh  = float(gp('z_dev_thresh_m').value)
        out_dir = str(gp('out_dir').value)
        run = str(gp('run_label').value) or time.strftime('run_%Y%m%d_%H%M%S')
        self._run = run

        os.makedirs(out_dir, exist_ok=True)
        self._csv_path = os.path.join(out_dir, f'{run}_ca_metrics.csv')

        self._t0 = time.monotonic()

        # Per-drone durum
        self._z0:       dict[int, float | None] = {i: None for i in self._ids}
        self._prev_v:   dict[int, tuple | None]  = {i: None for i in self._ids}

        # CA aktivasyon takibi per-drone
        self._ca_active:      dict[int, bool]  = {i: False for i in self._ids}
        self._ca_start:       dict[int, float] = {i: 0.0   for i in self._ids}
        self._ca_count:       dict[int, int]   = {i: 0     for i in self._ids}
        self._ca_total_s:     dict[int, float] = {i: 0.0   for i in self._ids}

        # Z sapması per-drone
        self._z_dev_max:   dict[int, float] = {i: 0.0 for i in self._ids}
        self._z_dev_count: dict[int, int]   = {i: 0   for i in self._ids}  # thresh aşım

        # v_cmd modifikasyon büyüklüğü (raw vs filtered farkı)
        self._mod_max:  dict[int, float] = {i: 0.0 for i in self._ids}
        self._mod_sum:  dict[int, float] = {i: 0.0 for i in self._ids}
        self._mod_n:    dict[int, int]   = {i: 0   for i in self._ids}

        # Slew ihlali sayısı
        self._slew_viol: dict[int, int] = {i: 0 for i in self._ids}

        # Raw setpoint: karşılaştırma için
        self._raw_v:    dict[int, tuple | None] = {i: None for i in self._ids}

        self._csv = open(self._csv_path, 'w')
        self._csv.write(
            't_s,drone_id,ca_active,ca_source,'
            'vx_cmd,vy_cmd,vz_cmd,'
            'vx_raw,vy_raw,vz_raw,'
            'mod_xy_m_s,z_dev_m,slew_delta_m_s\n'
        )

        for did in self._ids:
            self.create_subscription(
                AgentSetpoint,
                f'/drone_{did}/control/setpoint',
                lambda msg, d=did: self._on_setpoint(d, msg),
                _QOS,
            )
            self.create_subscription(
                AgentSetpoint,
                f'/drone_{did}/control/setpoint/raw',
                lambda msg, d=did: self._on_raw(d, msg),
                _QOS,
            )
            self.create_subscription(
                AgentStatus,
                f'/swarm/agent/drone{did}/telemetry',
                lambda msg, d=did: self._on_telemetry(d, msg),
                _QOS,
            )

        self.get_logger().info(
            f'ca_metrics_logger [{run}]: agent_ids={self._ids} '
            f'max_accel={self._max_accel}m/s² z_thresh={self._z_thresh}m '
            f'csv={self._csv_path}'
        )

    def _on_telemetry(self, did: int, msg: AgentStatus) -> None:
        if not msg.z_valid:
            return
        z = float(msg.pos_z)
        if self._z0[did] is None:
            self._z0[did] = z   # ilk geçerli ölçüm = referans

    def _on_raw(self, did: int, msg: AgentSetpoint) -> None:
        if msg.velocity_valid:
            self._raw_v[did] = (float(msg.vx), float(msg.vy), float(msg.vz))

    def _on_setpoint(self, did: int, msg: AgentSetpoint) -> None:
        t = time.monotonic() - self._t0
        ca_active = getattr(msg, 'source_module', '') == 'collision_avoidance'
        vx = float(msg.vx) if msg.velocity_valid else 0.0
        vy = float(msg.vy) if msg.velocity_valid else 0.0
        vz = float(msg.vz) if msg.velocity_valid else 0.0

        # --- CA aktivasyon süresi ---
        if ca_active and not self._ca_active[did]:
            self._ca_active[did] = True
            self._ca_start[did] = t
            self._ca_count[did] += 1
        elif not ca_active and self._ca_active[did]:
            self._ca_active[did] = False
            self._ca_total_s[did] += t - self._ca_start[did]

        # --- Z sapması ---
        z0 = self._z0.get(did)
        z_dev = 0.0
        if z0 is not None and msg.position_valid:
            z_dev = abs(float(msg.z) - z0)
            if z_dev > self._z_dev_max[did]:
                self._z_dev_max[did] = z_dev
            if z_dev > self._z_thresh:
                self._z_dev_count[did] += 1

        # --- v_cmd vs v_raw modifikasyon ---
        raw = self._raw_v.get(did)
        mod_xy = 0.0
        if raw is not None and msg.velocity_valid:
            dvx = vx - raw[0]
            dvy = vy - raw[1]
            mod_xy = math.sqrt(dvx * dvx + dvy * dvy)
            if mod_xy > self._mod_max[did]:
                self._mod_max[did] = mod_xy
            self._mod_sum[did] += mod_xy
            self._mod_n[did] += 1

        # --- Slew ihlali ---
        slew_delta = 0.0
        prev = self._prev_v.get(did)
        if prev is not None and msg.velocity_valid:
            dvx = vx - prev[0]
            dvy = vy - prev[1]
            dvz = vz - prev[2]
            slew_delta = math.sqrt(dvx*dvx + dvy*dvy + dvz*dvz)
            # dt ≈ 0.05s (20 Hz), max_accel * dt = max_delta
            max_delta = self._max_accel * 0.05
            if slew_delta > max_delta * 1.2:   # %20 tolerans
                self._slew_viol[did] += 1

        if msg.velocity_valid:
            self._prev_v[did] = (vx, vy, vz)

        raw_vx = raw[0] if raw else 0.0
        raw_vy = raw[1] if raw else 0.0
        raw_vz = raw[2] if raw else 0.0

        self._csv.write(
            f'{t:.3f},{did},{int(ca_active)},'
            f'{getattr(msg,"source_module","")},'
            f'{vx:.4f},{vy:.4f},{vz:.4f},'
            f'{raw_vx:.4f},{raw_vy:.4f},{raw_vz:.4f},'
            f'{mod_xy:.4f},{z_dev:.4f},{slew_delta:.4f}\n'
        )
        self._csv.flush()

    def ozet_bas(self) -> None:
        t_now = time.monotonic() - self._t0

        # Açık kalan aktivasyon sürelerini kapat
        for did in self._ids:
            if self._ca_active[did]:
                self._ca_total_s[did] += t_now - self._ca_start[did]

        print('\n' + '=' * 65)
        print(f'CA METRİK ÖZETI  [{self._run}]')
        print('=' * 65)

        all_ok = True
        for did in self._ids:
            mod_avg = (self._mod_sum[did] / self._mod_n[did]
                       if self._mod_n[did] > 0 else 0.0)
            z_ok  = self._z_dev_max[did] <= self._z_thresh
            slew_ok = self._slew_viol[did] == 0

            status = '✓' if (z_ok and slew_ok) else '✗'
            if not (z_ok and slew_ok):
                all_ok = False

            print(f'\n  Drone {did}  [{status}]')
            print(f'    CA aktivasyon  : {self._ca_count[did]} kez, '
                  f'toplam {self._ca_total_s[did]:.1f}s')
            print(f'    Z sapması max  : {self._z_dev_max[did]:.4f}m  '
                  f'(eşik={self._z_thresh}m)  '
                  f'{"✓" if z_ok else "✗ AŞIM " + str(self._z_dev_count[did]) + " kez"}')
            print(f'    v_cmd modif    : ort={mod_avg:.3f} m/s  '
                  f'max={self._mod_max[did]:.3f} m/s')
            print(f'    Slew ihlali    : {self._slew_viol[did]}  '
                  f'{"✓" if slew_ok else "✗"}')

        print('\n' + '-' * 65)
        print(f'GENEL: {"PASS ✓" if all_ok else "FAIL ✗"}')
        print(f'CSV  : {self._csv_path}')
        print('=' * 65 + '\n')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CaMetricsLogger()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.ozet_bas()
        try:
            node._csv.close()
        except Exception:  # noqa: BLE001
            pass
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:  # noqa: BLE001
            pass


if __name__ == '__main__':
    main()
