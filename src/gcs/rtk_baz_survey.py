#!/usr/bin/env python3
# =============================================================================
# RTK BAZINI SURVEY-IN'E AL — u-blox F9P, seri porttan UBX-CFG-VALSET.
#
# NEDEN VAR (2 Agustos, okul sahasi): baz alici FIXED BASE modundaydi ve
# flash'inda EVDE yapilmis survey'in koordinati yaziliydi. Sahaya gelince
# yeniden olcmedi, o eski koordinati yayinlamaya devam etti. RTCM 1005'in
# icini acinca goruldu: baz kendini ucaklardan 2820 m otede sanIyordu.
# Rover BURADA alinan gozlemleri ORADAKI bir baz koordinatiyla eslestirmeye
# calisiyor, baz cizgisi anlamsiz cikiyor ve cozum ASLA oturmuyor —
# dronelar sonsuza kadar DGPS'te kaliyor. "Biraz daha bekleyelim" ise
# yaramaz; teshis 1005'i cozmekten geciyor (--oku ile bakilir).
#
# ANTENI HER TASIDIGINDA BUNU KOSTUR. Survey bir kez oturduktan sonra alici
# o koordinati KULLANMAYA devam eder; anten tasinsa bile kendiliginden
# yeniden olcmez.
#
# Kullanim:
#     # 1) RTCM okuyucusunu durdur (seri port tek sahipli):
#     pkill -f yki_rtcm_reader.py
#     # 2) survey-in'i basIat ve ilerlemeyi izle:
#     python3 src/gcs/rtk_baz_survey.py
#     # 3) YKI'yi yeniden basIat (okuyucuyu dogru ortamla o ayaga kaldirir):
#     ./src/gcs/yki_baslat.sh
#
#     python3 src/gcs/rtk_baz_survey.py --oku      # yalniz 1005'i coz ve bas
#     python3 src/gcs/rtk_baz_survey.py --sure 120 --dogruluk 1.5
#
# CFG-VALSET anahtarlari (F9P arayuz tanimi, anahtarin ust nibble'i boyut):
#     CFG-TMODE-MODE           0x20030001  U1  0=kapali 1=survey-in 2=sabit
#     CFG-TMODE-SVIN_MIN_DUR   0x40030010  U4  saniye
#     CFG-TMODE-SVIN_ACC_LIMIT 0x40030011  U4  0.1 mm birim
# =============================================================================

import argparse
import math
import pathlib
import struct
import sys
import time

import serial

# ORTAK MODUL — RTCM cerceve ayiklama, CRC24Q ve 1005 cozumu artik
# swarm_control/rtcm_1005.py'de. Bu dosyada YAZILDI ve sahada calisti;
# drone tarafi da ayni koda ihtiyac duyunca kopyalamak yerine oraya
# TASINDI (CLAUDE.md §9: ayni sabiti/mantigi iki yere yazma).
# Fark: ortak surumde CRC24Q dogrulamasi VAR — mesh'ten gelen bozuk
# cerceveler elensin diye.
sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parents[2] / 'src' / 'swarm_control'))
from swarm_control.rtcm_1005 import (          # noqa: E402
    AyiklaRTCM, coz_1005, uzaklik_m,
)

VARSAYILAN_PORT = "/dev/ttyACM0"
# RAM (0x01) + BBR (0x02) + Flash (0x04). Kalici olmasi sart: USB kopmasi
# 2 Agustos'ta yasandi ve her kopus aliciyi yeniden baslatiyor.
KATMAN = 0x07


def ubx(cls, mid, payload=b""):
    g = bytes([cls, mid]) + struct.pack("<H", len(payload)) + payload
    a = b = 0
    for x in g:
        a = (a + x) & 0xFF
        b = (b + a) & 0xFF
    return b"\xb5\x62" + g + bytes([a, b])


def valset(pairs):
    p = bytes([0x00, KATMAN, 0x00, 0x00])
    for key, val, boyut in pairs:
        p += struct.pack("<I", key) + val.to_bytes(boyut, "little")
    return ubx(0x06, 0x8A, p)


class Ayikla:
    """Akistan UBX cerceveleri ayikla; aradaki RTCM3'u atla."""

    def __init__(self):
        self.b = bytearray()

    def besle(self, veri):
        self.b += veri
        out = []
        while True:
            i = self.b.find(b"\xb5\x62")
            if i < 0:
                del self.b[:max(0, len(self.b) - 1)]
                return out
            if len(self.b) < i + 6:
                del self.b[:i]
                return out
            ln = struct.unpack("<H", self.b[i + 4:i + 6])[0]
            son = i + 6 + ln + 2
            if len(self.b) < son:
                del self.b[:i]
                return out
            out.append((self.b[i + 2], self.b[i + 3],
                        bytes(self.b[i + 6:i + 6 + ln])))
            del self.b[:son]


def baz_bas(gov, karsilastir=None):
    """RTCM 1005/1006 govdesinden baz koordinatini coz ve ekrana bas."""
    cozum = coz_1005(gov)
    if cozum is None:
        return False
    tip, ref, lat, lon, alt = cozum
    print(f"RTCM {tip} · istasyon {ref}")
    print(f"  BAZ KONUMU  lat={lat:.7f}  lon={lon:.7f}  elipsoit={alt:.2f} m")
    if karsilastir:
        d = uzaklik_m(lat, lon, karsilastir[0], karsilastir[1])
        print(f"  verilen noktaya uzaklik: {d:.1f} m"
              + ("   <-- BU YANLIS, baz orada degil!" if d > 50 else "   (makul)"))
    return True


def oku(s, karsilastir, saniye=30):
    """1005 gelene kadar dinle."""
    a = AyiklaRTCM()
    t0 = time.time()
    print("1005 (baz konumu) bekleniyor...", flush=True)
    while time.time() - t0 < saniye:
        for gov in a.besle(s.read(4096)):
            if baz_bas(gov, karsilastir):
                return 0
        time.sleep(0.05)
    print(f"!! {saniye} sn'de 1005 gelmedi — baz survey-in'de veya "
          "TMODE kapali olabilir")
    return 2


def survey(s, min_sure, acc_m):
    a = Ayikla()
    # ONCE KAPAT: survey bir kez oturunca alici o koordinati kullanmaya devam
    # eder. MODE 0 -> 1 gecisi olcumu sifirdan baslatir.
    print("TMODE kapatiliyor (survey sifirlanacak)...", flush=True)
    s.write(valset([(0x20030001, 0, 1)]))
    time.sleep(1.5)
    s.read(8192)

    acc10 = int(round(acc_m * 10000))
    print(f"CFG-VALSET (RAM+BBR+Flash · min {min_sure}s · sinir {acc_m:.1f} m)...",
          flush=True)
    s.write(valset([(0x20030001, 1, 1),
                    (0x40030010, int(min_sure), 4),
                    (0x40030011, acc10, 4)]))

    ack, t0 = None, time.time()
    while time.time() - t0 < 6:
        for cls, mid, _ in a.besle(s.read(4096)):
            if cls == 0x05 and mid in (0x00, 0x01):
                ack = (mid == 0x01)
        if ack is not None:
            break
    if ack is False:
        print("!! ACK-NAK — alici ayari REDDETTI")
        return 1
    print("ACK-ACK — kabul edildi" if ack else
          "!! ACK gelmedi, yine de ilerlemeye bakiliyor", flush=True)

    print("\nSURVEY-IN (dur = gecen sure, acc = ortalama dogruluk):", flush=True)
    son, t0 = "", time.time()
    while time.time() - t0 < 900:
        s.write(ubx(0x01, 0x3B))              # NAV-SVIN poll
        t1 = time.time()
        while time.time() - t1 < 1.5:
            for cls, mid, pl in a.besle(s.read(4096)):
                if cls != 0x01 or mid != 0x3B or len(pl) < 40:
                    continue
                dur, = struct.unpack("<I", pl[8:12])
                acc, = struct.unpack("<I", pl[28:32])
                obs, = struct.unpack("<I", pl[32:36])
                gecerli, aktif = pl[36], pl[37]
                sat = (f"  dur={dur:4d}s  acc={acc/10000:6.3f} m  "
                       f"obs={obs:6d}  aktif={aktif}  gecerli={gecerli}")
                if sat != son:
                    print(sat, flush=True)
                    son = sat
                if gecerli == 1:
                    print("\n>>> SURVEY-IN TAMAMLANDI — baz artik BURAYI "
                          "yayinliyor.\n    Simdi ./src/gcs/yki_baslat.sh "
                          "ile YKI'yi baslat.", flush=True)
                    return 0
        time.sleep(1.0)
    print("!! 15 dakikada oturmadi — anten gok gorusu kapali olabilir, "
          "ya da --dogruluk degerini buyut")
    return 2


def main():
    ap = argparse.ArgumentParser(
        description="u-blox RTK bazini survey-in'e al (anteni her tasidiginda)")
    ap.add_argument("--port", default=VARSAYILAN_PORT)
    ap.add_argument("--sure", type=int, default=60,
                    help="survey-in en az kac saniye surecek (varsayilan 60)")
    ap.add_argument("--dogruluk", type=float, default=2.0,
                    help="hedef ortalama dogruluk, metre (varsayilan 2.0)")
    ap.add_argument("--oku", action="store_true",
                    help="ayar YAPMA; yalniz RTCM 1005'i coz ve baz konumunu bas")
    ap.add_argument("--karsilastir", default=None, metavar="LAT,LON",
                    help="--oku ile: baz konumunu bu noktayla karsilastir "
                         "(or. dronelarin oldugu yer)")
    a = ap.parse_args()

    kar = None
    if a.karsilastir:
        try:
            la, _, lo = a.karsilastir.partition(",")
            kar = (float(la), float(lo))
        except ValueError:
            ap.error("--karsilastir 'LAT,LON' olmali")

    try:
        s = serial.Serial(a.port, 115200, timeout=0.2)
    except serial.SerialException as e:
        print(f"Port acilamadi ({a.port}): {e}\n"
              "RTCM okuyucusu calisiyor olabilir: pkill -f yki_rtcm_reader.py")
        return 1
    with s:
        return oku(s, kar) if a.oku else survey(s, a.sure, a.dogruluk)


if __name__ == "__main__":
    sys.exit(main())
