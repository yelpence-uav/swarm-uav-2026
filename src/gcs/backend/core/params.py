"""Uçuş parametreleri — operatörün Ayarlar sekmesinden düzenlediği varsayılanlar.

Takeoff/goto komutları için varsayılan irtifa ve hız ile güvenlik için
min-navigasyon-irtifası burada tutulur. Bellek-içi (session boyu); ileride
dosyaya kalıcı yapılabilir. Backend goto guard'ı min_nav_altitude_m'i uygular;
frontend pop-up'ları default_* değerlerini ön-doldurur (operatör değiştirebilir).
"""

from dataclasses import asdict, dataclass
from threading import Lock


@dataclass
class UcusParametreleri:
    default_altitude_m: float = 5.0     # takeoff/goto varsayılan irtifa (m)
    default_speed_ms: float = 3.0       # yatay seyir hızı (m/s)
    min_nav_altitude_m: float = 2.0     # bunun altında yatay navigasyon yok → oto-kalkış tetikler


# Alan → (min, max) sınırları; dışına çıkan değerler kırpılır.
_SINIRLAR = {
    "default_altitude_m": (0.5, 120.0),
    "default_speed_ms": (0.2, 20.0),
    "min_nav_altitude_m": (0.0, 50.0),
}


class ParamStore:
    """Thread-safe uçuş parametre deposu."""

    def __init__(self) -> None:
        self._p = UcusParametreleri()
        self._lock = Lock()

    def get(self) -> dict:
        with self._lock:
            return asdict(self._p)

    def update(self, **kwargs) -> dict:
        with self._lock:
            for key, val in kwargs.items():
                if val is None or not hasattr(self._p, key):
                    continue
                lo, hi = _SINIRLAR.get(key, (float("-inf"), float("inf")))
                setattr(self._p, key, max(lo, min(hi, float(val))))
            return asdict(self._p)
