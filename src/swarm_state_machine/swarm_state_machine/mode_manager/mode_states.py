# Copyright 2026 Yelpence
"""Semi-autonomous kontrol FSM durum sabitleri."""

from enum import IntEnum


class ModeState(IntEnum):
    """mode_manager FSM durum sabitleri."""

    IDLE = 0
    PREFLIGHT = 1
    TAKEOFF = 2
    READY = 3
    MOVEMENT = 4
    MANEUVER = 5
    HOLD = 6
    LANDING = 7
    RTL = 8
    EMERGENCY = 9
    COMPLETED = 10


class ControlMode(IntEnum):
    """Kontrol modu sabitleri."""

    UNKNOWN = 0
    SWARM_MOVEMENT = 1
    MANEUVER = 2


AIRBORNE_MODE_STATES = frozenset({
    ModeState.READY,
    ModeState.MOVEMENT,
    ModeState.MANEUVER,
    ModeState.HOLD,
    ModeState.RTL,
})

ACTIVE_CONTROL_STATES = frozenset({
    ModeState.READY,
    ModeState.MOVEMENT,
    ModeState.MANEUVER,
    ModeState.HOLD,
})
