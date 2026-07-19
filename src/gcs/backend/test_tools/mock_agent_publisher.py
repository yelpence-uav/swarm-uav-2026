"""Sahte AgentStatus, SwarmState ve TriggerMission yayıncısı.

GCS arayüzünü uçtan uca test etmek için veri üretir.
"""

import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSPresetProfiles, QoSProfile, QoSReliabilityPolicy

from swarm_interfaces.msg import AgentStatus, SwarmState, SystemEvent
from swarm_interfaces.srv import TriggerMission

# SITL referans konumu
HOME_LAT = 47.397742
HOME_LON = 8.545594
HOME_ALT_M = 488.0  # AMSL


# Mock durumlar
class MockMode:
    IDLE = "idle"  # yerde, armed=False
    ACTIVE = "active"  # daire çiziyor
    PAUSED = "paused"  # havada hareketsiz
    RTL = "rtl"  # home'a dönüyor
    LANDING = "landing"  # iniyor
    ABORTED = "aborted"  # anında IDLE'a düşer


CRUISE_ALT_M = 10.0
DESCEND_RATE_MPS = 1.5  # iniş hızı
RTL_HORIZ_RATE_MPS = 2.0  # RTL'de yatay hız


class MockAgentPublisher(Node):

    PUBLISH_HZ = 5.0
    SWARM_STATE_HZ = 2.0
    EVENT_INTERVAL_SEC = 4.0
    DRONE_IDS = (1, 2, 3)

    def __init__(self):
        super().__init__("mock_agent_publisher")
        sensor_qos = QoSPresetProfiles.SENSOR_DATA.value
        reliable_qos = QoSProfile(
            depth=10, reliability=QoSReliabilityPolicy.RELIABLE
        )

        # Tüm drone ve network_proxy zincirinin yerine geçtiği için
        # doğrudan /swarm/public/... (proxy çıktısı) yayınlar.
        self._pubs = {
            drone_id: self.create_publisher(
                AgentStatus,
                f"/swarm/public/drone{drone_id}/status",
                sensor_qos,
            )
            for drone_id in self.DRONE_IDS
        }
        self._swarm_state_pub = self.create_publisher(
            SwarmState, "/swarm/public/state", reliable_qos
        )
        self._event_pub = self.create_publisher(
            SystemEvent, "/swarm/public/events/system", reliable_qos
        )
        self._trigger_srv = self.create_service(
            TriggerMission, "/swarm/mission/trigger", self._on_trigger_mission
        )

        # --- State machine ---
        self._mode = MockMode.ACTIVE  # default: hemen hareket görsün
        self._last_tick = time.time()
        # Her drone için durum verisi
        self._drone_state = {
            drone_id: {
                # daire üzerindeki başlangıç açısı
                "phase": i * (2 * math.pi / 3),
                "x": 5.0 * math.cos(i * (2 * math.pi / 3)),
                "y": 5.0 * math.sin(i * (2 * math.pi / 3)),
                "alt": CRUISE_ALT_M,
                "battery": max(20.0, 95.0 - drone_id * 2.0),
            }
            for i, drone_id in enumerate(self.DRONE_IDS)
        }

        self._t0 = time.time()
        self._next_event = 2.0
        self._event_idx = 0
        self.create_timer(1.0 / self.PUBLISH_HZ, self._tick_status)
        self.create_timer(1.0 / self.SWARM_STATE_HZ, self._tick_swarm_state)
        self.create_timer(0.5, self._tick_event)
        self.get_logger().info(
            f"test publisher başladı [mode={self._mode}]"
            f"AgentStatus@{self.PUBLISH_HZ}Hz × {len(self.DRONE_IDS)} drone, "
            f"SwarmState@{self.SWARM_STATE_HZ}Hz, "
            f"TriggerMission server hazır"
        )

    # --- Helper metodları --------------------------------------------------

    def _all_landed(self) -> bool:
        return all(s["alt"] < 0.3 for s in self._drone_state.values())

    def _all_at_home(self) -> bool:
        return all(
            math.hypot(s["x"], s["y"]) < 0.5
            for s in self._drone_state.values()
        )

    def _set_mode(self, new_mode: str, reason: str = "") -> None:
        if self._mode == new_mode:
            return
        old = self._mode
        self._mode = new_mode
        self.get_logger().info(f"state: {old} -> {new_mode} ({reason})")

    def _advance_drones(self, dt: float) -> None:
        """Mod'a göre per-drone pozisyon güncelle."""
        elapsed = time.time() - self._t0

        for drone_id, s in self._drone_state.items():
            # Batarya: ACTIVE/PAUSED'da yavaş tüket, diğerlerinde az tüket
            drain = (
                0.05
                if self._mode in (MockMode.ACTIVE, MockMode.PAUSED)
                else 0.02
            )
            s["battery"] = max(15.0, s["battery"] - drain * dt)

            if self._mode == MockMode.ACTIVE:
                # Daire üzerinde dönmeye devam
                s["phase"] = (drone_id - 1) * (2 * math.pi / 3) + elapsed * 0.1
                s["x"] = 5.0 * math.cos(s["phase"])
                s["y"] = 5.0 * math.sin(s["phase"])
                s["alt"] = CRUISE_ALT_M
            elif self._mode == MockMode.PAUSED:
                # Olduğu yerde dur
                s["alt"] = CRUISE_ALT_M
            elif self._mode == MockMode.RTL:
                # (0,0)'a doğru hareket
                dist = math.hypot(s["x"], s["y"])
                if dist > 0.05:
                    step = min(RTL_HORIZ_RATE_MPS * dt, dist)
                    s["x"] -= (s["x"] / dist) * step
                    s["y"] -= (s["y"] / dist) * step
                s["alt"] = CRUISE_ALT_M
            elif self._mode == MockMode.LANDING:
                # İrtifa azalıyor
                s["alt"] = max(0.0, s["alt"] - DESCEND_RATE_MPS * dt)
            elif self._mode in (MockMode.IDLE, MockMode.ABORTED):
                # Yerde bekliyor
                s["alt"] = 0.0

        # State otomatik geçişleri
        if self._mode == MockMode.RTL and self._all_at_home():
            self._set_mode(MockMode.LANDING, "home'a varıldı, iniş başladı")
        if self._mode == MockMode.LANDING and self._all_landed():
            self._set_mode(MockMode.IDLE, "tüm drone'lar indi")
        if self._mode == MockMode.ABORTED:
            # Anlık IDLE'a düşür
            for s in self._drone_state.values():
                s["alt"] = 0.0
            self._set_mode(MockMode.IDLE, "abort sonrası reset")

    # --- Callback fonksiyonları --------------------------------------------

    def _tick_status(self) -> None:
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now
        self._advance_drones(dt)

        for drone_id in self.DRONE_IDS:
            msg = self._build_status(drone_id)
            self._pubs[drone_id].publish(msg)

    def _tick_swarm_state(self) -> None:
        elapsed = time.time() - self._t0
        m = SwarmState()
        m.stamp = self.get_clock().now().to_msg()

        # Mode vs SwarmState eşlemesi
        if self._mode == MockMode.IDLE:
            m.swarm_state = SwarmState.SWARM_IDLE
        elif self._mode == MockMode.ACTIVE:
            m.swarm_state = SwarmState.SWARM_NAVIGATING
        elif self._mode == MockMode.PAUSED:
            m.swarm_state = (
                SwarmState.SWARM_FORMING
            )  # "duraklatıldı" yerine en yakın
        elif self._mode == MockMode.RTL:
            m.swarm_state = SwarmState.SWARM_RTL
        elif self._mode == MockMode.LANDING:
            m.swarm_state = SwarmState.SWARM_LANDING
        else:
            m.swarm_state = SwarmState.SWARM_FAILSAFE

        m.leader_id = 1
        m.active_agent_count = sum(
            1 for s in self._drone_state.values() if s["alt"] > 0.3
        )
        m.active_formation = SwarmState.FORMATION_V
        m.mission_active = self._mode in (MockMode.ACTIVE, MockMode.PAUSED)
        m.formation_reached = self._mode == MockMode.ACTIVE
        m.formation_stable = self._mode == MockMode.ACTIVE
        m.emergency_active = False

        # Centroid (ortalama pozisyon)
        if self._drone_state:
            cx = sum(s["x"] for s in self._drone_state.values()) / len(
                self._drone_state
            )
            cy = sum(s["y"] for s in self._drone_state.values()) / len(
                self._drone_state
            )
            cz = -sum(s["alt"] for s in self._drone_state.values()) / len(
                self._drone_state
            )
        else:
            cx = cy = cz = 0.0
        m.centroid_x = cx
        m.centroid_y = cy
        m.centroid_z = cz

        m.formation_heading_deg = (
            (math.degrees(elapsed * 0.1)) % 360
            if self._mode == MockMode.ACTIVE
            else 0.0
        )
        m.formation_max_error_m = 0.4 if self._mode == MockMode.ACTIVE else 0.0
        m.formation_avg_error_m = 0.2 if self._mode == MockMode.ACTIVE else 0.0
        m.formation_heading_error_deg = (
            1.5 if self._mode == MockMode.ACTIVE else 0.0
        )
        m.active_mission = "qr_chain" if m.mission_active else ""
        m.status_text = ""
        m.current_qr_id = 1 if m.mission_active else 0
        m.current_qr_seq = 1 if m.mission_active else 0
        m.last_event_type = 0
        m.last_event_severity = 0
        m.last_event_source = 0
        m.last_event_value = 0.0
        m.last_event_message = ""
        self._swarm_state_pub.publish(m)

    def _on_trigger_mission(self, request, response):
        """TriggerMission alınca state machine'i değiştir."""
        cmd_names = {
            1: "START",
            2: "ABORT",
            3: "PAUSE",
            4: "RESUME",
            5: "RTL",
            6: "LAND",
        }
        mission_names = {1: "DYNAMIC_SWARM", 2: "SEMI_AUTONOMOUS"}
        cmd = cmd_names.get(request.command, f"cmd={request.command}")
        mid = mission_names.get(
            request.mission_id, f"mid={request.mission_id}"
        )
        team = request.team_id or "(takım belirtilmedi)"

        # State geçişleri
        prev_mode = self._mode
        if request.command == 1:  # START
            if self._mode == MockMode.IDLE:
                # Yerden başla -> ACTIVE
                for s in self._drone_state.values():
                    s["alt"] = CRUISE_ALT_M
                    s["battery"] = max(s["battery"], 80.0)
                self._set_mode(MockMode.ACTIVE, "START: yerden kalkış")
                response.success = True
                response.message = f"{mid}/START - kalktı (team={team})"
            else:
                response.success = False
                response.message = f"zaten aktif (mode={self._mode})"
        elif request.command == 2:  # ABORT
            self._set_mode(MockMode.ABORTED, "ABORT komutu")
            response.success = True
            response.message = "görev iptal, drone'lar yerde"
        elif request.command == 3:  # PAUSE
            if self._mode == MockMode.ACTIVE:
                self._set_mode(MockMode.PAUSED, "PAUSE komutu")
                response.success = True
                response.message = "duraklatıldı, drone'lar havada bekliyor"
            else:
                response.success = False
                response.message = (
                    f"PAUSE sadece ACTIVE'den (mode={self._mode})"
                )
        elif request.command == 4:  # RESUME
            if self._mode == MockMode.PAUSED:
                self._set_mode(MockMode.ACTIVE, "RESUME komutu")
                response.success = True
                response.message = "göreve devam"
            else:
                response.success = False
                response.message = (
                    f"RESUME sadece PAUSED'dan (mode={self._mode})"
                )
        elif request.command == 5:  # RTL
            self._set_mode(MockMode.RTL, "RTL komutu")
            response.success = True
            response.message = "drone'lar home'a dönüyor"
        elif request.command == 6:  # LAND
            self._set_mode(MockMode.LANDING, "LAND komutu")
            response.success = True
            response.message = "iniş başladı"
        else:
            response.success = False
            response.message = f"bilinmeyen komut {request.command}"

        self.get_logger().info(
            f"TriggerMission: mission={mid} command={cmd} team={team} "
            f"-> {prev_mode}->{self._mode} ({response.message})"
        )
        return response

    def _tick_event(self) -> None:
        elapsed = time.time() - self._t0
        if elapsed < self._next_event:
            return
        self._next_event = elapsed + self.EVENT_INTERVAL_SEC

        # ACTIVE değilse event yayınını yavaşlat
        if self._mode != MockMode.ACTIVE:
            return

        events = [
            (
                SystemEvent.EVENT_QR_DETECTED,
                SystemEvent.SEVERITY_INFO,
                1,
                "QR1 algılandı",
            ),
            (
                SystemEvent.EVENT_FORMATION_REACHED,
                SystemEvent.SEVERITY_INFO,
                0,
                "V formasyonu kuruldu",
            ),
            (
                SystemEvent.EVENT_BATTERY_LOW,
                SystemEvent.SEVERITY_WARNING,
                2,
                "Drone 2 batarya %20",
            ),
            (
                SystemEvent.EVENT_LEADER_CHANGED,
                SystemEvent.SEVERITY_INFO,
                0,
                "Lider Drone 1 -> Drone 2",
            ),
        ]
        evt_type, severity, source, text = events[
            self._event_idx % len(events)
        ]
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
        m.source_module = "test_publisher"
        m.message = text
        self._event_pub.publish(m)

    # --- AgentStatus oluşturma --------------------------------------------

    def _build_status(self, drone_id: int) -> AgentStatus:
        s = self._drone_state[drone_id]
        elapsed = time.time() - self._t0

        # Mode'a göre flight_mode + state + armed
        if self._mode == MockMode.ACTIVE:
            armed = True
            flight_mode = AgentStatus.FLIGHT_MODE_OFFBOARD
            agent_state = AgentStatus.STATE_IN_SWARM
        elif self._mode == MockMode.PAUSED:
            armed = True
            flight_mode = AgentStatus.FLIGHT_MODE_AUTO_LOITER
            agent_state = AgentStatus.STATE_IN_SWARM
        elif self._mode == MockMode.RTL:
            armed = True
            flight_mode = AgentStatus.FLIGHT_MODE_AUTO_RTL
            agent_state = AgentStatus.STATE_RETURN_HOME
        elif self._mode == MockMode.LANDING:
            armed = s["alt"] > 0.3  # yere değince disarm
            flight_mode = AgentStatus.FLIGHT_MODE_AUTO_LAND
            agent_state = (
                AgentStatus.STATE_LANDING
                if s["alt"] > 0.3
                else AgentStatus.STATE_LANDED
            )
        else:  # IDLE / ABORTED
            armed = False
            flight_mode = AgentStatus.FLIGHT_MODE_MANUAL
            agent_state = AgentStatus.STATE_IDLE

        m = AgentStatus()
        m.stamp = self.get_clock().now().to_msg()
        m.agent_id = drone_id
        m.role = (
            AgentStatus.ROLE_LEADER
            if drone_id == 1
            else AgentStatus.ROLE_FOLLOWER
        )
        m.state = agent_state
        m.flight_mode = flight_mode
        m.px4_link_ok = True
        m.gcs_link_ok = True
        m.armed = armed
        m.offboard_enabled = armed
        m.offboard_active = self._mode == MockMode.ACTIVE
        m.pilot_override_active = False
        m.failsafe_active = False
        m.healthy = True

        m.battery_percent = s["battery"]
        m.battery_voltage_v = 14.8 - (95.0 - s["battery"]) * 0.02
        m.battery_current_a = (8.0 + drone_id) if armed else 0.5

        # Local NED pos
        m.pos_x = s["x"]
        m.pos_y = s["y"]
        m.pos_z = -s["alt"]  # NED z negatif yukarı

        if self._mode == MockMode.ACTIVE:
            m.vel_x = -5.0 * 0.1 * math.sin(s["phase"])
            m.vel_y = 5.0 * 0.1 * math.cos(s["phase"])
            m.vel_z = 0.0
        elif self._mode == MockMode.RTL:
            dist = math.hypot(s["x"], s["y"])
            if dist > 0.05:
                m.vel_x = -RTL_HORIZ_RATE_MPS * (s["x"] / dist)
                m.vel_y = -RTL_HORIZ_RATE_MPS * (s["y"] / dist)
            else:
                m.vel_x = 0.0
                m.vel_y = 0.0
            m.vel_z = 0.0
        elif self._mode == MockMode.LANDING:
            m.vel_x = 0.0
            m.vel_y = 0.0
            m.vel_z = DESCEND_RATE_MPS  # NED z aşağı pozitif
        else:
            m.vel_x = m.vel_y = m.vel_z = 0.0

        m.heading_deg = (math.degrees(elapsed * 0.1) + drone_id * 120) % 360
        m.roll_deg = 0.0
        m.pitch_deg = 0.0

        m.gps_fix_type = 6
        m.gps_hdop = 0.6
        m.gps_satellites = 18
        m.lat_deg = HOME_LAT + (s["x"] / 111111.0)
        m.lon_deg = HOME_LON + (
            s["y"] / (111111.0 * math.cos(math.radians(HOME_LAT)))
        )
        m.alt_amsl_m = HOME_ALT_M + s["alt"]

        m.home_set = True
        m.home_lat_deg = HOME_LAT
        m.home_lon_deg = HOME_LON
        m.home_alt_amsl_m = HOME_ALT_M

        m.imu_healthy = True
        m.mag_healthy = True
        m.baro_healthy = True
        m.estimator_ok = True
        m.xy_valid = True
        m.z_valid = True
        m.v_xy_valid = True

        m.origin_synced = True
        m.origin_sequence = 1

        m.rc_link_ok = True
        m.kill_switch_active = False
        m.rc_signal_failsafe_active = False

        m.oscillation_detected = False
        m.unstable_flight = False

        m.wants_to_join = False
        m.ready_to_arm = self._mode == MockMode.IDLE

        m.status_text = ""
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
