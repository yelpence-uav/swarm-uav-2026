#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from px4_msgs.msg import DistanceSensor
import math

class LidarRelay(Node):
    def __init__(self, drone_count):
        super().__init__('lidar_relay_node')
        self.drone_count = drone_count
        self.subs = []
        self.pubs = []
        
        for i in range(self.drone_count):
            drone_id = i + 1
            # Subscriber for Gazebo LaserScan
            topic_in = f'/drone_{drone_id}/lidar/scan'
            # Publisher for PX4 DistanceSensor
            topic_out = f'/drone_{drone_id}/fmu/in/distance_sensor'
            
            sub = self.create_subscription(
                LaserScan,
                topic_in,
                lambda msg, d_id=drone_id: self.lidar_callback(msg, d_id),
                10
            )
            pub = self.create_publisher(
                DistanceSensor,
                topic_out,
                10
            )
            self.subs.append(sub)
            self.pubs.append(pub)

    def lidar_callback(self, msg, drone_id):
        if not msg.ranges:
            return
            
        # Get the first valid distance (assuming single-point lidar)
        dist = 0.0
        for r in msg.ranges:
            if not math.isinf(r) and not math.isnan(r) and r > 0.01:
                dist = float(r)
                break
        
        if dist == 0.0:
            return # No valid reading

        # Create DistanceSensor message
        ds_msg = DistanceSensor()
        ds_msg.timestamp = int(self.get_clock().now().nanoseconds / 1000) # Microseconds
        ds_msg.device_id = drone_id + 1
        ds_msg.min_distance = msg.range_min
        ds_msg.max_distance = msg.range_max
        ds_msg.current_distance = dist
        ds_msg.type = 0 # MAV_DISTANCE_SENSOR_LASER
        ds_msg.orientation = 25 # ROTATION_DOWNWARD_FACING
        ds_msg.variance = 0.0
        ds_msg.signal_quality = 100
        
        self.pubs[drone_id - 1].publish(ds_msg)

def main(args=None):
    import sys
    drone_count = 1
    if len(sys.argv) > 1:
        try:
            drone_count = int(sys.argv[1])
        except ValueError:
            pass

    rclpy.init(args=args)
    node = LidarRelay(drone_count)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
