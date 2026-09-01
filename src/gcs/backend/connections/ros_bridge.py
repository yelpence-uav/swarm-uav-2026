"""ROS 2 köprüsü — swarm_interfaces kontratı üzerinden drone'larla konuşur.

GCS'in birincil iletişim katmanı. Faz 1-4'teki MavlinkListener'ın yerini alır;
MAVLink yan-yolu (sim erken testi için) `mavlink_listener.py` altında fallback
olarak kalır, `connection_mode` ile seçilir.

GCS rolü (kontrat 3.3):
  - Subscribe: AgentStatus, SwarmState, SystemEvent, ElectionResult,
              LandingZoneDetection
  - Service client: TriggerMission (Görev başlat/durdur), ManageSwarmMember (debug)

Bu dosya iskelet sürüm — şimdilik sadece AgentStatus subscriber + log.
Aşama 2'de StateStore beslemesi, Aşama 3'te service client + publisher eklenir.

Çalıştırma ön koşulu:
  source /opt/ros/jazzy/setup.bash
  source /home/yelpence/ros2_ws/install/setup.bash   # swarm_interfaces için
"""

import json
import logging
import math
import threading
import time
from typing import Callable, Optional

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSPresetProfiles,
    QoSProfile,
    QoSReliabilityPolicy,
)

from std_msgs.msg import Bool, Float32MultiArray, String, UInt8MultiArray
from swarm_interfaces.msg import (
    AgentStatus,
    GuidedCommand,
    SwarmControlCommand,
    QRMissionData,
    SwarmOrigin,
    SwarmState,
    SystemEvent,
)

# WGS84 ekvatoral yarıçap (m) — harita lat/lon → yerel NED çevirisi için.
_R_EARTH = 6378137.0
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

# MissionType.SEMI_AUTONOMOUS ve TriggerMission.Request.COMMAND_START.
# Enum'lari import ETMIYORUZ: backend `swarm_state_machine`'e bagimli degil
# ve oyle kalmali (yalniz `swarm_interfaces`).
_MISSION_SEMI_AUTONOMOUS = 2
_COMMAND_START = 1
_COMMAND_ABORT = 2


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
    SystemEvent.EVENT_AGENT_FAULT: "Drone arızalandı",
    SystemEvent.EVENT_AGENT_JOIN_REQUEST: "Sürüye katılmak istiyor",
    SystemEvent.EVENT_AGENT_PILOT_OVERRIDE: "Pilot müdahalesi",
    SystemEvent.EVENT_QR_DETECTED: "QR algılandı",
    SystemEvent.EVENT_QR_PARSED: "QR okundu",
    SystemEvent.EVENT_FORMATION_REACHED: "Formasyon kuruldu",
    SystemEvent.EVENT_FORMATION_FAILED: "Formasyon kurulamadı",
    SystemEvent.EVENT_MISSION_STARTED: "Görev başladı",
    SystemEvent.EVENT_MISSION_COMPLETED: "Görev tamamlandı",
    SystemEvent.EVENT_COLOR_ZONE_DETECTED: "Renkli iniş alanı bulundu",
    SystemEvent.EVENT_QR_SEQUENCE_REJECTED: "QR sırası uymadı, atlandı",
    SystemEvent.EVENT_PRECISION_LANDING_STARTED: "Hassas iniş başladı",
    SystemEvent.EVENT_PRECISION_LANDING_COMPLETED: "Hassas iniş tamamlandı",
    SystemEvent.EVENT_ROTATION_STARTED: "Formasyon rotasyonu başladı",
    SystemEvent.EVENT_ROTATION_COMPLETED: "Formasyon rotasyonu tamamlandı",
    SystemEvent.EVENT_MANEUVER_STARTED: "Manevra başladı",
    SystemEvent.EVENT_MANEUVER_COMPLETED: "Manevra tamamlandı",
    SystemEvent.EVENT_MANEUVER_FAILED: "Manevra başarısız",
    SystemEvent.EVENT_MEMBER_DETACH_STARTED: "Sürüden ayrılma başladı",
    SystemEvent.EVENT_MEMBER_REJOIN_STARTED: "Sürüye katılma başladı",
    SystemEvent.EVENT_MEMBER_MANAGEMENT_FAILED: "Sürü üyesi değişimi başarısız",
    SystemEvent.EVENT_GCS_LINK_LOST: "Yer istasyonu bağlantısı koptu",
    SystemEvent.EVENT_GCS_LINK_RESTORED: "Yer istasyonu bağlantısı geri geldi",
    SystemEvent.EVENT_BATTERY_LOW: "Pil azaldı",
    SystemEvent.EVENT_COLLISION_RISK: "Çarpışma riski",
    SystemEvent.EVENT_OFFBOARD_LOST: "OFFBOARD modundan çıkıldı",
    SystemEvent.EVENT_RTL_TRIGGERED: "Kalkış noktasına dönüyor",
    SystemEvent.EVENT_EMERGENCY_LAND: "Acil iniş",
    SystemEvent.EVENT_PX4_LINK_LOST: "Uçuş kontrolcüsü bağlantısı koptu",
    SystemEvent.EVENT_LEADER_CHANGED: "Lider değişti",
    SystemEvent.EVENT_SAFETY_HOLD: "Güvenlik için bekletiliyor",
    SystemEvent.EVENT_FAILSAFE_CLEARED: "Failsafe durumu geçti",
    SystemEvent.EVENT_ORIGIN_READY: "Sürü başlangıç noktası hazır",
    SystemEvent.EVENT_ORIGIN_SYNCED: "Başlangıç noktası eşitlendi",
    SystemEvent.EVENT_ORIGIN_FAILED: "Başlangıç noktası eşitlenemedi",
    SystemEvent.EVENT_OSCILLATION_DETECTED: "Salınım başladı",
    SystemEvent.EVENT_UNSTABLE_FLIGHT: "Kararsız uçuş",
    SystemEvent.EVENT_GEOFENCE_VIOLATION: "Uçuş alanı sınırı aşıldı",
    SystemEvent.EVENT_ALTITUDE_LIMIT_EXCEEDED: "İrtifa sınırı aşıldı",
    SystemEvent.EVENT_RC_LINK_LOST: "Kumanda bağlantısı koptu",
    SystemEvent.EVENT_KILL_SWITCH_ACTIVATED: "Kill switch çekildi",

    # HOME DENETIMI (px4_bridge._OLAY_HOME_*) — 26 Agustos saha olayi.
    # SystemEvent.msg'de 38/39 BOS (37'den 40'a atliyor); sabit olarak
    # EKLENMEDI cunku arayuz degisikligi swarm_interfaces'i ve tum
    # bagimlilarini yeniden derletir, uc ucaga dagitim ister (TUZAKLAR
    # §2.11b). Kod telde zaten uint8; isim sadece okunabilirlik icin.
    # 60-68 arasi Pi olaylari icin de birebir ayni sey yapilmis.
    # value = olculen sapma (m).
    38: "HOME kaydı güvenilmez — RTL kapalı, iniş land ile (m)",
    39: "HOME otomatik düzeltildi — doğrulaması bekleniyor",

    # TASIMA KATMANI (packet_parser.OLAY_TIPI_*) — SystemEvent.msg'de yok,
    # cunku bunlar ucaktaki bir dugumun urettigi olaylar degil, olay yolunun
    # KENDI hakkinda soyledikleri. SystemEvent'in 0-59 araligiyla cakismaz.
    # Pi ANA SISTEM (packet_parser.OLAY_TIPI_PI_*). SIDDET DURUMU ANLATIR:
    # aciliş WARNING/CRITICAL, normale donus INFO. Deger her iki durumda da
    # tasinir, yani "Pi sıcaklığı (82)" kritik, "(64)" bilgi olarak okunur.
    60: "Pi sıcaklığı",
    61: "Pi beslemesi düşük — güç kısıtlaması",
    62: "Pi diski doluyor",
    63: "Pi belleği azaldı",
    64: "Pi yükü yüksek",
    65: "Drone konteyneri çalışmıyor",
    66: "ROS düğümü eksik",
    67: "Pi Wi-Fi bağlantısı",
    68: "MAVROS yer istasyonu hattı bozuk — günlük şişiyor (MB)",

    250: "Olay gönderim sınırı doldu — bazı olaylar iletilemedi",
    251: "Olay mesh üzerinde kayboldu",
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

        # RTCM izleme: akis var mi, ne hizda. Veriyi saklamiyoruz, sadece olcuyoruz.
        self._rtk_lock = threading.Lock()
        self._rtk_toplam = 0
        self._rtk_bayt = 0
        self._rtk_son_t = 0.0
        self._rtk_pencere = []   # (zaman, bayt) — son birkac saniye

        self._node: Optional[Node] = None
        self._executor: Optional[SingleThreadedExecutor] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        # Service client + publisher (Aşama 3)
        self._trigger_mission_client = None
        # Guided (YKİ tekil komut) yayıncısı + harita→NED için son origin.
        self._guided_pub = None
        self._gorev_baslat_pub = None
        self._g2_ayar_pub = None
        self._kumanda = None
        self._kumanda_lock = threading.Lock()
        self._son_origin: Optional[SwarmOrigin] = None
        # QR konum tablosu yayıncısı (operatör → drone, latched). QRCoordinates
        # mesajı derli değilse None kalır.
        self._qr_coords_pub = None

    def get_swarm_state(self) -> Optional[dict]:
        with self._swarm_state_lock:
            return self.latest_swarm_state

    def get_kumanda(self) -> Optional[dict]:
        """Sürü kumandasının SON komutu (mesh'ten). Arayüz sanal görünüm çizer.

        Veri kaynağı mesh: pilot uçağı (ylp00) `SwarmControlCommand` yayınlıyor,
        base ESP köprüsü onu `/swarm/public/control/command`'a düşürüyor.
        **Yeni mesh trafiği YOK** — zaten uçan veriyi gösteriyoruz.

        `yas_s` ŞART: komut akışı kesilince arayüz "son görülen" değerleri
        canlıymış gibi göstermemeli. Kumanda kapanınca alıcı son çerçeveyi
        tutuyor (TUZAKLAR §9.5 sınıfı), yani donuk veri gerçekçi görünür.
        """
        with self._kumanda_lock:
            k = self._kumanda
            if k is None:
                return None
            return dict(k, yas_s=round(time.time() - k["t"], 2))

    def _on_kumanda(self, msg) -> None:
        with self._kumanda_lock:
            self._kumanda = {
                "t": time.time(),
                "pitch": round(float(msg.pitch_cmd), 3),
                "roll": round(float(msg.roll_cmd), 3),
                "yaw": round(float(msg.yaw_cmd), 3),
                "gaz": round(float(msg.throttle_cmd), 3),
                "deadman": bool(msg.deadman_pressed),
                "gecerli": bool(msg.command_valid),
                "mod": int(msg.mode),
                "takeoff": bool(msg.takeoff),
                "land": bool(msg.land),
                "formasyon": int(msg.requested_formation),
                "aralik_m": round(float(msg.requested_spacing_m), 2),
            }

    def _on_rtcm(self, msg) -> None:
        t = time.time()
        n = len(msg.data)
        with self._rtk_lock:
            self._rtk_toplam += 1
            self._rtk_bayt += n
            self._rtk_son_t = t
            self._rtk_pencere.append((t, n))
            # 5 sn'lik kayan pencere — anlik hiz icin
            kesme = t - 5.0
            while self._rtk_pencere and self._rtk_pencere[0][0] < kesme:
                self._rtk_pencere.pop(0)

    def get_rtk_status(self) -> dict:
        """RTCM akisinin durumu — arayuzdeki RTK gostergesi bunu okur.

        'bagli' = son 3 sn icinde RTCM geldi mi. u-blox cikarilirsa ya da
        okuyucu coker/hic baslamazsa bu alan false'a duser ve arayuzde
        gorunur. Onceden bunu anlamanin tek yolu drone'a SSH atip
        px4_bridge logundaki 'rtk: msg=' sayacina bakmakti.
        """
        t = time.time()
        with self._rtk_lock:
            yas = (t - self._rtk_son_t) if self._rtk_son_t else None
            pencere = list(self._rtk_pencere)
            toplam = self._rtk_toplam
        if pencere:
            aralik = max(0.001, t - pencere[0][0])
            hz = len(pencere) / aralik
            bps = sum(n for _, n in pencere) / aralik
        else:
            hz = 0.0
            bps = 0.0
        return {
            "bagli": yas is not None and yas < 3.0,
            "msg_hz": round(hz, 1),
            "bayt_s": int(bps),
            "toplam": toplam,
            "son_paket_s": round(yas, 1) if yas is not None else None,
        }

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
        # 🔴 GÖREV 2 BAŞLAT MESH'TEN GİDER — 31 Ağustos 2026.
        #
        # ROS servisi uçaklardan GÖRÜNMÜYOR: baslat.sh `ROS_LOCALHOST_ONLY=1`
        # ile koşuyor, yani drone'ların servisleri YKİ laptopunun ROS
        # grafiğinde YOK (ölçüldü: `ros2 service list` içinde çıkmıyor).
        # Bu yüzden "Görev 2 BAŞLAT" butonu uçaklara ULAŞAMIYORDU ve görev
        # 31 Ağustos gecesi SSH ile elle tetiklenmek zorunda kaldı.
        #
        # Mesh yolu bu boşluğu kapatıyor ve Wi-Fi'ye de bağımlı değil.
        # Servis çağrısı YİNE denenir (SITL/yerel kurulumlarda çalışır);
        # mesh yayını ondan BAĞIMSIZ gider, biri tutmasa öteki tutar.
        mesh_gonderildi = False
        if int(mission_id) == _MISSION_SEMI_AUTONOMOUS:
            if int(command) == _COMMAND_START:
                # 🔴 MADDE 29 — ARALIK/IRTIFA BASLATMADAN ÖNCE YAYINLANIR.
                #
                # Sıra ÖNEMLİ: esp32_bridge ayarı önbelleğe alır ve BAŞLAT
                # paketine koyar. Ters sırada başlatma paketi ESKİ ayarla
                # (ya da ayarsız) giderdi — operatör sayıyı girmiş olur,
                # sürü eski değerle uçardı. Sessiz ve tam olarak "hata
                # vermeden yanlış sonuç" sınıfı.
                #
                # Ayar konusu MANDALLI (TRANSIENT_LOCAL): iki yayın arasında
                # esp32_bridge yeniden başlasa bile son değeri alır.
                self._g2_ayar_yayinla(parameters_json)
                mesh_gonderildi = self.publish_gorev_baslat(True)
            elif int(command) == _COMMAND_ABORT:
                mesh_gonderildi = self.publish_gorev_baslat(False)

        if self._trigger_mission_client is None:
            if mesh_gonderildi:
                return {"success": True,
                        "message": "Görev 2 komutu mesh'ten yayınlandı"}
            return {"success": False, "message": "ROS 2 service client hazır değil"}

        # Karşı tarafta server var mı?
        if not self._trigger_mission_client.service_is_ready():
            # Bir kez wait — server yeni başladıysa şans verelim.
            ready = self._trigger_mission_client.wait_for_service(timeout_sec=1.0)
            if not ready:
                if mesh_gonderildi:
                    # Beklenen durum: YKİ drone'ların ROS grafiğini görmez.
                    return {
                        "success": True,
                        "message": ("Görev 2 komutu mesh'ten yayınlandı "
                                    "(yerel ROS servisi yok — normal)"),
                    }
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

    def _g2_ayar_yayinla(self, parameters_json: str) -> None:
        """Görev 2 aralık/irtifa ayarını mesh köprüsüne verir.

        `parameters_json` YKİ'den geliyor:
            {"aralik_m": 9.0, "irtifa_m": 15.0}
        Alan yoksa ya da boşsa 0.0 gönderilir = "belirtilmedi"; uçak kendi
        varsayılanını korur (aralık 7 m). Operatörün hiçbir şey girmemesi
        GEÇERLİ bir seçim.

        🔴 DOĞRULAMA UÇAKTA DA VAR (canli_param.g2_ayar_dogrula). Burada
        yalnız ayrıştırma yapılıyor; sınır denetimini tek yerde tutmak
        için tekrarlamıyoruz — iki kopya kaçınılmaz olarak ayrışır.
        """
        if self._g2_ayar_pub is None:
            return
        aralik = irtifa = 0.0
        if parameters_json:
            try:
                p = json.loads(parameters_json)
                aralik = float(p.get("aralik_m") or 0.0)
                irtifa = float(p.get("irtifa_m") or 0.0)
            except (ValueError, TypeError, AttributeError) as e:
                logger.warning(
                    "Görev 2 parametreleri okunamadı (%s) — varsayılanlar "
                    "korunacak: %s", e, parameters_json
                )
                aralik = irtifa = 0.0
        m = Float32MultiArray()
        m.data = [aralik, irtifa]
        self._g2_ayar_pub.publish(m)
        logger.info(
            "Görev 2 ayarı yayınlandı: aralık=%.1f m irtifa=%.1f m "
            "(0.0 = belirtilmedi)", aralik, irtifa
        )

    def publish_gorev_baslat(self, basla: bool = True) -> bool:
        """Görev 2 BAŞLAT/DURDUR'u mesh'e yayınlar (base ESP iletir).

        Args:
            basla: True = başlat, False = durdur.

        Returns:
            bool: yayınlandıysa True.
        """
        if self._gorev_baslat_pub is None:
            logger.warning("gorev baslat publisher yok — mesh'e yayınlanamadı")
            return False
        m = Bool()
        m.data = bool(basla)
        self._gorev_baslat_pub.publish(m)
        logger.info(
            "Görev 2 %s -> /swarm/internal/mission/baslat (mesh)",
            "BAŞLAT" if basla else "DURDUR",
        )
        return True

    def publish_guided(
        self,
        agent_id: int,
        action: int,
        *,
        altitude_m: float = 0.0,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        heading_deg: float = 0.0,
        heading_valid: bool = False,
    ) -> None:
        """GuidedCommand.msg yayınla — YKİ tekil komut (arm/takeoff/goto/rtl/land).

        agent_id hedef drone (0 = tümü). GOTO için x/y/z yerel NED (metre);
        z aşağı-pozitif (irtifa = -z). Base esp32_bridge mesh'e iletir.
        """
        if self._guided_pub is None:
            raise RuntimeError("GuidedCommand publisher hazır değil")
        m = GuidedCommand()
        m.stamp = self._node.get_clock().now().to_msg()
        m.agent_id = int(agent_id)
        m.action = int(action)
        m.altitude_m = float(altitude_m)
        m.x = float(x)
        m.y = float(y)
        m.z = float(z)
        m.heading_deg = float(heading_deg)
        m.heading_valid = bool(heading_valid)
        self._guided_pub.publish(m)

    def publish_rtk_reset(self, kip: str) -> None:
        """u-blox baz alıcısına reset komutu gönderir (sicak|ilik|soguk).

        Komutu yki_rtcm_reader.py alır ve UBX-CFG-RST olarak seri porta yazar.
        Kip anlamları orada tanımlı; burada doğrulama YAPILMAZ ki iki yerde
        iki ayrı liste tutulmasın — okuyucu bilinmeyen kipi reddedip loglar.
        """
        if self._rtk_komut_pub is None:
            raise RuntimeError("RTK komut publisher hazır değil")
        m = String()
        m.data = str(kip)
        self._rtk_komut_pub.publish(m)

    def has_origin(self) -> bool:
        """Harita→NED çevirisi için origin hazır mı."""
        return self._son_origin is not None

    def latlon_to_ned(self, lat_deg: float, lon_deg: float):
        """Hedef lat/lon'u son SwarmOrigin'e göre yerel NED (kuzey, doğu) metreye çevirir.

        Küçük saha için equirectangular yaklaşımı (birkaç km'de <1 m hata).
        Origin yoksa None döner.
        """
        o = self._son_origin
        if o is None:
            return None
        dlat = math.radians(lat_deg - o.origin_lat_deg)
        dlon = math.radians(lon_deg - o.origin_lon_deg)
        north = dlat * _R_EARTH
        east = dlon * _R_EARTH * math.cos(math.radians(o.origin_lat_deg))
        return (north, east)

    def _on_origin(self, msg: SwarmOrigin) -> None:
        """SwarmOrigin'i sakla (harita→NED çevirisi için). Kalitesiz olanı atla."""
        if msg.valid and msg.gps_fix_type >= 3:
            self._son_origin = msg

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
        # MESH KAYNAKLI konular icin. esp32_bridge _MESH_QOS ile, yani
        # BEST_EFFORT yayinliyor; RELIABLE abone onunla ESLESMEZ ve konu
        # sessizce bos kalir. BEST_EFFORT abone ise her iki yayinciyla da
        # uyumlu — bu yuzden /swarm/public/... dinlerken varsayilan bu olmali.
        best_effort_qos = QoSProfile(
            depth=10, reliability=QoSReliabilityPolicy.BEST_EFFORT)
        self._node.create_subscription(
            SwarmState, "/swarm/public/state", self._on_swarm_state, reliable_qos
        )
        logger.info("subscribe → /swarm/public/state")

        # SystemEvent — RELIABLE event akışı. agent_fsm + diğerleri yayıncı.
        self._node.create_subscription(
            SystemEvent, "/swarm/public/events/system", self._on_system_event, reliable_qos
        )
        logger.info("subscribe → /swarm/public/events/system")

        # QRMissionData — çözülmüş QR görev içeriği.
        #
        # BEST_EFFORT — ÖNCEDEN RELIABLE'DI VE TERS TEPİYORDU (15 Ağustos).
        # Gerekçe "QR mesajı GCS'te en az 1 kez görünmeli (şartname V2,
        # -20 ceza)" idi; niyet doğru ama etkisi TAM TERSİ. Bu konunun mesh
        # kaynağı esp32_bridge ve o _MESH_QOS ile, yani BEST_EFFORT
        # yayınlıyor. RELIABLE abone + BEST_EFFORT yayıncı EŞLEŞMEZ:
        #
        #   [esp32_base] '/swarm/public/perception/qr_data' requesting
        #   incompatible QoS. No messages will be sent to it. RELIABILITY
        #
        # Yani "hiç kaçırmayalım" diye konan ayar, HER ZAMAN hepsini
        # kaçırıyordu. Aynı dosyanın aşağısında doğru not zaten var:
        # "BEST_EFFORT bilerek: yayıncı RELIABLE olsa bile uyumlu, tersi
        # değil." Kayıp riski mesh'in kendisinde (~%30) ve yerel DDS hop'unu
        # RELIABLE yapmak onu geri getirmiyor.
        self._node.create_subscription(
            QRMissionData,
            "/swarm/public/perception/qr_data",
            self._on_qr_data,
            best_effort_qos,
        )
        logger.info("subscribe → /swarm/public/perception/qr_data")

        # RTCM (RTK düzeltmesi) — YALNIZ İZLEME AMAÇLI.
        #
        # NEDEN VAR: 31 Temmuz'da u-blox sonradan takıldı, yki_baslat.sh açılışta
        # portu göremeyip RTCM okuyucusunu HİÇ başlatmamıştı. Arayüzde bunu
        # gösteren hiçbir şey yoktu; RTK'nın akmadığı ancak drone'a SSH atıp
        # px4_bridge logundaki 'rtk: msg=0' sayacına bakınca anlaşıldı.
        # Artık YKİ'de görünüyor.
        #
        # BEST_EFFORT bilerek: yayıncı RELIABLE olsa bile uyumlu, tersi değil.
        # Burada tek bir RTCM paketini kaçırmak zararsız — sayaç zaten akışı
        # ölçüyor, veriyi biz kullanmıyoruz.
        self._node.create_subscription(
            UInt8MultiArray, "/swarm/internal/rtcm", self._on_rtcm, sensor_qos
        )
        logger.info("subscribe → /swarm/internal/rtcm (RTK izleme)")

        # TriggerMission service client — GCS'in tek müdahale noktası.
        # mission_fsm_node karşı tarafta server (doğrulandı: /swarm/mission/trigger).
        self._trigger_mission_client = self._node.create_client(
            TriggerMission, "/swarm/mission/trigger"
        )
        logger.info("service client → /swarm/mission/trigger")

        # GuidedCommand publisher — YKİ tekil komut (arm/takeoff/goto/rtl/land).
        # RELIABLE, depth 10: komut kaybolmamalı, geç katılan re-execute etmesin
        # (VOLATILE). Base esp32_bridge bunu mesh'e iletir.
        guided_qos = QoSProfile(
            depth=10,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        self._guided_pub = self._node.create_publisher(
            GuidedCommand, "/swarm/internal/guided/command", guided_qos
        )
        logger.info("publisher → /swarm/internal/guided/command")

        # Görev 2 BAŞLAT — mesh yolu (bkz. trigger_mission yorumu).
        self._gorev_baslat_pub = self._node.create_publisher(
            Bool, "/swarm/internal/mission/baslat", guided_qos
        )
        logger.info("publisher → /swarm/internal/mission/baslat")

        # --- MADDE 29: Görev 2 aralık/irtifa ayarı (31 Ağustos 2026) ------
        # 🔴 MANDALLI (TRANSIENT_LOCAL) VE RELIABLE, bilerek:
        #   * esp32_bridge BAŞLAT'tan hemen önce yayınlanan bu değeri
        #     kaçırırsa sürü ESKİ aralıkla uçar — sessiz ve yanlış.
        #   * Mandallı olduğu için esp32_bridge sonradan açılsa bile son
        #     ayarı alır; "girdim ama gitmedi" durumu oluşmaz.
        # Abone tarafı (esp32_bridge) AYNI profili kullanıyor; RELIABLE
        # yayıncı + RELIABLE abone eşleşir.
        self._g2_ayar_pub = self._node.create_publisher(
            Float32MultiArray,
            "/swarm/internal/mission/g2_ayar",
            QoSProfile(
                reliability=QoSReliabilityPolicy.RELIABLE,
                durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
                history=QoSHistoryPolicy.KEEP_LAST,
                depth=1,
            ),
        )
        logger.info("publisher → /swarm/internal/mission/g2_ayar")

        # Sürü kumandası sanal görünümü — mesh'ten gelen komutu okur.
        # 🔴 BEST_EFFORT ŞART: esp32_bridge bu konuyu _MESH_QOS (BEST_EFFORT)
        # ile yayınlıyor. RELIABLE abone BEST_EFFORT yayıncıyla EŞLEŞMEZ ve
        # TEK MESAJ BİLE GELMEZ — 30 Ağustos'ta sahada bunun aynısı yaşandı
        # (D1: joystick BEST_EFFORT yayınlıyordu, ic_dis_kopru RELIABLE
        # dinliyordu, komut zinciri sessizce kopuktu).
        kumanda_qos = QoSProfile(
            depth=5,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        self._node.create_subscription(
            SwarmControlCommand,
            "/swarm/public/control/command",
            self._on_kumanda,
            kumanda_qos,
        )
        logger.info("subscriber → /swarm/public/control/command (kumanda)")

        # RTK baz reset komutu (18 Ağustos 2026).
        #
        # Doğrudan seri porta yazmıyoruz: u-blox portunun sahibi
        # yki_rtcm_reader.py ve seri port TEK SAHİPLİ — ikinci bir açan
        # "Resource busy" alır. Komut bu topic'ten okuyucuya gider, yazmayı o
        # yapar. QGC'nin aynı portu kapması da bu sınıftan bir arızaydı
        # (17 Ağustos'ta ölçüldü, AutoConnect→RTK GPS kapatılarak çözüldü).
        #
        # RELIABLE: operatör butona bir kez basar, komut kaybolmamalı.
        self._rtk_komut_pub = self._node.create_publisher(
            String, "/swarm/internal/rtk/komut", guided_qos
        )
        logger.info("publisher → /swarm/internal/rtk/komut (u-blox reset)")

        # SwarmOrigin aboneliği — harita tıklaması (lat/lon) → yerel NED çevirisi
        # için gerekli. Latched (TRANSIENT_LOCAL) ki sonradan başlasak da son
        # origin'i alalım.
        origin_qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._node.create_subscription(
            SwarmOrigin, "/swarm/public/origin", self._on_origin, origin_qos
        )
        logger.info("subscribe → /swarm/public/origin (harita→NED)")

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
            #
            # MESH'TEN GELEN OLAYLARDA `message` HEP BOS: metin mesh'te
            # tasinmiyor (16 bayt ~16 karakter eder), yalniz kod tasiniyor.
            # O yuzden bilgi tasiyan `value` ve `source_module` alanlarini
            # etikete ekliyoruz — aksi halde "Olay KAYBI" yazar ama KAC olay
            # kaybedildigi hicbir yerde gorunmezdi.
            if msg.message:
                mesaj = f"{label}: {msg.message.strip()}"
            else:
                ekler = []
                if msg.value:
                    # %g: 3.0 -> "3", 3.88 -> "3.88" (gereksiz sifir yok)
                    ekler.append(f"{msg.value:g}")
                if msg.source_module:
                    ekler.append(msg.source_module)
                mesaj = f"{label} ({', '.join(ekler)})" if ekler else label
            # source_agent_id 0 = sistem geneli; aksi halde drone_id olarak göster.
            drone_id = msg.source_agent_id if msg.source_agent_id != 0 else 0
            self.alerts.push_event(
                drone_id=drone_id,
                severity=severity,
                code=f"event_{msg.event_type}",
                message=mesaj,
            )
        except Exception:
            logger.exception("SystemEvent → AlertManager bağlantı hatası")

    def _make_agent_status_cb(self, drone_id: int):
        def cb(msg: AgentStatus) -> None:
            if self.store is not None:
                try:
                    # alt_m = -pos_z; pos_z artik drone'un EKF goreli irtifasini
                    # tasiyor (mesh POSE alt_dm), origin gerekmez.
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
