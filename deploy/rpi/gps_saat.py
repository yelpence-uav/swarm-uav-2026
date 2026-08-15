#!/usr/bin/env python3
"""Pi'nin sistem saatini PX4'un GPS zamanindan duzeltir.

NEDEN VAR (15 Agustos 2026'da olculdu)
--------------------------------------
Raspberry Pi 5'te RTC var (/dev/rtc0) ama YEDEK PILI YOK. Aciliste kernel
RTC'yi 1970 okuyor, systemd son bilinen saati geri yukluyor. Olcum:

    Aug 15 02:25:40  kernel: rpi-rtc: setting system clock to 1970-01-01
    konteyner "basladi" damgasi : 2026-08-14T23:25 UTC
    Pi gercek acilisi           : 2026-08-15 13:18 yerel

Yani Pi ~11 saat geriden aciliyor ve ancak ag gelince NTP saati one atlatiyor.

BU NEDEN ONEMLI: iki ucagin saati o pencerede BIRBIRINDEN FARKLI olur. Suru
entegrasyonunda "hangi ucak once lider oldu", "kacinma hangi anda tetiklendi"
gibi CAPRAZ UCAK karsilastirmalari buna dayaniyor. Ayrica yarisma gunu sahada
internet olmayabilir; NTP hic senkronlanmaz ve iki kayit birlestirilemez.

COZUM: PX4 UTC'yi GPS'ten aliyor (Here4 -> DroneCAN -> PX4 RTC) ve MAVROS bunu
1 Hz'de /drone_N/mavros/time_reference uzerinden yayinliyor. Internet gerekmez,
iki ucak da AYNI GPS zamanina kilitlenir.

GUVENLI OLMASININ SEBEBI
------------------------
MAVROS'un time eklentisi olculdu:

    time_ref_source:  fcu     -> yayinlanan zaman FCU'nun kendi saati
    system_time_rate: 0.0     -> MAVROS Pi'nin saatini FCU'ya HIC gondermiyor

Yani akis TEK YONLU: FCU -> Pi. Bayat Pi saatinin FCU'nun iyi GPS saatini
bozma yolu yok.

⚠️ YALNIZ ACILISTA CALISIR. Saati ucus sirasinda atlatmak ROS zamanlayicilarini
ve kayit damgalarini bozar. baslat.sh bunu mavros ayaga kalktiktan SONRA,
diger dugumlerden ONCE bir kez cagirir.

Kullanim:
    python3 /ws/gps_saat.py --ns /drone_1 [--bekle 40] [--esik 3.0] [--kuru]

Cikis kodu HER ZAMAN 0 — acilisi asla bloke etmez.
"""

import argparse
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import TimeReference

# 2024-01-01. Bundan eski bir "GPS zamani" gercek olamaz; PX4'un RTC'si
# henuz GPS'ten beslenmemis demektir (time_unix_usec=0 ya da cop).
EN_ERKEN_MAKUL_EPOCH = 1_704_067_200.0


class GpsSaat(Node):
    """time_reference'tan tek bir gecerli ornek toplar."""

    def __init__(self, ns: str):
        super().__init__('gps_saat')
        self.ornek: tuple[float, float] | None = None   # (fcu_utc, alindigi_an)

        # Yayinci BEST_EFFORT. Varsayilan RELIABLE ile abone olunursa QoS
        # ESLESMEZ ve mesaj HIC gelmez — 15 Agustos'ta tam bu yasandi ve
        # "eklenti kapali" sanildi.
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self.create_subscription(
            TimeReference, f'{ns}/mavros/time_reference', self._geldi, qos
        )

    def _geldi(self, msg: TimeReference) -> None:
        fcu = msg.time_ref.sec + msg.time_ref.nanosec * 1e-9
        if fcu < EN_ERKEN_MAKUL_EPOCH:
            return   # PX4'un RTC'si henuz GPS'ten beslenmemis
        # header.stamp = mesajin ALINDIGI andaki sistem saati. Farki buradan
        # almak, "oku" ile "yaz" arasinda gecen sureyi disarida birakir.
        alindi = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if alindi <= 0.0:
            alindi = time.time()
        self.ornek = (fcu, alindi)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ns', default='/drone_1', help='ornek: /drone_1')
    ap.add_argument('--bekle', type=float, default=40.0,
                    help='GPS zamani icin en fazla bu kadar saniye bekle')
    ap.add_argument('--esik', type=float, default=3.0,
                    help='bu saniyeden kucuk farkta saate DOKUNMA')
    ap.add_argument('--kuru', action='store_true',
                    help='yalniz olc ve yaz, saati degistirme')
    a = ap.parse_args()

    rclpy.init(args=None)
    dugum = GpsSaat(a.ns)
    bitis = time.monotonic() + a.bekle
    try:
        while time.monotonic() < bitis and dugum.ornek is None:
            rclpy.spin_once(dugum, timeout_sec=0.5)
        ornek = dugum.ornek
    finally:
        dugum.destroy_node()
        rclpy.shutdown()

    if ornek is None:
        print(f'[gps_saat] GPS zamani {a.bekle:.0f} sn icinde gelmedi '
              f'({a.ns}/mavros/time_reference). Saat DEGISMEDI.')
        return 0

    fcu_utc, alindi = ornek
    fark = fcu_utc - alindi
    print(f'[gps_saat] GPS(FCU)={fcu_utc:.3f}  sistem={alindi:.3f}  '
          f'fark={fark:+.3f} sn')

    if abs(fark) < a.esik:
        print(f'[gps_saat] fark esigin ({a.esik} sn) altinda — saate dokunulmadi.')
        return 0

    if a.kuru:
        print(f'[gps_saat] KURU: saat {fark:+.3f} sn kaydirilacakti.')
        return 0

    # Simdiki ana AYNI farki uygula — okuma ile yazma arasinda gecen sure
    # hesaptan dusmus olur.
    yeni = time.time() + fark
    try:
        time.clock_settime(time.CLOCK_REALTIME, yeni)
    except PermissionError:
        print('[gps_saat] IZIN YOK: konteynere --cap-add SYS_TIME gerekiyor. '
              'Saat DEGISMEDI.')
        return 0
    except OSError as e:
        print(f'[gps_saat] saat yazilamadi: {e}. Saat DEGISMEDI.')
        return 0

    print(f'[gps_saat] sistem saati {fark:+.3f} sn kaydirildi -> '
          f'{time.strftime("%F %T", time.gmtime(yeni))} UTC')
    return 0


if __name__ == '__main__':
    sys.exit(main())
