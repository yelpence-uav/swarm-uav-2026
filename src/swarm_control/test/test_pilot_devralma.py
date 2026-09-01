# Copyright 2026 Yelpence
"""PILOT DEVRALDIYSA MOD GERI ALINMAZ — 22 Agustos 2026, ucusta yasandi.

OLAY: operator kumandadan LAND dedi. Ucak inmeye basladi, sonra GERI
TIRMANDI. Her seferinde.

ZINCIR:
  1. Gorev kosucusu bekleme evresinde 0.5 sn'de bir hedefi tekrarliyor
     (21 Agustos'ta eklendi: kacinma o evrede ATIL kaliyordu).
  2. Her goto ile birlikte esp32_bridge KOSULSUZ 'offboard' yolluyor
     (_isle_goto).
  3. px4_bridge de KOSULSUZ set_offboard_mode() cagiriyordu.
  => pilot LAND -> AUTO.LAND -> 0.5 sn sonra offboard -> OFFBOARD ->
     yurutucu ucagi 10 m hedefe GERI SURUYOR.

Olculdu: 120 goto'ya karsilik 124 offboard komutu, ~3-5 Hz.

AYNI TEHLIKE 20 AGUSTOS'TA P0.12(b) OLARAK BULUNMUSTU ve esp32_bridge
tarafinda KISMEN kapatilmisti: YKI'den iptal gelince o ucagin
kuyrugundaki GOTO'lar atiliyor. Ama o koruma yalniz YKI yolundan gelen
iptali gorur — PILOT kumandadan mudahale ettiginde YKI BILMEZ.

Bu yuzden kapi px4_bridge'de: tek PX4 yazicisi ve pilotun modunu gorebilen
tek yer. Kaynak ne olursa olsun (mesh tekrari, bayat cerceve, gorev
kosucusu) pilot moddayken mod DEGISTIRILMEZ.
"""


from swarm_control.px4_interface.mavros_telemetry_mapper import (
    MODE_STR_TO_FLIGHT_MODE,
    PILOT_FLIGHT_MODES,
)


def test_PILOT_MODLARI_dogru_kodlar():
    """Kod->mod eslemesi sessizce kaymasin: pilot modlari tam bu bes."""
    assert PILOT_FLIGHT_MODES == frozenset({1, 2, 3, 9, 10})
    for ad in ('MANUAL', 'ALTCTL', 'POSCTL', 'ACRO', 'STABILIZED'):
        assert MODE_STR_TO_FLIGHT_MODE[ad] in PILOT_FLIGHT_MODES, \
            f'{ad} pilot modu sayilmiyor — pilot devralamaz'


def test_OTOMATIK_modlar_pilot_SAYILMAZ():
    """AUTO.* ve OFFBOARD gorevin kendi akisi; kapiya takilmamali.

    Ozellikle AUTO.LOITER: kalkis dizisi ORADAN offboard'a geciyor.
    Yanlislikla pilot sayilirsa ucak HIC KALKAMAZ.
    """
    for ad in ('OFFBOARD', 'AUTO.LOITER', 'AUTO.LAND', 'AUTO.RTL',
               'AUTO.MISSION', 'AUTO.TAKEOFF'):
        assert MODE_STR_TO_FLIGHT_MODE[ad] not in PILOT_FLIGHT_MODES, \
            f'{ad} yanlislikla pilot modu sayiliyor'


def _kaynak_govde():
    """px4_bridge ROS'suz import edilemiyor; _on_fsm_command govdesini oku."""
    import os
    import re
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yol = os.path.join(kok, 'swarm_control', 'px4_interface', 'px4_bridge.py')
    with open(yol, encoding='utf-8') as f:
        tam = f.read()
    m = re.search(r"elif cmd == 'offboard':.*?(?=\n        else:)", tam, re.S)
    assert m, "offboard dali bulunamadi"
    return m.group(0)


def test_offboard_dali_PILOT_KAPISI_tasiyor():
    govde = _kaynak_govde()
    assert 'PILOT_FLIGHT_MODES' in govde, \
        'offboard komutu pilot modunu DENETLEMIYOR — pilot devralamaz'
    assert 'return' in govde, 'pilot moddayken erken cikis yok'


def _kod_satirlari(govde):
    """Yorumlari ATAR.

    Ilk yazimda bu test kendi ACIKLAMA yorumumdaki 'set_offboard_mode()'
    metnini yakalayip yanlis yerde hata verdi — kodun sirasini sinamak
    isterken metnin sirasini sinamis oldu.
    """
    cikti = []
    for satir in govde.splitlines():
        kirpik = satir.split('#', 1)[0]
        if kirpik.strip():
            cikti.append(kirpik)
    return '\n'.join(cikti)


def test_kapi_set_offboard_mode_ONCESINDE():
    """Kapi cagridan SONRA olursa hicbir ise yaramaz."""
    kod = _kod_satirlari(_kaynak_govde())
    i_kapi = kod.index('PILOT_FLIGHT_MODES')
    i_cagri = kod.index('set_offboard_mode')
    assert i_kapi < i_cagri, \
        'pilot denetimi set_offboard_mode() SONRASINDA — mod yine alinir'


def test_kapi_streaming_i_de_KAPATIYOR():
    """Yalniz mod degistirmemek YETMEZ: _offboard_streaming acik kalirsa
    OffboardControlMode akmaya devam eder ve PX4 pilot modundan cikip
    offboard'a donebilir."""
    kod = _kod_satirlari(_kaynak_govde())
    kapi = kod[kod.index('PILOT_FLIGHT_MODES'):kod.index('return')]
    assert '_offboard_streaming = False' in kapi, \
        'pilot moddayken offboard akisi durdurulmuyor'


# =====================================================================
# 31 AGUSTOS 2026 — AYNI KUSURUN 'land' DALINDAKI IKIZI
#
# Yukaridaki 22 Agustos duzeltmesi kapiyi YALNIZ 'offboard' dalina
# koydu ve yorumunda AUTO.LAND/RTL'yi BILEREK muaf tuttu: "onlar
# gorevin kendi akisinin parcasi". Bu muafiyet YANLISTI.
#
# OLAY (ylp00, Gorev 2 ilk gercek kalkisi): kumandadan SwD ile inis
# verildi, AUTO.LAND basladi, emniyet pilotu 0.05 sn sonra cubuklara
# asildi, PX4 "Pilot took over using sticks" deyip POSCTL'e gecti —
# ve mode_manager'in 1 Hz'lik inis tekrari ucagi pilottan GERI ALDI.
# 20 saniye boyunca saniyede bir. Rosbag olcumu:
#     6 mod degisimi (AUTO.LAND <-> POSCTL)
#     istenen roll +-19.5 deg, GERCEK pitch -27.4 deg
#     PX4 statustext: 13 kez "Pilot took over using sticks"
# Operator: "asiri yalpaladi neredeyse dusecekti".
#
# Emniyet pilotu SON savunma hattidir. Yazilim onu ezemez.
# =====================================================================


def _dal_govde(baslangic: str, bitis: str) -> str:
    """_on_fsm_command icindeki tek bir dali metin olarak dondurur."""
    import os
    import re
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yol = os.path.join(kok, 'swarm_control', 'px4_interface', 'px4_bridge.py')
    with open(yol, encoding='utf-8') as f:
        tam = f.read()
    m = re.search(
        re.escape(baslangic) + r'.*?(?=\n        ' + re.escape(bitis) + ')',
        tam,
        re.S,
    )
    assert m, f'{baslangic} dali bulunamadi'
    return m.group(0)


def _land_govde():
    return _dal_govde("elif cmd == 'land':", "elif cmd == 'rtl':")


def _rtl_govde():
    return _dal_govde("elif cmd == 'rtl':", "elif cmd == 'offboard':")


def test_land_dali_PILOT_KAPISI_tasiyor():
    """Pilot POSCTL'e gectiyse AUTO.LAND GERI ZORLANMAMALI."""
    govde = _land_govde()
    assert 'PILOT_FLIGHT_MODES' in govde, \
        "land komutu pilot modunu DENETLEMIYOR — 31 Agustos kusuru geri geldi"
    assert 'return' in govde, 'pilot moddayken erken cikis yok'


def test_land_kapisi_cmd_sender_ONCESINDE():
    """Kapi cagridan SONRA olursa hicbir ise yaramaz."""
    kod = _kod_satirlari(_land_govde())
    assert kod.index('PILOT_FLIGHT_MODES') < kod.index('_cmd_sender.land'), \
        'pilot denetimi land() SONRASINDA — mod yine alinir'


def test_land_defter_tutma_KAPIDAN_ONCE():
    """Kapi yalniz MOD YAZMAYI engellemeli, defter tutmayi DEGIL.

    Pilot ucagi aldiysa offboard akisinin susmasi ve bayat kalkis
    hedefinin silinmesi HER HALUKARDA dogru — bunlar kapinin disinda,
    kosulsuz kalmali. Kapinin arkasina duserlerse pilot devraldiginda
    OffboardControlMode akmaya devam eder ve PX4 offboard'a donebilir.
    """
    kod = _kod_satirlari(_land_govde())
    i_kapi = kod.index('PILOT_FLIGHT_MODES')
    for alan in ('_offboard_streaming = False',
                 '_target_altitude_ned = None',
                 '_takeoff_anchor_x = None'):
        assert alan in kod, f'{alan} land dalinda yok'
        assert kod.index(alan) < i_kapi, \
            f'{alan} pilot kapisinin ARKASINDA — pilot devralinca atlanir'


def test_rtl_dali_PILOT_KAPISI_tasiyor():
    """RTL pilottan ucagi almak acisindan LAND'den daha agir."""
    govde = _rtl_govde()
    assert 'PILOT_FLIGHT_MODES' in govde, \
        'rtl komutu pilot modunu DENETLEMIYOR'
    assert 'return' in govde, 'pilot moddayken erken cikis yok'


def test_rtl_kapisi_cmd_sender_ONCESINDE():
    kod = _kod_satirlari(_rtl_govde())
    assert kod.index('PILOT_FLIGHT_MODES') < kod.index('_cmd_sender.return_home'), \
        'pilot denetimi return_home() SONRASINDA — mod yine alinir'


def test_UC_DAL_DA_kapili():
    """offboard/land/rtl: PX4'un modunu degistiren UC dal da kapili olmali.

    Yeni bir mod komutu eklenirse bu test onu yakalamaz — ama en
    azindan mevcut ucunun kapisi sessizce dusmez.
    """
    import os
    import re
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yol = os.path.join(kok, 'swarm_control', 'px4_interface', 'px4_bridge.py')
    with open(yol, encoding='utf-8') as f:
        tam = f.read()
    m = re.search(r'def _on_fsm_command.*?\n    # =====', tam, re.S)
    assert m, '_on_fsm_command bulunamadi'
    govde = _kod_satirlari(m.group(0))
    assert govde.count('PILOT_FLIGHT_MODES') == 3, \
        (f'_on_fsm_command icinde {govde.count("PILOT_FLIGHT_MODES")} pilot '
         f'kapisi var, 3 bekleniyor (offboard + land + rtl)')
