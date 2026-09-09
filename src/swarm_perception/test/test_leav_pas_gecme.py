# Copyright 2026 Yelpence
"""'leav' (ayrilma) komutu PAS GECILIR — KARAR-21.

🔴 8 EYLUL 2026, OPERATOR KARARI: "leav olmayacak. Geldiginde pas
gecilecek. Onu sakin unutma."

Sahada 30 QR sayfasi var ve alti tanesi BIZE (team_slot=1) ayrilma
komutu veriyor. Hedefler:
    sayfa  4 -> ajan 5   (filoda YOK; 1-2-3 ucuyoruz)
    sayfa  8 -> ajan 4   (filoda YOK)
    sayfa 11 -> ajan 1   (KAMERALI SABIT LIDERIMIZ)
    sayfa 19 -> ajan 2
    sayfa 21 -> ajan 3
    sayfa 27 -> ajan 4   (filoda YOK)

Yani komut uygulansaydi ya var olmayan bir ucagi ayirmaya calisacaktik
ya da kamerayi ve lideri suruden kopartacaktik.

KESME NOKTASI: `QRDetector._apply_command`. Kaynak tek nokta oldugu icin
mission_fsm adim sirasi, swarm_fsm ve agent_fsm ayrilmayi HIC gormez.

SESSIZ DEGIL: istenen ajan ve renk alanlara YAZILIR, yalniz
`detach_active` False kalir — YKI'de "istendi ama uygulanmadi" gorunur.
"""

import json
import sys
from unittest.mock import MagicMock

# pyzbar/zxing saha kutuphaneleri laptopta yok; cozucu mantigi onlardan
# BAGIMSIZ (biz JSON ayristirmayi siniyoruz). test_qr_detector.py ile ayni yol.
sys.modules.setdefault('pyzbar', MagicMock())
sys.modules.setdefault('pyzbar.pyzbar', MagicMock())

from swarm_perception.vision_node.qr_detector import QRDetector  # noqa: E402

# Sahadaki gercek sayfalar (operator 8 Eylul'de verdi).
SAYFA_04 = ('{"qr":4,"w":4,"mis":[[["leav",5,"r"]],[["frm","ok",6],'
            '["mnv",0,0],["alt",24]],[["frm","l",6],["mnv",15,-10],'
            '["alt",24]]],"team":{"1":[1,2],"2":[1,5],"3":[3,2],'
            '"4":[3,5],"5":[1,5]}}')
SAYFA_11 = ('{"qr":1,"w":4,"mis":[[["frm","ok",6],["mnv",15,5],["alt",24]],'
            '[["frm","ok",5],["mnv",10,5],["alt",26]],[["leav",1,"b"]]],'
            '"team":{"1":[3,3],"2":[3,4],"3":[1,2],"4":[2,5],"5":[2,2]}}')
SAYFA_01 = ('{"qr":1,"w":4,"mis":[[["frm","l",5],["mnv",10,10],["alt",28]],'
            '[["frm","ok",6],["mnv",5,0],["alt",18]],[["frm","ok",6],'
            '["mnv",0,0],["alt",25]]],"team":{"1":[3,4],"2":[1,2],'
            '"3":[3,3],"4":[1,4],"5":[1,2]}}')


def _coz(metin, slot=1):
    d = QRDetector(team_slot=slot)
    return d, d._parse_qr_text(metin)


# ----------------------------------------------------------- asil karar

def test_SADECE_LEAV_ICEREN_PAKET_AYRILMA_URETMEZ():
    """🔴 KARAR-21: sayfa 4 bize 'ajan 5'i ayir' diyor — uygulanmaz."""
    _, p = _coz(SAYFA_04)
    assert p['detach_active'] is False


def test_LIDERI_AYIRMA_KOMUTU_DA_PAS_GECILIR():
    """Sayfa 11 kamerali sabit lideri (ajan 1) ayirmak istiyor."""
    _, p = _coz(SAYFA_11)
    assert p['detach_active'] is False


def test_ISTENEN_AJAN_VE_RENK_GORUNUR_KALIR():
    """Sessiz yutma YOK: ne istendigi alanlarda durmali."""
    _, p = _coz(SAYFA_04)
    assert p['target_agent_id'] == 5
    assert p['detach_color'] == 1                      # r = KIRMIZI
    _, p11 = _coz(SAYFA_11)
    assert p11['target_agent_id'] == 1
    assert p11['detach_color'] == 2                    # b = MAVI


def test_PAS_GECME_SAYILIYOR():
    d, _ = _coz(SAYFA_04)
    assert d.atlanan_leav == 1


# ------------------------------------------- gorev AKISI kesilmemeli

def test_LEAV_PAKETI_HALA_GECERLI_VE_SONRAKI_QR_KORUNUR():
    """Pas gecmek gorevi durdurmamali: sürü bir sonraki QR'a gitmeli."""
    _, p = _coz(SAYFA_04)
    assert p['valid'] is True
    assert p['target_active'] is True
    assert p['next_qr'] == 2
    assert p['complete_mission'] is False


def test_LEAV_PAKETINDE_BASKA_ADIM_YOK():
    """Sayfa 4'un bizim paketimiz YALNIZ leav; digerleri kapali kalmali."""
    _, p = _coz(SAYFA_04)
    assert p['formation_active'] is False
    assert p['maneuver_active'] is False
    assert p['altitude_active'] is False


def test_GOREV_ADIMI_DOGRUDAN_DONE_OLUR():
    """mission_fsm sirasi ayrilma gormemeli — dogrudan DONE."""
    from swarm_state_machine.mission_fsm.mission_transitions import (
        QrTaskStep, find_first_qr_step,
    )

    class _Sahte:
        pass

    _, p = _coz(SAYFA_04)
    q = _Sahte()
    for k in ('formation_active', 'maneuver_active',
              'altitude_active', 'detach_active'):
        setattr(q, k, p[k])
    assert find_first_qr_step(q) == QrTaskStep.DONE


# ------------------------------------------------ normal paket bozulmadi

def test_NORMAL_PAKET_ETKILENMEDI():
    """Sayfa 1 bize paket 3: OKBASI 6 m, manevra yok, 25 m, sonraki QR4."""
    _, p = _coz(SAYFA_01)
    assert p['valid'] is True
    assert p['formation_active'] is True
    assert p['formation_type'] == 1                    # ok = OKBASI
    assert p['spacing_m'] == 6.0
    assert p['altitude_active'] is True
    assert p['altitude_agl_m'] == 25.0
    assert p['next_qr'] == 4
    assert p['detach_active'] is False


def test_BASKA_SLOT_ICIN_DE_GECERLI():
    """Karar takim slotundan bagimsiz: leav hicbir slotta uygulanmaz."""
    for slot in (1, 2, 3, 4, 5):
        d = QRDetector(team_slot=slot)
        for metin in (SAYFA_04, SAYFA_11):
            assert d._parse_qr_text(metin)['detach_active'] is False


def test_HAM_METIN_KORUNUYOR():
    """QR'in ham icerigi degistirilmemeli — hakem kaydi icin."""
    ham = json.loads(SAYFA_04)
    assert ham['mis'][0][0][0] == 'leav'               # kaynak dokunulmadi
