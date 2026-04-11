import math
import json
import time
from std_msgs.msg import String

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

    def start(self, spacing=2.0, speed=1.5, formation_type="arrowhead"):
        self.spacing = spacing
        self.swarm_speed = speed
        self.formation_type = formation_type

        if self.bridge_node is not None:
            self.active = True
            
            # Başlangıçta havada olan (Yerden >30cm yüksekte) dronları bul
            active_drones = []
            for id, d in self.bridge_node.drones.items():
                if d.get('status', {}).get('armed', False) or d.get('local_z', 0.0) < -0.3:
                    active_drones.append(d)
                    
            if active_drones:
                self.virtual_x = sum([d.get('unified_x', d['x']) for d in active_drones]) / len(active_drones)
                self.virtual_y = sum([d.get('unified_y', d['y']) for d in active_drones]) / len(active_drones)
                
                # --- YENİ: İRTİFAYI LİDAR İLE OKUYUP KİLİTLE ---
                # Barometre yalan söylese bile, başlangıçta yere lazer tutup gerçek ortalamayı alıyoruz
                alt_list = []
                for d in active_drones:
                    if d.get('lidar'):
                        alt_list.append(min(d['lidar']))
                    elif d.get('dist_bottom', 0) > 0:
                        alt_list.append(d['dist_bottom'])
                    else:
                        alt_list.append(-d.get('local_z', -5.0))
                
                self.virtual_alt = sum(alt_list) / len(alt_list) if alt_list else 5.0
                # -----------------------------------------------

                self.target_x = self.virtual_x
                self.target_y = self.virtual_y

            self.bridge_node.get_logger().info(f">>> FORMATION: Sanal Merkez Aktif. Tip: {self.formation_type}")

            # Dronları komutları dinlemeleri için Loiter moduna geçir
            for d_id in self.bridge_node.drones.keys():
                self.bridge_node.send_command(d_id, 176, param1=1.0, param2=4.0, param3=3.0)
        else:
            self.active = False

    def set_target(self, x, y):
        self.target_x = x
        self.target_y = y

    def stop(self):
        self.active = False

    def run_loop(self):
        while True:
            self.socketio.sleep(0.1) # 10 Hz Yenileme Hızı

            if not self.active or self.bridge_node is None:
                continue

            # 1. DİNAMİK RÜTBELENDİRME
            active_ids = []
            for d_id, d_data in self.bridge_node.drones.items():
                is_flying = d_data.get('status', {}).get('armed', False) or d_data.get('local_z', 0.0) < -0.3
                if is_flying and d_id not in self.manual_mask:
                    active_ids.append(d_id)
            active_ids.sort()

            if not active_ids:
                continue

            # 2. SANAL MERKEZİ HEDEFE KAYDIR
            dx = self.target_x - self.virtual_x
            dy = self.target_y - self.virtual_y
            dist = math.hypot(dx, dy)

            if dist > 0.05:
                step = self.swarm_speed * 0.1 
                if step > dist:
                    step = dist
                self.virtual_x += (dx / dist) * step
                self.virtual_y += (dy / dist) * step
                self.virtual_yaw = math.atan2(dy, dx)

            # 3. İHA'LARI SANAL MERKEZİN ETRAFINA IŞINLA
            for i, f_id in enumerate(active_ids):
                
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
                else: 
                    body_x = -row * self.spacing  
                    body_y = side * row * self.spacing

                f_target_x = self.virtual_x + (body_x * math.cos(self.virtual_yaw)) - (body_y * math.sin(self.virtual_yaw))
                f_target_y = self.virtual_y + (body_x * math.sin(self.virtual_yaw)) + (body_y * math.cos(self.virtual_yaw))

                f_data = self.bridge_node.drones[f_id]
                f_ref_alt = f_data.get('ref_alt', 0.0)
                
                # --- YENİ: LİDAR İLE DİNAMİK İRTİFA DÜZELTMESİ ---
                current_ekf_alt = -f_data.get('local_z', -self.virtual_alt)
                
                # Lazerden gelen fiziksel gerçeği oku
                true_alt = current_ekf_alt
                if f_data.get('lidar'):
                    true_alt = min(f_data['lidar'])
                elif f_data.get('dist_bottom', 0) > 0:
                    true_alt = f_data['dist_bottom']
                
                # Drone fiziksel olarak hedeften ne kadar saptı? (Örn: Çarpışma önleyici yüzünden 50cm düştü)
                alt_error = self.virtual_alt - true_alt
                
                # EKF'nin hedefini bu hataya göre kaydırarak dronu fiziksel ipe geri çek!
                target_ekf_alt = current_ekf_alt + alt_error 
                target_amsl = f_ref_alt + target_ekf_alt
                # -------------------------------------------------

                master_lat = getattr(self.bridge_node, 'master_lat', f_data['gps']['lat'])
                master_lon = getattr(self.bridge_node, 'master_lon', f_data['gps']['lon'])

                target_lat = master_lat + (f_target_x / 111111.0)
                target_lon = master_lon + (f_target_y / (111111.0 * math.cos(math.radians(master_lat))))

                self.bridge_node.send_command(
                    f_id, 192,
                    param1=self.swarm_speed * 1.5, 
                    param2=1.0,
                    param4=self.virtual_yaw,
                    param5=target_lat,
                    param6=target_lon,
                    param7=target_amsl
                )