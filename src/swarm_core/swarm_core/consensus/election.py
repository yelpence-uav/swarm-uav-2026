"""Saf lider seçim mantığı — deterministik, PREEMPTIVE (self-promotion).

ROS'tan bağımsız ve test edilebilir. KTR 5.1: lider = uygun havuzdaki en
küçük agent_id. Toparlanan küçük ID liderliği GERİ ALIR — AMA liderlik
İTİLMEZ, ÇEKİLİR: küçük ID yalnızca KENDİ canlı consensus'uyla kendini
terfi ettirir; başka bir lider, telemetriye bakıp ölü/uygun-görünen bir
drona liderlik İTMEZ. Ölü dron kendini ilan edemez → flapping olmaz.
Yield (split-brain heal) consensus_node._on_heartbeat'te: küçük-ID lider
heartbeat'i duyan büyük-ID lider çekilir.

KARAR:
  - Bootstrap (lider yok)                  → en küçük uygun (grace ile).
  - Failover (mevcut lider effective'den   → en küçük uygun devralır.
    düştü: heartbeat timeout/uygunsuzluk)
  - Self-promotion: BEN en küçük uygunum ve → kendimi terfi ettiririm
    daha büyük ID'li liderin altındayım       (sadece ben, canlıyken).
  - Aksi halde                              → değiştirme.
"""

from swarm_interfaces.msg import ElectionResult

from .consensus_states import (
    AIRBORNE_STATES,
    ELIGIBLE_STATES,
    INELIGIBLE_ROLES,
)


def is_eligible(rec, now: float, stale_s: float, battery_min_v: float) -> bool:
    """KTR 5.1 uygunluk filtresi: konum/EKF2/bağlantı/batarya + durum/rol."""
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
    """Uygun (lider adayı olabilen) ajan id'leri kümesi."""
    return {
        aid for aid, rec in ctx.agents.items()
        if is_eligible(rec, now, ctx.stale_s, ctx.battery_min_v)
    }


def effective_set(ctx, now: float, own_airborne: bool, eligible: set) -> set:
    """Uygun küme; follower isek heartbeat'i kesilen lideri dışlar.

    Heartbeat-timeout kontrolü YALNIZCA lider ve ben havadayken yapılır;
    yerde lider kaybı uygunluk filtresinin stale/fault yoluyla anlaşılır.
    """
    effective = set(eligible)
    if not ctx.is_leader and ctx.leader_id != 0 and own_airborne:
        lrec = ctx.agents.get(ctx.leader_id)
        leader_airborne = lrec is not None and lrec.state in AIRBORNE_STATES
        hb_age = (now - ctx.last_hb_time) if ctx.last_hb_time > 0 else 1e9
        if leader_airborne and hb_age > ctx.hb_timeout_s:
            effective.discard(ctx.leader_id)
    return effective


def decide_change(ctx, effective: set, now: float):
    """Preemptive (self-promotion) liderlik kararı.

    - Bootstrap (lider yok): alanın oturması için KISA grace bekler → kesin
      min-ID, erken seçim min-ID kaçırmaz.
    - Failover: mevcut lider effective'den DÜŞTÜĞÜNDE → en küçük uygun devralır.
    - Self-promotion: BEN en küçük uygunsam ve daha büyük ID'li liderin
      altındaysam KENDİMİ terfi ettiririm (KTR: en küçük sağlıklı ID lider).
      Yalnızca BEN (candidate==agent_id) terfi olur — kimse başkasına liderlik
      İTMEZ → ölü ama uygun-görünen drona itip flap olmaz.

    Returns:
        (new_leader_id, reason) tuple veya değişim yoksa None.
    """
    candidate = min(effective) if effective else 0
    if candidate == 0:
        return None
    if ctx.leader_id == 0:
        # Bootstrap grace — tüm alan belli olana ya da grace bitene kadar bekle.
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
        return (candidate, ElectionResult.REASON_LEADER_FAULT)   # failover
    # Lider hâlâ geçerli, ama daha küçük ID var → SELF-PROMOTION:
    # yalnızca BEN en küçüksem kendimi terfi ettiririm (push değil, pull).
    if candidate == ctx.agent_id and candidate < ctx.leader_id:
        return (candidate, ElectionResult.REASON_UNKNOWN)
    return None
