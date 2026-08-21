# Copyright 2026 Yelpence
"""Lider secim mantigi."""

from swarm_interfaces.msg import ElectionResult

from .consensus_states import (
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
    ctx, now: float, own_aday: bool, eligible: set
) -> set:
    """Follower isek hb alamadigimiz lideri haric tutan kume.

    `own_aday`: BIZ lider adayi miyiz (ELIGIBLE_STATES icinde miyiz).

    20 AGUSTOS 2026'DA DUZELTILDI — P0.14(a). Bu parametre eskiden
    `own_airborne` idi ve YOL TAMAMEN OLUYDU:

        own_airborne = own.state in AIRBORNE_STATES
        AIRBORNE_STATES = {TAKEOFF, IN_SWARM, EXECUTING_TASK}

    ama gecis doneminde `kalkis_olayla=false` oldugu icin FSM UCUS BOYUNCA
    ARMED'da kaliyor (agent_transitions.py:160-163 kapisi hic acilmiyor) ve
    ARMED o kumede YOK. Yani `heartbeat_timeout_ms` hicbir kararda
    kullanilmiyordu; cok ajanli denetimde 2/2 dogrulandi.

    Somut sonucu: liderin consensus'u coker ama agent_fsm + esp32_bridge
    calismaya devam ederse takipci lider kaybini ASLA fark etmez. Tek yedek
    3 sn'lik bayatlik ve o da yanlis akisi olcuyordu (P0.14b).

    `own_aday` dogru sarttir: lider kaybiyla ilgilenmemizin sebebi havada
    olmamiz degil, ADAY olmamiz — uygun degilsek zaten secim yapamayiz.
    """
    effective = set(eligible)
    if not ctx.is_leader and ctx.leader_id != 0 and own_aday:
        # LIDER YAYIN YAPMALI MIYDI? — P0.14(a), 20 Agustos 2026.
        #
        # Bu kapi eskiden `lrec.state in AIRBORNE_STATES` idi ve `own_airborne`
        # ile AYNI hastaligi tasiyordu: ARMED o kumede yok. Bugun tesadufen
        # calisiyordu, cunku mesh ARMED'i KALKIS'a esleyip karsi tarafta
        # STATE_TAKEOFF'a cozuyor (TUZAKLAR 4.9) — yani uzak ARMED lider
        # "havada" gorunuyor. O esleme ADIM 3/4 on kosullari arasinda
        # DEGISECEK; degistigi gun bu kapi sessizce kapanirdi.
        #
        # Dayandigi varsayim da artik gecersiz: "yerdeki lider kalp atisi
        # yayinlamaz" idi, ama 19 Agustos'tan beri (c3068c8) lider oldugu
        # surece YERDE DE yayinliyor. Ustelik P0.12(a) ile uygunlugunu
        # yitiren lider liderligi BIRAKIYOR ve yayini kendisi kesiyor.
        #
        # Dogru sart: lider YAYIN YAPMASI GEREKEN bir durumda mi
        # (ELIGIBLE_STATES). Oyleyse ve kalp atisi gelmiyorsa KAYIPTIR.
        lrec = ctx.agents.get(ctx.leader_id)
        lider_yayinlamali = (
            lrec is not None and lrec.state in ELIGIBLE_STATES
        )
        hb_age = (
            (now - ctx.last_hb_time) if ctx.last_hb_time > 0 else 1e9
        )
        if lider_yayinlamali and hb_age > ctx.hb_timeout_s:
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
        # ONALMA BASTIRMASI — P1.14. Rakibe bilerek boyun egdiysek
        # (kalp atisimiz ona ulasmiyor) burasi bizi aninda geri lider
        # yapar ve 10 Hz'lik titreme olusur. Damga dolana kadar sus.
        #
        # NOT: yalniz BU dal bastiriliyor. Ustteki `leader_id not in
        # effective` (LEADER_FAULT) dali bilerek disarida — bastirilsaydi
        # boyun egmenin ardindan gelen 10 sn boyunca lider GERCEKTEN olse
        # bile kimse devralmazdi. test_rakip_lider.py bunu kilitliyor.
        if now < ctx.onalma_bastir_until:
            return None
        return (candidate, ElectionResult.REASON_UNKNOWN)
    return None
