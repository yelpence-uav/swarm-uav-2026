#!/usr/bin/env python3
# =============================================================================
# KANIT UÇUŞU GÖREV KOŞUCUSU
#
# Koreografi (şartname 5.1.2'deki görev komutlarının hepsini gösterir):
#   0. Yerde OK BAŞI dizilimi
#   1. Tek komutla eş zamanlı kalkış, formasyonu koruyarak irtifaya
#   2. Ok başında P1'e
#   3. P1'de ROLL manevrası (sürü merkezi SABİT, biri yukarı biri aşağı)
#   4. Roll'lu halde P2'ye
#   5. P2'de roll'u düzelt, sonra FORMASYON DEĞİŞİMİ
#   6. P3'e
#   7. P3'te İRTİFA DEĞİŞİMİ
#   8. Kalkış noktasına dön ve in
#
# Uçuş kanıt videosu yönergesi de karşılanır: >=2 İHA, üç doğrusal olmayan
# nokta, çarpışmasız, en az bir formasyon değişimi + rotasyon, tam otonom
# (RC'ye dokunulmaz), stabil iniş, <=5 dk, tek çekim.
#
# ---------------------------------------------------------------------------
# NEDEN YERDE KOŞUYOR
# Sürü düğümleri (formation_node, consensus_node, collision_avoidance, ...)
# simülasyon için yazıldı ve sahada HİÇ koşmadılar — bkz. deploy/rpi/baslat.sh
# yorumu, ve ölçüldü: dronlarda yalnız agent_fsm + esp32_bridge + px4_bridge
# çalışıyor, 14 sürü düğümünün hiçbiri açık değil.
#
# collision_avoidance'ı açmak tek başına MÜMKÜN DEĞİL: zincirde
# formation_node -> collision_avoidance -> px4_bridge şeklinde zorunlu halka,
# yani onu açmak bütün denenmemiş zinciri işin içine sokmak demek. Onun yerine
# çarpışmasızlık GEOMETRİK olarak garanti ediliyor ve uçuştan ÖNCE
# kanıtlanıyor (bkz. plan_dogrula).
#
# Komut yolu (hepsi kanıtlanmış):
#   REST -> YKİ backend -> base ESP -> mesh -> drone esp32_bridge
#        -> AgentSetpoint -> px4_bridge -> OFFBOARD -> PX4
#
# ---------------------------------------------------------------------------
# GÜVENLİK
# - Hedefler mutlak değil, ÖLÇÜLEN kalkış konumuna göreli. yki_baslat.sh'in
#   origin'i sahaya uymazsa mutlak hedef uçağı kilometrelerce öteye yollardı.
# - Plan uçmadan önce bütünüyle kurulur ve doğrulanır: her adımda ve
#   adımlar ARASINDAKİ geçişte uçaklar arası en küçük mesafe hesaplanır.
#   Eşiğin altına düşen varsa görev BAŞLAMAZ.
# - Her goto öncesi mesafe kelepçesi (MAX_GOTO_M).
# - Ctrl-C ve her hata yolu LAND gönderir. DISARM ASLA gönderilmez.
#
# Kullanım:
#     python3 gorev_kanit_ucus.py --kuru          # komut yok, plan + doğrulama
#     python3 gorev_kanit_ucus.py --dronelar 1,3  # prova (iki drone)
#     python3 gorev_kanit_ucus.py --dronelar 1,2,3
# =============================================================================

import argparse
import itertools
import math
import signal
import sys
import time
import urllib.error
import urllib.request

YKI = "http://localhost:8000"
ZAMAN_ASIMI_S = 5.0

# ylp00 -> 1, ylp01 -> 2, ylp02 -> 3 (bkz. docs/cihazlar.md)
DRONELAR = [1, 3]

# --- Geometri ---------------------------------------------------------------
ARALIK_M = 12.0         # formasyonda komşu slotlar arası mesafe
KANAT_ACISI_DEG = 45.0  # ok başı kanat açısı (orchestrator wing_alpha ile aynı)
KENAR_M = 22.0          # görev noktaları arası
TOLERANS_M = 2.5        # "vardı" yarıçapı
MAX_GOTO_M = 60.0       # tek goto için mesafe tavanı

# --- İrtifalar --------------------------------------------------------------
# KALKIS_IRTIFA_M agent_fsm_node'un target_altitude_m VARSAYILANIYLA (10.0)
# BİLEREK AYNI. Sebep ölçüldü: agent_fsm TAKEOFF durumuna girince px4_bridge'e
# kendi 'takeoff:10.0' komutunu yolluyor (agent_fsm_node.py:251). Farklı bir
# değer seçersek iki komut çakışır ve hangisinin kazandığı sıralamaya kalır.
KALKIS_IRTIFA_M = 10.0
# Görev (formasyon) irtifası. Kalkıştan AYRI tutuluyor: roll manevrasında
# kanatlar merkezden dz = 0.408 x ARALIK_M kadar ayrılıyor (12 m aralıkta
# ±4.9 m). Kalkış irtifası 10 m'de kalsaydı alttaki uçak 5.1 m'ye inerdi —
# manevra sırasında fazla alçak. 12 m'de yayılım 7.1-16.9 m arasında kalıyor.
GOREV_IRTIFA_M = 12.0
YENI_IRTIFA_M = 18.0    # P3'teki irtifa değişimi hedefi

# --- Manevra ----------------------------------------------------------------
# Şartname: sürü merkezi sabit, sağa/sola yatış. 30° seçildi çünkü 20°'de
# kanatlar merkezden yalnız ±2.1 m ayrılıyordu ve yerden çekimde bu sınırda
# kalıyor; 30°'de ±3.3 m'ye çıkıyor, manevra videoda net görünüyor.
ROLL_ACISI_DEG = 30.0

# --- Çarpışma ---------------------------------------------------------------
# Uçaklar arası kabul edilen en küçük mesafe. Plan bunu ihlal ederse görev
# başlamaz. GPS hatası + pervane çapı + akış etkisi için bolca pay.
MIN_AYRIM_M = 4.0

# --- Zamanlama (saniye) — 1 m/s'e göre; toplam 5 dk sınırına sığmalı --------
# Hız PX4'te: MPC_XY_VEL_MAX = 1.0 (31 Tem'de iki dronda da ayarlandı).
# Bütçe: kalkış ~25 + 4 bacak x 22 + manevralar ~60 + iniş ~20 =~ 195 s.
ARM_ASIM_S = 10
KALKIS_ASIM_S = 60
ADIM_ASIM_S = 70
YERLESME_S = 6.0        # YALNIZ manevra adimlarindan sonra (roll, rotasyon,
                        # formasyon, irtifa). Duz seyir bacaklarinda beklenmez:
                        # gosterilecek bir sey yok ve 5 dk sinirinda 24 sn yer actik.
GOREV_ASIM_S = 285

_iniyor = False


# --- HTTP -------------------------------------------------------------------
def _istek(yol: str, yontem: str = "POST", govde: dict | None = None):
    import json as _json
    veri = None
    basliklar = {}
    if govde is not None:
        veri = _json.dumps(govde).encode()
        basliklar["Content-Type"] = "application/json"
    istek = urllib.request.Request(YKI + yol, data=veri, headers=basliklar, method=yontem)
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI_S) as c:
            return _json.loads(c.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{yol} -> HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"{yol} -> YKİ'ye ulaşılamıyor ({e.reason}). "
                           "src/gcs/yki_baslat.sh çalışıyor mu?") from None


def durum() -> dict:
    snap = _istek("/api/telemetry/snapshot", "GET")
    return {d["drone_id"]: d for d in snap.get("drones", [])}


def durum_toleransli(kuru: bool) -> dict:
    try:
        return durum()
    except RuntimeError:
        if kuru:
            return {}
        raise


# --- Formasyon geometrisi ---------------------------------------------------
def _merkezle(ofsetler):
    """Ofsetleri merkezle: toplamları sıfır olsun.

    Şartname 'sürü merkezi' üzerinden konuşuyor; ofsetlerin ağırlık merkezi
    sıfır olursa komut verdiğimiz nokta gerçekten sürünün merkezi olur.
    """
    n = len(ofsetler)
    oi = sum(o[0] for o in ofsetler) / n
    od = sum(o[1] for o in ofsetler) / n
    return [(o[0] - oi, o[1] - od) for o in ofsetler]


def formasyon_ofsetleri(ad: str, n: int):
    """Gövde ekseninde (ileri, sağ) ofsetleri, METRE. Merkezlenmiş döner."""
    if ad == "okbasi":
        # Lider önde; kanatlar geride, ±KANAT_ACISI ile açılarak.
        a = math.radians(KANAT_ACISI_DEG)
        o = [(0.0, 0.0)]
        for k in range(1, n):
            yan = 1.0 if k % 2 == 1 else -1.0
            kat = (k + 1) // 2
            o.append((-math.cos(a) * ARALIK_M * kat, yan * math.sin(a) * ARALIK_M * kat))
        return _merkezle(o)
    if ad == "kolon":
        o = [(-ARALIK_M * i, 0.0) for i in range(n)]
        return _merkezle(o)
    if ad == "cizgi":
        o = [(0.0, ARALIK_M * i) for i in range(n)]
        return _merkezle(o)
    raise ValueError(f"bilinmeyen formasyon: {ad}")


def egim_dz(ofsetler, pitch_deg: float, roll_deg: float):
    """Eğim manevrasının slot başına irtifa deltası (metre, yukarı +).

    swarm_core.formation_control.manual_kinematics.apply_tilt ile AYNI
    matematik. Ortalamanın çıkarılması şartnamenin 'sürü merkezinin konumunu
    SABİT tutarak' şartını sağlar: bazı slot yukarı, bazı aşağı, net kayma 0.
    """
    if pitch_deg == 0.0 and roll_deg == 0.0:
        return [0.0] * len(ofsetler)
    tp = math.tan(math.radians(pitch_deg))
    tr = math.tan(math.radians(roll_deg))
    dz = [-dx * tp + dy * tr for (dx, dy) in ofsetler]
    ort = sum(dz) / len(dz)
    return [d - ort for d in dz]


def yon_derece(a, b) -> float:
    """a'dan b'ye pusula yönü (kuzeyden saat yönüne, derece)."""
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360.0


def slot_dunya(merkez, heading_deg: float, ileri: float, sag: float):
    """Gövde ofsetini NED (kuzey, doğu)'ya çevirir."""
    h = math.radians(heading_deg)
    return (merkez[0] + ileri * math.cos(h) + sag * (-math.sin(h)),
            merkez[1] + ileri * math.sin(h) + sag * math.cos(h))


def hedefler_uret(merkez, heading, formasyon, irtifa, roll_deg,
                  onceki=None, slot=None, yeniden_ata=False):
    """drone_id -> (kuzey, doğu, irtifa). slot: drone_id -> slot indeksi.

    SLOT ATAMASI NE ZAMAN DEĞİŞİR — bu ayrım videoyu belirliyor:

    * Rotasyon ve eğim adımlarında slotlar SABİT kalır. Yoksa "en kısa yol"
      araması uçakları birbirinin slotuna yerleştiriyor; formasyon dönüyor
      ama uçaklar yerinde sayıyormuş gibi görünüyor (kuru koşuda ölçüldü:
      90° rotasyonda yatay hareket 2.7 m'ye düşüyordu). Yönerge rotasyonun
      "net bir şekilde" görünmesini istiyor, o yüzden uçaklar gerçekten
      savrulmalı.
    * FORMASYON DEĞİŞİMİNDE yeniden atama yapılır. Orada sabit atama
      uçakları birbirinin yerine yollayıp KAFA KAFAYA geçiriyordu.
    """
    n = len(DRONELAR)
    ofs = formasyon_ofsetleri(formasyon, n)
    dz = egim_dz(ofs, 0.0, roll_deg)
    noktalar = [slot_dunya(merkez, heading, *o) + (irtifa + z,)
                for o, z in zip(ofs, dz)]

    if slot is None:
        slot = {did: i for i, did in enumerate(DRONELAR)}

    if yeniden_ata and onceki:
        en_iyi, en_ucuz = None, float("inf")
        for perm in itertools.permutations(range(n)):
            maliyet = sum(
                math.dist(noktalar[perm[i]], onceki[did])
                for i, did in enumerate(DRONELAR) if did in onceki
            )
            if maliyet < en_ucuz:
                en_ucuz, en_iyi = maliyet, perm
        slot = {did: en_iyi[i] for i, did in enumerate(DRONELAR)}

    return {did: noktalar[slot[did]] for did in DRONELAR}, slot


# --- Çarpışma doğrulaması ---------------------------------------------------
def _min_mesafe_gecis(a0, a1, b0, b1) -> float:
    """İki uçak düz çizgide EŞ ZAMANLI giderken aralarındaki en küçük mesafe.

    Göreli konum r(t) = (a0-b0) + t*((a1-a0)-(b1-b0)), t in [0,1].
    |r(t)|'nin minimumu kapalı formülle bulunur — örnekleme yok, kesin.
    """
    r0 = tuple(a0[k] - b0[k] for k in range(3))
    r1 = tuple(a1[k] - b1[k] for k in range(3))
    d = tuple(r1[k] - r0[k] for k in range(3))
    dd = sum(x * x for x in d)
    if dd < 1e-9:
        return math.dist(r0, (0.0, 0.0, 0.0))
    t = -sum(r0[k] * d[k] for k in range(3)) / dd
    t = max(0.0, min(1.0, t))
    p = tuple(r0[k] + t * d[k] for k in range(3))
    return math.dist(p, (0.0, 0.0, 0.0))


def plan_dogrula(plan) -> bool:
    """Uçmadan önce çarpışmasızlığı KANITLAR.

    İki şey denetlenir:
      1. Her adımda uçaklar arası mesafe (durağan hal)
      2. Bir adımdan diğerine GEÇERKEN en çok yaklaştıkları an
    İkincisi şart: hedefler ayrı ayrı güvenli olsa bile yollar kesişebilir.
    """
    if len(DRONELAR) < 2:
        print("\n=== ÇARPIŞMA DOĞRULAMASI: tek drone, denetim gereksiz ===")
        return True

    print(f"\n=== ÇARPIŞMA DOĞRULAMASI (eşik {MIN_AYRIM_M:.1f} m) ===")
    tamam = True
    en_kotu = (float("inf"), "")

    for i, (etiket, _heading, hedefler, _b) in enumerate(plan):
        for a, b in itertools.combinations(DRONELAR, 2):
            m = math.dist(hedefler[a], hedefler[b])
            if m < en_kotu[0]:
                en_kotu = (m, f"{etiket} (durağan, d{a}-d{b})")
            if m < MIN_AYRIM_M:
                print(f"  İHLAL  {etiket}: d{a}-d{b} = {m:.2f} m")
                tamam = False
        if i == 0:
            continue
        onceki = plan[i - 1][2]
        for a, b in itertools.combinations(DRONELAR, 2):
            # Üç senaryo birden denetlenir. İkisi ve üçüncüsü şart, çünkü
            # "ikisi de eş zamanlı, aynı hızda gider" varsayımı sahada
            # tutmayabilir: mesh paketi biri için geç gelebilir, rüzgâr birini
            # yavaşlatabilir, biri hedefine erken oturup bekleyebilir.
            # DONMUŞ senaryosu bu durumların hepsini kapsayan en kötü hâldir.
            senaryolar = (
                ("eş zamanlı", onceki[a], hedefler[a], onceki[b], hedefler[b]),
                (f"d{a} donmuş", onceki[a], onceki[a], onceki[b], hedefler[b]),
                (f"d{b} donmuş", onceki[a], hedefler[a], onceki[b], onceki[b]),
            )
            for ad, a0, a1, b0, b1 in senaryolar:
                m = _min_mesafe_gecis(a0, a1, b0, b1)
                if m < en_kotu[0]:
                    en_kotu = (m, f"{plan[i-1][0]} -> {etiket} ({ad}, d{a}-d{b})")
                if m < MIN_AYRIM_M:
                    print(f"  İHLAL  {plan[i-1][0]} -> {etiket}: "
                          f"d{a}-d{b} [{ad}] {m:.2f} m'ye yaklaşıyor")
                    tamam = False

    print(f"  en kritik an: {en_kotu[0]:.2f} m  ({en_kotu[1]})")
    print("  SONUÇ: " + ("GEÇTİ" if tamam else "KALDI — görev başlatılmayacak"))
    return tamam


# --- Plan kurulumu ----------------------------------------------------------
def plan_kur(merkez0):
    """Bütün görevi (etiket, hedefler) adımları olarak kurar.

    Uçmadan önce tamamı kurulur ki doğrulanabilsin. Noktalar kalkış
    merkezine GÖRELİ: P1=(K,0) P2=(K,K) P3=(0,K) — çapraz çarpım K^2 != 0,
    yani üçü doğrusal DEĞİL (yönergenin şartı).
    """
    K = KENAR_M
    P1 = (merkez0[0] + K, merkez0[1])
    P2 = (merkez0[0] + K, merkez0[1] + K)
    P3 = (merkez0[0], merkez0[1] + K)

    plan = []
    onceki = None
    slot = None

    def ekle(etiket, merkez, heading, formasyon, irtifa, roll,
             yeniden_ata=False, beklet=True):
        nonlocal onceki, slot
        h, slot = hedefler_uret(merkez, heading, formasyon, irtifa, roll,
                                onceki, slot, yeniden_ata)
        # heading PLANA yazılır. Onceden adım sırasında "bir önceki hedeften
        # bu hedefe" diye türetiliyordu; ilk adımda önceki olmadığı için
        # burun kuzeye (0°) bakıyordu. Formasyonun yönü zaten burada belli.
        plan.append((etiket, heading, h, beklet))
        onceki = h

    y1 = yon_derece(merkez0, P1)
    y2 = yon_derece(P1, P2)
    y3 = yon_derece(P2, P3)
    y4 = yon_derece(P3, merkez0)

    # 1) Kalkış sonrası diziliş — ok başı, P1 yönünde
    ekle("kalkis/okbasi", merkez0, y1, "okbasi", GOREV_IRTIFA_M, 0.0)
    # 2) P1'e
    ekle("-> P1", P1, y1, "okbasi", GOREV_IRTIFA_M, 0.0, beklet=False)
    # 3) P1'de ROLL
    ekle("P1: ROLL %+.0f" % ROLL_ACISI_DEG, P1, y1, "okbasi", GOREV_IRTIFA_M, ROLL_ACISI_DEG)
    # 4) rotasyon (P2 yönü), roll KORUNARAK
    ekle("P1: rotasyon->P2", P1, y2, "okbasi", GOREV_IRTIFA_M, ROLL_ACISI_DEG)
    # 5) roll'lu halde P2'ye
    ekle("-> P2 (roll'lu)", P2, y2, "okbasi", GOREV_IRTIFA_M, ROLL_ACISI_DEG, beklet=False)
    # 6) P2'de roll düzelt
    ekle("P2: roll duzelt", P2, y2, "okbasi", GOREV_IRTIFA_M, 0.0)
    # 7) P2'de FORMASYON DEĞİŞİMİ (ok başı -> çizgi), yön sabit.
    #    Slot yeniden ataması YALNIZ BURADA: şekil değiştiği için sabit atama
    #    uçakları birbirinin yerine yollayıp kafa kafaya geçirirdi.
    ekle("P2: FORMASYON okbasi->cizgi", P2, y2, "cizgi", GOREV_IRTIFA_M, 0.0,
         yeniden_ata=True)
    # 8) rotasyon (P3 yönü)
    ekle("P2: rotasyon->P3", P2, y3, "cizgi", GOREV_IRTIFA_M, 0.0)
    # 9) P3'e
    ekle("-> P3", P3, y3, "cizgi", GOREV_IRTIFA_M, 0.0, beklet=False)
    # 10) P3'te İRTİFA DEĞİŞİMİ
    ekle("P3: IRTIFA %.0f->%.0f m" % (GOREV_IRTIFA_M, YENI_IRTIFA_M),
         P3, y3, "cizgi", YENI_IRTIFA_M, 0.0)
    # 11) rotasyon (eve yön)
    ekle("P3: rotasyon->EV", P3, y4, "cizgi", YENI_IRTIFA_M, 0.0)
    # 12) kalkış noktasına dön
    ekle("-> EV (kalkis noktasi)", merkez0, y4, "cizgi", YENI_IRTIFA_M, 0.0, beklet=False)
    return plan


def plan_yaz(plan):
    print("\n=== GÖREV PLANI ===")
    for etiket, heading, hedefler, _b in plan:
        print(f"  {etiket}   (yön {heading:.0f}°)")
        for did in DRONELAR:
            k, d, i = hedefler[did]
            print(f"      drone {did}: ({k:+7.1f},{d:+7.1f})  irtifa {i:5.1f} m")


# --- Komutlar ---------------------------------------------------------------
def git(did: int, hedef, heading_deg: float, kuru: bool, t_durum):
    k, d, irtifa = hedef
    mevcut = t_durum.get(did)
    if mevcut is None:
        if not kuru:
            raise RuntimeError(f"drone {did} telemetride yok")
    else:
        mesafe = math.hypot(k - mevcut["pos_x"], d - mevcut["pos_y"])
        if mesafe > MAX_GOTO_M:
            raise RuntimeError(
                f"GÜVENLİK: drone {did} hedefi {mesafe:.0f} m uzakta "
                f"(tavan {MAX_GOTO_M:.0f} m). Komut GÖNDERİLMEDİ.")
    if kuru:
        return
    _istek(f"/api/guided/{did}/goto", govde={
        "x": k, "y": d, "z": irtifa, "heading_deg": heading_deg})


def varis_bekle(hedefler, asim_s: float, kuru: bool) -> bool:
    if kuru:
        return True
    basla = time.time()
    while time.time() - basla < asim_s:
        time.sleep(1.0)
        t = durum()

        # PİLOT DEVRALDI MI / OFFBOARD DÜŞTÜ MÜ — hemen anla, zaman aşımını
        # bekleme. Kumandadan bir drone'a müdahale edilirse (POSCTL, LAND,
        # failsafe) o uçak artık bizim setpoint'lerimizi izlemiyor demektir;
        # diğerlerini 70 sn havada tutmanın anlamı yok. Sessiz kalırsak
        # varis_bekle zaman aşımına düşene kadar sürü uçmaya devam ederdi.
        for did in DRONELAR:
            d = t.get(did)
            if d is None:
                continue
            if not d.get("offboard_active", False):
                print(f"\n      !!! drone {did} OFFBOARD'DAN ÇIKTI "
                      f"(mod={d.get('mode')}) — pilot müdahalesi ya da failsafe")
                return False
            if d.get("pilot_override_active", False):
                print(f"\n      !!! drone {did} PİLOT KONTROLÜNDE "
                      f"(mod={d.get('mode')})")
                return False

        uzak = {}
        for did, h in hedefler.items():
            dd = t.get(did)
            if dd is None:
                continue
            uzak[did] = math.dist((dd["pos_x"], dd["pos_y"], dd["alt_m"]), h)
        if uzak and all(u <= TOLERANS_M for u in uzak.values()):
            print("      vardı: " + "  ".join(f"d{k}={v:.1f}m" for k, v in sorted(uzak.items())))
            return True
        print("      ... " + "  ".join(f"d{k}={v:.1f}m" for k, v in sorted(uzak.items())), end="\r")
    print(f"\n      ZAMAN AŞIMI ({asim_s:.0f}s)")
    return False


def indir(kuru: bool):
    """LAND. DISARM ASLA gönderilmez — havada motor kesmek düşmek demektir."""
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
        except Exception as e:
            print(f"    drone {did}: land GÖNDERİLEMEDİ: {e}")


def on_kontrol(kuru: bool) -> bool:
    print("\n=== ÖN KONTROL ===")
    t = durum_toleransli(kuru)
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
        engel = []
        if not d["connected"]:
            engel.append("BAĞLI DEĞİL")
        if d["armed"]:
            engel.append("ZATEN ARMED")
        if d["gps_fix_type"] < 3:
            engel.append(f"GPS fix={d['gps_fix_type']}")
        print(f"  drone {did}: bagli={d['connected']} armed={d['armed']} mod={d['mode']} "
              f"fix={d['gps_fix_type']} sat={d['gps_satellites']} pil={d['battery_percent']:.0f}% "
              f"NED=({d['pos_x']:+.1f},{d['pos_y']:+.1f})")
        if engel:
            print(f"           ENGEL: {', '.join(engel)}")
            tamam = False
    return tamam


# --- Görev ------------------------------------------------------------------
def gorev(kuru: bool) -> int:
    basla = time.time()

    def kalan():
        return GOREV_ASIM_S - (time.time() - basla)

    if not on_kontrol(kuru) and not kuru:
        print("\n  ÖN KONTROL GEÇMEDİ — görev başlatılmıyor.")
        return 1

    t = durum_toleransli(kuru)
    if t:
        pts = [(t[d]["pos_x"], t[d]["pos_y"]) for d in DRONELAR if d in t]
        merkez0 = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    elif kuru:
        merkez0 = (0.0, 0.0)
        print("\n[KURU] telemetri yok — merkez (0,0) varsayıldı")
    else:
        print("Telemetri yok.")
        return 1
    print(f"\nKalkış merkezi (ölçüldü): ({merkez0[0]:+.1f}, {merkez0[1]:+.1f}) NED")

    plan = plan_kur(merkez0)
    plan_yaz(plan)
    if not plan_dogrula(plan):
        return 1
    if kuru:
        print("\n[KURU] plan doğrulandı, komut gönderilmedi.")
        return 0

    # --- ARM + KALKIŞ -------------------------------------------------------
    # ARM TEYİDİ BEKLENİR: px4_bridge önce OFFBOARD'a geçip sonra arm ediyor
    # (PX4 yerde armlıyken OFFBOARD'a girmiyor). Teyit beklemeden takeoff
    # yollamak, komutun hâlâ disarm uçağa gitmesi ve sessizce düşmesi demek.
    print("\n=== ARM + KALKIŞ ===")
    for did in DRONELAR:
        print(f"    drone {did}: arm")
        _istek(f"/api/guided/{did}/arm")
        t0 = time.time()
        while time.time() - t0 < ARM_ASIM_S:
            time.sleep(0.5)
            if durum().get(did, {}).get("armed"):
                print(f"      arm teyit ({time.time()-t0:.1f}s)")
                break
        else:
            print(f"      ARM EDİLEMEDİ — görev durduruluyor")
            indir(kuru)
            return 1
    for did in DRONELAR:
        _istek(f"/api/guided/{did}/takeoff?altitude={KALKIS_IRTIFA_M}")
    print(f"    takeoff {KALKIS_IRTIFA_M:.0f} m gönderildi, irtifa bekleniyor...")
    t0 = time.time()
    while time.time() - t0 < KALKIS_ASIM_S:
        time.sleep(1.0)
        t = durum()
        if all(t.get(d, {}).get("alt_m", 0.0) >= KALKIS_IRTIFA_M * 0.9 for d in DRONELAR):
            print("    irtifa tamam: " + "  ".join(f"d{d}={t[d]['alt_m']:.1f}m" for d in DRONELAR))
            break
        print("    ... " + "  ".join(f"d{d}={t.get(d,{}).get('alt_m',0.0):.1f}m"
                                     for d in DRONELAR), end="\r")
    else:
        print("\n    KALKIŞ ZAMAN AŞIMI — iniliyor")
        indir(kuru)
        return 1

    # --- Plan adımları ------------------------------------------------------
    for i, (etiket, heading, hedefler, beklet) in enumerate(plan):
        print(f"\n=== [{i+1}/{len(plan)}] {etiket}   yön {heading:.0f}°   "
              f"(kalan {kalan():.0f}s) ===")
        t_durum = durum()
        for did in DRONELAR:
            h = hedefler[did]
            print(f"      drone {did}: ({h[0]:+7.1f},{h[1]:+7.1f}) "
                  f"irtifa {h[2]:5.1f} m yön {heading:5.1f}°")
            git(did, h, heading, kuru, t_durum)
        if not varis_bekle(hedefler, min(ADIM_ASIM_S, max(kalan(), 5)), kuru):
            indir(kuru)
            return 1
        if beklet:
            print(f"    yerleşme {YERLESME_S:.0f}s (videoda net görünsün)")
            time.sleep(YERLESME_S)
        if kalan() < 40:
            print(f"\n    GÖREV SÜRE TAVANI ({kalan():.0f}s) — iniliyor")
            break

    indir(kuru)
    print(f"\n=== GÖREV TAMAM — {time.time()-basla:.0f} s ===")
    return 0




def main() -> int:
    global DRONELAR
    ap = argparse.ArgumentParser(description="Kanıt uçuşu görev koşucusu")
    ap.add_argument("--kuru", action="store_true", help="komut gönderme; planı kur ve doğrula")
    ap.add_argument("--dronelar", default="1,3", help="virgülle: 1,3 (prova) veya 1,2,3")
    a = ap.parse_args()
    DRONELAR = [int(x) for x in a.dronelar.split(",") if x.strip()]

    def _kesildi(_s, _f):
        print("\n\n!!! KESİLDİ (Ctrl-C) !!!")
        indir(a.kuru)
        sys.exit(130)

    signal.signal(signal.SIGINT, _kesildi)
    signal.signal(signal.SIGTERM, _kesildi)

    print("=" * 72)
    print("  KANIT UÇUŞU — ok başı, roll, formasyon değişimi, irtifa değişimi")
    print(f"  dronelar: {DRONELAR}   kalkış {KALKIS_IRTIFA_M:.0f} m -> {YENI_IRTIFA_M:.0f} m")
    print(f"  roll {ROLL_ACISI_DEG:.0f}°   aralık {ARALIK_M:.0f} m   kenar {KENAR_M:.0f} m")
    print(f"  mod: {'KURU (komut yok)' if a.kuru else 'CANLI'}")
    print("=" * 72)
    try:
        return gorev(a.kuru)
    except Exception as e:
        print(f"\nHATA: {e}")
        indir(a.kuru)
        return 1


if __name__ == "__main__":
    sys.exit(main())
