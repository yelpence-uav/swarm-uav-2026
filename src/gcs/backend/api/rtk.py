"""RTK baz istasyonu bakım komutları — şimdilik yalnız u-blox reset.

Komut seri porta DOĞRUDAN yazılmaz: u-blox portunun sahibi
`yki_rtcm_reader.py` ve seri port TEK SAHİPLİ (ikinci açan "Resource busy"
alır). Bu uç nokta komutu ROS'a basar, okuyucu UBX-CFG-RST olarak porta yazar.

    POST /api/rtk/reset            → sıcak reset (varsayılan)
    POST /api/rtk/reset?kip=soguk  → soğuk reset

⚠️ RESET RTCM AKIŞINI KESER. Alıcı yeniden açılana kadar (tipik 5-15 sn) baz
düzeltme yayınlamaz ve UÇAKLAR RTK-FIX'İ DÜŞÜRÜR. Havadayken çağırma.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/rtk", tags=["rtk"])

logger = logging.getLogger("backend.rtk")

# Okuyucudaki _UBX_BBR ile AYNI kümeyi tanır. Burada tutulma sebebi arayüze
# seçenek listesi verebilmek; anlamları ve UBX karşılıkları okuyucuda.
KIPLER = {
    "sicak": "Hafızadaki her şey korunur, en hızlı toparlanır (varsayılan)",
    "ilik": "Efemeris silinir, uydu takibi baştan kurulur",
    "soguk": "Tüm yardımcı veri silinir, toparlanması en uzun sürer",
}


def _bridge(request: Request):
    bridge = request.app.state.bridge
    if bridge is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "RTK komutları sadece ros2 modunda kullanılır. "
                f"Şu anki mod: {request.app.state.connection_mode}."
            ),
        )
    return bridge


@router.get("/kipler")
def kipler():
    """Arayüzün seçenek listesi — tek kaynak burada."""
    return {"kipler": [{"ad": k, "aciklama": v} for k, v in KIPLER.items()]}


@router.post("/reset")
def reset(request: Request, kip: str = "sicak"):
    """u-blox baz alıcısını yeniden başlatır."""
    if kip not in KIPLER:
        raise HTTPException(
            status_code=400,
            detail=f"Bilinmeyen kip: {kip}. Geçerli: {', '.join(KIPLER)}",
        )
    _bridge(request).publish_rtk_reset(kip)
    logger.warning(
        "u-blox RESET komutu gönderildi (kip=%s) — RTCM birkaç saniye "
        "kesilecek, uçaklar RTK-FIX düşürebilir",
        kip,
    )
    return {
        "status": "sent",
        "action": "rtk_reset",
        "kip": kip,
        "uyari": (
            "RTCM akışı birkaç saniye kesilecek; uçaklar RTK-FIX'i "
            "düşürüp yeniden yakalayacak."
        ),
    }
