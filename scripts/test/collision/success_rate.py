#!/usr/bin/env python3
"""success_rate.py — Senaryo kategorilerine göre kaçınma başarı oranı (%).

Offline kinematik sim (ca_sim) üzerinden, raporun istediği iki başlangıç
varyasyonu için kaçınma başarı oranını yüzde bazında hesaplar ve yayın
kalitesinde Türkçe çubuk grafik + ayrıntı tablosu (CSV) üretir.

Kaçınma BAŞARISI tanımı: koşu boyunca İHA-İHA min mesafesi emniyet
yarıçapının (1.5 m) altına HİÇ inmedi (= çarpışma yok). Osilasyon ayrı bir
kalite metriğidir, burada ayrıca raporlanır ama başarı kriterini düşürmez.

SITL doğrulama: kafa-kafaya temsilci vaka SITL'de koşuldu (Fig.1); bu script
o SITL min değerini grafikte referans çizgisi olarak işaretleyebilir.

KULLANIM:
    python3 success_rate.py --out fig2_basari --sitl-headon 1.60
"""

import argparse
import csv
import os
import shutil
import subprocess
import sys

import ca_sim
import scenarios


def _auto_open(path: str) -> None:
    """Figürü otomatik aç: VS Code sekmesi, olmazsa xdg-open."""
    for opener in ('code', 'xdg-open'):
        if shutil.which(opener):
            try:
                subprocess.Popen([opener, path],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                print(f'  → otomatik açıldı ({opener}): {path}')
                return
            except Exception:  # noqa: BLE001
                continue
    print(f'  (otomatik açılamadı — elle aç: {path})')


# Raporun iki başlangıç varyasyonu → senaryo üyelikleri (encounter tipine göre).
CATEGORIES = {
    'Kafa-kafaya': [
        'head_on', 'head_on_offset', 'perfect_symmetric_headon',
        'local_minimum', 'high_closing_speed',
    ],
    'Çapraz': [
        'crossing_90', 'crossing_45', 'crossing_wide',
        'crossing_diff_alt', 'four_corner_cross', 'sandwich_crossthrough',
    ],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='fig2_basari_orani')
    ap.add_argument('--safety', type=float, default=1.5)
    ap.add_argument('--sitl-headon', type=float, default=None,
                    help='SITL kafa-kafaya min mesafe (referans çizgi)')
    ap.add_argument('--csv-out', default='tablo_basari.csv')
    args = ap.parse_args()

    rows = []          # (kategori, senaryo, min, marj, çarpışma_yok, osilasyonsuz)
    summary = {}       # kategori -> (başarı, toplam, min_listesi)
    for cat, names in CATEGORIES.items():
        succ = 0
        mins = []
        for name in names:
            s = scenarios.get(name)
            r = ca_sim.run_scenario(s)
            mn = r['min_dist']
            no_coll = mn >= args.safety - 1e-3
            no_osc = r['osc'] <= 2
            succ += int(no_coll)
            mins.append(mn)
            rows.append((cat, name, mn, mn - args.safety, no_coll, no_osc))
        summary[cat] = (succ, len(names), mins)

    # --- Tablo CSV ---
    with open(args.csv_out, 'w') as f:
        w = csv.writer(f)
        w.writerow(['kategori', 'senaryo', 'min_mesafe_m', 'marj_m',
                    'carpisma_yok', 'osilasyonsuz'])
        for r in rows:
            w.writerow([r[0], r[1], f'{r[2]:.2f}', f'{r[3]:.2f}',
                        int(r[4]), int(r[5])])

    # --- Konsol özeti ---
    print(f'\n{"KATEGORİ":14s} {"BAŞARI":>8s} {"%":>6s} '
          f'{"min(en kötü)":>13s} {"min(ort)":>9s}')
    print('-' * 56)
    for cat, (succ, tot, mins) in summary.items():
        pct = 100.0 * succ / tot
        print(f'{cat:14s} {succ:>4d}/{tot:<3d} {pct:>5.0f}% '
              f'{min(mins):>11.2f}m {sum(mins)/len(mins):>8.2f}m')
    print(f'\n  Ayrıntı tablosu: {os.path.abspath(args.csv_out)}')

    # --- Çubuk grafik (Türkçe, yayın kalitesi) ---
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('  (matplotlib yok — grafik atlandı)')
        return 0

    plt.rcParams.update({
        'font.family': 'serif', 'font.size': 14,
        'axes.labelsize': 15, 'xtick.labelsize': 14, 'ytick.labelsize': 13,
        'axes.linewidth': 1.0, 'legend.fontsize': 12,
    })

    cats = list(summary.keys())
    pcts = [100.0 * summary[c][0] / summary[c][1] for c in cats]
    ns = [f'n={summary[c][1]}' for c in cats]

    fig, ax = plt.subplots(figsize=(6.0, 4.4), dpi=300)
    bars = ax.bar(cats, pcts, width=0.55,
                  color=['#1f77b4', '#2ca02c'], edgecolor='black', lw=1.0)
    for b, p, n in zip(bars, pcts, ns):
        ax.text(b.get_x() + b.get_width() / 2, p + 1.5,
                f'%{p:.0f}\n({n})', ha='center', va='bottom', fontsize=13)
    ax.set_ylabel('Kaçınma başarı oranı (%)')
    ax.set_ylim(0, 112)
    ax.axhline(100, color='gray', ls=':', lw=1.0)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.grid(True, axis='y', alpha=0.3, lw=0.5)
    fig.tight_layout(pad=0.4)
    fig.savefig(f'{args.out}.pdf')
    fig.savefig(f'{args.out}.png')
    plt.close(fig)
    print(f'  Başarı grafiği:  {args.out}.pdf / .png')
    _auto_open(f'{args.out}.png')
    return 0


if __name__ == '__main__':
    sys.exit(main())
