"""Tek MAVLink kanalını dinler, sysid'ye göre 3 drone'a demultiplex eder.

Bağlantı string'i pymavlink format'ında olmalı:
  - udpin:0.0.0.0:14550        (PX4 SITL veya ESP-NOW gateway)
  - serial:/dev/ttyUSB0:57600  (gerçek donanım, USB üstünden)
"""

import math
import threading

from pymavlink import mavutil

from backend.core.state_store import StateStore


PX4_MAIN_MODE_MAP = {
    1: "MANUAL",
    2: "ALTCTL",
    3: "POSCTL",
    4: "AUTO",
    5: "ACRO",
    6: "OFFBOARD",
    7: "STABILIZED",
    8: "RATTITUDE",
}

# AUTO ana modunun alt modları — yerde LOITER, kalkışta TAKEOFF, dönüşte RTL gibi
PX4_AUTO_SUB_MODE_MAP = {
    1: "READY",
    2: "TAKEOFF",
    3: "LOITER",
    4: "MISSION",
    5: "RTL",
    6: "LAND",
    8: "FOLLOW",
    9: "PRECLAND",
}


def parse_px4_mode(custom_mode: int) -> str:
    main_mode = (custom_mode >> 16) & 0xFF
    sub_mode = (custom_mode >> 24) & 0xFF

    main_name = PX4_MAIN_MODE_MAP.get(main_mode)
    if main_name is None:
        return f"raw:{custom_mode:#x}"

    if main_mode == 4 and sub_mode in PX4_AUTO_SUB_MODE_MAP:
        return f"AUTO.{PX4_AUTO_SUB_MODE_MAP[sub_mode]}"

    return main_name


class MavlinkListener:
    """Tek MAVLink endpoint dinler, sysid → drone_id eşlemesine göre dağıtır."""

    def __init__(self, connection_string: str, sysid_to_drone_id: dict[int, int], store: StateStore):
        self.connection_string = connection_string
        self.sysid_map = sysid_to_drone_id
        self.store = store
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="mavlink-listener"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        link = mavutil.mavlink_connection(self.connection_string, dialect="common")
        print(
            f"[mavlink] Dinleniyor: {self.connection_string} | "
            f"beklenen sysid'ler: {sorted(self.sysid_map.keys())}"
        )

        while not self._stop.is_set():
            msg = link.recv_match(blocking=True, timeout=1.0)
            if msg is None:
                continue
            sysid = msg.get_srcSystem()
            drone_id = self.sysid_map.get(sysid)
            if drone_id is None:
                continue
            self._dispatch(drone_id, msg)

    def _dispatch(self, drone_id: int, msg) -> None:
        t = msg.get_type()

        if t == "HEARTBEAT":
            armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            mode = parse_px4_mode(msg.custom_mode)
            self.store.update(drone_id, armed=armed, mode=mode)

        elif t == "GLOBAL_POSITION_INT":
            self.store.update(
                drone_id,
                lat=msg.lat / 1e7,
                lon=msg.lon / 1e7,
                alt_m=msg.relative_alt / 1000.0,
            )

        elif t == "BATTERY_STATUS":
            pct = msg.battery_remaining if msg.battery_remaining >= 0 else 0
            voltage = (msg.voltages[0] / 1000.0) if msg.voltages and msg.voltages[0] != 65535 else 0.0
            self.store.update(drone_id, battery_percent=float(pct), battery_voltage=voltage)

        elif t == "SYS_STATUS":
            voltage = msg.voltage_battery / 1000.0
            pct = msg.battery_remaining if msg.battery_remaining >= 0 else 0
            self.store.update(drone_id, battery_voltage=voltage, battery_percent=float(pct))

        elif t == "GPS_RAW_INT":
            self.store.update(
                drone_id,
                gps_fix_type=msg.fix_type,
                gps_satellites=msg.satellites_visible,
            )

        elif t == "VFR_HUD":
            self.store.update(drone_id, groundspeed_mps=msg.groundspeed)

        elif t == "ATTITUDE":
            self.store.update(drone_id, yaw_deg=math.degrees(msg.yaw))
