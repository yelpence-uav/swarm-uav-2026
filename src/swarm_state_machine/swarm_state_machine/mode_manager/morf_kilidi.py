# Copyright 2026 Yelpence
"""Formasyon morfu sirasindaki slot hizi kilidi — SAF mantik, ROS yok.

NEDEN AYRI MODUL: kardesleri rc_eksen.py · swd_mandal.py ·
formasyon_kilidi.py ile ayni gerekce — mode_manager_node donanim/ROS
olmadan import EDILEMIYOR, bu mantik ise birim testle KILITLENMEK ZORUNDA.
Buradaki bir isaret ya da sira hatasi sessizdir: kilit dusmezse formasyon
merkezin gerisinde kalir, dusmemesi gerekirken duserse ucaklar birbirine
tam hizla girer. Ikisi de hata VERMEZ.

═══════════════════════════════════════════════════════════════════
NEDEN VAR — 31 Agustos 2026 ucusu, OLCULDU

Kumandadan formasyon gecisinde iki ucak birbirine 1,65 m yaklasti.
Kayittan cikan sayilar:

    duruştan 2,71 m/s'e     1,2 saniyede
    tepe kapanma hizi       4,13 m/s
    kacinma giris esigi     4,00 m
    frenleme mesafesi       4,13^2 / (2 * 3,58) = 2,38 m
    kalmasi gereken         4,00 - 2,38 = 1,62 m
    OLCULEN                 1,65 m          <- 3 cm fark

🔴 KACINMA BOZUK DEGIL. Kitabina gore calisti; 4 m'lik esik 4 m/s'lik bir
kapanma icin tasarlanmamis. Cozum esigi buyutmek DEGIL — 7 m aralikta
kacinma o zaman surekli acik kalir (cikis esigi 6,5 m) — morfu
YAVASLATMAK. 0,6 m/s'de kapanma 1,2 m/s, frenleme 0,20 m, kacinmaya
3,80 m kaliyor.

═══════════════════════════════════════════════════════════════════
🔴 KILIT NEDEN CUBUKLA DUSER

Yavaslatma YALNIZ morf suresince gecerli olmali. Suru merkezi cubukla
oteleniyorken slot hizi 0,6 m/s'de kalirsa formasyon merkezin GERISINDE
kalir. Bu tam olarak formation_node'da bir kez yasanmis bir hata:
"merkez 3.00 m/s iken komut 1.05, dron 1.07 -> aradaki ~2 m/s her saniye
acige eklenip bacak basina 5 -> 12,5 -> 20,4 m". Ayni tuzagi morf
kilidiyle yeniden acmiyoruz.
"""

# Kilit yok / sure belirtilmedi.
KILIT_YOK = 0.0

# `istenen <= 0` = "hiz belirtilmedi" (HOLD komutu boyle yolluyor).
# Bu degere DOKUNULMAZ: 0'i 0,6 yapmak HOLD'u hareket komutuna cevirirdi.
BELIRTILMEDI = 0.0

SEBEP_YOK = ''
SEBEP_CUBUK = 'cubuk'
SEBEP_SURE = 'sure'


def hiz_sinirla(istenen: float, morf_hiz: float, bitis_s: float,
                simdi_s: float, cubuk: float,
                cubuk_esigi: float) -> tuple:
    """Morf suruyorsa slot hizini sinirlar, kilidin yeni halini doner.

    Args:
        istenen (float): komutun tasidigi hiz tavani (m/s). <=0 =
            belirtilmedi, dokunulmaz.
        morf_hiz (float): morf sirasindaki tavan (m/s).
        bitis_s (float): kilidin bitis ani (monotonik saniye).
            KILIT_YOK = kilit kapali.
        simdi_s (float): su anki monotonik saniye.
        cubuk (float): cubuk girdisinin buyuklugu (0..1), uc eksenin
            mutlak degerlerinin en buyugu.
        cubuk_esigi (float): bunun ustu "operator oteleme istiyor".

    Returns:
        tuple: (hiz, yeni_bitis_s, sebep) — `sebep` kilit DUSTUYSE
            neden dustugunu soyler (log icin), yoksa SEBEP_YOK.
    """
    if bitis_s <= KILIT_YOK:
        return istenen, KILIT_YOK, SEBEP_YOK

    # SIRA ONEMLI: cubuk denetimi sureden ONCE. Ikisi ayni anda olursa
    # operatore gosterilecek sebep "cubuk" olmali — sure dolmus olsa bile
    # kilidi fiilen kaldiran onun komutudur.
    if cubuk > cubuk_esigi:
        return istenen, KILIT_YOK, SEBEP_CUBUK

    if simdi_s >= bitis_s:
        return istenen, KILIT_YOK, SEBEP_SURE

    if istenen <= BELIRTILMEDI:
        return istenen, bitis_s, SEBEP_YOK

    return min(istenen, morf_hiz), bitis_s, SEBEP_YOK
