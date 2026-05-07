"""GCS giriş noktası — Faz 4.

FastAPI uygulaması:
  - HTTP GET  /api/telemetry/snapshot       (anlık state + alerts)
  - HTTP GET  /api/health                   (sağlık + drone sayısı)
  - HTTP POST /api/command/{drone_id}/...   (takeoff/land/rtl/arm/disarm)
  - HTTP POST /api/command/all/...          (tüm drone'lara aynı komut)
  - WS        /ws/telemetry                 (10 Hz canlı snapshot push)

MavlinkListener arka plan thread'inde çalışır; CommandWorker (drone başına
ayrı thread) komut kuyruğunu MAVLink'e yazar. Listener ile sender aynı UDP
soketini paylaşır (send_lock korumalı).

Çalıştırma (proje kökünden):
    cd src/gcs/backend
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.api.commands import router as commands_router
from backend.api.telemetry import router as telemetry_router
from backend.connections.command_sender import CommandSender
from backend.connections.command_worker import CommandWorker
from backend.connections.heartbeat_sender import HeartbeatSender
from backend.connections.mavlink_listener import MavlinkListener
from backend.core.alert_manager import AlertManager, SEVERITY_INFO, SEVERITY_WARNING
from backend.core.command_gate import CommandGate
from backend.core.state_store import StateStore
from backend.ws.telemetry_ws import telemetry_ws

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("gcs")


GPS_FIX_NAMES = {0: "yok", 1: "yok", 2: "2D", 3: "3D", 4: "DGPS", 5: "RTK-Float", 6: "RTK-Fix"}


# MAVLink command id → kullanıcıya gösterilecek isim
COMMAND_NAMES = {
    11: "set_mode",
    176: "set_mode",
    400: "arm/disarm",
    22: "takeoff",
    21: "land",
    20: "rtl",
}


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


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


async def terminal_printer(store: StateStore, interval: float) -> None:
    """Faz 1 davranışını koru — her N saniyede terminale snapshot bas."""
    while True:
        await asyncio.sleep(interval)
        now = time.strftime("%H:%M:%S")
        print(f"\n--- {now} ---")
        for d in store.snapshot():
            print(format_drone_line(d))


def make_ack_callback(alerts: AlertManager):
    """COMMAND_ACK gelince AlertManager'a info/warning event olarak yansıt."""
    def cb(drone_id: int, command_id: int, result_code: int, result_text: str) -> None:
        cmd_name = COMMAND_NAMES.get(command_id, f"cmd={command_id}")
        if result_code == 0:  # ACCEPTED
            alerts.push_event(
                drone_id, SEVERITY_INFO, f"ack_{command_id}",
                f"{cmd_name} kabul edildi",
            )
        else:
            alerts.push_event(
                drone_id, SEVERITY_WARNING, f"ack_{command_id}",
                f"{cmd_name} reddedildi ({result_text})",
            )
    return cb


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    store = StateStore(offline_timeout_sec=cfg.get("offline_timeout_sec", 3.0))
    alerts = AlertManager()

    sysid_map: dict[int, int] = {}              # sysid -> drone_id (listener)
    drone_id_to_sysid: dict[int, int] = {}      # drone_id -> sysid (sender)
    for drone_cfg in cfg["drones"]:
        store.register_drone(drone_cfg["id"], drone_cfg["name"], drone_cfg["sysid"])
        sysid_map[drone_cfg["sysid"]] = drone_cfg["id"]
        drone_id_to_sysid[drone_cfg["id"]] = drone_cfg["sysid"]

    listener = MavlinkListener(
        connection_string=cfg["mavlink"]["connection"],
        sysid_to_drone_id=sysid_map,
        store=store,
    )
    listener.set_ack_callback(make_ack_callback(alerts))
    listener.start()

    # Send tarafı — listener'ın connection'ını paylaşır.
    sender = CommandSender(link=listener.link, send_lock=listener.send_lock)

    # GCS heartbeat — yoksa PX4 datalink loss failsafe drone'u indirir.
    heartbeat = HeartbeatSender(link=listener.link, send_lock=listener.send_lock)
    heartbeat.start()

    gate = CommandGate()
    for drone_cfg in cfg["drones"]:
        gate.register_drone(drone_cfg["id"])

    worker = CommandWorker(gate=gate, sender=sender, drone_id_to_sysid=drone_id_to_sysid)
    worker.start()

    app.state.store = store
    app.state.listener = listener
    app.state.sender = sender
    app.state.heartbeat = heartbeat
    app.state.gate = gate
    app.state.worker = worker
    app.state.alerts = alerts
    app.state.config = cfg

    print_interval = cfg.get("print_interval_sec", 0)
    printer_task = None
    if print_interval and print_interval > 0:
        printer_task = asyncio.create_task(terminal_printer(store, print_interval))

    logger.info(
        "GCS hazır — %d drone bekleniyor (sysid'ler: %s)",
        len(cfg["drones"]), sorted(sysid_map.keys()),
    )

    try:
        yield
    finally:
        logger.info("kapanıyor...")
        if printer_task:
            printer_task.cancel()
        worker.stop()
        heartbeat.stop()
        listener.stop()


def create_app() -> FastAPI:
    cfg = load_config()
    app = FastAPI(title="Yelpence GCS", version="0.4.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.get("server", {}).get("cors_origins", ["*"]),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(telemetry_router)
    app.include_router(commands_router)

    @app.websocket("/ws/telemetry")
    async def ws_telemetry(websocket: WebSocket):
        store = websocket.app.state.store
        alerts = websocket.app.state.alerts
        hz = float(websocket.app.state.config.get("server", {}).get("ws_hz", 10.0))
        await telemetry_ws(websocket, store, alerts, hz=hz)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    cfg = load_config().get("server", {})
    uvicorn.run(
        "main:app",
        host=cfg.get("host", "0.0.0.0"),
        port=cfg.get("port", 8000),
        reload=False,
    )
