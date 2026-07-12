"""Görev tetikleme + Görev 2 sürü kontrolü REST endpoint'leri (Faz 5).

Yollar:
  POST /api/mission/trigger        TriggerMission.srv çağrısı (görev başlat/durdur)
  POST /api/swarm/control          SwarmControlCommand.msg yayını (Görev 2 joystick)
  GET  /api/swarm/state            En son SwarmState snapshot'ı

Sadece connection_mode='ros2' iken aktif. mavlink-sim modunda 503 döner.
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


router = APIRouter(tags=["mission"])


# --- /api/mission/trigger -----------------------------------------------------


class TriggerMissionBody(BaseModel):
    """TriggerMission.srv request gövdesi.

    Kontrat referansı (swarm_interfaces/srv/TriggerMission.srv):
      mission_id 1 = MISSION_DYNAMIC_SWARM (Görev 1)
      mission_id 2 = MISSION_SEMI_AUTONOMOUS (Görev 2)
      command 1=START, 2=ABORT, 3=PAUSE, 4=RESUME, 5=RTL, 6=LAND
    """

    mission_id: int = Field(..., ge=0, le=2, description="MISSION_* enum (1 veya 2)")
    command: int = Field(..., ge=0, le=6, description="COMMAND_* enum (1=START..6=LAND)")
    team_id: str = Field("", description="Hakem söyleyeceği takım ID, örn. 'team_1'")
    parameters_json: str = Field("", description="Opsiyonel ek parametreler (JSON string)")


def _bridge(request: Request):
    bridge = request.app.state.bridge
    if bridge is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "ROS 2 köprüsü aktif değil. connection_mode='ros2' gerekir "
                f"(şu an: {request.app.state.connection_mode})."
            ),
        )
    return bridge


@router.post("/api/mission/trigger")
async def mission_trigger(body: TriggerMissionBody, request: Request):
    """Görev tetikleme — şartname Görev 1'in tek müdahale noktası."""
    bridge = _bridge(request)
    # ROS 2 service çağrısı blocking — event loop'u bloklamamak için executor.
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
        # Service çağrısı yapıldı ama success=false geldi (veya timeout/missing).
        # 502 Bad Gateway yerine 200 + body kullanıyoruz, frontend'in
        # message'ı kullanıcıya gösterebilmesi için.
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


# --- /api/mission/qr_coords ---------------------------------------------------


class QRCoordsBody(BaseModel):
    """QRCoordinates.msg gövdesi — operatörün girdiği QR konum tablosu.

    Paralel diziler (hepsi aynı uzunlukta). Operatör YKİ formundan girer;
    GCS bunu /swarm/internal/mission/qr_coords'a (latched) yayınlar → proxy →
    mission_fsm tabloyu saklar, "next_qr → lat/lon" çözümü için kullanır.

    alt_m opsiyonel: form yalnızca enlem/boylam topluyor (irtifa QR görev
    komutundan gelir). Boş bırakılırsa backend sıfırla doldurur.
    """

    qr_ids: list[int] = Field(..., description="QR numaraları, örn. [1,2,3,4,5]")
    lat_deg: list[float] = Field(..., description="her QR'ın enlemi (WGS84)")
    lon_deg: list[float] = Field(..., description="her QR'ın boylamı (WGS84)")
    alt_m: list[float] = Field(default_factory=list, description="opsiyonel irtifa")


@router.post("/api/mission/qr_coords")
def mission_qr_coords(body: QRCoordsBody, request: Request):
    """QR konum tablosunu sürüye yayınla (latched).

    Şartname V2: QR konumları önceden paylaşılır; operatör YKİ'den girer,
    sürüye iletilir. Bu, GCS'in ağa yazdığı ikinci kanal (joystick dışında).
    """
    bridge = _bridge(request)
    n = len(body.qr_ids)
    if n == 0:
        raise HTTPException(status_code=400, detail="En az bir QR konumu gerekli.")
    if not (len(body.lat_deg) == n and len(body.lon_deg) == n):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Paralel diziler eşit uzunlukta olmalı "
                f"(qr_ids={n}, lat={len(body.lat_deg)}, lon={len(body.lon_deg)})."
            ),
        )
    try:
        bridge.publish_qr_coords(body.qr_ids, body.lat_deg, body.lon_deg, body.alt_m)
    except RuntimeError as e:
        # QRCoordinates mesajı henüz derli değil → 503 (yapılandırma sorunu).
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"QR konum yayını hatası: {e}")
    return {"published": True, "count": n}


# --- /api/swarm/state ---------------------------------------------------------


@router.get("/api/swarm/state")
def swarm_state(request: Request):
    """En son SwarmState snapshot'ı (henüz mesaj gelmediyse null)."""
    bridge = _bridge(request)
    snapshot = bridge.get_swarm_state()
    return {"swarm_state": snapshot}


# --- /api/swarm/control -------------------------------------------------------


class SwarmControlBody(BaseModel):
    """SwarmControlCommand.msg gövdesi (Görev 2 joystick frame'i).

    Frontend Browser Gamepad API'den 20-50 Hz okur, bu endpoint'e POST'lar.
    Yüksek frekans için ileride WebSocket yoluna geçilebilir; şimdilik REST.

    Deadman kuralı: command_valid=true VE deadman_pressed=true olmadan
    drone'lar HOLD'a geçer (kontrat).
    """

    sequence_num: int = 0
    command_valid: bool = False
    deadman_pressed: bool = False
    deadman_timeout_s: float = 0.5
    mode: int = 0                      # MODE_UNKNOWN=0/SWARM_MOVEMENT=1/MANEUVER=2
    pitch_cmd: float = 0.0             # [-1,+1]
    roll_cmd: float = 0.0
    yaw_cmd: float = 0.0
    throttle_cmd: float = 0.0
    takeoff: bool = False
    land: bool = False
    rtl: bool = False
    emergency_stop: bool = False
    formation_change_requested: bool = False
    requested_formation: int = 0       # FORMATION_UNKNOWN=0/OKBASI=1/V=2/CIZGI=3
    requested_spacing_m: float = 0.0
    duration_s: float = 0.0
    max_speed_mps: float = 0.0
    max_yaw_rate_deg_s: float = 0.0
    max_tilt_deg: float = 0.0
    source_module: str = "gcs"


@router.post("/api/swarm/control")
def swarm_control(body: SwarmControlBody, request: Request):
    """Görev 2 sürü komutu yayını."""
    bridge = _bridge(request)
    try:
        bridge.publish_swarm_control(body.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Publish hatası: {e}")
    return {"published": True, "sequence_num": body.sequence_num}
