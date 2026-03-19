#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from px4_msgs.msg import VehicleOdometry, VehicleLocalPosition
import random
import time
from collections import deque
from functools import partial
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

class ChaosNetwork(Node):
    def __init__(self, drone_count=5):
        super().__init__('chaos_network')
        self.drone_count = drone_count
        self.drones = list(range(1, self.drone_count + 1))
        
        # Kaptanın İstediği Kaos Ayarları
        self.delay_sec = 0.200 # 200ms ping gecikmesi
        self.loss_rate = 0.10  # %10 paket kaybı

        self.pubs = {}
        # Her drone için ayrı kuyruklar
        self.msg_queues = {i: deque() for i in self.drones}

        self.get_logger().info(f"🌪️ Kaos Ağı Başlatıldı: {self.drone_count} İHA için %10 Kayıp, 200ms Gecikme devrede!")

        best_effort_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        for i in self.drones:
            # 1. Odometry (Konum/Hız)
            self.create_subscription(
                VehicleOdometry,
                f'/drone_{i}/fmu/out/vehicle_odometry',
                partial(self.incoming_callback, drone_id=i, topic_key='odom'),
                best_effort_qos
            )
            # 2. Local Position (İrtifa/EKF2)
            self.create_subscription(
                VehicleLocalPosition,
                f'/drone_{i}/fmu/out/vehicle_local_position',
                partial(self.incoming_callback, drone_id=i, topic_key='local_pos'),
                best_effort_qos
            )

            self.pubs[i] = {
                'odom': self.create_publisher(VehicleOdometry, f'/swarm/drone_{i}/delayed_odometry', best_effort_qos),
                'local_pos': self.create_publisher(VehicleLocalPosition, f'/swarm/drone_{i}/delayed_local_position', best_effort_qos)
            }

        # Kuyrukları saniyede 50 kere kontrol eden zamanlayıcı
        self.create_timer(0.02, self.process_queues)

    def incoming_callback(self, msg, drone_id, topic_key):
        # GERÇEK KAOS: %10 ihtimalle veriyi yut! (Kötü bir Wi-Fi çekimi)
        if random.random() < self.loss_rate:
            return

        # JITTER SİMÜLASYONU: 50ms ile 500ms arası rastgele dalgalı ping!
        dynamic_delay = random.uniform(0.05, 0.400)
        delivery_time = time.time() + dynamic_delay
        self.msg_queues[drone_id].append((delivery_time, msg, topic_key))

        
    def process_queues(self):
        current_time = time.time()
        for i in self.drones:
            # Zamanı gelen paketleri kuyruktan çıkarıp yayına ver
            while self.msg_queues[i] and self.msg_queues[i][0][0] <= current_time:
                _, msg, topic_key = self.msg_queues[i].popleft()
                self.pubs[i][topic_key].publish(msg)

def main(args=None):
    import sys
    drone_count = 5
    if len(sys.argv) > 1:
        try:
            drone_count = int(sys.argv[1])
        except ValueError:
            pass
            
    rclpy.init(args=args)
    node = ChaosNetwork(drone_count)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
