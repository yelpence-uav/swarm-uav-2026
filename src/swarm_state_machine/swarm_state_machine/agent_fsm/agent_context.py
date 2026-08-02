# Copyright 2026 Yelpence
"""Tek bir drone'un tum anlik durumunu tutan veri yapisi."""

from dataclasses import dataclass, field
import time

from .agent_states import AgentRole, AgentState, FlightMode


@dataclass
class AgentContext:
    """Tek bir drone'un tum anlik durumunu tutar."""

    agent_id: int

    state: AgentState = AgentState.UNKNOWN
    role: AgentRole = AgentRole.UNKNOWN

    px4_link_ok: bool = False
    gcs_link_ok: bool = False

    # Ilk AgentStatus ulasti mi. "Henuz bilmiyorum" ile "koptu" ayrimini kurar.
    #
    # Neden gerekli: px4_link_ok varsayilan False ve yalnizca _on_telemetry
    # icinde set ediliyor. Bu bayrak olmadan, node acildiktan ~0.1 sn sonra
    # calisan ilk tick, DDS kesfi daha bitmemisken px4_link_ok=False goruyor ve
    # "PX4 link koptu" diye FAILSAFE'e dusuyordu. _from_failsafe disaridan
    # pending_state bekledigi icin de bir daha cikamiyordu — yani node yaklasik
    # yarim olasilikla aciliste kalici kilitleniyordu (sahada olculdu).
    telemetri_alindi: bool = False

    armed: bool = False
    offboard_enabled: bool = False
    offboard_active: bool = False
    flight_mode: FlightMode = FlightMode.UNKNOWN
    pilot_override_active: bool = False

    failsafe_active: bool = False

    battery_percent: float = 0.0
    battery_voltage_v: float = 0.0
    battery_current_a: float = 0.0

    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0
    vel_x: float = 0.0
    vel_y: float = 0.0
    vel_z: float = 0.0

    heading_deg: float = 0.0
    roll_deg: float = 0.0
    pitch_deg: float = 0.0

    gps_fix_type: int = 0
    gps_hdop: float = 9.9
    gps_satellites: int = 0

    lat_deg: float = 0.0
    lon_deg: float = 0.0
    alt_amsl_m: float = 0.0

    home_set: bool = False
    home_lat_deg: float = 0.0
    home_lon_deg: float = 0.0
    home_alt_amsl_m: float = 0.0

    imu_healthy: bool = False
    mag_healthy: bool = False
    baro_healthy: bool = False

    estimator_ok: bool = False
    xy_valid: bool = False
    z_valid: bool = False
    v_xy_valid: bool = False
    estimator_stable_ticks: int = 0

    origin_synced: bool = False
    origin_sequence: int = 0

    rc_link_ok: bool = False
    kill_switch_active: bool = False
    rc_signal_failsafe_active: bool = False

    oscillation_detected: bool = False
    unstable_flight: bool = False

    wants_to_join: bool = False
    ready_to_arm: bool = False

    status_text: str = ''

    sitl_mode: bool = False

    mission_start_sequence_active: bool = False

    # Sürüden ayrılan ajanın renkli pedde disarm bekleyeceği süre (saniye).
    # EVENT_MEMBER_DETACH_STARTED.value ile gelir; WAITING_REJOIN bu süre
    # dolunca kendi kendine tekrar arm olur (rejoin zamanlaması dronda).
    detach_wait_s: float = 0.0

    altitude_stable: bool = False
    attitude_stable: bool = False
    vertical_speed_ok: bool = False

    autonomous_control_paused: bool = False

    hold_active: bool = False

    state_entry_time: float = field(default_factory=time.monotonic)

    target_altitude_m: float = 10.0

    target_altitude_reached: bool = False

    battery_critical_voltage_v: float = 13.6

    geofence_violated: bool = False

    pending_state: AgentState | None = None

    offboard_lost_since: float | None = None

    @property
    def healthy(self) -> bool:
        """Drone ucus icin guvenli mi?."""
        if self.sitl_mode:
            return not self.kill_switch_active and not self.failsafe_active
        is_sim_bat = self.battery_voltage_v <= 0.0
        battery_ok = (
            is_sim_bat
            or self.battery_voltage_v > self.battery_critical_voltage_v
        )
        return (
            self.px4_link_ok
            and not self.kill_switch_active
            and not self.failsafe_active
            and self.xy_valid
            and self.z_valid
            and self.v_xy_valid
            and battery_ok
        )

    def set_state(self, new_state: AgentState) -> None:
        """Durumu degistirir."""
        self.state = new_state
        self.state_entry_time = time.monotonic()

    def time_in_state(self) -> float:
        """Bu durumda gecen sureyi doner."""
        return time.monotonic() - self.state_entry_time
