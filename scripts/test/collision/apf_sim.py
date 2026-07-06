"""apf_sim.py — Senaryoları NODE-SADIK pipeline ile koşturan simülatör.

ROS / Gazebo / PX4 GEREKMEZ. Sahadaki İKİ node'un matematiğini tek bir
kinematik döngüde üst üste koyar:

    formation_node:  SVT(slota çek) + göreli(komşuya göre sıkılaştır) → base_v
    collision_avoidance_node:  additive_avoidance(base_v) + slew
                               + slot_dev_clamp + alt_clamp → carrot
    fizik:  efektif_v = (carrot − pos)/lookahead ; pos += efektif_v·dt
            (+ pertürbasyon: dış itme/rüzgar, kontrolün üstüne biner)

Böylece sim = saha: aynı apf_core fonksiyonları, aynı formation_geometry
slotları, node ile aynı parametreler. İKİ MODDA koşar:
    additive-only (enable_tangent=False)  vs  hibrit (True)
→ teğet kaçışın kafa-kafaya'daki değeri ölçülür (rapor A2).

ÖLÇÜLEN METRİKLER (her tick):
    min_pairwise   en yakın ikili mesafe   → < emniyet(1.5) ihlal (çarpışma)
    max_slot_dev   slottan max sapma        → slot_dev clamp kanıtı
    alt_min/max    irtifa bandı             → 5–30 m dışı ihlal
    formation_rms  RMS(|pos−slot|)          → formasyon kalitesi
    recovery_time  pert sonrası rms<eşik    → toparlanma hızı

KULLANIM (swarm_core build + source edilmiş olmalı):
    source ~/ros2_ws/install/setup.bash
    python3 ~/ros2_ws/scripts/test/collision/apf_sim.py
"""

from __future__ import annotations

import math
import os

from swarm_core.collision_avoidance.apf_core import (
    ApfParams,
    NeighborObs,
    additive_avoidance,
    clamp_altitude_ned,
    clamp_slot_deviation,
    slew_limit,
)
import scenarios as scn


# Kontrol+integrasyon adımı. Gerçek node 20 Hz; en yakın geçişi doğru
# yakalamak için 50 Hz (0.02 s) integre ediyoruz (daha hassas min mesafe).
_DT = 0.02
_T_MAX = 30.0          # senaryo zaman aşımı (s)
_GOAL_TOL = 0.3        # hedefe varmış sayma yarıçapı (m)

# --- Çıkış sınırları (collision_avoidance_node ile aynı) ---
_ALT_MIN = 5.0
_ALT_MAX = 30.0
_CARROT_LH = 1.0       # carrot_lookahead_s

# --- Slew ivme sınırı (node ile aynı, mesafeye bağlı) ---
_MAX_ACCEL = 30.0          # acil (yakın)
_MAX_ACCEL_NORMAL = 8.0    # normal (uzak)
_EMERGENCY_RADIUS = 2.2

# --- formation_node SVT + göreli (A7) parametreleri (node defaultları) ---
_SVT_K = 0.3
_SVT_THRESH = 0.5
_SVT_K_Z = 2.0
_SVT_THRESH_Z = 0.05
_REL_K = 0.2
_REL_THRESH = 0.2
_TARGET_RAMP = 1.0     # slot ramp hızı (m/s)


def make_params(max_speed: float) -> ApfParams:
    """Saha APF parametreleri — collision_avoidance_node ile AYNI değerler.

    Hiyerarşi (emniyet-mesafesi-tasarimi): emniyet eşiği 1.5 m, hard=2.0
    (emniyetten önce max itki), influence=3.5 (5 m spacing'de normalde kapalı).
    """
    return ApfParams(
        influence_radius_m=3.5,
        influence_radius_max=6.0,
        approach_radius_gain=0.8,
        hard_radius_m=2.0,
        k_rep=4.0,
        k_att=0.8,
        max_speed_mps=max_speed,
        z_weight=0.6,
        z_up_factor=0.5,
        approach_gain=0.0,
        damping_gain=0.5,
        rep_saturation=6.0,
        deadlock_cos_thresh=-0.8,
        tangent_gain=0.9,
        activate_speed_mps=0.05,
        t_horizon=1.0,
        svt_attenuation=0.6,   # node ile eşitlendi
                               # (senaryo-3 limit cycle çözümü)
        approach_cancel=0.0,   # node ile eşit: SITL'de regresyon yaptı (carrot/clamp)
        safety_radius_m=1.5,   # hard garantisi: r_min altında kapanma sıfırlanır
        rmax_smooth_frac=0.15,  # node ile eşitlendi: d0 sınırı smoothstep zarfı
    )


def _dist(a: list[float], b: list[float]) -> float:
    """İki NED noktası arası Öklid mesafesi."""
    return math.sqrt(
        (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
    )


def _clamp_speed(vx, vy, vz, max_speed):
    """Hız vektörünü max_speed büyüklüğüne kırpar (formation_node ile aynı)."""
    speed = math.sqrt(vx * vx + vy * vy + vz * vz)
    if speed > max_speed and speed > 0.0:
        s = max_speed / speed
        return vx * s, vy * s, vz * s
    return vx, vy, vz


def _formation_base_velocity(
    i: int, pos: list, slot: list, goal: list,
    excluded: list, max_speed: float,
) -> tuple[float, float, float]:
    """formation_node base_v: SVT(slota çek) + göreli(komşuya göre) düzeltme.

    SVT (mutlak): kendi konumunu ramp'lenmiş slota çeker (dünyaya çapa).
    Göreli (A7): komşuların gerçek göreli konumu (ground-truth) ile slot
    geometrisinden istenen göreli konum arasındaki hatayı kapatır. Excluded
    komşu (inen/ayrılan) göreli hesaba katılmaz.
    """
    # --- SVT (mutlak) ---
    ex = pos[i][0] - slot[i][0]
    ey = pos[i][1] - slot[i][1]
    ez = pos[i][2] - slot[i][2]
    vx = vy = vz = 0.0
    if math.sqrt(ex * ex + ey * ey) > _SVT_THRESH:
        vx -= _SVT_K * ex
        vy -= _SVT_K * ey
    if abs(ez) > _SVT_THRESH_Z:
        vz -= _SVT_K_Z * ez

    # --- Göreli (A7): istenen=goal[j]-goal[i], gerçek=pos[j]-pos[i] ---
    sum_ex = sum_ey = sum_ez = 0.0
    count = 0
    for j in range(len(pos)):
        if j == i or excluded[j]:
            continue
        des_x = goal[j][0] - goal[i][0]
        des_y = goal[j][1] - goal[i][1]
        des_z = goal[j][2] - goal[i][2]
        sum_ex += (pos[j][0] - pos[i][0]) - des_x
        sum_ey += (pos[j][1] - pos[i][1]) - des_y
        sum_ez += (pos[j][2] - pos[i][2]) - des_z
        count += 1
    if count > 0:
        mx, my, mz = sum_ex / count, sum_ey / count, sum_ez / count
        if math.sqrt(mx * mx + my * my) > _REL_THRESH:
            vx += _REL_K * mx
            vy += _REL_K * my
        if abs(mz) > _REL_THRESH:
            vz += _REL_K * mz

    return _clamp_speed(vx, vy, vz, max_speed)


class SimResult:
    """Tek senaryo (tek mod) koşum sonucu + metrikler."""

    def __init__(self, scenario: scn.Scenario) -> None:
        self.scenario = scenario
        self.n = len(scenario.drones)
        self.min_dist = float('inf')       # min ikili mesafe (çarpışma)
        self.max_slot_dev = 0.0            # slottan max sapma
        self.alt_min = float('inf')        # min irtifa (m)
        self.alt_max = 0.0                 # max irtifa (m)
        self.triggered = False             # APF hiç devreye girdi mi
        self.reached = 0
        self.series: list[tuple[float, float]] = []   # (t, min_dist)
        self.rms_series: list[tuple[float, float]] = []  # (t, formation_rms)
        self.t_end = 0.0
        self.recovery_time: float | None = None
        self.max_reversals = 0

    @property
    def passed(self) -> bool:
        """Emniyet eşiği korundu VE (gerekiyorsa) slot_dev tavanı aşılmadı."""
        ok = self.min_dist >= self.scenario.safety_radius_m
        if self.scenario.check_slot_dev:
            # slot_dev clamp KOMUT sınırı; dış itme fiziksel olarak geçici
            # aşabilir. Tolerans: tavan + makul pay (itme sönümlenir).
            ok = ok and self.max_slot_dev <= self.scenario.slot_dev_max_m + 1.0
        return ok


def _perturbation_vel(s: scn.Scenario, agent_id: int, t: float):
    """t anında bu agent için aktif dış itme hızı (yoksa sıfır)."""
    vx = vy = vz = 0.0
    for p in s.perturbations:
        if p.agent_id == agent_id and p.t_start <= t < p.t_end:
            vx += p.vel[0]
            vy += p.vel[1]
            vz += p.vel[2]
    return vx, vy, vz


def _ramp(cur: float, target: float, max_step: float) -> float:
    """Tek eksen ramp (formation_node slot yumuşatma)."""
    diff = target - cur
    step = max(-max_step, min(max_step, diff))
    return cur + step


def run_scenario(
    s: scn.Scenario, enable_tangent: bool = True,
) -> SimResult:
    """Senaryoyu NODE-SADIK pipeline ile koşturur (tek mod).

    enable_tangent: True → hibrit (deadlock'ta teğet), False → additive-only.
    """
    res = SimResult(s)
    n = res.n
    pos = [list(d.start) for d in s.drones]
    goal = [list(d.goal) for d in s.drones]        # slot geometrisi (final)
    slot = [list(d.start) for d in s.drones]        # ramp'lenen anlık slot
    excluded = [d.excluded for d in s.drones]
    vel = [[0.0, 0.0, 0.0] for _ in range(n)]
    prev_cmd = [[0.0, 0.0, 0.0] for _ in range(n)]
    params = make_params(s.max_speed_mps)

    # Osilasyon takibi (yatay hız yön tersine sayısı).
    prev_h: list = [None] * n
    rev = [0] * n

    # Son pertürbasyon bitiş anı (recovery ölçümü için).
    pert_end = max((p.t_end for p in s.perturbations), default=0.0)

    t = 0.0
    while t < _T_MAX:
        # --- 1) Metrik: anlık min ikili mesafe + irtifa + formation_rms ---
        cur_min = float('inf')
        for i in range(n):
            for j in range(i + 1, n):
                cur_min = min(cur_min, _dist(pos[i], pos[j]))
        res.min_dist = min(res.min_dist, cur_min)
        res.series.append((t, cur_min))

        sq = 0.0
        for i in range(n):
            alt = -pos[i][2]
            res.alt_min = min(res.alt_min, alt)
            res.alt_max = max(res.alt_max, alt)
            dev = _dist(pos[i], slot[i])
            res.max_slot_dev = max(res.max_slot_dev, dev)
            sq += dev * dev
        rms = math.sqrt(sq / n)
        res.rms_series.append((t, rms))
        # Recovery: pertürbasyon bittikten sonra rms eşiğin altına inince.
        if (res.recovery_time is None and pert_end > 0.0 and t >= pert_end
                and rms < s.recover_threshold_m):
            res.recovery_time = t - pert_end

        # --- 2) Slot ramp (start → goal), formation_node yumuşatma ---
        max_step = _TARGET_RAMP * _DT
        for i in range(n):
            for k in range(3):
                slot[i][k] = _ramp(slot[i][k], goal[i][k], max_step)

        # --- 3) Her drone: formation base_v + CA additive ---
        new_cmd = []
        for i in range(n):
            base_vx, base_vy, base_vz = _formation_base_velocity(
                i, pos, slot, goal, excluded, s.max_speed_mps,
            )
            # CA komşu gözlemleri (excluded atla — kontrat m.8).
            obs = []
            for j in range(n):
                if i == j or excluded[j]:
                    continue
                rx = pos[j][0] - pos[i][0]
                ry = pos[j][1] - pos[i][1]
                rz = pos[j][2] - pos[i][2]
                rvx = vel[j][0] - vel[i][0]
                rvy = vel[j][1] - vel[i][1]
                rvz = vel[j][2] - vel[i][2]
                d = math.sqrt(rx * rx + ry * ry + rz * rz)
                obs.append(NeighborObs(rx, ry, rz, rvx, rvy, rvz, d))

            vx, vy, vz, risk = additive_avoidance(
                base_vx, base_vy, base_vz, obs, params,
                enable_tangent=enable_tangent,
            )
            if risk:
                res.triggered = True
            else:
                vx, vy, vz = base_vx, base_vy, base_vz

            # Slew (mesafeye bağlı ivme), nihai çıkış hızına.
            min_d = min((o.distance for o in obs), default=float('inf'))
            accel = (_MAX_ACCEL if min_d < _EMERGENCY_RADIUS
                     else _MAX_ACCEL_NORMAL)
            vx, vy, vz = slew_limit(
                tuple(prev_cmd[i]), (vx, vy, vz), accel * _DT,
            )
            new_cmd.append([vx, vy, vz])

        # --- 4) Carrot + SINIR clamp + efektif hız + integre ---
        for i in range(n):
            vx, vy, vz = new_cmd[i]
            prev_cmd[i] = [vx, vy, vz]

            cx = pos[i][0] + vx * _CARROT_LH
            cy = pos[i][1] + vy * _CARROT_LH
            cz = pos[i][2] + vz * _CARROT_LH
            # Slot_dev clamp (carrot vs anlık slot) + irtifa clamp.
            cx, cy = clamp_slot_deviation(
                cx, cy, slot[i][0], slot[i][1], s.slot_dev_max_m,
            )
            cz = clamp_altitude_ned(cz, _ALT_MIN, _ALT_MAX)
            # Efektif hız = clamp'li carrot'tan geri türet (px4 pozisyon takibi).
            evx = (cx - pos[i][0]) / _CARROT_LH
            evy = (cy - pos[i][1]) / _CARROT_LH
            evz = (cz - pos[i][2]) / _CARROT_LH

            # Pertürbasyon (dış itme/rüzgar) — kontrolün ÜSTÜNE biner.
            px, py, pz = _perturbation_vel(s, s.drones[i].agent_id, t)
            evx += px
            evy += py
            evz += pz

            # Osilasyon say (keskin yön tersine).
            ch = math.sqrt(evx * evx + evy * evy)
            p = prev_h[i]
            if p is not None and ch > 0.15 and p[2] > 0.15:
                if evx * p[0] + evy * p[1] < 0.0:
                    rev[i] += 1
            prev_h[i] = (evx, evy, ch)

            pos[i][0] += evx * _DT
            pos[i][1] += evy * _DT
            pos[i][2] += evz * _DT
            vel[i] = [evx, evy, evz]

        t += _DT
        # Hover formasyon senaryolarında "varış" goal=start → erken bitmesin;
        # pertürbasyon varsa tam süre koş (toparlanmayı görmek için).
        if not s.perturbations and all(
            _dist(pos[i], goal[i]) < _GOAL_TOL for i in range(n)
        ):
            break

    res.t_end = t
    res.reached = sum(
        1 for i in range(n) if _dist(pos[i], goal[i]) < 0.5
    )
    res.max_reversals = max(rev) if rev else 0
    if res.alt_min == float('inf'):
        res.alt_min = 0.0
    return res


def _write_csv(out_dir: str, res: SimResult, mode: str) -> None:
    """Min-mesafe–zaman + formation_rms serisini CSV'ye yazar (jüri grafiği)."""
    path = os.path.join(out_dir, f'{res.scenario.name}_{mode}.csv')
    sr = res.scenario.safety_radius_m
    rms_map = dict(res.rms_series)
    with open(path, 'w') as f:
        f.write('t_s,min_dist_m,safety_radius_m,formation_rms_m\n')
        for t, d in res.series:
            rms = rms_map.get(t, 0.0)
            f.write(f'{t:.3f},{d:.4f},{sr:.3f},{rms:.4f}\n')


def _run_suite(enable_tangent: bool) -> list[SimResult]:
    """Tüm senaryoları verilen modda koşturur."""
    return [run_scenario(s, enable_tangent) for s in scn.SCENARIOS]


def _category_pct(results: list[SimResult]) -> dict:
    """Kategori bazında kaçınma başarı yüzdesi (rapor A2 isteri).

    Yalnızca CA-çözülebilir senaryolar sayılır.
    """
    out = {}
    for cat in scn.CATEGORIES:
        rs = [r for r in results
              if r.scenario.category == cat and r.scenario.ca_solvable]
        if not rs:
            continue
        passed = sum(1 for r in rs if r.passed)
        out[cat] = (passed, len(rs), 100.0 * passed / len(rs))
    return out


def main() -> None:
    """İki modu (additive-only vs hibrit) karşılaştırır, detay tablo + CSV üretir."""
    out_dir = os.path.expanduser('~/ros2_ws/analysis/collision_sim')
    os.makedirs(out_dir, exist_ok=True)

    print(scn.summary())

    # ---- İKİ MOD KARŞILAŞTIRMA (teğet kaçışın değeri) ----
    print('\n=== MOD KARSILASTIRMA: additive-only vs hibrit (additive+tegset) ===')
    add_results = _run_suite(enable_tangent=False)
    hyb_results = _run_suite(enable_tangent=True)
    add_map = {r.scenario.name: r for r in add_results}

    solvable = [r for r in hyb_results if r.scenario.ca_solvable]
    add_pass = sum(
        1 for r in add_results if r.scenario.ca_solvable and r.passed
    )
    hyb_pass = sum(1 for r in solvable if r.passed)
    print(f'{"senaryo":24s} {"kategori":10s} '
          f'{"add.min":>8s} {"hib.min":>8s} {"kazanim":>8s}')
    print('-' * 62)
    for r in hyb_results:
        if not r.scenario.ca_solvable:
            continue
        a = add_map[r.scenario.name]
        gain = ''
        if not a.passed and r.passed:
            gain = 'TEGET+'      # additive kaldı, hibrit kurtardı
        elif a.passed and not r.passed:
            gain = 'REGRES-'
        print(f'{r.scenario.name:24s} {r.scenario.category:10s} '
              f'{a.min_dist:8.3f} {r.min_dist:8.3f} {gain:>8s}')
    print('-' * 62)
    print(f'GECEN: additive-only={add_pass}/{len(solvable)}  '
          f'hibrit={hyb_pass}/{len(solvable)}  '
          f'(TEGET+ = teğetin kurtardığı senaryo sayısı)')

    # ---- HİBRİT (saha modu) DETAY TABLO + CSV ----
    print('\n=== HIBRIT (SAHA MODU) DETAY ===')
    header = (
        f'{"senaryo":22s} {"kategori":10s} {"min(m)":>7s} '
        f'{"slot_dev":>8s} {"irtifa":>11s} {"rms":>6s} '
        f'{"recov":>6s} {"sonuc":>7s} {"kacis":>6s}'
    )
    print(header)
    print('-' * len(header))
    for r in hyb_results:
        _write_csv(out_dir, r, 'hibrit')
        _write_csv(out_dir, add_map[r.scenario.name], 'additive')
        verdict = 'GECTI' if r.passed else '*KALDI*'
        trig = 'evet' if r.triggered else 'yok'
        recov = (f'{r.recovery_time:.1f}s' if r.recovery_time is not None
                 else '—')
        alt = f'{r.alt_min:.0f}-{r.alt_max:.0f}m'
        final_rms = r.rms_series[-1][1] if r.rms_series else 0.0
        print(
            f'{r.scenario.name:22s} {r.scenario.category:10s} '
            f'{r.min_dist:7.3f} {r.max_slot_dev:8.2f} {alt:>11s} '
            f'{final_rms:6.2f} {recov:>6s} {verdict:>7s} {trig:>6s}'
        )

    # ---- KATEGORİ BAZINDA % BAŞARI (rapor A2) ----
    print('\n=== KATEGORI BAZINDA KACINMA BASARISI (hibrit, rapor A2) ===')
    for cat, (p, tot, pct) in _category_pct(hyb_results).items():
        print(f'  {cat:12s}: {p}/{tot}  (%{pct:.0f})')

    # ---- Özet + ihlaller ----
    fails = [r for r in solvable if not r.passed]
    print('-' * len(header))
    print(f'TOPLAM (CA-cozulebilir): {hyb_pass}/{len(solvable)} '
          f'(%{100.0 * hyb_pass / len(solvable):.1f})')
    if fails:
        print('\n! IHLAL EDEN (CA-cozulebilir) SENARYOLAR:')
        for r in fails:
            print(f'  {r.scenario.name}: min={r.min_dist:.3f}m '
                  f'slot_dev={r.max_slot_dev:.2f}m '
                  f'irtifa={r.alt_min:.0f}-{r.alt_max:.0f}m')
    else:
        print('\nCA-cozulebilir senaryolarda hicbir ihlal yok.')

    unsolv = [r for r in hyb_results if not r.scenario.ca_solvable]
    if unsolv:
        print('\nGOREV KATMANI SORUMLULUGU (CA tek basina cozemez):')
        for r in unsolv:
            print(f'  {r.scenario.name}: min={r.min_dist:.3f}m '
                  f'irtifa={r.alt_min:.0f}-{r.alt_max:.0f}m (clamp testi)')

    print(f'\nCSV grafik verileri: {out_dir}')


if __name__ == '__main__':
    main()
