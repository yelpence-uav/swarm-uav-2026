# Copyright 2026 Yelpence
"""22 Agustos 2026: kacinma UCAGIN YAPAMAYACAGI ivme istiyordu.

OPERATOR: "baya bildigin sag sol yapti, devrilecek gibi."
KAYITTAN OLCULDU (ylp00, ayni ucus):

    evre                 roll araligi          genlik   MAKS EGIM
    asili (once)         -5.0 .. +6.1          11 deg   11.6 deg
    KACIS                -24.7 .. +28.3        53 deg   34.0 deg  <<<
    DONUS                -15.7 .. +5.2         21 deg   22.0 deg
    asili (sonra)        -2.7 .. -0.3           2 deg    4.6 deg

SEBEP: ca_core ivme sinirlari ucus_ayarlari'na HIC baglanmamisti:

    slew_normal    =  4.0 m/s2  ->  22.2 derece
    slew_emergency = 30.0 m/s2  ->  71.9 derece   IMKANSIZ

slew_emergency komsu `hard`in icine girince devreye giriyor. Operator
6.14 m'ye geldi, hard=6.0 — tam devreye girdi. Ucak 72 derece egilemez;
elinden geleni yapti (34 derece), yetisemedi, komut degisti, ters yone
egildi. Yalpa BU.

CLAUDE.md 8 zaten diyordu: "Acilari elle ayarlama. Egim tavani ivmeden
turetiliyor (a = g*tan(theta))". Hiz, ivme, egim hepsi ucus_ayarlari'nda
turetiliyordu — KACINMA HARIC.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src' / 'gcs'))

from swarm_core.collision_avoidance.ca_core import (  # noqa: E402
    CaParams,
    CollisionAvoidanceCore,
    NeighborObs,
)

YERCEKIMI = 9.81


def _egim(ivme):
    return math.degrees(math.atan(ivme / YERCEKIMI))


# --- 1) IVMELER EGIM TAVANINA BAGLI ---------------------------------------

def test_turetilen_ivmeler_EGIM_TAVANINI_ASMAZ():
    import ucus_ayarlari as A
    tavan = A.EGIM_TAVANI_DEG
    assert _egim(A.KACINMA_IVME_ACIL_MPS2) <= tavan + 0.01, (
        f'acil kacis ivmesi {A.KACINMA_IVME_ACIL_MPS2:.2f} m/s2 = '
        f'{_egim(A.KACINMA_IVME_ACIL_MPS2):.1f} derece, tavan {tavan}')
    assert _egim(A.KACINMA_IVME_NORMAL_MPS2) <= tavan + 0.01
    assert A.KACINMA_IVME_NORMAL_MPS2 < A.KACINMA_IVME_ACIL_MPS2, \
        'normal kacis acil kacistan sert olamaz'


def test_ESKI_SABIT_gercekten_imkansizdi():
    """Regresyon belgesi: 30 m/s2 ~72 derece ister. Bir daha konmasin."""
    assert _egim(30.0) > 70.0
    import ucus_ayarlari as A
    assert A.KACINMA_IVME_ACIL_MPS2 < 30.0 / 4, \
        'acil ivme hala eski buyuklukte'


def test_donus_ivmesi_kacistan_DUSUK():
    """Tehlike aninda sert, tehlike gecince sakin."""
    import ucus_ayarlari as A
    assert A.KACINMA_DONUS_IVME_MPS2 < A.KACINMA_IVME_NORMAL_MPS2 / 3
    # 6 m'lik donusun tepe hizi: v = sqrt(a*d)
    assert math.sqrt(A.KACINMA_DONUS_IVME_MPS2 * 6.0) < 2.0, \
        'donus tepe hizi hala 2 m/s ustunde (olculen 3.21 idi)'


# --- 2) KAPI SUREKLI ------------------------------------------------------

def _cikis(P, d3, kapanma):
    ca = CollisionAvoidanceCore(P)
    ca.reset((0.0, 0.0, 0.0))
    n = NeighborObs(d3, 0.0, 0.0, -kapanma, 0.0, 0.0, d3)
    vx = 0.0
    for _ in range(60):
        (vx, _vy, _vz), _r = ca.compute((0.0, 0.0, 0.0), [n])
    return vx


def test_hard_sinirinda_BASAMAK_YOK():
    """Eski hali `hard`i gecerken kapiyi 0'dan 1'e atliyordu; ucak itilip
    disari cikinca kapi kapaniyor, geri gelince aciliyordu."""
    P = CaParams(d0=10.0, hard=6.0, dt=0.05,
                 slew_normal=3.58, slew_emergency=5.66)
    onc = None
    ensic = 0.0
    d = 7.6
    while d >= 5.4:
        vx = _cikis(P, d, 0.3)          # YAVAS yaklasma: en kotu hal
        if onc is not None:
            ensic = max(ensic, abs(vx - onc))
        onc = vx
        d -= 0.2
    assert ensic < 2.5, (
        f'0.2 m adimda {ensic:.2f} m/s sicrama var — kapi hala basamakli '
        f'(duzeltme oncesi 3.19 idi)')


def test_KABUK_ICINDE_tam_kuvvet_KORUNDU():
    """Duzeltme korumayi zayiflatmamali."""
    P = CaParams(d0=10.0, hard=6.0, dt=0.05,
                 slew_normal=3.58, slew_emergency=5.66)
    for d3 in (5.5, 5.0, 4.0):
        for kap in (-2.0, 0.0, 1.0):
            assert _cikis(P, d3, kap) <= -3.0, \
                f'sert kabukta ({d3} m) itme zayifladi'


def test_d0_DISINDA_hala_sessiz():
    P = CaParams(d0=10.0, hard=6.0, dt=0.05)
    for d3 in (10.5, 12.0):
        assert abs(_cikis(P, d3, 1.0)) < 1e-9


def test_slew_ile_EGIM_SINIRLI():
    """Hedef zipla da ziplamasin: slew ivmeyi sinirliyor, yani egim de
    sinirli. Bir tikta uretilen en buyuk hiz degisimi -> ivme -> egim."""
    P = CaParams(d0=10.0, hard=6.0, dt=0.05,
                 slew_normal=3.58, slew_emergency=5.66)
    ca = CollisionAvoidanceCore(P)
    ca.reset((0.0, 0.0, 0.0))
    n = NeighborObs(5.0, 0.0, 0.0, -3.0, 0.0, 0.0, 5.0)   # kabuk ICINDE
    onc = 0.0
    en_ivme = 0.0
    for _ in range(60):
        (vx, _vy, _vz), _r = ca.compute((0.0, 0.0, 0.0), [n])
        en_ivme = max(en_ivme, abs(vx - onc) / P.dt)
        onc = vx
    assert _egim(en_ivme) <= 31.0, (
        f'tek tikta {en_ivme:.1f} m/s2 = {_egim(en_ivme):.1f} derece '
        f'talep ediliyor (olculen yalpa 34 dereceydi)')
