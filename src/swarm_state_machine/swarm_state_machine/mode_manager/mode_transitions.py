"""mode_transitions.py — Görev 2 yarı otonom kontrol FSM geçiş kuralları.

Tek giriş noktası: evaluate_transitions(ctx), ctx'i okur ve
bir sonraki ModeState'i ya da geçiş olmaması için None döner.

ROS2 import'u yoktur; ROS2 kurulumu olmadan birim test yapılabilir.
Kural: Bu modüldeki fonksiyonlar ctx'i okur ama yazmaz.
"""

from .mode_context import ModeContext
from .mode_states import ControlMode, ModeState

_PREFLIGHT_TIMEOUT_S = 60.0
_TAKEOFF_TIMEOUT_S = 90.0
_LANDING_TIMEOUT_S = 90.0
_RTL_TIMEOUT_S = 120.0

_TERMINAL_STATES = frozenset({
    ModeState.COMPLETED,
})


def evaluate_transitions(ctx: ModeContext) -> ModeState | None:
    """Bir sonraki ModeState'i ya da geçiş yoksa None döner.

    Önce genel güvenlik kurallarını kontrol eder, ardından duruma
    özgü işleyiciye delege eder.

    Args:
        ctx: Mevcut FSM çalışma zamanı durumu.

    Returns:
        ModeState: Geçilecek hedef durum.
        None: Geçiş yok; FSM mevcut durumda kalır.
    """
    if ctx.state in _TERMINAL_STATES:
        return None

    # ─── Genel güvenlik kuralları (her state'ten geçerli) ───

    if ctx.emergency_stop_requested and ctx.state != ModeState.EMERGENCY:
        return ModeState.EMERGENCY

    if ctx.pending_abort and ctx.state != ModeState.EMERGENCY:
        return ModeState.EMERGENCY

    # RTL komutu — IDLE, PREFLIGHT, LANDING, EMERGENCY, COMPLETED hariç
    if (ctx.rtl_requested
            and ctx.state not in (
                ModeState.IDLE,
                ModeState.PREFLIGHT,
                ModeState.LANDING,
                ModeState.RTL,
                ModeState.EMERGENCY,
                ModeState.COMPLETED,
            )):
        return ModeState.RTL

    # Land komutu — havadaki state'lerden geçerli
    if (ctx.land_requested
            and ctx.state not in (
                ModeState.IDLE,
                ModeState.PREFLIGHT,
                ModeState.LANDING,
                ModeState.EMERGENCY,
                ModeState.COMPLETED,
            )):
        return ModeState.LANDING

    handler = _HANDLERS.get(ctx.state)
    return handler(ctx) if handler else None


# ═════════════════════════════════════════════════════════════════════
# DURUMA ÖZGÜ İŞLEYİCİLER
# ═════════════════════════════════════════════════════════════════════

def _from_idle(ctx: ModeContext) -> ModeState | None:
    """IDLE → PREFLIGHT: mission_fsm SEMI_AUTONOMOUS'a geçti.

    Args:
        ctx: FSM çalışma zamanı durumu.

    Returns:
        ModeState.PREFLIGHT veya None.
    """
    if ctx.is_mission_semi_autonomous():
        return ModeState.PREFLIGHT
    return None


def _from_preflight(ctx: ModeContext) -> ModeState | None:
    """PREFLIGHT → TAKEOFF: Kumandadan takeoff komutu geldi ve
    tüm drone'lar sağlıklı.

    Args:
        ctx: FSM çalışma zamanı durumu.

    Returns:
        ModeState.TAKEOFF, EMERGENCY veya None.
    """
    if not ctx.all_agents_seen():
        if ctx.time_in_state() > _PREFLIGHT_TIMEOUT_S:
            return ModeState.EMERGENCY
        return None

    if ctx.takeoff_requested and ctx.all_agents_healthy():
        return ModeState.TAKEOFF

    if ctx.time_in_state() > _PREFLIGHT_TIMEOUT_S:
        return ModeState.EMERGENCY

    return None


def _from_takeoff(ctx: ModeContext) -> ModeState | None:
    """TAKEOFF → READY: Tüm drone'lar IN_SWARM oldu.

    Args:
        ctx: FSM çalışma zamanı durumu.

    Returns:
        ModeState.READY, EMERGENCY veya None.
    """
    if ctx.all_agents_in_swarm():
        return ModeState.READY

    if ctx.time_in_state() > _TAKEOFF_TIMEOUT_S:
        return ModeState.EMERGENCY

    return None


def _from_ready(ctx: ModeContext) -> ModeState | None:
    """READY → MOVEMENT/MANEUVER: İlk geçerli joystick komutu geldi.

    Args:
        ctx: FSM çalışma zamanı durumu.

    Returns:
        ModeState.MOVEMENT, MANEUVER veya None.
    """
    if not ctx.command_active:
        return None

    if ctx.control_mode == ControlMode.SWARM_MOVEMENT:
        return ModeState.MOVEMENT
    if ctx.control_mode == ControlMode.MANEUVER:
        return ModeState.MANEUVER

    return None


def _from_movement(ctx: ModeContext) -> ModeState | None:
    """MOVEMENT: Sürü Hareket Modu aktif.

    Deadman bırakılırsa HOLD'a geçer.
    Mod değişirse MANEUVER'e geçer.

    Args:
        ctx: FSM çalışma zamanı durumu.

    Returns:
        Hedef ModeState veya None.
    """
    if not ctx.command_active:
        return ModeState.HOLD

    if ctx.control_mode == ControlMode.MANEUVER:
        return ModeState.MANEUVER

    return None


def _from_maneuver(ctx: ModeContext) -> ModeState | None:
    """MANEUVER: Manevra Modu aktif.

    Deadman bırakılırsa HOLD'a geçer.
    Mod değişirse MOVEMENT'a geçer.

    Args:
        ctx: FSM çalışma zamanı durumu.

    Returns:
        Hedef ModeState veya None.
    """
    if not ctx.command_active:
        return ModeState.HOLD

    if ctx.control_mode == ControlMode.SWARM_MOVEMENT:
        return ModeState.MOVEMENT

    return None


def _from_hold(ctx: ModeContext) -> ModeState | None:
    """HOLD: Deadman bırakıldı, sürü yerinde duruyor.

    Deadman tekrar basılınca aktif moda döner.

    Args:
        ctx: FSM çalışma zamanı durumu.

    Returns:
        Hedef ModeState veya None.
    """
    if not ctx.command_active:
        return None

    if ctx.control_mode == ControlMode.SWARM_MOVEMENT:
        return ModeState.MOVEMENT
    if ctx.control_mode == ControlMode.MANEUVER:
        return ModeState.MANEUVER

    return None


def _from_landing(ctx: ModeContext) -> ModeState | None:
    """LANDING: Sürü iniyor.

    Args:
        ctx: FSM çalışma zamanı durumu.

    Returns:
        ModeState.COMPLETED, EMERGENCY veya None.
    """
    if ctx.all_agents_landed():
        return ModeState.COMPLETED

    if ctx.time_in_state() > _LANDING_TIMEOUT_S:
        return ModeState.COMPLETED

    return None


def _from_rtl(ctx: ModeContext) -> ModeState | None:
    """RTL: Eve dönüş.

    Args:
        ctx: FSM çalışma zamanı durumu.

    Returns:
        ModeState.LANDING, COMPLETED veya None.
    """
    if ctx.all_agents_landed():
        return ModeState.COMPLETED

    if ctx.time_in_state() > _RTL_TIMEOUT_S:
        return ModeState.LANDING

    return None


def _from_emergency(ctx: ModeContext) -> ModeState | None:
    """EMERGENCY: Acil durum.

    Tüm drone'lar indiyse COMPLETED'e geçer.

    Args:
        ctx: FSM çalışma zamanı durumu.

    Returns:
        ModeState.COMPLETED veya None.
    """
    if ctx.all_agents_landed():
        return ModeState.COMPLETED

    return None


# ═════════════════════════════════════════════════════════════════════
# İŞLEYİCİ HARİTASI
# ═════════════════════════════════════════════════════════════════════

_HANDLERS = {
    ModeState.IDLE: _from_idle,
    ModeState.PREFLIGHT: _from_preflight,
    ModeState.TAKEOFF: _from_takeoff,
    ModeState.READY: _from_ready,
    ModeState.MOVEMENT: _from_movement,
    ModeState.MANEUVER: _from_maneuver,
    ModeState.HOLD: _from_hold,
    ModeState.LANDING: _from_landing,
    ModeState.RTL: _from_rtl,
    ModeState.EMERGENCY: _from_emergency,
}
