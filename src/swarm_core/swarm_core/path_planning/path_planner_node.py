# Copyright 2026 Yelpence
"""ROS 2 dogrusal rota planlama dugumu."""

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
from ..formation_control.formation_geometry import rotate_offset

_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


class PathPlannerNode(Node):
    """Dogrusal yoringe ureterek FormationCommand yayinlayan dugum."""

    def __init__(self) -> None:
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
        # Yay kipi eşiği: komutun SAF ROTASYON mu yoksa rotasyon+yer değiştirme
        # mi olduğunu ayırır (bkz. _yay_kur). Dönüşün başından ve sonundan
        # hesaplanan çıpalar bu kadar yakınsa "saf rotasyon" sayılır. Sürü
        # komutlar arasında bir miktar sürüklendiği için sıfır olamaz; slot
        # takip hatası mertebesinde (ölçüldü: durakta ort. 0.2 m, en kötü 0.6 m)
        # tutuldu. Büyütmek gerçek navigasyonu yanlışlıkla yay sanmaya, çok
        # küçültmek dönüşlerde yay kipinin hiç açılmamasına yol açar.
        self.declare_parameter('yay_capa_tolerans_m', 1.0)

        self._max_speed_mps = float(
            self.get_parameter('max_speed_mps').value
        )
        self._control_rate_hz = float(
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
        # Yay kipi durumu: çıpa (dönüşün etrafında yapıldığı sabit nokta) ve
        # slot ofsetlerinin ortalaması. None ise kip kapalıdır.
        self._yay_capa: tuple[float, float, float] | None = None
        self._yay_ortalama: tuple[float, float] = (0.0, 0.0)
        self._yay_capa_tolerans_m: float = float(
            self.get_parameter('yay_capa_tolerans_m').value
        )

        self.create_subscription(
            FormationCommand,
            '/swarm/path_planning/target',
            self._on_target_received,
            _RELIABLE_QOS
        )

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
        """Yeni bir hedef rota komutu alindiginda tetiklenir."""
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

        # Saf rotasyonda merkez düz çizgide yürütülmez; her tick'te heading'den
        # türetilir (bkz. _yay_kur). O yüzden yörünge listesi boş bırakılır.
        if self._yay_kur(msg, target_pos):
            self._waypoints = []
        else:
            self._waypoints = self._planner.generate_waypoints(
                self._last_pos, target_pos
            )
        self._current_cmd = msg
        self.get_logger().info(
            f'Yeni rota olusturuldu: {len(self._waypoints)} adim.'
        )

    @staticmethod
    def _shortest_delta_deg(current: float, target: float) -> float:
        """İki açı arasındaki en kısa yönlü farkı (-180, 180] verir."""
        return (target - current + 180.0) % 360.0 - 180.0

    def _yay_kur(self, msg, target_pos) -> bool:
        """Saf rotasyon mu? Öyleyse merkezin YAY çıpasını kurar."""
        self._yay_capa = None
        if self._current_heading_deg is None:
            return False
        hedef_h = float(msg.heading_deg)
        if abs(self._shortest_delta_deg(
                self._current_heading_deg, hedef_h)) < 1.0:
            return False                      # dönüş yok → normal seyir

        n = len(msg.offset_x)
        if n == 0:
            return False
        mx = sum(float(o) for o in msg.offset_x) / n
        my = sum(float(o) for o in msg.offset_y) / n
        if math.hypot(mx, my) < 1e-6:
            # Ofsetler zaten sıfır ortalamalı → merkez = centroid, dönüşte
            # merkezin kayması gerekmiyor; yay kipine de gerek yok.
            return False

        # Çıpa (dönüşün etrafında yapılacağı sabit nokta) iki uçtan hesaplanır:
        #   bitişten  : hedef merkez + döndür(ortalama, hedef heading)
        #   başlangıçtan: mevcut merkez + döndür(ortalama, mevcut heading)
        # Saf rotasyonda ikisi aynı noktadır. Farklıysa komut ayrıca yer
        # değiştirme istiyor demektir → yay kipi uygulanmaz.
        bx, by = rotate_offset(mx, my, math.radians(hedef_h))
        capa_bitis = (target_pos[0] + bx, target_pos[1] + by)
        sx, sy = rotate_offset(
            mx, my, math.radians(self._current_heading_deg))
        capa_bas = (self._last_pos[0] + sx, self._last_pos[1] + sy)
        if math.dist(capa_bitis, capa_bas) > self._yay_capa_tolerans_m:
            return False

        self._yay_capa = (capa_bitis[0], capa_bitis[1], float(target_pos[2]))
        self._yay_ortalama = (mx, my)
        return True

    def _yay_merkezi(self, heading_deg: float):
        """Yay kipinde o anki heading'e karşılık gelen merkez konumu."""
        mx, my = self._yay_ortalama
        dx, dy = rotate_offset(mx, my, math.radians(heading_deg))
        return (self._yay_capa[0] - dx,
                self._yay_capa[1] - dy,
                self._yay_capa[2])

    def _slew_limit_deg_s(self) -> float:
        """Formasyon boyutuna uyarlanmış güvenli dönüş hızı (derece/sn)."""
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
        """Ease-in/out açısal ivmesi (deg/s²), formasyon boyutuna uyarlı."""
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
        """Heading'i hedefe doğru YAMUK hız profiliyle yaklaştırır."""
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
        """Duzenli araliklarla sonraki ara noktayi yayinlar."""
        # _waypoints boş olabilir (yay kipi yerinde rotasyonda listeyi bilerek
        # boş bırakır) — o yüzden burada sadece komut var mı diye bakıyoruz.
        # Eskiden "not self._waypoints" guard'ı yay kipini bloke ediyor, sürü
        # yerinde dönemeyip navigasyonda takılıyordu. Boş liste durumu aşağıda
        # heading kontrolüyle zaten doğru yönetiliyor.
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

        # YAY KİPİ: merkez, heading ile AYNI tick'te türetilir. Böylece ikisi
        # asla desenkron olmaz ve centroid dönüş boyunca sabit kalır (şartname:
        # "sürünün sabit bir merkez etrafında rotasyon gerçekleştirmesi").
        if self._yay_capa is not None:
            next_pos = self._yay_merkezi(self._current_heading_deg)
            self._last_pos = next_pos
            if abs(self._shortest_delta_deg(
                    self._current_heading_deg, target_heading)) < 1e-3:
                route_just_completed = True
                self._yay_capa = None

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
    rclpy.init(args=args)
    node = PathPlannerNode()
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
