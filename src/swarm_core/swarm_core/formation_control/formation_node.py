"""Dağıtık formasyon kontrol node'u — her drone'da ayrı çalışır.

FormationCommand + SwarmState okur, kendi rank'ini Macar algoritmasıyla
belirler, shared NED → local NED dönüşümü yaparak AgentSetpoint üretir.
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

from swarm_interfaces.msg import (
    AgentSetpoint,
    AgentStatus,
    FormationCommand,
    SwarmOrigin,
    SwarmState,
)

from .formation_geometry import (
    compute_setpoint,
    compute_slot_offsets,
    FORMATION_CIZGI,
    FORMATION_OKBASI,
    FORMATION_V,
    hungarian_assignment,
    latlon_to_ned,
    rotate_offset,
)


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

_SUPPORTED_FORMATIONS = (FORMATION_OKBASI, FORMATION_V, FORMATION_CIZGI)

_PASSIVE_SWARM_STATES = frozenset({
    SwarmState.SWARM_UNKNOWN,
    SwarmState.SWARM_IDLE,
    SwarmState.SWARM_LANDING,
    SwarmState.SWARM_RTL,
    SwarmState.SWARM_FAILSAFE,
    SwarmState.SWARM_MISSION_COMPLETE,
})


class FormationControlNode(Node):
    """Tek drone için dağıtık formasyon setpoint hesaplayıcısı."""

    def __init__(self) -> None:
        """Node'u baslatir; parametreler, publisher ve subscriber'lar kurulur."""
        super().__init__('formation_control')

        self._declare_params()

        self._current_formation: FormationCommand | None = None
        self._latest_swarm_state: SwarmState | None = None
        self._active_agent_ids: list[int] = []
        self._sequence_num: int = 0

        self._cached_rank: int | None = None
        self._cached_formation_seq: int = -1

        self._current_pos_x: float = 0.0
        self._current_pos_y: float = 0.0
        self._current_pos_z: float = 0.0
        self._pos_valid: bool = False
        self._z_error_filtered: float = 0.0
        self._oscillating: bool = False

        self._origin_synced: bool = False
        self._estimator_ok: bool = False
        self._xy_valid: bool = False
        self._z_valid: bool = False

        self._current_lat: float = 0.0
        self._current_lon: float = 0.0
        self._gps_valid: bool = False

        self._origin_lat: float | None = None
        self._origin_lon: float | None = None

        self._centroid_vel_x: float = 0.0
        self._centroid_vel_y: float = 0.0
        self._centroid_vel_z: float = 0.0
        self._prev_centroid_x: float = 0.0
        self._prev_centroid_y: float = 0.0
        self._prev_centroid_z: float = 0.0
        self._prev_centroid_time: float | None = None

        # Hedef pozisyon ramp — ani sıçramayı yumuşatır
        self._ramp_x: float | None = None
        self._ramp_y: float | None = None
        self._ramp_z: float | None = None
        self._last_publish_time: float | None = None

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
            f'default_spacing={self._default_spacing_m} m, '
            f'alpha={self._alpha_deg} deg'
        )

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanımlar ve sınıf değişkenlerine okur."""
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('default_spacing_m', 5.0)
        self.declare_parameter('alpha_deg', 50.0)
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('position_tolerance_m', 0.5)
        self.declare_parameter('heading_tolerance_deg', 5.0)
        self.declare_parameter('max_speed_mps', 3.0)
        self.declare_parameter('svt_k', 0.3)
        self.declare_parameter('svt_threshold_m', 0.5)
        self.declare_parameter('svt_k_z', 2.0)
        self.declare_parameter('svt_threshold_z_m', 0.05)
        self.declare_parameter('svt_z_filter', 0.5)
        self.declare_parameter('target_ramp_mps', 1.0)

        self._agent_id: int = int(self.get_parameter('agent_id').value)
        self._default_spacing_m: float = float(
            self.get_parameter('default_spacing_m').value
        )
        self._alpha_deg: float = float(self.get_parameter('alpha_deg').value)
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
        self._svt_z_filter: float = float(
            self.get_parameter('svt_z_filter').value
        )
        self._target_ramp_mps: float = float(
            self.get_parameter('target_ramp_mps').value
        )
        self._alpha_rad: float = math.radians(self._alpha_deg)

    def _setup_publishers(self) -> None:
        """Setpoint publisher'ini olusturur (AgentSetpoint)."""
        self._setpoint_pub = self.create_publisher(
            AgentSetpoint,
            f'/drone_{self._agent_id}/control/setpoint',
            _BEST_EFFORT_QOS,
        )

    def _setup_subscribers(self) -> None:
        """Tüm topic aboneliklerini oluşturur.

        FormationCommand, SwarmState, AgentStatus ve SwarmOrigin.
        """
        self.create_subscription(
            FormationCommand,
            '/swarm/public/formation/target',
            self._on_formation_command,
            _RELIABLE_QOS,
        )
        self.create_subscription(
            SwarmState,
            '/swarm/public/state',
            self._on_swarm_state,
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

    def _on_formation_command(self, msg: FormationCommand) -> None:
        """Gelen FormationCommand'ı saklar."""
        prev = self._current_formation
        self._current_formation = msg
        # Formasyon tipi değişirse ramp'i sıfırla — yeni slota yumuşak geçiş
        if prev is None or prev.formation_type != msg.formation_type:
            self._ramp_x = None
            self._ramp_y = None
            self._ramp_z = None
        self.get_logger().info(
            f'FormationCommand alindi: type={msg.formation_type}, '
            f'spacing={msg.spacing_m:.1f}m, '
            f'heading={msg.heading_deg:.1f}deg, '
            f'center=({msg.center_x:.1f}, {msg.center_y:.1f}, '
            f'{msg.center_z:.1f})',
            throttle_duration_sec=1.0,
        )

    def _on_swarm_state(self, msg: SwarmState) -> None:
        """Suru durumunu isler; ajan listesini ve centroid hizini gunceller."""
        now = self.get_clock().now().nanoseconds * 1e-9
        if self._prev_centroid_time is not None:
            dt = now - self._prev_centroid_time
            if dt >= 0.05:
                self._centroid_vel_x = (
                    (msg.centroid_x - self._prev_centroid_x) / dt
                )
                self._centroid_vel_y = (
                    (msg.centroid_y - self._prev_centroid_y) / dt
                )
                self._centroid_vel_z = (
                    (msg.centroid_z - self._prev_centroid_z) / dt
                )
        self._prev_centroid_x = float(msg.centroid_x)
        self._prev_centroid_y = float(msg.centroid_y)
        self._prev_centroid_z = float(msg.centroid_z)
        self._prev_centroid_time = now

        self._latest_swarm_state = msg

        active_ids = sorted(int(i) for i in msg.active_agent_ids)
        if active_ids != self._active_agent_ids:
            self._active_agent_ids = active_ids
            # N değişince centroid hız tahmini geçersizleşir.
            self._prev_centroid_time = None
            self._centroid_vel_x = 0.0
            self._centroid_vel_y = 0.0
            self._centroid_vel_z = 0.0
            self.get_logger().info(
                f'Aktif ajan listesi guncellendi: {active_ids}'
            )

    def _on_agent_status(self, msg: AgentStatus) -> None:
        """Bu drone'un pozisyon, GPS ve güvenlik flag'lerini günceller."""
        self._current_pos_x = float(msg.pos_x)
        self._current_pos_y = float(msg.pos_y)
        self._current_pos_z = float(msg.pos_z)
        self._pos_valid = True
        self._oscillating = msg.oscillation_detected

        self._origin_synced = bool(msg.origin_synced)
        self._estimator_ok = bool(msg.estimator_ok)
        self._xy_valid = bool(msg.xy_valid)
        self._z_valid = bool(msg.z_valid)

        if msg.lat_deg != 0.0 or msg.lon_deg != 0.0:
            self._current_lat = float(msg.lat_deg)
            self._current_lon = float(msg.lon_deg)
            self._gps_valid = True

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
        use_ff_xy: bool = False,
        use_ff_z: bool = False,
    ) -> tuple[float, float, float]:
        """Feed-forward hız + SVT (Soft Virtual Tethering) düzeltmesi."""
        vx = self._centroid_vel_x if use_ff_xy else 0.0
        vy = self._centroid_vel_y if use_ff_xy else 0.0
        vz = self._centroid_vel_z if use_ff_z else 0.0

        # SVT: threshold'u aşınca sabit kazançlı yay kuvveti uygula.
        # oscillating=True ise salınım tespit edilmiş — SVT atlanır.
        if self._pos_valid and not self._oscillating:
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

        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        if speed > max_speed:
            scale = max_speed / speed
            vx *= scale
            vy *= scale
            vz *= scale

        return vx, vy, vz

    def _resolve_spacing(self, msg: FormationCommand) -> float:
        """Komuttaki spacing_m'i döndürür; 0 ise varsayılan parametre."""
        if msg.spacing_m > 0.0:
            return float(msg.spacing_m)
        return self._default_spacing_m

    def _resolve_center(
        self,
        msg: FormationCommand,
    ) -> tuple[float, float, float]:
        """Formasyon merkezini döndürür; bayraklara göre centroid'den okur."""
        cx = float(msg.center_x)
        cy = float(msg.center_y)
        cz = float(msg.center_z)

        state = self._latest_swarm_state
        if state is None:
            return cx, cy, cz

        if msg.use_current_centroid:
            cx = float(state.centroid_x)
            cy = float(state.centroid_y)
        if msg.use_current_altitude:
            cz = float(state.centroid_z)
        return cx, cy, cz

    def _find_rank(self) -> int | None:
        """Bu drone'un rank'ini döndürür.

        Yeni FormationCommand geldiğinde Macar algoritmasıyla yeniden hesaplar;
        aynı komut süresince rank kilitli kalır (titreme önleme).
        """
        if self._agent_id not in self._active_agent_ids:
            return None

        msg = self._current_formation
        if msg is None:
            return self._active_agent_ids.index(self._agent_id)

        # Merkezi atama: publisher Macar'ı kendi yapmışsa agent_ids dolludur.
        # Her tick'te güncel assignment'ı al — publisher GPS düzeldikçe
        # assignment'ı düzeltebilir, kilitleme yapma (dağıtık Macar'ın aksine).
        if len(msg.agent_ids) > 0 and self._agent_id in list(msg.agent_ids):
            idx = list(msg.agent_ids).index(self._agent_id)
            self._cached_rank = idx
            self._cached_formation_seq = msg.sequence_num
            return self._cached_rank

        if msg.sequence_num != self._cached_formation_seq:

            # Merkezi atama yoksa dağıtık Macar (fallback)
            state = self._latest_swarm_state
            if state is not None:
                cmd_t = msg.stamp.sec + msg.stamp.nanosec * 1e-9
                state_t = state.stamp.sec + state.stamp.nanosec * 1e-9
                if state_t < cmd_t:
                    return self._active_agent_ids.index(self._agent_id)

            rank = self._compute_optimal_rank(msg)
            if rank is None:
                return self._active_agent_ids.index(self._agent_id)
            self._cached_rank = rank
            self._cached_formation_seq = msg.sequence_num

        return self._cached_rank

    def _compute_optimal_rank(self, msg: FormationCommand) -> int | None:
        """Bu drone için optimal slot rank'ini hesaplar (O(N³) Macar).

        GPS gecikmesi nedeniyle pozisyonlar henüz hazır değilse None döner;
        çağıran cache'i kilitlemeden yeniden dener.
        """
        ids = self._active_agent_ids
        n = len(ids)

        state = self._latest_swarm_state
        if state is None or len(state.agent_pos_x) != n:
            return None

        drone_xy: list[tuple[float, float]] = [
            (float(state.agent_pos_x[i]), float(state.agent_pos_y[i]))
            for i in range(n)
        ]

        # GPS hazır olmadan test publisher pozisyonları (0,0) ile doldurur;
        # bu maliyet matrisini bozar → kilitleme, hazır olunca yeniden dene.
        if any(px == 0.0 and py == 0.0 for px, py in drone_xy):
            return None

        spacing = (
            float(msg.spacing_m)
            if msg.spacing_m > 0.0
            else self._default_spacing_m
        )
        heading_rad = math.radians(msg.heading_deg)
        center_x, center_y, _ = self._resolve_center(msg)

        offsets = compute_slot_offsets(
            int(msg.formation_type), n, spacing, self._alpha_rad
        )
        slot_xy: list[tuple[float, float]] = []
        for dx, dy, _ in offsets:
            rx, ry = rotate_offset(dx, dy, heading_rad)
            slot_xy.append((center_x + rx, center_y + ry))

        cost = [
            [
                math.hypot(
                    drone_xy[i][0] - slot_xy[j][0],
                    drone_xy[i][1] - slot_xy[j][1],
                )
                for j in range(n)
            ]
            for i in range(n)
        ]
        assignment = hungarian_assignment(cost)
        return assignment[ids.index(self._agent_id)]

    def _publish_setpoint(self) -> None:
        """Periyodik setpoint hesaplar ve AgentSetpoint yayınlar."""
        msg = self._current_formation
        if msg is None or not self._active_agent_ids:
            return

        state = self._latest_swarm_state
        if state is not None:
            if not state.mission_active:
                return
            if state.swarm_state in _PASSIVE_SWARM_STATES:
                return

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

        rank = self._find_rank()
        if rank is None:
            return

        center_x, center_y, center_z = self._resolve_center(msg)
        heading_rad = math.radians(msg.heading_deg)

        # Merkezi atama: publisher offset'i hazır vermiş — doğrudan kullan.
        if len(msg.agent_ids) > 0 and self._agent_id in list(msg.agent_ids):
            idx = list(msg.agent_ids).index(self._agent_id)
            if idx < len(msg.offset_x):
                dx, dy = rotate_offset(
                    msg.offset_x[idx], msg.offset_y[idx], heading_rad
                )
                x = center_x + dx
                y = center_y + dy
                z = center_z + msg.offset_z[idx]
            else:
                return
        else:
            # Dağıtık Macar fallback
            if msg.formation_type not in _SUPPORTED_FORMATIONS:
                self.get_logger().warn(
                    f'Desteklenmeyen formation_type={msg.formation_type}',
                    throttle_duration_sec=2.0,
                )
                return
            spacing = self._resolve_spacing(msg)
            total = len(self._active_agent_ids)
            try:
                x, y, z = compute_setpoint(
                    center_x=center_x, center_y=center_y, center_z=center_z,
                    formation_type=int(msg.formation_type), rank=rank,
                    total=total, spacing=spacing,
                    alpha_rad=self._alpha_rad, heading_rad=heading_rad,
                )
            except ValueError as e:
                self.get_logger().error(
                    f'Setpoint hesaplanamadi: {e}',
                    throttle_duration_sec=1.0,
                )
                return

        x, y = self._shared_to_local(x, y)
        # Z dönüştürülmez: local z=center_z her drone'un kendi origin'ine göre,
        # aynı zeminden kalkanlar için aynı gerçek yükseklik demektir. (AMSL
        # düzeltmesi denendi → tahmin bias'ı yüksekliği bozuyor + feedback
        # salınımı yapıyordu, kaldırıldı.)

        # max_speed komuttan veya parametreden çözülür (ramp hızı tavanı).
        max_speed = (
            float(msg.max_speed_mps)
            if msg.max_speed_mps > 0.0
            else self._max_speed_mps
        )

        # Hedef pozisyonu ramp ile yumuşat — ani slot atlamasını önler.
        # Ramp hızı max_speed ile sınırlanır: statik formasyonda
        # (velocity_valid=False) bridge pozisyon-only moda geçip SVT hızını
        # attığı için EFEKTİF hız knob'u budur. target_ramp_mps daha yavaş
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
        ramp_converged = True
        if dt > 0.0 and ramp_rate > 0.0:
            max_step = ramp_rate * dt
            for attr, target in [
                ('_ramp_x', x), ('_ramp_y', y), ('_ramp_z', z)
            ]:
                cur = getattr(self, attr)
                diff = target - cur
                if abs(diff) > 0.05:
                    ramp_converged = False
                step = max(-max_step, min(max_step, diff))
                setattr(self, attr, cur + step)
        x, y, z = self._ramp_x, self._ramp_y, self._ramp_z

        # Hareket ederken: velocity_valid=False → PX4 kendi pozisyon
        # kontrolcüsüyle yumuşak gider, SVT hızı görmez → sert eğilme olmaz.
        # Slota yerleştikten sonra: velocity_valid=True → SVT aktif,
        # GPS gürültüsüne karşı aktif düzeltme yapar, formasyon tutulur.
        vx, vy, vz = self._compute_velocity(
            x, y, z, max_speed,
            use_ff_xy=msg.use_current_centroid,
            use_ff_z=msg.use_current_altitude,
        )
        out = self._build_setpoint_msg(
            msg, x, y, z, vx, vy, vz,
            velocity_valid=ramp_converged,
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
        out.position_valid = True

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
