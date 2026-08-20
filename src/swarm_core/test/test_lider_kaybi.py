# Copyright 2026 Yelpence
"""P0.14(a): lider kalp atisi zaman asimi yolu OLU idi.

`election.effective_set` liderin kalp atisi kesildiginde onu kumeden atiyor,
AMA kapisi `own_airborne` idi:

    own_airborne = own.state in AIRBORNE_STATES
    AIRBORNE_STATES = {TAKEOFF, IN_SWARM, EXECUTING_TASK}

Gecis doneminde `kalkis_olayla=false` oldugu icin FSM UCUS BOYUNCA ARMED'da
kaliyor ve ARMED o kumede YOK. Yani `heartbeat_timeout_ms` hicbir kararda
kullanilmiyordu — cok ajanli denetimde 2/2 bagimsiz dogrulayici onayladi.

Somut sonucu: liderin consensus'u coker ama agent_fsm + esp32_bridge
calismaya devam ederse takipci lider kaybini ASLA fark etmez.

Dogru sart ADAY olmak: lider kaybiyla ilgilenmemizin sebebi havada olmamiz
degil, kendimizin secime girebiliyor olmasi.
"""

from swarm_core.consensus import election

from swarm_interfaces.msg import AgentStatus


class _Rec:
    def __init__(self, state):
        self.state = state


class _Ctx:
    def __init__(self, lider_id, is_leader, hb_yasi_s, lider_state):
        self.leader_id = lider_id
        self.is_leader = is_leader
        self.hb_timeout_s = 1.0
        self.last_hb_time = 1000.0 - hb_yasi_s
        self.agents = {lider_id: _Rec(lider_state)} if lider_id else {}


ARMED = AgentStatus.STATE_ARMED
TAKEOFF = AgentStatus.STATE_TAKEOFF
IDLE = AgentStatus.STATE_IDLE
SIMDI = 1000.0


def test_kalp_atisi_kesilince_lider_kumeden_ATILIR():
    """Asil arıza: bu yol eskiden HIC calismiyordu."""
    ctx = _Ctx(lider_id=1, is_leader=False, hb_yasi_s=2.0, lider_state=TAKEOFF)
    sonuc = election.effective_set(ctx, SIMDI, own_aday=True, eligible={1, 3})
    assert 1 not in sonuc, 'lider kaybi hala fark edilmiyor'
    assert 3 in sonuc


def test_ARMED_takipci_de_lider_kaybini_gorur():
    """P0.14(a)'nin ta kendisi — gecis doneminde FSM ARMED'da kaliyor.

    Eski kod `own_airborne` istedigi ve ARMED o kumede olmadigi icin bu
    senaryoda lider ASLA dusurulmuyordu.
    """
    ctx = _Ctx(lider_id=1, is_leader=False, hb_yasi_s=2.0, lider_state=ARMED)
    sonuc = election.effective_set(ctx, SIMDI, own_aday=True, eligible={1, 3})
    assert 1 not in sonuc, 'ARMED takipci lider kaybini goremiyor (P0.14a)'


def test_kalp_atisi_TAZEYSE_lider_kalir():
    ctx = _Ctx(lider_id=1, is_leader=False, hb_yasi_s=0.2, lider_state=TAKEOFF)
    sonuc = election.effective_set(ctx, SIMDI, own_aday=True, eligible={1, 3})
    assert 1 in sonuc, 'taze kalp atisi oldugu halde lider dusuruldu'


def test_UYGUN_DEGILSEK_lideri_dusurmeyiz():
    """Aday degilsek secim kararina karisma.

    Yerde bekleyen ucak lideri dusurmemeli.
    """
    ctx = _Ctx(lider_id=1, is_leader=False, hb_yasi_s=5.0, lider_state=TAKEOFF)
    sonuc = election.effective_set(ctx, SIMDI, own_aday=False, eligible={1, 3})
    assert 1 in sonuc


def test_KENDIMIZ_liderken_dal_calismaz():
    ctx = _Ctx(lider_id=1, is_leader=True, hb_yasi_s=9.0, lider_state=TAKEOFF)
    sonuc = election.effective_set(ctx, SIMDI, own_aday=True, eligible={1, 3})
    assert 1 in sonuc


def test_lider_YERDE_ise_dusurulmez():
    """Yerdeki lider kalp atisi yayinlamayabilir — bu kayip degil."""
    ctx = _Ctx(lider_id=1, is_leader=False, hb_yasi_s=9.0, lider_state=IDLE)
    sonuc = election.effective_set(ctx, SIMDI, own_aday=True, eligible={1, 3})
    assert 1 in sonuc
