#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
import os

class TofTestNode(Node):
    def __init__(self):
        super().__init__('tof_test_diagnostic')
        
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=5)
            
        self.sides = ['front', 'back', 'left', 'right']
        self.data = {side: 0.0 for side in self.sides}
        
        for side in self.sides:
            topic = f'/drone_1/tof/{side}'
            self.create_subscription(
                LaserScan,
                topic,
                lambda msg, s=side: self.tof_callback(msg, s),
                qos)
        
        self.create_timer(0.5, self.display)
        print("ToF Test Başlatıldı: Drone 1 (4 Yön) dinleniyor...")

    def tof_callback(self, msg, side):
        if msg.ranges:
            # Get first valid range
            for r in msg.ranges:
                if r > 0.01:
                    self.data[side] = r
                    break

    def display(self):
        os.system('clear')
        print("="*40)
        print("TOF SENSÖRÜ CANLI VERI (Drone 1)")
        print("="*40)
        print(f"ÖN:    {self.data['front']:.2f} m")
        print(f"ARKA:  {self.data['back']:.2f} m")
        print(f"SOL:   {self.data['left']:.2f} m")
        print(f"SAĞ:   {self.data['right']:.2f} m")
        print("-"*40)
        print("Çıkmak için Ctrl+C")

def main(args=None):
    rclpy.init(args=args)
    node = TofTestNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
