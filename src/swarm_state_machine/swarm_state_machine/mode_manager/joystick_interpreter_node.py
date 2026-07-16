"""joystick_interpreter_node.py — MAVROS RC girdisi to SwarmControlCommand.

MAVROS'un /mavros/manual_control/control mesajını okur, normalize
ederek SwarmControlCommand mesajına dönüştürür ve
/swarm/internal/control/command'a yayınlar.
(uXRCE-DDS yolu SITL kanıtı sonrası söküldü, 2026-07-17.)

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

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from mavros_msgs.msg import ManualControl
from swarm_interfaces.msg import SwarmControlCommand

# MAVROS ManualControl -> normalize alanlar (cevirici tek tip gorsun diye).
# Araliklar SITL'de dogrulanmali.
_MavrosManual = namedtuple('_MavrosManual', [
    'pitch', 'roll', 'yaw', 'throttle',
    'aux1', 'aux2', 'aux3', 'aux4', 'aux5', 'aux6',
])

# Sensor-tipi girdi: BEST_EFFORT, VOLATILE QoS.
_PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


class JoystickInterpreterNode(Node):
    """MAVROS ManualControl → SwarmControlCommand dönüştürücü.

    RC kumanda (FLYSKY FS-i6X) sinyalleri PX4→MAVROS üzerinden
    ManualControl olarak yayınlanır. Bu node:
    1. Girdileri normalize eder [-1.0, +1.0].
    2. Deadman switch durumunu okur.
    3. SwarmControlCommand mesajı oluşturur.
    4. /swarm/internal/control/command'a yayınlar.

    Mod değişimi ve formasyon komutları GCS web arayüzünden ROS2
    topic/service üzerinden gelir ve bu node tarafından
    SwarmControlCommand'a gömülür.
    """

    def __init__(self) -> None:
        super().__init__('joystick_interpreter_node')

        self._declare_params()

        self._sequence_num: int = 0

        # Arayüzden gelen mod ve formasyon bilgileri
        self._active_mode: int = SwarmControlCommand.MODE_SWARM_MOVEMENT
        self._formation_change_requested: bool = False
        self._requested_formation: int = 0
        self._requested_spacing_m: float = 5.0

        self._setup_publishers()
        self._setup_subscribers()

        self.get_logger().info(
            f'JoystickInterpreterNode başladı: '
            f'deadman_ch={self._deadman_channel} '
            f'deadman_thr={self._deadman_threshold:.2f}'
        )

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
        self._deadman_channel: str = str(
            self.get_parameter('deadman_channel').value
        )
        self._deadman_threshold: float = float(
            self.get_parameter('deadman_threshold').value
        )
        self._deadman_timeout_s: float = float(
            self.get_parameter('deadman_timeout_s').value
        )
        self._max_speed_mps: float = float(
            self.get_parameter('max_speed_mps').value
        )
        self._max_yaw_rate_deg_s: float = float(
            self.get_parameter('max_yaw_rate_deg_s').value
        )
        self._max_tilt_deg: float = float(
            self.get_parameter('max_tilt_deg').value
        )

    def _setup_publishers(self) -> None:
        """SwarmControlCommand publisher'ını oluşturur."""
        self._cmd_pub = self.create_publisher(
            SwarmControlCommand,
            '/swarm/internal/control/command',
            10,
        )

    def _setup_subscribers(self) -> None:
        """MAVROS joystick girdi aboneliğini oluşturur.

        Topic namespace'i launch'ta netleşecek (Faz 6); şimdilik
        global /mavros/manual_control/control.
        """
        self.create_subscription(
            ManualControl,
            '/mavros/manual_control/control',
            self._on_mavros_manual_control,
            _PX4_QOS,
        )

    def _on_manual_control(self, msg: '_MavrosManual') -> None:
        """Normalize girdiyi SwarmControlCommand'a çevirir.

        _MavrosManual alanları (PX4 konvansiyonuyla ayni):
          pitch: -1.0 (geri) → +1.0 (ileri)
          roll:  -1.0 (sol)  → +1.0 (sağ)
          yaw:   -1.0 (sol)  → +1.0 (sağ)
          throttle: 0.0 (min) → +1.0 (max) — normalize edilir [-1, +1]
          aux1..aux6: -1.0 → +1.0 (switch/dial kanalları)

        Args:
            msg: Normalize girdi (_MavrosManual).
        """
        cmd = SwarmControlCommand()
        cmd.stamp = self.get_clock().now().to_msg()
        self._sequence_num += 1
        cmd.sequence_num = self._sequence_num

        # ─── Deadman switch ───
        deadman_value = self._read_aux_channel(msg)
        deadman_pressed = deadman_value > self._deadman_threshold
        cmd.command_valid = True
        cmd.deadman_pressed = deadman_pressed
        cmd.deadman_timeout_s = self._deadman_timeout_s

        # ─── Mod ───
        cmd.mode = self._active_mode

        # ─── Normalize girdiler ───
        cmd.pitch_cmd = self._clamp(msg.pitch)
        cmd.roll_cmd = self._clamp(msg.roll)
        cmd.yaw_cmd = self._clamp(msg.yaw)
        # PX4 throttle: 0→1, sürü konvansiyonu: -1→+1
        cmd.throttle_cmd = self._clamp(msg.throttle * 2.0 - 1.0)

        # ─── Ayrık komutlar ───
        # Takeoff/Land/RTL/Emergency butonlar aux kanallarından
        # veya GCS'den gelir. Şimdilik GCS tarafından ayarlanır.
        cmd.takeoff = False
        cmd.land = False
        cmd.rtl = False
        cmd.emergency_stop = False

        # ─── Formasyon değişikliği ───
        cmd.formation_change_requested = self._formation_change_requested
        cmd.requested_formation = self._requested_formation
        cmd.requested_spacing_m = self._requested_spacing_m

        # Formasyon değişikliği bir kerelik — gönderildikten sonra temizle
        if self._formation_change_requested:
            self._formation_change_requested = False

        # ─── Limitler ───
        cmd.max_speed_mps = self._max_speed_mps
        cmd.max_yaw_rate_deg_s = self._max_yaw_rate_deg_s
        cmd.max_tilt_deg = self._max_tilt_deg

        cmd.source_module = 'joystick_interpreter'

        self._cmd_pub.publish(cmd)

    def _on_mavros_manual_control(self, msg: ManualControl) -> None:
        """MAVROS ManualControl'u normalize edip _on_manual_control'a verir.

        MAVLink MANUAL_CONTROL aralığı [-1000, 1000]; sürü [-1, 1].
        x=pitch, y=roll, r=yaw, z=throttle(0..1000). aux1..aux6 doğrudan.
        NOT: aralıklar (özellikle aux) SITL'de doğrulanmalıdır.
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

    def _read_aux_channel(self, msg: '_MavrosManual') -> float:
        """Yapılandırılmış deadman kanalını okur.

        Args:
            msg: Normalize girdi (_MavrosManual).

        Returns:
            Kanal değeri [-1.0, +1.0] aralığında.
        """
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
        """Değeri [lo, hi] aralığına kısıtlar.

        Args:
            value: Kısıtlanacak değer.
            lo: Alt sınır.
            hi: Üst sınır.

        Returns:
            Kısıtlanmış değer.
        """
        return max(lo, min(hi, value))

    # ─── GCS Arayüz Entegrasyon Noktaları ───
    # GCS web arayüzü hazır olduğunda bu metotlar ROS2 subscriber
    # callback'leri tarafından çağrılacak.

    def set_control_mode(self, mode: int) -> None:
        """GCS'den gelen mod değişikliği.

        Args:
            mode: SwarmControlCommand.MODE_* sabiti.
        """
        self._active_mode = mode
        self.get_logger().info(
            f'[joystick_interpreter] Mod değişti: {mode}'
        )

    def set_formation(
        self, formation_type: int, spacing_m: float = 5.0
    ) -> None:
        """GCS'den gelen formasyon değişikliği talebi.

        Args:
            formation_type: FormationCommand.FORMATION_* sabiti.
            spacing_m: Ajanlar arası mesafe (metre).
        """
        self._formation_change_requested = True
        self._requested_formation = formation_type
        self._requested_spacing_m = spacing_m
        self.get_logger().info(
            f'[joystick_interpreter] Formasyon değişikliği: '
            f'tip={formation_type} mesafe={spacing_m}m'
        )


# ═════════════════════════════════════════════════════════════════════
# GİRİŞ NOKTASI
# ═════════════════════════════════════════════════════════════════════

def main(args=None) -> None:
    """ros2 run tarafından çağrılan giriş noktası."""
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
