"""ROS 2 doğrusal rota planlama düğümü (Path Planner Node)."""

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_interfaces.msg import FormationCommand
from .linear_trajectory import LinearTrajectoryPlanner

_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


class PathPlannerNode(Node):
    """Doğrusal yörünge üreterek FormationCommand yayınlayan düğüm."""

    def __init__(self) -> None:
        """Düğümü başlatır ve parametreleri okur."""
        super().__init__('path_planner_node')

        self.declare_parameter('max_speed_mps', 3.0)
        self.declare_parameter('control_rate_hz', 5.0)
        # Heading, merkez gibi rampalanır: hedefe bakan açı tek tick'te
        # atanırsa (özellikle sonraki QR'a ~180° dönüşte) formasyon rijit
        # snap yapıp savruluyordu. Bu sınır dönüşü saniyelere yayar.
        self.declare_parameter('max_heading_slew_deg_s', 90.0)
        # Formasyon rotasyonunda EN DIŞTAKİ dronun teğetsel hız tavanı (m/s).
        # Rijit dönüşte merkeze r uzaklıktaki dron v = ω·r hızıyla yay çizer;
        # sabit bir açısal hız, formasyon büyüdükçe (spacing QR'dan gelir) bu
        # dronu max_speed'in üstüne zorlar → yetişemez, geride kalır, formasyon
        # çarpılır, dönüş bitince açığı kapatmak için fırlar (savrulma).
        # Açısal sınırı buradan türetmek her spacing'de güvenli tutar. Değer
        # max_speed'in yarısı seçilir: kalan yarı, dönüş sırasında formasyonu
        # tutan düzeltmelere (rüzgâr, komşu, CA) pay bırakır.
        self.declare_parameter('rot_tangential_speed_mps', 1.5)
        # Rotasyon başında dönüş, açısal hızı 0'dan tavana TEK adımda çıkarıyordu;
        # dron duruyorken bir anda "tangansiyel hızda koş" komutu alıyor, fiziksel
        # olarak o hıza anında çıkamadığı için geride kalıp sonra fırlıyordu
        # (savrulma; ölçüldü: dönüş başında kanat dronu gereken hızın %34'ünde).
        # Açısal hızı bir İVME sınırıyla rampalarsak (ease-in/out) dönüş yumuşak
        # başlar ve biter; dron hiç geride kalmaz. İvme de hız gibi kanat dronun
        # tangansiyel ivmesinden türetilir → her formasyon boyutunda güvenli.
        self.declare_parameter('rot_tangential_accel_mps2', 0.8)

        self._max_speed_mps: float = float(
            self.get_parameter('max_speed_mps').value
        )
        self._control_rate_hz: float = float(
            self.get_parameter('control_rate_hz').value
        )
        self._max_heading_slew_deg_s: float = float(
            self.get_parameter('max_heading_slew_deg_s').value
        )
        self._rot_tangential_speed_mps: float = float(
            self.get_parameter('rot_tangential_speed_mps').value
        )
        self._rot_tangential_accel_mps2: float = float(
            self.get_parameter('rot_tangential_accel_mps2').value
        )
        # Ease-in/out için o an uygulanan açısal hız (deg/s). Dönüş bitince
        # (heading hedefe oturunca) sıfırlanır → sonraki dönüş yeniden yumuşak
        # başlar.
        self._current_slew_rate: float = 0.0

        self._planner = LinearTrajectoryPlanner(
            max_speed_mps=self._max_speed_mps,
            control_rate_hz=self._control_rate_hz
        )

        self._waypoints: list[tuple[float, float, float]] = []
        self._current_cmd: FormationCommand | None = None
        self._last_pos: tuple[float, float, float] | None = None
        # Uygulanmakta olan (rampalanmış) heading. İlk komutta hedefe eşitlenir
        # ki formasyon kurulurken yerinde dönme olmasın; sonraki komutlarda
        # bu değerden hedefe doğru sınırlı hızla ilerler.
        self._current_heading_deg: float | None = None

        # Hedef koordinatı dinler (Örn: mission_fsm'den)
        self.create_subscription(
            FormationCommand,
            '/swarm/path_planning/target',
            self._on_target_received,
            _RELIABLE_QOS
        )

        # Interpolasyon yapılmış ara noktaları formation_control'e gönderir
        self._cmd_pub = self.create_publisher(
            FormationCommand,
            '/swarm/internal/formation/target',
            _RELIABLE_QOS
        )

        self._timer = self.create_timer(
            1.0 / self._control_rate_hz,
            self._timer_callback
        )

        self.get_logger().info('Path Planner Node baslatildi.')

    def _on_target_received(self, msg: FormationCommand) -> None:
        """Yeni bir hedef rota komutu alındığında tetiklenir.

        Args:
            msg (FormationCommand): Hedef konum ve konfigürasyon verisi.
        """
        if self._last_pos is None:
            self._last_pos = (msg.center_x, msg.center_y, msg.center_z)
        if self._current_heading_deg is None:
            # Rampa, İLK komutun heading'inden başlar (varsayım yok, mesajdan
            # okunur → node yeniden başlasa da doğru yerden devam eder).
            # Sürünün ilk komutu dizilişi KORUYAN komuttur (orchestrator taze
            # snapshot'ta heading=0 yayınlar) → rampa doğal olarak 0'dan başlar
            # ve rotasyona yumuşak geçer.
            self._current_heading_deg = float(msg.heading_deg)

        target_pos = (msg.center_x, msg.center_y, msg.center_z)

        self._waypoints = self._planner.generate_waypoints(
            self._last_pos, target_pos
        )
        self._current_cmd = msg
        self.get_logger().info(
            f'Yeni rota olusturuldu. Toplam {len(self._waypoints)} adim.'
        )

    @staticmethod
    def _shortest_delta_deg(current: float, target: float) -> float:
        """İki açı arasındaki en kısa yönlü farkı (-180, 180] verir."""
        return (target - current + 180.0) % 360.0 - 180.0

    def _slew_limit_deg_s(self) -> float:
        """Formasyon boyutuna uyarlanmış güvenli dönüş hızı (derece/sn).

        Rijit rotasyonda merkeze r uzaklıktaki dron v = ω·r ile yay çizer. En
        dıştaki dronun hızı rot_tangential_speed_mps'i aşmasın diye açısal hız
        ω_max = v_safe / r_max ile sınırlanır. r_max, komuttaki slot
        ofsetlerinden gelir (ofsetler zaten formasyon MERKEZİNE göredir; dönüş
        de o merkez etrafındadır) → yeni veri/abonelik gerekmez.

        Böylece spacing QR'dan ne gelirse gelsin (5 m, 8 m, 15 m…) dönüş hızı
        kendiliğinden ölçeklenir: formasyon büyüdükçe yavaşlar, kanat dronlar
        her zaman yetişebilir. Sabit bir açısal hız büyük formasyonda dronu
        max_speed'in üstüne zorlayıp savrulmaya yol açıyordu.

        Ofset yoksa/çok küçükse (tek dron, dejenere formasyon) yapılandırılmış
        tavan kullanılır. Sonuç asla max_heading_slew_deg_s'i aşmaz.
        """
        cmd = self._current_cmd
        if cmd is None:
            return self._max_heading_slew_deg_s
        r_max = 0.0
        for ox, oy in zip(cmd.offset_x, cmd.offset_y):
            r_max = max(r_max, math.hypot(float(ox), float(oy)))
        if r_max < 0.5 or self._rot_tangential_speed_mps <= 0.0:
            return self._max_heading_slew_deg_s
        w_deg_s = math.degrees(self._rot_tangential_speed_mps / r_max)
        return min(self._max_heading_slew_deg_s, w_deg_s)

    def _slew_accel_deg_s2(self) -> float:
        """Ease-in/out açısal ivmesi (deg/s²), formasyon boyutuna uyarlı.

        Kanat dronun tangansiyel ivmesi rot_tangential_accel'i aşmasın diye
        a_ang = a_tan / r_max. Böylece dron sıfırdan tangansiyel hıza YUMUŞAK
        çıkar; ani başlangıç savrulmayı tetikliyordu. Ofset yoksa sınır konmaz.
        """
        cmd = self._current_cmd
        if cmd is None or self._rot_tangential_accel_mps2 <= 0.0:
            return 1e9
        r_max = 0.0
        for ox, oy in zip(cmd.offset_x, cmd.offset_y):
            r_max = max(r_max, math.hypot(float(ox), float(oy)))
        if r_max < 0.5:
            return 1e9
        return math.degrees(self._rot_tangential_accel_mps2 / r_max)

    def _step_heading_deg(self, current: float, target: float) -> float:
        """Heading'i hedefe doğru YAMUK hız profiliyle yaklaştırır.

        Sabit adım yerine açısal hız (_current_slew_rate) bir ivme sınırıyla
        rampalanır:
          · ease-in : hız her tick a·dt kadar artar → yumuşak başlangıç
          · seyir   : hız tavana (slew_limit) oturur
          · ease-out: hedefe yaklaşınca hız √(2·a·Δ) ile sınırlanır → hedefte
                      tam durur, aşmaz
        Böylece dron dönüş başında da sonunda da fırlamaz (rijit rotasyon).
        """
        delta = self._shortest_delta_deg(current, target)
        if abs(delta) <= 1e-3:
            self._current_slew_rate = 0.0
            return target

        accel = self._slew_accel_deg_s2()
        slew_max = self._slew_limit_deg_s()
        # ease-out tavanı: kalan açıda 0'a inebilecek en yüksek hız.
        stop_rate = math.sqrt(2.0 * accel * abs(delta)) if accel < 1e8 \
            else slew_max
        rate_target = min(slew_max, stop_rate)
        # ease-in: hızı ivme adımıyla hedefe rampala, sonra tavanla kırp.
        self._current_slew_rate = min(
            rate_target, self._current_slew_rate + accel / self._control_rate_hz
        )

        max_step = self._current_slew_rate / self._control_rate_hz
        if abs(delta) <= max_step:
            self._current_slew_rate = 0.0
            return target
        stepped = current + math.copysign(max_step, delta)
        return (stepped + 180.0) % 360.0 - 180.0

    def _timer_callback(self) -> None:
        """Düzenli aralıklarla sonraki ara noktayı yayınlar."""
        if self._current_cmd is None:
            return

        target_heading = float(self._current_cmd.heading_deg)
        heading_settled = (
            self._current_heading_deg is not None
            and abs(self._shortest_delta_deg(
                self._current_heading_deg, target_heading)) < 1e-3
        )

        # Merkez rampası bittiyse ama heading hâlâ dönüyorsa yayına devam et:
        # aksi halde yerinde büyük dönüşlerde heading yarıda snap'lerdi.
        if not self._waypoints and heading_settled:
            return

        route_just_completed = False
        if self._waypoints:
            next_pos = self._waypoints.pop(0)
            self._last_pos = next_pos
            route_just_completed = not self._waypoints
        else:
            next_pos = self._last_pos

        self._current_heading_deg = self._step_heading_deg(
            self._current_heading_deg, target_heading
        )

        # Komutu kopyala ve merkez koordinatını güncelle
        out_msg = FormationCommand()
        out_msg.stamp = self.get_clock().now().to_msg()
        out_msg.sequence_num = self._current_cmd.sequence_num
        out_msg.formation_type = self._current_cmd.formation_type
        out_msg.center_x = float(next_pos[0])
        out_msg.center_y = float(next_pos[1])
        out_msg.center_z = float(next_pos[2])
        out_msg.heading_deg = float(self._current_heading_deg)
        out_msg.spacing_m = float(self._current_cmd.spacing_m)
        out_msg.use_current_centroid = self._current_cmd.use_current_centroid
        out_msg.use_current_altitude = self._current_cmd.use_current_altitude
        out_msg.rotate_towards_target = (
            self._current_cmd.rotate_towards_target
        )
        out_msg.hold_after_reached = self._current_cmd.hold_after_reached
        out_msg.agent_ids = self._current_cmd.agent_ids
        out_msg.offset_x = self._current_cmd.offset_x
        out_msg.offset_y = self._current_cmd.offset_y
        out_msg.offset_z = self._current_cmd.offset_z
        out_msg.position_tolerance_m = float(
            self._current_cmd.position_tolerance_m
        )
        out_msg.heading_tolerance_deg = float(
            self._current_cmd.heading_tolerance_deg
        )
        out_msg.timeout_sec = float(self._current_cmd.timeout_sec)
        out_msg.max_speed_mps = float(self._current_cmd.max_speed_mps)
        out_msg.source_module = 'path_planning'

        self._cmd_pub.publish(out_msg)

        if route_just_completed:
            self.get_logger().info('Rota tamamlandi, hedefe ulasildi.')


def main(args=None) -> None:
    """ROS 2 giriş noktası."""
    rclpy.init(args=args)
    node = PathPlannerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
