#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

class TofRelay(Node):
    def __init__(self, drone_count):
        super().__init__('tof_relay_node')
        self.drone_count = drone_count
        self.subs = []
        
        self.sides = ['front', 'back', 'left', 'right']
        
        for i in range(self.drone_count):
            drone_id = i + 1
            for side in self.sides:
                # Subscriber for Gazebo ToF Sensor
                topic_in = f'/drone_{drone_id}/tof/{side}'
                
                sub = self.create_subscription(
                    LaserScan,
                    topic_in,
                    lambda msg, d_id=drone_id, s=side: self.tof_callback(msg, d_id, s),
                    10
                )
                self.subs.append(sub)
            
        self.get_logger().info(f"ToF Relay Başlatıldı: {drone_count} İHA (4 Yön) takip ediliyor.")

    def tof_callback(self, msg, drone_id, side):
        # Şimdilik sadece veri geldiğini doğrulamak için (İleride engel tespiti eklenebilir)
        pass

def main(args=None):
    import sys
    drone_count = 1
    if len(sys.argv) > 1:
        try:
            drone_count = int(sys.argv[1])
        except ValueError:
            pass

    rclpy.init(args=args)
    node = TofRelay(drone_count)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
