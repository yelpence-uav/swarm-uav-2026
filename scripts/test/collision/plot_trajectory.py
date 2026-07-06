#!/usr/bin/env python3
"""plot_trajectory.py — Dron yörüngelerini Doğu–Kuzey düzleminde çiz.

trajectory_logger.py'nin ürettiği {run}_traj.csv'yi okur, her dronun
yolunu çizer. CA aktif örnekleri KALIN/renkli işaretler → sağ-el
yaylanması göz ile görünür: drone1 batıya, drone2 doğuya büker, kesişmeden
sıyrılırlar. headon_proof.sh'in sayısal verdict'inin GÖRSEL tamamlayıcısı.

KULLANIM:
    python3 plot_trajectory.py <run_traj.csv> [çıktı.png]
"""

import csv
import shutil
import subprocess
import sys
from collections import defaultdict


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


def main() -> int:
    if len(sys.argv) < 2:
        print('kullanım: plot_trajectory.py <run_traj.csv> [out.png]')
        return 2
    csv_path = sys.argv[1]
    out_png = sys.argv[2] if len(sys.argv) > 2 else csv_path.rsplit('.', 1)[0] + '.png'

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('  (matplotlib yok — grafik atlandı; CSV yine kullanılabilir)')
        return 0

    # drone -> sıralı (t, north, east, ca) örnekleri
    data: dict[int, list] = defaultdict(list)
    try:
        with open(csv_path) as f:
            for row in csv.DictReader(f):
                data[int(row['drone'])].append((
                    float(row['t_s']), float(row['north_m']),
                    float(row['east_m']), int(row['ca']),
                ))
    except FileNotFoundError:
        print(f'  CSV yok: {csv_path}')
        return 1
    if not data:
        print('  CSV boş — grafik yok.')
        return 1

    fig, ax = plt.subplots(figsize=(7, 7))
    colors = {1: 'tab:blue', 2: 'tab:orange', 3: 'tab:green'}
    for did in sorted(data):
        pts = data[did]
        east = [p[2] for p in pts]    # Doğu → yatay eksen
        north = [p[1] for p in pts]   # Kuzey → dikey eksen
        ca = [p[3] for p in pts]
        c = colors.get(did, 'gray')
        ax.plot(east, north, '-', color=c, lw=1.2, alpha=0.6,
                label=f'drone{did}')
        # CA aktif örnekleri vurgula (sağ-el kaçışının olduğu segment)
        ce = [e for e, a in zip(east, ca) if a]
        cn = [n for n, a in zip(north, ca) if a]
        if ce:
            ax.plot(ce, cn, 'o', color=c, ms=4, alpha=0.9)
        ax.plot(east[0], north[0], 'o', color=c, ms=10, mfc='white', mew=2)   # başlangıç
        ax.plot(east[-1], north[-1], 's', color=c, ms=10)                     # bitiş

    ax.set_aspect('equal')
    ax.set_xlabel('Doğu (m)')
    ax.set_ylabel('Kuzey (m)')
    ax.set_title('Head-on yörüngeleri — ○ başlangıç, □ bitiş, • CA aktif\n'
                 'sağ-el kuralı: her dron kendi sağına yaylanıp geçer')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.savefig(out_png, dpi=120, bbox_inches='tight')
    plt.close(fig)
    print(f'  yörünge grafiği: {out_png}')
    _auto_open(out_png)
    return 0


if __name__ == '__main__':
    sys.exit(main())
