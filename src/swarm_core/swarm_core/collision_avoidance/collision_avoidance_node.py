"""collision_avoidance_node.py — Hız-tabanlı çarpışma önleme filtresi (son emniyet).

Setpoint zincirinde formasyon ile px4_interface ARASINDA durur:

    formation_control → /drone_{id}/control/setpoint/raw
        → collision_avoidance (BU NODE, hız filtresi)
        → /drone_{id}/control/setpoint → px4_interface → PX4 (Offboard hız)

Sistem HIZ-TABANLIDIR (bkz. ca_core.py): formation node saf hız setpoint'i
(position_valid=False, velocity_valid=True) üretir; px4_bridge velocity_only
modda PX4'e SADECE hız gönderir, pozisyon kontrolü yapmaz. Bu node da hız
üretir — pozisyon ÜRETMEZ. Risk yokken ham setpoint olduğu gibi geçirilir
(formasyon kalitesi korunur, CA seyirde uyur). Etki yarıçapı içinde komşu
varsa ca_core (kapanma-kapılı Khatib + teğet + r_min projeksiyon) formasyon
hızına bir kaçış hızı ekler.

GİRİŞ TOPIC'LERİ:
    /drone_{id}/control/setpoint/raw            (formasyon ham hız hedefi)
    /swarm/agent/drone{id}/telemetry            (kendi konum/hız/state/validity)
    /swarm/public/formation/target              (komşu keşfi için agent_ids)
    /swarm/agent/drone{id}/neighbor/drone{nid}  (her komşu, kinematic_fusion)

ÇIKIŞ:
    /drone_{id}/control/setpoint                (px4_interface'in dinlediği)

GÜVENLİK KURALLARI (INTERFACE_CONTRACT m.8-9):
    - Komşu state ∈ {DETACHED, PRECISION_LANDING, LANDED, FAILSAFE} → atla
    - link_active=false veya data_age_ms > eşik → atla
    - Ham setpoint FAILSAFE önceliğinde / land/rtl/hold ise → dokunma, geçir
    - Kendi xy/z_valid=false → CA'sız geçir (konum güvenilmez)
    - Kalkış/iniş fazı (irtifa < gate) → yatay kaçış dikey manevrayı bozmasın, geçir
"""

import copy

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_interfaces.msg import (
    AgentSetpoint,
    AgentStatus,
    FormationCommand,
    NeighborInfo,
)

from .ca_core import CaParams, CollisionAvoidanceCore, NeighborObs


# Avoidance hesabından çıkarılan komşu state'leri (kontrat m.8).
_AVOIDANCE_DISI_STATELER = frozenset({
    AgentStatus.STATE_DETACHED,
    AgentStatus.STATE_PRECISION_LANDING,
    AgentStatus.STATE_LANDED,
    AgentStatus.STATE_FAILSAFE,
})


_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_BEST_EFFORT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


class CollisionAvoidanceNode(Node):
    """Hız-tabanlı çarpışma önleme filtre node'u — tek drone'da çalışır."""

    def __init__(self) -> None:
        super().__init__('collision_avoidance')

        self._declare_params()

        # ----- Durum -----
        self._raw: AgentSetpoint | None = None
        self._raw_stamp: float = 0.0

        self._cur_z: float = 0.0
        self._cur_vx: float = 0.0
        self._cur_vy: float = 0.0
        self._cur_vz: float = 0.0
        self._pos_ok: bool = False  # xy_valid && z_valid

        self._neighbors: dict[int, NeighborInfo] = {}
        self._neighbor_rx: dict[int, float] = {}
        self._neighbor_subs: dict[int, object] = {}

        self._sequence_num: int = 0

        # Tanı sayaçları
        self._n_passthrough = 0     # risk yok / bypass — ham geçirildi
        self._n_avoid = 0           # CA kaçışı uygulandı
        self._n_skip_state = 0      # komşu state avoidance dışı
        self._n_skip_stale = 0      # komşu link/yaş eski
        self._n_gate_alt = 0        # kalkış/iniş gate — CA pasif
        self._last_active_log: float = 0.0

        self._ca = CollisionAvoidanceCore(CaParams(
            dt=1.0 / self._publish_rate_hz,
            d0=self._d0_m,
            hard=self._hard_m,
            r_min=self._r_min_m,
            f_sat=self._f_sat,
            c_dead=self._c_dead_mps,
            c_ref=self._c_ref_mps,
            c_damp=self._c_damp,
            damp_band=self._damp_band_m,
            k_tan=self._k_tan,
            v_max=self._v_max_mps,
            slew_normal=self._slew_normal,
            slew_emergency=self._slew_emergency,
        ))

        self._setup_io()

        self._timer = self.create_timer(
            1.0 / self._publish_rate_hz, self._tick,
        )
        self.create_timer(5.0, self._diag_tick)

        self.get_logger().info(
            f'collision_avoidance başlatıldı (ca_core/Model B): '
            f'agent_id={self._agent_id} '
            f'd0={self._d0_m}m hard={self._hard_m}m r_min={self._r_min_m}m '
            f'c_ref={self._c_ref_mps}m/s rate={self._publish_rate_hz}Hz '
            f'static_neighbors={self._static_neighbor_ids}'
        )

    # ---------- Parametreler ----------
    def _declare_params(self) -> None:
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('neighbor_ids', [0])
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('raw_timeout_s', 0.5)
        # Komşu geçerlilik eşikleri
        self.declare_parameter('neighbor_stale_ms', 500)
        self.declare_parameter('neighbor_rx_stale_s', 0.5)
        # Kalkış/iniş APF pasif eşiği: irtifa (=−z) bu eşiğin altındayken
        # ham setpoint passthrough → tırmanış/alçalış yatay kaçışla bozulmaz.
        # Görev irtifası 5–30 m, gate 3 m → görev uçuşunda tetiklenmez. 0=kapalı.
        self.declare_parameter('altitude_gate_m', 3.0)
        # --- ca_core (Model B) yarıçapları — katmanlı emniyet ---
        # Hiyerarşi: r_min(1.5) < hard(2.0) < d0(3.5) < aralık(5.0).
        # d0 < aralık → nominal formasyonda CA UYUR (formasyon bozulmaz).
        self.declare_parameter('d0_m', 4.5)            # influence: itki başlar
        self.declare_parameter('hard_m', 2.0)          # acil: doygunluk + kapı açık
        self.declare_parameter('r_min_m', 1.5)         # hard floor: projeksiyon
        self.declare_parameter('f_sat', 6.0)           # itici doygunluk büyüklüğü
        self.declare_parameter('c_dead_mps', 0.2)      # kapanma-hızı deadband (mikro-osilasyon)
        self.declare_parameter('c_ref_mps', 1.0)       # kapanma-hızı kapı bandı
        self.declare_parameter('c_damp', 0.7)          # radyal sönüm (standoff salınımı)
        self.declare_parameter('damp_band_m', 0.5)     # içeri-frenleme bandı (hard..hard+band)
        self.declare_parameter('k_tan', 0.9)           # teğet kazancı
        self.declare_parameter('v_max_mps', 4.0)       # XY hız tavanı
        # İvme sınırı (slew): mesafeye bağlı — yakınsa acil (hızlı kaçış),
        # uzaksa normal (titremesiz). ca_core içinde histerezisle yönetilir.
        self.declare_parameter('slew_normal_mps2', 4.0)
        self.declare_parameter('slew_emergency_mps2', 30.0)

        gp = self.get_parameter
        self._agent_id = int(gp('agent_id').value)
        self._static_neighbor_ids = [
            int(x) for x in gp('neighbor_ids').value if int(x) > 0
        ]
        self._publish_rate_hz = float(gp('publish_rate_hz').value)
        self._raw_timeout_s = float(gp('raw_timeout_s').value)
        self._neighbor_stale_ms = int(gp('neighbor_stale_ms').value)
        self._neighbor_rx_stale_s = float(gp('neighbor_rx_stale_s').value)
        self._altitude_gate_m = float(gp('altitude_gate_m').value)
        self._d0_m = float(gp('d0_m').value)
        self._hard_m = float(gp('hard_m').value)
        self._r_min_m = float(gp('r_min_m').value)
        self._f_sat = float(gp('f_sat').value)
        self._c_dead_mps = float(gp('c_dead_mps').value)
        self._c_ref_mps = float(gp('c_ref_mps').value)
        self._c_damp = float(gp('c_damp').value)
        self._damp_band_m = float(gp('damp_band_m').value)
        self._k_tan = float(gp('k_tan').value)
        self._v_max_mps = float(gp('v_max_mps').value)
        self._slew_normal = float(gp('slew_normal_mps2').value)
        self._slew_emergency = float(gp('slew_emergency_mps2').value)

        if not 1 <= self._agent_id <= 254:
            raise ValueError(f'agent_id 1-254 olmalı: {self._agent_id}')
        if self._publish_rate_hz <= 0.0:
            raise ValueError('publish_rate_hz pozitif olmalı')
        if not (self._r_min_m < self._hard_m < self._d0_m):
            raise ValueError('r_min < hard < d0 olmalı')

    # ---------- I/O kurulumu ----------
    def _setup_io(self) -> None:
        self._setpoint_pub = self.create_publisher(
            AgentSetpoint,
            f'/drone_{self._agent_id}/control/setpoint',
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            AgentSetpoint,
            f'/drone_{self._agent_id}/control/setpoint/raw',
            self._on_raw_setpoint,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            AgentStatus,
            f'/swarm/agent/drone{self._agent_id}/telemetry',
            self._on_agent_status,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            FormationCommand,
            '/swarm/public/formation/target',
            self._on_formation_command,
            _RELIABLE_QOS,
        )
        # Statik parametreyle verilen komşulara hemen abone ol.
        self._ensure_neighbor_subs(self._static_neighbor_ids)

    def _ensure_neighbor_subs(self, agent_ids) -> None:
        """Verilen ID'lerden kendisi olmayan her komşuya bir kez abone ol."""
        for nid in agent_ids:
            nid = int(nid)
            if nid == self._agent_id or nid <= 0 or nid in self._neighbor_subs:
                continue
            topic = (
                f'/swarm/agent/drone{self._agent_id}/neighbor/drone{nid}'
            )
            self._neighbor_subs[nid] = self.create_subscription(
                NeighborInfo,
                topic,
                lambda m, n=nid: self._on_neighbor(n, m),
                _BEST_EFFORT_QOS,
            )
            self.get_logger().info(f'NeighborInfo aboneliği: drone{nid}')

    # ---------- Callback'ler ----------
    def _on_raw_setpoint(self, msg: AgentSetpoint) -> None:
        self._raw = msg
        self._raw_stamp = self.get_clock().now().nanoseconds * 1e-9

    def _on_agent_status(self, msg: AgentStatus) -> None:
        self._cur_z = float(msg.pos_z)
        self._cur_vx = float(msg.vel_x)
        self._cur_vy = float(msg.vel_y)
        self._cur_vz = float(msg.vel_z)
        self._pos_ok = bool(msg.xy_valid and msg.z_valid)

    def _on_formation_command(self, msg: FormationCommand) -> None:
        # Atamadaki komşular için dinamik abonelik (üye ekleme/çıkarma).
        self._ensure_neighbor_subs(msg.agent_ids)

    def _on_neighbor(self, nid: int, msg: NeighborInfo) -> None:
        self._neighbors[nid] = msg
        self._neighbor_rx[nid] = self.get_clock().now().nanoseconds * 1e-9

    # ---------- Komşu süzme ----------
    def _gather_obstacles(self, now: float) -> list[NeighborObs]:
        """Geçerli komşulardan CA girdisi (NeighborObs) listesi üretir.

        Göreli konum + göreli HIZ taşır (kapanma-hızı kapısı için zorunlu).
        """
        obs: list[NeighborObs] = []
        for nid, info in self._neighbors.items():
            # Link / yaş kontrolü
            if not info.link_active:
                self._n_skip_stale += 1
                continue
            if info.data_age_ms > self._neighbor_stale_ms:
                self._n_skip_stale += 1
                continue
            rx = self._neighbor_rx.get(nid, 0.0)
            if now - rx > self._neighbor_rx_stale_s:
                self._n_skip_stale += 1
                continue
            # State kontrolü (kontrat m.8)
            if info.neighbor_state in _AVOIDANCE_DISI_STATELER:
                self._n_skip_state += 1
                continue
            obs.append(NeighborObs(
                rel_x=float(info.relative_x),
                rel_y=float(info.relative_y),
                rel_z=float(info.relative_z),
                rel_vx=float(info.relative_vx),
                rel_vy=float(info.relative_vy),
                rel_vz=float(info.relative_vz),
                distance=float(info.distance_m),
            ))
        return obs

    # ---------- Ana döngü ----------
    def _tick(self) -> None:
        try:
            self._tick_inner()
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(
                f'_tick hata: {type(e).__name__}: {e}'
            )

    def _tick_inner(self) -> None:
        raw = self._raw
        if raw is None:
            return
        now = self.get_clock().now().nanoseconds * 1e-9
        # Ham setpoint eskiyse yayını kes → px4_interface kendi hold'una düşer.
        if now - self._raw_stamp > self._raw_timeout_s:
            return

        # --- Bypass: yüksek öncelikli / güvenlik setpoint'ine dokunma ---
        if (raw.priority >= AgentSetpoint.PRIORITY_FAILSAFE
                or raw.hold_position or raw.land_now or raw.rtl_now):
            self._relay(raw)
            return

        # --- Konum güvenilmezse CA yapma → ham geçir ---
        if not self._pos_ok:
            self._relay(raw)
            return

        # --- ALTITUDE GATE: kalkış/iniş fazında CA pasif ---
        # İrtifa (=−cur_z) gate altındaysa drone tırmanıyor/alçalıyor → yatay
        # kaçış dikey manevrayı bozmasın diye passthrough.
        if self._altitude_gate_m > 0.0 and (-self._cur_z) < self._altitude_gate_m:
            self._n_gate_alt += 1
            self._relay(raw)
            return

        obstacles = self._gather_obstacles(now)

        # --- Hız filtresi: v_form + Σ(F_rep + F_tan), clamp, r_min projeksiyon ---
        # Formasyon hızı (SVT+damp+rel+vff paketi) ham setpoint'in HIZ alanlarındadır.
        base = (
            (float(raw.vx), float(raw.vy), float(raw.vz))
            if raw.velocity_valid else (0.0, 0.0, 0.0)
        )
        v_cmd, risk = self._ca.compute(base, obstacles)

        if not risk:
            # CA uyuyor: ham hız setpoint'ini aynen geçir (formasyon kalitesi korunur).
            # ca_core.compute passthrough'da slew'i zaten resetledi.
            self._relay(raw, reset_core=False)
            return

        # --- Kaçış setpoint'i: SADECE hız (position_valid=False) ---
        # raw'ı deepcopy'le → heading/tolerans/yaw vb. korunur, yalnızca hız ezilir.
        # Pozisyon ÜRETMEYİZ: pozisyon kontrolü SVT'de (hız-tabanlı tek kontrolcü).
        out = copy.deepcopy(raw)
        out.stamp = self.get_clock().now().to_msg()
        out.sequence_num = self._sequence_num
        self._sequence_num += 1
        out.source = AgentSetpoint.SOURCE_COLLISION_AVOIDANCE
        out.priority = AgentSetpoint.PRIORITY_COLLISION_AVOIDANCE
        out.position_valid = False
        out.vx = float(v_cmd[0])
        out.vy = float(v_cmd[1])
        out.vz = float(v_cmd[2])
        out.velocity_valid = True
        out.acceleration_valid = False
        out.max_speed_mps = self._v_max_mps
        out.source_module = 'collision_avoidance'

        self._setpoint_pub.publish(out)
        self._n_avoid += 1

        # Aktif kaçışı seyrek logla (flood değil).
        if now - self._last_active_log > 1.0:
            self.get_logger().warn(
                f'CA kaçış aktif: v=({v_cmd[0]:.2f},{v_cmd[1]:.2f},'
                f'{v_cmd[2]:.2f}) m/s, {len(obstacles)} komşu etkide',
            )
            self._last_active_log = now

    def _relay(self, raw: AgentSetpoint, reset_core: bool = True) -> None:
        """Ham setpoint'i değiştirmeden yeniden yayınlar (risk yok/bypass).

        ca_core slew başlangıcını gerçek hıza eşitler: kaçış devreye girdiğinde
        ivme sınırı drone'un mevcut hızından yumuşak başlasın (sıfırdan değil)
        → geçişte gecikme/sıçrama olmaz. reset_core=False ise compute() zaten
        passthrough'da resetledi (çift reset gereksiz).
        """
        if reset_core:
            self._ca.reset((self._cur_vx, self._cur_vy, self._cur_vz))
        self._n_passthrough += 1
        self._setpoint_pub.publish(raw)

    def _diag_tick(self) -> None:
        try:
            self.get_logger().info(
                f'tanı: passthrough={self._n_passthrough} '
                f'avoid={self._n_avoid} '
                f'gate_alt={self._n_gate_alt} '
                f'skip_state={self._n_skip_state} '
                f'skip_stale={self._n_skip_stale} '
                f'komşu_sub={len(self._neighbor_subs)}'
            )
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(f'tanı log hata: {e}')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CollisionAvoidanceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
