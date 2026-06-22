"""mode_context.py — mode_manager çalışma zamanı durum kabı.

mode_manager_node callback'leri bu nesneye yazar.
mode_transitions fonksiyonları yalnızca okur.
"""

import math
import time
from dataclasses import dataclass, field
from typing import Optional

from .mode_states import ControlMode, ModeState


# AgentStatus.msg STATE_* sabitleriyle eşleşmeli.
_AGENT_STATE_IN_SWARM = 5
_AGENT_STATE_LANDED = 13

# MissionState sabiti.
_MISSION_STATE_SEMI_AUTONOMOUS = 8


@dataclass
class ModeContext:
    """mode_manager FSM çalışma zamanı durumu.

    mode_manager_node'daki callback'ler bu nesneye yazar.
    mode_transitions fonksiyonları yalnızca okur.

    Args:
        agent_ids: Sürüdeki aktif drone ID'leri, örn. [1, 2, 3].
        sitl_mode: True ise GPS/origin kontrolleri atlanır.
    """

    agent_ids: list

    sitl_mode: bool = False

    # FSM durumu
    state: ModeState = ModeState.IDLE
    state_entry_time: float = field(default_factory=time.monotonic)

    # mission_fsm'den gelen durum
    mission_state: int = 0

    # ─── Son gelen SwarmControlCommand bilgileri ───
    command_valid: bool = False
    deadman_pressed: bool = False
    deadman_timeout_s: float = 0.5
    control_mode: ControlMode = ControlMode.UNKNOWN

    # Normalize joystick girdileri [-1.0, +1.0]
    pitch_cmd: float = 0.0
    roll_cmd: float = 0.0
    yaw_cmd: float = 0.0
    throttle_cmd: float = 0.0

    # Ayrık komutlar
    takeoff_requested: bool = False
    land_requested: bool = False
    rtl_requested: bool = False
    emergency_stop_requested: bool = False

    # Formasyon değişikliği talebi (arayüzden gelecek)
    formation_change_requested: bool = False
    requested_formation: int = 0
    requested_spacing_m: float = 5.0

    # Hız limitleri
    max_speed_mps: float = 2.0
    max_yaw_rate_deg_s: float = 30.0
    max_tilt_deg: float = 15.0

    last_valid_command_time: float = 0.0
    command_sequence_num: int = 0

    # ─── Sürü durumu (SwarmState'ten alınır) ───
    centroid_x: float = 0.0
    centroid_y: float = 0.0
    centroid_z: float = 0.0
    formation_heading_deg: float = 0.0
    active_formation: int = 0  # FormationType enum
    formation_reached: bool = False
    formation_stable: bool = False

    # ─── Manevra durumu ───
    # Son uygulanan eğim açıları — sürekli kontrol için tutulur
    maneuver_pitch_deg: float = 0.0
    maneuver_roll_deg: float = 0.0

    # ─── Ajan durumları ───
    agent_statuses: dict = field(default_factory=dict)

    # ─── GCS komut takibi ───
    pending_abort: bool = False

    def set_state(self, new_state: ModeState) -> None:
        """Durumu değiştirir ve zamanlayıcıyı sıfırlar.

        Args:
            new_state: Geçilecek hedef state.
        """
        self.state = new_state
        self.state_entry_time = time.monotonic()

        # Geçici komut bayraklarını temizle
        self.takeoff_requested = False
        self.land_requested = False
        self.rtl_requested = False
        self.emergency_stop_requested = False
        self.formation_change_requested = False

    def time_in_state(self) -> float:
        """Bu state'te geçen süre (saniye)."""
        return time.monotonic() - self.state_entry_time

    def deadman_timed_out(self) -> bool:
        """Deadman timeout aşıldı mı?

        Son geçerli komuttan bu yana geçen süre deadman_timeout_s'yi
        aşmışsa True döner.

        Returns:
            True ise deadman timeout aşıldı, HOLD'a geçilmeli.
        """
        if self.last_valid_command_time <= 0.0:
            return True
        elapsed = time.monotonic() - self.last_valid_command_time
        return elapsed > self.deadman_timeout_s

    @property
    def command_active(self) -> bool:
        """Geçerli bir joystick komutu aktif mi?

        command_valid VE deadman_pressed VE timeout aşılmamış.
        """
        return (
            self.command_valid
            and self.deadman_pressed
            and not self.deadman_timed_out()
        )

    def has_nonzero_input(self) -> bool:
        """Joystick'te sıfır olmayan girdi var mı?"""
        threshold = 0.05
        return (
            abs(self.pitch_cmd) > threshold
            or abs(self.roll_cmd) > threshold
            or abs(self.yaw_cmd) > threshold
            or abs(self.throttle_cmd) > threshold
        )

    # ─── Ajan sorgulama yardımcıları ───

    def all_agents_seen(self) -> bool:
        """Her ajan için en az bir durum mesajı alındıysa True."""
        return all(aid in self.agent_statuses for aid in self.agent_ids)

    def all_agents_in_swarm(self) -> bool:
        """Tüm ajanlar STATE_IN_SWARM ise True."""
        if not self.agent_statuses:
            return False
        return all(
            s.state == _AGENT_STATE_IN_SWARM
            for s in self.agent_statuses.values()
        )

    def all_agents_landed(self) -> bool:
        """Tüm ajanlar STATE_LANDED ise True."""
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
        """mission_fsm SEMI_AUTONOMOUS state'inde mi?"""
        return self.mission_state == _MISSION_STATE_SEMI_AUTONOMOUS

    def compute_heading_rotation(
        self, yaw_cmd: float, dt: float
    ) -> float:
        """Yaw komutuna göre yeni heading hesaplar.

        Args:
            yaw_cmd: Normalize yaw girdisi [-1.0, +1.0].
            dt: Zaman adımı (saniye).

        Returns:
            Güncellenmiş heading (derece, 0-360).
        """
        delta = yaw_cmd * self.max_yaw_rate_deg_s * dt
        new_heading = (self.formation_heading_deg + delta) % 360.0
        return new_heading

    def compute_centroid_delta(
        self, pitch_cmd: float, roll_cmd: float,
        throttle_cmd: float, dt: float,
    ) -> tuple[float, float, float]:
        """Joystick girdisine göre centroid delta hesaplar (NED).

        Body frame → NED dönüşümü heading'e göre yapılır.
        pitch_cmd > 0 → ileri (heading yönünde).
        roll_cmd > 0 → sağ.
        throttle_cmd > 0 → yukarı (NED'de z azalır).

        Args:
            pitch_cmd: Normalize ileri/geri girdisi.
            roll_cmd: Normalize sağ/sol girdisi.
            throttle_cmd: Normalize irtifa girdisi.
            dt: Zaman adımı (saniye).

        Returns:
            (delta_x, delta_y, delta_z) NED frame'de.
        """
        # Body frame velocities
        v_forward = pitch_cmd * self.max_speed_mps
        v_right = roll_cmd * self.max_speed_mps
        v_up = throttle_cmd * self.max_speed_mps

        # Body → NED dönüşümü (heading açısına göre)
        heading_rad = math.radians(self.formation_heading_deg)
        cos_h = math.cos(heading_rad)
        sin_h = math.sin(heading_rad)

        # NED: x=North, y=East
        dx = (v_forward * cos_h - v_right * sin_h) * dt
        dy = (v_forward * sin_h + v_right * cos_h) * dt
        dz = -v_up * dt  # NED: z pozitif aşağı, yukarı = negatif

        return dx, dy, dz
