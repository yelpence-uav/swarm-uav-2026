"""Uçuş parametreleri — operatörün Ayarlar sekmesinden düzenlediği varsayılanlar.

İKİ AYRI KÜME VAR ve karıştırılmamalı:

  1. `default_*` / `min_nav_*` — YALNIZ YKİ'nin GUIDED (takeoff/goto) test
     yolunu besler (`api/guided.py`). Görev 1 ve Görev 2 bunları HİÇ
     okumaz. 5 Eylül 2026'da bu ayrım yazıldı; öncesinde panel bunu
     söylemiyordu ve "ayarladım ama görevde değişmedi" tuzağı vardı.

  2. `suru_*` — GÖREV 2 sürü davranışı. Bunlar BAŞLAT paketinin içinde
     mesh'ten uçaklara gider (`ros_bridge._g2_ayar_yayinla` →
     `_GOREV_FMT` rezervi) ve `mode_manager` ROS parametresi olarak
     uygular. Sınır denetimi UÇAKTA (`canli_param`); buradaki sınırlar
     yalnızca kaba emniyet — tek kaynak uçaktır.

Bellek-içi (session boyu); ileride dosyaya kalıcı yapılabilir.
"""

from dataclasses import asdict, dataclass
from threading import Lock


@dataclass
class UcusParametreleri:
    default_altitude_m: float = 5.0     # takeoff/goto varsayılan irtifa (m)
    default_speed_ms: float = 3.0       # yatay seyir hızı (m/s)
    min_nav_altitude_m: float = 2.0     # bunun altında yatay navigasyon yok → oto-kalkış tetikler

    # --- GÖREV 2 sürü davranışı (BAŞLAT paketiyle uçaklara gider) -------
    # 0.0 = "belirtilmedi" → uçak kendi varsayılanını korur. Operatörün
    # boş bırakması GEÇERLİ bir seçim, aralık/irtifa ile aynı sözleşme.
    suru_morf_hiz_mps: float = 0.0      # formasyon değişimi slot hızı
    suru_hareket_hiz_mps: float = 0.0   # MOVEMENT öteleme hızı
    suru_yaw_hiz_deg_s: float = 0.0     # sürü dönüş hızı tavanı
    suru_egim_tavan_deg: float = 0.0    # manevra eğim genliği


# Alan → (min, max) sınırları; dışına çıkan değerler kırpılır.
_SINIRLAR = {
    "default_altitude_m": (0.5, 120.0),
    "default_speed_ms": (0.2, 20.0),
    "min_nav_altitude_m": (0.0, 50.0),
    # 0.0 = belirtilmedi, o yüzden alt sınır 0. Üst sınırlar mesh'in
    # 1 baytlık kodlamasıyla uyumlu; asıl denetim uçakta (canli_param).
    "suru_morf_hiz_mps": (0.0, 3.0),
    "suru_hareket_hiz_mps": (0.0, 5.0),
    "suru_yaw_hiz_deg_s": (0.0, 25.0),
    "suru_egim_tavan_deg": (0.0, 30.0),
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
