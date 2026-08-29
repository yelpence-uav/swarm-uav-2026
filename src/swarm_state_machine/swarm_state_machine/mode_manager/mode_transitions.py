# Copyright 2026 Yelpence
"""Semi-autonomous kontrol FSM gecis kurallari."""

from .mode_context import ModeContext
from .mode_states import ControlMode, ModeState

_PREFLIGHT_TIMEOUT_S = 3600.0
_TAKEOFF_TIMEOUT_S = 300.0
_LANDING_TIMEOUT_S = 90.0
_RTL_TIMEOUT_S = 120.0

_TERMINAL_STATES = frozenset({
    ModeState.COMPLETED,
})


def evaluate_transitions(ctx: ModeContext) -> ModeState | None:
    """Bir sonraki ModeState'i ya da gecis yoksa None doner."""
    if ctx.state in _TERMINAL_STATES:
        return None

    if ctx.emergency_stop_requested and ctx.state != ModeState.EMERGENCY:
        return ModeState.EMERGENCY

    if ctx.pending_abort and ctx.state != ModeState.EMERGENCY:
        return ModeState.EMERGENCY

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


def _from_idle(ctx: ModeContext) -> ModeState | None:
    """IDLE durumundan gecisleri degerlendirir."""
    # B3: sahada mission_fsm KAPALI oldugu icin mission_state hic 8 olmuyor
    # ve FSM IDLE'da takili kaliyordu. test_hazir_atla bu kapiyi atlatir.
    # Tam Gorev 2 akisi (kumandadan kalkis + mission_fsm) ADIM 6'nin isi.
    if ctx.is_mission_semi_autonomous() or ctx.test_hazir_atla:
        return ModeState.PREFLIGHT
    return None


def _from_preflight(ctx: ModeContext) -> ModeState | None:
    """PREFLIGHT durumundan gecisleri degerlendirir."""
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
    """TAKEOFF durumundan gecisleri degerlendirir."""
    # B3: ajanlar sahada ARMED'da kaliyor, IN_SWARM'a hic gecmiyor.
    # test_hazir_atla'da olcut KALKIS KAPISI olur (B15) — yani "gercekten
    # havada mi", varsayimsal bir FSM durumu degil. Kapi kapaliyken READY'ye
    # gecmek, yerde tarif yayinlamak demek olurdu.
    if ctx.all_agents_in_swarm():
        return ModeState.READY

    if ctx.test_hazir_atla and ctx.kalkis_tamam:
        return ModeState.READY

    if ctx.time_in_state() > _TAKEOFF_TIMEOUT_S:
        return ModeState.EMERGENCY

    return None


def _from_ready(ctx: ModeContext) -> ModeState | None:
    """READY durumundan gecisleri degerlendirir."""
    if not ctx.command_active:
        return None

    if ctx.control_mode == ControlMode.SWARM_MOVEMENT:
        return ModeState.MOVEMENT
    if ctx.control_mode == ControlMode.MANEUVER:
        return ModeState.MANEUVER

    return None


def _from_movement(ctx: ModeContext) -> ModeState | None:
    """MOVEMENT durumundan gecisleri degerlendirir."""
    if not ctx.command_active:
        return ModeState.HOLD

    if ctx.control_mode == ControlMode.MANEUVER:
        return ModeState.MANEUVER

    return None


def _from_maneuver(ctx: ModeContext) -> ModeState | None:
    """MANEUVER durumundan gecisleri degerlendirir."""
    if not ctx.command_active:
        return ModeState.HOLD

    if ctx.control_mode == ControlMode.SWARM_MOVEMENT:
        return ModeState.MOVEMENT

    return None


def _from_hold(ctx: ModeContext) -> ModeState | None:
    """HOLD durumundan gecisleri degerlendirir.

    G2-K6 (operator, 30 Agustos 2026) — OTOMATIK INIS KALDIRILDI.
    Eskiden komut akisi 5 sn kesilince kendiliginden LANDING'e geciliyordu.
    Mesh sarsintisi 5 saniyeyi rahat buluyor ve bu, GOREV ORTASINDA
    istenmeyen bir inis demekti. Artik komut kesilince suru HOLD'da bekler;
    inis kararini pilot ya da hakem verir.

    🔴 KABUL EDILEN BEDEL: kumanda kalici olarak kaybedilirse suru SURESIZ
    asili kalir. Kacinma calismaya devam eder ama PIL IZLEME UC YERDE DE
    KAPALI (BAT1_SOURCE disabled, BATARYA_KRITIK_V=0.0) — yazilim tarafinda
    hicbir otomatik koruma YOK. Sureyi pilotlar tutar; cikis yolu
    kill-switch pilotlaridir. Ayrinti: docs/gorev2.md G2-K6.
    """
    if not ctx.command_active:
        return None

    if ctx.control_mode == ControlMode.SWARM_MOVEMENT:
        return ModeState.MOVEMENT
    if ctx.control_mode == ControlMode.MANEUVER:
        return ModeState.MANEUVER

    return None


def _from_landing(ctx: ModeContext) -> ModeState | None:
    """LANDING durumundan gecisleri degerlendirir."""
    if ctx.all_agents_landed():
        return ModeState.COMPLETED

    if ctx.time_in_state() > _LANDING_TIMEOUT_S:
        return ModeState.COMPLETED

    return None


def _from_rtl(ctx: ModeContext) -> ModeState | None:
    """RTL durumundan gecisleri degerlendirir."""
    if ctx.all_agents_landed():
        return ModeState.COMPLETED

    if ctx.time_in_state() > _RTL_TIMEOUT_S:
        return ModeState.LANDING

    return None


def _from_emergency(ctx: ModeContext) -> ModeState | None:
    """EMERGENCY durumundan gecisleri degerlendirir."""
    if ctx.all_agents_landed():
        return ModeState.COMPLETED

    return None


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
