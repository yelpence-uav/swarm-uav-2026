"""GCS giriş noktası.

REST API + WebSocket sunucusunu uvicorn ile kaldırır.

Çalıştırma (container içinde):
    cd /home/yelpence/ros2_ws/src/gcs
    source /opt/ros/jazzy/setup.bash
    source /home/yelpence/ros2_ws/install/setup.bash
    source /home/yelpence/venv/bin/activate
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""

from backend.ws.telemetry_ws import telemetry_ws
from backend.core.state_store import StateStore
from backend.core.command_gate import CommandGate
from backend.core.alert_manager import (
    AlertManager,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)
from backend.connections.mavlink_listener import MavlinkListener
from backend.connections.heartbeat_sender import HeartbeatSender
from backend.connections.command_worker import CommandWorker
from backend.connections.command_sender import CommandSender
from backend.api.telemetry import router as telemetry_router
from backend.api.mission import router as mission_router
from backend.api.commands import router as commands_router
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


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("gcs")


GPS_FIX_NAMES = {
    0: "yok",
    1: "yok",
    2: "2D",
    3: "3D",
    4: "DGPS",
    5: "RTK-Float",
    6: "RTK-Fix",
}


# MAVLink komut isimleri
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
        return f"  {d.name:8s} | OFFLINE - son paket gelmiyor"

    armed_str = "ARMED" if d.armed else "yerde"
    gps_str = (
        f"{GPS_FIX_NAMES.get(d.gps_fix_type, '?')}({d.gps_satellites}sat)"
    )
    return (
        f"  {d.name:8s} | {armed_str:5s} {d.mode:12s} | "
        f"alt={d.alt_m:5.1f}m hız={d.groundspeed_mps:4.1f}m/s "
        f"yaw={d.yaw_deg:6.1f}° | "
        f"bat=%{d.battery_percent:5.1f} ({d.battery_voltage:4.1f}V) | "
        f"gps={gps_str:14s} | "
        f"lat={d.lat:9.5f} lon={d.lon:9.5f}"
    )


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


async def terminal_printer(store: StateStore, interval: float) -> None:
    """Her N saniyede terminale snapshot basır."""
    while True:
        await asyncio.sleep(interval)
        now = time.strftime("%H:%M:%S")
        print(f"\n--- {now} ---")
        for d in store.snapshot():
            print(format_drone_line(d))


def make_ack_callback(alerts: AlertManager):
    """COMMAND_ACK gelince AlertManager'a info/warning event olarak yansıt."""

    def cb(
        drone_id: int, command_id: int, result_code: int, result_text: str
    ) -> None:
        cmd_name = COMMAND_NAMES.get(command_id, f"cmd={command_id}")
        if result_code == 0:  # ACCEPTED
            alerts.push_event(
                drone_id,
                SEVERITY_INFO,
                f"ack_{command_id}",
                f"{cmd_name} kabul edildi",
            )
        else:
            alerts.push_event(
                drone_id,
                SEVERITY_WARNING,
                f"ack_{command_id}",
                f"{cmd_name} reddedildi ({result_text})",
            )

    return cb


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    mode = cfg.get("connection_mode", "ros2")
    store = StateStore(offline_timeout_sec=cfg.get("offline_timeout_sec", 3.0))
    alerts = AlertManager()

    sysid_map: dict[int, int] = {}  # sysid -> drone_id
    drone_id_to_sysid: dict[int, int] = {}  # drone_id -> sysid
    drone_ids: list[int] = []
    for drone_cfg in cfg["drones"]:
        store.register_drone(
            drone_cfg["id"], drone_cfg["name"], drone_cfg["sysid"]
        )
        sysid_map[drone_cfg["sysid"]] = drone_cfg["id"]
        drone_id_to_sysid[drone_cfg["id"]] = drone_cfg["sysid"]
        drone_ids.append(drone_cfg["id"])

    # app.state ortak alanlar (her iki mod da yazar)
    app.state.store = store
    app.state.alerts = alerts
    app.state.config = cfg
    app.state.connection_mode = mode

    # Bileşenleri None ile başlat
    bridge = None
    listener = None
    sender = None
    heartbeat = None
    gate = None
    worker = None

    if mode == "ros2":
        # ROS 2 modülü yüklenir
        from backend.connections.ros_bridge import RosBridge

        bridge = RosBridge(
            drone_ids=drone_ids,
            store=store,
            alerts=alerts,
        )
        bridge.start()
        app.state.bridge = bridge
        logger.info(
            "GCS hazır [mode=ros2] - %d drone, ROS 2 köprü aktif (ids: %s)",
            len(drone_ids),
            drone_ids,
        )
    elif mode == "mavlink-sim":
        listener = MavlinkListener(
            connection_string=cfg["mavlink"]["connection"],
            sysid_to_drone_id=sysid_map,
            store=store,
        )
        listener.set_ack_callback(make_ack_callback(alerts))
        listener.start()

        sender = CommandSender(
            link=listener.link, send_lock=listener.send_lock
        )
        heartbeat = HeartbeatSender(
            link=listener.link, send_lock=listener.send_lock
        )
        heartbeat.start()

        gate = CommandGate()
        for drone_cfg in cfg["drones"]:
            gate.register_drone(drone_cfg["id"])
        worker = CommandWorker(
            gate=gate, sender=sender, drone_id_to_sysid=drone_id_to_sysid
        )
        worker.start()

        app.state.listener = listener
        app.state.sender = sender
        app.state.heartbeat = heartbeat
        app.state.gate = gate
        app.state.worker = worker
        logger.info(
            "GCS hazır [mode=mavlink-sim] - %d drone (sysid: %s)",
            len(cfg["drones"]),
            sorted(sysid_map.keys()),
        )
    else:
        raise ValueError(
            f"Bilinmeyen connection_mode: {mode!r} (ros2 veya mavlink-sim)"
        )

    print_interval = cfg.get("print_interval_sec", 0)
    printer_task = None
    if print_interval and print_interval > 0:
        printer_task = asyncio.create_task(
            terminal_printer(store, print_interval)
        )

    try:
        yield
    finally:
        logger.info("kapanıyor [mode=%s]...", mode)
        if printer_task:
            printer_task.cancel()
        if app.state.worker:
            app.state.worker.stop()
        if app.state.heartbeat:
            app.state.heartbeat.stop()
        if app.state.listener:
            app.state.listener.stop()
        if app.state.bridge:
            app.state.bridge.stop()


def create_app() -> FastAPI:
    cfg = load_config()
    app = FastAPI(title="Yelpence GCS", version="0.5.0-dev", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.get("server", {}).get("cors_origins", ["*"]),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(telemetry_router)
    app.include_router(commands_router)
    app.include_router(mission_router)

    @app.websocket("/ws/telemetry")
    async def ws_telemetry(websocket: WebSocket):
        state = websocket.app.state
        hz = float(state.config.get("server", {}).get("ws_hz", 10.0))
        await telemetry_ws(
            websocket,
            state.store,
            state.alerts,
            hz=hz,
            bridge=state.bridge,
            connection_mode=state.connection_mode,
        )

    dist_dir = Path(__file__).parent.parent / "frontend" / "dist"
    if dist_dir.exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="static")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    cfg = load_config().get("server", {})
    uvicorn.run(
        "main:app",
        # Operatör ve gateway erişimi için tüm arayüzlere bağlanır.
        host=cfg.get("host", "0.0.0.0"),  # nosec B104
        port=cfg.get("port", 8000),
        reload=False,
    )
