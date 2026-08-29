# Copyright 2026 Yelpence
"""Uyarı motoru."""

import threading
import time
from dataclasses import dataclass
from typing import Iterable

from backend.core.log_store import LogStore
from backend.core.state_store import DroneState

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

# GPS fix tipi -> operatorun okuyabilecegi ad. Uyari metninde "fix=2" yerine
# "2B konum" yaziyoruz; sahada sayiyi kimse akilda tutmuyor.
FIX_ADI = {
    0: "konum yok",
    1: "konum yok",
    2: "2B konum",
    3: "3B konum",
    4: "DGPS",
    5: "RTK (kayan)",
    6: "RTK (sabit)",
}


@dataclass
class Alert:
    """Tek bir aktif uyarının özeti."""

    drone_id: int
    severity: str
    code: str
    message: str
    timestamp: float


class AlertManager:
    """Sürü durumlarına göre uyarılar üreten motor."""

    GPS_GRACE_SEC = 15.0
    BAT_LOW_ON = 25.0
    BAT_LOW_OFF = 27.0
    BAT_CRIT_ON = 15.0
    BAT_CRIT_OFF = 17.0
    EVENT_TTL_SEC = 10.0
    RTK_FIX_MIN = 5

    # SUSTURULABILIR UYARILAR — kanit videosu icin.
    #
    # Yonerge YKI ekraninin videoda gorunmesini SART kosuyor ve videoya
    # mudahale (kirpma/kesme) YASAK. Yani ekranda ne varsa hakem onu goruyor.
    # Ucus sirasinda "Baglanti koptu" ve "Dusuk batarya" kutulari surekli
    # aciIip kapaniyor (mesh %30 paket kaybi yasiyor, tek bir bosluk bile
    # link_timeout uretiyor) ve ekrani ariza gorunumune sokuyor.
    #
    # SILMIYORUZ, SUSTURUYORUZ: kod tarafinda uyari yine uretiliyor, yalniz
    # listeye konmuyor. config.yaml -> alerts.susturulan ile ac/kapa.
    #
    # DIKKAT: batarya uyarisini susturmak, pilin bittigini EKRANDAN
    # ogrenmeyecegin anlamina gelir. Kalan yuzdeyi drone kartlarindaki
    # BatteryGauge gostermeye devam ediyor — ucustan once oraya bak.
    SUSTURULABILIR = frozenset(
        {"link_timeout", "low_battery", "critical_battery", "weak_gps",
         "rtk_lost"}
    )

    # PIL DEGERLENDIRMESI KAPALI (27 Agustos 2026, operator karari)
    #
    # NEDEN: su an sahada pil olcumu YOK. ylp01'in guc olcum karti eksik,
    # digerlerinde de PX4 tezgahta sabit "12.6 V / %100" sentinel'i veriyor
    # (TUZAKLAR §1.20). Yani gelen sayi ne dolu ne bos — ANLAMSIZ.
    #
    # Bunu "sustur" ile cozmuyoruz: susturma, GERCEK bir sinyali ekrandan
    # gizlemek demek ve o sinyal deftere yine giriyor. Burada gizlenecek bir
    # sinyal yok; olmayan bir olcumden uyari uretmeyi tamamen birakiyoruz.
    # Aksi halde her arka uc acilisinda "Batarya kritik %0" defteri
    # kirletiyor ve LOG butonunu bos yere kirmizi yakiyordu — telemetri
    # gelmeden once durum sifir ve pilin GPS'teki gibi lutuf suresi yok.
    #
    # ACMAK ICIN: pil olcum kartlari takilinca config.yaml -> alerts.pil: true.
    # O gun esikler (BAT_*) ve lutuf suresi de bastan gozden gecirilmeli.
    def __init__(
        self,
        susturulan: Iterable[str] = (),
        gunluk: "LogStore | None" = None,
        pil: bool = False,
    ) -> None:
        self.susturulan = {
            k for k in susturulan if k in self.SUSTURULABILIR
        }
        # Kalici defter (bkz. core/log_store.py). Uyari motorunun davranisi
        # DEGISMIYOR — ayni kayitlar bir de deftere dusuyor. None ise hicbir
        # sey degismez, yani mevcut testler ve cagirilar etkilenmez.
        #
        # DIKKAT: susturulan uyarilar da deftere GIRER. Ekranda susturmak
        # "hakem videosunda ariza gorunumu olmasin" icindi; sonradan
        # incelerken o kayitlarin YOK olmasi bambaska bir sey olurdu.
        self._gunluk = gunluk
        self._pil = bool(pil)
        self._active: dict[tuple[int, str], Alert] = {}
        self._events: list[Alert] = []
        self._events_lock = threading.Lock()
        self._started_at = time.time()
        self._had_rtk: set[int] = set()

    def push_event(
        self, drone_id: int, severity: str, code: str, message: str
    ) -> None:
        """Tek seferlik bir event yayınla."""
        with self._events_lock:
            self._events.append(
                Alert(
                    drone_id=drone_id,
                    severity=severity,
                    code=code,
                    message=message,
                    timestamp=time.time(),
                )
            )
        if self._gunluk is not None:
            self._gunluk.ekle(drone_id, severity, code, message)

    def _grace_active(self) -> bool:
        return (time.time() - self._started_at) < self.GPS_GRACE_SEC

    def _set(self, key: tuple[int, str], severity: str, message: str) -> None:
        existing = self._active.get(key)
        if (
            existing
            and existing.severity == severity
            and existing.message == message
        ):
            return
        self._active[key] = Alert(
            drone_id=key[0],
            severity=severity,
            code=key[1],
            message=message,
            timestamp=time.time(),
        )
        # Yalniz DEGISIM aninda deftere dusuyoruz: yukaridaki erken donus,
        # ayni uyari surdugu surece buraya gelinmesini engelliyor. Aksi halde
        # "Baglanti koptu" her degerlendirme turunda (10 Hz) deftere yazilir
        # ve defter tek bir arizayla dolardi.
        if self._gunluk is not None:
            self._gunluk.ekle(key[0], severity, key[1], message)

    def _clear(self, key: tuple[int, str]) -> None:
        self._active.pop(key, None)

    def evaluate(self, drones: Iterable[DroneState]) -> list[Alert]:
        """Durumu degerlendirip aktif uyarilari doner."""
        for d in drones:
            link_key = (d.drone_id, "link_timeout")
            bat_low_key = (d.drone_id, "low_battery")
            bat_crit_key = (d.drone_id, "critical_battery")
            gps_key = (d.drone_id, "weak_gps")
            rtk_key = (d.drone_id, "rtk_lost")

            if not d.connected:
                self._set(link_key, SEVERITY_CRITICAL, "Telemetri kesildi")
                self._clear(bat_low_key)
                self._clear(bat_crit_key)
                self._clear(gps_key)
                self._clear(rtk_key)
                continue

            self._clear(link_key)

            if not self._pil:
                # Pil olcumu yok -> hic uyari uretme, eskisini de temizle.
                self._clear(bat_low_key)
                self._clear(bat_crit_key)
            elif d.battery_percent <= self.BAT_CRIT_ON:
                self._set(
                    bat_crit_key,
                    SEVERITY_CRITICAL,
                    f"Pil kritik: %{d.battery_percent:.0f}",
                )
            elif d.battery_percent >= self.BAT_CRIT_OFF:
                self._clear(bat_crit_key)

            if self._pil and bat_crit_key not in self._active:
                if (
                    d.battery_percent <= self.BAT_LOW_ON
                    and d.battery_percent > 0
                ):
                    self._set(
                        bat_low_key,
                        SEVERITY_CRITICAL,
                        f"Pil azaldı: %{d.battery_percent:.0f}",
                    )
                elif d.battery_percent >= self.BAT_LOW_OFF:
                    self._clear(bat_low_key)
            else:
                self._clear(bat_low_key)

            if not self._grace_active():
                if d.gps_fix_type < 3:
                    msg = (
                        f"GPS zayıf: {FIX_ADI.get(d.gps_fix_type, d.gps_fix_type)}"
                        f", {d.gps_satellites} uydu"
                    )
                    self._set(gps_key, SEVERITY_WARNING, msg)
                else:
                    self._clear(gps_key)

            if d.gps_fix_type >= self.RTK_FIX_MIN:
                self._had_rtk.add(d.drone_id)
                self._clear(rtk_key)
            elif d.drone_id in self._had_rtk and not self._grace_active():
                self._set(
                    rtk_key,
                    SEVERITY_WARNING,
                    "RTK kilidi kayboldu — şu an "
                    f"{FIX_ADI.get(d.gps_fix_type, d.gps_fix_type)}",
                )

        now = time.time()
        with self._events_lock:
            self._events = [
                e
                for e in self._events
                if (now - e.timestamp) < self.EVENT_TTL_SEC
            ]
            current_events = list(self._events)

        order = {SEVERITY_CRITICAL: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}
        hepsi = list(self._active.values()) + current_events
        if self.susturulan:
            hepsi = [a for a in hepsi if a.code not in self.susturulan]
        return sorted(
            hepsi,
            key=lambda a: (order.get(a.severity, 3), -a.timestamp),
        )
