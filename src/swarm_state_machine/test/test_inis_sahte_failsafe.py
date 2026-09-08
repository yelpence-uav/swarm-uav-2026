# Copyright 2026 Yelpence
"""Otonom `land` her seferinde SAHTE bir failsafe tetikliyordu.

🔴 SAHADA IKI KEZ OLCULDU (5 Eylul ylp01, 8 Eylul ylp00):

    RETURN_HOME -> LANDING   1788848472.63
    LANDING     -> FAILSAFE  1788848477.63     = TAM 5.000 sn

Otonom inişte PX4 OFFBOARD'dan cikip AUTO.LAND'e geciyor — BEKLENEN
davranis, komutu biz veriyoruz. Ama `AgentState.LANDING` `_AIRBORNE`
kumesindeydi ve OFFBOARD-kaybi kurali o kumeye bakiyordu:

    if ctx.state in _AIRBORNE and offboard_lost_since ... > 5.0:
        critical_fault=True, EVENT_OFFBOARD_LOST

Yani HER OTONOM INIS bir kritik ariza ile bitiyordu. Inis zaten surdugu
icin sonucu disaridan gorunmuyor; bedeli olay kaydinin kirlenmesi ve
FSM'in gereksiz yere FAILSAFE'e girmesi.

⚠️ QGC/PX4 AYARIYLA KARISTIRILMASIN: 8 Eylul'de operator QGC'de land'i
uyariya aldi; o PX4 katmani ve bu kurala DOKUNMAZ.

DUZELTME: kural artik `_OFFBOARD_GEREKLI = _AIRBORNE - {LANDING}`
kumesine bakiyor. Yalniz LANDING cikarildi — digerlerinde OFFBOARD'da
KALINMALI ve orada OFFBOARD kaybi GERCEK arizadir.
"""

import time

from swarm_state_machine.agent_fsm.agent_health_monitor import (
    _AIRBORNE,
    _OFFBOARD_GEREKLI,
    _OFFBOARD_LOSS_TIMEOUT_S,
)
from swarm_state_machine.agent_fsm.agent_states import AgentState


# --------------------------------------------------------------- kumeler

def test_LANDING_OFFBOARD_KURALINDAN_CIKARILDI():
    """🔴 Kusurun ta kendisi."""
    assert AgentState.LANDING in _AIRBORNE, (
        'LANDING havada bir durum; _AIRBORNE icinde KALMALI (irtifa tavani, '
        'EKF, RC-failsafe gibi diger kontroller ona da uygulanmali)'
    )
    assert AgentState.LANDING not in _OFFBOARD_GEREKLI


def test_DIGER_HAVA_DURUMLARI_KORUNUYOR():
    """OFFBOARD kaybi bunlarda GERCEK ariza — koruma kaldirilmamali."""
    for d in (AgentState.TAKEOFF, AgentState.IN_SWARM,
              AgentState.EXECUTING_TASK, AgentState.RETURN_HOME,
              AgentState.PRECISION_LANDING, AgentState.REJOINING,
              AgentState.DETACHED):
        assert d in _OFFBOARD_GEREKLI, f'{d} korumasi kayboldu'


def test_YALNIZ_LANDING_CIKARILDI():
    """Kume farki TAM OLARAK {LANDING} olmali — baska bir sey duserse fark et."""
    assert _AIRBORNE - _OFFBOARD_GEREKLI == {AgentState.LANDING}


# ----------------------------------------------------------------- kural

class _Ctx:
    """AgentContext yerine gecen kabuk — kural yalniz iki alanini okuyor."""

    def __init__(self, state, gecen_s):
        self.state = state
        self.offboard_lost_since = time.monotonic() - gecen_s


def _tetikler(ctx):
    """Kuralin kendisi (agent_health_monitor:243 ile birebir)."""
    return (ctx.state in _OFFBOARD_GEREKLI
            and ctx.offboard_lost_since is not None
            and (time.monotonic() - ctx.offboard_lost_since)
            > _OFFBOARD_LOSS_TIMEOUT_S)


def test_INISTE_5_SANIYE_SONRA_ARIZA_YOK():
    """Sahada olculen tam senaryo: LANDING + 5 sn -> ariza OLMAMALI."""
    assert not _tetikler(_Ctx(AgentState.LANDING, _OFFBOARD_LOSS_TIMEOUT_S + 1))
    assert not _tetikler(_Ctx(AgentState.LANDING, 30.0))


def test_SURUDEYKEN_OFFBOARD_KAYBI_HALA_ARIZA():
    """En kritik yon: gercek OFFBOARD kaybi susturulmus olmamali."""
    assert _tetikler(_Ctx(AgentState.IN_SWARM, _OFFBOARD_LOSS_TIMEOUT_S + 1))
    assert _tetikler(_Ctx(AgentState.RETURN_HOME, _OFFBOARD_LOSS_TIMEOUT_S + 1))


def test_ESIK_DOLMADAN_ARIZA_YOK():
    """5 sn dolmadan tetiklenmemeli (gecici mod gecisleri icin pay)."""
    assert not _tetikler(_Ctx(AgentState.IN_SWARM,
                              _OFFBOARD_LOSS_TIMEOUT_S - 1))
