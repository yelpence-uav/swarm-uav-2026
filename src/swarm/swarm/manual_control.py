#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from px4_msgs.msg import OffboardControlMode, TrajectorySetpoint, VehicleCommand, VehicleStatus, VehicleLocalPosition
from std_msgs.msg import String
import json
import time
import math

class ManualControlV6(Node):
    def __init__(self):
        super().__init__('manual_control_node')
        
        self.drones = {}
        self.max_vel_h = 2.5  # Yatay maksimum hız (m/s)
        self.max_vel_v = 1.5  # Dikey maksimum hız (m/s)
        self.smoothing = 0.2  # Yumuşak geçiş katsayısı (0.1 - 0.3 ideal)
        
        qos_best = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST, depth=1)

        # GCS ile haberleşme
        self.create_subscription(String, '/gcs/manual_control', self.command_callback, 10)
        self.alert_pub = self.create_publisher(String, '/gcs/alerts', 10)
        self.system_pub = self.create_publisher(String, '/gcs/system_control', 10)
        self.manual_active_pub = self.create_publisher(String, '/gcs/manual_active_ids', 10)
        
        # 20Hz Kontrol Döngüsü
        self.timer = self.create_timer(0.05, self.control_loop)
        
        self.get_logger().info("--- MANUEL KONTROL v6.0 (TEMİZ KURULUM) AKTİF ---")

    def init_drone(self, drone_id):
        if drone_id not in self.drones:
            self.get_logger().info(f"İHA {drone_id} Sinyal Hattı Kuruluyor...")
            self.drones[drone_id] = {
                'active': False,
                'nav_state': 0,
                'current_yaw': 0.0,
                'last_cmd_time': time.time(),
                # Hedef ve Mevcut hızlar (Smooth geçiş için)
                'target': {'vx': 0.0, 'vy': 0.0, 'vz': 0.0, 'yaw_vel': 0.0},
                'current': {'vx': 0.0, 'vy': 0.0, 'vz': 0.0, 'yaw_vel': 0.0},
                'pubs': {
                    'offboard': self.create_publisher(OffboardControlMode, f'/drone_{drone_id}/fmu/in/offboard_control_mode', 10),
                    'setpoint': self.create_publisher(TrajectorySetpoint, f'/drone_{drone_id}/fmu/in/trajectory_setpoint', 10),
                    'command': self.create_publisher(VehicleCommand, f'/drone_{drone_id}/fmu/in/vehicle_command', 10)
                }
            }
            # Telemetri abonelikleri
            self.create_subscription(VehicleStatus, f'/drone_{drone_id}/fmu/out/vehicle_status_v2', 
                lambda msg, d_id=drone_id: self.status_callback(msg, d_id), QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST, depth=1))
            self.create_subscription(VehicleLocalPosition, f'/drone_{drone_id}/fmu/out/vehicle_local_position_v1',
                lambda msg, d_id=drone_id: self.pos_callback(msg, d_id), QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST, depth=1))

    def status_callback(self, msg, drone_id):
        self.drones[drone_id]['nav_state'] = msg.nav_state

    def pos_callback(self, msg, drone_id):
        # Radyan cinsinden heading
        self.drones[drone_id]['current_yaw'] = msg.heading

    def command_callback(self, msg):
        try:
            data = json.loads(msg.data)
            ids = data.get('ids', [])
            key = data.get('key')
            state = data.get('state') # 'down' veya 'up'

            for d_id in ids:
                self.init_drone(d_id)
                self.drones[d_id]['last_cmd_time'] = time.time()
                
                if key is None: # Tamamen durdur/kapat
                    self.send_bypass_signal(True) # Diğer sistemleri aç
                    self.drones[d_id]['active'] = False
                    self.drones[d_id]['target'] = {'vx': 0.0, 'vy': 0.0, 'vz': 0.0, 'yaw_vel': 0.0}
                    continue

                # Herhangi bir tuşa basıldıysa bypass gönder
                self.send_bypass_signal(False) # İrtifa korumayı kapat
                self.drones[d_id]['active'] = True
                
                val = 1.0 if state == 'down' else 0.0 # Tuş basılıysa hız var, bırakıldıysa 0
                t = self.drones[d_id]['target']
                
                # 1. Drone'un önü (vx) ve arkası
                if key == 'w': t['vx'] = val * self.max_vel_h
                elif key == 's': t['vx'] = -val * self.max_vel_h
                # 2. Drone'un sağı (vy) ve solu
                elif key == 'a': t['vy'] = -val * self.max_vel_h
                elif key == 'd': t['vy'] = val * self.max_vel_h
                # 4. Yön değiştirme (yaw)
                elif key == 'q': t['yaw_vel'] = -1.2 if state == 'down' else 0.0
                elif key == 'e': t['yaw_vel'] = 1.2 if state == 'down' else 0.0
                # 5. İrtifa artır/azalt (vz)
                elif key == 'shift': t['vz'] = -val * self.max_vel_v
                elif key == 'control': t['vz'] = val * self.max_vel_v
        except: pass

    def send_bypass_signal(self, enabled):
        # Kullanıcı isteği üzerine manuel kontrolde çarpışma önleyici artık kapatılmıyor.
        # Bu fonksiyon pasif hale getirildi.
        pass

    def set_offboard(self, drone_id):
        msg = VehicleCommand()
        msg.command = 176 # MAV_CMD_DO_SET_MODE
        msg.param1, msg.param2 = 1.0, 6.0 # Offboard Mode
        msg.target_system, msg.target_component = 1, 1
        msg.source_system, msg.source_component = 1, 1
        msg.from_external = True
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.drones[drone_id]['pubs']['command'].publish(msg)

    def control_loop(self):
        for d_id, data in self.drones.items():
            # Kalp Atışı (Zorunlu)
            ocm = OffboardControlMode()
            ocm.velocity = True
            ocm.timestamp = int(self.get_clock().now().nanoseconds / 1000)
            data['pubs']['offboard'].publish(ocm)
            
            # Deadman Switch: Yarım saniye sinyal gelmezse her şeyi sıfırla
            if time.time() - data['last_cmd_time'] > 0.5:
                data['target'] = {'vx': 0.0, 'vy': 0.0, 'vz': 0.0, 'yaw_vel': 0.0}

            # Exponential Smoothing: Motor sarsıntısını önle
            for axis in ['vx', 'vy', 'vz', 'yaw_vel']:
                data['current'][axis] += (data['target'][axis] - data['current'][axis]) * self.smoothing

            if data['active']:
                # Offboard Modu Zorla (Takeoff bittiyse)
                if data['nav_state'] not in [14, 17]: # 14: Offboard, 17: Takeoff
                    self.set_offboard(d_id)
                
                # ROTASYON MATRİSİ: Body Frame -> NED Frame
                # W/S ve A/D'yi İHA'nın bakış açısına (yaw) göre dünyaya çevir
                yaw = data['current_yaw']
                v_north = data['current']['vx'] * math.cos(yaw) - data['current']['vy'] * math.sin(yaw)
                v_east = data['current']['vx'] * math.sin(yaw) + data['current']['vy'] * math.cos(yaw)
                v_down = data['current']['vz']

                # Active Signal (v8.0.1)
                active_ids = [d_id for d_id, d in self.drones.items() if d['active']]
                active_msg = String()
                active_msg.data = json.dumps(active_ids)
                self.manual_active_pub.publish(active_msg)
                
                if active_ids:
                    self.get_logger().info(f"MANUEL AKTIF: {active_ids}")

                sp = TrajectorySetpoint()
                sp.position = [float('nan'), float('nan'), float('nan')]
                sp.velocity = [v_north, v_east, v_down]
                
                # Dönüş veya Yüz Kararı
                if abs(data['current']['yaw_vel']) > 0.01:
                    sp.yaw = float('nan') # Pusula kilidini bırak
                    sp.yawspeed = data['current']['yaw_vel']
                elif abs(data['current']['vx']) > 0.05 or abs(data['current']['vy']) > 0.05:
                    sp.yaw = float('nan') # Hareket anında mevcut yönü koru
                    sp.yawspeed = 0.0
                else:
                    sp.yaw = data['current_yaw'] # Dururken çapa at
                    sp.yawspeed = 0.0
                
                sp.timestamp = int(self.get_clock().now().nanoseconds / 1000)
                data['pubs']['setpoint'].publish(sp)

def main(args=None):
    rclpy.init(args=args)
    node = ManualControlV6()
    try:
        rclpy.spin(node)
    except: pass
    finally:
        if rclpy.ok(): rclpy.shutdown()

if __name__ == '__main__':
    main()
