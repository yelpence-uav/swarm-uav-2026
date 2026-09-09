# Copyright 2026 Yelpence
"""BUYUK BASLIK DEGISIMINDE slotlar EN YAKINA yeniden atanir.

🔴 8 EYLUL 2026, SAHADA OLCULDU — operator: "biri baya uzaklasti".

QR1 -> QR2 bacagi. QR2, QR1'in 12.4 m BATISINDA; seyir basligi
108° -> -110°, yani ~180° dondu. Diziliş rijit oldugu icin iki KANAT
fiziksel olarak yer degistirdi (konumlar ylp00'in kalkis noktasina gore):

    23:25:40   ylp02  +5.3 dogu   (BATI kanadi)
    23:26:10   ylp02 +18.7 dogu   <- suru BATIYA giderken 13.4 m DOGUYA
    23:26:20   ylp02  +8.0 dogu   (DOGU kanadi)   ylp01 ise +17.8 -> -4.4

Yani iki ucak formasyonun ICINDEN gecerek yer degistirdi. Yan etkisi
olculdu: gecis sirasinda en dar ayrim 2.41 m (kacinmanin yatay son care
kabugu 2.0 m).

COZUM: baslik esikten fazla dondiyse donmus atama BIR KEZ cozulur,
`build_slot_assignment` (Hungarian) herkesi EN YAKIN slota atar. 180°
donus boylece "formasyon aynalandi, herkes yerinde" olur.

⚠️ SARTNAME SINIRI: bir ucak AYRILDIYSA formasyon yeniden hesaplanmaz.
O yuzden yeniden atama YALNIZ TAM KADRODA yapilir.
"""

import math

from swarm_missions.mission1_dynamic_swarm.orchestrator import (
    Mission1Orchestrator,
    OrchestratorConfig,
    OrchestratorInput,
)

S_EXECUTE = 5
_IDS = [1, 2, 3]
# Konumlar (kuzey, dogu, asagi). Cizgi formasyonunun slotlari GOVDE
# cercevesinde dogu ekseninde; heading 90°'de dunyada KUZEY eksenine
# doner. Fixture'i o eksene koyuyoruz ki atama dejenere olmasin —
# ucaklar slot cizgisinin uzerinde dursun.
_POS = [(0.0, 0.0, -15.0), (7.0, 0.0, -15.0), (-7.0, 0.0, -15.0)]


def _orch(esik=90.0, kadro=3):
    o = Mission1Orchestrator(OrchestratorConfig(
        full_agent_count=kadro, yeniden_atama_derece=esik,
    ))
    o.set_origin(41.0, 29.0)
    return o


def _inp(pos=None, ids=None):
    p = list(pos if pos is not None else _POS)
    i = list(ids if ids is not None else _IDS)
    return OrchestratorInput(
        mission_state=S_EXECUTE, qr_step=0, is_leader=True,
        agent_ids=i, positions=p,
        centroid=(0.0, 0.0, -15.0), home=(0.0, 0.0, 0.0), time_in_state=1.0,
    )


def _ata(o, heading, tip=3, pos=None, ids=None):
    """Verilen baslikta slot ofsetlerini uretir (tip 3 = cizgi)."""
    inp = _inp(pos, ids)
    return o._assign(tip, 7.0, (0.0, 0.0, -15.0), heading, inp)


# --------------------------------------------------------- asil kusur

def test_180_DERECE_DONUSTE_YENIDEN_ATANIR():
    """🔴 Kusurun ta kendisi: kanatlar yer degistirip icten geciyordu."""
    o = _orch()
    ilk = _ata(o, 90.0)
    donuk1 = dict(o._st.frozen_offsets)
    _ata(o, -90.0)                       # 180 derece donus
    donuk2 = dict(o._st.frozen_offsets)
    assert donuk1 != donuk2, (
        'baslik 180° dondu ama diziliş DONUK kaldi — kanatlar yine '
        'formasyonun icinden gecip yer degistirir (8 Eylul, ylp02 13.4 m)'
    )
    assert ilk is not None


def test_YENI_ATAMA_EN_YAKIN_SLOTU_VERIR():
    """Yeniden atama, her ucagi BULUNDUGU yere en yakin slota koymali."""
    o = _orch()
    _ata(o, 90.0)
    yeni = _ata(o, -90.0)
    # Ofsetler heading ile donduruluyor. Dunya cercevesinde her ucagin
    # hedefi KENDI konumuna 1 m'den yakin olmali: 180° donusun dogru
    # karsiligi "diziliş aynalandi, herkes yerinde kaldi".
    h = math.radians(-90.0)
    for (px, py, _pz), (ox, oy, _oz) in zip(_POS, yeni):
        wx = ox * math.cos(h) - oy * math.sin(h)
        wy = ox * math.sin(h) + oy * math.cos(h)
        assert math.hypot(px - wx, py - wy) < 1.0, (
            f'ucak ({px},{py}) icin hedef ({wx:.1f},{wy:.1f}) — '
            f'en yakin slot degil; kanat degistirmis olur'
        )


def test_KUCUK_DONUSTE_DIZILIS_KORUNUR():
    """30° donus atamayi bozmamali; her karede yeniden dizilmek titretir."""
    o = _orch()
    _ata(o, 90.0)
    d1 = dict(o._st.frozen_offsets)
    _ata(o, 120.0)
    assert dict(o._st.frozen_offsets) == d1


def test_ESIK_KAPALIYKEN_ESKI_DAVRANIS():
    """0 = kapali; eski davranis birebir donmeli."""
    o = _orch(esik=0.0)
    _ata(o, 90.0)
    d1 = dict(o._st.frozen_offsets)
    _ata(o, -90.0)
    assert dict(o._st.frozen_offsets) == d1


# ---------------------------------------------------- sartname siniri

def test_EKSIK_KADRODA_YENIDEN_ATAMA_YOK():
    """🔴 Bir ucak ayrildiysa formasyon YENIDEN HESAPLANMAZ (sartname)."""
    o = _orch(kadro=3)
    _ata(o, 90.0)
    d1 = dict(o._st.frozen_offsets)
    _ata(o, -90.0, pos=_POS[:2], ids=_IDS[:2])       # bir ucak dustu
    assert dict(o._st.frozen_offsets) == d1, (
        'eksik kadroda yeniden dizildi — ayrilan ucak formasyonu bozamamali'
    )


def test_KONUM_YOKSA_YENIDEN_ATAMA_YOK():
    """Atama maliyeti konumlardan hesaplaniyor; konum yoksa dokunma."""
    o = _orch()
    _ata(o, 90.0)
    d1 = dict(o._st.frozen_offsets)
    _ata(o, -90.0, pos=[])
    assert dict(o._st.frozen_offsets) == d1


def test_NOT_YAZILIYOR():
    """Sessiz yeniden dizilme, operator icin aciklanamaz hareket demektir."""
    o = _orch()
    _ata(o, 90.0)
    o.atama_notu                                  # temizle
    _ata(o, -90.0)
    n = o.atama_notu
    assert n and 'YENIDEN ATAMA' in n and '180' in n.replace('°', '')


def test_NOT_OKUNUNCA_TEMIZLENIR():
    """kadro_notu deseni: iki kez okunursa ikincisi bos gelmeli."""
    o = _orch()
    _ata(o, 90.0)
    _ata(o, -90.0)
    assert o.atama_notu is not None
    assert o.atama_notu is None
