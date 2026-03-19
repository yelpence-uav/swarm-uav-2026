#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from px4_msgs.msg import ActuatorOutputs
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
import os

class MotorTestNode(Node):
    def __init__(self):
        super().__init__('motor_test_diagnostic')
        # PX4 uses Best Effort + Transient Local for many telemetry topics
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            depth=5)
        self.subscription = self.create_subscription(
            ActuatorOutputs,
            '/drone_1/fmu/out/actuator_outputs',
            self.listener_callback,
            qos)
        print("Motor Test Başlatıldı: /drone_1/fmu/out/actuator_outputs dinleniyor (BEST_EFFORT)...")

    def listener_callback(self, msg):
        outputs = msg.output[:4]
        os.system('clear')
        print("="*40)
        print("MOTOR CANLI VERI (Drone 1)")
        print("="*40)
        for i, val in enumerate(outputs):
            print(f"Motor {i+1}: {int(val)} PWM")
        print("-"*40)
        print("Not: Çarklar dönmüyorsa değerler 0 veya 1000 kalabilir.")
        print("Çıkmak için Ctrl+C")

def main(args=None):
    rclpy.init(args=args)
    node = MotorTestNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
