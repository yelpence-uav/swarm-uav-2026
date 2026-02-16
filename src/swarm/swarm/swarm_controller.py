#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

class SwarmControllerNode(Node):
    def __init__(self):
        super().__init__('swarm_controller')
        self.get_logger().info('Yelpence Suru Kontrol Dugumu baslatildi. Dinlemede...')
        
        # Ilerleyen asamalarda yelpence_msgs kullanarak 
        # Publisher (yayinci) ve Subscriber (dinleyici) tanimlamalarini buraya ekleyecegiz.

def main(args=None):
    rclpy.init(args=args)
    node = SwarmControllerNode()
    
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
