"""Tek doğruluk kaynağı — drone telemetrisinin merkezi snapshot'ı.

Tüm okuyucular (terminal print, WebSocket, REST API, log servisi) buradan okur.
Tüm yazıcılar (mavlink_listener) buradan yazar. Thread-safe.
"""

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

    armed: bool = False
    mode: str = "?"

    lat: float = 0.0
    lon: float = 0.0
    alt_m: float = 0.0          # Kalkış yerinden yükseklik (relative alt)

    battery_percent: float = 0.0
    battery_voltage: float = 0.0

    gps_fix_type: int = 0       # 0=yok, 2=2D, 3=3D, 4=DGPS, 5/6=RTK
    gps_satellites: int = 0

    groundspeed_mps: float = 0.0
    yaw_deg: float = 0.0


class StateStore:
    """3 drone'un anlık durumunu tutan thread-safe kayıt."""

    def __init__(self, offline_timeout_sec: float = 3.0):
        self._drones: dict[int, DroneState] = {}
        self._lock = threading.Lock()
        self._offline_timeout = offline_timeout_sec

    def register_drone(self, drone_id: int, name: str, sysid: int) -> None:
        with self._lock:
            self._drones[drone_id] = DroneState(drone_id=drone_id, name=name, sysid=sysid)

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
        """Tüm drone'ların anlık durumunu döndürür. OFFLINE tespitini de yapar."""
        with self._lock:
            now = time.time()
            for d in self._drones.values():
                if d.last_message_time and (now - d.last_message_time) > self._offline_timeout:
                    d.connected = False
            return list(self._drones.values())
