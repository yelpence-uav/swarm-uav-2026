#!/usr/bin/env python3
"""
mission_timing_logger.py — SITL'de tam görev süresini GERÇEK ölçer.

FSM'in yayınladığı /swarm/internal/mission/state (UInt8) topic'ini dinler,
her MissionState'te geçen gerçek süreyi kaydeder ve görev bitince
(MISSION_COMPLETE) faz süreleri + toplam görev süresini CSV'ye yazar.

KULLANIM:
  1) SITL + sürü + FSM'i SEN başlat (Gazebo, launch_swarm.py).
  2) Bu logger'ı ayrı terminalde çalıştır:
        python3 scripts/test/scalability/mission_timing_logger.py --n 3
     (SITL'de use_sim_time gerekiyorsa:  --ros-args -p use_sim_time:=true)
  3) Görevi başlat: scripts/test/05_mission_baslat.sh
  4) MISSION_COMPLETE'e gelince logger CSV yazıp özet basar.

Çıktı: mission_timing_N{n}.csv  →  her faz: ad, giriş_t, süre_s
"""

import argparse
import csv
import os

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import UInt8

# mission_states.py ile birebir
STATE_NAME = {
    0: "UNKNOWN", 1: "IDLE", 2: "PREFLIGHT", 3: "SYNCHRONIZED_TAKEOFF",
    4: "NAVIGATE_TO_QR", 5: "EXECUTE_QR_TASK", 6: "WAIT_AT_QR",
    7: "ROTATE_TO_NEXT", 8: "SEMI_AUTONOMOUS", 9: "RETURN_HOME",
    10: "LANDING", 11: "MISSION_COMPLETE", 12: "ABORTED", 13: "PAUSED",
}
QR_STEP_NAME = {0: "NONE", 1: "FORMATION", 2: "MANEUVER", 3: "ALTITUDE",
                4: "DETACH", 5: "DONE"}


class MissionTimingLogger(Node):
    def __init__(self, n_agents: int, out_dir: str):
        super().__init__("mission_timing_logger")
        self.n = n_agents
        self.out_path = os.path.join(out_dir, f"mission_timing_N{n_agents}.csv")
        qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                         history=HistoryPolicy.KEEP_LAST, depth=10)
        self.create_subscription(UInt8, "/swarm/internal/mission/state",
                                 self._on_state, qos)
        self.create_subscription(UInt8, "/swarm/internal/mission/qr_step",
                                 self._on_qr, qos)
        self._cur_state = None
        self._cur_qr = 0
        self._enter_t = None
        self._t0 = None                 # ilk hareketin (PREFLIGHT/TAKEOFF) zamanı
        self._rows = []                 # (state_name, qr_step_name, enter_s, dur_s)
        self._per_state = {}            # toplam süre / state
        self.get_logger().info(
            f"Dinleniyor: /swarm/internal/mission/state  (N={n_agents}). "
            f"Görevi başlat; MISSION_COMPLETE'te CSV yazılacak → {self.out_path}")

    def _now(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    def _on_qr(self, msg: UInt8):
        self._cur_qr = msg.data

    def _on_state(self, msg: UInt8):
        s = msg.data
        t = self._now()
        if s == self._cur_state:
            return                                    # aynı state, yoksay
        # önceki state'in süresini kapat
        if self._cur_state is not None and self._enter_t is not None:
            dur = t - self._enter_t
            name = STATE_NAME.get(self._cur_state, str(self._cur_state))
            self._rows.append((name, QR_STEP_NAME.get(self._cur_qr, "?"),
                               round(self._enter_t - self._t0, 2), round(dur, 2)))
            self._per_state[name] = self._per_state.get(name, 0.0) + dur
            self.get_logger().info(f"  {name:22s} {dur:6.2f} s")
        # yeni state'e gir
        self._cur_state = s
        self._enter_t = t
        # görev sayacını ilk aktif state'te başlat (IDLE/UNKNOWN sayılmaz)
        if self._t0 is None and s >= MissionState_PREFLIGHT:
            self._t0 = t
        if s == 11:                                   # MISSION_COMPLETE
            self._finish()

    def _finish(self):
        total = (self._enter_t - self._t0) if self._t0 else 0.0
        with open(self.out_path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["faz", "qr_step", "giris_s", "sure_s"])
            w.writerows(self._rows)
            w.writerow([])
            w.writerow(["# state bazinda toplam", "", "", ""])
            for k, v in self._per_state.items():
                w.writerow([k, "", "", round(v, 2)])
            w.writerow(["TOPLAM_GOREV_SURESI", "", "", round(total, 2)])
        print("\n" + "=" * 50)
        print(f"  GÖREV TAMAMLANDI  (N={self.n})")
        print(f"  Toplam görev süresi (SITL ölçümü): {total:.1f} s")
        print(f"  CSV: {self.out_path}")
        print("=" * 50)
        rclpy.shutdown()


MissionState_PREFLIGHT = 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3, help="aktif İHA sayısı (etiket)")
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    args, _ = ap.parse_known_args()
    rclpy.init()
    node = MissionTimingLogger(args.n, args.out)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
