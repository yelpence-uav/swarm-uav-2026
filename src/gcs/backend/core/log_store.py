# Copyright 2026 Yelpence
"""Uçuş ve sistem olaylarının KALICI defteri.

NEDEN AYRI BIR SINIF (27 Agustos 2026)
--------------------------------------
`AlertManager` uyarilari EVENT_TTL_SEC = 10 sn sonra siliyor — dogru davranis,
cunku o ekrandaki *anlik* kutulari besliyor. Ama operatorun sordugu sey baska:
"her drone'un loglarini gorebilecegim bir kisim olsun". Bunun icin gecmis
gerekiyor ve gecmis TTL ile bagdasmiyor.

Bu yuzden defter ayri: uyari motorunun davranisi DEGISMIYOR, yalnizca ayni
kayitlar bir de buraya dusuyor.

DISKE YAZMA — P1.16
-------------------
Uyarilar bugune kadar yalnizca RAM'deydi: YKI kapaninca ucus boyunca ne
oldugunun kaydi kayboluyordu. Yonerge YKI ekraninin videoda gorunmesini sart
kosuyor ama video sonradan aranabilir bir kayit degil.

DOSYA BUYUMESI SINIRLI — bu bir tercih degil, 26/27 Agustos dersi. O gece
MAVROS'un GCS hatti bozulunca `mavros.log` tek oturumda 876 MB'a cikti ve SD
karti yipratti; tarihsel tepe 18,64 GB'ti. Sinirsiz buyuyen hicbir kayit
dosyasi birakmiyoruz.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

# Bellekte tutulan kayit sayisi. 2000 kayit ~ yogun bir ucusun tamami; panel
# zaten sayfa sayfa okuyor, daha fazlasi RAM'de bosuna durur.
VARSAYILAN_KAPASITE = 2000

# Disk dosyasinin tavani. Asilinca .1 uzantisiyla tek bir yedege donulur ve
# yeni dosya acilir (bir onceki yedek silinir). Yani en fazla 2x bu boyut.
VARSAYILAN_DOSYA_TAVANI_B = 8 * 1024 * 1024


@dataclass
class GunlukKaydi:
    """Deftere düşen tek satır."""

    sira: int          # monoton artan; panel "bundan sonrasini ver" diyebilsin
    zaman: float       # unix epoch
    drone_id: int      # 0 = sistem geneli
    siddet: str        # info / warning / critical
    kod: str           # makine tarafi: event_43, link_timeout, ...
    mesaj: str         # insan tarafi


class LogStore:
    """Sınırlı halka tampon + isteğe bağlı diske yazma.

    Iplik guvenli: ROS geri cagirma ipliginden yazilir, HTTP ipliginden
    okunur.
    """

    def __init__(
        self,
        kapasite: int = VARSAYILAN_KAPASITE,
        dosya: str | os.PathLike[str] | None = None,
        dosya_tavani_b: int = VARSAYILAN_DOSYA_TAVANI_B,
    ) -> None:
        self._kapasite = max(1, int(kapasite))
        self._kayitlar: list[GunlukKaydi] = []
        self._kilit = threading.Lock()
        self._sira = 0
        self._dosya = Path(dosya) if dosya else None
        self._dosya_tavani_b = int(dosya_tavani_b)
        if self._dosya is not None:
            # Dizin acilamiyorsa (izin yok, salt-okunur disk) diske yazmayi
            # KAPATIP devam ediyoruz. Burada istisna firlatmak butun YKI
            # arka ucunu acilista dusururdu — defter, calistirdigi sistemden
            # daha onemli degil. `_diske_yaz` da ayni ilkeyle sessiz.
            try:
                self._dosya.parent.mkdir(parents=True, exist_ok=True)
            except Exception:  # noqa: BLE001
                self._dosya = None

    # ------------------------------------------------------------------ yaz
    def ekle(self, drone_id: int, siddet: str, kod: str, mesaj: str) -> GunlukKaydi:
        """Deftere bir satır ekler ve eklenen kaydı döner."""
        with self._kilit:
            self._sira += 1
            kayit = GunlukKaydi(
                sira=self._sira,
                zaman=time.time(),
                drone_id=int(drone_id),
                siddet=str(siddet),
                kod=str(kod),
                mesaj=str(mesaj),
            )
            self._kayitlar.append(kayit)
            # Halka tampon: bastan kirp. `del` dilimi, her eklemede yeni liste
            # kurmaktan ucuz.
            if len(self._kayitlar) > self._kapasite:
                del self._kayitlar[: len(self._kayitlar) - self._kapasite]
        self._diske_yaz(kayit)
        return kayit

    def _diske_yaz(self, kayit: GunlukKaydi) -> None:
        """Kaydı JSONL olarak diske ekler. Hata YUTULUR — defter, uyarı
        motorunu düşürmemeli; disk dolu olsa bile YKİ çalışmaya devam eder."""
        if self._dosya is None:
            return
        try:
            # Tavan asildiysa tek yedege don. Iki dosyadan fazlasini
            # tutmuyoruz: amac "son bir dilim" saklamak, arsiv degil.
            if (self._dosya.exists()
                    and self._dosya.stat().st_size >= self._dosya_tavani_b):
                yedek = self._dosya.with_suffix(self._dosya.suffix + ".1")
                os.replace(self._dosya, yedek)
            with self._dosya.open("a", encoding="utf-8") as f:
                # flush: olaylar seyrek, gecikme onemsiz; YKI cokerse kayit
                # diskte kalsin (bu defterin varlik sebebi).
                f.write(json.dumps(asdict(kayit), ensure_ascii=False) + "\n")
                f.flush()
        except Exception:  # noqa: BLE001 — bilincli olarak yutuluyor
            pass

    # ------------------------------------------------------------------ oku
    def oku(
        self,
        drone_id: int | None = None,
        min_siddet: str | None = None,
        sonra: int = 0,
        limit: int = 200,
    ) -> list[GunlukKaydi]:
        """Süzülmüş kayıtları döner (eskiden yeniye).

        sonra : bu sira numarasindan BUYUK olanlar (panel artimli ceker)
        limit : en fazla kac kayit — SON `limit` tanesi doner
        """
        sira_esik = max(0, int(sonra))
        with self._kilit:
            secilen = [k for k in self._kayitlar if k.sira > sira_esik]
        if drone_id is not None:
            # 0 = sistem geneli; belirli bir drone istendiginde sistem
            # olaylarini da GOSTERIYORUZ, cunku "Pi diski doldu" o drone'u
            # ilgilendirir ve ayri sekmede aramak zorunda kalmamali.
            secilen = [k for k in secilen
                       if k.drone_id == drone_id or k.drone_id == 0]
        if min_siddet:
            esik = _SIDDET_SIRA.get(min_siddet, 0)
            secilen = [k for k in secilen
                       if _SIDDET_SIRA.get(k.siddet, 0) >= esik]
        if limit > 0:
            secilen = secilen[-limit:]
        return secilen

    def son_sira(self) -> int:
        with self._kilit:
            return self._sira


# Siddet siralamasi — string karsilastirmasi yanlis sonuc verirdi
# ("critical" < "info" alfabetik olarak dogru ama anlamsiz).
_SIDDET_SIRA = {"info": 0, "warning": 1, "critical": 2, "emergency": 3}
