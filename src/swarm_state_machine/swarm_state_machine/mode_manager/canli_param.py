# Copyright 2026 Yelpence
"""Gorev oncesi CANLI parametre kapisi. Saf mantik, ROS yok.

NEDEN AYRI MODUL (30 Agustos 2026): kardesleri rc_eksen.py ve
swd_mandal.py ile ayni gerekce — dugumler rclpy olmadan import
edilemiyor (rclpy konteynerde), bu kapi ise BIRIM TESTLE KILITLENMEK
ZORUNDA. Kapinin yanlis acilmasi "ucus sirasinda B15 kalkis kapisini ya
da G2-K10'un ucuncu kapisini canli canli devre disi birakmak" demek.

🔴 NEDEN BOYLE BIR KAPI VAR — G2-K9 (madde 29):
Sartname araligi ve kalkis irtifasini GOREV ONCESI veriyor ("Orn: 15m")
ve hakem baska bir sayi soyleyebilir. Bugunku yol (env dosyasi +
`docker restart`) saha gununde dakikalar aliyor. Canli param o dakikalari
saniyeye indiriyor ve MESH'E DOKUNMUYOR — yani gorev sirasinda yeni bir
komut yolu ACMIYOR (sartname §5.2: YKI mudahalesi gorevi BASARISIZ yapar).

🔴 VE NEDEN BIR KAPI, "hepsi serbest" DEGIL:
px4_bridge'in kurali birebir kopyalandi (CLAUDE.md §8): "Yalniz hiz/ivme/kp
alanlari kabul edilir; kimlik, kill/arm kanallari ve kalkis kilidi
REDDEDILIR." Kapilar ve kimlik canli degistirilebilseydi, tek bir
`ros2 param set` guvenlik mimarisinin tamamini bosa cikarirdi.

⚠️ CANLI DEGISIKLIK KALICI DEGIL: konteyner yeniden baslayinca
`/ws/ucus_ayarlari.env` gecerli olur (CLAUDE.md §8).
"""

# mode_manager: aralik (yedek) + kalkis irtifasi.
MODE_MANAGER_CANLI = ('default_spacing_m', 'kalkis_irtifa_m',
                      'morf_hiz_mps', 'max_speed_mps',
                      'max_yaw_rate_deg_s', 'max_tilt_deg',
                      # Manevra egim rampasi (6 Eylul). Bir HIZ alani,
                      # yani px4_bridge kuralinin ("yalniz hiz/ivme/kp")
                      # icinde; hicbir kapiyi ve kimligi acmiyor.
                      'max_tilt_rate_deg_s')

# joystick_interpreter: ARALIGIN GERCEK KAYNAGI.
# mode_manager'inki yalnizca yedek — her cerceve `cmd.requested_spacing_m`
# ile buradan bir deger gidiyor ve mode_manager onu ">0 ise KABUL ET"
# kuraliyla aliyor. Yani ylp00'daki bu sayi mesh uzerinden
# (talep_spacing_dm) UCUNU birden suruyor.
JOYSTICK_CANLI = ('default_spacing_m',)


class ParamRed(ValueError):
    """Kapi reddetti; mesaji dogrudan operatore gosterilir."""


# =====================================================================
# MADDE 29 — GOREV 2 BASLATILIRKEN ARALIK / IRTIFA
# =====================================================================
# Operator "Gorev 2 baslat"a basmadan ONCE YKI'de iki sayi giriyor.
# Degerler mesh'te TIP_GOREV paketiyle uc ucaga AYNI ANDA gidiyor.
#
# 🔴 SINIRLAR KEYFI DEGIL:
#
# ARALIK ALT SINIRI = carpisma esigi (MIN_AYRIM_M, ucus_ayarlari 4.0 m).
# Bunun altinda DURGUN formasyonda bile ucaklar esigin icinde kalir —
# yani kacinma surekli tetiklenir ve formasyon hic oturmaz. Sabit burada
# TEKRAR yaziliyor cunku bu modul ROS'suz ve GCS'siz kalmak zorunda;
# degeri degistirirsen ucus_ayarlari.MIN_AYRIM_M ile birlikte degistir.
#
# ARALIK UST SINIRI = mesh tavani. Aralik 1 bayt desimetre ile tasiniyor
# (packet_parser._GOREV_FMT), yani 25.5 m. Ustu SESSIZCE kirpilsaydi
# "12 m istedim, 25.5 m uctu" sinifi bir hata cikardi.
#
# IRTIFA SINIRLARI = kuru testin kendi sinirlariyla AYNI
# (gorev_kanit_ucus `--irtifa` 3..30 m). 3 m altinda yer etkisi ve inis
# dedektoru; 30 m ustu bu sahada planlanmadi.
ARALIK_ALT_M = 4.0
ARALIK_UST_M = 25.5
IRTIFA_ALT_M = 3.0
IRTIFA_UST_M = 30.0

# --- SURU DAVRANIS AYARLARI (5 Eylul 2026) -----------------------------
# Ayni BASLAT paketinden geliyorlar; sinirlar ucus_ayarlari.py'deki
# turetmelerle TUTARLI olmali, bu yuzden tavanlar oradaki MOD_* tavanlarina
# dayaniyor. Ust sinirlar ayrica mesh'in 1 baytlik kodlamasiyla sinirli
# (0.1 birim -> 25.5).
MORF_HIZ_ALT = 0.2      # altinda morf pratikte durur
MORF_HIZ_UST = 3.0      # seyir hizi mertebesi; ustu carpisma payini yer
HAREKET_HIZ_ALT = 0.3
HAREKET_HIZ_UST = 5.0   # PX4_HIZ_TAVANI_MPS
YAW_HIZ_ALT = 2.0
YAW_HIZ_UST = 25.0      # PX4_DONUS_HIZI_DEG_S (MPC_YAWRAUTO_MAX)
EGIM_TAVAN_ALT = 3.0
EGIM_TAVAN_UST = 30.0   # MPC_TILTMAX_AIR — ustu ucagin YAPAMAYACAGI komut

# 0.0 = "operator bir sey girmedi" -> alici KENDI varsayilanini korur.
# Bos birakmak gecerli bir secim; varsayilan aralik 7 m (MOD_ARALIK).
BELIRTILMEDI = 0.0


def _sayi(ad: str, deger) -> float:
    if isinstance(deger, bool):
        raise ParamRed(f'{ad} sayi olmali')
    try:
        return float(deger)
    except (TypeError, ValueError):
        raise ParamRed(f'{ad} sayi olmali')


def g2_ayar_dogrula(aralik_m, irtifa_m) -> tuple:
    """Gorev 2 baslatma ayarini dogrular.

    Args:
        aralik_m: formasyon araligi (m). 0 / None = belirtilmedi.
        irtifa_m: kalkis irtifasi (m). 0 / None = belirtilmedi.

    Returns:
        tuple: (aralik_m, irtifa_m) — belirtilmeyen alan 0.0 doner.

    Raises:
        ParamRed: deger sayi degilse ya da sinirlarin disindaysa.
            Mesaj dogrudan operatore gosterilecek sekilde yazilir.
    """
    a = BELIRTILMEDI if aralik_m in (None, '') else _sayi('aralik', aralik_m)
    i = BELIRTILMEDI if irtifa_m in (None, '') else _sayi('irtifa', irtifa_m)

    if a != BELIRTILMEDI and not (ARALIK_ALT_M <= a <= ARALIK_UST_M):
        raise ParamRed(
            f'Aralik {a:g} m kabul edilmedi. Izinli: '
            f'{ARALIK_ALT_M:g}-{ARALIK_UST_M:g} m. '
            f'Alt sinir carpisma esigi ({ARALIK_ALT_M:g} m) — altinda '
            f'kacinma surekli tetiklenir; ust sinir mesh tavani.'
        )
    if i != BELIRTILMEDI and not (IRTIFA_ALT_M <= i <= IRTIFA_UST_M):
        raise ParamRed(
            f'Irtifa {i:g} m kabul edilmedi. Izinli: '
            f'{IRTIFA_ALT_M:g}-{IRTIFA_UST_M:g} m.'
        )
    return a, i


def g2_suru_ayari_dogrula(morf_hiz, hareket_hiz, yaw_hiz, egim_tavan):
    """Gorev 2 suru davranis ayarlarini dogrular.

    Aralik/irtifa ile AYNI sozlesme: 0 / None = BELIRTILMEDI ve o alan
    icin ucak kendi varsayilanini korur. Sinir disi deger SESSIZCE
    kirpilmaz, ParamRed atilir — mesaj dogrudan operatore gosterilir.

    🔴 UST SINIRLAR KEYFI DEGIL: yaw tavani PX4'un MPC_YAWRAUTO_MAX'i,
    egim tavani MPC_TILTMAX_AIR'i. Ustune cikmak ucagin YAPAMAYACAGI bir
    komut uretmek demek — 14 Agustos'ta MAKS_EGIM_DEG'in kodda 35 sabit
    olmasi tam bu sinifta bir hataydi (ucus_ayarlari.py basligi).

    Returns:
        tuple: (morf_hiz, hareket_hiz, yaw_hiz, egim_tavan);
        belirtilmeyen alan BELIRTILMEDI doner.
    """
    alanlar = (
        ('morf hizi', morf_hiz, MORF_HIZ_ALT, MORF_HIZ_UST, 'm/s'),
        ('hareket hizi', hareket_hiz, HAREKET_HIZ_ALT, HAREKET_HIZ_UST,
         'm/s'),
        ('yaw hizi', yaw_hiz, YAW_HIZ_ALT, YAW_HIZ_UST, 'deg/s'),
        ('egim tavani', egim_tavan, EGIM_TAVAN_ALT, EGIM_TAVAN_UST, 'deg'),
    )
    cikti = []
    for ad, ham, alt, ust, birim in alanlar:
        if ham in (None, ''):
            cikti.append(BELIRTILMEDI)
            continue
        v = _sayi(ad, ham)
        if v == BELIRTILMEDI:
            cikti.append(BELIRTILMEDI)
            continue
        if not (alt <= v <= ust):
            raise ParamRed(
                f'{ad} {v:g} {birim} kabul edilmedi. '
                f'Izinli: {alt:g}-{ust:g} {birim}.'
            )
        cikti.append(v)
    return tuple(cikti)


def dogrula(ad: str, deger, izinli) -> float:
    """Canli parametre istegini dogrular, sayiyi doner.

    Args:
        ad (str): parametre adi.
        deger: gelen ham deger.
        izinli: izinli adlar dizisi (MODE_MANAGER_CANLI / JOYSTICK_CANLI).

    Returns:
        float: kabul edilen deger.

    Raises:
        ParamRed: ad izinli degilse ya da deger gecersizse.
    """
    if ad not in izinli:
        raise ParamRed(
            f'{ad} canli degistirilemez — kapilar ve kimlik korumali '
            f'(G2-K9). Canli olanlar: {", ".join(izinli)}'
        )
    if isinstance(deger, bool):
        # bool int'in alt sinifi; float(True) = 1.0 sessizce gecerdi.
        raise ParamRed(f'{ad} sayi olmali')
    try:
        sayi = float(deger)
    except (TypeError, ValueError):
        raise ParamRed(f'{ad} sayi olmali')
    if not sayi > 0.0:
        raise ParamRed(f'{ad} > 0 olmali (gelen: {sayi:g})')
    return sayi
