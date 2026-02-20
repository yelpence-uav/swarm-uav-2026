#!/usr/bin/env python3
import rclpy
from rclpy.node import Node


class GCSNode(Node):

    def __init__(self):
        super().__init__('gcs_node')
        self.get_logger().info(
            'Yelpence Yer Kontrol Istasyonu (GCS) Dugumu baslatildi. Komutlar bekleniyor...'
        )

        # Joystick/RC kumanda verilerini okuyacak, kullanici arayuzu (GUI) ile
        # haberlesecek ve suruye 'yelpence_msgs' uzerinden Formasyon/Hareket
        # komutlarini iletecek yapi buraya kurulacak.


def main(args=None):
    rclpy.init(args=args)
    node = GCSNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print('\nDugum kullanici tarafindan durduruldu.')
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
