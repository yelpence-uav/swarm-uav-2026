# Copyright 2026 Yelpence
"""Ajan FSM durum gecis kurallari."""

from .agent_context import AgentContext
from .agent_states import AgentState, FlightMode
from .preflight_checker import run_preflight_checks

_ARMING_TIMEOUT_S = 15.0
_ARMED_STABILIZE_S = 2.0
_WAITING_REJOIN_TIMEOUT_S = 120.0
# LANDING'de disarm beklenir; offboard kaybı burada failsafe tetiklemediği
# için takılan iniş ayrı bir zaman aşımıyla yakalanır.
_LANDING_TIMEOUT_S = 60.0

_FAILSAFE_EXEMPT = frozenset({
    AgentState.UNKNOWN,
    AgentState.IDLE,
    AgentState.ARMING,
    AgentState.ARMED,
    AgentState.WAITING_REJOIN,
    AgentState.LANDED,
    AgentState.STANDBY,
    AgentState.FAILSAFE,
})

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
    """Mevcut duruma gore gecilmesi gereken sonraki state'i doner."""
    if ctx.autonomous_control_paused or ctx.hold_active:
        if ctx.pending_state in (AgentState.LANDING, AgentState.FAILSAFE):
            return ctx.pending_state
        return None

    if ctx.state not in _FAILSAFE_EXEMPT and not ctx.healthy:
        return AgentState.FAILSAFE

    if (ctx.state in _OFFBOARD_CHECK_STATES
            and not ctx.offboard_active
            and ctx.time_in_state() > 10.0):
        return AgentState.FAILSAFE

    handlers = {
        AgentState.UNKNOWN: _from_unknown,
        AgentState.IDLE: _from_idle,
        AgentState.ARMING: _from_arming,
        AgentState.ARMED: _from_armed,
        AgentState.TAKEOFF: _from_takeoff,
        AgentState.IN_SWARM: _from_in_swarm,
        AgentState.EXECUTING_TASK: _from_executing_task,
        AgentState.DETACHED: _from_detached,
        AgentState.PRECISION_LANDING: _from_precision_landing,
        AgentState.WAITING_REJOIN: _from_waiting_rejoin,
        AgentState.REJOINING: _from_rejoining,
        AgentState.RETURN_HOME: _from_return_home,
        AgentState.LANDING: _from_landing,
        AgentState.LANDED: _from_landed,
        AgentState.FAILSAFE: _from_failsafe,
        AgentState.STANDBY: _from_standby,
    }
    handler = handlers.get(ctx.state)
    next_state = handler(ctx) if handler else None

    if next_state == AgentState.RETURN_HOME and not ctx.home_set:
        ctx.status_text = 'Home set değil - RTL yerine acil iniş'
        return AgentState.LANDING

    return next_state


def _from_unknown(ctx: AgentContext) -> AgentState | None:
    """PX4 linki kurulunca IDLE'a geçer; kurulana kadar UNKNOWN'da bekler."""
    if not ctx.px4_link_ok:
        return None
    return AgentState.IDLE


def _from_idle(ctx: AgentContext) -> AgentState | None:
    """IDLE durumundan gecisleri degerlendirir."""
    if ctx.pending_state == AgentState.ARMING:
        passed, _ = run_preflight_checks(ctx)
        if passed:
            return AgentState.ARMING
    return None


def _from_arming(ctx: AgentContext) -> AgentState | None:
    """ARMING durumundan gecisleri degerlendirir."""
    if ctx.armed:
        return AgentState.ARMED
    if not ctx.healthy:
        return AgentState.IDLE
    if ctx.time_in_state() > _ARMING_TIMEOUT_S:
        return AgentState.IDLE
    return None


def _from_armed(ctx: AgentContext) -> AgentState | None:
    """ARMED durumundan gecisleri degerlendirir."""
    if not ctx.armed or not ctx.healthy:
        return AgentState.IDLE
    if (ctx.mission_start_sequence_active
            and ctx.offboard_active
            and ctx.time_in_state() >= _ARMED_STABILIZE_S):
        return AgentState.TAKEOFF
    return None


def _from_takeoff(ctx: AgentContext) -> AgentState | None:
    """TAKEOFF durumundan gecisleri degerlendirir."""
    if (ctx.target_altitude_reached
            and ctx.altitude_stable
            and ctx.attitude_stable
            and ctx.vertical_speed_ok
            and (ctx.origin_synced or ctx.sitl_mode)):
        return AgentState.IN_SWARM
    return None


def _from_in_swarm(ctx: AgentContext) -> AgentState | None:
    """IN_SWARM durumundan gecisleri degerlendirir."""
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
    """EXECUTING_TASK durumundan gecisleri degerlendirir."""
    if ctx.pending_state == AgentState.RETURN_HOME:
        return AgentState.RETURN_HOME
    if ctx.pending_state == AgentState.IN_SWARM:
        return AgentState.IN_SWARM
    return None


def _from_detached(ctx: AgentContext) -> AgentState | None:
    """DETACHED durumundan gecisleri degerlendirir."""
    return AgentState.PRECISION_LANDING


def _from_precision_landing(ctx: AgentContext) -> AgentState | None:
    """PRECISION_LANDING durumundan gecisleri degerlendirir."""
    if not ctx.armed:
        return AgentState.WAITING_REJOIN
    return None


def _from_waiting_rejoin(ctx: AgentContext) -> AgentState | None:
    """WAITING_REJOIN durumundan gecisleri degerlendirir."""
    ready = (
        ctx.time_in_state() >= ctx.detach_wait_s
        or ctx.pending_state == AgentState.REJOINING
    )
    if ready:
        passed, _ = run_preflight_checks(ctx)
        if passed:
            return AgentState.ARMING
    if ctx.time_in_state() > _WAITING_REJOIN_TIMEOUT_S:
        return AgentState.FAILSAFE
    return None


def _from_rejoining(ctx: AgentContext) -> AgentState | None:
    """REJOINING durumundan gecisleri degerlendirir."""
    if ctx.pending_state == AgentState.IN_SWARM:
        return AgentState.IN_SWARM
    return None


def _from_return_home(ctx: AgentContext) -> AgentState | None:
    """RETURN_HOME durumundan gecisleri degerlendirir."""
    if ctx.flight_mode == FlightMode.AUTO_LAND:
        return AgentState.LANDING
    if ctx.pending_state == AgentState.LANDING:
        return AgentState.LANDING
    return None


def _from_landing(ctx: AgentContext) -> AgentState | None:
    """LANDING durumundan gecisleri degerlendirir."""
    if not ctx.armed:
        return AgentState.LANDED
    if ctx.time_in_state() > _LANDING_TIMEOUT_S:
        return AgentState.FAILSAFE
    return None


def _from_landed(ctx: AgentContext) -> AgentState | None:
    """LANDED durumundan gecisleri degerlendirir."""
    if ctx.pending_state == AgentState.STANDBY:
        return AgentState.STANDBY
    if ctx.pending_state == AgentState.IDLE:
        return AgentState.IDLE
    return None


def _from_failsafe(ctx: AgentContext) -> AgentState | None:
    """FAILSAFE durumundan gecisleri degerlendirir."""
    if not ctx.armed and ctx.pending_state == AgentState.IDLE:
        return AgentState.IDLE
    if ctx.healthy and ctx.pending_state == AgentState.RETURN_HOME:
        return AgentState.RETURN_HOME
    if ctx.pending_state == AgentState.LANDING:
        return AgentState.LANDING
    return None


def _from_standby(ctx: AgentContext) -> AgentState | None:
    """STANDBY durumundan gecisleri degerlendirir."""
    if ctx.wants_to_join and ctx.ready_to_arm:
        passed, _ = run_preflight_checks(ctx)
        if passed:
            return AgentState.ARMING
    return None
