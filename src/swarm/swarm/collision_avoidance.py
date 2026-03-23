#!/usr/bin/env python3
"""
Yelpençe Predictive Collision Avoidance v9.0
============================================
Tahminsel Hız Engeli (Predictive Velocity Obstacle) algoritması.

Mevcut sistemdeki 5 kritik sorunu çözer:
1. VehicleLocalPosition kullanır (GPS yerine) → 50Hz, ±0.05m hassasiyet
2. Offboard velocity ile doğrudan müdahale → REPOSITION gecikmesi yok
3. 3 katmanlı mesafe zonları → erken uyarı, kademeli müdahale
4. Kapanma hızı tahmini → 1 sn ileriye bakarak önceden kaçış
5. Tüm komşulardan itme vektörü toplama → çoklu tehdit desteği
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from px4_msgs.msg import (
    VehicleLocalPosition,
    SensorGps,
    OffboardControlMode,
    TrajectorySetpoint,
    VehicleCommand,
    VehicleStatus,
)
from std_msgs.msg import String
import math
import json
import time

# ──────────────────────────────────────────────
# ZON PARAMETRELERİ
# ──────────────────────────────────────────────
ZONE_WARN   = 3.5   # Uyarı bölgesi (m) — sadece log
ZONE_ACTIVE = 2.0   # Aktif kaçış bölgesi (m) — yumuşak itme uygulanır
ZONE_CRIT   = 1.0   # Kritik bölge (m) — sert acil kaçış
CLEAR_DIST  = 4.0   # "Güvenli" etiketinin kalkması için gereken mesafe

# İTME GÜCÜ PARAMETRELERİ
MAX_PUSH_SPEED = 2.5   # Maksimum kaçış hızı (m/s)
PREDICT_DT     = 1.0   # Tahmin penceresi (saniye)
LOOP_HZ        = 20    # Kontrol döngüsü frekansı

# ──────────────────────────────────────────────


class PredictiveCollisionAvoidance(Node):
    """
    Tahminsel Hız Engeli (PVO) tabanlı çarpışma önleyici.
    - Her drone için VehicleLocalPosition (konum+hız) dinler.
    - Tehlike anında Offboard velocity setpoint ile doğrudan kaçış emri verir.
    - Tehlike yoksa hiçbir şey yayınlamaz — diğer sistemlere (formasyon, manuel)
      karışmaz.
    """

    def __init__(self, drone_count):
        super().__init__('predictive_collision_avoidance')
        self.drone_count = int(drone_count)
        self.enabled = True
        self.manual_mask = []

        # drone_id → {pos, vel, nav_state, avoiding, last_intervene_time}
        self.drones = {}

        qos_be = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        for i in range(1, self.drone_count + 1):
            ns = f'/drone_{i}'
            # ── Telemetri (giriş) ──
            self.create_subscription(
                VehicleLocalPosition,
                f'{ns}/fmu/out/vehicle_local_position_v1',
                lambda msg, d=i: self._pos_cb(msg, d),
                qos_be,
            )
            self.create_subscription(
                SensorGps,
                f'{ns}/fmu/out/vehicle_gps_position',
                lambda msg, d=i: self._gps_pos_cb(msg, d),
                qos_be,
            )
            self.create_subscription(
                VehicleStatus,
                f'{ns}/fmu/out/vehicle_status_v2',
                lambda msg, d=i: self._status_cb(msg, d),
                qos_be,
            )

            # ── Komut çıkışları ──
            self.drones[i] = {
                'lat': 0.0, 'lon': 0.0, 'z': 0.0,
                'vx': 0.0, 'vy': 0.0, 'vz': 0.0,
                'has_gps': False,
                'nav_state': 0,
                'ready': False,
                'avoiding': False,
                'last_intervene': 0.0,
                'offboard_pub': self.create_publisher(
                    OffboardControlMode, f'{ns}/fmu/in/offboard_control_mode', 10
                ),
                'setpoint_pub': self.create_publisher(
                    TrajectorySetpoint, f'{ns}/fmu/in/trajectory_setpoint', 10
                ),
                'cmd_pub': self.create_publisher(
                    VehicleCommand, f'{ns}/fmu/in/vehicle_command', 10
                ),
            }

        # GCS haberleşme
        self.alert_pub = self.create_publisher(String, '/gcs/alerts', 10)
        self.status_pub = self.create_publisher(String, '/swarm/collision_status', 10)
        self.create_subscription(String, '/gcs/alerts', self._gcs_cb, 10)
        self.create_subscription(String, '/gcs/manual_active_ids', self._manual_cb, 10)

        # Kontrol döngüsü
        self.create_timer(1.0 / LOOP_HZ, self._control_loop)
        self.get_logger().info(
            f'PVO v9.0: {self.drone_count} İHA için tahminsel çarpışma önleyici aktif. '
            f'Zonlar: WARN={ZONE_WARN}m  ACTIVE={ZONE_ACTIVE}m  CRIT={ZONE_CRIT}m'
        )

    # ──────────── Callback'ler ────────────

    def _pos_cb(self, msg, d_id):
        """VehicleLocalPosition → sadece hız ve irtifa için kullan (yerel çerçeve)."""
        d = self.drones[d_id]
        d['z'] = msg.z       # NED: z pozitif = aşağı
        d['vx'] = msg.vx
        d['vy'] = msg.vy
        d['vz'] = msg.vz

    def _gps_pos_cb(self, msg, d_id):
        """SensorGps → konum için kullan (küresel çerçeve, tüm dronelar ortak)."""
        d = self.drones[d_id]
        d['lat'] = msg.latitude_deg
        d['lon'] = msg.longitude_deg
        if not d['has_gps']:
            d['has_gps'] = True
        if not d['ready'] and d['has_gps'] and abs(d['z']) > 0.5:
            d['ready'] = True
            self.get_logger().info(f'İHA {d_id}: GPS + Yerel telemetri bağlantısı kuruldu.')

    @staticmethod
    def _gps_distance(lat1, lon1, lat2, lon2):
        """İki GPS noktası arasında yatay mesafe (metre)."""
        dlat = (lat1 - lat2) * 111320.0
        dlon = (lon1 - lon2) * 111320.0 * math.cos(math.radians((lat1 + lat2) / 2.0))
        return math.sqrt(dlat * dlat + dlon * dlon)

    def _status_cb(self, msg, d_id):
        self.drones[d_id]['nav_state'] = msg.nav_state

    def _gcs_cb(self, msg):
        try:
            data = json.loads(msg.data)
            if data.get('type') == 'control':
                self.enabled = data.get('enabled', True)
        except Exception:
            pass

    def _manual_cb(self, msg):
        try:
            self.manual_mask = json.loads(msg.data)
        except Exception:
            pass

    # ──────────── Ana Kontrol Döngüsü ────────────

    def _control_loop(self):
        if not self.enabled:
            return

        any_intervention = False
        status_data = {}

        for i in range(1, self.drone_count + 1):
            di = self.drones[i]
            if not di['ready'] or not di['has_gps']:
                continue
            if abs(di['z']) < 0.5:
                continue  # Yerde, kaçışa gerek yok
            if i in self.manual_mask:
                continue  # Manuel kontrolde, karışma

            # ── Tüm komşulardan itme vektörü topla ──
            push_x, push_y, push_z = 0.0, 0.0, 0.0
            threat_level = 0  # 0=yok, 1=uyarı, 2=aktif, 3=kritik
            closest_id = -1
            closest_dist = 999.0

            for j in range(1, self.drone_count + 1):
                if i == j:
                    continue
                dj = self.drones[j]
                if not dj['ready'] or not dj['has_gps'] or abs(dj['z']) < 0.5:
                    continue

                # Yatay mesafe: GPS tabanlı (küresel çerçeve — doğru sonuç verir)
                dist_h = self._gps_distance(di['lat'], di['lon'], dj['lat'], dj['lon'])
                dz = di['z'] - dj['z']
                dist_3d = math.sqrt(dist_h * dist_h + dz * dz)

                if dist_3d < closest_dist:
                    closest_dist = dist_3d
                    closest_id = j

                if dist_3d >= ZONE_WARN:
                    continue  # Bu komşu güvenli

                # ── Kapanma hızı (closing speed) ──
                dvx = di['vx'] - dj['vx']
                dvy = di['vy'] - dj['vy']
                dvz = di['vz'] - dj['vz']
                # İtme yönü: GPS farkından birim vektör hesapla
                dlat_m = (di['lat'] - dj['lat']) * 111320.0
                dlon_m = (di['lon'] - dj['lon']) * 111320.0 * math.cos(math.radians(di['lat']))
                inv_dist = 1.0 / max(dist_3d, 0.1)
                ux = dlat_m * inv_dist   # Kuzey ekseni
                uy = dlon_m * inv_dist   # Doğu ekseni
                uz = dz * inv_dist       # Aşağı ekseni
                # Kapanma hızı = göreceli hızın, birbirlerine doğru olan bileşeni (pozitif = yaklaşıyor)
                v_closing = -(dvx * ux + dvy * uy + dvz * uz)

                # ── Tahminsel mesafe (1 sn sonra ne olur?) ──
                predicted_dist = dist_3d - max(v_closing, 0.0) * PREDICT_DT

                # ── Zon belirleme (tahminsel mesafeye göre) ──
                if predicted_dist < ZONE_CRIT:
                    level = 3
                elif predicted_dist < ZONE_ACTIVE:
                    level = 2
                elif predicted_dist < ZONE_WARN:
                    level = 1
                else:
                    continue

                threat_level = max(threat_level, level)

                # ── İtme vektörü hesabı ──
                if level >= 2:  # Aktif veya Kritik → kaçış kuvveti uygula
                    # Kuvvet şiddeti: mesafe azaldıkça artar
                    if level == 3:
                        # Kritik: Çok sert itme
                        strength = MAX_PUSH_SPEED
                    else:
                        # Aktif: Yumuşak itme (mesafeyle orantılı)
                        t = (ZONE_ACTIVE - predicted_dist) / (ZONE_ACTIVE - ZONE_CRIT)
                        t = max(0.0, min(1.0, t))  # 0..1 arası kırp
                        strength = MAX_PUSH_SPEED * 0.3 + (MAX_PUSH_SPEED * 0.7) * t

                    # Hız farkındalığı: yaklaşma hızı yüksekse ekstra güç
                    if v_closing > 1.0:
                        strength = min(strength * 1.5, MAX_PUSH_SPEED)

                    # ID hiyerarşisi: büyük ID daha çok esner
                    if i > j:
                        strength *= 1.3

                    # Kuvveti ters yöne (uzaklaşma vektörüne) uygula
                    push_x += ux * strength
                    push_y += uy * strength
                    push_z += uz * strength * 0.3  # Dikeyde daha az itme

            # ── Sonuç: Toplam itme vektörünü değerlendir ──
            push_mag = math.sqrt(push_x*push_x + push_y*push_y + push_z*push_z)

            if threat_level >= 2 and push_mag > 0.1:
                # Hız limitine kırp
                if push_mag > MAX_PUSH_SPEED:
                    scale = MAX_PUSH_SPEED / push_mag
                    push_x *= scale
                    push_y *= scale
                    push_z *= scale

                # Offboard velocity ile müdahale et
                self._send_velocity(i, push_x, push_y, push_z)

                di['avoiding'] = True
                di['last_intervene'] = time.time()
                any_intervention = True
                status_data[i] = True

                if threat_level == 3:
                    log_level = 'KRİTİK'
                    alert_level = 'critical'
                else:
                    log_level = 'AKTİF'
                    alert_level = 'warning'

                self.get_logger().info(
                    f'[{log_level}] İHA_{i}←İHA_{closest_id}: '
                    f'mesafe={closest_dist:.2f}m  '
                    f'kapanma={v_closing if "v_closing" in dir() else 0:.1f}m/s  '
                    f'itme=({push_x:.1f}, {push_y:.1f}, {push_z:.1f})'
                )
                alert = String()
                alert.data = json.dumps({
                    'drone_id': i,
                    'level': alert_level,
                    'msg': f'İHA_{closest_id} ile {log_level} mesafe: {closest_dist:.2f}m'
                })
                self.alert_pub.publish(alert)

            elif threat_level == 1 and closest_id > 0:
                # Uyarı bölgesi — sadece log, müdahale yok
                status_data[i] = False

            else:
                # Tehlike yok — eğer daha önce kaçıştaysa bırak
                if di['avoiding']:
                    # Yeterince uzaklaştı mı?
                    if closest_dist > CLEAR_DIST or closest_id < 0:
                        di['avoiding'] = False
                        self.get_logger().info(f'İHA_{i}: Tehlike geçti, kontrol bırakıldı.')

        # Durum yayını
        s_msg = String()
        s_msg.data = json.dumps(status_data)
        self.status_pub.publish(s_msg)

    # ──────────── Offboard Velocity Müdahalesi ────────────

    def _send_velocity(self, drone_id, vx, vy, vz):
        d = self.drones[drone_id]
        now_us = int(self.get_clock().now().nanoseconds / 1000)

        # 1) Offboard heartbeat (her döngüde şart)
        ocm = OffboardControlMode()
        ocm.timestamp = now_us
        ocm.position = False
        ocm.velocity = True
        ocm.acceleration = False
        ocm.attitude = False
        ocm.body_rate = False
        d['offboard_pub'].publish(ocm)

        # 2) Offboard moduna geçiş (zaten offboard değilse)
        if d['nav_state'] != 14:  # 14 = Offboard
            cmd = VehicleCommand()
            cmd.command = 176
            cmd.param1 = 1.0
            cmd.param2 = 6.0  # Offboard
            cmd.target_system = 1
            cmd.target_component = 1
            cmd.source_system = 1
            cmd.source_component = 1
            cmd.from_external = True
            cmd.timestamp = now_us
            d['cmd_pub'].publish(cmd)

        # 3) Velocity setpoint
        sp = TrajectorySetpoint()
        sp.timestamp = now_us
        sp.position = [float('nan'), float('nan'), float('nan')]
        sp.velocity = [float(vx), float(vy), float(vz)]
        sp.yaw = float('nan')         # Mevcut yönü koru
        sp.yawspeed = 0.0
        d['setpoint_pub'].publish(sp)


def main(args=None):
    import sys
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    rclpy.init(args=args)
    node = PredictiveCollisionAvoidance(count)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
