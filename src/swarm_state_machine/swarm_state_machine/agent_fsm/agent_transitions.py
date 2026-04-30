"""
agent_transitions.py
Her ajan durumu için geçiş koşullarını tanımlar.

evaluate_transitions(ctx) her FSM tick'inde çağrılır.
None dönerse mevcut state korunur.
"""

from .agent_context import AgentContext
from .agent_states import AgentState, FlightMode
from .preflight_checker import run_preflight_checks

# Zaman sabitleri (saniye)
_ARMING_TIMEOUT_S = 15.0
_TAKEOFF_TIMEOUT_S = 30.0
_PRECISION_LANDING_TIMEOUT_S = 60.0
_REJOIN_TIMEOUT_S = 60.0
_WAITING_REJOIN_TIMEOUT_S = 120.0

# Bu state'lerde healthy=False failsafe tetiklemez (yerde/güvende)
_FAILSAFE_EXEMPT = frozenset({
    AgentState.UNKNOWN,
    AgentState.IDLE,
    AgentState.ARMING,        # yerde, henüz kalkmadı
    AgentState.ARMED,         # yerde, arm edildi ama uçmadı
    AgentState.WAITING_REJOIN,  # yerde, disarm, rejoin bekliyor
    AgentState.LANDED,
    AgentState.STANDBY,
    AgentState.FAILSAFE,
})

# Yalnızca bu havada state'lerde OFFBOARD kaybı FAILSAFE tetikler
# ARMING ve ARMED henüz OFFBOARD'a geçmemiştir — kontrol dışı
_OFFBOARD_CHECK_STATES = frozenset({
    AgentState.TAKEOFF,
    AgentState.IN_SWARM,
    AgentState.EXECUTING_TASK,
    AgentState.DETACHED,
    AgentState.PRECISION_LANDING,
    AgentState.REJOINING,
    AgentState.RETURN_HOME,
    AgentState.LANDING,
})


def evaluate_transitions(ctx: AgentContext) -> AgentState | None:
    """
    Mevcut duruma göre geçilmesi gereken sonraki state'i döner.

    Args:
        ctx: Drone'un anlık durum bilgisi.

    Returns:
        Hedef AgentState veya geçiş yoksa None.
    """
    # Pilot override veya safety hold aktifken geçiş yapma
    if ctx.autonomous_control_paused or ctx.hold_active:
        return None

    # Global öncelik: havadayken sağlık kaybı → FAILSAFE
    if ctx.state not in _FAILSAFE_EXEMPT and not ctx.healthy:
        return AgentState.FAILSAFE

    # Global öncelik: uçuş state'lerinde OFFBOARD kaybı → FAILSAFE
    if ctx.state in _OFFBOARD_CHECK_STATES and not ctx.offboard_active:
        return AgentState.FAILSAFE

    handlers = {
        AgentState.UNKNOWN:           _from_unknown,
        AgentState.IDLE:              _from_idle,
        AgentState.ARMING:            _from_arming,
        AgentState.ARMED:             _from_armed,
        AgentState.TAKEOFF:           _from_takeoff,
        AgentState.IN_SWARM:          _from_in_swarm,
        AgentState.EXECUTING_TASK:    _from_executing_task,
        AgentState.DETACHED:          _from_detached,
        AgentState.PRECISION_LANDING: _from_precision_landing,
        AgentState.WAITING_REJOIN:    _from_waiting_rejoin,
        AgentState.REJOINING:         _from_rejoining,
        AgentState.RETURN_HOME:       _from_return_home,
        AgentState.LANDING:           _from_landing,
        AgentState.LANDED:            _from_landed,
        AgentState.FAILSAFE:          _from_failsafe,
        AgentState.STANDBY:           _from_standby,
    }
    handler = handlers.get(ctx.state)
    return handler(ctx) if handler else None


def _from_unknown(ctx: AgentContext) -> AgentState | None:
    """UNKNOWN → IDLE: Başlangıç durumu, her zaman geçer."""
    return AgentState.IDLE


def _from_idle(ctx: AgentContext) -> AgentState | None:
    """IDLE → ARMING: Preflight geçerse ve arming talebi varsa."""
    if ctx.pending_state == AgentState.ARMING:
        passed, _ = run_preflight_checks(ctx)
        if passed:
            return AgentState.ARMING
    return None


def _from_arming(ctx: AgentContext) -> AgentState | None:
    """
    ARMING → ARMED: PX4 arm onayı.
    ARMING → IDLE: Timeout veya sağlık kaybı.
    """
    if ctx.armed:
        return AgentState.ARMED
    if not ctx.healthy:
        return AgentState.IDLE
    if ctx.time_in_state() > _ARMING_TIMEOUT_S:
        return AgentState.IDLE
    return None


def _from_armed(ctx: AgentContext) -> AgentState | None:
    """
    ARMED → TAKEOFF: Mission başlatma sinyali + offboard aktif.
    ARMED → IDLE: Disarm veya sağlık kaybı.
    """
    if not ctx.armed or not ctx.healthy:
        return AgentState.IDLE
    if ctx.mission_start_sequence_active and ctx.offboard_active:
        return AgentState.TAKEOFF
    return None


def _from_takeoff(ctx: AgentContext) -> AgentState | None:
    """
    TAKEOFF → IN_SWARM: Hedef irtifaya ulaşıldı, stabilite sağlandı.
    TAKEOFF → FAILSAFE: Timeout.
    """
    if (ctx.altitude_stable
            and ctx.attitude_stable
            and ctx.vertical_speed_ok
            and ctx.origin_synced):
        return AgentState.IN_SWARM
    if ctx.time_in_state() > _TAKEOFF_TIMEOUT_S:
        return AgentState.FAILSAFE
    return None


def _from_in_swarm(ctx: AgentContext) -> AgentState | None:
    """IN_SWARM: Görev, detach, RTL veya iniş taleplerine göre geçiş."""
    if ctx.pending_state == AgentState.EXECUTING_TASK:
        return AgentState.EXECUTING_TASK
    if ctx.pending_state == AgentState.DETACHED:
        return AgentState.DETACHED
    if ctx.pending_state == AgentState.RETURN_HOME:
        return AgentState.RETURN_HOME
    if ctx.pending_state == AgentState.LANDING:
        return AgentState.LANDING
    return None


def _from_executing_task(ctx: AgentContext) -> AgentState | None:
    """
    EXECUTING_TASK → IN_SWARM: Görev tamamlandı.
    EXECUTING_TASK → RETURN_HOME: RTL talebi görev sırasında da geçerli.
    """
    if ctx.pending_state == AgentState.RETURN_HOME:
        return AgentState.RETURN_HOME
    if ctx.pending_state == AgentState.IN_SWARM:
        return AgentState.IN_SWARM
    return None


def _from_detached(ctx: AgentContext) -> AgentState | None:
    """DETACHED → PRECISION_LANDING: Otomatik iniş akışı başlar."""
    return AgentState.PRECISION_LANDING


def _from_precision_landing(ctx: AgentContext) -> AgentState | None:
    """
    PRECISION_LANDING → WAITING_REJOIN: Disarm ile iniş tamamlandı.
    PRECISION_LANDING → FAILSAFE: Timeout.
    """
    if not ctx.armed:
        return AgentState.WAITING_REJOIN
    if ctx.time_in_state() > _PRECISION_LANDING_TIMEOUT_S:
        return AgentState.FAILSAFE
    return None


def _from_waiting_rejoin(ctx: AgentContext) -> AgentState | None:
    """
    WAITING_REJOIN → REJOINING: Yeniden katılma talebi.
    WAITING_REJOIN → FAILSAFE: Timeout.
    """
    if ctx.pending_state == AgentState.REJOINING:
        return AgentState.REJOINING
    if ctx.time_in_state() > _WAITING_REJOIN_TIMEOUT_S:
        return AgentState.FAILSAFE
    return None


def _from_rejoining(ctx: AgentContext) -> AgentState | None:
    """
    REJOINING → IN_SWARM: Sürüye katıldı.
    REJOINING → FAILSAFE: Timeout.
    """
    if ctx.pending_state == AgentState.IN_SWARM:
        return AgentState.IN_SWARM
    if ctx.time_in_state() > _REJOIN_TIMEOUT_S:
        return AgentState.FAILSAFE
    return None


def _from_return_home(ctx: AgentContext) -> AgentState | None:
    """RETURN_HOME → LANDING: PX4 RTL tamamlandı, iniş başlıyor."""
    if ctx.flight_mode == FlightMode.AUTO_LAND:
        return AgentState.LANDING
    if ctx.pending_state == AgentState.LANDING:
        return AgentState.LANDING
    return None


def _from_landing(ctx: AgentContext) -> AgentState | None:
    """LANDING → LANDED: Disarm ile iniş tamamlandı."""
    if not ctx.armed:
        return AgentState.LANDED
    return None


def _from_landed(ctx: AgentContext) -> AgentState | None:
    """
    LANDED → IDLE: Sistem sıfırlanmaya hazır.
    LANDED → STANDBY: Drone standby moduna alınıyor.
    """
    if ctx.pending_state == AgentState.STANDBY:
        return AgentState.STANDBY
    if ctx.pending_state == AgentState.IDLE:
        return AgentState.IDLE
    return None


def _from_failsafe(ctx: AgentContext) -> AgentState | None:
    """
    FAILSAFE → RETURN_HOME: Sağlık geri geldi, RTL başlat.
    FAILSAFE → LANDING: RTL mümkün değilse acil iniş.
    """
    if ctx.healthy and ctx.pending_state == AgentState.RETURN_HOME:
        return AgentState.RETURN_HOME
    if ctx.pending_state == AgentState.LANDING:
        return AgentState.LANDING
    return None


def _from_standby(ctx: AgentContext) -> AgentState | None:
    """STANDBY → ARMING: Katılma talebi onaylandı ve preflight geçti."""
    if ctx.wants_to_join and ctx.ready_to_arm:
        passed, _ = run_preflight_checks(ctx)
        if passed:
            return AgentState.ARMING
    return None
