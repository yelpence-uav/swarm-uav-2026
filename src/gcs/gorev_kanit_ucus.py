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
#     python3 gorev_kanit_ucus.py --dronelar 1,2  # prova (iki drone)
#     python3 gorev_kanit_ucus.py --dronelar 1,2,3
# =============================================================================

import argparse
import itertools
import math
import pathlib
import signal
import sys
import time
import urllib.error
import urllib.request

YKI = "http://localhost:8000"
ZAMAN_ASIMI_S = 5.0

# ylp00 -> 1, ylp01 -> 2, ylp02 -> 3 (bkz. docs/cihazlar.md)
# 31 Temmuz: ylp02 DEVRE DISI — pusulasi 143 uT / std 63 okuyor (saglami
# 48 uT / std 1), kalibrasyon "unable to fit mag 0" ile basarisiz.
# Olcumle elenenler: kamera guc kablosu, ESP32 mesh yayini, hareket,
# yapilandirma farki. Bkz. src/gcs/pusula_olc.py
DRONELAR = [1, 2]

# --- Geometri ---------------------------------------------------------------
ARALIK_M = 12.0         # formasyonda komşu slotlar arası mesafe (lider-kanat)
KANAT_ACISI_DEG = 45.0  # ok başı kanat açısı (orchestrator wing_alpha ile aynı)
# Görev noktaları arası. Kenarı kısaltmak çarpışma marjını HİÇ etkilemiyor
# (ölçüldü: kritik an bacaklarda değil, P1'deki roll'lu rotasyonda oluşuyor)
# ama kaplanan alanı küçültüyor — yani sahaya sığdırmanın bedavaya gelen kolu.
# Gorev rotasinin YONU (pusula derecesi). 0 = ilk bacak KUZEYE.
# NEDEN VAR: kod BINALARI GOREMEZ. Engel algilama, harita, geofence yok —
# ucgeni onunde ne varsa ucar. Guvenlik tamamen rotanin acik alana
# denk gelmesine bagli. Bu yuzden rota dondurulebilir: acik alan
# doguya bakiyorsa --yon 90, guneye bakiyorsa --yon 180.
# SAHADA SECILDI (31 Temmuz): -90 = ilk bacak BATIYA. Acik alan o yonde.
# Varsayilan yapildi ki --yon vermeyi unutan bir kosu ucagi kuzeye,
# yani binalarin oldugu tarafa yollamasin.
ROTA_YONU_DEG = -90.0

KENAR_M = 18.0
TOLERANS_M = 2.5        # "vardı" yarıçapı
MAX_GOTO_M = 60.0       # tek goto için mesafe tavanı

# --- İrtifalar --------------------------------------------------------------
# KALKIS_IRTIFA_M agent_fsm_node'un target_altitude_m VARSAYILANIYLA (10.0)
# BİLEREK AYNI. Sebep ölçüldü: agent_fsm TAKEOFF durumuna girince px4_bridge'e
# kendi 'takeoff:10.0' komutunu yolluyor (agent_fsm_node.py:251). Farklı bir
# değer seçersek iki komut çakışır ve hangisinin kazandığı sıralamaya kalır.
KALKIS_IRTIFA_M = 10.0
# Görev (formasyon) irtifası — kalkış irtifasından AYRI. Roll manevrasında
# kanatlar merkezden dz = 0.408 x ARALIK_M kadar ayrılıyor; 10 m aralıkta
# ±4.1 m. Kalkış irtifası 10 m'de kalsaydı alttaki uçak 5.9 m'ye inerdi,
# manevra sırasında fazla alçak. 12 m'de yayılım 7.9 - 16.1 m arasında kalıyor.
GOREV_IRTIFA_M = 12.0
YENI_IRTIFA_M = 18.0    # P3'teki irtifa değişimi hedefi

# --- Manevra ----------------------------------------------------------------
# Şartname: sürü merkezi sabit, sağa/sola yatış. 30° seçildi çünkü 20°'de
# kanatlar merkezden yalnız ±2.7 m ayrılıyor ve yerden çekimde sınırda
# kalıyordu; 30°'de ±4.1 m'ye çıkıyor.
#
# SEZGİYE AYKIRI, DİKKAT: roll'u KÜÇÜLTMEK çarpışma marjını KÖTÜLEŞTİRİYOR.
# Ölçüldü (8 m aralıkta): roll 30° -> kritik an 4.13 m, roll 20° -> 3.26 m.
# Sebebi, roll'lu rotasyonda uçakları ayıran şeyin bir kısmının DİKEY ayrım
# olması ve onu roll'un üretmesi. "Daha az manevra = daha güvenli" burada
# yanlış; roll'u düşürürsen aralığı da büyütmen gerekir.
ROLL_ACISI_DEG = 30.0

# --- Çarpışma ---------------------------------------------------------------
# Uçaklar arası kabul edilen en küçük mesafe. Plan bunu ihlal ederse görev
# başlamaz. GPS hatası + pervane çapı + akış etkisi için bolca pay.
MIN_AYRIM_M = 4.0

# MAVLink GPS_FIX_TYPE. 5/6 = RTK; ancak orada konum hatasi cm mertebesine
# iner. Alttaki degerlerde metre mertebesinde hata var ve carpisma marji
# (5.16 m) bunu SOGURMAK zorunda kalir. RTK ENGEL DEGIL, uyari.
_FIX_ADI = {0: 'yok', 1: 'fixsiz', 2: '2D', 3: '3D', 4: 'DGPS',
            5: 'RTK-Float', 6: 'RTK-FIX'}

# --- Zamanlama (saniye) — 1 m/s'e göre; toplam 5 dk sınırına sığmalı --------
# Hız PX4'te: MPC_XY_VEL_MAX (31 Tem: 12 -> 1 -> 2 -> 4 m/s).
# 4 m/s'te bütçe: arm+kalkış ~30 + 4 bacak x 4.5 + manevralar ~25 +
# yerleşmeler ~48 + iniş (18 m / 0.7 m/s) ~26 =~ 150 s. Bol pay var.
#
# HIZ ARTTIKCA CARPISMA MARJI INCELIR: plan_dogrula KOMUT EDILEN geometriyi
# denetliyor, gercek ucusta hedefe yaklasirken frenleme mesafesi hizin
# KARESIYLE buyuyor. 3 drone senaryosunda kritik an 5.16 m; 4 m/s'te iki
# ucakta birden ~0.5 m asma olursa 4.2 m'ye iner (esik 4.0). Cok dronlu
# ucusta ya hizi 2'ye dondur ya ARALIK_M'i 12'ye cikar.
ARM_ASIM_S = 10
KALKIS_ASIM_S = 60
ADIM_ASIM_S = 70
YERLESME_S = 6.0        # YALNIZ manevra adimlarindan sonra (roll, rotasyon,
                        # formasyon, irtifa). Duz seyir bacaklarinda beklenmez:
                        # gosterilecek bir sey yok ve 5 dk sinirinda 24 sn yer actik.
GOREV_ASIM_S = 285

# AgentStatus.flight_mode degerleri (swarm_interfaces/msg/AgentStatus.msg)
# Bir rotasyonda yon kac derecelik dilimler halinde verilsin.
# NEDEN: OFFBOARD'da yon setpoint'i DOGRUDAN gecer; MPC_YAWRAUTO_MAX (25/s)
# yalniz Auto modlarda uygulanir, ic dongu tavani ise MC_YAWRATE_MAX=200/s.
# Yani 90'lik tek sicrama yarim saniyede donduruyor — sahada "ani donus"
# diye goruldu (31 Temmuz, ilk tam gorev). Dilimlere bolunce donus hem
# yumusuyor hem videoda rotasyon net gorunuyor (yonergenin sarti).
# MC_YAWRATE_MAX'e DOKUNULMADI: o ucagin toparlama yetenegi.
YAW_ADIM_DEG = 20.0
YAW_ADIM_BEKLE_S = 0.8

_MOD_OFFBOARD = 4
# Pilot modlari: MANUAL, ALTCTL, POSCTL, ACRO, STABILIZED. Bunlardan biri
# gorulurse kumandadan devralinmis demektir.
_PILOT_MODLARI = frozenset({1, 2, 3, 9, 10})

_iniyor = False
_HARITA_DOSYA = None


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


def yon_dilimle(bas: float, son: float):
    """Bastan sona EN KISA yonden, YAW_ADIM_DEG'lik ara yonler uretir.

    Son eleman her zaman tam hedef yondur. Fark kucukse bos doner
    (ara adim gereksiz).
    """
    fark = (son - bas + 180.0) % 360.0 - 180.0   # -180..180, en kisa yon
    if abs(fark) <= YAW_ADIM_DEG:
        return []
    n = int(abs(fark) // YAW_ADIM_DEG)
    return [(bas + fark * (i + 1) / (n + 1)) % 360.0 for i in range(n)]


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


def plan_dogrula(plan, baslangic=None) -> bool:
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

    # YERDEKI GERCEK KONUM da denetlenir. Bu adim olmadan "kalkis noktasindan
    # ilk formasyona gecerken kesisiyorlar mi" sorusu hic sorulmuyordu.
    if baslangic:
        plan = [("YER (gerçek konum)", 0.0, baslangic, False)] + list(plan)

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
def plan_kur(merkez0, baslangic=None):
    """Bütün görevi (etiket, hedefler) adımları olarak kurar.

    Uçmadan önce tamamı kurulur ki doğrulanabilsin. Noktalar kalkış
    merkezine GÖRELİ: P1=(K,0) P2=(K,K) P3=(0,K) — çapraz çarpım K^2 != 0,
    yani üçü doğrusal DEĞİL (yönergenin şartı).
    """
    K = KENAR_M
    # Ucgen once yerel eksende kurulur (ileri, saga), sonra ROTA_YONU_DEG
    # kadar dondurulur. Boylece sekil ve carpismasizlik aynen korunur,
    # yalniz sahadaki yonelim degisir.
    h = math.radians(ROTA_YONU_DEG)
    def _dondur(ileri, saga):
        return (merkez0[0] + ileri * math.cos(h) + saga * (-math.sin(h)),
                merkez0[1] + ileri * math.sin(h) + saga * math.cos(h))
    P1 = _dondur(K, 0.0)
    P2 = _dondur(K, K)
    P3 = _dondur(0.0, K)

    plan = []
    # ILK ADIMIN SLOT ATAMASI GERCEK YER KONUMUNA GORE. Onceden sabitti
    # (drone 1 -> lider, drone 2 -> kanat) ve ucaklar ters yerlestirilirse
    # kalkista BIRBIRLERININ ICINDEN geciyorlardi. Ustelik dogrulayici bunu
    # goremiyordu: yalnizca plan adimlari ARASINI denetliyor, yerdeki
    # gercek konumdan ilk adima gecisi denetlemiyordu.
    onceki = dict(baslangic) if baslangic else None
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
    # yeniden_ata=True: ucaklar en yakin slota gitsin, kesismesin.
    ekle("kalkis/okbasi", merkez0, y1, "okbasi", GOREV_IRTIFA_M, 0.0,
         yeniden_ata=bool(baslangic))
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


def _origin_bul(t):
    """Telemetriden NED origin'ini turetir.

    Drone hem lat/lon hem NED bildiriyor; ikisinin farki origin'i verir.
    Yapilandirmadaki sabiti okumaktansa bunu tercih ediyoruz: origin
    yanlis ayarlanmissa bile burada GERCEK donusum cikar, yani haritaya
    koydugumuz nokta ucagin gercekten gidecegi yer olur.
    """
    for d in t.values():
        if d.get("connected") and abs(d.get("lat", 0.0)) > 0.001:
            enlem = d["lat"] - d["pos_x"] / 111320.0
            boylam = d["lon"] - d["pos_y"] / (111320.0 * math.cos(math.radians(d["lat"])))
            return enlem, boylam
    return None


def ned_to_latlon(origin, kuzey, dogu):
    enlem = origin[0] + kuzey / 111320.0
    boylam = origin[1] + dogu / (111320.0 * math.cos(math.radians(origin[0])))
    return enlem, boylam


def koordinat_yaz(merkez0, origin):
    """Gorev noktalarini GPS olarak basar — haritada kontrol edilebilsin.

    NEDEN VAR: kod engel GORMEZ. Ucmadan once noktalari haritaya koyup
    bina/agac var mi diye BAKMAK, elimizdeki tek engel kontrolu.
    """
    if origin is None:
        print("\n=== GPS KOORDİNATLARI: origin türetilemedi (telemetri yok) ===")
        return
    K = KENAR_M
    h = math.radians(ROTA_YONU_DEG)

    def _d(ileri, saga):
        return (merkez0[0] + ileri * math.cos(h) + saga * (-math.sin(h)),
                merkez0[1] + ileri * math.sin(h) + saga * math.cos(h))

    noktalar = [("KALKIS/EV", merkez0), ("P1", _d(K, 0.0)),
                ("P2", _d(K, K)), ("P3", _d(0.0, K))]
    print("\n=== GPS KOORDİNATLARI (haritada kontrol et) ===")
    for ad, (kz, dg) in noktalar:
        la, lo = ned_to_latlon(origin, kz, dg)
        print(f"  {ad:<10} {la:.7f}, {lo:.7f}")
    la0, lo0 = ned_to_latlon(origin, *merkez0)
    print(f"\n  Haritada tek tek aç:")
    for ad, (kz, dg) in noktalar:
        la, lo = ned_to_latlon(origin, kz, dg)
        print(f"    {ad:<10} https://www.google.com/maps?q={la:.7f},{lo:.7f}")


_HARITA_SABLON = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>Yelpence — gorev rotasi</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#h{height:100%%;margin:0}
.bilgi{position:absolute;z-index:1000;top:10px;left:50px;background:#fff;
padding:8px 12px;font:13px system-ui;border-radius:6px;box-shadow:0 1px 6px #0006}
</style></head><body>
<div class="bilgi"><b>Görev rotası</b><br>%(ozet)s</div>
<div id="h"></div><script>
var m=L.map('h');
// maxNativeZoom 18 SART: bu bolgede Esri z19+ icin gercek goruntu yerine
// "Map data not available" yer tutucusu donduruyor (2521 bayt, olculdu).
// 18'de birakinca Leaflet z18 karosunu buyuterek gosteriyor.
var uydu=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
 {maxZoom:22,maxNativeZoom:18,attribution:'Esri'}).addTo(m);
var sokak=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
 {maxZoom:22,maxNativeZoom:19,attribution:'OpenStreetMap'});
L.control.layers({'Uydu':uydu,'Sokak (binalar)':sokak}).addTo(m);
var n=%(noktalar)s;
var yol=n.map(function(p){return [p[1],p[2]]});
L.polyline(yol.concat([yol[0]]),{color:'#ff3b30',weight:3}).addTo(m);
n.forEach(function(p){
  L.circleMarker([p[1],p[2]],{radius:8,color:'#fff',weight:2,
    fillColor:p[0]=='KALKIS/EV'?'#34c759':'#ff9500',fillOpacity:1})
   .addTo(m).bindTooltip(p[0],{permanent:true,direction:'top'});
});
L.circle([%(mlat)f,%(mlon)f],{radius:%(yaricap)f,color:'#ffcc00',
  fillOpacity:0.06,dashArray:'6 6'}).addTo(m);
m.fitBounds(L.latLngBounds(yol).pad(0.8),{maxZoom:20});
</script></body></html>
"""


def harita_yaz(merkez0, origin, dosya):
    """Gorev noktalarini UYDU goruntusu uzerinde tek haritaya yazar.

    NEDEN VAR: kod engel GORMEZ — harita, geofence, mesafe sensoru yok.
    Ucmadan once rotayi uydu goruntusune koyup bina/agac var mi diye
    BAKMAK, elimizdeki tek engel kontrolu. Ayri ayri koordinat linkleri
    bunun icin yetersizdi; hepsi tek karede gorunmeli.
    """
    if origin is None:
        print("  harita: origin türetilemedi, atlandı")
        return
    K = KENAR_M
    h = math.radians(ROTA_YONU_DEG)

    def _d(ileri, saga):
        return (merkez0[0] + ileri * math.cos(h) + saga * (-math.sin(h)),
                merkez0[1] + ileri * math.sin(h) + saga * math.cos(h))

    ham = [("KALKIS/EV", merkez0), ("P1", _d(K, 0.0)),
           ("P2", _d(K, K)), ("P3", _d(0.0, K))]
    noktalar = []
    for ad, (kz, dg) in ham:
        la, lo = ned_to_latlon(origin, kz, dg)
        noktalar.append([ad, la, lo])
    # Daire merkezi NOKTALARIN AGIRLIK MERKEZI. Onceden sabit (+K/2, +K/2)
    # sapmasiyla hesaplaniyordu ve ROTASYON UYGULANMIYORDU: rota donunce
    # kare donuyor ama daire eski yerinde kaliyordu.
    ort_k = sum(n[0] for _a, n in ham) / len(ham)
    ort_d = sum(n[1] for _a, n in ham) / len(ham)
    mla, mlo = ned_to_latlon(origin, ort_k, ort_d)
    ozet = (f"kenar {K:.0f} m &middot; yön {ROTA_YONU_DEG:.0f}° &middot; "
            f"irtifa {GOREV_IRTIFA_M:.0f}-{YENI_IRTIFA_M:.0f} m<br>"
            f"<b>kod engel görmez</b> — kırmızı rotada bina/ağaç olmamalı")
    import json as _j
    html = _HARITA_SABLON % {
        "noktalar": _j.dumps(noktalar), "ozet": ozet,
        "mlat": mla, "mlon": mlo, "yaricap": K * 0.75,
    }
    pathlib.Path(dosya).write_text(html, encoding="utf-8")
    print(f"\n=== HARİTA YAZILDI ===\n  {dosya}")
    print(f"  Tarayıcıda aç:  xdg-open {dosya}")


def ayak_izi_yaz(plan, merkez0):
    """Kalkis noktasina gore HANGI YONDE NE KADAR yer gerektigini yazar.

    NEDEN VAR: kod binalari, agaclari, direkleri GORMEZ. Ucusun guvenligi
    tamamen rotanin acik alana denk gelmesine bagli. Ucmadan once
    "kuzeye 22 m, doguya 24 m yer lazim" diye somut gormek gerekiyor;
    "18 m'lik ucgen" demek yetmiyor cunku formasyon sapmasi ve rotasyon
    ucaklari noktalarin OTESINE tasiyor.
    """
    k = [h[0] - merkez0[0] for _e, _h, hed, _b in plan for h in hed.values()]
    d = [h[1] - merkez0[1] for _e, _h, hed, _b in plan for h in hed.values()]
    z = [h[2] for _e, _h, hed, _b in plan for h in hed.values()]
    print("\n=== GEREKEN ALAN (kalkış noktasına göre) ===")
    print(f"  kuzey  : {max(k):+6.1f} m        güney  : {min(k):+6.1f} m")
    print(f"  doğu   : {max(d):+6.1f} m        batı   : {min(d):+6.1f} m")
    print(f"  irtifa : {min(z):.1f} - {max(z):.1f} m")
    print(f"  toplam kutu: {max(k)-min(k):.0f} m (K-G) x {max(d)-min(d):.0f} m (D-B)")
    print(f"  rota yönü  : {ROTA_YONU_DEG:.0f}°  (0=kuzey, 90=doğu)")
    print("  UYARI: kod engel GÖRMEZ. Bu kutunun içinde bina/ağaç/direk olmamalı.")


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
        # bekleme. Kumandadan müdahale edilirse (POSCTL, LAND, failsafe) o
        # uçak artık bizim setpoint'lerimizi izlemiyor; diğerlerini 70 sn
        # havada tutmanın anlamı yok.
        #
        # KARAR flight_mode ILE VERILIR, offboard_active ILE DEGIL.
        # offboard_active MESH'TEN GELMIYOR — esp32_bridge'in kendi yorumu:
        # "mesh'e CIKMAZ" (esp32_bridge_node.py:408, 1069). Bayrak hep False
        # kaliyor. 31 Temmuz'daki ilk canli ucusta tam bu yuzden YANLIS ALARM
        # verildi: telemetri "mode=Offboard, flight_mode=4" derken bayrak
        # False oldugu icin gorev 9.4 m'de kendini iptal etti ve saglam bir
        # ucus bosuna indirildi. flight_mode mesh pakette TASINIYOR ve dogru
        # geliyor.
        for did in DRONELAR:
            d = t.get(did)
            if d is None:
                continue
            fm = d.get("flight_mode", 0)
            if fm in _PILOT_MODLARI:
                print(f"\n      !!! drone {did} PİLOT KONTROLÜNDE "
                      f"(mod={d.get('mode')}) — görev durduruluyor")
                return False
            if fm != _MOD_OFFBOARD:
                print(f"\n      !!! drone {did} OFFBOARD'DAN ÇIKTI "
                      f"(mod={d.get('mode')}, flight_mode={fm}) — failsafe olabilir")
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
    rtk_yok = []
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
        fix = d["gps_fix_type"]
        print(f"  drone {did}: bagli={d['connected']} armed={d['armed']} mod={d['mode']} "
              f"GPS={_FIX_ADI.get(fix, fix)} sat={d['gps_satellites']} "
              f"pil={d['battery_percent']:.0f}% "
              f"NED=({d['pos_x']:+.1f},{d['pos_y']:+.1f})")
        if fix < 5:
            rtk_yok.append(did)
        if engel:
            print(f"           ENGEL: {', '.join(engel)}")
            tamam = False

    # RTK ENGEL DEGIL, UYARI. Gorev RTK olmadan da ucar: carpisma marji
    # (5.16 m) metre mertebesindeki GPS hatasini sogurecek sekilde secildi.
    # Ama RTK fix varsa hata cm'ye iner ve ayni plan cok daha rahat olur —
    # o yuzden ucmadan once gorulmesi gereken bir bilgi.
    if rtk_yok:
        print(f"\n  UYARI: RTK fix YOK (drone {', '.join(map(str, rtk_yok))}). "
              f"Konum hatasi metre mertebesinde olabilir.")
        print(f"  Plan yine de guvenli: en kritik an {MIN_AYRIM_M:.1f} m esiginin "
              "uzerinde tutuluyor. Ruzgar varsa RTK'yi beklemek daha iyi.")
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

    baslangic = {did: (t[did]["pos_x"], t[did]["pos_y"], KALKIS_IRTIFA_M)
                 for did in DRONELAR if did in t} or None
    plan = plan_kur(merkez0, baslangic)
    plan_yaz(plan)
    ayak_izi_yaz(plan, merkez0)
    _org = _origin_bul(t)
    koordinat_yaz(merkez0, _org)
    if _HARITA_DOSYA:
        harita_yaz(merkez0, _org, _HARITA_DOSYA)
    if not plan_dogrula(plan, baslangic):
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
    onceki_heading = None
    for i, (etiket, heading, hedefler, beklet) in enumerate(plan):
        print(f"\n=== [{i+1}/{len(plan)}] {etiket}   yön {heading:.0f}°   "
              f"(kalan {kalan():.0f}s) ===")
        t_durum = durum()

        # YON KADEMELI VERILIR. Tek sicrama yerine ara yonler; bkz.
        # YAW_ADIM_DEG yorumu. Konum degismez, yalniz burun doner.
        if onceki_heading is not None and not kuru:
            aralar = yon_dilimle(onceki_heading, heading)
            if aralar:
                print(f"      dönüş {onceki_heading:.0f}° -> {heading:.0f}° "
                      f"({len(aralar)} ara adım)")
                for ara in aralar:
                    for did in DRONELAR:
                        git(did, hedefler[did], ara, kuru, t_durum)
                    time.sleep(YAW_ADIM_BEKLE_S)
        onceki_heading = heading
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
    ap.add_argument("--harita", nargs="?", const="/tmp/yelpence_rota.html",
                    default=None, metavar="DOSYA",
                    help="rotayi uydu haritasina yaz (varsayilan /tmp/yelpence_rota.html)")
    ap.add_argument("--yon", type=float, default=None,
                    help="rota yonu (pusula derecesi). 0=kuzey, 90=dogu. "
                         "Acik alan hangi yondeyse onu ver.")
    ap.add_argument("--dronelar", default="1,2",
                    help="virgülle: 1,2 (prova) veya 1,2,3")
    a = ap.parse_args()
    DRONELAR = [int(x) for x in a.dronelar.split(",") if x.strip()]
    global ROTA_YONU_DEG, _HARITA_DOSYA
    if a.yon is not None:
        ROTA_YONU_DEG = a.yon
    _HARITA_DOSYA = a.harita

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
