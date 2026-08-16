#!/usr/bin/env python3
"""Yerel internal -> public koprusu.

NE ISE YARAR
------------
Sozlesme (INTERFACE_CONTRACT.md) soyle: suru dugumleri kendi ciktilarini
`/swarm/internal/...` konularina yazar, BASKALARININ ciktilarini
`/swarm/public/...` konularindan okur. Ikisini birlestiren bir kopru olmali.

Simulasyonda bu kopru `network_proxy` idi ve IKI isi birden yapiyordu:
  1. YEREL DONGU  : ayni ucagin internal ciktisini kendi public'ine tasi
  2. AJANLAR ARASI: bir ucagin ciktisini digerlerinin public'ine tasi

Sahada `esp32_bridge` yalnizca 2'yi yapiyor (mesh uzerinden). 1 HIC
YAPILMIYORDU. Sonucu: bir ucak KENDI suru dugumlerinin ciktisini goremiyordu.

15 Agustos'ta olculen somut ornekler:
  * consensus `/swarm/internal/election/result`'a yaziyor, swarm_fsm
    `/swarm/public/election/result`'i dinliyor -> ayni ucakta swarm_fsm
    kendi consensus'unun secimini HIC gormuyordu.
  * swarm_origin_publisher `/swarm/internal/origin`'a yaziyor, agent_fsm
    `/swarm/public/origin`'i dinliyor -> preflight origin_synced'i hic
    goremiyor, IDLE -> ARMING olmuyordu. (Gecici olarak baslat.sh'te remap
    ile cozulmustu; bu dugum gelince o remap KALDIRILABILIR.)
  * swarm_fsm `/swarm/internal/state`'e yaziyor, mission1 ve mode_manager
    `/swarm/public/state`'i dinliyor -> suru durumu kimseye ulasmiyordu.

NEDEN AYRI DUGUM
----------------
esp32_bridge zaten en buyuk ve en kritik dugum; mesh tasimasi ile yerel
dongu farkli sorumluluklar. Ayri dugum tek basina test edilebiliyor ve
`SURU_DUGUMLERI`'nden acilip kapatilabiliyor. Gecikme maliyeti onemsiz:
tasinan konularin hepsi dusuk hizli (durum ~5 Hz, secim/olay seyrek);
50 Hz setpoint yolu buradan GECMIYOR.

⚠️ `drone{N}/status` BILEREK TASINMIYOR
--------------------------------------
Ucagin kendi durumu kendi `/swarm/public/droneN/status` konusuna dusseydi,
komsu tuketicileri (basit_kacinma, collision_avoidance) onu KOMSU sanip
ucagin KENDINDEN kacmasina calisirdi. Kodun mevcut gelenegi de bu:
consensus kendi kaydini ayrica `/swarm/internal/drone{ben}/status`'tan
okuyor. O geleneği bozmuyoruz.

DONGU YOK
---------
Kopru TEK YONLU: yalniz internal okur, yalniz public yazar. Public'i hic
dinlemedigi icin kendi basina dongu kuramaz. Dugum tarafinda da dogrulandi
(15 Agustos): `public/X` dinleyip `internal/X`'e yayinlayan bir islem yok;
tek yakin durum swarm_fsm._on_election'in olay yayinlamasi, o da FARKLI bir
konuya yaziyor ve olay isleyicileri yeni olay uretmiyor -> zincir sonlaniyor.

Kullanim:
    ros2 run swarm_control ic_dis_kopru
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from std_msgs.msg import UInt8

from swarm_interfaces.msg import (
    ElectionResult,
    FormationCommand,
    LeaderHeartbeat,
    MissionTarget,
    QRCoordinates,
    QRMissionData,
    SwarmControlCommand,
    SwarmOrigin,
    SwarmState,
    SystemEvent,
)

# Iki dayaniklilik sinifi yetiyor. Ikisi de RELIABLE:
#   * Butun internal yayincilar RELIABLE (15 Agustos'ta tarandi), yani
#     RELIABLE abone olmak eslesiyor.
#   * RELIABLE yayinlamak hem RELIABLE hem BEST_EFFORT abonelerle uyumlu.
#     Tersi degil — BEST_EFFORT yayinci + RELIABLE abone ESLESMEZ ve konu
#     sessizce bos kalir. Bugun bu tuzaga uc kez dusuldu, o yuzden koprude
#     en genis uyumlu tarafi seciyoruz.
_VOLATILE = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)
# TRANSIENT_LOCAL: gec acilan dugum son degeri de alsin. origin ve secim
# sonucu icin sart — ikisi de "bir kez yayinlanir, sonra herkes bilmeli".
_TRANSIENT = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

# (mesaj tipi, konu soneki, qos)
# Kaynak: network_proxy'nin tablosu (sim ikizi) + 15 Agustos taramasi.
# drone{N}/status BILEREK YOK — yukaridaki uyariya bak.
KOPRU_TABLOSU = (
    (SystemEvent,         'events/system',        _VOLATILE),
    (ElectionResult,      'election/result',      _TRANSIENT),
    (LeaderHeartbeat,     'leader/heartbeat',     _VOLATILE),
    (FormationCommand,    'formation/target',     _VOLATILE),
    (SwarmOrigin,         'origin',               _TRANSIENT),
    (SwarmState,          'state',                _VOLATILE),
    (UInt8,               'mission/state',        _VOLATILE),
    (UInt8,               'mission/qr_step',      _VOLATILE),
    (MissionTarget,       'mission/next_target',  _VOLATILE),
    (QRCoordinates,       'mission/qr_coords',    _TRANSIENT),
    (QRMissionData,       'perception/qr_data',   _VOLATILE),
    (SwarmControlCommand, 'control/command',      _VOLATILE),
)


class IcDisKopru(Node):
    """internal -> public yerel dongusu."""

    def __init__(self):
        super().__init__('ic_dis_kopru')

        self.declare_parameter('ozet_saniye', 30.0)
        ozet_s = float(self.get_parameter('ozet_saniye').value)

        self._sayac: dict[str, int] = {}
        self._pub: dict[str, object] = {}

        for tip, sonek, qos in KOPRU_TABLOSU:
            ic = f'/swarm/internal/{sonek}'
            dis = f'/swarm/public/{sonek}'
            self._sayac[sonek] = 0
            self._pub[sonek] = self.create_publisher(tip, dis, qos)
            self.create_subscription(
                tip, ic, self._aktarici(sonek), qos
            )

        if ozet_s > 0.0:
            self.create_timer(ozet_s, self._ozet)

        self.get_logger().info(
            f'IcDisKopru basladi: {len(KOPRU_TABLOSU)} konu '
            f'internal -> public (drone*/status BILEREK haric)'
        )

    def _aktarici(self, sonek: str):
        """Konuya ozel geri cagirma uretir."""
        def _cb(msg):
            self._sayac[sonek] += 1
            self._pub[sonek].publish(msg)
        return _cb

    def _ozet(self) -> None:
        """Hangi konudan kac mesaj gecti — sessiz kalmasin diye."""
        gecen = {k: v for k, v in self._sayac.items() if v > 0}
        if not gecen:
            self.get_logger().info(
                'kopru: hicbir konudan mesaj gecmedi '
                '(suru dugumleri kapali olabilir)',
                throttle_duration_sec=120.0,
            )
            return
        ozet = ' '.join(f'{k}={v}' for k, v in sorted(gecen.items()))
        self.get_logger().info(f'kopru gecen: {ozet}')


def main(args=None):
    rclpy.init(args=args)
    dugum = IcDisKopru()
    try:
        rclpy.spin(dugum)
    except KeyboardInterrupt:
        pass
    finally:
        dugum.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
