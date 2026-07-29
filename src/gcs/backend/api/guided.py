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

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from swarm_interfaces.msg import GuidedCommand

router = APIRouter(prefix="/api/guided", tags=["guided"])

logger = logging.getLogger("backend.guided")

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
def cmd_takeoff(drone_id: int, request: Request, altitude: Optional[float] = None):
    _check_drone(request, drone_id)
    alt = altitude if altitude is not None else request.app.state.params.get()["default_altitude_m"]
    if alt <= 0.0:
        raise HTTPException(400, "takeoff irtifası > 0 olmalı")
    _bridge(request).publish_guided(
        drone_id, GuidedCommand.ACTION_TAKEOFF, altitude_m=alt
    )
    return _ok(drone_id, "takeoff", altitude_m=alt)


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
    speed: Optional[float] = Field(None, description="seyir hızı (m/s); boşsa parametre varsayılanı")
    heading_deg: Optional[float] = Field(None, description="hedef yön (derece); boşsa serbest")


def _drone_state(request: Request, drone_id: int):
    """StateStore'dan drone'un güncel telemetri durumunu döner (yoksa None)."""
    for d in request.app.state.store.snapshot():
        if d.drone_id == drone_id:
            return d
    return None


def _publish_goto(bridge, drone_id, north, east, irtifa, heading_deg, heading_valid):
    bridge.publish_guided(
        drone_id,
        GuidedCommand.ACTION_GOTO,
        x=float(north),
        y=float(east),
        z=-float(irtifa),  # irtifa (yukarı) → NED aşağı-pozitif
        heading_deg=heading_deg or 0.0,
        heading_valid=heading_valid,
    )


async def _oto_kalkis_sonra_git(
    bridge, store, drone_id, irtifa, north, east, heading_deg, heading_valid
):
    """Yerde/alçaktayken: önce hedef irtifaya oto-kalkış, ulaşınca navigasyon.

    KAZA ÖNLEME: irtifaya çıkmadan yatay hareket YOK. Önce dikey tırmanış
    (takeoff), telemetriden irtifa teyidi, sonra goto. İrtifaya ulaşılamazsa
    (timeout) goto GÖNDERİLMEZ — drone tırmanışta güvende kalır.
    """
    bridge.publish_guided(drone_id, GuidedCommand.ACTION_TAKEOFF, altitude_m=float(irtifa))
    hedef = float(irtifa) * 0.9
    ulasti = False
    for _ in range(60):  # ~30 sn (0.5 sn adım)
        await asyncio.sleep(0.5)
        d = next((x for x in store.snapshot() if x.drone_id == drone_id), None)
        if d is not None and d.alt_m >= hedef:
            ulasti = True
            break
    if not ulasti:
        logger.warning(
            "goto oto-kalkış: drone=%d irtifaya (%.1fm) ulaşamadı, goto iptal",
            drone_id, irtifa,
        )
        return
    _publish_goto(bridge, drone_id, north, east, irtifa, heading_deg, heading_valid)
    logger.info("goto oto-kalkış tamam: drone=%d irtifa=%.1fm → navigasyon", drone_id, irtifa)


@router.post("/{drone_id}/goto")
async def cmd_goto(drone_id: int, body: GotoBody, request: Request):
    _check_drone(request, drone_id)
    bridge = _bridge(request)
    prm = request.app.state.params.get()
    varsayilan_irtifa = prm["default_altitude_m"]

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
        irtifa = body.alt if body.alt is not None else varsayilan_irtifa
    elif body.x is not None and body.y is not None:
        north, east = body.x, body.y
        irtifa = body.z if body.z is not None else varsayilan_irtifa
    else:
        raise HTTPException(
            status_code=400,
            detail="goto: ya (x,y[,z]) NED ya da (lat,lon[,alt]) verilmeli",
        )

    if irtifa <= 0.0:
        raise HTTPException(400, "goto irtifası > 0 olmalı")

    heading_valid = body.heading_deg is not None
    ned_ozet = {"kuzey": round(north, 2), "dogu": round(east, 2), "z": round(-irtifa, 2)}

    # --- GÜVENLİK KİLİDİ: min-nav-irtifasının altındaysa oto-kalkış-sonra-git ---
    d = _drone_state(request, drone_id)
    guncel_alt = d.alt_m if d is not None else 0.0
    min_nav = prm["min_nav_altitude_m"]

    if guncel_alt >= min_nav:
        # Zaten yeterli irtifada → doğrudan navigasyon.
        _publish_goto(bridge, drone_id, north, east, irtifa, body.heading_deg, heading_valid)
        return _ok(drone_id, "goto", mod="direkt", ned=ned_ozet, irtifa_m=irtifa)

    # Alçak/yerde → önce irtifaya çıkmalı. Oto-kalkış için ARM şart.
    if d is None or not d.armed:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Drone {guncel_alt:.1f}m'de (min-nav {min_nav:.1f}m altında) ve disarm. "
                "Önce ARM et; sonra 'noktaya git' oto-kalkış yapıp gider."
            ),
        )

    # Armed + alçak → arka planda: oto-kalkış → irtifa → git.
    asyncio.create_task(
        _oto_kalkis_sonra_git(
            bridge, request.app.state.store, drone_id, irtifa, north, east,
            body.heading_deg, heading_valid,
        )
    )
    return _ok(
        drone_id, "goto", mod="oto-kalkis-sonra-git",
        ned=ned_ozet, irtifa_m=irtifa,
        not_="Önce hedef irtifaya çıkılıyor, sonra navigasyon.",
    )
