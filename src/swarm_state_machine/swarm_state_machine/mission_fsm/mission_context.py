# Copyright 2026 Yelpence
"""mission_fsm_node ve mission_transitions icin ortak bellek."""

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .mission_states import MissionState, MissionType, QrTaskStep

_AGENT_STATE_IN_SWARM = 5
_AGENT_STATE_LANDING = 12
_AGENT_STATE_LANDED = 13


@dataclass
class MissionContext:
    """mission_fsm_node ve mission_transitions için ortak bellek."""

    agent_ids: list

    team_id: str = ''
    sitl_mode: bool = False

    state: MissionState = MissionState.UNKNOWN
    mission_type: MissionType = MissionType.UNKNOWN
    state_entry_time: float = field(default_factory=time.monotonic)

    agent_statuses: dict = field(default_factory=dict)

    last_accepted_qr_seq: int = 0
    current_qr: Optional[Any] = None
    qr_task_step: QrTaskStep = QrTaskStep.NONE

    qr_coord_table: dict = field(default_factory=dict)
    next_qr_target: Optional[tuple] = None
    route_unknown: bool = False

    pause_return_state: MissionState = MissionState.NAVIGATE_TO_QR
    wait_deadline: Optional[float] = None

    action_done: bool = False
    action_success: bool = False

    event_formation_reached: bool = False
    event_rotation_completed: bool = False

    pending_command: int = 0
    abort_reason: str = ''

    def set_state(self, new_state: MissionState) -> None:
        """Durum gecisini uygular."""
        self.state = new_state
        self.state_entry_time = time.monotonic()
        self.action_done = False
        self.action_success = False
        self.event_formation_reached = False
        self.event_rotation_completed = False
        self.qr_task_step = QrTaskStep.NONE

    def time_in_state(self) -> float:
        """Mevcut duruma giristen bu yana gecen saniyeyi doner."""
        return time.monotonic() - self.state_entry_time

    def lookup_qr_position(self, qr_id: int) -> Optional[tuple]:
        """QR numarasindan koordinati cozer."""
        return self.qr_coord_table.get(int(qr_id))

    @property
    def all_agents_seen(self) -> bool:
        """Her ajan icin en az bir durum mesaji alindiysa True."""
        return all(aid in self.agent_statuses for aid in self.agent_ids)

    def all_agents_in_state(self, state_value: int) -> bool:
        """Her ajan verilen AgentStatus state degerini bildiriyorsa True."""
        if not self.agent_statuses:
            return False
        return all(
            s.state == state_value for s in self.agent_statuses.values()
        )

    def all_agents_in_swarm(self) -> bool:
        """Tum ajanlar STATE_IN_SWARM ise True."""
        return self.all_agents_in_state(_AGENT_STATE_IN_SWARM)

    def all_agents_landing(self) -> bool:
        """Tum ajanlar STATE_LANDING ise True."""
        return self.all_agents_in_state(_AGENT_STATE_LANDING)

    def all_agents_landed(self) -> bool:
        """Tum ajanlar STATE_LANDED ise True."""
        return self.all_agents_in_state(_AGENT_STATE_LANDED)

    def all_agents_healthy(self) -> bool:
        """Her ajan healthy=True bildiriyorsa True."""
        if not self.agent_statuses:
            return False
        return all(s.healthy for s in self.agent_statuses.values())

    def all_agents_origin_synced(self) -> bool:
        """Tum ajanlar SwarmOrigin'i uyguladiysa True."""
        if not self.agent_statuses:
            return False
        return all(
            s.origin_synced for s in self.agent_statuses.values()
        )

    def all_agents_home_set(self) -> bool:
        """Tum ajanlarin home_set'i True ise True."""
        if not self.agent_statuses:
            return False
        return all(s.home_set for s in self.agent_statuses.values())

    def all_agents_gps_ok(self) -> bool:
        """Tum ajanlarda 3D GPS fix ve HDOP < 1.5 ise True."""
        if not self.agent_statuses:
            return False
        return all(
            s.gps_fix_type >= 3 and s.gps_hdop < 1.5
            for s in self.agent_statuses.values()
        )
