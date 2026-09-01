# Copyright 2026 Yelpence
"""Semi-autonomous kontrol FSM gecis kurallari."""

from .mode_context import ModeContext
from .mode_states import ControlMode, ModeState

_PREFLIGHT_TIMEOUT_S = 3600.0
_TAKEOFF_TIMEOUT_S = 300.0
# Kalkisi BIZ suruyorsak (madde 25) 300 s cok uzun: tirmanis takilirsa suru
# bes dakika armli bekler. formasyon_sekans ayni isi 90 s ile sinirliyor
# (ucus_ayarlari.SEKANS_KALKIS_ZAMAN_ASIMI_S) — ayni sayi, ayni gerekce.
_KALKIS_ZAMAN_ASIMI_S = 90.0
_LANDING_TIMEOUT_S = 90.0
_RTL_TIMEOUT_S = 120.0

_TERMINAL_STATES = frozenset({
    ModeState.COMPLETED,
})


def evaluate_transitions(ctx: ModeContext) -> ModeState | None:
    """Bir sonraki ModeState'i ya da gecis yoksa None doner."""
    # 🔴 B19 — COMPLETED'in TEK cikisi burasi (30 Agustos 2026).
    #
    # Erken donus KORUNUYOR: asagidaki acil/RTL/inis kapilari COMPLETED'a
    # UYGULANMAZ. Sebep, EMERGENCY'nin cikisinin `all_agents_landed()`
    # olmasi — ajan FSM'i bizim akisimizda IDLE'da kaldigi icin o kosul
    # hic gerceklesmiyor ve suru EMERGENCY'de takilir kalirdi (yerde,
    # disarm, 1 Hz bosa 'land' basarak). Tek, denetlenebilir cikis:
    if ctx.state in _TERMINAL_STATES:
        return _from_completed(ctx)

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

    # 🔴 G2-K10 UCUNCU KAPI — gorev YKI'den baslatilmadiysa TAKEOFF'a
    # HIC GIRILMEZ. Gecis kapisi asil kilit degil (o, komutun uretildigi
    # yerde: mode_manager_node._kalkis_komutu_gonder); burasi bosuna durum
    # degistirip 90 s sonra EMERGENCY'ye dusmeyi onluyor. Reddin sebebi
    # dugumde loglanir — sessiz kalmasi 30 Agustos'ta bir kusuru gizledi.
    if (ctx.takeoff_requested
            and ctx.all_agents_healthy()
            and ctx.kalkis_yetkisi_var()):
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

    # 🔴 KALKISI BIZ SURUYORSAK OLCUT HEDEF IRTIFA (madde 25).
    #
    # Bu dal test_hazir_atla'nin ONUNDE olmak ZORUNDA. Bugun ucaklarda
    # /ws/mod_test takili; kalkis kapisi 2 m'de acilir acilmaz
    # `test_hazir_atla and kalkis_tamam` READY verirdi, _dispatch_hold()
    # centroid'i (kapinin acildigi 2 m) hedef gosteren bir tarif yayinlardi
    # ve TIRMANIS 2 m'DE DURURDU — hedef 8 m iken, hicbir hata gorunmeden.
    # Kalkis komutunu biz verdiysek bitisini de biz olceriz.
    if ctx.kalkis_komutu_verildi:
        if ctx.kalkis_irtifasina_ulasildi():
            return ModeState.READY
        if ctx.time_in_state() > _KALKIS_ZAMAN_ASIMI_S:
            return ModeState.EMERGENCY
        return None

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


def _from_completed(ctx: ModeContext) -> ModeState | None:
    """COMPLETED -> IDLE. B19: gorev basina UC HAKKIMIZ var.

    Eskiden COMPLETED gercekten terminaldi: inis bitince (ya da 90 sn
    LANDING zaman asiminda) mode_manager oraya girip KALIYORDU ve ikinci
    kalkis icin KONTEYNER YENIDEN BASLATMAK gerekiyordu. Saha gununde
    denemeler arasi bu yasanacakti.

    IKI KOSUL, ikisi de ZORUNLU:

    1. **SwD inis konumundan cikmis olacak** (`land_requested` dusmus).
       Pilot salteri asagida birakmissa suru COMPLETED'da bekler — bu
       kasitli: mandalin dusmesi "pilot artik inis istemiyor" demek ve
       bunu FIZIKSEL bir hareket olarak istiyoruz.
    2. **Butun ucaklar DISARM.** Havada bir ucak varken defteri
       temizlemek, ikinci kalkisi ucan bir ucagin ustune vermek olurdu.

    ⚠️ SwD'yi yukari almak AYNI ANDA bir kalkis kenari da uretir
    (swd_mandal: yukari = kalkis tek atisi). O istek bu gecisin
    `set_state`'inde TEMIZLENIR ve IDLE->PREFLIGHT'ta bir kez daha
    temizlenir; yani suru KENDILIGINDEN kalkmaz. Ikinci kalkis icin pilot
    SwD'yi bilerek asagi-yukari yapmak zorunda. Bu bir kolaylik kaybi
    degil, ISTENEN davranis.
    """
    if ctx.land_requested:
        return None
    if not ctx.all_agents_disarmed():
        return None
    return ModeState.IDLE


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
