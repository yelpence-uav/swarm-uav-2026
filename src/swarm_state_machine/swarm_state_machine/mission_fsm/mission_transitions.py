"""mission_transitions.py — Mission FSM gecis kurallari.

Tek giris noktasi evaluate_transitions(ctx):
  ctx'i okur, gecilecek MissionState doner ya da None doner.

Bu dosyada ROS2 yoktur; birim testleri kolayca yazilir.
KURAL: Bu dosyadaki fonksiyonlar ctx'e YAZAMAZ.
"""

import time

from .mission_context import MissionContext
from .mission_states import MissionState, MissionType, QrTaskStep


# TriggerMission.srv komut sabitleri
_CMD_START = 1
_CMD_ABORT = 2
_CMD_PAUSE = 3
_CMD_RESUME = 4
_CMD_RTL = 5
_CMD_LAND = 6

# Timeout sabitleri (saniye)
_PREFLIGHT_TIMEOUT_S = 60.0
_TAKEOFF_TIMEOUT_S = 90.0
_NAVIGATE_TIMEOUT_S = 120.0
_QR_TASK_TIMEOUT_S = 90.0
_ROTATE_TIMEOUT_S = 30.0
_RETURN_HOME_TIMEOUT_S = 120.0
_LANDING_TIMEOUT_S = 90.0

# Bu state'lerde ABORT veya RTL komutu islenmez.
_TERMINAL_STATES = frozenset({
    MissionState.MISSION_COMPLETE,
    MissionState.ABORTED,
})


# =============================================================================
# ANA GECIS FONKSIYONU
# =============================================================================

def evaluate_transitions(ctx: MissionContext) -> MissionState | None:
    """
    Mevcut duruma bakarak bir sonraki state'i doner.

    Once GLOBAL KOMUTLARI kontrol eder (her state'ten gecerli):
      ABORT -> hemen ABORTED
      RTL   -> hemen RETURN_HOME
      PAUSE -> hemen PAUSED

    Sonra STATE'E OZGU HANDLER'I cagirır.

    Args:
        ctx: Mission FSM'nin anlık durum bilgisi.

    Returns:
        Gecilecek MissionState; gecis yoksa None.
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

    if (ctx.pending_command == _CMD_PAUSE
            and ctx.state not in _TERMINAL_STATES
            and ctx.state not in (
                MissionState.IDLE,
                MissionState.PAUSED,
                MissionState.RETURN_HOME,
                MissionState.LANDING,
            )):
        return MissionState.PAUSED

    handlers = {
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
    handler = handlers.get(ctx.state)
    return handler(ctx) if handler else None


# =============================================================================
# STATE HANDLER FONKSIYONLARI
# =============================================================================

def _from_unknown(ctx: MissionContext) -> MissionState | None:
    """
    UNKNOWN -> IDLE: node baslar baslamaz ilk tick'te.

    Hicbir kosul kontrol edilmeden direkt IDLE'a gecilir.
    """
    return MissionState.IDLE


def _from_idle(ctx: MissionContext) -> MissionState | None:
    """
    IDLE -> PREFLIGHT: GCS'ten COMMAND_START gelince.

    START gelmezse None doner ve IDLE'da kalir.
    """
    if ctx.pending_command == _CMD_START:
        return MissionState.PREFLIGHT
    return None


def _from_preflight(ctx: MissionContext) -> MissionState | None:
    """
    PREFLIGHT: tum ajanlarin hazirlik kontrolu.

    Kontrol sirasi:
      1. Tum ajanlardan mesaj geldi mi? (all_agents_seen)
      2. GPS, origin, home kontrolleri (sitl_mode=True ise atlanir)
      3. Tum ajanlar healthy mi?
         -> Hepsi OK: SYNCHRONIZED_TAKEOFF
         -> Timeout: ABORTED
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
    """
    SYNCHRONIZED_TAKEOFF: tum ajanlar IN_SWARM'a ulasinca bir sonraki asama.

    Gorev tipine gore:
      DYNAMIC_SWARM(1)   -> NAVIGATE_TO_QR
      SEMI_AUTONOMOUS(2) -> SEMI_AUTONOMOUS

    QR koordinatlari yaris oncesi paylasılır; suru oraya varinca icerik okunur.
    current_qr beklenmez; beklenmesi DEADLOCK olusturur.

    Timeout (90s) -> ABORTED
    """
    if ctx.all_agents_in_swarm():
        if ctx.mission_type == MissionType.SEMI_AUTONOMOUS:
            return MissionState.SEMI_AUTONOMOUS
        return MissionState.NAVIGATE_TO_QR

    if ctx.time_in_state() > _TAKEOFF_TIMEOUT_S:
        return MissionState.ABORTED

    return None


def _from_navigate_to_qr(ctx: MissionContext) -> MissionState | None:
    """
    NAVIGATE_TO_QR: suru QR noktasina gidiyor.

    formation_control hedefe varinca EVENT_FORMATION_REACHED yayinlar.
    _on_event() bu eventi alinca ctx.event_formation_reached=True yapar.

    Timeout (120s) -> RETURN_HOME
    """
    if ctx.event_formation_reached:
        return MissionState.EXECUTE_QR_TASK

    if ctx.time_in_state() > _NAVIGATE_TIMEOUT_S:
        return MissionState.RETURN_HOME

    return None


def _from_execute_qr_task(ctx: MissionContext) -> MissionState | None:
    """
    EXECUTE_QR_TASK: QR alt gorevleri sirasyla calisiyor.

    Alt adim sirasi (sartname 5.1.2):
      FORMATION -> MANEUVER -> ALTITUDE -> DETACH -> DONE

    Sonraki state karari:
      current_qr=None       -> RETURN_HOME (QR kayboldu)
      action_success=False  -> RETURN_HOME (gorev basarisiz)
      DONE + complete_mission -> RETURN_HOME
      DONE + wait_s > 0      -> WAIT_AT_QR
      DONE + next_qr > 0     -> ROTATE_TO_NEXT
      DONE diger             -> RETURN_HOME

    Timeout (90s) -> RETURN_HOME
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
    """
    WAIT_AT_QR: QR'in wait_s suresi kadar bekleniyor.

    _on_state_entry(WAIT_AT_QR) su hesabi yapar:
      ctx.wait_deadline = time.monotonic() + qr.wait_s

    Sure dolunca:
      next_qr > 0 ve complete_mission=False -> ROTATE_TO_NEXT
      Aksi halde -> RETURN_HOME
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
    """
    ROTATE_TO_NEXT: formasyon bir sonraki QR yonune dondurüluyor.

    formation_control rotasyonu tamamlayinca EVENT_ROTATION_COMPLETED yayinlar.

    Timeout (30s): yanit gelmese de NAVIGATE_TO_QR'a devam edilir;
    navigate asamasi zaten dogru konuma goturur.
    """
    if ctx.event_rotation_completed:
        return MissionState.NAVIGATE_TO_QR

    if ctx.time_in_state() > _ROTATE_TIMEOUT_S:
        return MissionState.NAVIGATE_TO_QR

    return None


def _from_semi_autonomous(ctx: MissionContext) -> MissionState | None:
    """
    SEMI_AUTONOMOUS (Gorev 2): GCS joystick kontrol modu.

    Cikis evaluate_transitions() global handler'indan gelir (RTL/ABORT).
    Bu fonksiyonda ayrica kontrol gerekmez.
    """
    return None


def _from_return_home(ctx: MissionContext) -> MissionState | None:
    """
    RETURN_HOME: ajanlar RTL modunda eve doniyor.

    Drone'lar LANDING(12) ya da LANDED(13) state'ine gecinceye kadar beklenir.
    Timeout (120s) -> LANDING; kalan drone'lari izlemeye devam etmek daha guvenli.
    """
    if ctx.all_agents_landing() or ctx.all_agents_landed():
        return MissionState.LANDING

    if ctx.time_in_state() > _RETURN_HOME_TIMEOUT_S:
        return MissionState.LANDING

    return None


def _from_landing(ctx: MissionContext) -> MissionState | None:
    """
    LANDING: tum ajanlarin inisi izleniyor.

    Normal: tum drone'lar LANDED(13) -> MISSION_COMPLETE
    Timeout (90s): bir kismi cevap vermiyorsa yine de MISSION_COMPLETE sayilir.
    """
    if ctx.all_agents_landed():
        return MissionState.MISSION_COMPLETE

    if ctx.time_in_state() > _LANDING_TIMEOUT_S:
        return MissionState.MISSION_COMPLETE

    return None


def _from_paused(ctx: MissionContext) -> MissionState | None:
    """
    PAUSED: GCS PAUSE komutuyla gorev durduruldu.

    GCS RESUME gonderince pause_return_state'e doner.
    pause_return_state kaydedilir; sabit NAVIGATE_TO_QR kullanmak
    EXECUTE_QR_TASK sirasinda durdurulunca QR gorevini kaybettirir.
    """
    if ctx.pending_command == _CMD_RESUME:
        return ctx.pause_return_state
    return None


# =============================================================================
# QR ADIM YARDIMCI FONKSIYONLARI
# =============================================================================

def find_first_qr_step(qr) -> QrTaskStep:
    """
    QR mesajindaki ilk aktif adimi doner.

    Sartname sirasina gore ilk aktif bayragi bulur.
    Tum bayraklar False ise DONE doner.

    Args:
        qr: QRMissionData mesaji (None olabilir).

    Returns:
        Ilk aktif QrTaskStep; hicbiri aktif degilse DONE.
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
    """
    Tamamlanan adimdan sonra gelen ilk aktif adimi doner.

    Sartname sirasi: FORMATION -> MANEUVER -> ALTITUDE -> DETACH

    Args:
        qr: QRMissionData mesaji.
        current: Su an tamamlanan QrTaskStep.

    Returns:
        Siradaki aktif QrTaskStep; yoksa DONE.
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
