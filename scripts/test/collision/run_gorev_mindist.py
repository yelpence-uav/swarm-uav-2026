#!/usr/bin/env python3
"""run_gorev_mindist.py — Dinamik görev icrası min mesafe-zaman CSV'si.

TEKNOFEST §5.1 dinamik görev senaryosunu (gorev_dinamik) GERÇEK ca_core ile
(ca_sim, = production collision_avoidance_node kodu) koşar; her tick İHA-İHA
arası min mesafeyi safety_monitor formatında CSV'ye yazar. Sonra
plot_min_distance_ieee.py bu CSV'den jüri grafiğini üretir.

NEDEN ca_sim (apf_sim DEĞİL): apf_sim/apf_core terk edildi (silindi); gerçek
güncel CA v2 ca_core'dadır → bu script onunla koşar.

KULLANIM:
    . ~/ros2_ws/install/setup.bash
    python3 run_gorev_mindist.py
    # sonra grafik:
    python3 plot_min_distance_ieee.py --lang tr --safety 1.5 --warn 2.0 \\
        --out ~/ros2_ws/analysis/collision_sitl/JURI_gorev_mindist \\
        --label "Dinamik Görev" <CSV>
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ca_sim  # noqa: E402
import scenarios  # noqa: E402

OUT_DIR = os.path.expanduser('~/ros2_ws/analysis/collision_sim')


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else 'gorev_formasyon'
    s = scenarios.get(name)
    r = ca_sim.run_scenario(s)
    series = r['series']
    safety = r['safety']

    os.makedirs(OUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUT_DIR, f'{name}_cacore.csv')
    with open(csv_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['t_s', 'min_dist_m', 'safety_radius_m', 'warn_radius_m'])
        for t, d in series:
            w.writerow([f'{t:.3f}', f'{d:.4f}', f'{safety:.3f}', '2.000'])

    gmin = min(d for _, d in series)
    print(f'CSV: {csv_path}')
    print(f'süre={series[-1][0]:.0f}s  örnek={len(series)}  '
          f'global min={gmin:.3f}m  emniyet={safety:.2f}m  '
          f'ihlal={"VAR!" if gmin < safety else "YOK"}')
    print('Fazlar:')
    for ph in s.phases:
        print(f'  t={ph.t_start:>4.0f}s  {ph.label}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
