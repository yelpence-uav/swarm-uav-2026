#!/usr/bin/env python3
"""video_scenario_director.py — Uçuş kanıt videosu üçgen senaryosu sürücüsü.

Uçuş kanıt videosu için sürüyü 3 doğrusal olmayan noktaya (üçgen) uçurur:
her köşeden önce formasyon rotasyonu, bir köşede formasyon değişimi, tam
otonom. QR KODU / KAMERA GEREKMEZ — bu düğüm, kameranın okuyacağı bilgiyi
(sıradaki nokta + formasyon komutu) doğrudan sürünün beynine besler.

Ne yapar (sırayla):
  1. QR konum tablosunu (3 köşe lat/lon) latched yayınlar   → mission_fsm okur.
  2. Kısa bekleme sonrası görevi başlatır (TriggerMission START) → kalkış.
  3. Sürü her köşeye vardığında (mission_fsm EXECUTE_QR_TASK'a girince) o
     köşenin QR içeriğini yayınlar → beyin sıradaki köşeyi hedefler.
  4. next_qr=0 okununca beyin eve döner ve iner; düğüm görevi loglar.

Sürünün uçuş/rotasyon/navigasyon/formasyon/CA koduna DOKUNMAZ; yalnız rota
bilgisini dışarıdan verir.

ÖNEMLİ — team_id:
  mission_fsm team_id'si boşsa TÜM QR'ları atlar. Bu yüzden:
    - gorev1.launch'ı team_id ile aç:  team_id:=752825
    - bu düğümü aynı team ile çalıştır: --team 752825
  İkisi eşleşmezse beyin enjekte edilen içeriği görmezden gelir.

Çalıştırma (altyapı + gorev1 stack AYAKTA olduktan sonra):
  source /opt/ros/jazzy/setup.bash
  source /home/yelpence/ros2_ws/install/setup.bash
  python3 scripts/video_scenario_director.py --team 752825 \
      --origin-lat 41.0441 --origin-lon 29.0017

Sahada: --origin-lat/--origin-lon değerlerini gerçek alanın GPS orijinine,
üçgen köşelerini (VERTICES) alana göre ayarla. Hepsi tek dosyada, kod
düzenlemesi yeter (uçuş koduna dokunmadan).
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
from std_msgs.msg import UInt8

from swarm_interfaces.msg import QRCoordinates, QRMissionData
from swarm_interfaces.srv import TriggerMission

# Enlem başına metre (formation_geometry ile birebir). NED ofsetlerini
# köşe lat/lon'una çevirmek için kullanılır.
_M_PER_DEG_LAT = 111_320.0

# mission_states.py MissionState enum değerleri (birebir kopya; import değil ki
# bu araç swarm_state_machine paketine bağımlı olmasın).
_ST_SYNC_TAKEOFF = 3
_ST_NAVIGATE_TO_QR = 4
_ST_EXECUTE_QR_TASK = 5
_ST_WAIT_AT_QR = 6
_ST_ROTATE_TO_NEXT = 7
_ST_RETURN_HOME = 9
_ST_LANDING = 10
_ST_MISSION_COMPLETE = 11

_STATE_NAMES = {
    0: 'UNKNOWN', 1: 'IDLE', 2: 'PREFLIGHT', 3: 'SYNC_TAKEOFF',
    4: 'NAVIGATE_TO_QR', 5: 'EXECUTE_QR_TASK', 6: 'WAIT_AT_QR',
    7: 'ROTATE_TO_NEXT', 8: 'SEMI_AUTONOMOUS', 9: 'RETURN_HOME',
    10: 'LANDING', 11: 'MISSION_COMPLETE', 12: 'ABORTED', 13: 'PAUSED',
}

# Formasyon tipleri (QRMissionData / formation_geometry ile birebir).
_FRM_OKBASI = 1
_FRM_V = 2
_FRM_CIZGI = 3

# --- ÜÇGEN SENARYOSU ---------------------------------------------------------
# Her köşe: home'a (origin) göre NED ofset (kuzey, doğu) metre + o köşede
# okunacak QR içeriği. Köşeler DOĞRUSAL OLMAYAN (üçgen) seçilir — video şartı.
# Sahada bu değerleri alana göre değiştir; origin'i --origin-lat/lon ile ver.
#
# Sıra: HOME → V1(QR1) → V2(QR2) → V3(QR3) → HOME.
#   QR1'de FORMASYON DEĞİŞİMİ (video şartı: en az bir formasyon değişimi).
#   QR3'te next_qr=0 → görev sonu → eve dönüş.
# Köşeler sahanın GERÇEK QR noktalarından seçildi → hepsi saha İÇİNDE
# (saha 105x68 m; QR'lar hexagon halinde içeride). Dünya ENU olduğundan
# world(x,y) = (Doğu, Kuzey); director NED (kuzey, doğu) ister →
# kuzey = world_y, doğu = world_x.
#   V1 = QR1 world(24, 0)      → kuzey  0.00, doğu +24
#   V2 = QR3 world(-12, 20.78) → kuzey +20.78, doğu -12
#   V3 = QR5 world(-12,-20.78) → kuzey -20.78, doğu -12
# Home (spawn) saha merkezinde → üçgen home etrafında, her bacakta belirgin
# dönüş, hepsi ±34m kuzey / ±52m doğu sınırının rahat içinde.
_VERTICES = [
    # (qr_id, kuzey_m, doğu_m, next_qr, formasyon, spacing_m, wait_s)
    (1,   0.00,  24.0, 2, _FRM_OKBASI, 6.0, 4.0),   # V1: OKBAŞI'na geç, bekle
    (2,  20.78, -12.0, 3, 0,           0.0, 2.0),   # V2: formasyon aynı, next=3
    (3, -20.78, -12.0, 0, 0,           0.0, 2.0),   # V3: son nokta (next=0)
]


def _ned_to_latlon(north, east, ref_lat, ref_lon):
    """NED ofsetini (metre) referans noktasına göre lat/lon'a çevirir.

    latlon_to_ned'in tersidir; küçük alanlar için düz (equirectangular) yaklaşım
    yeterli. Sürünün uçtuğu shared-NED çerçevesiyle tutarlıdır.
    """
    lat = ref_lat + north / _M_PER_DEG_LAT
    lon = ref_lon + east / (_M_PER_DEG_LAT * math.cos(math.radians(ref_lat)))
    return lat, lon


class VideoScenarioDirector(Node):
    """Üçgen rotayı süren senaryo düğümü (QR/kamera olmadan)."""

    def __init__(self, args) -> None:
        """Yayıncı/abone/servis kurar, koordinat tablosunu yayınlar."""
        super().__init__('video_scenario_director')
        self._team = str(args.team)
        self._origin_lat = float(args.origin_lat)
        self._origin_lon = float(args.origin_lon)
        self._start_delay_s = float(args.start_delay)

        # QoS profilleri — mission_fsm'in beklediğiyle eşleşir.
        reliable = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.VOLATILE,
            history=QoSHistoryPolicy.KEEP_LAST, depth=10,
        )
        latched = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST, depth=1,
        )

        # Koordinat tablosu (latched) — geç başlayan mission_fsm bile yakalar.
        self._coords_pub = self.create_publisher(
            QRCoordinates, '/swarm/public/mission/qr_coords', latched,
        )
        # QR içeriği (kameranın okuyacağı şeyin yerine) — varışlarda yayınlanır.
        self._qr_pub = self.create_publisher(
            QRMissionData, '/swarm/public/perception/qr_data', reliable,
        )
        # Görev başlatma servisi (kalkış).
        self._trigger_cli = self.create_client(
            TriggerMission, '/swarm/mission/trigger',
        )

        # Mission durumu — hem internal (mission_fsm doğrudan) hem public (proxy
        # röle) dinlenir; proxy açık/kapalı fark etmez, hangisi tıkırsa o kullanılır.
        best_effort = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
            history=QoSHistoryPolicy.KEEP_LAST, depth=10,
        )
        self.create_subscription(
            UInt8, '/swarm/internal/mission/state', self._on_state, best_effort,
        )
        self.create_subscription(
            UInt8, '/swarm/public/mission/state', self._on_state, best_effort,
        )

        self._prev_state: int | None = None
        # Kaçıncı köşeye vardık (EXECUTE_QR_TASK'a her yeni girişte artar).
        self._exec_index = 0
        self._qr_seq = 0
        self._started = False
        self._done = False

        self._publish_coords()
        # Stack ayağa kalksın diye kısa bekleme, sonra görevi başlat.
        self._start_timer = self.create_timer(
            self._start_delay_s, self._start_mission,
        )
        self.get_logger().info(
            f'Director hazır. team={self._team} '
            f'origin=({self._origin_lat:.6f},{self._origin_lon:.6f}). '
            f'{self._start_delay_s:.0f} sn sonra görev başlatılacak.'
        )

    def _publish_coords(self) -> None:
        """3 köşenin lat/lon'unu QRCoordinates olarak latched yayınlar."""
        msg = QRCoordinates()
        msg.stamp = self.get_clock().now().to_msg()
        ids, lats, lons = [], [], []
        for qr_id, north, east, *_ in _VERTICES:
            lat, lon = _ned_to_latlon(
                north, east, self._origin_lat, self._origin_lon,
            )
            ids.append(int(qr_id))
            lats.append(float(lat))
            lons.append(float(lon))
            self.get_logger().info(
                f'  QR{qr_id}: NED({north:+.1f},{east:+.1f}) '
                f'→ lat={lat:.7f} lon={lon:.7f}'
            )
        msg.qr_ids = ids
        msg.lat_deg = lats
        msg.lon_deg = lons
        self._coords_pub.publish(msg)
        self.get_logger().info(f'Koordinat tablosu yayınlandı ({len(ids)} köşe).')

    def _start_mission(self) -> None:
        """TriggerMission START çağırır (bir kez) — sürü kalkışa geçer."""
        self._start_timer.cancel()
        if self._started:
            return
        if not self._trigger_cli.wait_for_service(timeout_sec=5.0):
            self.get_logger().error(
                '/swarm/mission/trigger servisi yok — mission_fsm ayakta mı? '
                'Görev başlatılamadı.'
            )
            return
        req = TriggerMission.Request()
        req.mission_id = TriggerMission.Request.MISSION_DYNAMIC_SWARM
        req.command = TriggerMission.Request.COMMAND_START
        req.team_id = self._team
        req.parameters_json = ''
        fut = self._trigger_cli.call_async(req)
        fut.add_done_callback(self._on_start_result)
        self._started = True
        self.get_logger().info('Görev başlatma komutu gönderildi (START).')

    def _on_start_result(self, fut) -> None:
        """START servis yanıtını loglar."""
        try:
            res = fut.result()
            self.get_logger().info(
                f'START yanıtı: success={res.success} '
                f'msg="{getattr(res, "message", "")}"'
            )
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f'START servisi hata: {exc}')

    def _on_state(self, msg: UInt8) -> None:
        """Mission durumu değişince tetiklenir; varışta QR içeriği enjekte eder."""
        state = int(msg.data)
        if state == self._prev_state:
            return
        prev = self._prev_state
        self._prev_state = state
        self.get_logger().info(
            f'Mission durumu: {_STATE_NAMES.get(prev, prev)} '
            f'→ {_STATE_NAMES.get(state, state)}'
        )

        # EXECUTE_QR_TASK'a YENİ giriş = bir köşeye VARDIK → o köşenin içeriğini bas.
        if state == _ST_EXECUTE_QR_TASK and prev != _ST_EXECUTE_QR_TASK:
            self._inject_current_vertex()

        # Görev sonu — logla, düğümü kapat.
        if state in (_ST_RETURN_HOME, _ST_LANDING, _ST_MISSION_COMPLETE) \
                and not self._done:
            self._done = True
            self.get_logger().info(
                'Son köşe okundu → sürü eve dönüyor/iniyor. Senaryo tamam.'
            )

    def _inject_current_vertex(self) -> None:
        """Sıradaki köşenin QR içeriğini (formasyon + next_qr) yayınlar."""
        if self._exec_index >= len(_VERTICES):
            self.get_logger().warn(
                'Beklenenden fazla EXECUTE girişi — enjeksiyon atlandı.'
            )
            return
        qr_id, _n, _e, next_qr, frm, spacing, wait_s = \
            _VERTICES[self._exec_index]
        self._exec_index += 1
        self._qr_seq += 1

        m = QRMissionData()
        m.stamp = self.get_clock().now().to_msg()
        m.qr_id = int(qr_id)
        m.qr_seq = int(self._qr_seq)
        m.next_qr = int(next_qr)
        m.team_id = self._team
        m.detected = True
        m.decoded = True
        m.valid = True
        m.confidence = 1.0
        m.complete_mission = next_qr == 0
        # Formasyon değişimi varsa aktifle.
        m.formation_active = frm != 0
        m.formation_type = int(frm)
        m.spacing_m = float(spacing)
        # Bu senaryoda manevra/irtifa/ayrılma yok.
        m.maneuver_active = False
        m.altitude_active = False
        m.detach_active = False
        m.wait_s = float(wait_s)
        m.raw_text = (
            f'VIDEO QR{qr_id}: next={next_qr} '
            f'frm={frm} spacing={spacing} wait={wait_s}'
        )
        self._qr_pub.publish(m)
        self.get_logger().info(
            f'>>> QR{qr_id} içeriği enjekte edildi '
            f'(sıradaki=QR{next_qr}, formasyon={frm}, wait={wait_s}s).'
        )


def main() -> None:
    """Giriş noktası — argümanları okur, düğümü döndürür."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--team', default='752825',
                    help='team_id (mission_fsm ile AYNI olmalı)')
    ap.add_argument('--origin-lat', type=float, default=41.0441,
                    help='Alan GPS orijini enlemi (SwarmOrigin ile aynı)')
    ap.add_argument('--origin-lon', type=float, default=29.0017,
                    help='Alan GPS orijini boylamı (SwarmOrigin ile aynı)')
    ap.add_argument('--start-delay', type=float, default=8.0,
                    help='Koordinat yayınından START komutuna kadar bekleme (sn)')
    args = ap.parse_args()

    rclpy.init()
    node = VideoScenarioDirector(args)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
