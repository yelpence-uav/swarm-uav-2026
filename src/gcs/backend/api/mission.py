# Copyright 2026 Yelpence
"""Görev tetikleme ve Görev 2 sürü kontrolü REST endpoint'leri."""

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["mission"])


class TriggerMissionBody(BaseModel):
    """TriggerMission servis istek gövdesi."""

    mission_id: int = Field(
        ..., ge=0, le=2, description="MISSION_* enum (1 veya 2)"
    )
    command: int = Field(
        ..., ge=0, le=6, description="COMMAND_* enum (1=START..6=LAND)"
    )
    team_id: str = Field(
        "", description="Takım ID, örn. 'team_1'"
    )
    parameters_json: str = Field(
        "", description="Ek parametreler (JSON string)"
    )


def _bridge(request: Request):
    bridge = request.app.state.bridge
    if bridge is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "ROS 2 köprüsü aktif değil. Mod: ros2 gerekir "
                f"(şu an: {request.app.state.connection_mode})."
            ),
        )
    return bridge


@router.post("/api/mission/trigger")
async def mission_trigger(body: TriggerMissionBody, request: Request):
    """Görev tetikleme."""
    bridge = _bridge(request)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        bridge.trigger_mission,
        body.mission_id,
        body.command,
        body.team_id,
        body.parameters_json,
    )
    if not result["success"]:
        return {
            "success": False,
            "message": result["message"],
            "mission_id": body.mission_id,
            "command": body.command,
        }
    return {
        "success": True,
        "message": result["message"],
        "mission_id": body.mission_id,
        "command": body.command,
    }


class QRCoordsBody(BaseModel):
    """QRCoordinates mesaj gövdesi."""

    qr_ids: list[int] = Field(
        ..., description="QR numaraları, örn. [1,2,3,4,5]"
    )
    lat_deg: list[float] = Field(..., description="her QR'ın enlemi")
    lon_deg: list[float] = Field(..., description="her QR'ın boylamı")
    alt_m: list[float] = Field(
        default_factory=list, description="opsiyonel irtifa"
    )


@router.post("/api/mission/qr_coords")
def mission_qr_coords(body: QRCoordsBody, request: Request):
    """QR konum tablosunu sürüye yayınlar."""
    bridge = _bridge(request)
    n = len(body.qr_ids)
    if n == 0:
        raise HTTPException(
            status_code=400, detail="En az bir QR konumu gerekli."
        )
    if not (len(body.lat_deg) == n and len(body.lon_deg) == n):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Paralel diziler eşit uzunlukta olmalı "
                f"(qr_ids={n}, lat={len(body.lat_deg)}, "
                f"lon={len(body.lon_deg)})."
            ),
        )
    try:
        bridge.publish_qr_coords(
            body.qr_ids, body.lat_deg, body.lon_deg, body.alt_m
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"QR konum yayını hatası: {e}"
        )
    return {"published": True, "count": n}


@router.get("/api/swarm/state")
def swarm_state(request: Request):
    """En son SwarmState snapshot'ı."""
    bridge = _bridge(request)
    snapshot = bridge.get_swarm_state()
    return {"swarm_state": snapshot}


