#!/usr/bin/env python3
"""plot_success_rate.py — Çarpışmadan kaçınma başarı istatistikleri.

İki panel:
  Sol  — Her koşunun minimum mesafesi (scatter + güven bandı + emniyet çizgisi)
  Sağ  — PASS/FAIL başarı oranı çubuk grafiği

KULLANIM:
    python3 plot_success_rate.py --safety 1.5 --out fig_success \
        analysis/collision_sitl/headon_proof_*.csv
"""

import argparse
import csv
import os
import shutil
import subprocess
import sys


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


def _min_dist(path):
    d = [float(r['min_dist_m']) for r in csv.DictReader(open(path))]
    return min(d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv', nargs='+')
    ap.add_argument('--safety', type=float, default=1.5)
    ap.add_argument('--warn',   type=float, default=2.0)
    ap.add_argument('--out',    default='fig_success')
    ap.add_argument('--scenario', default='Kafa-kafaya (Head-on)')
    ap.add_argument('--no-open', action='store_true')
    args = ap.parse_args()

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import numpy as np
    except ImportError:
        print('matplotlib/numpy yok — pip install matplotlib numpy')
        return 1

    plt.rcParams.update({
        'font.family': 'serif',
        'font.size': 18,
        'axes.labelsize': 20,
        'xtick.labelsize': 15,
        'ytick.labelsize': 15,
        'axes.linewidth': 1.2,
        'mathtext.fontset': 'dejavuserif',
        'legend.frameon': True,
        'legend.framealpha': 0.95,
        'legend.fontsize': 14,
    })

    # --- veri yükle ---
    mins = []
    for path in args.csv:
        if 'events' in path or 'traj' in path:
            continue
        try:
            mins.append(_min_dist(path))
        except Exception:
            pass

    mins = sorted(mins)
    n = len(mins)
    passes = [m for m in mins if m >= args.safety]
    fails  = [m for m in mins if m <  args.safety]
    pct    = 100.0 * len(passes) / n if n else 0.0

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5.5), dpi=300,
                                   gridspec_kw={'width_ratios': [1.7, 1]})
    fig.subplots_adjust(wspace=0.38)

    # ── Panel 1: her koşu minimum mesafesi ──
    x_all    = np.arange(1, n + 1)
    colors1  = ['#2ca02c' if m >= args.safety else '#d62728' for m in mins]

    ax1.axhspan(0,           args.safety, color='red',  alpha=0.07, zorder=0)
    ax1.axhspan(args.safety, args.warn,   color='gold', alpha=0.10, zorder=0)
    ax1.axhline(args.safety, color='red',  ls='--', lw=1.8,
                label=f'Emniyet = {args.safety:.1f} m')
    ax1.axhline(args.warn,   color='gray', ls=':',  lw=1.4,
                label=f'Uyarı = {args.warn:.1f} m')

    ax1.scatter(x_all, mins, c=colors1, s=70, zorder=5,
                edgecolors='black', linewidths=0.5)

    # ortalama ± std bant
    mn_arr = np.array(mins)
    mu, sd = mn_arr.mean(), mn_arr.std()
    ax1.axhline(mu, color='#1f77b4', ls='-', lw=1.5,
                label=f'Ort. = {mu:.2f} m')
    ax1.axhspan(mu - sd, mu + sd, color='#1f77b4', alpha=0.12,
                label=f'±1σ = {sd:.2f} m')

    # PASS/FAIL etiket noktaları
    pass_patch = mpatches.Patch(color='#2ca02c', label=f'PASS ({len(passes)})')
    fail_patch = mpatches.Patch(color='#d62728', label=f'FAIL ({len(fails)})')

    ax1.set_xlabel('Koşu numarası')
    ax1.set_ylabel('Minimum İHA-İHA Mesafesi (m)')
    ax1.set_xlim(0.3, n + 0.7)
    ax1.set_ylim(0, max(mins) * 1.30)
    ax1.set_xticks(x_all)
    ax1.grid(True, alpha=0.25, lw=0.5)
    ax1.legend(handles=[*ax1.get_legend_handles_labels()[0], pass_patch, fail_patch],
               loc='upper left', fontsize=12, ncol=2, columnspacing=0.8)

    # başarı oranı rozeti — sol panel üst sağ
    ax1.text(0.97, 0.97,
             f'Başarı Oranı\n%{pct:.0f}  ({len(passes)}/{n})',
             transform=ax1.transAxes, ha='right', va='top', fontsize=13,
             bbox=dict(boxstyle='round,pad=0.4', fc='#e8f5e9',
                       ec='#2ca02c', lw=1.4))

    # ── Panel 2: başarı oranı çubuğu ──
    categories = ['PASS', 'FAIL']
    counts     = [len(passes), len(fails)]
    bar_colors = ['#2ca02c', '#d62728']
    bars = ax2.bar(categories, counts, color=bar_colors,
                   edgecolor='black', linewidth=0.8, width=0.5)

    for bar, cnt in zip(bars, counts):
        pct_b = 100.0 * cnt / n
        ax2.text(bar.get_x() + bar.get_width() / 2,
                 bar.get_height() + 0.15,
                 f'{cnt}\n(%{pct_b:.0f})',
                 ha='center', va='bottom', fontsize=15, fontweight='bold')

    ax2.set_ylabel('Koşu Sayısı')
    ax2.set_ylim(0, n * 1.30)
    ax2.set_title(f'{args.scenario}\nN = {n} koşu', fontsize=15)
    ax2.grid(True, axis='y', alpha=0.25, lw=0.5)
    ax2.yaxis.set_major_locator(plt.MaxNLocator(integer=True))

    pdf = f'{args.out}.pdf'
    png = f'{args.out}.png'
    fig.savefig(pdf, bbox_inches='tight')
    fig.savefig(png, bbox_inches='tight')
    plt.close(fig)
    print(f'  Başarı istatistik figürü: {pdf}')
    print(f'                            {png}')
    print(f'  N={n}  PASS={len(passes)} (%{pct:.0f})  FAIL={len(fails)}')
    print(f'  Min mesafe aralığı: {min(mins):.3f}–{max(mins):.3f} m')
    print(f'  Ortalama ± std: {mu:.3f} ± {sd:.3f} m')
    if not args.no_open:
        _auto_open(png)
    return 0


if __name__ == '__main__':
    sys.exit(main())
