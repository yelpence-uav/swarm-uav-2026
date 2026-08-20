#!/usr/bin/env python3
# =============================================================================
# UCUS AYARLARI — TEK KAYNAK
#
# Hiz, ivme, formasyon araligi ve egim tavanlari BURADA. Baska hicbir yerde
# elle yazilmaz.
#
# NEDEN: ayni sabitin iki yerde durmasi bu projede iki kez bedel odetti.
# Filo varsayilani hem backend hem frontend'deydi, biri guncellenip digeri
# unutuldu ve dusmus drone'a komut gitti. MPC_TILTMAX_AIR kodda "30" diye
# VARSAYILDI ama ylp00'da 45'ti ve gorev kendini havada iptal edebilirdi.
#
# ---------------------------------------------------------------------------
# NASIL KULLANILIR
#
#   python3 src/gcs/ucus_ayarlari.py           # cozumleme + tutarlilik denetimi
#   python3 src/gcs/ucus_ayarlari.py --kabuk   # baslat.sh icin env satirlari
#   python3 src/gcs/ucus_ayarlari.py --px4     # ros2 param set komutlari
#
# HIZI DEGISTIRMEK: asagidaki GIRDILER bolumunde tek sayiyi degistir, sonra
# betigi calistir. Gereken egim tavani, dedektor esigi, frenleme mesafesi ve
# carpisma payi KENDILIGINDEN hesaplanir ve tutarsizlik varsa soylenir.
# Aciyi elle ayarlamaya calisma — hesap zaten burada.
# =============================================================================

import argparse
import math
import sys

YERCEKIMI = 9.80665


# =============================================================================
# GIRDILER — elle degistirilecek yer YALNIZCA burasi
# =============================================================================

# --- Gorev seyir hizi -------------------------------------------------------
# Ucagin bir noktadan digerine giderken tuttugu hiz. px4_bridge'in yurutucusu
# uygular (guided_hiz_yatay_mps), PX4'un tavani DEGIL.
#
# 2.0 -> 3.0 (14 Agustos). 5.0 da mumkun: asagidaki tablo mevcut 12 m
# aralikla 6 m/s'e kadar yettigini gosteriyor. Hizi yukseltmeden once tek
# ucakla duz bir bacakta IZLEME GECIKMESINI olc ve IZLEME_GECIKME_S'i
# dogrula — o sabit 2 m/s'te olculdu, yuksek hizda dogrusalliktan sapabilir.
GOREV_HIZ_MPS = 3.0

# Yurutucunun ivme rampasi. Egim tavanini belirleyen sey BU, hiz degil.
# 1.5'te kaldi: 3. turda 0.8'e indirmek asimi %25'ten yalnizca %21'e cekti
# ve 3 sn ekledi (olculdu, bkz. baslat.sh).
GOREV_IVME_MPS2 = 1.5

# --- Dikey ------------------------------------------------------------------
GOREV_DIKEY_HIZ_MPS = 1.0      # motor isinmasi: daha yavas
GOREV_DIKEY_IVME_MPS2 = 1.0

# --- PX4 tavanlari ----------------------------------------------------------
# MPC_XY_VEL_MAX. Gorev seyir hizindan YUKSEK olmali:
#   * carpisma kacinmasinin kacis manevrasi bu tavandan yararlaniyor;
#     seyir hizina esitlersek kacis da o hiza iner ve itme yetersiz kalir
#   * ayni parametre kumandadaki POSCTL'i de sinirlar
PX4_HIZ_TAVANI_MPS = 5.0

# MPC_VEL_MANUAL — kumandayla POSCTL'de cubuk sonuna basildigindaki hiz.
# 14 Agustos'ta ylp00=4, ylp02=2 olctuk: ayni cubuk hareketi iki ucakta
# farkli hiz uretiyordu. Operatorun kas hafizasi biri icin yanlis.
KUMANDA_HIZI_MPS = 3.0

# MPC_ACC_HOR — PX4'un kendi yatay ivme siniri. Yurutucu ivmesinin USTUNDE
# olmali, yoksa PX4 yurutucuyu takip edemez.
PX4_IVME_MPS2 = 2.0

# MPC_YAWRAUTO_MAX — Auto modlarindaki donus hizi tavani.
#
# UCUSU DOGRUDAN ETKILEMIYOR: rotasyonlarimiz OFFBOARD'da yapiliyor ve orada
# gecerli olan MC_YAWRATE_MAX (200 deg/s). Ama 14 Agustos'ta ylp00=45,
# ylp02=25 olctuk ve gorev_kanit_ucus.py uc yerde 25 VARSAYIYOR. Ucaklar
# arasi ayrisma birakmamak icin burada.
PX4_DONUS_HIZI_DEG_S = 25.0

# --- Formasyon --------------------------------------------------------------
# Komsu slotlar arasi mesafe. Kritik ayrim buna DOGRUDAN oranli
# (kritik = ARALIK x cos(kanat acisi)), yani carpisma payinin ana kaldiraci.
#
# 10.0 -> 12.0 (14 Agustos): hiz 3.0'a cikarken pay genisletildi.
# 12 m su anki modelle 6 m/s'e kadar yetiyor (bkz. gereken_aralik_m).
#
# BEDELI: rotasyon yaylari orantili uzuyor — takipci lider etrafinda ARALIK
# yaricapinda doner, yani yay boyu aralikla dogru orantili.
#
# SURU ENTEGRASYONUNDA: bu deger formation_node'un slot geometrisiyle AYNI
# olmali. Su an YKI plani uretiyor; formation_node devreye girince ayni sayi
# oraya da gecmeli, yoksa iki taraf farkli geometri kurar.
ARALIK_M = 12.0
KANAT_ACISI_DEG = 45.0         # ok basi kanat acisi

# --- Guvenlik ---------------------------------------------------------------
MIN_AYRIM_M = 4.0              # ucaklar arasi kabul edilen en kucuk mesafe
TOLERANS_M = 1.0               # "vardi" yaricapi

# EGIM PAY KATI — egim tavani, komut edilen en buyuk ivmenin KAC KATINI
# karsilayabilmeli.
#
# 2.0 secildi: ivmenin tamami kullanilirken geri kalan yarisi ruzgara,
# bozulmadan toparlanmaya ve kacinma itmesine kalir. 1.0 yapmak "tam gaz
# giderken ruzgar esmesin" demek olurdu.
EGIM_PAY_KATI = 2.0

# EGIM TAVANI TABANI — formul ne derse desin bunun altina inilmez.
#
# NEDEN GEREKLI: yukaridaki hesap yalnizca BIZIM KOMUT ETTIGIMIZ ivmeyi
# sayiyor. Ruzgari saymiyor. Ucak havada asili dururken bile ruzgarin
# suruklemesini yenmek icin egilmek zorunda; 10 m/s ruzgarda bu 1.5-2.5 m/s²
# tuketebilir. Salt formule birakirsak (2.0 m/s² x2 = 25°) ruzgarli gunde
# konum tutamayacak bir tavan cikiyor.
#
# 30° = 5.66 m/s². Komut ettigimiz 2.0'i cikarinca ruzgar ve toparlanmaya
# 3.66 m/s² kaliyor. PX4 varsayilani 45° (9.81 m/s²) ama o kadarina ihtiyac
# yok ve yuksek tavan yere yakin sert duzeltme demek — 1 Agustos'ta kalkista
# devrilme yasandi.
EGIM_TAVANI_TABAN_DEG = 30.0

# DEDEKTOR PAYI — MAKS_EGIM_DEG, egim tavaninin bu kadar USTUNDE olur.
#
# NEDEN USTUNDE OLMAK ZORUNDA: MAKS_EGIM_DEG bir DEVRILME DEDEKTORU.
# Mantigi "PX4 asla MPC_TILTMAX_AIR'dan fazlasini komut etmez, o halde
# fazlasini goruyorsam fiziksel bir sey ters gitmistir". Esik tavanin
# ALTINDA kalirsa normal ucus ariza sayilir ve gorev kendini havada iptal
# eder — 14 Agustos'ta ylp00'da tam bu durum vardi (tavan 45, esik 35).
DEDEKTOR_PAY_DEG = 5.0


# =============================================================================
# TURETILENLER — elle degistirme, hesaplanir
# =============================================================================

def egim_icin(ivme_mps2: float) -> float:
    """Verilen yatay ivme icin gereken egim (derece).

    Cok rotorlu ucak egilerek hizlanir: itki vektoru yana yatar ve yatay
    bileseni ivme uretir.  a = g * tan(egim)
    """
    return math.degrees(math.atan(ivme_mps2 / YERCEKIMI))


def ivme_icin(egim_deg: float) -> float:
    """Verilen egim tavaninin sagladigi en buyuk yatay ivme."""
    return YERCEKIMI * math.tan(math.radians(egim_deg))


def frenleme_m(hiz_mps: float, ivme_mps2: float) -> float:
    """Frenleme mesafesi — "tam hizda durmam gerekse kac metrede dururum".

    KACINMA icin anlamli (kacis manevrasinda gercekten fren yapilir).
    FORMASYON AYRIMI icin DEGIL — bkz. izleme_gecikmesi_m.
    """
    return hiz_mps ** 2 / (2.0 * ivme_mps2)


# IZLEME GECIKMESI ZAMAN SABITI — ⚠️ DOGRULANMAMIS, muhtemelen KARAMSAR.
#
# Tek olcumden turetildi: 2 Agustos, 2 m/s'te 0.44 m -> 0.44/2.0 = 0.22 s.
# AMA o olcum 7 METRELIK bir bacakta alindi ve kodun kendi notu "7 m'lik
# gecisin neredeyse tamami gecici rejim" diyor. Yani olculen sey SEYIR
# kaymasi degil, HIZLANMA fazinin artigi.
#
# TEORI SIFIR DIYOR: yurutucu PX4'e hiz ileri-beslemesi veriyor, yani
#     v = Kp x hata + v_ff   ve   v_ff = v   ->   hata = 0
# Kalici halde kayma olmamali ve hizla BUYUMEMELI.
# Ayrinti ve olcum sonuclari: docs/PLAN.md §9
#
# Bu sabit o olcum yapilana kadar GUVENLI TARAFTA kalmak icin duruyor;
# ayrim payini gereginden genis tutuyor. Olcum sonrasi guncellenecek.
#
# NEDEN FRENLEME MESAFESI DEGIL: formasyonda ucaklar birbirine dogru tam
# hizla gidip fren yapmiyor, planlanmis bir yorungeyi izliyorlar. Ayrimi
# yiyen sey ucagin hedefinden ne kadar GERI KALDIGI. Ilk surumde buraya
# frenleme mesafesi konmustu ve 5 m/s icin 17 m aralik cikariyordu —
# gercek gecikmenin yedi kati, asiri muhafazakar. Duzeltildi.
#
# Gecikme hizla DOGRUSAL buyur (hizin karesiyle degil), cunku yurutucuda
# hiz ileri-beslemesi var; kalan hata orantili terimden geliyor.
IZLEME_GECIKME_S = 0.22

# Gecikmenin kac kati pay birakilir. 3.0: iki ucak birbirine dogru
# gecikebilir (2x) ve uzerine ruzgar/olcum payi.
IZLEME_PAY_KATI = 3.0


def izleme_gecikmesi_m(hiz_mps: float) -> float:
    """Ucagin yuruyen setpoint'in ne kadar gerisinde kaldigi."""
    return hiz_mps * IZLEME_GECIKME_S


def gereken_aralik_m(hiz_mps: float) -> float:
    """Bu hizda MIN_AYRIM'i korumak icin gereken formasyon araligi."""
    pay = IZLEME_PAY_KATI * izleme_gecikmesi_m(hiz_mps)
    return (MIN_AYRIM_M + pay) / math.cos(math.radians(KANAT_ACISI_DEG))


# En buyuk komut edilen ivme: yurutucu ile PX4'un kendi sinirinin buyugu.
EN_BUYUK_IVME_MPS2 = max(GOREV_IVME_MPS2, PX4_IVME_MPS2)

# Gereken egim + pay kati -> onerilen MPC_TILTMAX_AIR.
GEREKEN_EGIM_DEG = egim_icin(EN_BUYUK_IVME_MPS2)
EGIM_TAVANI_DEG = max(
    EGIM_TAVANI_TABAN_DEG,
    math.ceil(egim_icin(EN_BUYUK_IVME_MPS2 * EGIM_PAY_KATI) / 5.0) * 5.0,
)

# TIPIK BACAK BOYU — yalnizca bilgi amacli, plani BAGLAMAZ.
#
# "Bu hiza gercekten ulasiliyor mu" sorusuna bakmak icin. Suru entegrasyonu
# ilerledikce navigasyonu formation_node ve gorev orkestratoru surecek;
# bacak boylari o zaman degisecek. Bu sayi bir VARSAYIM degil, tablodaki
# "seyir payi" sutununu doldurmak icin bir ornek.
TIPIK_BACAK_M = 20.0

# Devrilme dedektoru esigi. gorev_kanit_ucus.py bunu MAKS_EGIM_DEG olarak alir.
MAKS_EGIM_DEG = EGIM_TAVANI_DEG + DEDEKTOR_PAY_DEG

# ---------------------------------------------------------------------------
# ROTA SEKILLENDIRME (path_planner) — 15 Agustos'ta buraya baglandi
#
# path_planner "en kisa yol" bulmuyor; rota zaten belli. Yaptigi is hedefi
# ucagin izleyebilecegi hiza YAYMAK: merkez rampasi + donus rampasi. Bu
# olmadan formation_node her yeni hedefte buyuk bir konum hatasi gorur ve
# hiz komutunu tavana dayar.
#
# NEDEN BURADA: baslat.sh path_planner'a HIC parametre gecmiyordu, dugum
# kendi gomulu varsayilanlariyla kosuyordu. Ayni sinifin hatasi 2 Agustos'ta
# yasanmisti — merkez 3.0 ile kosarken formation_node'un slot rampasi 1.0'da
# tavan yapiyordu, iki sayi birbirinden habersizdi ve suru merkezin gerisinde
# kaliyordu (bacak basina 5 -> 12.5 -> 20.4 m).

# Donus sirasinda KANATTAKI ucagin tegetsel hizi. Formasyon donerken en hizli
# hareket eden odur: hiz = aci_hizi x kanat_yaricapi. Seyrin YARISI seciliyor;
# kalan yari donus sirasinda formasyonu tutan duzeltmelere (ruzgar, komsu,
# carpisma kacinma) pay birakiyor.
ROT_TEGET_HIZ_MPS = GOREV_HIZ_MPS / 2.0

# Ayni mantik ivme icin. Donus yumusak baslasin/bitsin diye (ease-in/out).
ROT_TEGET_IVME_MPS2 = GOREV_IVME_MPS2 / 2.0

# Formasyon heading'inin en hizli donus hizi. Ust sinir; asil sinir yukaridaki
# tegetsel hizdan formasyon boyutuna gore turetiliyor (buyuk formasyon -> daha
# yavas donus). Burada PX4'un kendi yaw tavanini asmiyoruz: uclar donus
# sirasinda burnunu da cevirmek zorunda kalirsa PX4 yetisemezse formasyon
# bozulur.
MAKS_HEADING_DONUS_DEG_S = PX4_DONUS_HIZI_DEG_S

# Rota adim hizi (path_planner ara nokta uretim frekansi). formation_node
# 20 Hz'de setpoint uretiyor; 5 Hz ara nokta yeterli, arasini SVT dolduruyor.
ROTA_ADIM_HZ = 5.0

# Ok basi geciside iki ucak en cok bu kadar yaklasir.
KRITIK_AYRIM_M = ARALIK_M * math.cos(math.radians(KANAT_ACISI_DEG))
CARPISMA_PAYI_M = KRITIK_AYRIM_M - MIN_AYRIM_M

# --- KACINMA ESIKLERI -------------------------------------------------------
# 15 AGUSTOS'TA BULUNDU — dogrudan bu dosyanin basligindaki hatanin ta kendisi.
# `basit_kacinma` dugumu d0=8.0 / hard=4.0 ile geliyordu, ama `baslat.sh`
# `${KACINMA_D0:-6.0}` / `${KACINMA_HARD:-3.0}` geciyordu ve bu iki degiskeni
# HIC KIMSE uretmiyordu. Yani ucaklar 6.0/3.0 ile ucuyordu ve kimse bilmiyordu.
#
# NEDEN ONEMLI: hard = tam kuvvet itmenin basladigi mesafe. 3.0 ile bu,
# MIN_AYRIM_M'in (4.0) ALTINDA kaliyor — koruma devreye girdiginde kabul
# edilen sinir zaten asilmis oluyor. Dugumun kendi varsayilani (4.0) dogruydu.
#
# TUREME: hard tam olarak MIN_AYRIM — sinira degdigi an tam kuvvet.
#
# d0 ONCE 2.0 x MIN_AYRIM (8.0) IDI, 1.5'e (6.0) CEKILDI — 20 Agustos 2026,
# operator karari. Sebep 18 Agustos'ta olculdu: 12 m aralikta formasyonun
# PLANLI en yakin yaklasmasi 8.49 m. d0=8.0 ile pay yalnizca 0.49 m kaliyor,
# yani kacinma NORMAL formasyon gecisinde tetiklenir ve formasyonla cekisir.
# 6.0 ile pay 2.49 m.
#
# Iki ayri ariza bicimi var ve ikisi de gercek:
#   hard < MIN_AYRIM  -> koruma GEC kaliyor (sinir asildiktan sonra tam kuvvet)
#   d0   ~ formasyon  -> koruma FAZLA calisiyor (normal ucusta tetikleniyor)
# hard'i MIN_AYRIM'e, d0'i 1.5 katina baglamak ikisini birden cozuyor.
# Bedeli: rampa 4.0 m yerine 2.0 m (3 m/s'te 1.33 s yerine 0.67 s). Dar ama
# yeterli; ilk iki ucakli ucusta kayittan itmenin ne zaman basladigi olculecek.
KACINMA_HARD_M = MIN_AYRIM_M
KACINMA_D0_M = 1.5 * MIN_AYRIM_M

# Komsu verisi bu suredan eskiyse YOK SAYILIR. Mesh ~5-7 Hz ve ~%30 kayipli;
# 0.5 s penceresi iki-uc ardisik kayipta komsuyu dusurur ve kacinma SESSIZCE
# korumasiz kalir. 1.5 s `basit_kacinma`nin sahada kosan degeri
# (basit_kacinma_node.py:146) — `collision_avoidance` varsayilani 0.5 idi,
# yani ucte biri. Ikisi ayni degeri kullanmali, yoksa dugum degistirince
# kacinmanin gorus alani sessizce degisir.
KACINMA_BAYAT_S = 1.5

FRENLEME_GOREV_M = frenleme_m(GOREV_HIZ_MPS, GOREV_IVME_MPS2)
FRENLEME_TAVAN_M = frenleme_m(PX4_HIZ_TAVANI_MPS, PX4_IVME_MPS2)


# =============================================================================
# DENETIM
# =============================================================================

def denetle():
    """(uyarilar, hatalar) doner. Hata varsa yapilandirma tutarsiz."""
    uyari, hata = [], []

    # KACINMA ESIKLERI vs FORMASYON GEOMETRISI (KARAR-01 uyarisi)
    #
    # d0, itmenin BASLADIGI mesafe. Ok basi geciside iki ucak zaten
    # KRITIK_AYRIM_M kadar yaklasiyor. d0 ondan buyukse kacinma NORMAL
    # formasyon geciside tetiklenir ve formasyonla cekisir — carpisma
    # olmadigi halde surekli itilme olur.
    if KACINMA_D0_M >= KRITIK_AYRIM_M:
        uyari.append(
            f'kacinma d0 ({KACINMA_D0_M:.1f} m) formasyonun en yakin '
            f'yaklasmasindan ({KRITIK_AYRIM_M:.2f} m) BUYUK — kacinma normal '
            f'gecislerde tetiklenir. ARALIK_M buyut ya da d0 kucult.')
    elif KRITIK_AYRIM_M - KACINMA_D0_M < 1.0:
        uyari.append(
            f'kacinma d0 ({KACINMA_D0_M:.1f} m) ile formasyonun en yakin '
            f'yaklasmasi ({KRITIK_AYRIM_M:.2f} m) arasinda yalniz '
            f'{KRITIK_AYRIM_M - KACINMA_D0_M:.2f} m pay var. Ilk ucusta '
            f'kayittan kacinmanin NE ZAMAN tetiklendigine bak (KARAR-01).')

    # hard, tam kuvvetin basladigi mesafe. MIN_AYRIM'in altina duserse
    # koruma ancak sinir asildiktan SONRA tam guce ciker.
    if KACINMA_HARD_M < MIN_AYRIM_M:
        hata.append(
            f'kacinma hard ({KACINMA_HARD_M:.1f} m) MIN_AYRIM_M '
            f'({MIN_AYRIM_M:.1f} m) ALTINDA — tam kuvvet itme, kabul edilen '
            f'sinir asildiktan sonra basliyor.')
    if not KACINMA_HARD_M < KACINMA_D0_M:
        hata.append(
            f'kacinma hard ({KACINMA_HARD_M:.1f}) < d0 ({KACINMA_D0_M:.1f}) '
            f'olmali — collision_avoidance bu sartI kendi de dogruluyor.')

    # DOYGUNLUK PAYI — KAYMANIN SIFIR KALMASININ TEK SARTI.
    #
    # Kalici kaymanin sifir olmasi "v_ff + Kp x hata" toplaminin
    # MPC_XY_VEL_MAX tavanini ASMAMASINA bagli. Seyir hizi tavana esitse
    # konum duzeltmesine HIC yer kalmaz: PX4 kirpar, hata kapanamaz ve
    # kayma geri gelir.
    #     seyir 3.0 / tavan 5.0  -> duzeltmeye 2.0 m/s pay   iyi
    #     seyir 5.0 / tavan 5.0  -> duzeltmeye 0 pay         kayma garanti
    # Bkz. docs/PLAN.md §9 (doygunluk payi). Bu yuzden UYARI degil HATA.
    if PX4_HIZ_TAVANI_MPS < GOREV_HIZ_MPS * 1.5:
        hata.append(
            f'PX4 tavani ({PX4_HIZ_TAVANI_MPS}) gorev hizinin '
            f'({GOREV_HIZ_MPS}) en az 1.5 katI olmali '
            f'(su an {PX4_HIZ_TAVANI_MPS / GOREV_HIZ_MPS:.2f}x). '
            f'Konum duzeltmesine pay kalmazsa KAYMA geri gelir; '
            f'ayrica kacinmanin kacis manevrasi icin de yer gerekiyor. '
            f'Tavani {GOREV_HIZ_MPS * 1.5:.1f} yap ya da hizi dusur.')

    if PX4_IVME_MPS2 < GOREV_IVME_MPS2:
        hata.append(
            f'MPC_ACC_HOR ({PX4_IVME_MPS2}) yurutucu ivmesinden '
            f'({GOREV_IVME_MPS2}) kucuk — PX4 yurutucuyu takip edemez')

    if CARPISMA_PAYI_M <= 0:
        hata.append(
            f'kritik ayrim ({KRITIK_AYRIM_M:.2f} m) esigin '
            f'({MIN_AYRIM_M} m) ALTINDA — plan dogrulamayi gecmez')
    elif ARALIK_M < gereken_aralik_m(GOREV_HIZ_MPS):
        uyari.append(
            f'aralik {ARALIK_M:.1f} m, bu hizda gereken '
            f'{gereken_aralik_m(GOREV_HIZ_MPS):.1f} m. ARALIK_M buyut ya da '
            f'hizi dusur.')

    if MAKS_EGIM_DEG <= EGIM_TAVANI_DEG:
        hata.append(
            'devrilme dedektoru esigi egim tavaninin altinda — normal ucus '
            'ariza sayilir ve gorev kendini havada iptal eder')

    if TOLERANS_M < izleme_gecikmesi_m(GOREV_HIZ_MPS) * 1.5:
        uyari.append(
            f'varis tolerans {TOLERANS_M} m, izleme gecikmesi '
            f'{izleme_gecikmesi_m(GOREV_HIZ_MPS):.2f} m — ucak "vardim" '
            f'demeden once uzun sure salinabilir')

    return uyari, hata


# =============================================================================
# CIKTILAR
# =============================================================================

def _cozumleme() -> int:
    g = '\033[32m'; k = '\033[31m'; s = '\033[33m'; kl = '\033[1m'; z = '\033[0m'
    if not sys.stdout.isatty():
        g = k = s = kl = z = ''

    print(f'\n{kl}=== UCUS AYARLARI ==={z}\n')
    print(f'{kl}GIRDILER{z}')
    print(f'  gorev seyir hizi      {GOREV_HIZ_MPS:6.2f} m/s')
    print(f'  gorev ivmesi          {GOREV_IVME_MPS2:6.2f} m/s²')
    print(f'  dikey hiz             {GOREV_DIKEY_HIZ_MPS:6.2f} m/s')
    print(f'  PX4 hiz tavani        {PX4_HIZ_TAVANI_MPS:6.2f} m/s   (MPC_XY_VEL_MAX)')
    print(f'  kumanda POSCTL hizi   {KUMANDA_HIZI_MPS:6.2f} m/s   (MPC_VEL_MANUAL)')
    print(f'  PX4 ivme siniri       {PX4_IVME_MPS2:6.2f} m/s²  (MPC_ACC_HOR)')
    print(f'  formasyon araligi     {ARALIK_M:6.2f} m')
    print(f'  en kucuk ayrim        {MIN_AYRIM_M:6.2f} m')

    print(f'\n{kl}TURETILEN ACILAR{z}')
    print(f'  en buyuk komut ivmesi {EN_BUYUK_IVME_MPS2:6.2f} m/s²'
          f'  -> gereken egim {GEREKEN_EGIM_DEG:.1f}°')
    print(f'  pay kati x{EGIM_PAY_KATI:.1f}'
          f'            -> {kl}MPC_TILTMAX_AIR = {EGIM_TAVANI_DEG:.0f}°{z}'
          f'  ({ivme_icin(EGIM_TAVANI_DEG):.2f} m/s² saglar)')
    print(f'  dedektor payi +{DEDEKTOR_PAY_DEG:.0f}°'
          f'         -> {kl}MAKS_EGIM_DEG = {MAKS_EGIM_DEG:.0f}°{z}')

    print(f'\n{kl}MESAFELER{z}')
    print(f'  izleme gecikmesi      {izleme_gecikmesi_m(GOREV_HIZ_MPS):6.2f} m'
          f'   (olculdu: {IZLEME_GECIKME_S} s x hiz)')
    print(f'  kritik ayrim          {KRITIK_AYRIM_M:6.2f} m'
          f'   (= aralik x cos{KANAT_ACISI_DEG:.0f}°)')
    _ger = gereken_aralik_m(GOREV_HIZ_MPS)
    pay_renk = g if ARALIK_M >= _ger else s
    print(f'  {pay_renk}carpisma payi         {CARPISMA_PAYI_M:6.2f} m{z}'
          f'   (kritik - esik; bu hizda gereken aralik {_ger:.1f} m)')
    print(f'  frenleme (kacinma)    {FRENLEME_TAVAN_M:6.2f} m'
          f'   (PX4 tavaninda, kacis manevrasi icin)')

    # ROTA SEKILLENDIRME — fiili donus hizi formasyon BOYUTUNDAN turiyor.
    # Kanattaki ucak en hizli hareket eden; aci_hizi = teget_hiz / yaricap.
    # Bu yuzden ayni ayarla 12 m formasyon 4 m'lik olandan cok daha yavas
    # doner. Operatorun gorecegi sayi bu, parametre degil.
    _yaricap = ARALIK_M
    _fiili_donus = min(MAKS_HEADING_DONUS_DEG_S,
                       math.degrees(ROT_TEGET_HIZ_MPS / _yaricap))
    print(f'\n{kl}ROTA SEKILLENDIRME{z}  (path_planner)')
    print(f'  merkez rampa hizi     {GOREV_HIZ_MPS:6.2f} m/s')
    print(f'  teget hiz (kanat)     {ROT_TEGET_HIZ_MPS:6.2f} m/s'
          f'   (seyrin yarisi, kalan yari duzeltmelere pay)')
    print(f'  donus tavani          {MAKS_HEADING_DONUS_DEG_S:6.1f} deg/s'
          f'   (PX4 yaw tavaniyla ayni)')
    print(f'  FIILI donus hizi      {_fiili_donus:6.2f} deg/s'
          f'   ({ARALIK_M:.0f} m yaricapta)')
    print(f'  180 derece donus      {180.0 / _fiili_donus:6.1f} s')

    print(f'\n{kl}HIZ SECENEKLERI{z}  (aralik {ARALIK_M:.0f} m)')
    print(f'  {"hiz":>5}  {"gecikme":>8}  {"gereken aralik":>15}  durum')
    for v in (2.0, 3.0, 4.0, 5.0, 6.0):
        gec = izleme_gecikmesi_m(v)
        ger = gereken_aralik_m(v)
        if ger > ARALIK_M:
            d, r = f'aralik {ger:.1f} m olmali', s
        else:
            d, r = 'yeterli', g
        im = ' <-' if abs(v - GOREV_HIZ_MPS) < 0.01 else '   '
        print(f'  {v:5.1f}  {gec:7.2f} m  {ger:14.1f} m  {r}{d}{z}{im}')
    rampa = GOREV_HIZ_MPS ** 2 / GOREV_IVME_MPS2
    print(f'\n  Bilgi: {GOREV_HIZ_MPS:.1f} m/s\'e hizlanip yavaslamak '
          f'{rampa:.1f} m suruyor.')
    print(f'  {TIPIK_BACAK_M:.0f} m\'lik bir bacakta '
          f'{max(0.0, TIPIK_BACAK_M - rampa):.1f} m seyir kaliyor '
          f'(bacak boyu senaryoya gore degisir).')

    uyari, hata = denetle()
    print()
    for h in hata:
        print(f'{k}HATA : {h}{z}')
    for u in uyari:
        print(f'{s}UYARI: {u}{z}')
    if not hata and not uyari:
        print(f'{g}Yapilandirma tutarli.{z}')
    print()
    return 1 if hata else 0


def _kabuk():
    """baslat.sh'in kaynak alabilecegi env satirlari."""
    print('# ucus_ayarlari.py tarafindan URETILDI — elle degistirme.')
    print('# Degisiklik icin src/gcs/ucus_ayarlari.py duzenle ve yeniden uret.')
    print(f'GUIDED_HIZ_YATAY={GOREV_HIZ_MPS}')
    print(f'GUIDED_HIZ_DIKEY={GOREV_DIKEY_HIZ_MPS}')
    print(f'GUIDED_IVME_YATAY={GOREV_IVME_MPS2}')
    print(f'GUIDED_IVME_DIKEY={GOREV_DIKEY_IVME_MPS2}')
    print(f'KANAT_ALFA_DEG={KANAT_ACISI_DEG}')
    # path_planner (rota sekillendirme)
    print(f'ROTA_MAKS_HIZ={GOREV_HIZ_MPS}')
    print(f'ROTA_ADIM_HZ={ROTA_ADIM_HZ}')
    print(f'ROTA_DONUS_TAVANI_DEG_S={MAKS_HEADING_DONUS_DEG_S}')
    print(f'ROTA_TEGET_HIZ={ROT_TEGET_HIZ_MPS}')
    print(f'ROTA_TEGET_IVME={ROT_TEGET_IVME_MPS2}')
    # Kacinma — basit_kacinma VE collision_avoidance ayni degerleri alir.
    # Dugum degistiginde esikler degismesin diye tek kaynak burasi.
    print(f'KACINMA_D0={KACINMA_D0_M}')
    print(f'KACINMA_HARD={KACINMA_HARD_M}')
    print(f'KACINMA_BAYAT_S={KACINMA_BAYAT_S}')


def _px4():
    """Her ucakta calistirilacak parametre komutlari."""
    print('# Her ucak icin <N> yerine agent_id koy (ylp00->1, ylp01->2, ylp02->3)')
    print('# MAV_SYS_ID BURADA YOK — ucaga OZGU olmali, esitlenmez.')
    for ad, deger in (
            ('MPC_XY_VEL_MAX', f'{PX4_HIZ_TAVANI_MPS:.1f}'),
            ('MPC_VEL_MANUAL', f'{KUMANDA_HIZI_MPS:.1f}'),
            ('MPC_ACC_HOR', f'{PX4_IVME_MPS2:.1f}'),
            ('MPC_TILTMAX_AIR', f'{EGIM_TAVANI_DEG:.1f}'),
            ('MPC_YAWRAUTO_MAX', f'{PX4_DONUS_HIZI_DEG_S:.1f}'),
    ):
        print(f'ros2 param set /drone_<N>/mavros/param {ad} {deger}')


def main() -> int:
    ap = argparse.ArgumentParser(description='Ucus ayarlari — tek kaynak')
    ap.add_argument('--kabuk', action='store_true', help='baslat.sh icin env')
    ap.add_argument('--px4', action='store_true', help='ros2 param set komutlari')
    a = ap.parse_args()
    if a.kabuk:
        _kabuk()
        return 0
    if a.px4:
        _px4()
        return 0
    return _cozumleme()


if __name__ == '__main__':
    sys.exit(main())
