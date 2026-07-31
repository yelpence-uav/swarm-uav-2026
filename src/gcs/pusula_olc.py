#!/usr/bin/env python3
# =============================================================================
# PUSULA SAGLIK OLCUMU — manyetik girisimi SAYIYLA gosterir.
#
# NEDEN VAR (31 Temmuz)
# ylp02'de QGC "strong magnetic interference" verdi ve kalibrasyon
# "unable to fit mag 0" ile basarisiz oldu. Sebebi bulmak icin sirayla
# kamera guc kablosu ve ESP32 mesh yayini suclandi; IKISI DE ELENDI cunku
# olcum degismedi. Elle her seferinde ros2 topic echo cikti ayikladigimiz
# icin bu is uzun surdu — arac haline getiriliyor.
#
# NE OLCER
#   |B| ortalamasi : dunya alani bu enlemde ~48-52 uT olmali
#   |B| std        : ASIL TESHIS. Alan zamanla ne kadar oynuyor?
#   durus          : yaw/roll std — arac gercekten duruyor mu?
#
# ONEMLI AYRIM (bu olcumu anlamli kilan sey):
#   |B| donmekle DEGISMEZ, cunku vektor buyuklugu donmeye gore degismez.
#   * Arac DURUYOR ve |B| oynuyorsa  -> gercek, zamanla degisen GIRISIM.
#   * Arac HAREKET EDIYOR ve |B| oynuyorsa -> hard-iron kalibrasyonu bozuk
#     (sabit ofset donen vektore eklenince buyukluk oynar).
#   Bu ikisi ayirt edilmezse yanlis teshise gidilir; o yuzden durus da olculuyor.
#
# 31 Temmuz referans degerleri:
#   ylp00 (saglam) : |B| = 48.5 uT, std = 1.01
#   ylp02 (bozuk)  : |B| = 143.5 uT, std = 62.85, 63-260 uT arasi zipliyor
#
# Kullanim (dizustunden, drone'a SSH ile baglanir):
#     python3 pusula_olc.py ylp00
#     python3 pusula_olc.py ylp00 ylp01
#     python3 pusula_olc.py --sure 20 ylp01
# =============================================================================

import argparse
import math
import re
import subprocess
import sys

# docs/cihazlar.md ile ayni. ad -> (ssh kullanici, ip, konteyner, agent_id)
DRONELAR = {
    "ylp00": ("yelpence00", "10.158.16.134", "drone1", 1),
    "ylp01": ("yelpence01", "10.158.16.211", "drone2", 2),
    "ylp02": ("yelpence02", "10.158.16.189", "drone3", 3),
}

DUNYA_ALANI_UT = (45.0, 55.0)   # bu enlemde beklenen aralik
STD_ESIK_UT = 3.0               # bunun ustu girisim sayilir


def _uzak(kul: str, ip: str, kap: str, komut: str, zaman: int) -> str:
    """Konteyner icinde ROS komutu kosturur.

    CycloneDDS ortami VERILMEK ZORUNDA: verilmezse dugumler 'yok' gorunur
    ve bos cikti aliriz (31 Temmuz'da tam bu tuzaga dusuldu).
    """
    ic = ("source /opt/ros/jazzy/setup.bash; source /ws/install/setup.bash; "
          "export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp "
          "ROS_LOCALHOST_ONLY=1; " + komut)
    try:
        s = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", f"{kul}@{ip}",
             f"docker exec {kap} bash -lc {_tirnak(ic)}"],
            capture_output=True, text=True, timeout=zaman)
        return s.stdout
    except subprocess.TimeoutExpired:
        return ""


def _tirnak(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def _istatistik(v):
    ort = sum(v) / len(v)
    std = (sum((x - ort) ** 2 for x in v) / len(v)) ** 0.5
    return ort, std


def olc(ad: str, sure: int) -> None:
    if ad not in DRONELAR:
        print(f"  {ad}: bilinmeyen drone (tablo: {', '.join(DRONELAR)})")
        return
    kul, ip, kap, aid = DRONELAR[ad]
    print(f"\n=== {ad}  ({kul}@{ip} / {kap} / drone_{aid}) ===")

    mag = _uzak(kul, ip, kap,
                f"timeout {sure} ros2 topic echo /drone_{aid}/mavros/imu/mag 2>/dev/null",
                sure + 20)
    att = _uzak(kul, ip, kap,
                f"timeout {sure} ros2 topic echo /drone_{aid}/mavros/imu/data 2>/dev/null",
                sure + 20)

    b = re.findall(r"magnetic_field:\s*\n\s*x:\s*([-\d.e+]+)\s*\n\s*y:\s*([-\d.e+]+)"
                   r"\s*\n\s*z:\s*([-\d.e+]+)", mag)
    if not b:
        print("  manyetometre verisi YOK — MAVROS bagli mi? (connected: true?)")
        return

    buy = [math.sqrt(float(x) ** 2 + float(y) ** 2 + float(z) ** 2) * 1e6 for x, y, z in b]
    ort, std = _istatistik(buy)

    # Durus: arac gercekten duruyor mu? |B| yorumu buna bagli.
    q = re.findall(r"orientation:\s*\n\s*x:\s*([-\d.e+]+)\s*\n\s*y:\s*([-\d.e+]+)"
                   r"\s*\n\s*z:\s*([-\d.e+]+)\s*\n\s*w:\s*([-\d.e+]+)", att)
    duruyor = None
    if q:
        yaw = [math.degrees(math.atan2(2 * (float(w) * float(z) + float(x) * float(y)),
                                       1 - 2 * (float(y) ** 2 + float(z) ** 2)))
               for x, y, z, w in q]
        _, sy = _istatistik(yaw)
        duruyor = sy < 1.0
        print(f"  durus     : yaw std = {sy:.2f}°  -> {'DURUYOR' if duruyor else 'HAREKET EDIYOR'}")

    print(f"  |B|       : ort = {ort:.1f} uT   std = {std:.2f}   "
          f"(min {min(buy):.1f} / max {max(buy):.1f}, n={len(buy)})")

    # --- Hukum --------------------------------------------------------------
    sorun = []
    if not (DUNYA_ALANI_UT[0] <= ort <= DUNYA_ALANI_UT[1]):
        sorun.append(f"buyukluk beklenen {DUNYA_ALANI_UT[0]:.0f}-{DUNYA_ALANI_UT[1]:.0f} uT "
                     "araliginda DEGIL")
    if std > STD_ESIK_UT:
        if duruyor is False:
            sorun.append(f"std {std:.1f} uT yuksek AMA arac hareket ediyor -> once "
                         "hareketsiz tekrarla; oyleyse hard-iron kalibrasyonu bozuk demektir")
        else:
            sorun.append(f"std {std:.1f} uT (esik {STD_ESIK_UT:.0f}) — arac DURUYOR, "
                         "yani gercek zamanla-degisen GIRISIM")

    if sorun:
        print("  HUKUM     : SORUNLU")
        for s in sorun:
            print(f"              - {s}")
        print("              Kalibrasyon bunu COZMEZ: degisken alan her an baska,")
        print("              kalibrasyon yalniz SABIT ofseti soguruyor.")
    else:
        print("  HUKUM     : SAGLIKLI")


def main() -> int:
    ap = argparse.ArgumentParser(description="Pusula/manyetik girisim olcumu")
    ap.add_argument("dronelar", nargs="*", default=["ylp00"],
                    help="olculecek drone adlari (varsayilan: ylp00)")
    ap.add_argument("--sure", type=int, default=12, help="ornekleme suresi (sn)")
    a = ap.parse_args()

    print("=" * 66)
    print("  PUSULA SAGLIK OLCUMU")
    print(f"  referans — ylp00 saglam: 48.5 uT std 1.01 | ylp02 bozuk: 143.5 std 62.9")
    print("=" * 66)
    for ad in a.dronelar:
        olc(ad, a.sure)
    return 0


if __name__ == "__main__":
    sys.exit(main())
