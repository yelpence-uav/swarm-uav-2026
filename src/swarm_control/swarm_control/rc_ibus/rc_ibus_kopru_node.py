# Copyright 2026 Yelpence
"""Gorev 2 surus kumandasi: FS-iA6B i-BUS -> mavros_msgs/RCIn.

NEDEN VAR (gorev2.md B1, 30 Agustos 2026)
-----------------------------------------
Sartname 5.2 her IHA icin, suruyu suren kumanda DISINDA, kill switch icin
AYRI bir kumanda ve ayri bir yetkili pilot ZORUNLU kiliyor. Yani ylp00'da
IKI alici olmak zorunda ve Pixhawk'in RC girisi kill-switch pilotunun
alicisina ait (CH5 kill, CH8 arm, CH3 failsafe 2100 — RPI_ESITLEME §5,
19 Agu havada dogrulandi). PX4'te tek RC girisi vardir.

Bu yuzden suru kumandasinin alicisi Pi'ye baglaniyor ve bu dugum onu
`joystick_interpreter`'in bekledigi RCIn bicimine cevirip yerel bir konuya
yayinliyor. joystick_interpreter'da TEK SATIR kod degismedi: `_on_mavros_rc_in`
zaten 1000-2000 PWM bekliyor; baslat.sh yalniz remap'i buraya cevirdi.

🔴 KANAL CAKISMASI — remap tekillesmezse TERS CALISIR
Suru zinciri CH5'i *emniyet (SwA)*, CH8'i *kalkis/inis (SwD)* saniyor.
joystick_interpreter kill pilotunun `/drone_N/mavros/rc/in` konusuna bagli
kalirsa KILL SWITCH'I KALDIRMAK SURU KOMUTLARINI ACAR ve ARM SWITCH'I
KALKIS/INIS TETIKLER. baslat.sh iki remap'i birlikte cevirir; biri
unutulursa iki kaynak ayni callback'i besler (gorev2.md B11).

DEADMAN NASIL DUSER
Kumanda kapaninca FS-iA6B SUSMAZ, failsafe cercevesi basmaya devam eder
(RPI_ESITLEME §5'te olculdu) — yani "veri geliyor mu" bakmak YETMEZ.
Cozum alicinin kendi ozelligi: suru alicisinin failsafe'i SwA (emniyet)
kanali KILITLI konuma gidecek sekilde kaydedilir. O zaman:
    kumanda kapandi -> SwA failsafe = KILITLI -> deadman duser
                    -> mode_manager HOLD -> suru havada asili bekler
Bu dugumun bayatlik denetimi ayri bir sey: KABLO/ALICI kopmasini yakalar
(cerceve hic gelmez -> yayin durur -> joystick_interpreter zaman asimi).
"""

import threading
import time

from mavros_msgs.msg import RCIn
import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
import serial

from .ibus_cozucu import IbusAyiklayici, kanallar_makul

# joystick_interpreter'in `_PX4_QOS`'uyla BIREBIR ayni. Uyusmazlik bu
# projede bes abonelik + YKI koprusunu SESSIZCE bos birakmisti
# (INTERFACE_CONTRACT §3.0.1, 15 Agustos).
_RC_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


class RcIbusKopruNode(Node):
    """i-BUS seri akisini RCIn olarak yayinlar."""

    def __init__(self) -> None:
        super().__init__('rc_ibus_kopru')

        from rcl_interfaces.msg import ParameterDescriptor
        _dnm = ParameterDescriptor(dynamic_typing=True)
        # `-p x:=50` INTEGER gelir ve double declare edilmis dugumu
        # ACILISTA oldurur (sahada iki kez yasandi).
        self.declare_parameter('port', '/dev/ttyUSB0')
        self.declare_parameter('baud', 115200, _dnm)
        self.declare_parameter('agent_id', 1, _dnm)
        self.declare_parameter('yayin_konusu', '')
        # Cerceve ~130 Hz geliyor; hepsini yayinlamak gereksiz.
        # joystick_interpreter zaten 30 Hz yayinliyor, 50 Hz bol bol taze.
        # Her cerceveyi gecirmek esp32_bridge'i 130 Hz TIP_KOMUT yazmaya
        # zorlardi; firmware kapisi 50 ms (20 Hz) ve fazlasi RTCM ile ayni
        # UART'ta bosuna yer kaplardi.
        # NOT (30 Agu, olculdu): bu bir TAVAN, birebir hiz degil. Gercek
        # hiz seri okuma periyoduyla NICEMLENIR: read(64) @ 4160 B/s =
        # 15,4 ms dongu, 20 ms sinir -> her IKINCI tur gecer = 32,5 Hz
        # (olculen). Sorun degil: tuketicilerin ikisi de 20 Hz
        # (mode_manager tick + firmware TIP_KOMUT kapisi) ve msg sozlesmesi
        # 20-50 Hz istiyor. 50'ye yaklastirmak icin okuma boyu kucultulur.
        self.declare_parameter('yayin_hz', 50.0, _dnm)
        # Bu kadar sure gecerli cerceve gelmezse YAYIN DURUR (kablo/alici
        # kopmasi). Kumanda kapanmasi bundan FARKLI — onu SwA failsafe'i
        # tasir, bkz. modul basligi.
        self.declare_parameter('bayat_s', 0.3, _dnm)
        self.declare_parameter('tani_s', 10.0, _dnm)

        self._port = str(self.get_parameter('port').value)
        self._baud = int(self.get_parameter('baud').value)
        self._agent_id = int(self.get_parameter('agent_id').value)
        self._yayin_araligi = 1.0 / max(
            1e-6, float(self.get_parameter('yayin_hz').value)
        )
        self._bayat_s = float(self.get_parameter('bayat_s').value)
        tani_s = float(self.get_parameter('tani_s').value)

        konu = str(self.get_parameter('yayin_konusu').value) \
            or f'/drone_{self._agent_id}/rc/suru'
        self._konu = konu

        self._pub = self.create_publisher(RCIn, konu, _RC_QOS)

        self._ayiklayici = IbusAyiklayici()
        self._ser = None
        self._calisiyor = True
        self._son_yayin = 0.0
        self._son_gecerli = 0.0
        self._yayinlanan = 0
        self._makul_uyarildi = False
        self._son_kanallar: list[int] = []
        self._tani_onceki_gecerli = 0

        self._okuyucu = threading.Thread(
            target=self._seri_oku_dongusu, daemon=True
        )
        self._okuyucu.start()

        if tani_s > 0.0:
            self.create_timer(tani_s, self._tani_yaz)

        self.get_logger().info(
            f'rc_ibus_kopru basladi: {self._port} @ {self._baud} -> {konu} '
            f'(yayin <= {1.0 / self._yayin_araligi:.0f} Hz)'
        )

    # ------------------------------------------------------------------
    def _seri_ac(self) -> bool:
        """Portu acar. Hata firlatmaz; dongu tekrar dener."""
        try:
            # DTR/RTS'yi port ATANMADAN once dusur: bazi USB-TTL
            # adaptorleri acilista bu hatlari darbeliyor (esp32_bridge'de
            # ayni desen; orada ESP'yi resetliyordu).
            ser = serial.Serial(baudrate=self._baud, timeout=0.1)
            ser.dtr = False
            ser.rts = False
            ser.port = self._port
            ser.open()
            self._ser = ser
            self.get_logger().info(f'i-BUS portu acildi: {self._port}')
            return True
        except (serial.SerialException, OSError) as exc:
            self._ser = None
            self.get_logger().error(
                f'i-BUS portu acilamadi ({self._port}): {exc}',
                throttle_duration_sec=5.0,
            )
            return False

    def _seri_oku_dongusu(self) -> None:
        """Seri porttan surekli okur; kopmada yeniden baglanir."""
        while self._calisiyor:
            if self._ser is None or not self._ser.is_open:
                time.sleep(1.0)
                self._seri_ac()
                continue
            try:
                # 🔴 OKUMA BOYU YAYIN HIZINI BELIRLIYOR — 30 Agu sahada
                # olculdu. read(N) N bayt DOLANA ya da timeout'a kadar
                # bloklar; 4160 B/s'te read(256) = 61,5 ms, yani dongu
                # 16,2 Hz kosuyordu ve `yayin_hz=50` hicbir ise yaramiyordu
                # (olculen /drone_1/rc/suru = 16.2 Hz). 64 bayt = ~15 ms.
                veri = self._ser.read(64)
            except (serial.SerialException, OSError) as exc:
                self.get_logger().warning(
                    f'i-BUS okuma hatasi, yeniden baglanilacak: {exc}'
                )
                try:
                    self._ser.close()
                except Exception:  # noqa: BLE001
                    pass
                self._ser = None
                continue

            if not veri:
                continue

            # Bir okumada birden fazla cerceve gelebilir. Sayaclar ve
            # makullik denetimi HEPSI icin kosar, ama YAYIN yalnizca EN
            # TAZE cerceveyle yapilir: hiz siniri eskiden yiginin ILK
            # (en eski) cercevesini yayinliyordu ve pilotun cubugu
            # gereksiz yere bayatliyordu.
            son = None
            for kanallar in self._ayiklayici.besle(veri):
                self._cerceve_geldi(kanallar)
                son = kanallar
            if son is not None:
                self._belki_yayinla(son)

    # ------------------------------------------------------------------
    def _cerceve_geldi(self, kanallar: list[int]) -> None:
        """Gecerli bir cerceve cozuldu — sayaclar ve saglik denetimi."""
        self._son_gecerli = time.monotonic()
        self._son_kanallar = kanallar

        # 🔴 SESSIZ ARIZA KAPISI: FS-i6X VARSAYILANI ALTI KANAL. 10 kanal
        # kipine alinmazsa SwC (formasyon) ve SwD (kalkis/inis) coplukten
        # okunur ve kumandadaki iki anahtar hicbir sey yapmaz. Bu uyari
        # olmasa ariza ancak havada fark edilirdi.
        if not kanallar_makul(kanallar) and not self._makul_uyarildi:
            self._makul_uyarildi = True
            self.get_logger().error(
                'i-BUS ILK 8 KANAL MAKUL DEGIL: '
                f'{kanallar[:8]} (beklenen 900-2100). Kumanda 10 KANAL '
                'KIPINDE mi? FS-i6X varsayilani ALTI kanaldir ve o zaman '
                'SwC/SwD hicbir sey yapmaz.'
            )

    def _belki_yayinla(self, kanallar: list[int]) -> None:
        """Hiz siniri izin veriyorsa EN TAZE cerceveyi yayinlar."""
        simdi = time.monotonic()
        if simdi - self._son_yayin < self._yayin_araligi:
            return
        self._son_yayin = simdi

        msg = RCIn()
        msg.header.stamp = self.get_clock().now().to_msg()
        # i-BUS servo cercevesi RSSI TASIMAZ; uydurmuyoruz.
        msg.rssi = 0
        msg.channels = [int(k) for k in kanallar]
        self._pub.publish(msg)
        self._yayinlanan += 1

    def _tani_yaz(self) -> None:
        """Periyodik saglik ozeti — G0'da bakilacak tek satir."""
        a = self._ayiklayici
        yeni = a.gecerli - self._tani_onceki_gecerli
        self._tani_onceki_gecerli = a.gecerli
        bayat = (time.monotonic() - self._son_gecerli) > self._bayat_s

        if self._son_gecerli == 0.0:
            self.get_logger().warning(
                f'i-BUS: HIC GECERLI CERCEVE YOK ({self._port}). '
                f'atilan_bayt={a.atilan_bayt} '
                'Kablo? Baud? TX/RX ters mi?'
            )
            return

        seviye = self.get_logger().warning if bayat else self.get_logger().info
        seviye(
            f'i-BUS {"BAYAT" if bayat else "akiyor"}: '
            f'gecerli={a.gecerli} (+{yeni}) '
            f'checksum_hata={a.checksum_hata} atilan={a.atilan_bayt} '
            f'yayin={self._yayinlanan} '
            f'kanallar[1..8]={self._son_kanallar[:8]}'
        )

    def destroy_node(self) -> bool:
        self._calisiyor = False
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:  # noqa: BLE001
                pass
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RcIbusKopruNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
