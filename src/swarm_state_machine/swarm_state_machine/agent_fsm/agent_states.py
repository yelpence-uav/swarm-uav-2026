from enum import IntEnum


class AgentState(IntEnum):
    """Ajan FSM durum sabitleri. AgentStatus.msg STATE_* ile birebir eşleşir."""

    UNKNOWN = 0
    IDLE = 1
    ARMING = 2
    ARMED = 3
    TAKEOFF = 4
    IN_SWARM = 5
    EXECUTING_TASK = 6
    DETACHED = 7
    PRECISION_LANDING = 8
    WAITING_REJOIN = 9
    REJOINING = 10
    RETURN_HOME = 11
    LANDING = 12
    LANDED = 13
    FAILSAFE = 14
    STANDBY = 15


class AgentRole(IntEnum):
    """Ajan rol sabitleri. AgentStatus.msg ROLE_* ile birebir eşleşir."""

    UNKNOWN = 0
    LEADER = 1
    FOLLOWER = 2
    STANDBY = 3
    DETACHED = 4


class FlightMode(IntEnum):
    """PX4 uçuş modu sabitleri. AgentStatus.msg FLIGHT_MODE_* ile eşleşir."""

    UNKNOWN = 0
    MANUAL = 1
    ALTCTL = 2
    POSCTL = 3
    OFFBOARD = 4
    AUTO_MISSION = 5
    AUTO_LOITER = 6
    AUTO_RTL = 7
    AUTO_LAND = 8
    ACRO = 9
    STABILIZED = 10


# State 7,8,13,14: avoidance hesabına dahil edilmez (ORCA/APF)
AVOIDANCE_EXCLUDE_STATES = frozenset({
    AgentState.DETACHED,
    AgentState.PRECISION_LANDING,
    AgentState.LANDED,
    AgentState.FAILSAFE,
})
