"""sim_rtcm_source_node.py — Yalniz-sim RTCM3 byte akisi yayincisi.

Sim ortaminda px4_bridge'in RTK girisini (/drone_{id}/rtcm/in) besler.
Iki mode destekler:

  mode='synthetic' (default):
    rtcm_synth.produce_synthetic_burst() ile 1005 + 1077 sentetik
    cerceveleri publish_hz periyodunda yayinlanir. Faz 1 referans 1005
    vektoru kullanilabilir; receiver-anlamli olmayan minimal cerceveler.

  mode='replay':
    sample_data/ altindaki bir .rtcm dosyasini dongude oynatir
    (replay_file parametresi). Dosya 1 kere okunup byte byte yayilir.

YAYIN TOPIC:
    /drone_{agent_id}/rtcm/in  (std_msgs/UInt8MultiArray,
        RELIABLE depth=10, command_sender deseni)
    - LOKAL topic — network_proxy'den gecmez.
    - px4_bridge (RTK) bu topic'i dinler.

YALNIZCA-SIM:
    Bu paket gercek donanim launch'una EKLENMEZ. Sahada esp32_bridge
    rtcm/in topic'ini besler (Busra firmware koordinasyonu sonrasi).
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
    """Sim RTCM3 byte akisi yayincisi (synthetic veya replay)."""

    def __init__(self) -> None:
        super().__init__('sim_rtcm_source')

        # ----- Parametreler -----
        self.declare_parameter('agent_id', _DEFAULT_AGENT_ID)
        self.declare_parameter('mode', _DEFAULT_MODE)
        self.declare_parameter('publish_hz', _DEFAULT_PUBLISH_HZ)
        self.declare_parameter('replay_file', _DEFAULT_REPLAY_FILE)

        self._agent_id = int(self.get_parameter('agent_id').value)
        self._mode = str(self.get_parameter('mode').value)
        self._publish_hz = float(
            self.get_parameter('publish_hz').value
        )
        self._replay_file = str(
            self.get_parameter('replay_file').value
        )

        # ----- Parametre dogrulama -----
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
                "mode='replay' icin replay_file parametresi sart"
            )

        # ----- Durum -----
        self._yayinlanan_cerceve = 0  # tanı sayaci
        self._replay_baytlar = b''
        self._replay_pos = 0

        # ----- Replay verisini yukle -----
        if self._mode == 'replay':
            if not os.path.isfile(self._replay_file):
                raise FileNotFoundError(
                    f'replay_file bulunamadi: {self._replay_file}'
                )
            self._replay_baytlar = replay_byte_akisi(self._replay_file)
            self.get_logger().info(
                f'replay: {len(self._replay_baytlar)} byte yuklendi'
            )

        # ----- Publisher -----
        topic = f'/drone_{self._agent_id}/rtcm/in'
        self._pub = self.create_publisher(
            UInt8MultiArray, topic, _QOS_DEPTH
        )

        # ----- Timer -----
        periyot = 1.0 / self._publish_hz
        self.create_timer(periyot, self._yayinla)

        self.get_logger().info(
            f'sim_rtcm_source basladi: agent_id={self._agent_id} '
            f'mode={self._mode} hz={self._publish_hz}'
        )

    def _yayinla(self) -> None:
        """Timer callback'i: mode'a gore cerceve yayinlar."""
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
        """Synthetic mode: 1005 + 1077 cerceveleri tek timer'da yayinla."""
        for cerceve in produce_synthetic_burst():
            msg = UInt8MultiArray()
            msg.data = list(cerceve)
            self._pub.publish(msg)
            self._yayinlanan_cerceve += 1

    def _yayinla_replay(self) -> None:
        """Replay mode: dosyadan chunk byte yayinla (dongusel)."""
        chunk_boy = max(1, len(self._replay_baytlar) // 10)
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
        # Dongu basa sar
        if self._replay_pos >= len(self._replay_baytlar):
            self._replay_pos = 0


def main(args=None):
    """Dugum giris noktasi."""
    rclpy.init(args=args)
    node = SimRtcmSourceNode()
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
            print(f'sim_rtcm_source shutdown uyarisi: {e}')


if __name__ == '__main__':
    main()
