# Copyright 2026 Yelpence
"""Uçuş ve sistem olay defteri — REST uçları.

Panel bunu ARTIMLI okur: elindeki en büyük `sira` numarasını `sonra=` ile
geri gönderir, yalnız yeni kayıtlar döner. Böylece 2 saniyede bir sorgu,
defter binlerce satıra ulaşsa bile birkaç yüz bayt taşır.
"""

import dataclasses

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api", tags=["loglar"])


@router.get("/loglar")
def get_loglar(
    request: Request,
    drone: int | None = Query(None, description="drone_id; yoksa hepsi"),
    min_siddet: str | None = Query(
        None, description="info | warning | critical | emergency"
    ),
    sonra: int = Query(0, description="bu sira numarasindan BUYUK olanlar"),
    limit: int = Query(200, ge=1, le=1000),
):
    """Süzülmüş olay kayıtlarını döner (eskiden yeniye)."""
    gunluk = getattr(request.app.state, "gunluk", None)
    if gunluk is None:
        # Defter kurulmamissa BOS donuyoruz, hata degil: panel acik kalsin,
        # yalnizca kayit gostermesin. 500 donmek arayuzu kirardi.
        return {"kayitlar": [], "son_sira": 0, "aktif": False}

    kayitlar = gunluk.oku(
        drone_id=drone, min_siddet=min_siddet, sonra=sonra, limit=limit
    )
    return {
        "kayitlar": [dataclasses.asdict(k) for k in kayitlar],
        "son_sira": gunluk.son_sira(),
        "aktif": True,
    }
