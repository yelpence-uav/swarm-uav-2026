"""Drone telemetrisinin merkezi durum kaydı (thread-safe)."""

import threading
import time
from dataclasses import dataclass


@dataclass
class DroneState:
    drone_id: int
    name: str
    sysid: int

    connected: bool = False
    last_message_time: float = 0.0

    # Temel telemetri
    armed: bool = False
    mode: str = "?"

    lat: float = 0.0
    lon: float = 0.0
    alt_m: float = 0.0  # Relative irtifa (m)

    battery_percent: float = 0.0
    battery_voltage: float = 0.0

    gps_fix_type: int = 0  # 0=yok, 2=2D, 3=3D, 4=DGPS, 5/6=RTK
    gps_satellites: int = 0

    groundspeed_mps: float = 0.0
    yaw_deg: float = 0.0

    # FSM ve rol
    state: int = 0  # AgentStatus.STATE_*
    role: int = 0  # LEADER / FOLLOWER / STANDBY / DETACHED
    flight_mode: int = 0  # FLIGHT_MODE_*

    offboard_active: bool = False
    pilot_override_active: bool = False
    failsafe_active: bool = False
    healthy: bool = False

    # NED pozisyon ve hız
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0  # negatif = yukarı
    vel_x: float = 0.0
    vel_y: float = 0.0
    vel_z: float = 0.0

    # Yönelim (Attitude)
    roll_deg: float = 0.0
    pitch_deg: float = 0.0

    # Ek telemetri
    battery_current_a: float = 0.0
    gps_hdop: float = 0.0

    # Ev konumu (Home)
    home_set: bool = False
    home_lat: float = 0.0
    home_lon: float = 0.0
    home_alt_amsl_m: float = 0.0

    # Sensor + EKF health (gerçek donanım pre-arm + in-flight).
    imu_healthy: bool = False
    mag_healthy: bool = False
    baro_healthy: bool = False
    estimator_ok: bool = False
    xy_valid: bool = False
    z_valid: bool = False
    v_xy_valid: bool = False

    # Origin sync (sahada paylaşılan NED origin).
    origin_synced: bool = False

    # RC + kill switch.
    rc_link_ok: bool = False
    kill_switch_active: bool = False
    rc_signal_failsafe_active: bool = False

    # Uçuş kalitesi.
    oscillation_detected: bool = False
    unstable_flight: bool = False

    status_text: str = ""


class StateStore:
    """3 drone'un anlık durumunu tutan thread-safe kayıt."""

    def __init__(self, offline_timeout_sec: float = 3.0):
        self._drones: dict[int, DroneState] = {}
        self._lock = threading.Lock()
        self._offline_timeout = offline_timeout_sec

    def register_drone(self, drone_id: int, name: str, sysid: int) -> None:
        with self._lock:
            self._drones[drone_id] = DroneState(
                drone_id=drone_id, name=name, sysid=sysid
            )

    def update(self, drone_id: int, **fields) -> None:
        with self._lock:
            d = self._drones.get(drone_id)
            if d is None:
                return
            for key, value in fields.items():
                setattr(d, key, value)
            d.last_message_time = time.time()
            d.connected = True

    def snapshot(self) -> list[DroneState]:
        """Tüm drone durumlarını döndürür ve OFFLINE tespitini yapar."""
        with self._lock:
            now = time.time()
            for d in self._drones.values():
                if (
                    d.last_message_time
                    and (now - d.last_message_time) > self._offline_timeout
                ):
                    d.connected = False
            return list(self._drones.values())
