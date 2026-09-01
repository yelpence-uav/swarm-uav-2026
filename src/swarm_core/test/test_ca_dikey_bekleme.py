# Copyright 2026 Yelpence
"""DIKEY AYRIM KURULANA KADAR YAKLASMA YOK — 1 Eylul 2026.

Operator onerisi: "kacinma devreye girerse drone yatayda ilerlemeyi
durduracak ve farkli bir irtifaya gecip oyle yatayda harekete devam
edecek."

NEDEN DOGRU — ca_core'un KENDI olcum tablosu (CaParams.k_yatay, 23 Agu):

    yaklasma    SAF DIKEY   SAF YATAY
     1.0 m/s      2.63 m      2.27 m
     2.5 m/s      1.01 m      2.02 m
     4.0 m/s      0.47 m      1.53 m   <- dikey COKUYOR

Coku ayar degil ZAMAN sorunu: 3 m'lik katmani kurmak 2-3 sn aliyor.
31 Agustos ucusunda birebir olculdu — kapanma 4,13 m/s, en yakin 1,65 m.
Kapanma durursa dikey kacis o zamani bulur.

🔴 BU DOSYANIN KILITLEDIGI SESSIZ HATALAR:
  * yaklasma bileseninin YANLIS ISARETLE silinmesi (ucagi komsuya iter),
  * ayrim saglandiktan sonra yatayin SERBEST BIRAKILMAMASI (formasyon
    hic kurulmaz, ucak komsusunun yaninda kilitlenir),
  * yaklasma yerine TUM yatay hizin silinmesi (suru cubukla ilerlerken
    ucak formasyondan 2-6 m geride kalir ve UCUNCU ucakla catisir).
Ucu de hata VERMEZ.
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..'))

from swarm_core.collision_avoidance.ca_core import (  # noqa: E402
    CaParams, CollisionAvoidanceCore, NeighborObs)

KATMAN = 3.0
ORAN = 0.8
GEREKEN = KATMAN * ORAN      # 2.4 m


def _p(bekle=ORAN, **kw):
    varsayilan = dict(
        d0=4.0, hard=2.0, r_min=1.5, katman_m=KATMAN,
        k_dikey=1.0, k_yatay=0.0, k_tan=0.0,
        v_dikey_max=1.5, a_dikey_max=1.0, kp_dikey=0.8,
        hist_m=0.5, dt=0.05, dikey_taban_m=4.0,
        agent_id=3, dikey_bekle_orani=bekle,
    )
    varsayilan.update(kw)
    return CaParams(**varsayilan)


def _komsu(dx=2.0, dy=0.0, rel_z=0.0, aid=1):
    """rel = KOMSU - BEN."""
    return NeighborObs(
        rel_x=dx, rel_y=dy, rel_z=rel_z, rel_vx=0.0, rel_vy=0.0,
        rel_vz=0.0,
        distance=math.sqrt(dx * dx + dy * dy + rel_z * rel_z),
        agent_id=aid)


def _tek(ca, vf, komsular, h=10.0):
    (vx, vy, _vz), _risk = ca.compute(vf, komsular, h_now=h)
    return vx, vy


# ---------------------------------------------------------------- kapali

def test_KAPALIYKEN_davranis_degismez():
    """0.0 = eski davranis. Yeni mekanizma opt-in olmali."""
    ca = CollisionAvoidanceCore(_p(bekle=0.0))
    vx, vy = _tek(ca, (2.0, 0.0, 0.0), [_komsu(dx=2.0)])
    assert vx == 2.0 and vy == 0.0
    assert ca.yatay_tutuldu is False


# --------------------------------------------------------------- tutulma

def test_ayrim_YOKKEN_yaklasma_silinir():
    ca = CollisionAvoidanceCore(_p())
    vx, vy = _tek(ca, (2.0, 0.0, 0.0), [_komsu(dx=2.0, rel_z=0.0)])
    assert abs(vx) < 1e-9, f'komsuya dogru {vx:.2f} m/s kaldi'
    assert ca.yatay_tutuldu is True


def test_yaklasma_ISARETI_dogru_komsuya_ITMEZ():
    """🔴 Isaret ters olsaydi hiz KOMSUYA DOGRU buyurdu."""
    ca = CollisionAvoidanceCore(_p())
    vx, _vy = _tek(ca, (2.0, 0.0, 0.0), [_komsu(dx=2.0)])
    assert vx <= 1e-9, 'yaklasma silinmek yerine artmis'


def test_UZAKLASAN_hiz_dokunulmaz():
    """Uzaklasmanin zarari yok; frenlemek formasyonu bozardi."""
    ca = CollisionAvoidanceCore(_p())
    vx, _vy = _tek(ca, (-2.0, 0.0, 0.0), [_komsu(dx=2.0)])
    assert vx == -2.0
    assert ca.yatay_tutuldu is False


def test_DIK_bilesen_KORUNUR():
    """🔴 En kritik test: tum yatay hiz silinmiyor.

    Suru cubukla ilerliyorken ucagi tamamen dondurmak onu formasyondan
    2-6 m geride birakir ve UCUNCU ucakla yeni bir catisma acar.
    """
    ca = CollisionAvoidanceCore(_p())
    # Komsu +x'te; hiz +x (yaklasma) ve +y (dik) bilesenli.
    vx, vy = _tek(ca, (2.0, 2.0, 0.0), [_komsu(dx=2.0, dy=0.0)])
    assert abs(vx) < 1e-9, 'yaklasma bileseni silinmedi'
    assert abs(vy - 2.0) < 1e-9, 'DIK bilesen de silinmis — suru kopar'


# ----------------------------------------------------- ayrim saglandiktan

def test_ayrim_SAGLANINCA_yatay_SERBEST():
    """Operatorun tarifindeki "farkli bir irtifaya gecip OYLE devam et".

    Serbest birakilmazsa ucak komsusunun yaninda kilitlenir ve formasyon
    HIC kurulmaz — 31 Agustos V gecisindeki kilitlenmenin aynisi.
    """
    ca = CollisionAvoidanceCore(_p())
    vx, _vy = _tek(ca, (2.0, 0.0, 0.0),
                   [_komsu(dx=2.0, rel_z=GEREKEN + 0.1)])
    assert abs(vx - 2.0) < 1e-9, 'ayrim varken yatay hala tutuluyor'
    assert ca.yatay_tutuldu is False


def test_ayrim_SINIRDA_hala_tutulur():
    ca = CollisionAvoidanceCore(_p())
    vx, _vy = _tek(ca, (2.0, 0.0, 0.0),
                   [_komsu(dx=2.0, rel_z=GEREKEN - 0.1)])
    assert abs(vx) < 1e-9


def test_ayrim_isaretten_BAGIMSIZ():
    """Komsu altimda da ustumde de ayrim ayrimdir."""
    for rz in (GEREKEN + 0.5, -(GEREKEN + 0.5)):
        ca = CollisionAvoidanceCore(_p())
        vx, _vy = _tek(ca, (2.0, 0.0, 0.0), [_komsu(dx=2.0, rel_z=rz)])
        assert abs(vx - 2.0) < 1e-9, f'rel_z={rz} icin serbest degil'


# ------------------------------------------------------------- yaricap

def test_d0_DISINDAKI_komsu_tutmaz():
    ca = CollisionAvoidanceCore(_p())
    vx, _vy = _tek(ca, (2.0, 0.0, 0.0), [_komsu(dx=6.0)])
    assert abs(vx - 2.0) < 1e-9
    assert ca.yatay_tutuldu is False


def test_iki_komsu_ikisi_de_silinir():
    ca = CollisionAvoidanceCore(_p())
    vx, vy = _tek(ca, (2.0, 2.0, 0.0),
                  [_komsu(dx=2.0, dy=0.0, aid=1),
                   _komsu(dx=0.0, dy=2.0, aid=2)])
    assert abs(vx) < 1e-9 and abs(vy) < 1e-9


# ---------------------------------------------------------- saha sayilari

def test_OLCULEN_kapanma_durdurulur():
    """31 Agustos: 4,13 m/s kapanma, en yakin 1,65 m.

    Ayni yaklasma hiziyla tek tikte komut sifirlanmali.
    """
    ca = CollisionAvoidanceCore(_p())
    vx, _vy = _tek(ca, (2.07, 0.0, 0.0), [_komsu(dx=3.5)])
    assert abs(vx) < 1e-9


def test_katman_sifirsa_KAPALI():
    """katman_m=0 ile bolme/anlamsiz esik olusmasin."""
    ca = CollisionAvoidanceCore(_p(katman_m=0.0, k_dikey=0.0))
    vx, _vy = _tek(ca, (2.0, 0.0, 0.0), [_komsu(dx=2.0)])
    assert abs(vx - 2.0) < 1e-9
