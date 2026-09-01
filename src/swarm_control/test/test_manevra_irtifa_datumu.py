# Copyright 2026 Yelpence
"""MANEVRA MODUNDA SURU ALCALDI — 1 Eylul 2026, ucusta olculdu.

OLAY: operator manevra moduna gecti, UC UCAK DA ~1,7 m alcaldi. ylp02
ardindan OFFBOARD'dan dusup ALTCTL'e gecti (yatay konum tutma YOK) ve
sahanin disina suruklendi.

OLCULEN ZINCIR (ylp02):
    mode_manager gonderdi   sp.z = -6,97 m   (MUTLAK NED, 7,0 m yukarida)
    kalkis zemin referansi  +1,68 m
    px4_bridge hesapladi    -5,29 m
    PX4'e giden hedef       6,72 -> 5,74 -> 5,29 m  (ENU yukari)
    ucak                    takip etti, alcaldi

SEBEP: `target_z = _takeoff_baslangic_z + sp.z` TUM setpoint'lere
uygulaniyordu. Bu kural GUIDED GOTO icin dogru (YKI "8 m" derken kalkis
zeminini kasteder), FORMASYON/MANEVRA icin YANLIS (mutlak NED gelir).

🔴 NEDEN AYLARCA GORUNMEDI: hareket modunda maske HIZ modunda (0x09C7),
PX4 konum alanini HIC KULLANMIYOR. Hata orada da vardi ama olusuz. Manevra
maskeyi konuma cevirince gizli hata gerceklesti. Bu dosya onu kilitliyor.

ROS gerektirmez: kaynak metni denetleniyor (px4_bridge donanimsiz import
edilemiyor — test_pilot_devralma.py ile ayni yontem).
"""

import os
import re


def _govde() -> str:
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yol = os.path.join(kok, 'swarm_control', 'px4_interface', 'px4_bridge.py')
    with open(yol, encoding='utf-8') as f:
        tam = f.read()
    # 🔴 NON-GREEDY REGEX KULLANMA: gerekce yorumunun kendisi de
    # 'heading_valid' geciyor ve arama KODA ULASMADAN duruyordu.
    # Sabit pencere hem yorumu hem kodu kapsiyor.
    i = tam.index('target_z = float(sp.z)')
    return tam[i - 200:i + 400]


def test_ofset_GUIDED_ICIN_kaliyor():
    """2 Agustos dersi: guided goto zemine goreli, bu KORUNMALI.

    Kaldirilirsa ucak kalkistan sonra zemin referansi kadar alcalir ve
    gorev hedefe hic varamaz (o gun operator uc kez elle indirdi).
    """
    g = _govde()
    assert '_takeoff_baslangic_z + float(sp.z)' in g, \
        'guided goto icin zemin ofseti kaldirilmis — 2 Agustos hatasi geri gelir'


def test_ofset_FORMASYONA_uygulanmaz():
    """1 Eylul dersi: formasyon/manevra MUTLAK NED gonderir."""
    g = _govde()
    assert 'not sp.heading_valid' in g, (
        'zemin ofseti formasyon/manevra setpointlerine de uygulaniyor — '
        'manevraya gecince suru zemin referansi kadar ALCALIR')


def test_iki_kosul_AYNI_satirda():
    """Ofset yalnizca IKISI birden saglandiginda uygulanmali."""
    g = _govde()
    kosul = re.search(
        r'if self\._takeoff_baslangic_z is not None and not sp\.heading_valid:',
        g)
    assert kosul, 'kosul beklenen halde degil'


def test_OLCULEN_sayilarla_hesap():
    """Sahada olculen degerlerle aritmetigi kilitler."""
    sp_z = -6.97          # mode_manager, mutlak NED
    zemin = 1.68          # olculen kalkis zemin referansi
    hatali = zemin + sp_z          # eski davranis
    dogru = sp_z                   # yeni davranis
    assert abs(hatali - (-5.29)) < 0.02, 'olculen hata yeniden uretilemedi'
    assert abs(dogru - (-6.97)) < 1e-9
    # Fark = ucaklarin alcaldigi miktar
    assert abs((dogru - hatali) - (-1.68)) < 0.02
