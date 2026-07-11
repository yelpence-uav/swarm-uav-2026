"""mission_transitions.py — Görev FSM geçiş kuralları.

Tek giriş noktası: evaluate_transitions(ctx), ctx'i okur ve
bir sonraki MissionState'i ya da geçiş olmaması için None döner.

ROS2 import'u yoktur; ROS2 kurulumu olmadan birim test yapılabilir.
Kural: Bu modüldeki fonksiyonlar ctx'i okur ama yazmaz.
"""

import time

from .mission_context import MissionContext
from .mission_states import MissionState, MissionType, QrTaskStep

_CMD_START = 1
_CMD_ABORT = 2
_CMD_PAUSE = 3
_CMD_RESUME = 4
_CMD_RTL = 5
_CMD_LAND = 6

_PREFLIGHT_TIMEOUT_S = 60.0
_TAKEOFF_TIMEOUT_S = 90.0
_NAVIGATE_TIMEOUT_S = 120.0
_QR_TASK_TIMEOUT_S = 90.0
_ROTATE_TIMEOUT_S = 30.0
_RETURN_HOME_TIMEOUT_S = 120.0
_LANDING_TIMEOUT_S = 90.0

# Rota bilinemez (gidilecek QR'ın konumu tabloda yok) → RETURN_HOME'a geçmeden
# önce tanınan süre. Geç gelen konum tablosuna / QR yeniden okumaya şans tanır;
# NAVIGATE_TIMEOUT'u (120 s) beklemeden daha hızlı, kontrollü failsafe.
_ROUTE_UNKNOWN_GRACE_S = 30.0

_TERMINAL_STATES = frozenset({
    MissionState.MISSION_COMPLETE,
    MissionState.ABORTED,
})


def evaluate_transitions(ctx: MissionContext) -> MissionState | None:
    """Bir sonraki MissionState'i ya da geçiş için None döner.

    Önce genel komutları kontrol eder (terminal olmayan herhangi
    bir durumdan geçerli), ardından duruma özgü işleyiciye delege eder.

    Args:
        ctx (MissionContext): Mevcut FSM çalışma zamanı durumu.

    Returns:
        MissionState: Geçilecek hedef durum.
        None: Geçiş yok; FSM mevcut durumda kalır.
    """
    if ctx.pending_command == _CMD_ABORT:
        if ctx.state not in _TERMINAL_STATES:
            return MissionState.ABORTED

    if (ctx.pending_command in (_CMD_RTL, _CMD_LAND)
            and ctx.state not in _TERMINAL_STATES
            and ctx.state not in (
                MissionState.RETURN_HOME,
                MissionState.LANDING,
                MissionState.IDLE,
            )):
        return MissionState.RETURN_HOME

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
    """UNKNOWN -> ilk tick'te IDLE."""
    return MissionState.IDLE


def _from_idle(ctx: MissionContext) -> MissionState | None:
    """IDLE -> GCS'den START gelince PREFLIGHT."""
    if ctx.pending_command == _CMD_START:
        return MissionState.PREFLIGHT
    return None


def _from_preflight(ctx: MissionContext) -> MissionState | None:
    """PREFLIGHT: tüm ajanların hazırlık kontrollerini geçmesini bekler.

    Args:
        ctx (MissionContext): Mevcut FSM çalışma zamanı durumu.

    Returns:
        MissionState: Tüm kontroller geçilince SYNCHRONIZED_TAKEOFF.
        MissionState: Timeout'ta ABORTED.
        None: Hâlâ bekleniyor.
    """
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
    """SYNCHRONIZED_TAKEOFF: tüm ajanların IN_SWARM olmasını bekler.

    Args:
        ctx (MissionContext): Mevcut FSM çalışma zamanı durumu.

    Returns:
        MissionState: Hazır olunca ROTATE_TO_NEXT veya SEMI_AUTONOMOUS.
        MissionState: Timeout'ta ABORTED.
        None: Hâlâ bekleniyor.
    """
    if ctx.all_agents_in_swarm():
        if ctx.mission_type == MissionType.SEMI_AUTONOMOUS:
            return MissionState.SEMI_AUTONOMOUS
        # Şartname: navigate öncesi ilk QR'a doğru dön.
        return MissionState.ROTATE_TO_NEXT

    if ctx.time_in_state() > _TAKEOFF_TIMEOUT_S:
        return MissionState.ABORTED

    return None


def _from_navigate_to_qr(ctx: MissionContext) -> MissionState | None:
    """NAVIGATE_TO_QR: sürü QR noktasına doğru hareket ediyor.

    Args:
        ctx (MissionContext): Mevcut FSM çalışma zamanı durumu.

    Returns:
        MissionState: formation_control varışı bildirince EXECUTE_QR_TASK.
        MissionState: Timeout'ta RETURN_HOME.
        None: Hâlâ navigasyon devam ediyor.
    """
    if ctx.event_formation_reached:
        return MissionState.EXECUTE_QR_TASK

    # Failsafe: gidilecek QR'ın konumu tabloda yok (route_unknown). Şartname:
    # rota bilinemezse ev konumuna dön. Grace süresi, geç gelen konum tablosuna
    # veya QR'ın yeniden okunmasına şans tanır; dolunca NAVIGATE_TIMEOUT'u
    # beklemeden RETURN_HOME'a geçilir.
    if ctx.route_unknown and ctx.time_in_state() > _ROUTE_UNKNOWN_GRACE_S:
        return MissionState.RETURN_HOME

    if ctx.time_in_state() > _NAVIGATE_TIMEOUT_S:
        return MissionState.RETURN_HOME

    return None


def _from_execute_qr_task(ctx: MissionContext) -> MissionState | None:
    """EXECUTE_QR_TASK: QR alt-adımları sırayla çalışıyor.

    Args:
        ctx (MissionContext): Mevcut FSM çalışma zamanı durumu.

    Returns:
        MissionState: Adımlar bitince ya da hata durumunda sonraki durum.
        None: Görev hâlâ devam ediyor.
    """
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
    """WAIT_AT_QR: wait_deadline dolana kadar sabit irtifada bekler.

    Args:
        ctx (MissionContext): Mevcut FSM çalışma zamanı durumu.

    Returns:
        MissionState: Deadline dolunca ROTATE_TO_NEXT veya RETURN_HOME.
        None: Deadline henüz dolmadı.
    """
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
    """ROTATE_TO_NEXT: formasyon bir sonraki QR noktasına döndürülüyor.

    EVENT_ROTATION_COMPLETED beklenir ya da timeout'ta navigasyona geçilir
    (navigasyon başlık düzeltmesini zaten yapar).

    Args:
        ctx (MissionContext): Mevcut FSM çalışma zamanı durumu.

    Returns:
        MissionState: Rotasyon tamamlanınca veya timeout'ta NAVIGATE_TO_QR.
        None: Hâlâ dönülüyor.
    """
    if ctx.event_rotation_completed:
        return MissionState.NAVIGATE_TO_QR

    if ctx.time_in_state() > _ROTATE_TIMEOUT_S:
        return MissionState.NAVIGATE_TO_QR

    return None


def _from_semi_autonomous(ctx: MissionContext) -> MissionState | None:
    """SEMI_AUTONOMOUS: joystick güdümlü sürü modu (Görev 2).

    Çıkış yalnızca genel RTL/ABORT komutlarıyla yapılır.

    Args:
        ctx (MissionContext): Mevcut FSM çalışma zamanı durumu.

    Returns:
        None: Her zaman; çıkış global kurallarıyla yapılır.
    """
    return None


def _from_return_home(ctx: MissionContext) -> MissionState | None:
    """RETURN_HOME: sürü kalkış noktasına geri dönüyor.

    Args:
        ctx (MissionContext): Mevcut FSM çalışma zamanı durumu.

    Returns:
        MissionState: Ajanlar inişe geçince veya timeout'ta LANDING.
        None: Hâlâ geri dönülüyor.
    """
    if ctx.all_agents_landing() or ctx.all_agents_landed():
        return MissionState.LANDING

    if ctx.time_in_state() > _RETURN_HOME_TIMEOUT_S:
        return MissionState.LANDING

    return None


def _from_landing(ctx: MissionContext) -> MissionState | None:
    """LANDING: tüm ajanlar yere inene kadar izleniyor.

    Args:
        ctx (MissionContext): Mevcut FSM çalışma zamanı durumu.

    Returns:
        MissionState: Tüm ajanlar indi ya da timeout'ta MISSION_COMPLETE.
        None: Hâlâ iniş devam ediyor.
    """
    if ctx.all_agents_landed():
        return MissionState.MISSION_COMPLETE

    if ctx.time_in_state() > _LANDING_TIMEOUT_S:
        return MissionState.MISSION_COMPLETE

    return None


def _from_paused(ctx: MissionContext) -> MissionState | None:
    """PAUSED: GCS'den RESUME komutu bekleniyor.

    Args:
        ctx (MissionContext): Mevcut FSM çalışma zamanı durumu.

    Returns:
        MissionState: pause_return_state'te saklanan önceki durum.
        None: Hâlâ duraklatılmış.
    """
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
    """Mesajdaki (QRMissionData) ilk aktif QrTaskStep'i döner.

    Args:
        qr: QRMissionData mesaj örneği ya da None.

    Returns:
        QrTaskStep: Yarışma sırasına göre ilk aktif adım.
        QrTaskStep.DONE: Hiç aktif adım yoksa ya da qr None ise.
    """
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
    """Tamamlanan adımdan sonraki aktif adımı döner.

    Args:
        qr: QRMissionData mesaj örneği ya da None.
        current (QrTaskStep): Az önce tamamlanan adım.

    Returns:
        QrTaskStep: Yarışma sırasına göre sonraki aktif adım.
        QrTaskStep.DONE: Başka aktif adım kalmadıysa.
    """
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
