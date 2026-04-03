#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from px4_msgs.msg import VehicleOdometry
import random
import time
from collections import deque
from functools import partial
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy


class ChaosNetwork(Node):
    def __init__(self):
        super().__init__("chaos_network")
        self.drones = [1, 2, 3, 4, 5]

        # Kaptanın İstediği Kaos Ayarları
        self.delay_sec = 0.200  # 200ms ping gecikmesi
        self.loss_rate = 0.10  # %10 paket kaybı

        self.pubs = {}
        self.msg_queues = {i: deque() for i in self.drones}

        self.get_logger().info(
            "🌪️ Kaos Ağı Başlatıldı: %10 Kayıp, 200ms Gecikme devrede!"
        )

        # Kaptanın İstediği QoS Profili: "Best Effort"
        best_effort_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        for i in self.drones:
            # 1. Dronlardan gelen kusursuz veriyi BEST EFFORT ile dinle
            self.create_subscription(
                VehicleOdometry,
                f"/px4_{i}/fmu/out/vehicle_odometry",
                partial(self.incoming_callback, drone_id=i),
                best_effort_qos,  # <-- HATA BURADAYDI, DÜZELTİLDİ
            )
            # 2. Geciktirilmiş veriyi BEST EFFORT ile yay
            self.pubs[i] = self.create_publisher(
                VehicleOdometry,
                f"/swarm/px4_{i}/delayed_odometry",
                best_effort_qos,  # <-- HATA BURADAYDI, DÜZELTİLDİ
            )

        # Kuyrukları saniyede 50 kere kontrol eden zamanlayıcı
        self.create_timer(0.02, self.process_queues)

    def incoming_callback(self, msg, drone_id):
        # GERÇEK KAOS: %40 ihtimalle veriyi yut! (Kötü bir Wi-Fi çekimi)
        if random.random() < 0.40:
            return

        # JITTER SİMÜLASYONU: 50ms ile 500ms arası rastgele dalgalı ping!
        dynamic_delay = random.uniform(0.05, 0.500)
        delivery_time = time.time() + dynamic_delay
        self.msg_queues[drone_id].append((delivery_time, msg))

    def process_queues(self):
        current_time = time.time()
        for i in self.drones:
            # Zamanı gelen (200ms beklemiş) paketleri kuyruktan çıkarıp yayına ver
            while self.msg_queues[i] and self.msg_queues[i][0][0] <= current_time:
                _, msg = self.msg_queues[i].popleft()
                self.pubs[i].publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = ChaosNetwork()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
