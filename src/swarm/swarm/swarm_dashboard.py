#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from px4_msgs.msg import VehicleOdometry
from functools import partial
import time
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

class SwarmDashboard(Node):
    def __init__(self):
        super().__init__('swarm_dashboard')
        
        self.drones = [1, 2, 3, 4, 5]
        self.positions = {i: {'x': 0.0, 'y': 0.0, 'z': 0.0} for i in self.drones}
        self.last_msg_time = {i: time.time() for i in self.drones} # Son mesaj gelme zamanları

        best_effort_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        for i in self.drones:
            # DİKKAT: Artık doğrudan dronları değil, Kaos Düğümünden (delayed_odometry) süzülen veriyi dinliyoruz
            topic_name = f'/swarm/px4_{i}/delayed_odometry'
            
            self.create_subscription(
                VehicleOdometry,
                topic_name,
                partial(self.position_callback, drone_id=i),
                best_effort_qos
            )
            
        # Ekranı çok daha hızlı yenile (Saniyede 20 kere)
        self.timer = self.create_timer(0.05, self.timer_callback)

    def position_callback(self, msg, drone_id):
        self.positions[drone_id]['x'] = msg.position[0]
        self.positions[drone_id]['y'] = msg.position[1]
        self.positions[drone_id]['z'] = msg.position[2]
        self.last_msg_time[drone_id] = time.time() # Veri geldiği an kronometreyi sıfırla

    def timer_callback(self):
        print('\033c', end='')
        
        print("=========================================================")
        print("             🛰️ SÜRÜ CANLI TELEMETRİ RADARI 🛰️             ")
        print("=========================================================")
        print("BİRİM   | İLERİ(X) | SAĞ/SOL(Y) | YÜKSEKLİK(Z)| AĞ DURUMU")
        print("---------------------------------------------------------")
        
        current_time = time.time()
        
        for i in self.drones:
            pos = self.positions[i]
            age = current_time - self.last_msg_time[i] # Veri kaç saniye önce geldi?
            
            # Ağ durumunu analiz et
            if age > 0.5:
                status = "🔴 BAĞLANTI KOPTU!"
            elif age > 0.15:
                status = f"🟡 GECİKME ({age*1000:.0f}ms)"
            else:
                status = "🟢 STABİL"

            print(f"Drone {i} | {pos['x']:>8.2f} | {pos['y']:>10.2f} | {pos['z']:>11.2f} | {status}")
            
        print("=========================================================")

def main(args=None):
    rclpy.init(args=args)
    node = SwarmDashboard()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()