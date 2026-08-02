# Copyright 2026 Yelpence
"""Kalkis oncesi guvenlik kontrol listesi."""

from .agent_context import AgentContext


def run_preflight_checks(
    ctx: AgentContext,
    battery_min_voltage: float = 13.60,
) -> tuple[bool, list[str]]:
    """Arming'e izin verilip verilmeyecegini kontrol eder."""
    if ctx.sitl_mode:
        return (True, [])

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

    is_low_battery = (
        ctx.battery_voltage_v > 0.0
        and ctx.battery_voltage_v < battery_min_voltage
    )
    if is_low_battery:
        failures.append(
            f'Batarya voltajı düşük: {ctx.battery_voltage_v:.1f}V'
            f' (min {battery_min_voltage}V)'
        )

    return (len(failures) == 0, failures)
