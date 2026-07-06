#!/usr/bin/env python3
"""
rmse_paper.py — Yayın kalitesinde Formasyon Konum Hatası (RMSE) figürü.

Bölüm 5.2: "Formasyon Kontrolü ve Yörünge Takip Hassasiyeti Analizi".
Hedef konum = formasyon MATEMATİĞİNİN ürettiği ideal slot
(center + rotate_offset(offset, heading)); gerçek konum = AgentStatus pos.
Böylece grafik, formasyon matematiğinin pratik doğruluğunu doğrudan kanıtlar
(setpoint takip hatası DEĞİL — ideal geometriye olan toplam sapma).

Sade/temiz stil (dergi figürü): gri faz bandları, tek tepe + Ts etiketi,
colorblind-güvenli palet, vektör (PDF) çıktı.

Kullanım:
    python3 rmse_paper.py <bag_dizini> --drones 1 2 3 \
        --fazlar 30 55 80 --kalkis 22 --out rmse_52.pdf

Okunan topic'ler:
    Hedef geo : /swarm/public/formation/target   (FormationCommand)
    Gerçek    : /swarm/internal/drone{id}/status  (AgentStatus)

NOT: ideal slot ile gerçek pos'un AYNI çerçevede olması için tüm dronlar
ortak NED origin kullanmalı (SITL'de swarm_origin fixed). use_proxy=false.
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
except ImportError:
    print('HATA: matplotlib yüklü değil. pip install matplotlib')
    sys.exit(1)

import subprocess

try:
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
except ImportError:
    print('HATA: rosbag2_py yok — ROS2 ortamını source et.')
    sys.exit(1)


# Okabe-Ito colorblind-güvenli palet (dronlar için)
_PALETTE = ['#0072B2', '#E69F00', '#009E73', '#CC79A7', '#56B4E9']
_TOL_M = 0.5          # tolerans eşiği (m)
_Y_MAX_PAD = 1.10     # y ekseni tepe payı
_M_PER_DEG_LAT = 111320.0   # latlon_to_ned ile aynı sabit

# Ortak NED origin (swarm_origin_publisher fixed_lat/lon) — drone'un GERÇEK
# shared konumu GPS'ten buraya göre hesaplanır. KRİTİK: her drone'un PX4 local
# NED origin'i kendi spawn noktası olduğundan, local pos_x/y çerçeveler arası
# kıyasta YANILTICI. GPS→shared NED tüm dronlar için ortak çerçeve verir.
_DEFAULT_ORIGIN_LAT = 41.0441
_DEFAULT_ORIGIN_LON = 29.0017


def _rotate(dx: float, dy: float, heading_rad: float) -> tuple[float, float]:
    """Body offsetini heading kadar döndürür (NED) — formation_geometry ile aynı."""
    c = math.cos(heading_rad)
    s = math.sin(heading_rad)
    return dx * c - dy * s, dx * s + dy * c


def _latlon_to_ned(lat, lon, ref_lat, ref_lon) -> tuple[float, float]:
    """GPS → ortak NED (formation_geometry.latlon_to_ned ile birebir aynı)."""
    north = (lat - ref_lat) * _M_PER_DEG_LAT
    east = ((lon - ref_lon) * _M_PER_DEG_LAT
            * math.cos(math.radians(ref_lat)))
    return north, east


def _bag_dir(bag_yolu: str) -> str:
    """Bag dizinini döndürür; metadata.yaml yoksa reindex eder (C++ reader)."""
    p = Path(bag_yolu)
    bag_dir = p.parent if (p.is_file() and p.suffix == '.mcap') else p
    if not (bag_dir / 'metadata.yaml').exists():
        print('[NOT] metadata yok → reindex ediliyor...')
        subprocess.run(['ros2', 'bag', 'reindex', str(bag_dir), 'mcap'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not (bag_dir / 'metadata.yaml').exists():
            subprocess.run(['ros2', 'bag', 'reindex', str(bag_dir)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(bag_dir)


def _bag_oku(bag_yolu: str, drone_ids: list[int],
             origin_lat: float, origin_lon: float):
    """Bag'den gerçek konumları (GPS→shared NED) ve FormationCommand'leri çeker.

    rosbag2_py (C++ reader) ile okur — düzgün kapanmamış bag'leri reindex
    sonrası file-order'da okuyabilir (ros2 bag info ile aynı motor).

    Gerçek konum: XY = GPS(lat/lon)→ortak NED (tüm dronlar ortak çerçevede),
    Z = pos_z (irtifa dönüştürülmez — hepsi aynı zeminden). LOCAL pos_x/y
    KULLANILMAZ (her drone'un local origin'i farklı → çerçeve karışır).

    Returns:
        actuals : {drone_id: np.ndarray (N,4) [t_ns, n, e, z]}
        cmds    : sorted list[(t_ns, cx, cy, cz, heading_deg, {aid:(ox,oy,oz)})]
    """
    bag_dir = _bag_dir(bag_yolu)
    actuals = {d: [] for d in drone_ids}        # GPS→shared NED (geometry için)
    actuals_local = {d: [] for d in drone_ids}  # PX4 local NED (tracking için)
    setpoints = {d: [] for d in drone_ids}      # /control/setpoint/raw (local)
    cmds = []
    status_topics = {f'/swarm/internal/drone{d}/status': d for d in drone_ids}
    sp_topics = {f'/drone_{d}/control/setpoint/raw': d for d in drone_ids}

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=bag_dir, storage_id='mcap'),
        rosbag2_py.ConverterOptions(
            input_serialization_format='cdr',
            output_serialization_format='cdr'),
    )
    type_map = {t.name: t.type for t in reader.get_all_topics_and_types()}
    msg_cls = {}

    while reader.has_next():
        try:
            topic, data, t_ns = reader.read_next()
        except Exception as e:
            print(f'[NOT] okuma kesildi ({type(e).__name__}); mevcut veri yeter.')
            break
        if topic not in msg_cls:
            msg_cls[topic] = get_message(type_map[topic])
        msg = deserialize_message(data, msg_cls[topic])
        if topic == '/swarm/public/formation/target':
            offs = {
                int(a): (float(msg.offset_x[i]), float(msg.offset_y[i]),
                         float(msg.offset_z[i]))
                for i, a in enumerate(msg.agent_ids)
            }
            cmds.append((t_ns, float(msg.center_x), float(msg.center_y),
                         float(msg.center_z), float(msg.heading_deg), offs))
        elif topic in status_topics:
            did = status_topics[topic]
            # XY: GPS→ortak shared NED (çerçeve birliği). Z: local pos_z.
            if msg.lat_deg != 0.0 or msg.lon_deg != 0.0:
                n, e = _latlon_to_ned(msg.lat_deg, msg.lon_deg,
                                      origin_lat, origin_lon)
            else:
                n, e = float(msg.pos_x), float(msg.pos_y)
            actuals[did].append((t_ns, n, e, float(msg.pos_z)))
            actuals_local[did].append(
                (t_ns, float(msg.pos_x), float(msg.pos_y), float(msg.pos_z)))
        elif topic in sp_topics:
            did = sp_topics[topic]
            setpoints[did].append(
                (t_ns, float(msg.x), float(msg.y), float(msg.z)))

    actuals = {d: np.array(sorted(v)) for d, v in actuals.items() if v}
    actuals_local = {d: np.array(sorted(v))
                     for d, v in actuals_local.items() if v}
    setpoints = {d: np.array(sorted(v)) for d, v in setpoints.items() if v}
    cmds.sort(key=lambda c: c[0])
    return actuals, actuals_local, cmds, setpoints


def _geometri_rmse(actuals, cmds, drone_ids):
    """Her drone için ideal slot ↔ gerçek konum hatasını (geometri) hesaplar.

    Her gerçek örnek için, o ana kadarki SON FormationCommand'in ideal slotu
    referanstır. Komut gelmeden önceki örnekler (kalkış fazı) NaN bırakılır.

    Returns:
        {drone_id: (t_sn (M,), err (M,))}, t0_ns
    """
    if not actuals:
        return {}, 0
    t0 = min(a[0, 0] for a in actuals.values())
    cmd_t = np.array([c[0] for c in cmds]) if cmds else np.empty(0)

    out = {}
    for did in drone_ids:
        if did not in actuals:
            continue
        arr = actuals[did]
        t_sn = (arr[:, 0] - t0) / 1e9
        err = np.full(len(arr), np.nan)
        for k in range(len(arr)):
            if len(cmd_t) == 0:
                continue
            j = int(np.searchsorted(cmd_t, arr[k, 0], side='right')) - 1
            if j < 0:
                continue                         # kalkış fazı: komut yok
            _, cx, cy, cz, hdg, offs = cmds[j]
            if did not in offs:
                continue
            ox, oy, oz = offs[did]
            dx, dy = _rotate(ox, oy, math.radians(hdg))
            ex = (cx + dx) - arr[k, 1]
            ey = (cy + dy) - arr[k, 2]
            ez = (cz + oz) - arr[k, 3]
            err[k] = math.sqrt(ex * ex + ey * ey + ez * ez)
        out[did] = (t_sn, err)
    return out, t0


def _tracking_rmse(actuals_local, setpoints, drone_ids):
    """Komut edilen setpoint ↔ gerçek konum hatası (YÖRÜNGE TAKİP hassasiyeti).

    Her ikisi de PX4 LOCAL NED → çerçeve tutarlı (GPS gerekmez). Her gerçek
    örnek için zaman olarak en yakın setpoint referans. Bu metrik "drone
    komut edilen yörüngeyi ne kadar sıkı takip ediyor" sorusunu yanıtlar
    (v_ff'in asıl kanıtı); reconfigure yol-süresini hata saymaz.
    """
    out = {}
    if not actuals_local or not setpoints:
        return out, 0
    t0 = min(a[0, 0] for a in actuals_local.values())
    for did in drone_ids:
        if did not in actuals_local or did not in setpoints:
            continue
        arr = actuals_local[did]
        sp = setpoints[did]
        sp_t = sp[:, 0]
        t_sn = (arr[:, 0] - t0) / 1e9
        err = np.full(len(arr), np.nan)
        for k in range(len(arr)):
            if arr[k, 0] < sp_t[0]:
                continue   # setpoint henüz yayınlanmadı (kalkış) → NaN
            j = int(np.searchsorted(sp_t, arr[k, 0]))
            j = min(max(j, 0), len(sp) - 1)
            ex = sp[j, 1] - arr[k, 1]
            ey = sp[j, 2] - arr[k, 2]
            ez = sp[j, 3] - arr[k, 3]
            err[k] = math.sqrt(ex * ex + ey * ey + ez * ez)
        out[did] = (t_sn, err)
    return out, t0


def _settle(t, rm, t_gecis, esik, pencere=30.0):
    """Geçiş anından sonra tepe + yerleşme süresini (Ts) bulur."""
    son = t_gecis + pencere
    mask = (t >= t_gecis) & (t <= son) & np.isfinite(rm)
    ts, rs = t[mask], rm[mask]
    if len(ts) < 5:
        return None
    pi = int(np.argmax(rs))
    peak_t, peak_v = ts[pi], rs[pi]
    if peak_v < esik:
        return None
    after, t_after = rs[pi:], ts[pi:]
    below = np.where(after < esik)[0]
    if len(below) == 0:
        return (peak_t, peak_v, None, None)
    t_set = t_after[below[0]]
    return (peak_t, peak_v, t_set, t_set - peak_t)


def _smooth(rm, w=15):
    """NaN-güvenli hareketli ortalama (kalkış NaN'larını yaymaz)."""
    out = np.copy(rm)
    fin = np.isfinite(rm)
    if fin.sum() < w:
        return out
    idx = np.where(fin)[0]
    sm = np.convolve(rm[idx], np.ones(w) / w, mode='same')
    out[idx] = sm
    return out


def ciz(bag, drone_ids, out_path, fazlar=None, kalkis=None,
        tmin=None, tmax=None, mode='geometry',
        origin_lat=_DEFAULT_ORIGIN_LAT, origin_lon=_DEFAULT_ORIGIN_LON):
    """Yayın figürünü üretir ve kaydeder.

    mode='geometry' → ideal slota (GPS→shared) hata: formasyon doğruluğu +
        reconfigure geçici rejimi (büyük tepeler = yol-süresi).
    mode='tracking' → komut edilen setpoint'e (local) hata: YÖRÜNGE TAKİP
        hassasiyeti (v_ff kanıtı, küçük; reconfigure'u hata saymaz).
    """
    print(f'Bag okunuyor: {bag}  | mode={mode}')
    actuals, actuals_local, cmds, setpoints = _bag_oku(
        bag, drone_ids, origin_lat, origin_lon)
    if not actuals:
        print('HATA: gerçek konum verisi yok.')
        sys.exit(1)
    print(f'FormationCommand={len(cmds)}  setpoint dronları='
          f'{sorted(setpoints)}')

    if mode == 'tracking':
        sonuc, _ = _tracking_rmse(actuals_local, setpoints, drone_ids)
    else:
        print(f'Çerçeve: GPS→shared NED, origin=({origin_lat}, {origin_lon})')
        sonuc, _ = _geometri_rmse(actuals, cmds, drone_ids)

    # tmin/tmax kırpma
    for did in list(sonuc.keys()):
        t, rm = sonuc[did]
        m = np.ones(len(t), dtype=bool)
        if tmin is not None:
            m &= t >= tmin
        if tmax is not None:
            m &= t <= tmax
        off = tmin if tmin else 0.0
        sonuc[did] = (t[m] - off, rm[m])
    if fazlar and tmin:
        fazlar = [f - tmin for f in fazlar]
    if kalkis and tmin:
        kalkis = kalkis - tmin

    # --- Figür ---
    plt.rcParams.update({'font.size': 11, 'axes.linewidth': 0.8})
    fig, ax = plt.subplots(figsize=(7.0, 3.6))   # tek sütun dergi oranı

    t_son = max(t[-1] for t, _ in sonuc.values())
    tum_t, tum_rm = [], []
    for i, did in enumerate(drone_ids):
        if did not in sonuc:
            continue
        t, rm = sonuc[did]
        ax.plot(t, _smooth(rm), color=_PALETTE[i % len(_PALETTE)],
                lw=1.1, alpha=0.85, label=f'İHA {did}')
        tum_t.append(t)
        tum_rm.append(rm)

    # Sürü ortalaması (ortak zaman gridinde, NaN-güvenli)
    rm_ort = t_ort = None
    if len(tum_t) > 1:
        t_ort = np.linspace(max(t[0] for t in tum_t),
                            min(t[-1] for t in tum_t), 600)
        cols = [np.interp(t_ort, t, _smooth(rm)) for t, rm in
                zip(tum_t, tum_rm)]
        rm_ort = np.nanmean(cols, axis=0)
        ax.plot(t_ort, rm_ort, color='black', lw=2.0,
                label='Sürü ortalaması')

    # Kalkış fazı (gri bant, RMSE tanımsız)
    if kalkis:
        ax.axvspan(0, kalkis, color='#E8E8E8', alpha=0.7, lw=0)
        ax.text(kalkis / 2, ax.get_ylim()[1] * 0.92, 'Kalkış',
                ha='center', va='top', fontsize=9, color='#666666',
                style='italic')

    # Faz geçişleri: ince dikey çizgi + Ts/tepe etiketi (geçiş başına TEK)
    if fazlar and rm_ort is not None:
        for tg in fazlar:
            ax.axvline(tg, color='#999999', ls='--', lw=0.8, alpha=0.7)
        for tg in fazlar:
            r = _settle(t_ort, rm_ort, tg, _TOL_M)
            if r is None:
                continue
            peak_t, peak_v, t_set, ts = r
            lbl = f'tepe {peak_v:.2f} m'
            if ts is not None:
                lbl += f'\n$T_s$ {ts:.1f} s'
            ax.annotate(lbl, xy=(peak_t, peak_v),
                        xytext=(peak_t + 2, peak_v),
                        fontsize=8.5, color='#333333', va='center',
                        arrowprops=dict(arrowstyle='->', color='#888888',
                                        lw=0.8))

    # Tolerans eşiği
    ax.axhline(_TOL_M, color='#D55E00', ls=':', lw=1.2,
               label=f'Tolerans ({_TOL_M:.1f} m)')

    # Kararlı hal RMSE (son %25, finite)
    if tum_t:
        ths = t_son * 0.75
        vals = []
        for t, rm in zip(tum_t, tum_rm):
            mm = (t >= ths) & np.isfinite(rm)
            if mm.sum() > 5:
                vals.append(float(np.mean(rm[mm])))
        if vals:
            ss = float(np.mean(vals))
            ax.text(0.985, 0.08, f'Kararlı hal RMSE = {ss:.3f} m',
                    transform=ax.transAxes, ha='right', va='bottom',
                    fontsize=9, color='#1A7A3A',
                    bbox=dict(boxstyle='round,pad=0.3', fc='white',
                              ec='#1A7A3A', lw=0.8))
            print(f'Kararlı hal RMSE: {ss:.3f} m')

    ax.set_xlabel('Zaman (s)')
    ax.set_ylabel('Konum hatası RMSE (m)')
    ax.set_xlim(0, t_son)
    ax.set_ylim(0, None)
    ax.grid(True, alpha=0.25, lw=0.6)
    ax.legend(loc='upper right', fontsize=8.5, framealpha=0.95,
              ncol=2, handlelength=1.6)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    fig.tight_layout(pad=0.6)
    fig.savefig(out_path, bbox_inches='tight')
    print(f'Figür kaydedildi: {out_path}')

    # Konsol özeti
    print('\n--- Geçici rejim (sürü ortalaması) ---')
    if fazlar and rm_ort is not None:
        for k, tg in enumerate(fazlar):
            r = _settle(t_ort, rm_ort, tg, _TOL_M)
            if r:
                pt, pv, ts_, ts = r
                tss = f'{ts:.1f}s' if ts else 'yerleşmedi'
                print(f'  Geçiş {k+1}: tepe={pv:.2f}m  Ts={tss}')


def main():
    ap = argparse.ArgumentParser(
        description='Yayın kalitesinde formasyon RMSE figürü (geometri hatası)'
    )
    ap.add_argument('bag', help='ROS 2 bag dizini')
    ap.add_argument('--drones', nargs='+', type=int, default=[1, 2, 3])
    ap.add_argument('--out', default='rmse_52.pdf',
                    help='Çıktı (PDF/SVG önerilir; .png de olur)')
    ap.add_argument('--fazlar', nargs='+', type=float, default=None,
                    help='Heading komut anları (s), örn: --fazlar 30 55 80')
    ap.add_argument('--kalkis', type=float, default=None,
                    help='Kalkış fazı bitişi (s) — gri bant')
    ap.add_argument('--tmin', type=float, default=None)
    ap.add_argument('--tmax', type=float, default=None)
    ap.add_argument('--mode', choices=['geometry', 'tracking'],
                    default='geometry',
                    help='geometry=ideal slota; tracking=komut setpoint\'e')
    ap.add_argument('--origin-lat', type=float, default=_DEFAULT_ORIGIN_LAT,
                    help='Ortak NED origin enlemi (swarm_origin fixed_lat)')
    ap.add_argument('--origin-lon', type=float, default=_DEFAULT_ORIGIN_LON,
                    help='Ortak NED origin boylamı (swarm_origin fixed_lon)')
    args = ap.parse_args()

    if not Path(args.bag).exists():
        print(f'HATA: bag bulunamadı: {args.bag}')
        sys.exit(1)

    ciz(args.bag, args.drones, args.out, fazlar=args.fazlar,
        kalkis=args.kalkis, tmin=args.tmin, tmax=args.tmax, mode=args.mode,
        origin_lat=args.origin_lat, origin_lon=args.origin_lon)


if __name__ == '__main__':
    main()
