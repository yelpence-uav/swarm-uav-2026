# Copyright 2026 Yelpence
"""Sürü seviyesi gorev FSM durum ve tip enumlari."""

from enum import IntEnum


class MissionState(IntEnum):
    """Sürü seviyesi görev FSM durumları."""

    UNKNOWN = 0
    IDLE = 1
    PREFLIGHT = 2
    SYNCHRONIZED_TAKEOFF = 3
    NAVIGATE_TO_QR = 4
    EXECUTE_QR_TASK = 5
    WAIT_AT_QR = 6
    ROTATE_TO_NEXT = 7
    SEMI_AUTONOMOUS = 8
    RETURN_HOME = 9
    LANDING = 10
    MISSION_COMPLETE = 11
    ABORTED = 12
    PAUSED = 13


class MissionType(IntEnum):
    """Görev tipi."""

    UNKNOWN = 0
    DYNAMIC_SWARM = 1
    SEMI_AUTONOMOUS = 2


class QrTaskStep(IntEnum):
    """EXECUTE_QR_TASK QR alt-adımları."""

    NONE = 0
    FORMATION = 1
    MANEUVER = 2
    ALTITUDE = 3
    DETACH = 4
    DONE = 5
