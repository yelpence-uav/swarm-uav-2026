#!/usr/bin/env python3
"""
sync_takeoff.py

FSM üzerinden tüm drone'ları kaldırır.
EVENT_MISSION_STARTED → FSM: IDLE→ARMING→ARMED→TAKEOFF→IN_SWARM
PX4 komutlarını (arm/offboard/takeoff) FSM yönetir; bu script sadece
tetikler ve FSM state'ini izler.
"""
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSPresetProfiles, QoSReliabilityPolicy, QoSProfile
from swarm_interfaces.msg import AgentStatus, SystemEvent

DRONES = ['drone1', 'drone2', 'drone3']
EKF_TIMEOUT_S = 60.0     # xy_valid+z_valid için
IN_SWARM_TIMEOUT_S = 60.0  # FSM'nin TAKEOFF→IN_SWARM tamamlaması için


class SyncTakeoff(Node):
    def __init__(self):
        super().__init__('sync_takeoff')
        qos = QoSPresetProfiles.SYSTEM_DEFAULT.value
        # FSM internal topic'leri RELIABLE yayınlıyor; eşleşmesi için RELIABLE sub
        reliable_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            depth=10,
        )

        self._fsm_state = {d: AgentStatus.STATE_UNKNOWN for d in DRONES}
        self._ekf_ready = {d: False for d in DRONES}

        for d in DRONES:
            self.create_subscription(
                AgentStatus,
                f'/swarm/agent/{d}/telemetry',
                lambda msg, name=d: self._on_telem(name, msg),
                qos,
            )
            self.create_subscription(
                AgentStatus,
                f'/swarm/internal/{d}/status',
                lambda msg, name=d: self._on_fsm_status(name, msg),
                reliable_qos,
            )

        # FSM /swarm/public/events/system dinliyor
        self._event_pub = self.create_publisher(
            SystemEvent,
            '/swarm/public/events/system',
            qos,
        )

    def _on_telem(self, drone: str, msg: AgentStatus) -> None:
        self._ekf_ready[drone] = bool(msg.xy_valid and msg.z_valid)

    def _on_fsm_status(self, drone: str, msg: AgentStatus) -> None:
        self._fsm_state[drone] = msg.state

    def _wait_for(self, condition_fn, label: str, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            ok = condition_fn()
            print(f"  {label}: {ok}/{len(DRONES)}", end='\r')
            if ok == len(DRONES):
                print()
                return True
        print()
        return False

    def _send_mission_started(self) -> None:
        msg = SystemEvent()
        msg.stamp = self.get_clock().now().to_msg()
        msg.event_type = SystemEvent.EVENT_MISSION_STARTED
        msg.severity = SystemEvent.SEVERITY_INFO
        msg.source_module = 'sync_takeoff'
        self._event_pub.publish(msg)

    def run(self) -> bool:
        print("Publisher'lar hazırlanıyor...")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)

        print("EKF hazırlığı bekleniyor (xy_valid+z_valid)...")
        if not self._wait_for(
            lambda: sum(1 for d in DRONES if self._ekf_ready[d]),
            'ekf_ready', EKF_TIMEOUT_S,
        ):
            notready = [d for d in DRONES if not self._ekf_ready[d]]
            print(f"HATA: EKF hazır değil ({notready}) — kalkış iptal.")
            return False

        print("FSM'e EVENT_MISSION_STARTED gönderiliyor (3x)...")
        for _ in range(3):
            self._send_mission_started()
            time.sleep(0.3)
        self.get_logger().info('EVENT_MISSION_STARTED → FSM kaldırış başlatıyor')

        print("FSM kaldırış zinciri bekleniyor (IDLE→ARMING→ARMED→TAKEOFF→IN_SWARM)...")
        if not self._wait_for(
            lambda: sum(
                1 for d in DRONES
                if self._fsm_state[d] == AgentStatus.STATE_IN_SWARM
            ),
            'in_swarm', IN_SWARM_TIMEOUT_S,
        ):
            states = {d: self._fsm_state[d] for d in DRONES}
            print(f"HATA: FSM IN_SWARM'a ulaşamadı {states}, iptal.")
            return False

        print("✓ 3 drone IN_SWARM — kalkış başarılı.")
        return True


def main():
    rclpy.init(args=sys.argv)
    node = SyncTakeoff()
    ok = False
    try:
        ok = node.run()
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
