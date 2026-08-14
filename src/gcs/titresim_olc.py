#!/usr/bin/env python3
# =============================================================================
# TITRESIM / EKF KARARLILIK OLCUMU — "kalkarken neden devrildi" sorusunun testi.
#
# NEDEN VAR (1 Agustos 03:13, ylp00)
# Ucak kalkista yerden kesilemedi, yerde kaydi, devrildi ve pervaneleri
# kirildi. Loglar sunu gosterdi:
#
#   BASARILI kalkislar   capa (2.27,-13.43) -> (2.27,-13.44)   oynama 0.01 m
#   DEVRILEN kalkis      capa (5.51,  3.32) -> (6.04,  2.69)   oynama 0.90 m
#
# Ilk 0.3 saniyede capa 0.34 m sicradi. Yerde duran ucak 0.3 sn'de 34 cm
# gidemez — bu ucagin hareketi degil, KONUM KESTIRIMININ sicramasi. Ayrica
# on kontrolde (DISARM) (5.29,4.74) okunmustu, kalkis aninda (5.51,3.32):
# ucak hic kimildamadan 1.42 m kaymis. Kayma ARM ile KALKIS ARASINDA, yani
# motorlar dondugu anda oldu.
#
# OFFBOARD kalkista bu olumcul: kalkisi PX4'un AUTO.TAKEOFF'u degil OFFBOARD
# konum setpoint'i yapiyor, yani ucak daha YERDEYKEN PX4 yatay konum tutmaya
# calisiyor. Kestirim 1 m sicrayinca PX4 "yanlis yerdeyim" deyip duzeltmek
# icin EGILIYOR; egilince itki dusey bilesenini kaybediyor (kalkamiyor),
# pervane yere vuruyor ve ucak devriliyor.
#
# DISARM halde konum 2 cm'de duruyor (olculdu) — sorun kestirimin kendisinde
# degil, motorlar donerken ortaya cikiyor. Bu arac tam o gecisi olcer.
#
# NASIL KULLANILIR — GUVENLI, KALKIS YOK
#   1. Kumandayi STABILIZED moduna al (konum tutma YOK; PX4 kendi kendine
#      duzeltmeye calismaz, dolayisiyla kacak dongu olusamaz)
#   2. Bu araci baslat
#   3. Arm et, gazi YAVASCA kaldir ama UCAGI KALDIRMA (kalkis esiginin
#      hemen altinda tut, ~5 sn)
#   4. Gazi kes, disarm et
#
# Arac sunlari raporlar:
#   * titresim x/y/z          — PX4'un kendi olcumu (m/s^2)
#   * clipping sayaci         — ivmeolcer DOYDU MU (en kotu isaret)
#   * konum sicramasi         — ardisik ornekler arasi en buyuk kayma
#
# OKUMA
#   sicrama < 0.10 m   -> kestirim saglam, devrilmenin sebebi bu degil
#   sicrama > 0.25 m   -> OFFBOARD kalkis bu ucakta guvenli degil; once
#                         titresim cozulmeli (pervane balansi, motor
#                         yataklari, FC montaj kopugu, gevsek kol)
#   clipping artiyorsa -> ivmeolcer doyuyor; EKF'e giren veri zaten bozuk
#
# Kullanim:
#     python3 titresim_olc.py            # ylp00
#     python3 titresim_olc.py ylp01 --sure 45
# =============================================================================

import argparse
import json
import math
import re
import subprocess
import sys
import threading
import time
import urllib.request

YKI = "http://localhost:8000"

# ad -> (ssh kullanici, ip, konteyner, agent_id)
DRONELAR = {
    "ylp00": ("yelpence00", "10.158.16.134", "drone1", 1),
    "ylp01": ("yelpence01", "10.158.16.211", "drone2", 2),
    "ylp02": ("yelpence02", "10.158.16.189", "drone3", 3),
}

ESIK_SICRAMA_M = 0.25       # bunun ustunde OFFBOARD kalkis guvenli degil
ESIK_UYARI_M = 0.10
ESIK_TITRESIM = 30.0        # PX4 rehberi: >30 m/s^2 kotu, >60 kabul edilemez


def _titresim_topla(kul, ip, kap, aid, sure, cikti):
    """Drone'da `ros2 topic echo` calistirip titresim satirlarini toplar."""
    ic = ("source /opt/ros/jazzy/setup.bash; source /ws/install/setup.bash; "
          "export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp "
          f"ROS_LOCALHOST_ONLY=1; timeout {sure + 5} ros2 topic echo "
          f"/drone_{aid}/mavros/vibration/raw/vibration 2>/dev/null")
    try:
        r = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", f"{kul}@{ip}",
             "docker exec %s bash -lc '%s'" % (kap, ic.replace("'", "'\\''"))],
            capture_output=True, text=True, timeout=sure + 25)
        cikti.append(r.stdout)
    except subprocess.TimeoutExpired:
        cikti.append("")


def _coz(ham):
    """echo ciktisindan (zaman, titresim_xyz, clipping) kayitlarini cikarir."""
    kayitlar = []
    for blok in ham.split("---"):
        t = re.search(r"sec:\s*(\d+)", blok)
        v = re.search(r"vibration:\s*\n\s*x:\s*([-\d.e+]+)\s*\n\s*y:\s*([-\d.e+]+)"
                      r"\s*\n\s*z:\s*([-\d.e+]+)", blok)
        c = re.search(r"clipping:\s*\n-\s*([\d.e+]+)\s*\n-\s*([\d.e+]+)\s*\n-\s*([\d.e+]+)",
                      blok)
        if v and c:
            kayitlar.append((
                float(t.group(1)) if t else 0.0,
                tuple(float(v.group(i)) for i in (1, 2, 3)),
                tuple(float(c.group(i)) for i in (1, 2, 3)),
            ))
    return kayitlar


def _zaman_serisi_yaz(kayitlar):
    """Saniye saniye titresim/doyma — hangi anda ne oldugunu gormek icin.

    NEDEN: ozet "80 doyma oldu" der ama NEREDE oldugunu soylemez. QGC'nin
    Motor Test'iyle motorlar TEK TEK dondurulunce bu seri hangi motorun
    titresimi urettigini dogrudan gosterir — arizali motoru tahminle degil
    olcumle bulmanin yolu bu.
    """
    if len(kayitlar) < 2:
        return
    print("\n=== ZAMAN SERİSİ (saniye saniye) ===")
    print("  sn   titreşim z      yeni doyma   çubuk")
    t0 = kayitlar[0][0]
    onceki_clip = kayitlar[0][2][0]
    kova: dict = {}
    for t, v, c in kayitlar:
        kova.setdefault(int(t - t0), []).append((abs(v[2]), c[0]))
    for sn in sorted(kova):
        zler = [x[0] for x in kova[sn]]
        son_clip = kova[sn][-1][1]
        yeni = son_clip - onceki_clip
        onceki_clip = son_clip
        tepe = max(zler)
        cubuk = "#" * min(40, int(tepe / 1.5))
        isaret = f"  +{yeni:.0f}" if yeni > 0 else "    ."
        print(f"  {sn:3d}  {tepe:7.2f} m/s²  {isaret:>10}   {cubuk}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Titresim / EKF kararlilik olcumu")
    ap.add_argument("drone", nargs="?", default="ylp00", choices=list(DRONELAR))
    ap.add_argument("--sure", type=float, default=40.0, help="olcum suresi (sn)")
    a = ap.parse_args()
    kul, ip, kap, aid = DRONELAR[a.drone]

    print("=" * 74)
    print(f"  TİTREŞİM / EKF KARARLILIK — {a.drone} (drone_{aid})")
    print("=" * 74)
    print("  GÜVENLİ TEST — UÇURMA:")
    print("    1. Kumandayı STABILIZED moduna al")
    print("    2. Arm et")
    print("    3. Gazı YAVAŞÇA kaldır, uçağı KALDIRMA (kalkış eşiğinin altında tut)")
    print("    4. ~5 sn tut, gazı kes, disarm et")
    print("")
    print("  HANGİ MOTOR olduğunu bulmak istersen bunun yerine:")
    print("    QGC > Vehicle Setup > Motors > her motoru TEK TEK ~5 sn döndür")
    print("    (1, bekle, 2, bekle, 3, bekle, 4). Zaman serisi hangisinin")
    print("    titrettiğini gösterir.")
    print(f"  Ölçüm {a.sure:.0f} sn sürecek. Başlıyor...\n")

    ham = []
    ip_thread = threading.Thread(target=_titresim_topla,
                                 args=(kul, ip, kap, aid, a.sure, ham))
    ip_thread.start()

    konum, armed_gorulen = [], []
    t0 = time.time()
    while time.time() - t0 < a.sure:
        try:
            s = json.load(urllib.request.urlopen(
                f"{YKI}/api/telemetry/snapshot", timeout=3))
            d = next((x for x in s["drones"] if x["drone_id"] == aid), None)
            if d:
                konum.append((time.time() - t0, d["pos_x"], d["pos_y"], d["armed"]))
                if d["armed"]:
                    armed_gorulen.append(time.time() - t0)
        except Exception:
            pass
        time.sleep(0.4)
        gecen = time.time() - t0
        print(f"    {gecen:4.0f}/{a.sure:.0f} sn   "
              f"armed={konum[-1][3] if konum else '?'}   "
              f"örnek={len(konum)}", end="\r")

    ip_thread.join()
    print("\n")

    # --- konum kararliligi -------------------------------------------------
    def sicrama(kesit):
        return max((math.dist(kesit[i][1:3], kesit[i - 1][1:3])
                    for i in range(1, len(kesit))), default=0.0)

    yerde = [k for k in konum if not k[3]]
    donerken = [k for k in konum if k[3]]

    print("=== KONUM KESTİRİMİ ===")
    print(f"  {'durum':<22} {'örnek':>6} {'en büyük sıçrama':>18}")
    for ad, kesit in (("DISARM (motorlar dur)", yerde),
                      ("ARMED (motorlar döner)", donerken)):
        if len(kesit) < 3:
            print(f"  {ad:<22} {len(kesit):>6}   (yeterli örnek yok)")
            continue
        s = sicrama(kesit)
        hukum = ("SAĞLAM" if s < ESIK_UYARI_M else
                 "SINIRDA" if s < ESIK_SICRAMA_M else "OYNAK — KALKIŞTA DEVİRİR")
        print(f"  {ad:<22} {len(kesit):>6} {s:>15.3f} m   {hukum}")

    if not donerken:
        print("\n  !! Uçak hiç ARM edilmedi — asıl ölçüm yapılamadı.")
        print("     Kumandadan arm edip gazı kalkış eşiğinin altında tutmalısın.")

    # --- titresim ----------------------------------------------------------
    kayitlar = _coz("".join(ham))
    print("\n=== TİTREŞİM (PX4 kendi ölçümü) ===")
    if not kayitlar:
        print("  okunamadı (topic akmıyor olabilir)")
    else:
        eks = list(zip(*[k[1] for k in kayitlar]))
        for ad, seri in zip("xyz", eks):
            tepe = max(abs(v) for v in seri)
            hukum = "iyi" if tepe < ESIK_TITRESIM else "YÜKSEK"
            print(f"  {ad}: tepe {tepe:7.2f} m/s²   ort {sum(map(abs, seri))/len(seri):6.2f}"
                  f"   {hukum}  (eşik {ESIK_TITRESIM:.0f})")
        ilk, son = kayitlar[0][2], kayitlar[-1][2]
        artis = [son[i] - ilk[i] for i in range(3)]
        print(f"  clipping (ivmeölçer doyması): {ilk} -> {son}")
        if any(x > 0 for x in artis):
            print(f"  !! ÖLÇÜM SIRASINDA {artis} YENİ DOYMA — ivmeölçer saturasyona "
                  "giriyor, EKF'e giren veri zaten bozuk.")
        else:
            print("  ölçüm sırasında yeni doyma YOK")
        _zaman_serisi_yaz(kayitlar)

    print("\n" + "=" * 74)
    print("  Sıçrama > 0.25 m ise bu uçakta OFFBOARD kalkış güvenli değil:")
    print("  önce titreşim çözülmeli (pervane balansı, motor yatağı,")
    print("  FC montaj köpüğü, gevşek kol/gövde).")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
