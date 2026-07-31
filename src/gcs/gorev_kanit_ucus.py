#!/usr/bin/env python3
# =============================================================================
# KANIT UÇUŞU GÖREV KOŞUCUSU — iki drone, üç nokta, formasyon değişimi.
#
# Yönerge (SÜRÜ İHA YARIŞMASI UÇUŞ KANIT VİDEOSU) şunları istiyor:
#   - En az iki İHA, üç DOĞRUSAL OLMAYAN noktaya çarpışmadan navigasyon
#   - En az bir formasyon değişimi; sonraki noktaya gitmeden ÖNCE formasyon
#     rotasyonu videoda net görünmeli
#   - Tam otonom; RC ile müdahale YOK (kumanda görünür ama dokunulmuyor)
#   - Stabil iniş, <= 5 dakika, videoda kurgu YOK (yani tek çekim, tek koşu)
#
# NEDEN YERDE KOŞUYOR
# Sürü düğümleri (formation_node, consensus, ...) simülasyon için yazıldı ve
# sahada hiç koşmadılar (bkz. deploy/rpi/baslat.sh yorumu). Kanıt uçuşunu
# onlara bağlamak, havada ilk kez çalışacak ~14 düğüme güvenmek demek.
# Bunun yerine formasyon geometrisi BURADA hesaplanır ve her drone'a zaten
# kanıtlanmış olan guided yolundan tek tek hedef verilir:
#     backend REST -> /swarm/internal/guided/command -> base ESP -> mesh
#       -> drone esp32_bridge -> px4_bridge -> FCU
# Bu yol arm/takeoff ile sahada çalıştığı görülmüş yoldur.
#
# GÜVENLİK: HEDEFLER MUTLAK DEĞİL, GÖRELİDİR
# goto hedefi SwarmOrigin'e göre mutlak NED'dir. yki_baslat.sh'in varsayılan
# origin'i Elazığ'a çakılı; saha başka yerdeyse mutlak hedef vermek uçağı
# kilometrelerce öteye yollar. Bu yüzden bütün noktalar, görev başında
# ÖLÇÜLEN kalkış konumundan sapma olarak hesaplanır ve her goto öncesi
# "drone'un şu anki yerinden ne kadar uzağa gönderiyorum" diye kelepçelenir.
#
# Kullanım:
#     python3 gorev_kanit_ucus.py --kuru      # hiçbir şey gönderme, geometriyi bas
#     python3 gorev_kanit_ucus.py --tek 1     # yalnız drone 1 ile prova
#     python3 gorev_kanit_ucus.py             # tam görev (iki drone)
#
# Ctrl-C: her iki drone'a LAND gider. DISARM ASLA gönderilmez — havadayken
# motor kesmek düşmek demektir.
# =============================================================================

import argparse
import itertools
import math
import signal
import sys
import time
import urllib.error
import urllib.request

# --- Bağlantı ---------------------------------------------------------------
YKI = "http://localhost:8000"
ZAMAN_ASIMI_S = 5.0

# --- Sürü ------------------------------------------------------------------
# ylp00 -> drone 1, ylp02 -> drone 3 (konteyner adı ile drone no aynı değil,
# bkz. docs/cihazlar.md). Lider/sağ kanat sırası bu listenin sırasıdır.
DRONELAR = [1, 3]

# İrtifalar BİLEREK FARKLI: yatay mantıkta bir hata olsa bile iki uçak aynı
# yükseklikte olmadığı için çarpışamazlar. Yönergenin "çarpışmadan kaçınarak"
# şartını donanımsal olarak garanti eder. Temiz bir koşudan sonra eşitlenebilir.
IRTIFA_M = {1: 6.0, 3: 9.0}

# --- Geometri ---------------------------------------------------------------
ARALIK_M = 8.0        # formasyondaki iki uçak arası mesafe
KENAR_M = 22.0        # üçgen kenarı (görev noktaları arası)
TOLERANS_M = 2.5      # "vardı" sayılma yarıçapı
MAX_GOTO_M = 60.0     # GÜVENLİK KELEPÇESİ: bundan uzağa tek goto YOK

# --- Hız --------------------------------------------------------------------
# UÇUŞ HIZI BURADAN DEĞİL, PX4'TEN GELİR. GotoBody'de bir 'speed' alanı var
# ama cmd_goto onu hiç okumuyor — ölü alan, yanıltmasın. px4_bridge POZİSYON
# setpoint'i yolluyor; OFFBOARD'da hızı sınırlayan parametre MPC_XY_VEL_MAX.
# Varsayılan 12 m/s idi ve sahada "çok hızlı" bulundu; 31 Temmuz'da iki
# dronda da 1.0 m/s yapıldı (ros2 param set ... MPC_XY_VEL_MAX 1.0).
# Aşağıdaki süre bütçesi 1 m/s varsayar. Hızı değiştirirsen bunları da gözden
# geçir. RÜZGÂR NOTU: 1 m/s'te rüzgâr baskın hale gelir; rüzgâra karşı bacak
# uzarsa BACAK_ASIM_S yetmeyebilir.
SEYIR_HIZI_MS = 1.0

# --- Zamanlama (saniye) — toplam 5 dk sınırına sığmalı ----------------------
# 1 m/s'te ölçüsel bütçe: kalkış ~25 + diziliş 10 + 3 bacak x 22 + formasyon
# değişimi 12 + iki rotasyon 26 + iniş ~20  =~ 160 s (2:40). 300 s sınırının
# rahat altında; sıkışırsak KENAR_M küçültülür.
ARM_ASIM_S = 10         # arm teyidi için tanınan süre
KALKIS_ASIM_S = 45      # irtifaya çıkma için tanınan süre
BACAK_ASIM_S = 60       # bir bacağı uçmak için tanınan süre (22 m @ 1 m/s = 22 s)
YERLESME_S = 6.0        # rotasyon/formasyon sonrası bekleme (videoda görünsün)
GOREV_ASIM_S = 280      # toplam görev tavanı; aşılırsa iniş

# --- Formasyonlar -----------------------------------------------------------
# (ileri, sağ) çarpanları; ARALIK_M ile ölçeklenir. Gövde ekseninde tanımlı,
# heading'e göre döndürülür — rotasyon tam olarak budur.
FORMASYONLAR = {
    "cizgi": [(0.0, -0.5), (0.0, +0.5)],   # yan yana (heading'e dik)
    "kolon": [(+0.5, 0.0), (-0.5, 0.0)],   # ardışık (heading boyunca)
}

_iniyor = False
_son_hedef: dict = {}   # drone_id -> (kuzey, dogu); kuru modda konum takibi


# --- HTTP -------------------------------------------------------------------
def _istek(yol: str, yontem: str = "POST", govde: dict | None = None):
    veri = None
    basliklar = {}
    if govde is not None:
        import json as _json
        veri = _json.dumps(govde).encode()
        basliklar["Content-Type"] = "application/json"
    istek = urllib.request.Request(
        YKI + yol, data=veri, headers=basliklar, method=yontem
    )
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI_S) as c:
            import json as _json
            return _json.loads(c.read().decode())
    except urllib.error.HTTPError as e:
        govde_metin = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"{yol} -> HTTP {e.code}: {govde_metin}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"{yol} -> YKİ'ye ulaşılamıyor ({e.reason}). "
            "src/gcs/yki_baslat.sh çalışıyor mu?"
        ) from None


def durum() -> dict:
    """drone_id -> telemetri sözlüğü."""
    snap = _istek("/api/telemetry/snapshot", "GET")
    return {d["drone_id"]: d for d in snap.get("drones", [])}


def durum_kuru_toleransli(kuru: bool) -> dict:
    """Kuru modda YKİ kapalıysa boş dön — geometri masada doğrulanabilsin."""
    try:
        return durum()
    except RuntimeError:
        if kuru:
            return {}
        raise


def irtifa(did: int) -> float:
    return IRTIFA_M.get(did, 6.0)


# --- Geometri ---------------------------------------------------------------
def yon_derece(a, b) -> float:
    """a'dan b'ye pusula yönü (kuzeyden saat yönüne, derece)."""
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360.0


def slot_konumu(merkez, heading_deg: float, ileri: float, sag: float):
    """Formasyon slotunu NED'e çevirir.

    heading kuzeyden saat yönünde. İleri birim vektörü (cos h, sin h);
    sağ birim vektörü heading+90 -> (-sin h, cos h).
    """
    h = math.radians(heading_deg)
    ileri_k, ileri_d = math.cos(h), math.sin(h)
    sag_k, sag_d = -math.sin(h), math.cos(h)
    return (
        merkez[0] + ileri * ARALIK_M * ileri_k + sag * ARALIK_M * sag_k,
        merkez[1] + ileri * ARALIK_M * ileri_d + sag * ARALIK_M * sag_d,
    )


def formasyon_hedefleri(merkez, heading_deg: float, formasyon: str,
                        mevcut: dict | None = None) -> dict:
    """drone_id -> (kuzey, dogu) hedefi.

    SLOT ATAMASI SABİT DEĞİL. Sabit atama (drone i -> slot i) ile çizgi->kolon
    geçişinde iki uçak birbirinin yerine gider, yani KAFA KAFAYA geçerler;
    kuru koşuda ölçüldü. Bunun yerine toplam yolu en aza indiren atama
    seçilir — uçaklar en yakın slota gider, kesişme oluşmaz. Uçak sayısı az
    olduğu için tam arama yeterli.
    """
    slotlar = FORMASYONLAR[formasyon][:len(DRONELAR)]
    noktalar = [slot_konumu(merkez, heading_deg, *s) for s in slotlar]

    if not mevcut:
        return {did: noktalar[i] for i, did in enumerate(DRONELAR)}

    en_iyi, en_ucuz = None, float("inf")
    for perm in itertools.permutations(range(len(noktalar))):
        maliyet = 0.0
        for i, did in enumerate(DRONELAR):
            if did not in mevcut:
                continue
            n = noktalar[perm[i]]
            maliyet += math.hypot(n[0] - mevcut[did][0], n[1] - mevcut[did][1])
        if maliyet < en_ucuz:
            en_ucuz, en_iyi = maliyet, perm
    return {did: noktalar[en_iyi[i]] for i, did in enumerate(DRONELAR)}


def mevcut_konumlar(kuru: bool) -> dict:
    """Uçakların şu anki (kuzey, doğu) konumu.

    Canlıda telemetriden; kuru modda son gönderilen hedeflerden — böylece
    kuru koşu slot atamasını da gerçekçi doğrular.
    """
    t = durum_kuru_toleransli(kuru)
    if t:
        return {did: (t[did]["pos_x"], t[did]["pos_y"])
                for did in DRONELAR if did in t}
    return dict(_son_hedef)


# --- Komutlar ---------------------------------------------------------------
def git(did: int, hedef, irtifa_m: float, heading_deg: float, kuru: bool):
    """Tek drone'a goto. Mesafe kelepçesi burada uygulanır."""
    t = durum_kuru_toleransli(kuru).get(did)
    if t is None:
        if not kuru:
            raise RuntimeError(f"drone {did} telemetride yok")
        mesafe = float("nan")
    else:
        mesafe = math.hypot(hedef[0] - t["pos_x"], hedef[1] - t["pos_y"])
        if mesafe > MAX_GOTO_M:
            raise RuntimeError(
                f"GÜVENLİK: drone {did} için hedef {mesafe:.0f} m uzakta "
                f"(tavan {MAX_GOTO_M:.0f} m). Komut GÖNDERİLMEDİ. "
                "Origin/geometri hatası olabilir."
            )
    print(f"      drone {did}: ({hedef[0]:+7.1f},{hedef[1]:+7.1f}) "
          f"irtifa {irtifa_m:.1f}m yön {heading_deg:5.1f}°  [{mesafe:5.1f} m]")
    _son_hedef[did] = (hedef[0], hedef[1])
    if kuru:
        return
    _istek(f"/api/guided/{did}/goto", govde={
        "x": hedef[0], "y": hedef[1], "z": irtifa_m, "heading_deg": heading_deg,
    })


def varis_bekle(hedefler: dict, asim_s: float, kuru: bool) -> bool:
    """Hepsi toleransa girene kadar bekler. True = vardı."""
    if kuru:
        return True
    basla = time.time()
    while time.time() - basla < asim_s:
        time.sleep(1.0)
        t = durum()
        uzakliklar = {}
        for did, hedef in hedefler.items():
            d = t.get(did)
            if d is None:
                continue
            uzakliklar[did] = math.hypot(hedef[0] - d["pos_x"], hedef[1] - d["pos_y"])
        if uzakliklar and all(u <= TOLERANS_M for u in uzakliklar.values()):
            print("      vardı: " + "  ".join(
                f"d{k}={v:.1f}m" for k, v in sorted(uzakliklar.items())))
            return True
        print("      ... " + "  ".join(
            f"d{k}={v:.1f}m" for k, v in sorted(uzakliklar.items())), end="\r")
    print(f"\n      ZAMAN AŞIMI ({asim_s:.0f}s) — hedefe ulaşılamadı")
    return False


def indir(kuru: bool):
    """Her iki drone'a LAND. DISARM ASLA gönderilmez."""
    global _iniyor
    if _iniyor:
        return
    _iniyor = True
    print("\n>>> İNİŞ (land) — motor kesme YOK")
    for did in DRONELAR:
        try:
            if not kuru:
                _istek(f"/api/guided/{did}/land")
            print(f"    drone {did}: land gönderildi")
        except Exception as e:  # iniş her koşulda denenmeli
            print(f"    drone {did}: land GÖNDERİLEMEDİ: {e}")


# --- Ön kontrol -------------------------------------------------------------
def on_kontrol(kuru: bool) -> bool:
    print("\n=== ÖN KONTROL ===")
    t = durum_kuru_toleransli(kuru)
    if kuru and not t:
        print("  [KURU] YKİ kapalı — telemetri yok, ön kontrol atlandı")
        return True
    tamam = True
    for did in DRONELAR:
        d = t.get(did)
        if d is None:
            print(f"  drone {did}: TELEMETRİDE YOK")
            tamam = False
            continue
        notlar = []
        if not d["connected"]:
            notlar.append("BAĞLI DEĞİL")
        if d["armed"]:
            notlar.append("ZATEN ARMED (önce disarm et)")
        if d["gps_fix_type"] < 3:
            notlar.append(f"GPS fix={d['gps_fix_type']} (<3)")
        print(f"  drone {did}: bagli={d['connected']} armed={d['armed']} "
              f"mod={d['mode']} fix={d['gps_fix_type']} sat={d['gps_satellites']} "
              f"pil={d['battery_percent']:.0f}% "
              f"NED=({d['pos_x']:+.1f},{d['pos_y']:+.1f},{d['pos_z']:+.1f})")
        if notlar:
            print(f"           ENGEL: {', '.join(notlar)}")
            tamam = False
    if not tamam and not kuru:
        print("\n  ÖN KONTROL GEÇMEDİ — görev başlatılmıyor.")
    return tamam


# --- Görev ------------------------------------------------------------------
def gorev(kuru: bool) -> int:
    basla = time.time()

    def kalan() -> float:
        return GOREV_ASIM_S - (time.time() - basla)

    if not on_kontrol(kuru) and not kuru:
        return 1

    # --- Referans: ölçülen kalkış merkezi ---------------------------------
    t = durum_kuru_toleransli(kuru)
    if kuru and not t:
        merkez0 = (0.0, 0.0)
        print("\n[KURU] telemetri yok — merkez (0,0) varsayıldı")
    else:
        noktalar = [(t[did]["pos_x"], t[did]["pos_y"]) for did in DRONELAR if did in t]
        if not noktalar:
            print("Telemetri yok, görev başlatılamaz.")
            return 1
        merkez0 = (sum(p[0] for p in noktalar) / len(noktalar),
                   sum(p[1] for p in noktalar) / len(noktalar))
    print(f"\nKalkış merkezi (ölçüldü): ({merkez0[0]:+.1f}, {merkez0[1]:+.1f}) NED")

    # --- Üç doğrusal olmayan nokta (kalkış merkezine göre) ----------------
    # P1=(K,0) P2=(K,K) P3=(0,K) — çapraz çarpım K^2 != 0, yani doğrusal değil.
    K = KENAR_M
    P1 = (merkez0[0] + K, merkez0[1])
    P2 = (merkez0[0] + K, merkez0[1] + K)
    P3 = (merkez0[0], merkez0[1] + K)
    print(f"Görev noktaları:  P1=({P1[0]:+.1f},{P1[1]:+.1f})  "
          f"P2=({P2[0]:+.1f},{P2[1]:+.1f})  P3=({P3[0]:+.1f},{P3[1]:+.1f})")

    # --- 1) ARM + KALKIŞ ---------------------------------------------------
    print("\n=== 1) ARM + KALKIŞ ===")
    # ARM TEYİDİ BEKLENİR. arm komutu px4_bridge'de önce OFFBOARD'a geçip
    # sonra arm ediyor (PX4 yerde armlıyken OFFBOARD'a girmiyor); bu birkaç
    # yüz ms sürer. Teyit beklemeden takeoff yollamak, komutun daha disarm
    # haldeki uçağa gitmesi ve sessizce düşmesi demek.
    for did in DRONELAR:
        print(f"    drone {did}: arm + takeoff {irtifa(did):.1f}m")
        if kuru:
            time.sleep(0.2)
            continue
        _istek(f"/api/guided/{did}/arm")
        t_bas = time.time()
        while time.time() - t_bas < ARM_ASIM_S:
            time.sleep(0.5)
            if durum().get(did, {}).get("armed"):
                print(f"      arm teyit ({time.time() - t_bas:.1f}s)")
                break
        else:
            print(f"      ARM EDİLEMEDİ ({ARM_ASIM_S:.0f}s) — görev durduruluyor")
            indir(kuru)
            return 1
        _istek(f"/api/guided/{did}/takeoff?altitude={irtifa(did)}")
        time.sleep(1.0)

    if not kuru:
        print("    irtifa bekleniyor...")
        t_bas = time.time()
        while time.time() - t_bas < KALKIS_ASIM_S:
            time.sleep(1.0)
            t = durum()
            if all(t.get(did, {}).get("alt_m", 0.0) >= irtifa(did) * 0.9
                   for did in DRONELAR):
                print("    irtifa tamam: " + "  ".join(
                    f"d{did}={t[did]['alt_m']:.1f}m" for did in DRONELAR))
                break
            print("    ... " + "  ".join(
                f"d{did}={t.get(did,{}).get('alt_m',0.0):.1f}m"
                for did in DRONELAR), end="\r")
        else:
            print("\n    KALKIŞ ZAMAN AŞIMI — iniliyor")
            indir(kuru)
            return 1

    # --- 2..N) Bacaklar ----------------------------------------------------
    # ÜÇ AYRI GÖRÜNÜR OLAY: formasyon değişimi, rotasyon, ilerleme.
    #
    # Bunlar BİLEREK ayrı adımlar. İlk kuru koşuda formasyon çizgi->kolon
    # olurken heading de 0->90 dönüyordu; ikisi birbirini tam götürüp uçaklar
    # HİÇ KIMILDAMIYORDU (ölçüldü). Yönerge formasyon değişiminin ve
    # rotasyonun "net bir şekilde" görünmesini istiyor — o yüzden önce eski
    # yönde formasyonu değiştir, bekle; sonra yeni yöne dön, bekle; sonra git.
    def adim(ad: str, merkez, heading: float, formasyon: str, etiket: str) -> bool:
        print(f"\n=== {etiket} ===")
        print(f"    formasyon={formasyon}  yön={heading:5.1f}°  "
              f"merkez=({merkez[0]:+.1f},{merkez[1]:+.1f})  (kalan {kalan():.0f}s)")
        hedefler = formasyon_hedefleri(merkez, heading, formasyon,
                                       mevcut_konumlar(kuru))
        for did, h in hedefler.items():
            git(did, h, irtifa(did), heading, kuru)
        if not varis_bekle(hedefler, min(BACAK_ASIM_S, max(kalan(), 5)), kuru):
            return False
        print(f"    yerleşme {YERLESME_S:.0f}s (videoda görünsün)")
        if not kuru:
            time.sleep(YERLESME_S)
        return True

    noktalar_sirasi = [("P1", P1), ("P2", P2), ("P3", P3)]
    merkez = merkez0
    formasyon = "cizgi"
    heading = yon_derece(merkez0, P1)

    # Kalkış noktasında ilk diziliş.
    if not adim("P0", merkez0, heading, formasyon, "DİZİLİŞ @ kalkış — çizgi"):
        indir(kuru)
        return 1

    for i, (ad, nokta) in enumerate(noktalar_sirasi):
        yeni_heading = yon_derece(merkez, nokta)

        # (a) Formasyon değişimi — ESKİ yönde, tek başına görünsün.
        if i == 1:  # P1'e vardıktan sonra: yönergenin istediği değişim
            formasyon = "kolon"
            if not adim(ad, merkez, heading, formasyon,
                        f"FORMASYON DEĞİŞİMİ @ {noktalar_sirasi[i-1][0]}: "
                        f"çizgi -> kolon (yön sabit {heading:.0f}°)"):
                indir(kuru)
                return 1

        # (b) Rotasyon — formasyon sabit, yalnız yön değişiyor.
        if abs((yeni_heading - heading + 180) % 360 - 180) > 1.0:
            heading = yeni_heading
            if not adim(ad, merkez, heading, formasyon,
                        f"ROTASYON -> {ad} yönü ({heading:.0f}°)"):
                indir(kuru)
                return 1

        # (c) İlerleme.
        print(f"\n=== NAVİGASYON -> {ad} ===")
        varis = formasyon_hedefleri(nokta, heading, formasyon,
                                    mevcut_konumlar(kuru))
        for did, h in varis.items():
            git(did, h, irtifa(did), heading, kuru)
        if not varis_bekle(varis, min(BACAK_ASIM_S, max(kalan(), 5)), kuru):
            indir(kuru)
            return 1
        merkez = nokta

        if kalan() < 50:
            print(f"\n    GÖREV SÜRE TAVANI yaklaştı ({kalan():.0f}s) — iniliyor")
            break

    # --- İniş --------------------------------------------------------------
    indir(kuru)
    print(f"\n=== GÖREV TAMAM — toplam {time.time() - basla:.0f} s ===")
    return 0


def main() -> int:
    global DRONELAR
    ap = argparse.ArgumentParser(description="Kanıt uçuşu görev koşucusu")
    ap.add_argument("--kuru", action="store_true",
                    help="hiçbir komut gönderme, yalnız geometriyi bas")
    ap.add_argument("--tek", type=int, metavar="ID",
                    help="yalnız bu drone ile prova (formasyon tek slota düşer)")
    a = ap.parse_args()

    if a.tek is not None:
        DRONELAR = [a.tek]
        print(f"[TEK DRONE PROVASI] yalnız drone {a.tek}")

    def _kesildi(_sig, _frm):
        print("\n\n!!! KESİLDİ (Ctrl-C) !!!")
        indir(a.kuru)
        sys.exit(130)

    signal.signal(signal.SIGINT, _kesildi)
    signal.signal(signal.SIGTERM, _kesildi)

    print("=" * 70)
    print("  KANIT UÇUŞU — 2 drone, 3 nokta, formasyon değişimi")
    print(f"  mod: {'KURU (komut gönderilmez)' if a.kuru else 'CANLI'}")
    print(f"  dronelar: {DRONELAR}   irtifalar: "
          + "  ".join(f"d{d}={irtifa(d)}m" for d in DRONELAR))
    print("=" * 70)

    try:
        return gorev(a.kuru)
    except Exception as e:
        print(f"\nHATA: {e}")
        indir(a.kuru)
        return 1


if __name__ == "__main__":
    sys.exit(main())
