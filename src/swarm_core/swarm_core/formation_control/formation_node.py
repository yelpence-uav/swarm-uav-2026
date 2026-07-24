# Copyright 2026 Yelpence
"""Dagitik formasyon kontrol node'u."""

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from std_msgs.msg import UInt8

from swarm_interfaces.msg import (
    AgentSetpoint,
    AgentStatus,
    FormationCommand,
    NeighborInfo,
    SwarmOrigin,
)

from .formation_geometry import (
    FORMATION_CIZGI,
    FORMATION_OKBASI,
    FORMATION_V,
    compute_slot_offsets,
    hungarian_assignment,
    latlon_to_ned,
    rotate_offset,
)

# mission_fsm aktif QR alt-adımını /swarm/public/mission/qr_step üzerinde
# QrTaskStep değeriyle (UInt8) yayınlar. MANEUVER adımında formasyon çıkışı
# susturulur; o an /raw'a yalnız maneuver_executor yazsın (tek yazıcı → drone
# titremez). Manevra sonrası eğik poz, lider'in FormationCommand'a gömdüğü
# eğik ofsetlerle korunur; bu node onları normal şekilde uygular.
_QR_STEP_MANEUVER = 2

# Bu drone formasyondan ayrılmış/iniş/rejoin durumundayken formation_control
# susar; o an precision_landing veya agent_fsm/PX4 sürücüdür. Aynı /raw'a iki
# yazıcı olmasın (ayrılan dronda formasyon-precision çakışması önlenir).
_MUTE_STATES = frozenset({
    AgentStatus.STATE_DETACHED,
    AgentStatus.STATE_PRECISION_LANDING,
    AgentStatus.STATE_WAITING_REJOIN,
    AgentStatus.STATE_REJOINING,
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

_ORIGIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


class FormationControlNode(Node):
    """Tek drone icin dagitik formasyon setpoint hesaplayicisi."""

    def __init__(self) -> None:
        super().__init__('formation_control')

        self._declare_params()

        self._current_formation = None
        self._sequence_num = 0

        self._current_pos_x = 0.0
        self._current_pos_y = 0.0
        self._current_pos_z = 0.0
        self._current_vel_x = 0.0
        self._current_vel_y = 0.0
        self._current_vel_z = 0.0
        self._pos_valid = False
        self._oscillating = False

        self._origin_synced = False
        self._estimator_ok = False
        self._xy_valid = False
        self._z_valid = False

        self._current_lat = 0.0
        self._current_lon = 0.0
        self._gps_valid = False

        self._origin_lat = None
        self._origin_lon = None

        self._ramp_x = None
        self._ramp_y = None
        self._ramp_z = None
        self._last_publish_time = None

        self._neighbors = {}
        self._neighbor_rx_time = {}
        self._neighbor_subs = {}

        self._setup_publishers()
        self._setup_subscribers()

        self._timer = self.create_timer(
            1.0 / self._publish_rate_hz,
            self._publish_setpoint,
        )

        self.get_logger().info(
            f'FormationControlNode baslatildi: agent_id={self._agent_id}'
        )

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanimlar ve sınıf degiskenlerine okur."""
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('position_tolerance_m', 0.5)
        self.declare_parameter('heading_tolerance_deg', 5.0)
        self.declare_parameter('max_speed_mps', 3.0)
        self.declare_parameter('svt_k', 0.8)
        self.declare_parameter('svt_threshold_m', 0.1)
        self.declare_parameter('svt_k_z', 2.0)
        self.declare_parameter('svt_threshold_z_m', 0.05)
        self.declare_parameter('svt_damp', 0.35)
        # Slot rampasi: hedef slotun saniyede kac metre kayabilecegi.
        # 0.0 => ramp_rate = max_speed, yani rampa SEYIR HIZINDAN TURETILIR.
        #
        # Eskiden sabit 1.0 idi. max_speed 3.0 olmasina ragmen slot 1.0 m/s'den
        # hizli kayamiyordu ve v_ff de rampanin hizindan turedigi icin drona
        # giden komut 1.0'da tavan yapiyordu. Merkez ise (path_planner, ayri
        # dosya, ayri parametre) 3.0 ile kosuyordu; iki sayi birbirinden
        # habersizdi. Olculdu: merkez 3.00 m/s iken komut 1.05, dron 1.07 m/s
        # -> aradaki ~2 m/s her saniye acige eklenip suru merkezin gerisinde
        # kaliyordu (bacak basina 5 -> 12.5 -> 20.4 m).
        #
        # Turetme sayesinde max_speed 2/3/4 ne verilirse verilsin merkez ile
        # dron ayni tavani paylasir, aralarinda kalici fark olusmaz.
        # Ani slot sicramalarinin yumusatilmasi artik path_planner'daki ivme
        # rampasi (linear_trajectory.accel_time_s) tarafindan saglaniyor.
        self.declare_parameter('target_ramp_mps', 0.0)
        # A7 — göreli (komşu tabanlı) formasyon koruma. VARSAYILAN KAPALI:
        # komşu konumu NeighborInfo'dan gelir ve 0.5 sn'ye kadar bayat olabilir;
        # bayat veriyle düzeltme yalpalatıp dronları birbirine sokuyordu
        # (ölçüldü: relative açıkken en yakın mesafe 0.28 m — near-collision;
        # kapatınca 0 ihlal, min 2.68 m). SITL'de GPS temiz olduğu için mutlak
        # SVT tek başına yeterli. Gerçek sahada GPS gürültüsünde relative'e
        # ihtiyaç olursa: -p rel_enable:=true ile açılır (ama bayatlık sorunu
        # da giderilmeli).
        self.declare_parameter('rel_enable', False)
        self.declare_parameter('rel_k', 0.2)
        self.declare_parameter('rel_threshold_m', 0.2)
        self.declare_parameter('rel_stale_s', 0.5)
        self.declare_parameter('keeping_enter_m', 1.2)
        self.declare_parameter('keeping_exit_m', 1.8)
        self.declare_parameter('vff_lpf_alpha', 0.3)
        # v_ff bayatlık süresi: bu kadar süredir yeni FormationCommand
        # gelmediyse merkez artık HAREKET ETMİYOR demektir → v_ff sıfırlanır.
        # Yoksa son komuttaki hız donup kalır ve her tick'te komuta eklenir;
        # SVT ile dengelenip kalıcı sapma üretir (hata = v_ff / svt_k).
        # 1.5 s: path_planner rampasında komutlar ~1.0-1.2 s arayla gelir;
        # eşik bunun üstünde olmalı ki rampa boyunca v_ff yaşasın, rampa
        # bitince (komut kesilince) sıfırlansın.
        self.declare_parameter('vff_hold_s', 1.5)
        # Ok Başı/V kanat açısı — yerel (dağıtık) atama geometrisi lider ile
        # birebir aynı olsun diye orchestrator ile aynı default (45°).
        self.declare_parameter('wing_alpha_deg', 45.0)

        self._agent_id = int(self.get_parameter('agent_id').value)
        self._publish_rate_hz = float(
            self.get_parameter('publish_rate_hz').value
        )
        self._position_tolerance_m = float(
            self.get_parameter('position_tolerance_m').value
        )
        self._heading_tolerance_deg = float(
            self.get_parameter('heading_tolerance_deg').value
        )
        self._max_speed_mps = float(
            self.get_parameter('max_speed_mps').value
        )
        self._svt_k = float(self.get_parameter('svt_k').value)
        self._svt_threshold_m = float(
            self.get_parameter('svt_threshold_m').value
        )
        self._svt_k_z = float(self.get_parameter('svt_k_z').value)
        self._svt_threshold_z_m = float(
            self.get_parameter('svt_threshold_z_m').value
        )
        self._svt_damp = float(self.get_parameter('svt_damp').value)
        self._target_ramp_mps = float(
            self.get_parameter('target_ramp_mps').value
        )
        self._rel_enable = bool(
            self.get_parameter('rel_enable').value
        )
        self._rel_k = float(self.get_parameter('rel_k').value)
        self._rel_threshold_m = float(
            self.get_parameter('rel_threshold_m').value
        )
        self._rel_stale_s = float(
            self.get_parameter('rel_stale_s').value
        )
        self._keeping_enter_m = float(
            self.get_parameter('keeping_enter_m').value
        )
        self._keeping_exit_m = float(
            self.get_parameter('keeping_exit_m').value
        )
        self._vff_hold_s: float = float(
            self.get_parameter('vff_hold_s').value
        )
        self._vff_lpf_alpha: float = float(
            self.get_parameter('vff_lpf_alpha').value
        )
        # C MODU (SAF HIZ-TABANLI): position_valid=False → pozisyon kontrolü
        # TÜMÜYLE bizde (SVT tek feedback, PX4 ile çakışmaz). v_cmd = v_svt +
        # v_damp + v_rel + v_ff. in_formation gate KALDIRILDI — SVT hem form-up
        # hem seyirde çalışır, tek mod. v_ff LPF durumu:
        self._vff_x: float = 0.0
        self._vff_y: float = 0.0
        self._vff_z: float = 0.0
        # v_ff = d(SHARED slot)/dt — KOMUT callback'inde (2Hz) hesaplanır,
        # publish loop'ta (50Hz) DEĞİL. 50Hz'de sabit-merkezi türevlemek
        # testere dişi (impuls treni) üretir → sallanma. Komut frekansında:
        # merkez 0.5s'de 0.5m kayar → v_ff=1.0 düz.
        self._prev_slot_x: float | None = None
        self._prev_slot_y: float | None = None
        self._prev_slot_z: float | None = None
        self._prev_cmd_time: float | None = None
        # v_ff artık 2Hz komut türevinden değil, 50Hz ramp'ın hızından gelir
        # (ramp trajektöriyi sürekli interpole eder → basamaklı değil). Ramp'ın
        # bir önceki konumu, hızını 50Hz'de türevlemek için tutulur.
        self._prev_ramp_x: float | None = None
        self._prev_ramp_y: float | None = None
        self._prev_ramp_z: float | None = None
        # Aktif QR alt-adımı (mission_fsm yayınlar); MANEUVER'da çıkış susar.
        self._qr_step: int = 0
        # Bu drone'un kendi FSM durumu; ayrılma/iniş durumlarında çıkış susar.
        self._agent_state: int = 0

        # DAĞITIK ATAMA (çıpalı): her dron kendi slotunu peer konumlarından
        # yerel hesaplar; liderin komuttaki atamasıyla uyuşursa yereli kullanır
        # (dağıtık), yoksa lidere düşer (güvenli, çakışma yok). Sonuç
        # formation_type'a freeze → reshape'te bir kez, aynı tipte tekrar yok
        # (rijit diziliş korunur). Kanat açısı lider ile aynı olmalı.
        self._wing_alpha_rad: float = math.radians(
            float(self.get_parameter('wing_alpha_deg').value)
        )
        self._local_offsets: dict[int, tuple[float, float, float]] | None = None
        self._local_offsets_type: int | None = None

    def _setup_publishers(self) -> None:
        """Setpoint publisher'ini olusturur."""
        self._setpoint_pub = self.create_publisher(
            AgentSetpoint,
            f'/drone_{self._agent_id}/control/setpoint/raw',
            _BEST_EFFORT_QOS,
        )

    def _setup_subscribers(self) -> None:
        """Topic aboneliklerini olusturur."""
        self.create_subscription(
            FormationCommand,
            '/swarm/public/formation/target',
            self._on_formation_command,
            _RELIABLE_QOS,
        )
        self.create_subscription(
            AgentStatus,
            f'/swarm/agent/drone{self._agent_id}/telemetry',
            self._on_agent_status,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            SwarmOrigin,
            '/swarm/public/origin',
            self._on_swarm_origin,
            _ORIGIN_QOS,
        )
        self.create_subscription(
            UInt8,
            '/swarm/public/mission/qr_step',
            self._on_qr_step,
            _RELIABLE_QOS,
        )

    def _ensure_neighbor_subs(self, agent_ids) -> None:
        """Atamadaki her komsu icin abonelik kurar."""
        if not self._rel_enable:
            return
        for nid in agent_ids:
            nid = int(nid)
            if nid == self._agent_id or nid in self._neighbor_subs:
                continue
            topic = (
                f'/swarm/agent/drone{self._agent_id}'
                f'/neighbor/drone{nid}'
            )
            self._neighbor_subs[nid] = self.create_subscription(
                NeighborInfo,
                topic,
                lambda m, n=nid: self._on_neighbor(n, m),
                _BEST_EFFORT_QOS,
            )
            self.get_logger().info(
                f'NeighborInfo aboneligi kuruldu: drone{nid}'
            )

    def _on_formation_command(self, msg: FormationCommand) -> None:
        """Gelen FormationCommand'ı saklar."""
        if int(self._agent_id) not in [int(a) for a in msg.agent_ids]:
            return

        prev = self._current_formation
        self._current_formation = msg
        type_changed = (
            prev is None or prev.formation_type != msg.formation_type
        )
        if type_changed:
            self._ramp_x = None
            self._ramp_y = None
            self._ramp_z = None

        # v_ff artık burada (2Hz komut türevi) DEĞİL, publish loop'ta ramp'ın
        # 50Hz hızından hesaplanıyor → basamaklı 2Hz zıplama yok, sürekli
        # feedforward. Burada yalnızca komut zaman damgası tutulur: akış
        # kesilince v_ff'i sıfırlayan bayatlık kapısı (publish loop'ta) bunu
        # kullanır. Ramp, tip değişiminde de hedefe pürüzsüz kaydığından
        # eski slot-türevi spike-engeli gerekmez.
        self._prev_cmd_time = self.get_clock().now().nanoseconds * 1e-9

        self._ensure_neighbor_subs(msg.agent_ids)

        # DAĞITIK ATAMA (çıpalı): reshape'te (tip değişince) kendi atamamı peer
        # konumlarından yerel hesapla, liderin gömdüğüyle karşılaştır. Aynıysa
        # yereli kullan (dağıtık → puan); farklı/eksikse lidere düş (güvenli →
        # çakışma yok). Sonuç formation_type'a freeze: aynı tipte yeniden
        # hesaplama yok, rijit diziliş korunur. Peer/GPS hazır değilse bu tip
        # boyunca her komutta tekrar denenir (hazır olunca dondurulur).
        if type_changed:
            self._local_offsets = None
            self._local_offsets_type = None
        if (self._local_offsets is None
                and int(msg.formation_type) in (
                    FORMATION_OKBASI, FORMATION_V, FORMATION_CIZGI)):
            now_s = self.get_clock().now().nanoseconds * 1e-9
            ids = [int(a) for a in msg.agent_ids]
            peer = self._peer_positions(ids, now_s)
            leader = self._leader_offsets(msg)
            local = (
                self._compute_local_offsets(msg, peer)
                if peer is not None else None
            )
            if (local is not None and leader is not None
                    and self._assignments_match(local, leader)):
                self._local_offsets = local
                self._local_offsets_type = int(msg.formation_type)
                mine = local.get(self._agent_id)
                tablo = ' '.join(
                    f'a{a}->({o[0]:+.1f},{o[1]:+.1f})'
                    for a, o in sorted(local.items())
                )
                self.get_logger().info(
                    f'dagitik atama: yerel hesap lider ile UYUSTU '
                    f'-> yerel kullaniliyor | BENIM SLOT='
                    f'({mine[0]:+.2f},{mine[1]:+.2f},{mine[2]:+.2f}) '
                    f'| TAM ATAMA: {tablo}'
                )
            elif local is not None and leader is not None:
                y = ' '.join(
                    f'a{a}->({o[0]:+.1f},{o[1]:+.1f})'
                    for a, o in sorted(local.items())
                )
                ldr = ' '.join(
                    f'a{a}->({o[0]:+.1f},{o[1]:+.1f})'
                    for a, o in sorted(leader.items())
                )
                self.get_logger().warn(
                    f'dagitik atama: yerel != lider -> guvenlik icin lider '
                    f'kullaniliyor | YEREL: {y} | LIDER: {ldr}'
                )

        self.get_logger().info(
            f'FormationCommand alindi: type={msg.formation_type}, '
            f'heading={msg.heading_deg:.1f}deg, '
            f'center=({msg.center_x:.1f}, {msg.center_y:.1f}, '
            f'{msg.center_z:.1f}), atama={list(msg.agent_ids)}',
            throttle_duration_sec=1.0,
        )

    def _on_agent_status(self, msg: AgentStatus) -> None:
        """Drone durumunu gunceller."""
        self._current_pos_x = float(msg.pos_x)
        self._current_pos_y = float(msg.pos_y)
        self._current_pos_z = float(msg.pos_z)
        self._current_vel_x = float(msg.vel_x)
        self._current_vel_y = float(msg.vel_y)
        self._current_vel_z = float(msg.vel_z)
        self._pos_valid = True
        self._oscillating = msg.oscillation_detected

        self._agent_state = int(msg.state)

        self._origin_synced = bool(msg.origin_synced)
        self._estimator_ok = bool(msg.estimator_ok)
        self._xy_valid = bool(msg.xy_valid)
        self._z_valid = bool(msg.z_valid)

        if msg.lat_deg != 0.0 or msg.lon_deg != 0.0:
            self._current_lat = float(msg.lat_deg)
            self._current_lon = float(msg.lon_deg)
            self._gps_valid = True

    def _on_neighbor(self, nid: int, msg: NeighborInfo) -> None:
        """Komsu verisini kaydeder."""
        self._neighbors[nid] = msg
        self._neighbor_rx_time[nid] = (
            self.get_clock().now().nanoseconds * 1e-9
        )

    def _on_swarm_origin(self, msg: SwarmOrigin) -> None:
        """Referans baslangic noktasini kaydeder."""
        if not msg.valid:
            return
        self._origin_lat = float(msg.origin_lat_deg)
        self._origin_lon = float(msg.origin_lon_deg)

    def _shared_to_local(
        self, shared_x: float, shared_y: float
    ) -> tuple[float, float]:
        """Shared koordinati local NED frame'e cevirir."""
        if self._origin_lat is None or not self._gps_valid:
            return shared_x, shared_y

        cur_n, cur_e = latlon_to_ned(
            self._current_lat, self._current_lon,
            self._origin_lat, self._origin_lon,
        )
        return (
            shared_x - cur_n + self._current_pos_x,
            shared_y - cur_e + self._current_pos_y,
        )

    def _compute_velocity(
        self,
        target_x: float,
        target_y: float,
        target_z: float,
        max_speed: float,
    ) -> tuple[float, float, float]:
        """SVT duzeltme hizini hesaplar."""
        vx = 0.0
        vy = 0.0
        vz = 0.0

        # SVT: konum hatasıyla orantılı yay kuvveti (çıktı HIZ — C modu aynen).
        # Sert deadband (hata > threshold ise çek, altında SIFIR) bir aç/kapa
        # süreksizliğiydi ve limit-cycle üretiyordu: dron threshold sınırında
        # çekme açılıp kapanınca titriyordu (genlik ≈ threshold). Yerine C¹
        # sürekli smoothstep zarfı: merkezde çekme pürüzsüzce sıfıra iner
        # (gürültü kovalamaz) ama süreksizlik yok → limit-cycle yok.
        if self._pos_valid:
            ex = self._current_pos_x - target_x
            ey = self._current_pos_y - target_y
            dist_xy = math.sqrt(ex * ex + ey * ey)
            thr = self._svt_threshold_m
            t = dist_xy / thr if thr > 1e-9 else 2.0
            s_xy = 1.0 if t >= 1.0 else t * t * (3.0 - 2.0 * t)
            vx -= self._svt_k * ex * s_xy
            vy -= self._svt_k * ey * s_xy

            # Z SVT: anlık yükseklik düzeltmesi (aynı yumuşak-zone)
            ez = self._current_pos_z - target_z
            thrz = self._svt_threshold_z_m
            tz = abs(ez) / thrz if thrz > 1e-9 else 2.0
            s_z = 1.0 if tz >= 1.0 else tz * tz * (3.0 - 2.0 * tz)
            vz -= self._svt_k_z * ez * s_z

            vx -= self._svt_damp * self._current_vel_x
            vy -= self._svt_damp * self._current_vel_y
            vz -= self._svt_damp * self._current_vel_z

        return self._clamp_speed(vx, vy, vz, max_speed)

    def _compute_relative_correction(
        self,
        msg: FormationCommand,
        my_idx: int,
        heading_rad: float,
        now: float,
    ) -> tuple[float, float, float]:
        """Komsulara gore goreli duzeltme hizini hesaplar."""
        if not self._rel_enable:
            return 0.0, 0.0, 0.0

        agent_ids = list(msg.agent_ids)
        my = self._slot_offset(msg, self._agent_id)
        if my is None:
            return 0.0, 0.0, 0.0
        my_ox, my_oy, my_oz = my

        sum_ex = 0.0
        sum_ey = 0.0
        sum_ez = 0.0
        count = 0
        for nid in agent_ids:
            nid = int(nid)
            if nid == self._agent_id:
                continue
            info = self._neighbors.get(nid)
            if info is None or not info.link_active:
                continue
            rx = self._neighbor_rx_time.get(nid, 0.0)
            if now - rx > self._rel_stale_s:
                continue
            no = self._slot_offset(msg, nid)
            if no is None:
                continue
            # İstenen göreli (komşu - ben), body frame → shared NED
            dbx = no[0] - my_ox
            dby = no[1] - my_oy
            dbz = no[2] - my_oz
            des_x, des_y = rotate_offset(dbx, dby, heading_rad)
            des_z = dbz

            sum_ex += float(info.relative_x) - des_x
            sum_ey += float(info.relative_y) - des_y
            sum_ez += float(info.relative_z) - des_z
            count += 1

        if count == 0:
            return 0.0, 0.0, 0.0

        mean_ex = sum_ex / count
        mean_ey = sum_ey / count
        mean_ez = sum_ez / count

        horiz = math.sqrt(mean_ex * mean_ex + mean_ey * mean_ey)
        vx = self._rel_k * mean_ex if horiz > self._rel_threshold_m else 0.0
        vy = self._rel_k * mean_ey if horiz > self._rel_threshold_m else 0.0
        if abs(mean_ez) > self._rel_threshold_m:
            vz = self._rel_k * mean_ez
        else:
            vz = 0.0
        return vx, vy, vz

    @staticmethod
    def _clamp_speed(
        vx: float, vy: float, vz: float, max_speed: float
    ) -> tuple[float, float, float]:
        """Hiz vektorunu max_speed degerine kirpar."""
        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        if speed > max_speed and speed > 0.0:
            scale = max_speed / speed
            return vx * scale, vy * scale, vz * scale
        return vx, vy, vz

    def _resolve_center(
        self, msg: FormationCommand
    ) -> tuple[float, float, float]:
        """Komutla gelen merkezi doner."""
        return (
            float(msg.center_x),
            float(msg.center_y),
            float(msg.center_z),
        )

    # --- Dağıtık atama (çıpalı) ----------------------------------------------

    def _peer_positions(
        self,
        agent_ids: list[int],
        now: float,
    ) -> dict[int, tuple[float, float, float]] | None:
        """Tüm sürünün shared-NED konumunu SADECE peer veriden kurar."""
        origin_lat = getattr(self, '_origin_lat', None)
        origin_lon = getattr(self, '_origin_lon', None)
        if (not getattr(self, '_gps_valid', False)
                or origin_lat is None or origin_lon is None):
            return None
        my_n, my_e = latlon_to_ned(
            self._current_lat, self._current_lon, origin_lat, origin_lon
        )
        pos: dict[int, tuple[float, float, float]] = {}
        for a in agent_ids:
            a = int(a)
            if a == self._agent_id:
                pos[a] = (my_n, my_e, 0.0)
                continue
            info = self._neighbors.get(a)
            if info is None or not info.link_active:
                return None
            if now - self._neighbor_rx_time.get(a, 0.0) > self._rel_stale_s:
                return None
            pos[a] = (
                my_n + float(info.relative_x),
                my_e + float(info.relative_y),
                0.0,
            )
        return pos

    def _compute_local_offsets(
        self,
        msg: FormationCommand,
        positions: dict[int, tuple[float, float, float]],
    ) -> dict[int, tuple[float, float, float]] | None:
        """Slot atamasını yerel olarak hesaplar (dağıtık atama)."""
        ftype = int(msg.formation_type)
        if ftype not in (FORMATION_OKBASI, FORMATION_V, FORMATION_CIZGI):
            return None
        ids = [int(a) for a in msg.agent_ids]
        n = len(ids)
        if n == 0:
            return None
        try:
            slots = compute_slot_offsets(
                ftype, n, float(msg.spacing_m), self._wing_alpha_rad
            )
        except ValueError:
            return None
        cx, cy, _cz = self._resolve_center(msg)
        heading_rad = math.radians(msg.heading_deg)
        world = []
        for (ox, oy, _oz) in slots:
            wx, wy = rotate_offset(ox, oy, heading_rad)
            world.append((cx + wx, cy + wy))
        cost = []
        for a in ids:
            px, py, _pz = positions[a]
            cost.append([math.hypot(px - sx, py - sy) for (sx, sy) in world])
        assignment = hungarian_assignment(cost)
        return {
            ids[i]: (
                float(slots[assignment[i]][0]),
                float(slots[assignment[i]][1]),
                float(slots[assignment[i]][2]),
            )
            for i in range(n)
        }

    def _leader_offsets(
        self,
        msg: FormationCommand,
    ) -> dict[int, tuple[float, float, float]] | None:
        """Liderin komuta gömdüğü atamayı sözlük olarak döner (çıpa/fallback)."""
        ids = [int(a) for a in msg.agent_ids]
        if (len(msg.offset_x) < len(ids) or len(msg.offset_y) < len(ids)
                or len(msg.offset_z) < len(ids)):
            return None
        return {
            ids[i]: (
                float(msg.offset_x[i]),
                float(msg.offset_y[i]),
                float(msg.offset_z[i]),
            )
            for i in range(len(ids))
        }

    @staticmethod
    def _assignments_match(
        a: dict[int, tuple[float, float, float]],
        b: dict[int, tuple[float, float, float]],
        tol: float = 0.05,
    ) -> bool:
        """İki atama (id→ofset) tol metre içinde birebir aynı mı."""
        if set(a.keys()) != set(b.keys()):
            return False
        for k in a:
            if (abs(a[k][0] - b[k][0]) > tol
                    or abs(a[k][1] - b[k][1]) > tol
                    or abs(a[k][2] - b[k][2]) > tol):
                return False
        return True

    def _slot_offset(
        self,
        msg: FormationCommand,
        agent_id: int,
    ) -> tuple[float, float, float] | None:
        """Ajanın efektif slot ofsetini verir (yerel atama varsa ondan)."""
        agent_id = int(agent_id)
        if self._local_offsets is not None and agent_id in self._local_offsets:
            return self._local_offsets[agent_id]
        ids = [int(a) for a in msg.agent_ids]
        if agent_id in ids:
            i = ids.index(agent_id)
            if (i < len(msg.offset_x) and i < len(msg.offset_y)
                    and i < len(msg.offset_z)):
                return (
                    float(msg.offset_x[i]),
                    float(msg.offset_y[i]),
                    float(msg.offset_z[i]),
                )
        return None

    def _on_qr_step(self, msg: UInt8) -> None:
        """mission_fsm'in yayınladığı aktif QR alt-adımını saklar."""
        self._qr_step = int(msg.data)

    def _publish_setpoint(self) -> None:
        """Periyodik setpoint hesaplar ve AgentSetpoint yayınlar."""
        # MANEUVER adımında formasyon susar → /raw'a yalnız maneuver_executor
        # yazar, iki yazıcı çakışması önlenir. Eğik poz sonradan eğik ofsetle
        # korunduğu için bu susma yalnızca aktif manevra hareketi süresincedir.
        if self._qr_step == _QR_STEP_MANEUVER:
            return

        # Bu drone ayrılmış/iniş/rejoin durumundaysa formation sürücü değildir
        # (precision_landing veya agent_fsm/PX4). /raw'a yazma.
        if self._agent_state in _MUTE_STATES:
            return

        msg = self._current_formation
        if msg is None:
            return

        agent_ids = list(msg.agent_ids)
        if not agent_ids or self._agent_id not in agent_ids:
            return

        if not self._origin_synced:
            self.get_logger().warn(
                'origin senkronlanmadi; setpoint bekletiliyor',
                throttle_duration_sec=2.0,
            )
            return

        if not (self._xy_valid and self._z_valid):
            self.get_logger().warn(
                'konum tahmini gecersiz; setpoint bekletiliyor',
                throttle_duration_sec=2.0,
            )
            return

        idx = agent_ids.index(self._agent_id)
        off = self._slot_offset(msg, self._agent_id)
        if off is None:
            self.get_logger().warn(
                'slot ofseti yok (yerel/komut); setpoint atlandi',
                throttle_duration_sec=2.0,
            )
            return

        center_x, center_y, center_z = self._resolve_center(msg)
        heading_rad = math.radians(msg.heading_deg)

        dx, dy = rotate_offset(off[0], off[1], heading_rad)
        x = center_x + dx
        y = center_y + dy
        z = center_z + off[2]

        x, y = self._shared_to_local(x, y)

        max_speed = (
            float(msg.max_speed_mps)
            if msg.max_speed_mps > 0.0
            else self._max_speed_mps
        )

        now = self.get_clock().now().nanoseconds * 1e-9
        dt = (
            (now - self._last_publish_time)
            if self._last_publish_time is not None
            else 0.0
        )
        self._last_publish_time = now
        ramp_rate = max_speed
        if self._target_ramp_mps > 0.0:
            ramp_rate = min(self._target_ramp_mps, max_speed)
        if self._ramp_x is None:
            self._ramp_x = self._current_pos_x if self._pos_valid else x
            self._ramp_y = self._current_pos_y if self._pos_valid else y
            self._ramp_z = self._current_pos_z if self._pos_valid else z

        if dt > 0.0 and ramp_rate > 0.0:
            max_step = ramp_rate * dt
            for attr, target in [
                ('_ramp_x', x), ('_ramp_y', y), ('_ramp_z', z)
            ]:
                cur = getattr(self, attr)
                diff = target - cur
                step = max(-max_step, min(max_step, diff))
                setattr(self, attr, cur + step)
        x, y, z = self._ramp_x, self._ramp_y, self._ramp_z

        # v_ff = ramp'ın 50Hz hızı (pürüzsüz feedforward). Ramp, komut hedefine
        # doğru her tick ilerler; slot'un aksine 50Hz'de SABİT DEĞİL, o yüzden
        # türevi testere dişi değil sürekli hız verir. Hedefe yaklaşınca adım
        # küçülür → v_ff pürüzsüzce 0'a iner (basamaklı 2Hz zıplama yok).
        if self._prev_ramp_x is None:
            self._prev_ramp_x, self._prev_ramp_y, self._prev_ramp_z = x, y, z
        elif dt > 1e-3:
            a = self._vff_lpf_alpha
            self._vff_x = (a * (x - self._prev_ramp_x) / dt
                           + (1.0 - a) * self._vff_x)
            self._vff_y = (a * (y - self._prev_ramp_y) / dt
                           + (1.0 - a) * self._vff_y)
            self._vff_z = (a * (z - self._prev_ramp_z) / dt
                           + (1.0 - a) * self._vff_z)
            self._prev_ramp_x, self._prev_ramp_y, self._prev_ramp_z = x, y, z

        # === HIZ KOMUTU (C MODU: SAF HIZ-TABANLI) =========================
        # v_cmd = v_svt + v_damp + v_rel + v_ff. Pozisyon kontrolü TÜMÜYLE
        # burada (SVT tek feedback) → position_valid=False, PX4 ile ÇAKIŞMAZ.
        # in_formation gate YOK: SVT form-up'ta büyük hata→büyük çekme, seyirde
        # küçük→ince koruma; tek mod. APF (CA node) bu hıza zincirde eklenir.
        #
        # SVT + damping: ramp'lı lokal slota çeker (-k·err) + sönümler (-b·v).
        svx, svy, svz = self._compute_velocity(x, y, z, max_speed)
        rvx, rvy, rvz = self._compute_relative_correction(
            msg, idx, heading_rad, now
        )
        # v_ff: merkez hızı feed-forward. KOMUT callback'inde (2Hz) hesaplandı
        # (self._vff_*); burada SADECE eklenir. Hız frame-bağımsız (sabit origin
        # offset'i türevde kaybolur) → shared'de hesaplanan lokalde de geçerli.
        #
        # BAYATLIK KAPISI: komut akışı kesilince merkez artık hareket etmiyordur;
        # v_ff sıfırlanmalı. Aksi halde son komuttaki hız DONAR ve her tick'te
        # eklenmeye devam eder → SVT ile dengelenip kalıcı sapma bırakır
        # (hata = v_ff / svt_k; ölçümde 3.0/0.8 ≈ 3.7 m). Emit-once komut
        # mimarisinde bu kaçınılmazdır, o yüzden burada kapatılır.
        if (self._prev_cmd_time is None
                or (now - self._prev_cmd_time) > self._vff_hold_s):
            self._vff_x = 0.0
            self._vff_y = 0.0
            self._vff_z = 0.0

        vx, vy, vz = self._clamp_speed(
            svx + rvx + self._vff_x,
            svy + rvy + self._vff_y,
            svz + rvz + self._vff_z, max_speed
        )
        out = self._build_setpoint_msg(
            msg, x, y, z, vx, vy, vz,
            position_valid=False,
            velocity_valid=True,
        )
        self._setpoint_pub.publish(out)

    def _build_setpoint_msg(
        self,
        cmd: FormationCommand,
        x: float,
        y: float,
        z: float,
        vx: float,
        vy: float,
        vz: float,
        velocity_valid: bool = False,
        position_valid: bool = True,
    ) -> AgentSetpoint:
        """Hesaplanan veriyle AgentSetpoint mesaji uretir."""
        out = AgentSetpoint()
        out.stamp = self.get_clock().now().to_msg()
        out.sequence_num = self._sequence_num
        self._sequence_num += 1

        out.agent_id = self._agent_id
        out.source = AgentSetpoint.SOURCE_FORMATION_CONTROL
        out.priority = AgentSetpoint.PRIORITY_FORMATION

        out.x = float(x)
        out.y = float(y)
        out.z = float(z)
        out.position_valid = position_valid

        out.vx = float(vx)
        out.vy = float(vy)
        out.vz = float(vz)
        out.velocity_valid = velocity_valid
        out.acceleration_valid = False

        out.heading_deg = float(cmd.heading_deg)
        out.heading_valid = True
        out.yaw_rate_valid = False

        out.hold_position = False
        out.land_now = False
        out.rtl_now = False

        out.position_tolerance_m = self._position_tolerance_m
        out.heading_tolerance_deg = self._heading_tolerance_deg

        if cmd.max_speed_mps > 0.0:
            out.max_speed_mps = float(cmd.max_speed_mps)
        else:
            out.max_speed_mps = self._max_speed_mps
        out.max_acc_mps2 = 0.0

        out.source_module = 'formation_control'
        return out


def main(args=None) -> None:
    rclpy.init(args=args)
    node = FormationControlNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:  # noqa: BLE001
            pass


if __name__ == '__main__':
    main()
