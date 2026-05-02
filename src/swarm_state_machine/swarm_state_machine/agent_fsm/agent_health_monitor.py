"""
agent_health_monitor.py

Drone uçarken sürekli "Her şey yolunda mı?" diye kontrol eden modül.
Tıpkı bir pilotun sürekli göstergelere bakması gibi — sadece bizimki otomatik.

Her FSM tick'inde (saniyede 10 kez) agent_fsm_node.py tarafından çağrılır.
ROS topic yayınlamaz — sadece sonucu node'a döndürür, node karar verir.

Kontrol sırası önemli: kritik hatalar önce kontrol edilir, erken dönülür.
"""

import statistics           # İstatistik hesapları için (varyans, ortalama)
from collections import deque   # Sabit boyutlu kuyruk — eski veriyi otomatik siler
from dataclasses import dataclass  # Sonuç veri yapısı için

from swarm_interfaces.msg import SystemEvent  # Event tipleri için (EVENT_PX4_LINK_LOST vs.)

from .agent_context import AgentContext        # Drone'un tüm verisi burada
from .agent_states import AgentRole, AgentState  # Durum ve rol sabitleri

# =============================================================================
# ZAMAN SABİTLERİ — Timeout eşikleri (saniye)
# Roadmap bölüm 6.5 — İleride YAML parametresine taşınmalı
# =============================================================================
_TAKEOFF_TIMEOUT_S = 30.0       # 30 saniyede hedef irtifaya ulaşamazsa → FAILSAFE
_LANDING_TIMEOUT_S = 60.0       # 60 saniyede inemezse → FAILSAFE
_RETURN_HOME_TIMEOUT_S = 120.0  # 120 saniyede eve dönemezse → safety_hold (bekle)

# =============================================================================
# STABİLİTE EŞİKLERİ
# Bu değerlerin altında/üstünde kalırsa drone stabil sayılır
# =============================================================================
_ALT_STABLE_VAR = 0.05    # m²  — irtifa varyansı bu kadar küçükse "stabil"
_ATT_STABLE_VAR = 4.0     # deg² — roll/pitch varyansı bu kadar küçükse "stabil"
_VEL_Z_OK_THR = 0.5       # m/s — dikey hız bu kadar küçükse "yeterince yavaş"
_ALT_REACH_THR = 0.5      # m   — hedef irtifaya 0.5m yaklaşınca "ulaştı" sayılır
_OSCILLATION_VAR = 9.0    # deg² — bu kadar sallanıyorsa "osilasyon" uyarısı
_UNSTABLE_ATT_VAR = 25.0  # deg² — bu kadar sallanıyorsa "tehlikeli kararsız"
_UNSTABLE_VEL_THR = 2.0   # m/s — dikey hız bu kadarı geçerse "tehlikeli"

# =============================================================================
# BATARYA EŞİKLERİ
# Kritik eşik AgentContext'ten gelir (YAML parametresi)
# Düşük uyarı: kritik eşik + 1V — "Batarya azalıyor, dikkat et"
# =============================================================================
_BATT_LOW_OFFSET_V = 1.0  # Kritik voltajın 1V üstünde "düşük batarya" uyarısı ver

# =============================================================================
# MAKSİMUM İRTİFA
# Yarışma kuralı: droneler bu yüksekliği geçemez
# İleride YAML'dan okunmalı
# =============================================================================
_MAX_ALTITUDE_M = 30.0  # Maksimum 30 metre — üstüne çıkarsa safety_hold

# =============================================================================
# HAVADA OLAN STATE'LER
# Bu state'lerde drone havadadır — sağlık kontrolleri kritik önem taşır
# ARMING ve ARMED dahil değil çünkü drone henüz kalkmadı
# =============================================================================
_AIRBORNE = frozenset({
    AgentState.TAKEOFF,            # Kalkıyor
    AgentState.IN_SWARM,           # Sürüde uçuyor
    AgentState.EXECUTING_TASK,     # Görev yapıyor
    AgentState.DETACHED,           # Sürüden kopuk uçuyor
    AgentState.PRECISION_LANDING,  # Hassas iniş yapıyor
    AgentState.REJOINING,          # Sürüye katılmak için uçuyor
    AgentState.RETURN_HOME,        # Eve dönüyor
    AgentState.LANDING,            # İniyor
})


@dataclass
class HealthCheckResult:
    """
    check() fonksiyonunun döndürdüğü sonuç.

    Node bu sonuca bakarak ne yapacağına karar verir:
    - critical_fault=True → hemen FAILSAFE'e geç, acil event yayınla
    - safety_hold=True   → dur, bekle, hold_active=True yap
    - warning=True       → sadece log at, state değişmez
    - Hepsi False        → her şey yolunda, devam et

    Attributes:
        critical_fault: True ise node FAILSAFE geçişi uygular.
        safety_hold: True ise node hold_active'i aktif eder.
        warning: Sadece log/status_text; state değişmez.
        event_type: Yayınlanacak SystemEvent.event_type değeri.
        reason: status_text ve log için açıklama.
    """
    critical_fault: bool = False                    # Kritik hata: hemen FAILSAFE
    safety_hold: bool = False                       # Güvenlik beklemesi: dur ve bekle
    warning: bool = False                           # Uyarı: sadece log, state değişmez
    event_type: int = SystemEvent.EVENT_UNKNOWN     # Hangi event yayınlanacak?
    reason: str = ''                                # Neden bu karar verildi?


# =============================================================================
# STABİLİTE PENCERESİ
# Son 2 saniyelik veriyi tutar (10 Hz × 2 saniye = 20 örnek)
# Her drone için ayrı bir pencere tutulur
# =============================================================================

class _StabilityWindow:
    """
    Son 2 saniyelik telemetri penceresi.

    deque(maxlen=20): 20'den fazla veri gelince en eskisi otomatik silinir.
    Bu sayede her zaman son 2 saniyenin verisi elimizde olur.
    """

    MAXLEN = 20  # 10 Hz × 2 saniye = 20 örnek

    def __init__(self) -> None:
        # Her biri 20 elemanlı kuyruk — dolunca eskiyi atar
        self.pos_z: deque[float] = deque(maxlen=self.MAXLEN)  # Dikey konum geçmişi
        self.vel_z: deque[float] = deque(maxlen=self.MAXLEN)  # Dikey hız geçmişi
        self.roll: deque[float] = deque(maxlen=self.MAXLEN)   # Roll açısı geçmişi
        self.pitch: deque[float] = deque(maxlen=self.MAXLEN)  # Pitch açısı geçmişi

    def update(self, ctx: AgentContext) -> None:
        """Her tick'te anlık sensör verisini kuyruğa ekle."""
        self.pos_z.append(ctx.pos_z)       # Dikey konumu ekle
        self.vel_z.append(ctx.vel_z)       # Dikey hızı ekle
        self.roll.append(ctx.roll_deg)     # Roll açısını ekle
        self.pitch.append(ctx.pitch_deg)   # Pitch açısını ekle

    def is_full(self) -> bool:
        """Pencere dolmadan istatistik hesaplanamaz — en az 20 veri lazım."""
        return len(self.pos_z) == self.MAXLEN


# Her drone'un kendi stabite penceresi: {agent_id: _StabilityWindow}
_windows: dict[int, _StabilityWindow] = {}


def _get_window(ctx: AgentContext) -> _StabilityWindow:
    """Bu drone'un stabite penceresini getir, yoksa yeni oluştur."""
    aid = ctx.agent_id
    if aid not in _windows:
        _windows[aid] = _StabilityWindow()  # İlk kez görülen drone için pencere aç
    return _windows[aid]


# =============================================================================
# ANA KONTROL FONKSİYONU — Her tick'te çağrılır
# =============================================================================

def check(ctx: AgentContext) -> HealthCheckResult:
    """
    Tüm uçuş sağlık kontrollerini sırayla çalıştırır.

    Kontrol sırası önemli: kritik olanlar önce kontrol edilir.
    Kritik hata veya safety_hold bulunduğunda erken döner (diğerlerine bakmaz).
    Bu sayede en önemli sorun tespit edilir ve gereksiz işlem yapılmaz.

    Args:
        ctx: Drone'un anlık durum bilgisi (bazı alanlar burada güncellenir).

    Returns:
        HealthCheckResult: node'un karar vereceği sonuç.
    """
    # 1. Kritik donanım hataları (PX4 bağlantısı, estimator, offboard, batarya)
    result = _check_critical_faults(ctx)
    if result.critical_fault:
        return result  # Kritik hata varsa diğer kontrollere gerek yok — hemen dön

    # 2. RC güvenlik kontrolleri (kill switch, RC bağlantısı, sinyal failsafe)
    result = _check_rc_safety(ctx)
    if result.critical_fault:
        return result  # Kill switch basıldıysa başka bir şeye bakma

    # 3. Jeofen (yasak bölge) ihlali — şartname kural 31: ihlalde RTL zorunlu
    result = _check_geofence(ctx)
    if result.safety_hold:
        return result

    # 4. State timeout kontrolleri (çok uzun süre aynı state'te kaldıysa)
    result = _check_state_timeout(ctx)
    if result.critical_fault or result.safety_hold:
        return result

    # 5. Uçuş stabilitesini hesapla ve ctx'i güncelle (sonuç döndürmez)
    _check_flight_stability(ctx)

    # 6. İrtifa limiti kontrolü (30m sınırı)
    result = _check_altitude_limits(ctx)
    if result.safety_hold:
        return result

    # 7. Role/state tutarlılığı — sadece uyarı, state değiştirmez
    _check_role_state_consistency(ctx)

    # Tüm kontrollerden geçti — her şey yolunda
    return HealthCheckResult()


# =============================================================================
# ALT KONTROL FONKSİYONLARI
# =============================================================================

def _check_critical_faults(ctx: AgentContext) -> HealthCheckResult:
    """
    En kritik donanım hatalarını kontrol eder.

    PX4 bağlantısı koptu mu? EKF2 bozuldu mu? OFFBOARD kayboldu mu? Batarya kritik mi?
    Bunların herhangi biri olunca drone havadaysa FAILSAFE kaçınılmaz.

    Args:
        ctx: Drone durum bilgisi.

    Returns:
        HealthCheckResult: critical_fault veya warning.
    """
    # PX4 ile bağlantı yok — drone'u hiç kontrol edemiyoruz, en kritik hata
    if not ctx.px4_link_ok:
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_PX4_LINK_LOST,
            reason='PX4 link koptu',
        )

    # Havadayken EKF2 bozuldu — drone nerede olduğunu bilmiyor, çok tehlikeli
    if ctx.state in _AIRBORNE and not ctx.estimator_ok:
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_AGENT_FAULT,
            reason='EKF2 estimator hatalı',
        )

    # Havadayken OFFBOARD modu kayboldu — dış bilgisayar kontrolü yok
    if ctx.state in _AIRBORNE and not ctx.offboard_active:
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_OFFBOARD_LOST,
            reason='OFFBOARD modu kayboldu',
        )

    # Batarya telemetrisi henüz gelmedi (ilk saniyeler) — kontrol etme
    if ctx.battery_voltage_v <= 0.0:
        return HealthCheckResult()  # Veri yok, atla

    # Batarya kritik eşiğin altında — acil inis şart!
    if ctx.battery_voltage_v < ctx.battery_critical_voltage_v:
        reason = (
            f'Kritik batarya: {ctx.battery_voltage_v:.1f}V '
            f'(esik {ctx.battery_critical_voltage_v:.1f}V)'
        )
        ctx.status_text = reason  # GCS'de göster
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_BATTERY_LOW,
            reason=reason,
        )

    # Batarya düşük uyarı eşiğinde (kritik + 1V) — henüz kritik değil, uyar
    batt_low_v = ctx.battery_critical_voltage_v + _BATT_LOW_OFFSET_V
    if ctx.battery_voltage_v < batt_low_v:
        reason = f'Batarya dusuk: {ctx.battery_voltage_v:.1f}V'
        ctx.status_text = reason
        return HealthCheckResult(
            warning=True,                               # Sadece uyarı, state değişmez
            event_type=SystemEvent.EVENT_BATTERY_LOW,
            reason=reason,
        )

    return HealthCheckResult()  # Her şey yolunda


def _check_rc_safety(ctx: AgentContext) -> HealthCheckResult:
    """
    RC (uzaktan kumanda) güvenlik kontrollerini yapar.

    Kill switch, RC bağlantısı ve RC sinyal failsafe kontrol edilir.
    SITL modunda RC kontrolü atlanır (simülasyonda RC yok).

    Args:
        ctx: Drone durum bilgisi.

    Returns:
        HealthCheckResult: critical_fault veya warning.
    """
    # Kill switch basıldı — motorlar anında durdurulmalı, en acil durum
    if ctx.kill_switch_active:
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_KILL_SWITCH_ACTIVATED,
            reason='Kill switch aktif',
        )

    # Gerçek donanımda RC bağlantısı koptu (SITL'de bu kontrol atlanır)
    if not ctx.sitl_mode and not ctx.rc_link_ok:
        reason = 'RC link koptu'
        ctx.status_text = reason
        if ctx.state in _AIRBORNE:
            # Havadayken RC koptu — kritik, FAILSAFE gerek
            return HealthCheckResult(
                critical_fault=True,
                event_type=SystemEvent.EVENT_RC_LINK_LOST,
                reason=f'{reason} (havada)',
            )
        # Yerdeyken RC koptu — sadece uyarı, kalkış yapmasın
        return HealthCheckResult(
            warning=True,
            event_type=SystemEvent.EVENT_RC_LINK_LOST,
            reason=reason,
        )

    # RC sinyal kaybı failsafe aktif ve drone havada — tehlikeli
    if ctx.rc_signal_failsafe_active and ctx.state in _AIRBORNE:
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_AGENT_FAULT,
            reason='RC signal failsafe aktif (havada)',
        )

    return HealthCheckResult()  # RC güvenli


def _check_geofence(ctx: AgentContext) -> HealthCheckResult:
    """
    Jeofen (yasak bölge) ihlalini kontrol eder.

    Şartname kural 31: Jeofen ihlali tespit edilince drone RTL başlatmalı.
    Bu yüzden critical_fault=True dönülür — FAILSAFE üzerinden RTL tetiklenir.

    ctx.geofence_violated: px4_interface veya swarm node tarafından set edilir,
    EVENT_GEOFENCE_VIOLATION event'i ile agent_fsm_node set eder.

    Args:
        ctx: Drone durum bilgisi.

    Returns:
        HealthCheckResult: critical_fault veya boş sonuç.
    """
    # Havadayken jeofen ihlali — RTL başlat (şartname zorunluluğu)
    if ctx.geofence_violated and ctx.state in _AIRBORNE:
        reason = 'Jeofen ihlali tespit edildi — RTL başlatılıyor'
        ctx.status_text = reason
        return HealthCheckResult(
            critical_fault=True,                              # FAILSAFE → RTL zinciri başlar
            event_type=SystemEvent.EVENT_GEOFENCE_VIOLATION,
            reason=reason,
        )
    return HealthCheckResult()  # İhlal yok veya havada değil


def _check_state_timeout(ctx: AgentContext) -> HealthCheckResult:
    """
    State timeout kontrolü — bir state'te çok uzun kalındı mı?

    Roadmap bölüm 6.5.
    TAKEOFF: 30s içinde irtifaya ulaşamazsa → FAILSAFE (motor sorunu olabilir)
    LANDING: 60s içinde inemezse → FAILSAFE (iniş sorunu)
    RETURN_HOME: 120s içinde dönemezse → safety_hold (bekle, tekrar dene)

    Args:
        ctx: Drone durum bilgisi.

    Returns:
        HealthCheckResult: critical_fault veya safety_hold.
    """
    elapsed = ctx.time_in_state()  # Bu state'te kaç saniye geçti?

    # TAKEOFF 30 saniyeyi geçti — motor veya rüzgar sorunu olabilir
    if (
        ctx.state == AgentState.TAKEOFF
        and elapsed > _TAKEOFF_TIMEOUT_S
    ):
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_AGENT_FAULT,
            reason=f'TAKEOFF timeout: {elapsed:.0f}s',
        )

    # LANDING 60 saniyeyi geçti — iniş taktiği çalışmıyor
    if (
        ctx.state == AgentState.LANDING
        and elapsed > _LANDING_TIMEOUT_S
    ):
        return HealthCheckResult(
            critical_fault=True,
            event_type=SystemEvent.EVENT_AGENT_FAULT,
            reason=f'LANDING timeout: {elapsed:.0f}s',
        )

    # RETURN_HOME 120 saniyeyi geçti — safety_hold: bekle, swarm manager müdahale etsin
    if (
        ctx.state == AgentState.RETURN_HOME
        and elapsed > _RETURN_HOME_TIMEOUT_S
    ):
        reason = f'RETURN_HOME timeout: {elapsed:.0f}s'
        ctx.status_text = reason
        return HealthCheckResult(
            safety_hold=True,                          # Kritik değil, bekle
            event_type=SystemEvent.EVENT_SAFETY_HOLD,
            reason=reason,
        )

    return HealthCheckResult()  # Timeout yok


def _check_flight_stability(ctx: AgentContext) -> None:
    """
    Son 2 saniyelik veriden stabite bayraklarını hesaplar.

    Bu fonksiyon ctx alanlarını günceller (sonuç döndürmez):
    - target_altitude_reached: Hedef irtifaya ulaşıldı mı?
    - altitude_stable: İrtifa sabit mi?
    - attitude_stable: Duruş sabit mi?
    - vertical_speed_ok: Dikey hız yeterince küçük mü?
    - oscillation_detected: Tehlikeli sallanma var mı?
    - unstable_flight: Tehlikeli kararsız uçuş var mı?

    Args:
        ctx: Drone durum bilgisi (in-place güncellenir).
    """
    win = _get_window(ctx)  # Bu drone'un stabite penceresini al
    win.update(ctx)          # Anlık veriyi kuyruğa ekle

    # Hedef irtifaya ulaşıldı mı?
    # NED koordinatında yukarı = negatif z, bu yüzden -target kullanılır
    # Örnek: target=10m → hedef pos_z <= -9.5 (0.5m tolerans)
    ctx.target_altitude_reached = (
        ctx.pos_z <= -(ctx.target_altitude_m - _ALT_REACH_THR)
    )

    # Pencere dolmadan istatistik hesaplanamaz — en az 20 veri lazım (2 saniye)
    if not win.is_full():
        return  # Yeni başladı, veri yetersiz

    # Dikey hız kontrolü: tüm 20 örnekte hız < 0.5 m/s ise "yeterince yavaş"
    ctx.vertical_speed_ok = all(
        abs(v) < _VEL_Z_OK_THR for v in win.vel_z
    )

    # İrtifa stabilitesi: son 2 saniyelik irtifa varyansı küçükse "stabil"
    pz_var = statistics.variance(win.pos_z)   # Varyans: ortalamadan ne kadar saptı?
    ctx.altitude_stable = pz_var < _ALT_STABLE_VAR  # 0.05 m²'den küçükse stabil

    # Attitude (duruş) stabilitesi: roll ve pitch varyanslarının büyüğüne bak
    r_var = statistics.variance(win.roll)    # Roll varyansı
    p_var = statistics.variance(win.pitch)   # Pitch varyansı
    att_var = max(r_var, p_var)              # En kötü durumu al
    ctx.attitude_stable = att_var < _ATT_STABLE_VAR  # 4 deg²'den küçükse stabil

    # Osilasyon tespiti: çok fazla sallanıyor mu?
    ctx.oscillation_detected = att_var > _OSCILLATION_VAR   # 9 deg²'den büyükse

    # Tehlikeli kararsız uçuş: çok sallanma VEYA çok hızlı dikey hareket
    max_vz = max(abs(v) for v in win.vel_z)  # Son 2 saniyedeki max dikey hız
    ctx.unstable_flight = (
        att_var > _UNSTABLE_ATT_VAR    # 25 deg²'den fazla sallanma
        or max_vz > _UNSTABLE_VEL_THR  # veya 2 m/s'den fazla dikey hız
    )


def _check_altitude_limits(ctx: AgentContext) -> HealthCheckResult:
    """
    Maksimum irtifa sınırını kontrol eder.

    Yarışma kuralı: 30m üstüne çıkamazlar.
    Aşılırsa safety_hold: drone olduğu yerde bekler, swarm manager müdahale eder.

    Args:
        ctx: Drone durum bilgisi.

    Returns:
        HealthCheckResult: safety_hold veya boş sonuç.
    """
    # Yerdeyken irtifa kontrolü anlamsız
    if ctx.state not in _AIRBORNE:
        return HealthCheckResult()

    altitude_m = -ctx.pos_z  # NED → pozitif yukarı: pos_z negatif olduğu için -1 çarpıyoruz
    if altitude_m > _MAX_ALTITUDE_M:
        reason = (
            f'Irtifa limiti asildi: {altitude_m:.1f}m '
            f'(max {_MAX_ALTITUDE_M:.0f}m)'
        )
        ctx.status_text = reason
        return HealthCheckResult(
            safety_hold=True,                                    # Dur, aşağı in
            event_type=SystemEvent.EVENT_ALTITUDE_LIMIT_EXCEEDED,
            reason=reason,
        )

    return HealthCheckResult()  # İrtifa normal


def _check_role_state_consistency(ctx: AgentContext) -> None:
    """
    Role ve state arasında mantıksal çelişki var mı kontrol eder.

    Roadmap bölüm 6.7.
    Çelişki varsa status_text güncellenir (log/GCS için), state değişmez.

    Örnek çelişki: STANDBY rolü ama IN_SWARM state'i — imkansız kombinasyon.

    Args:
        ctx: Drone durum bilgisi (status_text güncellenir).
    """
    # STANDBY rolü + IN_SWARM state: imkansız — standby sürüde olamaz
    if (
        ctx.role == AgentRole.STANDBY
        and ctx.state == AgentState.IN_SWARM
    ):
        ctx.status_text = (
            'Role/state tutarsizlik: STANDBY + IN_SWARM'
        )
    # IN_SWARM state'i ama ne LEADER ne FOLLOWER — kim bu drone?
    elif (
        ctx.state == AgentState.IN_SWARM
        and ctx.role not in (AgentRole.LEADER, AgentRole.FOLLOWER)
    ):
        ctx.status_text = (
            f'Role/state tutarsizlik: '
            f'IN_SWARM + {ctx.role.name}'
        )
