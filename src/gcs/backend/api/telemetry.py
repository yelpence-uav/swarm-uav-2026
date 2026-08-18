# Copyright 2026 Yelpence
"""REST telemetry endpoint'leri."""

import dataclasses

from backend.core.state_store import ikili_mesafeler

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["telemetry"])


@router.get("/telemetry/snapshot")
def get_snapshot(request: Request):
    """Anlık telemetri durumunu döner."""
    store = request.app.state.store
    alerts = request.app.state.alerts
    bridge = getattr(request.app.state, "bridge", None)
    snap = store.snapshot()
    return {
        "drones": [dataclasses.asdict(d) for d in snap],
        "alerts": [dataclasses.asdict(a) for a in alerts.evaluate(snap)],
        "swarm_state": (
            bridge.get_swarm_state() if bridge is not None else None
        ),
        "qr": bridge.get_qr_data() if bridge is not None else None,
        # RTK/RTCM akis durumu — arayuzdeki RTK gostergesi bunu okur.
        "rtk": bridge.get_rtk_status() if bridge is not None else None,
        # Drone'lar arasi mesafe — RTK dogrulugunu seritmetreyle sinamak icin.
        "mesafeler": ikili_mesafeler(snap),
        "connection_mode": request.app.state.connection_mode,
    }


@router.get("/health")
def health(request: Request):
    """Sağlık kontrolü."""
    store = request.app.state.store
    snap = store.snapshot()

    # origin: harita tıklamasının çalışıp çalışmayacağı.
    #
    # NEDEN EKLENDİ (18 Ağustos 2026): `ros_bridge.has_origin()` yazılmıştı ama
    # HİÇBİR YERDEN çağrılmıyordu ve origin durumunu gösteren uç nokta yoktu.
    # Sonuç: operatör "harita hedefi çalışacak mı"yı ancak haritaya tıklayıp
    # 409 "Origin henüz yok" yiyerek öğreniyordu. Aynı gün gerçek bir arıza
    # bunun arkasına saklandı: `yki_baslat.sh`'in iki origin yayıncısı da
    # /internal'a yazıyordu ve /swarm/public/origin BOŞTU — telemetri normal
    # aktığı için hiçbir şey belirti vermedi.
    #
    # bridge yoksa (mavlink-sim modu) alan None döner; "false" demek yanlış
    # olurdu çünkü o modda origin kavramı zaten yok.
    bridge = getattr(request.app.state, "bridge", None)
    origin_var = bridge.has_origin() if bridge is not None else None

    return {
        "ok": True,
        "drone_count": len(snap),
        "connected": sum(1 for d in snap if d.connected),
        "origin": origin_var,
    }
