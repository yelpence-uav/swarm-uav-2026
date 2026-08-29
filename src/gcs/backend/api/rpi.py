# Copyright 2026 Yelpence
"""Raspberry Pi anlık durumu — YALNIZ SSH üzerinden.

    GET /api/rpi/{drone_id}

🔴 BU VERİ MESH'TEN GEÇMEZ. Operatör kararı (29 Ağustos 2026): Pi sağlık
bilgisi yalnız SSH ile gelir. Mesh 16 baytlık paketler taşıyor ve görev
telemetrisi için ayrılmış; oraya teşhis verisi koymak dar bandı yer. SSH
yoksa bilgi de yoktur — bu uç `ssh_ok:false` döner ve arayüz "bilinmiyor"
gösterir. **Tahmin üretilmez, bayat değer gösterilmez.**

Ölçümü `deploy/rpi/teshis/rpi_durum.sh` yapıyor ve betik stdin'den
geçiriliyor: uçağa dağıtım GEREKMEZ, dolayısıyla bu özellik uçaklardaki
kod sürümünden bağımsız çalışır.

Kimlik/IP çözümlemesi `deploy/yki/drone_bul.sh` üzerinden — kendi drone
tablosunu tutan İKİNCİ bir yer açmıyoruz (`CLAUDE.md` §9: "aynı sabiti iki
yere yazma"; 2 Ağustos'ta filo varsayılanı iki yerde durduğu için düşmüş
drone'a komut gitti).
"""

import logging
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/rpi", tags=["rpi"])

logger = logging.getLogger("backend.rpi")

# backend/api/rpi.py -> src/gcs/backend/api -> depo kökü
_KOK = Path(__file__).resolve().parents[4]
_DRONE_BUL = _KOK / "deploy" / "yki" / "drone_bul.sh"
_OLCUM = _KOK / "deploy" / "rpi" / "teshis" / "rpi_durum.sh"

# SSH + ölçüm (içinde 0.3 sn CPU örneklemesi var) tipik olarak 1-3 sn sürüyor.
# 12 sn: ağ yavaşsa bir şans daha, ama arayüz kilitlenmesin.
_ZAMAN_ASIMI_SN = 12

# Drone tablosu ağ taraması yapabiliyor (önbellek → mDNS → MAC). Her panel
# açılışında taramamak için kısa süre bellekte tutuluyor; IP değişirse
# 60 sn içinde kendiliğinden düzelir.
_TABLO_OMRU_SN = 60
_tablo_onbellek: dict[int, str] = {}
_tablo_zaman = 0.0


def _tablo() -> dict[int, str]:
    """agent_id -> drone adı (ylp00...). Tek kaynak: drone_bul.sh --tablo."""
    global _tablo_onbellek, _tablo_zaman
    if _tablo_onbellek and (time.time() - _tablo_zaman) < _TABLO_OMRU_SN:
        return _tablo_onbellek
    try:
        r = subprocess.run(
            [str(_DRONE_BUL), "--tablo"],
            capture_output=True, text=True, timeout=_ZAMAN_ASIMI_SN,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("drone_bul.sh --tablo başarısız: %s", e)
        return _tablo_onbellek  # eldeki bayat tablo hiç yoktan iyi
    esleme: dict[int, str] = {}
    for satir in r.stdout.splitlines():
        alan = satir.split("\t")
        if len(alan) >= 5 and alan[4].strip().isdigit():
            esleme[int(alan[4])] = alan[0].strip()
    if esleme:
        _tablo_onbellek, _tablo_zaman = esleme, time.time()
    return _tablo_onbellek or esleme


def _sayi(s: str) -> float | int | str:
    """'54.9' -> 54.9, '42' -> 42, geri kalanı olduğu gibi."""
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


@router.get("/{drone_id}")
def rpi_durum(drone_id: int):
    """Pi'nin anlık sağlık değerlerini SSH ile okur."""
    if not _OLCUM.is_file():
        raise HTTPException(500, f"ölçüm betiği yok: {_OLCUM}")

    ad = _tablo().get(drone_id)
    if ad is None:
        # Ağda değilse tablo onu hiç listelemiyor — hata değil, "ulaşılamıyor".
        return {
            "drone_id": drone_id, "ssh_ok": False,
            "hata": "Drone ağda bulunamadı (SSH yok)", "degerler": {},
        }

    try:
        with _OLCUM.open("rb") as f:
            r = subprocess.run(
                [str(_DRONE_BUL), ad, "bash -s"],
                stdin=f, capture_output=True, text=True,
                timeout=_ZAMAN_ASIMI_SN,
            )
    except subprocess.TimeoutExpired:
        return {
            "drone_id": drone_id, "ad": ad, "ssh_ok": False,
            "hata": f"SSH {_ZAMAN_ASIMI_SN} sn içinde cevap vermedi",
            "degerler": {},
        }
    except OSError as e:
        return {
            "drone_id": drone_id, "ad": ad, "ssh_ok": False,
            "hata": f"SSH başlatılamadı: {e}", "degerler": {},
        }

    degerler = {
        k: _sayi(v)
        for satir in r.stdout.splitlines()
        if "=" in satir
        for k, v in [satir.split("=", 1)]
    }
    if not degerler:
        ham = r.stderr.strip()
        # Arka uç KONTEYNERDE koşuyorsa (Arch kurulumu) `ssh` istemcisi ve
        # ~/.ssh anahtarları imajda olmayabilir. Ham "command not found"
        # mesajı operatöre bir şey anlatmıyor — ne yapılacağını söylüyoruz.
        # Ubuntu/macOS kurulumlarında arka uç konteynersiz koştuğu için bu
        # yola hiç girilmez.
        if "not found" in ham and "ssh" in ham:
            hata = (
                "Yer istasyonunda `ssh` istemcisi yok. Arka uç konteynerde "
                "koşuyorsa imaja `openssh-client` eklenmeli ve ~/.ssh "
                "bağlanmalı (arch-docker/)."
            )
        elif "Permission denied" in ham or "publickey" in ham:
            hata = f"SSH anahtarı kabul edilmedi ({ad}). Anahtar kurulu mu?"
        else:
            hata = (ham.splitlines() or ["SSH cevap vermedi"])[-1][:200]
        return {
            "drone_id": drone_id, "ad": ad, "ssh_ok": False,
            "hata": hata, "degerler": {},
        }
    return {
        "drone_id": drone_id, "ad": ad, "ssh_ok": True,
        "zaman": time.time(), "degerler": degerler,
    }
