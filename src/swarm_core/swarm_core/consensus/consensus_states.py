# Copyright 2026 Yelpence
"""Consensus icin durum kumeleri ve sabitler."""

from swarm_interfaces.msg import AgentStatus

# Lider adayi olabilmek icin ajanin bulunmasi gereken durumlar.
ELIGIBLE_STATES = frozenset({
    AgentStatus.STATE_ARMED,
    AgentStatus.STATE_TAKEOFF,
    AgentStatus.STATE_IN_SWARM,
    AgentStatus.STATE_EXECUTING_TASK,
})

# Havada sayilan durumlar.
AIRBORNE_STATES = frozenset({
    AgentStatus.STATE_TAKEOFF,
    AgentStatus.STATE_IN_SWARM,
    AgentStatus.STATE_EXECUTING_TASK,
})

# Secim disi roller.
INELIGIBLE_ROLES = frozenset({
    AgentStatus.ROLE_STANDBY,
    AgentStatus.ROLE_DETACHED,
})
