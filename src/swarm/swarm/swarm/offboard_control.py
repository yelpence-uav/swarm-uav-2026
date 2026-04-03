#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from px4_msgs.msg import OffboardControlMode, TrajectorySetpoint, VehicleCommand


class OffboardControlNode(Node):
    def __init__(self):
        super().__init__("offboard_control")

        # PX4 ile konuşacağımız veri kanalları (Publishers)
        self.offboard_ctrl_mode_pub = self.create_publisher(
            OffboardControlMode, "/fmu/in/offboard_control_mode", 10
        )
        self.trajectory_setpoint_pub = self.create_publisher(
            TrajectorySetpoint, "/fmu/in/trajectory_setpoint", 10
        )
        self.vehicle_command_pub = self.create_publisher(
            VehicleCommand, "/fmu/in/vehicle_command", 10
        )

        # 10 Hz (Saniyede 10 kere) çalışacak döngümüz
        self.timer = self.create_timer(0.1, self.timer_callback)
        self.setpoint_counter = 0

    def timer_callback(self):
        # 1. KURAL: PX4'e sürekli "Ben buradayım" mesajı (kalp atışı) göndermeliyiz
        self.publish_offboard_control_mode()
        self.publish_trajectory_setpoint()

        # 2. KURAL: PX4, komutları dinlemeye başlamadan önce en az 1 saniye (10 döngü) kalp atışı duymak ister
        if self.setpoint_counter == 10:
            self.publish_vehicle_command(
                VehicleCommand.VEHICLE_CMD_DO_SET_MODE, 1.0, 6.0
            )  # Offboard Moduna Geç
            self.arm_vehicle()  # Motorları Ateşle
            self.get_logger().info("Otonom Uçuş Başladı! Hedef: 5 Metre İrtifa")

        if self.setpoint_counter < 11:
            self.setpoint_counter += 1

    def publish_offboard_control_mode(self):
        msg = OffboardControlMode()
        msg.position = True  # Sadece pozisyon kontrolü yapacağız
        msg.velocity = False
        msg.acceleration = False
        msg.attitude = False
        msg.body_rate = False
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.offboard_ctrl_mode_pub.publish(msg)

    def publish_trajectory_setpoint(self):
        msg = TrajectorySetpoint()
        # DİKKAT: PX4, NED (Kuzey, Doğu, Aşağı) koordinat sistemini kullanır.
        # Bu yüzden yukarı çıkmak için Z eksenine eksi (-) değer vermeliyiz!
        msg.position = [0.0, 0.0, -5.0]  # X:0, Y:0, Z:-5 (Yani 5 metre yukarı)
        msg.yaw = 0.0  # Burnu kuzeye baksın
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.trajectory_setpoint_pub.publish(msg)

    def publish_vehicle_command(self, command, param1=0.0, param2=0.0):
        msg = VehicleCommand()
        msg.command = command
        msg.param1 = param1
        msg.param2 = param2
        msg.target_system = 1
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.vehicle_command_pub.publish(msg)

    def arm_vehicle(self):
        self.publish_vehicle_command(
            VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, 1.0
        )


def main(args=None):
    rclpy.init(args=args)
    node = OffboardControlNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
