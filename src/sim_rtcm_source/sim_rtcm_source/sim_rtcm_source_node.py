"""Sim ortaminda RTCM3 byte akisi yayinlayan ROS 2 node.

Synthetic veya replay modunda px4_bridge RTK girisini besler.
Yalnizca sim icin; sahada esp32_bridge kullanilir.
"""

import os

import rclpy
from rclpy.node import Node

from std_msgs.msg import UInt8MultiArray

from .rtcm_synth import (
    produce_synthetic_burst,
    replay_byte_akisi,
)


_DEFAULT_AGENT_ID = 1
_DEFAULT_MODE = 'synthetic'
_DEFAULT_PUBLISH_HZ = 1.0
_DEFAULT_REPLAY_FILE = ''
_QOS_DEPTH = 10


class SimRtcmSourceNode(Node):
    """Sentetik veya replay RTCM3 yayincisi."""

    def __init__(self) -> None:
        super().__init__('sim_rtcm_source')

        self.declare_parameter('agent_id', _DEFAULT_AGENT_ID)
        self.declare_parameter('mode', _DEFAULT_MODE)
        self.declare_parameter('publish_hz', _DEFAULT_PUBLISH_HZ)
        self.declare_parameter('replay_file', _DEFAULT_REPLAY_FILE)

        self._agent_id = int(
            self.get_parameter('agent_id').value
        )
        self._mode = str(self.get_parameter('mode').value)
        self._publish_hz = float(
            self.get_parameter('publish_hz').value
        )
        self._replay_file = str(
            self.get_parameter('replay_file').value
        )

        # Parametre dogrulama
        if self._agent_id <= 0:
            raise ValueError('agent_id pozitif olmali')
        if self._mode not in ('synthetic', 'replay'):
            raise ValueError(
                f"mode 'synthetic' veya 'replay' olmali "
                f'(verilen: {self._mode})'
            )
        if self._publish_hz <= 0:
            raise ValueError('publish_hz pozitif olmali')
        if self._mode == 'replay' and not self._replay_file:
            raise ValueError(
                "mode='replay' icin replay_file sart"
            )

        self._yayinlanan_cerceve = 0
        self._replay_baytlar = b''
        self._replay_pos = 0

        if self._mode == 'replay':
            if not os.path.isfile(self._replay_file):
                raise FileNotFoundError(
                    f'replay_file bulunamadi: '
                    f'{self._replay_file}'
                )
            self._replay_baytlar = replay_byte_akisi(
                self._replay_file
            )
            self.get_logger().info(
                f'replay: {len(self._replay_baytlar)}'
                ' byte yuklendi'
            )

        topic = f'/drone_{self._agent_id}/rtcm/in'
        self._pub = self.create_publisher(
            UInt8MultiArray, topic, _QOS_DEPTH
        )

        periyot = 1.0 / self._publish_hz
        self.create_timer(periyot, self._yayinla)

        self.get_logger().info(
            f'sim_rtcm_source basladi: '
            f'agent_id={self._agent_id} '
            f'mode={self._mode} hz={self._publish_hz}'
        )

    def _yayinla(self) -> None:
        """Mode'a gore cerceve yayinlar."""
        try:
            if self._mode == 'synthetic':
                self._yayinla_synthetic()
            else:
                self._yayinla_replay()
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(
                f'_yayinla hata: {type(e).__name__}: {e}'
            )

    def _yayinla_synthetic(self) -> None:
        """1005 + 1077 sentetik cercevelerini yayinlar."""
        for cerceve in produce_synthetic_burst():
            msg = UInt8MultiArray()
            msg.data = list(cerceve)
            self._pub.publish(msg)
            self._yayinlanan_cerceve += 1

    def _yayinla_replay(self) -> None:
        """Replay dosyasindan chunk byte yayinlar."""
        chunk_boy = max(
            1, len(self._replay_baytlar) // 10
        )
        if not self._replay_baytlar:
            return
        son = min(
            self._replay_pos + chunk_boy,
            len(self._replay_baytlar),
        )
        chunk = self._replay_baytlar[self._replay_pos:son]
        msg = UInt8MultiArray()
        msg.data = list(chunk)
        self._pub.publish(msg)
        self._yayinlanan_cerceve += 1
        self._replay_pos = son
        if self._replay_pos >= len(self._replay_baytlar):
            self._replay_pos = 0


def main(args=None):
    """Node giris noktasi."""
    rclpy.init(args=args)
    node = SimRtcmSourceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:  # noqa: BLE001
        node.get_logger().error(
            f'rclpy.spin hata: '
            f'{type(e).__name__}: {e}'
        )
    finally:
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception as e:  # noqa: BLE001
            print(
                f'sim_rtcm_source shutdown uyarisi: {e}'
            )


if __name__ == '__main__':
    main()
