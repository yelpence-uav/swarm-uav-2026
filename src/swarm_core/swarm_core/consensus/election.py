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
    # --- SABIT LIDER — 4 Eylul 2026, operator karari. SISTEM GENELI. ------
    #
    # KAPSAM: HEM GOREV 1 HEM GOREV 2. (Ilk tasarimda yalniz Gorev 2'ydi;
    # operator ayni gun kapsami genisletti — gorev bazli dallanma
    # KALDIRILDI, tek profil tek davranis.) `ctx.sabit_lider == 0` iken bu
    # blok HICBIR SEY YAPMAZ ve asagidaki secim mantigi bire bir eski
    # hâliyle kosar; kapatma anahtari budur.
    #
    # NEDEN VAR: lider kilidi (3 Eylul) ILK secimi NIHAI yapiyor, ama o
    # secimin ylp00'a dusmesi TESADUFE bagliydi: `candidate = min(effective)`
    # + tam kadro beklemesi. Tam kadro `kilit_tam_kadro_s` (8 sn) icinde
    # olusmazsa yedek yol devreye giriyor ve O AN uygun olan kim varsa
    # KALICI lider oluyordu. Ucaklar arasi evre kaymasi 3 Eylul ucusunda
    # 25 SANIYE olculdu — yani 8 sn'lik pencere guvenilir degil ve yanlis
    # lider bir daha duzelmiyor.
    #
    # NEDEN GOREV 1'DE DE GUVENLI: `lider_kilitli` ZATEN gorevden bagimsiz
    # ve sahada `true`. Yani Gorev 1'de de devir coktan kapaliydi; bu blok
    # yeni bir kisit GETIRMIYOR, yalnizca kimligi yarisa birakmak yerine
    # belirli kiliyor. Net etki risk AZALTMASI.
    #
    # Bu blok tesadufu KURALA cevirir: kimlik disaridan verilir, uygunluga
    # BAKILMAZ (aday beklenmez), ve bir kez kurulduktan sonra hicbir yoldan
    # degismez. Uygunluk kapisi bilerek yok: bekleseydik ylp00 gec arm
    # oldugunda yine yedek yola dusme riski kalirdi — ki kapatmaya
    # calistigimiz sey tam olarak o.
    #
    # 🔴 BEDELI — `lider_kilitli` ile ayni ve bilerek kabul edildi: sabit
    # lider GERCEKTEN duserse devir OLMAZ, takipciler son formasyon
    # komutunda kalir; cikis yolu kill switch pilotlaridir. Parametre
    # oldugu icin tek satirla kapanir (SURU_SABIT_LIDER=0).
    #
    # ⚠️ Bu fonksiyon liderin degisebilecegi DORT yoldan yalniz birincisi.
    # Digerleri (_liderligi_birak, _adopt_leader, _rakip_tahkim)
    # consensus_node icinde ayrica kapatiliyor; biri atlanirsa mesh'ten
    # gelen tek bir kalp atisi sabit lideri devirir.
    if ctx.sabit_lider:
        if ctx.leader_id == ctx.sabit_lider:
            return None
        return (ctx.sabit_lider, ElectionResult.REASON_UNKNOWN)

    candidate = min(effective) if effective else 0
    if candidate == 0:
        return None
    if ctx.leader_id == 0:
        full_field = len(effective) >= ctx.agent_count
        grace_done = (
            ctx.bootstrap_since > 0.0
            and (now - ctx.bootstrap_since) >= ctx.grace_s
        )
        # 🔴 KILIT ACIKKEN ILK SECIM YARISA GIREMEZ — 3 Eylul 2026.
        #
        # Kilit degisimi kapatiyor, yani ILK secim ARTIK NIHAI. Oysa bu dal
        # `grace_s` = 1.5 SANIYE sonra, o an uygun olan kim varsa onunla
        # secim yapiyor: `bootstrap_since` ILK uygun ajan gorununce
        # basliyor, ucunun de uygun olmasini BEKLEMIYOR.
        #
        # Neden gercek bir risk: uygunluk ARM ile basliyor ve ucaklar ayni
        # anda arm olmuyor. 3 Eylul ucusunda ucaklar arasi EVRE KAYMASI
        # 25 SANIYE olculdu — 1.5 sn'lik pencere guvenilir sekilde
        # tutmuyor. Kilit yokken bu onemsizdi (yanlis lider bir sonraki
        # turda duzeliyordu); kilit VARKEN yanlis lider KALICI olur ve
        # slotlar butun ucus boyunca yanlis ucakta kalir.
        #
        # Cozum: kilit acikken TAM KADRO beklenir. Bu deterministiktir —
        # aday min(1,2,3) = 1 (ylp00). Ama sonsuza kadar beklenmez:
        # `kilit_tam_kadro_s` dolunca eski davranisa DUSULUR, yoksa bir
        # ucak hic arm olmazsa suru HIC lider secemez ve gorev baslamaz.
        if ctx.lider_kilitli and not full_field:
            tam_kadro_beklendi = (
                ctx.bootstrap_since > 0.0
                and (now - ctx.bootstrap_since) >= ctx.kilit_tam_kadro_s
            )
            if not tam_kadro_beklendi:
                return None
        if full_field or grace_done:
            return (candidate, ElectionResult.REASON_UNKNOWN)
        return None
    if ctx.leader_id == candidate:
        return None

    # --- LIDER KILIDI (operator karari, 3 Eylul 2026) -------------------
    # Lider BIR KEZ secilir, bir daha degismez. Ilk secim (leader_id == 0)
    # yukarida yapildi; buradan sonrasi yalniz DEGISIM kararlaridir.
    #
    # NEDEN: 3 Eylul ucusunda liderlik BES KEZ el degistirdi
    # (1->2, 2->1, 1->2, 2->1, 1->3). Kok neden DURUM paketinin bayatlamasi:
    # ucak basina 7-8 kez "DURUM paketi 5.0-5.1 sndir gelmedi (esik 5.0)"
    # olculdu, yani lider anlik olarak uygun kumeden dusuyordu. Her degisim
    # yeni liderin slot atamasini yeniden hesaplamasina yol acti; ylp01 ile
    # ylp02 YER DEGISTIRDI, birbirinin ustunden gectiler ve kacinma
    # binlerce kare devrede kaldi (avoid=1136 / 1614, yatay_tut=48/52).
    #
    # 🔴 BEDELI — bilerek kabul edildi: lider GERCEKTEN duserse devir OLMAZ.
    # Takipciler son formasyon komutunda kalir (yerinde tutar), yeni komut
    # gelmez. Cikis yolu kill switch pilotlaridir. Bu yuzden bir PARAMETRE:
    # yarisma gunu tek satirla acilip kapatilabilir (SURU_LIDER_KILIDI).
    if ctx.lider_kilitli:
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
