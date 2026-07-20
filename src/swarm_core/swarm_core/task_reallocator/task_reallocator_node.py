# Copyright 2026 Yelpence
"""Rol yeniden dagitim dugumu."""

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
    """Rol yeniden dagitimini ROS 2 ortaminda yoneten dugum."""

    def __init__(self) -> None:
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

        self._last_seen: dict[int, float] = {}
        self._agent_emergency: dict[int, bool] = {}
        self._emergency = False

        self._consensus_leader: int | None = None
        self._last_election_round = -1
        self._last_election_seq = 0
        self._last_heartbeat_time = 0.0
        self._hb_timeout_s = float(self._gp('leader_heartbeat_timeout_s'))

        self._setup_interfaces()
        self.get_logger().info(
            f'task_reallocator hazir: agents={self._agent_ids}'
        )

    def _declare_params(self) -> None:
        """ROS parametrelerini tanımlar."""
        self.declare_parameter('agent_ids', [1, 2, 3])
        self.declare_parameter('stale_timeout_s', 1.0)
        self.declare_parameter('leader_heartbeat_timeout_s', 0.5)
        self.declare_parameter('min_active_for_formation', 3)
        self.declare_parameter('min_active_for_navigation', 2)
        self.declare_parameter('pinned_leader_id', 0)

    def _gp(self, name: str):
        """Parametre degerini okur."""
        return self.get_parameter(name).value

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

        self._role_clients = {}
        for agent_id in self._agent_ids:
            srv = '/swarm/agent/%d/assign_role' % agent_id
            self._role_clients[agent_id] = self.create_client(
                AssignRole, srv
            )

    def _on_status(self, msg: AgentStatus) -> None:
        """Telemetri verilerini roster uzerinde gunceller."""
        agent_id = int(msg.agent_id)
        if agent_id <= 0 or agent_id not in self._agent_ids:
            return
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
        """Sistem olaylarına gore rol guncellemelerini tetikler."""
        if self._emergency:
            return
        event_type = int(msg.event_type)
        target = int(msg.target_agent_id)
        if event_type in _DETACH_EVENTS and target > 0:
            self._handle_detach(target)
        elif event_type in _REJOIN_EVENTS and target > 0:
            self._handle_rejoin(target)

    def _on_election(self, msg: ElectionResult) -> None:
        """Consensus lider sonucunu tabloya yansitir."""
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
        """Lider heartbeat sinyalini takip eder."""
        self._last_heartbeat_time = time.monotonic()
        leader = int(msg.leader_id)
        if leader > 0 and leader != self._consensus_leader:
            self._consensus_leader = leader
            self._refresh_freshness()
            result = self._core.apply_leader(leader)
            self._apply(result, 'heartbeat')

    def _handle_detach(self, target_id: int) -> None:
        """Ayrilma durumunda tablolari gunceller."""
        self._refresh_freshness()
        det = self._core.detach(target_id)
        self._apply(det, 'detach:%d' % target_id)
        if not self._core.has_leader() and not self._consensus_alive():
            el = self._core.elect_leader()
            if el.changed_ids:
                self._apply(el, 'fallback_election')

    def _handle_rejoin(self, target_id: int) -> None:
        """Geri donus durumunda tablolari gunceller."""
        self._refresh_freshness()
        rej = self._core.rejoin(target_id)
        self._apply(rej, 'rejoin:%d' % target_id)

    def _apply(self, reallocation, reason: str) -> None:
        """Rol degisim kararlarini AssignRole ile servis eder."""
        for note in reallocation.notes:
            self.get_logger().warning('[%s] not: %s' % (reason, note))
        for agent_id in reallocation.changed_ids:
            role = reallocation.role_map.get(agent_id)
            if role is not None:
                self._send_role(agent_id, role, reason)

    def _send_role(self, agent_id: int, role: int, reason: str) -> None:
        """Asenkron servis cagrisi ile yeni rolu gonderir."""
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
        """Rol atama servis yanıtını dogrular."""
        try:
            result = future.result()
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error('AssignRole cagri hatasi: %s' % exc)
            return
        if result is not None and not result.success:
            self.get_logger().warning(
                'AssignRole reddedildi: %s' % result.message
            )

    def _consensus_alive(self) -> bool:
        """Consensus'un aktif olup olmadigini doner."""
        if self._last_heartbeat_time <= 0.0:
            return False
        elapsed = time.monotonic() - self._last_heartbeat_time
        return elapsed <= self._hb_timeout_s

    def _refresh_freshness(self) -> None:
        """Ajanlarin telemetri tazelik durumlarini gunceller."""
        now = time.monotonic()
        for agent_id in self._agent_ids:
            entry = self._core.get_entry(agent_id)
            if entry is None:
                continue
            last = self._last_seen.get(agent_id, 0.0)
            entry.fresh = (now - last) <= self._stale_timeout_s


def main(args=None) -> None:
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
