#!/usr/bin/env python3
# Copyright 2026 Yelpence
"""QR tablosunu ve QR gorev komutunu UCAKTA elle enjekte eder.

NIYE VAR: QR tablosunun mesh yolu baz ESP32 firmware'inde takili
(`TIP_QR_COORDS` beyaz listede yok, sessizce atiliyor). Kamerayla gercek QR
okumadan Gorev 1 zincirini — ozellikle roll/pitch manevrasini — ucurabilmek
icin QR'i uretecek bir yol lazim. Bu betik tam olarak esp32_bridge'in
mesh'ten alinca yapacagi seyi yapiyor, sadece kaynagi elle veriyoruz.

🔴 HER UCAKTA AYRI KOSAR. baslat.sh `ROS_LOCALHOST_ONLY=1` ile calisiyor;
laptoptan yayinlanan konu ucaga ULASMAZ. Uc ucakta da, YAKIN ZAMANLI
calistirilmali (sarmalayici: qr_enjekte_hepsi.sh).

🔴 QoS UYUSMAZLIGI SESSIZDIR (TUZAKLAR §2.1). Iki konu iki farkli profil
kullaniyor ve ikisi de mission_fsm_node.py'deki abonelikten birebir
kopyalandi:
    /swarm/public/mission/qr_coords     RELIABLE + TRANSIENT_LOCAL depth=1
    /swarm/public/perception/qr_data    BEST_EFFORT + VOLATILE   depth=5
qr_data'yi RELIABLE yayinlarsak abone HIC almaz — mesh kaynagi
(esp32_bridge _MESH_QOS) best-effort oldugu icin abonelik oyle yazilmis.

🔴 BEST_EFFORT DUSURULEBILIR. qr_data bir kez degil, --tekrar kez
yayinlanir (varsayilan 10, 5 Hz). Tablo latched oldugu icin bir kez yeter.

🔴 team_id TUTMAZSA GOREV SESSIZCE YOK SAYILIR (sartname: baska takimin
QR'i). Varsayilan 752825; --takim ile degistirilebilir.

🔴 qr_seq ARTMAK ZORUNDA. mission_fsm eski/sirasiz QR'i dusuruyor. Ayni
ucusta ikinci kez enjekte ederken --seq'i BUYUT (varsayilan: unix saniye).

Ornek — uc ucaga 10 derece roll manevrasi (QR 1, sonrasi eve donus):
    ros2 run ... yok; dogrudan:
    python3 /ws/qr_enjekte.py --qr 1 --sonraki 0 --roll 10 --bekle 4
Ornek — once konum tablosu (QR'a UCARAK gitmek icin):
    python3 /ws/qr_enjekte.py --tablo "1:38.690476,39.161019" --qr 1 \
        --sonraki 0 --roll 10
"""

import argparse
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_interfaces.msg import QRCoordinates, QRMissionData

# mission_fsm_node.py:49 ile BIREBIR — degistirme.
_LATCHED_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)
# mission_fsm_node.py:42 ile BIREBIR — RELIABLE yaparsan abone ALMAZ.
_BEST_EFFORT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


def _tablo_coz(metin):
    """'1:38.69,39.16;2:38.70,39.17' -> ([1,2], [38.69,38.70], [39.16,39.17])."""
    ids, lats, lons = [], [], []
    for parca in metin.split(';'):
        parca = parca.strip()
        if not parca:
            continue
        qr, konum = parca.split(':', 1)
        lat, lon = konum.split(',', 1)
        ids.append(int(qr))
        lats.append(float(lat))
        lons.append(float(lon))
    return ids, lats, lons


class QrEnjektor(Node):
    """Iki konuya yayin yapan tek kullanimlik dugum."""

    def __init__(self, a):
        """Yayincilari kurar ve argumanlari saklar."""
        super().__init__('qr_enjekte')
        self._a = a
        self._tablo_pub = self.create_publisher(
            QRCoordinates, '/swarm/public/mission/qr_coords', _LATCHED_QOS)
        self._qr_pub = self.create_publisher(
            QRMissionData, '/swarm/public/perception/qr_data',
            _BEST_EFFORT_QOS)

    def tablo_yayinla(self):
        """QR konum tablosunu bir kez yayinlar (latched — kalici)."""
        if not self._a.tablo:
            return 0
        ids, lats, lons = _tablo_coz(self._a.tablo)
        m = QRCoordinates()
        m.stamp = self.get_clock().now().to_msg()
        m.qr_ids = ids
        m.lat_deg = lats
        m.lon_deg = lons
        self._tablo_pub.publish(m)
        return len(ids)

    def qr_kur(self):
        """CLI argumanlarindan QRMissionData kurar."""
        a = self._a
        m = QRMissionData()
        m.stamp = self.get_clock().now().to_msg()
        m.detector_agent_id = int(a.tespit_eden)
        m.qr_id = int(a.qr)
        m.qr_seq = int(a.seq if a.seq is not None else int(time.time()))
        m.team_id = a.takim
        # Algi zincirini taklit ediyoruz: gercek okumada bu ucu de true olur.
        m.detected = True
        m.decoded = True
        m.valid = True
        m.confidence = 1.0
        m.raw_text = a.ham or f'ELLE-ENJEKTE qr={a.qr}'
        # Bolum bayraklari — abone bunlari "dogruluk kaynagi" sayiyor,
        # command_type geriye uyumluluk icin duruyor.
        m.maneuver_active = bool(a.roll or a.pitch or a.yaw)
        m.formation_active = a.formasyon is not None
        m.altitude_active = a.irtifa is not None
        m.pitch_deg = float(a.pitch)
        m.roll_deg = float(a.roll)
        m.yaw_deg = float(a.yaw)
        if a.formasyon is not None:
            m.formation_type = int(a.formasyon)
            m.spacing_m = float(a.aralik)
            m.command_type = QRMissionData.COMMAND_SET_FORMATION
        if a.irtifa is not None:
            m.altitude_agl_m = float(a.irtifa)
        m.wait_s = float(a.bekle)
        m.next_qr = int(a.sonraki)
        return m

    def qr_yayinla(self, m):
        """BEST_EFFORT oldugu icin tekrarli yayinlar."""
        for _ in range(int(self._a.tekrar)):
            m.stamp = self.get_clock().now().to_msg()
            self._qr_pub.publish(m)
            time.sleep(1.0 / max(1.0, float(self._a.hz)))


def main():
    """Argumanlari okur, iki konuya yayin yapar, cikar."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--qr', type=int, required=True, help='QR numarasi')
    p.add_argument('--sonraki', type=int, default=0,
                   help='next_qr; 0 = son nokta, sonrasinda eve donus')
    p.add_argument('--roll', type=float, default=0.0, help='roll derece')
    p.add_argument('--pitch', type=float, default=0.0, help='pitch derece')
    p.add_argument('--yaw', type=float, default=0.0, help='yaw derece')
    p.add_argument('--formasyon', type=int, default=None,
                   help='1=okbasi 2=V 3=cizgi (verilmezse formasyon degismez)')
    p.add_argument('--aralik', type=float, default=7.0, help='formasyon araligi m')
    p.add_argument('--irtifa', type=float, default=None, help='hedef irtifa m')
    p.add_argument('--bekle', type=float, default=0.0, help='QR uzerinde bekleme sn')
    p.add_argument('--tablo', default='',
                   help='"1:lat,lon;2:lat,lon" — QR konum tablosu')
    p.add_argument('--takim', default='752825', help='team_id')
    p.add_argument('--ham', default='',
                   help='raw_text; bos birakilirsa ELLE-ENJEKTE etiketi')
    p.add_argument('--tespit-eden', type=int, default=3,
                   help='detector_agent_id (kamera ylp02=3 uzerinde)')
    p.add_argument('--seq', type=int, default=None,
                   help='qr_seq; ARTMALI (varsayilan unix saniye)')
    p.add_argument('--tekrar', type=int, default=10, help='qr_data tekrar sayisi')
    p.add_argument('--hz', type=float, default=5.0, help='tekrar hizi')
    a = p.parse_args()

    rclpy.init()
    d = QrEnjektor(a)
    # Aboneler baglansin; TRANSIENT_LOCAL gec baglanani da yakalar ama
    # BEST_EFFORT yakalamaz — o yuzden once kisa bir es.
    time.sleep(1.0)
    n = d.tablo_yayinla()
    if n:
        print(f'QR konum tablosu yayinlandi: {n} nokta (latched)')
    m = d.qr_kur()
    print(f'QR gorev verisi: qr_id={m.qr_id} seq={m.qr_seq} '
          f'next={m.next_qr} manevra={m.maneuver_active} '
          f'(roll={m.roll_deg} pitch={m.pitch_deg} yaw={m.yaw_deg}) '
          f'formasyon={m.formation_active} irtifa={m.altitude_active}')
    d.qr_yayinla(m)
    print(f'{a.tekrar} kez yayinlandi ({a.hz} Hz) — bitti')
    d.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
