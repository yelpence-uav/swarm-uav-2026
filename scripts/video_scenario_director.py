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
import os
import sys

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

from std_msgs.msg import UInt8

from swarm_interfaces.msg import (
    AgentStatus, QRCoordinates, QRMissionData, SwarmOrigin)
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
_AGENT_COUNT = 3
# Kalkış köşesine varınca okbaşı komutunun gecikmesi (sn) — diziliş
# heading'e oturmadan geçilirse formasyon dağınık görünür.
_KALKIS_OTURMA_S = 5.0

# Varsayılanlar; swarm_config.py aşağıda bunları ezer.
_UCGEN_YARICAP_M = 24.0
_KALKIS_KOSE_MESAFE_M = 1.0


def _UCGEN_KOSE(aci_deg):
    """Üçgenin bir köşesini (kuzey, doğu) metre olarak verir.

    Köşeler home merkezli _UCGEN_YARICAP_M yarıçaplı çember üzerinde 120°
    aralıkla dizilir; açı kuzeyden saat yönünde ölçülür. Yarıçap değişince
    üç köşe de birlikte ölçeklenir — elle koordinat düzeltmek gerekmez.
    """
    r = math.radians(aci_deg)
    return (
        round(_UCGEN_YARICAP_M * math.cos(r), 2),   # kuzey
        round(_UCGEN_YARICAP_M * math.sin(r), 2),   # doğu
    )


_FRM_OKBASI = 1
_FRM_V = 2
_FRM_CIZGI = 3

# Tüm video ayarları swarm_config.py'den okunur; sahada yalnız o dosya
# düzenlenir. (sys.path eklemesi import'tan önce şart → E402 kaçınılmaz.)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import swarm_config as _cfg  # noqa: E402,I100
_UCGEN_YARICAP_M = float(_cfg.ALAN_YARICAP_M)
_KALKIS_KOSE_MESAFE_M = float(_cfg.KALKIS_MESAFE_M)
_VERTICES = [
    (kid,
     *(_UCGEN_KOSE(aci) if aci is not None else (None, None)),
     nxt, frm, sp, wait, alt, roll, pitch)
    for (kid, aci, nxt, frm, sp, wait, alt, roll, pitch) in _cfg.KOSELER
]

# Üçgen senaryosu: her köşe home'a göre NED ofset (kuzey, doğu) + o köşede
# okunacak QR içeriği. Akış: HOME → V1 → V2 → V3 → HOME; V1'de formasyon
# değişimi, son köşede next_qr=0 ile görev sonu.


def _ned_to_latlon(north, east, ref_lat, ref_lon):
    """NED ofsetini (metre) referans noktasına göre lat/lon'a çevirir.

    latlon_to_ned tersi; küçük alanda düz (equirectangular) yaklaşım
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
        # Origin swarm_origin'den otomatik; --origin fallback.
        self._origin_ready = False
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
        # QR içeriği (kamera yerine) — varışlarda yayınlanır.
        self._qr_pub = self.create_publisher(
            QRMissionData, '/swarm/public/perception/qr_data', reliable,
        )
        # Görev başlatma servisi (kalkış).
        self._trigger_cli = self.create_client(
            TriggerMission, '/swarm/mission/trigger',
        )

        # Mission durumu — internal (mission_fsm) + public (proxy röle)
        # dinlenir; hangisi tıkırsa o kullanılır.
        best_effort = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
            history=QoSHistoryPolicy.KEEP_LAST, depth=10,
        )
        self.create_subscription(
            UInt8, '/swarm/internal/mission/state',
            self._on_state, best_effort,
        )
        self.create_subscription(
            UInt8, '/swarm/public/mission/state', self._on_state, best_effort,
        )
        # Origin'i swarm_origin'den otomatik al (saha: first_fix).
        self.create_subscription(
            SwarmOrigin, '/swarm/internal/origin', self._on_origin, latched,
        )

        self._prev_state: int | None = None
        # Kaçıncı köşeye vardık (EXECUTE_QR_TASK'a her yeni girişte artar).
        self._exec_index = 0
        self._qr_seq = 0
        self._started = False
        self._done = False
        self._land_sent = False   # LAND bir kez gönderilsin (emit-once)

        # Sürünün YERDEKİ konumları — kalkış köşesini buradan hesaplayacağız.
        # Diziliş sahada rastgele olacağı için sabit koordinat yazılamaz.
        self._pos: dict[int, tuple[float, float]] = {}
        self._yaw: dict[int, float] = {}
        for i in range(1, _AGENT_COUNT + 1):
            self.create_subscription(
                AgentStatus, f'/swarm/agent/drone{i}/telemetry',
                lambda m, k=i: (
                    self._pos.__setitem__(k, (m.pos_x, m.pos_y)),
                    self._yaw.__setitem__(k, m.heading_deg),
                ),
                best_effort,
            )

        self._coords_sent = False
        # Koordinat tablosu, sürünün konumu bilinmeden yayınlanamaz (kalkış
        # köşesi merkeze göre hesaplanıyor). Telemetri gelene kadar bekle;
        # gelince yayınla ve görev başlatma sayacını o an kur.
        self._coords_timer = self.create_timer(0.5, self._try_publish_coords)
        self._start_timer = None
        self.get_logger().info(
            f'Director hazır. team={self._team} '
            f'origin=({self._origin_lat:.6f},{self._origin_lon:.6f}). '
            f'{_AGENT_COUNT} dronun konumu bekleniyor '
            '(kalkış köşesi sürü merkezinden hesaplanacak).'
        )

    def _try_publish_coords(self) -> None:
        """Sürünün konumu gelince koordinat tablosunu yayınlar (bir kez).

        Kalkış köşesi sürünün merkezine göre hesaplandığı için tablo,
        telemetri akmadan yayınlanamaz. Konumlar gelmezse bekler; makul
        bir süre sonra merkezi origin varsayıp yine de devam eder ki
        senaryo hiç başlamamazlık etmesin.
        """
        if self._coords_sent:
            return
        self._coords_bekleme = getattr(self, '_coords_bekleme', 0) + 1
        # Konum + origin gelmeli; gelmezse ~30 sn sonra --origin fallback.
        yeter = len(self._pos) >= _AGENT_COUNT and self._origin_ready
        if not yeter and self._coords_bekleme < 60:      # ~30 sn bekle
            return
        if not yeter:
            self.get_logger().warn(
                f'{len(self._pos)}/{_AGENT_COUNT} konum, '
                f'origin_ready={self._origin_ready}; elle --origin ile devam.'
            )
        self._coords_sent = True
        self._coords_timer.cancel()
        self._publish_coords()
        self._start_timer = self.create_timer(
            self._start_delay_s, self._start_mission,
        )
        self.get_logger().info(
            f'{self._start_delay_s:.0f} sn sonra görev başlatılacak.'
        )

    def _on_origin(self, msg: SwarmOrigin) -> None:
        """Origin'i swarm_origin'den otomatik alır (saha: first_fix)."""
        if not msg.valid:
            return
        self._origin_lat = float(msg.origin_lat_deg)
        self._origin_lon = float(msg.origin_lon_deg)
        self._origin_ready = True

    def _swarm_centroid(self) -> tuple[float, float]:
        """Sürünün yerdeki merkezi (shared NED, metre)."""
        if not self._pos:
            return (0.0, 0.0)
        xs = [p[0] for p in self._pos.values()]
        ys = [p[1] for p in self._pos.values()]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    def _kalkis_kosesi(self) -> tuple[float, float]:
        """Kalkış köşesini sürünün ÖNÜNE (baktığı yöne) yerleştirir.

        Yön, sürünün mevcut yaw'ından alınır — hedeften DEĞİL. Sebebi sıra:
        sistem her köşeden önce o köşeye DÖNER (ROTATE), sonra gider, sonra
        görevi (formasyon değişimi) uygular. Köşe hedef yönüne konursa sürü
        okbaşına geçmeden ÖNCE çizgi halindeyken dönmek zorunda kalıyor —
        gözlenen "yatay çizgi dikleşiyor" hareketi buydu.

        Sürünün zaten baktığı yöne konunca dönecek bir şey kalmaz: sürü
        kalkar, okbaşına geçer, asıl rotasyonu okbaşı halinde yapar.
        Diziliş rastgele olsa da çalışır; yön de konum da telemetriden gelir.
        """
        cn, ce = self._swarm_centroid()
        if not self._yaw:
            return (cn, ce)
        # Yaw ortalaması açısal olarak alınır (359°/1° ortalaması 180 değil 0).
        sn = sum(math.sin(math.radians(y)) for y in self._yaw.values())
        cs = sum(math.cos(math.radians(y)) for y in self._yaw.values())
        if abs(sn) < 1e-9 and abs(cs) < 1e-9:
            return (cn, ce)
        yon = math.atan2(sn, cs)          # NED: 0 = kuzey, saat yönü +
        return (
            cn + _KALKIS_KOSE_MESAFE_M * math.cos(yon),
            ce + _KALKIS_KOSE_MESAFE_M * math.sin(yon),
        )

    def _publish_coords(self) -> None:
        """Köşelerin lat/lon'unu QRCoordinates olarak latched yayınlar."""
        msg = QRCoordinates()
        msg.stamp = self.get_clock().now().to_msg()
        ids, lats, lons = [], [], []
        kalkis = self._kalkis_kosesi()
        cn, ce = self._swarm_centroid()
        self.get_logger().info(
            f'Sürü merkezi NED({cn:+.1f},{ce:+.1f}) — kalkış köşesi '
            f'NED({kalkis[0]:+.1f},{kalkis[1]:+.1f}) olarak hesaplandı.'
        )
        for qr_id, north, east, *_ in _VERTICES:
            if north is None:               # kalkış köşesi — hesaplanan konum
                north, east = kalkis
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
        self.get_logger().info(f'Koordinat tablosu yayınlandı ({len(ids)}).')

    def _start_mission(self) -> None:
        """Görevi başlatır (TriggerMission START, bir kez) — sürü kalkar."""
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
        """Durum değişince tetiklenir; varışta QR içeriği enjekte eder."""
        state = int(msg.data)
        if state == self._prev_state:
            return
        prev = self._prev_state
        self._prev_state = state
        self.get_logger().info(
            f'Mission durumu: {_STATE_NAMES.get(prev, prev)} '
            f'→ {_STATE_NAMES.get(state, state)}'
        )

        # EXECUTE_QR_TASK'a YENİ giriş = köşeye VARDIK → içeriğini bas.
        if state == _ST_EXECUTE_QR_TASK and prev != _ST_EXECUTE_QR_TASK:
            # İlk köşede enjeksiyonu geciktir: sürü varışta rotasyonu henüz
            # tamamlamamış oluyor, yamuk dizilişte formasyon geçişi dağınık
            # görünür. Diğer köşelerde sürü navigasyon sonunda zaten oturur.
            if self._exec_index == 0 and _KALKIS_OTURMA_S > 0.0:
                self.get_logger().info(
                    f'Kalkış köşesi: formasyon otursun diye '
                    f'{_KALKIS_OTURMA_S:.0f} sn bekleniyor.'
                )
                self._oturma_timer = self.create_timer(
                    _KALKIS_OTURMA_S, self._gecikmeli_enjekte,
                )
            else:
                self._inject_current_vertex()

        # Son köşeden sonra olduğun yerde in — yalnız bu senaryoda.
        # Video 5 dakikayla sınırlı; eve dönüş bacağı bu bütçeye sığmıyor.
        # Gerçek görevde FSM normal RETURN_HOME akışını uygular
        # (gorev1.launch.py bu director'ı çalıştırmaz).
        if state == _ST_RETURN_HOME and not self._land_sent:
            self._land_sent = True
            self._send_land()

        # Görev sonu — logla.
        if state in (_ST_RETURN_HOME, _ST_LANDING, _ST_MISSION_COMPLETE) \
                and not self._done:
            self._done = True
            self.get_logger().info(
                'Son köşe okundu → sürü iniyor. Senaryo tamam.'
            )

    def _send_land(self) -> None:
        """Sürüye 'olduğun yerde in' komutu gönderir (TriggerMission LAND)."""
        if not self._trigger_cli.service_is_ready():
            self.get_logger().error(
                '/swarm/mission/trigger hazır değil — LAND gönderilemedi; '
                'sürü eve dönüşe devam edecek.'
            )
            return
        req = TriggerMission.Request()
        req.mission_id = TriggerMission.Request.MISSION_DYNAMIC_SWARM
        req.command = TriggerMission.Request.COMMAND_LAND
        req.team_id = self._team
        fut = self._trigger_cli.call_async(req)
        fut.add_done_callback(
            lambda f: self.get_logger().info(
                f'LAND yanıtı: {getattr(f.result(), "message", "?")}'
            )
        )
        self.get_logger().info(
            '>>> Son köşe tamamlandı → LAND gönderildi '
            '(video: eve dönüş yok, olduğu yerde iniş).'
        )

    def _gecikmeli_enjekte(self) -> None:
        """Bekleme bitince kalkış köşesi içeriğini enjekte eder (bir kez)."""
        if getattr(self, '_oturma_timer', None) is not None:
            self._oturma_timer.cancel()
            self._oturma_timer = None
        self._inject_current_vertex()

    def _inject_current_vertex(self) -> None:
        """Sıradaki köşenin QR içeriğini (formasyon + next_qr) yayınlar."""
        if self._exec_index >= len(_VERTICES):
            self.get_logger().warn(
                'Beklenenden fazla EXECUTE girişi — enjeksiyon atlandı.'
            )
            return
        qr_id, _n, _e, next_qr, frm, spacing, wait_s, irtifa, roll, pitch = \
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
        # Manevra: roll veya pitch sıfırdan farklıysa aktif.
        m.maneuver_active = (roll != 0.0) or (pitch != 0.0)
        m.roll_deg = float(roll)
        m.pitch_deg = float(pitch)
        # İrtifa: >0 ise o irtifaya çıkılır (0 = değişiklik yok).
        m.altitude_active = irtifa > 0.0
        m.altitude_agl_m = float(irtifa)
        # Bu senaryoda sürüden ayrılma yok.
        m.detach_active = False
        m.wait_s = float(wait_s)
        m.raw_text = (
            f'VIDEO QR{qr_id}: next={next_qr} frm={frm} spacing={spacing} '
            f'alt={irtifa} roll={roll} pitch={pitch} wait={wait_s}'
        )
        self._qr_pub.publish(m)
        self.get_logger().info(
            f'>>> QR{qr_id} içeriği enjekte edildi '
            f'(sıradaki=QR{next_qr}, formasyon={frm}, irtifa={irtifa}, '
            f'roll={roll}, wait={wait_s}s).'
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
                    help='Koordinat yayını → START arası bekleme (sn)')
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
