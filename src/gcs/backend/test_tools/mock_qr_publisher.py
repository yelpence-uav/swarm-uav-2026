"""Mock QR yayıncısı - GCS QRPanel testi için.

Şartname V2 örnek QR verilerini public topic'e basar.
"""

import argparse

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy

from swarm_interfaces.msg import QRMissionData


def _qr(
    qr_id,
    next_qr,
    *,
    formation=0,
    spacing=0.0,
    alt=0.0,
    pitch=0.0,
    roll=0.0,
    detach_id=0,
    detach_color=0,
    wait=4.0,
    team_id="2",
    raw="",
):
    """Tek bir QRMissionData mesajı kur (şartname alan kurallarına göre)."""
    m = QRMissionData()
    m.qr_id = qr_id
    m.qr_seq = qr_id  # örnek: seq = qr_id
    m.next_qr = next_qr
    m.team_id = team_id
    m.detected = True
    m.decoded = True
    m.valid = True
    m.confidence = 0.97
    m.raw_text = raw or (
        f'{{"qr":{qr_id},"w":{int(wait)},'
        f'"frm":{formation},"alt":{alt},"next":{next_qr}}}'
    )
    # Aktif bölüm bayrakları
    m.formation_active = formation != 0
    m.altitude_active = alt != 0.0
    m.maneuver_active = pitch != 0.0 or roll != 0.0
    m.detach_active = detach_id != 0
    m.complete_mission = next_qr == 0
    # Alanlar
    m.formation_type = formation
    m.spacing_m = float(spacing)
    m.altitude_agl_m = float(alt)
    m.pitch_deg = float(pitch)
    m.roll_deg = float(roll)
    m.wait_s = float(wait)
    m.target_agent_id = int(detach_id)
    m.detach_color = int(detach_color)
    m.detach_wait_s = 5.0 if detach_id else 0.0
    return m


# FORMATION: 1=ok, 2=v, 3=çizgi | COLOR: 1=kırmızı, 2=mavi
SCENARIO = [
    _qr(
        1,
        4,
        formation=1,
        spacing=6,
        alt=20,
        pitch=-10,
        raw="QR1 · ok başı 6m · pitch -10 · alt 20",
    ),
    _qr(
        4,
        2,
        formation=3,
        spacing=7,
        alt=26,
        roll=-5,
        raw="QR4 · çizgi 7m · roll -5 · alt 26",
    ),
    _qr(
        2,
        3,
        detach_id=3,
        detach_color=2,
        raw="QR2 · Drone 3 mavi bölgeye ayrılır",
    ),
    _qr(
        3,
        5,
        formation=2,
        spacing=7,
        alt=28,
        pitch=-15,
        raw="QR3 · V 7m · pitch -15 · alt 28",
    ),
    _qr(
        5,
        0,
        formation=3,
        spacing=5,
        alt=3,
        raw="QR5 · çizgi 5m · alt 3 · GÖREV SONU",
    ),
]


class MockQRPublisher(Node):
    def __init__(self, period: float, team_id: str):
        super().__init__("mock_qr_publisher")
        qos = QoSProfile(depth=10, reliability=QoSReliabilityPolicy.RELIABLE)
        self.pub = self.create_publisher(
            QRMissionData, "/swarm/public/perception/qr_data", qos
        )
        self.team_id = team_id
        self.idx = 0
        self.timer = self.create_timer(period, self.tick)
        self.get_logger().info(
            f"Mock QR yayıncısı başladı - /swarm/public/perception/qr_data "
            f"({period:.0f}s aralık, takım={team_id})"
        )

    def tick(self):
        msg = SCENARIO[self.idx % len(SCENARIO)]
        msg.team_id = self.team_id
        self.pub.publish(msg)
        self.get_logger().info(
            f"QR yayınlandı: #{msg.qr_id} -> sonraki #{msg.next_qr} "
            f"(form={msg.formation_type} alt={msg.altitude_agl_m:.0f} "
            f"ayrılma={msg.detach_active})"
        )
        self.idx += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--period", type=float, default=5.0, help="QR aralığı (sn)"
    )
    ap.add_argument("--team", default="2", help="team_id")
    args = ap.parse_args()

    rclpy.init()
    node = MockQRPublisher(args.period, args.team)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
