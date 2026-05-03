"""
agent_transitions.py

FSM'in (Sonlu Durum Makinesi) kalbi — hangi durumdan hangisine geçilecek?

Bunu bir trafik ışığı sistemi gibi düşün:
- Her state'in kendi geçiş kuralları var
- Koşullar sağlandığında bir sonraki state'e geçilir
- Koşullar sağlanmadıysa mevcut state korunur (None döner)

evaluate_transitions(ctx) her FSM tick'inde (saniyede 10 kez) çağrılır.
None dönerse → mevcut state korunur
AgentState döner → o state'e geç
"""

from .agent_context import AgentContext
from .agent_states import AgentState, FlightMode
from .preflight_checker import run_preflight_checks

# =============================================================================
# ZAMAN SABİTLERİ — State timeout eşikleri (saniye)
# Bu süre içinde geçiş olmazsa FAILSAFE'e düşülür
# =============================================================================
_ARMING_TIMEOUT_S = 15.0    # 15s içinde arm edilemezse → IDLE'a dön
_TAKEOFF_TIMEOUT_S = 30.0   # 30s içinde irtifaya ulaşamazsa → FAILSAFE
_PRECISION_LANDING_TIMEOUT_S = 60.0  # 60s içinde inemezse → FAILSAFE
_REJOIN_TIMEOUT_S = 60.0             # 60s içinde sürüye katılamazsa → FAILSAFE
# 120s içinde rejoin talebi gelmezse → FAILSAFE
_WAITING_REJOIN_TIMEOUT_S = 120.0

# =============================================================================
# FAILSAFE'DEN MUAF STATE'LER
# Bu state'lerde healthy=False olsa bile FAILSAFE tetiklenmez
# Çünkü drone zaten yerde veya güvende
# =============================================================================
_FAILSAFE_EXEMPT = frozenset({
    AgentState.UNKNOWN,         # Başlangıç, drone henüz aktif değil
    AgentState.IDLE,            # Yerde bekliyor, güvende
    AgentState.ARMING,          # Yerde, henüz kalkmadı
    AgentState.ARMED,           # Yerde, arm edildi ama uçmadı
    AgentState.WAITING_REJOIN,  # Yerde, disarm, rejoin bekliyor
    AgentState.LANDED,          # İndi, güvende
    AgentState.STANDBY,         # Pasif mod
    AgentState.FAILSAFE,        # Zaten failsafe'de, tekrar tetiklenmesin
})

# =============================================================================
# OFFBOARD KONTROLÜ YAPILACAK STATE'LER
# Bu state'lerde OFFBOARD modu kaybolursa → FAILSAFE
# ARMING ve ARMED henüz OFFBOARD'a geçmediği için dahil değil
# =============================================================================
_OFFBOARD_CHECK_STATES = frozenset({
    AgentState.TAKEOFF,            # Kalkıyor — OFFBOARD şart
    AgentState.IN_SWARM,           # Sürüde — OFFBOARD şart
    AgentState.EXECUTING_TASK,     # Görev yapıyor — OFFBOARD şart
    AgentState.DETACHED,           # Sürüden kopuk uçuyor — OFFBOARD şart
    AgentState.PRECISION_LANDING,  # Hassas iniş — OFFBOARD şart
    AgentState.REJOINING,          # Sürüye katılıyor — OFFBOARD şart
    AgentState.RETURN_HOME,        # Eve dönüyor — OFFBOARD şart
    AgentState.LANDING,            # İniyor — OFFBOARD şart
})


def evaluate_transitions(ctx: AgentContext) -> AgentState | None:
    """
    Mevcut duruma göre geçilmesi gereken sonraki state'i döner.

    Bu fonksiyon her tick'te çağrılır ve şu sırayla çalışır:
    1. Kontrol durdurulmuş mu? (pilot override veya safety hold)
    2. Global öncelik: sağlık kaybı → FAILSAFE
    3. Global öncelik: OFFBOARD kaybı → FAILSAFE
    4. State'e özel geçiş kuralları

    Args:
        ctx: Drone'un anlık durum bilgisi.

    Returns:
        Geçilecek AgentState veya geçiş yoksa None.
    """
    # Pilot joystick'e dokunmuş veya safety hold aktif → otonom geçiş yapma
    # Pilot müdahale ederken sistem kendiliginden state değiştirmemeli
    if ctx.autonomous_control_paused or ctx.hold_active:
        return None

    # GLOBAL ÖNCELİK 1: Havadayken sağlık kaybı → hemen FAILSAFE
    # _FAILSAFE_EXEMPT state'leri yerde/güvende olduğu için muaf
    if ctx.state not in _FAILSAFE_EXEMPT and not ctx.healthy:
        return AgentState.FAILSAFE

    # GLOBAL ÖNCELİK 2: Uçuş state'lerinde OFFBOARD kaybı → FAILSAFE
    # OFFBOARD olmadan dış bilgisayar (biz) drone'u kontrol edemeyiz
    if ctx.state in _OFFBOARD_CHECK_STATES and not ctx.offboard_active:
        return AgentState.FAILSAFE

    # Her state için kendi geçiş fonksiyonu var
    # dict ile her state'i doğru handler'a yönlendir
    handlers = {
        AgentState.UNKNOWN: _from_unknown,
        AgentState.IDLE: _from_idle,
        AgentState.ARMING: _from_arming,
        AgentState.ARMED: _from_armed,
        AgentState.TAKEOFF: _from_takeoff,
        AgentState.IN_SWARM: _from_in_swarm,
        AgentState.EXECUTING_TASK: _from_executing_task,
        AgentState.DETACHED: _from_detached,
        AgentState.PRECISION_LANDING: _from_precision_landing,
        AgentState.WAITING_REJOIN: _from_waiting_rejoin,
        AgentState.REJOINING: _from_rejoining,
        AgentState.RETURN_HOME: _from_return_home,
        AgentState.LANDING: _from_landing,
        AgentState.LANDED: _from_landed,
        AgentState.FAILSAFE: _from_failsafe,
        AgentState.STANDBY: _from_standby,
    }
    # Bu state'in handler'ını bul
    handler = handlers.get(ctx.state)
    # Handler varsa çalıştır
    next_state = handler(ctx) if handler else None

    # ŞARTNAME KURAL 13: Home set değilken RTL yapılamaz
    # Home konumu kaydedilmemişse drone nereye döneceğini bilemez
    # RTL yerine acil iniş yap — bulunduğun yere in
    if next_state == AgentState.RETURN_HOME and not ctx.home_set:
        ctx.status_text = 'Home set değil — RTL yerine acil iniş'
        return AgentState.LANDING  # RTL yerine direkt iniş

    return next_state  # Normal geçiş


# =============================================================================
# STATE'E ÖZEL GEÇİŞ FONKSİYONLARI
# Her fonksiyon: koşul sağlandıysa → hedef state, sağlanmadıysa → None
# =============================================================================

def _from_unknown(ctx: AgentContext) -> AgentState | None:
    """
    UNKNOWN → IDLE: Sistem ilk başladığında her zaman IDLE'a geç.

    UNKNOWN sadece başlangıç anında olur.
    İlk tick'te hemen IDLE'a geçilir, hiçbir koşul aranmaz.
    """
    return AgentState.IDLE  # Her zaman geç, koşul yok


def _from_idle(ctx: AgentContext) -> AgentState | None:
    """
    IDLE → ARMING: Arming talebi varsa ve tüm preflight kontrolleri geçiyorsa.

    pending_state: EVENT_MISSION_STARTED event'i gelince ARMING yapılır.
    Preflight geçmezse (GPS yok, batarya düşük vs.) IDLE'da kalınır.
    """
    if ctx.pending_state == AgentState.ARMING:
        # Preflight kontrol listesini çalıştır
        passed, _ = run_preflight_checks(ctx)
        if passed:
            return AgentState.ARMING  # Tüm kontroller geçti, arm etmeye başla
    return None  # Talep yok veya preflight başarısız


def _from_arming(ctx: AgentContext) -> AgentState | None:
    """
    ARMING → ARMED: PX4 arm onayı verdi.
    ARMING → IDLE: Sağlık kaybı veya timeout — arm edilemedi, geri dön.

    Arm işlemi PX4'ün onaylaması gereken bir süreç.
    15 saniye içinde onay gelmezse bir sorun var demek.
    """
    if ctx.armed:
        return AgentState.ARMED  # PX4 arm onayı verdi, motorlar çalışıyor

    if not ctx.healthy:
        return AgentState.IDLE   # Sağlık kaybı → güvenli moda geç

    if ctx.time_in_state() > _ARMING_TIMEOUT_S:
        return AgentState.IDLE   # 15s içinde arm edilemedi → geri dön

    return None  # Henüz arm olmadı, beklemeye devam


def _from_armed(ctx: AgentContext) -> AgentState | None:
    """
    ARMED → TAKEOFF: Görev başlatma sinyali geldi ve OFFBOARD aktif.
    ARMED → IDLE: Disarm oldu veya sağlık kaybı.

    Drone arm edilmiş ama henüz kalkmadı.
    İki şart birden sağlanmalı: hem görev başlatma sinyali hem OFFBOARD.
    """
    if not ctx.armed or not ctx.healthy:
        return AgentState.IDLE  # Disarm veya sağlık kaybı → geri dön

    # Görev başlatma sinyali geldi VE OFFBOARD modu aktif → kalkışa geç
    if ctx.mission_start_sequence_active and ctx.offboard_active:
        return AgentState.TAKEOFF

    return None  # Henüz hazır değil


def _from_takeoff(ctx: AgentContext) -> AgentState | None:
    """
    TAKEOFF → IN_SWARM: Hedef irtifaya ulaşıldı ve drone stabil.
    TAKEOFF → FAILSAFE: 30 saniyede irtifaya ulaşılamadı.

    IN_SWARM'a geçmek için 5 koşul birden sağlanmalı:
    1. Hedef irtifaya ulaşıldı (10m civarı)
    2. İrtifa stabil (sallanmıyor)
    3. Duruş stabil (roll/pitch küçük)
    4. Dikey hız küçük (sakinleşti)
    5. Origin senkronize (tüm dronelerle aynı koordinat sistemi)
    """
    if (ctx.target_altitude_reached    # Hedef yüksekliğe ulaşıldı
            and ctx.altitude_stable    # İrtifa sabitlendi
            and ctx.attitude_stable    # Roll/pitch sabit
            and ctx.vertical_speed_ok  # Dikey hız yeterince küçük
            and ctx.origin_synced):    # Swarm koordinat sistemi hazır
        return AgentState.IN_SWARM    # Tüm koşullar tamam → sürüye katıl

    if ctx.time_in_state() > _TAKEOFF_TIMEOUT_S:
        return AgentState.FAILSAFE    # 30s geçti, bir şeyler yanlış

    return None  # Henüz hazır değil, beklemeye devam


def _from_in_swarm(ctx: AgentContext) -> AgentState | None:
    """
    IN_SWARM: Sürüdeyken gelen taleplere göre geçiş.

    Swarm manager'dan gelen event'ler pending_state'i belirler:
    - Görev komutu → EXECUTING_TASK
    - Detach komutu → DETACHED (sürüden ayrıl)
    - RTL komutu → RETURN_HOME
    - İniş komutu → LANDING
    """
    if ctx.pending_state == AgentState.EXECUTING_TASK:
        return AgentState.EXECUTING_TASK  # Görev başlıyor

    if ctx.pending_state == AgentState.DETACHED:
        return AgentState.DETACHED    # Sürüden ayrıl, hassas inişe hazırlan

    if ctx.pending_state == AgentState.RETURN_HOME:
        return AgentState.RETURN_HOME     # Eve dön komutu geldi

    if ctx.pending_state == AgentState.LANDING:
        return AgentState.LANDING         # İniş komutu geldi

    return None  # Sürüde devam, komut yok


def _from_executing_task(ctx: AgentContext) -> AgentState | None:
    """
    EXECUTING_TASK → IN_SWARM: Görev tamamlandı, sürüye geri dön.
    EXECUTING_TASK → RETURN_HOME: Görev sırasında RTL komutu geldi.

    Görev yapılırken bile RTL komutu öncelikli.
    Görev tamamlanınca veya başarısız olunca IN_SWARM'a dön.
    """
    if ctx.pending_state == AgentState.RETURN_HOME:
        return AgentState.RETURN_HOME  # RTL — güvenlik öncelikli

    if ctx.pending_state == AgentState.IN_SWARM:
        return AgentState.IN_SWARM  # Görev tamamlandı → sürüye dön

    return None  # Görev devam ediyor


def _from_detached(ctx: AgentContext) -> AgentState | None:
    """
    DETACHED → PRECISION_LANDING: Sürüden ayrılınca hassas iniş başlar.

    Detach olunca yapılacak şey bellidir: hassas iniş.
    Başka bir seçenek yok, direkt geçiş yapılır.
    """
    return AgentState.PRECISION_LANDING  # Her zaman geç, koşul yok


def _from_precision_landing(ctx: AgentContext) -> AgentState | None:
    """
    PRECISION_LANDING → WAITING_REJOIN: Disarm oldu, iniş tamamlandı.
    PRECISION_LANDING → FAILSAFE: 60s içinde inemedi.

    Hassas iniş tamamlandığının kanıtı: disarm olmuş olması.
    Disarm = motorlar durdu = yere indi.
    """
    if not ctx.armed:
        return AgentState.WAITING_REJOIN  # İndi → sürüye katılmayı bekle

    if ctx.time_in_state() > _PRECISION_LANDING_TIMEOUT_S:
        return AgentState.FAILSAFE  # 60s içinde inemedi — sorun var

    return None  # İniş devam ediyor


def _from_waiting_rejoin(ctx: AgentContext) -> AgentState | None:
    """
    WAITING_REJOIN → REJOINING: Swarm manager yeniden katılma izni verdi.
    WAITING_REJOIN → FAILSAFE: 120s içinde izin gelmedi.

    Drone yerde bekliyor, batarya değişimi yapılıyor olabilir.
    Swarm manager uygun görünce EVENT_MEMBER_REJOIN_STARTED gönderir.
    """
    if ctx.pending_state == AgentState.REJOINING:
        return AgentState.REJOINING   # İzin geldi, sürüye katılmaya başla

    if ctx.time_in_state() > _WAITING_REJOIN_TIMEOUT_S:
        return AgentState.FAILSAFE    # 2 dakika geçti, bir sorun var

    return None  # Hâlâ bekliyoruz


def _from_rejoining(ctx: AgentContext) -> AgentState | None:
    """
    REJOINING → IN_SWARM: Sürüye başarıyla katıldı.
    REJOINING → FAILSAFE: 60s içinde katılamadı.

    Drone kalkıp sürünün formasyonuna giriyor.
    Swarm manager "katıldı" onayı verince IN_SWARM'a geçilir.
    """
    if ctx.pending_state == AgentState.IN_SWARM:
        return AgentState.IN_SWARM    # Swarm manager onayladı, sürüdeyiz

    if ctx.time_in_state() > _REJOIN_TIMEOUT_S:
        return AgentState.FAILSAFE    # 60s içinde katılamadı

    return None  # Katılmaya çalışıyoruz


def _from_return_home(ctx: AgentContext) -> AgentState | None:
    """
    RETURN_HOME → LANDING: PX4 RTL tamamlandı, otomatik iniş başlıyor.

    PX4 RTL süreci: eve uç → eve gelince otomatik iniş başlat (AUTO_LAND modu).
    AUTO_LAND moduna geçince biz de LANDING state'ine geçeriz.
    Ya da swarm manager direkt iniş komutu verebilir.
    """
    if ctx.flight_mode == FlightMode.AUTO_LAND:
        return AgentState.LANDING     # PX4 otomatik iniş moduna geçti

    if ctx.pending_state == AgentState.LANDING:
        return AgentState.LANDING     # Swarm manager iniş komutu verdi

    return None  # RTL devam ediyor


def _from_landing(ctx: AgentContext) -> AgentState | None:
    """
    LANDING → LANDED: Disarm oldu, iniş tamamlandı.

    İniş tamamlandığının kanıtı: disarm olmuş olması.
    PX4 yere değince otomatik disarm yapar.
    """
    if not ctx.armed:
        return AgentState.LANDED  # İndi ve disarm oldu → LANDED

    return None  # Hâlâ iniyor


def _from_landed(ctx: AgentContext) -> AgentState | None:
    """
    LANDED → IDLE: Sistem sıfırlanmaya hazır, yeni görev için hazırlan.
    LANDED → STANDBY: Drone pasif moda alınıyor.

    İnişten sonra iki seçenek:
    1. IDLE → yeniden görev için hazırlan
    2. STANDBY → bu drone'u devre dışı bırak
    """
    if ctx.pending_state == AgentState.STANDBY:
        return AgentState.STANDBY   # Pasif moda geç

    if ctx.pending_state == AgentState.IDLE:
        return AgentState.IDLE      # Yeniden hazırlan

    return None  # Komut bekleniyor


def _from_failsafe(ctx: AgentContext) -> AgentState | None:
    """
    FAILSAFE → RETURN_HOME: Sağlık geri geldi ve swarm manager RTL onayladı.
    FAILSAFE → LANDING: RTL mümkün değilse (home_set=False) acil iniş.

    FAILSAFE'den çıkış için:
    1. Drone sağlıklı olmalı (healthy=True)
    2. Swarm manager onay vermeli (pending_state=RETURN_HOME)
    Home set değilse RTL yerine acil iniş — guard halleder.
    """
    if ctx.healthy and ctx.pending_state == AgentState.RETURN_HOME:
        return AgentState.RETURN_HOME  # Sağlık geri geldi → eve dön

    if ctx.pending_state == AgentState.LANDING:
        return AgentState.LANDING      # RTL mümkün değil → bulunduğun yere in

    return None  # FAILSAFE'de kal, bekle


def _from_standby(ctx: AgentContext) -> AgentState | None:
    """
    STANDBY → ARMING: Arm için hazır ve preflight geçiyor.

    Standby modundaki drone göreve katılmak isteyince:
    1. wants_to_join=True olmalı (EVENT_AGENT_JOIN_REQUEST geldi)
    2. ready_to_arm=True olmalı (PX4 preflight kontrollerini geçti)
    3. Preflight kontrol listesi tekrar çalıştırılır
    """
    if ctx.wants_to_join and ctx.ready_to_arm:
        passed, _ = run_preflight_checks(ctx)  # Son bir kez daha kontrol et
        if passed:
            return AgentState.ARMING   # Her şey hazır → arm etmeye başla

    return None  # Henüz hazır değil veya katılmak istemiyor
