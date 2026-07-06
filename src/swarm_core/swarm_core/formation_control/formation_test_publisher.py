"""Formation pipeline'ini uctan uca test etmek icin minimal yayinci node.

formation_test_publisher.py

Zincir:
  Bu node → formation_node → AgentSetpoint → px4_bridge → drone hareket

Başlatıldığında tüm drone'lardan telemetri bekler, centroid'i bir kez kilitler
(snapshot), sonra bu sabit merkezi FormationCommand'a yazar. Böylece dronlar
hareket ederken merkez kaymaz ve formasyon istikrarlı kalır.

Kullanım (proxy olmadan, SITL 3-drone testi):
  ros2 run swarm_core formation_test_publisher \
    --ros-args \
    -p agent_ids:=[1,2,3] \
    -p formation_type:=2 \
    -p spacing_m:=8.0 \
    -p heading_deg:=0.0 \
    -p center_z:=-15.0 \
    -p use_proxy:=false
"""

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSPresetProfiles,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_interfaces.msg import (
    AgentStatus,
    FormationCommand,
    SwarmOrigin,
)

from .formation_geometry import (
    compute_slot_offsets,
    hungarian_assignment,
    latlon_to_ned,
    rotate_offset,
)

# SwarmOrigin: leader yayınlar, geç katılan node son değeri almalı.
_ORIGIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


class FormationTestPublisher(Node):
    """FormationCommand yayınlayan sahte lider test node'u.

    Lider orkestratörü (mission1_dynamic_swarm) henüz yokken onun yerine
    geçer: drone telemetrisini dinler, Macar ataması yapar ve sonucu
    FormationCommand içinde (agent_ids + offset) yayınlar. Merkezi SwarmState
    yayınlamaz; yeni formation_node onu okumaz.
    """

    def __init__(self):
        """Node'u başlatır, parametreleri okur ve abonelikleri kurar."""
        super().__init__('formation_test_publisher')

        self.declare_parameter('agent_ids', [1])
        self.declare_parameter(
            'formation_type', FormationCommand.FORMATION_OKBASI
        )
        self.declare_parameter('spacing_m', 5.0)
        self.declare_parameter('heading_deg', 0.0)
        self.declare_parameter('center_z', -15.0)
        self.declare_parameter('rate_hz', 10.0)
        self.declare_parameter('use_proxy', False)
        # use_hungarian=False → slotlar agent_ids SIRASINA göre atanır
        # (Macar/optimal değil). Çakışma testi için: sırayı ters çevirince
        # drone'lar GERÇEKTEN yer değiştirir (yoksa Macar hareketi sıfırlar).
        self.declare_parameter('use_hungarian', True)
        # Hareketli merkez testi: merkezi kilitlendikten sonra sabit hızla
        # kaydırır (path_planning waypoint hareketini taklit). 0.0 = sabit.
        self.declare_parameter('move_speed_mps', 0.0)
        self.declare_parameter('move_heading_deg', 0.0)
        self.declare_parameter('lock_after_sec', 10.0)
        self.declare_parameter('center_lat', 0.0)
        self.declare_parameter('center_lon', 0.0)
        self.declare_parameter('max_speed_mps', 0.0)
        # Kademeli (rijit) dönüş: heading'i start'tan target'a bu hızda yürüt.
        # Tüm drone'lar aynı kademeli açıyı aldığı için formasyon RİJİT döner
        # (anlık step → çapraz kiriş → CA çatışması yerine). 0 = anlık (eski).
        # KISIT: rijit dönüş için heading_rate ≤ max_speed/r_max (r=kol yarıçapı)
        # olmalı; aksi halde dış drone teğet hıza yetişemez.
        self.declare_parameter('start_heading_deg', -999.0)  # -999 = target'a eşit
        self.declare_parameter('heading_rate_dps', 0.0)

        self._agent_ids = list(
            self.get_parameter('agent_ids')
            .get_parameter_value().integer_array_value
        )
        self._formation_type = int(
            self.get_parameter('formation_type')
            .get_parameter_value().integer_value
        )
        self._spacing_m = float(
            self.get_parameter('spacing_m').get_parameter_value().double_value
        )
        self._heading_deg = float(
            self.get_parameter('heading_deg')
            .get_parameter_value().double_value
        )
        # Kademeli dönüş parametreleri.
        _sh = float(
            self.get_parameter('start_heading_deg')
            .get_parameter_value().double_value
        )
        self._start_heading_deg = (
            self._heading_deg if _sh <= -998.0 else _sh
        )
        self._heading_rate_dps = float(
            self.get_parameter('heading_rate_dps')
            .get_parameter_value().double_value
        )
        self._heading_t0: float | None = None
        self._fallback_center_z = float(
            self.get_parameter('center_z').get_parameter_value().double_value
        )
        rate_hz = float(
            self.get_parameter('rate_hz').get_parameter_value().double_value
        )
        use_proxy = bool(
            self.get_parameter('use_proxy').get_parameter_value().bool_value
        )
        self._use_hungarian = bool(
            self.get_parameter('use_hungarian')
            .get_parameter_value().bool_value
        )
        self._move_speed_mps = float(
            self.get_parameter('move_speed_mps')
            .get_parameter_value().double_value
        )
        self._move_heading_deg = float(
            self.get_parameter('move_heading_deg')
            .get_parameter_value().double_value
        )
        self._lock_after_sec = float(
            self.get_parameter('lock_after_sec')
            .get_parameter_value().double_value
        )
        self._center_lat = float(
            self.get_parameter('center_lat')
            .get_parameter_value().double_value
        )
        self._center_lon = float(
            self.get_parameter('center_lon')
            .get_parameter_value().double_value
        )
        self._use_fixed_center = (
            self._center_lat != 0.0 or self._center_lon != 0.0
        )
        self._centroid_locked = False
        self._lock_timer_started: float | None = None
        # Merkez kilitlendiği an (hareket bu andan itibaren hesaplanır).
        self._move_t0: float | None = None

        if use_proxy:
            formation_topic = '/swarm/internal/formation/target'
            telem_prefix = '/swarm/public/agent/drone'
        else:
            formation_topic = '/swarm/public/formation/target'
            telem_prefix = '/swarm/agent/drone'

        self._formation_pub = self.create_publisher(
            FormationCommand,
            formation_topic,
            QoSPresetProfiles.SYSTEM_DEFAULT.value,
        )

        # Drone pozisyonlarını dinle (centroid snapshot için)
        # GPS (lat/lon) — shared NED hesabı için; alt — Z için.
        self._gps: dict[int, tuple[float, float]] = {}
        self._alt: dict[int, float] = {}
        for aid in self._agent_ids:
            topic = f'{telem_prefix}{aid}/telemetry'
            self.create_subscription(
                AgentStatus,
                topic,
                lambda msg, i=aid: self._on_telemetry(i, msg),
                QoSPresetProfiles.SYSTEM_DEFAULT.value,
            )

        # Ortak referans GPS noktası (SwarmOrigin'den) — shared NED origin'i.
        self._origin_lat: float | None = None
        self._origin_lon: float | None = None
        self.create_subscription(
            SwarmOrigin,
            '/swarm/public/origin',
            self._on_swarm_origin,
            _ORIGIN_QOS,
        )

        # Centroid her döngüde güncellenir (live), kilitlenmez
        self._center_x: float | None = None
        self._center_y: float | None = None
        self._center_z: float | None = None

        self._seq = 0
        self._last_cmd_key: tuple | None = None
        # Merkezi Macar ataması — sadece formasyon değişince hesaplanır.
        # Her tick yeniden hesaplanırsa: drone konumuna göre atanır → öz-döngü.
        self._cached_assignment: list | None = None  # her drone için offset
        self._cached_assignment_seq: int = -1
        period = 1.0 / rate_hz
        self.create_timer(period, self._publish)

        self.get_logger().info(
            f'FormationTestPublisher başladı | agent_ids={self._agent_ids} '
            f'| formation_type={self._formation_type} '
            f'| spacing={self._spacing_m}m '
            f'| heading={self._heading_deg}° '
            f'| fallback_z={self._fallback_center_z} '
            f'| {rate_hz:.1f} Hz | proxy={"on" if use_proxy else "off"}'
        )

    def _on_telemetry(self, agent_id: int, msg: AgentStatus) -> None:
        """GPS + irtifa güncelle."""
        if msg.lat_deg != 0.0 or msg.lon_deg != 0.0:
            self._gps[agent_id] = (float(msg.lat_deg), float(msg.lon_deg))
        self._alt[agent_id] = float(msg.pos_z)

        if self._centroid_locked:
            return

        # Sabit merkez verilmişse origin gelince hemen kilitle
        if self._use_fixed_center and self._origin_lat is not None:
            n, e = latlon_to_ned(
                self._center_lat, self._center_lon,
                self._origin_lat, self._origin_lon,
            )
            self._center_x = n
            self._center_y = e
            self._center_z = self._fallback_center_z
            self._centroid_locked = True
            self.get_logger().info(
                f'Sabit merkez kilitlendi: '
                f'({self._center_x:.2f}, {self._center_y:.2f})'
            )
            return

        # Sabit merkez yoksa drone ortalamasından hesapla;
        # lock_after_sec sonra kilitle.
        self._update_centroid()
        if self._center_x is not None and self._lock_timer_started is None:
            self._lock_timer_started = (
                self.get_clock().now().nanoseconds * 1e-9
            )
        if (self._lock_timer_started is not None
                and self.get_clock().now().nanoseconds * 1e-9
                - self._lock_timer_started >= self._lock_after_sec):
            self._centroid_locked = True
            self.get_logger().info(
                f'Centroid kilitlendi ({self._lock_after_sec:.0f}s sonra): '
                f'({self._center_x:.2f}, {self._center_y:.2f})'
            )

    def _on_swarm_origin(self, msg: SwarmOrigin) -> None:
        """Ortak referans GPS noktasını saklar (shared NED frame origin'i)."""
        if not msg.valid:
            return
        self._origin_lat = float(msg.origin_lat_deg)
        self._origin_lon = float(msg.origin_lon_deg)

    def _shared_ned(self, agent_id: int) -> tuple[float, float]:
        """Bir drone'un shared NED (north, east) konumu — GPS'ten."""
        lat, lon = self._gps[agent_id]
        return latlon_to_ned(lat, lon, self._origin_lat, self._origin_lon)

    def _update_centroid(self) -> None:
        """Centroidi her çağrıda mevcut GPS'ten hesapla (live)."""
        if self._origin_lat is None or not self._gps:
            return
        pts = [self._shared_ned(aid) for aid in self._gps]
        n = len(pts)
        self._center_x = sum(p[0] for p in pts) / n
        self._center_y = sum(p[1] for p in pts) / n
        self._center_z = self._fallback_center_z

    def _compute_heading(self) -> float:
        """Kademeli (rijit) dönüş için o anki heading'i döndürür.

        start_heading'den target'a (heading_deg) heading_rate_dps ile yürür.
        rate=0 → anlık (target). Tüm drone'lar aynı komuttan aynı kademeli
        açıyı aldığı için formasyon rijit cisim gibi döner.
        """
        if self._heading_rate_dps <= 0.0:
            return self._heading_deg
        nowf = self.get_clock().now().nanoseconds * 1e-9
        if self._heading_t0 is None:
            self._heading_t0 = nowf
        diff = ((self._heading_deg - self._start_heading_deg + 180.0)
                % 360.0) - 180.0
        max_change = self._heading_rate_dps * (nowf - self._heading_t0)
        if abs(diff) <= max_change:
            return self._heading_deg
        return self._start_heading_deg + math.copysign(max_change, diff)

    def _publish(self) -> None:
        """Her timer tetiklemesinde FormationCommand yayınlar."""
        if self._center_x is None:
            return  # Henüz GPS gelmedi, bekle

        now = self.get_clock().now().to_msg()
        cmd_key = (
            self._formation_type, self._spacing_m,
            self._heading_deg, self._move_speed_mps,
        )
        if cmd_key != self._last_cmd_key:
            self._seq += 1
            self._last_cmd_key = cmd_key

        # Hareketli merkez: kilitlendikten sonra geçen süreye göre sabit
        # hızla kaydır (path_planning waypoint hareketini taklit).
        # move_speed=0 ise sabit merkez. Merkez her tick fc.center'a yazılır;
        # formation_node doğrudan komuttaki center'ı izler.
        cx, cy = self._center_x, self._center_y
        use_moving = self._move_speed_mps > 0.0
        if use_moving:
            nowf = self.get_clock().now().nanoseconds * 1e-9
            if self._move_t0 is None:
                self._move_t0 = nowf
            dist = self._move_speed_mps * (nowf - self._move_t0)
            hdg = math.radians(self._move_heading_deg)
            cx = self._center_x + dist * math.cos(hdg)   # north
            cy = self._center_y + dist * math.sin(hdg)   # east

        # --- Merkezi Macar Ataması ---
        # Sadece formasyon değişince (yeni _seq) yeniden hesaplanır.
        # Her tick yeniden hesaplamak → drone konumuna göre atanır → öz-döngü.
        alpha_rad = math.radians(30.0)
        # Macar atamasını BAŞLANGIÇ heading'inde yap: dronlar şu an o
        # yönelimdeki formasyonda duruyor. Hedef heading kullanılırsa atama
        # mevcut formasyonla uyuşmaz → faz başında d1/d2 swap → birbirinin
        # içinden geçerek savrulma. Atama start_heading'de kilitlenir, sonra
        # formasyon o atamayla rijit döner (offset'ler formasyon-çerçevesinde,
        # formation_node onları kademeli heading ile döndürür).
        heading_rad = math.radians(self._start_heading_deg)
        n = len(self._agent_ids)
        offsets = compute_slot_offsets(
            self._formation_type, n, self._spacing_m, alpha_rad
        )

        assigned_ids = []
        assigned_offsets = []
        if self._seq != self._cached_assignment_seq:
            # Formasyon değişti — yeniden hesapla.
            if not self._use_hungarian:
                # Index'e göre atama: agent_ids[i] → offsets[i] (optimal
                # DEĞİL). Çakışma testi: agent_ids ters çevrilince drone'lar
                # GERÇEKTEN yer değiştirir (Macar hareketi sıfırlamaz).
                self._cached_assignment = [offsets[i] for i in range(n)]
                self._cached_assignment_seq = self._seq
                self.get_logger().warn(
                    'INDEX ATAMA@seq=%d (Macar kapalı): %s' % (
                        self._seq,
                        ', '.join(
                            f'd{self._agent_ids[i]}->slot{i}'
                            for i in range(n)
                        ),
                    )
                )
            elif self._origin_lat is not None and len(self._gps) == n:
                slot_xy = []
                for dx, dy, _ in offsets:
                    rx, ry = rotate_offset(dx, dy, heading_rad)
                    slot_xy.append((cx + rx, cy + ry))
                drone_xy = [self._shared_ned(aid) for aid in self._agent_ids]
                cost = [
                    [math.hypot(drone_xy[i][0] - slot_xy[j][0],
                                drone_xy[i][1] - slot_xy[j][1])
                     for j in range(n)]
                    for i in range(n)
                ]
                assignment = hungarian_assignment(cost)
                self._cached_assignment = [
                    offsets[assignment[i]] for i in range(n)
                ]
                self._cached_assignment_seq = self._seq
                # Macar hesaplandığı andaki HAM GPS + hesaplanan shared NED
                self.get_logger().warn(
                    'MACAR@seq=%d origin=(%.6f,%.6f) | ' % (
                        self._seq, self._origin_lat, self._origin_lon)
                    + ' || '.join(
                        f'd{self._agent_ids[i]}: '
                        f'lat={self._gps[self._agent_ids[i]][0]:.7f} '
                        f'lon={self._gps[self._agent_ids[i]][1]:.7f} '
                        f'→ N={drone_xy[i][0]:+.2f} E={drone_xy[i][1]:+.2f} '
                        f'→ slot{assignment[i]}'
                        for i in range(n)
                    )
                )

        if self._cached_assignment is not None:
            assigned_ids = list(self._agent_ids)
            assigned_offsets = self._cached_assignment

        # --- FormationCommand ---
        fc = FormationCommand()
        fc.stamp = now
        fc.sequence_num = self._seq
        fc.formation_type = self._formation_type
        fc.center_x = cx
        fc.center_y = cy
        fc.center_z = self._center_z
        fc.heading_deg = self._compute_heading()
        fc.spacing_m = self._spacing_m
        fc.use_current_centroid = use_moving
        fc.use_current_altitude = False
        fc.rotate_towards_target = False
        fc.hold_after_reached = False
        fc.position_tolerance_m = 0.5
        fc.heading_tolerance_deg = 5.0
        fc.timeout_sec = 0.0
        fc.max_speed_mps = float(
            self.get_parameter('max_speed_mps')
            .get_parameter_value().double_value
        )
        # Merkezi atama sonuçları — formation_node bunu okuyunca
        # kendi Macar'ını çalıştırmaz.
        fc.agent_ids = [int(aid) for aid in assigned_ids]
        fc.offset_x = [float(o[0]) for o in assigned_offsets]
        fc.offset_y = [float(o[1]) for o in assigned_offsets]
        fc.offset_z = [float(o[2]) for o in assigned_offsets]
        fc.source_module = 'formation_test_publisher'

        # Sahte lider: yalnızca FormationCommand yayınlanır. (Yeni
        # formation_node merkezi SwarmState okumadığı için SwarmState yayını
        # kaldırıldı; atama agent_ids + offset ile komutun içindedir.)
        fc.stamp = self.get_clock().now().to_msg()
        self._formation_pub.publish(fc)


def main(args=None):
    """ROS2 entry point."""
    rclpy.init(args=args)
    node = FormationTestPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
