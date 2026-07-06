"""ca_sim.py — Hız-tabanlı çarpışma önleme offline kinematik simülatörü.

PX4/Gazebo/ROS OLMADAN, saf Python'da sürüyü taklit eder: drone'lar
nokta-kütle, her adımda formasyon hızı (SVT) + GERÇEK ca_core kaçış hızı
hesaplanır, kinematik olarak entegre edilir. Saniyeler içinde tüm şartname
senaryolarını tarar; min merkez-merkez mesafe (−20×N cezası) ve osilasyon
(−10 cezası) metriklerini üretir.

MODELLER:   ca_core mantığı, SVT+CA etkileşimi, çok-drone geometrisi.
MODELLEMEZ: quadrotor dinamiği, EKF/GPS gürültüsü, ESP-NOW gecikmesi,
            PX4 iç döngüsü. → Offline = hızlı ön-eleme; SITL = gerçek kanıt.
            Offline'da PATLAYAN kesinlikle SITL'de de patlar.

KULLANIM:
    python3 ca_sim.py                 # tüm senaryolar, özet tablo
    python3 ca_sim.py head_on         # tek senaryo (ayrıntılı)
    python3 ca_sim.py --cat ikili     # kategori
    python3 ca_sim.py --plot          # yörünge grafiği kaydet (matplotlib varsa)
"""

from __future__ import annotations

import argparse
import math
import os
import sys

# Aynı klasördeki scenarios.py (tek kaynak senaryo kataloğu) için path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scenarios  # noqa: E402

from swarm_core.collision_avoidance.ca_core import (  # noqa: E402
    CaParams,
    CollisionAvoidanceCore,
    NeighborObs,
)


# --- Simülasyon sabitleri (formation_node ile aynı SVT ayarları) ---
DT = 0.05            # 20 Hz (node ile aynı)
T_END = 30.0         # senaryo süresi (s)
SVT_K = 0.8          # SVT yatay kazanç (formation_node)
SVT_THR = 0.1        # SVT yatay deadband (m)
SVT_KZ = 2.0         # SVT dikey kazanç
SVT_THRZ = 0.05      # SVT dikey deadband (m)
SVT_DAMP = 0.35      # SVT hız sönümü
TARGET_RAMP = 1.0    # slot ramp hızı (m/s)


def _clamp(vx, vy, vz, vmax):
    s = math.sqrt(vx * vx + vy * vy + vz * vz)
    if s > vmax and s > 1e-9:
        k = vmax / s
        return vx * k, vy * k, vz * k
    return vx, vy, vz


def _svt(pos, slot, vel, vmax):
    """Formasyon hızı (SVT + sönüm) — formation_node._compute_velocity sadık.

    Bu, ca_core'a giren v_form: pozisyon kontrolünü yapan TEK terim (hız modu).
    rel/vff senaryo katalogunda yok → SVT+damp ana etkileşimi temsil eder.
    """
    ex, ey, ez = pos[0] - slot[0], pos[1] - slot[1], pos[2] - slot[2]
    vx = vy = vz = 0.0
    if math.hypot(ex, ey) > SVT_THR:
        vx -= SVT_K * ex
        vy -= SVT_K * ey
    if abs(ez) > SVT_THRZ:
        vz -= SVT_KZ * ez
    vx -= SVT_DAMP * vel[0]
    vy -= SVT_DAMP * vel[1]
    vz -= SVT_DAMP * vel[2]
    return _clamp(vx, vy, vz, vmax)


def _ramp(cur, target, max_step):
    diff = target - cur
    return cur + max(-max_step, min(max_step, diff))


def _dist3(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
                     + (a[2] - b[2]) ** 2)


def run_scenario(s, dt=DT, t_end=T_END):
    """Bir senaryoyu kinematik koşar; metrik sözlüğü + yörünge döndürür."""
    n = len(s.drones)
    pos = [list(d.start) for d in s.drones]
    vel = [[0.0, 0.0, 0.0] for _ in s.drones]
    slot = [list(d.start) for d in s.drones]      # ramp'lenen anlık slot
    goal = [list(d.goal) for d in s.drones]
    excluded = [d.excluded for d in s.drones]
    vmax = s.max_speed_mps
    ca_vmax = max(4.0, vmax + 2.0)                # CA'ya kaçış başlığı (>cruise)

    # Çok-fazlı görev: tam süre + zamanı gelince uygulanacak fazlar.
    if getattr(s, 'duration_s', None):
        t_end = s.duration_s
    phases = sorted(getattr(s, 'phases', ()), key=lambda p: p.t_start)
    phase_idx = 0

    cores = [CollisionAvoidanceCore(CaParams(dt=dt, v_max=ca_vmax))
             for _ in s.drones]

    traj = [[] for _ in s.drones]
    series = []                 # (t, tüm-çiftler min mesafe) — jüri grafiği
    min_active = float('inf')   # non-excluded çiftler arası min 3D mesafe
    reversals = [0] * n         # osilasyon: keskin hız yön tersine dönmesi
    prev_v = [None] * n

    steps = int(t_end / dt)
    settle_start = int(steps * 0.5)   # osilasyonu ikinci yarıda say (geçici hariç)

    for k in range(steps):
        t = k * dt
        # 0) çok-fazlı görev: zamanı gelen fazı uygula (slot yeni hedefe ramp)
        while phase_idx < len(phases) and t >= phases[phase_idx].t_start:
            ph = phases[phase_idx]
            for i in range(n):
                goal[i] = list(ph.goals[i])
            if ph.excluded is not None:
                for i in range(n):
                    excluded[i] = ph.excluded[i]
            phase_idx += 1
        # 1) slot ramp (start → goal)
        for i in range(n):
            for c in range(3):
                slot[i][c] = _ramp(slot[i][c], goal[i][c], TARGET_RAMP * dt)

        v_cmds = []
        for i in range(n):
            v_form = _svt(pos[i], slot[i], vel[i], vmax)
            # 2) komşular: excluded olanlar DİĞERLERİNİN hesabından çıkar
            obs = []
            for j in range(n):
                if j == i or excluded[j]:
                    continue
                rel = (pos[j][0] - pos[i][0], pos[j][1] - pos[i][1],
                       pos[j][2] - pos[i][2])
                rv = (vel[j][0] - vel[i][0], vel[j][1] - vel[i][1],
                      vel[j][2] - vel[i][2])
                obs.append(NeighborObs(
                    rel[0], rel[1], rel[2], rv[0], rv[1], rv[2],
                    math.sqrt(rel[0] ** 2 + rel[1] ** 2 + rel[2] ** 2)))
            v_cmd, _ = cores[i].compute(v_form, obs)
            v_cmds.append(list(v_cmd))

        # 3) dış pertürbasyon (rüzgar/itme)
        for p in s.perturbations:
            if p.t_start <= t < p.t_end:
                idx = p.agent_id - 1
                v_cmds[idx][0] += p.vel[0]
                v_cmds[idx][1] += p.vel[1]
                v_cmds[idx][2] += p.vel[2]

        # 4) entegre + metrik
        for i in range(n):
            vel[i] = v_cmds[i]
            for c in range(3):
                pos[i][c] += vel[i][c] * dt
            traj[i].append((pos[i][0], pos[i][1], pos[i][2]))
            # osilasyon: settling sonrası keskin yön tersine dönme
            if k >= settle_start and prev_v[i] is not None:
                a, b = prev_v[i], vel[i]
                na = math.hypot(a[0], a[1])
                nb = math.hypot(b[0], b[1])
                if na > 0.1 and nb > 0.1:
                    cos = (a[0] * b[0] + a[1] * b[1]) / (na * nb)
                    if cos < -0.3:    # >107° dönüş = salınım işareti
                        reversals[i] += 1
            prev_v[i] = list(vel[i])

        # min mesafe: non-excluded (pass/fail) + tüm-çiftler zaman serisi (grafik)
        cur_min_all = float('inf')
        for i in range(n):
            for j in range(i + 1, n):
                d = _dist3(pos[i], pos[j])
                if d < cur_min_all:
                    cur_min_all = d
                if excluded[i] or excluded[j]:
                    continue
                if d < min_active:
                    min_active = d
        series.append((t, cur_min_all))

    # yakınsama: son formasyon hatası (slota uzaklık ortalaması)
    form_err = sum(_dist3(pos[i], slot[i]) for i in range(n)) / n
    osc_total = sum(reversals)
    return {
        'min_dist': min_active,
        'safety': s.safety_radius_m,
        'osc': osc_total,
        'form_err': form_err,
        'ca_solvable': s.ca_solvable,
        'expect_avoid': s.expect_avoid,
        'traj': traj,
        'series': series,
    }


def _verdict(r):
    """min mesafe emniyet üstünde + osilasyon yok → GEÇTİ."""
    if not r['ca_solvable']:
        return 'N/A*'   # CA tek başına çözmez (görev katmanı gerekir)
    safe = r['min_dist'] >= r['safety'] - 1e-3
    calm = r['osc'] <= 2   # birkaç dönüş tolere; sürekli salınım değil
    if safe and calm:
        return '✓ GEÇTİ'
    if not safe:
        return '✗ ÇARPIŞMA'
    return '✗ OSİLASYON'


def _plot(name, r):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('  (matplotlib yok — grafik atlandı)')
        return
    fig, ax = plt.subplots(figsize=(6, 6))
    for i, tr in enumerate(r['traj']):
        xs = [p[1] for p in tr]   # Doğu (Y) → yatay eksen
        ys = [p[0] for p in tr]   # Kuzey (X) → dikey eksen
        ax.plot(xs, ys, label=f'drone{i + 1}')
        ax.plot(xs[0], ys[0], 'o')   # başlangıç
        ax.plot(xs[-1], ys[-1], 's')  # bitiş
    ax.set_aspect('equal')
    ax.set_xlabel('Doğu (m)')
    ax.set_ylabel('Kuzey (m)')
    ax.set_title(f'{name}  min={r["min_dist"]:.2f}m  osc={r["osc"]}')
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)
    out = f'/tmp/ca_sim_{name}.png'
    fig.savefig(out, dpi=110, bbox_inches='tight')
    plt.close(fig)
    print(f'  grafik: {out}')


def main():
    ap = argparse.ArgumentParser(description='CA offline kinematik sim')
    ap.add_argument('name', nargs='?', help='tek senaryo adı')
    ap.add_argument('--cat', help='kategori')
    ap.add_argument('--plot', action='store_true', help='yörünge grafiği')
    args = ap.parse_args()

    if args.name:
        sel = [scenarios.get(args.name)]
    elif args.cat:
        sel = scenarios.by_category(args.cat)
    else:
        sel = list(scenarios.SCENARIOS)

    print(f'{"SENARYO":28s} {"kategori":11s} {"min":>7s} {"emniyet":>8s} '
          f'{"osc":>4s} {"form_err":>9s}  SONUÇ')
    print('-' * 86)
    n_pass = n_eval = 0
    for s in sel:
        r = run_scenario(s)
        v = _verdict(r)
        if r['ca_solvable']:
            n_eval += 1
            if v == '✓ GEÇTİ':
                n_pass += 1
        print(f'{s.name:28s} {s.category:11s} {r["min_dist"]:6.2f}m '
              f'{r["safety"]:6.2f}m {r["osc"]:4d} {r["form_err"]:7.2f}m  {v}')
        if args.plot:
            _plot(s.name, r)

    print('-' * 86)
    print(f'CA-çözülebilir senaryolar: {n_pass}/{n_eval} GEÇTİ   '
          f'(N/A* = CA tek başına çözmez, görev katmanı gerekir)')
    return 0 if n_pass == n_eval else 1


if __name__ == '__main__':
    sys.exit(main())
