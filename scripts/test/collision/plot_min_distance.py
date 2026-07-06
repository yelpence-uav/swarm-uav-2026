#!/usr/bin/env python3
"""plot_min_distance.py — safety_monitor CSV'sinden jüri grafiği üretir.

Şartname: "İHA-İHA Arası Minimum Mesafe - Zaman Grafiği" + emniyet sınırının
asla ihlal edilmediğini görsel göster + en çok yaklaşılan kritik anlar.

Bu script ROS GEREKTİRMEZ — sadece matplotlib. safety_monitor'ün ürettiği
{run}.csv (ve varsa {run}_events.csv) okunur, PNG kaydedilir.

KULLANIM:
    python3 scripts/test/collision/plot_min_distance.py \\
        ~/ros2_ws/analysis/collision_sitl/swap_test1.csv
"""

import csv
import os
import sys


def _read_csv(path: str):
    """Min-mesafe–zaman CSV'sini okur.

    İki kaynağı da okur: safety_monitor (SITL) CSV'si tüm sütunları içerir;
    apf_sim (offline) CSV'si yalnızca t_s,min_dist_m,safety_radius_m içerir.
    Eksik sütunlar (violation, warn_radius_m) türetilir → tek script iki
    kaynağı da çizer (jüri grafiği, rapor A1).
    """
    t, dist, viol = [], [], []
    safety = warn = None
    with open(path) as f:
        for row in csv.DictReader(f):
            t.append(float(row['t_s']))
            d = float(row['min_dist_m'])
            dist.append(d)
            if 'safety_radius_m' in row:
                safety = float(row['safety_radius_m'])
            if 'warn_radius_m' in row:
                warn = float(row['warn_radius_m'])
            # İhlal sütunu yoksa (sim) emniyet eşiğinden türet.
            if 'violation' in row:
                viol.append(int(row['violation']))
            elif safety is not None:
                viol.append(int(d < safety))
            else:
                viol.append(0)
    # Varsayılanlar: sim CSV'sinde safety var, warn yok → emniyetin üstü.
    if safety is None:
        safety = 1.5
    if warn is None:
        warn = safety + 0.5
    return t, dist, viol, safety, warn


def _read_events(path: str):
    """Kritik yaklaşma anları CSV'sini okur (varsa)."""
    evs = []
    if not os.path.exists(path):
        return evs
    with open(path) as f:
        for row in csv.DictReader(f):
            evs.append((
                float(row['t_s']), row['pair'], float(row['min_dist_m']),
                int(row['excluded']),
            ))
    return evs


def main() -> None:
    if len(sys.argv) < 2:
        print('Kullanım: plot_min_distance.py <csv_yolu> [çıktı.png]')
        sys.exit(1)

    csv_path = sys.argv[1]
    out_png = (
        sys.argv[2] if len(sys.argv) > 2
        else os.path.splitext(csv_path)[0] + '.png'
    )

    import matplotlib
    matplotlib.use('Agg')  # ekransız ortam için
    import matplotlib.pyplot as plt

    t, dist, viol, safety, warn = _read_csv(csv_path)
    events_path = os.path.splitext(csv_path)[0] + '_events.csv'
    evs = _read_events(events_path)

    if not t:
        print('CSV boş.')
        sys.exit(1)

    fig, ax = plt.subplots(figsize=(11, 5))

    # Min mesafe eğrisi
    ax.plot(t, dist, color='#1f77b4', lw=1.6, label='Min İHA-İHA mesafesi')

    # Emniyet yarıçapı (kırmızı çizgi) — ihlal edilmemeli
    ax.axhline(safety, color='red', ls='--', lw=1.5,
               label=f'Emniyet sınırı ({safety:.2f} m)')
    # Uyarı bandı (sarı bölge)
    ax.axhspan(safety, warn, color='gold', alpha=0.15,
               label=f'Uyarı bölgesi (<{warn:.2f} m)')
    # İhlal bölgesi (kırmızı, emniyet altı)
    ax.axhspan(0, safety, color='red', alpha=0.08)

    # İhlal noktaları (varsa)
    vt = [t[i] for i in range(len(t)) if viol[i]]
    vd = [dist[i] for i in range(len(dist)) if viol[i]]
    if vt:
        ax.scatter(vt, vd, color='red', s=18, zorder=5, label='İHLAL')

    # Kritik yaklaşma anları (dipler) işaretle
    for (et, pair, emin, excl) in evs:
        ax.scatter([et], [emin], color='darkorange', s=40, zorder=6,
                   marker='v')
        etk = ' (iniş)' if excl else ''
        ax.annotate(f'{emin:.2f}m\ndrone{pair}{etk}', (et, emin),
                    textcoords='offset points', xytext=(0, 10),
                    ha='center', fontsize=7, color='#8a4b00')

    gmin = min(dist)
    title = (
        'İHA-İHA Arası Minimum Mesafe — Zaman\n'
        f'En küçük mesafe: {gmin:.3f} m  |  '
        f'Emniyet sınırı: {safety:.2f} m  |  '
        f'İhlal: {"YOK ✓" if not vt else f"{len(vt)} tick ✗"}'
    )
    ax.set_title(title, fontsize=11)
    ax.set_xlabel('Zaman (s)')
    ax.set_ylabel('Minimum mesafe (m)')
    ax.set_ylim(0, max(max(dist) * 1.1, warn * 1.3))
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper right', fontsize=8)
    fig.tight_layout()
    fig.savefig(out_png, dpi=140)
    print(f'Grafik kaydedildi: {out_png}')
    print(f'En küçük mesafe: {gmin:.3f} m, emniyet: {safety:.2f} m, '
          f'ihlal: {len(vt)} tick, kritik an: {len(evs)}')


if __name__ == '__main__':
    main()
