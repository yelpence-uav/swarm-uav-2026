#!/usr/bin/env python3
# =============================================================================
# KAÇINMA UÇUŞ TESTİ — ylp00 tek noktada asılı dursun, sen ylp01 ile yaklaş.
#
# NE YAPAR
#   1. ylp00'ı arm edip hedef irtifaya kaldırır
#   2. BULUNDUĞU NOKTAYA goto gönderir ve bunu sürekli tazeler
#   3. Ekrana şunu basar: söylenen nokta / gerçek konum / aradaki sapma /
#      APF formülünün öngördüğü itme / komşu mesafesi
#
# NEDEN goto GÖNDERİYORUZ, SADECE KALKIŞ YETMİYOR
# Kaçınma düğümü zincirde `esp32_bridge → kaçınma → px4_bridge` yerinde
# duruyor ve yalnız AgentSetpoint akarsa çalışır. Kalkış-tutma px4_bridge'in
# KENDİ iç mantığı; o yolda setpoint akmaz, kaçınma devre dışı kalır ve
# test hiçbir şey göstermez.
#
# SONUÇ NASIL OKUNUR
#   sapma ≈ beklenen itme   -> kaçınma ÇALIŞIYOR
#   sapma ≈ 0, itme > 0     -> kaçınma hesaplıyor ama uçağa GEÇMİYOR
#   itme = 0                -> komşu henüz etki alanı dışında (d0)
#
# GÜVENLİK
# * Bu test DİKEY AYRIMLA yapılır: ylp00 yukarıda, sen aşağıda. Kaçınma
#   yatay mesafeye baktığı için sonuç aynı irtifadakiyle BİREBİR aynıdır,
#   ama çarpışma fiziksel olarak imkânsız.
# * Ctrl-C her an iniş gönderir. Disarm ASLA gönderilmez.
# * Hedef, uçağın ÖLÇÜLEN konumudur; sabit bir koordinat değil.
#
# Kullanım:
#     python3 kacinma_testi.py                 # ylp00 15 m'de assın
#     python3 kacinma_testi.py --irtifa 12
# =============================================================================

import argparse
import json
import math
import signal
import sys
import time
import urllib.error
import urllib.request

YKI = "http://localhost:8000"
OTONOM = 1          # ylp00 — asılı duracak olan
KOMSU = 2           # ylp01 — kumandayla yaklaşacağın

# basit_kacinma_node.py ile AYNI değerler olmalı; buradaki hesap yalnızca
# "ne bekliyoruz" sütununu üretmek için, uçağa komut vermiyor.
D0 = 8.0
HARD = 4.0
F_SAT = 4.0
MAX_ITME = 6.0

ARM_ASIM_S = 10
KALKIS_ASIM_S = 60
TAZELE_S = 2.0      # goto'yu bu sıklıkta tekrarla (setpoint bayatlamasın)

# DURDURMA DOSYASI — her koşulda çalışan iptal.
# NEDEN VAR: test arka planda (operatörün terminaline bağlı olmadan)
# başlatılabiliyor. O durumda Ctrl-C sürece HİÇ ULAŞMIYOR. 31 Temmuz gecesi
# tam bu yaşandı: operatör Ctrl-C'ye bastı, hiçbir şey olmadı, uçağı
# indirmek için kumandaya müdahale etmek zorunda kaldı. Güvendiği iptal
# yolunun çalışmaması, hiç olmamasından kötüdür.
DUR_DOSYASI = "/tmp/kacinma_dur"

_iniyor = False


def _istek(yol, yontem="POST", govde=None):
    veri, bas = None, {}
    if govde is not None:
        veri = json.dumps(govde).encode()
        bas["Content-Type"] = "application/json"
    r = urllib.request.Request(YKI + yol, data=veri, headers=bas, method=yontem)
    try:
        with urllib.request.urlopen(r, timeout=5) as c:
            return json.loads(c.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{yol} -> HTTP {e.code}: "
                           f"{e.read().decode(errors='replace')[:200]}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"{yol} -> YKİ yok ({e.reason})") from None


def durum():
    return {d["drone_id"]: d for d in _istek("/api/telemetry/snapshot", "GET")["drones"]}


def _smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def beklenen_itme(kendi, komsu):
    """basit_kacinma'nın uygulaması gereken itme — bağımsız hesap."""
    dk, dd = kendi[0] - komsu[0], kendi[1] - komsu[1]
    d = math.hypot(dk, dd)
    if d >= D0 or d < 1e-6:
        return (0.0, 0.0), d
    b = F_SAT if d <= HARD else F_SAT * _smoothstep((D0 - d) / (D0 - HARD))
    it = (b * dk / d, b * dd / d)
    buy = math.hypot(*it)
    if buy > MAX_ITME:
        it = (it[0] * MAX_ITME / buy, it[1] * MAX_ITME / buy)
    return it, d


def indir():
    global _iniyor
    if _iniyor:
        return
    _iniyor = True
    print("\n>>> İNİŞ — motor kesme YOK")
    try:
        _istek(f"/api/guided/{OTONOM}/land")
        print(f"    drone {OTONOM}: land gönderildi")
    except Exception as e:
        print(f"    land GÖNDERİLEMEDİ: {e}")


def main():
    ap = argparse.ArgumentParser(description="Çarpışma kaçınması uçuş testi")
    ap.add_argument("--irtifa", type=float, default=15.0)
    a = ap.parse_args()

    signal.signal(signal.SIGINT, lambda *_: (indir(), sys.exit(130)))
    signal.signal(signal.SIGTERM, lambda *_: (indir(), sys.exit(143)))

    print("=" * 72)
    print(f"  KAÇINMA TESTİ — drone {OTONOM} {a.irtifa:.0f} m'de asılı duracak")
    print(f"  Sen drone {KOMSU} ile DAHA ALÇAKTAN yaklaş.")
    print(f"  DURDURMAK İÇİN:  touch {DUR_DOSYASI}   (ya da Ctrl-C)")
    print("=" * 72)

    t = durum()
    for did in (OTONOM, KOMSU):
        d = t.get(did)
        if d is None or not d["connected"]:
            print(f"  drone {did}: BAĞLI DEĞİL — test başlatılmıyor")
            return 1
        print(f"  drone {did}: fix={d['gps_fix_type']} pil={d['battery_percent']:.0f}% "
              f"armed={d['armed']}")
    if t[OTONOM]["armed"]:
        print(f"  drone {OTONOM} ZATEN ARMED — önce disarm et")
        return 1

    # --- arm + kalkış ------------------------------------------------------
    print(f"\n=== ARM + KALKIŞ {a.irtifa:.0f} m ===")
    _istek(f"/api/guided/{OTONOM}/arm")
    t0 = time.time()
    while time.time() - t0 < ARM_ASIM_S:
        time.sleep(0.5)
        if durum().get(OTONOM, {}).get("armed"):
            print(f"    arm teyit ({time.time()-t0:.1f}s)")
            break
    else:
        print("    ARM EDİLEMEDİ")
        return 1

    _istek(f"/api/guided/{OTONOM}/takeoff?altitude={a.irtifa}")
    t0 = time.time()
    while time.time() - t0 < KALKIS_ASIM_S:
        time.sleep(1.0)
        alt = durum().get(OTONOM, {}).get("alt_m", 0.0)
        if alt >= a.irtifa * 0.9:
            print(f"    irtifa tamam: {alt:.1f} m")
            break
        print(f"    ... {alt:.1f} m", end="\r")
    else:
        print("\n    KALKIŞ ZAMAN AŞIMI")
        indir()
        return 1

    # --- asılı durma noktası ----------------------------------------------
    t = durum()
    hedef = (t[OTONOM]["pos_x"], t[OTONOM]["pos_y"])
    print(f"\n=== ASILI DURMA NOKTASI: ({hedef[0]:+.2f}, {hedef[1]:+.2f}) "
          f"irtifa {a.irtifa:.0f} m ===")
    print("    Bu nokta SABİT. Kaçınma çalışıyorsa uçak burada DURMAYACAK.\n")
    print(f"    {'komşu':>7} {'beklenen itme':>16} {'gerçek sapma':>16}  hüküm")
    print("    " + "-" * 62)

    import os
    if os.path.exists(DUR_DOSYASI):
        os.remove(DUR_DOSYASI)      # eski dosya kalmışsa temizle

    son_goto = 0.0
    while True:
        if os.path.exists(DUR_DOSYASI):
            print(f"\n    DURDURMA DOSYASI görüldü ({DUR_DOSYASI}) — iniliyor")
            os.remove(DUR_DOSYASI)
            indir()
            return 0
        # goto'yu tazele: setpoint bayatlarsa kaçınma zinciri boşa döner
        if time.time() - son_goto >= TAZELE_S:
            try:
                _istek(f"/api/guided/{OTONOM}/goto",
                       govde={"x": hedef[0], "y": hedef[1], "z": a.irtifa})
            except Exception as e:
                print(f"    goto gönderilemedi: {e}")
            son_goto = time.time()

        time.sleep(0.5)
        t = durum()
        o, k = t.get(OTONOM), t.get(KOMSU)
        if o is None or k is None:
            continue

        # PİLOT DEVRALDI MI — flight_mode 4 = OFFBOARD
        if o.get("flight_mode") != 4:
            print(f"\n    !!! drone {OTONOM} OFFBOARD'DAN ÇIKTI "
                  f"(mod={o.get('mode')}) — test durduruluyor")
            indir()
            return 1

        gercek = (o["pos_x"], o["pos_y"])
        komsu = (k["pos_x"], k["pos_y"])
        it, mesafe = beklenen_itme(gercek, komsu)
        sapma = (gercek[0] - hedef[0], gercek[1] - hedef[1])
        b_buy, s_buy = math.hypot(*it), math.hypot(*sapma)

        if b_buy < 0.1:
            hukum = "komşu uzak (d0 dışı)"
        elif s_buy > 0.5 * b_buy:
            hukum = "KAÇINMA ÇALIŞIYOR"
        elif s_buy < 0.3:
            hukum = "itme var ama uçak KIMILDAMIYOR"
        else:
            hukum = "kısmi — uçak henüz yolda"

        # HER SATIR AYRI YAZILIR (\r ile ustune yazilmaz): test arka planda
        # kosarken log tek satira biner ve ilerleme okunamaz.
        print(f"    {mesafe:6.1f}m {b_buy:9.2f}m {'':4} {s_buy:9.2f}m {'':4}  {hukum}",
              flush=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\nHATA: {e}")
        indir()
        sys.exit(1)
