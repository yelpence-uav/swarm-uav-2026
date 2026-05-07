"""Uyarı motoru — DroneState'e bakar, kuralları uygular, alert listesini yönetir.

Davranışlar:
  - Hysteresis: bat %20 altında aktif, %22 üstünde pasif (titreme/spam yok).
  - GPS grace period: backend açıldıktan sonra ilk 15 sn GPS uyarısı verme.
  - Aynı (drone_id, code) çifti aktifken yeni alert üretilmez; pasif olunca düşer.
  - Bağlantı kopuk drone için yalnızca link_timeout uyarısı (diğerleri stale veriyle yanıltır).
"""

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
    drone_id: int
    severity: str
    code: str
    message: str
    timestamp: float


class AlertManager:
    """Drone snapshot'larından alert listesi üretir."""

    GPS_GRACE_SEC = 15.0

    BAT_LOW_ON = 20.0
    BAT_LOW_OFF = 22.0
    BAT_CRIT_ON = 10.0
    BAT_CRIT_OFF = 12.0

    EVENT_TTL_SEC = 8.0  # info-level event'lar bu kadar süre görünür

    def __init__(self) -> None:
        self._started_at = time.time()
        # Aktif alert'ler: (drone_id, code) -> Alert (kural-tabanlı, kalıcı)
        self._active: dict[tuple[int, str], Alert] = {}
        # Tek seferlik event'lar: liste — TTL dolunca düşer
        self._events: list[Alert] = []
        self._events_lock = threading.Lock()

    def push_event(self, drone_id: int, severity: str, code: str, message: str) -> None:
        """Tek seferlik bir event yayınla (komut ACK gibi). EVENT_TTL_SEC sonra düşer."""
        with self._events_lock:
            self._events.append(Alert(
                drone_id=drone_id,
                severity=severity,
                code=code,
                message=message,
                timestamp=time.time(),
            ))

    def _grace_active(self) -> bool:
        return (time.time() - self._started_at) < self.GPS_GRACE_SEC

    def _set(self, key: tuple[int, str], severity: str, message: str) -> None:
        existing = self._active.get(key)
        if existing and existing.severity == severity and existing.message == message:
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
        for d in drones:
            link_key = (d.drone_id, "link_timeout")
            bat_low_key = (d.drone_id, "low_battery")
            bat_crit_key = (d.drone_id, "critical_battery")
            gps_key = (d.drone_id, "weak_gps")

            if not d.connected:
                # Bağlantı yoksa diğer kuralları çalıştırma — stale veri.
                self._set(link_key, SEVERITY_CRITICAL, "Bağlantı koptu")
                # Diğerlerini temizle (stale)
                self._clear(bat_low_key)
                self._clear(bat_crit_key)
                self._clear(gps_key)
                continue

            self._clear(link_key)

            # Batarya — kritik (hysteresis ON/OFF)
            if d.battery_percent <= self.BAT_CRIT_ON:
                self._set(
                    bat_crit_key, SEVERITY_CRITICAL,
                    f"Batarya kritik %{d.battery_percent:.0f}",
                )
            elif d.battery_percent >= self.BAT_CRIT_OFF:
                self._clear(bat_crit_key)

            # Batarya — düşük (kritik aktif değilse)
            if bat_crit_key not in self._active:
                if d.battery_percent <= self.BAT_LOW_ON and d.battery_percent > 0:
                    self._set(
                        bat_low_key, SEVERITY_CRITICAL,
                        f"Düşük batarya %{d.battery_percent:.0f}",
                    )
                elif d.battery_percent >= self.BAT_LOW_OFF:
                    self._clear(bat_low_key)
            else:
                # Kritik aktifken düşüğü gizle
                self._clear(bat_low_key)

            # GPS — grace period sonrası
            if not self._grace_active():
                if d.gps_fix_type < 3:
                    self._set(
                        gps_key, SEVERITY_WARNING,
                        f"Zayıf GPS (fix={d.gps_fix_type}, sat={d.gps_satellites})",
                    )
                else:
                    self._clear(gps_key)

        # Süresi dolan event'ları temizle
        now = time.time()
        with self._events_lock:
            self._events = [e for e in self._events if (now - e.timestamp) < self.EVENT_TTL_SEC]
            current_events = list(self._events)

        # Severity sırası: critical → warning → info; aynı severity'de en yeni en üstte
        order = {SEVERITY_CRITICAL: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}
        return sorted(
            list(self._active.values()) + current_events,
            key=lambda a: (order.get(a.severity, 3), -a.timestamp),
        )
