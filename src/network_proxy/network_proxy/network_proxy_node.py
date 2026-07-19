#!/usr/bin/env python3
"""Suru IHA ESP-NOW Mesh Agi Simulatoru (ROS 2 Proxy Node).

Internal topic'lerden gelen verileri alir, fiziksel engellerden
ve mesafe kisitlamalarindan gecirerek Public topic'lere aktarir.
"""

import heapq
import itertools

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from rclpy.serialization import serialize_message
from std_msgs.msg import String, UInt8

from network_proxy.rf_model import ESPNowRFModel
from swarm_interfaces.msg import (
    AgentStatus,
    ElectionResult,
    FormationCommand,
    LeaderHeartbeat,
    MissionTarget,
    QRCoordinates,
    QRMissionData,
    SwarmControlCommand,
    SwarmOrigin,
    SwarmState,
    SystemEvent,
)

_HEARTBEAT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)

_STATE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_CONTROL_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_EVENT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_ELECTION_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_ORIGIN_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

_FORMATION_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_STATUS_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

_ESPNOW_MTU_BYTES = 250
_STALE_LIMIT_S = 12.0


class NetworkProxyNode(Node):
    """ESP-NOW agi simule eden proxy dugumu."""

    def __init__(self):
        super().__init__("network_proxy_node")

        self.declare_parameter("rng_seed", -1)
        rng_seed = int(self.get_parameter("rng_seed").value)
        self.rf_model = ESPNowRFModel(
            seed=rng_seed if rng_seed >= 0 else None
        )

        self.declare_parameter("gcs_lat", 0.0)
        self.declare_parameter("gcs_lon", 0.0)
        self.declare_parameter("gcs_alt", 0.0)
        gcs_lat = float(self.get_parameter("gcs_lat").value)
        gcs_lon = float(self.get_parameter("gcs_lon").value)
        gcs_alt = float(self.get_parameter("gcs_alt").value)
        self._gcs_configured = not (
            gcs_lat == 0.0 and gcs_lon == 0.0
        )
        if not self._gcs_configured:
            self.get_logger().warn(
                "gcs_lat/gcs_lon parametreleri eksik"
            )
        self.positions = {"gcs": (gcs_lat, gcs_lon, gcs_alt)}

        self._pos_stamp: dict[str, float] = {}
        self._current_leader_id = None

        self.declare_parameter("num_drones", 3)
        num_drones = int(self.get_parameter("num_drones").value)
        self.agent_ids = [
            f"drone{i}" for i in range(1, num_drones + 1)
        ]

        self.unreachable_agents = set()
        self.create_subscription(
            String, "/swarm/proxy/unreachable",
            self._on_unreachable_set, 10
        )

        self._pending = []
        self._seq_counter = itertools.count()
        self._last_scheduled = {}
        self.create_timer(0.002, self._drain_pending)

        self.internal_subs = {}
        self.public_pubs = {}

        for agent in self.agent_ids:
            internal_topic = f"/swarm/internal/{agent}/status"
            self.internal_subs[agent] = self.create_subscription(
                AgentStatus,
                internal_topic,
                lambda msg, a=agent: (
                    self.internal_status_callback(msg, a)
                ),
                _STATUS_QOS,
            )

            public_topic = f"/swarm/public/{agent}/status"
            self.public_pubs[agent] = self.create_publisher(
                AgentStatus, public_topic, _STATUS_QOS
            )

            self.positions[agent] = None

        self._hb_pub = self.create_publisher(
            LeaderHeartbeat,
            "/swarm/public/leader/heartbeat",
            _HEARTBEAT_QOS
        )
        self.create_subscription(
            LeaderHeartbeat,
            "/swarm/internal/leader/heartbeat",
            self._on_internal_heartbeat,
            _HEARTBEAT_QOS,
        )

        self._state_pub = self.create_publisher(
            SwarmState, "/swarm/public/state", _STATE_QOS
        )
        self.create_subscription(
            SwarmState, "/swarm/internal/state",
            self._on_internal_state,
            _STATE_QOS,
        )

        self._control_pub = self.create_publisher(
            SwarmControlCommand,
            "/swarm/public/control/command",
            _CONTROL_QOS
        )
        self.create_subscription(
            SwarmControlCommand, "/swarm/internal/control/command",
            self._on_internal_control, _CONTROL_QOS,
        )

        self._event_pub = self.create_publisher(
            SystemEvent, "/swarm/public/events/system", _EVENT_QOS
        )
        self.create_subscription(
            SystemEvent, "/swarm/internal/events/system",
            self._on_internal_event, _EVENT_QOS,
        )

        self._qr_pub = self.create_publisher(
            QRMissionData, "/swarm/public/perception/qr_data",
            _EVENT_QOS
        )
        self.create_subscription(
            QRMissionData, "/swarm/internal/perception/qr_data",
            self._on_internal_qr, _EVENT_QOS,
        )

        self._election_pub = self.create_publisher(
            ElectionResult, "/swarm/public/election/result",
            _ELECTION_QOS
        )
        self.create_subscription(
            ElectionResult, "/swarm/internal/election/result",
            self._on_internal_election, _ELECTION_QOS,
        )

        self._origin_pub = self.create_publisher(
            SwarmOrigin, "/swarm/public/origin", _ORIGIN_QOS
        )
        self.create_subscription(
            SwarmOrigin, "/swarm/internal/origin",
            self._on_internal_origin, _ORIGIN_QOS,
        )

        self._formation_pub = self.create_publisher(
            FormationCommand, "/swarm/public/formation/target",
            _FORMATION_QOS
        )
        self.create_subscription(
            FormationCommand, "/swarm/internal/formation/target",
            self._on_internal_formation, _FORMATION_QOS,
        )

        self._qr_coords_pub = self.create_publisher(
            QRCoordinates, "/swarm/public/mission/qr_coords",
            _ORIGIN_QOS
        )
        self.create_subscription(
            QRCoordinates, "/swarm/internal/mission/qr_coords",
            self._on_internal_qr_coords, _ORIGIN_QOS,
        )

        self._mission_state_pub = self.create_publisher(
            UInt8, "/swarm/public/mission/state", _FORMATION_QOS
        )
        self.create_subscription(
            UInt8, "/swarm/internal/mission/state",
            self._on_internal_mission_state, _FORMATION_QOS,
        )
        self._mission_qr_step_pub = self.create_publisher(
            UInt8, "/swarm/public/mission/qr_step", _FORMATION_QOS
        )
        self.create_subscription(
            UInt8, "/swarm/internal/mission/qr_step",
            self._on_internal_mission_qr_step, _FORMATION_QOS,
        )

        self._mission_next_target_pub = self.create_publisher(
            MissionTarget, "/swarm/public/mission/next_target",
            _FORMATION_QOS
        )
        self.create_subscription(
            MissionTarget, "/swarm/internal/mission/next_target",
            self._on_internal_mission_next_target, _FORMATION_QOS,
        )

        self.get_logger().info("Network Proxy Node baslatildi.")

    def _on_unreachable_set(self, msg: String):
        """Fault-injection icin menzil disi ajanlari gunceller."""
        names = {
            n.strip() for n in msg.data.split(",") if n.strip()
        }
        self.unreachable_agents = names
        self.get_logger().warn(
            f"Menzil disi ajanlar: {names or '(bos)'}"
        )

    def _schedule(
        self, channel_key: str, publisher, msg
    ) -> None:
        """Mesajlari sirali ve gecikmeli olarak kuyruğa ekler."""
        now = self.get_clock().now().nanoseconds / 1e9
        target = now + self.rf_model.get_jitter()
        last = self._last_scheduled.get(channel_key, 0.0)
        if target <= last:
            target = last + 1e-6
        self._last_scheduled[channel_key] = target
        heapq.heappush(
            self._pending,
            (target, next(self._seq_counter), publisher, msg)
        )

    def _drain_pending(self) -> None:
        """Kuyruktaki zamani gecmis mesajlari yayinlar."""
        now = self.get_clock().now().nanoseconds / 1e9
        while self._pending and self._pending[0][0] <= now:
            _, _, publisher, msg = heapq.heappop(self._pending)
            publisher.publish(msg)

    def _within_budget(self, msg, label: str) -> bool:
        """Paket boyutunun limitler icinde oldugunu dogrular."""
        size = len(serialize_message(msg))
        if size > _ESPNOW_MTU_BYTES:
            self.get_logger().warn(
                f"Paket limiti asildi! {label}: {size}B"
            )
            return False
        return True

    def _min_neighbor_distance_m(
        self, sender_pos, exclude_key=None
    ):
        """Ajanin en yakin komsuya olan uzakligini olcer."""
        now = self.get_clock().now().nanoseconds / 1e9
        min_dist = None
        for receiver_id in self.agent_ids:
            if receiver_id == exclude_key:
                continue
            if receiver_id in self.unreachable_agents:
                continue
            receiver_pos = self.positions.get(receiver_id)
            if receiver_pos is None:
                continue
            stamp = self._pos_stamp.get(receiver_id)
            if stamp is not None and now - stamp > _STALE_LIMIT_S:
                continue
            d = self.rf_model.distance_m(sender_pos, receiver_pos)
            min_dist = d if min_dist is None else min(min_dist, d)
        return min_dist

    def _broadcast_drop(self, sender_key: str) -> bool:
        """Yayin pakedinin dusup dusmeyecegine karar verir."""
        if sender_key in self.unreachable_agents:
            return True
        sender_pos = self.positions.get(sender_key)
        if sender_pos is None:
            return False
        min_dist = self._min_neighbor_distance_m(
            sender_pos, exclude_key=sender_key
        )
        if min_dist is None:
            return False
        return self.rf_model.should_drop_packet(min_dist)

    def _leader_drop(self) -> bool:
        """Lider kaynakli paketlerin dusme durumunu sorgular."""
        if self._current_leader_id is None:
            return False
        return self._broadcast_drop(
            f"drone{self._current_leader_id}"
        )

    def internal_status_callback(
        self, msg: AgentStatus, sender_id: str
    ):
        """Ajan telemetri verisini alip relay eder."""
        if sender_id in self.unreachable_agents:
            return

        now = self.get_clock().now().nanoseconds / 1e9
        if msg.gps_fix_type >= 3 and not (
            msg.lat_deg == 0.0 and msg.lon_deg == 0.0
        ):
            self.positions[sender_id] = (
                msg.lat_deg, msg.lon_deg, msg.alt_amsl_m
            )
            self._pos_stamp[sender_id] = now

        if not self._within_budget(msg, sender_id):
            return

        sender_pos = self.positions[sender_id]

        if self._gcs_configured and sender_pos is not None:
            gcs_dist = self.rf_model.distance_m(
                sender_pos, self.positions["gcs"]
            )
            if gcs_dist > self.rf_model.cutoff_m:
                self.get_logger().warn(
                    f"GCS menzil disi: {gcs_dist:.1f}m"
                )

        if self._broadcast_drop(sender_id):
            return

        self._schedule(
            sender_id, self.public_pubs[sender_id], msg
        )

    def _on_internal_heartbeat(self, msg: LeaderHeartbeat):
        """Lider hb mesajini yayinlar."""
        self._current_leader_id = msg.leader_id
        leader_key = f"drone{msg.leader_id}"

        if leader_key in self.unreachable_agents:
            return

        if not self._within_budget(msg, f"{leader_key} hb"):
            return

        if self._broadcast_drop(leader_key):
            return

        self._schedule("heartbeat", self._hb_pub, msg)

    def _simple_relay(
        self, msg, publisher, channel_key: str
    ):
        """Mesaji kuyruga ekler."""
        self._schedule(channel_key, publisher, msg)

    def _on_internal_state(self, msg: SwarmState):
        if not self._within_budget(msg, "state"):
            return
        if self._broadcast_drop(f"drone{msg.leader_id}"):
            return
        self._simple_relay(msg, self._state_pub, "state")

    def _on_internal_event(self, msg: SystemEvent):
        if not self._within_budget(msg, "event"):
            return
        if msg.source_agent_id != 0:
            if self._broadcast_drop(
                f"drone{msg.source_agent_id}"
            ):
                return
        self._simple_relay(msg, self._event_pub, "events")

    def _on_internal_qr(self, msg: QRMissionData):
        msg.raw_text = ""
        msg.error_message = ""
        if not self._within_budget(msg, "qr_data"):
            return
        if self._broadcast_drop(f"drone{msg.detector_agent_id}"):
            return
        self._simple_relay(msg, self._qr_pub, "qr_data")

    def _on_internal_election(self, msg: ElectionResult):
        self._current_leader_id = msg.new_leader_id
        if not self._within_budget(msg, "election"):
            return
        if self._broadcast_drop(f"drone{msg.new_leader_id}"):
            return
        if len(msg.confirmed_by_agent_ids) > 4:
            mesh_msg = ElectionResult()
            mesh_msg.stamp = msg.stamp
            mesh_msg.sequence_num = msg.sequence_num
            mesh_msg.new_leader_id = msg.new_leader_id
            mesh_msg.election_round = msg.election_round
            mesh_msg.triggered_by_agent_id = (
                msg.triggered_by_agent_id
            )
            mesh_msg.reason = msg.reason
            mesh_msg.confirmed_by_agent_ids = list(
                msg.confirmed_by_agent_ids[:4]
            )
            mesh_msg.message = msg.message
            msg = mesh_msg
        self._simple_relay(
            msg, self._election_pub, "election"
        )

    def _on_internal_origin(self, msg: SwarmOrigin):
        if not self._within_budget(msg, "origin"):
            return
        self._simple_relay(msg, self._origin_pub, "origin")

    def _on_internal_qr_coords(self, msg: QRCoordinates):
        if not self._within_budget(msg, "qr_coords"):
            return
        self._simple_relay(
            msg, self._qr_coords_pub, "qr_coords"
        )

    def _on_internal_formation(self, msg: FormationCommand):
        if not self._within_budget(msg, "formation"):
            return
        if self._leader_drop():
            return
        self._simple_relay(
            msg, self._formation_pub, "formation"
        )

    def _on_internal_mission_state(self, msg: UInt8):
        if not self._within_budget(msg, "mission_state"):
            return
        if self._leader_drop():
            return
        self._simple_relay(
            msg, self._mission_state_pub, "mission_state"
        )

    def _on_internal_mission_qr_step(self, msg: UInt8):
        if not self._within_budget(msg, "mission_qr_step"):
            return
        if self._leader_drop():
            return
        self._simple_relay(
            msg, self._mission_qr_step_pub, "mission_qr_step"
        )

    def _on_internal_mission_next_target(
        self, msg: MissionTarget
    ):
        if not self._within_budget(msg, "mission_next_target"):
            return
        if self._leader_drop():
            return
        self._simple_relay(
            msg, self._mission_next_target_pub,
            "mission_next_target"
        )

    def _on_internal_control(self, msg: SwarmControlCommand):
        if not self._within_budget(msg, "control command"):
            return
        if self._gcs_configured and self._broadcast_drop("gcs"):
            return
        self._schedule("control", self._control_pub, msg)

    def destroy_node(self) -> bool:
        """Kuyruktaki bekleyen mesajlari temizler."""
        self._pending.clear()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = NetworkProxyNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
