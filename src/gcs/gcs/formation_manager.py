import math
import json
from std_msgs.msg import String

class FormationManager:
    """
    İHA Sürü Formasyon Yönetim Sınıfı.
    V-Tipi (Arrowhead) formasyonun matematiksel hesaplamalarını ve 10Hz döngüsünü yönetir.
    """
    def __init__(self, socketio):
        self.socketio = socketio
        self.active = False
        self.leader_id = -1
        self.spacing = 2.0
        self.formation_type = "arrowhead"
        self.bridge_node = None
        self.last_targets_xy = {}
        # Keep XY step above typical PX4 acceptance radius so reposition commands are actually executed.
        self.max_step_xy_m = 2.5
        self.max_step_alt_m = 0.70
        self.cmd_speed_mps = 0.8
        self.min_separation_m = 1.2
        self.on_road_states = {} # drone_id -> bool

    def start(self, leader_id, spacing=2.0, formation_type="arrowhead"):
        self.leader_id = leader_id
        self.spacing = spacing
        self.formation_type = formation_type
        self.last_targets_xy = {}
        if self.leader_id != -1 and self.bridge_node is not None:
            self.active = True
            print(
                f"FORMATION: Started {self.formation_type} with "
                f"Leader={self.leader_id}, Spacing={self.spacing}"
            )
            
            # Tüm takipçileri LOITER (HOLD) moduna geçir ki komutları kabul etsinler
            # MAV_CMD_DO_SET_MODE (176), Param1: 1 (Custom), Param2: 4 (AUTO), Param3: 3 (LOITER)
            for d_id in self.bridge_node.drones.keys():
                if d_id != self.leader_id:
                    self.bridge_node.send_command(d_id, 176, param1=1.0, param2=4.0, param3=3.0)
                    print(f"FORMATION: Drone {d_id} forced to LOITER mode.")
        else:
            self.active = False
            print("FORMATION: Leader ID invalid or Bridge Not Ready, stopping.")

    def stop(self):
        self.active = False
        self.leader_id = -1
        self.last_targets_xy = {}
        print("FORMATION: Stopped.")

    def _limit_step(self, current_x, current_y, target_x, target_y):
        dx = target_x - current_x
        dy = target_y - current_y
        dist = math.hypot(dx, dy)
        if dist <= self.max_step_xy_m or dist < 1e-6:
            return target_x, target_y
        s = self.max_step_xy_m / dist
        return current_x + (dx * s), current_y + (dy * s)

    def run_loop(self):
        """
        10Hz hızında çalışan formasyon takip döngüsü.
        """
        while True:
            self.socketio.sleep(0.1) 
            
            if not self.active or self.bridge_node is None or self.leader_id == -1:
                if self.on_road_states: # Clear if inactive
                    self.on_road_states = {}
                    self._publish_nav_status()
                continue
                
            if self.leader_id not in self.bridge_node.drones:
                continue
            
            # Lider verilerini al
            leader = self.bridge_node.drones[self.leader_id]
            l_x = leader['x']
            l_y = leader['y']
            l_yaw_deg = leader.get('yaw', 0.0)
            l_yaw_rad = math.radians(l_yaw_deg)
            
            # Liderin BAĞIL (Relative) yüksekliğini belirle (LiDAR > DistBottom > EKF)
            l_rel_alt = -leader['local_z'] # Varsayılan EKF (-z = up)
            if leader.get('lidar') and len(leader['lidar']) > 0:
                l_rel_alt = min(leader['lidar'])
            elif leader.get('dist_bottom', 0) > 0:
                l_rel_alt = leader['dist_bottom']
            
            # Takipçileri belirle (ID sırasına göre).
            # Not: x/y == 0 filtresi uygulanırsa orijinde duran drone (örn. Drone 1) hiç komut almaz.
            armed_ids = []
            for d_id, d_data in self.bridge_node.drones.items():
                if d_id != self.leader_id:
                    if d_data.get('status', {}).get('armed', False):
                        armed_ids.append(d_id)

            # Eğer armed durumu henüz telemetriye düşmediyse (QoS gecikmesi vb.),
            # formasyonu tamamen durdurmamak için tüm takipçileri hedefle.
            if armed_ids:
                active_ids = armed_ids
            else:
                active_ids = [d_id for d_id in self.bridge_node.drones.keys() if d_id != self.leader_id]

            active_ids.sort()
            
            # GCS'de OFFBOARD mesajları yüklü mü?
            has_offboard = hasattr(self.bridge_node, 'offboard_ctrl_pubs') and len(self.bridge_node.offboard_ctrl_pubs) > 0
            
            desired_targets_xy = {}
            for i, f_id in enumerate(active_ids):
                # Leader body frame offsets by formation type.
                if self.formation_type == "line":
                    offset_idx = i - ((len(active_ids) - 1) / 2.0)
                    body_x = 0.0
                    body_y = offset_idx * self.spacing
                elif self.formation_type == "column":
                    body_x = -(i + 1) * self.spacing
                    body_y = 0.0
                elif self.formation_type in ("reverse_arrowhead", "circle"):
                    # "circle" kept as backward-compatible alias.
                    row = (i // 2) + 1
                    side = 1 if (i % 2 == 0) else -1
                    body_x = row * self.spacing
                    body_y = side * row * self.spacing
                else:
                    # Default: arrowhead (V)
                    row = (i // 2) + 1
                    side = 1 if (i % 2 == 0) else -1
                    body_x = -row * self.spacing
                    body_y = side * row * self.spacing
                
                # Rotate offsets by Leader Yaw
                f_target_x = l_x + (body_x * math.cos(l_yaw_rad)) - (body_y * math.sin(l_yaw_rad))
                f_target_y = l_y + (body_x * math.sin(l_yaw_rad)) + (body_y * math.cos(l_yaw_rad))
                desired_targets_xy[f_id] = (f_target_x, f_target_y)

            for f_id in active_ids:
                f_data = self.bridge_node.drones[f_id]
                f_ref_alt = f_data.get('ref_alt', 0.0)
                desired_x, desired_y = desired_targets_xy.get(f_id, (l_x, l_y))

                # Smooth transition in command space.
                # Do NOT use follower local x/y here (different local frames can cause drift).
                prev_x, prev_y = self.last_targets_xy.get(f_id, (desired_x, desired_y))
                f_target_x, f_target_y = self._limit_step(prev_x, prev_y, desired_x, desired_y)
                
                # İrtifa eşitleme: liderin gerçek bağıl yüksekliğini takipçiye kapalı döngü uygula.
                # Sadece ref_alt kullanımı drone'lar arası EKF ofsetinde kalıcı irtifa farkı üretebiliyor.
                f_current_ekf_alt = -f_data.get('local_z', 0.0)
                f_true_alt = f_current_ekf_alt
                if f_data.get('lidar') and len(f_data['lidar']) > 0:
                    f_true_alt = min(f_data['lidar'])
                elif f_data.get('dist_bottom', 0.0) > 0.0:
                    f_true_alt = f_data['dist_bottom']

                alt_error = l_rel_alt - f_true_alt
                alt_error = max(-self.max_step_alt_m, min(self.max_step_alt_m, alt_error))
                target_ekf_alt = f_current_ekf_alt + alt_error
                target_amsl = f_ref_alt + target_ekf_alt
                
                try:
                    # Yüksek Hassasiyetli OFFBOARD Kontrol (Eğer mesaj kütüphanesi hazırsa)
                    if has_offboard:
                        self.bridge_node.publish_offboard_control_mode(f_id)
                        self.bridge_node.publish_trajectory_setpoint(f_id, f_target_x, f_target_y, -l_rel_alt, l_yaw_rad)
                    else:
                        # Alternatif: Klasik REPOSITION (192) - GPS Tabanlı
                        target_lat = leader['gps']['lat'] + (f_target_x - l_x) / 111111.0
                        target_lon = leader['gps']['lon'] + (f_target_y - l_y) / (111111.0 * math.cos(math.radians(leader['gps']['lat'])))

                        # ÖNEMLİ: param1=-1.0 (default speed), param2=1.0 (Force coordinate frame/reposition)
                        self.bridge_node.send_command(
                            f_id,
                            192,
                            param1=self.cmd_speed_mps,
                            param2=1.0,
                            param4=l_yaw_rad,
                            param5=target_lat,
                            param6=target_lon,
                            param7=target_amsl
                        )
                        self.last_targets_xy[f_id] = (f_target_x, f_target_y)
                except Exception as exc:
                    print(f"FORMATION: command publish failed for Drone {f_id}: {exc}")
            
            # Update and publish On-Road states
            self._update_on_road_states(active_ids, desired_targets_xy)

    def _update_on_road_states(self, active_ids, desired_targets):
        changed = False
        new_states = {}
        for d_id in active_ids:
            if d_id in desired_targets and d_id in self.bridge_node.drones:
                d_data = self.bridge_node.drones[d_id]
                tx, ty = desired_targets[d_id]
                dist = math.hypot(d_data['x'] - tx, d_data['y'] - ty)
                on_road = dist > 0.5 # Moving if > 50cm from target
                new_states[d_id] = on_road
                if on_road != self.on_road_states.get(d_id, False):
                    changed = True
        
        if changed or len(new_states) != len(self.on_road_states):
            self.on_road_states = new_states
            self._publish_nav_status()

    def _publish_nav_status(self):
        if self.bridge_node and hasattr(self.bridge_node, 'nav_status_pub'):
            msg = String()
            msg.data = json.dumps(self.on_road_states)
            self.bridge_node.nav_status_pub.publish(msg)
