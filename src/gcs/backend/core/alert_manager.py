# Copyright 2026 Yelpence
"""Uyarı motoru."""

import threading
import time
from dataclasses import dataclass
from typing import Iterable

from backend.core.state_store import DroneState

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"


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

    def __init__(self, susturulan: Iterable[str] = ()) -> None:
        self.susturulan = {
            k for k in susturulan if k in self.SUSTURULABILIR
        }
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
                self._set(link_key, SEVERITY_CRITICAL, "Bağlantı koptu")
                self._clear(bat_low_key)
                self._clear(bat_crit_key)
                self._clear(gps_key)
                self._clear(rtk_key)
                continue

            self._clear(link_key)

            if d.battery_percent <= self.BAT_CRIT_ON:
                self._set(
                    bat_crit_key,
                    SEVERITY_CRITICAL,
                    f"Batarya kritik %{d.battery_percent:.0f}",
                )
            elif d.battery_percent >= self.BAT_CRIT_OFF:
                self._clear(bat_crit_key)

            if bat_crit_key not in self._active:
                if (
                    d.battery_percent <= self.BAT_LOW_ON
                    and d.battery_percent > 0
                ):
                    self._set(
                        bat_low_key,
                        SEVERITY_CRITICAL,
                        f"Düşük batarya %{d.battery_percent:.0f}",
                    )
                elif d.battery_percent >= self.BAT_LOW_OFF:
                    self._clear(bat_low_key)
            else:
                self._clear(bat_low_key)

            if not self._grace_active():
                if d.gps_fix_type < 3:
                    msg = (
                        f"Zayıf GPS (fix={d.gps_fix_type}, "
                        f"sat={d.gps_satellites})"
                    )
                    self._set(gps_key, SEVERITY_WARNING, msg)
                else:
                    self._clear(gps_key)

            if d.gps_fix_type >= self.RTK_FIX_MIN:
                self._had_rtk.add(d.drone_id)
                self._clear(rtk_key)
            elif d.drone_id in self._had_rtk and not self._grace_active():
                fix_name = {
                    0: "yok",
                    1: "yok",
                    2: "2D",
                    3: "3D",
                    4: "DGPS",
                }.get(d.gps_fix_type, str(d.gps_fix_type))
                self._set(
                    rtk_key,
                    SEVERITY_WARNING,
                    f"RTK sinyali kayboldu (şu an {fix_name})",
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
