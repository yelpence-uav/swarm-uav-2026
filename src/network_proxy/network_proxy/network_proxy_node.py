#!/usr/bin/env python3
"""
Sürü İHA ESP-NOW Mesh Ağı Simülatörü (ROS 2 Proxy Node)
İç (Internal) topic'lerden gelen verileri alır, fiziksel engellerden
ve mesafe kısıtlamalarından geçirerek Dış (Public) topic'lere aktarır.
"""

import sys
import rclpy
from rclpy.node import Node
from threading import Timer

# Fiziksel Radyo Modelimiz
from network_proxy.rf_model import ESPNowRFModel

# Swarm Interfaces (Örnek olarak AgentStatus üzerinden kurgulanmıştır)
from swarm_interfaces.msg import AgentStatus


class NetworkProxyNode(Node):
    def __init__(self):
        super().__init__("network_proxy_node")

        # 1. RF Modelini Başlat
        self.rf_model = ESPNowRFModel()

        # 2. Ajanların (İHA'lar ve YKİ) güncel 3D konumlarını tutacağımız sözlük
        # YKİ'yi sabit (0,0,0) olarak başlatıyoruz.
        self.positions = {"gcs": (0.0, 0.0, 0.0)}

        # Sistemdeki ajan listesi (5 İHA)
        self.agent_ids = ["agent_1", "agent_2", "agent_3", "agent_4", "agent_5"]

        # 3. Publisher ve Subscriber'ları Dinamik Oluştur
        self.internal_subs = {}
        self.public_pubs = {}

        for agent in self.agent_ids:
            # İHA'ların KÖPRÜYE gönderdiği GİZLİ (Internal) topic'leri dinle
            internal_topic = f"/swarm/internal/{agent}/status"
            self.internal_subs[agent] = self.create_subscription(
                AgentStatus,
                internal_topic,
                lambda msg, a=agent: self.internal_status_callback(msg, a),
                10,
            )

            # KÖPRÜNÜN diğer İHA'lara ileteceği GENEL (Public) topic'leri oluştur
            public_topic = f"/swarm/public/{agent}/status"
            self.public_pubs[agent] = self.create_publisher(
                AgentStatus, public_topic, 10
            )

            # Başlangıç konumlarını sıfırla
            self.positions[agent] = (0.0, 0.0, 0.0)

        self.get_logger().info("Network Proxy Node (ESP-NOW Simulator) Başlatıldı.")
        self.get_logger().info(
            "Yönlendirme aktif: /swarm/internal/... -> /swarm/public/..."
        )

    def internal_status_callback(self, msg: AgentStatus, sender_id: str):
        """
        Bir İHA'dan (Gönderici) mesaj geldiğinde tetiklenir.
        """
        # 1. Göndericinin Konumunu Güncelle (Odometri veya Status içinden)
        # Not: Arayüzünüzdeki gerçek konumu çektiğiniz yeri buraya uyarlamalısınız.
        self.positions[sender_id] = (msg.position.x, msg.position.y, msg.position.z)

        # 2. ESP-NOW 250 Byte Limiti Kontrolü
        # Python objesinin yaklaşık boyutunu ölçer. ROS2 serileştirme boyutu biraz farklı olabilir
        # ama optimizasyon testleri için harika bir yaklaşımdır.
        msg_size = sys.getsizeof(str(msg))
        if msg_size > 250:
            self.get_logger().warn(
                f"PAKET REDDEDİLDİ! {sender_id} mesajı 250 byte sınırını aştı! (Boyut: {msg_size} bytes)"
            )
            return  # Mesajı iptal et (Drop)

        # 3. Mesajı Sistemdeki Diğer Alıcılara (İHA'lar ve YKİ) Yönlendir
        sender_pos = self.positions[sender_id]

        # Örnek: YKİ'ye (GCS) ulaşıp ulaşmadığını test edelim
        gcs_dist = self.rf_model.calculate_distance(sender_pos, self.positions["gcs"])
        if gcs_dist > 110.0:
            # Şartname kuralı: 110 metreyi geçerse GCS ile bağlantı kopar (Failsafe tetiklenmeli)
            self.get_logger().warn(
                f"BAĞLANTI KOPTU: {sender_id} GCS'ten çok uzak ({gcs_dist:.1f}m)"
            )

        # Diğer İHA'lara iletim
        for receiver_id in self.agent_ids:
            if receiver_id == sender_id:
                continue  # Kendine gönderme

            receiver_pos = self.positions[receiver_id]
            distance = self.rf_model.calculate_distance(sender_pos, receiver_pos)

            # Zar At (Paket düşecek mi?)
            if self.rf_model.should_drop_packet(distance):
                # Paket fiziksel engele veya mesafeye takıldı (Sessizce sil)
                # İsterseniz debug için log basabilirsiniz: self.get_logger().debug(...)
                continue

            # Paket geçmeyi başardı! ESP-NOW Gecikmesini (Jitter) hesapla
            latency = self.rf_model.get_jitter()

            # Gecikmeyi uygulayıp paketi asıl hedefe (Public) yayınla
            # Threading Timer kullanımı, ROS 2 spin döngüsünü bloklamadan (dondurmadan) gecikme sağlar.
            Timer(latency, self.publish_to_public, args=[sender_id, msg]).start()

    def publish_to_public(self, sender_id: str, msg: AgentStatus):
        """Asenkron gecikme süresi dolduğunda paketi ağa bırakır."""
        self.public_pubs[sender_id].publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = NetworkProxyNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
