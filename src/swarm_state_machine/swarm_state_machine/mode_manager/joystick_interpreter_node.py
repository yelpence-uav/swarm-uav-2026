"""MAVROS RC girdisini SwarmControlCommand mesajına dönüştüren düğüm.

MAVROS'un /mavros/manual_control/control mesajını okur, normalize
ederek SwarmControlCommand mesajına dönüştürür ve
/swarm/internal/control/command'a yayınlar.

Contract (§4.2):
  joystick_interpreter_node.py → /swarm/internal/control/command
    [SwarmControlCommand.msg]
  → proxy → /swarm/public/control/command
  → mode_manager/movement_mode.py / mode_manager/maneuver_mode.py

Yayın frekansı: 20-50 Hz (contract'ta belirtilmiş).

GCS arayüzünden gelen mod değişimleri ve formasyon komutları bu
node tarafından SwarmControlCommand'a gömülür.
"""

from collections import namedtuple

from mavros_msgs.msg import ManualControl
from sensor_msgs.msg import Joy

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_interfaces.msg import SwarmControlCommand
from swarm_interfaces.srv import TriggerMission

_MavrosManual = namedtuple('_MavrosManual', [
    'pitch', 'roll', 'yaw', 'throttle',
    'aux1', 'aux2', 'aux3', 'aux4', 'aux5', 'aux6',
])

_PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


class JoystickInterpreterNode(Node):
    """MAVROS ManualControl - SwarmControlCommand dönüştürücü."""

    # =========================================================================
    # FLYSKY FS-I6X KUMANDA KANAL VE EŞİK DEĞERİ AYARLARI
    # Kumanda switch kanallarını değiştirmek istediğinizde
    # buradaki sabitleri güncelleyebilirsiniz:
    # =========================================================================
    AUX_SAFETY_CHANNEL = 'aux1'         # Emniyet Kilidi (SwA)
    AUX_MODE_CHANNEL = 'aux2'          # Mod Seçimi (SwB)
    AUX_FORMATION_CHANNEL = 'aux3'     # Formasyon Seçimi (SwC)
    AUX_TAKEOFF_LAND_CHANNEL = 'aux4'  # Kalkış / İniş (SwD)

    # AUX 1 Emniyet Kilidi Eşik Değeri
    AUX_SAFETY_THRESH = 300            # >300  -> Emniyet AKTİF (komutlar çalışır)

    # AUX 3 Formasyon Seçimi Eşik Değerleri (-1000..+1000 MAVROS aralığı)
    AUX_FORMATION_THRESH_LOW = -300    # <-300 -> Ok Başı (1)
    AUX_FORMATION_THRESH_HIGH = 300    # >300  -> Çizgi (3)
    # -300..+300 arası -> V Formasyonu (2)

    # AUX 4 Kalkış / İniş Eşik Değerleri
    AUX_TAKEOFF_THRESH = 300           # >300  -> Takeoff
    AUX_LAND_THRESH = -300             # <-300 -> Land
    # =========================================================================

    def __init__(self) -> None:
        super().__init__('joystick_interpreter_node')

        self._declare_params()

        self._sequence_num = 0
        self._active_mode = SwarmControlCommand.MODE_SWARM_MOVEMENT
        self._formation_change_requested = False
        self._requested_formation = 0
        self._requested_spacing_m = 5.0
        self._last_aux3_formation = None
        self._last_aux4 = -1000  # SwD UP varsayılan
        self._safety_active = False
        init_cmd = SwarmControlCommand()
        init_cmd.mode = SwarmControlCommand.MODE_SWARM_MOVEMENT
        init_cmd.command_valid = False
        init_cmd.deadman_pressed = False
        self._last_cmd = init_cmd
        self._last_input_time = self.get_clock().now()

        self._setup_publishers()
        self._setup_subscribers()

        self._trigger_client = self.create_client(
            TriggerMission, '/swarm/mission/trigger'
        )

        self._timer = self.create_timer(
            1.0 / self._publish_hz,
            self._timer_callback,
        )

        self.get_logger().info(
            f'JoystickInterpreterNode basladi: {self._deadman_channel}'
        )

    def _call_trigger_mission(self, command_id: int) -> None:
        """Görev 2 için kalkış (1) veya iniş/iptal (4) servisini çağırır."""
        if not self._trigger_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().warn('TriggerMission servisi henüz hazır değil!')
            return
        req = TriggerMission.Request()
        req.mission_id = 2
        req.command = command_id
        req.team_id = 'team_1'
        self._trigger_client.call_async(req)
        cmd_name = 'START' if command_id == 1 else 'ABORT/LAND'
        self.get_logger().info(f'Kumandadan Görev 2 {cmd_name} tetiklendi!')

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanımlar ve okur."""
        self.declare_parameter('publish_hz', 30.0)
        self.declare_parameter('deadman_channel', 'aux1')
        self.declare_parameter('deadman_threshold', 0.5)
        self.declare_parameter('deadman_timeout_s', 0.5)
        self.declare_parameter('max_speed_mps', 2.0)
        self.declare_parameter('max_yaw_rate_deg_s', 30.0)
        self.declare_parameter('max_tilt_deg', 15.0)

        self._publish_hz = float(
            self.get_parameter('publish_hz').value
        )
        self._deadman_channel = str(
            self.get_parameter('deadman_channel').value
        )
        self._deadman_threshold = float(
            self.get_parameter('deadman_threshold').value
        )
        self._deadman_timeout_s = float(
            self.get_parameter('deadman_timeout_s').value
        )
        self._max_speed_mps = float(
            self.get_parameter('max_speed_mps').value
        )
        self._max_yaw_rate_deg_s = float(
            self.get_parameter('max_yaw_rate_deg_s').value
        )
        self._max_tilt_deg = float(
            self.get_parameter('max_tilt_deg').value
        )

    def _setup_publishers(self) -> None:
        """Aciklama: SwarmControlCommand publisher'ını oluşturur."""
        self._cmd_pub = self.create_publisher(
            SwarmControlCommand,
            '/swarm/internal/control/command',
            _PX4_QOS,
        )

    def _setup_subscribers(self) -> None:
        """MAVROS joystick ve ROS2 Joy girdi aboneliğini oluşturur."""
        self.create_subscription(
            ManualControl,
            '/mavros/manual_control/control',
            self._on_mavros_manual_control,
            _PX4_QOS,
        )
        self.create_subscription(
            Joy,
            '/joy',
            self._on_joy,
            10,
        )

    def _on_manual_control(self, msg: '_MavrosManual') -> None:
        """Normalize girdiyi SwarmControlCommand'a cevirir."""
        cmd = SwarmControlCommand()
        cmd.stamp = self.get_clock().now().to_msg()
        self._sequence_num += 1
        cmd.sequence_num = self._sequence_num

        deadman_value = self._read_aux_channel(msg)
        deadman_pressed = deadman_value > self._deadman_threshold
        cmd.command_valid = deadman_pressed
        cmd.deadman_pressed = deadman_pressed
        cmd.deadman_timeout_s = self._deadman_timeout_s

        # ======= EMNİYET KİLİDİ (AUX 1 - SwA) =======
        # SwA aktif değilse hiçbir komut çalışmaz (arm dahil)
        aux1_val = getattr(msg, self.AUX_SAFETY_CHANNEL, 0)
        self._safety_active = aux1_val > self.AUX_SAFETY_THRESH

        # Emniyet kilitliyken de aux durumlarını takip et.
        # Böylece kilit açıldığında sahte edge tetiklenmez.
        aux4_val = getattr(msg, self.AUX_TAKEOFF_LAND_CHANNEL, 0)
        aux3_val = getattr(msg, self.AUX_FORMATION_CHANNEL, 0)

        if not self._safety_active:
            # Aux durumlarını güncelle ama komut gönderme
            self._last_aux4 = aux4_val
            if aux3_val < self.AUX_FORMATION_THRESH_LOW:
                self._last_aux3_formation = SwarmControlCommand.FORMATION_OKBASI
            elif aux3_val > self.AUX_FORMATION_THRESH_HIGH:
                self._last_aux3_formation = SwarmControlCommand.FORMATION_CIZGI
            else:
                self._last_aux3_formation = SwarmControlCommand.FORMATION_UNKNOWN

            cmd.command_valid = False
            cmd.deadman_pressed = False
            cmd.takeoff = False
            cmd.land = False
            cmd.rtl = False
            cmd.emergency_stop = False
            cmd.pitch_cmd = 0.0
            cmd.roll_cmd = 0.0
            cmd.yaw_cmd = 0.0
            cmd.throttle_cmd = 0.0
            cmd.mode = self._active_mode
            cmd.formation_change_requested = False
            cmd.requested_formation = self._requested_formation
            cmd.requested_spacing_m = self._requested_spacing_m
            cmd.max_speed_mps = self._max_speed_mps
            cmd.max_yaw_rate_deg_s = self._max_yaw_rate_deg_s
            cmd.max_tilt_deg = self._max_tilt_deg
            cmd.source_module = 'joystick_interpreter'
            self._last_cmd = cmd
            self._last_input_time = self.get_clock().now()
            self._cmd_pub.publish(cmd)
            return

        # Mod Seçimi (AUX 2 - SwB: 0 -> Movement, 1 -> Maneuver)
        aux2_val = getattr(msg, self.AUX_MODE_CHANNEL, 0)
        if aux2_val > 0:
            self._active_mode = SwarmControlCommand.MODE_MANEUVER
        else:
            self._active_mode = SwarmControlCommand.MODE_SWARM_MOVEMENT
        cmd.mode = self._active_mode

        # Formasyon Seçimi (AUX 3 - SwC: Ok Başı / Formasyonsuz / Çizgi)
        # aux3_val yukarıda okundu
        if aux3_val < self.AUX_FORMATION_THRESH_LOW:
            current_aux3_formation = SwarmControlCommand.FORMATION_OKBASI
        elif aux3_val > self.AUX_FORMATION_THRESH_HIGH:
            current_aux3_formation = SwarmControlCommand.FORMATION_CIZGI
        else:
            current_aux3_formation = SwarmControlCommand.FORMATION_UNKNOWN  # ORTA = Formasyonsuz (0)

        if self._last_aux3_formation != current_aux3_formation:
            self._last_aux3_formation = current_aux3_formation
            self._requested_formation = current_aux3_formation
            self._formation_change_requested = True

        cmd.pitch_cmd = self._clamp(msg.pitch)
        cmd.roll_cmd = self._clamp(msg.roll)
        cmd.yaw_cmd = self._clamp(msg.yaw)
        cmd.throttle_cmd = self._clamp(msg.throttle * 2.0 - 1.0)

        cmd.takeoff = False
        cmd.land = False
        cmd.rtl = False
        cmd.emergency_stop = False

        # Kalkış / İniş Tetikleme (AUX 4 - SwD)
        # Şalteri AŞAĞI indirince (>300) KALKIŞ (Mission 1), YUKARI kaldırınca (<-300) İNİŞ (Mission 6)
        # aux4_val yukarıda okundu
        if aux4_val > self.AUX_TAKEOFF_THRESH and (
            self._last_aux4 <= self.AUX_TAKEOFF_THRESH
        ):
            cmd.takeoff = True
            self._call_trigger_mission(1)
        elif aux4_val < self.AUX_LAND_THRESH and (
            self._last_aux4 >= self.AUX_LAND_THRESH
        ):
            cmd.land = True
            self._call_trigger_mission(6)
        self._last_aux4 = aux4_val

        cmd.formation_change_requested = self._formation_change_requested
        cmd.requested_formation = self._requested_formation
        cmd.requested_spacing_m = self._requested_spacing_m

        if self._formation_change_requested:
            self._formation_change_requested = False

        cmd.max_speed_mps = self._max_speed_mps
        cmd.max_yaw_rate_deg_s = self._max_yaw_rate_deg_s
        cmd.max_tilt_deg = self._max_tilt_deg
        cmd.source_module = 'joystick_interpreter'

        self._last_cmd = cmd
        self._last_input_time = self.get_clock().now()
        self._cmd_pub.publish(cmd)

    def _timer_callback(self) -> None:
        """Kesintisiz 30 Hz komut akısı saglar."""
        if self._last_cmd is None:
            return

        now = self.get_clock().now()
        elapsed_s = (now - self._last_input_time).nanoseconds / 1e9

        cmd = SwarmControlCommand()
        cmd.stamp = now.to_msg()
        self._sequence_num += 1
        cmd.sequence_num = self._sequence_num

        cmd.mode = self._last_cmd.mode
        cmd.pitch_cmd = self._last_cmd.pitch_cmd
        cmd.roll_cmd = self._last_cmd.roll_cmd
        cmd.yaw_cmd = self._last_cmd.yaw_cmd
        cmd.throttle_cmd = self._last_cmd.throttle_cmd
        cmd.deadman_timeout_s = self._deadman_timeout_s

        if elapsed_s > self._deadman_timeout_s:
            return

        cmd.command_valid = self._last_cmd.command_valid
        cmd.deadman_pressed = self._last_cmd.deadman_pressed

        cmd.requested_formation = self._requested_formation
        cmd.requested_spacing_m = self._requested_spacing_m
        cmd.max_speed_mps = self._max_speed_mps
        cmd.max_yaw_rate_deg_s = self._max_yaw_rate_deg_s
        cmd.max_tilt_deg = self._max_tilt_deg
        cmd.source_module = 'joystick_interpreter'

        self._cmd_pub.publish(cmd)

    def _on_mavros_manual_control(self, msg: ManualControl) -> None:
        """MAVROS ManualControl'u normalize edip _on_manual_control'a verir.

        MAVLink MANUAL_CONTROL aralığı [-1000, 1000]; sürü [-1, 1].
        x=pitch, y=roll, r=yaw, z=throttle(0..1000). aux1..aux6 doğrudan.
        Aux aralıkları gerçek kumandayla kontrol edilmeli.
        """
        norm = _MavrosManual(
            pitch=self._clamp(msg.x / 1000.0),
            roll=self._clamp(msg.y / 1000.0),
            yaw=self._clamp(msg.r / 1000.0),
            throttle=self._clamp(msg.z / 1000.0, 0.0, 1.0),
            aux1=msg.aux1, aux2=msg.aux2, aux3=msg.aux3,
            aux4=msg.aux4, aux5=msg.aux5, aux6=msg.aux6,
        )
        self._on_manual_control(norm)

    def _on_joy(self, msg: Joy) -> None:
        """ROS2 sensor_msgs/Joy mesajını normalize edip _on_manual_control'a verir.

        FlySky FS-i6X Dongle Channel Mapping (DOĞRULANMIŞ):
        - axes[0]: Roll (Sağ stick LR)
        - axes[1]: Pitch (Sağ stick UD)
        - axes[2]: Throttle (Sol stick UD)
        - axes[3]: Yaw (Sol stick LR)
        - axes[4]: SwA (2-pos: Emniyet)
        - axes[5]: SwC (3-pos: Formasyon)
        - axes[6]: SwB (2-pos: Mod)
        - axes[7]: SwD (2-pos: Kalkış/İniş)
        """
        roll = msg.axes[0] if len(msg.axes) > 0 else 0.0
        pitch = msg.axes[1] if len(msg.axes) > 1 else 0.0
        throttle = msg.axes[2] if len(msg.axes) > 2 else 0.0
        yaw = msg.axes[3] if len(msg.axes) > 3 else 0.0

        # SwA (Emniyet Kilidi): Yukarı = Buton 1 (idx 0) veya axis 4 < -0.2 -> KİLİTLİ (-1000)
        #                        Aşağı  = Buton 2 (idx 1) veya axis 4 > 0.2 -> EMNİYET AÇIK (1000)
        btn_swa_up = bool(msg.buttons[0]) if len(msg.buttons) > 0 else False
        btn_swa_down = bool(msg.buttons[1]) if len(msg.buttons) > 1 else False
        axis_swa = msg.axes[4] if len(msg.axes) > 4 else 0.0

        if btn_swa_up or axis_swa < -0.2:
            aux1 = -1000
        elif btn_swa_down or axis_swa > 0.2:
            aux1 = 1000
        else:
            aux1 = -1000

        # SwB (Sürü Modu): Yukarı = Buton 3 (idx 2), Aşağı = Buton 4 (idx 3)
        btn_swb_down = bool(msg.buttons[3]) if len(msg.buttons) > 3 else False
        aux2 = 1000 if btn_swb_down else -1000

        # SwC (Formasyon 3-pos): En Üst = Buton 5 (idx 4), Orta = Nötr, En Aşağı = Buton 6 (idx 5)
        btn_swc_top = bool(msg.buttons[4]) if len(msg.buttons) > 4 else False
        btn_swc_bot = bool(msg.buttons[5]) if len(msg.buttons) > 5 else False
        if btn_swc_top:
            aux3 = -1000   # EN ÜST = Ok Başı (0)
        elif btn_swc_bot:
            aux3 = 1000    # EN AŞAĞI = Çizgi (2)
        else:
            aux3 = 0       # ORTA = Formasyonsuz (1)

        # SwD (Kalkış / İniş): Yukarı = Buton 7 (idx 6), Aşağı = Buton 8 (idx 7)
        btn_swd_down = bool(msg.buttons[7]) if len(msg.buttons) > 7 else False
        aux4 = 1000 if btn_swd_down else -1000

        aux5 = 0
        aux6 = 0

        norm = _MavrosManual(
            pitch=self._clamp(pitch),
            roll=self._clamp(roll),
            yaw=self._clamp(yaw),
            throttle=self._clamp(throttle),
            aux1=int(aux1), aux2=int(aux2), aux3=int(aux3),
            aux4=int(aux4), aux5=int(aux5), aux6=int(aux6),
        )
        self._on_manual_control(norm)

    def _read_aux_channel(self, msg: '_MavrosManual') -> float:
        """Yapılandırılmış deadman kanalını okur."""
        channel_map = {
            'aux1': getattr(msg, 'aux1', 0.0),
            'aux2': getattr(msg, 'aux2', 0.0),
            'aux3': getattr(msg, 'aux3', 0.0),
            'aux4': getattr(msg, 'aux4', 0.0),
            'aux5': getattr(msg, 'aux5', 0.0),
            'aux6': getattr(msg, 'aux6', 0.0),
        }
        return channel_map.get(self._deadman_channel, 0.0)

    @staticmethod
    def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
        """Değeri sınırlandırır."""
        return max(lo, min(hi, value))

    def set_control_mode(self, mode: int) -> None:
        """GCS mod değişimi."""
        self._active_mode = mode
        self.get_logger().info(
            f'Mod degisti: {mode}'
        )

    def set_formation(
        self, formation_type: int, spacing_m: float = 5.0
    ) -> None:
        """GCS formasyon değişimi."""
        self._formation_change_requested = True
        self._requested_formation = formation_type
        self._requested_spacing_m = spacing_m
        self.get_logger().info(
            f'Formasyon degisikligi: {formation_type}'
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = JoystickInterpreterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
