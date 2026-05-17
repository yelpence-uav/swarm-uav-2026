"""Sürü seviyesi FSM geçiş kuralları — hangi durumdan hangisine geçilecek."""

from ..agent_fsm.agent_states import AgentState
from .swarm_context import SwarmContext
from .swarm_states import SwarmState

# FORMING'de minimum IN_SWARM ajan oranı
_FORMING_READY_RATIO = 0.8

# LANDING tamamlanma timeout (saniye)
_LANDING_TIMEOUT_S = 120.0
_RTL_TIMEOUT_S = 180.0

# MISSION_COMPLETE'te minimum kalma süresi (GCS'in görebilmesi için)
_MISSION_COMPLETE_HOLD_S = 5.0


def evaluate_transitions(ctx: SwarmContext) -> SwarmState | None:
    """Mevcut sürü durumuna göre geçilmesi gereken sonraki state'i döner.

    Args:
        ctx: Sürünün anlık durum bilgisi.

    Returns:
        Geçilecek SwarmState veya geçiş yoksa None.
    """
    # Global RTL/LAND komutları — her state'ten geçerli
    if ctx.pending_rtl and ctx.swarm_state not in (
        SwarmState.RTL,
        SwarmState.LANDING,
        SwarmState.MISSION_COMPLETE,
        SwarmState.FAILSAFE,
    ):
        ctx.pending_rtl = False
        return SwarmState.RTL

    if ctx.pending_land and ctx.swarm_state not in (
        SwarmState.LANDING,
        SwarmState.MISSION_COMPLETE,
    ):
        ctx.pending_land = False
        return SwarmState.LANDING

    handlers = {
        SwarmState.UNKNOWN: _from_unknown,
        SwarmState.IDLE: _from_idle,
        SwarmState.FORMING: _from_forming,
        SwarmState.NAVIGATING: _from_navigating,
        SwarmState.EXECUTING_TASK: _from_executing_task,
        SwarmState.ROTATING: _from_rotating,
        SwarmState.LANDING: _from_landing,
        SwarmState.RTL: _from_rtl,
        SwarmState.FAILSAFE: _from_failsafe,
        SwarmState.MISSION_COMPLETE: _from_mission_complete,
    }

    handler = handlers.get(ctx.swarm_state)
    return handler(ctx) if handler else None


def _from_unknown(ctx: SwarmContext) -> SwarmState | None:
    """İlk tick'te her zaman IDLE'a geçer.

    Args:
        ctx: Sürü durum bilgisi.

    Returns:
        Her zaman SwarmState.IDLE.
    """
    return SwarmState.IDLE


def _from_idle(ctx: SwarmContext) -> SwarmState | None:
    """IDLE → FORMING: Görev başladı ve ajanlar kalkışa geçti.

    Args:
        ctx: Sürü durum bilgisi.

    Returns:
        SwarmState.FORMING veya None.
    """
    if not ctx.mission_active:
        return None

    # En az bir ajan TAKEOFF veya IN_SWARM durumunda olmalı
    takeoff_count = ctx.count_agents_in_state(AgentState.TAKEOFF)
    in_swarm_count = ctx.count_agents_in_state(AgentState.IN_SWARM)

    if takeoff_count + in_swarm_count > 0:
        return SwarmState.FORMING

    return None


def _from_forming(ctx: SwarmContext) -> SwarmState | None:
    """FORMING → NAVIGATING: Formasyon oluştu.

    Args:
        ctx: Sürü durum bilgisi.

    Returns:
        Hedef SwarmState veya None.
    """
    if not ctx.mission_active:
        return SwarmState.IDLE

    # Yeterli sayıda ajan IN_SWARM state'inde VE formasyon stabil
    in_swarm = ctx.count_agents_in_state(AgentState.IN_SWARM)
    exec_task = ctx.count_agents_in_state(AgentState.EXECUTING_TASK)
    active_flyers = in_swarm + exec_task

    if ctx.active_agent_count > 0:
        ratio = active_flyers / ctx.active_agent_count
        if ratio >= _FORMING_READY_RATIO and ctx.formation_reached:
            return SwarmState.NAVIGATING

    return None


def _from_navigating(ctx: SwarmContext) -> SwarmState | None:
    """NAVIGATING → ROTATING / EXECUTING_TASK.

    Args:
        ctx: Sürü durum bilgisi.

    Returns:
        Hedef SwarmState veya None.
    """
    if not ctx.mission_active:
        return SwarmState.LANDING

    # Rotasyon aktif — INTERFACE_CONTRACT Kural 21
    if ctx.rotation_active:
        return SwarmState.ROTATING

    # Görev icrası başladıysa (QR, manevra, detach vb.)
    exec_count = ctx.count_agents_in_state(AgentState.EXECUTING_TASK)
    if exec_count > 0:
        return SwarmState.EXECUTING_TASK

    return None


def _from_rotating(ctx: SwarmContext) -> SwarmState | None:
    """ROTATING → NAVIGATING: Rotasyon tamamlandı.

    INTERFACE_CONTRACT Kural 21: EVENT_ROTATION_COMPLETED
    gelince NAVIGATING'e dön.

    Args:
        ctx: Sürü durum bilgisi.

    Returns:
        Hedef SwarmState veya None.
    """
    if not ctx.rotation_active:
        return SwarmState.NAVIGATING

    return None


def _from_executing_task(ctx: SwarmContext) -> SwarmState | None:
    """EXECUTING_TASK → NAVIGATING / FORMING.

    Args:
        ctx: Sürü durum bilgisi.

    Returns:
        Hedef SwarmState veya None.
    """
    if not ctx.mission_active:
        return SwarmState.LANDING

    # Tüm ajanlar görev bitti → NAVIGATING'e dön
    exec_count = ctx.count_agents_in_state(AgentState.EXECUTING_TASK)
    if exec_count == 0:
        in_swarm = ctx.count_agents_in_state(AgentState.IN_SWARM)
        if in_swarm > 0:
            return SwarmState.NAVIGATING
        else:
            return SwarmState.FORMING

    return None


def _from_landing(ctx: SwarmContext) -> SwarmState | None:
    """LANDING → MISSION_COMPLETE: Tüm ajanlar indi.

    Args:
        ctx: Sürü durum bilgisi.

    Returns:
        Hedef SwarmState veya None.
    """
    # Tüm aktif ajanlar LANDED state'inde mi?
    landed_states = {AgentState.LANDED, AgentState.IDLE}
    if ctx.all_agents_in_states(landed_states):
        return SwarmState.MISSION_COMPLETE

    # Timeout kontrolü
    if ctx.time_in_state() > _LANDING_TIMEOUT_S:
        ctx.status_text = (
            f'İniş timeout: {ctx.time_in_state():.0f}s'
        )
        return SwarmState.FAILSAFE

    return None


def _from_rtl(ctx: SwarmContext) -> SwarmState | None:
    """RTL → LANDING: Ajanlar eve döndü ve inişe geçiyor.

    Args:
        ctx: Sürü durum bilgisi.

    Returns:
        Hedef SwarmState veya None.
    """
    # Çoğunluk LANDING veya LANDED state'ine geçti mi?
    landing_count = ctx.count_agents_in_state(AgentState.LANDING)
    landed_count = ctx.count_agents_in_state(AgentState.LANDED)
    total_landing = landing_count + landed_count

    if ctx.active_agent_count > 0:
        ratio = total_landing / ctx.active_agent_count
        if ratio >= _FORMING_READY_RATIO:
            return SwarmState.LANDING

    # RTL timeout
    if ctx.time_in_state() > _RTL_TIMEOUT_S:
        ctx.status_text = (
            f'RTL timeout: {ctx.time_in_state():.0f}s'
        )
        return SwarmState.FAILSAFE

    return None


def _from_failsafe(ctx: SwarmContext) -> SwarmState | None:
    """FAILSAFE → RTL / LANDING.

    Args:
        ctx: Sürü durum bilgisi.

    Returns:
        Hedef SwarmState veya None.
    """
    # Sağlık düzeldi mi?
    if ctx.expected_agent_count > 0:
        healthy = ctx.count_healthy_agents()
        ratio = healthy / ctx.expected_agent_count
        if ratio >= ctx.min_healthy_ratio:
            ctx.emergency_active = False
            return SwarmState.RTL

    # Tüm ajanlar yerdeyse MISSION_COMPLETE
    landed_states = {AgentState.LANDED, AgentState.IDLE}
    if ctx.all_agents_in_states(landed_states):
        return SwarmState.MISSION_COMPLETE

    return None


def _from_mission_complete(ctx: SwarmContext) -> SwarmState | None:
    """MISSION_COMPLETE → IDLE: Yeni görev bekleniyor.

    Args:
        ctx: Sürü durum bilgisi.

    Returns:
        SwarmState.IDLE veya None.
    """
    # GCS'in bu state'i görebilmesi için minimum bekleme süresi
    if ctx.time_in_state() < _MISSION_COMPLETE_HOLD_S:
        return None

    # Görev sonu temizliği yapıldıysa IDLE'a dön
    if not ctx.mission_active:
        return SwarmState.IDLE

    return None
