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

# PX4'un KENDI dikey tavanlari — 23 Agustos 2026'da UCAKTAN OKUNDU.
#
# 🔴 NEDEN BURADA: dikey yol verme (carpisma kacinmasi) dikey hiz komutu
# veriyor ve PX4 bu tavanin ustunu SESSIZCE KIRPIYOR. Kacinmaya 3.0 m/s
# yazip PX4'te 1.2 birakmak, ayarda ve logda 3.0 gorunurken ucagin 1.2 ile
# tirmanmasi demek — bu depoda MPC_TILTMAX_AIR ile bire bir ayni tuzak
# yasandi (kodda 30 varsayildi, ylp00'da 45'ti).
#
# OLCULEN (iki ucakta da ayni):
#     MPC_Z_VEL_MAX_UP  1.2    MPC_ACC_UP_MAX    4.0
#     MPC_Z_VEL_MAX_DN  1.5    MPC_ACC_DOWN_MAX  3.0
#
# 1.2 dusuk bir deger ve bilincli secilmis gorunuyor (gorev dikey hizi 1.0,
# "motor isinmasi" notu). Yukseltmek AYRI bir karar: kalkis ve gorev
# tirmanislarini da etkiler ve itki payi hala olculmedi.
PX4_DIKEY_HIZ_TAVANI_MPS = 1.2
PX4_DIKEY_INIS_TAVANI_MPS = 1.5
PX4_DIKEY_IVME_TAVANI_MPS2 = 4.0
PX4_DIKEY_INIS_IVME_TAVANI_MPS2 = 3.0

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
# =============================================================================
# 🔀 23 AGUSTOS 2026 — DIKEY YOL VERMEYE GECILDI, ESIKLERIN ANLAMI DEGISTI
# =============================================================================
# Yukaridaki turetme YATAY itme icin dogruydu: tek savunma yatay itmeyken
# `hard` "kabul edilen sinira degdigimiz an tam kuvvet" demekti.
#
# Artik birincil kacis DIKEY (operator karari): catisan ucaklardan kimligi
# buyuk olan, kucuk olanin olculen irtifasindan KATMAN kadar uzaga gider.
# Yatay itme SON CARE olarak, yalnizca `hard` kabugunun icinde aciliyor.
# Bu iki esigin anlamini degistirdi:
#
#   d0   = DIKEY manevranin BASLADIGI mesafe (yatay itme DEGIL)
#   hard = dikey yetisememisse YATAY itmenin acildigi kabuk
#
# d0 = 4.0 SABIT — operator karari. Sartname ajanlar arasi mesafeyi
# hakemlere birakiyor (3-10 m, calisma aninda QR ile geliyor) ve operator
# aksiyonun 4 m'de baslamasini istedi. Araliga BAGLANMADI: hakem 5 m'nin
# altini secerse kacinma surekli tetikli olur — davranis dogru ama
# collision_avoidance_node bunu UYARI olarak logluyor, sessiz kalmiyor.
#
# hard = 2.5 — dikey katman 3.0 m oldugu icin buraya kadar gelinmisse
# dikey ayrim SAGLANAMAMIS demektir; yatay itme hakli olarak acilir.
#
# ⚠️ hard artik MIN_AYRIM_M'in ALTINDA ve bu BILEREK: eski kuralda
# "sinira degince tam kuvvet" mantikliydi cunku baska savunma yoktu.
# Simdi sinira gelmeden once dikey zaten devrede.
KACINMA_HARD_M = 2.5
KACINMA_D0_M = 4.0

# --- DIKEY YOL VERME ---------------------------------------------------------
# DIKEY KACIS HIZI — PX4 TAVANINA ESITLENDI, 23 Agustos 2026.
#
# 1.5 yazilmisti; ucaktan okununca PX4'un tavani 1.2 cikti. Ustunu yazmak
# PX4'un sessizce kirpmasi demekti: ayar 1.5 gorunur, ucak 1.2 tirmanir.
# Simdi ikisi ayni ve asagidaki denetim ayrismayi HATA olarak veriyor.
#
# DAHA HIZLI ISTENIRSE: once MPC_Z_VEL_MAX_UP yukseltilir (ayri karar,
# kalkis ve gorev tirmanislarini da etkiler), sonra bu sayi. Benzetimde
# 1.2 -> 3.0 kazanci: en yakin mesafe 2.17 -> 2.26 m (kucuk), yanal kayma
# 4.83 -> 1.92 m (buyuk), 3 m merdiven 6.7 -> 5.4 sn.
KACINMA_DIKEY_HIZ_MPS = PX4_DIKEY_HIZ_TAVANI_MPS

# Dikey ivme — operator karari (23 Agustos): "en dengeli deger".
#
# OLCULDU: hiz tavani (1.2, PX4) baskin oldugu icin IVMENIN KATKISI COK
# KUCUK. a=1.5 ile a=3.0 arasinda en yakin mesafe farki 0.07 m:
#     a=1.5 -> 2.10 m,  a=2.0 -> 2.13 m,  a=3.0 -> 2.17 m
# Cunku 1.2 m/s'e ulasmak a=3.0'da 0.4 sn, a=1.5'te 0.8 sn suruyor; 3 m
# tirmanmanin kendisi zaten 2.5 sn.
#
# 2.0 SECILDI, 3.0 DEGIL — iki gerekce:
#   * ITKI PAYI: a=3.0 -> 1.31x aski itkisi (~%75 gaz), a=2.0 -> 1.20x
#     (~%72). Aski gazi zaten %66 olculmus (TUZAKLAR §0.3); performans
#     farki 0.04 m iken %3 gaz payi vermek dogru takas degil.
#   * MPC_ACC_DOWN_MAX = 3.0: cift rutbeli ucak ASAGI kaciyor ve a=3.0
#     tam o sinira basiyor — PX4 kirpar. 2.0 her iki yonde de payda.
#
# DAHA HIZLI ISTENIRSE dogru kol IVME DEGIL, MPC_Z_VEL_MAX_UP.
KACINMA_DIKEY_IVME_MPS2 = 2.0

# Dikey konum kazanci — operator karari (23 Agustos). 0.8 -> 2.0.
# 3 m'lik hatada 0.8 yalnizca 2.4 m/s komut uretiyordu ve hiz tavanina hic
# ulasmiyordu; sinir kp'nin kendisiydi.
KACINMA_DIKEY_KP = 2.0

# Dikey merdivende ardisik rutbeler arasi ayrim (operator karari).
KACINMA_KATMAN_M = 3.0

# CIKIS HISTEREZISI — catisma d0'da ACILIR, d0 + hist'te KAPANIR.
#
# 0.5 -> 2.5 (24 Agustos 2026, ilk dikey ucusun bulgusu). Cikis 4.5 m
# iken komsu 4.9 m'de DURURKEN 3 m'lik ayrim 6 saniyede geri veriliyordu.
# Sinir pilotun gozle kestirebileceginden dar ("icerideyim" ile "ciktim"
# arasi 1.2 m) ve operator bunu yo-yo olarak gordu — CA.md §6.5, §7.2.
# 2.5 ile cikis 6.5 m: komsu GERCEKTEN uzaklasmadan ayrim birakilmaz.
#
# NEDEN 2.5, 3.0 DEGIL: cikis esigi (d0 + hist) formasyonun planli en
# yakin yaklasmasinin (KRITIK_AYRIM_M, 12 m aralikta 8.49 m) ALTINDA
# kalmali — ustune cikarsa normal gecisin actigi catisma bir daha
# KAPANMAZ ve merdiven kalici olur. 2.5 -> pay 1.99 m, 3.0 -> 1.49 m.
# Asagidaki denetim bu payi izliyor.
#
# BEDELI: catisma ve merdiven daha uzun surer. Siki formasyonda
# (aralik <= 7 m) d0 ile birlikte yeniden dusunulmeli.
KACINMA_HIST_M = 2.5

# KORLUK YER ESIGI — kaybolan komsunun SON bilinen irtifasi bunun
# altinda VE disarm ise korluk DONUS TUTMASI uygulanmaz (kapali ucak,
# dusen ucak). 25 Agustos sahasi: kapali ylp02 yuzunden ylp01 donusu
# 34 sn bloke kaldi. Havada/arm'li kaybolan komsu icin tutma aynen
# surer (46.4 sn'lik tek yonlu mesh vakasi o siniftir, TUZAKLAR 2.15).
KACINMA_KORLUK_YER_M = 1.5

# KACIS ZARFI (YANAL) — kacinma bir ucagi PLANLI yerinden en fazla bu
# kadar yana itebilir/kaydirabilir. Kuru testin haritasi ve ayak izi bu
# payi cizmek icin kullaniyor (24 Agustos'ta baglandi — onceden harita
# yalniz planli rotayi ciziyordu ve zarf operatore ELLE soyleniyordu).
#
# KAYNAK: 23 Agustos benzetimi — v_dikey=1.2 ile kacis sirasinda yanal
# kayma 4.83 m olculdu (yukarida 'DIKEY KACIS HIZI' notu), 5.0'a
# yuvarlandi. Dikey zarf ayrica var: KACINMA_KATMAN_M tirmanma —
# haritada cizilemez, lejantta soylenir.
KACINMA_ZARF_YANAL_M = 5.0

# Komsu verisi bu suredan eskiyse YOK SAYILIR. Mesh ~5-7 Hz ve ~%30 kayipli;
# 0.5 s penceresi iki-uc ardisik kayipta komsuyu dusurur ve kacinma SESSIZCE
# korumasiz kalir. 1.5 s `basit_kacinma`nin sahada kosan degeri
# (basit_kacinma_node.py:146) — `collision_avoidance` varsayilani 0.5 idi,
# yani ucte biri. Ikisi ayni degeri kullanmali, yoksa dugum degistirince
# kacinmanin gorus alani sessizce degisir.
KACINMA_BAYAT_S = 1.5

# --- KACINMA IVME SINIRLARI --------------------------------------------------
# 22 AGUSTOS 2026'DA UCUSTA BULUNDU. Operator: "baya bildigin sag sol yapti,
# devrilecek gibi". Kayittan olculdu (ylp00, kacis evresi):
#
#     roll  -24.7 .. +28.3 derece  (53 derecelik yalpa)
#     MAKS EGIM 34.0 derece        (asili evrede yalniz 11.6 idi)
#
# SEBEP: `ca_core.CaParams` ivme sinirlari bu dosyaya HIC BAGLANMAMISTI.
# Ozgun tasarimdan kalma sabitlerdi:
#
#     slew_normal    =  4.0 m/s2  ->  22.2 derece
#     slew_emergency = 30.0 m/s2  ->  71.9 derece   <-- IMKANSIZ
#
# `slew_emergency` komsu `hard`in icine girince devreye giriyor. Operator
# 6.14 m'ye kadar geldi, hard=6.0 — tam devreye girdi. Ucak 72 derece
# egilemez; elinden geleni yapti (34 derece), yetisemedi, komut degisti,
# ters yone egildi. Yalpa BU: imkansiz bir komutu takip etme cabasi.
#
# CLAUDE.md 8 zaten diyordu: "Acilari elle ayarlama. Egim tavani ivmeden
# turetiliyor (a = g*tan(theta))". Hiz, ivme, egim hepsi burada turetiliyordu
# — kacinma haric. Bu o bosluk.
#
# TURETME: kacis bir ACIL manevra, o yuzden egim tavaninin TAMAMINI
# kullanabilir (guided seyir gibi pay birakmaz). Normal kacis ise seyir
# ivmesiyle acil arasinda: ikisinin ortasi.
KACINMA_IVME_ACIL_MPS2 = ivme_icin(EGIM_TAVANI_DEG)
KACINMA_IVME_NORMAL_MPS2 = 0.5 * (GOREV_IVME_MPS2 + KACINMA_IVME_ACIL_MPS2)

# Kacinma bittikten SONRA eve donus ivmesi. Ayri ve DUSUK olmasi kasitli:
# tehlike aninda sert olmali, tehlike gecince acele etmenin faydasi yok.
# 22 Agustos olcumu: 6 m'lik donus 3.21 m/s tepe hizla yapildi
# (v_tepe = sqrt(a*d) = sqrt(1.5*6) = 3.0) ve donus evresinde 22 derece
# yalpa olustu. 0.5 m/s2 ile tepe 1.73 m/s'e iner.
KACINMA_DONUS_IVME_MPS2 = 0.5

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

    # hard, artik YATAY SON CARENIN acildigi kabuk (23 Agustos'ta anlami
    # degisti — bkz. KACINMA ESIKLERI bolumu). MIN_AYRIM'in altinda olmasi
    # ARTIK HATA DEGIL: sinira gelmeden once DIKEY zaten devrede.
    #
    # Kontrol edilecek yeni sart: dikey katman, yatay son carenin acildigi
    # kabuktan BUYUK olmali. Kucukse dikey ayrim tamamlansa bile ucaklar
    # sert kabugun icinde kalir ve yatay itme HER catismada aciliyor
    # demektir — yani "dikey birincil" karari fiilen bozulur.
    if KACINMA_KATMAN_M <= KACINMA_HARD_M:
        hata.append(
            f'dikey katman ({KACINMA_KATMAN_M:.1f} m) yatay son care '
            f'kabugundan ({KACINMA_HARD_M:.1f} m) BUYUK olmali — yoksa '
            f'dikey ayrim tamamlansa bile yatay itme her catismada acilir.')

    # CIKIS ESIGI vs FORMASYON — 24 Agustos 2026 (hist_m 0.5 -> 2.5).
    # Catisma d0'da acilir ama d0+hist'te kapanir. Kapanis esigi
    # formasyonun planli en yakin yaklasmasini asarsa, normal gecisin
    # ACTIGI catisma bir daha KAPANMAZ — merdiven kalici olur. Bu yuzden
    # d0 denetiminin aksine HATA (o "fazladan tetiklenir" der, bu
    # "tetiklenen hic sonmez" der).
    _kacinma_cikis = KACINMA_D0_M + KACINMA_HIST_M
    if _kacinma_cikis >= KRITIK_AYRIM_M:
        hata.append(
            f'kacinma cikis esigi (d0+hist = {_kacinma_cikis:.1f} m) '
            f'formasyonun en yakin yaklasmasinin ({KRITIK_AYRIM_M:.2f} m) '
            f'USTUNDE — normal geciste acilan catisma hic kapanmaz. '
            f'KACINMA_HIST_M kucult ya da ARALIK_M buyut.')
    elif KRITIK_AYRIM_M - _kacinma_cikis < 1.0:
        uyari.append(
            f'kacinma cikis esigi ({_kacinma_cikis:.1f} m) ile formasyonun '
            f'en yakin yaklasmasi ({KRITIK_AYRIM_M:.2f} m) arasinda yalniz '
            f'{KRITIK_AYRIM_M - _kacinma_cikis:.2f} m pay var.')

    # 🔴 PX4 SESSIZ KIRPMA DENETIMI — 23 Agustos 2026.
    # Kacinmanin dikey komutu PX4 tavanini asarsa PX4 kirpar ve HICBIR YERDE
    # uyari cikmaz: ayar ve log istenen degeri gosterir, ucak baskasini yapar.
    if KACINMA_DIKEY_HIZ_MPS > PX4_DIKEY_HIZ_TAVANI_MPS + 1e-9:
        hata.append(
            f'kacinma dikey hizi ({KACINMA_DIKEY_HIZ_MPS:.1f} m/s) PX4 '
            f'tavanindan ({PX4_DIKEY_HIZ_TAVANI_MPS:.1f} m/s, '
            f'MPC_Z_VEL_MAX_UP) BUYUK — PX4 sessizce kirpar. Once PX4 '
            f'parametresini yukselt.')
    if KACINMA_DIKEY_IVME_MPS2 > PX4_DIKEY_IVME_TAVANI_MPS2 + 1e-9:
        hata.append(
            f'kacinma dikey ivmesi ({KACINMA_DIKEY_IVME_MPS2:.1f} m/s2) '
            f'MPC_ACC_UP_MAX ({PX4_DIKEY_IVME_TAVANI_MPS2:.1f}) USTUNDE.')
    if KACINMA_DIKEY_IVME_MPS2 > PX4_DIKEY_INIS_IVME_TAVANI_MPS2 + 1e-9:
        uyari.append(
            f'kacinma dikey ivmesi ({KACINMA_DIKEY_IVME_MPS2:.1f} m/s2) '
            f'MPC_ACC_DOWN_MAX ({PX4_DIKEY_INIS_IVME_TAVANI_MPS2:.1f}) '
            f'USTUNDE — ASAGI kacan ucak (cift rutbe) kirpilir.')
    # Dikey merdivenin kurulma suresi, catisma suresinden kisa olmali.
    _t_merdiven = (KACINMA_KATMAN_M / KACINMA_DIKEY_HIZ_MPS
                   + KACINMA_DIKEY_HIZ_MPS / KACINMA_DIKEY_IVME_MPS2)
    _t_catisma = KACINMA_D0_M / max(0.1, 2.0 * GOREV_HIZ_MPS)
    if _t_merdiven > _t_catisma:
        uyari.append(
            f'dikey merdiven {_t_merdiven:.1f} saniyede kuruluyor ama kafa '
            f'kafaya kapanma {_t_catisma:.1f} sn suruyor — en yakin anda '
            f'ayrimin TAMAMI olusmus olmayacak (beklenen davranis, '
            f'ucus oncesi bilinmeli).')
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
    print(f'  kacinma giris/cikis   {KACINMA_D0_M:6.2f} m / '
          f'{KACINMA_D0_M + KACINMA_HIST_M:.2f} m'
          f'   (d0 / d0+hist; donus ancak cikista baslar)')

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
    # Kacinma ivme sinirlari — 22 Agustos 2026'da EKLENDI. Oncesinde
    # ca_core'daki sabitler kullaniliyordu ve slew_emergency 30 m/s2 idi
    # (71.9 derece egim = imkansiz). Ucakta 34 derece yalpa olculdu.
    print(f'KACINMA_IVME_NORMAL={KACINMA_IVME_NORMAL_MPS2:.2f}')
    print(f'KACINMA_IVME_ACIL={KACINMA_IVME_ACIL_MPS2:.2f}')
    print(f'KACINMA_DONUS_IVME={KACINMA_DONUS_IVME_MPS2:.2f}')
    print(f'KACINMA_HARD={KACINMA_HARD_M}')
    print(f'KACINMA_KATMAN={KACINMA_KATMAN_M}')
    print(f'KACINMA_HIST={KACINMA_HIST_M}')
    print(f'KACINMA_KORLUK_YER={KACINMA_KORLUK_YER_M}')
    print(f'KACINMA_DIKEY_HIZ={KACINMA_DIKEY_HIZ_MPS}')
    print(f'KACINMA_DIKEY_IVME={KACINMA_DIKEY_IVME_MPS2}')
    print(f'KACINMA_DIKEY_KP={KACINMA_DIKEY_KP}')
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
