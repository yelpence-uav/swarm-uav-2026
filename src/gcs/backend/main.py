"""GCS giriş noktası — Faz 1.

Tek MAVLink kanalından (UDP veya serial) gelen telemetriyi sysid'ye göre 3 drone'a ayrıştırır
ve her saniye terminale basar.
Faz 2'de FastAPI + WebSocket eklenecek; bu dosya o zaman da giriş noktası kalacak.

Çalıştırma (proje kökünden):
    python3 src/gcs/backend/main.py
"""

import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.connections.mavlink_listener import MavlinkListener
from backend.core.state_store import StateStore


GPS_FIX_NAMES = {0: "yok", 1: "yok", 2: "2D", 3: "3D", 4: "DGPS", 5: "RTK-Float", 6: "RTK-Fix"}


def format_drone_line(d) -> str:
    if not d.connected:
        return f"  {d.name:8s} | OFFLINE — son paket gelmiyor"

    armed_str = "ARMED" if d.armed else "yerde"
    gps_str = f"{GPS_FIX_NAMES.get(d.gps_fix_type, '?')}({d.gps_satellites}sat)"
    return (
        f"  {d.name:8s} | {armed_str:5s} {d.mode:12s} | "
        f"alt={d.alt_m:5.1f}m hız={d.groundspeed_mps:4.1f}m/s yaw={d.yaw_deg:6.1f}° | "
        f"bat=%{d.battery_percent:5.1f} ({d.battery_voltage:4.1f}V) | "
        f"gps={gps_str:14s} | "
        f"lat={d.lat:9.5f} lon={d.lon:9.5f}"
    )


def main() -> None:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    store = StateStore(offline_timeout_sec=cfg.get("offline_timeout_sec", 3.0))

    sysid_map: dict[int, int] = {}
    for drone_cfg in cfg["drones"]:
        store.register_drone(drone_cfg["id"], drone_cfg["name"], drone_cfg["sysid"])
        sysid_map[drone_cfg["sysid"]] = drone_cfg["id"]

    listener = MavlinkListener(
        connection_string=cfg["mavlink"]["connection"],
        sysid_to_drone_id=sysid_map,
        store=store,
    )
    listener.start()

    interval = cfg.get("print_interval_sec", 1.0)
    print(f"\n[gcs] {len(cfg['drones'])} drone bekleniyor. Çıkmak için Ctrl+C.\n")

    try:
        while True:
            time.sleep(interval)
            now = time.strftime("%H:%M:%S")
            print(f"\n--- {now} ---")
            for d in store.snapshot():
                print(format_drone_line(d))
    except KeyboardInterrupt:
        print("\n[gcs] Kapatılıyor...")
        listener.stop()


if __name__ == "__main__":
    main()
