# Copyright 2026 Yelpence
"""P0.12(a): uygunlugunu yitiren lider liderligi BIRAKIR.

OLCULEN ARIZA (20 Agustos 2026, kod okunarak dogrulandi):
`ctx.is_leader` hicbir yerde geri alinmiyordu. `election.decide_change` ilk
satirlari

    candidate = min(effective) if effective else 0
    if candidate == 0:
        return None

ile cikiyor, yani KIMSE UYGUN DEGILSE `_set_leader` hic cagrilmiyor ve bayrak
True takili kaliyor. Inis sonrasi iki ucak da IDLE olunca yerde duran, disarm
olmus ucak mesh'e 10 Hz LeaderHeartbeat basmaya DEVAM ediyordu (19 Agustos'ta
'own_airborne' kapisi kalkinca yayin yalniz ctx.is_leader'a baglanmisti).

Ikinci ucusta konteyner yeniden baslatilmazsa: diger ucak arm olur, kendini
secer, sonra yerdeki hayalet kalp atisi gelir, _adopt_leader liderligi olu
ucaga GERI verir, bir sonraki tick geri alir -> saniyede 5-10 lider degisimi,
pervaneler donerken ve guided komutlarla AYNI ESP-NOW kanalinda.

Bu testler duzeltmeyi ve BOZULMAMASI gerekenleri sabitler.
"""

import time
from unittest.mock import MagicMock

from swarm_core.consensus.consensus_context import AgentRec, ConsensusContext
from swarm_core.consensus.consensus_node import ConsensusNode

from swarm_interfaces.msg import AgentStatus


def _rec(agent_id, state, now=None, healthy=True, ekf=True, batarya=0.0):
    # last_update MUTLAKA time.monotonic()'e gore olmali — _tick gercek
    # saati kullaniyor ve is_stale(now, 3.0) sabit bir damgayi hep bayat
    # sayar. (Ilk yazimda 100.0 verilmisti ve uc test bu yuzden dustu;
    # kod degil test yanlisti.)
    if now is None:
        now = time.monotonic()
    r = AgentRec(agent_id)
    r.state = state
    r.role = AgentStatus.ROLE_FOLLOWER
    r.healthy = healthy
    r.estimator_ok = ekf
    r.battery_v = batarya
    r.last_update = now
    return r


def _dugum(agent_id=1, lider_id=1, agents=None):
    """ROS'suz minimal ConsensusNode (bkz. test_formation_node.py deseni)."""
    n = object.__new__(ConsensusNode)
    n._agent_id = agent_id
    ctx = ConsensusContext(
        agent_id=agent_id, agent_count=3, stale_s=3.0,
        hb_timeout_s=0.3, battery_min_v=0.0, grace_s=1.5,
    )
    ctx.agents = agents or {}
    ctx.leader_id = lider_id
    ctx.is_leader = (lider_id == agent_id)
    ctx.last_hb_time = time.monotonic()
    n._ctx = ctx
    n.get_logger = MagicMock()
    n._publish_heartbeat = MagicMock()
    n._pub_leader_changed = MagicMock()
    n._apply_role = MagicMock()
    n._publish_election_result = MagicMock()
    return n


# --- ASIL ARIZA -------------------------------------------------------------

def test_inis_sonrasi_lider_bayragi_birakiliyor():
    """Herkes IDLE'a dusunce lider liderligi birakir ve kalp atisi keser."""
    n = _dugum(agent_id=1, lider_id=1, agents={
        1: _rec(1, AgentStatus.STATE_IDLE),      # biz indik
        3: _rec(3, AgentStatus.STATE_IDLE),      # o da indi
    })
    n._tick()
    assert n._ctx.is_leader is False, 'liderlik birakilmadi'
    assert n._ctx.leader_id == 0
    n._publish_heartbeat.assert_not_called()


def test_birakma_sonrasi_tekrar_tick_sessiz():
    """Birakildiktan sonra tekrar tekrar olay/rol yayilmaz."""
    n = _dugum(agent_id=1, lider_id=1, agents={
        1: _rec(1, AgentStatus.STATE_IDLE),
    })
    n._tick()
    cagri = n._pub_leader_changed.call_count
    n._tick()
    n._tick()
    assert n._pub_leader_changed.call_count == cagri, 'her tickte olay yayiyor'


def test_birakmada_secim_turu_ARTIRILMAZ():
    """Cekilme bir SECIM degil — round artarsa komsunun mesru secimi duser.

    consensus_node.py:287 `msg.election_round < ctx.election_round` filtresi
    var; turu bosuna artirmak komsudan gelen gecerli secimleri sessizce
    dusururdu.
    """
    n = _dugum(agent_id=1, lider_id=1, agents={
        1: _rec(1, AgentStatus.STATE_IDLE),
    })
    once = n._ctx.election_round
    n._tick()
    assert n._ctx.election_round == once


# --- BOZULMAMASI GEREKENLER -------------------------------------------------

def test_uygun_lider_liderligi_KORUR():
    """Havada, saglikli lider hicbir sey kaybetmez ve kalp atisi surer."""
    n = _dugum(agent_id=1, lider_id=1, agents={
        1: _rec(1, AgentStatus.STATE_IN_SWARM),
        3: _rec(3, AgentStatus.STATE_IN_SWARM),
    })
    n._tick()
    assert n._ctx.is_leader is True
    assert n._ctx.leader_id == 1
    n._publish_heartbeat.assert_called_once()


def test_devralacak_biri_varsa_NORMAL_DEVIR_yolu_calisir():
    """Biz uygunlugu yitirdik ama komsu uygun -> birakma degil DEVIR.

    Bu ayrim onemli: birakma dali yalniz 'devralacak kimse yok' durumunu
    yakalamali, havada calisan lider degisimi mantigina dokunmamali.
    """
    n = _dugum(agent_id=1, lider_id=1, agents={
        1: _rec(1, AgentStatus.STATE_IDLE),        # biz dustuk
        3: _rec(3, AgentStatus.STATE_IN_SWARM),    # o havada ve uygun
    })
    n._tick()
    assert n._ctx.leader_id == 3, 'liderlik devredilmedi'
    assert n._ctx.is_leader is False
    # devir bir SECIMDIR — turu artar (birakmanin tersi)
    assert n._ctx.election_round == 1


def test_takipci_lider_degilse_birakma_dali_calismaz():
    """is_leader False olan ajan bu daldan etkilenmez."""
    n = _dugum(agent_id=3, lider_id=1, agents={
        3: _rec(3, AgentStatus.STATE_IDLE),
    })
    n._tick()
    n._pub_leader_changed.assert_not_called()


def test_birakma_sonrasi_yeniden_secilebilir():
    """Arm olunca normal secim yolu yeniden isler."""
    n = _dugum(agent_id=1, lider_id=1, agents={
        1: _rec(1, AgentStatus.STATE_IDLE),
    })
    n._tick()
    assert n._ctx.is_leader is False

    # tekrar arm: uygun hale geldik, bootstrap grace'i dolmus varsayalim
    n._ctx.agents[1] = _rec(1, AgentStatus.STATE_ARMED)
    n._ctx.bootstrap_since = 0.0
    n._tick()                       # bootstrap saatini kurar
    n._ctx.bootstrap_since = 1.0    # grace doldu
    n._tick()
    assert n._ctx.is_leader is True, 'yeniden secilemedi'
    assert n._ctx.leader_id == 1


# --- IKINCI KAPI ------------------------------------------------------------

def test_uygun_degilken_bayrak_elle_kaldirilsa_bile_kalp_atisi_cikmaz():
    """_adopt_leader/_on_election bayragi uygun degilken kaldirirsa da sessiz.

    Kusak ve pantolon askisi: birakma dali bayragi zaten indiriyor, ama
    baska bir yol bayragi disaridan kaldirabilir.
    """
    n = _dugum(agent_id=1, lider_id=1, agents={
        1: _rec(1, AgentStatus.STATE_IDLE),
    })
    n._tick()
    n._ctx.is_leader = True          # baska bir yol bayragi geri kaldirdi
    n._publish_heartbeat.reset_mock()
    n._tick()
    n._publish_heartbeat.assert_not_called()
