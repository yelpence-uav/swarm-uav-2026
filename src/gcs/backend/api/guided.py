"""Guided (tekil drone) uçuş komutları — YKİ'den arm/takeoff/goto/rtl/land.

Otonom görev (TriggerMission) DIŞINDA operatörün tek drone'u elle uçurması için.
Komut ESP mesh üzerinden gider: backend → /swarm/internal/guided/command →
base esp32_bridge (TIP_KOMUT[guided]/TIP_GOTO) → drone → px4_bridge → FCU.

Sadece connection_mode='ros2' iken aktif; mavlink-sim modunda 503.

Yollar:
  POST /api/guided/{drone_id}/arm
  POST /api/guided/{drone_id}/disarm
  POST /api/guided/{drone_id}/takeoff?altitude=5
  POST /api/guided/{drone_id}/rtl
  POST /api/guided/{drone_id}/land
  POST /api/guided/{drone_id}/goto   (gövde: NED x/y/z VEYA GPS lat/lon + alt)
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from swarm_interfaces.msg import GuidedCommand

router = APIRouter(prefix="/api/guided", tags=["guided"])

_VARSAYILAN_IRTIFA_M = 5.0


def _bridge(request: Request):
    bridge = request.app.state.bridge
    if bridge is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Guided komutlar sadece ros2 modunda kullanılır. "
                f"Şu anki mod: {request.app.state.connection_mode}."
            ),
        )
    return bridge


def _check_drone(request: Request, drone_id: int) -> None:
    ids = [d["id"] for d in request.app.state.config["drones"]]
    if drone_id not in ids:
        raise HTTPException(status_code=404, detail=f"Bilinmeyen drone: {drone_id}")


def _ok(drone_id: int, action: str, **extra) -> dict:
    return {"status": "sent", "drone_id": drone_id, "action": action, **extra}


@router.post("/{drone_id}/arm")
def cmd_arm(drone_id: int, request: Request):
    _check_drone(request, drone_id)
    _bridge(request).publish_guided(drone_id, GuidedCommand.ACTION_ARM)
    return _ok(drone_id, "arm")


@router.post("/{drone_id}/disarm")
def cmd_disarm(drone_id: int, request: Request):
    _check_drone(request, drone_id)
    _bridge(request).publish_guided(drone_id, GuidedCommand.ACTION_DISARM)
    return _ok(drone_id, "disarm")


@router.post("/{drone_id}/takeoff")
def cmd_takeoff(drone_id: int, request: Request, altitude: float = _VARSAYILAN_IRTIFA_M):
    _check_drone(request, drone_id)
    if altitude <= 0.0:
        raise HTTPException(400, "takeoff irtifası > 0 olmalı")
    _bridge(request).publish_guided(
        drone_id, GuidedCommand.ACTION_TAKEOFF, altitude_m=altitude
    )
    return _ok(drone_id, "takeoff", altitude_m=altitude)


@router.post("/{drone_id}/rtl")
def cmd_rtl(drone_id: int, request: Request):
    _check_drone(request, drone_id)
    _bridge(request).publish_guided(drone_id, GuidedCommand.ACTION_RTL)
    return _ok(drone_id, "rtl")


@router.post("/{drone_id}/land")
def cmd_land(drone_id: int, request: Request):
    _check_drone(request, drone_id)
    _bridge(request).publish_guided(drone_id, GuidedCommand.ACTION_LAND)
    return _ok(drone_id, "land")


class GotoBody(BaseModel):
    """Nokta-git hedefi — iki giriş modundan biri.

    Manuel NED: x=Kuzey(m), y=Doğu(m), z=İrtifa(m, yukarı).
    Harita/GPS: lat, lon (derece), alt=İrtifa(m, yukarı).
    İkisinde de irtifa 'yukarı-pozitif'; içeride NED aşağı-pozitife çevrilir.
    """

    x: Optional[float] = Field(None, description="NED kuzey (m)")
    y: Optional[float] = Field(None, description="NED doğu (m)")
    z: Optional[float] = Field(None, description="irtifa (m, yukarı)")
    lat: Optional[float] = Field(None, description="hedef enlem (derece)")
    lon: Optional[float] = Field(None, description="hedef boylam (derece)")
    alt: Optional[float] = Field(None, description="irtifa (m, yukarı)")
    heading_deg: Optional[float] = Field(None, description="hedef yön (derece); boşsa serbest")


@router.post("/{drone_id}/goto")
def cmd_goto(drone_id: int, body: GotoBody, request: Request):
    _check_drone(request, drone_id)
    bridge = _bridge(request)

    if body.lat is not None and body.lon is not None:
        ned = bridge.latlon_to_ned(body.lat, body.lon)
        if ned is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Origin henüz yok — harita hedefi NED'e çevrilemiyor. "
                    "Manuel x/y/z kullan veya origin gelene kadar bekle."
                ),
            )
        north, east = ned
        irtifa = body.alt if body.alt is not None else _VARSAYILAN_IRTIFA_M
    elif body.x is not None and body.y is not None:
        north, east = body.x, body.y
        irtifa = body.z if body.z is not None else _VARSAYILAN_IRTIFA_M
    else:
        raise HTTPException(
            status_code=400,
            detail="goto: ya (x,y[,z]) NED ya da (lat,lon[,alt]) verilmeli",
        )

    z_ned = -float(irtifa)  # irtifa (yukarı) → NED aşağı-pozitif
    heading_valid = body.heading_deg is not None
    bridge.publish_guided(
        drone_id,
        GuidedCommand.ACTION_GOTO,
        x=north,
        y=east,
        z=z_ned,
        heading_deg=body.heading_deg or 0.0,
        heading_valid=heading_valid,
    )
    return _ok(
        drone_id, "goto",
        ned={"kuzey": round(north, 2), "dogu": round(east, 2), "z": round(z_ned, 2)},
        irtifa_m=irtifa,
    )
