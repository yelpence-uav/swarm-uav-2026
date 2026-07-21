# Copyright 2026 Yelpence
"""Lider secim mantigi."""

from swarm_interfaces.msg import ElectionResult

from .consensus_states import (
    AIRBORNE_STATES,
    ELIGIBLE_STATES,
    INELIGIBLE_ROLES,
)


def is_eligible(
    rec, now: float, stale_s: float, battery_min_v: float
) -> bool:
    """Ajanin liderlik icin uygunlugunu denetler."""
    if rec is None:
        return False
    if rec.is_stale(now, stale_s):
        return False
    if rec.role in INELIGIBLE_ROLES:
        return False
    if rec.state not in ELIGIBLE_STATES:
        return False
    if not rec.healthy:
        return False
    if not rec.estimator_ok:
        return False
    if rec.battery_v > 0.0 and rec.battery_v < battery_min_v:
        return False
    return True


def eligible_ids(ctx, now: float) -> set:
    """Uygun olan ajan id'leri kumesini doner."""
    return {
        aid for aid, rec in ctx.agents.items()
        if is_eligible(rec, now, ctx.stale_s, ctx.battery_min_v)
    }


def effective_set(
    ctx, now: float, own_airborne: bool, eligible: set
) -> set:
    """Follower isek hb alamadigimiz lideri haric tutan kume."""
    effective = set(eligible)
    if not ctx.is_leader and ctx.leader_id != 0 and own_airborne:
        lrec = ctx.agents.get(ctx.leader_id)
        leader_airborne = (
            lrec is not None and lrec.state in AIRBORNE_STATES
        )
        hb_age = (
            (now - ctx.last_hb_time) if ctx.last_hb_time > 0 else 1e9
        )
        if leader_airborne and hb_age > ctx.hb_timeout_s:
            effective.discard(ctx.leader_id)
    return effective


def decide_change(ctx, effective: set, now: float):
    """Preemptive liderlik degisimi kararini verir."""
    candidate = min(effective) if effective else 0
    if candidate == 0:
        return None
    if ctx.leader_id == 0:
        full_field = len(effective) >= ctx.agent_count
        grace_done = (
            ctx.bootstrap_since > 0.0
            and (now - ctx.bootstrap_since) >= ctx.grace_s
        )
        if full_field or grace_done:
            return (candidate, ElectionResult.REASON_UNKNOWN)
        return None
    if ctx.leader_id == candidate:
        return None
    if ctx.leader_id not in effective:
        return (candidate, ElectionResult.REASON_LEADER_FAULT)
    if candidate == ctx.agent_id and candidate < ctx.leader_id:
        return (candidate, ElectionResult.REASON_UNKNOWN)
    return None
