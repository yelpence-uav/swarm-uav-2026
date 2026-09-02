#!/usr/bin/env python3
"""HOME kaydinin OLCEREK denetlenmesi — RTL'in dayandigi tek sayi.

NEDEN VAR (26 Agustos 2026 saha olayi, P0)
RTL basildiginda uc ucak da kalkis noktalarina degil, UCU BIRDEN AYNI
NOKTAYA indi: kalkislarin ~9 m kuzeydogusu, birbirlerine 1-2 m. Olculdu:
PX4'un home kayitlari TAM o inis noktalariydi. Yani RTL dogru uctu,
HOME'LAR YANLISTI. Ayni gece, ayni ucaklarla, ayni kodla yapilan ONCEKI
ucusta RTL uc ucagi da kendi kalkis noktasina nokta atisi indirmisti —
yani hata SUREKLI DEGIL, home'un YAZILDIGI ANDA kilitleniyor.

Depoda origin icin olcerek dogrulayan bir katman vardi (_origin_dogrula)
ama HOME icin hicbir denetim YOKTU: mavros_telemetry_mapper.map_home
gelen degeri kosulsuz kopyaliyor ve `home_set = True` yaziyordu. Yani
sistem home'un DOGRU oldugunu degil, yalnizca GELDIGINI biliyordu.

HUKUM VEREN TEK DENETIM: HOME YERINDE MI  [yalniz YERDE ve DISARM]
  home lat/lon, ucagin kendi GPS'ine yakin olmali. 26 Agustos'ta home
  kalkis noktasindan ~9 m uzaktaydi ve ucak kalkis noktasinda duruyordu —
  yani bu denetim o arizayi YAKALARDI. RTL'in kullandigi sey de zaten
  home'un GLOBAL kaydidir. Kalkistan sonra ucak home'dan uzaklasacagi
  icin denetim havada ANLAMSIZDIR ve kosulmaz.

🔴 CERCEVE FARKI HUKUM VERMEZ — 2 Eylul 2026'da UCAKTA olculerek ogrenildi.
  Ilk surumde ikinci bir denetim vardi: home'un global temsilinden ortak
  origin'e gore hesaplanan NED ile PX4'un bildirdigi yerel NED
  (HomePosition.position) karsilastiriliyordu. Ayrilirlarsa "cerceve
  home'un altindan kaydi" deniyordu. SAHADA YANLIS CIKTI:

      HomePosition.position : (0.0, 0.0, -0.0)      <- PX4'un yerel home'u
      ucagin yerel konumu   : (16.12, 10.54)        =  19.26 m
      origin_synced         : true, olculen sapma 0.01 m

  Sebep: PX4 home'u origin push'undan ONCE yaziyor. O an yerel cerceve
  ucagin uzerinde oldugu icin home yerel olarak (0,0,0) kaydediliyor.
  Sonra SET_GPS_GLOBAL_ORIGIN uygulaniyor, cerceve 19 m kayiyor, ama PX4
  home'un YEREL kaydini GERI HESAPLAMIYOR. Yani fark NORMAL bir acilis
  durumu — her boot'ta olusuyor ve home'un global kaydi bu sirada
  DOGRU kaliyor (olculdu: ucagin GPS'ine 0.67 m).

  Ustelik duzeltilemiyor da: `SET_HOME(current_gps)` yedi kez "KABUL
  edildi" dedi ve `position` (0,0,0) olarak KALDI. Yani bu farka bakip
  otomatik duzeltme denemek, duzeltemeyecegi bir seyi sonsuza kadar
  tekrarlamak oluyordu.

  Fark yine de OLCULUP RAPORLANIYOR (`cerceve_m`) — bilgi degerli, ama
  `home_ok`'a girmiyor ve RTL'i kapatmiyor.

TOLERANS FIX'E BAGLI — olcumden
  1 Eylul, ylp00, RTK YOK (fix 3): home <-> kendi GPS'i tek ornekte
  0.062 m cikti. Ama 2 Eylul'de ayni ucakta 30 saniyelik araliklarla
  1.17-1.27 m olculdu: RTK'siz konum cozümü bu mertebede geziniyor.
  Tek ornege bakip 1.0 m koymak YANLIS ALARM uretirdi — nitekim uretti.
  🔴 O 3.0 m DE DARDI. 04:25'te ylp02'de HAREKETSIZ ucakta olculdu:
      yatay  1.39 · 1.52 · 1.57 · 1.63 · 3.07 · 3.51 · 3.75 m
      dikey  0.54 · 1.00 · 1.23 · 2.66 · 2.81 · 3.00 m
  Denetim durmadan yanlis alarm verdi. Esikler ikinci kez genisletildi:
      fix >= 5 (RTK)            -> yatay 1.0 m · dikey 2.0 m
      fix 3-4  (standalone/DGPS)-> yatay 6.0 m · dikey 5.0 m
  6.0 m, olculen en buyuk gezinmenin ~1.6 kati ve 26 Agustos arizasinin
  (9 m) ~0.67'si — yani RTK'siz bile gercek kaymayi yakalar.

  DERS: bir esigi IKI ORNEKTEN turetme. Ilk tahmin (1.0) tek ornekten,
  ikincisi (3.0) iki ornekten geldi; ikisi de dardi. Ucuncusu yedi
  ornekten geliyor.

OLCULEMEYEN DURUMDA HUKUM VERILMEZ
  jole_olc.py'nin dersi burada da gecerli: sessizce sayi ureten bir olcu
  aleti, hic olcmeyenden kotudur. GPS fix yoksa, home henuz yazilmadiysa
  ya da origin bilinmiyorsa `gecerli=False` doner ve `home_ok` None kalir.
  Cagiran taraf "bilinmiyor"u "bozuk" ile karistirmamalidir.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

# Enlem derecesi basina metre. px4_bridge._origin_dogrula ile AYNI sabit —
# iki denetim ayni geodezik yaklasimi kullanmazsa sonuclari kiyaslanamaz.
_M_PER_DEG_LAT = 111320.0

TOL_YATAY_RTK_M = 1.0    # fix >= 5: cozum cm mertebesinde
# 🔴 RTK'SIZ BANT OLCULDU ve ilk tahmin DARDI. 2 Eylul 04:20'de iki ornege
# bakip 3.0 m konmustu; 04:25'te ylp02'de HAREKETSIZ ucakta sunlar olculdu:
#     yatay  1.39 · 1.52 · 1.57 · 1.63 · 3.07 · 3.51 · 3.75 m
#     dikey  0.54 · 1.00 · 1.23 · 2.66 · 2.81 · 3.00 m
# Yani 3.0/2.0 esikleri GURULTU BANDININ ICINDE kaliyordu ve denetim
# durmadan yanlis alarm veriyordu.
#
# 6.0 m secildi: olculen en buyuk gezinmenin (3.75) ~1.6 kati, 26 Agustos
# arizasinin (9 m) ~0.67'si. Yani RTK'siz bile GERCEK kaymayi yakalar,
# gurultuye takilmaz. RTK gelince 1.0 m'ye iner ve cok daha keskin olur.
TOL_YATAY_HAM_M = 6.0
TOL_DIKEY_RTK_M = 2.0    # fix >= 5
# Dikey GPS yataydan kotudur; olculen 3.00 m. 5.0 m ayni mantikla secildi.
TOL_DIKEY_HAM_M = 5.0
# Bu esigin ustundeki cerceve farki RAPORLANIR ama HUKUM VERMEZ (bkz. modul
# basligi). Acilista 19 m cikmasi normaldir; burada yalnizca "kayda deger mi"
# esigi olarak duruyor.
TOL_CERCEVE_M = 1.0
RTK_FIX_ESIGI = 5        # MAVROS/PX4: 5=RTK float, 6=RTK fixed


def yatay_tolerans(gps_fix_type: int) -> float:
    """Fix kalitesine gore yatay tolerans secer.

    Args:
        gps_fix_type (int): 0=fix yok ... 3=3D, 4=DGPS, 5/6=RTK.

    Returns:
        float: Metre cinsinden tolerans.
    """
    return (TOL_YATAY_RTK_M if gps_fix_type >= RTK_FIX_ESIGI
            else TOL_YATAY_HAM_M)


def dikey_tolerans(gps_fix_type: int) -> float:
    """Fix kalitesine gore dikey tolerans secer.

    Args:
        gps_fix_type (int): 0=fix yok ... 3=3D, 4=DGPS, 5/6=RTK.

    Returns:
        float: Metre cinsinden tolerans.
    """
    return (TOL_DIKEY_RTK_M if gps_fix_type >= RTK_FIX_ESIGI
            else TOL_DIKEY_HAM_M)


@dataclass
class HomeDenetimi:
    """Tek bir denetim turunun sonucu.

    Attributes:
        gecerli (bool): Olcum YAPILABILDI mi. False ise home_ok'a bakma.
        home_ok (bool | None): Kosulabilen denetimlerin hepsi gecti mi.
            Olculemediyse None ("bilinmiyor" != "bozuk").
        yatay_m (float | None): home <-> kendi GPS yatay sapmasi (yerde).
        dikey_m (float | None): home AMSL <-> GPS AMSL sapmasi (yerde).
        cerceve_m (float | None): geodezik NED <-> PX4 yerel NED sapmasi.
        sebep (str): Insan okuyacak tek satirlik gerekce.
    """

    gecerli: bool
    home_ok: bool | None
    yatay_m: float | None
    dikey_m: float | None
    cerceve_m: float | None
    sebep: str


def geodezik_ned(
    lat: float, lon: float, ref_lat: float, ref_lon: float
) -> tuple[float, float]:
    """(lat, lon) noktasinin referansa gore kuzey/dogu ofsetini metre verir.

    Args:
        lat (float): Nokta enlemi, derece.
        lon (float): Nokta boylami, derece.
        ref_lat (float): Referans enlemi, derece.
        ref_lon (float): Referans boylami, derece.

    Returns:
        tuple[float, float]: (kuzey_m, dogu_m).
    """
    kuzey = (lat - ref_lat) * _M_PER_DEG_LAT
    dogu = (lon - ref_lon) * _M_PER_DEG_LAT * math.cos(math.radians(lat))
    return kuzey, dogu


def home_denetle(
    *,
    home_set: bool,
    home_lat: float,
    home_lon: float,
    home_alt_amsl: float,
    home_yerel_dogu: float | None,
    home_yerel_kuzey: float | None,
    home_yerel_yukari: float | None,
    origin_lat: float | None,
    origin_lon: float | None,
    origin_alt_amsl: float | None,
    gps_lat: float,
    gps_lon: float,
    gps_alt_amsl: float,
    gps_fix_type: int,
    yerde: bool,
    tol_yatay_m: float | None = None,
    tol_dikey_m: float | None = None,
) -> HomeDenetimi:
    """HOME kaydini denetler; hukmu YER denetimi verir.

    Args:
        home_set (bool): PX4 home'u yazdi mi.
        home_lat (float): Home enlemi, derece.
        home_lon (float): Home boylami, derece.
        home_alt_amsl (float): Home AMSL yuksekligi, metre.
        home_yerel_dogu (float | None): HomePosition.position.x (ENU dogu).
        home_yerel_kuzey (float | None): HomePosition.position.y (ENU kuzey).
        home_yerel_yukari (float | None): HomePosition.position.z (ENU yukari).
        origin_lat (float | None): Ortak origin enlemi.
        origin_lon (float | None): Ortak origin boylami.
        origin_alt_amsl (float | None): Ortak origin AMSL yuksekligi.
        gps_lat (float): Ucagin anlik GPS enlemi.
        gps_lon (float): Ucagin anlik GPS boylami.
        gps_alt_amsl (float): Ucagin anlik GPS AMSL yuksekligi.
        gps_fix_type (int): 0=fix yok ... 3=3D, 6=RTK fixed.
        yerde (bool): Ucak yerde ve disarm mi (2. denetim yalniz o zaman).
        tol_yatay_m (float | None): Yatay tolerans, metre. None ise fix
            kalitesine gore secilir (bkz. yatay_tolerans).
        tol_dikey_m (float | None): Dikey tolerans, metre. None ise fix
            kalitesine gore secilir (bkz. dikey_tolerans).

    Returns:
        HomeDenetimi: Denetim sonucu.
    """
    if not home_set:
        return HomeDenetimi(False, None, None, None, None,
                            'home henuz yazilmadi')

    # --- CERCEVE FARKI — yalnizca OLCULUR, hukum vermez ------------------
    # Acilista 19 m cikmasi NORMALDIR (bkz. modul basligi): PX4 home'u
    # origin push'undan once yaziyor ve yerel kaydi geri hesaplamiyor.
    cerceve_m = None
    if (None not in (home_yerel_dogu, home_yerel_kuzey)
            and None not in (origin_lat, origin_lon)):
        bek_kuzey, bek_dogu = geodezik_ned(
            home_lat, home_lon, origin_lat, origin_lon)
        cerceve_m = math.hypot(bek_dogu - home_yerel_dogu,
                               bek_kuzey - home_yerel_kuzey)

    # --- HUKUM: HOME YERINDE MI — yalniz yerde ---------------------------
    gps_var = gps_fix_type >= 3 and abs(gps_lat) > 0.001
    if not (yerde and gps_var):
        neden = (f'GPS fix yetersiz (fix={gps_fix_type})' if not gps_var
                 else 'ucak havada — home yer denetimi anlamsiz')
        return HomeDenetimi(False, None, None, None, cerceve_m, neden)

    tol_yatay = (tol_yatay_m if tol_yatay_m is not None
                 else yatay_tolerans(gps_fix_type))
    tol_dikey = (tol_dikey_m if tol_dikey_m is not None
                 else dikey_tolerans(gps_fix_type))
    kuzey, dogu = geodezik_ned(home_lat, home_lon, gps_lat, gps_lon)
    yatay_m = math.hypot(kuzey, dogu)
    dikey_m = abs(home_alt_amsl - gps_alt_amsl)
    home_ok = yatay_m <= tol_yatay and dikey_m <= tol_dikey

    if home_ok:
        sebep = f'home dogrulandi ({yatay_m:.2f} m yatay, fix={gps_fix_type})'
    else:
        sebep = (f'home kendi GPS-inden {yatay_m:.2f} m yatay / '
                 f'{dikey_m:.2f} m dikey ayri '
                 f'(tolerans {tol_yatay:.1f}/{tol_dikey:.1f}, '
                 f'fix={gps_fix_type})')
    return HomeDenetimi(True, home_ok, yatay_m, dikey_m, cerceve_m, sebep)
