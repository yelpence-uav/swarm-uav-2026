# Copyright 2026 Yelpence
"""Surunun tum anlik durumunu tutan veri yapisi."""

import math
import time
from dataclasses import dataclass, field

from .swarm_states import FormationType, SwarmState
from ..agent_fsm.agent_states import AgentState


@dataclass
class AgentStatusCache:
    """Tek bir ajandan gelen son AgentStatus bilgisinin ozeti."""

    agent_id: int = 0
    state: int = 0
    role: int = 0

    armed: bool = False
    healthy: bool = False
    px4_link_ok: bool = False
    gcs_link_ok: bool = False
    offboard_active: bool = False
    failsafe_active: bool = False
    origin_synced: bool = False

    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0
    lat_deg: float = 0.0
    lon_deg: float = 0.0
    vel_x: float = 0.0
    vel_y: float = 0.0
    vel_z: float = 0.0
    heading_deg: float = 0.0

    battery_voltage_v: float = 0.0
    battery_percent: float = 0.0

    oscillation_detected: bool = False
    unstable_flight: bool = False

    kill_switch_active: bool = False
    rc_link_ok: bool = False

    last_update: float = 0.0

    def is_stale(self, timeout_s: float = 3.0) -> bool:
        """Son guncelleme cok eski mi?"""
        if self.last_update <= 0.0:
            return True
        return (time.monotonic() - self.last_update) > timeout_s


@dataclass
class SwarmContext:
    """Sürünün tüm anlık durumunu tutar."""

    swarm_state: SwarmState = SwarmState.UNKNOWN
    leader_id: int = 0
    active_agent_count: int = 0
    active_formation: FormationType = FormationType.UNKNOWN

    mission_active: bool = False
    formation_reached: bool = False
    formation_stable: bool = False
    emergency_active: bool = False

    centroid_x: float = 0.0
    centroid_y: float = 0.0
    centroid_z: float = 0.0
    formation_heading_deg: float = 0.0

    formation_max_error_m: float = 0.0
    formation_avg_error_m: float = 0.0
    formation_heading_error_deg: float = 0.0

    agents: dict[int, AgentStatusCache] = field(default_factory=dict)

    expected_agent_count: int = 3

    current_qr_id: int = 0
    current_qr_seq: int = 0

    active_mission: str = ''
    status_text: str = ''

    last_event_type: int = 0
    last_event_severity: int = 0
    last_event_source: int = 0
    last_event_value: float = 0.0
    last_event_pos_x: float = 0.0
    last_event_pos_y: float = 0.0
    last_event_pos_z: float = 0.0
    last_event_has_position: bool = False
    last_event_message: str = ''

    last_heartbeat_time: float = 0.0
    election_round: int = 0
    heartbeat_timeout_s: float = 0.3

    rotation_active: bool = False

    pending_rtl: bool = False
    pending_land: bool = False

    state_entry_time: float = field(default_factory=time.monotonic)

    sitl_mode: bool = False

    min_healthy_ratio: float = 0.5

    def set_state(self, new_state: SwarmState) -> None:
        """Sürünün durumunu degistirir."""
        self.swarm_state = new_state
        self.state_entry_time = time.monotonic()

    def time_in_state(self) -> float:
        """Bu durumda gecen sure."""
        return time.monotonic() - self.state_entry_time

    def compute_centroid(self) -> None:
        """Aktif ajanların agirlik merkezini hesaplar."""
        in_swarm_states = {AgentState.IN_SWARM, AgentState.EXECUTING_TASK}
        active = [
            a for a in self.agents.values()
            if a.state in in_swarm_states and not a.is_stale()
        ]
        if not active:
            return

        n = len(active)
        self.centroid_x = sum(a.pos_x for a in active) / n
        self.centroid_y = sum(a.pos_y for a in active) / n
        self.centroid_z = sum(a.pos_z for a in active) / n

    def compute_formation_quality(
        self,
        target_offsets: dict[int, tuple[float, float, float]] | None = None,
    ) -> None:
        """Formasyon kalite metriklerini hesaplar."""
        in_swarm_states = {AgentState.IN_SWARM, AgentState.EXECUTING_TASK}
        active = [
            a for a in self.agents.values()
            if a.state in in_swarm_states and not a.is_stale()
        ]
        if not active:
            self.formation_max_error_m = 0.0
            self.formation_avg_error_m = 0.0
            return

        errors: list[float] = []
        for a in active:
            if target_offsets and a.agent_id in target_offsets:
                dx, dy, dz = target_offsets[a.agent_id]
                tx = self.centroid_x + dx
                ty = self.centroid_y + dy
                tz = self.centroid_z + dz
            else:
                tx, ty, tz = self.centroid_x, self.centroid_y, self.centroid_z

            err = math.sqrt(
                (a.pos_x - tx) ** 2
                + (a.pos_y - ty) ** 2
                + (a.pos_z - tz) ** 2
            )
            errors.append(err)

        self.formation_max_error_m = max(errors) if errors else 0.0
        self.formation_avg_error_m = (
            sum(errors) / len(errors) if errors else 0.0
        )

    def count_agents_in_state(self, state: int) -> int:
        """Belirtilen state'teki aktif ajan sayisini doner."""
        return sum(
            1 for a in self.agents.values()
            if a.state == state and not a.is_stale()
        )

    def count_healthy_agents(self) -> int:
        """Saglikli ve guncel ajan sayisini doner."""
        return sum(
            1 for a in self.agents.values()
            if a.healthy and not a.is_stale()
        )

    def all_agents_in_states(self, states: set[int]) -> bool:
        """Tüm aktif ajanlar belirtilen state'lerden birinde mi?"""
        active = [
            a for a in self.agents.values()
            if not a.is_stale()
        ]
        if not active:
            return False
        return all(a.state in states for a in active)
