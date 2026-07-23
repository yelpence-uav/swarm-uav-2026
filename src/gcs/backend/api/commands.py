# Copyright 2026 Yelpence
"""REST komut endpoint'leri."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from backend.core.command_gate import Command, CommandGate

router = APIRouter(prefix="/api/command", tags=["command"])


def _gate(request: Request) -> CommandGate:
    gate = request.app.state.gate
    if gate is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Bireysel MAVLink komutları simülasyonda kullanılır. "
                "Şu anki mod: ros2."
            ),
        )
    return gate


def _drone_ids(request: Request) -> list[int]:
    return [d["id"] for d in request.app.state.config["drones"]]


def _submit(
    gate: CommandGate,
    drone_id: int,
    action: str,
    params: Optional[dict] = None,
) -> None:
    cmd = Command(drone_id=drone_id, action=action, params=params or {})
    if not gate.submit(cmd):
        raise HTTPException(
            status_code=429,
            detail=f"Drone {drone_id}: kuyruk dolu veya bilinmeyen drone",
        )


ALLOWED_BULK = {"takeoff", "land", "rtl", "loiter", "arm", "disarm"}


@router.post("/all/{action}")
def cmd_all(
    action: str,
    request: Request,
    force: bool = False,
    altitude: Optional[float] = None,
):
    if action not in ALLOWED_BULK:
        raise HTTPException(400, f"Geçersiz action: {action}")
    gate = _gate(request)
    drone_ids = _drone_ids(request)

    submitted = []
    failed = []
    for drone_id in drone_ids:
        params: dict = {}
        if action in ("arm", "disarm"):
            params["force"] = force
        if action == "takeoff" and altitude is not None:
            params["altitude"] = altitude

        cmd = Command(drone_id=drone_id, action=action, params=params)
        if gate.submit(cmd):
            submitted.append(drone_id)
        else:
            failed.append(drone_id)

    return {
        "status": "queued" if not failed else "partial",
        "action": action,
        "submitted": submitted,
        "failed": failed,
    }


@router.post("/{drone_id}/takeoff")
def cmd_takeoff(
    drone_id: int, request: Request, altitude: Optional[float] = None
):
    params = {"altitude": altitude} if altitude is not None else {}
    _submit(_gate(request), drone_id, "takeoff", params)
    return {"status": "queued", "drone_id": drone_id, "action": "takeoff"}


@router.post("/{drone_id}/land")
def cmd_land(drone_id: int, request: Request):
    _submit(_gate(request), drone_id, "land")
    return {"status": "queued", "drone_id": drone_id, "action": "land"}


@router.post("/{drone_id}/rtl")
def cmd_rtl(drone_id: int, request: Request):
    _submit(_gate(request), drone_id, "rtl")
    return {"status": "queued", "drone_id": drone_id, "action": "rtl"}


@router.post("/{drone_id}/loiter")
def cmd_loiter(drone_id: int, request: Request):
    _submit(_gate(request), drone_id, "loiter")
    return {"status": "queued", "drone_id": drone_id, "action": "loiter"}


@router.post("/{drone_id}/arm")
def cmd_arm(drone_id: int, request: Request, force: bool = False):
    _submit(_gate(request), drone_id, "arm", {"force": force})
    return {"status": "queued", "drone_id": drone_id, "action": "arm"}


@router.post("/{drone_id}/disarm")
def cmd_disarm(drone_id: int, request: Request, force: bool = False):
    _submit(_gate(request), drone_id, "disarm", {"force": force})
    return {"status": "queued", "drone_id": drone_id, "action": "disarm"}
