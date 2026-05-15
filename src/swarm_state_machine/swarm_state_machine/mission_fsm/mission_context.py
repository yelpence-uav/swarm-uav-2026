"""mission_context.py — Mission FSM'nin tüm anlık durumu tek bir yerde.

=============================================================================
BU DOSYA NE YAPAR?
=============================================================================
  MissionContext bir "hafıza kutusu"dur.
  mission_fsm_node içindeki callback'ler bu kutuya YAZAR.
  mission_transitions içindeki fonksiyonlar bu kutudan OKUR.

  Kimin ne yaptığı:
    mission_fsm_node   → ctx'e YAZAR (callback'lerden gelen verileri kaydeder)
    mission_transitions → ctx'i OKUR  (geçiş kararı verir, yazmaz)
    set_state()        → tek yerde bayrak temizliği yapar

  Neden ROS2 import'u YOK?
    → Bu dosyayı birim testlerinde ROS2 kurulu olmadan doğrudan kullanabiliriz.
    → "from swarm_interfaces.msg import AgentStatus" yazsaydık, test sırasında
       ROS2 kurulu olmayan ortamda ImportError alırdık.
    → Tüm değişken durum tek yerde toplandığı için "hangi veri nerede?" sorusu
       ortadan kalkar.

=============================================================================
KULLANIM ÖRNEĞİ
=============================================================================
  # MissionFsmNode.__init__'te:
  ctx = MissionContext(agent_ids=[1, 2, 3], team_id='YELPENCE')

  # Callback'te (yazar):
  ctx.agent_statuses[agent_id] = msg

  # Transitions'ta (okur):
  if ctx.all_agents_in_swarm():
      return MissionState.NAVIGATE_TO_QR
"""

import time  # time.monotonic() için — duvar saati değil, monoton artan sayaç
# @dataclass: __init__/__repr__ otomatik üretir; field: özel varsayılan
from dataclasses import dataclass, field
from typing import Any, Optional  # Any: belirsiz tip; Optional[X]: X veya None


# =============================================================================
# @dataclass import'tan gelen .mission_states modülü
# =============================================================================
# Neden buradan import?
#   mission_states.py → sadece sabitler, ROS2 yok
#   → MissionContext de ROS2'siz kalır → testler çalışır
from .mission_states import MissionState, MissionType, QrTaskStep


# =============================================================================
# AJAN STATE SABITLERİ
# =============================================================================
# AgentStatus.msg'deki .state alanının integer değerleri.
#
# Neden buraya yazdık, AgentStatus.msg'den import etmedik?
#   AgentStatus ROS2 mesaj sınıfıdır → "from swarm_interfaces.msg import AgentStatus"
#   Bu satır ROS2'ye bağımlılık yaratır → testlerde ImportError verir.
#   Çözüm: sayıları burada sabit olarak tanımlıyoruz.
#   UYARI: AgentStatus.msg değişirse burası da güncellenmelidir!
#
# Sadece MissionContext metodlarında KULLANILAN sabitler burada:
# all_agents_in_swarm() için: STATE_IN_SWARM=5
_AGENT_STATE_IN_SWARM = 5   # drone sürüde, göreve hazır
# all_agents_landing() için: STATE_LANDING=12
_AGENT_STATE_LANDING = 12   # drone iniş sürecinde
# all_agents_landed() için: STATE_LANDED=13
_AGENT_STATE_LANDED = 13   # drone yerde, motor kapalı


# =============================================================================
# MISSION CONTEXT SINIFI
# =============================================================================

# @dataclass dekoratörü: Python otomatik __init__, __repr__ ve __eq__ üretir.
# Manuel "def __init__(self, ...)" yazmak gerekmez.
@dataclass
class MissionContext:
    """Mission FSM'nin tüm anlık durumunu tutar.

    Bu sınıfın TEK ÖRNEĞİ vardır; MissionFsmNode.__init__'te oluşturulur
    ve node boyunca yaşar. Birden fazla örnek oluşturmak anlamsızdır.

    Zorunlu kurucu argümanlar (varsayılanı olmayan alanlar):
        agent_ids : Sürüdeki drone ID listesi, ör. [1, 2, 3]

    İsteğe bağlı kurucu argümanlar (varsayılanı olan alanlar):
        team_id   : Yarışma takım adı; QR mesajı filtrelemede kullanılır
        sitl_mode : True → GPS/origin/home kontrolleri atlanır (simülasyon)

    Örnek kullanım:
        ctx = MissionContext(agent_ids=[1, 2, 3], team_id='YELPENCE')
        ctx = MissionContext(agent_ids=[1, 2], sitl_mode=True)  # sim modu
    """

    # ------------------------------------------------------------------
    # ZORUNLU ALANLAR — @dataclass kurucu argümanları (varsayılan yok)
    # ------------------------------------------------------------------
    # Bu alanlar MissionContext(agent_ids=...) çağrısında verilmek zorunda.
    # @dataclass varsayılansız alanları varsayılanlı alanların ÖNÜNE koyar.

    # all_agents_seen, all_agents_in_swarm vb. metodlar bu listeyi kullanır
    agent_ids: list   # ör. [1, 2, 3] — hangi drone'ların mesajını bekliyoruz

    # ------------------------------------------------------------------
    # İSTEĞE BAĞLI ALANLAR — varsayılan değerleri var
    # ------------------------------------------------------------------
    # Varsayılanlı alanlar kurucu çağrısında belirtilmezse bu değerleri alır.
    # Python kuralı: varsayılansız alanlardan SONRA gelmelidir.

    # Yarışmada takım numarası açıklanır; uçuştan önce -p team_id:=<değer> ile set et.
    # Boş ("") kalırsa _on_qr_data tüm QR'ları kabul eder (test / simülasyon için).
    team_id: str = ""  # QR mesajındaki team_id ile eşleşmeli
    # True → simülasyon modu; GPS/origin/home kontrolleri atlanır (sim'de gereksiz)
    sitl_mode: bool = False

    # ------------------------------------------------------------------
    # FSM DURUMU
    # ------------------------------------------------------------------

    # Şu anki mission state — başlangıçta UNKNOWN.
    # UYARI: Direkt değiştirme! set_state() çağrılmadan değiştirirsen
    # bayraklar ve zamanlayıcı temizlenmez → tutarsız durum.
    state: MissionState = MissionState.UNKNOWN

    # Görev tipi: DYNAMIC_SWARM(1) veya SEMI_AUTONOMOUS(2).
    # GCS'ten COMMAND_START gelince request.mission_id ile doldurulur.
    # SYNCHRONIZED_TAKEOFF handler'da bu değere bakılarak:
    #   DYNAMIC_SWARM  → NAVIGATE_TO_QR'a geçilir
    #   SEMI_AUTONOMOUS → SEMI_AUTONOMOUS'a geçilir
    mission_type: MissionType = MissionType.UNKNOWN

    # Bu state'e kaçta girildi? (time.monotonic saniyesi cinsinden).
    # time_in_state() bu değeri kullanarak "ne kadar süredir bu state'teyiz?" hesaplar.
    # field(default_factory=...):
    #   Neden lambda değil, default_factory?
    #   @dataclass tüm instance'lar için AYNI varsayılan değeri paylaşır.
    #   Eğer state_entry_time: float = time.monotonic() yazsaydık,
    #   tüm instance'lar sınıf tanımlandığı andaki zamanı paylaşırdı.
    #   default_factory=time.monotonic → her __init__ çağrısında yeni zaman üretir.
    state_entry_time: float = field(default_factory=time.monotonic)

    # ------------------------------------------------------------------
    # AJAN DURUMLARI
    # ------------------------------------------------------------------

    # Sözlük: { agent_id (int) : AgentStatus mesajı (tip: Any) }
    # Örnek:  { 1: <AgentStatus>, 2: <AgentStatus>, 3: <AgentStatus> }
    # Neden Any tip? AgentStatus'u import etmemek için (ROS2 bağımlılığı olur).
    # Her ajan kendi topic'inden mesaj gönderir:
    #   /swarm/public/drone1/status → _on_agent_status(msg, 1) → agent_statuses[1] = msg
    #   /swarm/public/drone2/status → _on_agent_status(msg, 2) → agent_statuses[2] = msg
    # field(default_factory=dict):
    #   Her instance için ayrı boş sözlük üretir.
    #   Eğer agent_statuses: dict = {} yazsaydık, tüm instance'lar AYNI sözlüğü paylaşırdı!
    agent_statuses: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # QR TAKİP
    # ------------------------------------------------------------------

    # Kabul edilen son QR'ın sıra numarası (başlangıç: 0 = henüz QR kabul edilmedi).
    # QR kameradan her okunduğunda qr_seq artar (1, 2, 3...).
    # Yeni gelen msg.qr_seq bu değerden küçükse veya eşitse "stale" (eski) sayılıp reddedilir.
    # Böylece aynı QR iki kez işlenmez (örn. drone geçtikten sonra kamera hâlâ okuyor).
    last_accepted_qr_seq: int = 0

    # Şu an aktif olan QRMissionData mesajı (tip: Any → ROS2 bağımlılığı olmasın).
    # None → henüz QR okunmadı veya görev bitmedi.
    # Nereden güncellenir: _on_qr_data() callback'i
    # Nereden okunur: _from_execute_qr_task(), _from_wait_at_qr() vb.
    # Optional[Any]: ya None ya da QRMissionData nesnesi olabilir
    current_qr: Optional[Any] = None

    # EXECUTE_QR_TASK içindeki aktif alt adım.
    # Değer sırası (şartname 5.1.2): NONE → FORMATION → MANEUVER → ALTITUDE → DETACH → DONE
    # Nasıl ilerler?
    #   _on_state_entry(EXECUTE_QR_TASK) → find_first_qr_step() ile başlangıç adımı set edilir
    #   _advance_qr_step() → bir sonraki adıma geçer
    # Nerede okunur?
    #   _from_execute_qr_task(): DONE olunca bir sonraki state'e geçer
    #   _publish_state(): her tick /swarm/mission/qr_step topic'ine yayınlanır
    #   mission1_dynamic_swarm: bu değeri okuyarak hangi alt görevi çalıştıracağını bilir
    # Neden set_state()'de sıfırlanır?
    #   EXECUTE_QR_TASK dışındaki state'lerde (WAIT_AT_QR, ROTATE_TO_NEXT vb.) eski adım
    #   değeri yayınlanmaya devam eder. mission1_dynamic_swarm state != EXECUTE_QR_TASK ise
    #   qr_step'i yoksaymalı ama NONE yayınlamak daha temiz ve açık bir sinyal.
    qr_task_step: QrTaskStep = QrTaskStep.NONE

    # PAUSED state'ine girerken hangi state'teydiniz?
    # _from_paused(): RESUME gelince bu state'e döner.
    # Neden lazım?
    #   EXECUTE_QR_TASK sırasında PAUSE gelirse RESUME'da NAVIGATE_TO_QR'a değil,
    #   EXECUTE_QR_TASK'a dönmek gerekir. Aksi hâlde QR görevi kaybolur.
    # Varsayılan: NAVIGATE_TO_QR (hiç PAUSED'a girilmeden önce güvenli değer)
    pause_return_state: MissionState = MissionState.NAVIGATE_TO_QR

    # WAIT_AT_QR state'i için bekleme bitiş zamanı.
    # Nasıl set edilir:
    #   _on_state_entry(WAIT_AT_QR):
    #     wait_deadline = time.monotonic() + current_qr.wait_s
    # Nasıl okunur:
    #   _from_wait_at_qr():
    #     time.monotonic() >= wait_deadline → süre doldu → geçiş yap
    # None: henüz WAIT_AT_QR'a girilmedi veya önceki deadline geçersiz.
    wait_deadline: Optional[float] = None

    # ------------------------------------------------------------------
    # ASENKRON EYLEM BAYRAKLARI
    # ------------------------------------------------------------------
    # İcra node'ları (maneuver_executor, agent_fsm vb.) işi bitince bir event yayınlar.
    # _on_event() bu eventleri alır ve aşağıdaki bayrakları set eder.
    # _from_execute_qr_task() bu bayraklara bakarak:
    #   action_done=True, action_success=False → RETURN_HOME (hata: güvenli dön)
    # set_state() her state geçişinde bunları sıfırlar → temiz başlangıç garantisi.

    # True: icra node'u işi tamamladı (başarılı ya da değil); False: hâlâ sürüyor
    action_done: bool = False  # iş bitti mi? (başarılı veya başarısız)
    # True: başarılı tamamlandı → bir sonraki adıma geç; False: başarısız → RETURN_HOME
    action_success: bool = False  # iş başarılı mıydı?

    # ------------------------------------------------------------------
    # EVENT BAYRAKLARI
    # ------------------------------------------------------------------
    # Sürüden gelen önemli olaylar için tek-kullanımlık bayraklar.
    # Yaşam döngüsü:
    #   1. _on_event() callback'i → event alınır → bayrak True yapılır
    #   2. _tick() → evaluate_transitions() → bayrak okunur → geçiş kararı
    #   3. set_state() → bayrak False yapılır (bir sonraki state temiz başlar)

    # formation_control EVENT_FORMATION_REACHED yayınlar
    # → _from_navigate_to_qr(): EXECUTE_QR_TASK'a geç
    event_formation_reached: bool = False  # sürü navigasyon hedefine (QR noktası) vardı
    # formation_control EVENT_ROTATION_COMPLETED yayınlar
    # → _from_rotate_to_next(): NAVIGATE_TO_QR'a geç
    event_rotation_completed: bool = False  # formasyon rotasyonu tamamlandı

    # ------------------------------------------------------------------
    # FORMASYON TAKİP
    # ------------------------------------------------------------------

    # Şu an uygulanan formasyon tipi.
    # FormationCommand msg'deki integer değeriyle eşleşir:
    #   FORMATION_OKBASI = 1 → V/okbaşı şekli (varsayılan)
    #   FORMATION_LINE   = 2 → tek sıra
    #   FORMATION_CIRCLE = 3 → çember  (değerler FormationCommand.msg'e bakılarak doğrulanmalı)
    # Neden takip ediyoruz? QR görevi formasyon değişikliği içeriyorsa,
    # formation_control yeni formasyon tipini uygular ve bu değeri günceller.
    current_formation_type: int = 1    # FORMATION_OKBASI — başlangıç formasyon tipi

    # Drone'lar arası mesafe (metre).
    # formation_control bu değeri kullanarak ajanlar arasındaki boşluğu ayarlar.
    # 5.0m → şartname gereksinimi veya güvenli başlangıç değeri.
    current_spacing_m: float = 5.0

    # ------------------------------------------------------------------
    # KONTROL
    # ------------------------------------------------------------------

    # GCS'ten gelen son TriggerMission.command değeri.
    # Değerler (TriggerMission.srv'deki COMMAND_* sabitleriyle eşleşir):
    #   0 = yok (henüz komut gelmedi veya işlendi/sıfırlandı)
    #   1 = START  → görevi başlat
    #   2 = ABORT  → görevi iptal et
    #   3 = PAUSE  → görevi duraklat
    #   4 = RESUME → duraklatılan göreve devam et
    #   5 = RTL    → eve dön
    #   6 = LAND   → iniş yap
    # Nasıl çalışır:
    #   _handle_trigger() → ctx.pending_command = cmd
    #   _tick() → evaluate_transitions(ctx) → pending_command okunur
    #   _tick() → ctx.pending_command = 0 (sıfırla — aynı komut iki kez işlenmesin)
    pending_command: int = 0

    # ABORT sebebi — ABORTED state'ine girince event mesajına yazılır.
    # GCS COMMAND_ABORT gönderirse: "GCS abort komutu"
    # Timeout kaynaklı abort'ta: "Timeout veya preflight hatası (PREFLIGHT)"
    # Boş string → sebep bilinmiyor (olmaması gerekir ama failsafe)
    abort_reason: str = ""

    # ------------------------------------------------------------------
    # GÖREV 2 (SEMI_AUTONOMOUS)
    # ------------------------------------------------------------------

    # GCS joystick'ten gelen son SwarmControlCommand mesajı (tip: Any).
    # formation_control bu mesajı okuyarak sürüyü yönlendirir.
    # mission_fsm sadece saklar — içeriğine karışmaz, karar vermez.
    # None: henüz komut gelmedi veya Görev 2 aktif değil.
    latest_control_cmd: Optional[Any] = None

    # Son komutun alındığı zaman (time.monotonic saniyesi).
    # Şu an aktif kullanımda değil.
    # İleride: joystick X saniyedir gelmiyorsa "güvenli mod"a geç (hover).
    # 0.0: henüz komut gelmedi.
    last_control_cmd_time: float = 0.0

    # =================================================================
    # YARDIMCI METODLAR
    # =================================================================
    # @dataclass otomatik __init__ üretir ama metodlar elle yazılır.
    # Bu metodların hepsi: self değişkenlerine bakar, dışarıya etki etmez.

    def set_state(self, new_state: MissionState) -> None:
        """State geçişini uygular ve tüm geçici bayrakları sıfırlar.

        KULLANIM:
          mission_fsm_node._transition() → ctx.set_state(new_state)
          Direkt ctx.state = ... yapma! Bu metodu kullan.

        NE YAPAR?
          1. state'i günceller          → ctx.state = new_state
          2. zamanlayıcıyı sıfırlar     → ctx.state_entry_time = time.monotonic()
          3. event bayraklarını temizler → action_done, event_formation_reached vb.

        NEDEN BAYRAKLARI TEMİZLEMEK GEREKİR?
          Önceki state'te set edilen bayraklar yeni state'i kirletebilir.
          Örnek senaryo:
            NAVIGATE_TO_QR'da event_formation_reached=True set edildi.
            EXECUTE_QR_TASK'a geçildi (set_state çağrıldı, bayrak False yapıldı).
            Eğer temizlenmeseydi: _from_execute_qr_task() hemen EXECUTE_QR_TASK'ta da
            bu bayrağı görebilir (ama burada anlamı farklı) → karışıklık.

        Args:
            new_state: Geçilecek hedef MissionState.
        """
        self.state = new_state  # state'i güncelle (ör. PREFLIGHT → SYNCHRONIZED_TAKEOFF)
        # time_in_state() = time.monotonic() - state_entry_time = 0.0
        self.state_entry_time = time.monotonic()  # zamanlayıcıyı şu ana sıfırla

        # Temizlenmesi gereken bayraklar — önceki state'ten kalan değerleri sıfırla:
        self.action_done = False           # önceki action sonucu temizle
        self.action_success = False           # önceki action başarı durumu temizle
        self.event_formation_reached = False           # önceki navigate olayı temizle
        self.event_rotation_completed = False           # önceki rotasyon olayı temizle
        self.qr_task_step = QrTaskStep.NONE  # EXECUTE_QR_TASK dışında NONE yayınla
        # Neden qr_task_step burada sıfırlanıyor?
        #   WAIT_AT_QR veya ROTATE_TO_NEXT'teyken eski adım (ör. DONE) yayınlanır.
        #   mission1_dynamic_swarm state != EXECUTE_QR_TASK ise yoksaymalı;
        #   ama NONE yayınlamak daha net sinyal → _on_state_entry(EXECUTE_QR_TASK) tekrar set eder.
        # NOT: wait_deadline burada temizlenmiyor.
        #      WAIT_AT_QR'a girilince _on_state_entry() wait_deadline'ı set eder.
        # NOT: pause_return_state burada temizlenmiyor; _transition() set eder.
        #      WAIT_AT_QR'a girilince _on_state_entry() wait_deadline'ı set eder.

    def time_in_state(self) -> float:
        """Şu anki state'te kaç saniye geçtiğini döner.

        NE YAPAR?
          time.monotonic() → şu anki monoton zaman sayacı
          state_entry_time → bu state'e girildiğindeki zaman
          fark = kaç saniye geçti

        NEDEN time.monotonic()?
          time.time() → duvar saati → sistem saati değişebilir (NTP, DST) → tutarsız
          time.monotonic() → sadece artar, hiç geriye gitmez → timeout hesabı için güvenli

        KULLANIM ÖRNEĞİ (mission_transitions.py'da):
          if ctx.time_in_state() > _PREFLIGHT_TIMEOUT_S:  # 60 saniye geçti mi?
              return MissionState.ABORTED

        Returns:
            Geçen süre (saniye, float). Örn: 3.14 → bu state'te 3.14 saniye geçmiş.
        """
        return time.monotonic() - self.state_entry_time   # şu an - giriş anı = geçen süre

    # ------------------------------------------------------------------
    # AJAN DURUM KONTROL METODLARI
    # ------------------------------------------------------------------
    # Bunların hepsi agent_statuses sözlüğüne bakar.
    # ORTAK KURAL:
    #   agent_statuses boşsa (henüz hiç mesaj gelmemişse) → her zaman False döner.
    #   Çünkü "hiç drone görmüyoruz" = "hepsi hazır" demek değildir.
    # all() fonksiyonu ne yapar?
    #   all([True, True, True]) → True
    #   all([True, False, True]) → False  (bir tane bile False yeterli)
    #   all([]) → True  (boş liste — bu yüzden "if not agent_statuses" ile önce kontrol ediyoruz)

    # @property: bu metodu ctx.all_agents_seen() değil ctx.all_agents_seen olarak çağırır
    @property
    def all_agents_seen(self) -> bool:
        """Tüm beklenen ajan ID'lerinden en az bir mesaj alınıp alınmadığını döner.

        NE KONTROL EDER?
          agent_ids listesindeki her ID, agent_statuses sözlüğünde var mı?

        Örnek:
          agent_ids=[1, 2, 3]
          agent_statuses={1: ..., 2: ...}  → drone3'ten mesaj yok → False
          agent_statuses={1: ..., 2: ..., 3: ...} → hepsi görüldü → True

        NEREDE KULLANILIR?
          _from_preflight(): tüm ajanlar görülene kadar bekleriz.
          (Bir ajan hiç mesaj göndermemişse hazır olup olmadığını bilemeyiz.)
        """
        return all(
            aid in self.agent_statuses   # her beklenen ID sözlükte var mı?
            for aid in self.agent_ids    # agent_ids listesini dolaş
        )
        # Örnek: agent_ids=[1,2,3], agent_statuses={1:.., 3:..}
        # → 1 in agent_statuses → True
        # → 2 in agent_statuses → False (drone2'den mesaj yok)
        # → 3 in agent_statuses → True
        # → all([True, False, True]) → False → drone2 henüz görülmedi

    def all_agents_in_state(self, state_value: int) -> bool:
        """Tüm ajanların verilen AgentStatus durum değerinde olup olmadığını döner.

        Genel amaçlı kontrol fonksiyonu.
        Daha özelleşmiş metodlar (all_agents_in_swarm vb.) bunu çağırır.

        NASIL ÇALIŞIR?
          Her ajanın AgentStatus mesajının .state alanını state_value ile karşılaştırır.
          Hepsi eşitse True, biri bile farklıysa False.

        Args:
            state_value: AgentStatus.state alanının beklenen integer değeri.
                         Örn: 5 (IN_SWARM), 12 (LANDING), 13 (LANDED)

        Returns:
            Tüm ajanlar bu state'teyse True; hiç ajan yoksa False.
        """
        if not self.agent_statuses:      # hiç mesaj yoksa (boş sözlük)
            return False                 # "henüz görmedik" → False (güvenli taraf)

        return all(
            s.state == state_value       # her ajanın .state alanı == state_value mı?
            for s in self.agent_statuses.values()  # sözlükteki tüm AgentStatus nesnelerini dolaş
        )
        # Örnek: state_value=5 (IN_SWARM)
        # agent_statuses = {1: (state=5), 2: (state=5), 3: (state=4)}
        # → 5==5 True, 5==5 True, 4==5 False
        # → all([True, True, False]) → False → drone3 henüz IN_SWARM değil

    def all_agents_in_swarm(self) -> bool:
        """Tüm ajanların IN_SWARM(5) state'inde olup olmadığını döner.

        IN_SWARM durumu ne anlama gelir?
          Drone kalkış yaptı, formasyon pozisyonunda, göreve hazır.
          agent_fsm bu state'e geçince "sürüdeyim" sinyali vermiş olur.

        NEREDE KULLANILIR?
          _from_synchronized_takeoff(): tüm drone'lar IN_SWARM olunca
          NAVIGATE_TO_QR veya SEMI_AUTONOMOUS'a geçeriz.
        """
        return self.all_agents_in_state(_AGENT_STATE_IN_SWARM)   # 5 ile karşılaştır

    def all_agents_landing(self) -> bool:
        """Tüm ajanların LANDING(12) state'inde olup olmadığını döner.

        LANDING durumu ne anlama gelir?
          Drone yere iniş sürecinde — motor hâlâ açık, alçalıyor.

        NEREDE KULLANILIR?
          _from_return_home(): drone'lar RTL'den dönerken alçalmaya başlarsa
          LANDING state'ine geçeriz.
        """
        return self.all_agents_in_state(_AGENT_STATE_LANDING)   # 12 ile karşılaştır

    def all_agents_landed(self) -> bool:
        """Tüm ajanların LANDED(13) state'inde olup olmadığını döner.

        LANDED durumu ne anlama gelir?
          Drone yerde, motor kapalı, arming değil.
          agent_fsm en son bu state'e geçer.

        NEREDE KULLANILIR?
          _from_landing(): hepsi LANDED olunca MISSION_COMPLETE'e geçeriz.
        """
        return self.all_agents_in_state(_AGENT_STATE_LANDED)   # 13 ile karşılaştır

    def all_agents_healthy(self) -> bool:
        """Tüm ajanların healthy=True olup olmadığını döner.

        AgentStatus.healthy alanı ne anlama gelir?
          True: IMU, EKF2, GPS bağlantısı, arming engeli yok — her şey yolunda.
          False: drone uçuşa hazır değil (kalibrasyon eksik, GPS yok, bağlantı sorunlu).

        NEREDE KULLANILIR?
          _from_preflight(): healthy=False olan ajan varsa timeout bekleriz,
          60s içinde düzelmezse ABORTED.

        Returns:
            Tüm ajanlar sağlıklıysa True; hiç ajan yoksa False.
        """
        if not self.agent_statuses:      # hiç mesaj yoksa
            return False                 # "bilinmiyor" → False (güvenli taraf)

        return all(
            s.healthy                    # her ajanın .healthy alanı True mu?
            for s in self.agent_statuses.values()
        )

    def all_agents_origin_synced(self) -> bool:
        """Tüm ajanlarda NED koordinat orijininin senkronize olup olmadığını döner.

        NED (North-East-Down) koordinat sistemi ne demek?
          Sürünün ortak referans koordinat sistemi.
          Kuzey=+X, Doğu=+Y, Aşağı=+Z.
          Drone'ların NED orijini aynı olmazsa:
            drone1: "sol 5m" → drone2: "sol 5m" → ama farklı yer!
            Formasyon hesapları bozulur.

        origin_synced alanı ne anlama gelir?
          True: Bu drone'un NED orijini sürünün ortak orijiniyle senkron.

        NEREDE KULLANILIR?
          _from_preflight():
            sitl_mode=False → bu kontrol yapılır
            sitl_mode=True  → atlanır (sim zaten senkron)

        Returns:
            Tüm ajanlar origin_synced=True ise True; hiç ajan yoksa False.
        """
        if not self.agent_statuses:
            return False

        return all(
            s.origin_synced              # her ajanın .origin_synced alanı True mu?
            for s in self.agent_statuses.values()
        )

    def all_agents_home_set(self) -> bool:
        """Tüm ajanlarda RTL için home pozisyonunun set olup olmadığını döner.

        Home pozisyonu ne demek?
          RTL (Return To Launch) komutuyla drone nereye döner?
          Arming anında GPS pozisyonu "home" olarak kaydedilir.
          Home set edilmemişse drone nereye döneceğini bilmez.

        home_set alanı ne anlama gelir?
          True: PX4 home pozisyonunu belirledi, RTL güvenli.

        NEREDE KULLANILIR?
          _from_preflight():
            sitl_mode=False → kontrol edilir (gerçek uçuşta şart)
            sitl_mode=True  → atlanır (simde home otomatik)

        Returns:
            Tüm ajanlar home_set=True ise True; hiç ajan yoksa False.
        """
        if not self.agent_statuses:
            return False

        return all(
            s.home_set                   # her ajanın .home_set alanı True mu?
            for s in self.agent_statuses.values()
        )

    def all_agents_gps_ok(self) -> bool:
        """Tüm ajanlarda GPS kalitesinin arming için yeterli olup olmadığını döner.

        GPS kalite kriterleri (PX4 arming gereksinimleri):
          gps_fix_type >= 3 → en az 3D GPS fix (4+ uydu gerekir)
            0: GPS yok
            1: No fix
            2: 2D fix (sadece enlem/boylam, yükseklik yok)
            3: 3D fix (enlem + boylam + yükseklik) → arming için minimum
            4: DGPS, 6: RTK → daha iyi ama zorunlu değil
          gps_hdop < 1.5 → yatay doğruluk yeterince iyi
            HDOP (Horizontal Dilution of Precision):
            1.0 = mükemmel, 2.0 = zayıf, 5.0+ = kabul edilemez
            1.5 → "iyi ila orta" sınırı

        NEREDE KULLANILIR?
          _from_preflight():
            sitl_mode=False → GPS kalitesi kontrol edilir
            sitl_mode=True  → atlanır (sim'de GPS simüle ama mükemmel)

        Returns:
            Tüm ajanlar yeterli GPS kalitesine sahipse True; hiç ajan yoksa False.
        """
        if not self.agent_statuses:
            return False

        return all(
            s.gps_fix_type >= 3 and s.gps_hdop < 1.5   # iki koşul aynı anda sağlanmalı
            for s in self.agent_statuses.values()
            # gps_fix_type: kaç boyutlu fix var? (>=3 → 3D, arming için minimum)
            # gps_hdop: yatay doğruluk (<1.5 → yeterince iyi)
        )
        # Örnek: 3 drone
        #   drone1: gps_fix_type=3, gps_hdop=1.2 → True  and True  → True
        #   drone2: gps_fix_type=3, gps_hdop=1.7 → True  and False → False
        #   drone3: gps_fix_type=2, gps_hdop=0.9 → False and True  → False
        # → all([True, False, False]) → False → drone2 ve drone3 GPS kalitesi yetersiz
