"""rtk_bridge_node.py — RTCM düzeltme verisini PX4'e enjekte eden köprü.

GİRİŞ:
    /drone_{agent_id}/rtcm/in (std_msgs/UInt8MultiArray)
    - LOKAL topic — network_proxy'den geçmez (drone içi yol).
    - Sim'de: sim_rtcm_source bu topic'i besler.
    - Sahada: esp32_bridge bu topic'e basar (Büşra firmware
      koordinasyonu Issue açılacak).

ÇIKIŞ:
    /drone_{agent_id}/fmu/in/gps_inject_data (px4_msgs/GpsInjectData)
    - PX4 uXRCE-DDS'in dinlediği topic. dds_topics.yaml yamasız
      iletilmez (Faz 2.5'te hazırlanan yama firmware/build sahibi
      tarafından uygulanacak).
    - command_sender deseni: düz depth=10 QoS (varsayılan RELIABLE).

İŞLEYİŞ:
    1. UInt8MultiArray ile gelen RTCM bayt akışı tampona eklenir.
    2. rtcm_packing.iter_rtcm_messages tam mesajları ayıklar, yarım
       kuyruğu callback'ler arası saklar.
    3. Her tam mesaj rtcm_packing.fragment_for_inject ile 300 byte
       parçalara bölünür; fragmented bayrağı flags LSB'sine yazılır.
    4. Her parça GpsInjectData mesajına sarılıp PX4'e yayınlanır.
       Rate-limit YOK: RTCM epoch bundle'ları (1005+1077 vb.) bir bütün
       gönderilir; PX4 ORB kuyruğu (QUEUE_LENGTH=8) burst'ü kaldırır.
    5. 1 Hz tanı log'u: alınan mesaj / yayınlanan fragment sayacı.

device_id ATAMASI:
    PX4 gps.cpp:574 self-injection korunmasından geçmek için ground
    enjekterleri device_id=0 kullanır (mavlink_receiver.cpp:2565
    referansı). Gerçek GPS sensörlerinin device_id'si bus/devtype/
    address bitfield'i ile non-zero üretilir — biz 0 ile çarpışmayız.
"""

import rclpy
from rclpy.node import Node

from px4_msgs.msg import GpsInjectData
from std_msgs.msg import UInt8MultiArray

from .rtcm_packing import fragment_for_inject, iter_rtcm_messages


# Sabitler
_DEFAULT_AGENT_ID = 1
_DEFAULT_MAX_PAYLOAD = 300       # GpsInjectData.data sabit boyut
_DEFAULT_GPS_DEVICE_ID = 0       # ground injector standardı
_GPS_INJECT_QOS_DEPTH = 10       # command_sender deseni
_DIAG_PERIOD_S = 1.0
_GPS_INJECT_DATA_SIZE = 300      # px4_msgs/GpsInjectData.data uzunluğu


class RtkBridgeNode(Node):
    """RTCM3 düzeltme baytlarını PX4 GpsInjectData fragmanlarına çevirir."""

    def __init__(self) -> None:
        super().__init__('rtk_bridge')

        # ----- Parametreler -----
        self.declare_parameter('agent_id', _DEFAULT_AGENT_ID)
        self.declare_parameter('sitl_mode', True)
        self.declare_parameter('max_payload', _DEFAULT_MAX_PAYLOAD)
        self.declare_parameter('gps_device_id', _DEFAULT_GPS_DEVICE_ID)

        self._agent_id = int(self.get_parameter('agent_id').value)
        self._sitl_mode = bool(self.get_parameter('sitl_mode').value)
        self._max_payload = int(
            self.get_parameter('max_payload').value
        )
        self._gps_device_id = int(
            self.get_parameter('gps_device_id').value
        )

        # Parametre doğrulama
        if not 1 <= self._max_payload <= _GPS_INJECT_DATA_SIZE:
            raise ValueError(
                'max_payload 1-300 arasında olmalı '
                f'(verilen: {self._max_payload})'
            )
        if self._agent_id <= 0:
            raise ValueError('agent_id pozitif olmalı')

        # ----- Durum -----
        # iter_rtcm_messages yarım kuyruğu
        self._tampon: bytes = b''
        # Tanı sayaçları
        self._alinan_msg = 0
        self._yayinlanan_frag = 0
        self._cb_hata = 0

        # ----- Topic'ler -----
        ns = f'/drone_{self._agent_id}'
        self._rtcm_sub = self.create_subscription(
            UInt8MultiArray,
            f'{ns}/rtcm/in',
            self._on_rtcm,
            10,
        )
        self._gps_inject_pub = self.create_publisher(
            GpsInjectData,
            f'{ns}/fmu/in/gps_inject_data',
            _GPS_INJECT_QOS_DEPTH,
        )

        # ----- Tanı timer'ı (1 Hz) -----
        self.create_timer(_DIAG_PERIOD_S, self._tani_yayinla)

        self.get_logger().info(
            f'rtk_bridge başlatıldı: agent_id={self._agent_id} '
            f'sitl={self._sitl_mode} '
            f'max_payload={self._max_payload} '
            f'device_id={self._gps_device_id}'
        )

    # ---------- Callback'ler ----------
    def _on_rtcm(self, msg: UInt8MultiArray) -> None:
        """RTCM bayt akışı callback'i (try'lı, exception node'u çökertmez)."""
        try:
            self._on_rtcm_inner(msg)
        except Exception as e:  # noqa: BLE001
            self._cb_hata += 1
            self.get_logger().error(
                f'_on_rtcm hata: {type(e).__name__}: {e}'
            )

    def _on_rtcm_inner(self, msg: UInt8MultiArray) -> None:
        """RTCM byte akışını işleyip tam mesajları fragmenter'a yollar.

        Kaynak sustuğunda hiçbir şey yayınlamaz (sessiz bekleme).
        Yarım kuyruk callback'ler arası korunur.

        NOT: RTCM düşük hızlı bir akıştır (tipik 1 Hz) ve her epoch'ta
        BIRDEN FAZLA mesaj (ör. 1005 + 1077) bundle olarak gelir. Eski
        sürümde her mesaj arası `max_rate_hz` ile rate-limit yapılıyordu;
        bu epoch içindeki ikinci mesajı (genelde 1077 GPS gözlemi)
        sessizce düşürüyordu. PX4 ORB kuyruğu (QUEUE_LENGTH=8) bu burst'ü
        zaten kaldırır, ek rate-limit'e GEREK YOK ve ZARARLI.
        """
        if not msg.data:
            return
        akis = self._tampon + bytes(msg.data)
        mesajlar, self._tampon = iter_rtcm_messages(akis)
        if not mesajlar:
            return  # yarım kuyruk biriktiriyoruz, bekle
        for rtcm_msg in mesajlar:
            self._alinan_msg += 1
            self._yayinla_fragmenler(rtcm_msg)

    def _yayinla_fragmenler(self, rtcm_msg: bytes) -> None:
        """RTCM mesajını fragmenter'a verip her parçayı yayınlar.

        Args:
            rtcm_msg (bytes): Tam RTCM3 çerçevesi (preamble..CRC).
        """
        parcalar = fragment_for_inject(
            rtcm_msg, max_payload=self._max_payload
        )
        ts_us = self.get_clock().now().nanoseconds // 1000
        for chunk, fragmented in parcalar:
            inject = GpsInjectData()
            inject.timestamp = ts_us
            inject.device_id = self._gps_device_id
            inject.len = len(chunk)
            inject.flags = 1 if fragmented else 0
            # data alanı uint8[300] sabit; chunk'u 0 ile padle
            dolgu = _GPS_INJECT_DATA_SIZE - len(chunk)
            inject.data = list(chunk) + [0] * dolgu
            self._gps_inject_pub.publish(inject)
            self._yayinlanan_frag += 1

    def _tani_yayinla(self) -> None:
        """1 Hz tanı log'u; node sağlığını dışarıya bildirir."""
        try:
            self.get_logger().info(
                f'tani: msg={self._alinan_msg} '
                f'frag={self._yayinlanan_frag} '
                f'tampon={len(self._tampon)}B '
                f'cb_hata={self._cb_hata}'
            )
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(f'tani log hata: {e}')


def main(args=None):
    """Düğüm giriş noktası."""
    rclpy.init(args=args)
    node = RtkBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:  # noqa: BLE001
        node.get_logger().error(
            f'rclpy.spin hata: {type(e).__name__}: {e}'
        )
    finally:
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception as e:  # noqa: BLE001
            # Sinyal işleyici zaten shutdown yapmış olabilir
            # (SIGTERM/timeout). Hatayı yutmak yerine debug log'a yaz.
            print(f'rtk_bridge shutdown uyarisi: {e}')


if __name__ == '__main__':
    main()
