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
    return [dataclasses.asdict(d) for d in store.snapshot()]


@router.get("/health")
def health(request: Request):
    store = request.app.state.store
    snap = store.snapshot()
    return {
        "ok": True,
        "drone_count": len(snap),
        "connected": sum(1 for d in snap if d.connected),
    }
