#!/usr/bin/env python3
"""RTCM3 cerceve ayiklama ve 1005/1006 (baz istasyonu konumu) cozme.

SAF PYTHON — ROS importu YOK. Iki yerden birden kullanilir:
  * `src/gcs/rtk_baz_survey.py`  (YKI dizustunde, seri porttan, `--oku`)
  * `swarm_control/swarm_origin_publisher.py` (uctaki dronda, mesh'ten)

NEDEN ORTAK MODUL: ayni bit cozumunu iki yere yazmak, birinin duzeltilip
digerinin unutulmasi demek (CLAUDE.md §9). Kod once rtk_baz_survey.py'de
yazildi ve sahada calisti; buraya BIREBIR tasindi, yeniden yazilmadi.

NE ISE YARIYOR
--------------
RTCM 1005/1006 mesaji baz istasyonunun OLCULMUS konumunu tasir (survey-in
tamamlaninca yayinlanmaya baslar). Suru bunu ORTAK ORIGIN olarak kullanir:
butun ucaklar AYNI yayini, AYNI baytlari cozdugu icin farkli origin almalari
imkansizdir. 1 Agustos'taki "iki taraf farkli cerceve kullaniyordu" kazasinin
kok nedeni boylece yapisal olarak ortadan kalkar.

⚠️ BAZ YANLIS YERDE OLABILIR — 2 Agustos, okul sahasi: alici FIXED BASE
modundaydi ve flash'inda EVDE yapilmis survey'in koordinati duruyordu.
Sahaya gelince yeniden olcmedi. 1005 acilinca goruldu: baz kendini
ucaklardan 2820 m otede saniyordu. Bu yuzden cozulen konum HER ZAMAN bilinen
bir noktayla karsilastirilmali (`uzaklik_m`).
"""

import math

# WGS84
A = 6378137.0
F = 1 / 298.257223563
E2 = F * (2 - F)


def ecef_to_lla(x, y, z):
    """ECEF metre -> (enlem, boylam, elipsoit yukseklik)."""
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - E2))
    for _ in range(8):
        n = A / math.sqrt(1 - E2 * math.sin(lat) ** 2)
        alt = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1 - E2 * n / (n + alt)))
    n = A / math.sqrt(1 - E2 * math.sin(lat) ** 2)
    alt = p / math.cos(lat) - n
    return math.degrees(lat), math.degrees(lon), alt


def lla_to_ecef(lat_deg, lon_deg, alt_m):
    """(enlem, boylam, yukseklik) -> ECEF metre. Test ve dogrulama icin."""
    p, l = math.radians(lat_deg), math.radians(lon_deg)
    n = A / math.sqrt(1 - E2 * math.sin(p) ** 2)
    return ((n + alt_m) * math.cos(p) * math.cos(l),
            (n + alt_m) * math.cos(p) * math.sin(l),
            (n * (1 - E2) + alt_m) * math.sin(p))


def uzaklik_m(lat1, lon1, lat2, lon2):
    """Iki nokta arasi yatay mesafe (duz-dunya, <10 km'de cm hatali)."""
    dk = (lat1 - lat2) * 111320.0
    dd = (lon1 - lon2) * 111320.0 * math.cos(math.radians(lat2))
    return math.hypot(dk, dd)


class Bit:
    """RTCM govdesi bit hizali degil; bit bit okumak sart."""

    def __init__(self, b):
        self.b, self.i = b, 0

    def u(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.b[self.i >> 3] >> (7 - (self.i & 7))) & 1)
            self.i += 1
        return v

    def s(self, n):
        v = self.u(n)
        return v - (1 << n) if v & (1 << (n - 1)) else v


# CRC-24Q (RTCM3). Polinom 0x1864CFB, baslangic 0.
_CRC24_TABLO = []
for _i in range(256):
    _c = _i << 16
    for _ in range(8):
        _c <<= 1
        if _c & 0x1000000:
            _c ^= 0x1864CFB
    _CRC24_TABLO.append(_c & 0xFFFFFF)


def crc24q(veri: bytes) -> int:
    """RTCM3 CRC-24Q."""
    c = 0
    for x in veri:
        c = ((c << 8) & 0xFFFFFF) ^ _CRC24_TABLO[((c >> 16) ^ x) & 0xFF]
    return c


class AyiklaRTCM:
    """Akistan RTCM3 cerceveleri ayikla (D3 + 10 bit uzunluk + 3 bayt CRC).

    ⚠️ CRC DOGRULAMASI VARSAYILAN ACIK. Onceki surumde yoktu ve dogrudan
    seri hatta sorun cikarmiyordu. Ama dronda RTCM ~%30 kayipli MESH'ten
    geliyor: kayip paket yuzunden iki parcadan birlesen bir akista uzunluk
    alani yanlis okunur ve govde COP olur. O cop 1005 gibi gorunurse origin
    dunyanin rastgele bir noktasina oturur. CRC bunu keser.
    """

    def __init__(self, crc_denetle: bool = True):
        self.b = bytearray()
        self.crc_denetle = crc_denetle
        self.crc_hatasi = 0
        self.gecerli = 0

    def besle(self, veri):
        self.b += veri
        out = []
        while True:
            i = self.b.find(b"\xd3")
            if i < 0 or len(self.b) < i + 3:
                del self.b[:max(0, i if i >= 0 else len(self.b) - 1)]
                return out
            ln = ((self.b[i + 1] & 0x03) << 8) | self.b[i + 2]
            son = i + 3 + ln + 3
            if len(self.b) < son:
                del self.b[:i]
                return out
            cerceve = bytes(self.b[i:son])
            if self.crc_denetle:
                bekle = (cerceve[-3] << 16) | (cerceve[-2] << 8) | cerceve[-1]
                if crc24q(cerceve[:-3]) != bekle:
                    # Bozuk cerceve: TEK bayt ilerle, senkron kaymis olabilir.
                    self.crc_hatasi += 1
                    del self.b[:i + 1]
                    continue
            self.gecerli += 1
            out.append(cerceve[3:3 + ln])
            del self.b[:son]


def coz_1005(govde: bytes):
    """RTCM 1005/1006 govdesini coz.

    Returns:
        (tip, istasyon_no, lat, lon, alt) ya da govde 1005/1006 degilse None.
    """
    if len(govde) < 19:
        return None
    tip = (govde[0] << 4) | (govde[1] >> 4)
    if tip not in (1005, 1006):
        return None
    b = Bit(govde)
    b.u(12)                       # mesaj no
    ref = b.u(12)                 # istasyon no
    b.u(6); b.u(1); b.u(1); b.u(1); b.u(1)   # ITRF + GPS/GLO/GAL + ref gost.
    x = b.s(38) * 1e-4            # ECEF-X, 0.1 mm
    b.u(1); b.u(1)                # tek alici osilatoru + rezerv
    y = b.s(38) * 1e-4
    b.u(2)                        # ceyrek cevrim
    z = b.s(38) * 1e-4
    lat, lon, alt = ecef_to_lla(x, y, z)
    return tip, ref, lat, lon, alt


def paketle_1005(lat, lon, alt, istasyon=0) -> bytes:
    """Verilen konumdan gecerli bir RTCM 1005 CERCEVESI uretir.

    YALNIZ TEST ICIN — baz olmadan cozucuyu dogrulamak icin var. Gercek
    akista bunu kimse cagirmaz.
    """
    x, y, z = lla_to_ecef(lat, lon, alt)
    bitler = []

    def yaz(deger, n, isaretli=False):
        if isaretli and deger < 0:
            deger += (1 << n)
        for k in range(n - 1, -1, -1):
            bitler.append((deger >> k) & 1)

    yaz(1005, 12); yaz(istasyon, 12); yaz(0, 6)
    yaz(1, 1); yaz(0, 1); yaz(0, 1); yaz(0, 1)
    yaz(round(x * 10000), 38, True); yaz(0, 1); yaz(0, 1)
    yaz(round(y * 10000), 38, True); yaz(0, 2)
    yaz(round(z * 10000), 38, True)
    while len(bitler) % 8:
        bitler.append(0)
    govde = bytearray()
    for k in range(0, len(bitler), 8):
        bayt = 0
        for bit in bitler[k:k + 8]:
            bayt = (bayt << 1) | bit
        govde.append(bayt)
    basli = bytes([0xD3, (len(govde) >> 8) & 0x03, len(govde) & 0xFF]) + bytes(govde)
    c = crc24q(basli)
    return basli + bytes([(c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF])
