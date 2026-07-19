"""WebSocket endpoint - 10 Hz telemetry push."""

import asyncio
import dataclasses
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from backend.core.alert_manager import AlertManager
from backend.core.state_store import StateStore

logger = logging.getLogger(__name__)


async def telemetry_ws(
    ws: WebSocket,
    store: StateStore,
    alerts: AlertManager,
    hz: float = 10.0,
    bridge=None,
    connection_mode: str = "ros2",
) -> None:
    """Telemetri ve alarm verilerini periyodik gönderir."""
    await ws.accept()
    interval = 1.0 / hz
    client = f"{ws.client.host}:{ws.client.port}" if ws.client else "?"
    logger.info("ws bağlandı: %s", client)

    try:
        while True:
            snap = store.snapshot()
            active_alerts = alerts.evaluate(snap)
            swarm_state = (
                bridge.get_swarm_state() if bridge is not None else None
            )
            qr = bridge.get_qr_data() if bridge is not None else None
            payload = {
                "drones": [dataclasses.asdict(d) for d in snap],
                "alerts": [dataclasses.asdict(a) for a in active_alerts],
                "swarm_state": swarm_state,
                "qr": qr,
                "connection_mode": connection_mode,
            }
            await ws.send_text(json.dumps(payload))
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        logger.info("ws koptu: %s", client)
    except Exception:
        logger.exception("ws hata: %s", client)
