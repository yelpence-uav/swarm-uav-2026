"""
agent_health_monitor.py

Uçuş sırasında kritik hata/failsafe kontrollerini yapar.
agent_fsm_node.py tarafından her FSM tick'inde çağrılır;
ROS topic yayınlamaz, sonucu node'a döndürür.
"""

import statistics
from collections import deque
from dataclasses import dataclass

from swarm_interfaces.msg import SystemEvent

from .agent_context import AgentContext
from .agent_states import AgentRole, AgentState

# --- Timeout eşikleri (saniye) — roadmap bölüm 6.5 ---
# YAML parametresine taşınmalı; şimdilik sabit.
_TAKEOFF_TIMEOUT_S = 30.0
_LANDING_TIMEOUT_S = 60.0
_RETURN_HOME_TIMEOUT_S = 120.0

# --- Stabilite eşikleri ---
_ALT_STABLE_VAR = 0.05    # m²  — pos_z varyansı
_ATT_STABLE_VAR = 4.0     # deg² — roll/pitch varyansı
_VEL_Z_OK_THR = 0.5       # m/s — dikey hız eşiği
_ALT_REACH_THR = 0.5      # m   — hedef irtifaya tolerans
_OSCILLATION_VAR = 9.0    # deg² — salınım tetik eşiği
_UNSTABLE_ATT_VAR = 25.0  # deg² — kararsız uçuş eşiği
_UNSTABLE_VEL_THR = 2.0   # m/s — kararsız dikey hız

# --- Batarya ---
# Kritik eşik ctx.battery_critical_voltage_v'den gelir.
# Düşük uyarı: kritik + bu offset.
_BATT_LOW_OFFSET_V = 1.0

# --- Maksimum irtifa (m, pozitif yukarı) ---
# Yarışma kuralına göre YAML'dan okunmalı.
_MAX_ALTITUDE_M = 30.0

# Havada olan state'ler — bu state'lerde sağlık/offboard kritik
_AIRBORNE = frozenset({
    AgentState.TAKEOFF,
    AgentState.IN_SWARM,
    AgentState.EXECUTING_TASK,
    AgentState.DETACHED,
    AgentState.PRECISION_LANDING,
    AgentState.REJOINING,
    AgentState.RETURN_HOME,
    AgentState.LANDING,
})


@dataclass
class HealthCheckResult:
    """
    check() fonksiyonunun dönüş tipi.

    Attributes:
        critical_fault: True ise node FAILSAFE geçişi uygular.
        safety_hold: True ise node hold_active'i aktif eder.
        warning: Sadece log/status_text; state değişmez.
        event_type: Yayınlanacak SystemEvent.event_type değeri.
        reason: status_text ve log için açıklama.
    """

    critical_fault: bool = False
    safety_hold: bool = False
    warning: bool = False
    event_type: int = SystemEvent.EVENT_UNKNOWN
    reason: str = ''


# ------------------------------------------------------------------
# Stabilite penceresi — agent başına ayrı tutulur
# ------------------------------------------------------------------

class _StabilityWindow:
    """Son 2 saniyelik veri penceresi (10 Hz → 20 örnek)."""

    MAXLEN = 20

    def __init__(self) -> None:
        self.pos_z: deque[float] = deque(maxlen=self.MAXLEN)
        self.vel_z: deque[float] = deque(maxlen=self.MAXLEN)
        self.roll: deque[float] = deque(maxlen=self.MAXLEN)
        self.pitch: deque[float] = deque(maxlen=self.MAXLEN)

    def update(self, ctx: AgentContext) -> None:
        """Anlık telemetriyi pencereye ekle."""
        self.pos_z.append(ctx.pos_z)
        self.vel_z.append(ctx.vel_z)
        self.roll.append(ctx.roll_deg)
        self.pitch.append(ctx.pitch_deg)

    def is_full(self) -> bool:
        """Pencere dolmadan stabilite hesaplanamaz."""
        return len(self.pos_z) == self.MAXLEN


_windows: dict[int, _StabilityWindow] = {}


def _get_window(ctx: AgentContext) -> _StabilityWindow:
    aid = ctx.agent_id
    if aid not in _windows:
        _windows[aid] = _StabilityWindow()
    return _windows[aid]


# ------------------------------------------------------------------
# Ana kontrol fonksiyonu
# ------------------------------------------------------------------

def check(ctx: AgentContext) -> HealthCheckResult:
    """
    Tüm uçuş sağlık kontrollerini sırayla çalıştırır.

    critical_fault veya safety_hold bulunduğunda erken döner.
    Stabilite ve tutarlılık kontrolleri ctx alanlarını günceller.

    Args:
        ctx: Drone'un anlık durum bilgisi (in-place güncellenir).

    Returns:
        HealthCheckResult: node'un karar vereceği sonuç.
    """
    result = _check_critical_faults(ctx)
    if result.critical_fault:
        return result

    result = _check_rc_safety(ctx)
    if result.critical_fault:
        return result

    result = _check_geofence(ctx)
    if result.safety_hold:
        return result

    result = _check_state_timeout(ctx)
    if result.critical_fault or result.safety_hold:
        return result

    _check_flight_stability(ctx)

    result = _check_altitude_limits(ctx)
    if result.safety_hold:
        return result

    _check_role_state_consistency(ctx)

    return HealthCheckResult()


# ------------------------------------------------------------------
# Alt kontrol fonksiyonları
# ------------------------------------------------------------------

def _check_critical_faults(ctx: AgentContext) -> HealthCheckResult:
    """
    PX4 link, estimator, offboard ve batarya kritik hatalarını kontrol
    eder.

    Args:
        ctx: Drone durum bilgisi.

    Returns:
        HealthCheckResult: critical_fault veya warning.
    """
    if not ctx.px4_link_ok:
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_PX4_LINK_LOST,
            reason='PX4 link koptu',
        )

    if ctx.state in _AIRBORNE and not ctx.estimator_ok:
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_AGENT_FAULT,
            reason='EKF2 estimator hatalı',
        )

    if ctx.state in _AIRBORNE and not ctx.offboard_active:
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_OFFBOARD_LOST,
            reason='OFFBOARD modu kayboldu',
        )

    # Batarya telemetrisi henüz gelmediyse (default 0.0) atla
    if ctx.battery_voltage_v <= 0.0:
        return HealthCheckResult()

    if ctx.battery_voltage_v < ctx.battery_critical_voltage_v:
        reason = (
            f'Kritik batarya: {ctx.battery_voltage_v:.1f}V '
            f'(esik {ctx.battery_critical_voltage_v:.1f}V)'
        )
        ctx.status_text = reason
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_BATTERY_LOW,
            reason=reason,
        )

    batt_low_v = ctx.battery_critical_voltage_v + _BATT_LOW_OFFSET_V
    if ctx.battery_voltage_v < batt_low_v:
        reason = f'Batarya dusuk: {ctx.battery_voltage_v:.1f}V'
        ctx.status_text = reason
        return HealthCheckResult(
            warning=True,
            event_type=SystemEvent.EVENT_BATTERY_LOW,
            reason=reason,
        )

    return HealthCheckResult()


def _check_rc_safety(ctx: AgentContext) -> HealthCheckResult:
    """
    Kill switch, RC link ve RC signal failsafe kontrollerini yapar.

    Args:
        ctx: Drone durum bilgisi.

    Returns:
        HealthCheckResult: critical_fault veya warning.
    """
    if ctx.kill_switch_active:
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_KILL_SWITCH_ACTIVATED,
            reason='Kill switch aktif',
        )

    if not ctx.sitl_mode and not ctx.rc_link_ok:
        reason = 'RC link koptu'
        ctx.status_text = reason
        if ctx.state in _AIRBORNE:
            return HealthCheckResult(
                critical_fault=True,
                event_type=SystemEvent.EVENT_RC_LINK_LOST,
                reason=f'{reason} (havada)',
            )
        return HealthCheckResult(
            warning=True,
            event_type=SystemEvent.EVENT_RC_LINK_LOST,
            reason=reason,
        )

    if ctx.rc_signal_failsafe_active and ctx.state in _AIRBORNE:
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_AGENT_FAULT,
            reason='RC signal failsafe aktif (havada)',
        )

    return HealthCheckResult()


def _check_geofence(ctx: AgentContext) -> HealthCheckResult:
    """
    Jeofen ihlalini kontrol eder.

    ctx.geofence_violated px4_interface veya swarm node tarafından
    set edilir. İhlal tespit edilince drone mevcut konumunda durur;
    swarm manager müdahale edebilir.

    Args:
        ctx: Drone durum bilgisi.

    Returns:
        HealthCheckResult: critical_fault veya boş sonuç.
    """
    if ctx.geofence_violated and ctx.state in _AIRBORNE:
        reason = 'Jeofen ihlali tespit edildi — RTL başlatılıyor'
        ctx.status_text = reason
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_GEOFENCE_VIOLATION,
            reason=reason,
        )
    return HealthCheckResult()


def _check_state_timeout(ctx: AgentContext) -> HealthCheckResult:
    """
    State timeout kontrolü. Roadmap bölüm 6.5.

    Args:
        ctx: Drone durum bilgisi.

    Returns:
        HealthCheckResult: critical_fault veya safety_hold.
    """
    elapsed = ctx.time_in_state()

    if (
        ctx.state == AgentState.TAKEOFF
        and elapsed > _TAKEOFF_TIMEOUT_S
    ):
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_AGENT_FAULT,
            reason=f'TAKEOFF timeout: {elapsed:.0f}s',
        )

    if (
        ctx.state == AgentState.LANDING
        and elapsed > _LANDING_TIMEOUT_S
    ):
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_AGENT_FAULT,
            reason=f'LANDING timeout: {elapsed:.0f}s',
        )

    if (
        ctx.state == AgentState.RETURN_HOME
        and elapsed > _RETURN_HOME_TIMEOUT_S
    ):
        reason = f'RETURN_HOME timeout: {elapsed:.0f}s'
        ctx.status_text = reason
        return HealthCheckResult(
            safety_hold=True,
            event_type=SystemEvent.EVENT_SAFETY_HOLD,
            reason=reason,
        )

    return HealthCheckResult()


def _check_flight_stability(ctx: AgentContext) -> None:
    """
    Son 2 saniyelik pencereden stabilite bayraklarını hesaplar.

    ctx alanlarını günceller:
        target_altitude_reached, altitude_stable, attitude_stable,
        vertical_speed_ok, oscillation_detected, unstable_flight.

    Args:
        ctx: Drone durum bilgisi (in-place güncellenir).
    """
    win = _get_window(ctx)
    win.update(ctx)

    # Hedef irtifaya ulaşıldı mı? (NED: pos_z negatif = yukarı)
    ctx.target_altitude_reached = (
        ctx.pos_z <= -(ctx.target_altitude_m - _ALT_REACH_THR)
    )

    if not win.is_full():
        return

    # Dikey hız kontrolü
    ctx.vertical_speed_ok = all(
        abs(v) < _VEL_Z_OK_THR for v in win.vel_z
    )

    # İrtifa stabilitesi
    pz_var = statistics.variance(win.pos_z)
    ctx.altitude_stable = pz_var < _ALT_STABLE_VAR

    # Attitude stabilitesi
    r_var = statistics.variance(win.roll)
    p_var = statistics.variance(win.pitch)
    att_var = max(r_var, p_var)
    ctx.attitude_stable = att_var < _ATT_STABLE_VAR

    # Osilasyon ve kararsız uçuş tespiti
    ctx.oscillation_detected = att_var > _OSCILLATION_VAR
    max_vz = max(abs(v) for v in win.vel_z)
    ctx.unstable_flight = (
        att_var > _UNSTABLE_ATT_VAR
        or max_vz > _UNSTABLE_VEL_THR
    )


def _check_altitude_limits(ctx: AgentContext) -> HealthCheckResult:
    """
    Maksimum irtifa sınırını kontrol eder.

    Args:
        ctx: Drone durum bilgisi.

    Returns:
        HealthCheckResult: safety_hold veya boş sonuç.
    """
    if ctx.state not in _AIRBORNE:
        return HealthCheckResult()

    altitude_m = -ctx.pos_z  # NED → pozitif yukarı
    if altitude_m > _MAX_ALTITUDE_M:
        reason = (
            f'Irtifa limiti asildi: {altitude_m:.1f}m '
            f'(max {_MAX_ALTITUDE_M:.0f}m)'
        )
        ctx.status_text = reason
        return HealthCheckResult(
            safety_hold=True,
            event_type=SystemEvent.EVENT_ALTITUDE_LIMIT_EXCEEDED,
            reason=reason,
        )

    return HealthCheckResult()


def _check_role_state_consistency(ctx: AgentContext) -> None:
    """
    Role/state çelişkilerini status_text ile bildirir.

    Roadmap bölüm 6.7.

    Args:
        ctx: Drone durum bilgisi (status_text güncellenir).
    """
    if (
        ctx.role == AgentRole.STANDBY
        and ctx.state == AgentState.IN_SWARM
    ):
        ctx.status_text = (
            'Role/state tutarsizlik: STANDBY + IN_SWARM'
        )
    elif (
        ctx.state == AgentState.IN_SWARM
        and ctx.role not in (AgentRole.LEADER, AgentRole.FOLLOWER)
    ):
        ctx.status_text = (
            f'Role/state tutarsizlik: '
            f'IN_SWARM + {ctx.role.name}'
        )
