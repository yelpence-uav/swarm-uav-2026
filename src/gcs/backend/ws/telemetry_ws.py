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
    bridge=None,
    connection_mode: str = "ros2",
) -> None:
    """drones + alerts + swarm_state üçlüsünü periyodik push.

    bridge None ise (mavlink-sim modu) swarm_state alanı da None gider —
    frontend bunu graceful handle eder. connection_mode payload'a girer ki
    frontend yarışma-dışı butonları (MAVLink bireysel komutlar) sadece
    mavlink-sim modunda göstersin.
    """
    await ws.accept()
    interval = 1.0 / hz
    client = f"{ws.client.host}:{ws.client.port}" if ws.client else "?"
    logger.info("ws bağlandı: %s", client)

    try:
        while True:
            snap = store.snapshot()
            active_alerts = alerts.evaluate(snap)
            swarm_state = bridge.get_swarm_state() if bridge is not None else None
            payload = {
                "drones": [dataclasses.asdict(d) for d in snap],
                "alerts": [dataclasses.asdict(a) for a in active_alerts],
                "swarm_state": swarm_state,
                "connection_mode": connection_mode,
            }
            await ws.send_text(json.dumps(payload))
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        logger.info("ws koptu: %s", client)
    except Exception:
        logger.exception("ws hata: %s", client)
