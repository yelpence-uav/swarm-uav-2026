# Copyright 2026 Yelpence
"""ROS2 node running FSM for the swarm mission."""

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

_BEST_EFFORT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)

_LATCHED_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


class MissionFsmNode(Node):
    """Sürü seviyesi görev FSM node'u."""

    def __init__(self) -> None:
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

        # LANDING'de inis komutunun son yayin zamani (saniyede bir tekrar).
        self._last_land_cmd_s = 0.0

        self._timer = self.create_timer(
            1.0 / self._tick_hz, self._tick
        )

        self.get_logger().info(
            f'MissionFsmNode baslatildi: {self._agent_ids}'
        )

    def _declare_params(self) -> None:
        """ROS2 parametrelerini tanimlar ve okur."""
        self.declare_parameter('agent_ids', [1, 2, 3])
        self.declare_parameter('team_id', '752825')
        self.declare_parameter('tick_hz', 5.0)
        self.declare_parameter('sitl_mode', False)
        self.declare_parameter('max_restarts', 0)  # 0 = sınırsız (şartname)
        # Görev başındaki ilk QR hedefi (şartname: QR1). Jenerik kalsın diye
        # parametre; farklı senaryoda değiştirilebilir.
        self.declare_parameter('start_qr', 1)

        self._agent_ids = list(
            self.get_parameter('agent_ids').value
        )
        self._team_id = str(self.get_parameter('team_id').value)
        self._tick_hz = float(
            self.get_parameter('tick_hz').value
        )
        self._sitl_mode = bool(
            self.get_parameter('sitl_mode').value
        )
        self._max_restarts: int = int(
            self.get_parameter('max_restarts').value
        )
        self._start_qr: int = int(self.get_parameter('start_qr').value)

    def _setup_publishers(self) -> None:
        """Yayıncı kanallarını oluşturur."""
        self._state_pub = self.create_publisher(
            UInt8, '/swarm/internal/mission/state', _RELIABLE_QOS,
        )
        self._qr_step_pub = self.create_publisher(
            UInt8, '/swarm/internal/mission/qr_step', _RELIABLE_QOS,
        )
        self._event_pub = self.create_publisher(
            SystemEvent, '/swarm/internal/events/system', _RELIABLE_QOS,
        )
        self._next_target_pub = self.create_publisher(
            MissionTarget,
            '/swarm/internal/mission/next_target',
            _RELIABLE_QOS,
        )

    def _setup_subscribers(self) -> None:
        """Abone kanallarını oluşturur."""
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
            # BEST_EFFORT SART — mesh kaynagi esp32_bridge _MESH_QOS ile
            # yayinliyor; RELIABLE abone QR verisini HIC almaz.
            _BEST_EFFORT_QOS,
        )

        self.create_subscription(
            SystemEvent,
            '/swarm/public/events/system',
            self._on_event,
            _RELIABLE_QOS,
        )

        self.create_subscription(
            QRCoordinates,
            '/swarm/public/mission/qr_coords',
            self._on_qr_coords,
            _LATCHED_QOS,
        )

    def _setup_service(self) -> None:
        """Servis sunucusunu oluşturur."""
        self._trigger_srv = self.create_service(
            TriggerMission,
            '/swarm/mission/trigger',
            self._handle_trigger,
        )

    def _tick(self) -> None:
        """FSM ana dongusu."""
        ctx = self._ctx

        next_state = evaluate_transitions(ctx)

        if next_state is not None and next_state != ctx.state:
            self._transition(next_state)

        # LANDING'de inis komutunu TEKRARLA.
        # _on_state_entry olayi yalnizca BIR KEZ yayinlar. Bu olay
        # /swarm/internal/... -> network_proxy -> /swarm/public/... yolundan
        # gecer ve proxy ESP-NOW telsizini PAKET KAYBIYLA simule eder
        # (_broadcast_drop). Tek paket duserse ajanlar inis komutunu HIC
        # almaz: gorev MISSION_COMPLETE'e ilerler ama ajanlar RETURN_HOME'da
        # asili kalir (olculdu: 3 dron da 9.3 m'de armed bekledi, mission_fsm
        # "indim" sandi). Kritik tek-seferlik komutu kayipli kanalda yollamak
        # yeterli degil; ajanlar LANDING'e gecene kadar tekrarliyoruz.
        # Saniyede bir yeter: LANDING timeout'u 90 sn, yani ~90 deneme. Tick
        # hizinda (5 Hz) yollamak proxy'yi ve tum aboneleri bosuna mesgul eder.
        if ctx.state == MissionState.LANDING:
            simdi = time.monotonic()
            if simdi - self._last_land_cmd_s >= 1.0:
                self._last_land_cmd_s = simdi
                self._pub_event(
                    SystemEvent.EVENT_EMERGENCY_LAND,
                    SystemEvent.SEVERITY_INFO,
                    "Sürü home'da — iniş tetiklendi (tekrar)",
                )

        self._publish_state()

        # Terminal durumda pending_command KORUNUR (komut kaybolmasın), ama
        # timer DURDURULMAZ: _from_terminal, sürü yere inince ABORTED/
        # MISSION_COMPLETE'ten IDLE'a döndürebilsin diye FSM tick'lemeye devam
        # etmeli. (Eskiden timer iptal ediliyordu → terminalden çıkış
        # imkânsızdı, yeni görev için node restart gerekiyordu.)
        terminal = (MissionState.ABORTED, MissionState.MISSION_COMPLETE)
        if ctx.state not in terminal:
            ctx.pending_command = 0

    def _transition(self, new_state: MissionState) -> None:
        """Durum gecisini uygular."""
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
        """Yeni girilen durum eylemlerini calistirir."""
        ctx = self._ctx

        if state == MissionState.SYNCHRONIZED_TAKEOFF:
            self._pub_event(
                SystemEvent.EVENT_MISSION_STARTED,
                SystemEvent.SEVERITY_INFO,
                f'Görev {ctx.mission_type.name} başlıyor',
            )
            # İlk hedefi (start_qr) ROTASYONDAN ÖNCE çöz. Eskiden yalnız
            # NAVIGATE_TO_QR'a girerken çözülüyordu; ama akış ROTATE→NAVIGATE
            # olduğundan ilk ROTASYON hedefsiz kalıyordu: orchestrator dönüş
            # bearing'ini hesaplayamıyor, heading rampası tamamlanmadan rotasyon  # noqa: E501
            # bitiyor, sonra navigasyon boyunca heading slew'lenip formasyonu
            # DÖNERKEN İLERLETİYOR → eğri yol (ölçüldü: ilk bacak düz hattan
            # 7.6 m sapma). Hedef start_qr'dan; QR okumaya bağlı değil, konum
            # tablosu geldiği an (görev başından) çözülebilir → erken çözülür,
            # ilk rotasyon hedefli olur, heading tam oturur, navigasyon düz gider.  # noqa: E501
            if ctx.next_qr_target is None:
                self._resolve_initial_target()

        elif state == MissionState.EXECUTE_QR_TASK:
            if ctx.current_qr is not None:
                ctx.qr_task_step = find_first_qr_step(ctx.current_qr)
                self.get_logger().info(
                    f'[mission_fsm] QR adimi: {ctx.qr_task_step.name}'
                )
            else:
                ctx.qr_task_step = QrTaskStep.NONE
                self.get_logger().info(
                    '[mission_fsm] QR görevi basladi'
                )

        elif state == MissionState.NAVIGATE_TO_QR:
            ctx.current_qr = None
            ctx.last_accepted_qr_seq = 0
            if ctx.next_qr_target is None:
                self._resolve_initial_target()

        elif state == MissionState.WAIT_AT_QR:
            wait_s = ctx.current_qr.wait_s if ctx.current_qr else 0.0
            ctx.wait_deadline = time.monotonic() + max(wait_s, 0.0)
            self.get_logger().info(
                f'[mission_fsm] QR noktasinda bekleniyor: {wait_s:.1f}s'
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
                "Sürü home'da — iniş tetiklendi",
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

    def _on_agent_status(self, msg: AgentStatus, agent_id: int) -> None:
        self._ctx.agent_statuses[agent_id] = msg

    def _on_qr_data(self, msg: QRMissionData) -> None:
        """Kabul edilebilir QR mesajlarini filtreler ve isler."""
        if self._ctx.team_id == '':
            self.get_logger().warn(
                '[mission_fsm] team_id ayarlı değil',
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
                f'[mission_fsm] Gec QR alindi: {self._ctx.qr_task_step.name}'
            )

    def _on_qr_coords(self, msg: QRCoordinates) -> None:
        """QR koordinat tablosunu gunceller."""
        n = min(len(msg.qr_ids), len(msg.lat_deg), len(msg.lon_deg))
        if n != len(msg.qr_ids):
            self.get_logger().warn(
                '[mission_fsm] QRCoordinates dizi uzunlukları tutarsız'
            )

        table = {}
        for i in range(n):
            table[int(msg.qr_ids[i])] = (
                float(msg.lat_deg[i]), float(msg.lon_deg[i])
            )
        self._ctx.qr_coord_table = table
        self.get_logger().info(
            f'[mission_fsm] QR tablosu alindi: {len(table)} nokta'
        )

        if self._ctx.current_qr is not None:
            self._resolve_next_qr_target(self._ctx.current_qr)
        elif self._ctx.state == MissionState.NAVIGATE_TO_QR:
            self._resolve_initial_target()

    def _resolve_next_qr_target(self, qr) -> None:
        """Bir sonraki hedef QR koordinatini tablodan cozer."""
        if qr.next_qr <= 0:
            self._ctx.next_qr_target = None
            self._ctx.route_unknown = False
            return

        target = self._ctx.lookup_qr_position(qr.next_qr)
        self._ctx.next_qr_target = target
        self._ctx.route_unknown = target is None

        if target is None:
            self.get_logger().warn(
                f'[mission_fsm] next_qr={qr.next_qr} icin konum tabloda yok'
            )
        else:
            self.get_logger().info(
                f'[mission_fsm] Sonraki hedef: {qr.next_qr}'
            )

        self._publish_next_target(qr.next_qr)

    def _resolve_initial_target(self) -> None:
        """Gorev basindaki ilk hedefi cozer."""
        target = self._ctx.lookup_qr_position(self._start_qr)
        self._ctx.next_qr_target = target
        self._ctx.route_unknown = target is None

        if target is None:
            self.get_logger().warn(
                f'[mission_fsm] Ilk hedef QR{self._start_qr} konum tabloda yok'
            )
        else:
            self.get_logger().info(
                f'[mission_fsm] Ilk hedef: {self._start_qr}'
            )

        self._publish_next_target(self._start_qr)

    def _publish_next_target(self, qr_id: int) -> None:
        """Hedef koordinati yayinlar."""
        m = MissionTarget()
        m.stamp = self.get_clock().now().to_msg()
        m.qr_id = int(qr_id)
        tgt = self._ctx.next_qr_target
        m.valid = tgt is not None
        m.lat_deg = float(tgt[0]) if tgt is not None else 0.0
        m.lon_deg = float(tgt[1]) if tgt is not None else 0.0
        self._next_target_pub.publish(m)

    def _on_event(self, msg: SystemEvent) -> None:
        """Aciklama: SystemEvent mesajlarini isler."""
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

    def _advance_qr_step(self) -> None:
        """Mevcut QR alt adimini ilerletir."""
        ctx = self._ctx
        next_step = find_next_qr_step(ctx.current_qr, ctx.qr_task_step)
        ctx.qr_task_step = next_step
        self.get_logger().info(
            f'[mission_fsm] QR adimi: {next_step.name}'
        )

    def _handle_trigger(
        self,
        request: TriggerMission.Request,
        response: TriggerMission.Response,
    ) -> TriggerMission.Response:
        """Aciklama: TriggerMission servis isteklerini isler."""
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
            f'[mission_fsm] TriggerMission: cmd={cmd}'
        )
        return response

    def _publish_state(self) -> None:
        """Mevcut MissionState ve QrTaskStep degerlerini yayinlar."""
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
        """Aciklama: SystemEvent yayinlar."""
        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = event_type
        m.severity = severity
        m.source_agent_id = 0
        m.target_agent_id = target_agent_id
        m.source_module = 'mission_fsm'
        m.message = message
        self._event_pub.publish(m)


def main(args=None) -> None:
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
