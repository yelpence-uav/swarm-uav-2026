"""Bozulma & gerçek-karşılaşma test yayıncısı (B + C katmanları).

formation_test_publisher'ın KOPYASI + bağımsız-hedef yetenekleri. Orijinal
production aracına dokunmamak için scripts/test/collision/ altında standalone
çalışır (python3 ile, ros2 run değil).

TEMEL İLKE — slot oyunu DEĞİL, fiziksel karşılaşma:
  Çakışmayı atama manipülasyonuyla (Macar kapatıp ters slot) ÜRETMİYORUZ.
  Her drone'a GERÇEK, zamanla hareket eden bir hedef offset'i veriyoruz;
  drone oraya FİZİKSEL uçuyor, yolda komşu çıkınca CA gerçekten devreye girer.
  Tek FormationCommand yayınlanır (tüm agent_ids) → formation_node uyumlu
  (iki ayrı instance titretiyordu: node her komutu saklayıp kendi id'si
  yoksa atlıyor → bu yüzden tek-komut/çok-hedef modeli kullanılır).

Modlar:
  two_group      : agent'lar iki gruba bölünür, ZIT yönde hareket → orta
                   noktada fiziksel kesişme (C1/C3). Gerçek iki-ekip karşılaşması.
  breakaway      : bir drone GEÇİCİ olarak komşusuna doğru hedeflenir (rüzgar/
                   görev sapması) → CA durdurmalı, sonra SVT geri toplamalı (B1/B2).
  static_obstacle: bir drone sabit (engel), diğerleri üstüne hareket (C2).

Kullanım örnekleri scripts'lerde (b1_lateral.sh, c1_two_group.sh, ...).
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

from swarm_core.formation_control.formation_geometry import (
    compute_slot_offsets,
    latlon_to_ned,
)

_ORIGIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


class DisturbancePublisher(Node):
    """Bağımsız-hedef test yayıncısı: fiziksel karşılaşma/bozulma üretir."""

    def __init__(self):
        super().__init__('disturbance_publisher')

        # --- Ortak ---
        self.declare_parameter('agent_ids', [1, 2, 3])
        self.declare_parameter('formation_type', FormationCommand.FORMATION_CIZGI)
        self.declare_parameter('spacing_m', 5.0)
        self.declare_parameter('heading_deg', 0.0)
        self.declare_parameter('center_z', -15.0)
        self.declare_parameter('rate_hz', 10.0)
        self.declare_parameter('center_lat', 0.0)
        self.declare_parameter('center_lon', 0.0)
        self.declare_parameter('max_speed_mps', 2.0)
        self.declare_parameter('alpha_deg', 30.0)

        # --- Mod seçimi ---
        # two_group | breakaway | static_obstacle | normal
        self.declare_parameter('mode', 'normal')

        # --- iki grupta da yer almayan sabit drone'lar ---
        self.declare_parameter('neutral_ids', [0])     # kendi slotunda sabit kalır

        # --- two_group (C1/C3): iki ekip zıt yönde geçer ---
        self.declare_parameter('group_b_ids', [3])     # karşı grup
        self.declare_parameter('separation_m', 8.0)    # başlangıç X ayrımı
        self.declare_parameter('cross_speed_mps', 1.5)  # zıt geçiş hızı
        self.declare_parameter('cross_axis', 'horizontal')  # horizontal | vertical
        self.declare_parameter('lateral_offset_m', 0.0)  # y kaçık (0=tam kafa)
        # park_time_s: dronlar başlangıç pozisyonuna gidip yerleşsin; SONRA geçiş başlasın
        self.declare_parameter('park_time_s', 6.0)

        # --- breakaway (B1/B2): bir drone geçici komşuya sürüklenir ---
        self.declare_parameter('disturb_id', 2)
        self.declare_parameter('disturb_axis', 'lateral')  # lateral | vertical
        self.declare_parameter('disturb_mag_m', 4.0)   # komşuya doğru sapma
        self.declare_parameter('disturb_start_s', 8.0)
        self.declare_parameter('disturb_dur_s', 4.0)

        # --- rendezvous (hover): iki drone birbirine yakın AYRI hedeflere ---
        self.declare_parameter('rdv_gap_m', 1.0)  # iki drone arası hedef mesafe

        # --- static_obstacle (C2): bir drone sabit engel ---
        self.declare_parameter('obstacle_id', 3)
        self.declare_parameter('approach_speed_mps', 1.0)

        gp = self.get_parameter
        self._agent_ids = list(gp('agent_ids').get_parameter_value()
                               .integer_array_value)
        self._ftype = int(gp('formation_type').value)
        self._spacing = float(gp('spacing_m').value)
        self._heading = float(gp('heading_deg').value)
        self._cz = float(gp('center_z').value)
        rate = float(gp('rate_hz').value)
        self._clat = float(gp('center_lat').value)
        self._clon = float(gp('center_lon').value)
        self._max_speed = float(gp('max_speed_mps').value)
        self._alpha = math.radians(float(gp('alpha_deg').value))

        self._mode = str(gp('mode').value)
        self._neutral = list(gp('neutral_ids').get_parameter_value()
                             .integer_array_value)
        self._group_b = list(gp('group_b_ids').get_parameter_value()
                             .integer_array_value)
        self._sep = float(gp('separation_m').value)
        self._cross_speed = float(gp('cross_speed_mps').value)
        self._cross_axis = str(gp('cross_axis').value)
        self._lat_off = float(gp('lateral_offset_m').value)
        self._park_time = float(gp('park_time_s').value)

        self._dist_id = int(gp('disturb_id').value)
        self._dist_axis = str(gp('disturb_axis').value)
        self._dist_mag = float(gp('disturb_mag_m').value)
        self._dist_start = float(gp('disturb_start_s').value)
        self._dist_dur = float(gp('disturb_dur_s').value)

        self._rdv_gap = float(gp('rdv_gap_m').value)
        self._obs_id = int(gp('obstacle_id').value)
        self._approach = float(gp('approach_speed_mps').value)

        self._pub = self.create_publisher(
            FormationCommand, '/swarm/public/formation/target',
            QoSPresetProfiles.SYSTEM_DEFAULT.value,
        )
        self._gps: dict[int, tuple[float, float]] = {}
        for aid in self._agent_ids:
            self.create_subscription(
                AgentStatus, f'/swarm/agent/drone{aid}/telemetry',
                lambda m, i=aid: self._on_tel(i, m),
                QoSPresetProfiles.SYSTEM_DEFAULT.value,
            )
        self._origin_lat: float | None = None
        self._origin_lon: float | None = None
        self.create_subscription(
            SwarmOrigin, '/swarm/public/origin', self._on_origin, _ORIGIN_QOS,
        )

        self._cx: float | None = None
        self._cy: float | None = None
        self._t0: float | None = None
        self._seq = 0
        self.create_timer(1.0 / rate, self._publish)
        self.get_logger().info(
            f'DisturbancePublisher | mode={self._mode} | '
            f'agents={self._agent_ids} | spacing={self._spacing}m'
        )

    def _on_tel(self, aid: int, msg: AgentStatus) -> None:
        if msg.lat_deg != 0.0 or msg.lon_deg != 0.0:
            self._gps[aid] = (float(msg.lat_deg), float(msg.lon_deg))

    def _on_origin(self, msg: SwarmOrigin) -> None:
        if msg.valid:
            self._origin_lat = float(msg.origin_lat_deg)
            self._origin_lon = float(msg.origin_lon_deg)

    def _ensure_center(self) -> bool:
        """Sabit merkezi origin gelince bir kez NED'e çevirir."""
        if self._cx is not None:
            return True
        if self._origin_lat is None:
            return False
        n, e = latlon_to_ned(self._clat, self._clon,
                             self._origin_lat, self._origin_lon)
        self._cx, self._cy = n, e
        return True

    def _base_offsets(self) -> list[tuple[float, float, float]]:
        """agent_ids SIRASINA göre formasyon slot offsetleri (index ataması)."""
        return compute_slot_offsets(
            self._ftype, len(self._agent_ids), self._spacing, self._alpha,
        )

    def _compute_offsets(self, t: float) -> list[tuple[float, float, float]]:
        """Moda göre her drone'un (zamanla hareket eden) hedef offset'i."""
        n = len(self._agent_ids)
        base = self._base_offsets()

        if self._mode == 'two_group':
            # İki ekip zıt yönde geçer → orta noktada fiziksel kesişme.
            # Faz 1 (t < park_time_s): dronlar başlangıç pozisyonuna gidip yerleşir.
            # Faz 2 (t >= park_time_s): SABİT karşı taraf hedefine uçar (süpürmez).
            #   Süpüren hedef yerine sabit swap noktası: CA etkisini temiz ölçer.
            # neutral_ids: crossing yolundan uzak sabit nokta (lateral_offset * 3).
            out = []
            ia = ib = 0
            # Neutral drone'lar crossing koridorundan laterale çekilir
            neutral_lat_pull = self._sep * 0.8   # crossing ekseninden yeterince uzak
            for k, aid in enumerate(self._agent_ids):
                if aid in self._neutral:
                    # Kendi slotunda değil — crossing yolundan uzak lateral noktada park
                    bx, by, bz = base[k]
                    if self._cross_axis == 'vertical':
                        out.append((bx, neutral_lat_pull, bz))
                    else:
                        out.append((bx, neutral_lat_pull, bz))
                    continue
                in_b = aid in self._group_b
                if in_b:
                    rank = ib; ib += 1
                else:
                    rank = ia; ia += 1
                lane = (rank - 0.5) * self._spacing
                # Park tarafı: group A = +sep/2, group B = -sep/2
                park_side = +self._sep / 2 if not in_b else -self._sep / 2
                lat = self._lat_off if not in_b else -self._lat_off
                if t < self._park_time:
                    # Faz 1: park pozisyonuna git ve bekle
                    pos = park_side
                else:
                    # Faz 2: SABİT karşı tarafa uç (drone A → -sep/2, drone B → +sep/2)
                    pos = -park_side
                if self._cross_axis == 'vertical':
                    out.append((lane, lat, pos))
                else:
                    out.append((pos, lane + lat, 0.0))
            return out

        if self._mode == 'rendezvous':
            # HOVER testi: group_b dışındaki drone'lar AYNI noktaya (center,
            # offset 0) çekilir; group_b uzakta park eder (karışmasın). İki
            # drone aynı hedefe gidince CA onları güvenli mesafede DURDURUP
            # hover ettirebiliyor mu? (öneri: kaçacak yer yoksa dengede dur).
            out = []
            rdv_i = 0
            for k, aid in enumerate(self._agent_ids):
                if aid in self._group_b:
                    out.append(base[k])                  # KENDİ slotunda kal
                else:
                    # center'ın iki yanında rdv_gap/2 → birbirine YAKIN ama
                    # AYRI hedef (gap < emniyet). CA bunları emniyet mesafesine
                    # açıp orada DURDURUP hover ettirmeli (kaçacak yer yok).
                    side = -1.0 if rdv_i == 0 else +1.0
                    out.append((0.0, side * self._rdv_gap / 2.0, 0.0))
                    rdv_i += 1
            return out

        if self._mode == 'breakaway':
            # Hepsi normal slot; disturb_id geçici komşuya doğru sürüklenir.
            out = list(base)
            if self._dist_start <= t < self._dist_start + self._dist_dur:
                try:
                    k = self._agent_ids.index(self._dist_id)
                except ValueError:
                    return out
                dx, dy, dz = out[k]
                # Sürüklenme: rampalı (ani değil) — gerçek itiş gibi.
                phase = (t - self._dist_start) / max(self._dist_dur, 1e-3)
                ramp = math.sin(min(phase, 1.0) * math.pi)  # 0→1→0
                bias = self._dist_mag * ramp
                if self._dist_axis == 'vertical':
                    out[k] = (dx, dy, dz + bias)
                else:
                    out[k] = (dx, dy - bias, dz)  # komşuya (–y) doğru
            return out

        if self._mode == 'static_obstacle':
            # obstacle_id sabit merkezde; diğerleri merkeze doğru yaklaşır.
            out = []
            for k, aid in enumerate(self._agent_ids):
                if aid == self._obs_id:
                    out.append((0.0, 0.0, 0.0))  # sabit engel = merkez
                else:
                    # başlangıç slotundan merkeze doğru ilerle
                    bx, by, bz = base[k]
                    h = math.hypot(bx, by)
                    if h > 1e-6:
                        step = min(self._approach * t, h)
                        bx -= bx / h * step
                        by -= by / h * step
                    out.append((bx, by, bz))
            return out

        return base  # normal

    def _publish(self) -> None:
        if not self._ensure_center():
            return
        if self._t0 is None:
            self._t0 = self.get_clock().now().nanoseconds * 1e-9
        t = self.get_clock().now().nanoseconds * 1e-9 - self._t0

        offs = self._compute_offsets(t)
        self._seq += 1
        fc = FormationCommand()
        fc.stamp = self.get_clock().now().to_msg()
        fc.sequence_num = self._seq
        fc.formation_type = self._ftype
        fc.center_x = self._cx
        fc.center_y = self._cy
        fc.center_z = self._cz
        fc.heading_deg = self._heading
        fc.spacing_m = self._spacing
        fc.use_current_centroid = False
        fc.use_current_altitude = False
        fc.rotate_towards_target = False
        fc.hold_after_reached = False
        fc.position_tolerance_m = 0.5
        fc.heading_tolerance_deg = 5.0
        fc.timeout_sec = 0.0
        fc.max_speed_mps = self._max_speed
        fc.agent_ids = [int(a) for a in self._agent_ids]
        fc.offset_x = [float(o[0]) for o in offs]
        fc.offset_y = [float(o[1]) for o in offs]
        fc.offset_z = [float(o[2]) for o in offs]
        fc.source_module = 'disturbance_publisher'
        self._pub.publish(fc)


def main(args=None):
    rclpy.init(args=args)
    node = DisturbancePublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
