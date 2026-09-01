#!/usr/bin/env python3
"""HOME DENETIMI — ucus oncesi, uctan uca, uc saniye. Ucus GEREKMEZ.

NEDEN VAR (26 Agustos 2026, P0)
RTL basildiginda uc ucak da kalkis noktalarina degil UCU BIRDEN AYNI
NOKTAYA indi: kalkislarin ~9 m kuzeydogusu, birbirlerine 1-2 m. PX4'un
home kayitlari TAM o inis noktalariydi — RTL dogru uctu, HOME'LAR
YANLISTI. Ayni gece ONCEKI ucusta RTL kusursuz calismisti; yani hata
surekli degil, home'un YAZILDIGI ANDA kilitleniyor.

Bugune kadar bunu ucus ONCESINDE gorebilecegimiz hicbir arac yoktu:
home yalnizca okunuyor, hicbir yerde DOGRULANMIYORDU. YKI haritasinda
home isareti de yok, yani operator kaymayi ekrandan da goremiyor.

NE OLCER — iki bagimsiz denetim (ayrinti: home_dogrulama.py)
  1. CERCEVE : home'un global temsili ile PX4'un yerel temsili ortusuyor mu
  2. YERDE   : home, ucagin kendi GPS konumunda mi

KULLANIM
  ⚠️ `docker exec` ROS ortamini MIRAS ALMAZ (TUZAKLAR 1.25) — dugumleri
  goremez ve HATA DA VERMEZ. Sourcelamak zorunlu:

    docker exec -e ROS_LOCALHOST_ONLY=1 drone1 bash -lc \
      'source /opt/ros/jazzy/setup.bash; source /ws/install/setup.bash; \
       python3 /ws/home_denetle.py 1'

  YKI'den, tek satir (drone_bul.sh IP'yi kendi bulur):
    ./deploy/yki/drone_bul.sh ylp00 "docker exec -e ROS_LOCALHOST_ONLY=1 \
      drone1 bash -lc 'source /opt/ros/jazzy/setup.bash; \
      source /ws/install/setup.bash; python3 /ws/home_denetle.py 1'"

  Duzeltme (YERDE, disarm):  ... home_denetle.py 1 --duzelt

CIKIS KODU
    0 = GECTI      home guvenilir
    1 = KALDI      home kaymis  -> RTL'siz uc, inis "land" ile
    2 = OLCULEMEDI hukum yok    -> sebebi ekranda yazar

🔴 --duzelt YALNIZ YERDE VE DISARM ISE calisir. Home'u havada degistirmek
RTL'in hedefini ucus ortasinda kaydirir; cozmeye calistigimiz hatanin
daha kotusudur.
"""
import sys
import time

from mavros_msgs.msg import HomePosition, State
from mavros_msgs.srv import CommandHome
import rclpy
from rclpy.node import Node
from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile,
                       ReliabilityPolicy)
from sensor_msgs.msg import NavSatFix
from swarm_control.px4_interface.home_dogrulama import (
    home_denetle, TOL_DIKEY_M, yatay_tolerans)
from swarm_interfaces.msg import SwarmOrigin

# MAVROS konulari icin: BEST_EFFORT + VOLATILE her yayinciyla uyumludur.
# Ters yon (RELIABLE abone, BEST_EFFORT yayinci) SESSIZCE baglanmaz —
# TUZAKLAR 2.1, bu depodaki en pahali tek kural.
MAVROS_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)
# Origin yayincisi RELIABLE + TRANSIENT_LOCAL (swarm_origin_publisher).
# TRANSIENT_LOCAL sart: gec baglanan abone SON degeri aninda alir, yoksa
# 1 Hz'lik yayini beklemek gerekirdi.
ORIGIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


class HomeDenetci(Node):
    """Home, GPS, durum ve origin'i toplayip tek hukum verir."""

    def __init__(self, agent_id: int) -> None:
        super().__init__(f'home_denetle_{agent_id}')
        ns = f'/drone_{agent_id}'
        self.home = None
        self.fix = None
        self.state = None
        self.origin = None
        self.create_subscription(
            HomePosition, f'{ns}/mavros/home_position/home',
            lambda m: setattr(self, 'home', m), MAVROS_QOS)
        self.create_subscription(
            NavSatFix, f'{ns}/mavros/global_position/global',
            lambda m: setattr(self, 'fix', m), MAVROS_QOS)
        self.create_subscription(
            State, f'{ns}/mavros/state',
            lambda m: setattr(self, 'state', m), MAVROS_QOS)
        self.create_subscription(
            SwarmOrigin, '/swarm/internal/origin',
            lambda m: setattr(self, 'origin', m), ORIGIN_QOS)
        self._home_cli = self.create_client(
            CommandHome, f'{ns}/mavros/cmd/set_home')

    def topla(self, saniye: float = 8.0) -> None:
        """Dort kaynagin hepsi gelene kadar (ya da sure dolana kadar) doner."""
        bitis = time.time() + saniye
        while time.time() < bitis and rclpy.ok():
            rclpy.spin_once(self, timeout_sec=0.2)
            if all(x is not None
                   for x in (self.home, self.fix, self.state, self.origin)):
                return


def _eksikleri_yaz(d: HomeDenetci) -> None:
    """Hangi kaynagin gelmedigini tek tek soyler — sessiz basarisizlik yok."""
    for ad, deger, ipucu in (
        ('mavros/state', d.state, 'mavros ayakta mi'),
        ('home_position/home', d.home, 'PX4 home yazdi mi (GPS fix?)'),
        ('global_position/global', d.fix, 'GPS fix var mi'),
        ('/swarm/internal/origin', d.origin,
         'swarm_origin_publisher kosuyor mu'),
    ):
        if deger is None:
            print(f'  ❌ {ad:26s} GELMEDI   ({ipucu})')


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].isdigit():
        print(__doc__)
        return 2
    agent_id = int(sys.argv[1])
    duzelt = '--duzelt' in sys.argv

    rclpy.init()
    d = HomeDenetci(agent_id)
    d.topla()

    if d.state is None or not d.state.connected:
        print(f'\n🔴 drone_{agent_id}: MAVROS PX4-e BAGLI DEGIL '
              f'(connected={getattr(d.state, "connected", "?")}).')
        print('   Once bunu coz — home okunamaz. 1 Eylul 2026: ayni belirti '
              'ylp00-da `docker restart` ile kapandi, donanim degildi.')
        _eksikleri_yaz(d)
        rclpy.shutdown()
        return 2

    if d.home is None or d.fix is None or d.origin is None:
        print(f'\n⚠️  drone_{agent_id}: olcum icin gereken veri eksik.')
        _eksikleri_yaz(d)
        rclpy.shutdown()
        return 2

    armed = bool(d.state.armed)
    sonuc = home_denetle(
        home_set=True,
        home_lat=d.home.geo.latitude,
        home_lon=d.home.geo.longitude,
        home_alt_amsl=d.home.geo.altitude,
        home_yerel_dogu=d.home.position.x,
        home_yerel_kuzey=d.home.position.y,
        home_yerel_yukari=d.home.position.z,
        origin_lat=d.origin.origin_lat_deg,
        origin_lon=d.origin.origin_lon_deg,
        origin_alt_amsl=d.origin.origin_alt_amsl_m,
        gps_lat=d.fix.latitude,
        gps_lon=d.fix.longitude,
        gps_alt_amsl=d.fix.altitude,
        gps_fix_type=(3 if d.fix.status.status >= 0 else 0),
        yerde=not armed,
    )

    print(f'\n=========== drone_{agent_id} · HOME DENETIMI ===========')
    print(f'  durum      : {"ARMED" if armed else "disarm"} · '
          f'mod {d.state.mode or "?"}')
    print(f'  home       : {d.home.geo.latitude:.7f}, '
          f'{d.home.geo.longitude:.7f}  @ {d.home.geo.altitude:.2f} m AMSL')
    print(f'  anlik GPS  : {d.fix.latitude:.7f}, '
          f'{d.fix.longitude:.7f}  @ {d.fix.altitude:.2f} m AMSL')
    print(f'  ortak origin: {d.origin.origin_lat_deg:.7f}, '
          f'{d.origin.origin_lon_deg:.7f}')
    print()
    fix = 3 if d.fix.status.status >= 0 else 0
    if sonuc.yatay_m is not None:
        print(f'  HUKUM  home <-> kendi GPS: yatay {sonuc.yatay_m:6.2f} m   '
              f'dikey {sonuc.dikey_m:5.2f} m')
        print(f'         tolerans {yatay_tolerans(fix):.1f} / '
              f'{TOL_DIKEY_M:.1f} m  (fix={fix})')
    else:
        print('  HUKUM  kosulmadi ' +
              ('(ucak ARMED — home yer denetimi havada anlamsiz)' if armed
               else '(GPS yok)'))
    if sonuc.cerceve_m is not None:
        # BILGI, hukum degil: acilista 19 m normaldir — PX4 home'u origin
        # push'undan once yaziyor ve yerel kaydini geri hesaplamiyor
        # (2 Eylul 2026'da ucakta olculdu, TUZAKLAR §2.26).
        print(f'  bilgi  cerceve farki {sonuc.cerceve_m:6.2f} m '
              f'(hukme GIRMEZ)')
    print()

    if not sonuc.gecerli:
        print(f'  ⚠️  OLCULEMEDI — {sonuc.sebep}')
        print('     Hukum verilmedi. "Bilinmiyor" ile "bozuk" ayni sey degil.')
        kod = 2
    elif sonuc.home_ok:
        print('  ✅ GECTI — home guvenilir')
        kod = 0
    else:
        print(f'  🔴 KALDI — {sonuc.sebep}')
        print('     RTL BU HALIYLE KULLANILMAZ. Inis "land" ile yapilmali.')
        print('     Duzeltmek icin (YERDE, disarm): --duzelt')
        kod = 1

    if duzelt:
        print()
        if armed:
            print('  🔴 --duzelt REDDEDILDI: ucak ARMED. Home-u havada '
                  'degistirmek RTL hedefini ucus ortasinda kaydirir.')
            kod = max(kod, 1)
        elif not d._home_cli.service_is_ready():
            print('  ❌ set_home servisi hazir degil (mavros?).')
            kod = max(kod, 2)
        else:
            print('  🔧 HOME anlik GPS konumuna yeniden yaziliyor...')
            req = CommandHome.Request()
            req.current_gps = True
            req.yaw = 0.0
            fut = d._home_cli.call_async(req)
            rclpy.spin_until_future_complete(d, fut, timeout_sec=5.0)
            cevap = fut.result()
            if cevap is not None and cevap.success:
                print('  ✅ KABUL edildi. Betigi TEKRAR kosturup dogrula — '
                      '"gonderdim" demek "oldu" demek degildir.')
            else:
                print(f'  🔴 REDDEDILDI (MAV_RESULT='
                      f'{getattr(cevap, "result", "?")})')
                kod = max(kod, 1)

    rclpy.shutdown()
    return kod


if __name__ == '__main__':
    sys.exit(main())
