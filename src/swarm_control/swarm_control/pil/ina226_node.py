# Copyright 2026 Yelpence
"""INA226 pil olcum dugumu — I2C'den okur, BatteryState yayinlar.

Cevrim mantigi BURADA DEGIL: `ina226.py` (saf, birim testli). Bu dosya
yalnizca I2C erisimi + ROS yayini yapiyor. Bolunmenin gerekcesi o dosyanin
basliginda.

NASIL KOSAR
    /ws/suru_dugumleri dosyasina `pil` yazilir, konteyner yeniden baslar.
    baslat.sh parametreleri env'den gecirir (INA226_*).

ON KOSUL — I2C ACIK OLMALI
    /boot/firmware/config.txt : dtparam=i2c_arm=on   (yeniden baslatma ister)
    cekirdek modulu           : i2c-dev             (/dev/i2c-1'i yaratir)
    kalici                    : echo i2c-dev >> /etc/modules
    Ikisi de yoksa dugun ERROR yazip SESSIZ KALIR — sahte deger YAYINLAMAZ.

🔴 SAHTE DEGER YAYINLAMAMA KURALI
Cihaz yoksa, kimlik tutmuyorsa ya da okuma hata veriyorsa bu dugum
HICBIR SEY yayinlamaz. Yayinlasaydi px4_bridge onu MAVROS'un yerine
kullanip "pil dolu" gosterebilirdi — sessiz-yanlis, ucusta pahali.
"""

import fcntl
import os

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from sensor_msgs.msg import BatteryState

from . import ina226 as IN

# Linux i2c-dev ioctl: kole adresini sec.
_I2C_SLAVE = 0x0703

# px4_bridge BEST_EFFORT abone olacak; yayinci da oyle olmali yoksa
# ESLESMEZ (D1 dersi, TUZAKLAR §2.x — 30 Agustos'ta olculdu).
_PIL_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)


class Ina226Node(Node):
    """INA226'dan pil gerilimi/akimi okur ve yayinlar."""

    def __init__(self) -> None:
        super().__init__('ina226_node')

        self.declare_parameter('i2c_veriyolu', '/dev/i2c-1')
        self.declare_parameter('adres', 0x40)
        # 🔴 SONT DIRENCI BILINMIYORSA 0.0 BIRAK. 0.0 = "akimi hesaplama",
        # gerilim yine dogru okunur. Uydurma bir deger yazmak akimi
        # olcekli-yanlis yapar ve bu HATA VERMEZ.
        self.declare_parameter('sont_ohm', 0.0)
        # Seri hucre sayisi — yalnizca kaba yuzde kestirimi icin.
        self.declare_parameter('hucre_sayisi', 0)
        self.declare_parameter('hz', 2.0)
        # Gerilim kalibrasyonu. VARSAYILAN NO-OP (1.0 / 0.0).
        # Gerekce ve 31 Agu'daki 0.22 V gozlemi: ina226.
        # bara_gerilimi_kalibre_v docstring'i. Once AYIRT EDICI OLCUM,
        # sonra kalibrasyon — yoksa yukle degisen bir farki sabit
        # carpanla 'duzeltip' baska yerde buyutmus oluruz.
        self.declare_parameter('gerilim_carpani', 1.0)
        self.declare_parameter('gerilim_ofset_v', 0.0)

        self._yol = str(self.get_parameter('i2c_veriyolu').value)
        self._adres = int(self.get_parameter('adres').value)
        self._sont = float(self.get_parameter('sont_ohm').value)
        self._hucre = int(self.get_parameter('hucre_sayisi').value)
        hz = max(0.2, float(self.get_parameter('hz').value))
        self._carpan = float(self.get_parameter('gerilim_carpani').value)
        self._ofset = float(self.get_parameter('gerilim_ofset_v').value)

        self._pub = self.create_publisher(BatteryState, 'pil/ina226', _PIL_QOS)
        self._hazir = False
        self._hata_sayaci = 0

        if self._acilis_dogrula():
            self._hazir = True
            self.create_timer(1.0 / hz, self._oku_ve_yayinla)

    # ------------------------------------------------------------------
    # I2C
    # ------------------------------------------------------------------
    def _yazmac_oku(self, reg: int) -> int:
        """Bir 16 bitlik yazmaci okur (big-endian, INA226 sozlesmesi)."""
        fd = os.open(self._yol, os.O_RDWR)
        try:
            fcntl.ioctl(fd, _I2C_SLAVE, self._adres)
            os.write(fd, bytes([reg]))
            ham = os.read(fd, 2)
            if len(ham) != 2:
                raise OSError(f'yazmac 0x{reg:02X}: kisa okuma ({len(ham)} bayt)')
            return (ham[0] << 8) | ham[1]
        finally:
            os.close(fd)

    def _acilis_dogrula(self) -> bool:
        """Cihaz var mi ve GERCEKTEN INA226 mi?

        Adres taramasi yetmez: o adreste baska bir cihaz olabilir ve
        yazmaclari anlamsiz sayilar dondurur. Kimlik yazmaclari tek kesin
        ayirt edici.
        """
        if not os.path.exists(self._yol):
            self.get_logger().error(
                f'{self._yol} YOK — I2C acik degil. Dugum SESSIZ kaliyor '
                '(sahte deger yayinlamaz). Acmak icin: '
                'config.txt `dtparam=i2c_arm=on` + yeniden baslat, '
                'sonra `sudo modprobe i2c-dev`.'
            )
            return False
        try:
            uretici = self._yazmac_oku(IN.YAZMAC_URETICI_KIMLIK)
            die = self._yazmac_oku(IN.YAZMAC_DIE_KIMLIK)
        except OSError as e:
            self.get_logger().error(
                f'0x{self._adres:02X} adresinde cihaz okunamadi ({e}). '
                'Kablo: SDA=pin 3 · SCL=pin 5 · 3V3=pin 1 · GND=pin 6. '
                'Dugum SESSIZ kaliyor.'
            )
            return False
        if not IN.kimlik_dogru(uretici, die):
            self.get_logger().error(
                f'0x{self._adres:02X} adresinde bir cihaz VAR ama INA226 '
                f'DEGIL (uretici=0x{uretici:04X} beklenen 0x{IN.URETICI_KIMLIK_TI:04X}, '
                f'die=0x{die:04X} beklenen 0x{IN.DIE_KIMLIK_INA226:04X}). '
                'Yanlis adres olabilir. Dugum SESSIZ kaliyor.'
            )
            return False

        if self._sont > 0.0:
            tavan = IN.azami_akim_a(self._sont)
            self.get_logger().info(
                f'INA226 DOGRULANDI @0x{self._adres:02X} · sont '
                f'{self._sont * 1000:.2f} mohm · olculebilir azami akim '
                f'{tavan:.1f} A. 🔴 Bunun USTUNDE yazmac DOYAR ve akim '
                'OLDUGUNDAN KUCUK okunur.'
            )
        else:
            self.get_logger().warning(
                f'INA226 DOGRULANDI @0x{self._adres:02X} · sont direnci '
                'VERILMEDI (sont_ohm=0). GERILIM dogru okunacak, AKIM 0.0 '
                'kalacak. Akim istiyorsan modulun sont degerini `sont_ohm` '
                'parametresine gir (or. 0.002 = 2 mohm).'
            )
        if self._carpan != 1.0 or self._ofset != 0.0:
            self.get_logger().warning(
                f'GERILIM KALIBRASYONU ACIK: carpan={self._carpan} '
                f'ofset={self._ofset:+.3f} V. Yayinlanan deger HAM DEGIL. '
                'Gerekcesi olculmus olmali (ina226.bara_gerilimi_kalibre_v).'
            )
        return True

    # ------------------------------------------------------------------
    def _oku_ve_yayinla(self) -> None:
        try:
            ham_bara = self._yazmac_oku(IN.YAZMAC_BARA_GERILIM)
            ham_sont = self._yazmac_oku(IN.YAZMAC_SONT_GERILIM)
        except OSError as e:
            self._hata_sayaci += 1
            self.get_logger().warning(
                f'INA226 okunamadi ({e}) — toplam {self._hata_sayaci} hata. '
                'Kablo gevsek olabilir.',
                throttle_duration_sec=5.0,
            )
            return

        gerilim = IN.bara_gerilimi_kalibre_v(ham_bara, self._carpan,
                                             self._ofset)
        akim = IN.akim_a(ham_sont, self._sont)

        m = BatteryState()
        m.header.stamp = self.get_clock().now().to_msg()
        m.voltage = float(gerilim)
        # ROS sozlesmesi: bosalma NEGATIF akim. INA226 yuke akan akimi
        # POZITIF olcuyor, o yuzden isaret cevriliyor.
        m.current = float(-akim)
        yuzde = IN.yuzde_kestir(gerilim, self._hucre)
        m.percentage = float(yuzde / 100.0) if self._hucre > 0 else float('nan')
        m.present = True
        m.power_supply_technology = BatteryState.POWER_SUPPLY_TECHNOLOGY_LIPO
        self._pub.publish(m)


def main(args=None) -> None:
    rclpy.init(args=args)
    dugum = Ina226Node()
    try:
        rclpy.spin(dugum)
    except KeyboardInterrupt:
        pass
    finally:
        dugum.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
