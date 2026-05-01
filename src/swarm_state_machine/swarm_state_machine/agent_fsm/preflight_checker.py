"""
preflight_checker.py
Arming öncesi tüm uçuş güvenliği koşullarını doğrular.

Kaynak: swarm_interfaces/msg/AgentStatus.msg — GCS Pre-flight Checklist
"""

from .agent_context import AgentContext


def run_preflight_checks(
    ctx: AgentContext,
    battery_min_voltage: float = 15.2,
) -> tuple[bool, list[str]]:
    """
    Arming'e izin verilip verilmeyeceğini kontrol eder.

    Args:
        ctx: Drone'un anlık durum bilgisi.
        battery_min_voltage: Minimum güvenli paket voltajı (V).

    Returns:
        (passed, failures): passed=True ise arming'e izin var.
        failures listesi başarısız kontrollerin açıklamalarını içerir.
    """
    failures: list[str] = []

    # --- BAĞLANTI ---
    if not ctx.px4_link_ok:
        failures.append("PX4 bağlantısı yok")
    if not ctx.sitl_mode and not ctx.gcs_link_ok:
        failures.append("GCS bağlantısı yok")
    if not ctx.sitl_mode and not ctx.rc_link_ok:
        failures.append("RC bağlantısı yok")
    if ctx.kill_switch_active:
        failures.append("Kill switch aktif")
    if ctx.failsafe_active:
        failures.append("Failsafe aktif")
    if ctx.rc_signal_failsafe_active:
        failures.append("RC sinyal kaybı failsafe'i aktif")

    # --- GPS ---
    if ctx.gps_fix_type < 3:
        failures.append(f"GPS fix yetersiz: {ctx.gps_fix_type} (min 3)")
    if ctx.gps_hdop >= 1.5:
        failures.append(f"GPS HDOP yüksek: {ctx.gps_hdop:.2f} (max 1.5)")
    if ctx.gps_satellites < 6:
        failures.append(
            f"Yetersiz uydu sayısı: {ctx.gps_satellites} (min 6)"
        )

    # --- HOME / ORIGIN ---
    if not ctx.home_set:
        failures.append("Home konumu set edilmedi")
    if not ctx.origin_synced:
        failures.append("Swarm origin senkronize değil")

    # --- BATARYA ---
    if ctx.battery_voltage_v < battery_min_voltage:
        failures.append(
            f"Batarya voltajı düşük: {ctx.battery_voltage_v:.1f}V"
            f" (min {battery_min_voltage}V)"
        )

    # --- SENSÖR SAĞLIĞI ---
    if not ctx.imu_healthy:
        failures.append("IMU sağlıksız")
    if not ctx.mag_healthy:
        failures.append("Manyetometre sağlıksız")
    if not ctx.baro_healthy:
        failures.append("Barometre sağlıksız")

    # --- EKF2 / ESTIMATOR ---
    if not ctx.estimator_ok:
        failures.append("EKF2 estimator sağlıksız")
    if not ctx.xy_valid:
        failures.append("Yatay pozisyon tahmini geçersiz")
    if not ctx.z_valid:
        failures.append("Dikey pozisyon tahmini geçersiz")
    if not ctx.v_xy_valid:
        failures.append("Yatay hız tahmini geçersiz")

    return (len(failures) == 0, failures)
