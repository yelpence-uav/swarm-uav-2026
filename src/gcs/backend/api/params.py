"""Uçuş parametreleri API — Ayarlar sekmesi bunları okur/yazar.

  GET  /api/params            → mevcut parametreler
  PUT  /api/params  {gövde}   → verilen alanları günceller, güncel hali döner
"""

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/params", tags=["params"])


class ParamsBody(BaseModel):
    """Kısmi güncelleme — sadece verilen alanlar değişir."""

    default_altitude_m: Optional[float] = Field(None, description="takeoff/goto varsayılan irtifa (m)")
    default_speed_ms: Optional[float] = Field(None, description="yatay seyir hızı (m/s)")
    min_nav_altitude_m: Optional[float] = Field(None, description="altında navigasyon yok (m)")
    # GÖREV 2 sürü davranışı — BAŞLAT paketiyle uçaklara gider. 0 = belirtilmedi.
    suru_morf_hiz_mps: Optional[float] = Field(None, description="formasyon değişimi slot hızı (m/s)")
    suru_hareket_hiz_mps: Optional[float] = Field(None, description="hareket modu öteleme hızı (m/s)")
    suru_yaw_hiz_deg_s: Optional[float] = Field(None, description="sürü dönüş hızı tavanı (deg/s)")
    suru_egim_tavan_deg: Optional[float] = Field(None, description="manevra eğim genliği (deg)")


@router.get("")
def get_params(request: Request) -> dict:
    return request.app.state.params.get()


@router.put("")
def update_params(body: ParamsBody, request: Request) -> dict:
    return request.app.state.params.update(**body.model_dump(exclude_none=True))
