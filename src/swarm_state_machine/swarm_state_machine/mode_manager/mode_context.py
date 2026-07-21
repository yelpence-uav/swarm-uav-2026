# Copyright 2026 Yelpence
"""mode_manager calisma zamani durum kabi."""

from dataclasses import dataclass, field
import math
import time

from .mode_states import ControlMode, ModeState

_AGENT_STATE_IN_SWARM = 5
_AGENT_STATE_LANDED = 13

_MISSION_STATE_SEMI_AUTONOMOUS = 8


@dataclass
class ModeContext:
    """mode_manager FSM calisma zamani durumu."""

    agent_ids: list

    sitl_mode: bool = False

    state: ModeState = ModeState.IDLE
    state_entry_time: float = field(default_factory=time.monotonic)

    mission_state: int = 0

    command_valid: bool = False
    deadman_pressed: bool = False
    deadman_timeout_s: float = 0.5
    control_mode: ControlMode = ControlMode.UNKNOWN

    pitch_cmd: float = 0.0
    roll_cmd: float = 0.0
    yaw_cmd: float = 0.0
    throttle_cmd: float = 0.0

    takeoff_requested: bool = False
    land_requested: bool = False
    rtl_requested: bool = False
    emergency_stop_requested: bool = False

    formation_change_requested: bool = False
    requested_formation: int = 0
    requested_spacing_m: float = 5.0

    max_speed_mps: float = 2.0
    max_yaw_rate_deg_s: float = 30.0
    max_tilt_deg: float = 15.0

    last_valid_command_time: float = 0.0
    command_sequence_num: int = 0

    centroid_x: float = 0.0
    centroid_y: float = 0.0
    centroid_z: float = 0.0
    formation_heading_deg: float = 0.0
    active_formation: int = 0
    formation_reached: bool = False
    formation_stable: bool = False

    maneuver_pitch_deg: float = 0.0
    maneuver_roll_deg: float = 0.0

    agent_statuses: dict = field(default_factory=dict)

    pending_abort: bool = False

    def set_state(self, new_state: ModeState) -> None:
        """Durumu degistirir ve zamanlayiciyi sifirlar."""
        self.state = new_state
        self.state_entry_time = time.monotonic()

        self.takeoff_requested = False
        self.land_requested = False
        self.rtl_requested = False
        self.emergency_stop_requested = False
        self.formation_change_requested = False

    def time_in_state(self) -> float:
        """Bu state'te gecen sure."""
        return time.monotonic() - self.state_entry_time

    def deadman_timed_out(self) -> bool:
        """Deadman timeout asildi mi?."""
        if self.last_valid_command_time <= 0.0:
            return True
        elapsed = time.monotonic() - self.last_valid_command_time
        return elapsed > self.deadman_timeout_s

    @property
    def command_active(self) -> bool:
        """Gecerli bir joystick komutu aktif mi?."""
        return (
            self.command_valid
            and self.deadman_pressed
            and not self.deadman_timed_out()
        )

    def has_nonzero_input(self) -> bool:
        """Joystick'te sifir olmayan girdi var mi?."""
        threshold = 0.05
        return (
            abs(self.pitch_cmd) > threshold
            or abs(self.roll_cmd) > threshold
            or abs(self.yaw_cmd) > threshold
            or abs(self.throttle_cmd) > threshold
        )

    def all_agents_seen(self) -> bool:
        """Her ajan icin en az bir durum mesaji alindiysa True."""
        return all(aid in self.agent_statuses for aid in self.agent_ids)

    def all_agents_in_swarm(self) -> bool:
        """Tum ajanlar STATE_IN_SWARM ise True."""
        if not self.agent_statuses:
            return False
        return all(
            s.state == _AGENT_STATE_IN_SWARM
            for s in self.agent_statuses.values()
        )

    def all_agents_landed(self) -> bool:
        """Tum ajanlar STATE_LANDED ise True."""
        if not self.agent_statuses:
            return False
        return all(
            s.state == _AGENT_STATE_LANDED
            for s in self.agent_statuses.values()
        )

    def all_agents_healthy(self) -> bool:
        """Her ajan healthy=True bildiriyorsa True."""
        if not self.agent_statuses:
            return False
        return all(s.healthy for s in self.agent_statuses.values())

    def is_mission_semi_autonomous(self) -> bool:
        """mission_fsm SEMI_AUTONOMOUS state'inde mi?."""
        return self.mission_state == _MISSION_STATE_SEMI_AUTONOMOUS

    def compute_heading_rotation(
        self, yaw_cmd: float, dt: float
    ) -> float:
        """Yaw komutuna gore yeni heading hesaplar."""
        delta = yaw_cmd * self.max_yaw_rate_deg_s * dt
        new_heading = (self.formation_heading_deg + delta) % 360.0
        return new_heading

    def compute_centroid_delta(
        self, pitch_cmd: float, roll_cmd: float,
        throttle_cmd: float, dt: float,
    ) -> tuple[float, float, float]:
        """Joystick girdisine gore centroid delta hesaplar (NED)."""
        v_forward = pitch_cmd * self.max_speed_mps
        v_right = roll_cmd * self.max_speed_mps
        v_up = throttle_cmd * self.max_speed_mps

        heading_rad = math.radians(self.formation_heading_deg)
        cos_h = math.cos(heading_rad)
        sin_h = math.sin(heading_rad)

        dx = (v_forward * cos_h - v_right * sin_h) * dt
        dy = (v_forward * sin_h + v_right * cos_h) * dt
        dz = -v_up * dt

        return dx, dy, dz
