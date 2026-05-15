"""mission_fsm_node.py — Gorev seviyesi durum makinesi ROS2 node'u.

mission_fsm bir izleyicidir; drona dogrudan komut vermez.
Gelen verileri ctx'e kaydeder, 5 Hz'de gecis degerlendirir, state yayinlar.

Osman'in proxy kurali:
  Yayın   -> /swarm/internal/...
  Abonelik <- /swarm/public/...
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
    QRMissionData,
    SwarmControlCommand,
    SystemEvent,
)
from swarm_interfaces.srv import TriggerMission

from .mission_context import MissionContext
from .mission_states import MissionState, MissionType, QrTaskStep
from .mission_transitions import evaluate_transitions, find_first_qr_step, find_next_qr_step


_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


class MissionFsmNode(Node):
    """
    Gorev seviyesi FSM node'u.

    Tek ornek calisir; lider drone'un companion computer'inda (Raspberry Pi) calisir.
    """

    def __init__(self) -> None:
        """
        MissionFsmNode'u baslatin.
        """
        super().__init__('mission_fsm')

        self._declare_params()

        self._ctx = MissionContext(
            agent_ids=self._agent_ids,
            team_id=self._team_id,
            sitl_mode=self._sitl_mode,
        )

        self._setup_publishers()
        self._setup_subscribers()
        self._setup_service()

        self._timer = self.create_timer(1.0 / self._tick_hz, self._tick)

        self.get_logger().info(
            f'MissionFsmNode basladi: agents={self._agent_ids} '
            f'team={self._team_id} sitl={self._sitl_mode}'
        )

    # =========================================================================
    # BASLANGIC METODLARI
    # =========================================================================

    def _declare_params(self) -> None:
        """
        ROS2 parametrelerini tanimlar ve okur.

        Ornek kullanim:
            ros2 run swarm_state_machine mission_fsm_node
                --ros-args -p agent_ids:=[1,2,3] -p sitl_mode:=true
        """
        self.declare_parameter('agent_ids', [1, 2, 3])
        self.declare_parameter('team_id', '')
        self.declare_parameter('tick_hz', 5.0)
        self.declare_parameter('sitl_mode', False)

        self._agent_ids: list = list(self.get_parameter('agent_ids').value)
        self._team_id: str = str(self.get_parameter('team_id').value)
        self._tick_hz: float = float(self.get_parameter('tick_hz').value)
        self._sitl_mode: bool = bool(self.get_parameter('sitl_mode').value)

    def _setup_publishers(self) -> None:
        """
        Yayin kanallarini (publisher) olusturur.

        /swarm/mission/state   (UInt8) -> mevcut MissionState; her tick yayinlanir
        /swarm/mission/qr_step (UInt8) -> mevcut QrTaskStep; EXECUTE_QR_TASK'ta anlamlidir
        /swarm/internal/events/system (SystemEvent) -> yasam dongusu olaylari
        """
        self._state_pub = self.create_publisher(
            UInt8, '/swarm/mission/state', _RELIABLE_QOS,
        )
        self._qr_step_pub = self.create_publisher(
            UInt8, '/swarm/mission/qr_step', _RELIABLE_QOS,
        )
        self._event_pub = self.create_publisher(
            SystemEvent, '/swarm/internal/events/system', _RELIABLE_QOS,
        )

    def _setup_subscribers(self) -> None:
        """
        Abonelik kanallarini (subscriber) olusturur.

        Her ajan icin ayri topic kullanilir; lambda'da a=aid ile deger sabitleniyor.
        Sabitlenmezse dongu bittikten sonra tum lambda'larda son aid degeri kaliyor.
        """
        for aid in self._agent_ids:
            self.create_subscription(
                AgentStatus,
                f'/swarm/public/drone{aid}/status',
                lambda msg, a=aid: self._on_agent_status(msg, a),
                10,
            )

        self.create_subscription(
            QRMissionData,
            '/swarm/perception/qr_data',
            self._on_qr_data,
            _RELIABLE_QOS,
        )

        self.create_subscription(
            SystemEvent,
            '/swarm/public/events/system',
            self._on_event,
            _RELIABLE_QOS,
        )

        self.create_subscription(
            SwarmControlCommand,
            '/swarm/control/command',
            self._on_control_cmd,
            10,
        )

    def _setup_service(self) -> None:
        """
        TriggerMission servis sunucusunu olusturur.

        Servis (topic yerine) kullanilir; GCS komutun alınıp alinmadigini dogrulayabilir.
        /swarm/mission/trigger -> TriggerMission.srv
        """
        self._trigger_srv = self.create_service(
            TriggerMission,
            '/swarm/mission/trigger',
            self._handle_trigger,
        )

    # =========================================================================
    # FSM ANA DONGUSU
    # =========================================================================

    def _tick(self) -> None:
        """
        5 Hz'de calisan FSM ana dongusu (her 200ms bir kez).

        Akis:
          1. evaluate_transitions(ctx) -> gecis var mi?
          2. Gecis varsa _transition() cagir
          3. Her tick _publish_state() cagir
          4. pending_command'i sifirla
        """
        ctx = self._ctx

        next_state = evaluate_transitions(ctx)

        if next_state is not None and next_state != ctx.state:
            self._transition(next_state)

        self._publish_state()

        terminal = (MissionState.ABORTED, MissionState.MISSION_COMPLETE)
        if ctx.state not in terminal:
            ctx.pending_command = 0

    def _transition(self, new_state: MissionState) -> None:
        """
        State gecisini uygular.

        Args:
            new_state: Gecilecek hedef MissionState.
        """
        old = self._ctx.state

        # set_state()'den once kaydet; set_state() ctx.state'i degistirir.
        if new_state == MissionState.PAUSED:
            self._ctx.pause_return_state = old

        self._ctx.set_state(new_state)

        if new_state == MissionState.ABORTED and not self._ctx.abort_reason:
            self._ctx.abort_reason = f'Timeout veya preflight hatasi ({old.name})'

        self.get_logger().info(f'[mission_fsm] {old.name} -> {new_state.name}')

        self._on_state_entry(new_state)

    def _on_state_entry(self, state: MissionState) -> None:
        """
        Yeni state'e girilince calisir; yasam dongusu eventleri yayinlar.

        BU FONKSIYON DRONA KOMUT VERMEZ.

        SYNCHRONIZED_TAKEOFF -> EVENT_MISSION_STARTED (agent_fsm'ler arm+kalkis yapar)
        EXECUTE_QR_TASK      -> ilk QR adimini belirle
        NAVIGATE_TO_QR       -> onceki QR verisini temizle
        WAIT_AT_QR           -> wait_deadline hesapla
        RETURN_HOME          -> EVENT_RTL_TRIGGERED (agent_fsm'ler RTL yapar)
        MISSION_COMPLETE     -> EVENT_MISSION_COMPLETED
        ABORTED              -> EVENT_EMERGENCY_LAND

        Args:
            state: Girilen yeni MissionState.
        """
        ctx = self._ctx

        if state == MissionState.SYNCHRONIZED_TAKEOFF:
            self._pub_event(
                SystemEvent.EVENT_MISSION_STARTED,
                SystemEvent.SEVERITY_INFO,
                f'Gorev {ctx.mission_type.name} baslatiuyor',
            )

        elif state == MissionState.EXECUTE_QR_TASK:
            if ctx.current_qr is not None:
                ctx.qr_task_step = find_first_qr_step(ctx.current_qr)
                self.get_logger().info(
                    f'[mission_fsm] QR gorevi basladi, ilk adim: {ctx.qr_task_step.name}'
                )
            else:
                ctx.qr_task_step = QrTaskStep.NONE
                self.get_logger().info('[mission_fsm] QR gorevi basladi, QR okunmasi bekleniyor')

        elif state == MissionState.NAVIGATE_TO_QR:
            # Yeni QR noktasina gidiyoruz; eski veri temizlenmelidir.
            # Temizlenmezse EXECUTE_QR_TASK'ta onceki QR gorevi yeniden calisir.
            self._ctx.current_qr = None

        elif state == MissionState.WAIT_AT_QR:
            wait_s = ctx.current_qr.wait_s if ctx.current_qr else 0.0
            ctx.wait_deadline = time.monotonic() + max(wait_s, 0.0)
            self.get_logger().info(f'[mission_fsm] QR bekleme: {wait_s:.1f}s')

        elif state == MissionState.RETURN_HOME:
            self._pub_event(
                SystemEvent.EVENT_RTL_TRIGGERED,
                SystemEvent.SEVERITY_WARNING,
                'Mission FSM RTL tetikledi',
            )

        elif state == MissionState.MISSION_COMPLETE:
            self._pub_event(
                SystemEvent.EVENT_MISSION_COMPLETED,
                SystemEvent.SEVERITY_INFO,
                'Gorev basariyla tamamlandi',
            )

        elif state == MissionState.ABORTED:
            self._pub_event(
                SystemEvent.EVENT_EMERGENCY_LAND,
                SystemEvent.SEVERITY_CRITICAL,
                f'Gorev iptal: {ctx.abort_reason}',
            )

    # =========================================================================
    # ABONELIK CALLBACK'LERI
    # =========================================================================

    def _on_agent_status(self, msg: AgentStatus, agent_id: int) -> None:
        """
        Ajan durumu mesajini ctx'e kaydeder.

        Args:
            msg: Gelen AgentStatus mesaji.
            agent_id: Hangi drone'dan geldigi.
        """
        self._ctx.agent_statuses[agent_id] = msg

    def _on_qr_data(self, msg: QRMissionData) -> None:
        """
        QR verisini filtreler ve gecerliyse ctx'e kaydeder.

        Filtreler (sirasıyla):
          1. team_id: baska takim QR'i -> yoksay
          2. decoded + valid: bozuk okuma -> yoksay
          3. qr_seq: eski mesaj (stale) -> yoksay

        Args:
            msg: Gelen QRMissionData mesaji.
        """
        if self._ctx.team_id == '':
            self.get_logger().warn(
                '[mission_fsm] team_id set edilmemis! Tum QR\'lar kabul ediliyor.',
                throttle_duration_sec=10.0,
            )
        elif msg.team_id != self._ctx.team_id:
            return

        if not msg.decoded or not msg.valid:
            return

        if msg.qr_seq <= self._ctx.last_accepted_qr_seq:
            self.get_logger().warn(
                f'[mission_fsm] Stale QR reddedildi: seq={msg.qr_seq}'
            )
            self._pub_event(
                SystemEvent.EVENT_QR_SEQUENCE_REJECTED,
                SystemEvent.SEVERITY_WARNING,
                f'Stale QR seq={msg.qr_seq}',
            )
            return

        self._ctx.last_accepted_qr_seq = msg.qr_seq
        self._ctx.current_qr = msg
        self.get_logger().info(
            f'[mission_fsm] QR kabul: seq={msg.qr_seq} '
            f'formation={msg.formation_active} maneuver={msg.maneuver_active}'
        )

        # EXECUTE_QR_TASK'tayken QR gecikmeyle geldiyse adimi simdi baslat.
        if (self._ctx.state == MissionState.EXECUTE_QR_TASK
                and self._ctx.qr_task_step == QrTaskStep.NONE):
            self._ctx.qr_task_step = find_first_qr_step(msg)
            self.get_logger().info(
                f'[mission_fsm] EXECUTE_QR_TASK: ilk adim: {self._ctx.qr_task_step.name}'
            )

    def _on_event(self, msg: SystemEvent) -> None:
        """
        Suruden gelen sistem eventlerini dinler ve ctx'i gunceller.

        EVENT_FORMATION_REACHED:
          -> NAVIGATE_TO_QR: event_formation_reached=True
          -> EXECUTE_QR_TASK + FORMATION/ALTITUDE: adimi ilerlet

        EVENT_ROTATION_COMPLETED:
          -> ROTATE_TO_NEXT: event_rotation_completed=True

        EVENT_MANEUVER_COMPLETED:
          -> EXECUTE_QR_TASK + MANEUVER: adimi ilerlet

        EVENT_MANEUVER_FAILED / EVENT_FORMATION_FAILED / EVENT_MEMBER_MANAGEMENT_FAILED:
          -> action_done=True, action_success=False -> RETURN_HOME

        EVENT_AGENT_DETACHED:
          -> EXECUTE_QR_TASK + DETACH: adimi ilerlet

        Args:
            msg: Gelen SystemEvent mesaji.
        """
        eid = msg.event_type
        ctx = self._ctx

        if eid == SystemEvent.EVENT_FORMATION_REACHED:
            if ctx.state == MissionState.NAVIGATE_TO_QR:
                ctx.event_formation_reached = True
            elif ctx.state == MissionState.EXECUTE_QR_TASK:
                if ctx.qr_task_step in (QrTaskStep.FORMATION, QrTaskStep.ALTITUDE):
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

    def _on_control_cmd(self, msg: SwarmControlCommand) -> None:
        """
        Gorev 2 joystick komutunu ctx'e kaydeder.

        command_valid ve deadman_pressed ikisi birden True olmalidir.

        Args:
            msg: Gelen SwarmControlCommand mesaji.
        """
        if msg.command_valid and msg.deadman_pressed:
            self._ctx.latest_control_cmd = msg
            self._ctx.last_control_cmd_time = time.monotonic()

    # =========================================================================
    # QR ADIM TAKIBI
    # =========================================================================

    def _advance_qr_step(self) -> None:
        """
        Tamamlanan QR adimından sonraki adima gecer.

        Sartname sirasi: FORMATION -> MANEUVER -> ALTITUDE -> DETACH -> DONE
        DONE olunca _from_execute_qr_task() bir sonraki state'e gecer.
        """
        ctx = self._ctx
        next_step = find_next_qr_step(ctx.current_qr, ctx.qr_task_step)
        ctx.qr_task_step = next_step
        self.get_logger().info(f'[mission_fsm] QR adim: {next_step.name}')

    # =========================================================================
    # SERVIS HANDLER
    # =========================================================================

    def _handle_trigger(
        self,
        request: TriggerMission.Request,
        response: TriggerMission.Response,
    ) -> TriggerMission.Response:
        """
        TriggerMission.srv GCS istegini isler.

        START ozeli isleme:
          - IDLE state'inde degilsek reddedilir
          - mission_id MissionType'a donusturulur
          - team_id gonderildiyse guncellenir

        Args:
            request: Gelen servis istegi.
            response: Doldurulup geri gonderilecek yanit.

        Returns:
            Doldurulmus TriggerMission.Response.
        """
        ctx = self._ctx
        cmd = request.command

        if cmd == TriggerMission.Request.COMMAND_START:
            if ctx.state != MissionState.IDLE:
                response.success = False
                response.message = f'START reddedildi: state={ctx.state.name}'
                return response

            try:
                mission_type = MissionType(request.mission_id)
            except ValueError:
                response.success = False
                response.message = f'Gecersiz mission_id: {request.mission_id}'
                return response

            if mission_type == MissionType.UNKNOWN:
                response.success = False
                response.message = 'mission_id=0 (UNKNOWN) ile gorev baslatilamaz'
                return response

            ctx.mission_type = mission_type

            if request.team_id:
                ctx.team_id = request.team_id

        elif cmd == TriggerMission.Request.COMMAND_ABORT:
            ctx.abort_reason = 'GCS abort komutu'

        ctx.pending_command = cmd

        response.success = True
        response.message = f'Komut alindi: cmd={cmd}'
        self.get_logger().info(
            f'[mission_fsm] TriggerMission: cmd={cmd} mission={request.mission_id}'
        )
        return response

    # =========================================================================
    # YARDIMCI METODLAR
    # =========================================================================

    def _publish_state(self) -> None:
        """
        Mevcut mission state ve QR adimini topic'lere yayinlar.

        Her tick cagrilir; state degismese de yayinlanir.
        Yeni baslayan bir icra node'u boylece hemen senkron olur.
        """
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
        """
        SystemEvent mesaji olusturup /swarm/internal/events/system'e yayinlar.

        Args:
            event_type: SystemEvent.EVENT_* integer sabiti.
            severity: SystemEvent.SEVERITY_* seviyesi.
            message: Istege bagli aciklama.
            target_agent_id: Hedef ajan ID; 0 = tum suru.
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
# GIRIS NOKTASI
# =============================================================================

def main(args=None) -> None:
    """
    ros2 run komutu bu fonksiyonu cagirır.
    """
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
