#!/usr/bin/env python3
# =============================================================================
# ON UCUS KONTROLU — ucmadan once her seyi tek komutta olcer.
#
# NEDEN VAR: 31 Temmuz'da tek bir aksamda saatler kaybedildi cunku "neyin
# calistigi" her seferinde elle ve dagink sekilde olculuyordu. Ayrica bazi
# arizalar SESSIZ: MAVROS'un tgt_system'i FCU ile uyusmazsa paketler akmaya
# devam eder ama icerik bosalir; RTCM okuyucusu hic baslamamis olabilir;
# pusula 3 kat sapmis okuyabilir. Hicbiri "hata" diye kendini gostermez.
#
# Her satirin yaninda GECER/KALIR hukmu ve esigi var. Kirmizi bir satir
# varken ucma.
#
# Kullanim:
#     python3 on_ucus_kontrol.py            # varsayilan: ylp00 + ylp01
#     python3 on_ucus_kontrol.py ylp00 ylp02
# =============================================================================

import argparse
import json
import math
import re
import subprocess
import sys
import urllib.request

YKI = "http://localhost:8000"

# ad -> (ssh kullanici, ip, konteyner, agent_id, beklenen MAV_SYS_ID)
DRONELAR = {
    "ylp00": ("yelpence00", "10.158.16.134", "drone1", 1, 1),
    "ylp01": ("yelpence01", "10.158.16.211", "drone2", 2, 2),
    "ylp02": ("yelpence02", "10.158.16.189", "drone3", 3, 3),
}

# Beklenen ucus parametreleri — ikisinde de AYNI olmali, yoksa formasyon
# sessizce ayrisir (biri digerinden hizli gider).
BEKLENEN = {
    "MPC_XY_VEL_MAX": 2.0,
    "MPC_XY_CRUISE": 2.0,
    "MPC_YAWRAUTO_MAX": 25.0,
    "MPC_TILTMAX_AIR": 30.0,
    "MPC_ACC_HOR": 2.0,
    "BAT1_SOURCE": 0,
}

ESIK_HACC_M = 1.0        # bunun ustunde ucma (RTK varken 0.02 bekleriz)
ESIK_UYDU = 12
ESIK_PIL_YUZDE = 40.0
ESIK_MAG_UT = (45.0, 55.0)
ESIK_MAG_STD = 3.0

_gecti = 0
_kaldi = 0


def hh(ad: str, deger: str, ok: bool, not_: str = "") -> None:
    global _gecti, _kaldi
    if ok:
        _gecti += 1
    else:
        _kaldi += 1
    isaret = "  OK " if ok else "  !! "
    print(f"{isaret}{ad:<26} {deger:<28} {not_}")


def _uzak(kul, ip, kap, komut, zaman=30):
    ic = ("source /opt/ros/jazzy/setup.bash; source /ws/install/setup.bash; "
          "export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp "
          "ROS_LOCALHOST_ONLY=1; " + komut)
    try:
        r = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", f"{kul}@{ip}",
             "docker exec %s bash -lc '%s'" % (kap, ic.replace("'", "'\\''"))],
            capture_output=True, text=True, timeout=zaman)
        return r.stdout
    except subprocess.TimeoutExpired:
        return ""


def param(kul, ip, kap, aid, adlar):
    """Birden cok PX4 parametresini tek SSH ile ceker."""
    komut = "; ".join(
        f'echo -n "{a}="; timeout 6 ros2 param get /drone_{aid}/mavros/param {a} '
        f'2>/dev/null | tail -1 | sed "s/.*is: //"' for a in adlar)
    cikti = _uzak(kul, ip, kap, komut, zaman=20 + 6 * len(adlar))
    sonuc = {}
    for satir in cikti.splitlines():
        if "=" in satir:
            k, _, v = satir.partition("=")
            sonuc[k.strip()] = v.strip()
    return sonuc


def yki_kontrol():
    print("\n=== YER İSTASYONU ===")
    try:
        snap = json.load(urllib.request.urlopen(f"{YKI}/api/telemetry/snapshot", timeout=5))
    except Exception as e:
        hh("YKİ backend", "ULAŞILAMIYOR", False, str(e)[:40])
        return None
    hh("YKİ backend", "ayakta", True)
    rtk = snap.get("rtk") or {}
    hh("RTCM akışı", f"{rtk.get('msg_hz', 0)} Hz, {rtk.get('bayt_s', 0)} B/s",
       bool(rtk.get("bagli")), "" if rtk.get("bagli") else "u-blox takılı mı?")
    return snap


def drone_kontrol(ad, snap):
    if ad not in DRONELAR:
        print(f"\n  bilinmeyen drone: {ad}")
        return
    kul, ip, kap, aid, beklenen_sys = DRONELAR[ad]
    print(f"\n=== {ad}  (drone_{aid}) ===")

    # --- mesh telemetrisi (YKİ'nin gördüğü) --------------------------------
    d = None
    if snap:
        d = next((x for x in snap.get("drones", []) if x["drone_id"] == aid), None)
    if d is None or not d.get("connected"):
        hh("mesh telemetrisi", "BAĞLI DEĞİL", False, "ESP mesh / base köprü?")
    else:
        hh("mesh telemetrisi", f"bağlı, mod={d['mode']}", True)
        hh("pil", f"{d['battery_percent']:.0f}%  {d['battery_voltage']:.1f} V",
           d["battery_percent"] >= ESIK_PIL_YUZDE,
           f"eşik %{ESIK_PIL_YUZDE:.0f}")
        hh("armed", str(d["armed"]), not d["armed"], "uçuş öncesi disarm olmalı")

    # --- MAVROS / FCU ------------------------------------------------------
    st = _uzak(kul, ip, kap,
               f"timeout 6 ros2 topic echo /drone_{aid}/mavros/state --once 2>/dev/null")
    bagli = "connected: true" in st
    hh("MAVROS ↔ FCU", "connected" if bagli else "KOPUK", bagli,
       "" if bagli else "tgt_system FCU ile uyuşuyor mu?")

    # --- GPS ---------------------------------------------------------------
    g = _uzak(kul, ip, kap,
              f"timeout 8 ros2 topic echo /drone_{aid}/mavros/gpsstatus/gps1/raw "
              "--once 2>/dev/null")
    fix = re.search(r"fix_type:\s*(\d+)", g)
    hacc = re.search(r"h_acc:\s*(\d+)", g)
    sat = re.search(r"satellites_visible:\s*(\d+)", g)
    if fix:
        f = int(fix.group(1))
        adi = {0: "yok", 1: "fixsiz", 2: "2D", 3: "3D", 4: "DGPS",
               5: "RTK-Float", 6: "RTK-FIX"}.get(f, str(f))
        hh("GPS fix", f"{adi} ({f})", f >= 3)
    if hacc:
        h = int(hacc.group(1)) / 1000.0
        hh("konum doğruluğu", f"{h:.3f} m", h <= ESIK_HACC_M, f"eşik {ESIK_HACC_M} m")
    if sat:
        s = int(sat.group(1))
        hh("uydu", str(s), s >= ESIK_UYDU, f"eşik {ESIK_UYDU}")

    # --- pusula ------------------------------------------------------------
    m = _uzak(kul, ip, kap,
              f"timeout 10 ros2 topic echo /drone_{aid}/mavros/imu/mag 2>/dev/null", 30)
    b = re.findall(r"magnetic_field:\s*\n\s*x:\s*([-\d.e+]+)\s*\n\s*y:\s*([-\d.e+]+)"
                   r"\s*\n\s*z:\s*([-\d.e+]+)", m)
    if b:
        v = [math.sqrt(float(x)**2 + float(y)**2 + float(z)**2) * 1e6 for x, y, z in b]
        o = sum(v) / len(v)
        sd = (sum((k - o)**2 for k in v) / len(v)) ** 0.5
        hh("pusula |B|", f"{o:.1f} µT", ESIK_MAG_UT[0] <= o <= ESIK_MAG_UT[1],
           f"beklenen {ESIK_MAG_UT[0]:.0f}-{ESIK_MAG_UT[1]:.0f}")
        hh("pusula girişim", f"std {sd:.2f} µT", sd <= ESIK_MAG_STD,
           f"eşik {ESIK_MAG_STD:.0f} — üstü girişim")
    else:
        hh("pusula", "ÖLÇÜLEMEDİ", False)

    # --- parametreler ------------------------------------------------------
    p = param(kul, ip, kap, aid, list(BEKLENEN) + ["MAV_SYS_ID"])
    for k, bek in BEKLENEN.items():
        ham = p.get(k, "")
        try:
            deg = float(ham)
            ok = abs(deg - float(bek)) < 0.01
            hh(k, f"{deg:g}", ok, f"beklenen {bek}")
        except ValueError:
            hh(k, ham or "OKUNAMADI", False, f"beklenen {bek}")
    ham = p.get("MAV_SYS_ID", "")
    try:
        ok = int(float(ham)) == beklenen_sys
        hh("MAV_SYS_ID", ham, ok, f"beklenen {beklenen_sys} (QGC ayrımı)")
    except ValueError:
        hh("MAV_SYS_ID", ham or "OKUNAMADI", False)


def main() -> int:
    ap = argparse.ArgumentParser(description="Uçuş öncesi tam kontrol")
    ap.add_argument("dronelar", nargs="*", default=["ylp00", "ylp01"])
    a = ap.parse_args()

    print("=" * 78)
    print("  UÇUŞ ÖNCESİ KONTROL")
    print("=" * 78)
    snap = yki_kontrol()
    for ad in a.dronelar:
        drone_kontrol(ad, snap)

    print("\n" + "=" * 78)
    print(f"  GEÇEN: {_gecti}    KALAN: {_kaldi}")
    if _kaldi:
        print("  !! Kırmızı satır varken UÇMA.")
    else:
        print("  Bütün kontroller geçti.")
    print("=" * 78)
    return 1 if _kaldi else 0


if __name__ == "__main__":
    sys.exit(main())
