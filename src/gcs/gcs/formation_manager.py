import math
import json
import time
from std_msgs.msg import String

# Durum Makinesi Sabitleri
STATE_IDLE        = 0  # Hedef yok, yerinde dur
STATE_ROTATING    = 1  # Hedefe dön (yerinde), formasyon şeklini koru
STATE_STABILIZING = 2  # Dönüş bitti, drone'lar yerine otursun (3 sn bekleme)
STATE_MOVING      = 3  # Hedefe git (hep birlikte)

# Dönüş hassasiyeti (radyan) — bu açı altında "hedefe baktın" sayılır
YAW_TOLERANCE = 0.15  # ~8.6 derece
# Dönüş hızı (radyan/saniye)
YAW_RATE = 0.8  # ~46 derece/saniye
# Stabilizasyon bekleme süresi (saniye)
STABILIZE_WAIT = 10.0
# LiDAR güvenilirlik eşiği (metre) — bu değerin üstündeki okumalar menzil dışı sayılır
LIDAR_MAX_RELIABLE = 7.5


class FormationManager:
    def __init__(self, socketio):
        self.socketio = socketio
        self.active = False
        self.spacing = 2.0
        self.swarm_speed = 1.5
        self.formation_type = "arrowhead"
        self.bridge_node = None
        self.manual_mask = []

        # SANAL MERKEZ MATEMATİĞİ
        self.virtual_x = 0.0
        self.virtual_y = 0.0
        self.virtual_alt = 5.0  # KESİN İRTİFA KİLİDİ
        self.target_x = 0.0
        self.target_y = 0.0
        self.virtual_yaw = 0.0

        # DURUM MAKİNESİ
        self.state = STATE_IDLE
        self.target_yaw = 0.0  # Hedefe bakış açısı
        self._stabilize_start_time = 0.0  # Stabilizasyon başlangıç zamanı

        # LİDER İHA TAKİBİ
        self._cached_active_ids = []

        # FORMASYON DURUMU YAYINI
        self._formation_status_pub = None

    def _ensure_publisher(self):
        """Bridge node bağlandıktan sonra publisher'ı oluştur."""
        if self._formation_status_pub is None and self.bridge_node is not None:
            self._formation_status_pub = self.bridge_node.create_publisher(
                String, '/swarm/formation_status', 10
            )

    def _publish_formation_status(self, active_ids):
        """Formasyon durumunu çarpışma önleyiciye bildir."""
        self._ensure_publisher()
        if self._formation_status_pub is None:
            return
        state_names = {STATE_IDLE: "idle", STATE_ROTATING: "rotating", STATE_STABILIZING: "stabilizing", STATE_MOVING: "moving"}
        status = {
            'active': self.active,
            'drone_ids': active_ids,
            'spacing': self.spacing,
            'type': self.formation_type,
            'state': state_names.get(self.state, "idle")
        }
        msg = String()
        msg.data = json.dumps(status)
        self._formation_status_pub.publish(msg)

    def _get_active_ids(self):
        """Havada olan ve manuel kontrol altında olmayan İHA ID'lerini sıralı döndürür.
        En küçük ID her zaman lider (index 0) olur."""
        if self.bridge_node is None:
            return []
        active_ids = []
        for d_id, d_data in self.bridge_node.drones.items():
            is_flying = d_data.get('status', {}).get('armed', False) or d_data.get('local_z', 0.0) < -0.3
            if is_flying and d_id not in self.manual_mask:
                active_ids.append(d_id)
        active_ids.sort()
        return active_ids

    def _get_body_offset(self, slot_index, num_drones):
        """Formasyondaki bir slot'un body-frame offset'ini hesaplar.
        slot_index 0 = lider."""
        i = slot_index
        row = (i + 1) // 2 if i > 0 else 0
        side = 1 if (i % 2 == 1) else -1 if i > 0 else 0

        if self.formation_type == "line":
            body_x = 0.0
            body_y = side * row * self.spacing
        elif self.formation_type == "column":
            body_x = -i * self.spacing
            body_y = 0.0
        elif self.formation_type == "reverse_arrowhead":
            body_x = row * self.spacing
            body_y = side * row * self.spacing
        else:  # arrowhead (varsayılan)
            body_x = -row * self.spacing
            body_y = side * row * self.spacing

        return body_x, body_y

    @staticmethod
    def _normalize_angle(angle):
        """Açıyı -pi ile +pi arasına normalize et."""
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle

    def _shortest_angle_diff(self, target, current):
        """İki açı arasındaki en kısa farkı bul (yön bilgisiyle)."""
        diff = self._normalize_angle(target - current)
        return diff

    def start(self, spacing=2.0, speed=1.5, formation_type="arrowhead"):
        self.spacing = spacing
        self.swarm_speed = speed
        self.formation_type = formation_type

        if self.bridge_node is not None:
            self.active = True
            self.state = STATE_IDLE
            self._ensure_publisher()
            
            # Başlangıçta havada olan dronları bul
            active_drones = []
            for id, d in self.bridge_node.drones.items():
                if d.get('status', {}).get('armed', False) or d.get('local_z', 0.0) < -0.3:
                    active_drones.append(d)
                    
            if active_drones:
                self.virtual_x = sum([d.get('unified_x', d['x']) for d in active_drones]) / len(active_drones)
                self.virtual_y = sum([d.get('unified_y', d['y']) for d in active_drones]) / len(active_drones)
                
                # İRTİFAYI LİDAR İLE OKUYUP KİLİTLE
                alt_list = []
                for d in active_drones:
                    lidar_alt = min(d['lidar']) if d.get('lidar') else None
                    if lidar_alt is not None and lidar_alt < LIDAR_MAX_RELIABLE:
                        alt_list.append(lidar_alt)
                    elif d.get('dist_bottom', 0) > 0:
                        alt_list.append(d['dist_bottom'])
                    else:
                        alt_list.append(-d.get('local_z', -5.0))
                
                self.virtual_alt = sum(alt_list) / len(alt_list) if alt_list else 5.0

                self.target_x = self.virtual_x
                self.target_y = self.virtual_y

            self.bridge_node.get_logger().info(f">>> FORMATION: Sanal Merkez Aktif. Tip: {self.formation_type}, Aralık: {self.spacing}m")

            # Dronları Loiter moduna geçir
            for d_id in self.bridge_node.drones.keys():
                self.bridge_node.send_command(d_id, 176, param1=1.0, param2=4.0, param3=3.0)
        else:
            self.active = False

    def set_target(self, x, y):
        """Hedef noktayı ayarla. Önce hedefe dönülür, sonra gidilir."""
        active_ids = self._get_active_ids()
        num_drones = len(active_ids)

        # Lider offset kompansasyonu
        if num_drones > 0:
            leader_body_x, leader_body_y = self._get_body_offset(0, num_drones)
        else:
            leader_body_x, leader_body_y = 0.0, 0.0

        # Hedef yönüne göre yaw hesapla
        dx = x - self.virtual_x
        dy = y - self.virtual_y
        dist = math.hypot(dx, dy)

        if dist > 0.3:
            self.target_yaw = math.atan2(dy, dx)
            
            # Liderin body offset'ini world-frame'e çevir (hedef yaw'a göre)
            world_offset_x = (leader_body_x * math.cos(self.target_yaw)) - (leader_body_y * math.sin(self.target_yaw))
            world_offset_y = (leader_body_x * math.sin(self.target_yaw)) + (leader_body_y * math.cos(self.target_yaw))
            
            self.target_x = x - world_offset_x
            self.target_y = y - world_offset_y

            # DURUM: DÖNÜŞ FAZINa geç
            self.state = STATE_ROTATING

            if self.bridge_node:
                leader_id = active_ids[0] if active_ids else "?"
                yaw_deg = math.degrees(self.target_yaw)
                self.bridge_node.get_logger().info(
                    f">>> HEDEF AYARLANDI: Lider İHA {leader_id} -> ({x:.2f}, {y:.2f}) | "
                    f"Yaw: {yaw_deg:.1f}° | Durum: ÖNCE DÖN"
                )
        else:
            # Çok yakın, doğrudan git
            self.target_x = x
            self.target_y = y
            self.state = STATE_MOVING

    def stop(self):
        self.active = False
        self.state = STATE_IDLE
        if self._formation_status_pub is not None:
            msg = String()
            msg.data = json.dumps({
                'active': False, 'drone_ids': [], 'spacing': self.spacing,
                'type': self.formation_type, 'state': 'idle'
            })
            self._formation_status_pub.publish(msg)

    def run_loop(self):
        dt = 0.05  # 20 Hz
        while True:
            self.socketio.sleep(dt)

            if not self.active or self.bridge_node is None:
                continue

            # 1. DİNAMİK RÜTBELENDİRME
            active_ids = self._get_active_ids()
            self._cached_active_ids = active_ids

            if not active_ids:
                continue

            # 2. FORMASYON DURUMUNU YAYINLA
            self._publish_formation_status(active_ids)

            # ═══════════════════════════════════════════════
            # DURUM MAKİNESİ
            # ═══════════════════════════════════════════════

            if self.state == STATE_ROTATING:
                # ── FAZ 1: YERİNDE DÖN ──
                # Sanal merkez hareket ETMİYOR, sadece yaw hedefe doğru dönüyor.
                # Drone'lar formasyonu koruyarak etrafta yer değiştirir.
                yaw_diff = self._shortest_angle_diff(self.target_yaw, self.virtual_yaw)

                if abs(yaw_diff) < YAW_TOLERANCE:
                    # Dönüş tamamlandı → STABİLİZASYON FAZına geç (3 sn bekle)
                    self.virtual_yaw = self.target_yaw
                    self.state = STATE_STABILIZING
                    self._stabilize_start_time = time.time()
                    if self.bridge_node:
                        self.bridge_node.get_logger().info(
                            f">>> DÖNÜŞ TAMAM! Yaw: {math.degrees(self.virtual_yaw):.1f}° | {STABILIZE_WAIT:.0f} sn bekleniyor..."
                        )
                else:
                    # Yaw'ı kademeli olarak hedefe döndür
                    max_step = YAW_RATE * dt
                    if abs(yaw_diff) < max_step:
                        self.virtual_yaw = self.target_yaw
                    else:
                        self.virtual_yaw += max_step * (1.0 if yaw_diff > 0 else -1.0)
                    self.virtual_yaw = self._normalize_angle(self.virtual_yaw)

            elif self.state == STATE_STABILIZING:
                # ── FAZ 2: STABİLİZASYON BEKLEMESİ ──
                # Drone'lar formasyondaki yerlerine otursun diye bekliyoruz.
                # AYRICA lider drone'un fiziksel yaw'ının hedefe ulaşmasını doğruluyoruz.
                elapsed = time.time() - self._stabilize_start_time
                
                # LİDER DRONE FİZİKSEL YAW KONTROLÜ
                leader_yaw_ok = False
                if active_ids and self.bridge_node:
                    leader_id = active_ids[0]
                    leader_data = self.bridge_node.drones.get(leader_id, {})
                    # Drone yaw değeri derece cinsinden, target_yaw radyan
                    leader_physical_yaw_deg = leader_data.get('yaw', 0.0)
                    target_yaw_deg = math.degrees(self.target_yaw)
                    # En kısa açı farkını hesapla
                    yaw_error_deg = abs(self._normalize_angle(
                        math.radians(leader_physical_yaw_deg) - self.target_yaw
                    ))
                    leader_yaw_ok = yaw_error_deg < math.radians(15.0)  # ±15° tolerans
                else:
                    leader_yaw_ok = True  # Veri yoksa süreye güven
                
                # İKİ KOŞUL BİRLİKTE SAĞLANMALI:
                # 1) Minimum süre dolmuş olmalı
                # 2) Lider drone fiziksel olarak dönüşünü tamamlamış olmalı
                if elapsed >= STABILIZE_WAIT and leader_yaw_ok:
                    self.state = STATE_MOVING
                    if self.bridge_node:
                        self.bridge_node.get_logger().info(
                            f">>> STABİLİZASYON TAMAM! Lider yaw doğrulandı. İLERİ HAREKET BAŞLIYOR."
                        )
                elif elapsed >= STABILIZE_WAIT and not leader_yaw_ok:
                    # Süre doldu ama lider hâlâ dönmedi — bekle ve logla
                    if int(elapsed) % 3 == 0:  # Her 3 saniyede bir logla
                        if self.bridge_node:
                            self.bridge_node.get_logger().warn(
                                f">>> BEKLEME: Lider drone hâlâ dönüyor... "
                                f"Fiziksel yaw hatası: {math.degrees(yaw_error_deg):.1f}°"
                            )
                # Bekleme sırasında sanal merkez hareket etmez, drone'lar pozisyonlarına oturur.

            elif self.state == STATE_MOVING:
                # ── FAZ 2: HEP BİRLİKTE İLERİ ──
                dx = self.target_x - self.virtual_x
                dy = self.target_y - self.virtual_y
                dist = math.hypot(dx, dy)

                if dist > 0.05:
                    step = self.swarm_speed * dt
                    if step > dist:
                        step = dist
                    self.virtual_x += (dx / dist) * step
                    self.virtual_y += (dy / dist) * step
                    # Yaw'ı hareket yönüne kilitle (hafif smooth)
                    move_yaw = math.atan2(dy, dx)
                    yaw_diff = self._shortest_angle_diff(move_yaw, self.virtual_yaw)
                    self.virtual_yaw += yaw_diff * 0.1  # Çok yumuşak yaw takibi
                    self.virtual_yaw = self._normalize_angle(self.virtual_yaw)
                else:
                    # Hedefe ulaşıldı
                    self.state = STATE_IDLE
                    if self.bridge_node:
                        self.bridge_node.get_logger().info(">>> HEDEFE ULAŞILDI! Formasyon bekleme modunda.")

            # else: STATE_IDLE — hiçbir şey yapma, yerinde dur

            # ═══════════════════════════════════════════════
            # 3. İHA'LARI SANAL MERKEZİN ETRAFINA KOMUTA ET
            # ═══════════════════════════════════════════════
            for i, f_id in enumerate(active_ids):
                
                body_x, body_y = self._get_body_offset(i, len(active_ids))

                f_target_x = self.virtual_x + (body_x * math.cos(self.virtual_yaw)) - (body_y * math.sin(self.virtual_yaw))
                f_target_y = self.virtual_y + (body_x * math.sin(self.virtual_yaw)) + (body_y * math.cos(self.virtual_yaw))

                f_data = self.bridge_node.drones[f_id]
                f_ref_alt = f_data.get('ref_alt', 0.0)
                
                # LİDAR İLE DİNAMİK İRTİFA DÜZELTMESİ
                current_ekf_alt = -f_data.get('local_z', -self.virtual_alt)
                
                true_alt = current_ekf_alt
                lidar_alt = min(f_data['lidar']) if f_data.get('lidar') else None
                if lidar_alt is not None and lidar_alt < LIDAR_MAX_RELIABLE:
                    true_alt = lidar_alt
                elif f_data.get('dist_bottom', 0) > 0:
                    true_alt = f_data['dist_bottom']
                
                alt_error = self.virtual_alt - true_alt
                target_ekf_alt = current_ekf_alt + alt_error 
                target_amsl = f_ref_alt + target_ekf_alt

                master_lat = getattr(self.bridge_node, 'master_lat', f_data['gps']['lat'])
                master_lon = getattr(self.bridge_node, 'master_lon', f_data['gps']['lon'])

                target_lat = master_lat + (f_target_x / 111111.0)
                target_lon = master_lon + (f_target_y / (111111.0 * math.cos(math.radians(master_lat))))

                # DİNAMİK HIZ HESABI
                drone_x = f_data.get('unified_x', f_data.get('x', 0.0))
                drone_y = f_data.get('unified_y', f_data.get('y', 0.0))
                err_dist = math.hypot(f_target_x - drone_x, f_target_y - drone_y)

                if self.state == STATE_ROTATING:
                    # ── DÖNÜŞ FAZINDA: Yüksek minimum hız ──
                    # Lider (offset 0,0) bile yaw'ı değiştirebilsin.
                    # Follower'lar ark çizerken yeterli hıza sahip olsun.
                    body_radius = math.hypot(body_x, body_y)
                    arc_speed = body_radius * YAW_RATE  # Ark hızı = r × ω
                    
                    # Minimum hız: ark hızı veya swarm_speed, hangisi büyükse
                    min_rotate_speed = max(arc_speed, self.swarm_speed)
                    
                    if err_dist < 0.3:
                        reposition_speed = min_rotate_speed
                    elif err_dist > 2.0:
                        reposition_speed = min_rotate_speed * 2.0
                    else:
                        t = (err_dist - 0.3) / 1.7
                        reposition_speed = min_rotate_speed * (1.0 + t)
                else:
                    # ── HAREKET / BEKLEME FAZINDA: Normal dinamik hız ──
                    if err_dist < 0.5:
                        reposition_speed = self.swarm_speed * 0.5
                    elif err_dist > 3.0:
                        reposition_speed = self.swarm_speed * 2.5
                    else:
                        t = (err_dist - 0.5) / 2.5
                        reposition_speed = self.swarm_speed * (0.5 + t * 2.0)

                self.bridge_node.send_command(
                    f_id, 192,
                    param1=reposition_speed,
                    param2=1.0,
                    param4=self.virtual_yaw,
                    param5=target_lat,
                    param6=target_lon,
                    param7=target_amsl
                )