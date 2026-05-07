"""WebSocket endpoint — 10 Hz drone snapshot + alert push.

Frontend bağlanır, biz periyodik olarak {drones, alerts} JSON'unu basarız.
Bağlantı koparsa sessizce çıkar; reconnect'i frontend yapar.
"""

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
) -> None:
    await ws.accept()
    interval = 1.0 / hz
    client = f"{ws.client.host}:{ws.client.port}" if ws.client else "?"
    logger.info("ws bağlandı: %s", client)

    try:
        while True:
            snap = store.snapshot()
            active_alerts = alerts.evaluate(snap)
            payload = {
                "drones": [dataclasses.asdict(d) for d in snap],
                "alerts": [dataclasses.asdict(a) for a in active_alerts],
            }
            await ws.send_text(json.dumps(payload))
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        logger.info("ws koptu: %s", client)
    except Exception:
        logger.exception("ws hata: %s", client)
