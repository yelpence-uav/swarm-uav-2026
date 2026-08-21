# Copyright 2026 Yelpence
"""P1.14: tek yonlu kopmada iki lider KALICI ve SESSIZ kaliyordu.

`_on_heartbeat` split-brain'i yalniz TEK YONDE cozuyordu:

    elif ctx.leader_id == 0 or msg.leader_id < ctx.leader_id:
        self._adopt_leader(...)          # BUYUK id, kucuge uyar

Kucuk-id taraf rakibi tamamen yok sayiyordu — log bile basmiyordu. Iki
sonucu vardi:
  1. Split-brain kucuk-id tarafta GORUNMEZ (ucus kaydinda hic iz yok)
  2. Cozum, rakibin BIZIM kalp atisimizi duymasina bagli — yani kurtulus
     yolu, kopmus olan yonun ta kendisi.

Asimetrik linkte (biz->o kopuk, o->biz calisiyor) bu KALICI iki lider
demek. 21 Agustos ucusunda olculdu: lider kimligi mesh'e KALP ATISIYLA
tasiniyor (secim cercevesi hic gelmedi), yani yakinsamanin fiili tek
yolu bu.

DUZELTME: rakip, kalp atislarimiza RAGMEN `rakip_grace_s` boyunca iddiada
israr ederse "kalp atisim ona ulasmiyor" deyip BOYUN EGERIZ. Sebebi: o
bizi duymuyor ama biz onu duyuyoruz, yani calisan yon O->BIZ; komutu
fiilen ulastirabilen taraf O. Ardindan kucuk-id onalmasi bastirilir,
yoksa 10 Hz'de titrerdik.
"""

from swarm_core.consensus import election
from swarm_core.consensus.consensus_context import ConsensusContext

from swarm_interfaces.msg import ElectionResult

SIMDI = 1000.0


def _ctx(agent_id=1, leader_id=1, is_leader=True):
    c = ConsensusContext(
        agent_id=agent_id, agent_count=3, stale_s=3.0,
        hb_timeout_s=1.0, battery_min_v=0.0, grace_s=1.5,
    )
    c.leader_id = leader_id
    c.is_leader = is_leader
    c.last_hb_time = SIMDI
    return c


# --- bastirma alani -------------------------------------------------------

def test_baglam_bastirma_alani_var_ve_sifirdan_baslar():
    """Yeni alan olmadan election.py getattr ile 0.0 varsayardi."""
    assert _ctx().onalma_bastir_until == 0.0


def test_bastirma_yokken_kucuk_id_onalmasi_CALISIR():
    """Eski davranis korunuyor: bastirma yoksa kucuk id lideri alir."""
    c = _ctx(agent_id=1, leader_id=3, is_leader=False)
    karar = election.decide_change(c, {1, 3}, SIMDI)
    assert karar == (1, ElectionResult.REASON_UNKNOWN)


def test_bastirma_acikken_onalma_YAPILMAZ():
    """Boyun egdikten sonra aninda geri almak titreme uretirdi."""
    c = _ctx(agent_id=1, leader_id=3, is_leader=False)
    c.onalma_bastir_until = SIMDI + 10.0
    assert election.decide_change(c, {1, 3}, SIMDI) is None


def test_bastirma_suresi_dolunca_onalma_geri_gelir():
    c = _ctx(agent_id=1, leader_id=3, is_leader=False)
    c.onalma_bastir_until = SIMDI - 0.01
    assert election.decide_change(c, {1, 3}, SIMDI) is not None


def test_bastirma_GERCEK_lider_kaybini_engellemez():
    """En kritik kilit: bastirma LEADER_FAULT dalini vurmamali.

    Vursaydi tek yonlu kopmadan sonraki 10 sn boyunca lider gercekten
    olse bile kimse devralmazdi.
    """
    c = _ctx(agent_id=1, leader_id=3, is_leader=False)
    c.onalma_bastir_until = SIMDI + 10.0
    karar = election.decide_change(c, {1}, SIMDI)   # lider 3 kumede YOK
    assert karar == (1, ElectionResult.REASON_LEADER_FAULT)


def test_bastirma_bootstrap_secimini_engellemez():
    """Lider hic yokken bastirma sessizlige yol acmamali."""
    c = _ctx(agent_id=1, leader_id=0, is_leader=False)
    c.onalma_bastir_until = SIMDI + 10.0
    c.bootstrap_since = SIMDI - 2.0
    assert election.decide_change(c, {1, 3}, SIMDI) is not None


# --- TAHKIM: dugum davranisi ----------------------------------------------

import time                                              # noqa: E402
from unittest.mock import MagicMock                       # noqa: E402

from swarm_core.consensus.consensus_context import AgentRec  # noqa: E402
from swarm_core.consensus.consensus_node import ConsensusNode  # noqa: E402

from swarm_interfaces.msg import AgentStatus, LeaderHeartbeat  # noqa: E402


def _rec(agent_id, state=AgentStatus.STATE_ARMED):
    # last_update gercek monotonic'e gore — _tik is_stale(now, 3.0) kullaniyor.
    r = AgentRec(agent_id)
    r.state = state
    r.role = AgentStatus.ROLE_UNKNOWN
    r.healthy = True
    r.estimator_ok = True
    r.battery_v = 0.0
    r.last_update = time.monotonic()
    return r


def _dugum(agent_id=1, lider_id=1, rakip_grace=3.0, bastir=10.0):
    n = object.__new__(ConsensusNode)
    n._agent_id = agent_id
    ctx = ConsensusContext(
        agent_id=agent_id, agent_count=3, stale_s=3.0,
        hb_timeout_s=1.0, battery_min_v=0.0, grace_s=1.5,
    )
    ctx.agents = {1: _rec(1), 3: _rec(3)}
    ctx.leader_id = lider_id
    ctx.is_leader = (lider_id == agent_id)
    ctx.last_hb_time = time.monotonic()
    n._ctx = ctx
    n._uygunsuz_since = 0.0
    n._rakip_id = 0
    n._rakip_since = 0.0
    n._rakip_son_hb = 0.0
    n._rakip_grace_s = rakip_grace
    n._onalma_bastir_s = bastir
    n.get_logger = MagicMock()
    n._publish_heartbeat = MagicMock()
    n._pub_leader_changed = MagicMock()
    n._apply_role = MagicMock()
    n._publish_election_result = MagicMock()
    n._event_pub = MagicMock()
    n.get_clock = MagicMock()
    return n


def _hb(lider_id, tur=1):
    m = LeaderHeartbeat()
    m.leader_id = lider_id
    m.election_round = tur
    m.sequence_num = 1
    return m


def test_rakip_hb_si_ONCE_izlenir_hemen_boyun_egilmez():
    """Tek bir rakip atisi yeterli olsaydi bootstrap yarisi liderligi ucururdu."""
    n = _dugum(agent_id=1, lider_id=1)
    n._on_heartbeat(_hb(3))
    assert n._rakip_id == 3, 'rakip hic fark edilmedi (eski davranis)'
    n._tick()
    assert n._ctx.is_leader is True, 'grace dolmadan boyun egdi'
    assert n._ctx.leader_id == 1


def test_grace_dolunca_rakibe_BOYUN_EGILIR():
    """Asil duzeltme: israrci rakip = kalp atisim ona ulasmiyor."""
    n = _dugum(agent_id=1, lider_id=1)
    n._on_heartbeat(_hb(3))
    n._rakip_since -= 3.5                    # grace doldu
    n._rakip_son_hb = time.monotonic()       # rakip hala yayinda
    n._tick()
    assert n._ctx.is_leader is False, 'kalici iki lider — duzeltme calismadi'
    assert n._ctx.leader_id == 3
    assert n._ctx.onalma_bastir_until > time.monotonic()
    assert n._event_pub.publish.called, 'sessiz devir — kayitta iz kalmaz'


def test_rakip_susarsa_boyun_EGILMEZ_ve_izleme_sifirlanir():
    """Gecici bir carpisma liderligi ucurmamali."""
    n = _dugum(agent_id=1, lider_id=1)
    n._on_heartbeat(_hb(3))
    n._rakip_since -= 3.5
    n._rakip_son_hb = time.monotonic() - 2.0   # hb_timeout(1.0) asildi
    n._tick()
    assert n._ctx.is_leader is True
    assert n._rakip_id == 0, 'izleme sifirlanmadi'


def test_KUCUK_id_rakip_eski_yoldan_benimsenir_tahkime_girmez():
    """Buyuk-id taraf hicbir sey beklemeden uyar — bozulmamali."""
    n = _dugum(agent_id=3, lider_id=3)
    n._on_heartbeat(_hb(1))
    assert n._ctx.leader_id == 1, 'kucuk id benimsenmedi'
    assert n._rakip_id == 0, 'kucuk id yanlislikla rakip sayildi'


def test_lider_degilsek_rakip_izlemesi_kurulmaz():
    """Takipciyken baska liderin atisi bizi ilgilendirmez."""
    n = _dugum(agent_id=1, lider_id=3)
    n._ctx.is_leader = False
    n._on_heartbeat(_hb(5))
    assert n._rakip_id == 0


def test_boyun_egdikten_sonra_tikler_liderligi_GERI_ALMAZ():
    """Bastirma olmasa decide_change bir sonraki tikte geri alirdi (titreme)."""
    n = _dugum(agent_id=1, lider_id=1)
    n._on_heartbeat(_hb(3))
    n._rakip_since -= 3.5
    n._rakip_son_hb = time.monotonic()
    n._tick()
    assert n._ctx.leader_id == 3
    for _ in range(5):
        n._ctx.last_hb_time = time.monotonic()   # rakip lider yayinda
        n._tick()
    assert n._ctx.leader_id == 3, 'liderlik geri alindi — titreme'
    assert n._ctx.is_leader is False
