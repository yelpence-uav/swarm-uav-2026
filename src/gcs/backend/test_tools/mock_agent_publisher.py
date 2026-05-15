"""Sahte AgentStatus yayıncısı — ekibin agent_fsm node'u olmadan ros_bridge'i test etmek için.

3 drone için /swarm/agent/{id}/status topic'ine 5 Hz AgentStatus mesajı basar.
Drone'lar Zürich PX4 SITL home'u etrafında dairesel hareket ediyormuş gibi yapar.

Çalıştırma (container içinde):
  source /opt/ros/jazzy/setup.bash
  source /home/yelpence/ros2_ws/install/setup.bash
  source /home/yelpence/venv/bin/activate
  python3 -m backend.test_tools.mock_agent_publisher

İkinci terminalde ros_bridge'in (veya backend'in) bu mesajları aldığını
log'larda görmelisin: "AgentStatus drone=1 state=... pos=..."
"""

import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSPresetProfiles, QoSProfile, QoSReliabilityPolicy

from swarm_interfaces.msg import AgentStatus, SwarmState, SystemEvent


# PX4 SITL default home (Zürich Hönggerberg) — ekipte değişebilir.
HOME_LAT = 47.397742
HOME_LON = 8.545594
HOME_ALT_M = 488.0  # AMSL


class MockAgentPublisher(Node):

    PUBLISH_HZ = 5.0
    SWARM_STATE_HZ = 2.0
    EVENT_INTERVAL_SEC = 4.0  # her 4 sn'de bir test event'i bas
    DRONE_IDS = (1, 2, 3)

    def __init__(self):
        super().__init__("mock_agent_publisher")
        sensor_qos = QoSPresetProfiles.SENSOR_DATA.value
        reliable_qos = QoSProfile(depth=10, reliability=QoSReliabilityPolicy.RELIABLE)
        # Topic adı `drone{id}` prefix'iyle — ROS 2 token sayıyla başlayamaz.
        # Ekibin agent_fsm_node'u da aynı format'ı kullanıyor.
        self._pubs = {
            drone_id: self.create_publisher(
                AgentStatus, f"/swarm/agent/drone{drone_id}/status", sensor_qos
            )
            for drone_id in self.DRONE_IDS
        }
        self._swarm_state_pub = self.create_publisher(
            SwarmState, "/swarm/state", reliable_qos
        )
        self._event_pub = self.create_publisher(
            SystemEvent, "/swarm/events/system", reliable_qos
        )
        self._t0 = time.time()
        self._next_event = 2.0  # ilk event 2sn sonra
        self._event_idx = 0
        self.create_timer(1.0 / self.PUBLISH_HZ, self._tick_status)
        self.create_timer(1.0 / self.SWARM_STATE_HZ, self._tick_swarm_state)
        self.create_timer(0.5, self._tick_event)
        self.get_logger().info(
            f"mock_agent_publisher başladı — "
            f"AgentStatus@{self.PUBLISH_HZ}Hz × {len(self.DRONE_IDS)} drone, "
            f"SwarmState@{self.SWARM_STATE_HZ}Hz, SystemEvent@~{self.EVENT_INTERVAL_SEC}s"
        )

    def _tick_status(self) -> None:
        elapsed = time.time() - self._t0
        # Drone'ları home etrafında 5m yarıçaplı dairede 0.1 rad/s ile döndür.
        for i, drone_id in enumerate(self.DRONE_IDS):
            phase = elapsed * 0.1 + i * (2 * math.pi / 3)  # 120° offset
            dx_m = 5.0 * math.cos(phase)  # north (m)
            dy_m = 5.0 * math.sin(phase)  # east (m)

            msg = self._build_status(drone_id, dx_m, dy_m, elapsed)
            self._pubs[drone_id].publish(msg)

    def _tick_swarm_state(self) -> None:
        elapsed = time.time() - self._t0
        m = SwarmState()
        m.stamp = self.get_clock().now().to_msg()
        m.swarm_state = SwarmState.SWARM_NAVIGATING
        m.leader_id = 1
        m.active_agent_count = 3
        m.active_formation = SwarmState.FORMATION_V
        m.mission_active = True
        m.formation_reached = True
        m.formation_stable = True
        m.emergency_active = False
        m.centroid_x = 0.0
        m.centroid_y = 0.0
        m.centroid_z = -10.0
        m.formation_heading_deg = (math.degrees(elapsed * 0.1)) % 360
        m.formation_max_error_m = 0.4
        m.formation_avg_error_m = 0.2
        m.formation_heading_error_deg = 1.5
        m.active_mission = "qr_chain"
        m.status_text = f"mock t={elapsed:.0f}s"
        m.current_qr_id = 1
        m.current_qr_seq = 1
        # last_event boş başlat (zorunlu değil)
        m.last_event_type = 0
        m.last_event_severity = 0
        m.last_event_source = 0
        m.last_event_value = 0.0
        m.last_event_message = ""
        self._swarm_state_pub.publish(m)

    def _tick_event(self) -> None:
        elapsed = time.time() - self._t0
        if elapsed < self._next_event:
            return
        self._next_event = elapsed + self.EVENT_INTERVAL_SEC

        # Döngüsel test event'leri
        events = [
            (SystemEvent.EVENT_MISSION_STARTED, SystemEvent.SEVERITY_INFO, 0, "Görev 1 başlatıldı"),
            (SystemEvent.EVENT_QR_DETECTED, SystemEvent.SEVERITY_INFO, 1, "QR1 algılandı"),
            (SystemEvent.EVENT_FORMATION_REACHED, SystemEvent.SEVERITY_INFO, 0, "V formasyonu kuruldu"),
            (SystemEvent.EVENT_BATTERY_LOW, SystemEvent.SEVERITY_WARNING, 2, "Drone 2 batarya %20"),
            (SystemEvent.EVENT_LEADER_CHANGED, SystemEvent.SEVERITY_INFO, 0, "Lider Drone 1 → Drone 2"),
        ]
        evt_type, severity, source, text = events[self._event_idx % len(events)]
        self._event_idx += 1

        m = SystemEvent()
        m.stamp = self.get_clock().now().to_msg()
        m.event_type = evt_type
        m.severity = severity
        m.source_agent_id = source
        m.target_agent_id = 0
        m.value = 0.0
        m.has_position = False
        m.pos_x = 0.0
        m.pos_y = 0.0
        m.pos_z = 0.0
        m.source_module = "mock"
        m.message = text
        self._event_pub.publish(m)
        self.get_logger().info(f"event yayınladı: {text}")

    def _build_status(self, drone_id: int, dx_m: float, dy_m: float, elapsed: float) -> AgentStatus:
        m = AgentStatus()
        m.stamp = self.get_clock().now().to_msg()
        m.agent_id = drone_id
        m.role = AgentStatus.ROLE_LEADER if drone_id == 1 else AgentStatus.ROLE_FOLLOWER
        m.state = AgentStatus.STATE_IN_SWARM
        m.flight_mode = AgentStatus.FLIGHT_MODE_OFFBOARD
        m.px4_link_ok = True
        m.gcs_link_ok = True
        m.armed = True
        m.offboard_enabled = True
        m.offboard_active = True
        m.pilot_override_active = False
        m.failsafe_active = False
        m.healthy = True

        # Battery (drone'a göre biraz farklı)
        m.battery_percent = max(20.0, 95.0 - elapsed * 0.05 - drone_id * 2.0)
        m.battery_voltage_v = 14.8 - (95.0 - m.battery_percent) * 0.02
        m.battery_current_a = 8.0 + drone_id

        # Local NED pozisyon (z negatif = yukarı)
        m.pos_x = dx_m
        m.pos_y = dy_m
        m.pos_z = -10.0  # 10m yukarıda
        m.vel_x = -5.0 * 0.1 * math.sin(elapsed * 0.1)
        m.vel_y = 5.0 * 0.1 * math.cos(elapsed * 0.1)
        m.vel_z = 0.0

        # Attitude
        m.heading_deg = (math.degrees(elapsed * 0.1) + drone_id * 120) % 360
        m.roll_deg = 0.0
        m.pitch_deg = 0.0

        # GPS
        m.gps_fix_type = 6  # RTK Fixed (RTK üzerine konuştuk)
        m.gps_hdop = 0.6
        m.gps_satellites = 18

        # GPS lat/lon — local NED dx/dy → kabaca lat/lon delta
        m.lat_deg = HOME_LAT + (dx_m / 111111.0)
        m.lon_deg = HOME_LON + (dy_m / (111111.0 * math.cos(math.radians(HOME_LAT))))
        m.alt_amsl_m = HOME_ALT_M + 10.0

        # Home
        m.home_set = True
        m.home_lat_deg = HOME_LAT
        m.home_lon_deg = HOME_LON
        m.home_alt_amsl_m = HOME_ALT_M

        # Sensor + EKF health
        m.imu_healthy = True
        m.mag_healthy = True
        m.baro_healthy = True
        m.estimator_ok = True
        m.xy_valid = True
        m.z_valid = True
        m.v_xy_valid = True

        # Origin sync (sahada kritik, sim'de ignore)
        m.origin_synced = True
        m.origin_sequence = 1

        # RC / kill switch
        m.rc_link_ok = True
        m.kill_switch_active = False
        m.rc_signal_failsafe_active = False

        # Uçuş kalitesi
        m.oscillation_detected = False
        m.unstable_flight = False

        # Join request
        m.wants_to_join = False
        m.ready_to_arm = True

        m.status_text = f"mock drone {drone_id}"
        return m


def main(args=None):
    rclpy.init(args=args)
    node = MockAgentPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
