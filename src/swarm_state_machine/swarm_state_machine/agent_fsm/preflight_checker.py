# Copyright 2026 Yelpence
"""Kalkis oncesi guvenlik kontrol listesi."""

from .agent_context import AgentContext


def run_preflight_checks(
    ctx: AgentContext,
    battery_min_voltage: float = 15.2,
) -> tuple[bool, list[str]]:
    """Arming'e izin verilip verilmeyecegini kontrol eder."""
    failures: list[str] = []

    if not ctx.px4_link_ok:
        failures.append('PX4 bağlantısı yok')

    if not ctx.sitl_mode and not ctx.gcs_link_ok:
        failures.append('GCS bağlantısı yok')

    if not ctx.sitl_mode and not ctx.rc_link_ok:
        failures.append('RC bağlantısı yok')

    if ctx.kill_switch_active:
        failures.append('Kill switch aktif')

    if ctx.failsafe_active and not ctx.sitl_mode:
        failures.append('Failsafe aktif')

    if ctx.rc_signal_failsafe_active and not ctx.sitl_mode:
        failures.append("RC sinyal kaybı failsafe'i aktif")

    if ctx.gps_fix_type < 3:
        failures.append(f'GPS fix yetersiz: {ctx.gps_fix_type} (min 3)')

    if ctx.gps_hdop >= 1.5:
        failures.append(f'GPS HDOP yüksek: {ctx.gps_hdop:.2f} (max 1.5)')

    if ctx.gps_satellites < 6:
        failures.append(
            f'Yetersiz uydu sayısı: {ctx.gps_satellites} (min 6)'
        )

    if not ctx.sitl_mode and not ctx.home_set:
        failures.append('Home konumu set edilmedi')

    if not ctx.sitl_mode and not ctx.origin_synced:
        failures.append('Swarm origin senkronize değil')

    is_low_battery = (
        ctx.battery_voltage_v > 0.0
        and ctx.battery_voltage_v < battery_min_voltage
    )
    if is_low_battery:
        failures.append(
            f'Batarya voltajı düşük: {ctx.battery_voltage_v:.1f}V'
            f' (min {battery_min_voltage}V)'
        )

    if not ctx.imu_healthy:
        failures.append('IMU sağlıksız')

    if not ctx.mag_healthy:
        failures.append('Manyetometre sağlıksız')

    if not ctx.baro_healthy:
        failures.append('Barometre sağlıksız')

    if not ctx.estimator_ok:
        failures.append('EKF2 estimator sağlıksız')

    if ctx.estimator_stable_ticks < 20:
        failures.append(
            f'EKF2 henüz kararlı değil: {ctx.estimator_stable_ticks}/20 tick'
        )

    if not ctx.xy_valid:
        failures.append('Yatay pozisyon tahmini geçersiz')

    if not ctx.z_valid:
        failures.append('Dikey pozisyon tahmini geçersiz')

    if not ctx.v_xy_valid:
        failures.append('Yatay hız tahmini geçersiz')

    return (len(failures) == 0, failures)
