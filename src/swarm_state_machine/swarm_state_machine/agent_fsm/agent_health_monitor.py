"""Drone uçuş sağlık kontrollerini her FSM tick'inde çalıştırır."""

import statistics
import time
from collections import deque
from dataclasses import dataclass

from swarm_interfaces.msg import SystemEvent

from .agent_context import AgentContext
from .agent_states import AgentRole, AgentState

_OFFBOARD_LOSS_TIMEOUT_S = 5.0

_TAKEOFF_TIMEOUT_S = 30.0
_LANDING_TIMEOUT_S = 60.0
_RETURN_HOME_TIMEOUT_S = 120.0

_ALT_STABLE_VAR = 0.05
_ATT_STABLE_VAR = 4.0
_VEL_Z_OK_THR = 0.5
_ALT_REACH_THR = 0.5
_OSCILLATION_VAR = 9.0
_UNSTABLE_ATT_VAR = 25.0
_UNSTABLE_VEL_THR = 2.0

_BATT_LOW_OFFSET_V = 1.0

_MAX_ALTITUDE_M = 30.0

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
    check() fonksiyonunun döndürdüğü sonuç.

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


class _StabilityWindow:
    """Son 2 saniyelik telemetri penceresi (10 Hz × 2 s = 20 örnek)."""

    MAXLEN = 20

    def __init__(self) -> None:
        self.pos_z: deque[float] = deque(maxlen=self.MAXLEN)
        self.vel_z: deque[float] = deque(maxlen=self.MAXLEN)
        self.roll: deque[float] = deque(maxlen=self.MAXLEN)
        self.pitch: deque[float] = deque(maxlen=self.MAXLEN)

    def update(self, ctx: AgentContext) -> None:
        """Her tick'te anlık sensör verisini kuyruğa ekler.

        Args:
            ctx (AgentContext): Drone'un anlık durum bilgisi.
        """
        self.pos_z.append(ctx.pos_z)
        self.vel_z.append(ctx.vel_z)
        self.roll.append(ctx.roll_deg)
        self.pitch.append(ctx.pitch_deg)

    def is_full(self) -> bool:
        """İstatistik hesabı için yeterli veri olup olmadığını döner.

        Returns:
            bool: Pencere doluysa True.
        """
        return len(self.pos_z) == self.MAXLEN


_windows: dict[int, _StabilityWindow] = {}

# Yerde veya başlangıçta stabilite penceresi sıfırlanmalı
_GROUND_STATES = frozenset({
    AgentState.UNKNOWN,
    AgentState.IDLE,
    AgentState.LANDED,
    AgentState.STANDBY,
})


def clear_window(agent_id: int) -> None:
    """Belirtilen ajan için stabilite penceresini temizler.

    Node yeniden başlatıldığında veya ajan yere indiğinde
    eski verilerin kalmaması için çağrılmalıdır.

    Args:
        agent_id: Temizlenecek ajanın ID'si.
    """
    _windows.pop(agent_id, None)


def _get_window(ctx: AgentContext) -> _StabilityWindow:
    """Bu drone'un stabilite penceresini döner, yoksa yeni oluşturur.

    Drone yerdeyse (IDLE, LANDED, STANDBY) eski pencere temizlenir
    ve yeni boş pencere oluşturulur — eski uçuş verileri
    yeni kalkışı kirletmez.

    Args:
        ctx (AgentContext): Drone'un anlık durum bilgisi.

    Returns:
        _StabilityWindow: Drone'a ait stabilite penceresi.
    """
    aid = ctx.agent_id
    if ctx.state in _GROUND_STATES:
        _windows.pop(aid, None)
    if aid not in _windows:
        _windows[aid] = _StabilityWindow()
    return _windows[aid]


def check(ctx: AgentContext) -> HealthCheckResult:
    """
    Tüm uçuş sağlık kontrollerini sırayla çalıştırır.

    Kritik hatalar önce kontrol edilir; bulununca erken döner.

    Args:
        ctx: Drone'un anlık durum bilgisi (bazı alanlar burada güncellenir).

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


def _check_critical_faults(ctx: AgentContext) -> HealthCheckResult:
    """
    En kritik donanım hatalarını kontrol eder.

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

    # SITL'de yaw hizalaması başlangıçta salınım yapar; real flight'ta her zaman kontrol et
    if ctx.state in _AIRBORNE and not ctx.estimator_ok and not ctx.sitl_mode:
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_AGENT_FAULT,
            reason='EKF2 estimator hatalı',
        )

    if (ctx.state in _AIRBORNE
            and ctx.offboard_lost_since is not None
            and (time.monotonic() - ctx.offboard_lost_since)
            > _OFFBOARD_LOSS_TIMEOUT_S):
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_OFFBOARD_LOST,
            reason='OFFBOARD modu kayboldu',
        )

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
    RC güvenlik kontrollerini yapar (kill switch, bağlantı, sinyal failsafe).

    SITL modunda RC kontrolü atlanır.

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

    if ctx.rc_signal_failsafe_active and ctx.state in _AIRBORNE and not ctx.sitl_mode:
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_AGENT_FAULT,
            reason='RC signal failsafe aktif (havada)',
        )

    return HealthCheckResult()


def _check_geofence(ctx: AgentContext) -> HealthCheckResult:
    """
    Jeofen ihlalini kontrol eder.

    Şartname kural 31: ihlalde RTL zorunlu. critical_fault=True ile
    FAILSAFE → RTL zinciri tetiklenir.

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
    Bir state'te çok uzun kalındı mı kontrol eder.

    Args:
        ctx: Drone durum bilgisi.

    Returns:
        HealthCheckResult: critical_fault veya safety_hold.
    """
    elapsed = ctx.time_in_state()

    if ctx.state == AgentState.TAKEOFF and elapsed > _TAKEOFF_TIMEOUT_S:
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_AGENT_FAULT,
            reason=f'TAKEOFF timeout: {elapsed:.0f}s',
        )

    if ctx.state == AgentState.LANDING and elapsed > _LANDING_TIMEOUT_S:
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_AGENT_FAULT,
            reason=f'LANDING timeout: {elapsed:.0f}s',
        )

    if (ctx.state == AgentState.RETURN_HOME
            and elapsed > _RETURN_HOME_TIMEOUT_S):
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
    Son 2 saniyelik veriden stabilite bayraklarını hesaplar.

    ctx alanlarını in-place günceller; sonuç döndürmez.

    Args:
        ctx: Drone durum bilgisi.
    """
    win = _get_window(ctx)
    win.update(ctx)

    # NED'de yukarı = negatif z; 0.5m toleransla hedef irtifaya ulaşıldı mı?
    ctx.target_altitude_reached = (
        ctx.pos_z <= -(ctx.target_altitude_m - _ALT_REACH_THR)
    )

    if not win.is_full():
        return

    ctx.vertical_speed_ok = all(
        abs(v) < _VEL_Z_OK_THR for v in win.vel_z
    )

    pz_var = statistics.variance(win.pos_z)
    ctx.altitude_stable = pz_var < _ALT_STABLE_VAR

    r_var = statistics.variance(win.roll)
    p_var = statistics.variance(win.pitch)
    att_var = max(r_var, p_var)
    ctx.attitude_stable = att_var < _ATT_STABLE_VAR

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
    Role ve state arasında mantıksal çelişki var mı kontrol eder.

    Çelişki varsa status_text güncellenir; state değişmez.

    Args:
        ctx: Drone durum bilgisi (status_text güncellenir).
    """
    if (
        ctx.role == AgentRole.STANDBY
        and ctx.state == AgentState.IN_SWARM
    ):
        ctx.status_text = 'Role/state tutarsizlik: STANDBY + IN_SWARM'
    elif (
        ctx.state == AgentState.IN_SWARM
        and ctx.role not in (AgentRole.LEADER, AgentRole.FOLLOWER)
    ):
        ctx.status_text = (
            f'Role/state tutarsizlik: IN_SWARM + {ctx.role.name}'
        )
