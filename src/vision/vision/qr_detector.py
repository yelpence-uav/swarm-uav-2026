#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

class QRDetectorNode(Node):
    def __init__(self):
        super().__init__('qr_detector')
        self.get_logger().info('Yelpence Goruntu Isleme (QR) Dugumu baslatildi. Kamera verisi bekleniyor...')
        
        # Ilerleyen asamalarda ROS 2 uzerinden kamera goruntulerini (Image) dinleyen Subscriber
        # ve islenmis veriyi (QRData.msg) swarm paketine ileten Publisher buraya eklenecek.

def main(args=None):
    rclpy.init(args=args)
    node = QRDetectorNode()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print('\nDugum kullanici tarafindan durduruldu.')
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()
