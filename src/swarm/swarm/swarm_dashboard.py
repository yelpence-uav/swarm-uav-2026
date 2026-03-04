#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from px4_msgs.msg import VehicleOdometry  # DİKKAT: Artık Odometry dinliyoruz!
from functools import partial
import os

class SwarmDashboard(Node):
    def __init__(self):
        super().__init__('swarm_dashboard')
        
        self.drones = [1, 2, 3, 4, 5]
        self.positions = {i: {'x': 0.0, 'y': 0.0, 'z': 0.0} for i in self.drones}

        for i in self.drones:
            # DİKKAT: Kanal ismi vehicle_odometry olarak değiştirildi!
            topic_name = f'/px4_{i}/fmu/out/vehicle_odometry'
            self.create_subscription(
                VehicleOdometry,
                topic_name,
                partial(self.position_callback, drone_id=i),
                qos_profile_sensor_data
            )
            
        self.timer = self.create_timer(0.5, self.timer_callback)

    def position_callback(self, msg, drone_id):
        # Odometry mesajında X, Y, Z değerleri "position" isimli bir dizinin içindedir (0:X, 1:Y, 2:Z)
        self.positions[drone_id]['x'] = msg.position[0]
        self.positions[drone_id]['y'] = msg.position[1]
        self.positions[drone_id]['z'] = msg.position[2]

    def timer_callback(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        
        print("=========================================")
        print("       🛰️ SÜRÜ CANLI TELEMETRİ 🛰️       ")
        print("=========================================")
        print("BİRİM    | İLERİ (X) | SAĞ/SOL (Y)| YÜKSEKLİK (Z)")
        print("-----------------------------------------")
        
        for i in self.drones:
            pos = self.positions[i]
            print(f"Drone {i}  |  {pos['x']:>7.2f}  |  {pos['y']:>9.2f}  |  {pos['z']:>11.2f}")
            
        print("=========================================")

def main(args=None):
    rclpy.init(args=args)
    node = SwarmDashboard()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()