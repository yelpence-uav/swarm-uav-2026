# Copyright 2026 Yelpence
"""Sürü seviyesi FSM durum geçiş kuralları."""

from ..agent_fsm.agent_states import AgentState
from .swarm_context import SwarmContext
from .swarm_states import SwarmState

_FORMING_READY_RATIO = 0.8

_LANDING_TIMEOUT_S = 120.0
_RTL_TIMEOUT_S = 180.0

_MISSION_COMPLETE_HOLD_S = 5.0


def evaluate_transitions(ctx: SwarmContext) -> SwarmState | None:
    """Mevcut sürü durumuna göre geçilmesi gereken sonraki state'i döner."""
    if ctx.pending_rtl and ctx.swarm_state not in (
        SwarmState.RTL,
        SwarmState.LANDING,
        SwarmState.MISSION_COMPLETE,
        SwarmState.FAILSAFE,
    ):
        ctx.pending_rtl = False
        return SwarmState.RTL

    if ctx.pending_land and ctx.swarm_state not in (
        SwarmState.LANDING,
        SwarmState.MISSION_COMPLETE,
    ):
        ctx.pending_land = False
        return SwarmState.LANDING

    handlers = {
        SwarmState.UNKNOWN: _from_unknown,
        SwarmState.IDLE: _from_idle,
        SwarmState.FORMING: _from_forming,
        SwarmState.NAVIGATING: _from_navigating,
        SwarmState.EXECUTING_TASK: _from_executing_task,
        SwarmState.ROTATING: _from_rotating,
        SwarmState.LANDING: _from_landing,
        SwarmState.RTL: _from_rtl,
        SwarmState.FAILSAFE: _from_failsafe,
        SwarmState.MISSION_COMPLETE: _from_mission_complete,
    }

    handler = handlers.get(ctx.swarm_state)
    return handler(ctx) if handler else None


def _from_unknown(ctx: SwarmContext) -> SwarmState | None:
    """UNKNOWN durumundan gecisleri degerlendirir."""
    return SwarmState.IDLE


def _from_idle(ctx: SwarmContext) -> SwarmState | None:
    """IDLE durumundan gecisleri degerlendirir."""
    if not ctx.mission_active:
        return None

    takeoff_count = ctx.count_agents_in_state(AgentState.TAKEOFF)
    in_swarm_count = ctx.count_agents_in_state(AgentState.IN_SWARM)

    if takeoff_count + in_swarm_count > 0:
        return SwarmState.FORMING

    return None


def _from_forming(ctx: SwarmContext) -> SwarmState | None:
    """FORMING durumundan gecisleri degerlendirir."""
    if not ctx.mission_active:
        return SwarmState.IDLE

    in_swarm = ctx.count_agents_in_state(AgentState.IN_SWARM)
    exec_task = ctx.count_agents_in_state(AgentState.EXECUTING_TASK)
    active_flyers = in_swarm + exec_task

    if ctx.active_agent_count > 0:
        ratio = active_flyers / ctx.active_agent_count
        if ratio >= _FORMING_READY_RATIO and ctx.formation_reached:
            return SwarmState.NAVIGATING

    return None


def _from_navigating(ctx: SwarmContext) -> SwarmState | None:
    """NAVIGATING durumundan gecisleri degerlendirir."""
    if not ctx.mission_active:
        return SwarmState.LANDING

    if ctx.rotation_active:
        return SwarmState.ROTATING

    exec_count = ctx.count_agents_in_state(AgentState.EXECUTING_TASK)
    if exec_count > 0:
        return SwarmState.EXECUTING_TASK

    return None


def _from_rotating(ctx: SwarmContext) -> SwarmState | None:
    """ROTATING durumundan gecisleri degerlendirir."""
    if not ctx.rotation_active:
        return SwarmState.NAVIGATING

    return None


def _from_executing_task(ctx: SwarmContext) -> SwarmState | None:
    """EXECUTING_TASK durumundan gecisleri degerlendirir."""
    if not ctx.mission_active:
        return SwarmState.LANDING

    exec_count = ctx.count_agents_in_state(AgentState.EXECUTING_TASK)
    if exec_count == 0:
        in_swarm = ctx.count_agents_in_state(AgentState.IN_SWARM)
        if in_swarm > 0:
            return SwarmState.NAVIGATING
        else:
            return SwarmState.FORMING

    return None


def _from_landing(ctx: SwarmContext) -> SwarmState | None:
    """LANDING durumundan gecisleri degerlendirir."""
    landed_states = {AgentState.LANDED, AgentState.IDLE}
    if ctx.all_agents_in_states(landed_states):
        return SwarmState.MISSION_COMPLETE

    if ctx.time_in_state() > _LANDING_TIMEOUT_S:
        ctx.status_text = (
            f'İniş timeout: {ctx.time_in_state():.0f}s'
        )
        return SwarmState.FAILSAFE

    return None


def _from_rtl(ctx: SwarmContext) -> SwarmState | None:
    """RTL durumundan gecisleri degerlendirir."""
    landing_count = ctx.count_agents_in_state(AgentState.LANDING)
    landed_count = ctx.count_agents_in_state(AgentState.LANDED)
    total_landing = landing_count + landed_count

    if ctx.active_agent_count > 0:
        ratio = total_landing / ctx.active_agent_count
        if ratio >= _FORMING_READY_RATIO:
            return SwarmState.LANDING

    if ctx.time_in_state() > _RTL_TIMEOUT_S:
        ctx.status_text = (
            f'RTL timeout: {ctx.time_in_state():.0f}s'
        )
        return SwarmState.FAILSAFE

    return None


def _from_failsafe(ctx: SwarmContext) -> SwarmState | None:
    """FAILSAFE durumundan gecisleri degerlendirir."""
    if ctx.expected_agent_count > 0:
        healthy = ctx.count_healthy_agents()
        ratio = healthy / ctx.expected_agent_count
        if ratio >= ctx.min_healthy_ratio:
            ctx.emergency_active = False
            return SwarmState.RTL

    landed_states = {AgentState.LANDED, AgentState.IDLE}
    if ctx.all_agents_in_states(landed_states):
        return SwarmState.MISSION_COMPLETE

    return None


def _from_mission_complete(ctx: SwarmContext) -> SwarmState | None:
    """MISSION_COMPLETE durumundan gecisleri degerlendirir."""
    if ctx.time_in_state() < _MISSION_COMPLETE_HOLD_S:
        return None

    if not ctx.mission_active:
        return SwarmState.IDLE

    return None
