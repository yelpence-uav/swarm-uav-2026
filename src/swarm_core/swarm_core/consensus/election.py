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


def seq_kabul(
    seen: dict, kaynak: int, incarnation: int, seq: int
) -> tuple[bool, bool]:
    """Eskimis ElectionResult filtresi. Saf mantik, ROS bagimsiz.

    Onceden tek global `max_seen_seq` vardi ve iki ayri ariza uretiyordu
    (30 Temmuz, iki kollu deneyle olculdu):
      1. Yayinci dugum yeniden baslarsa `out_seq` 0'a doner. Global sayac
         yuksek kaldigi icin liderin BUTUN yeni secim sonuclari sessizce
         duserdi - log yok, uyari yok.
      2. Lider el degistirirse yeni lider de seq=1'den baslar; ayni sekilde
         duserdi. Bu, normal bir islem oldugu icin daha da sinsiydi.
    Kaynak basina tutmak (2)'yi, incarnation karsilastirmasi (1)'i cozer.

    Args:
        seen (dict): {kaynak_ajan: (incarnation, gorulen_en_yuksek_seq)}.
            Bu fonksiyon SOZLUGU DEGISTIRMEZ; guncellemeyi cagiran yapar.
        kaynak (int): Mesaji yayinlayan ajan (triggered_by_agent_id).
        incarnation (int): Yayincinin acilis kimligi. 0 = bilinmiyor.
        seq (int): Mesajin sequence_num'i.

    Returns:
        tuple: (kabul_edilir, incarnation_degisti). `incarnation_degisti`
        yalnizca bu kaynak daha once gorulduyse ve kimlik farkliysa True -
        cagiran bunu loglayabilsin diye ayri donuyor.
    """
    onceki = seen.get(kaynak)
    if onceki is None:
        return True, False
    eski_inc, eski_seq = onceki
    if eski_inc != incarnation:
        # Yayinci yeniden baslamis: sayac sifirlandi, mesaj taze kabul edilir.
        return True, True
    return seq > eski_seq, False


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
