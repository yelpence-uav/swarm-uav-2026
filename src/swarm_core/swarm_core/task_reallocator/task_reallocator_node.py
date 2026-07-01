"""task_reallocator_node.py — Rol/slot yeniden dağıtım ROS 2 düğümü.

Lider drone üzerinde (onboard) koşar. AgentStatus telemetrisinden roster'ı
besler, member-management SystemEvent'lerine tepki verir ve çekirdeğin
(``task_reallocator_core``) ürettiği kararı iki kanaldan yayar:

  1. Rol değişimi → her ilgili ajana ``AssignRole.srv`` (ASENKRON çağrı).
  2. Slot ataması → ``FormationCommand`` (CUSTOM offset'ler) ayrı bir
     "reallocation/assignment" topic'ine; mission_fsm bunu okuyup merkez/
     heading ekleyerek yetkili komutu basar (tek-yazıcı kuralı korunur).

EMNİYET TASARIM NOTLARI (risk raporu eşlemesi):
  K1 — AssignRole ``call_async`` ile çağrılır; callback içinde spin/bekleme
       YOK → tek-thread'li executor donmaz.
  K2 — Konum/origin/EKF/tazelik uygunluğu çekirdeğe bayrak olarak geçer;
       uygun olmayan ajan atamaya girmez.
  O5 — Tazelik ``time.monotonic()`` alış anına göre hesaplanır (clock skew
       bağışık); başka drone'un stamp'ine güvenilmez.
  O6 — Acil durum (failsafe/kill) sürerken yeni atama yayını yapılmaz.
"""

from __future__ import annotations

import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

from swarm_core.task_reallocator.task_reallocator_core import (
    ReallocatorParams,
    STATE_STANDBY,
    TaskReallocator,
)
from swarm_interfaces.msg import (
    AgentStatus,
    ElectionResult,
    FormationCommand,
    SystemEvent,
)
from swarm_interfaces.srv import AssignRole


# Tetikleyici member-management olayları (SystemEvent.event_type).
_EVENT_AGENT_DETACHED = 3
_EVENT_AGENT_REJOINED = 5
_EVENT_MEMBER_DETACH_STARTED = 35
_EVENT_MEMBER_REJOIN_STARTED = 36

_DETACH_EVENTS = frozenset({
    _EVENT_AGENT_DETACHED, _EVENT_MEMBER_DETACH_STARTED,
})
_REJOIN_EVENTS = frozenset({
    _EVENT_AGENT_REJOINED, _EVENT_MEMBER_REJOIN_STARTED,
})


class TaskReallocatorNode(Node):
    """Yeniden-dağıtım çekirdeğini ROS 2 mesajlarına bağlayan düğüm."""

    def __init__(self) -> None:
        """Parametreleri, çekirdeği, abonelikleri ve yayıncıyı kurar."""
        super().__init__('task_reallocator_node')

        self._declare_params()
        params = ReallocatorParams(
            formation_size=int(self._gp('formation_size')),
            spacing_m=float(self._gp('spacing_m')),
            alpha_deg=float(self._gp('alpha_deg')),
            min_active_for_formation=int(
                self._gp('min_active_for_formation')
            ),
            min_active_for_navigation=int(
                self._gp('min_active_for_navigation')
            ),
        )
        self._core = TaskReallocator(params)

        self._agent_ids = [int(a) for a in self._gp('agent_ids')]
        self._formation_type = int(self._gp('formation_type'))
        self._heading_rad = math.radians(float(self._gp('heading_deg')))
        self._stale_timeout_s = float(self._gp('stale_timeout_s'))
        pinned = int(self._gp('pinned_leader_id'))
        self._pinned_leader = pinned if pinned > 0 else None
        # İlk formasyon için gereken uygun ajan sayısı (0 => formation_size).
        req = int(self._gp('agents_required'))
        self._agents_required = req if req > 0 else params.formation_size

        # agent_id -> son telemetri alış anı (monotonic).
        self._last_seen: dict[int, float] = {}
        self._formation_assigned = False
        self._seq = 0
        # Acil durum LATCH DEĞİL: her ajanın anlık durumu izlenir; global
        # bayrak bunlardan türetilir (drone toparlayınca modül geri açılır).
        self._agent_emergency: dict[int, bool] = {}
        self._emergency = False

        # Consensus (Beyza) ElectionResult'tan gelen lider — biz SEÇMEYİZ.
        self._consensus_leader: int | None = None
        self._last_election_round = -1
        self._last_election_seq = 0

        self._setup_interfaces()
        self.get_logger().info(
            'task_reallocator hazir: agents=%s formation_size=%d'
            % (self._agent_ids, params.formation_size)
        )

    # ------------------------------------------------------------------ #
    #  Parametre yardımcıları                                             #
    # ------------------------------------------------------------------ #
    def _declare_params(self) -> None:
        """Tüm ROS parametrelerini varsayılanlarıyla tanımlar."""
        self.declare_parameter('agent_ids', [1, 2, 3])
        self.declare_parameter('formation_size', 3)
        self.declare_parameter('agents_required', 0)  # 0 = formation_size
        self.declare_parameter('spacing_m', 5.0)
        self.declare_parameter('alpha_deg', 45.0)
        self.declare_parameter('formation_type', 1)  # 1=OKBASI
        self.declare_parameter('heading_deg', 0.0)
        self.declare_parameter('stale_timeout_s', 1.0)
        self.declare_parameter('min_active_for_formation', 3)
        self.declare_parameter('min_active_for_navigation', 2)
        self.declare_parameter('pinned_leader_id', 0)  # 0 = sabitleme yok
        self.declare_parameter(
            'assignment_topic', '/swarm/internal/reallocation/assignment'
        )

    def _gp(self, name: str):
        """Parametre değerini döner (kısa yardımcı)."""
        return self.get_parameter(name).value

    # ------------------------------------------------------------------ #
    #  Arayüz kurulumu                                                    #
    # ------------------------------------------------------------------ #
    def _setup_interfaces(self) -> None:
        """Abonelikleri, yayıncıyı ve servis istemcilerini kurar."""
        status_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )
        event_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )
        assign_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        self._status_subs = []
        for agent_id in self._agent_ids:
            topic = '/swarm/public/drone%d/status' % agent_id
            sub = self.create_subscription(
                AgentStatus, topic, self._on_status, status_qos
            )
            self._status_subs.append(sub)

        self._event_sub = self.create_subscription(
            SystemEvent, '/swarm/public/events/system',
            self._on_event, event_qos,
        )

        # Consensus lider sonucu — latched (TRANSIENT_LOCAL), geç katılan alır.
        self._election_sub = self.create_subscription(
            ElectionResult, '/swarm/public/election/result',
            self._on_election, assign_qos,
        )

        # Aktif formasyon komutu — güncel tip/mesafe/yönü ÖĞRENMEK için
        # (formation_control yayınlar; biz yalnızca okuruz, değiştirmeyiz).
        self._formation_sub = self.create_subscription(
            FormationCommand, '/swarm/public/formation/target',
            self._on_formation_command, event_qos,
        )

        self._assignment_pub = self.create_publisher(
            FormationCommand, str(self._gp('assignment_topic')), assign_qos
        )

        # Ajan başına AssignRole istemcisi.
        self._role_clients: dict[int, rclpy.client.Client] = {}
        for agent_id in self._agent_ids:
            srv = '/swarm/agent/%d/assign_role' % agent_id
            self._role_clients[agent_id] = self.create_client(
                AssignRole, srv
            )

    # ------------------------------------------------------------------ #
    #  Callback'ler                                                       #
    # ------------------------------------------------------------------ #
    def _on_status(self, msg: AgentStatus) -> None:
        """Telemetriyi (AgentStatus) roster'a işler (atama TETİKLEMEZ).

        Yalnızca defter güncellenir (O(1)). Acil durum bayrağı burada
        izlenir. İlk formasyon ataması için hazırlık kontrolü yapılır.
        """
        agent_id = int(msg.agent_id)
        if agent_id <= 0 or agent_id not in self._agent_ids:
            return  # sistem/bilinmeyen id (0 veya listede yok) — yok say
        self._last_seen[agent_id] = time.monotonic()

        pos_valid = bool(msg.xy_valid) and bool(msg.estimator_ok)
        self._core.update_agent(
            agent_id,
            state=int(msg.state),
            pos_x=float(msg.pos_x),
            pos_y=float(msg.pos_y),
            origin_synced=bool(msg.origin_synced),
            pos_valid=pos_valid,
            fresh=True,
        )

        # Anlık acil durum (LATCH DEĞİL): global bayrak her ajanın son
        # durumundan türetilir → drone toparlayınca modül geri açılır.
        self._agent_emergency[agent_id] = (
            bool(msg.failsafe_active) or bool(msg.kill_switch_active)
        )
        self._emergency = any(self._agent_emergency.values())

        self._maybe_initial_assign()

    def _on_event(self, msg: SystemEvent) -> None:
        """Member-management olaylarında yeniden dağıtımı tetikler."""
        if self._emergency:
            # O6: acil durumda yeni atama yayını yapma.
            return
        event_type = int(msg.event_type)
        target = int(msg.target_agent_id)
        if event_type in _DETACH_EVENTS and target > 0:
            self._handle_detach(target)
        elif event_type in _REJOIN_EVENTS and target > 0:
            self._handle_rejoin(target)

    def _on_election(self, msg: ElectionResult) -> None:
        """Consensus lider sonucunu UYGULAR (lideri SEÇMEZ).

        Lider KARARI consensus'undur (Beyza). Biz yalnızca rol defterine
        yansıtır ve slot atamasını yeniden yayınlarız. Lider rolü için
        AssignRole GÖNDERMEYİZ — onu consensus duyurur. Eski round/sequence
        mesajları yok sayılır.
        """
        rnd = int(msg.election_round)
        seq = int(msg.sequence_num)
        is_stale = rnd < self._last_election_round or (
            rnd == self._last_election_round
            and seq <= self._last_election_seq
        )
        if is_stale:
            return
        self._last_election_round = rnd
        self._last_election_seq = seq
        self._consensus_leader = int(msg.new_leader_id)
        self._refresh_freshness()
        result = self._core.apply_leader(self._consensus_leader)
        for note in result.notes:
            self.get_logger().info('[election] %s' % note)
        if result.changed_ids:
            self._publish_assignment('election')

    def _on_formation_command(self, msg: FormationCommand) -> None:
        """Aktif formasyon tipi/mesafe/yönünü ÖĞRENİR (formasyonu SAHİPLENMEZ).

        formation_control/mission_fsm formasyonu değiştirince (QR: ok→V,
        mesafe 5→3) buradan haberdar oluruz; böylece SONRAKİ üye değişiminde
        katılan İHA'yı GÜNCEL formasyona göre yerleştiririz. Formasyonu biz
        DEĞİŞTİRMEYİZ veya yeniden dağıtmayız — yalnızca okuruz.

        Not: kendi atama yayınımız ayrı topic'tedir; bu callback onu
        tüketmez (geri besleme döngüsü yok).
        """
        if int(msg.formation_type) != 0:
            self._formation_type = int(msg.formation_type)
        if float(msg.spacing_m) > 0.0:
            self._core.p.spacing_m = float(msg.spacing_m)
        self._heading_rad = math.radians(float(msg.heading_deg))

    # ------------------------------------------------------------------ #
    #  Karar akışları                                                     #
    # ------------------------------------------------------------------ #
    def _maybe_initial_assign(self) -> None:
        """Yeterli uygun aktif ajan hazır olunca formasyonu bir kez atar.

        'Yeterli' eşiği ``agents_required`` (0 ise formation_size). Böylece
        ilk telemetride tek drone'la formasyon kurulmaz; tüm sürü hazır
        olana dek beklenir (eksik-drone formasyonu önlenir).
        """
        if self._formation_assigned or self._emergency:
            return
        if self._core.active_ranked_ids():
            return
        self._refresh_freshness()
        if self._core.eligible_active_count() < self._agents_required:
            return
        r = self._core.assign_formation(
            self._formation_type, self._heading_rad,
            pinned_leader=self._leader_hint(),
        )
        if r.rank_map:
            self._formation_assigned = True
            self._apply(r, 'initial_assignment')

    def _handle_detach(self, target_id: int) -> None:
        """Ayrılma olayını işler; yedek varsa devreye sokar."""
        self._refresh_freshness()
        det = self._core.detach(target_id)
        self._apply(det, 'detach:%d' % target_id)
        if self._has_standby():
            rep = self._core.replace_with_standby(
                self._formation_type, det.vacated_rank
            )
            if rep.changed_ids:
                self._apply(rep, 'replace_standby')
        # Lider SEÇİMİ consensus'un (Beyza) işidir; ElectionResult ile gelir.
        # Yalnızca consensus HİÇ konuşmadıysa (lider hiç bilinmiyor) son çare
        # olarak en küçük id'li güvenli ajanı yedek seçeriz.
        if not self._core.has_leader() and self._consensus_leader is None:
            el = self._core.elect_leader()
            if el.changed_ids:
                self._apply(el, 'fallback_election')

    def _handle_rejoin(self, target_id: int) -> None:
        """Katılma olayını işler; en küçük boş rank'e oturtur."""
        self._refresh_freshness()
        rej = self._core.rejoin(target_id, self._formation_type)
        self._apply(rej, 'rejoin:%d' % target_id)

    # ------------------------------------------------------------------ #
    #  Çıktı uygulama                                                     #
    # ------------------------------------------------------------------ #
    def _apply(self, reallocation, reason: str) -> None:
        """Reallocation kararını AssignRole + atama yayınına döker."""
        for note in reallocation.notes:
            self.get_logger().warning('[%s] not: %s' % (reason, note))
        for agent_id in reallocation.changed_ids:
            role = reallocation.role_map.get(agent_id)
            if role is not None:
                self._send_role(agent_id, role, reason)
        if reallocation.changed_ids:
            self._publish_assignment(reason)

    def _send_role(self, agent_id: int, role: int, reason: str) -> None:
        """Rol atamasını ASENKRON servis çağrısıyla gönderir (bloklamaz)."""
        client = self._role_clients.get(agent_id)
        if client is None:
            return
        if not client.service_is_ready():
            self.get_logger().warning(
                'AssignRole hazir degil: agent=%d' % agent_id
            )
            return
        req = AssignRole.Request()
        req.target_agent_id = agent_id
        req.role = int(role)
        req.reason = reason
        future = client.call_async(req)
        future.add_done_callback(self._on_role_response)

    def _on_role_response(self, future) -> None:
        """Servis (AssignRole) yanıtını loglar (hata sessizce yutulmaz)."""
        try:
            result = future.result()
        except Exception as exc:  # noqa: BLE001 — servis hatasini raporla
            self.get_logger().error('AssignRole cagri hatasi: %s' % exc)
            return
        if result is not None and not result.success:
            self.get_logger().warning(
                'AssignRole reddedildi: %s' % result.message
            )

    def _publish_assignment(self, reason: str) -> None:
        """Güncel slot atamasını FormationCommand (CUSTOM) olarak yayınlar."""
        ids, ox, oy, oz = self._core.build_custom_offsets(
            self._formation_type
        )
        if not ids:
            return
        msg = FormationCommand()
        msg.stamp = self.get_clock().now().to_msg()
        self._seq += 1
        msg.sequence_num = self._seq
        msg.formation_type = self._formation_type
        msg.use_current_centroid = True
        msg.use_current_altitude = True
        msg.agent_ids = [int(i) for i in ids]
        msg.offset_x = [float(v) for v in ox]
        msg.offset_y = [float(v) for v in oy]
        msg.offset_z = [float(v) for v in oz]
        msg.source_module = 'task_reallocator'
        self._assignment_pub.publish(msg)
        self.get_logger().info(
            '[%s] atama yayinlandi: %d ajan' % (reason, len(ids))
        )

    # ------------------------------------------------------------------ #
    #  Yardımcılar                                                        #
    # ------------------------------------------------------------------ #
    def _refresh_freshness(self) -> None:
        """Her ajanın tazelik bayrağını monotonic alış anına göre günceller."""
        now = time.monotonic()
        for agent_id in self._agent_ids:
            entry = self._core.get_entry(agent_id)
            if entry is None:
                continue
            last = self._last_seen.get(agent_id, 0.0)
            entry.fresh = (now - last) <= self._stale_timeout_s

    def _leader_hint(self) -> int | None:
        """Lider ipucu: consensus kararı varsa o, yoksa manuel pinned param."""
        if self._consensus_leader is not None:
            return self._consensus_leader
        return self._pinned_leader if self._pinned_leader else None

    def _has_standby(self) -> bool:
        """Uygun (taze + origin) en az bir yedek olup olmadığını döner."""
        for agent_id in self._agent_ids:
            entry = self._core.get_entry(agent_id)
            if (
                entry is not None
                and entry.state == STATE_STANDBY
                and entry.fresh
                and entry.origin_synced
            ):
                return True
        return False


def main(args=None) -> None:
    """Düğümü başlatır ve spin eder."""
    rclpy.init(args=args)
    node = TaskReallocatorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
