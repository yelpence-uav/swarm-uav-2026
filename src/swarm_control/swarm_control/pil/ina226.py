# Copyright 2026 Yelpence
"""INA226 pil olcumu — SAF cevrim mantigi, I2C yok, ROS yok.

NEDEN AYRI MODUL: kardesleri rc_eksen.py · swd_mandal.py · formasyon_kilidi.py
ile ayni gerekce — dugum donanim olmadan import edilemiyor, bu mantik ise
birim testle KILITLENMEK ZORUNDA. Isaret ya da olcek hatasi burada sessizdir:
yanlis gerilim "pil dolu" der ve ucus ortasinda dusersin.

═══════════════════════════════════════════════════════════════════
NEDEN VAR (31 Agustos 2026, operatör Pi 5'e INA226 takti)

ylp01'de PX4 guc modulu YOK (`DURUM.md` §1: "Pil sensor karti yok — tok pil
+ sure siniriyla uculuyor"). Yani o ucakta `battery_voltage_v` MAVROS'tan
0.0 geliyor ve YKI pil durumunu GOREMIYOR. INA226 bu bosluğu dolduruyor.

`AgentStatus` alanlari ZATEN var (battery_percent · battery_voltage_v ·
battery_current_a) ve mesh onlari tasiyor — protokol degisikligi GEREKMEZ.

═══════════════════════════════════════════════════════════════════
🔴 KALIBRASYON YAZMACI KULLANILMIYOR — BILEREK

INA226'nin kendi Current (0x04) ve Power (0x03) yazmaclari, once
Calibration (0x05) yazmacina dogru sayi yazilmasini ister:
    CAL = 0.00512 / (Current_LSB * R_sont)
Bu zincirde iki yuvarlama ve bir "hangi LSB" karari var; yanlis olursa
akim SESSIZCE olcekli-yanlis okunur.

Onun yerine SONT GERILIMINI dogrudan okuyup akimi yazilimda hesapliyoruz:
    I = V_sont / R_sont
Tek carpma, tek bolme, tam olarak test edilebilir. Chip'in kalibrasyonuna
hic dokunulmuyor, yani chip resetlense bile okuma dogru kalir.

═══════════════════════════════════════════════════════════════════
YAZMAC OLCEKLERI (veri sayfasi, INA226 Rev. B)

    0x01 Shunt Voltage : 2.5 uV/LSB, ISARETLI 16 bit (iki tumleyen)
    0x02 Bus Voltage   : 1.25 mV/LSB, isaretsiz 16 bit
    0xFE Manufacturer  : 0x5449 ('TI')
    0xFF Die ID        : 0x2260

⚠️ Sont gerilimi ISARETLI: akim ters yonde akarsa (sarj) deger negatiftir.
Isaretsiz okunursa 65535'e yakin sayilar cikar ve "1000 A cekiliyor"
gorunur. Bu tam olarak sessiz-yanlis sinifidir; test bunu kilitliyor.
"""

# --- Yazmac adresleri ---
YAZMAC_KONFIG = 0x00
YAZMAC_SONT_GERILIM = 0x01
YAZMAC_BARA_GERILIM = 0x02
YAZMAC_URETICI_KIMLIK = 0xFE
YAZMAC_DIE_KIMLIK = 0xFF

# --- Kimlik degerleri (dogrulama icin; tahmin yerine olcum) ---
URETICI_KIMLIK_TI = 0x5449
DIE_KIMLIK_INA226 = 0x2260

# --- Veri sayfasi olcekleri ---
SONT_LSB_V = 2.5e-6      # 2.5 uV
BARA_LSB_V = 1.25e-3     # 1.25 mV

# INA226 sont gerilimi tavani +-81.92 mV. Bunun ustu okunamaz, yani
# R_sont secimi maksimum akimi belirler: I_maks = 0.08192 / R_sont.
SONT_TAVAN_V = 0.08192


def isaretli16(ham: int) -> int:
    """16 bitlik iki-tumleyen degeri isaretli tam sayiya cevirir."""
    ham &= 0xFFFF
    return ham - 0x10000 if ham & 0x8000 else ham


def bara_gerilimi_v(ham: int) -> float:
    """0x02 yazmacindan paket gerilimi (volt).

    Args:
        ham (int): yazmacin 16 bitlik ham degeri.

    Returns:
        float: gerilim, volt.
    """
    return (ham & 0xFFFF) * BARA_LSB_V


def bara_gerilimi_kalibre_v(ham: int, carpan: float = 1.0,
                            ofset_v: float = 0.0) -> float:
    """Kalibrasyonlu paket gerilimi.

    🔴 VARSAYILAN 1.0 / 0.0 — yani KALIBRASYON YOK. Bu bilerek: cipin
    kendi dogrulugu (+-%0.1 kazanc, +-2.5 mV ofset) zaten yeterli.
    Parametre yalnizca OLCUMLE gerekcelendirilmis bir sapma bulunursa
    kullanilir.

    ═══════════════════════════════════════════════════════════════
    31 AGUSTOS 2026 — ylp00'da GOZLENEN FARK, HENUZ KAPATILMADI

        INA226      15.89 V  (gurultu +-0.005 V, cok kararli)
        multimetre  15.67 V
        fark        0.22 V  (%1.4)

    Bu fark cipin spekinin ~10 KATI, yani cip hatasi DEGIL. Iki aday:
      a) OLCUM NOKTASI FARKI — pil ile modul arasindaki kablo/konnektor
         uzerinde IR dususu. Bu durumda fark YUKLE DEGISIR ve sabit bir
         carpan YANLIS olur; kalibre ETME.
      b) KART OLCEK HATASI — modulun kendi giris uclarinda da fark
         varsa. Bu durumda carpan dogru cozumdur.

    AYIRT EDEN OLCUM: multimetreyi INA226'nin KENDI giris uclarina
    (VBUS/IN+ ve GND) bagla. Orada da fark varsa (b), yoksa (a).

    ⚠️ TEK NOKTADAN kalibrasyon kazanc ile ofseti AYIRAMAZ. Iki farkli
    gerilimde olcum yapilmadan `carpan` kullanmak, baska bir gerilimde
    hatayi BUYUTEBILIR. Tek nokta varsa ofset daha guvenlidir.
    ═══════════════════════════════════════════════════════════════

    Args:
        ham (int): 0x02 yazmacinin ham degeri.
        carpan (float): kazanc duzeltmesi (1.0 = duzeltme yok).
        ofset_v (float): sabit kaydirma, volt (0.0 = duzeltme yok).

    Returns:
        float: duzeltilmis gerilim, volt.
    """
    return bara_gerilimi_v(ham) * carpan + ofset_v


def sont_gerilimi_v(ham: int) -> float:
    """0x01 yazmacindan sont gerilimi (volt, ISARETLI)."""
    return isaretli16(ham) * SONT_LSB_V


def akim_a(ham_sont: int, sont_ohm: float) -> float:
    """Sont geriliminden akim (amper).

    Args:
        ham_sont (int): 0x01 yazmacinin ham degeri.
        sont_ohm (float): sont direnci, ohm. 0 ya da negatifse hesaplanamaz.

    Returns:
        float: akim, amper. Sont bilinmiyorsa 0.0 (bilinmiyor = 0, sozlesme
            AgentStatus.battery_current_a yorumuyla ayni).
    """
    if sont_ohm <= 0.0:
        return 0.0
    return sont_gerilimi_v(ham_sont) / sont_ohm


def kimlik_dogru(uretici: int, die: int) -> bool:
    """Okunan kimlik yazmaclari gercekten INA226'yi mi gosteriyor?"""
    return uretici == URETICI_KIMLIK_TI and die == DIE_KIMLIK_INA226


def azami_akim_a(sont_ohm: float) -> float:
    """Bu sont direnciyle okunabilecek en buyuk akim.

    Ustune cikilirsa yazmac DOYAR ve akim OLDUGUNDAN KUCUK okunur —
    sessiz-yanlis. Dugum acilista bunu log'a yaziyor ki operator
    "40 A cekiyorum ama 20 A goruyorum" durumunu tanisin.
    """
    if sont_ohm <= 0.0:
        return 0.0
    return SONT_TAVAN_V / sont_ohm


def yuzde_kestir(gerilim_v: float, hucre: int,
                 bos_v: float = 3.30, dolu_v: float = 4.20) -> float:
    """Paket geriliminden KABA doluluk yuzdesi.

    🔴 BU BIR KESTIRIM, YAKIT OLCERI DEGIL. LiPo gerilimi yuk altinda
    duser; %30 gorunen bir paket yuksuz %60 olabilir. `AgentStatus`
    yorumunun dedigi gibi: failsafe esigi icin YUZDE degil GERILIM
    kullanilir. Bu deger yalnizca ekranda hizli fikir vermek icin.

    Args:
        gerilim_v (float): olculen paket gerilimi.
        hucre (int): seri hucre sayisi (4S, 6S...). 0 ise kestirim yok.

    Returns:
        float: 0..100 arasi yuzde; hucre bilinmiyorsa 0.0.
    """
    if hucre <= 0 or gerilim_v <= 0.0:
        return 0.0
    hucre_v = gerilim_v / hucre
    oran = (hucre_v - bos_v) / (dolu_v - bos_v)
    return max(0.0, min(100.0, oran * 100.0))
