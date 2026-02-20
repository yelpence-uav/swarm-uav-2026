#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

class NetworkManagerNode(Node):
    def __init__(self):
        super().__init__('network_manager')
        self.get_logger().info('Yelpence Haberlesme (Network) Dugumu baslatildi. Ag trafigi yonetiliyor...')
        
        # Suru ici haberlesme yonetimi, QoS (Quality of Service) profilleri
        # ve GCS ile telemetri veri aktarimi islemleri burada yonetilecek.

def main(args=None):
    rclpy.init(args=args)
    node = NetworkManagerNode()
    
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
