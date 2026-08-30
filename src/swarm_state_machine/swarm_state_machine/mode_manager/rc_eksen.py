# Copyright 2026 Yelpence
"""RC PWM -> normalize eksen donusumu. Saf matematik, ROS yok.

NEDEN AYRI MODUL (30 Agustos 2026): isaret yonu bu projede UCUSLA
odenecek bir hata. Ters bir pitch isareti "suru cubugun TERSINE gider"
demek ve hicbir yerde hata vermez. Dugumun icinde gomulu kalirsa bu
laptopta test edilemez (rclpy konteynerde); disari alininca SAHA OLCUMU
KALICI BIR DOGRULAMAYA donusuyor.

═══════════════════════════════════════════════════════════════════
SAHA OLCUMU — 30 Agustos 2026, ylp00, FS-i6X #2 (suru kumandasi)
i-BUS'tan 3246 cerceve, tek yon denetimi TEMIZ:

    cubuk ILERI  -> CH2 pitch = 1974   (UST uc)
    cubuk SAGA   -> CH1 roll  = 1981   (UST uc)
    cubuk SAGA   -> CH4 yaw   = 1014   (ALT uc)   <- TEK TERS OLAN
    gaz  YUKARI  -> CH3       = 1988   ·  dipte 1001

SwarmControlCommand.msg sozlesmesi:
    pitch_cmd > 0 = ileri · roll_cmd > 0 = saga
    yaw_cmd   > 0 = saat yonu (saga) · throttle_cmd > 0 = tirmanis

🔴 ONCEDEN KOD PITCH'I NEGATIFLIYOR, YAW'I NEGATIFLEMIYORDU — ikisi de
yanlisti. Olcum oncesi "genellikle RCIn pitch ileri itince pwm duser"
diye bir VARSAYIM yaziliydi; bu kumandada TERSI cikti.

⚠️ Kumanda degisirse ya da FS-i6X'te bir kanalin REVERSE ayari
degistirilirse BU SABITLER GECERSIZ olur. G0 isaret testi tekrarlanmali
(gorev2.md §4 madde 17).
═══════════════════════════════════════════════════════════════════
"""

PWM_MERKEZ = 1500.0
PWM_YARIM = 500.0      # 1000..2000 araliginin yarisi
PWM_ALT = 1000.0
PWM_UST = 2000.0

# Olculen isaretler (yukaridaki blok). True = kanali ters cevir.
TERS_PITCH = False     # ileri zaten UST uca gidiyor
TERS_ROLL = False      # saga zaten UST uca gidiyor
TERS_YAW = True        # saga ALT uca gidiyor -> cevirmek SART


def _kirp(deger: float, alt: float = -1.0, ust: float = 1.0) -> float:
    """Degeri araliga kirpar."""
    return max(alt, min(ust, deger))


def eksen_normalize(pwm: float, ters: bool = False) -> float:
    """Ortalanan bir cubugun PWM'ini [-1, +1]'e cevirir (1500 = 0).

    Args:
        pwm (float): Kanal degeri, tipik 1000..2000.
        ters (bool): True ise isaret cevrilir.

    Returns:
        float: [-1, +1] araliginda normalize eksen.
    """
    v = _kirp((pwm - PWM_MERKEZ) / PWM_YARIM)
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
