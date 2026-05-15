"""mission_fsm_node.py — Görev seviyesi durum makinesi ROS2 node'u.

=============================================================================
BU DOSYA NE YAPAR?
=============================================================================
  mission_fsm bir "izleyici"dir.
  Drona doğrudan komut VERMEZ. Sadece gözlemler, durumu takip eder, yayınlar.

  Veri akışı:

    [GCS]               → TriggerMission.srv → pending_command
    [drone1/status]     → AgentStatus msg    → agent_statuses[1]
    [drone2/status]     → AgentStatus msg    → agent_statuses[2]
    [drone3/status]     → AgentStatus msg    → agent_statuses[3]
    [kamera/QR]         → QRMissionData msg  → current_qr
    [event bus]         → SystemEvent msg    → event bayrakları
    [GCS joystick]      → SwarmControlCommand → latest_control_cmd

    → 5 Hz tick → evaluate_transitions(ctx) → yeni state?
      → evet: geçiş yap, log at, yaşam döngüsü eventi yayınla
    → her tick: /swarm/mission/state ve /swarm/mission/qr_step yayınla

  Kim ne yapar (paket → ne okur → ne yapar):
    swarm_state_machine/mission_fsm      → sadece state takip eder, yayınlar
    swarm_state_machine/agent_fsm        → her drone'un bireysel uçuş FSM'i
    swarm_core/formation_control         → /swarm/mission/state okur → formasyon yönetir
    swarm_core/maneuver_executor         → state + qr_step okur → pitch/roll manevrası
    swarm_missions/mission1_dynamic_swarm → state + qr_step okur → QR görev adımlarını icra eder
    swarm_missions/mission2_semi_autonomous → state okur → Görev 2 joystick kontrolü

  Osman'ın proxy kuralı:
    Yayın   → /swarm/internal/...   (bu node yazar)
    Abonelik ← /swarm/public/...    (başkaları yazar, biz okuruz)
"""

import time   # wait_deadline hesabı ve last_control_cmd_time için

import rclpy                   # ROS2 Python kütüphanesi
from rclpy.node import Node    # tüm ROS2 node'larının temel sınıfı
from rclpy.qos import (        # QoS = Quality of Service (iletişim kalitesi ayarları)
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from std_msgs.msg import UInt8  # basit 8-bit tam sayı mesajı — state değerini taşır

from swarm_interfaces.msg import (
    AgentStatus,          # drone'un anlık durumu (sağlık, konum, state)
    QRMissionData,        # QR kodundan okunan görev verisi
    SwarmControlCommand,  # GCS joystick komutu (Görev 2)
    SystemEvent,          # sürü geneli olay mesajı (RTL, kalkış, iniş...)
)
from swarm_interfaces.srv import TriggerMission   # GCS → mission_fsm komut servisi

from .mission_context import MissionContext       # FSM'nin tüm değişken durumu
from .mission_states import MissionState, MissionType, QrTaskStep
from .mission_transitions import evaluate_transitions, find_first_qr_step, find_next_qr_step


# =============================================================================
# QoS PROFİLİ
# =============================================================================
# RELIABLE: mesaj kaybolmaz — alıcı alana kadar tekrar gönderilir.
# VOLATILE: geçmiş mesajlar yeni abonenin almaz (bağlantı anından itibaren alır).
# KEEP_LAST depth=10: son 10 mesaj bellekte tutulur.
#
# Ne zaman RELIABLE kullanırız?
#   QR verisi, agent durumu, kritik eventler — bunların kaybolması kabul edilemez.
# Ne zaman 10 (best-effort) kullanırız?
#   agent_status subscriber ve joystick — hız önemli, tek kayıp sorun değil.
_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


# =============================================================================
# NODE SINIFI
# =============================================================================

class MissionFsmNode(Node):
    """Görev seviyesi FSM node'u.

    Tek örnek (instance) çalışır.
    Lider drone'un companion computer'ında (Raspberry Pi) çalışır.
    """

    def __init__(self) -> None:
        """Initialize MissionFsmNode."""
        super().__init__('mission_fsm')   # node adı: 'mission_fsm'

        # Adım 1: launch/CLI parametrelerini oku (agent_ids, team_id, ...)
        self._declare_params()

        # Adım 2: FSM'nin hafıza kutusunu oluştur
        # Bu nesne tüm değişken durumu tutar; callback'ler günceller, transitions okur
        self._ctx = MissionContext(
            agent_ids=self._agent_ids,   # hangi drone'ları bekliyoruz
            team_id=self._team_id,       # QR mesajı filtresi
            sitl_mode=self._sitl_mode,   # simülasyon mu? (GPS kontrolleri atlanır)
        )

        # Adım 3: ROS2 altyapısı — publisher, subscriber, servis
        self._setup_publishers()
        self._setup_subscribers()
        self._setup_service()

        # Adım 4: Ana döngü zamanlayıcısı
        # tick_hz=5.0 → her 200ms'de bir _tick() çağrılır
        # 1.0 / self._tick_hz = 0.2 saniye
        self._timer = self.create_timer(
            1.0 / self._tick_hz, self._tick
        )

        self.get_logger().info(
            f'MissionFsmNode başlatıldı: agents={self._agent_ids} '
            f'team={self._team_id} sitl={self._sitl_mode}'
        )

    # =========================================================================
    # BAŞLATMA METODLARI
    # =========================================================================

    def _declare_params(self) -> None:
        r"""ROS2 parametrelerini tanımlar ve okur.

        Parametreler launch dosyasından veya CLI'dan gelir:
          ros2 run swarm_state_machine mission_fsm_node \\
              --ros-args -p agent_ids:=[1,2,3] -p sitl_mode:=true

        declare_parameter(isim, varsayılan_değer)
        get_parameter(isim).value → değeri al
        """
        # Parametre tanımları — varsayılan değerler
        self.declare_parameter('agent_ids',  [1, 2, 3])  # drone ID listesi
        self.declare_parameter('team_id',    '')          # yarışmada set edilecek takım ID'si
        self.declare_parameter('tick_hz',    5.0)        # FSM döngü hızı
        self.declare_parameter('sitl_mode',  False)      # sim modu

        # Parametreleri instance değişkenlerine ata
        # list() → ROS2 parametre değeri tuple olabilir, listeye çevir
        self._agent_ids: list = list(
            self.get_parameter('agent_ids').value
        )
        self._team_id: str = str(
            self.get_parameter('team_id').value
        )
        self._tick_hz: float = float(
            self.get_parameter('tick_hz').value
        )
        self._sitl_mode: bool = bool(
            self.get_parameter('sitl_mode').value
        )

    def _setup_publishers(self) -> None:
        """Yayın kanallarını (publisher) oluşturur.

        /swarm/mission/state (UInt8)
          → Mevcut MissionState'in integer değeri (ör. EXECUTE_QR_TASK=5)
          → Her tick yayınlanır — state değişmese de
          → formation_control, mission1_dynamic_swarm, maneuver_executor okur

        /swarm/mission/qr_step (UInt8)
          → Mevcut QrTaskStep değeri (ör. MANEUVER=2)
          → Sadece EXECUTE_QR_TASK sırasında anlamlı; diğer state'lerde NONE=0
          → mission1_dynamic_swarm hangi alt görevi çalıştıracağını buradan bilir

        /swarm/internal/events/system (SystemEvent)
          → Yaşam döngüsü olayları: kalkış başlıyor, RTL, görev bitti, acil iniş
          → internal/ çünkü biz yayınlıyoruz; başkaları public/'ten dinler
        """
        # İcra paketleri bu topic'i okuyarak hangi görev aşamasında
        # olduğumuzu anlıyor ve buna göre davranıyor
        self._state_pub = self.create_publisher(
            UInt8,
            '/swarm/mission/state',
            _RELIABLE_QOS,
        )

        # EXECUTE_QR_TASK içinde hangi alt adımdayız?
        # NONE(0) → görev yok
        # FORMATION(1) → formasyon değiştiriliyor
        # MANEUVER(2)  → pitch/roll manevrası
        # ALTITUDE(3)  → irtifa değişimi
        # DETACH(4)    → birey ekleme/çıkarma
        # DONE(5)      → adımlar bitti, ana state geçişi bekleniyor
        self._qr_step_pub = self.create_publisher(
            UInt8,
            '/swarm/mission/qr_step',
            _RELIABLE_QOS,
        )

        # Yaşam döngüsü eventleri — sistemin kritik dönüm noktaları
        # Bu eventleri alan node'lar tepki verir (agent_fsm RTL yapar vb.)
        self._event_pub = self.create_publisher(
            SystemEvent,
            '/swarm/internal/events/system',
            _RELIABLE_QOS,
        )

    def _setup_subscribers(self) -> None:
        """Abonelik kanallarını (subscriber) oluşturur.

        Her ajan için ayrı topic — drone1'in durumu drone2'ninkiyle karışmaz.
        Lambda trick: Python'da döngü içinde lambda tanımlanırsa tüm lambda'lar
        son değeri yakalar. "a=aid" ile her iterasyondaki değeri sabitleriz.

        Örnek hata (a=aid olmadan):
          aid=1,2,3 döngüsü biter → tüm lambda'larda aid=3 olur
          → her mesaj drone3'e atanır (YANLIŞ)

        Örnek doğru (a=aid ile):
          her lambda kendi 'a' değişkenini yakalar: 1, 2, 3 ayrı ayrı
        """
        # Her drone için ayrı subscriber
        for aid in self._agent_ids:
            self.create_subscription(
                AgentStatus,
                f'/swarm/public/drone{aid}/status',   # ör. /swarm/public/drone1/status
                lambda msg, a=aid: self._on_agent_status(msg, a),   # a=aid trick!
                10,   # best-effort QoS, depth=10
            )

        # QR kodu verisi — kamera/perception node'undan gelir
        # RELIABLE: QR mesajı kaybolmasın
        self.create_subscription(
            QRMissionData,
            '/swarm/perception/qr_data',
            self._on_qr_data,
            _RELIABLE_QOS,
        )

        # Sürüden gelen sistem eventleri
        # Formasyon tamamlandı, manevra bitti, birey ayrıldı vb.
        # RELIABLE: event kaybolmasın — kaybolursa adım ilerlemez, timeout'a düşer
        self.create_subscription(
            SystemEvent,
            '/swarm/public/events/system',
            self._on_event,
            _RELIABLE_QOS,
        )

        # Görev 2 joystick komutları
        # best-effort: joystick hızlı güncelleniyor, tek kayıp sorun değil
        self.create_subscription(
            SwarmControlCommand,
            '/swarm/control/command',
            self._on_control_cmd,
            10,
        )

    def _setup_service(self) -> None:
        """TriggerMission servis sunucusunu oluşturur.

        Servis neden topic değil?
          - GCS bir komut gönderir ve "alındı mı?" yanıtını bekler
          - Topic'te yanıt yoktur; servis request-response çiftidir
          - Kritik komutlar (START, ABORT) için servis daha güvenlidir

        GCS bu servisi çağırır:
          /swarm/mission/trigger → TriggerMission.srv
          request: mission_id, command, team_id
          response: success (bool), message (string)
        """
        self._trigger_srv = self.create_service(
            TriggerMission,
            '/swarm/mission/trigger',
            self._handle_trigger,   # callback fonksiyonu
        )

    # =========================================================================
    # FSM ANA DÖNGÜSÜ
    # =========================================================================

    def _tick(self) -> None:
        """5 Hz'de çalışan FSM ana döngüsü (her 200ms bir kez).

        Akış:
          1. evaluate_transitions(ctx)
             → ctx'i okur, geçiş yapılacak state'i döner (veya None)
          2. Geçiş varsa: _transition() çağır
             → ctx.set_state() → bayrakları temizle, zamanlayıcıyı sıfırla
             → log at
             → _on_state_entry() → yaşam döngüsü eventi yayınla
          3. Her tick: _publish_state() → state ve qr_step yayınla
          4. pending_command'ı sıfırla (bir kez işlendi, temizle)
        """
        ctx = self._ctx   # kısa isim — her satırda self._ctx yazmamak için

        # Geçiş değerlendirmesi — saf okuma, ctx'e yazmaz
        next_state = evaluate_transitions(ctx)   # None: geçiş yok, değer: yeni state

        # Geçiş varsa ve farklı bir state ise uygula
        # next_state == ctx.state kontrolü: aynı state'e tekrar geçişi önler (loop riski)
        if next_state is not None and next_state != ctx.state:
            self._transition(next_state)   # state geçişini uygula, log at, event yayınla

        # Her tick'te yayınla — state değişmese de.
        # Yeni başlayan bir icra node'u hemen güncel değeri alır.
        self._publish_state()

        # pending_command tek kullanımlık: bu tick'te işlendi, sonraki tick'te 0 olsun
        # Terminal state'lerde sıfırlamıyoruz — ABORTED/COMPLETE kalıcı kalmalı
        terminal = (MissionState.ABORTED, MissionState.MISSION_COMPLETE)
        if ctx.state not in terminal:
            ctx.pending_command = 0   # sıfırla, aynı komut tekrar işlenmesin

    def _transition(self, new_state: MissionState) -> None:
        """State geçişini uygular.

        Adımlar:
          1. set_state(): state'i güncelle, bayrakları temizle, zamanlayıcıyı sıfırla
          2. Log: hangi state'ten hangisine geçildi
          3. _on_state_entry(): yeni state'e özgü yaşam döngüsü eylemi

        Args:
            new_state: Geçilecek hedef MissionState.
        """
        old = self._ctx.state   # log için eski state'i sakla

        # PAUSED'a geçiyorsak hangi state'ten geldiğimizi kaydet.
        # _from_paused() RESUME gelince buraya döner.
        # set_state()'den ÖNCE kaydediyoruz: set_state() ctx.state'i değiştirir.
        if new_state == MissionState.PAUSED:
            self._ctx.pause_return_state = old

        # set_state: state=new_state, state_entry_time=now(),
        #            action_done/success/event bayrakları=False, qr_task_step=NONE
        self._ctx.set_state(new_state)

        # Timeout veya sistem hatasıyla ABORTED'a düşülünce abort_reason boş kalır.
        # GCS abort dışındaki durumlarda generic sebep yaz.
        if new_state == MissionState.ABORTED and not self._ctx.abort_reason:
            self._ctx.abort_reason = f'Timeout veya preflight hatası ({old.name})'

        # Geçiş logu — terminalde şunu görürsün:
        # [mission_fsm] PREFLIGHT -> SYNCHRONIZED_TAKEOFF
        self.get_logger().info(
            f'[mission_fsm] {old.name} -> {new_state.name}'
        )

        # Yeni state'e girerken yapılacaklar (event yayınlama vb.)
        self._on_state_entry(new_state)

    def _on_state_entry(self, state: MissionState) -> None:
        """Yeni state'e girilince çalışır — sadece yaşam döngüsü eventleri.

        BU FONKSİYON DRONA KOMUT VERMEZ.
        Yaşam döngüsü eventi yayınlar → diğer node'lar tepki verir.

        Kapsananlar:
          SYNCHRONIZED_TAKEOFF → EVENT_MISSION_STARTED
            agent_fsm'ler bu eventi görünce arm+kalkış başlatır

          WAIT_AT_QR → wait_deadline hesapla
            QR'ın bekleme süresini (wait_s) şu ana ekle
            _from_wait_at_qr() bu deadline'ı kontrol eder

          RETURN_HOME → EVENT_RTL_TRIGGERED
            agent_fsm'ler bu eventi görünce PX4'e RTL komutu gönderir

          MISSION_COMPLETE → EVENT_MISSION_COMPLETED
            ground station'a görevi tamamlandı bilgisi gider

          ABORTED → EVENT_EMERGENCY_LAND
            tüm drone'lar hemen yere iner

        Kapsanmayanlar (ilgili paketler state topic'ini izler):
          NAVIGATE_TO_QR  → swarm_core/formation_control state=4 görünce hedefe gider
          EXECUTE_QR_TASK → swarm_missions/mission1_dynamic_swarm state=5+qr_step görünce çalışır

        Args:
            state: Girilen yeni MissionState.
        """
        ctx = self._ctx

        if state == MissionState.SYNCHRONIZED_TAKEOFF:
            # Tüm ajanlar hazır, kalkış başlıyor
            # Bu eventi alan agent_fsm'ler arm+takeoff sürecini başlatır
            self._pub_event(
                SystemEvent.EVENT_MISSION_STARTED,
                SystemEvent.SEVERITY_INFO,
                f'Görev {ctx.mission_type.name} başlatılıyor',
            )

        elif state == MissionState.EXECUTE_QR_TASK:
            # QR içeriği hazırsa → ilk adımı hemen belirle.
            # QR içeriği henüz yoksa (kamera gecikti) → NONE bırak.
            # _on_qr_data(): QR gelince state=EXECUTE_QR_TASK + step=NONE görürse adımı başlatır.
            if ctx.current_qr is not None:
                ctx.qr_task_step = find_first_qr_step(ctx.current_qr)
                self.get_logger().info(
                    f'[mission_fsm] QR görevi başladı, ilk adım: {ctx.qr_task_step.name}'
                )
            else:
                ctx.qr_task_step = QrTaskStep.NONE   # QR bekleniyor
                self.get_logger().info('[mission_fsm] QR görevi başladı, QR okunması bekleniyor')

        elif state == MissionState.NAVIGATE_TO_QR:
            # Önceki QR verisini temizle — yeni noktaya gidiyoruz.
            # QR2'ye giderken current_qr hâlâ QR1 verisini tutuyordu;
            # EXECUTE_QR_TASK başlarken QR1 görevleri yeniden çalışırdı.
            # Sıfırlayınca kamera yeni QR'ı okuyunca _on_qr_data() set eder.
            self._ctx.current_qr = None

        elif state == MissionState.WAIT_AT_QR:
            # QR'ın bekleme süresi hesapla
            # wait_s: QR mesajındaki bekleme süresi (saniye)
            # wait_deadline: şu an + wait_s → "bu zamana kadar bekle"
            wait_s = ctx.current_qr.wait_s if ctx.current_qr else 0.0
            ctx.wait_deadline = time.monotonic() + max(wait_s, 0.0)
            # max(wait_s, 0.0): negatif değer gelirse 0 al
            self.get_logger().info(
                f'[mission_fsm] QR bekleme: {wait_s:.1f}s'
            )

        elif state == MissionState.RETURN_HOME:
            # RTL tetiklendi
            # Bu eventi alan agent_fsm'ler PX4'e RTL komutu gönderir
            self._pub_event(
                SystemEvent.EVENT_RTL_TRIGGERED,
                SystemEvent.SEVERITY_WARNING,
                'Mission FSM RTL tetikledi',
            )

        elif state == MissionState.MISSION_COMPLETE:
            # Tüm görev başarıyla bitti
            self._pub_event(
                SystemEvent.EVENT_MISSION_COMPLETED,
                SystemEvent.SEVERITY_INFO,
                'Görev başarıyla tamamlandı',
            )

        elif state == MissionState.ABORTED:
            # Acil iniş — abort_reason neden iptal edildiğini açıklar
            # Bu eventi alan agent_fsm'ler hemen yer iner (motor kesilmez, kontrollü iniş)
            self._pub_event(
                SystemEvent.EVENT_EMERGENCY_LAND,
                SystemEvent.SEVERITY_CRITICAL,
                f'Görev iptal: {ctx.abort_reason}',
            )

    # =========================================================================
    # ABONELİK CALLBACK'LERİ
    # =========================================================================
    # Her callback: gelen mesajı doğrular ve ctx'e kaydeder.
    # ctx'e yazmak dışında hiçbir şey yapmazlar (publish yok, decision yok).

    def _on_agent_status(self, msg: AgentStatus, agent_id: int) -> None:
        """Ajan durumu mesajını ctx'e kaydeder.

        Her drone 10 Hz'de kendi durumunu yayınlar.
        Bu callback her mesajda tetiklenir ve agent_statuses sözlüğünü günceller.

        agent_statuses yapısı:
          { 1: <AgentStatus>, 2: <AgentStatus>, 3: <AgentStatus> }

        evaluate_transitions → ctx.all_agents_in_swarm() → agent_statuses'e bakar

        Args:
            msg: Gelen AgentStatus mesajı (state, healthy, gps_fix_type...)
            agent_id: Hangi drone'dan geldiği (1, 2 veya 3)
        """
        self._ctx.agent_statuses[agent_id] = msg   # sözlüğü güncelle

    def _on_qr_data(self, msg: QRMissionData) -> None:
        """QR verisini filtreler ve geçerliyse ctx'e kaydeder.

        Filtreler (sırayla kontrol edilir):
          1. team_id: başka takımın QR'ı → yoksay
          2. decoded + valid: bozuk okuma → yoksay
          3. qr_seq: eski mesaj (stale) → yoksay + event yayınla

        qr_seq nedir?
          Her yeni QR noktası farklı sıra numarasına sahip.
          Aynı QR birden fazla kez okunursa qr_seq aynı kalır.
          last_accepted_qr_seq ile karşılaştırarak tekrar işlemeyi önleriz.

        Geçerliyse:
          last_accepted_qr_seq = msg.qr_seq  (yeni QR sırası)
          current_qr = msg                   (aktif QR verisi)

        Args:
            msg: Gelen QRMissionData mesajı.
        """
        # team_id filtresi:
        #   team_id boşsa → simülasyon/test modu, filtre yok ama uyarı ver
        #   team_id doluysa → başka takımın QR'ı ise yoksay
        if self._ctx.team_id == '':
            self.get_logger().warn(
                '[mission_fsm] team_id parametresi set edilmemiş! '
                'Tüm QR\'lar kabul ediliyor (simülasyon modu).',
                throttle_duration_sec=10.0,
            )
        elif msg.team_id != self._ctx.team_id:
            return   # başka takımın QR'ı, bizimle ilgisi yok

        # QR okuma başarısız mı? (kamera bulanık, açı kötü vb.)
        if not msg.decoded or not msg.valid:
            return   # bozuk veri, güvenilmez

        # Daha önce işlenmiş QR mı? qr_seq monoton artar (1, 2, 3...)
        # Yeni gelen qr_seq, son kabul edilenden küçükse veya eşitse "stale"
        if msg.qr_seq <= self._ctx.last_accepted_qr_seq:
            self.get_logger().warn(
                f'[mission_fsm] Stale QR reddedildi: '
                f'seq={msg.qr_seq} <= '
                f'last={self._ctx.last_accepted_qr_seq}'
            )
            # Reddi event olarak yayınla — debug/loglama için
            self._pub_event(
                SystemEvent.EVENT_QR_SEQUENCE_REJECTED,
                SystemEvent.SEVERITY_WARNING,
                f'Stale QR seq={msg.qr_seq}',
            )
            return   # eski mesaj, işleme

        # Tüm kontroller geçti → geçerli QR, kaydet
        self._ctx.last_accepted_qr_seq = msg.qr_seq   # bir sonraki için eşik güncelle
        self._ctx.current_qr = msg                    # aktif QR olarak ata
        self.get_logger().info(
            f'[mission_fsm] QR kabul: seq={msg.qr_seq} '
            f'formation={msg.formation_active} '
            f'maneuver={msg.maneuver_active} '
            f'detach={msg.detach_active}'
        )

        # EXECUTE_QR_TASK'taysak ve QR henüz işlenmemişse adımı şimdi başlat.
        # Senaryo: EVENT_FORMATION_REACHED geldi → EXECUTE_QR_TASK'a girildi →
        # o anda current_qr=None'dı → qr_task_step=NONE kaldı →
        # kamera şimdi QR'ı okudu → burada adımı başlatıyoruz.
        if (self._ctx.state == MissionState.EXECUTE_QR_TASK
                and self._ctx.qr_task_step == QrTaskStep.NONE):
            self._ctx.qr_task_step = find_first_qr_step(msg)
            self.get_logger().info(
                f'[mission_fsm] EXECUTE_QR_TASK: QR okundu, ilk adım: '
                f'{self._ctx.qr_task_step.name}'
            )

    def _on_event(self, msg: SystemEvent) -> None:
        """Sürüden gelen sistem eventlerini dinler ve ctx'i günceller.

        Bu callback mission_fsm'in "kulakları"dır.
        İcra node'ları işi bitince event yayınlar → buraya düşer → ctx güncellenir.

        Hangi event ne demek ve ne yapıyoruz:

        EVENT_FORMATION_REACHED
          formation_control "hedef konuma ulaştık" der.
          → NAVIGATE_TO_QR state'indeyse: event_formation_reached=True
            (bir sonraki tick'te _from_navigate_to_qr() EXECUTE_QR_TASK'a geçer)
          → EXECUTE_QR_TASK + FORMATION/ALTITUDE adımındaysa: adımı ilerlet
            (formation_control formasyon/irtifa değişikliğini tamamladı)

        EVENT_ROTATION_COMPLETED
          formation_control "rotasyon tamam" der.
          → event_rotation_completed=True
            (_from_rotate_to_next() NAVIGATE_TO_QR'a geçer)

        EVENT_MANEUVER_COMPLETED
          maneuver_executor "pitch/roll manevrası tamam" der.
          → EXECUTE_QR_TASK + MANEUVER adımındaysa: adımı ilerlet

        EVENT_MANEUVER_FAILED
          maneuver_executor "manevra başarısız" der.
          → action_done=True, action_success=False
            (_from_execute_qr_task() RETURN_HOME'a geçer)

        EVENT_AGENT_DETACHED
          Bir drone sürüden ayrıldı (DETACH görevi tamamlandı).
          → EXECUTE_QR_TASK + DETACH adımındaysa: adımı ilerlet

        EVENT_MEMBER_MANAGEMENT_FAILED
          Birey ekleme/çıkarma başarısız.
          → action_done=True, action_success=False → RETURN_HOME

        EVENT_FORMATION_FAILED
          Formasyon veya irtifa değişikliği başarısız.
          → action_done=True, action_success=False → RETURN_HOME

        Args:
            msg: Gelen SystemEvent mesajı.
        """
        # hangi event türü? (integer sabit, SystemEvent.EVENT_* ile karşılaştır)
        eid = msg.event_type
        ctx = self._ctx  # kısa isim

        if eid == SystemEvent.EVENT_FORMATION_REACHED:
            if ctx.state == MissionState.NAVIGATE_TO_QR:
                # Sürü QR noktasına vardı
                # Bayrağı set et → bir sonraki tick'te geçiş tetiklenir
                ctx.event_formation_reached = True

            elif ctx.state == MissionState.EXECUTE_QR_TASK:
                # formation_control bir formasyon veya irtifa adımını bitirdi
                # Sadece ilgili adımlarda tepki ver (MANEUVER/DETACH buraya girmez)
                if ctx.qr_task_step in (
                    QrTaskStep.FORMATION, QrTaskStep.ALTITUDE
                ):
                    self._advance_qr_step()   # bir sonraki QR adımına geç

        elif eid == SystemEvent.EVENT_ROTATION_COMPLETED:
            # Sadece ROTATE_TO_NEXT state'indeyken bayrağı set et.
            # Başka state'te gelirse (önceki rotasyondan kalan geç mesaj vb.)
            # yoksay — set_state() zaten temizler ama tam bu aralıkta
            # bayrağı set edip sonra ROTATE_TO_NEXT'e girseydik hemen
            # çıkardık. Guard koyarak bunu önlüyoruz.
            if ctx.state == MissionState.ROTATE_TO_NEXT:
                ctx.event_rotation_completed = True

        elif eid == SystemEvent.EVENT_MANEUVER_COMPLETED:
            # Pitch/roll manevrası tamamlandı
            # Doğru state ve adımda mıyız? Kontrol et.
            if (ctx.state == MissionState.EXECUTE_QR_TASK
                    and ctx.qr_task_step == QrTaskStep.MANEUVER):
                self._advance_qr_step()   # MANEUVER bitti → bir sonraki adım

        elif eid == SystemEvent.EVENT_MANEUVER_FAILED:
            # Manevra başarısız → güvenli RTL
            if (ctx.state == MissionState.EXECUTE_QR_TASK
                    and ctx.qr_task_step == QrTaskStep.MANEUVER):
                ctx.action_done = True   # iş bitti (ama başarısız)
                ctx.action_success = False  # başarısız olduğunu işaretle
                # Bir sonraki tick'te _from_execute_qr_task() → RETURN_HOME

        elif eid == SystemEvent.EVENT_AGENT_DETACHED:
            # Bir drone sürüden ayrıldı (DETACH görevi tamamlandı)
            if (ctx.state == MissionState.EXECUTE_QR_TASK
                    and ctx.qr_task_step == QrTaskStep.DETACH):
                self._advance_qr_step()   # DETACH bitti → DONE'a gidecek

        elif eid == SystemEvent.EVENT_MEMBER_MANAGEMENT_FAILED:
            # Birey ekleme/çıkarma başarısız → güvenli RTL
            if (ctx.state == MissionState.EXECUTE_QR_TASK
                    and ctx.qr_task_step == QrTaskStep.DETACH):
                ctx.action_done = True   # iş bitti (başarısız)
                ctx.action_success = False  # _from_execute_qr_task() → RETURN_HOME

        elif eid == SystemEvent.EVENT_FORMATION_FAILED:
            # Formasyon veya irtifa değişikliği başarısız → güvenli RTL
            if (ctx.state == MissionState.EXECUTE_QR_TASK
                    and ctx.qr_task_step in (
                        QrTaskStep.FORMATION, QrTaskStep.ALTITUDE
                    )):
                ctx.action_done = True   # iş bitti (başarısız)
                ctx.action_success = False  # _from_execute_qr_task() → RETURN_HOME

    def _on_control_cmd(self, msg: SwarmControlCommand) -> None:
        """Görev 2 joystick komutunu ctx'e kaydeder.

        Görev 2 (SEMI_AUTONOMOUS modunda):
          GCS operatörü joystick ile sürüyü yönlendiriyor.
          formation_control bu mesajı okuyarak sürüyü hareket ettirir.
          mission_fsm sadece son mesajı saklar — karar vermez.

        Güvenlik kilitleri (ikisi birden True olmalı):
          command_valid=True  → komut formatı doğru
          deadman_pressed=True → operatör "ölü adam düğmesi"ni basıyor
            Deadman düğmesi: bırakılırsa sistem durur (güvenlik mekanizması)

        Args:
            msg: Gelen SwarmControlCommand mesajı.
        """
        if msg.command_valid and msg.deadman_pressed:
            self._ctx.latest_control_cmd = msg  # son komutu sakla
            self._ctx.last_control_cmd_time = time.monotonic()  # zaman damgası

    # =========================================================================
    # QR ADIM TAKİBİ
    # =========================================================================

    def _advance_qr_step(self) -> None:
        """Tamamlanan QR adımından sonraki adıma geçer.

        find_next_qr_step() şartname sırasına göre:
          FORMATION → MANEUVER → ALTITUDE → DETACH → DONE

        Örnek:
          ctx.qr_task_step = MANEUVER
          qr.altitude_active = True
          → find_next_qr_step() → ALTITUDE döner
          → ctx.qr_task_step = ALTITUDE

          Bir sonraki tick'te _publish_state() yeni qr_step'i yayınlar.
          mission1_dynamic_swarm yeni değeri görünce ALTITUDE görevini başlatır.

        DONE'a gelince:
          ctx.qr_task_step = DONE
          → _from_execute_qr_task() DONE görür
          → wait_s, next_qr vb. koşullara bakarak WAIT_AT_QR / ROTATE_TO_NEXT / RETURN_HOME seçer
        """
        ctx = self._ctx   # kısa isim

        # Mevcut adımdan sonra gelen ilk aktif adımı bul
        # current_qr: QRMissionData, ctx.qr_task_step: şu anki tamamlanan adım
        next_step = find_next_qr_step(ctx.current_qr, ctx.qr_task_step)   # sıradaki aktif adım

        ctx.qr_task_step = next_step   # adımı güncelle → _publish_state() yeni değeri yayınlar
        self.get_logger().info(
            f'[mission_fsm] QR adım ilerledi: {next_step.name}'   # log: hangi adıma geçildi
        )

    # =========================================================================
    # SERVİS HANDLER
    # =========================================================================

    def _handle_trigger(
        self,
        request: TriggerMission.Request,
        response: TriggerMission.Response,
    ) -> TriggerMission.Response:
        """TriggerMission.srv GCS isteğini işler.

        GCS bu servisi çağırır → bu fonksiyon tepki verir → response döner.

        request.command değerleri:
          COMMAND_START  → görevi başlat (yalnızca IDLE'dan)
          COMMAND_ABORT  → görevi iptal et (her state'ten)
          COMMAND_PAUSE  → duraklat
          COMMAND_RESUME → devam et
          COMMAND_RTL    → eve dön
          COMMAND_LAND   → in

        START özel işleme:
          - IDLE state'inde değilsek → reddet (success=False)
          - mission_id'yi MissionType'a dönüştür (1=DYNAMIC_SWARM, 2=SEMI_AUTONOMOUS)
          - team_id gönderildiyse güncelle

        Tüm komutlar için:
          ctx.pending_command = cmd → _tick() sonraki turda bunu işler

        Args:
            request: Gelen servis isteği.
            response: Doldurulup geri gönderilecek yanıt.

        Returns:
            Doldurulmuş TriggerMission.Response.
        """
        ctx = self._ctx              # kısa isim
        cmd = request.command        # hangi komut? (integer, TriggerMission.Request.COMMAND_*)

        if cmd == TriggerMission.Request.COMMAND_START:
            # START yalnızca IDLE state'inde geçerli
            if ctx.state != MissionState.IDLE:
                response.success = False                        # reddedildi
                response.message = (
                    f'START reddedildi: state={ctx.state.name}'   # neden reddedildi
                )
                return response   # pending_command'a yazmadan dön

            # Görev tipini set et: 1=DYNAMIC_SWARM, 2=SEMI_AUTONOMOUS
            try:
                # enum dönüşümü; bilinmeyen ID → ValueError
                mission_type = MissionType(request.mission_id)
            except ValueError:
                response.success = False  # geçersiz ID
                response.message = (
                    f'Geçersiz mission_id: {request.mission_id}'
                )
                return response  # pending_command'a yazmadan dön
            if mission_type == MissionType.UNKNOWN:  # 0 geçerli enum ama anlamsız
                response.success = False  # UNKNOWN ile görev başlatılamaz
                response.message = 'mission_id=0 (UNKNOWN) ile görev başlatılamaz'
                return response  # reddedildi
            ctx.mission_type = mission_type  # DYNAMIC_SWARM veya SEMI_AUTONOMOUS

            # GCS farklı team_id gönderirse güncelle (isteğe bağlı)
            # Boş string gelirse güncelleme yapma — parametre değeri korunur
            if request.team_id:
                ctx.team_id = request.team_id   # QR filtresi için takım ID'si güncelle

        elif cmd == TriggerMission.Request.COMMAND_ABORT:
            # İptal sebebini kaydet — ABORTED event mesajına yazılır
            ctx.abort_reason = 'GCS abort komutu'   # _on_state_entry(ABORTED) bu mesajı yayınlar

        # Komutu ctx'e yaz — _tick() bir sonraki turda işler
        # Tüm komutlar buraya düşer (START/ABORT özel işlem sonrası, diğerleri doğrudan)
        ctx.pending_command = cmd   # evaluate_transitions() bir sonraki tick'te okur

        response.success = True                             # komut alındı
        response.message = f'Komut alındı: cmd={cmd}'      # GCS'e onay mesajı
        self.get_logger().info(
            f'[mission_fsm] TriggerMission: cmd={cmd} '
            f'mission={request.mission_id}'                 # log: komut + görev tipi
        )
        return response   # GCS'e yanıt dön

    # =========================================================================
    # YARDIMCI METODLAR
    # =========================================================================

    def _publish_state(self) -> None:
        """Mevcut mission state ve QR adımını topic'lere yayınlar.

        Her tick çağrılır — state değişmese de yayın yapar.
        Neden her tick?
          Yeni başlayan bir icra node'u "şu anki değer nedir?" diyemez;
          bir sonraki tick'te yayını alır ve hemen senkron olur.

        UInt8 neden?
          MissionState IntEnum'dur → int'e çevrilebilir.
          int(MissionState.EXECUTE_QR_TASK) → 5
          Basit veri tipi, overhead yok, her dil okuyabilir.
        """
        state_msg = UInt8()  # boş UInt8 mesajı oluştur
        # MissionState → integer (ör. 5 = EXECUTE_QR_TASK)
        state_msg.data = int(self._ctx.state)
        self._state_pub.publish(state_msg)  # /swarm/mission/state'e yayınla

        step_msg = UInt8()  # boş UInt8 mesajı oluştur
        # QrTaskStep → integer (ör. 2 = MANEUVER)
        step_msg.data = int(self._ctx.qr_task_step)
        self._qr_step_pub.publish(step_msg)  # /swarm/mission/qr_step'e yayınla

    def _pub_event(
        self,
        event_type: int,
        severity: int,
        message: str = '',
        target_agent_id: int = 0,
    ) -> None:
        """SystemEvent mesajı oluşturup /swarm/internal/events/system'e yayınlar.

        SystemEvent alanları:
          stamp          → ROS2 zaman damgası (senkronizasyon için)
          event_type     → SystemEvent.EVENT_* sabiti (ör. EVENT_RTL_TRIGGERED)
          severity       → INFO / WARNING / CRITICAL
          source_agent_id→ 0 = mission_fsm (bireysel drone değil)
          target_agent_id→ 0 = tüm sürü, >0 = belirli bir drone
          source_module  → 'mission_fsm' (debug için)
          message        → açıklama metni

        Args:
            event_type: SystemEvent.EVENT_* integer sabiti.
            severity:   SystemEvent.SEVERITY_* seviyesi.
            message:    İsteğe bağlı açıklama.
            target_agent_id: Hedef ajan ID; 0 = tüm sürü.
        """
        m = SystemEvent()  # boş SystemEvent mesajı oluştur
        m.stamp = self.get_clock().now().to_msg()  # ROS zaman damgası — senkronizasyon için
        # EVENT_RTL_TRIGGERED, EVENT_MISSION_STARTED vb.
        m.event_type = event_type
        m.severity = severity  # SEVERITY_INFO / WARNING / CRITICAL
        m.source_agent_id = 0  # 0 = mission_fsm gönderdi (drone değil)
        m.target_agent_id = target_agent_id  # 0 = tüm sürü, >0 = belirli drone
        m.source_module = 'mission_fsm'  # debug için kaynak modül adı
        m.message = message  # açıklama metni (log ve GCS için)
        self._event_pub.publish(m)  # /swarm/internal/events/system'e gönder


# =============================================================================
# GİRİŞ NOKTASI
# =============================================================================

def main(args=None) -> None:
    """ros2 run komutu bu fonksiyonu çağırır.

    rclpy.init()  → ROS2'yi başlat
    rclpy.spin()  → callback'ler için bekle (sonsuz döngü)
    Ctrl+C        → KeyboardInterrupt → temizle ve çık
    """
    rclpy.init(args=args)          # ROS2 başlat
    node = MissionFsmNode()        # node örneği oluştur
    try:
        rclpy.spin(node)           # callback döngüsü — Ctrl+C'ye kadar çalışır
    except KeyboardInterrupt:
        pass                       # Ctrl+C normal çıkış
    finally:
        node.destroy_node()        # ROS2 node'u temizle
        rclpy.shutdown()           # ROS2'yi kapat


if __name__ == '__main__':
    main()
