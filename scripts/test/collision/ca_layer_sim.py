"""ca_layer_sim.py — ca_layer için bağımsız kinematik test.

ROS / Gazebo gerekmez. Her senaryo birden fazla drone'u ileri sarım
(Euler) ile simüle eder; ca_layer.compute() her adımda çağrılır.

Geçme kriterleri (her senaryo için):
    min_dist  ≥ 1.5 m   (safety_radius, merkez-merkez)
    osc_count ≤ 2       (yön değişimi sayısı — salınım tespiti)
    Z_dev     ≤ 0.05 m  (CA Z'ye dokunmadı)

Çalıştır:
    python3 scripts/test/collision/ca_layer_sim.py
    python3 scripts/test/collision/ca_layer_sim.py --plot   (grafik)
"""

from __future__ import annotations

import argparse
import math
import sys
import os

import numpy as np

# Proje kökünden çalıştırılmak üzere
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from src.swarm_core.swarm_core.collision_avoidance.ca_layer import (
    CollisionAvoidanceLayer,
    NeighborVec,
)

# ------------------------------------------------------------------ #
#  Sabitler                                                            #
# ------------------------------------------------------------------ #
DT = 0.05          # 20 Hz
SAFETY_R = 1.5     # geçme kriteri (m)
MAX_OSC = 2        # max izin verilen yön ters dönmesi
MAX_Z_DEV = 0.05   # CA Z etkisi tavanı (m)


# ------------------------------------------------------------------ #
#  Kinematik simülatör                                                 #
# ------------------------------------------------------------------ #

class Drone:
    def __init__(self, pos: np.ndarray, goal: np.ndarray, speed: float = 2.0):
        self.pos   = pos.astype(float)
        self.goal  = goal.astype(float)
        self.speed = speed
        self.vel   = np.zeros(3)
        self.layer = CollisionAvoidanceLayer({'dt': DT})
        self.layer.reset(np.zeros(3))
        self._prev_vxy_sign = None
        self.osc_count = 0
        self.z0 = float(pos[2])   # başlangıç irtifası

    def formation_vel(self) -> np.ndarray:
        """Hedefe doğru sabit hız komutu (Formation Node simülasyonu)."""
        diff = self.goal - self.pos
        d = np.linalg.norm(diff)
        if d < 0.1:
            return np.zeros(3)
        return (diff / d) * self.speed

    def step(self, others: list['Drone']) -> None:
        vf = self.formation_vel()

        neighbors = []
        for o in others:
            rel = o.pos - self.pos
            dist = float(np.linalg.norm(rel))
            neighbors.append(NeighborVec(
                rel_x=float(rel[0]),
                rel_y=float(rel[1]),
                rel_z=float(rel[2]),
                distance=dist,
            ))

        v_cmd, risk = self.layer.compute(vf, neighbors)

        if not risk:
            self.layer.reset(v_cmd)

        # Salınım tespiti: XY hız yönü ters döndü mü?
        vxy = v_cmd[:2].copy()
        vxy_h = np.linalg.norm(vxy)
        if vxy_h > 0.1 and self._prev_vxy_sign is not None:
            cos_a = np.dot(vxy, self._prev_vxy_sign) / (
                vxy_h * np.linalg.norm(self._prev_vxy_sign))
            if cos_a < -0.5:
                self.osc_count += 1
        if vxy_h > 0.1:
            self._prev_vxy_sign = vxy.copy()

        self.vel = v_cmd
        self.pos = self.pos + v_cmd * DT


def run_scenario(
    drones: list[Drone],
    steps: int,
    name: str,
    plot: bool = False,
) -> dict:
    """Senaryoyu çalıştır, metrikleri döndür."""
    history = {i: [] for i in range(len(drones))}
    min_dist = float('inf')

    for _ in range(steps):
        for i, d in enumerate(drones):
            others = [drones[j] for j in range(len(drones)) if j != i]
            d.step(others)
            history[i].append(d.pos.copy())

        for i in range(len(drones)):
            for j in range(i + 1, len(drones)):
                dist = float(np.linalg.norm(drones[i].pos - drones[j].pos))
                if dist < min_dist:
                    min_dist = dist

    max_osc   = max(d.osc_count for d in drones)
    max_z_dev = max(abs(d.pos[2] - d.z0) for d in drones)

    passed = (
        min_dist  >= SAFETY_R and
        max_osc   <= MAX_OSC  and
        max_z_dev <= MAX_Z_DEV
    )

    result = {
        'name':      name,
        'passed':    passed,
        'min_dist':  min_dist,
        'max_osc':   max_osc,
        'max_z_dev': max_z_dev,
        'history':   history,
        'n_drones':  len(drones),
    }

    status = 'PASS' if passed else 'FAIL'
    print(
        f"[{status}] {name:<30}  "
        f"min_dist={min_dist:.3f}m  "
        f"osc={max_osc}  "
        f"Z_dev={max_z_dev:.4f}m"
    )
    if not passed:
        if min_dist < SAFETY_R:
            print(f"       ✗ çarpışma: {min_dist:.3f} < {SAFETY_R}m")
        if max_osc > MAX_OSC:
            print(f"       ✗ salınım: {max_osc} > {MAX_OSC}")
        if max_z_dev > MAX_Z_DEV:
            print(f"       ✗ Z kayması: {max_z_dev:.4f} > {MAX_Z_DEV}m")

    if plot:
        _plot_scenario(result)

    return result


# ------------------------------------------------------------------ #
#  Senaryolar                                                          #
# ------------------------------------------------------------------ #

def scenario_head_on(plot=False) -> dict:
    """Kafa kafaya 2.0 m/s: temel doğruluk testi."""
    drones = [
        Drone(np.array([ 5.0, 0.0, -15.0]), np.array([-5.0, 0.0, -15.0]), speed=2.0),
        Drone(np.array([-5.0, 0.0, -15.0]), np.array([ 5.0, 0.0, -15.0]), speed=2.0),
    ]
    return run_scenario(drones, steps=200, name='kafa_kafaya_2ms', plot=plot)


def scenario_head_on_25(plot=False) -> dict:
    """Kafa kafaya 2.5 m/s: SITL yarışma hızı — force dominance testi."""
    drones = [
        Drone(np.array([ 7.5, 0.3, -15.0]), np.array([-7.5,  0.3, -15.0]), speed=2.5),
        Drone(np.array([-7.5, 0.0, -15.0]), np.array([ 7.5,  0.0, -15.0]), speed=2.5),
    ]
    return run_scenario(drones, steps=240, name='kafa_kafaya_25ms', plot=plot)


def scenario_three_way(plot=False) -> dict:
    """Üçlü simetrik: üçgen köşelerinden merkeze."""
    r = 6.0
    angles = [90, 210, 330]
    drones = [
        Drone(
            np.array([r * math.cos(math.radians(a)),
                      r * math.sin(math.radians(a)), -15.0]),
            np.array([0.0, 0.0, -15.0]),
        )
        for a in angles
    ]
    return run_scenario(drones, steps=300, name='uclu_simetrik', plot=plot)


def scenario_sandwich(plot=False) -> dict:
    """Sandwich: orta drone iki yandan sıkışır."""
    drones = [
        Drone(np.array([-6.0,  0.0, -15.0]), np.array([ 6.0,  0.0, -15.0])),
        Drone(np.array([ 6.0,  0.0, -15.0]), np.array([-6.0,  0.0, -15.0])),
        Drone(np.array([ 0.0,  0.0, -15.0]), np.array([ 0.0,  5.0, -15.0])),
    ]
    return run_scenario(drones, steps=200, name='sandwich', plot=plot)


def scenario_hover_stability(plot=False) -> dict:
    """Hover kararlılığı: komşu yakınken salınım yok mu?"""
    drones = [
        Drone(np.array([0.0, 0.0, -15.0]), np.array([0.0, 0.0, -15.0])),   # hover
        Drone(np.array([2.2, 0.0, -15.0]), np.array([2.2, 0.0, -15.0])),   # hover yakında
    ]
    return run_scenario(drones, steps=200, name='hover_kararliligi', plot=plot)


def scenario_pass_through(plot=False) -> dict:
    """Pass-through: formasyon çapraz geçişte dağılıyor mu?"""
    drones = [
        Drone(np.array([-6.0, -2.0, -15.0]), np.array([ 6.0,  2.0, -15.0])),
        Drone(np.array([-6.0,  2.0, -15.0]), np.array([ 6.0, -2.0, -15.0])),
    ]
    return run_scenario(drones, steps=200, name='capraz_gecis', plot=plot)


def scenario_z_invariance(plot=False) -> dict:
    """Z-kilit: farklı irtifalarda yaklaşma — CA Z değiştirmemeli."""
    drones = [
        Drone(np.array([ 5.0, 0.0, -15.0]), np.array([-5.0, 0.0, -15.0])),
        Drone(np.array([-5.0, 0.0, -17.0]), np.array([ 5.0, 0.0, -17.0])),
    ]
    return run_scenario(drones, steps=200, name='z_invariance', plot=plot)


# ------------------------------------------------------------------ #
#  Grafik (opsiyonel)                                                  #
# ------------------------------------------------------------------ #

def _plot_scenario(result: dict) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (matplotlib yok — grafik atlandı)")
        return

    fig, ax = plt.subplots(figsize=(7, 7))
    colors = ['tab:blue', 'tab:orange', 'tab:green', 'tab:red']
    for i, traj in result['history'].items():
        pts = np.array(traj)
        ax.plot(pts[:, 0], pts[:, 1], color=colors[i % len(colors)],
                label=f'Drone {i+1}')
        ax.plot(*pts[0, :2], 'o', color=colors[i % len(colors)])
        ax.plot(*pts[-1, :2], 's', color=colors[i % len(colors)])

    # Emniyet daireleri (son konum)
    for i in range(result['n_drones']):
        pos = result['history'][i][-1]
        circle = plt.Circle(pos[:2], SAFETY_R / 2, fill=False,
                            linestyle='--', color='gray', alpha=0.4)
        ax.add_patch(circle)

    status = 'PASS' if result['passed'] else 'FAIL'
    ax.set_title(
        f"{result['name']} [{status}]  "
        f"min={result['min_dist']:.2f}m  osc={result['max_osc']}"
    )
    ax.set_xlabel('X (m, Kuzey)')
    ax.set_ylabel('Y (m, Doğu)')
    ax.legend()
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(f"/tmp/ca_{result['name']}.png", dpi=120)
    print(f"  → grafik: /tmp/ca_{result['name']}.png")
    plt.close()


# ------------------------------------------------------------------ #
#  Ana akış                                                            #
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--plot', action='store_true', help='Grafik kaydet')
    args = parser.parse_args()

    print("=" * 65)
    print("ca_layer kinematik sim")
    print(f"DT={DT}s  SAFETY_R={SAFETY_R}m  MAX_OSC={MAX_OSC}  MAX_Z_DEV={MAX_Z_DEV}m")
    print("=" * 65)

    scenarios = [
        scenario_head_on,
        scenario_head_on_25,
        scenario_three_way,
        scenario_sandwich,
        scenario_hover_stability,
        scenario_pass_through,
        scenario_z_invariance,
    ]

    results = [s(plot=args.plot) for s in scenarios]

    passed = sum(1 for r in results if r['passed'])
    total  = len(results)

    print("=" * 65)
    print(f"Sonuç: {passed}/{total} PASS")
    if passed < total:
        print("BAŞARISIZ senaryolar:")
        for r in results:
            if not r['passed']:
                print(f"  - {r['name']}")
    print("=" * 65)

    sys.exit(0 if passed == total else 1)


if __name__ == '__main__':
    main()
