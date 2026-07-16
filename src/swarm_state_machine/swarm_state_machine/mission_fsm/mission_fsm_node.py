"""mission_fsm_node.py — Sürü seviyesi görev FSM ROS2 node'u.

mission_fsm bir gözlemcidir: gelen veriyi ctx'e depolar,
5 Hz'de geçişleri değerlendirir ve mevcut durumu yayınlar.
Drone'lara veya aktüatör node'larına doğrudan komut göndermez.

Proxy kuralı (Osman):
  Publisher  -> /swarm/internal/...  (proxy /swarm/public/'e iletir)
  Subscriber <- /swarm/public/...    (proxy /swarm/internal/'den iletir)
"""

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from std_msgs.msg import UInt8

from swarm_interfaces.msg import (
    AgentStatus,
    MissionTarget,
    QRCoordinates,
    QRMissionData,
    SystemEvent,
)
from swarm_interfaces.srv import TriggerMission

from .mission_context import MissionContext
from .mission_states import MissionState, MissionType, QrTaskStep
from .mission_transitions import (
    evaluate_transitions,
    find_first_qr_step,
    find_next_qr_step,
)

_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

# agent_fsm AgentStatus'u BEST_EFFORT yayınlar; burada eşleşmeli.
_BEST_EFFORT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)

# QR konum tablosu (QRCoordinates) latched yayınlanır: görev öncesi bir kez
# girilir, geç başlayan/yeniden başlayan mission_fsm son tabloyu otomatik alır.
# SwarmOrigin ile aynı desen — yayıncı (GCS/proxy) ile BİREBİR eşleşmeli.
_LATCHED_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


class MissionFsmNode(Node):
    """Sürü seviyesi görev FSM node'u.

    Hibrit dağıtık mimaride seçili lider drone üzerinde çalışır.
    Lider değişirse consensus_fsm bu node'u yeni liderde yeniden başlatır.
    """

    def __init__(self) -> None:
        """Node'u başlatır ve ROS2 arayüzlerini kurar."""
        super().__init__('mission_fsm')

        self._declare_params()

        self._ctx = MissionContext(
            agent_ids=self._agent_ids,
            team_id=self._team_id,
            sitl_mode=self._sitl_mode,
            max_restarts=self._max_restarts,
        )

        self._setup_publishers()
        self._setup_subscribers()
        self._setup_service()

        self._timer = self.create_timer(
            1.0 / self._tick_hz, self._tick
        )

        self.get_logger().info(
            f'MissionFsmNode başladı: ajanlar={self._agent_ids} '
            f'takım={self._team_id} sitl={self._sitl_mode}'
        )

    # =========================================================================
    # BAŞLATMA
    # =========================================================================

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanımlar ve okur.

        Örnek kullanım:
            ros2 run swarm_state_machine mission_fsm_node
                --ros-args -p agent_ids:=[1,2,3] -p sitl_mode:=true
        """
        self.declare_parameter('agent_ids', [1, 2, 3])
        self.declare_parameter('team_id', '752825')
        self.declare_parameter('tick_hz', 5.0)
        self.declare_parameter('sitl_mode', False)
        self.declare_parameter('max_restarts', 0)  # 0 = sınırsız (şartname)
        # Görev başındaki ilk QR hedefi (şartname: QR1). Jenerik kalsın diye
        # parametre; farklı senaryoda değiştirilebilir.
        self.declare_parameter('start_qr', 1)

        self._agent_ids: list = list(
            self.get_parameter('agent_ids').value
        )
        self._team_id: str = str(self.get_parameter('team_id').value)
        self._tick_hz: float = float(
            self.get_parameter('tick_hz').value
        )
        self._sitl_mode: bool = bool(
            self.get_parameter('sitl_mode').value
        )
        self._max_restarts: int = int(
            self.get_parameter('max_restarts').value
        )
        self._start_qr: int = int(self.get_parameter('start_qr').value)

    def _setup_publishers(self) -> None:
        """Yayıncı kanallarını oluşturur.

        /swarm/internal/mission/state   (UInt8)       — mevcut durum
        /swarm/internal/mission/qr_step (UInt8)       — mevcut QR adımı
        /swarm/internal/events/system   (SystemEvent) — yaşam döngüsü olayları

        mission1_dynamic_swarm bunları okuyarak aktüatör komutlarını gönderir.
        """
        self._state_pub = self.create_publisher(
            UInt8, '/swarm/internal/mission/state', _RELIABLE_QOS,
        )
        self._qr_step_pub = self.create_publisher(
            UInt8, '/swarm/internal/mission/qr_step', _RELIABLE_QOS,
        )
        self._event_pub = self.create_publisher(
            SystemEvent, '/swarm/internal/events/system', _RELIABLE_QOS,
        )
        # Sonraki hedef QR konumu — mission1_dynamic_swarm buradan okuyup
        # navige eder. RELIABLE: hedef her QR'da değişir, kaybolmamalı.
        # Proxy /public'e taşır.
        self._next_target_pub = self.create_publisher(
            MissionTarget,
            '/swarm/internal/mission/next_target',
            _RELIABLE_QOS,
        )

    def _setup_subscribers(self) -> None:
        """Abone kanallarını oluşturur.

        Her drone için bir AgentStatus aboneliği; lambda, Python kapanma
        sorununu önlemek için drone ID'sini değer olarak yakalar.
        """
        for aid in self._agent_ids:
            self.create_subscription(
                AgentStatus,
                f'/swarm/public/drone{aid}/status',
                lambda msg, a=aid: self._on_agent_status(msg, a),
                _BEST_EFFORT_QOS,
            )

        self.create_subscription(
            QRMissionData,
            '/swarm/public/perception/qr_data',
            self._on_qr_data,
            _RELIABLE_QOS,
        )

        self.create_subscription(
            SystemEvent,
            '/swarm/public/events/system',
            self._on_event,
            _RELIABLE_QOS,
        )

        # QR konum tablosu (Akış B) — operatör YKİ'den girer, proxy public'e
        # iletir. next_qr -> lat/lon çözümü için saklanır. Latched QoS: geç
        # başlasak bile son tabloyu yakalarız.
        self.create_subscription(
            QRCoordinates,
            '/swarm/public/mission/qr_coords',
            self._on_qr_coords,
            _LATCHED_QOS,
        )

    def _setup_service(self) -> None:
        """Servis sunucusunu (TriggerMission) oluşturur.

        GCS alındıyı onaylayabilsin diye topic yerine servis kullanılır.
        """
        self._trigger_srv = self.create_service(
            TriggerMission,
            '/swarm/mission/trigger',
            self._handle_trigger,
        )

    # =========================================================================
    # FSM ANA DÖNGÜSÜ
    # =========================================================================

    def _tick(self) -> None:
        """tick_hz (varsayılan 5 Hz) hızında çalışan FSM döngüsü.

        1. Geçişleri değerlendir.
        2. Durum değişiyorsa geçişi uygula.
        3. Her tick'te mevcut durumu yayınla.
        4. pending_command'ı temizle (terminal durumlarda hariç).
        """
        ctx = self._ctx

        next_state = evaluate_transitions(ctx)

        if next_state is not None and next_state != ctx.state:
            self._transition(next_state)

        self._publish_state()

        terminal = (MissionState.ABORTED, MissionState.MISSION_COMPLETE)
        if ctx.state in terminal:
            if hasattr(self, '_timer'):
                self._timer.cancel()
        else:
            ctx.pending_command = 0

    def _transition(self, new_state: MissionState) -> None:
        """Durum geçişini uygular.

        Args:
            new_state (MissionState): Geçilecek hedef durum.
        """
        old = self._ctx.state

        if new_state == MissionState.PAUSED:
            self._ctx.pause_return_state = old

        self._ctx.set_state(new_state)

        # Şartname madde 17: eve varış sonrası restart. QR zincirini sıfırla
        # ki rota QR1'den yeniden başlasın; sayacı artır (sonsuz döngü yok).
        if (old == MissionState.RETURN_HOME
                and new_state == MissionState.ROTATE_TO_NEXT):
            self._ctx.restart_count += 1
            self._ctx.restart_pending = False
            self._ctx.last_accepted_qr_seq = 0
            self._ctx.current_qr = None
            self.get_logger().warn(
                f'[mission_fsm] QR okunamadı — rota baştan başlıyor '
                f'(deneme {self._ctx.restart_count}/{self._ctx.max_restarts})'
            )

        if new_state == MissionState.ABORTED and not self._ctx.abort_reason:
            self._ctx.abort_reason = (
                f'Timeout veya preflight hatası ({old.name})'
            )

        self.get_logger().info(
            f'[mission_fsm] {old.name} -> {new_state.name}'
        )

        self._on_state_entry(new_state)

    def _on_state_entry(self, state: MissionState) -> None:
        """Yeni girilen durum için giriş eylemlerini çalıştırır.

        Yaşam döngüsü SystemEvent'lerini yayınlar; aktüatör komutu göndermez.

        Args:
            state (MissionState): Az önce girilmiş durum.
        """
        ctx = self._ctx

        if state == MissionState.SYNCHRONIZED_TAKEOFF:
            self._pub_event(
                SystemEvent.EVENT_MISSION_STARTED,
                SystemEvent.SEVERITY_INFO,
                f'Görev {ctx.mission_type.name} başlıyor',
            )

        elif state == MissionState.EXECUTE_QR_TASK:
            if ctx.current_qr is not None:
                ctx.qr_task_step = find_first_qr_step(ctx.current_qr)
                self.get_logger().info(
                    f'[mission_fsm] QR görevi başladı, '
                    f'ilk adım: {ctx.qr_task_step.name}'
                )
            else:
                ctx.qr_task_step = QrTaskStep.NONE
                self.get_logger().info(
                    '[mission_fsm] QR görevi başladı, QR bekleniyor'
                )

        elif state == MissionState.NAVIGATE_TO_QR:
            # Eski QR verisini temizle; EXECUTE_QR_TASK taze veriyi okusun.
            ctx.current_qr = None
            ctx.last_accepted_qr_seq = 0
            # İlk navigasyon: hiç QR okunmadı → hedef sabit QR1 (şartname).
            # Sonraki navigasyonlarda next_qr_target önceki QR'dan zaten dolu.
            if ctx.next_qr_target is None:
                self._resolve_initial_target()

        elif state == MissionState.WAIT_AT_QR:
            wait_s = ctx.current_qr.wait_s if ctx.current_qr else 0.0
            ctx.wait_deadline = time.monotonic() + max(wait_s, 0.0)
            self.get_logger().info(
                f'[mission_fsm] QR noktasında bekleniyor: {wait_s:.1f}s'
            )

        elif state == MissionState.RETURN_HOME:
            # QR okunamadığı için dönülüyorsa (current_qr yok) eve varınca
            # rota baştan başlar; görev tamamlandığı için dönülüyorsa inilir.
            ctx.restart_pending = ctx.current_qr is None
            self._pub_event(
                SystemEvent.EVENT_RTL_TRIGGERED,
                SystemEvent.SEVERITY_WARNING,
                'Görev FSM RTL tetikledi',
            )

        elif state == MissionState.LANDING:
            # Sürü formasyonla home'a vardı (RETURN_HOME→LANDING kapısı
            # event_formation_reached). Ajanlar offboard'da RETURN_HOME'da
            # bekliyor; inişi ancak bu sinyalle tetikleriz. Sinyal olmadan
            # eskiden inişi yalnız native RTL'in AUTO_LAND'i başlatıyordu —
            # o da sürüyü eve varmadan rastgele yere indiriyordu. Ajan bu
            # olayı alınca RETURN_HOME→LANDING→'land' ile home slotuna iner.
            self._pub_event(
                SystemEvent.EVENT_EMERGENCY_LAND,
                SystemEvent.SEVERITY_INFO,
                'Sürü home\'da — iniş tetiklendi',
            )

        elif state == MissionState.MISSION_COMPLETE:
            self._pub_event(
                SystemEvent.EVENT_MISSION_COMPLETED,
                SystemEvent.SEVERITY_INFO,
                'Görev başarıyla tamamlandı',
            )

        elif state == MissionState.ABORTED:
            self._pub_event(
                SystemEvent.EVENT_EMERGENCY_LAND,
                SystemEvent.SEVERITY_CRITICAL,
                f'Görev iptal edildi: {ctx.abort_reason}',
            )

    # =========================================================================
    # ABONELİK CALLBACK'LERİ
    # =========================================================================

    def _on_agent_status(self, msg: AgentStatus, agent_id: int) -> None:
        """Belirtilen ajan için en güncel AgentStatus'u depolar.

        Args:
            msg (AgentStatus): Gelen durum mesajı.
            agent_id (int): Bildiren ajanın ID'si.
        """
        self._ctx.agent_statuses[agent_id] = msg

    def _on_qr_data(self, msg: QRMissionData) -> None:
        """Gelen QR görev verisini filtreler ve depolar.

        Sırasıyla uygulanan filtreler:
          1. team_id uyuşmazlığı  -> atla
          2. decoded veya valid False -> atla
          3. hâlihazırda işlenen QR'ın tekrarı -> atla

        Tekrarı ayırt eden QR NUMARASIDIR (qr_id), qr_seq DEĞİL: qr_seq her
        vision_node'un KENDİ sayacıdır, sürüde ajan sayısı kadar bağımsız sayaç
        vardır. Bunları tek bir "artan olmalı" çıtasıyla süzmek, bir dronun
        okumasının çıtayı yükseltip BAŞKA bir dronun sonraki QR okumasını (kendi
        sayacında henüz düşük) "eski" sanarak atmasına yol açıyordu; o QR'ın
        görevi (ör. sürüden ayrılma) hiç çalışmıyordu. qr_id içerikten gelir,
        yayıncıdan bağımsızdır; mission1 tarafı da aynı ölçütü kullanır, böylece
        iki düğüm hangi QR'ın güncel olduğunda ayrışamaz.

        Args:
            msg (QRMissionData): Gelen QR görev verisi mesajı.
        """
        if self._ctx.team_id == '':
            self.get_logger().warn(
                '[mission_fsm] team_id ayarlı değil;'
                " tüm QR'lar kabul ediliyor.",
                throttle_duration_sec=10.0,
            )
        elif msg.team_id != self._ctx.team_id:
            return

        if not msg.decoded or not msg.valid:
            return

        qr_id = int(msg.qr_id)
        if qr_id and qr_id == self._ctx.last_accepted_qr_id:
            self.get_logger().warn(
                f'[mission_fsm] Aynı QR tekrar okundu, atlandı: qr={qr_id}',
                throttle_duration_sec=5.0,
            )
            return

        self._ctx.last_accepted_qr_id = qr_id
        self._ctx.last_accepted_qr_seq = msg.qr_seq
        self._ctx.current_qr = msg
        self.get_logger().info(
            f'[mission_fsm] QR kabul edildi: qr={qr_id} '
            f'formasyon={msg.formation_active} '
            f'manevra={msg.maneuver_active} '
            f'irtifa={msg.altitude_active} '
            f'ayrilma={msg.detach_active}'
        )

        self._resolve_next_qr_target(msg)

        if (self._ctx.state == MissionState.EXECUTE_QR_TASK
                and self._ctx.qr_task_step == QrTaskStep.NONE):
            self._ctx.qr_task_step = find_first_qr_step(msg)
            self.get_logger().info(
                f'[mission_fsm] Geç QR alındı, '
                f'ilk adım: {self._ctx.qr_task_step.name}'
            )

    def _on_qr_coords(self, msg: QRCoordinates) -> None:
        """Operatörün girdiği QR konum tablosunu (Akış B) ctx'e depolar.

        Paralel diziler (qr_ids / lat_deg / lon_deg) tek bir dict'e çevrilir:
        QR numarası -> (lat_deg, lon_deg). Şartname enlem/boylam paylaşır.

        Savunmacı kodlama: dizi uzunlukları eşleşmezse (bozuk/eksik mesaj) en
        kısa ortak uzunluğa göre işlenir; kısmi tablo, yanlış tablodan iyidir.

        Args:
            msg (QRCoordinates): Paylaşılan QR konum tablosu (latched).
        """
        n = min(len(msg.qr_ids), len(msg.lat_deg), len(msg.lon_deg))
        if n != len(msg.qr_ids):
            self.get_logger().warn(
                '[mission_fsm] QRCoordinates dizi uzunlukları tutarsız; '
                f'ilk {n} nokta kullanılıyor.'
            )

        table: dict = {}
        for i in range(n):
            table[int(msg.qr_ids[i])] = (
                float(msg.lat_deg[i]), float(msg.lon_deg[i])
            )
        self._ctx.qr_coord_table = table
        self.get_logger().info(
            f'[mission_fsm] QR konum tablosu alındı: {len(table)} nokta '
            f'{sorted(table.keys())}'
        )

        # Tablo, hedef çözülmesinden SONRA gelmiş olabilir; bekleyeni çöz.
        # Bir QR okunduysa next_qr'ı, okunmadıysa (ilk nav) start_qr'ı çöz.
        if self._ctx.current_qr is not None:
            self._resolve_next_qr_target(self._ctx.current_qr)
        elif self._ctx.state == MissionState.NAVIGATE_TO_QR:
            self._resolve_initial_target()

    def _resolve_next_qr_target(self, qr) -> None:
        """current_qr.next_qr numarasını tablodan lat/lon'a çözer.

        Sonucu ctx.next_qr_target'a yazar (mission1_dynamic_swarm buradan
        okuyup navige eder). next_qr=0 ise son görev noktası -> hedef yok.
        Konum tabloda yoksa uyarır: rota bilinemez, QR-okuma failsafe'i
        (manevra ile tekrar dene / RTL) devreye girmelidir.

        Args:
            qr: Kabul edilmiş QRMissionData mesajı (next_qr alanı okunur).
        """
        if qr.next_qr <= 0:
            self._ctx.next_qr_target = None
            self._ctx.route_unknown = False  # görev sonu; rota hatası DEĞİL
            return

        target = self._ctx.lookup_qr_position(qr.next_qr)
        self._ctx.next_qr_target = target
        self._ctx.route_unknown = target is None

        if target is None:
            self.get_logger().warn(
                f'[mission_fsm] next_qr={qr.next_qr} için konum tabloda YOK '
                "— operatör YKİ'den girdi mi? Rota bilinemez."
            )
        else:
            self.get_logger().info(
                f'[mission_fsm] Sonraki hedef QR{qr.next_qr} = '
                f'lat={target[0]:.7f}, lon={target[1]:.7f}'
            )

        # Çözülen hedefi mission1_dynamic_swarm'a yayınla (valid=konum var mı).
        self._publish_next_target(qr.next_qr)

    def _resolve_initial_target(self) -> None:
        """Görev başındaki ilk hedefi (start_qr, şartname: QR1) çözer.

        Sürü ilk QR'a giderken henüz hiçbir QR OKUMAMIŞTIR (current_qr None),
        dolayısıyla next_qr yoktur; hedef tablodan start_qr ile bulunur.
        Konum tabloda yoksa uyarır — operatör YKİ'den girmemiş olabilir.
        """
        target = self._ctx.lookup_qr_position(self._start_qr)
        self._ctx.next_qr_target = target
        self._ctx.route_unknown = target is None

        if target is None:
            self.get_logger().warn(
                f'[mission_fsm] İlk hedef QR{self._start_qr} konumu tabloda '
                "YOK — operatör YKİ'den QR konumlarını girdi mi?"
            )
        else:
            self.get_logger().info(
                f'[mission_fsm] İlk hedef QR{self._start_qr} = '
                f'lat={target[0]:.7f}, lon={target[1]:.7f}'
            )

        self._publish_next_target(self._start_qr)

    def _publish_next_target(self, qr_id: int) -> None:
        """Çözülen sonraki hedefi mission1_dynamic_swarm'a yayınlar.

        ctx.next_qr_target (lat/lon) yoksa valid=False gönderilir — mission1
        navige etmez; rota bilinmiyor demektir (QR-okuma failsafe'i devrede).

        Args:
            qr_id (int): Hedef QR numarası (next_qr ya da start_qr).
        """
        m = MissionTarget()
        m.stamp = self.get_clock().now().to_msg()
        m.qr_id = int(qr_id)
        tgt = self._ctx.next_qr_target
        m.valid = tgt is not None
        m.lat_deg = float(tgt[0]) if tgt is not None else 0.0
        m.lon_deg = float(tgt[1]) if tgt is not None else 0.0
        self._next_target_pub.publish(m)

    def _on_event(self, msg: SystemEvent) -> None:
        """Gelen SystemEvent'leri işler ve ctx bayraklarını günceller.

        Args:
            msg (SystemEvent): Gelen sistem olayı mesajı.
        """
        eid = msg.event_type
        ctx = self._ctx
        # TEŞHİS (geçici): hangi event, kimden, hangi state'te geldi.
        self.get_logger().info(
            f'[EVENT] id={eid} src={msg.source_agent_id} '
            f'mod={msg.source_module} state={ctx.state.name}'
        )

        if eid == SystemEvent.EVENT_FORMATION_REACHED:
            if ctx.state == MissionState.NAVIGATE_TO_QR:
                ctx.event_formation_reached = True
            elif ctx.state == MissionState.RETURN_HOME:
                # Eve ulaşıldı; restart bekliyorsa rota baştan başlar.
                ctx.event_formation_reached = True
            elif ctx.state == MissionState.EXECUTE_QR_TASK:
                if ctx.qr_task_step in (
                    QrTaskStep.FORMATION, QrTaskStep.ALTITUDE
                ):
                    self._advance_qr_step()

        elif eid == SystemEvent.EVENT_ROTATION_COMPLETED:
            if ctx.state == MissionState.ROTATE_TO_NEXT:
                ctx.event_rotation_completed = True

        elif eid == SystemEvent.EVENT_MANEUVER_COMPLETED:
            if (ctx.state == MissionState.EXECUTE_QR_TASK
                    and ctx.qr_task_step == QrTaskStep.MANEUVER):
                self._advance_qr_step()

        elif eid == SystemEvent.EVENT_MANEUVER_FAILED:
            if (ctx.state == MissionState.EXECUTE_QR_TASK
                    and ctx.qr_task_step == QrTaskStep.MANEUVER):
                ctx.action_done = True
                ctx.action_success = False

        elif eid == SystemEvent.EVENT_AGENT_DETACHED:
            if (ctx.state == MissionState.EXECUTE_QR_TASK
                    and ctx.qr_task_step == QrTaskStep.DETACH):
                self._advance_qr_step()

        elif eid == SystemEvent.EVENT_MEMBER_MANAGEMENT_FAILED:
            if (ctx.state == MissionState.EXECUTE_QR_TASK
                    and ctx.qr_task_step == QrTaskStep.DETACH):
                ctx.action_done = True
                ctx.action_success = False

        elif eid == SystemEvent.EVENT_FORMATION_FAILED:
            if (ctx.state == MissionState.EXECUTE_QR_TASK
                    and ctx.qr_task_step in (
                        QrTaskStep.FORMATION, QrTaskStep.ALTITUDE
                    )):
                ctx.action_done = True
                ctx.action_success = False

    # =========================================================================
    # QR ADIM TAKİBİ
    # =========================================================================

    def _advance_qr_step(self) -> None:
        """Bir sonraki aktif QR alt-adımına ilerler.

        qr_task_step güncellenir; mission1_dynamic_swarm yayınlanan
        qr_step topic'ini okuyarak uygun aktüatör komutunu gönderir.
        """
        ctx = self._ctx
        next_step = find_next_qr_step(ctx.current_qr, ctx.qr_task_step)
        ctx.qr_task_step = next_step
        self.get_logger().info(
            f'[mission_fsm] QR adımı ilerledi: {next_step.name}'
        )

    # =========================================================================
    # SERVİS İŞLEYİCİ
    # =========================================================================

    def _handle_trigger(
        self,
        request: TriggerMission.Request,
        response: TriggerMission.Response,
    ) -> TriggerMission.Response:
        """Servis isteklerini (GCS'den gelen TriggerMission) işler.

        START yalnızca IDLE durumunda kabul edilir. mission_id geçerli
        bir MissionType'a eşlenmelidir. team_id verilmişse güncellenir.

        Args:
            request (TriggerMission.Request): Gelen servis isteği.
            response (TriggerMission.Response): Doldurulacak yanıt.

        Returns:
            TriggerMission.Response: Doldurulmuş yanıt.
        """
        ctx = self._ctx
        cmd = request.command

        if cmd == TriggerMission.Request.COMMAND_START:
            if ctx.state != MissionState.IDLE:
                response.success = False
                response.message = (
                    f'START reddedildi: durum={ctx.state.name}'
                )
                return response

            try:
                mission_type = MissionType(request.mission_id)
            except ValueError:
                response.success = False
                response.message = (
                    f'Geçersiz mission_id: {request.mission_id}'
                )
                return response

            if mission_type == MissionType.UNKNOWN:
                response.success = False
                response.message = 'mission_id=0 (UNKNOWN) kullanılamaz'
                return response

            ctx.mission_type = mission_type

            if request.team_id:
                ctx.team_id = request.team_id

        elif cmd == TriggerMission.Request.COMMAND_ABORT:
            ctx.abort_reason = 'GCS iptal komutu'

        ctx.pending_command = cmd

        response.success = True
        response.message = f'Komut kabul edildi: cmd={cmd}'
        self.get_logger().info(
            f'[mission_fsm] TriggerMission: cmd={cmd} '
            f'görev={request.mission_id}'
        )
        return response

    # =========================================================================
    # YARDIMCILAR
    # =========================================================================

    def _publish_state(self) -> None:
        """Her tick'te mevcut MissionState ve QrTaskStep'i yayınlar."""
        state_msg = UInt8()
        state_msg.data = int(self._ctx.state)
        self._state_pub.publish(state_msg)

        step_msg = UInt8()
        step_msg.data = int(self._ctx.qr_task_step)
        self._qr_step_pub.publish(step_msg)

    def _pub_event(
        self,
        event_type: int,
        severity: int,
        message: str = '',
        target_agent_id: int = 0,
    ) -> None:
        """Sistem olayı (SystemEvent) mesajı oluşturur ve yayınlar.

        Args:
            event_type (int): SystemEvent.EVENT_* sabiti.
            severity (int): SystemEvent.SEVERITY_* seviyesi.
            message (str): İsteğe bağlı okunabilir açıklama.
            target_agent_id (int): Hedef ajan; 0 tüm sürü anlamına gelir.
        """
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = event_type
        m.severity = severity
        m.source_agent_id = 0
        m.target_agent_id = target_agent_id
        m.source_module = 'mission_fsm'
        m.message = message
        self._event_pub.publish(m)


# =============================================================================
# GİRİŞ NOKTASI
# =============================================================================

def main(args=None) -> None:
    """ros2 run tarafından çağrılan giriş noktası."""
    rclpy.init(args=args)
    node = MissionFsmNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
