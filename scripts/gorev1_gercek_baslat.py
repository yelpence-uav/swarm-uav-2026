#!/usr/bin/env python3
"""Görev 1'i GERÇEK QR okumasıyla başlatır (video senaryosu değil).

video_scenario_director'dan farkı: QR içeriğini ENJEKTE ETMEZ. Sadece
şartnamenin öngördüğü iki şeyi yapar:

  1. QR kodlarının konum tablosunu yayınlar
     (s.14: "Tüm QR kodlarının konum bilgileri yarışma öncesinde hakemler
     tarafından paylaşılacaktır")
  2. Görevi başlatır (TriggerMission START)

Gerisi sürüye kalır: kameralar QR'ı görüp okuyacak, mission_fsm içeriği
çözümleyip sıradaki hedefi belirleyecek.

Konumlar Gazebo dünyasından (task1_dynamic_swarm.sdf) alınmıştır; dünya
x=doğu, y=kuzey olduğu için NED'e çevrilir.
"""
import argparse
import math

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

from swarm_interfaces.msg import QRCoordinates
from swarm_interfaces.srv import TriggerMission

_M_PER_DEG = 111320.0

# (qr_id, kuzey, doğu) — dünya dosyasındaki pose'lardan: kuzey=world_y,
# doğu=world_x. Altıgen, ~24 m yarıçap.
_QR_KONUMLARI = [
    (1,  20.78,  12.00),
    (2,   0.00,  24.00),
    (3, -20.78,  12.00),
    (4, -20.78, -12.00),
    (5,   0.00, -24.00),
    (6,  20.78, -12.00),
]


def _ned_to_latlon(north, east, olat, olon):
    """NED ofsetini enlem/boylama çevirir."""
    lat = olat + north / _M_PER_DEG
    lon = olon + east / (_M_PER_DEG * math.cos(math.radians(olat)))
    return lat, lon


class Baslatici(Node):
    """Koordinatları yayınlar ve görevi tetikler; sonra çekilir."""

    def __init__(self, team, olat, olon, gecikme):
        """Yayıncıyı ve servis istemcisini kurar."""
        super().__init__('gorev1_gercek_baslat')
        self._team = str(team)
        self._olat = float(olat)
        self._olon = float(olon)
        self._bitti = False

        latched = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST, depth=1,
        )
        self._coords_pub = self.create_publisher(
            QRCoordinates, '/swarm/public/mission/qr_coords', latched)
        self._trigger_cli = self.create_client(
            TriggerMission, '/swarm/mission/trigger')

        self._yayinla_koordinat()
        self.get_logger().info(
            f'{gecikme:.0f} sn sonra görev başlatılacak '
            f'(QR içeriği ENJEKTE EDİLMEYECEK — kameralar okuyacak).')
        self._timer = self.create_timer(gecikme, self._baslat)

    def _yayinla_koordinat(self):
        """6 QR'ın lat/lon tablosunu latched yayınlar."""
        msg = QRCoordinates()
        msg.stamp = self.get_clock().now().to_msg()
        ids, lats, lons = [], [], []
        for qr_id, north, east in _QR_KONUMLARI:
            lat, lon = _ned_to_latlon(north, east, self._olat, self._olon)
            ids.append(int(qr_id))
            lats.append(float(lat))
            lons.append(float(lon))
            self.get_logger().info(
                f'  QR{qr_id}: NED(K{north:+.2f}, D{east:+.2f}) '
                f'→ lat={lat:.7f} lon={lon:.7f}')
        msg.qr_ids = ids
        msg.lat_deg = lats
        msg.lon_deg = lons
        self._coords_pub.publish(msg)
        self.get_logger().info(f'Koordinat tablosu yayınlandı ({len(ids)} QR).')

    def _baslat(self):
        """TriggerMission START çağırır (bir kez)."""
        self._timer.cancel()
        if self._bitti:
            return
        if not self._trigger_cli.wait_for_service(timeout_sec=5.0):
            self.get_logger().error(
                '/swarm/mission/trigger yok — mission_fsm ayakta mı?')
            return
        req = TriggerMission.Request()
        req.mission_id = TriggerMission.Request.MISSION_DYNAMIC_SWARM
        req.command = TriggerMission.Request.COMMAND_START
        req.team_id = self._team
        req.parameters_json = ''
        self._trigger_cli.call_async(req)
        self._bitti = True
        self.get_logger().info(
            f'>>> GÖREV BAŞLATILDI (takım {self._team}). '
            f'Sürü kalkacak, QR1\'e gidip KAMERAYLA okumaya çalışacak.')


def main():
    """Başlatıcıyı çalıştırır."""
    p = argparse.ArgumentParser()
    p.add_argument('--team', default='1')
    p.add_argument('--origin-lat', type=float, default=41.0441)
    p.add_argument('--origin-lon', type=float, default=29.0017)
    p.add_argument('--start-delay', type=float, default=8.0)
    a = p.parse_args()

    rclpy.init()
    node = Baslatici(a.team, a.origin_lat, a.origin_lon, a.start_delay)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
