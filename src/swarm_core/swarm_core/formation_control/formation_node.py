"""Dağıtık formasyon kontrol node'u — her drone'da ayrı çalışır.

İşleyiş:
    1. mission_fsm /swarm/internal/formation/target'a FormationCommand
       yayınlar; proxy /swarm/public/formation/target'a iletir.
    2. swarm_fsm /swarm/internal/state'e SwarmState yayınlar; proxy
       /swarm/public/state'e iletir.
    3. Bu node /swarm/public/... aboneliklerinden mesajları alır,
       kendi agent_id'sine göre rank bulur, formation_geometry ile
       setpoint hesaplar ve /drone_{id}/control/setpoint üzerinden
       lokal px4_interface'e yayınlar.

Topic kuralları (network_proxy):
    - Yayıncılar: /swarm/internal/...
    - Aboneler: /swarm/public/...
    - Lokal (drone içi): /drone_{id}/...
    AgentSetpoint LOKAL kalır, proxy'den geçmez.

Aktif ajan listesi (tek kaynak: swarm_fsm):
    swarm_fsm, SwarmState.active_agent_ids alanını doldurur.
    Filtre swarm_fsm'de uygulanır: healthy + origin_synced +
    IN_SWARM/EXECUTING_TASK + stale değil. Bu node listeyi direkt okur,
    tekrar filtrelemez (tek kaynak ilkesi, kod tekrarı yok).

Spacing önceliği:
    1. FormationCommand.spacing_m > 0 ise (QR/YKİ'den) kullan.
    2. Aksi halde YAML'daki default_spacing_m'e düş.

Merkez çözümleme önceliği:
    1. use_current_centroid=true ise SwarmState.centroid_x/y kullan.
    2. use_current_altitude=true ise SwarmState.centroid_z kullan.
    3. Aksi halde FormationCommand.center_x/y/z kullan.
    SwarmState henüz gelmemişse her durumda mesajdaki değerlere düşer.
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
    SwarmState,
)

from .formation_geometry import (
    compute_setpoint,
    FORMATION_CIZGI,
    FORMATION_OKBASI,
    FORMATION_V,
)


# mission_fsm RELIABLE yayınlıyor.
_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


# AgentSetpoint yüksek frekanslı; BEST_EFFORT yeterli.
_BEST_EFFORT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


# Desteklenen formasyon tipleri.
_SUPPORTED_FORMATIONS = (
    FORMATION_OKBASI,
    FORMATION_V,
    FORMATION_CIZGI,
)


# Setpoint yayınlanmayacak pasif sürü durumları (Decision C).
# Bu durumlarda misyon yok veya drone'lar yerde/RTL modunda.
_PASSIVE_SWARM_STATES = frozenset({
    SwarmState.SWARM_UNKNOWN,
    SwarmState.SWARM_IDLE,
    SwarmState.SWARM_LANDING,
    SwarmState.SWARM_RTL,
    SwarmState.SWARM_FAILSAFE,
    SwarmState.SWARM_MISSION_COMPLETE,
})


class FormationControlNode(Node):
    """
    Tek drone için dağıtık formasyon setpoint hesaplayıcısı.

    Her drone bu node'u kendi çalıştırır. mission_fsm tek bir
    FormationCommand yayınladığında tüm drone'lar aynı mesajı alır,
    ama her biri kendi agent_id'sine göre farklı setpoint üretir.
    Merkezi koordinasyon yoktur.
    """

    def __init__(self) -> None:
        """Node'u başlatır ve ROS2 arayüzlerini kurar."""
        super().__init__('formation_control')

        self._declare_params()

        # State — gelen mesajlardan doldurulur.
        self._current_formation: FormationCommand | None = None
        self._latest_swarm_state: SwarmState | None = None
        self._active_agent_ids: list[int] = []
        self._sequence_num: int = 0

        # Bu drone'un anlık pozisyonu ve uçuş kalitesi (AgentStatus'tan).
        self._current_pos_x: float = 0.0
        self._current_pos_y: float = 0.0
        self._current_pos_z: float = 0.0
        self._pos_valid: bool = False
        self._oscillating: bool = False

        # Feed-forward için centroid hız tahmini.
        self._centroid_vel_x: float = 0.0
        self._centroid_vel_y: float = 0.0
        self._centroid_vel_z: float = 0.0
        self._prev_centroid_x: float = 0.0
        self._prev_centroid_y: float = 0.0
        self._prev_centroid_z: float = 0.0
        self._prev_centroid_time: float | None = None

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
        """ROS2 parametrelerini tanımlar ve okur.

        Kullanım:
            ros2 run swarm_core formation_node --ros-args
                -p agent_id:=1
                --params-file config/formations.yaml
        """
        self.declare_parameter('agent_id', 1)
        self.declare_parameter('default_spacing_m', 5.0)
        self.declare_parameter('alpha_deg', 30.0)
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('position_tolerance_m', 0.5)
        self.declare_parameter('heading_tolerance_deg', 5.0)
        self.declare_parameter('max_speed_mps', 3.0)
        self.declare_parameter('svt_gain', 0.2)
        self.declare_parameter('svt_threshold_m', 2.0)

        self._agent_id: int = int(
            self.get_parameter('agent_id').value
        )
        self._default_spacing_m: float = float(
            self.get_parameter('default_spacing_m').value
        )
        self._alpha_deg: float = float(
            self.get_parameter('alpha_deg').value
        )
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
        self._svt_gain: float = float(
            self.get_parameter('svt_gain').value
        )
        self._svt_threshold_m: float = float(
            self.get_parameter('svt_threshold_m').value
        )
        self._alpha_rad: float = math.radians(self._alpha_deg)

    def _setup_publishers(self) -> None:
        """Publisher'ları oluşturur: AgentSetpoint."""
        self._setpoint_pub = self.create_publisher(
            AgentSetpoint,
            f'/drone_{self._agent_id}/control/setpoint',
            _BEST_EFFORT_QOS,
        )

    def _setup_subscribers(self) -> None:
        """Abonelikleri oluşturur: FormationCommand, SwarmState.

        İkisi de proxy'den geçtiği için /swarm/public/... prefix'i
        kullanılır (network_proxy Kural 2).
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
        # Bu drone'un pozisyonu — lokal, proxy'den geçmez (Kural 3).
        self.create_subscription(
            AgentStatus,
            f'/swarm/agent/drone{self._agent_id}/telemetry',
            self._on_agent_status,
            _BEST_EFFORT_QOS,
        )

    def _on_formation_command(self, msg: FormationCommand) -> None:
        """
        Yeni formasyon komutu geldiğinde son komutu saklar.

        Args:
            msg (FormationCommand): mission_fsm'den gelen komut.
        """
        self._current_formation = msg
        self.get_logger().info(
            f'FormationCommand alindi: type={msg.formation_type}, '
            f'spacing={msg.spacing_m:.1f}m, '
            f'heading={msg.heading_deg:.1f}deg, '
            f'center=({msg.center_x:.1f}, {msg.center_y:.1f}, '
            f'{msg.center_z:.1f})',
            throttle_duration_sec=1.0,
        )

    def _on_swarm_state(self, msg: SwarmState) -> None:
        """
        Sürü durumunu işler: aktif ajan listesi + güncel centroid.

        Aktif filtre swarm_fsm tarafından uygulanmış; bu node
        SwarmState.active_agent_ids alanını direkt okur.
        Rank ataması en küçük agent_id'den büyüğüne doğru sıralıdır.

        Args:
            msg (SwarmState): swarm_fsm'den gelen sürü durumu.
        """
        # Feed-forward: centroid hızını ardışık mesajlardan türet.
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
            # N değişince centroid anında kayar → FF spike önle.
            self._prev_centroid_time = None
            self._centroid_vel_x = 0.0
            self._centroid_vel_y = 0.0
            self._centroid_vel_z = 0.0
            self.get_logger().info(
                f'Aktif ajan listesi guncellendi: {active_ids}'
            )

    def _on_agent_status(self, msg: AgentStatus) -> None:
        """Bu drone'un anlık pozisyonunu ve uçuş kalitesini saklar.

        Args:
            msg (AgentStatus): Lokal agent_fsm_node'dan gelen durum.
        """
        self._current_pos_x = float(msg.pos_x)
        self._current_pos_y = float(msg.pos_y)
        self._current_pos_z = float(msg.pos_z)
        self._pos_valid = True
        self._oscillating = msg.oscillation_detected

    def _compute_velocity(
        self,
        target_x: float,
        target_y: float,
        target_z: float,
        max_speed: float,
        use_ff_xy: bool = False,
        use_ff_z: bool = False,
    ) -> tuple[float, float, float]:
        """Feed-forward + SVT birleşik hız vektörü hesaplar.

        Feed-forward: sadece merkez hareketliyse (use_current_centroid/
        use_current_altitude) centroid hızı eklenir. Sabit merkezde
        centroid yakınsama hareketi spurious FF oluşturmaması için
        flag'e bağlıdır.

        SVT (Soft Virtual Tether): drone hedef slotundan uzaklaşırsa
        elastik düzeltme kuvveti uygular → slot hatası azalır.

        Args:
            target_x: Hedef slot NED X, metre.
            target_y: Hedef slot NED Y, metre.
            target_z: Hedef slot NED Z, metre.
            max_speed: Hız sınırı, m/s.
            use_ff_xy: True ise XY ekseninde centroid hızı eklenir.
            use_ff_z: True ise Z ekseninde centroid hızı eklenir.

        Returns:
            tuple: (vx, vy, vz) NED hız, m/s.
        """
        vx = self._centroid_vel_x if use_ff_xy else 0.0
        vy = self._centroid_vel_y if use_ff_xy else 0.0
        vz = self._centroid_vel_z if use_ff_z else 0.0

        if self._pos_valid and not self._oscillating:
            ex = target_x - self._current_pos_x
            ey = target_y - self._current_pos_y
            ez = target_z - self._current_pos_z
            err = math.sqrt(ex * ex + ey * ey + ez * ez)
            if err > self._svt_threshold_m:
                vx += self._svt_gain * ex
                vy += self._svt_gain * ey
                vz += self._svt_gain * ez

        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        if speed > max_speed:
            scale = max_speed / speed
            vx *= scale
            vy *= scale
            vz *= scale

        return vx, vy, vz

    def _resolve_spacing(self, msg: FormationCommand) -> float:
        """
        Geçerli spacing değerini belirler.

        Args:
            msg (FormationCommand): Aktif formasyon komutu.

        Returns:
            float: QR'dan gelen spacing_m geçerliyse onu,
                aksi halde YAML default'unu döndürür.
        """
        if msg.spacing_m > 0.0:
            return float(msg.spacing_m)
        return self._default_spacing_m

    def _resolve_center(
        self,
        msg: FormationCommand,
    ) -> tuple[float, float, float]:
        """
        Formasyon merkezini, mesajdaki flaglere göre belirler.

        Öncelik sırası:
            1. use_current_centroid=true → SwarmState.centroid_x/y
            2. use_current_altitude=true → SwarmState.centroid_z
            3. Aksi halde mesajdaki center_x/y/z

        SwarmState henüz alınmamışsa (state is None) güvenli düşüş:
        mesajdaki değerleri kullan. Bu durum normalde olmaz çünkü
        _publish_setpoint zaten active_agent_ids boşsa erken çıkar.

        Args:
            msg (FormationCommand): Aktif formasyon komutu.

        Returns:
            tuple: (center_x, center_y, center_z) NED, metre.
        """
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
        """
        Bu drone'un aktif liste içindeki rank'ini döndürür.

        Returns:
            int | None: rank (0-based) veya bu drone listede
                yoksa None.
        """
        try:
            return self._active_agent_ids.index(self._agent_id)
        except ValueError:
            return None

    def _publish_setpoint(self) -> None:
        """
        Periyodik setpoint hesaplama ve AgentSetpoint yayını.

        Şu durumlarda hiçbir mesaj yayınlanmaz:
            - Henüz FormationCommand gelmemişse.
            - Aktif ajan listesi boşsa.
            - Sürü pasif durumda (IDLE, LANDING, RTL, FAILSAFE vb.).
            - Misyon aktif değilse.
            - Bu drone aktif listede yoksa.
            - formation_type desteklenmiyorsa.
        """
        msg = self._current_formation
        if msg is None or not self._active_agent_ids:
            return

        # Decision C: pasif sürü durumlarında setpoint yayınlama.
        state = self._latest_swarm_state
        if state is not None:
            if not state.mission_active:
                return
            if state.swarm_state in _PASSIVE_SWARM_STATES:
                return

        rank = self._find_rank()
        if rank is None:
            return

        if msg.formation_type not in _SUPPORTED_FORMATIONS:
            self.get_logger().warn(
                f'Desteklenmeyen formation_type='
                f'{msg.formation_type}, setpoint yayinlanmiyor',
                throttle_duration_sec=2.0,
            )
            return

        spacing = self._resolve_spacing(msg)
        center_x, center_y, center_z = self._resolve_center(msg)
        total = len(self._active_agent_ids)
        heading_rad = math.radians(msg.heading_deg)

        try:
            x, y, z = compute_setpoint(
                center_x=center_x,
                center_y=center_y,
                center_z=center_z,
                formation_type=int(msg.formation_type),
                rank=rank,
                total=total,
                spacing=spacing,
                alpha_rad=self._alpha_rad,
                heading_rad=heading_rad,
            )
        except ValueError as e:
            self.get_logger().error(
                f'Setpoint hesaplanamadi: {e}',
                throttle_duration_sec=1.0,
            )
            return

        max_speed = (
            float(msg.max_speed_mps)
            if msg.max_speed_mps > 0.0
            else self._max_speed_mps
        )
        vx, vy, vz = self._compute_velocity(
            x, y, z, max_speed,
            use_ff_xy=msg.use_current_centroid,
            use_ff_z=msg.use_current_altitude,
        )
        out = self._build_setpoint_msg(msg, x, y, z, vx, vy, vz)
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
    ) -> AgentSetpoint:
        """
        Hesaplanmış pozisyondan AgentSetpoint mesajı üretir.

        Args:
            cmd (FormationCommand): Aktif formasyon komutu.
            x (float): Hedef NED X, metre.
            y (float): Hedef NED Y, metre.
            z (float): Hedef NED Z, metre.
            vx (float): FF+SVT hızı NED X, m/s.
            vy (float): FF+SVT hızı NED Y, m/s.
            vz (float): FF+SVT hızı NED Z, m/s.

        Returns:
            AgentSetpoint: Doldurulmuş mesaj.
        """
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
        out.velocity_valid = True
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
    """ROS2 entry point — node'u başlatır ve spin eder."""
    rclpy.init(args=args)
    node = FormationControlNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
