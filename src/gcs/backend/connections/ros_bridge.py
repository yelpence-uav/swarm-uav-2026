"""ROS 2 köprüsü — swarm_interfaces kontratı üzerinden drone'larla konuşur.

GCS'in birincil iletişim katmanı. Faz 1-4'teki MavlinkListener'ın yerini alır;
MAVLink yan-yolu (sim erken testi için) `mavlink_listener.py` altında fallback
olarak kalır, `connection_mode` ile seçilir.

GCS rolü (kontrat 3.3):
  - Subscribe: AgentStatus, SwarmState, SystemEvent, ElectionResult,
              LandingZoneDetection
  - Publish:   SwarmControlCommand (Görev 2 joystick)
  - Service client: TriggerMission (Görev başlat/durdur), ManageSwarmMember (debug)

Bu dosya iskelet sürüm — şimdilik sadece AgentStatus subscriber + log.
Aşama 2'de StateStore beslemesi, Aşama 3'te service client + publisher eklenir.

Çalıştırma ön koşulu:
  source /opt/ros/jazzy/setup.bash
  source /home/yelpence/ros2_ws/install/setup.bash   # swarm_interfaces için
"""

import logging
import threading
from typing import Callable, Optional

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSPresetProfiles,
    QoSProfile,
    QoSReliabilityPolicy,
)

from swarm_interfaces.msg import (
    AgentStatus,
    QRMissionData,
    SwarmControlCommand,
    SwarmState,
    SystemEvent,
)
from swarm_interfaces.srv import TriggerMission

# QRCoordinates (operatörün girdiği QR konum tablosu) feature/qr-coordinates
# branch'inde tanımlı; henüz main'de/derli olmayabilir. Guarded import — yoksa
# backend yine de normal çalışır, sadece QR konum yayını devre dışı kalır.
try:
    from swarm_interfaces.msg import QRCoordinates
    _HAS_QR_COORDS = True
except ImportError:  # pragma: no cover - mesaj tipi henüz derlenmemiş
    QRCoordinates = None  # type: ignore
    _HAS_QR_COORDS = False

from backend.core.alert_manager import (
    AlertManager,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)
from backend.core.state_store import StateStore

logger = logging.getLogger(__name__)


# AgentStatus.flight_mode (uint8) → frontend için Türkçe/PX4 etiketi.
# Faz 1-4'te MAVLink HEARTBEAT.custom_mode'dan parse ediliyordu; AgentStatus
# kontratında zaten enum. Frontend hâlâ "mode" string alanını gösteriyor.
FLIGHT_MODE_LABELS = {
    AgentStatus.FLIGHT_MODE_UNKNOWN: "?",
    AgentStatus.FLIGHT_MODE_MANUAL: "Manuel",
    AgentStatus.FLIGHT_MODE_ALTCTL: "AltCtl",
    AgentStatus.FLIGHT_MODE_POSCTL: "PosCtl",
    AgentStatus.FLIGHT_MODE_OFFBOARD: "Offboard",
    AgentStatus.FLIGHT_MODE_AUTO_MISSION: "Auto.Mission",
    AgentStatus.FLIGHT_MODE_AUTO_LOITER: "Auto.Loiter",
    AgentStatus.FLIGHT_MODE_AUTO_RTL: "Auto.RTL",
    AgentStatus.FLIGHT_MODE_AUTO_LAND: "Auto.Land",
    AgentStatus.FLIGHT_MODE_ACRO: "Acro",
    AgentStatus.FLIGHT_MODE_STABILIZED: "Stabilized",
}


def _ned_speed(msg: AgentStatus) -> float:
    return (msg.vel_x ** 2 + msg.vel_y ** 2) ** 0.5


# SystemEvent.event_type → kullanıcıya gösterilecek Türkçe etiket.
# Frontend daha güzel ikonlar/renkler ekleyebilir; backend sadece ham mesajı atar.
SYSTEM_EVENT_LABELS = {
    SystemEvent.EVENT_AGENT_READY: "Drone hazır",
    SystemEvent.EVENT_AGENT_REACHED_POS: "Drone hedefe vardı",
    SystemEvent.EVENT_AGENT_DETACHED: "Drone sürüden ayrıldı",
    SystemEvent.EVENT_AGENT_LANDED: "Drone indi",
    SystemEvent.EVENT_AGENT_REJOINED: "Drone sürüye katıldı",
    SystemEvent.EVENT_AGENT_FAULT: "Drone arızası",
    SystemEvent.EVENT_AGENT_JOIN_REQUEST: "Sürüye katılma talebi",
    SystemEvent.EVENT_AGENT_PILOT_OVERRIDE: "Pilot müdahalesi",
    SystemEvent.EVENT_QR_DETECTED: "QR algılandı",
    SystemEvent.EVENT_QR_PARSED: "QR çözümlendi",
    SystemEvent.EVENT_FORMATION_REACHED: "Formasyon kuruldu",
    SystemEvent.EVENT_FORMATION_FAILED: "Formasyon kurulamadı",
    SystemEvent.EVENT_MISSION_STARTED: "Görev başladı",
    SystemEvent.EVENT_MISSION_COMPLETED: "Görev tamamlandı",
    SystemEvent.EVENT_COLOR_ZONE_DETECTED: "Renkli iniş alanı tespit edildi",
    SystemEvent.EVENT_QR_SEQUENCE_REJECTED: "QR sırası reddedildi",
    SystemEvent.EVENT_PRECISION_LANDING_STARTED: "Hassas iniş başladı",
    SystemEvent.EVENT_PRECISION_LANDING_COMPLETED: "Hassas iniş tamamlandı",
    SystemEvent.EVENT_ROTATION_STARTED: "Formasyon rotasyonu başladı",
    SystemEvent.EVENT_ROTATION_COMPLETED: "Formasyon rotasyonu tamamlandı",
    SystemEvent.EVENT_MANEUVER_STARTED: "Manevra başladı",
    SystemEvent.EVENT_MANEUVER_COMPLETED: "Manevra tamamlandı",
    SystemEvent.EVENT_MANEUVER_FAILED: "Manevra başarısız",
    SystemEvent.EVENT_MEMBER_DETACH_STARTED: "Sürüden ayrılma başladı",
    SystemEvent.EVENT_MEMBER_REJOIN_STARTED: "Sürüye katılma başladı",
    SystemEvent.EVENT_MEMBER_MANAGEMENT_FAILED: "Sürü üyesi yönetimi başarısız",
    SystemEvent.EVENT_GCS_LINK_LOST: "GCS bağlantısı koptu",
    SystemEvent.EVENT_GCS_LINK_RESTORED: "GCS bağlantısı geri geldi",
    SystemEvent.EVENT_BATTERY_LOW: "Batarya düşük",
    SystemEvent.EVENT_COLLISION_RISK: "Çarpışma riski",
    SystemEvent.EVENT_OFFBOARD_LOST: "Offboard mod kaybedildi",
    SystemEvent.EVENT_RTL_TRIGGERED: "RTL tetiklendi",
    SystemEvent.EVENT_EMERGENCY_LAND: "Acil iniş",
    SystemEvent.EVENT_PX4_LINK_LOST: "PX4 bağlantısı koptu",
    SystemEvent.EVENT_LEADER_CHANGED: "Lider değişti",
    SystemEvent.EVENT_SAFETY_HOLD: "Güvenlik HOLD",
    SystemEvent.EVENT_FAILSAFE_CLEARED: "Failsafe temizlendi",
    SystemEvent.EVENT_ORIGIN_READY: "Sürü origin'i hazır",
    SystemEvent.EVENT_ORIGIN_SYNCED: "Origin senkronize",
    SystemEvent.EVENT_ORIGIN_FAILED: "Origin senkronu başarısız",
    SystemEvent.EVENT_OSCILLATION_DETECTED: "Salınım tespit edildi",
    SystemEvent.EVENT_UNSTABLE_FLIGHT: "Kararsız uçuş",
    SystemEvent.EVENT_GEOFENCE_VIOLATION: "Geofence ihlali",
    SystemEvent.EVENT_ALTITUDE_LIMIT_EXCEEDED: "İrtifa sınırı aşıldı",
    SystemEvent.EVENT_RC_LINK_LOST: "RC bağlantısı koptu",
    SystemEvent.EVENT_KILL_SWITCH_ACTIVATED: "Kill switch aktive edildi",
}

# SystemEvent.severity → AlertManager severity string.
SEVERITY_MAP = {
    SystemEvent.SEVERITY_INFO: SEVERITY_INFO,
    SystemEvent.SEVERITY_WARNING: SEVERITY_WARNING,
    SystemEvent.SEVERITY_CRITICAL: SEVERITY_CRITICAL,
    SystemEvent.SEVERITY_EMERGENCY: SEVERITY_CRITICAL,  # AlertManager 3-seviye
}


def swarm_state_to_dict(msg: SwarmState) -> dict:
    """SwarmState mesajını JSON-serialize edilebilir dict'e çevir.

    Frontend WebSocket payload'ında bu dict'i kullanır.
    """
    return {
        "swarm_state": msg.swarm_state,
        "leader_id": msg.leader_id,
        "active_agent_count": msg.active_agent_count,
        "active_formation": msg.active_formation,
        "mission_active": msg.mission_active,
        "formation_reached": msg.formation_reached,
        "formation_stable": msg.formation_stable,
        "emergency_active": msg.emergency_active,
        "centroid": [msg.centroid_x, msg.centroid_y, msg.centroid_z],
        "formation_heading_deg": msg.formation_heading_deg,
        "formation_max_error_m": msg.formation_max_error_m,
        "formation_avg_error_m": msg.formation_avg_error_m,
        "formation_heading_error_deg": msg.formation_heading_error_deg,
        "active_mission": msg.active_mission,
        "status_text": msg.status_text,
        "current_qr_id": msg.current_qr_id,
        "current_qr_seq": msg.current_qr_seq,
        "last_event": {
            "type": msg.last_event_type,
            "severity": msg.last_event_severity,
            "source": msg.last_event_source,
            "value": msg.last_event_value,
            "message": msg.last_event_message,
        },
    }


def qr_mission_data_to_dict(msg: QRMissionData) -> dict:
    """QRMissionData mesajını JSON-serialize edilebilir dict'e çevir.

    Şartname V2 kuralı: çözümlenen QR içeriği görev boyunca en az 1 kez GCS'te
    gösterilmeli (aksi halde -20 ceza). Bu dict frontend QRPanel'i besler.
    Üretici: qr_detector; proxy /swarm/public/perception/qr_data'ya relay eder.
    """
    return {
        "detector_agent_id": msg.detector_agent_id,
        "qr_id": msg.qr_id,
        "qr_seq": msg.qr_seq,
        "next_qr": msg.next_qr,
        "team_id": msg.team_id,
        "command_type": msg.command_type,
        # Ham algılama durumu
        "detected": msg.detected,
        "decoded": msg.decoded,
        "valid": msg.valid,
        "raw_text": msg.raw_text,
        "error_message": msg.error_message,
        "confidence": msg.confidence,
        # Aktif görev bölümü bayrakları (bir QR birden fazla iş isteyebilir)
        "formation_active": msg.formation_active,
        "target_active": msg.target_active,
        "maneuver_active": msg.maneuver_active,
        "altitude_active": msg.altitude_active,
        "detach_active": msg.detach_active,
        "complete_mission": msg.complete_mission,
        # Formasyon
        "formation_type": msg.formation_type,
        "spacing_m": msg.spacing_m,
        # Manevra (derece, işaretli)
        "pitch_deg": msg.pitch_deg,
        "roll_deg": msg.roll_deg,
        "yaw_deg": msg.yaw_deg,
        # İrtifa (pozitif = yukarı, m)
        "altitude_agl_m": msg.altitude_agl_m,
        "wait_s": msg.wait_s,
        # Sürüden ayrılma / ekleme
        "target_agent_id": msg.target_agent_id,
        "detach_color": msg.detach_color,
        "detach_wait_s": msg.detach_wait_s,
    }


def agent_status_to_state_fields(msg: AgentStatus) -> dict:
    """AgentStatus mesajından StateStore.update() için kwargs dict'i çıkar."""
    return {
        # Faz 1-4 alanları (geriye uyum)
        "armed": msg.armed,
        "mode": FLIGHT_MODE_LABELS.get(msg.flight_mode, f"mode={msg.flight_mode}"),
        "lat": msg.lat_deg,
        "lon": msg.lon_deg,
        "alt_m": -msg.pos_z,                 # NED z negatif → relative alt pozitif
        "battery_percent": msg.battery_percent,
        "battery_voltage": msg.battery_voltage_v,
        "gps_fix_type": msg.gps_fix_type,
        "gps_satellites": msg.gps_satellites,
        "groundspeed_mps": _ned_speed(msg),
        "yaw_deg": msg.heading_deg,
        # Faz 5 zenginleştirme
        "state": msg.state,
        "role": msg.role,
        "flight_mode": msg.flight_mode,
        "offboard_active": msg.offboard_active,
        "pilot_override_active": msg.pilot_override_active,
        "failsafe_active": msg.failsafe_active,
        "healthy": msg.healthy,
        "pos_x": msg.pos_x,
        "pos_y": msg.pos_y,
        "pos_z": msg.pos_z,
        "vel_x": msg.vel_x,
        "vel_y": msg.vel_y,
        "vel_z": msg.vel_z,
        "roll_deg": msg.roll_deg,
        "pitch_deg": msg.pitch_deg,
        "battery_current_a": msg.battery_current_a,
        "gps_hdop": msg.gps_hdop,
        "home_set": msg.home_set,
        "home_lat": msg.home_lat_deg,
        "home_lon": msg.home_lon_deg,
        "home_alt_amsl_m": msg.home_alt_amsl_m,
        "imu_healthy": msg.imu_healthy,
        "mag_healthy": msg.mag_healthy,
        "baro_healthy": msg.baro_healthy,
        "estimator_ok": msg.estimator_ok,
        "xy_valid": msg.xy_valid,
        "z_valid": msg.z_valid,
        "v_xy_valid": msg.v_xy_valid,
        "origin_synced": msg.origin_synced,
        "rc_link_ok": msg.rc_link_ok,
        "kill_switch_active": msg.kill_switch_active,
        "ready_to_arm": msg.ready_to_arm,
        "rc_signal_failsafe_active": msg.rc_signal_failsafe_active,
        "oscillation_detected": msg.oscillation_detected,
        "unstable_flight": msg.unstable_flight,
        "status_text": msg.status_text,
    }


class RosBridge:
    """rclpy.Node + ayrı thread'de spinning.

    FastAPI async dünyasıyla çakışmasın diye executor kendi thread'inde döner;
    callback'ler thread-safe StateStore.update_drone() ile besleme yapar.
    """

    NODE_NAME = "yelpence_gcs_bridge"

    # TriggerMission service'in cevap için bekleme süresi.
    TRIGGER_MISSION_TIMEOUT_SEC = 5.0

    def __init__(
        self,
        drone_ids: list[int],
        store: Optional[StateStore] = None,
        alerts: Optional[AlertManager] = None,
        on_agent_status: Optional[Callable[[int, AgentStatus], None]] = None,
        on_swarm_state: Optional[Callable[[dict], None]] = None,
    ):
        """ROS 2 köprüsü.

        Args:
          drone_ids: takip edilecek drone ID'leri (1..N).
          store: AgentStatus → DroneState beslemesi.
          alerts: SystemEvent → push_event ile uyarı paneli beslemesi.
          on_agent_status, on_swarm_state: ek callback'ler (test/debug).
        """
        self.drone_ids = sorted(drone_ids)
        self.store = store
        self.alerts = alerts
        self.on_agent_status = on_agent_status
        self.on_swarm_state = on_swarm_state

        # SwarmState son snapshot'ı — WebSocket payload'ı buradan okur.
        self.latest_swarm_state: Optional[dict] = None
        self._swarm_state_lock = threading.Lock()

        # QRMissionData son snapshot'ı — çözülmüş QR içeriği (şartname V2:
        # görev boyunca en az 1 kez GCS'te gösterilmeli). WebSocket buradan okur.
        self.latest_qr: Optional[dict] = None
        self._qr_lock = threading.Lock()

        self._node: Optional[Node] = None
        self._executor: Optional[SingleThreadedExecutor] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        # Service client + publisher (Aşama 3)
        self._trigger_mission_client = None
        self._control_pub = None
        # QR konum tablosu yayıncısı (operatör → drone, latched). QRCoordinates
        # mesajı derli değilse None kalır.
        self._qr_coords_pub = None

    def get_swarm_state(self) -> Optional[dict]:
        with self._swarm_state_lock:
            return self.latest_swarm_state

    def get_qr_data(self) -> Optional[dict]:
        with self._qr_lock:
            return self.latest_qr

    def trigger_mission(
        self,
        mission_id: int,
        command: int,
        team_id: str = "",
        parameters_json: str = "",
    ) -> dict:
        """TriggerMission.srv çağrısı — GCS'in tek müdahale yolu.

        Senkron — service çağrı thread'de blocking yapılır, max
        TRIGGER_MISSION_TIMEOUT_SEC bekler. FastAPI endpoint'i bunu
        run_in_executor ile çağırmalı (event loop'u bloklamasın).

        Returns:
          {"success": bool, "message": str}
        """
        if self._trigger_mission_client is None:
            return {"success": False, "message": "ROS 2 service client hazır değil"}

        # Karşı tarafta server var mı?
        if not self._trigger_mission_client.service_is_ready():
            # Bir kez wait — server yeni başladıysa şans verelim.
            ready = self._trigger_mission_client.wait_for_service(timeout_sec=1.0)
            if not ready:
                return {
                    "success": False,
                    "message": (
                        "/swarm/mission/trigger service'i bulunamadı "
                        "(mission_fsm çalışıyor mu?)"
                    ),
                }

        req = TriggerMission.Request()
        req.mission_id = int(mission_id)
        req.command = int(command)
        req.team_id = str(team_id or "")
        req.parameters_json = str(parameters_json or "")

        future = self._trigger_mission_client.call_async(req)

        # Future'u kendi executor thread'imizde döndüğümüz için spin_until
        # yerine event üzerinden bekleyelim. rclpy Future done callback'i
        # destekler.
        done_evt = threading.Event()
        future.add_done_callback(lambda _f: done_evt.set())
        if not done_evt.wait(timeout=self.TRIGGER_MISSION_TIMEOUT_SEC):
            self._trigger_mission_client.remove_pending_request(future)
            return {
                "success": False,
                "message": f"Service zaman aşımı ({self.TRIGGER_MISSION_TIMEOUT_SEC}s)",
            }

        if future.exception() is not None:
            return {"success": False, "message": f"Service hatası: {future.exception()}"}

        resp = future.result()
        return {"success": bool(resp.success), "message": str(resp.message)}

    def publish_swarm_control(self, payload: dict) -> None:
        """SwarmControlCommand.msg yayınla — Görev 2 joystick frame'i.

        payload: frontend'den gelen normalized joystick + mod + bayraklar.
        20-50 Hz çağrı bekleniyor; mesaj inşası fast-path.
        """
        if self._control_pub is None:
            raise RuntimeError("SwarmControlCommand publisher hazır değil")

        m = SwarmControlCommand()
        m.stamp = self._node.get_clock().now().to_msg()
        m.sequence_num = int(payload.get("sequence_num", 0))
        m.command_valid = bool(payload.get("command_valid", False))
        m.deadman_pressed = bool(payload.get("deadman_pressed", False))
        m.deadman_timeout_s = float(payload.get("deadman_timeout_s", 0.5))
        m.mode = int(payload.get("mode", SwarmControlCommand.MODE_UNKNOWN))
        m.pitch_cmd = float(payload.get("pitch_cmd", 0.0))
        m.roll_cmd = float(payload.get("roll_cmd", 0.0))
        m.yaw_cmd = float(payload.get("yaw_cmd", 0.0))
        m.throttle_cmd = float(payload.get("throttle_cmd", 0.0))
        m.takeoff = bool(payload.get("takeoff", False))
        m.land = bool(payload.get("land", False))
        m.rtl = bool(payload.get("rtl", False))
        m.emergency_stop = bool(payload.get("emergency_stop", False))
        m.formation_change_requested = bool(payload.get("formation_change_requested", False))
        m.requested_formation = int(
            payload.get("requested_formation", SwarmControlCommand.FORMATION_UNKNOWN)
        )
        m.requested_spacing_m = float(payload.get("requested_spacing_m", 0.0))
        m.duration_s = float(payload.get("duration_s", 0.0))
        m.max_speed_mps = float(payload.get("max_speed_mps", 0.0))
        m.max_yaw_rate_deg_s = float(payload.get("max_yaw_rate_deg_s", 0.0))
        m.max_tilt_deg = float(payload.get("max_tilt_deg", 0.0))
        m.source_module = str(payload.get("source_module", "gcs"))
        self._control_pub.publish(m)

    def publish_qr_coords(
        self,
        qr_ids: list,
        lat_deg: list,
        lon_deg: list,
        alt_m: Optional[list] = None,
    ) -> None:
        """QRCoordinates.msg yayınla — operatörün girdiği QR konum tablosu.

        Paralel diziler EŞİT uzunlukta olmalı (çağıran doğrular). Latched
        topic'e yayınlanır; tek sefer basmak yeterli, sonradan başlayan
        drone'lar son tabloyu otomatik alır.

        alt_m opsiyonel: form yalnızca enlem/boylam topluyor (irtifa QR
        görev komutundan gelir). Mevcut mesajda alt_m alanı varsa sıfırla
        (ya da verilen) doldurulur; Şeyda alt_m'i çıkarırsa hasattr guard'ı
        sayesinde kod kırılmaz.
        """
        if self._qr_coords_pub is None:
            raise RuntimeError(
                "QRCoordinates yayıncısı yok — swarm_interfaces'te QRCoordinates "
                "mesajı derli değil (feature/qr-coordinates merge edilmeli)."
            )
        n = len(qr_ids)
        if not (len(lat_deg) == n and len(lon_deg) == n):
            raise ValueError("qr_ids/lat_deg/lon_deg eşit uzunlukta olmalı")

        m = QRCoordinates()
        m.stamp = self._node.get_clock().now().to_msg()
        m.qr_ids = [int(x) for x in qr_ids]
        m.lat_deg = [float(x) for x in lat_deg]
        m.lon_deg = [float(x) for x in lon_deg]
        # alt_m alanı mesajda hâlâ varsa doldur (yoksa Şeyda çıkarmıştır — atla).
        if hasattr(m, "alt_m"):
            alts = alt_m if (alt_m is not None and len(alt_m) == n) else [0.0] * n
            m.alt_m = [float(x) for x in alts]
        self._qr_coords_pub.publish(m)
        logger.info("QRCoordinates yayınlandı: %d QR konumu (latched)", n)

    def start(self) -> None:
        """rclpy init + node + subscriber'lar + executor thread başlat."""
        if not rclpy.ok():
            rclpy.init(args=None)

        self._node = Node(self.NODE_NAME)
        logger.info("ROS 2 node oluşturuldu: %s", self.NODE_NAME)

        # Drone başına AgentStatus subscriber.
        # QoS: kontrata göre BEST_EFFORT, 5-20 Hz.
        # TOPIC ADLANDIRMA — network_proxy kontratı (INTERFACE_CONTRACT.md):
        #   yayıncı (drone) → /swarm/internal/...  (proxy ESP-NOW süzgecinden geçirir)
        #   abone  (tüketici) → /swarm/public/...  (proxy çıktısı)
        # GCS bir TÜKETİCİDİR → daima /swarm/public/... dinler.
        # GCS joystick komutu AĞA GİRER → /swarm/internal/control/command'a yayınlar.
        sensor_qos = QoSPresetProfiles.SENSOR_DATA.value
        for drone_id in self.drone_ids:
            topic = f"/swarm/public/drone{drone_id}/status"
            self._node.create_subscription(
                AgentStatus,
                topic,
                self._make_agent_status_cb(drone_id),
                sensor_qos,
            )
            logger.info("subscribe → %s (drone_id=%d)", topic, drone_id)

        # SwarmState — kontrata göre RELIABLE, 1-10 Hz. swarm_fsm yayıncı.
        # Mesaj gelmezse latest_swarm_state None kalır (frontend bunu handle eder).
        reliable_qos = QoSProfile(depth=10, reliability=QoSReliabilityPolicy.RELIABLE)
        self._node.create_subscription(
            SwarmState, "/swarm/public/state", self._on_swarm_state, reliable_qos
        )
        logger.info("subscribe → /swarm/public/state")

        # SystemEvent — RELIABLE event akışı. agent_fsm + diğerleri yayıncı.
        self._node.create_subscription(
            SystemEvent, "/swarm/public/events/system", self._on_system_event, reliable_qos
        )
        logger.info("subscribe → /swarm/public/events/system")

        # QRMissionData — çözülmüş QR görev içeriği. qr_detector yayıncı,
        # proxy /swarm/public/perception/qr_data'ya relay eder. RELIABLE:
        # QR mesajı GCS'te en az 1 kez görünmeli (şartname V2, -20 ceza).
        self._node.create_subscription(
            QRMissionData,
            "/swarm/public/perception/qr_data",
            self._on_qr_data,
            reliable_qos,
        )
        logger.info("subscribe → /swarm/public/perception/qr_data")

        # TriggerMission service client — GCS'in tek müdahale noktası.
        # mission_fsm_node karşı tarafta server (doğrulandı: /swarm/mission/trigger).
        self._trigger_mission_client = self._node.create_client(
            TriggerMission, "/swarm/mission/trigger"
        )
        logger.info("service client → /swarm/mission/trigger")

        # SwarmControlCommand publisher — Görev 2 joystick mesajı.
        # GCS ağa komut enjekte ettiği için /swarm/internal/... (proxy public'e iletir).
        # Kontrata göre BEST_EFFORT, 20-50 Hz; deadman switch ile guard.
        self._control_pub = self._node.create_publisher(
            SwarmControlCommand, "/swarm/internal/control/command", sensor_qos
        )
        logger.info("publisher → /swarm/internal/control/command")

        # QRCoordinates publisher — operatörün girdiği QR konum tablosu.
        # Kontrat: GCS /swarm/internal/mission/qr_coords'a yayınlar, proxy
        # /swarm/public/mission/qr_coords'a iletir, mission_fsm tabloyu saklar.
        # QoS LATCHED (RELIABLE + TRANSIENT_LOCAL, depth=1) — SwarmOrigin gibi:
        # sonradan başlayan/katılan drone son tabloyu otomatik alır. Proxy
        # aboneliği (_ORIGIN_QOS) ile eşleşmeli, yoksa hiç bağlanmaz.
        if _HAS_QR_COORDS:
            latched_qos = QoSProfile(
                depth=1,
                reliability=QoSReliabilityPolicy.RELIABLE,
                durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            )
            self._qr_coords_pub = self._node.create_publisher(
                QRCoordinates, "/swarm/internal/mission/qr_coords", latched_qos
            )
            logger.info("publisher → /swarm/internal/mission/qr_coords (latched)")
        else:
            self._qr_coords_pub = None
            logger.warning(
                "QRCoordinates mesajı derli değil — QR konum yayını devre dışı "
                "(feature/qr-coordinates merge edilmeli)"
            )

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)

        self._thread = threading.Thread(
            target=self._spin, daemon=True, name="ros2-bridge"
        )
        self._thread.start()
        logger.info("ROS 2 bridge başladı (executor thread aktif)")

    def stop(self) -> None:
        """Spinning'i durdur, node'u temizle."""
        self._stop.set()
        if self._executor is not None:
            self._executor.shutdown()
        if self._node is not None:
            self._node.destroy_node()
        # rclpy.shutdown() process kapanışında kendiliğinden — birden fazla
        # bridge çalıştırılırsa diye burada agresif kapatmıyoruz.
        logger.info("ROS 2 bridge durdu")

    # --- Internals ----------------------------------------------------------

    def _spin(self) -> None:
        try:
            while not self._stop.is_set() and rclpy.ok():
                # timeout_sec → stop event'ini kontrol edebilelim
                self._executor.spin_once(timeout_sec=0.5)
        except Exception:
            logger.exception("ROS 2 spin hatası")

    def _on_swarm_state(self, msg: SwarmState) -> None:
        snapshot = swarm_state_to_dict(msg)
        with self._swarm_state_lock:
            self.latest_swarm_state = snapshot
        if self.on_swarm_state is not None:
            try:
                self.on_swarm_state(snapshot)
            except Exception:
                logger.exception("on_swarm_state callback hatası")
        logger.debug(
            "SwarmState swarm=%d leader=%d active=%d formation=%d mission_active=%s",
            msg.swarm_state, msg.leader_id, msg.active_agent_count,
            msg.active_formation, msg.mission_active,
        )

    def _on_qr_data(self, msg: QRMissionData) -> None:
        # SADECE çözülmüş QR'ları sakla. qr_detector sürekli yayın yapıp
        # QR görüş alanında değilken decoded=false frame gönderebilir; bunlar
        # son geçerli QR'ı EZMEMELİ (şartname V2: çözülen QR görev boyunca
        # ekranda kalmalı, yoksa -20). Böylece "en son çözülen QR" kalıcı olur.
        if not msg.decoded:
            logger.debug(
                "QRMissionData çözülmemiş frame atlandı (detected=%s)", msg.detected
            )
            return
        snapshot = qr_mission_data_to_dict(msg)
        with self._qr_lock:
            self.latest_qr = snapshot
        logger.debug(
            "QRMissionData qr_id=%d seq=%d decoded=%s valid=%s next=%d "
            "form=%d alt=%.1f detach=%s",
            msg.qr_id, msg.qr_seq, msg.decoded, msg.valid, msg.next_qr,
            msg.formation_type, msg.altitude_agl_m, msg.detach_active,
        )

    def _on_system_event(self, msg: SystemEvent) -> None:
        if self.alerts is None:
            return
        try:
            label = SYSTEM_EVENT_LABELS.get(msg.event_type, f"event_{msg.event_type}")
            severity = SEVERITY_MAP.get(msg.severity, SEVERITY_INFO)
            # Mesaj custom alanı varsa onu, yoksa enum etiketini göster.
            text = msg.message.strip() if msg.message else label
            # source_agent_id 0 = sistem geneli; aksi halde drone_id olarak göster.
            drone_id = msg.source_agent_id if msg.source_agent_id != 0 else 0
            self.alerts.push_event(
                drone_id=drone_id,
                severity=severity,
                code=f"event_{msg.event_type}",
                message=f"{label}: {text}" if text != label else label,
            )
        except Exception:
            logger.exception("SystemEvent → AlertManager bağlantı hatası")

    def _make_agent_status_cb(self, drone_id: int):
        def cb(msg: AgentStatus) -> None:
            if self.store is not None:
                try:
                    self.store.update(drone_id, **agent_status_to_state_fields(msg))
                except Exception:
                    logger.exception(
                        "StateStore update hatası (drone=%d)", drone_id
                    )
            if self.on_agent_status is not None:
                try:
                    self.on_agent_status(drone_id, msg)
                except Exception:
                    logger.exception(
                        "on_agent_status callback hatası (drone=%d)", drone_id
                    )
            logger.debug(
                "AgentStatus drone=%d state=%d mode=%d armed=%s "
                "pos=(%.1f,%.1f,%.1f) bat=%.1f%% gps=%d sat=%d",
                drone_id, msg.state, msg.flight_mode, msg.armed,
                msg.pos_x, msg.pos_y, msg.pos_z,
                msg.battery_percent, msg.gps_fix_type, msg.gps_satellites,
            )
        return cb
