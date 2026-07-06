#!/usr/bin/env python3
"""plot_ca_analysis.py — Yörünge + Hız + Mesafe grafiklerini üretir.

ROS GEREKTİRMEZ — sadece matplotlib + CSV.

KULLANIM:
    python3 plot_ca_analysis.py /tmp/ca_logs [--out grafik.png] \
        [--safety 1.5] [--drones 1 2 3]

CSV beklentisi (ca_logger.py tarafından üretilir):
    trajectory.csv  → t_s, drone1_x, drone1_y, drone1_z, drone2_x ...
    velocity.csv    → t_s, drone1_vx, drone1_vy, drone1_vz ...
    distance.csv    → t_s, d1_2, d1_3, d2_3 ...

Üç grafik:
  1) Yörünge (XY düzlemi) — pürüzsüz yay vs. testere dişi
  2) Hız büyüklüğü zaman serisi — yumuşak azalma/artma vs. dalgalanma/satürasyon
  3) Mesafe grafiği — r_min altına hiç düşmemeli (kırmızı çizgi)
"""

import argparse
import csv
import math
import os
import sys


def _load_csv(path: str) -> tuple[list, list]:
    """CSV'yi (başlıklar, satırlar) olarak yükler."""
    if not os.path.exists(path):
        return [], []
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return reader.fieldnames or [], rows


def _col(rows, key, cast=float):
    return [cast(r[key]) for r in rows if key in r]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log_dir', help='ca_logger çıktı dizini (/tmp/ca_logs)')
    ap.add_argument('--out', default=None, help='Çıktı PNG yolu')
    ap.add_argument('--safety', type=float, default=1.5,
                    help='Emniyet mesafesi r_min (varsayılan 1.5 m)')
    ap.add_argument('--drones', nargs='+', type=int, default=None,
                    help='Hangi dronlar çizilsin (varsayılan: hepsi)')
    ap.add_argument('--title', default='CA Analiz', help='Grafik başlığı')
    args = ap.parse_args()

    out_png = args.out or os.path.join(args.log_dir, 'ca_analysis.png')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm
    import numpy as np

    # --- Veri yükle ---
    traj_hdr, traj_rows = _load_csv(
        os.path.join(args.log_dir, 'trajectory.csv'))
    vel_hdr, vel_rows = _load_csv(
        os.path.join(args.log_dir, 'velocity.csv'))
    dist_hdr, dist_rows = _load_csv(
        os.path.join(args.log_dir, 'distance.csv'))

    if not traj_rows:
        print('trajectory.csv bulunamadı veya boş.')
        sys.exit(1)

    # Drone ID'lerini başlıktan çıkar
    drone_ids = []
    for h in traj_hdr or []:
        if h.startswith('drone') and h.endswith('_x'):
            did = int(h.split('drone')[1].split('_')[0])
            if args.drones is None or did in args.drones:
                drone_ids.append(did)

    COLORS = ['#1f77b4', '#d62728', '#2ca02c', '#ff7f0e', '#9467bd']

    # --- Grafik düzeni: 3 panel ---
    fig = plt.figure(figsize=(16, 5))
    fig.suptitle(args.title, fontsize=13, fontweight='bold')
    ax_traj = fig.add_subplot(1, 3, 1)
    ax_vel = fig.add_subplot(1, 3, 2)
    ax_dist = fig.add_subplot(1, 3, 3)

    # =========================================================
    # 1) YÖRÜNGE GRAFİĞİ (XY düzlemi)
    # =========================================================
    ax_traj.set_title('Yörünge Grafiği (XY)')
    ax_traj.set_xlabel('X — Kuzey (m)')
    ax_traj.set_ylabel('Y — Doğu (m)')

    for i, did in enumerate(drone_ids):
        xk = f'drone{did}_x'
        yk = f'drone{did}_y'
        if xk not in (traj_hdr or []):
            continue
        xs = _col(traj_rows, xk)
        ys = _col(traj_rows, yk)
        if not xs:
            continue
        color = COLORS[i % len(COLORS)]
        # Yörünge çizgisi
        ax_traj.plot(xs, ys, lw=1.4, color=color, label=f'Drone {did}')
        # Başlangıç ★ / bitiş ●
        ax_traj.scatter([xs[0]], [ys[0]], marker='*', s=120,
                        color=color, zorder=5)
        ax_traj.scatter([xs[-1]], [ys[-1]], marker='o', s=60,
                        color=color, zorder=5)
        # Yörünge yönü oku (ortada)
        mid = len(xs) // 2
        if mid + 1 < len(xs):
            ax_traj.annotate('', xy=(xs[mid + 1], ys[mid + 1]),
                             xytext=(xs[mid], ys[mid]),
                             arrowprops=dict(arrowstyle='->', color=color,
                                             lw=1.5))

    ax_traj.set_aspect('equal')
    ax_traj.grid(True, alpha=0.3)
    ax_traj.legend(fontsize=8)

    # =========================================================
    # 2) HIZ BÜYÜKLÜĞÜ — ZAMAN
    # =========================================================
    ax_vel.set_title('Hız Büyüklüğü — Zaman')
    ax_vel.set_xlabel('Zaman (s)')
    ax_vel.set_ylabel('|v| (m/s)')

    if vel_rows:
        t_vel = _col(vel_rows, 't_s')
        for i, did in enumerate(drone_ids):
            vxk = f'drone{did}_vx'
            vyk = f'drone{did}_vy'
            vzk = f'drone{did}_vz'
            if vxk not in (vel_hdr or []):
                continue
            vxs = _col(vel_rows, vxk)
            vys = _col(vel_rows, vyk)
            vzs = _col(vel_rows, vzk)
            mags = [math.sqrt(x**2 + y**2 + z**2)
                    for x, y, z in zip(vxs, vys, vzs)]
            ax_vel.plot(t_vel[:len(mags)], mags, lw=1.4,
                        color=COLORS[i % len(COLORS)],
                        label=f'Drone {did}')

    # Satürasyon çizgisi (rep_saturation varsayılan 6 m/s)
    ax_vel.axhline(6.0, color='red', ls='--', lw=1.0,
                   label='rep_saturation (6 m/s)')
    ax_vel.grid(True, alpha=0.3)
    ax_vel.legend(fontsize=8)
    ax_vel.set_ylim(bottom=0)

    # =========================================================
    # 3) MESAFE GRAFİĞİ
    # =========================================================
    ax_dist.set_title('İHA-İHA Mesafesi — Zaman')
    ax_dist.set_xlabel('Zaman (s)')
    ax_dist.set_ylabel('Mesafe (m)')

    if dist_rows:
        t_dist = _col(dist_rows, 't_s')
        dist_pairs = [k for k in (dist_hdr or []) if k.startswith('d')]
        for i, pk in enumerate(dist_pairs):
            ds = _col(dist_rows, pk)
            label = pk.replace('_', '-').replace('d', 'Drone ')
            ax_dist.plot(t_dist[:len(ds)], ds, lw=1.4,
                         color=COLORS[i % len(COLORS)], label=label)

        # r_min kırmızı çizgi
        ax_dist.axhline(args.safety, color='red', ls='--', lw=1.5,
                        label=f'r_min = {args.safety} m')
        # Uyarı bandı (r_min..r_min+0.5)
        ax_dist.axhspan(args.safety, args.safety + 0.5,
                        color='gold', alpha=0.15)
        # İhlal bölgesi (kırmızı, r_min altı)
        ax_dist.axhspan(0, args.safety, color='red', alpha=0.08)

        # Global minimum işaret
        all_vals = []
        for pk in dist_pairs:
            all_vals += _col(dist_rows, pk)
        if all_vals:
            gmin = min(all_vals)
            gmin_t = t_dist[all_vals.index(gmin) % len(t_dist)]
            ax_dist.scatter([gmin_t], [gmin], color='red', s=60, zorder=6)
            ax_dist.annotate(f'min={gmin:.2f}m', (gmin_t, gmin),
                             textcoords='offset points', xytext=(5, 8),
                             fontsize=8, color='red')
            violated = sum(1 for v in all_vals if v < args.safety)
            suffix = 'YOK ✓' if violated == 0 else f'{violated} tick ✗'
            ax_dist.set_title(
                f'İHA-İHA Mesafesi — Zaman\n'
                f'min={gmin:.2f}m  |  r_min={args.safety}m  |  İhlal: {suffix}',
                fontsize=9,
            )

    ax_dist.set_ylim(bottom=0)
    ax_dist.grid(True, alpha=0.3)
    ax_dist.legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    print(f'Grafik kaydedildi: {out_png}')


if __name__ == '__main__':
    main()
