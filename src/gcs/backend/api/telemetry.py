"""REST endpoint — anlık snapshot (debug + frontend health check).

WebSocket'i tamamlar. Frontend ilk yüklemede bunu çağırarak başlangıç state'ini alır,
sonra WS'ye geçer.
"""

import dataclasses

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["telemetry"])


@router.get("/telemetry/snapshot")
def get_snapshot(request: Request):
    store = request.app.state.store
    alerts = request.app.state.alerts
    snap = store.snapshot()
    return {
        "drones": [dataclasses.asdict(d) for d in snap],
        "alerts": [dataclasses.asdict(a) for a in alerts.evaluate(snap)],
        "connection_mode": request.app.state.connection_mode,
    }


@router.get("/health")
def health(request: Request):
    store = request.app.state.store
    snap = store.snapshot()
    return {
        "ok": True,
        "drone_count": len(snap),
        "connected": sum(1 for d in snap if d.connected),
    }
