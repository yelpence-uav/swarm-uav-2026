"""
agent_context.py
Agent'ın anlık telemetri, sağlık, rol/state, RC güvenlik,
stabilite ve timer bilgisini tutan veri yapısı.

Kaynak: swarm_interfaces/msg/AgentStatus.msg
"""

import time
from dataclasses import dataclass, field
from .agent_states import AgentState, AgentRole, FlightMode


@dataclass
class AgentContext:
    """
    Tek bir drone'un tüm anlık durumunu tutar.

    agent_health_monitor bu sınıfı günceller.
    agent_fsm_node bu sınıfı okur ve AgentStatus.msg olarak yayınlar.
    """

    # --- KİMLİK ---
    agent_id: int

    # --- FSM DURUMU (AgentStatus.msg: state, role) ---
    state: AgentState = AgentState.UNKNOWN
    role: AgentRole = AgentRole.UNKNOWN

    # --- BAĞLANTI (AgentStatus.msg) ---
    px4_link_ok: bool = False
    gcs_link_ok: bool = False

    # --- ARM / OFFBOARD (AgentStatus.msg) ---
    armed: bool = False
    offboard_enabled: bool = False
    offboard_active: bool = False
    flight_mode: FlightMode = FlightMode.UNKNOWN
    pilot_override_active: bool = False

    # --- FAILSAFE / SAĞLIK (AgentStatus.msg) ---
    failsafe_active: bool = False

    # --- BATARYA (AgentStatus.msg) ---
    # Failsafe kararlarında battery_voltage_v kullanılır, battery_percent değil
    battery_percent: float = 0.0
    battery_voltage_v: float = 0.0
    battery_current_a: float = 0.0

    # --- POZİSYON - Local NED (AgentStatus.msg) ---
    # z aşağıya pozitif: 20m yükseklik = pos_z = -20.0
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0
    vel_x: float = 0.0
    vel_y: float = 0.0
    vel_z: float = 0.0

    # --- ATTITUDE (AgentStatus.msg) ---
    heading_deg: float = 0.0
    roll_deg: float = 0.0
    pitch_deg: float = 0.0

    # --- GPS (AgentStatus.msg) ---
    # fix_type: 0=no fix, 2=2D, 3=3D, 4=DGPS, 5=RTK float, 6=RTK fixed
    gps_fix_type: int = 0
    gps_hdop: float = 9.9
    gps_satellites: int = 0

    # --- GLOBAL POZİSYON (AgentStatus.msg) ---
    lat_deg: float = 0.0
    lon_deg: float = 0.0
    alt_amsl_m: float = 0.0

    # --- HOME KONUMU (AgentStatus.msg) ---
    home_set: bool = False
    home_lat_deg: float = 0.0
    home_lon_deg: float = 0.0
    home_alt_amsl_m: float = 0.0

    # --- SENSÖR SAĞLIĞI (AgentStatus.msg) ---
    imu_healthy: bool = False
    mag_healthy: bool = False
    baro_healthy: bool = False

    # --- EKF2 / ESTIMATOR (AgentStatus.msg) ---
    estimator_ok: bool = False
    xy_valid: bool = False
    z_valid: bool = False
    v_xy_valid: bool = False

    # --- ORIGIN SENKRONU (AgentStatus.msg) ---
    origin_synced: bool = False
    origin_sequence: int = 0

    # --- RC / GÜVENLİK (AgentStatus.msg) ---
    rc_link_ok: bool = False
    kill_switch_active: bool = False
    rc_signal_failsafe_active: bool = False

    # --- UÇUŞ STABİLİTESİ (AgentStatus.msg) ---
    oscillation_detected: bool = False
    unstable_flight: bool = False

    # --- STANDBY / JOIN (AgentStatus.msg) ---
    wants_to_join: bool = False
    ready_to_arm: bool = False

    # --- DURUM METNİ (AgentStatus.msg) ---
    status_text: str = ""

    # -------------------------------------------------------
    # Aşağıdaki alanlar AgentStatus.msg'de YOK.
    # Context içinde hesaplanır, geçiş koşullarında kullanılır.
    # -------------------------------------------------------

    # SITL modunda rc_link_ok kontrolü atlanır (gerçek donanımda False bırak)
    sitl_mode: bool = False

    # ARMED -> TAKEOFF için mission_fsm bu flag'i true yapar
    mission_start_sequence_active: bool = False

    # TAKEOFF -> IN_SWARM stabilite koşulları
    # agent_health_monitor son 2 saniyelik pencereden hesaplar
    altitude_stable: bool = False
    attitude_stable: bool = False
    vertical_speed_ok: bool = False

    # Pilot override gelince otomasyon durur
    autonomous_control_paused: bool = False

    # EVENT_SAFETY_HOLD aktifken true
    hold_active: bool = False

    # State'e girilen zaman — timeout kontrolü için
    state_entry_time: float = field(default_factory=time.monotonic)

    # Takeoff hedef irtifası (m, pozitif yukarı)
    target_altitude_m: float = 10.0

    # agent_health_monitor hedef irtifaya ulaşıldığında true yapar
    # TAKEOFF -> IN_SWARM koşulunda kullanılır (bkz. agent_transitions.py)
    target_altitude_reached: bool = False

    # Kritik batarya voltaj eşiği — healthy ve failsafe kararlarında kullanılır
    # YAML parametresinden okunmalı; varsayılan 4S LiPo kritik eşiği
    battery_critical_voltage_v: float = 13.6

    # Jeofen ihlali — px4_interface veya swarm node tarafından set edilir
    geofence_violated: bool = False

    # Geçiş talebi — node her tick'te kontrol eder, sonra None yapar
    pending_state: AgentState | None = None

    @property
    def healthy(self) -> bool:
        """
        Donanım, bağlantı, estimator ve batarya güvenliğini hesaplar.

        pilot_override_active bu hesaba dahil edilmez.
        oscillation_detected ve unstable_flight tek başına
        healthy=False yapmaz.
        """
        return (
            self.px4_link_ok
            and (self.rc_link_ok or self.sitl_mode)
            and not self.kill_switch_active
            and not self.rc_signal_failsafe_active
            and self.imu_healthy
            and self.mag_healthy
            and self.baro_healthy
            and self.estimator_ok
            and self.xy_valid
            and self.z_valid
            and self.v_xy_valid
            and self.battery_voltage_v > self.battery_critical_voltage_v
            and not self.failsafe_active
        )

    def set_state(self, new_state: AgentState) -> None:
        """State değiştir ve timeout sayacını sıfırla."""
        self.state = new_state
        self.state_entry_time = time.monotonic()

    def time_in_state(self) -> float:
        """Bu state'te kaç saniyedir? Timeout kontrolü için kullanılır."""
        return time.monotonic() - self.state_entry_time
