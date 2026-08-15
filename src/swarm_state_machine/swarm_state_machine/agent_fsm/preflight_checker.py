# Copyright 2026 Yelpence
"""Kalkis oncesi guvenlik kontrol listesi."""

from .agent_context import AgentContext


def run_preflight_checks(
    ctx: AgentContext,
    battery_min_voltage: float | None = None,
) -> tuple[bool, list[str]]:
    """Arming'e izin verilip verilmeyecegini kontrol eder."""
    failures: list[str] = []

    if not ctx.px4_link_ok:
        failures.append('PX4 bağlantısı yok')

    if ctx.kill_switch_active:
        failures.append('Kill switch aktif')

    if ctx.gps_fix_type < 3:
        failures.append(f'GPS fix yetersiz: {ctx.gps_fix_type} (min 3)')

    if not ctx.sitl_mode and not ctx.home_set:
        failures.append('Home konumu set edilmedi')

    if not ctx.sitl_mode and not ctx.origin_synced:
        failures.append('Swarm origin senkronize değil')

    # PX4 COM_ARM_WO_GPS=1 -> GPS'siz arm'a izin veriyor; otonom ucus icin
    # konum tahmini gecerliligini burada zorunlu tutuyoruz (flyaway onleme).
    if not ctx.sitl_mode and not (
        ctx.estimator_ok and ctx.xy_valid and ctx.z_valid
    ):
        failures.append('Konum tahmini (EKF2) hazır değil')

    # Esik: cagiran acikca vermediyse BAGLAMDAN gelir, gomulu sabitten degil.
    #
    # 15 Agustos 2026'da bulundu: burada varsayilan `13.60` GOMULUYDU ve uc
    # cagri yerinin (agent_fsm_node:325, agent_transitions:119 ve :404)
    # hicbiri deger gecmiyordu. Yani baslat.sh'in verdigi
    # `battery_critical_voltage_v:=0.0` buraya HIC ULASMIYORDU. Ucaklar
    # regulatorden beslendigi icin 3.1 V okuyor; `0 < 3.1 < 13.6` oldugundan
    # preflight her seferinde "Batarya voltaji dusuk" diyecek ve IDLE ->
    # ARMING gecisi FSM yolundan HIC olmayacakti.
    #
    # Neden bugune kadar patlamadi: YKI arm'i dogrudan px4_bridge'e yolluyor
    # (/api/guided/{id}/arm), FSM yolunu kullanmiyor. Suru akisinda tek
    # kalkis komutu FSM'den gececek ve tam burada duracakti.
    #
    # `<= 0 => izleme yok` guard'i agent_health_monitor.py:234 ve
    # AgentContext.healthy ile AYNI olmak zorunda. Ucu ayrisirsa ajan bir
    # yerde "ucusa uygun", baska yerde "degil" sayilir — 2 Agustos'ta
    # digerlerinde tam bu yasandi.
    esik = (
        ctx.battery_critical_voltage_v
        if battery_min_voltage is None
        else battery_min_voltage
    )
    batarya_izleniyor = esik > 0.0

    is_low_battery = (
        batarya_izleniyor
        and ctx.battery_voltage_v > 0.0
        and ctx.battery_voltage_v < esik
    )
    if is_low_battery:
        failures.append(
            f'Batarya voltajı düşük: {ctx.battery_voltage_v:.1f}V'
            f' (min {esik}V)'
        )

    return (len(failures) == 0, failures)
