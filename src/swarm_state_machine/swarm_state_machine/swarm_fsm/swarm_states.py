"""Sürü seviyesi FSM durum sabitleri.

SwarmState.msg SWARM_* sabitleri ile birebir eşleşir.
"""

from enum import IntEnum


class SwarmState(IntEnum):
    """Sürü FSM durum sabitleri.

    SwarmState.msg SWARM_* ile birebir eşleşir.
    """

    UNKNOWN = 0
    IDLE = 1
    FORMING = 2
    NAVIGATING = 3
    EXECUTING_TASK = 4
    ROTATING = 5
    LANDING = 6
    RTL = 7
    FAILSAFE = 8
    MISSION_COMPLETE = 9


class FormationType(IntEnum):
    """Formasyon tipi sabitleri.

    SwarmState.msg / FormationCommand.msg FORMATION_* ile eşleşir.
    """

    UNKNOWN = 0
    OKBASI = 1
    V = 2
    CIZGI = 3
    CUSTOM = 99


# Sürünün havada olduğu state'ler — iniş/RTL kararlarında kullanılır.
AIRBORNE_SWARM_STATES = frozenset({
    SwarmState.FORMING,
    SwarmState.NAVIGATING,
    SwarmState.EXECUTING_TASK,
    SwarmState.ROTATING,
})

# Görev icrası sırasında olunabilecek state'ler.
ACTIVE_MISSION_STATES = frozenset({
    SwarmState.FORMING,
    SwarmState.NAVIGATING,
    SwarmState.EXECUTING_TASK,
    SwarmState.ROTATING,
    SwarmState.LANDING,
    SwarmState.RTL,
})
