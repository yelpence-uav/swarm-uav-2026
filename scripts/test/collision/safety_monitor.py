#!/usr/bin/env python3
"""safety_monitor.py — İHA-İHA arası min mesafe ölçüm/kanıt aracı (YERDE).

Bu bir ÖLÇÜM cihazıdır, kontrolcü DEĞİLDİR: yalnızca tüm drone'ların
konumunu DİNLER, anlık en küçük ikili mesafeyi hesaplar, CSV'ye + ekrana
yazar. Hiçbir setpoint/komut YAYINLAMAZ → dağıtık sürü mimarisine dokunmaz
(şartname: merkezi sürü algoritması eksik puan; bu kontrol değil ölçümdür).

apf_sim.py algoritma testini (simülasyon) nasıl ölçüyorsa, bu da gerçek
uçuşu/SITL'i aynı şekilde ölçer: min-mesafe–zaman CSV'si → jüri grafiği.

ÜRETTİĞİ KANITLAR (şartname):
  - {run}.csv         : min-mesafe–zaman serisi (jüri grafiği verisi)
  - {run}_events.csv  : "kritik yaklaşma anları" (en çok yaklaşılan dipler)
  - kapanış özeti     : min mesafe, ihlal sayısı, uyarı süresi, salınım
                        sayısı → TEMİZ/İHLAL

OSİLASYON (salınım): şartname osilasyon gözlemini cezalandırır (-10 p). Her
drone'un yatay hızı izlenir; eşik üstündeyken yön tersine dönüşü (chattering)
sayılır. apf_sim offline'da nasıl sayıyorsa burada gerçek uçuş/SITL aynı
mantıkla sayar → "drone'lar titremiyor" iddiası sahada da kanıtlanır.

KOORDİNAT: her drone /swarm/agent/drone{id}/telemetry üzerinden NED
pozisyonunu (pos_x/y/z) yayınlar. SITL'de tüm drone'lar aynı simülatör
origin'inde olduğundan pozisyonlar doğrudan kıyaslanabilir (ground truth).

KULLANIM:
    python3 scripts/test/collision/safety_monitor.py --ros-args \\
        -p agent_ids:=[1,2,3] -p safety_radius_m:=1.5 \\
        -p warn_radius_m:=2.0 -p run_label:=swap_test1
"""

import math
import os
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

from swarm_interfaces.msg import AgentSetpoint, AgentStatus


# BEST_EFFORT abone: hem reliable hem best_effort yayıncıyla uyumlu.
_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)

# AgentStatus state enum → kısa ad (INTERFACE_CONTRACT madde 5).
_STATE_AD = {
    0: 'UNKNOWN', 1: 'IDLE', 2: 'ARMING', 3: 'ARMED', 4: 'TAKEOFF',
    5: 'IN_SWARM', 6: 'EXEC_TASK', 7: 'DETACHED', 8: 'PREC_LAND',
    9: 'WAIT_REJOIN', 10: 'REJOINING', 11: 'RTL', 12: 'LANDING',
    13: 'LANDED', 14: 'FAILSAFE', 15: 'STANDBY',
}

# Avoidance dışı (excluded) state'ler: bunlara yakınlık "beklenen" olabilir
# (örn. inen drone). Kritik anlar bunu ayrı işaretler.
_EXCLUDED = frozenset({7, 8, 13, 14})

# Düz-dünya yaklaşımı (sürü ölçeğinde hata ihmal edilebilir).
_M_PER_DEG_LAT = 111320.0


def _latlon_to_ne(lat: float, lon: float,
                  lat0: float, lon0: float) -> tuple:
    """GPS lat/lon → referans noktasına göre (kuzey, doğu) metre.

    KRİTİK: pos_x/pos_y KULLANILAMAZ — her PX4 kendi origin'ine göre
    raporlar (SITL'de bile hepsi ~0,0). GPS gerçek konumu verir.
    """
    north = (lat - lat0) * _M_PER_DEG_LAT
    east = (lon - lon0) * _M_PER_DEG_LAT * math.cos(math.radians(lat0))
    return north, east


def _dist(a, b) -> float:
    """İki NED noktası (x,y,z) arası Öklid mesafesi."""
    return math.sqrt(
        (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
    )


def _sname(s: int) -> str:
    """State int → kısa ad."""
    return _STATE_AD.get(int(s), f'?{s}')


class SafetyMonitor(Node):
    """Tüm drone'ların min ikili mesafesini ölçüp kaydeden yer aracı."""

    def __init__(self) -> None:
        super().__init__('safety_monitor')

        self.declare_parameter('agent_ids', [1, 2, 3])
        # Emniyet eşiği 1.5 m (merkez-merkez) — emniyet-mesafesi-tasarimi.
        # Uyarı bandı emniyetin üstünde (yaklaşma erken görünsün).
        self.declare_parameter('safety_radius_m', 1.5)
        self.declare_parameter('warn_radius_m', 2.0)
        self.declare_parameter('rate_hz', 10.0)
        self.declare_parameter('stale_s', 1.0)
        # Osilasyon eşiği: yatay hız bu büyüklüğün üstündeyken yön tersine
        # dönerse "salınım" sayılır (apf_sim ile AYNI mantık → sim/SITL kıyas).
        self.declare_parameter('osc_speed_thresh', 0.15)
        self.declare_parameter('z_dev_thresh_m', 0.05)
        self.declare_parameter('max_accel_mps2', 30.0)
        self.declare_parameter(
            'out_dir', os.path.expanduser('~/ros2_ws/analysis/collision_sitl'),
        )
        self.declare_parameter('run_label', '')

        gp = self.get_parameter
        self._ids = [int(x) for x in gp('agent_ids').value]
        self._safety = float(gp('safety_radius_m').value)
        self._warn = float(gp('warn_radius_m').value)
        rate = float(gp('rate_hz').value)
        self._stale_s = float(gp('stale_s').value)
        self._osc_thresh = float(gp('osc_speed_thresh').value)
        self._z_thresh   = float(gp('z_dev_thresh_m').value)
        self._max_accel  = float(gp('max_accel_mps2').value)
        out_dir = str(gp('out_dir').value)
        run = str(gp('run_label').value) or time.strftime('run_%Y%m%d_%H%M%S')

        os.makedirs(out_dir, exist_ok=True)
        self._csv_path = os.path.join(out_dir, f'{run}.csv')
        self._events_path = os.path.join(out_dir, f'{run}_events.csv')
        self._run = run

        # Drone ID -> pozisyon / state / son alım zamanı
        self._pos: dict[int, tuple] = {}
        self._state: dict[int, int] = {}
        self._rx: dict[int, float] = {}
        # Osilasyon takibi: drone -> yatay hız (vx, vy) + geçerlilik;
        # drone -> önceki (vx, vy, |h|); drone -> yön-tersine (reversal) sayısı.
        self._vel: dict[int, tuple] = {}
        self._osc_prev: dict[int, tuple] = {}
        self._reversals: dict[int, int] = {}
        self._osc_total = 0      # tüm drone'larda toplam salınım
        # İrtifa senkronizasyonu: drone'lar arası en büyük irtifa farkı
        # (Aşama 1 baseline kararlılık + Aşama 4 yer değiştirmede irtifa kaybı).
        self._alt_spread_max = 0.0

        # CA aktivasyon per-drone
        self._ca_active:   dict[int, bool]  = {i: False for i in self._ids}
        self._ca_start:    dict[int, float] = {i: 0.0   for i in self._ids}
        self._ca_count:    dict[int, int]   = {i: 0     for i in self._ids}
        self._ca_total_s:  dict[int, float] = {i: 0.0   for i in self._ids}

        # Z sapması per-drone (CA irtifayı değiştiriyor mu?)
        self._z0:          dict[int, float | None] = {i: None for i in self._ids}
        self._z_dev_max:   dict[int, float] = {i: 0.0 for i in self._ids}
        self._z_dev_count: dict[int, int]   = {i: 0   for i in self._ids}

        # v_cmd vs v_formation farkı
        self._raw_v:   dict[int, tuple | None] = {i: None for i in self._ids}
        self._mod_max: dict[int, float] = {i: 0.0 for i in self._ids}
        self._mod_sum: dict[int, float] = {i: 0.0 for i in self._ids}
        self._mod_n:   dict[int, int]   = {i: 0   for i in self._ids}

        # Slew ihlali
        self._prev_vcmd:  dict[int, tuple | None] = {i: None for i in self._ids}
        self._slew_viol:  dict[int, int]           = {i: 0   for i in self._ids}

        # İstatistik
        self._min_ever = float('inf')
        self._violations = 0     # safety altına düşülen tick sayısı
        self._n_ticks = 0
        self._n_warn = 0         # warn altına düşülen tick sayısı
        self._t0 = time.monotonic()

        # Kritik yaklaşma "episode"ları (warn altına girip çıkma).
        self._in_ep = False
        self._ep_min = float('inf')
        self._ep_pair = ''
        self._ep_t = 0.0
        self._ep_states = ('', '')
        self._ep_excluded = False
        self._events: list = []

        for did in self._ids:
            self.create_subscription(
                AgentStatus,
                f'/swarm/agent/drone{did}/telemetry',
                lambda msg, d=did: self._on_status(d, msg),
                _QOS,
            )
            self.create_subscription(
                AgentSetpoint,
                f'/drone_{did}/control/setpoint',
                lambda msg, d=did: self._on_setpoint(d, msg),
                _QOS,
            )
            self.create_subscription(
                AgentSetpoint,
                f'/drone_{did}/control/setpoint/raw',
                lambda msg, d=did: self._on_raw(d, msg),
                _QOS,
            )

        self._csv = open(self._csv_path, 'w')
        self._csv.write(
            't_s,min_dist_m,pair,state_a,state_b,safety_radius_m,'
            'warn_radius_m,violation,warning,pair_excluded,alt_spread_m\n'
        )

        self.create_timer(1.0 / rate, self._tick)

        self.get_logger().info(
            f'safety_monitor [{run}]: agent_ids={self._ids} '
            f'safety={self._safety}m warn={self._warn}m rate={rate}Hz '
            f'csv={self._csv_path}'
        )

    def _on_status(self, did: int, msg: AgentStatus) -> None:
        if not (msg.xy_valid and msg.z_valid):
            return
        # GPS yoksa kullanma (pos_x/pos_y drone'lar arası kıyaslanamaz).
        if msg.lat_deg == 0.0 and msg.lon_deg == 0.0:
            return
        # (lat, lon, pos_z): yatay GPS'ten, dikey pos_z'den (aynı zemin).
        self._pos[did] = (
            float(msg.lat_deg), float(msg.lon_deg), float(msg.pos_z),
        )
        # Yatay hız (osilasyon için): tek-drone kendi frame'inde, yön
        # değişimi frame-bağımsız → çiftler arası kıyas gerekmez. Hız tahmini
        # güvenilmezse (v_xy_valid=false) yön sayma → sahte salınım önlenir.
        if bool(msg.v_xy_valid):
            self._vel[did] = (float(msg.vel_x), float(msg.vel_y))
        else:
            self._vel.pop(did, None)
            self._osc_prev.pop(did, None)
        self._state[did] = int(msg.state)
        self._rx[did] = time.monotonic()
        if self._z0.get(did) is None and msg.z_valid:
            self._z0[did] = float(msg.pos_z)

    def _on_raw(self, did: int, msg: AgentSetpoint) -> None:
        if msg.velocity_valid:
            self._raw_v[did] = (float(msg.vx), float(msg.vy), float(msg.vz))

    def _on_setpoint(self, did: int, msg: AgentSetpoint) -> None:
        t = time.monotonic() - self._t0
        ca_active = getattr(msg, 'source_module', '') == 'collision_avoidance'

        # CA aktivasyon süresi
        if ca_active and not self._ca_active[did]:
            self._ca_active[did] = True
            self._ca_start[did] = t
            self._ca_count[did] += 1
        elif not ca_active and self._ca_active[did]:
            self._ca_active[did] = False
            self._ca_total_s[did] += t - self._ca_start[did]

        if not msg.velocity_valid:
            return

        vx, vy, vz = float(msg.vx), float(msg.vy), float(msg.vz)

        # Z sapması: CA çıkış pozisyonu vs başlangıç irtifası
        z0 = self._z0.get(did)
        if z0 is not None and msg.position_valid:
            z_dev = abs(float(msg.z) - z0)
            if z_dev > self._z_dev_max[did]:
                self._z_dev_max[did] = z_dev
            if z_dev > self._z_thresh:
                self._z_dev_count[did] += 1

        # v_cmd vs v_formation farkı
        raw = self._raw_v.get(did)
        if raw is not None:
            mod = math.sqrt((vx-raw[0])**2 + (vy-raw[1])**2)
            if mod > self._mod_max[did]:
                self._mod_max[did] = mod
            self._mod_sum[did] += mod
            self._mod_n[did] += 1

        # Slew ihlali
        prev = self._prev_vcmd.get(did)
        if prev is not None:
            delta = math.sqrt(
                (vx-prev[0])**2 + (vy-prev[1])**2 + (vz-prev[2])**2)
            if delta > self._max_accel * 0.05 * 1.2:
                self._slew_viol[did] += 1
        self._prev_vcmd[did] = (vx, vy, vz)

    def _tick(self) -> None:
        now = time.monotonic()
        fresh = {
            d: p for d, p in self._pos.items()
            if now - self._rx.get(d, 0.0) <= self._stale_s
        }
        if len(fresh) < 2:
            return

        ids = sorted(fresh.keys())

        # --- Osilasyon (yön-tersine) takibi: her drone kendi hızında ---
        # apf_sim ile AYNI mantık: yatay hız eşiğin üstündeyken ardışık iki
        # örnek ters yöne bakıyorsa (nokta çarpım < 0 → >90° dönüş) salınım say.
        for d in ids:
            v = self._vel.get(d)
            if v is None:
                continue
            h = math.hypot(v[0], v[1])
            prev = self._osc_prev.get(d)
            if (prev is not None and h > self._osc_thresh
                    and prev[2] > self._osc_thresh
                    and v[0] * prev[0] + v[1] * prev[1] < 0.0):
                self._reversals[d] = self._reversals.get(d, 0) + 1
                self._osc_total += 1
            self._osc_prev[d] = (v[0], v[1], h)

        # GPS lat/lon → ortak (kuzey, doğu, z) frame (ref = ilk drone).
        ref_lat, ref_lon = fresh[ids[0]][0], fresh[ids[0]][1]
        ned = {}
        for d in ids:
            lat, lon, z = fresh[d]
            n, e = _latlon_to_ne(lat, lon, ref_lat, ref_lon)
            ned[d] = (n, e, z)

        cur_min = float('inf')
        a = b = ids[0]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                d = _dist(ned[ids[i]], ned[ids[j]])
                if d < cur_min:
                    cur_min = d
                    a, b = ids[i], ids[j]

        # İrtifa farkı (NED z): drone'lar arası max − min. İrtifa = −z ama
        # FARK için işaret önemsiz (|Δz|). Yer değiştirirken dikey dağılır mı?
        zs = [ned[d][2] for d in ids]
        alt_spread = max(zs) - min(zs)
        if alt_spread > self._alt_spread_max:
            self._alt_spread_max = alt_spread

        sa = self._state.get(a, 0)
        sb = self._state.get(b, 0)
        excluded = sa in _EXCLUDED or sb in _EXCLUDED
        violation = cur_min < self._safety
        warning = cur_min < self._warn

        # İstatistik
        self._n_ticks += 1
        if warning:
            self._n_warn += 1
        if violation:
            self._violations += 1
        if cur_min < self._min_ever:
            self._min_ever = cur_min

        # Kritik yaklaşma episode takibi (warn altına girip çıkma).
        t = now - self._t0
        if warning:
            if not self._in_ep or cur_min < self._ep_min:
                self._in_ep = True
                self._ep_min = cur_min
                self._ep_pair = f'{a}-{b}'
                self._ep_t = t
                self._ep_states = (_sname(sa), _sname(sb))
                self._ep_excluded = excluded
        elif self._in_ep:
            self._close_episode()

        if violation:
            self.get_logger().warning(
                f'⚠ EMNİYET İHLALİ: drone{a}-{b} arası {cur_min:.3f}m '
                f'< {self._safety:.2f}m '
                f'[{_sname(sa)}/{_sname(sb)}]'
            )

        self._csv.write(
            f'{t:.3f},{cur_min:.4f},{a}-{b},{_sname(sa)},{_sname(sb)},'
            f'{self._safety:.3f},{self._warn:.3f},'
            f'{int(violation)},{int(warning)},{int(excluded)},'
            f'{alt_spread:.3f}\n'
        )
        self._csv.flush()

        self.get_logger().info(
            f'min={cur_min:.3f}m (drone{a}-{b}) | dek min={self._min_ever:.3f}m'
            f' | ihlal={self._violations} | kritik={len(self._events)}'
            f' | salınım={self._osc_total} | irtifaΔ={alt_spread:.2f}m',
            throttle_duration_sec=1.0,
        )

    def _close_episode(self) -> None:
        """Açık kritik-yaklaşma episode'unu olay listesine yazar."""
        self._events.append((
            self._ep_t, self._ep_pair, self._ep_min,
            self._ep_states[0], self._ep_states[1], self._ep_excluded,
        ))
        self._in_ep = False
        self._ep_min = float('inf')

    def ozet_bas(self) -> None:
        """Kapanışta özet + kritik anlar dosyasını yazar."""
        if self._in_ep:
            self._close_episode()

        # Kritik anlar CSV'si
        try:
            with open(self._events_path, 'w') as f:
                f.write('t_s,pair,min_dist_m,state_a,state_b,excluded\n')
                for ev in self._events:
                    f.write(
                        f'{ev[0]:.3f},{ev[1]},{ev[2]:.4f},{ev[3]},{ev[4]},'
                        f'{int(ev[5])}\n'
                    )
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(f'kritik anlar yazılamadı: {e}')

        pct_warn = (
            100.0 * self._n_warn / self._n_ticks if self._n_ticks else 0.0
        )
        # En çok salınan drone (apf_sim'in max_reversals'ı ile kıyaslanabilir).
        osc_max_id, osc_max = 0, 0
        for d, c in self._reversals.items():
            if c > osc_max:
                osc_max, osc_max_id = c, d
        # Açık CA aktivasyonlarını kapat
        t_now = time.monotonic() - self._t0
        for did in self._ids:
            if self._ca_active[did]:
                self._ca_total_s[did] += t_now - self._ca_start[did]

        durum = 'TEMİZ ✓' if self._violations == 0 else 'İHLAL VAR ✗'
        self.get_logger().info(
            f'=== ÖZET [{self._run}]: min mesafe = {self._min_ever:.3f}m | '
            f'emniyet = {self._safety:.2f}m | ihlal tick = {self._violations} '
            f'| uyarı süresi = %{pct_warn:.1f} | kritik an = '
            f'{len(self._events)} | salınım toplam = {self._osc_total} '
            f'(en çok drone{osc_max_id}: {osc_max}) '
            f'| max irtifa farkı = {self._alt_spread_max:.2f}m → {durum} ==='
        )
        # CA metrik özeti
        for did in self._ids:
            mod_avg = (self._mod_sum[did] / self._mod_n[did]
                       if self._mod_n[did] > 0 else 0.0)
            self.get_logger().info(
                f'  drone{did} CA: '
                f'aktivasyon={self._ca_count[did]}x '
                f'süre={self._ca_total_s[did]:.1f}s | '
                f'Z_dev_max={self._z_dev_max[did]:.4f}m '
                f'({"✓" if self._z_dev_max[did] <= self._z_thresh else "✗ AŞIM"}) | '
                f'v_mod_max={self._mod_max[did]:.3f}m/s ort={mod_avg:.3f}m/s | '
                f'slew_ihlal={self._slew_viol[did]}'
            )
        if self._events:
            self.get_logger().info('--- KRİTİK YAKLAŞMA ANLARI ---')
            for ev in self._events:
                etk = ' (excluded/iniş)' if ev[5] else ''
                self.get_logger().info(
                    f'  t={ev[0]:.1f}s drone{ev[1]} min={ev[2]:.3f}m '
                    f'[{ev[3]}/{ev[4]}]{etk}'
                )
        self.get_logger().info(f'CSV: {self._csv_path}')
        self.get_logger().info(f'Kritik anlar: {self._events_path}')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SafetyMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.ozet_bas()
        try:
            node._csv.close()
        except Exception:  # noqa: BLE001
            pass
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:  # noqa: BLE001
            pass


if __name__ == '__main__':
    main()
