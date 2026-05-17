"""mission_states.py — MissionState, MissionType, QrTaskStep enumları."""

from enum import IntEnum


class MissionState(IntEnum):
    """Sürü seviyesi görev FSM durumları.

    /swarm/internal/mission/state topicinde UInt8 olarak yayınlanır.
    Tüketiciler: formation_control, mission1_dynamic_swarm, GCS.
    """

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
    """Görev tipi (GCS'in TriggerMission.srv mission_id ile seçtiği)."""

    UNKNOWN = 0
    DYNAMIC_SWARM = 1
    SEMI_AUTONOMOUS = 2


class QrTaskStep(IntEnum):
    """EXECUTE_QR_TASK içinde sırayla çalışan QR alt-adımları.

    Çalışma sırası: FORMATION -> MANEUVER -> ALTITUDE -> DETACH.
    Aktif adımlar QRMissionData.*_active bayraklarıyla belirlenir.
    Tamamlanma SystemEvent ile bildirilir (EVENT_FORMATION_REACHED,
    EVENT_MANEUVER_COMPLETED, EVENT_AGENT_DETACHED).
    """

    NONE = 0
    FORMATION = 1
    MANEUVER = 2
    ALTITUDE = 3
    DETACH = 4
    DONE = 5
