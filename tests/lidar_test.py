#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
import os

class LidarTestNode(Node):
    def __init__(self):
        super().__init__('lidar_test_diagnostic')
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=5)
        self.subscription = self.create_subscription(
            LaserScan,
            '/drone_1/lidar/scan',
            self.listener_callback,
            qos)
        print("LiDAR Test Başlatıldı: /drone_1/lidar/scan dinleniyor (BEST_EFFORT)...")

    def listener_callback(self, msg):
        ranges = [r for r in msg.ranges if r > 0.05 and r < 50.0]
        if ranges:
            min_dist = min(ranges)
            max_dist = max(ranges)
            avg_dist = sum(ranges) / len(ranges)
            os.system('clear')
            print("="*40)
            print("LIDAR CANLI VERI (Drone 1)")
            print("="*40)
            print(f"Min Mesafe: {min_dist:.2f} m")
            print(f"Max Mesafe: {max_dist:.2f} m")
            print(f"Ortalama:   {avg_dist:.2f} m")
            print("-"*40)
            print("Çıkmak için Ctrl+C")

def main(args=None):
    rclpy.init(args=args)
    node = LidarTestNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
