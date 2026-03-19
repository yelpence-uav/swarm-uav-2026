#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

class CameraRelay(Node):
    def __init__(self, drone_count):
        super().__init__('camera_relay_node')
        self.drone_count = drone_count
        self.subs = []
        
        for i in range(self.drone_count):
            drone_id = i + 1
            # Subscriber for Gazebo Camera Image
            # This node can be used for future image processing (OpenCV, AI, etc.)
            topic_in = f'/drone_{drone_id}/camera/image_raw'
            
            sub = self.create_subscription(
                Image,
                topic_in,
                lambda msg, d_id=drone_id: self.camera_callback(msg, d_id),
                10
            )
            self.subs.append(sub)
            
        self.get_logger().info(f"Camera Relay Başlatıldı: {drone_count} İHA takip ediliyor.")

    def camera_callback(self, msg, drone_id):
        # Şimdilik sadece veri geldiğini doğrulamak için (İleride işlenebilir)
        # Çok sık log basmamak için sessiz kalıyoruz
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
    node = CameraRelay(drone_count)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
