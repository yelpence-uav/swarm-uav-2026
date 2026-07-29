# Copyright 2026 Yelpence
"""Gorev FSM gecis kurallari."""

import time

from .mission_context import MissionContext
from .mission_states import MissionState, MissionType, QrTaskStep

_CMD_START = 1
_CMD_ABORT = 2
_CMD_PAUSE = 3
_CMD_RESUME = 4
_CMD_RTL = 5
_CMD_LAND = 6

_PREFLIGHT_TIMEOUT_S = 3600.0
_TAKEOFF_TIMEOUT_S = 90.0
_NAVIGATE_TIMEOUT_S = 120.0
_QR_TASK_TIMEOUT_S = 90.0
_ROTATE_TIMEOUT_S = 30.0
_RETURN_HOME_TIMEOUT_S = 120.0
_LANDING_TIMEOUT_S = 90.0

_ROUTE_UNKNOWN_GRACE_S = 30.0

_TERMINAL_STATES = frozenset({
    MissionState.MISSION_COMPLETE,
    MissionState.ABORTED,
})


def evaluate_transitions(ctx: MissionContext) -> MissionState | None:
    """Bir sonraki MissionState'i ya da gecis yoksa None doner."""
    if ctx.pending_command == _CMD_ABORT:
        if ctx.state not in _TERMINAL_STATES:
            return MissionState.ABORTED

    if (ctx.pending_command == _CMD_RTL
            and ctx.state not in _TERMINAL_STATES
            and ctx.state not in (
                MissionState.RETURN_HOME,
                MissionState.LANDING,
                MissionState.IDLE,
            )):
        return MissionState.RETURN_HOME

    if (ctx.pending_command == _CMD_LAND
            and ctx.state not in _TERMINAL_STATES
            and ctx.state not in (
                MissionState.LANDING,
                MissionState.IDLE,
            )):
        return MissionState.LANDING

    if (ctx.pending_command == _CMD_PAUSE
            and ctx.state not in _TERMINAL_STATES
            and ctx.state not in (
                MissionState.IDLE,
                MissionState.PAUSED,
                MissionState.PREFLIGHT,
                MissionState.SYNCHRONIZED_TAKEOFF,
                MissionState.RETURN_HOME,
                MissionState.LANDING,
            )):
        return MissionState.PAUSED

    handler = _HANDLERS.get(ctx.state)
    return handler(ctx) if handler else None


def _from_unknown(ctx: MissionContext) -> MissionState | None:
    """UNKNOWN durumundan gecisleri degerlendirir."""
    return MissionState.IDLE


def _from_idle(ctx: MissionContext) -> MissionState | None:
    """IDLE durumundan gecisleri degerlendirir."""
    if ctx.pending_command == _CMD_START:
        return MissionState.PREFLIGHT
    return None


def _from_preflight(ctx: MissionContext) -> MissionState | None:
    """PREFLIGHT durumundan gecisleri degerlendirir."""
    if not ctx.all_agents_seen:
        if ctx.time_in_state() > _PREFLIGHT_TIMEOUT_S:
            return MissionState.ABORTED
        return None

    gps_ok = ctx.sitl_mode or ctx.all_agents_gps_ok()
    origin_ok = ctx.sitl_mode or ctx.all_agents_origin_synced()
    home_ok = ctx.sitl_mode or ctx.all_agents_home_set()

    if ctx.all_agents_healthy() and gps_ok and origin_ok and home_ok:
        return MissionState.SYNCHRONIZED_TAKEOFF

    if ctx.time_in_state() > _PREFLIGHT_TIMEOUT_S:
        return MissionState.ABORTED

    return None


def _from_synchronized_takeoff(ctx: MissionContext) -> MissionState | None:
    """SYNCHRONIZED_TAKEOFF durumundan gecisleri degerlendirir."""
    if ctx.all_agents_in_swarm():
        if ctx.mission_type == MissionType.SEMI_AUTONOMOUS:
            return MissionState.SEMI_AUTONOMOUS
        return MissionState.ROTATE_TO_NEXT

    if ctx.time_in_state() > _TAKEOFF_TIMEOUT_S:
        return MissionState.ABORTED

    return None


def _from_navigate_to_qr(ctx: MissionContext) -> MissionState | None:
    """NAVIGATE_TO_QR durumundan gecisleri degerlendirir."""
    if ctx.event_formation_reached:
        return MissionState.EXECUTE_QR_TASK

    if ctx.route_unknown and ctx.time_in_state() > _ROUTE_UNKNOWN_GRACE_S:
        return MissionState.RETURN_HOME

    if ctx.time_in_state() > _NAVIGATE_TIMEOUT_S:
        return MissionState.RETURN_HOME

    return None


def _from_execute_qr_task(ctx: MissionContext) -> MissionState | None:
    """EXECUTE_QR_TASK durumundan gecisleri degerlendirir."""
    qr = ctx.current_qr
    if qr is None:
        if ctx.time_in_state() > _QR_TASK_TIMEOUT_S:
            return MissionState.RETURN_HOME
        return None

    if ctx.action_done and not ctx.action_success:
        return MissionState.RETURN_HOME

    if ctx.qr_task_step == QrTaskStep.DONE:
        if qr.complete_mission:
            return MissionState.RETURN_HOME
        if qr.wait_s > 0.0:
            return MissionState.WAIT_AT_QR
        if qr.next_qr > 0:
            return MissionState.ROTATE_TO_NEXT
        return MissionState.RETURN_HOME

    if ctx.time_in_state() > _QR_TASK_TIMEOUT_S:
        return MissionState.RETURN_HOME

    return None


def _from_wait_at_qr(ctx: MissionContext) -> MissionState | None:
    """WAIT_AT_QR durumundan gecisleri degerlendirir."""
    deadline_passed = (
        ctx.wait_deadline is not None
        and time.monotonic() >= ctx.wait_deadline
    )
    if deadline_passed:
        qr = ctx.current_qr
        if qr is not None and qr.next_qr > 0 and not qr.complete_mission:
            return MissionState.ROTATE_TO_NEXT
        return MissionState.RETURN_HOME

    return None


def _from_rotate_to_next(ctx: MissionContext) -> MissionState | None:
    """ROTATE_TO_NEXT durumundan gecisleri degerlendirir."""
    if ctx.event_rotation_completed:
        return MissionState.NAVIGATE_TO_QR

    if ctx.time_in_state() > _ROTATE_TIMEOUT_S:
        return MissionState.NAVIGATE_TO_QR

    return None


def _from_semi_autonomous(ctx: MissionContext) -> MissionState | None:
    """SEMI_AUTONOMOUS durumundan gecisleri degerlendirir."""
    return None


def _from_return_home(ctx: MissionContext) -> MissionState | None:
    """RETURN_HOME durumundan gecisleri degerlendirir."""
    if ctx.all_agents_landing() or ctx.all_agents_landed():
        return MissionState.LANDING

    if ctx.time_in_state() > _RETURN_HOME_TIMEOUT_S:
        return MissionState.LANDING

    return None


def _from_landing(ctx: MissionContext) -> MissionState | None:
    """LANDING durumundan gecisleri degerlendirir."""
    if ctx.all_agents_landed():
        return MissionState.MISSION_COMPLETE

    if ctx.time_in_state() > _LANDING_TIMEOUT_S:
        return MissionState.MISSION_COMPLETE

    return None


def _from_paused(ctx: MissionContext) -> MissionState | None:
    """PAUSED durumundan gecisleri degerlendirir."""
    if ctx.pending_command == _CMD_RESUME:
        return ctx.pause_return_state
    return None


_HANDLERS = {
    MissionState.UNKNOWN: _from_unknown,
    MissionState.IDLE: _from_idle,
    MissionState.PREFLIGHT: _from_preflight,
    MissionState.SYNCHRONIZED_TAKEOFF: _from_synchronized_takeoff,
    MissionState.NAVIGATE_TO_QR: _from_navigate_to_qr,
    MissionState.EXECUTE_QR_TASK: _from_execute_qr_task,
    MissionState.WAIT_AT_QR: _from_wait_at_qr,
    MissionState.ROTATE_TO_NEXT: _from_rotate_to_next,
    MissionState.SEMI_AUTONOMOUS: _from_semi_autonomous,
    MissionState.RETURN_HOME: _from_return_home,
    MissionState.LANDING: _from_landing,
    MissionState.PAUSED: _from_paused,
}


def find_first_qr_step(qr) -> QrTaskStep:
    """Mesajdaki ilk aktif QrTaskStep'i doner."""
    if qr is None:
        return QrTaskStep.DONE

    if getattr(qr, 'formation_active', False):
        return QrTaskStep.FORMATION
    if getattr(qr, 'maneuver_active', False):
        return QrTaskStep.MANEUVER
    if getattr(qr, 'altitude_active', False):
        return QrTaskStep.ALTITUDE
    if getattr(qr, 'detach_active', False):
        return QrTaskStep.DETACH
    return QrTaskStep.DONE


def find_next_qr_step(qr, current: QrTaskStep) -> QrTaskStep:
    """Tamamlanan adimdan sonraki aktif adimi doner."""
    if qr is None:
        return QrTaskStep.DONE

    order = [
        (QrTaskStep.FORMATION, getattr(qr, 'formation_active', False)),
        (QrTaskStep.MANEUVER, getattr(qr, 'maneuver_active', False)),
        (QrTaskStep.ALTITUDE, getattr(qr, 'altitude_active', False)),
        (QrTaskStep.DETACH, getattr(qr, 'detach_active', False)),
    ]

    passed = False
    for step, active in order:
        if step == current:
            passed = True
            continue
        if passed and active:
            return step

    return QrTaskStep.DONE
