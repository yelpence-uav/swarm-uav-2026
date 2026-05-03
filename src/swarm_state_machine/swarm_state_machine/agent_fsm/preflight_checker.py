"""
preflight_checker.py

Drone kalkıştan önce "Her şey hazır mı?" diye kontrol eden modül.
Tıpkı pilotların uçuş öncesi kontrol listesi gibi — sadece bizimki otomatik.

Bu kontroller ARMING öncesinde çalışır:
- IDLE → ARMING geçişinde
- STANDBY → ARMING geçişinde
- WAITING_REJOIN → REJOINING geçişinde (rejoin öncesi tekrar kontrol)

Tüm kontroller geçerse arming'e izin verilir.
Herhangi biri başarısız olursa failures listesine eklenir ve arming engellenir.

Kaynak: swarm_interfaces/msg/AgentStatus.msg — GCS Pre-flight Checklist
"""

from .agent_context import AgentContext  # Drone'un tüm durum verisi burada


def run_preflight_checks(
    ctx: AgentContext,
    # Minimum güvenli voltaj — 4S LiPo tam dolu ~16.8V
    battery_min_voltage: float = 15.2,
) -> tuple[bool, list[str]]:
    """
    Arming'e izin verilip verilmeyeceğini kontrol eder.

    Her kontrol başarısız olursa failures listesine Türkçe açıklama eklenir.
    Tüm kontroller geçerse passed=True döner ve drone arm edilebilir.

    Args:
        ctx: Drone'un anlık durum bilgisi.
        battery_min_voltage: Kalkış için minimum güvenli voltaj (V).
                             Varsayılan 15.2V — 4S LiPo %80 doluluğu.

    Returns:
        (passed, failures):
            passed=True  → Tüm kontroller geçti, arming'e izin var
            passed=False → En az bir kontrol başarısız, failures listesine bak
            failures     → Başarısız kontrollerin açıklamaları
    """
    failures: list[str] = []  # Başarısız kontroller buraya eklenir

    # =================================================================
    # 1. BAĞLANTI KONTROLLERİ
    # Drone kalkıştan önce tüm sistemlerle iletişimde olmalı
    # =================================================================

    # PX4 uçuş kontrolcüsüyle bağlantı — en temel gereksinim
    # Bu olmadan drone'a hiçbir komut veremeyiz
    if not ctx.px4_link_ok:
        failures.append("PX4 bağlantısı yok")

    # Yer kontrol istasyonu bağlantısı — SITL'de (simülasyonda) gerek yok
    # Gerçek yarışmada GCS olmadan kalkış yapılamaz
    if not ctx.sitl_mode and not ctx.gcs_link_ok:
        failures.append("GCS bağlantısı yok")

    # RC uzaktan kumanda bağlantısı — SITL'de gerek yok
    # Gerçek yarışmada pilot her zaman manuel müdahale edebilmeli
    if not ctx.sitl_mode and not ctx.rc_link_ok:
        failures.append("RC bağlantısı yok")

    # Kill switch kontrolü — basılıyken kesinlikle kalkış yapılmaz
    # Kill switch güvenlik için var: basılıysa motorlar çalışmaz
    if ctx.kill_switch_active:
        failures.append("Kill switch aktif")

    # PX4'ün kendi failsafe'i aktifse kalkış yapma
    # Failsafe aktifken PX4 zaten arm etmez, biz de ekstradan kontrol ediyoruz
    if ctx.failsafe_active:
        failures.append("Failsafe aktif")

    # RC sinyal kaybı failsafe'i — kumanda sinyali kaybolmuş
    if ctx.rc_signal_failsafe_active:
        failures.append("RC sinyal kaybı failsafe'i aktif")

    # =================================================================
    # 2. GPS KALİTE KONTROLLERİ
    # GPS olmadan drone nerede olduğunu bilemez, formasyon yapamaz
    # =================================================================

    # GPS fix türü en az 3 (3D fix) olmalı
    # 0=sinyal yok, 1=tahmin, 2=2D(yükseklik yok), 3=3D(yeterli), 4+=daha iyi
    if ctx.gps_fix_type < 3:
        failures.append(f"GPS fix yetersiz: {ctx.gps_fix_type} (min 3)")

    # HDOP (Horizontal Dilution of Precision) — ne kadar küçükse o kadar iyi
    # 1.5'in altı iyi, üstü yatay konumda hata payı çok büyük demek
    if ctx.gps_hdop >= 1.5:
        failures.append(f"GPS HDOP yüksek: {ctx.gps_hdop:.2f} (max 1.5)")

    # Uydu sayısı — ne kadar çok uydu görünürse konum o kadar doğru
    # 6'nın altında güvenilir 3D konum hesaplanamaz
    if ctx.gps_satellites < 6:
        failures.append(
            f"Yetersiz uydu sayısı: {ctx.gps_satellites} (min 6)"
        )

    # =================================================================
    # 3. HOME KONUMU ve ORIGIN SENKRONU
    # RTL için home konumu şart, formasyon için origin senkronu şart
    # =================================================================

    # Home konumu kaydedilmemiş — RTL yapılamaz, nereye döneceğini bilmez
    # Home konumu ilk arm anında GPS'ten otomatik kaydedilir
    if not ctx.home_set:
        failures.append("Home konumu set edilmedi")

    # Swarm origin senkronize değil — tüm droneler aynı referans noktasını
    # kullanmazsa formasyon koordinatları birbirine uymaz
    if not ctx.origin_synced:
        failures.append("Swarm origin senkronize değil")

    # =================================================================
    # 4. BATARYA KONTROLLERİ
    # Düşük bataryayla kalkış yapılırsa görev sırasında batarya bitebilir
    # =================================================================

    # Batarya voltajı minimum kalkış voltajının altındaysa kalkma
    # 15.2V = 4S LiPo'nun yaklaşık %80 doluluğu — kalkış için yeterli minimum
    if ctx.battery_voltage_v < battery_min_voltage:
        failures.append(
            f"Batarya voltajı düşük: {ctx.battery_voltage_v:.1f}V"
            f" (min {battery_min_voltage}V)"
        )

    # =================================================================
    # 5. SENSÖR SAĞLIK KONTROLLERİ
    # Bu 3 sensör olmadan drone uçamaz
    # =================================================================

    # IMU (İnertial Measurement Unit) — ivmeölçer + jiroskop
    # Drone'un hangi yöne hareket ettiğini ve nasıl döndüğünü ölçer
    # IMU olmadan stabilizasyon yapılamaz
    if not ctx.imu_healthy:
        failures.append("IMU sağlıksız")

    # Manyetometre (elektronik pusula) — hangi yöne baktığını ölçer
    # GPS ile birlikte çalışır, yön tayininde kritik
    if not ctx.mag_healthy:
        failures.append("Manyetometre sağlıksız")

    # Barometre — hava basıncından irtifa ölçer
    # GPS sinyali kaybolursa irtifayı barometre tutar
    if not ctx.baro_healthy:
        failures.append("Barometre sağlıksız")

    # =================================================================
    # 6. EKF2 ESTIMATOR KONTROLLERİ
    # EKF2 = Extended Kalman Filter — tüm sensörleri birleştirerek
    # en doğru konum ve hız tahminini üretir
    # Bu olmadan drone güvenli uçamaz
    # =================================================================

    # EKF2 genel durumu — tilt (eğim) ve yaw (dönüş) hizalanmış mı?
    if not ctx.estimator_ok:
        failures.append("EKF2 estimator sağlıksız")

    # Yatay konum tahmini geçerli mi? (x, y koordinatları)
    # Geçerli değilse drone nerede olduğunu bilmiyor demek
    if not ctx.xy_valid:
        failures.append("Yatay pozisyon tahmini geçersiz")

    # Dikey konum tahmini geçerli mi? (z koordinatı, yükseklik)
    if not ctx.z_valid:
        failures.append("Dikey pozisyon tahmini geçersiz")

    # Yatay hız tahmini geçerli mi? (vx, vy)
    # Hız tahmini olmadan stabil hover yapılamaz
    if not ctx.v_xy_valid:
        failures.append("Yatay hız tahmini geçersiz")

    # =================================================================
    # SONUÇ
    # failures listesi boşsa tüm kontroller geçti demek
    # =================================================================
    return (len(failures) == 0, failures)
    # Örnek başarılı dönüş: (True, [])
    # Örnek başarısız dönüş: (False, ["GPS fix yetersiz: 2 (min 3)", "IMU
    # sağlıksız"])
