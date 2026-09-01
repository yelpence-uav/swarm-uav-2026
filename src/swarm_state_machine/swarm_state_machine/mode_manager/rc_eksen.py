# Copyright 2026 Yelpence
"""RC PWM -> normalize eksen donusumu. Saf matematik, ROS yok.

NEDEN AYRI MODUL (30 Agustos 2026): isaret yonu bu projede UCUSLA
odenecek bir hata. Ters bir pitch isareti "suru cubugun TERSINE gider"
demek ve hicbir yerde hata vermez. Dugumun icinde gomulu kalirsa bu
laptopta test edilemez (rclpy konteynerde); disari alininca SAHA OLCUMU
KALICI BIR DOGRULAMAYA donusuyor.

SwarmControlCommand.msg sozlesmesi:
    pitch_cmd > 0 = ileri · roll_cmd > 0 = saga
    yaw_cmd   > 0 = saat yonu (saga) · throttle_cmd > 0 = tirmanis

═══════════════════════════════════════════════════════════════════
GECERLI OLCUM — 31 Agustos 2026, ylp00, YENI BIND EDILEN KUMANDA
(kumanda_web.py arayuzunden, her eksen TEK YONE oynatilarak)

    cubuk ILERI  -> CH2 pitch = 2000   (UST uc)
    cubuk SAGA   -> CH1 roll  = 1998   (UST uc)
    cubuk SAGA   -> CH4 yaw   = 2000   (UST uc)
    gaz  YUKARI  -> CH3       = 2000   ·  dipte 1000

DORDU DE UST UC -> hicbir kanal cevrilmiyor.

🔴 YAW DEGISTI: onceki kumandada saga = ALT uc (1014) idi ve kod onu
CEVIRIYORDU (TERS_YAW = True). Yeni kumandada saga UST uca gidiyor.
Sabit guncellenmeseydi pilot SAGA cevirir, suru SOLA donerdi — ve
hicbir yerde hata gorunmezdi.
═══════════════════════════════════════════════════════════════════
ESKI OLCUM (30 Agustos 2026, FS-i6X #2) — TARIHCE, artik gecerli DEGIL

    ILERI -> 1974 (UST) · SAGA roll -> 1981 (UST)
    SAGA yaw -> 1014 (ALT)  <- o kumandada TEK TERS OLAN
    gaz YUKARI -> 1988 · dipte 1001

O olcumden once kodda "genellikle RCIn pitch ileri itince pwm duser"
diye bir VARSAYIM yaziliydi ve YANLISTI; ders burada duruyor.
⚠️ Ilk denemede her cubuk IKI YONE birden oynatildigi icin sonuc
belirsiz kaldi ve roll de ters sanildi; sira varsayimiyla koda
dokunulsaydi DOGRU olan roll bozulacakti. TEK YONE oynat.
═══════════════════════════════════════════════════════════════════

⚠️ Kumanda degisirse ya da bir kanalin REVERSE ayari degistirilirse BU
SABITLER GECERSIZ olur — 31 Agustos'ta tam bu yasandi. Olcumu tekrarla:
`src/gcs/kumanda_web.py` arayuzu, "madde 17" paneli.
"""

PWM_MERKEZ = 1500.0
PWM_YARIM = 500.0      # 1000..2000 araliginin yarisi
PWM_ALT = 1000.0
PWM_UST = 2000.0

# Olculen isaretler (yukaridaki GECERLI OLCUM blogu).
# True = kanali ters cevir.
TERS_PITCH = False     # ileri -> UST uc
TERS_ROLL = False      # saga  -> UST uc
TERS_YAW = False       # 31 Agu: saga artik UST uc (eski kumandada ALT idi)


def _kirp(deger: float, alt: float = -1.0, ust: float = 1.0) -> float:
    """Degeri araliga kirpar."""
    return max(alt, min(ust, deger))


# 🔴 OLU BANT — 31 Agustos 2026, UCUSTA OLCULDU.
#
# Cubuklar "merkezde" dururken bile PWM tam 1500 degil; olculen dinlenme
# degerleri: roll 1501 · pitch 1503 · yaw 1502. Olu bant olmadigi icin bu
# 1-3 us'lik trim sapmasi SUREKLI komuta donusuyordu:
#
#     yaw   1502 -> 0.004 -> 0.004 x 25 deg/s = 0.1 deg/s
#     pitch 1503 -> 0.006 -> 0.006 x 2.0 m/s  = 0.012 m/s
#
# Ucus kaydindan dogrulandi: formasyon heading'i 13 saniyede 212.7 -> 214.0
# (tam 0.1 deg/s) kaydi, YAW CUBUGU SIFIRKEN. Operator "drone geziyor,
# drift yapiyor" diye bildirdi.
#
# Iki dakikalik bir formasyon ucusunda bedeli: centroid ~1.4 m kayar,
# formasyon ~12 derece doner. Hicbir yerde hata gorunmez.
#
# ESIK SECIMI: olculen en buyuk sapma 3 us (0.006 normalize). 0.03 = 15 us,
# yani ~5 kat pay. Tam skalanin %1.5'i — pilotun hissetmeyecegi kadar
# kucuk, trim kaymasini yutacak kadar buyuk.
# ⚠️ Kumanda degisir ya da trim elle oynatilirsa bu sayi YENIDEN OLCULMELI:
# `kumanda_web.py` kanal panelinde cubuklar birakilmis halde okunur.
OLU_BANT = 0.03


def olu_bant_uygula(v: float, olu: float = OLU_BANT) -> float:
    """Merkez civarini sifirlar ve kalani YENIDEN OLCEKLER.

    Yeniden olcekleme sart: yalnizca sifirlansaydi cubuk olu bandi
    terk ettigi anda cikis 0'dan `olu`ya SICRARDI. Bu haliyle gecis
    surekli ve tam basildiginda cikis yine +-1.0 kaliyor.

    Args:
        v (float): [-1, +1] normalize eksen.
        olu (float): olu bant yarim genisligi.

    Returns:
        float: olu bant uygulanmis eksen.
    """
    if olu <= 0.0:
        return v
    if abs(v) <= olu:
        return 0.0
    isaret = 1.0 if v > 0 else -1.0
    return isaret * (abs(v) - olu) / (1.0 - olu)


def eksen_normalize(pwm: float, ters: bool = False,
                    olu: float = OLU_BANT) -> float:
    """Ortalanan bir cubugun PWM'ini [-1, +1]'e cevirir (1500 = 0).

    Olu bant UYGULANIR — gerekcesi ve saha olcumu OLU_BANT yorumunda.

    Args:
        pwm (float): Kanal degeri, tipik 1000..2000.
        ters (bool): True ise isaret cevrilir.
        olu (float): olu bant yarim genisligi; 0.0 = olu bant yok.

    Returns:
        float: [-1, +1] araliginda normalize eksen.
    """
    v = olu_bant_uygula(_kirp((pwm - PWM_MERKEZ) / PWM_YARIM), olu)
    return -v if ters else v


def gaz_normalize(pwm: float) -> float:
    """Gaz PWM'ini [0, 1]'e cevirir (dip = 0, tepe = 1).

    AYRI FONKSIYON, cunku gaz cubugu ORTALANMAZ: FlySky Mod 2'de birakildigi
    yerde kalir ve dogal olarak DIPTE durur. Ara sozlesme [0,1] — ucuncu
    giris yolu (`_on_joy`, `manual_control`) da bunu bekliyor; -1..+1'e
    cevrim `_on_manual_control`'da tek yerde yapiliyor.
    """
    return _kirp((pwm - PWM_ALT) / (PWM_UST - PWM_ALT), 0.0, 1.0)


def gaz_merkezde(throttle_cmd: float, pay: float) -> bool:
    """Gaz komutu 'notr' sayilacak kadar merkeze yakin mi.

    🔴 NEDEN VAR (30 Agustos 2026, saha olcumu): gaz cubugu ORTALANMIYOR ve
    dogal olarak DIPTE duruyor (olculen dinlenme PWM 1001). Zincir:

        PWM 1001 -> gaz_normalize 0.001 -> throttle_cmd = 0.001*2-1 = -1.0

    Yani pilot SwA'yi gaz DIPTEYKEN acarsa suru ANINDA tam hizla ALCALIR.
    mode_manager'da bunu tutan hicbir kapi yok. Ucus A'nin ilk saniyesinde
    isirirdi.

    Cozum: gaz merkeze gelene kadar hareket YOK (operator karari, 30 Agu —
    "yordam degil kod kapisi"). Yordama guvenmek bu projenin kendi kuralina
    ters; sartname osilasyonu -10, carpismayi -20xN ile cezalandiriyor.
    """
    return abs(throttle_cmd) <= pay
