"""mission_transitions.py — Mission FSM geçiş kuralları.

=============================================================================
BU DOSYA NE YAPAR?
=============================================================================
  "Şu anki duruma bakıp bir sonraki durumu söyle."
  Başka bir şey yapmaz. ROS2 yok, thread yok, publish yok.

  Tek giriş noktası: evaluate_transitions(ctx)
    → ctx'i okur
    → geçiş yapılacaksa hedef MissionState döner
    → geçiş yoksa None döner

  mission_fsm_node._tick() bu fonksiyonu çağırır:
    next_state = evaluate_transitions(ctx)
    if next_state:
        self._transition(next_state)

  Neden ayrı dosyada?
    → ROS2 import'u olmadığından birim testleri çok kolay yazılır.
    → "State geçiş mantığı" ile "ROS2 altyapısı" birbirinden ayrılır.
    → Saf Python → hızlı, test edilebilir, anlaşılır.

  KURAL: Bu dosyadaki fonksiyonlar ctx'e YAZAMAZ.
    Tek istisna: set_state() — o da _transition() içinden çağrılır, burada değil.
    (Önceden ctx.event_formation_reached=False yazılıyordu — yanlıştı, silindi.)
"""

import time   # _from_wait_at_qr'da time.monotonic() için

from .mission_context import MissionContext
from .mission_states import MissionState, MissionType, QrTaskStep


# =============================================================================
# TriggerMission.srv KOMUT SABITLERİ
# =============================================================================
# TriggerMission.srv import edilmeden kullanabilmek için burada tanımlıyoruz.
# GCS bu integer'ları gönderir; _handle_trigger() ctx.pending_command'a yazar.
_CMD_START = 1   # görevi başlat
_CMD_ABORT = 2   # görevi iptal et
_CMD_PAUSE = 3   # görevi duraklat
_CMD_RESUME = 4   # duraklatılan göreve devam et
_CMD_RTL = 5   # eve dön (Return To Launch)
_CMD_LAND = 6   # iniş yap


# =============================================================================
# TIMEOUT SABITLERİ (saniye)
# =============================================================================
# Her state için maksimum bekleme süresi.
# Bu süre geçerse ya ABORTED ya da RETURN_HOME'a gideriz.
_PREFLIGHT_TIMEOUT_S = 60.0   # 60s içinde tüm ajanlar hazır olmazsa iptal
_TAKEOFF_TIMEOUT_S = 90.0   # 90s içinde tüm ajanlar IN_SWARM olmazsa iptal
_NAVIGATE_TIMEOUT_S = 120.0  # 120s içinde QR'a ulaşamazsak eve dön
_QR_TASK_TIMEOUT_S = 90.0   # 90s içinde QR görevi bitmezse eve dön
_ROTATE_TIMEOUT_S = 30.0   # 30s içinde rotasyon tamamlanmazsa yine de devam et
# 120s içinde ajanlar LANDING'e geçemezse yine de LANDING'e al
_RETURN_HOME_TIMEOUT_S = 120.0
_LANDING_TIMEOUT_S = 90.0   # 90s içinde tüm ajanlar inmezse yine de "tamamlandı"


# Bu state'lerde ABORT veya RTL komutu işlenmez — görev zaten bitti.
_TERMINAL_STATES = frozenset({   # frozenset: değiştirilemez küme, 'in' kontrolü hızlı
    MissionState.MISSION_COMPLETE,
    MissionState.ABORTED,
})


# =============================================================================
# ANA GEÇİŞ FONKSİYONU
# =============================================================================

def evaluate_transitions(ctx: MissionContext) -> MissionState | None:
    """Mevcut duruma bakarak bir sonraki state'i döner.

    Önce GLOBAL KOMUTLARI kontrol eder (her state'ten geçerli):
      ABORT  → hemen ABORTED
      RTL    → hemen RETURN_HOME
      PAUSE  → hemen PAUSED

    Sonra STATE'E ÖZGÜ HANDLER'I çağırır:
      Her state'in kendi fonksiyonu var (_from_idle, _from_preflight, ...)
      O fonksiyon detaylı koşulları kontrol eder.

    Args:
        ctx: Mission FSM'nin anlık durum bilgisi.

    Returns:
        Geçilecek MissionState; geçiş yoksa None.
    """
    # ------------------------------------------------------------------
    # GLOBAL KOMUT KONTROLLERİ — her state'ten geçerli
    # ------------------------------------------------------------------

    # ABORT: terminal state'lerde değilsek → hemen ABORTED
    if ctx.pending_command == _CMD_ABORT:
        if ctx.state not in _TERMINAL_STATES:
            return MissionState.ABORTED

    # RTL veya LAND: terminal + zaten eve dönüş + iniş + idle state'lerinde değilsek
    # (zaten iniyor veya yerde oturuyorsa tekrar RTL tetiklemez)
    if (ctx.pending_command in (_CMD_RTL, _CMD_LAND)
            and ctx.state not in _TERMINAL_STATES
            and ctx.state not in (
                MissionState.RETURN_HOME,
                MissionState.LANDING,
                MissionState.IDLE,
            )):
        return MissionState.RETURN_HOME

    # PAUSE: terminal + zaten duraklatılmış + RTL/iniş state'lerinde değilsek
    if (ctx.pending_command == _CMD_PAUSE
            and ctx.state not in _TERMINAL_STATES
            and ctx.state not in (
                MissionState.IDLE,         # daha görev başlamadı, duraklatma anlamsız
                MissionState.PAUSED,       # zaten duraklatılmış
                MissionState.RETURN_HOME,  # eve dönüşü durduramayız
                MissionState.LANDING,      # inişi durduramayız
            )):
        return MissionState.PAUSED

    # ------------------------------------------------------------------
    # STATE'E ÖZGÜ HANDLER'LAR
    # ------------------------------------------------------------------
    # Sözlük: {state → fonksiyon}
    # handlers.get(ctx.state) → ilgili fonksiyonu al, yoksa None
    handlers = {
        MissionState.UNKNOWN: _from_unknown,  # ilk tick → hemen IDLE
        MissionState.IDLE: _from_idle,  # START bekle → PREFLIGHT
        # sağlık kontrolleri → SYNCHRONIZED_TAKEOFF
        MissionState.PREFLIGHT: _from_preflight,
        # tüm ajanlar IN_SWARM → NAVIGATE_TO_QR
        MissionState.SYNCHRONIZED_TAKEOFF: _from_synchronized_takeoff,
        # formation_reached → EXECUTE_QR_TASK
        MissionState.NAVIGATE_TO_QR: _from_navigate_to_qr,
        # DONE → WAIT_AT_QR / ROTATE_TO_NEXT / RETURN_HOME
        MissionState.EXECUTE_QR_TASK: _from_execute_qr_task,
        # deadline doldu → ROTATE_TO_NEXT / RETURN_HOME
        MissionState.WAIT_AT_QR: _from_wait_at_qr,
        # rotation_completed → NAVIGATE_TO_QR
        MissionState.ROTATE_TO_NEXT: _from_rotate_to_next,
        # joystick modu; çıkış global handler'dan
        MissionState.SEMI_AUTONOMOUS: _from_semi_autonomous,
        MissionState.RETURN_HOME: _from_return_home,  # ajanlar iniyor → LANDING
        MissionState.LANDING: _from_landing,  # hepsi indi → MISSION_COMPLETE
        MissionState.PAUSED: _from_paused,  # RESUME → pause_return_state'e dön
        # MISSION_COMPLETE ve ABORTED handler'ı yok → None döner → geçiş yok (terminal state)
    }
    handler = handlers.get(ctx.state)   # state'e karşılık gelen fonksiyon
    return handler(ctx) if handler else None   # fonksiyon varsa çağır


# =============================================================================
# STATE HANDLER FONKSİYONLARI
# =============================================================================
# Her fonksiyon: ctx'i okur, MissionState veya None döner.
# ctx'e YAZMAZ — bu kural testlerde doğrulanmıştır.

def _from_unknown(ctx: MissionContext) -> MissionState | None:
    """UNKNOWN → IDLE: node başlar başlamaz ilk tick'te.

    UNKNOWN sıradan bir hata durumu değil, başlangıç noktasıdır.
    Hiçbir koşul kontrol etmeden direkt IDLE'a geçeriz.
    """
    return MissionState.IDLE   # her zaman geçer, koşul yok


def _from_idle(ctx: MissionContext) -> MissionState | None:
    """IDLE → PREFLIGHT: GCS'ten COMMAND_START gelince.

    IDLE: drone'lar yerde, motor kapalı, görev başlamadı.
    GCS "start" butonuna basarsa pending_command = _CMD_START olur.
    Bu fonksiyon bunu görür ve PREFLIGHT'a geçirir.

    START gelmezse None → IDLE'da kalır.
    """
    if ctx.pending_command == _CMD_START:
        return MissionState.PREFLIGHT
    return None   # komut yok, bekle


def _from_preflight(ctx: MissionContext) -> MissionState | None:
    """PREFLIGHT: tüm ajanların hazırlık kontrolü.

    Kontrol sırası:
      1. Tüm ajanlardan mesaj geldi mi? (all_agents_seen)
         → Hayır: timeout'a kadar bekle; timeout → ABORTED
      2. GPS, origin, home kontrolleri geçti mi?
         → sitl_mode=True ise bu kontroller atlanır
      3. Tüm ajanlar healthy mi?
         → Hepsi OK: SYNCHRONIZED_TAKEOFF
         → 60s geçti ve hâlâ OK değil: ABORTED
    """
    # Önce tüm ajanlardan en az bir mesaj gelmiş mi?
    if not ctx.all_agents_seen:
        # Hiç mesaj gelmemiş ajan var, bekle
        if ctx.time_in_state() > _PREFLIGHT_TIMEOUT_S:
            return MissionState.ABORTED   # 60s geçti, ajan görünmüyor
        return None   # daha bekle

    # sitl_mode=True → GPS/origin/home kontrolleri atlanır (simülasyon)
    # sitl_mode=False → gerçek uçuş, her şeyin tamam olması şart
    gps_ok = ctx.sitl_mode or ctx.all_agents_gps_ok()
    origin_ok = ctx.sitl_mode or ctx.all_agents_origin_synced()
    home_ok = ctx.sitl_mode or ctx.all_agents_home_set()

    # Tüm kontroller geçtiyse kalkışa geç
    if ctx.all_agents_healthy() and gps_ok and origin_ok and home_ok:
        return MissionState.SYNCHRONIZED_TAKEOFF

    # Kontroller geçmedi ama süre doldu → iptal
    if ctx.time_in_state() > _PREFLIGHT_TIMEOUT_S:
        return MissionState.ABORTED

    return None   # kontroller geçmedi, daha bekle


def _from_synchronized_takeoff(ctx: MissionContext) -> MissionState | None:
    """SYNCHRONIZED_TAKEOFF: tüm ajanlar IN_SWARM'a ulaşınca bir sonraki aşama.

    EVENT_MISSION_STARTED yayınlandı; agent_fsm'ler arm+kalkış başlattı.
    Bekliyoruz: tüm drone'lar IN_SWARM(5) state'ine gelsin.

    Görev tipine göre farklı state:
      DYNAMIC_SWARM(1)  → hemen NAVIGATE_TO_QR
                          Şartname madde 11: QR koordinatları yarışma öncesi paylaşılır.
                          Sürü QR1'in konumunu ZATEN BİLİR (parametreden/config'den).
                          QR içeriğini (görev komutlarını) ancak ORAYA VARINCA okur.
                          current_qr kontrolü DEADLOCK yaratır:
                            → QR1'e gitmedikçe kamera okuyamaz
                            → Kamera okumadıkça QR1'e gitmez
                          Çözüm: IN_SWARM olunca hemen NAVIGATE_TO_QR.
      SEMI_AUTONOMOUS(2) → doğrudan SEMI_AUTONOMOUS
                           (QR gerekmez, joystick kontrol başlar)

    Timeout → ABORTED (90s içinde drone'lar IN_SWARM olmadı).
    """
    if ctx.all_agents_in_swarm():
        # Görev 2: joystick kontrolü → direkt SEMI_AUTONOMOUS
        if ctx.mission_type == MissionType.SEMI_AUTONOMOUS:
            return MissionState.SEMI_AUTONOMOUS

        # Görev 1: QR koordinatı biliniyor (yarışma öncesi paylaşıldı).
        # current_qr BEKLEME YOK — sürü QR1'e gidince kamera okuyacak.
        return MissionState.NAVIGATE_TO_QR

    # 90s geçti, hâlâ IN_SWARM olmadılar → iptal
    if ctx.time_in_state() > _TAKEOFF_TIMEOUT_S:
        return MissionState.ABORTED

    return None   # drone'lar kalkıyor, bekle


def _from_navigate_to_qr(ctx: MissionContext) -> MissionState | None:
    """NAVIGATE_TO_QR: sürü QR noktasına gidiyor.

    formation_control sürüyü QR koordinatına götürür.
    Hedefe varınca EVENT_FORMATION_REACHED yayınlar.
    _on_event() bu eventi alınca ctx.event_formation_reached=True yapar.
    Bunu gördüğümüzde EXECUTE_QR_TASK'a geçeriz.

    Timeout → RETURN_HOME (120s içinde hedefe ulaşamadık, güvenli dön).
    """
    if ctx.event_formation_reached:
        # Sürü QR noktasına vardı → görevi çalıştır
        return MissionState.EXECUTE_QR_TASK

    # 120s geçti, hâlâ ulaşamadık → eve dön
    if ctx.time_in_state() > _NAVIGATE_TIMEOUT_S:
        return MissionState.RETURN_HOME

    return None   # sürü yolda, bekle


def _from_execute_qr_task(ctx: MissionContext) -> MissionState | None:
    """EXECUTE_QR_TASK: QR alt görevleri sırayla çalışıyor.

    Alt adım sırası (şartname 5.1.2):
      FORMATION → MANEUVER → ALTITUDE → DETACH → DONE

    Adım ilerlemesi event-driven'dır:
      icra node'u işi bitince event yayınlar
      → _on_event() _advance_qr_step() çağırır
      → ctx.qr_task_step bir sonraki adıma geçer
      → DONE olunca bu fonksiyon tespit eder ve sonraki state'e geçer

    Bu fonksiyon yalnızca DONE ve hata hallerini yakalar.
    Adım ilerletme işi _on_event + _advance_qr_step'te.

    Sonraki state kararı:
      current_qr=None          → RETURN_HOME (QR kayboldu, güvenli dön)
      action_success=False      → RETURN_HOME (görev başarısız, güvenli dön)
      DONE + complete_mission   → RETURN_HOME (QR "görevi bitir" dedi)
      DONE + wait_s > 0         → WAIT_AT_QR  (QR'ın bekleme süresi var)
      DONE + next_qr > 0        → ROTATE_TO_NEXT (bir sonraki QR var)
      DONE + başka şey yok      → RETURN_HOME

    Timeout → RETURN_HOME (90s bitmedi, bir şeyler ters gitti).
    """
    qr = ctx.current_qr
    if qr is None:
        # QR henüz okunmadı. İki senaryo:
        #   a) Sürü QR noktasına yeni geldi, kamera 1-2s gecikebilir → bekle
        #   b) QR hiç okunamadı (kamera arızası vb.) → timeout sonrası RETURN_HOME
        # Hemen RETURN_HOME YAPMA: bu nadir değil, her QR geçişinde olabilir.
        if ctx.time_in_state() > _QR_TASK_TIMEOUT_S:
            return MissionState.RETURN_HOME   # 90s geçti, QR gelmedi → eve dön
        return None   # QR bekleniyor, bekle

    # İcra node'u "iş bitti ama başarısız" dedi
    if ctx.action_done and not ctx.action_success:
        return MissionState.RETURN_HOME

    # Tüm alt adımlar tamamlandı
    if ctx.qr_task_step == QrTaskStep.DONE:
        if qr.complete_mission:
            # QR mesajında "görevi bitir" işareti var
            return MissionState.RETURN_HOME
        if qr.wait_s > 0.0:
            # QR'da bekleme süresi tanımlı (örn. 5 saniye bekle)
            return MissionState.WAIT_AT_QR
        if qr.next_qr > 0:
            # Bir sonraki QR noktası var, rotasyona geç
            return MissionState.ROTATE_TO_NEXT
        # Hiçbiri yoksa görevi bitir
        return MissionState.RETURN_HOME

    # 90s içinde DONE gelmedi → bir şeyler takıldı, güvenli dön
    if ctx.time_in_state() > _QR_TASK_TIMEOUT_S:
        return MissionState.RETURN_HOME

    return None   # adım sürüyor, bekle


def _from_wait_at_qr(ctx: MissionContext) -> MissionState | None:
    """WAIT_AT_QR: QR'ın wait_s süresi kadar bu noktada bekleniyor.

    _on_state_entry(WAIT_AT_QR) şunu yapar:
      ctx.wait_deadline = time.monotonic() + qr.wait_s

    Bu fonksiyon her tick'te kontrol eder:
      time.monotonic() >= wait_deadline → süre doldu

    Süre dolunca:
      next_qr > 0 ve complete_mission=False → ROTATE_TO_NEXT
      Aksi hâlde → RETURN_HOME
    """
    deadline_passed = (
        ctx.wait_deadline is not None              # deadline set edilmiş mi?
        and time.monotonic() >= ctx.wait_deadline  # süre doldu mu?
    )
    if deadline_passed:
        qr = ctx.current_qr
        # Bir sonraki QR var ve "görevi bitir" işareti yoksa rotasyona geç
        if qr is not None and qr.next_qr > 0 and not qr.complete_mission:
            return MissionState.ROTATE_TO_NEXT
        return MissionState.RETURN_HOME   # başka QR yok, görev bitti

    return None   # süre dolmadı, bekle


def _from_rotate_to_next(ctx: MissionContext) -> MissionState | None:
    """ROTATE_TO_NEXT: formasyon bir sonraki QR yönüne döndürülüyor.

    formation_control rotasyonu tamamlayınca EVENT_ROTATION_COMPLETED yayınlar.
    _on_event() bunu alır, ctx.event_rotation_completed=True yapar.
    Bunu görünce NAVIGATE_TO_QR'a geçeriz.

    Timeout (30s): rotasyon yanıtı gelmediyse de devam ederiz.
    Neden devam ediyoruz? Rotasyon kısmen tamamlanmış olabilir;
    navigate aşaması zaten doğru konuma götürür.
    """
    if ctx.event_rotation_completed:
        return MissionState.NAVIGATE_TO_QR

    # 30s geçti, yanıt yok ama yine de bir sonraki QR'a gidiyoruz
    if ctx.time_in_state() > _ROTATE_TIMEOUT_S:
        return MissionState.NAVIGATE_TO_QR

    return None   # rotasyon sürüyor, bekle


def _from_semi_autonomous(ctx: MissionContext) -> MissionState | None:
    """SEMI_AUTONOMOUS (Görev 2): GCS joystick kontrol modu.

    Bu state'te formation_control, SwarmControlCommand mesajlarını okuyarak
    sürüyü yönlendirir. mission_fsm sadece yaşam döngüsünü izler.

    Çıkış koşulları:
      RTL veya LAND komutu → RETURN_HOME

    NOT — RTL/LAND ve ABORT burada YOK, kasıtlı:
      evaluate_transitions() global handler bu komutları önce yakalar → RETURN_HOME/ABORTED.
      Bu fonksiyon global handler'dan sonra çalışır; bu komutlar buraya asla düşmez.
      Eklemek dead code olur.
    """
    return None   # joystick kontrolü devam ediyor; çıkış global handler'dan gelir


def _from_return_home(ctx: MissionContext) -> MissionState | None:
    """RETURN_HOME: ajanlar RTL modunda eve dönüyor.

    agent_fsm'ler RTL komutunu alınca PX4'te RTL moduna geçer.
    Drone yavaşça inince agent_fsm LANDING(12) veya LANDED(13) state'ine geçer.
    Bunu görünce LANDING state'ine geçeriz.

    Timeout → LANDING (120s geçti, bir ajan LANDING'e geçemedi).
    Neden hemen ABORTED değil?
      RTL tamamlanmış drone'lar zaten inmekte; bağlantısı kopan drone PX4 failsafe'e girer.
      "LANDING" state'ine geçerek kalan drone'ları izlemeye devam etmek daha güvenli.
    """
    # LANDING(12) veya LANDED(13) state'ine geçen ajan var mı?
    if ctx.all_agents_landing() or ctx.all_agents_landed():
        return MissionState.LANDING

    # 120s geçti hâlâ LANDING değil → bağlantı kopmuş veya RTL takılmış olabilir
    # Yine de LANDING'e geç; orada ayrıca timeout var (90s)
    if ctx.time_in_state() > _RETURN_HOME_TIMEOUT_S:
        return MissionState.LANDING

    return None   # drone'lar hâlâ havada, bekle


def _from_landing(ctx: MissionContext) -> MissionState | None:
    """LANDING: tüm ajanların inişi izleniyor.

    Normal durum:
      Tüm drone'lar LANDED(13) → MISSION_COMPLETE

    Timeout (90s):
      Bazı drone'lar indi, bazıları cevap vermiyor (bağlantı kesildi vb.)
      90s geçtiyse yine de MISSION_COMPLETE → görevi tamamlandı say.
      (Kayıp ajan toleransı — yarışmada puan almak için görev tamamlanmalı.)
    """
    if ctx.all_agents_landed():
        return MissionState.MISSION_COMPLETE

    # 90s geçti, hepsi inmedi ama görevi tamamlandı say
    if ctx.time_in_state() > _LANDING_TIMEOUT_S:
        return MissionState.MISSION_COMPLETE

    return None   # iniş sürüyor, bekle


def _from_paused(ctx: MissionContext) -> MissionState | None:
    """PAUSED: GCS PAUSE komutuyla görev durduruldu.

    GCS RESUME komutu gönderince ctx.pause_return_state'e döner.
    Bu state'e girerken _transition() hangi state'teyken durdurulduğumuzu kaydeder.

    Neden sabit NAVIGATE_TO_QR değil, kaydedilen state?
      EXECUTE_QR_TASK sırasında PAUSE gelirse RESUME'da QR görevine dönmek gerekir.
      Sabit hedef kullanmak QR görevini kaybettirir ve gereksiz rota tekrarına yol açar.

    Bu state'te drone'lar hover'da bekler (formation_control hover uygular).
    mission_fsm sadece bekler, hiçbir şey yapmaz.
    """
    if ctx.pending_command == _CMD_RESUME:
        return ctx.pause_return_state   # durdurulmadan önceki state'e dön
    return None   # hâlâ duraklatılmış


# =============================================================================
# QR ADIM YARDIMCI FONKSİYONLARI
# =============================================================================
# mission_fsm_node._advance_qr_step() ve testler tarafından kullanılır.
# Şartname 5.1.2 sırası: FORMATION → MANEUVER → ALTITUDE → DETACH

def find_first_qr_step(qr) -> QrTaskStep:
    """QR mesajındaki ilk aktif adımı döner.

    Şartname sırasına göre ilk aktif bayrağı bulur.
    Tüm bayraklar False ise DONE döner (hiçbir adım yok).

    Örnek:
      formation_active=False, maneuver_active=True → MANEUVER döner
      formation_active=True,  maneuver_active=True → FORMATION döner (önce o)

    Args:
        qr: QRMissionData mesajı (None olabilir).

    Returns:
        İlk aktif QrTaskStep; hiçbiri aktif değilse DONE.
    """
    if qr is None:
        return QrTaskStep.DONE   # QR yoksa adım da yok

    # getattr(..., False): alan mesajda yoksa False döner (güvenli erişim)
    if getattr(qr, 'formation_active', False):
        return QrTaskStep.FORMATION
    if getattr(qr, 'maneuver_active', False):
        return QrTaskStep.MANEUVER
    if getattr(qr, 'altitude_active', False):
        return QrTaskStep.ALTITUDE
    if getattr(qr, 'detach_active', False):
        return QrTaskStep.DETACH
    return QrTaskStep.DONE   # hiçbir adım aktif değil


def find_next_qr_step(qr, current: QrTaskStep) -> QrTaskStep:
    """Tamamlanan adımdan sonra gelen ilk aktif adımı döner.

    Şartname sırasındaki (FORMATION→MANEUVER→ALTITUDE→DETACH) "order" listesini
    dolaşır. current adımı geçince ilk aktif adımı döner.

    Örnek:
      current=FORMATION, maneuver_active=True, altitude_active=False, detach_active=True
      → FORMATION geçildi, MANEUVER aktif → MANEUVER döner

    Örnek:
      current=MANEUVER, altitude_active=False, detach_active=True
      → MANEUVER geçildi, ALTITUDE aktif değil → DETACH döner

    Args:
        qr: QRMissionData mesajı.
        current: Şu an tamamlanan QrTaskStep.

    Returns:
        Sıradaki aktif QrTaskStep; yoksa DONE.
    """
    if qr is None:                  # QR verisi yoksa
        return QrTaskStep.DONE      # adım da yok, DONE döner

    # Şartname sırasına göre (adım, aktif mi?) çiftleri
    # getattr(qr, alan, False): alan mesajda yoksa güvenli şekilde False döner
    order = [
        (QrTaskStep.FORMATION, getattr(qr, 'formation_active', False)),  # sıra 1: formasyon
        (QrTaskStep.MANEUVER,  getattr(qr, 'maneuver_active',  False)),  # sıra 2: manevra
        (QrTaskStep.ALTITUDE,  getattr(qr, 'altitude_active',  False)),  # sıra 3: irtifa
        (QrTaskStep.DETACH,    getattr(qr, 'detach_active',    False)),  # sıra 4: ayrılma
    ]

    passed = False                  # current adımı henüz geçmedik
    for step, active in order:      # her (adım, aktif mi?) çiftini dolaş
        if step == current:         # current adımı bulduk mu?
            passed = True           # evet → artık sonrasını arıyoruz
            continue                # bu adımı atla, bir sonraki iterasyona geç
        if passed and active:       # current sonrası VE aktif olan ilk adım
            return step             # bu adımı döndür
    return QrTaskStep.DONE          # current sonrası aktif adım kalmadı → bitti
