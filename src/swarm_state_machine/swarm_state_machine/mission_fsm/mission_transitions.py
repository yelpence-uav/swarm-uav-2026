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
_NAVIGATE_TIMEOUT_S = 300.0
# Ayrılan ajanın sürüye dönmesi için QR'da beklenecek üst sınır (NAVIGATE'e
# girişten itibaren). Ajan: renkli alana in → disarm → bekle → arm → sürüye
# yetiş. Aşılırsa görev eksik sürüyle de olsa ilerler (tıkanma yerine kısmi
# puan). _NAVIGATE_TIMEOUT_S'ten küçük olmalı ki RETURN_HOME yedeği yaşasın.
_REJOIN_WAIT_S = 150.0
# QR okunamazsa orchestrator ısrarcı arama yapar (alçal/yüksel/ileri/geri,
# döngüsel). Eşik bu aramaya yetmeli; kısa eşik sürüyü tek denemede pes ettirip
# eve gönderir. 240 s ≈ 10 tam arama turu.
_QR_TASK_TIMEOUT_S = 240.0
_ROTATE_TIMEOUT_S = 30.0
_RETURN_HOME_TIMEOUT_S = 120.0
# Restart bekleyen (QR okunamamış) dönüşte sürü eve varana kadar indirilmez;
# bu sert sınır yalnız sonsuz takılmaya karşıdır (ev ulaşılamıyorsa iniş).
_RETURN_HOME_HARD_TIMEOUT_S = 300.0
_LANDING_TIMEOUT_S = 90.0
# AgentStatus.STATE_IDLE — terminal durumdan güvenli toparlanma kontrolü için.
_AGENT_STATE_IDLE = 1
# Terminal durumdan (ABORTED / MISSION_COMPLETE) IDLE'a dönmeden önce beklenen
# süre: terminal durumun YKİ'de görülebilmesi + durum yerleşimi içindir.
_TERMINAL_RESET_DWELL_S = 3.0

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

    # RTL = eve dön, sonra in. Görev bitişinin normal yolu budur ve şartname
    # 5.1.2 madde 17-18 bunu zorunlu kılar ("sürü home konumuna dönüş yapar",
    # "home konumuna ulaşıldığında ... güvenli bir iniş").
    if (ctx.pending_command == _CMD_RTL
            and ctx.state not in _TERMINAL_STATES
            and ctx.state not in (
                MissionState.RETURN_HOME,
                MissionState.LANDING,
                MissionState.IDLE,
            )):
        return MissionState.RETURN_HOME

    # LAND = OLDUĞUN YERDE İN. Eskiden RTL ile aynı daldaydı ve ikisi de
    # RETURN_HOME'a gidiyordu; yani "LAND" adı davranışını anlatmıyordu.
    # TriggerMission.srv bu komutu "test/safety/emergency use" diye tanımlar;
    # acil durumda beklenen davranış eve uçmak değil derhal inmektir.
    # RETURN_HOME'dan da kabul edilir: eve dönüş sürerken "burada in" demek
    # anlamlı olmalıdır (RTL'de gerekmez, o zaten eve gidiyor).
    #
    # GÖREV AKIŞI ETKİLENMEZ: bu komut kendiliğinden hiç gönderilmez. Görev
    # normal bitince FSM yine RETURN_HOME'a gider ve sürü eve dönüp home'da
    # iner. Yalnızca dışarıdan (YKİ/operatör) bilinçli gönderilirse çalışır.
    if (ctx.pending_command == _CMD_LAND
            and ctx.state not in _TERMINAL_STATES
            and ctx.state not in (
                MissionState.LANDING,
                MissionState.IDLE,
            )):
        return MissionState.LANDING

    # PAUSE, kalkış sırasında güvensiz kesintileri önlemek için engellenir.
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
        # 🔴 GOREV 2 KALKISI ATLAR — madde 27, 30 Agustos 2026.
        #
        # Sartname §5.2.2 kalkisi KUMANDAYA veriyor ("Takeoff ve land
        # komutlari da kumanda uzerinden yapilir") ve senaryo madde 4
        # (YKI: yari otonom moda gec) ile madde 5 (kumandadan kalkis)
        # AYRI adimlar. SYNCHRONIZED_TAKEOFF'tan gecmek iki sekilde
        # sartnameyi ve guvenligi bozardi:
        #
        #   1. O durumun girisi EVENT_MISSION_STARTED yayinliyor;
        #      agent_fsm onu ARM'a ceviriyor (agent_fsm_node.py:304).
        #      Yani "YKI'de BASLAT'a basmak SURUYU ARMLAR" demek olurdu —
        #      30 Agustos saha olayinin birebir tekrari, bu sefer baska
        #      dugumden. (gorev2.md §7.6)
        #   2. SYNCHRONIZED_TAKEOFF'un cikisi `all_agents_in_swarm()`.
        #      Gorev 2'de kalkisi mode_manager suruyor ve agent_fsm
        #      IDLE'da kaliyor — o kosul HIC gerceklesmez. mission_state
        #      8 olmaz, mode_manager'in ucuncu kapisi (G2-K10) HIC
        #      acilmaz ve suru kalkamaz. Sessiz kilitlenme.
        #
        # Preflight denetimleri (saglik + GPS + origin + home) BURADA
        # KALIYOR: G2-K10'un ucuncu kapisi artik "operator BASLAT'a basti
        # VE ucaklar preflight'i gecti" anlamina geliyor.
        if ctx.mission_type == MissionType.SEMI_AUTONOMOUS:
            return MissionState.SEMI_AUTONOMOUS
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
        # REJOIN KAPISI: ayrılan ajan sürüye katılmadan QR görevlerini BAŞLATMA.  # noqa: E501
        # Şartname, ayrılan elemanın "en geç bir sonraki QR kodunun GÖREVİNE
        # katılarak" sürüyle hareket etmesini ister; ayrıca formasyon/manevra/
        # rotasyon görevleri minimum 3 İHA gerektirir (Tablo 7) → eksik sürüyle
        # icra edilirse o kalemlerden puan alınamaz. Ajan iner, disarm olur,
        # bekler, tekrar arm olup sürüye yetişir; o dönene kadar burada beklenir.  # noqa: E501
        #
        # Sonsuz bekleme yok: ajan dönemezse (_REJOIN_WAIT_S aşılırsa) görev
        # eksik sürüyle de olsa ilerler — tamamen tıkanmaktansa kısmi puan.
        if (ctx.swarm_incomplete()
                and ctx.time_in_state() <= _REJOIN_WAIT_S):
            return None
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
        # Ayrılan ajan (renkli alana inen) sürüye dönmeden QR'dan ayrılma:
        # rotasyon ve sonraki QR'a geçiş sürünün TAMAMIYLA yapılır. Bu kapı
        # olmadan kalan dronlar inen dronu geride bırakıp dönüyordu.
        if ctx.swarm_incomplete():
            if ctx.time_in_state() <= _QR_TASK_TIMEOUT_S + _REJOIN_WAIT_S:
                return None
            return MissionState.RETURN_HOME
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
    """RETURN_HOME: sürü kalkış noktasına geri dönüyor."""
    # Şartname madde 17: QR okunamadığı için eve dönüldüyse, eve varınca
    # (formasyon home'a ulaşınca) rotayı baştan başlat. Şartname sınır
    # koymaz; max_restarts=0 → SINIRSIZ (batarya/hakem bitirir). >0 verilirse
    # o kadar denenip aşılınca normal inişe geçilir.
    restart_viable = (
        ctx.restart_pending
        and (ctx.max_restarts <= 0
             or ctx.restart_count < ctx.max_restarts)
    )

    if restart_viable and ctx.event_formation_reached:
        return MissionState.ROTATE_TO_NEXT

    # Sürüyü EVE VARMADAN indirme — HEM restart HEM NORMAL bitişte. Şartname en
    # son home'a dönüşü ister. Eskiden normal bitişte "ajanlar iniyor mu"
    # (all_agents_landing) ya da kısa timeout iniş tetikliyordu; bir ajan
    # FAILSAFE'e düşünce (örn. hassas iniş başarısız) bu koşul ANINDA doğru
    # olup sürüyü home'a hiç uçurmadan bulunduğu rastgele yere indiriyordu
    # (ölçüldü: RETURN_HOME yalnız 2 sn sürüp LANDING'e atladı). Artık sürü,
    # formasyon HOME'DA oturana kadar (event_formation_reached) uçar; sonsuz
    # takılmayı sert üst sınır (hard timeout) önler.
    if ctx.time_in_state() > _RETURN_HOME_HARD_TIMEOUT_S:
        return MissionState.LANDING

    # Tüm ajanlar zaten indiyse görev fiilen bitti (kısa yol).
    if ctx.all_agents_landed():
        return MissionState.LANDING

    # Normal bitiş: sürü eve varıp formasyon oturunca in.
    if not restart_viable and ctx.event_formation_reached:
        return MissionState.LANDING

    return None


def _from_landing(ctx: MissionContext) -> MissionState | None:
    """LANDING: tüm ajanlar yere inene kadar izleniyor."""
    if ctx.all_agents_landed() or ctx.time_in_state() > _LANDING_TIMEOUT_S:
        return MissionState.MISSION_COMPLETE

    return None


def _from_paused(ctx: MissionContext) -> MissionState | None:
    """PAUSED durumundan gecisleri degerlendirir."""
    if ctx.pending_command == _CMD_RESUME:
        return ctx.pause_return_state
    return None


def _from_terminal(ctx: MissionContext) -> MissionState | None:
    """ABORTED / MISSION_COMPLETE: sürü YERDE ve güvendeyken IDLE'a döner."""
    on_ground = (
        ctx.all_agents_landed()
        or ctx.all_agents_in_state(_AGENT_STATE_IDLE)
    )
    if on_ground and ctx.time_in_state() > _TERMINAL_RESET_DWELL_S:
        return MissionState.IDLE
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
    MissionState.ABORTED: _from_terminal,
    MissionState.MISSION_COMPLETE: _from_terminal,
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
