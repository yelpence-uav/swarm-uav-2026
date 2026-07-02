"""Consensus için durum kümeleri ve sabitler.

Tek kaynak: lider adayı (uygunluk) ve havada-olma durum kümeleri.
AgentStatus.STATE_* / ROLE_* sabitlerine dayanır (mesaj sözleşmesi
otoriter; agent_states.py ile aynı sayısal değerler).
"""

from swarm_interfaces.msg import AgentStatus


# Lider adayı olabilmek için ajanın bulunması gereken durumlar.
# Yerde ARMED dahil — lider arming'den itibaren belli olmalı.
ELIGIBLE_STATES = frozenset({
    AgentStatus.STATE_ARMED,
    AgentStatus.STATE_TAKEOFF,
    AgentStatus.STATE_IN_SWARM,
    AgentStatus.STATE_EXECUTING_TASK,
})

# Havada sayılan durumlar — heartbeat yalnızca havadayken atılır ve
# heartbeat-timeout lider kaybı yalnızca havadayken değerlendirilir.
AIRBORNE_STATES = frozenset({
    AgentStatus.STATE_TAKEOFF,
    AgentStatus.STATE_IN_SWARM,
    AgentStatus.STATE_EXECUTING_TASK,
})

# Election dışı roller — standby/detached ajan lider adayı olamaz.
INELIGIBLE_ROLES = frozenset({
    AgentStatus.ROLE_STANDBY,
    AgentStatus.ROLE_DETACHED,
})
