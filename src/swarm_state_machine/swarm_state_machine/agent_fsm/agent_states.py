# Copyright 2026 Yelpence
"""Ajan FSM durum ve rol sabitleri."""

from enum import IntEnum


class AgentState(IntEnum):
    """Ajan FSM durum sabitleri."""

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


FORMATION_ACTIVE_STATES = frozenset({
    AgentState.IN_SWARM,
    AgentState.EXECUTING_TASK,
})
"""Formasyon hesaplarına (centroid, konum dizileri, kalite) dahil edilen durumlar.  # noqa: E501

İnmiş/düşmüş/ayrılmış ajanlar (LANDED, FAILSAFE, DETACHED ...) dışarıda kalır —
onlara slot atanırsa formasyonda ölü boşluk oluşur.

ARMED/TAKEOFF bilerek DIŞARIDA: bu durumlar eklendiğinde yerdeki dronlar centroid'e  # noqa: E501
girip merkez irtifasını yer seviyesine çekiyor, formasyon sürüyü aşağıda tutmaya  # noqa: E501
çalışıyor ve kalkış tırmanışı engelleniyor (denendi, dronlar yükselemeyip indi).  # noqa: E501
Kalkış dizilişini korumak için önce irtifa referansının konumdan ayrılması gerekir.  # noqa: E501

Tek tanım: centroid, konum dizileri ve kalite metriği AYNI kümeyi kullanmalıdır.  # noqa: E501
Biri değişip diğeri unutulursa ofsetler (konum - centroid) tutarsız çıkar.
"""


class AgentRole(IntEnum):
    """Ajan rol sabitleri."""

    UNKNOWN = 0
    LEADER = 1
    FOLLOWER = 2
    STANDBY = 3
    DETACHED = 4


class FlightMode(IntEnum):
    """PX4 ucus modu sabitleri."""

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


AVOIDANCE_EXCLUDE_STATES = frozenset({
    AgentState.DETACHED,
    AgentState.PRECISION_LANDING,
    AgentState.LANDED,
    AgentState.FAILSAFE,
})
