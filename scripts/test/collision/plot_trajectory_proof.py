#!/usr/bin/env python3
"""plot_trajectory_proof.py — Oskilasyon-yok kanıtı için iki panel.

Panel 1 (sol): Her İHA'nın Kuzey-Doğu yörüngesi.
  → Düzgün S-eğrisi = oskilasyon yok; zigzag olsaydı çizgi kıvrımlı olurdu.

Panel 2 (sağ): Her çiftin (1-2, 1-3, 2-3) mesafesi ayrı ayrı zaman ekseninde.
  → Min-mesafe grafiğindeki çoklu dipler oskilasyon değil, farklı çiftlerin
    sırayla yaklaşmasıdır. Bunu ayrıştırarak gösterir.

KULLANIM:
    python3 plot_trajectory_proof.py \
        --traj headon_proof_235040_traj.csv \
        --dist headon_proof_235040.csv
"""

import argparse
import csv
import shutil
import subprocess
import sys
from collections import defaultdict


def _auto_open(path):
    for opener in ('code', 'xdg-open'):
        if shutil.which(opener):
            try:
                subprocess.Popen([opener, path],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                print(f'  → açıldı ({opener}): {path}')
                return
            except Exception:
                continue


def _load_traj(path):
    data = defaultdict(lambda: {'t': [], 'n': [], 'e': [], 'ca': []})
    with open(path) as f:
        for row in csv.DictReader(f):
            d = int(row['drone'])
            data[d]['t'].append(float(row['t_s']))
            data[d]['n'].append(float(row['north_m']))
            data[d]['e'].append(float(row['east_m']))
            data[d]['ca'].append(int(row.get('ca', 0)))
    return data


def _load_dist(path):
    """min_dist CSV → t, min_dist (genel)"""
    t, d = [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            t.append(float(row['t_s']))
            d.append(float(row['min_dist_m']))
    return t, d


def _pair_distances(traj):
    """Her t anında tüm çiftlerin mesafesini hesapla."""
    import math
    # Ortak zaman noktaları: drone 1 zamanlarını referans al
    drones = sorted(traj.keys())
    if len(drones) < 2:
        return {}

    ref_times = traj[drones[0]]['t']
    # Her drone için kuzey/doğuyu zaman indeksine göre eşleştir
    pos = {}
    for d in drones:
        pos[d] = {t: (n, e) for t, n, e in
                  zip(traj[d]['t'], traj[d]['n'], traj[d]['e'])}

    pairs = {}
    for i in range(len(drones)):
        for j in range(i + 1, len(drones)):
            da, db = drones[i], drones[j]
            key = f'İHA {da}-{db}'
            pt, pd = [], []
            for t in ref_times:
                if t in pos[da] and t in pos[db]:
                    na, ea = pos[da][t]
                    nb, eb = pos[db][t]
                    dist = math.hypot(na - nb, ea - eb)
                    pt.append(t)
                    pd.append(dist)
            pairs[key] = (pt, pd)
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--traj', required=True)
    ap.add_argument('--dist', required=True)
    ap.add_argument('--safety', type=float, default=1.5)
    ap.add_argument('--out', default='fig_trajectory_proof')
    ap.add_argument('--no-open', action='store_true')
    args = ap.parse_args()

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import numpy as np
    except ImportError:
        print('matplotlib yok — pip install matplotlib')
        return 1

    plt.rcParams.update({
        'font.family': 'serif',
        'font.size': 17,
        'axes.labelsize': 18,
        'xtick.labelsize': 14,
        'ytick.labelsize': 14,
        'axes.linewidth': 1.2,
        'mathtext.fontset': 'dejavuserif',
        'legend.fontsize': 13,
        'legend.framealpha': 0.95,
    })

    traj = _load_traj(args.traj)
    t_all, d_all = _load_dist(args.dist)
    pairs = _pair_distances(traj)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.2), dpi=300,
                                   gridspec_kw={'width_ratios': [1, 1.2]})
    fig.subplots_adjust(wspace=0.35)

    # ── Panel 1: Doğu Sapması (ΔE) – Zaman, CA penceresine zoom ──
    # En doğrudan oskilasyon kanıtı: yanal sapma tek hörgüç = oskilasyon yok;
    # ileri-geri = oskilasyon var. ΔE = E(t) − E(t=0) ile GPS offset'i sıfırla.
    drone_colors = {1: '#1f77b4', 2: '#d62728'}
    active_drones = [1, 2]

    # CA penceresi
    ca_start_all, ca_end_all = [], []
    for d in active_drones:
        ca_times = [traj[d]['t'][i] for i in range(len(traj[d]['ca']))
                    if traj[d]['ca'][i]]
        if ca_times:
            ca_start_all.append(ca_times[0])
            ca_end_all.append(ca_times[-1])

    # CA pair pencereleri: hangi band hangi çift
    # Veriden türetildi: t=8.1-8.5 → 1-3 çifti, t=20.9-24.3 → 1-2 çifti
    ca_bands = [
        (8.1,  8.5,  '#2ca02c', 'CA: İHA 1–3'),
        (20.9, 24.3, '#ff7f0e', 'CA: İHA 1–2'),
    ]
    t_lo = 5.0
    t_hi = 28.0

    ax1.axhline(0, color='gray', ls='--', lw=1.2, zorder=1)
    for (bt0, bt1, bc, blabel) in ca_bands:
        ax1.axvspan(bt0, bt1, color=bc, alpha=0.18, zorder=0, label=blabel)

    for d in active_drones:
        t  = traj[d]['t']
        e0 = traj[d]['e'][0]
        de = [ei - e0 for ei in traj[d]['e']]
        c  = drone_colors[d]
        mask = [i for i, ti in enumerate(t) if t_lo <= ti <= t_hi]
        tm = [t[i]  for i in mask]
        dm = [de[i] for i in mask]
        ax1.plot(tm, dm, '-', color=c, lw=2.2, label=f'İHA {d}', zorder=3)

    ax1.set_xlabel('Zaman (s)')
    ax1.set_ylabel('Doğu Sapması  ΔE (m)')
    ax1.set_title('Yanal Sapma – Zaman\n'
                  '2 hörgüç = 2 ayrı çift, oskilasyon degil', fontsize=15, pad=6)
    ax1.set_xlim(t_lo, t_hi)
    ax1.grid(True, alpha=0.25, lw=0.5)
    ax1.legend(loc='lower right', fontsize=11)

    ax1.text(0.03, 0.97,
             'Her hörgüç farkli bir\nİHA ciiftiyle CA manevrasi',
             transform=ax1.transAxes, ha='left', va='top', fontsize=11,
             bbox=dict(boxstyle='round,pad=0.3', fc='#e8f5e9',
                       ec='#2ca02c', lw=1.2))

    # ── Panel 2: Çift bazında mesafe ──
    pair_colors = ['#1f77b4', '#d62728', '#2ca02c', '#9467bd']
    ax2.axhspan(0, args.safety, color='red', alpha=0.07, zorder=0)
    ax2.axhline(args.safety, color='red', ls='--', lw=1.8,
                label=f'Emniyet = {args.safety:.1f} m')

    for idx, (label, (pt, pd)) in enumerate(pairs.items()):
        c = pair_colors[idx % len(pair_colors)]
        ax2.plot(pt, pd, '-', color=c, lw=1.8, label=label)

    ax2.set_xlabel('Zaman (s)')
    ax2.set_ylabel('Mesafe (m)')
    ax2.set_title('Çift Bazında İHA-İHA Mesafesi\n(Dipler = farklı çiftler, oskilasyon değil)',
                  fontsize=15, pad=6)
    ax2.set_xlim(0, max(t_all))
    ax2.set_ylim(0, max(d_all) * 1.25)
    ax2.grid(True, alpha=0.25, lw=0.5)
    ax2.legend(loc='upper right', fontsize=12)

    pdf = f'{args.out}.pdf'
    png = f'{args.out}.png'
    fig.savefig(pdf, bbox_inches='tight')
    fig.savefig(png, bbox_inches='tight')
    plt.close(fig)
    print(f'  Yörünge kanıt figürü: {pdf}')
    print(f'                        {png}')
    if not args.no_open:
        _auto_open(png)
    return 0


if __name__ == '__main__':
    sys.exit(main())
