#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
import os

class CameraTestNode(Node):
    def __init__(self):
        super().__init__('camera_test_diagnostic')
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=5)
        self.subscription = self.create_subscription(
            Image,
            '/drone_1/camera/image_raw',
            self.listener_callback,
            qos)
        self.msg_count = 0
        print("Kamera Test Başlatıldı: /drone_1/camera/image_raw dinleniyor (BEST_EFFORT)...")

    def listener_callback(self, msg):
        self.msg_count += 1
        os.system('clear')
        print("="*40)
        print("KAMERA CANLI VERI (Drone 1)")
        print("="*40)
        print(f"Görüntü Sayısı: {self.msg_count}")
        print(f"Çözünürlük:    {msg.width}x{msg.height}")
        print(f"Format:        {msg.encoding}")
        print("-"*40)
        print("Not: Terminalde sadece teknik veriler görünebilir.")
        print("Çıkmak için Ctrl+C")

def main(args=None):
    rclpy.init(args=args)
    node = CameraTestNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
