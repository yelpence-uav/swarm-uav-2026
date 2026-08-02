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


@router.get("")
def get_params(request: Request) -> dict:
    return request.app.state.params.get()


@router.put("")
def update_params(body: ParamsBody, request: Request) -> dict:
    return request.app.state.params.update(**body.model_dump(exclude_none=True))
