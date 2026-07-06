#!/usr/bin/env python3
"""
RMSE Analiz Scripti — Formasyon Konum Hatası

Kullanım:
    python3 rmse_analiz.py <bag_dizini> [--drones 1 2 3] [--out rmse.png]

Örnek:
    python3 rmse_analiz.py ~/test_formasyon \
        --drones 1 2 3 \
        --out rmse_grafik.png

Okunan topic'ler:
    Hedef   : /drone_{id}/control/setpoint/raw  (AgentSetpoint)
    Gerçek  : /swarm/internal/drone{id}/status  (AgentStatus)

Üretilen grafik:
    - Her drone için ayrı RMSE eğrisi (zamana karşı)
    - Sürü ortalaması (kalın çizgi)
    - Formasyon fazlarını ayıran dikey çizgiler (isteğe bağlı)
"""

import argparse
import math
import sys
from pathlib import Path

import numpy as np

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
except ImportError:
    print("HATA: matplotlib yüklü değil. pip install matplotlib")
    sys.exit(1)

try:
    from rosbags.rosbag2 import Reader
    from rosbags.typesys import Stores, get_typestore, get_types_from_msg
except ImportError:
    print("HATA: rosbags yüklü değil. pip install rosbags")
    sys.exit(1)


def _bag_oku(bag_yolu: str, drone_ids: list[int]):
    """Bag dosyasından setpoint ve gerçek konum verilerini çeker.

    MCAP formatındaki bag'den tip tanımlarını doğrudan okur (custom msg desteği).

    Returns:
        setpoints : {drone_id: [(t_ns, x, y, z), ...]}
        actuals   : {drone_id: [(t_ns, x, y, z), ...]}
    """
    setpoints = {d: [] for d in drone_ids}
    actuals   = {d: [] for d in drone_ids}

    with Reader(bag_yolu) as reader:
        # Bag içindeki msgdef'lerden typestore oluştur (custom msg desteği)
        store = get_typestore(Stores.ROS2_JAZZY)
        for conn in reader.connections:
            try:
                store.register(get_types_from_msg(conn.msgdef.data, conn.msgtype))
            except Exception:
                pass

        for conn, t_ns, rawdata in reader.messages():
            topic = conn.topic

            # --- Hedef setpoint ---
            for did in drone_ids:
                sp_topic = f'/drone_{did}/control/setpoint/raw'
                if topic == sp_topic:
                    msg = store.deserialize_cdr(rawdata, conn.msgtype)
                    setpoints[did].append((t_ns, float(msg.x),
                                           float(msg.y), float(msg.z)))

            # --- Gerçek konum ---
            for did in drone_ids:
                st_topic = f'/swarm/internal/drone{did}/status'
                if topic == st_topic:
                    msg = store.deserialize_cdr(rawdata, conn.msgtype)
                    actuals[did].append((t_ns, float(msg.pos_x),
                                         float(msg.pos_y), float(msg.pos_z)))

    return setpoints, actuals


def _rmse_hesapla(setpoints, actuals, drone_ids):
    """Her drone için zamana göre RMSE hesaplar.

    Setpoint ve actual zaman damgaları hizalanır:
    Her actual örneği için en yakın setpoint bulunur (nearest-neighbor).

    Returns:
        {drone_id: (t_sn_array, rmse_array)}
    """
    sonuclar = {}
    for did in drone_ids:
        sp = sorted(setpoints[did])
        ac = sorted(actuals[did])
        if not sp or not ac:
            print(f"  [UYARI] Drone {did} için yeterli veri yok, atlandı.")
            continue

        sp_arr = np.array(sp)   # (N, 4): t, x, y, z
        ac_arr = np.array(ac)   # (M, 4): t, x, y, z

        t0 = min(sp_arr[0, 0], ac_arr[0, 0])
        sp_arr[:, 0] -= t0
        ac_arr[:, 0] -= t0

        rmse_list = []
        t_list    = []

        for t_ns, ax, ay, az in ac_arr:
            # Nearest neighbor setpoint
            idx = np.searchsorted(sp_arr[:, 0], t_ns)
            idx = np.clip(idx, 0, len(sp_arr) - 1)
            _, sx, sy, sz = sp_arr[idx]
            err = math.sqrt((ax - sx)**2 + (ay - sy)**2 + (az - sz)**2)
            t_list.append(t_ns / 1e9)
            rmse_list.append(err)

        sonuclar[did] = (np.array(t_list), np.array(rmse_list))
    return sonuclar


def _gecici_rejim_analiz(t_ort, rm_ort, faz_anlari, esik=0.5):
    """Faz geçiş anlarından sonraki spike'lar için yerleşme süresi hesaplar.

    Returns:
        [(t_peak, peak_val, t_settle, Ts), ...]
    """
    sonuclar = []
    if not faz_anlari:
        return sonuclar
    t_max = t_ort[-1]
    for t_gecis in faz_anlari:
        # Geçiş anından 30s sonrasına bak
        pencere_son = min(t_gecis + 30.0, t_max)
        mask = (t_ort >= t_gecis) & (t_ort <= pencere_son)
        t_seg = t_ort[mask]
        rm_seg = rm_ort[mask]
        if len(t_seg) < 5:
            continue
        peak_idx = int(np.argmax(rm_seg))
        t_peak = t_seg[peak_idx]
        peak_val = rm_seg[peak_idx]
        if peak_val < esik:
            continue
        after = rm_seg[peak_idx:]
        t_after = t_seg[peak_idx:]
        settled = np.where(after < esik)[0]
        if len(settled) == 0:
            continue
        t_settle = t_after[settled[0]]
        sonuclar.append((t_peak, peak_val, t_settle, t_settle - t_peak))
    return sonuclar


def _grafik_ciz(sonuclar, drone_ids, cikti_dosyasi: str,
                faz_anlari: list[float] | None = None,
                faz_etiketleri: list[str] | None = None,
                kalkis_suresi: float | None = None):
    """RMSE - Zaman grafiğini çizer ve kaydeder."""
    renkler = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    fig, ax = plt.subplots(figsize=(16, 6))
    fig.patch.set_facecolor('white')

    tum_t  = []
    tum_rm = []

    for i, did in enumerate(drone_ids):
        if did not in sonuclar:
            continue
        t, rm = sonuclar[did]
        rm_smooth = np.convolve(rm, np.ones(25) / 25, mode='same')
        ax.plot(t, rm_smooth, color=renkler[i % len(renkler)],
                linewidth=1.6, alpha=0.85, label=f'İHA {did}')
        tum_t.append(t)
        tum_rm.append(rm)

    # Sürü ortalaması
    t_ortak = None
    rm_ort   = None
    if len(tum_t) > 1:
        t_ortak = np.linspace(
            max(v[0] for v in tum_t),
            min(v[-1] for v in tum_t),
            800,
        )
        rm_ort = np.mean(
            [np.interp(t_ortak, t, rm) for t, rm in zip(tum_t, tum_rm)],
            axis=0,
        )
        ax.plot(t_ortak, rm_ort, color='black', linewidth=2.4,
                linestyle='--', label='Sürü Ortalaması', zorder=5)

    ESIK = 0.5
    Y_MAX = 3.5
    t_end_data = tum_t[0][-1] if tum_t else 140.0

    # ── Arka plan: sadece kararlı bölgeler renkli, geçiş beyaz ──────────────
    # faz_anlari = [t_gecis1, t_gecis2] → heading komutunun verildiği anlar
    # Kararlı 0°  : 0 → faz_anlari[0]
    # Geçiş 1     : faz_anlari[0] → t_settle1  (beyaz, etiket yok)
    # Kararlı 90° : t_settle1 → faz_anlari[1]
    # Geçiş 2     : faz_anlari[1] → t_settle2  (beyaz, etiket yok)
    # Kararlı 180°: t_settle2 → t_end
    if faz_anlari and len(faz_anlari) >= 2:
        # Sürü ortalaması üzerinden yerleşme zamanlarını bul
        t_settle1 = faz_anlari[0] + 10.0  # varsayılan fallback
        t_settle2 = faz_anlari[1] + 10.0
        if t_ortak is not None:
            for t_gecis, idx_out in [(faz_anlari[0], 0), (faz_anlari[1], 1)]:
                pencere_son = min(t_gecis + 50.0, t_end_data)
                mask = (t_ortak >= t_gecis) & (t_ortak <= pencere_son)
                t_seg = t_ortak[mask]; rm_seg = rm_ort[mask]
                if len(t_seg) < 5:
                    continue
                peak_i = int(np.argmax(rm_seg))
                after = rm_seg[peak_i:]; t_after = t_seg[peak_i:]
                settled = np.where(after < ESIK)[0]
                if len(settled) > 0:
                    if idx_out == 0:
                        t_settle1 = t_after[settled[0]]
                    else:
                        t_settle2 = t_after[settled[0]]

        bolge_tanim = [
            (0.0,            faz_anlari[0], '#F0F0F0', 'Kararlı — Heading 0°'),
            (faz_anlari[0],  t_settle1,     '#FFFDF0', ''),
            (t_settle1,      faz_anlari[1], '#EBF5FB', 'Kararlı — Heading 90°'),
            (faz_anlari[1],  t_settle2,     '#FFFDF0', ''),
            (t_settle2,      t_end_data,    '#F0FFF4', 'Kararlı — Heading 180°'),
        ]
        for t_s, t_e, renk, etiket in bolge_tanim:
            ax.axvspan(t_s, t_e, alpha=1.0, color=renk, zorder=0)
            if etiket:
                ax.text((t_s + t_e) / 2, Y_MAX * 0.96, etiket,
                        fontsize=9.5, color='#555555', ha='center', va='top',
                        fontstyle='italic')

        # Heading geçiş çizgileri
        for t_faz in faz_anlari:
            ax.axvline(x=t_faz, color='#999999', linestyle='--',
                       linewidth=1.0, zorder=3)
            ax.text(t_faz + 0.5, Y_MAX * 0.88,
                    'Heading\nkomutu', fontsize=7.5, color='#888888', va='top')

    elif faz_anlari:
        # Tek faz verilmişse eski davranış
        ax.axvspan(0, faz_anlari[0], alpha=1.0, color='#F0F0F0', zorder=0)
        ax.axvspan(faz_anlari[0], t_end_data, alpha=1.0, color='#EBF5FB', zorder=0)
        ax.axvline(x=faz_anlari[0], color='#999999', linestyle='--', linewidth=1.0)

    # ── Tolerans eşiği ──────────────────────────────────────────────────────
    ax.axhline(y=ESIK, color='#E74C3C', linestyle='--', linewidth=1.4,
               alpha=0.8, label='Tolerans Eşiği (0.5 m)', zorder=4)

    # ── Geçici rejim analizi + annotasyon ───────────────────────────────────
    if t_ortak is not None and rm_ort is not None and faz_anlari:
        rejim = _gecici_rejim_analiz(t_ortak, rm_ort, faz_anlari, ESIK)
        print("\n--- Geçici Rejim Analizi (Sürü Ortalaması) ---")
        for idx, (t_peak, peak_val, t_settle, Ts) in enumerate(rejim):
            print(f"  Geçiş {idx+1}: tepe={peak_val:.2f}m @ t={t_peak:.1f}s  "
                  f"→ yerleşme t={t_settle:.1f}s  Ts={Ts:.1f}s")

        # Her geçiş için Ts annotasyonu — sağa metin, oka gerek yok
        for idx, (t_peak, peak_val, t_settle, Ts) in enumerate(rejim):
            ax.annotate(
                f'$T_s$ = {Ts:.1f} s\n(sürü ort.)',
                xy=(t_settle, ESIK),
                xytext=(t_settle + 1.5, ESIK + 0.55),
                fontsize=9, color='#444444',
                arrowprops=dict(arrowstyle='->', color='#888888', lw=1.1),
                bbox=dict(boxstyle='round,pad=0.25', facecolor='white',
                          edgecolor='#cccccc', alpha=0.95),
                zorder=10,
            )

        if rejim:
            ts_ort = np.mean([r[3] for r in rejim])
            print(f"  Ortalama Ts = {ts_ort:.1f} s")

    # ── Bireysel tepe değerleri ──────────────────────────────────────────────
    if faz_anlari and len(faz_anlari) >= 2:
        for fi, t_gecis in enumerate(faz_anlari[:2]):
            for i, (t_arr, rm_arr) in enumerate(zip(tum_t, tum_rm)):
                mask = (t_arr >= t_gecis) & (t_arr <= t_gecis + 20.0)
                if mask.sum() < 3:
                    continue
                peak_val = float(rm_arr[mask].max())
                if peak_val < ESIK:
                    continue
                t_peak_i = float(t_arr[mask][np.argmax(rm_arr[mask])])
                ax.annotate(
                    f'{peak_val:.2f} m',
                    xy=(t_peak_i, min(peak_val, Y_MAX - 0.05)),
                    xytext=(t_peak_i + 1.0, min(peak_val, Y_MAX - 0.05)),
                    fontsize=7.5, color=renkler[i % len(renkler)],
                    arrowprops=dict(arrowstyle='->', color=renkler[i % len(renkler)],
                                    lw=0.8),
                    zorder=10,
                )

    # ── Kararlı hal RMSE — son %25 (tüm dronlar yerleştikten sonra) ─────────
    if tum_t:
        t_end = tum_t[0][-1]
        t_stable_start = t_end * 0.78
        stable_vals = []
        for t_arr, rm_arr in zip(tum_t, tum_rm):
            mask = t_arr >= t_stable_start
            if mask.sum() > 5:
                stable_vals.append(float(np.mean(rm_arr[mask])))
        if stable_vals:
            stable_mean = float(np.mean(stable_vals))
            ax.annotate(
                f'Kararlı RMSE = {stable_mean:.3f} m',
                xy=(t_end * 0.90, stable_mean),
                xytext=(t_stable_start + 1, stable_mean + 0.45),
                fontsize=9.5, color='#1A7A3A',
                arrowprops=dict(arrowstyle='->', color='#1A7A3A', lw=1.3),
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                          edgecolor='#2ECC71', linewidth=1.3, alpha=0.97),
                zorder=10,
            )
            print(f"\nKararlı hal RMSE: {stable_mean:.3f} m")

    # ── Eksen / grid / başlık ───────────────────────────────────────────────
    ax.set_xlabel('Zaman (s)', fontsize=12)
    ax.set_ylabel('Konum Hatası RMSE (m)', fontsize=12)
    ax.set_title(
        'Formasyon Konum Hatası — RMSE / Zaman\n'
        'V Formasyonu  ·  Heading Geçiş Analizi (0°→90°→180°)  ·  n = 3 İHA',
        fontsize=12, fontweight='bold',
    )
    ax.legend(fontsize=10, loc='upper left',
              framealpha=0.97, edgecolor='#cccccc')
    ax.grid(True, alpha=0.3, linestyle='-', color='#dddddd', zorder=1)
    ax.set_ylim(0, Y_MAX)
    ax.set_xlim(0, t_end_data)
    ax.yaxis.set_major_locator(plt.MultipleLocator(0.5))
    ax.tick_params(axis='both', labelsize=10)
    ax.set_facecolor('white')
    fig.tight_layout(pad=1.8)
    fig.savefig(cikti_dosyasi, dpi=120, bbox_inches='tight')
    print(f"\nGrafik kaydedildi: {cikti_dosyasi}")

    # Özet istatistikler
    print("\n--- RMSE Özet ---")
    for did in drone_ids:
        if did not in sonuclar:
            continue
        _, rm = sonuclar[did]
        print(f"  İHA {did}: ort={rm.mean():.3f}m  maks={rm.max():.3f}m  "
              f"kararlı(son%20)={rm[int(len(rm)*0.8):].mean():.3f}m")


def main():
    ap = argparse.ArgumentParser(description='Formasyon RMSE analizi')
    ap.add_argument('bag', help='ROS 2 bag dizin yolu')
    ap.add_argument('--drones', nargs='+', type=int, default=[1, 2, 3],
                    help='Drone ID listesi (varsayılan: 1 2 3)')
    ap.add_argument('--out', default='rmse_formasyon.png',
                    help='Çıktı grafik dosyası')
    ap.add_argument('--fazlar', nargs='+', type=float, default=None,
                    help='Faz geçiş zamanları (saniye), örn: --fazlar 5 15 30')
    ap.add_argument('--faz-etiketleri', nargs='+', default=None,
                    help='Faz isimleri, örn: --faz-etiketleri Kalkış "V Formasyon" Dönüş')
    ap.add_argument('--kalkis', type=float, default=None,
                    help='Kalkış fazı bitiş zamanı (saniye) — gri bölge olarak işaretlenir')
    ap.add_argument('--tmax', type=float, default=None,
                    help='Grafik için maksimum zaman (saniye) — uzun bag\'leri kırpır')
    ap.add_argument('--tmin', type=float, default=None,
                    help='Grafik başlangıç zamanı (saniye) — başlangıç geçici rejimini atlar')
    args = ap.parse_args()

    bag_yolu = Path(args.bag)
    if not bag_yolu.exists():
        print(f"HATA: Bag dizini bulunamadı: {bag_yolu}")
        sys.exit(1)

    print(f"Bag okunuyor: {bag_yolu}")
    print(f"Drone'lar: {args.drones}")
    setpoints, actuals = _bag_oku(str(bag_yolu), args.drones)

    print("RMSE hesaplanıyor...")
    sonuclar = _rmse_hesapla(setpoints, actuals, args.drones)

    # --tmin / --tmax ile zaman kırpma; tmin varsa zamanı sıfırla
    t_offset = 0.0
    if args.tmin is not None:
        t_offset = args.tmin
    for did in list(sonuclar.keys()):
        t, rm = sonuclar[did]
        mask = np.ones(len(t), dtype=bool)
        if args.tmin is not None:
            mask &= (t >= args.tmin)
        if args.tmax is not None:
            mask &= (t <= args.tmax)
        sonuclar[did] = (t[mask] - t_offset, rm[mask])
    # Faz zamanlarını da kaydır
    if args.fazlar and t_offset > 0:
        args.fazlar = [f - t_offset for f in args.fazlar]

    print("Grafik çiziliyor...")
    _grafik_ciz(sonuclar, args.drones, args.out,
                faz_anlari=args.fazlar,
                faz_etiketleri=args.faz_etiketleri,
                kalkis_suresi=args.kalkis)


if __name__ == '__main__':
    main()
