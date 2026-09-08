# Copyright 2026 Yelpence
"""Kadro cokerse formasyon komutu SON TAM kadroyla yayinlanir.

🔴 8 EYLUL 2026 — OLCULDU, tahmin degil.

ylp01 bag `ylp01_20260905_171813` (5 Eylul 17:18, dusus ucusu),
`/swarm/public/formation/target` — takipcinin mesh'ten aldigi komutlar:

    97 mesaj,  formation_type dagilimi: {3: 97}
    agent_ids: (1,)      -> 32 mesaj      <- YALNIZ LIDERI adresliyor
               (1, 2, 3) -> 65 mesaj
    mesh_diag: form_rx=97  form_yarim=0   <- mesh SAGLAM, montaj SAGLAM

Komutlarin ucte biri yalniz lideri adresliyordu.
`formation_node._publish_setpoint` kadroda olmayan ucak icin SESSIZCE
cikiyor:

    if not agent_ids or self._agent_id not in agent_ids:
        return

Lider kendi listesinde oldugu icin komutu UYGULUYOR. Sonuc: lider
alcalir, takipciler donar, hicbir yerde hata gorunmez. Operatorun
bildirdigi "ilk QR'a gittikten sonra sadece lider irtifa degistirdi"
tam olarak budur.

KADRO NEDEN COKUYOR: `swarm_fsm_node.py:720` `active_agent_ids`'i ucak
basina DORT sarta bagliyor (healthy, origin_synced, not is_stale,
state in FORMATION_ACTIVE_STATES); dordu de mesh DURUM'undan besleniyor.
TEK kacan paket takipciyi o tick'te kadrodan dusuruyor.
"""

from swarm_missions.mission1_dynamic_swarm.orchestrator import (
    FormationTargetCmd,
    Mission1Orchestrator,
    OrchestratorConfig,
    OrchestratorInput,
)

S_NAVIGATE = 4

_IDS = [1, 2, 3]
_POS = [(0.0, 0.0, -15.0), (-7.0, 0.0, -15.0), (7.0, 0.0, -15.0)]
_CEN = (0.0, 0.0, -15.0)


def _orch(tam_kadro=3):
    o = Mission1Orchestrator(OrchestratorConfig(
        full_agent_count=tam_kadro,
        qr_okuma_irtifa_m=15.0,
    ))
    o.set_origin(41.0, 29.0)
    o.set_next_target(True, 41.001, 29.0)
    return o


def _inp(ids=None, poz=None, lider=True):
    ids = list(_IDS if ids is None else ids)
    poz = list(_POS[:len(ids)] if poz is None else poz)
    return OrchestratorInput(
        mission_state=S_NAVIGATE, qr_step=0, is_leader=lider,
        agent_ids=ids, positions=poz, centroid=_CEN, home=(0.0, 0.0, 0.0),
        swarm_yaw_deg=0.0,
    )


def _formasyonlar(cmds):
    return [c for c in cmds if isinstance(c, FormationTargetCmd)]


def _tam_kadroyla_kur(o):
    """Once TAM kadroyla bir tur kos: ofsetler dondurulsun, kadro ogrenilsin."""
    cmds = _formasyonlar(o.decide(_inp()))
    assert cmds, 'tam kadroda formasyon komutu uretilmedi'
    return cmds[0]


# ------------------------------------------------------------------ koruma

def test_TAM_KADRO_DOKUNULMAZ():
    """Kadro tamken koruma devreye GIRMEMELI — davranis aynen eski."""
    o = _orch()
    cmd = _tam_kadroyla_kur(o)
    assert [int(a) for a in cmd.agent_ids] == [1, 2, 3]
    assert o._st.kadro_koruma_sayaci == 0
    assert o.kadro_notu is None


def test_KADRO_COKUNCE_SON_TAM_KADRO_YAYINLANIR():
    """🔴 Kusurun ta kendisi: eskiden agent_ids=(1,) ile cikiyordu."""
    o = _orch()
    _tam_kadroyla_kur(o)
    o._st.handled_key = None                     # yeni komut uretilsin
    cmds = _formasyonlar(o.decide(_inp(ids=[1], poz=[_POS[0]])))
    assert cmds, 'kadro cokunce komut hic uretilmedi'
    assert [int(a) for a in cmds[0].agent_ids] == [1, 2, 3], (
        'komut hala tek ucagi adresliyor — takipciler bunu SESSIZCE atar'
    )


def test_OFSETLER_KADROYLA_PARALEL_KALIR():
    """Ofset dizisi kadroyla ayni uzunlukta olmali.

    Paralellik bozulursa `formation_node._slot_offset` indeksi bulamaz ve
    'slot ofseti yok' deyip setpoint atlar — korumayi yaparken ucagi
    sahipsiz birakmis olurduk.
    """
    o = _orch()
    _tam_kadroyla_kur(o)
    o._st.handled_key = None
    cmd = _formasyonlar(o.decide(_inp(ids=[1], poz=[_POS[0]])))[0]
    assert len(cmd.offsets) == len(cmd.agent_ids) == 3


def test_KORUMA_GORUNUR():
    """Sessiz koruma, korumasizliktan az farkli olurdu — not uretilmeli."""
    o = _orch()
    _tam_kadroyla_kur(o)
    o.kadro_notu                                  # tam kadro turunu temizle
    o._st.handled_key = None
    o.decide(_inp(ids=[1], poz=[_POS[0]]))
    notu = o.kadro_notu
    assert notu and 'KADRO KORUMASI' in notu
    assert o._st.kadro_koruma_sayaci == 1
    assert o.kadro_notu is None                   # okununca temizlenir


# ------------------------------------------------------- koruma UYGULANMAZ

def test_TAM_KADRO_HIC_GORULMEDIYSE_DOKUNMAZ():
    """Kalkista kadro hic tam olmadiysa uydurulacak bir kadro YOK."""
    o = _orch()
    cmds = _formasyonlar(o.decide(_inp(ids=[1, 2], poz=_POS[:2])))
    for c in cmds:
        assert [int(a) for a in c.agent_ids] == [1, 2]
    assert o._st.kadro_koruma_sayaci == 0


def test_full_agent_count_KAPALIYKEN_DOKUNMAZ():
    """full_agent_count=0 = kontrol kapali; eski davranis korunur."""
    o = _orch(tam_kadro=0)
    _tam_kadroyla_kur(o)
    o._st.handled_key = None
    cmds = _formasyonlar(o.decide(_inp(ids=[1], poz=[_POS[0]])))
    for c in cmds:
        assert [int(a) for a in c.agent_ids] == [1]
    assert o._st.kadro_koruma_sayaci == 0


def test_OFSET_BILINMIYORSA_DOKUNMAZ():
    """Ofset yoksa koruma UYGULANMAZ: yanlis slot, donmus takipciden kotu."""
    o = _orch()
    _tam_kadroyla_kur(o)
    o._st.frozen_offsets = {}                     # ofset bilgisi kayboldu
    o._st.handled_key = None
    cmds = _formasyonlar(o.decide(_inp(ids=[1], poz=[_POS[0]])))
    for c in cmds:
        assert [int(a) for a in c.agent_ids] == [1]
    assert o._st.kadro_koruma_sayaci == 0


# ------------------------------------------------------------------- kadro

def test_SON_TAM_KADRO_KOMUTSUZ_TICKLERDE_DE_OGRENILIR():
    """Kadro her tick kaydedilir — komut uretilmeyen tick'te de.

    Aksi halde koruma kadroyu ancak bir komut cikinca ogrenirdi ve tam
    o an kadro cokmusse hicbir sey bilmeden gecerdi.
    """
    o = _orch()
    o._st.handled_key = ('sahte',)                # komut uretme
    o.decide(_inp())
    assert o._st.son_tam_kadro == [1, 2, 3]
