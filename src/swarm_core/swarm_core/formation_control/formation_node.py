"""Dağıtık formasyon kontrol node'u — her drone'da ayrı çalışır.

Slot ataması lider tarafından FormationCommand içinde (agent_ids +
offset_x/y/z) yayınlanır; bu node yalnızca KENDİ slotunu okur, shared NED
→ local NED dönüşümü yaparak AgentSetpoint üretir.

Merkezi SwarmState'e bağlı DEĞİLDİR: konumunu kendi telemetrisinden
(AgentStatus), ortak frame'i SwarmOrigin'den, atamasını lider komutundan
alır.

HİBRİT FORMASYON KORUMA (A7):
  - Mutlak terim (SVT): kendi slot koordinatına çeker → dünyaya çapa,
    kolektif sürüklenmeyi önler.
  - Göreli terim: komşuların gerçek konumunu (kinematic_fusion →
    NeighborInfo) okuyup istenen mesafeyi korur → GPS sapmasına ve lider
    kaybına dayanıklılık (komşuya bakarak formasyonu sıkı tutar).
  - Link kopuk/eski komşu hesaba katılmaz → otomatik mutlak-only fallback.
"""

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
    """Tek drone için dağıtık formasyon setpoint hesaplayıcısı.

    Slot ataması lider'in yaydığı FormationCommand içindedir
    (agent_ids + offset_x/y/z). Bu node kendi slotunu uygular ve komşulara
    göre (NeighborInfo) formasyonu sıkı tutar.
    """

    def __init__(self) -> None:
        """Node'u baslatir; parametreler, publisher ve subscriber'lar kurulur."""
        super().__init__('formation_control')

        self._declare_params()

        self._current_formation: FormationCommand | None = None
        self._sequence_num: int = 0

        self._current_pos_x: float = 0.0
        self._current_pos_y: float = 0.0
        self._current_pos_z: float = 0.0
        # OSİLASYON DÜZELTMESİ: tether sönümü için anlık hız durumu.
        self._current_vel_x: float = 0.0
        self._current_vel_y: float = 0.0
        self._current_vel_z: float = 0.0
        self._pos_valid: bool = False
        self._oscillating: bool = False

        # Kendi telemetrimizden gelen lokal çalışma izni bayrakları.
        self._origin_synced: bool = False
        self._estimator_ok: bool = False
        self._xy_valid: bool = False
        self._z_valid: bool = False

        self._current_lat: float = 0.0
        self._current_lon: float = 0.0
        self._gps_valid: bool = False

        self._origin_lat: float | None = None
        self._origin_lon: float | None = None

        # Hedef pozisyon ramp — ani sıçramayı yumuşatır
        self._ramp_x: float | None = None
        self._ramp_y: float | None = None
        self._ramp_z: float | None = None
        self._last_publish_time: float | None = None

        # A7 — komşu durumu (göreli koruma için)
        self._neighbors: dict[int, NeighborInfo] = {}
        self._neighbor_rx_time: dict[int, float] = {}
        self._neighbor_subs: dict[int, object] = {}

        self._setup_publishers()
        self._setup_subscribers()

        self._timer = self.create_timer(
            1.0 / self._publish_rate_hz,
            self._publish_setpoint,
        )

        self.get_logger().info(
            f'FormationControlNode baslatildi: '
            f'agent_id={self._agent_id}, '
            f'publish_rate={self._publish_rate_hz} Hz, '
            f'max_speed={self._max_speed_mps} m/s, '
            f'rel_enable={self._rel_enable}'
        )

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanımlar ve sınıf değişkenlerine okur."""
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('position_tolerance_m', 0.5)
        self.declare_parameter('heading_tolerance_deg', 5.0)
        self.declare_parameter('max_speed_mps', 3.0)
        # C MODU SVT kazançları: SVT artık TEK pozisyon kontrolcüsü (PX4 değil),
        # bu yüzden pozisyon-tabanlı moddan DAHA güçlü + DAHA sıkı deadband:
        #   svt_k 0.3→0.8 (güçlü çekme: 0.5m hata→0.4m/s toparlama)
        #   threshold 0.5→0.1 (sıkı: hover'da gevşek drift yok, sürü rijit)
        self.declare_parameter('svt_k', 0.8)
        self.declare_parameter('svt_threshold_m', 0.1)
        self.declare_parameter('svt_k_z', 2.0)
        self.declare_parameter('svt_threshold_z_m', 0.05)
        # SVT hız sönümü (overdamped): güçlü SVT yayının overshoot'unu söndürür.
        # b_s 0.2→0.35 (k artınca rezonansı bastırmak için sönüm de artar).
        self.declare_parameter('svt_damp', 0.35)
        self.declare_parameter('target_ramp_mps', 1.0)
        # A7 — göreli (komşu tabanlı) formasyon koruma
        self.declare_parameter('rel_enable', True)
        self.declare_parameter('rel_k', 0.2)
        self.declare_parameter('rel_threshold_m', 0.2)
        self.declare_parameter('rel_stale_s', 0.5)
        # C MODU (SAF HIZ-TABANLI): position_valid=False, velocity_valid=True.
        # in_formation gate KALDIRILDI; keeping_* artık KULLANILMIYOR (geri
        # uyumluluk için duruyor). v_ff LPF alfa:
        self.declare_parameter('keeping_enter_m', 1.2)
        self.declare_parameter('keeping_exit_m', 1.8)
        self.declare_parameter('vff_lpf_alpha', 0.3)

        self._agent_id: int = int(self.get_parameter('agent_id').value)
        self._publish_rate_hz: float = float(
            self.get_parameter('publish_rate_hz').value
        )
        self._position_tolerance_m: float = float(
            self.get_parameter('position_tolerance_m').value
        )
        self._heading_tolerance_deg: float = float(
            self.get_parameter('heading_tolerance_deg').value
        )
        self._max_speed_mps: float = float(
            self.get_parameter('max_speed_mps').value
        )
        self._svt_k: float = float(self.get_parameter('svt_k').value)
        self._svt_threshold_m: float = float(
            self.get_parameter('svt_threshold_m').value
        )
        self._svt_k_z: float = float(self.get_parameter('svt_k_z').value)
        self._svt_threshold_z_m: float = float(
            self.get_parameter('svt_threshold_z_m').value
        )
        # OSİLASYON DÜZELTMESİ: tether hız sönüm katsayısı.
        self._svt_damp: float = float(self.get_parameter('svt_damp').value)
        self._target_ramp_mps: float = float(
            self.get_parameter('target_ramp_mps').value
        )
        self._rel_enable: bool = bool(
            self.get_parameter('rel_enable').value
        )
        self._rel_k: float = float(self.get_parameter('rel_k').value)
        self._rel_threshold_m: float = float(
            self.get_parameter('rel_threshold_m').value
        )
        self._rel_stale_s: float = float(
            self.get_parameter('rel_stale_s').value
        )
        self._keeping_enter_m: float = float(
            self.get_parameter('keeping_enter_m').value
        )
        self._keeping_exit_m: float = float(
            self.get_parameter('keeping_exit_m').value
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
        # Aktif QR alt-adımı (mission_fsm yayınlar); MANEUVER'da çıkış susar.
        self._qr_step: int = 0
        # Bu drone'un kendi FSM durumu; ayrılma/iniş durumlarında çıkış susar.
        self._agent_state: int = 0

    def _setup_publishers(self) -> None:
        """Setpoint publisher'ini olusturur (AgentSetpoint)."""
        # NOT: çıkış artık doğrudan px4_interface'e değil, collision_avoidance
        # filtresine gider (APF son emniyet katmanı). collision_avoidance bu
        # ham hedefi komşulara göre harmanlayıp /control/setpoint'e yazar.
        self._setpoint_pub = self.create_publisher(
            AgentSetpoint,
            f'/drone_{self._agent_id}/control/setpoint/raw',
            _BEST_EFFORT_QOS,
        )

    def _setup_subscribers(self) -> None:
        """Topic aboneliklerini oluşturur.

        FormationCommand (lider'in atama+merkez komutu), kendi AgentStatus
        telemetrisi ve SwarmOrigin. NeighborInfo abonelikleri komut gelince
        dinamik kurulur (atamadaki komşulara göre). Merkezi SwarmState'e
        abone OLUNMAZ.
        """
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
        """Atamadaki her komşu için NeighborInfo aboneliğini kurar.

        Komşu kümesi komutla değişebilir (üye ekleme/çıkarma); yeni görülen
        her komşu için bir kez abonelik açılır. kinematic_fusion bu topic'i
        yayınlar: /swarm/agent/drone{self}/neighbor/drone{nid}.
        """
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
        """Gelen FormationCommand'ı saklar.

        Atama (agent_ids + offset_x/y/z) komutun içindedir. Lider sussa bile
        son komut elde kalır → drone formasyonu korumaya devam eder.
        """
        prev = self._current_formation
        self._current_formation = msg
        type_changed = prev is None or prev.formation_type != msg.formation_type
        # Formasyon tipi değişirse ramp'i sıfırla — yeni slota yumuşak geçiş
        if type_changed:
            self._ramp_x = None
            self._ramp_y = None
            self._ramp_z = None

        # === v_ff = d(SHARED slot)/dt — KOMUT FREKANSINDA (burada, ~2Hz) =====
        # slot_shared = merkez + R(heading)·offset. Tüm girdileri komuttan gelir,
        # yani slot SADECE burada değişir; 50Hz publish loop'ta sabittir. Türevi
        # burada almak DOĞRU dt'yi (komut periyodu ~0.5s) kullanır → düz hız.
        # Publish'te alsaydık dt=0.02s ile bölüp testere dişi üretirdik (sallanma).
        agent_ids = list(msg.agent_ids)
        if self._agent_id in agent_ids:
            idx = agent_ids.index(self._agent_id)
            if (idx < len(msg.offset_x) and idx < len(msg.offset_y)
                    and idx < len(msg.offset_z)):
                hr = math.radians(msg.heading_deg)
                odx, ody = rotate_offset(
                    msg.offset_x[idx], msg.offset_y[idx], hr
                )
                ssx = float(msg.center_x) + odx
                ssy = float(msg.center_y) + ody
                ssz = float(msg.center_z) + float(msg.offset_z[idx])
                now = self.get_clock().now().nanoseconds * 1e-9
                if (not type_changed and self._prev_slot_x is not None
                        and self._prev_cmd_time is not None):
                    dtc = now - self._prev_cmd_time
                    if dtc > 1e-3:
                        a = self._vff_lpf_alpha
                        self._vff_x = (a * (ssx - self._prev_slot_x) / dtc
                                       + (1.0 - a) * self._vff_x)
                        self._vff_y = (a * (ssy - self._prev_slot_y) / dtc
                                       + (1.0 - a) * self._vff_y)
                        self._vff_z = (a * (ssz - self._prev_slot_z) / dtc
                                       + (1.0 - a) * self._vff_z)
                else:
                    # tip değişimi / ilk komut → slot zıplar, v_ff spike'ını engelle
                    self._vff_x = self._vff_y = self._vff_z = 0.0
                self._prev_slot_x, self._prev_slot_y, self._prev_slot_z = (
                    ssx, ssy, ssz
                )
                self._prev_cmd_time = now

        # Atamadaki komşular için NeighborInfo abonelikleri (A7)
        self._ensure_neighbor_subs(msg.agent_ids)
        self.get_logger().info(
            f'FormationCommand alindi: type={msg.formation_type}, '
            f'heading={msg.heading_deg:.1f}deg, '
            f'center=({msg.center_x:.1f}, {msg.center_y:.1f}, '
            f'{msg.center_z:.1f}), atama={list(msg.agent_ids)}',
            throttle_duration_sec=1.0,
        )

    def _on_agent_status(self, msg: AgentStatus) -> None:
        """Bu drone'un pozisyon, GPS ve güvenlik flag'lerini günceller."""
        self._current_pos_x = float(msg.pos_x)
        self._current_pos_y = float(msg.pos_y)
        self._current_pos_z = float(msg.pos_z)
        # OSİLASYON DÜZELTMESİ: tether sönümü için hızı sakla.
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
        """Komşudan gelen NeighborInfo'yu ve alım zamanını saklar (A7)."""
        self._neighbors[nid] = msg
        self._neighbor_rx_time[nid] = (
            self.get_clock().now().nanoseconds * 1e-9
        )

    def _on_swarm_origin(self, msg: SwarmOrigin) -> None:
        """Ortak GPS referans noktasını saklar."""
        if not msg.valid:
            return
        self._origin_lat = float(msg.origin_lat_deg)
        self._origin_lon = float(msg.origin_lon_deg)

    def _shared_to_local(
        self,
        shared_x: float,
        shared_y: float,
    ) -> tuple[float, float]:
        """Shared NED → local NED dönüşümü.

        local = shared_hedef - shared_anlik + local_anlik
        Origin veya GPS yoksa dönüşüm uygulanmaz.
        """
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
        """Mutlak SVT (Soft Virtual Tethering) düzeltme hızını üretir.

        Kendi konumumuzu kendi slot koordinatına çeker (dünyaya çapa).
        Çıktı max_speed'e kırpılır.
        """
        vx = 0.0
        vy = 0.0
        vz = 0.0

        # SVT: threshold'u aşınca sabit kazançlı yay kuvveti uygula.
        # C MODU: SVT TEK pozisyon kontrolcüsü → oscillating'de ATLANMAZ
        # (atlanırsa pozisyon tutma çöker). Salınımı damping (-b·v) söndürür.
        if self._pos_valid:
            # XY
            ex = self._current_pos_x - target_x
            ey = self._current_pos_y - target_y
            dist_xy = math.sqrt(ex * ex + ey * ey)
            if dist_xy > self._svt_threshold_m:
                vx -= self._svt_k * ex
                vy -= self._svt_k * ey

            # Z SVT: anlık yükseklik düzeltmesi
            ez = self._current_pos_z - target_z
            if abs(ez) > self._svt_threshold_z_m:
                vz -= self._svt_k_z * ez

            # OSİLASYON DÜZELTMESİ (#5 tether rezonansı): hız sönümü.
            # F_tether = -k_s*displacement - b_s*velocity. Saf yay engel sonrası
            # eski formasyona dönerken overshoot/rezonans yapıyordu; hıza orantılı
            # sönüm overdamped davranış sağlar (slota yumuşak oturma, titremez).
            # Slota oturunca v≈0 → sönüm≈0 (steady-state'i bozmaz).
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
        """Komşulara göre formasyon koruma düzeltmesi (A7 göreli terim).

        Her aktif+taze komşu için: slot geometrisinden istenen göreli konum
        ile NeighborInfo'dan gelen gerçek göreli konum arasındaki hatayı
        kapatır. Link kopuk/eski komşu hesaba katılmaz → o komşu için
        otomatik mutlak-only fallback. Komşu yoksa (0,0,0) döner.
        """
        if not self._rel_enable:
            return 0.0, 0.0, 0.0

        agent_ids = list(msg.agent_ids)
        my_ox = float(msg.offset_x[my_idx])
        my_oy = float(msg.offset_y[my_idx])
        my_oz = float(msg.offset_z[my_idx])

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
            n_idx = agent_ids.index(nid)
            if (n_idx >= len(msg.offset_x) or n_idx >= len(msg.offset_y)
                    or n_idx >= len(msg.offset_z)):
                continue
            # İstenen göreli (komşu - ben), body frame → shared NED
            dbx = float(msg.offset_x[n_idx]) - my_ox
            dby = float(msg.offset_y[n_idx]) - my_oy
            dbz = float(msg.offset_z[n_idx]) - my_oz
            des_x, des_y = rotate_offset(dbx, dby, heading_rad)
            des_z = dbz
            # Gerçek göreli (NeighborInfo: komşu - ben, shared NED)
            sum_ex += float(info.relative_x) - des_x
            sum_ey += float(info.relative_y) - des_y
            sum_ez += float(info.relative_z) - des_z
            count += 1

        if count == 0:
            return 0.0, 0.0, 0.0

        mean_ex = sum_ex / count
        mean_ey = sum_ey / count
        mean_ez = sum_ez / count

        # Deadband: küçük hataya dokunma (gürültü/titreme önleme).
        # Hareket yönü hatayı kapatmaya doğru: v = rel_k * (gerçek - istenen).
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
        vx: float,
        vy: float,
        vz: float,
        max_speed: float,
    ) -> tuple[float, float, float]:
        """Hız vektörünü max_speed büyüklüğüne kırpar."""
        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        if speed > max_speed and speed > 0.0:
            scale = max_speed / speed
            return vx * scale, vy * scale, vz * scale
        return vx, vy, vz

    def _resolve_center(
        self,
        msg: FormationCommand,
    ) -> tuple[float, float, float]:
        """Formasyon merkezini doğrudan komuttan döndürür (shared NED)."""
        return (
            float(msg.center_x),
            float(msg.center_y),
            float(msg.center_z),
        )

    def _on_qr_step(self, msg: UInt8) -> None:
        """mission_fsm'in yayınladığı aktif QR alt-adımını saklar."""
        self._qr_step = int(msg.data)

    def _publish_setpoint(self) -> None:
        """Periyodik setpoint hesaplar ve AgentSetpoint yayınlar.

        Slot ataması lider'in komutundadır; bu node kendi slotunu uygular
        ve komşulara göre (NeighborInfo) formasyonu sıkı tutar.
        """
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

        # Atama lider tarafından komutta yayınlanır. Atama yoksa (lider henüz
        # dağıtmadıysa) veya bu drone atamada değilse bekle.
        agent_ids = list(msg.agent_ids)
        if not agent_ids or self._agent_id not in agent_ids:
            return

        # Lokal çalışma izni — merkezi SwarmState yerine kendi validity'si.
        if not self._origin_synced:
            self.get_logger().warn(
                'origin senkronlanmadi; setpoint bekletiliyor',
                throttle_duration_sec=2.0,
            )
            return

        # estimator_ok SITL'de bypass edildiği için xy/z_valid kullanılır.
        if not (self._xy_valid and self._z_valid):
            self.get_logger().warn(
                'konum tahmini gecersiz (xy/z_valid); setpoint bekletiliyor',
                throttle_duration_sec=2.0,
            )
            return

        idx = agent_ids.index(self._agent_id)
        if (idx >= len(msg.offset_x) or idx >= len(msg.offset_y)
                or idx >= len(msg.offset_z)):
            self.get_logger().warn(
                'komuttaki offset dizileri eksik; setpoint atlandi',
                throttle_duration_sec=2.0,
            )
            return

        center_x, center_y, center_z = self._resolve_center(msg)
        heading_rad = math.radians(msg.heading_deg)

        dx, dy = rotate_offset(
            msg.offset_x[idx], msg.offset_y[idx], heading_rad
        )
        x = center_x + dx
        y = center_y + dy
        z = center_z + msg.offset_z[idx]

        # Shared NED slot → lokal NED (dronun kendi GPS/EKF origin'ine göre).
        # v_ff burada DEĞİL, komut callback'inde (shared frame, 2Hz) hesaplandı.
        x, y = self._shared_to_local(x, y)
        # Z dönüştürülmez: local z=center_z her drone'un kendi origin'ine göre,
        # aynı zeminden kalkanlar için aynı gerçek yükseklik demektir.

        # max_speed komuttan veya parametreden çözülür (ramp hızı tavanı).
        max_speed = (
            float(msg.max_speed_mps)
            if msg.max_speed_mps > 0.0
            else self._max_speed_mps
        )

        # Hedef pozisyonu ramp ile yumuşat — ani slot atlamasını önler.
        # Ramp hızı max_speed ile sınırlanır; target_ramp_mps daha yavaş
        # bir değer isterse (ekstra yumuşaklık) onu kullanır.
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
            # İlk çağrıda ramp'i drone'un mevcut konumundan başlat
            self._ramp_x = self._current_pos_x if self._pos_valid else x
            self._ramp_y = self._current_pos_y if self._pos_valid else y
            self._ramp_z = self._current_pos_z if self._pos_valid else z
        # Ramp: ani slot sıçramasını yumuşat (SVT'ye giren hedef pürüzsüz olsun).
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

        # === HIZ KOMUTU (C MODU: SAF HIZ-TABANLI) =========================
        # v_cmd = v_svt + v_damp + v_rel + v_ff. Pozisyon kontrolü TÜMÜYLE
        # burada (SVT tek feedback) → position_valid=False, PX4 ile ÇAKIŞMAZ.
        # in_formation gate YOK: SVT form-up'ta büyük hata→büyük çekme, seyirde
        # küçük→ince koruma; tek mod. APF (CA node) bu hıza zincirde eklenir.
        #
        # SVT + damping: ramp'lı lokal slota çeker (-k·err) + sönümler (-b·v).
        svx, svy, svz = self._compute_velocity(x, y, z, max_speed)
        # rel: komşulara göre düzeltme (dağıtık sürü koordinasyonu, hız uzayı).
        rvx, rvy, rvz = self._compute_relative_correction(
            msg, idx, heading_rad, now
        )
        # v_ff: merkez hızı feed-forward. KOMUT callback'inde (2Hz) hesaplandı
        # (self._vff_*); burada SADECE eklenir. Hız frame-bağımsız (sabit origin
        # offset'i türevde kaybolur) → shared'de hesaplanan lokalde de geçerli.
        vx, vy, vz = self._clamp_speed(
            svx + rvx + self._vff_x,
            svy + rvy + self._vff_y,
            svz + rvz + self._vff_z, max_speed)
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
        """Hesaplanan pozisyon ve hızdan AgentSetpoint mesajı üretir."""
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
    """ROS2 entry point."""
    rclpy.init(args=args)
    node = FormationControlNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
