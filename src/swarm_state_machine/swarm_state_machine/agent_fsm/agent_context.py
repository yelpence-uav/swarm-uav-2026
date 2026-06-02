"""Tek bir drone'un tüm anlık durumunu tutan veri yapısı."""

import time
from dataclasses import dataclass, field

from .agent_states import AgentState, AgentRole, FlightMode


@dataclass
class AgentContext:
    """
    Tek bir drone'un tüm anlık durumunu tutar.

    Her drone için ayrı bir AgentContext nesnesi oluşturulur.
    agent_health_monitor bu sınıfı günceller.
    agent_fsm_node bu sınıfı okur ve AgentStatus.msg olarak yayınlar.
    """

    agent_id: int

    state: AgentState = AgentState.UNKNOWN
    role: AgentRole = AgentRole.UNKNOWN

    px4_link_ok: bool = False
    gcs_link_ok: bool = False

    armed: bool = False
    offboard_enabled: bool = False
    offboard_active: bool = False
    flight_mode: FlightMode = FlightMode.UNKNOWN
    pilot_override_active: bool = False

    failsafe_active: bool = False

    battery_percent: float = 0.0
    battery_voltage_v: float = 0.0
    battery_current_a: float = 0.0

    # NED koordinat sistemi: Z ekseni aşağıya pozitif.
    # 20m yükseklikte uçan drone'un pos_z = -20.0
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
    estimator_stable_ticks: int = 0  # kaç ardışık tick'te estimator sağlıklı

    origin_synced: bool = False
    origin_sequence: int = 0

    rc_link_ok: bool = False
    kill_switch_active: bool = False
    rc_signal_failsafe_active: bool = False

    oscillation_detected: bool = False
    unstable_flight: bool = False

    wants_to_join: bool = False
    ready_to_arm: bool = False

    status_text: str = ""

    sitl_mode: bool = False

    mission_start_sequence_active: bool = False

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

    # Offboard'un kesintisiz kapalı olduğu an (None = offboard aktif)
    offboard_lost_since: float | None = None

    @property
    def healthy(self) -> bool:
        """
        Drone şu an uçuşa güvenli mi?

        Sadece uçuşu fiilen engelleyen 7 kritik koşul kontrol edilir.
        rc_link, imu/mag/baro, estimator_ok çıkarıldı — bunların
        gerçek etkisi zaten xy_valid/z_valid/v_xy_valid'e yansır;
        EKF bozulursa bu üçü zaten false olur. Anlık titremelerde
        drone'un formasyondan gereksiz çıkmasını önler.
        """
        battery_ok = (
            self.battery_voltage_v <= 0.0  # 0V = sim battery disabled, skip
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
        """
        Drone'un durumunu değiştirir ve timeout sayacını sıfırlar.

        Args:
            new_state: Geçilecek hedef state.
        """
        self.state = new_state
        self.state_entry_time = time.monotonic()

    def time_in_state(self) -> float:
        """
        Bu state'te kaç saniyedir?

        Returns:
            Geçen süre (saniye).
        """
        return time.monotonic() - self.state_entry_time
