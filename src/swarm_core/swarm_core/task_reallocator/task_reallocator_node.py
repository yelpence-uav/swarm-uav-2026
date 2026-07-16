"""task_reallocator_node.py — Rol yeniden dağıtım ROS 2 düğümü (geometrisiz).

Slot/offset hesabı YOKTUR; onu dağıtık olarak formation_control yapar. Bu
düğüm yalnızca ROL dağıtır: AgentStatus dinler, member-management olayları
(SystemEvent detach/rejoin) ve consensus lider sonucu (ElectionResult) ile
her ilgili ajana AssignRole (ASENKRON) gönderir.

EMNİYET NOTLARI:
  - AssignRole ``call_async`` ile çağrılır; callback içinde bekleme yok →
    tek-thread'li executor donmaz.
  - Tazelik ``time.monotonic()`` alış anına göre (clock skew bağışık).
  - Acil durum LATCH DEĞİL: her ajanın anlık durumundan türetilir →
    drone toparlayınca modül geri açılır.
"""

from __future__ import annotations

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
    TaskReallocator,
)
from swarm_interfaces.msg import (
    AgentStatus,
    ElectionResult,
    LeaderHeartbeat,
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
    """Rol yeniden dağıtım çekirdeğini ROS 2 mesajlarına bağlayan düğüm."""

    def __init__(self) -> None:
        """Parametreleri, çekirdeği, abonelikleri ve istemcileri kurar."""
        super().__init__('task_reallocator_node')

        self._declare_params()
        params = ReallocatorParams(
            min_active_for_formation=int(
                self._gp('min_active_for_formation')
            ),
            min_active_for_navigation=int(
                self._gp('min_active_for_navigation')
            ),
        )
        self._core = TaskReallocator(params)

        self._agent_ids = [int(a) for a in self._gp('agent_ids')]
        self._stale_timeout_s = float(self._gp('stale_timeout_s'))
        pinned = int(self._gp('pinned_leader_id'))
        self._pinned_leader = pinned if pinned > 0 else None

        # agent_id -> son telemetri alış anı (monotonic).
        self._last_seen: dict[int, float] = {}
        # agent_id -> anlık acil durum (latch DEĞİL).
        self._agent_emergency: dict[int, bool] = {}
        self._emergency = False

        # Consensus (Beyza) ElectionResult'tan gelen lider — biz SEÇMEYİZ.
        self._consensus_leader: int | None = None
        self._last_election_round = -1
        self._last_election_seq = 0
        # Consensus canlılık takibi (heartbeat). 0 = hiç heartbeat gelmedi.
        self._last_heartbeat_time = 0.0
        self._hb_timeout_s = float(self._gp('leader_heartbeat_timeout_s'))

        self._setup_interfaces()
        self.get_logger().info(
            'task_reallocator hazir (rol modu): agents=%s' % self._agent_ids
        )

    # ------------------------------------------------------------------ #
    #  Parametre yardımcıları                                             #
    # ------------------------------------------------------------------ #
    def _declare_params(self) -> None:
        """Tüm ROS parametrelerini varsayılanlarıyla tanımlar."""
        self.declare_parameter('agent_ids', [1, 2, 3])
        self.declare_parameter('stale_timeout_s', 1.0)
        # Consensus heartbeat zamanaşımı: bu süre kadar heartbeat gelmezse
        # consensus 'ölü' sayılır → yedek lider seçimi devreye girer.
        self.declare_parameter('leader_heartbeat_timeout_s', 0.5)
        self.declare_parameter('min_active_for_formation', 3)
        self.declare_parameter('min_active_for_navigation', 2)
        self.declare_parameter('pinned_leader_id', 0)  # 0 = sabitleme yok

    def _gp(self, name: str):
        """Parametre değerini döner (kısa yardımcı)."""
        return self.get_parameter(name).value

    # ------------------------------------------------------------------ #
    #  Arayüz kurulumu                                                    #
    # ------------------------------------------------------------------ #
    def _setup_interfaces(self) -> None:
        """Abonelikleri ve AssignRole istemcilerini kurar."""
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
        election_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        self._status_subs = []
        for agent_id in self._agent_ids:
            topic = '/swarm/public/drone%d/status' % agent_id
            self._status_subs.append(self.create_subscription(
                AgentStatus, topic, self._on_status, status_qos
            ))

        self._event_sub = self.create_subscription(
            SystemEvent, '/swarm/public/events/system',
            self._on_event, event_qos,
        )
        self._election_sub = self.create_subscription(
            ElectionResult, '/swarm/public/election/result',
            self._on_election, election_qos,
        )
        hb_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )
        self._heartbeat_sub = self.create_subscription(
            LeaderHeartbeat, '/swarm/public/leader/heartbeat',
            self._on_heartbeat, hb_qos,
        )

        self._role_clients: dict[int, rclpy.client.Client] = {}
        for agent_id in self._agent_ids:
            srv = '/swarm/agent/drone%d/assign_role' % agent_id
            self._role_clients[agent_id] = self.create_client(
                AssignRole, srv
            )

    # ------------------------------------------------------------------ #
    #  Callback'ler                                                       #
    # ------------------------------------------------------------------ #
    def _on_status(self, msg: AgentStatus) -> None:
        """Telemetriyi (AgentStatus) roster'a işler (rol tetiklemez).

        Yalnızca defter güncellenir (O(1)) ve yerdeki yedeklerin rolü
        senkronlanır. Acil durum bayrağı buradan türetilir.
        """
        agent_id = int(msg.agent_id)
        if agent_id <= 0 or agent_id not in self._agent_ids:
            return  # sistem/bilinmeyen id — yok say
        self._last_seen[agent_id] = time.monotonic()
        self._core.update_agent(
            agent_id,
            state=int(msg.state),
            origin_synced=bool(msg.origin_synced),
            fresh=True,
        )
        self._agent_emergency[agent_id] = (
            bool(msg.failsafe_active) or bool(msg.kill_switch_active)
        )
        self._emergency = any(self._agent_emergency.values())

        standby = self._core.sync_standby_roles()
        if standby.changed_ids:
            self._apply(standby, 'standby_sync')

    def _on_event(self, msg: SystemEvent) -> None:
        """Member-management olaylarında rol dağıtımını tetikler."""
        if self._emergency:
            return  # acil durumda yeni atama yapma
        event_type = int(msg.event_type)
        target = int(msg.target_agent_id)
        if event_type in _DETACH_EVENTS and target > 0:
            self._handle_detach(target)
        elif event_type in _REJOIN_EVENTS and target > 0:
            self._handle_rejoin(target)

    def _on_election(self, msg: ElectionResult) -> None:
        """Consensus lider sonucunu UYGULAR (lideri SEÇMEZ).

        Lider KARARI consensus'undur (Beyza). Eski round/sequence mesajları
        yok sayılır. Uygulanan lider AssignRole ile ilgili ajanlara işlenir.
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
        self._apply(result, 'election')

    def _on_heartbeat(self, msg: LeaderHeartbeat) -> None:
        """Consensus canlılığını (heartbeat) izler; lider değişimini uygular.

        Heartbeat consensus'un 10 Hz aliveness sinyalidir. Alış anı
        kaydedilir; heartbeat'teki lider bildiğimizden farklıysa uygulanır
        (kaçan ElectionResult'ı yakalar). Uçuş ortasında heartbeat kesilince
        consensus 'ölü' sayılır ve yedek seçim devreye girebilir.
        """
        self._last_heartbeat_time = time.monotonic()
        leader = int(msg.leader_id)
        if leader > 0 and leader != self._consensus_leader:
            self._consensus_leader = leader
            self._refresh_freshness()
            result = self._core.apply_leader(leader)
            self._apply(result, 'heartbeat')

    # ------------------------------------------------------------------ #
    #  Karar akışları                                                     #
    # ------------------------------------------------------------------ #
    def _handle_detach(self, target_id: int) -> None:
        """Ayrılma olayını işler (rol DETACHED); gerekirse yedek lider seçer."""
        self._refresh_freshness()
        det = self._core.detach(target_id)
        self._apply(det, 'detach:%d' % target_id)
        # Lider SEÇİMİ consensus'un işi. Yalnızca consensus SUSMUŞSA (heartbeat
        # zamanaşımı — hiç başlamadı VEYA uçuş ortasında öldü) son çare olarak
        # en küçük id'li üyeyi yedek seçeriz.
        if not self._core.has_leader() and not self._consensus_alive():
            el = self._core.elect_leader()
            if el.changed_ids:
                self._apply(el, 'fallback_election')

    def _handle_rejoin(self, target_id: int) -> None:
        """Katılma olayını işler (rol FOLLOWER)."""
        self._refresh_freshness()
        rej = self._core.rejoin(target_id)
        self._apply(rej, 'rejoin:%d' % target_id)

    # ------------------------------------------------------------------ #
    #  Çıktı uygulama                                                     #
    # ------------------------------------------------------------------ #
    def _apply(self, reallocation, reason: str) -> None:
        """Reallocation kararını AssignRole çağrılarına döker."""
        for note in reallocation.notes:
            self.get_logger().warning('[%s] not: %s' % (reason, note))
        for agent_id in reallocation.changed_ids:
            role = reallocation.role_map.get(agent_id)
            if role is not None:
                self._send_role(agent_id, role, reason)

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

    # ------------------------------------------------------------------ #
    #  Yardımcılar                                                        #
    # ------------------------------------------------------------------ #
    def _consensus_alive(self) -> bool:
        """Consensus'un son heartbeat'i zamanaşımı içindeyse True döner."""
        if self._last_heartbeat_time <= 0.0:
            return False
        elapsed = time.monotonic() - self._last_heartbeat_time
        return elapsed <= self._hb_timeout_s

    def _refresh_freshness(self) -> None:
        """Her ajanın tazelik bayrağını monotonic alış anına göre günceller."""
        now = time.monotonic()
        for agent_id in self._agent_ids:
            entry = self._core.get_entry(agent_id)
            if entry is None:
                continue
            last = self._last_seen.get(agent_id, 0.0)
            entry.fresh = (now - last) <= self._stale_timeout_s


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
