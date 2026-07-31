# Copyright 2026 Yelpence
"""REST telemetry endpoint'leri."""

import dataclasses

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["telemetry"])


@router.get("/telemetry/snapshot")
def get_snapshot(request: Request):
    """Anlık telemetri durumunu döner."""
    store = request.app.state.store
    alerts = request.app.state.alerts
    bridge = getattr(request.app.state, "bridge", None)
    snap = store.snapshot()
    return {
        "drones": [dataclasses.asdict(d) for d in snap],
        "alerts": [dataclasses.asdict(a) for a in alerts.evaluate(snap)],
        "swarm_state": (
            bridge.get_swarm_state() if bridge is not None else None
        ),
        "qr": bridge.get_qr_data() if bridge is not None else None,
        # RTK/RTCM akis durumu — arayuzdeki RTK gostergesi bunu okur.
        "rtk": bridge.get_rtk_status() if bridge is not None else None,
        "connection_mode": request.app.state.connection_mode,
    }


@router.get("/health")
def health(request: Request):
    """Sağlık kontrolü."""
    store = request.app.state.store
    snap = store.snapshot()
    return {
        "ok": True,
        "drone_count": len(snap),
        "connected": sum(1 for d in snap if d.connected),
    }
