#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from px4_msgs.msg import OffboardControlMode, TrajectorySetpoint, VehicleCommand

class SynchronizedSwarmCommander(Node):
    def __init__(self):
        super().__init__('sync_swarm_commander')
        
        self.drones = [1, 2, 3, 4, 5]  
        self.pubs = {}
        
        for i in self.drones:
            prefix = f'/px4_{i}'
            self.pubs[i] = {
                'mode': self.create_publisher(OffboardControlMode, f'{prefix}/fmu/in/offboard_control_mode', 10),
                'setpoint': self.create_publisher(TrajectorySetpoint, f'{prefix}/fmu/in/trajectory_setpoint', 10),
                'cmd': self.create_publisher(VehicleCommand, f'{prefix}/fmu/in/vehicle_command', 10)
            }
            
        self.timer = self.create_timer(0.1, self.timer_callback)
        self.counter = 0  # Düdük için sayacımız
        
        self.get_logger().info(f'🚀 SENKRONİZE KOMUTAN BAŞLADI: {len(self.drones)} İHA hatta bağlanıyor...')

    def timer_callback(self):
        # 1. KISIM: ZORUNLU KALP ATIŞI (Her döngüde çalışmalı)
        # PX4'ün otonom modu reddetmemesi için sürekli hedef setpoint gönderiyoruz
        for i in self.drones:
            self.publish_offboard_control_mode(i)
            self.publish_trajectory_setpoint(i)
            
        # 2. KISIM: SENKRONİZASYON BEKLEMESİ (Herkesin sensörü uyansın)
        if self.counter < 100:
            if self.counter % 20 == 0:
                kalan = (100 - self.counter) // 10
                self.get_logger().info(f'⏳ Sürü senkronize ediliyor... {kalan} saniye kaldı.')
                
        # 3. KISIM: HAKEMİN DÜDÜĞÜ! (Tam 10. saniyede herkese aynı anda ateşle komutu)
        elif self.counter == 100:
            self.get_logger().info('🔥 TÜM SENSÖRLER HAZIR! SÜRÜ AYNI ANDA KALKIŞ YAPIYOR! 🔥')
            for i in self.drones:
                self.arm_and_set_offboard(i)
                
        # (Opsiyonel Güvenlik): Paket kaybolursa diye 1 saniye boyunca emri pekiştir
        elif 100 < self.counter <= 110:
            for i in self.drones:
                self.arm_and_set_offboard(i)

        self.counter += 1

    def publish_offboard_control_mode(self, drone_id):
        msg = OffboardControlMode()
        msg.position = True
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.pubs[drone_id]['mode'].publish(msg)

    def publish_trajectory_setpoint(self, drone_id):
        msg = TrajectorySetpoint()
        msg.position = [0.0, 0.0, -5.0]  # Dümdüz 5 metre yukarı
        msg.yaw = 0.0
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.pubs[drone_id]['setpoint'].publish(msg)

    def arm_and_set_offboard(self, drone_id):
        cmd_offboard = VehicleCommand()
        cmd_offboard.command = VehicleCommand.VEHICLE_CMD_DO_SET_MODE
        cmd_offboard.param1 = 1.0
        cmd_offboard.param2 = 6.0
        cmd_offboard.target_system = drone_id + 1  
        cmd_offboard.target_component = 1
        cmd_offboard.source_system = 255
        cmd_offboard.source_component = 1
        cmd_offboard.from_external = True
        cmd_offboard.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.pubs[drone_id]['cmd'].publish(cmd_offboard)

        cmd_arm = VehicleCommand()
        cmd_arm.command = VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM
        cmd_arm.param1 = 1.0
        cmd_arm.target_system = drone_id + 1       
        cmd_arm.target_component = 1
        cmd_arm.source_system = 255
        cmd_arm.source_component = 1
        cmd_arm.from_external = True
        cmd_arm.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.pubs[drone_id]['cmd'].publish(cmd_arm)

def main(args=None):
    rclpy.init(args=args)
    node = SynchronizedSwarmCommander()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()