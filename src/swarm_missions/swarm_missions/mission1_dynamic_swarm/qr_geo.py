"""qr_geo.py — QR konum tablosu + SwarmOrigin ile NED hedef çözümü.

Şartname: QR kodu yalnızca ``next_qr`` NUMARASINI verir, konumu vermez.
Konumlar yarışma öncesi YKİ'den girilir (QRCoordinates tablosu). Bu modül
o tabloyu ve paylaşılan origin'i tutar; bir QR numarasını sürünün uçtuğu
shared-NED çerçevesine (metre) çevirir.

Neden NED: otopilot metreyle çalışır (formation_control ofsetleri metre).
GPS lat/lon → NED çevirimi ortak bir referans (SwarmOrigin) gerektirir;
origin gelmeden hiçbir QR konuma çözülemez.

Kontrol/geometri matematiği yok; yalnızca tablo + latlon_to_ned sarmalı.
ROS bağımlılığı yoktur → birim test edilebilir.
"""

from swarm_core.formation_control.formation_geometry import latlon_to_ned


class QrGeoResolver:
    """QR numarasını (north, east, agl) hedefine çözer.

    Tablo QRCoordinates mesajından, origin SwarmOrigin mesajından beslenir.
    Her ikisi de gelmeden ``ready`` False'tur ve çözüm yapılmaz.
    """

    def __init__(self) -> None:
        """Boş tablo ve tanımsız origin ile başlatır."""
        self._table: dict = {}
        self._origin: tuple | None = None

    def set_table(self, qr_ids, lat_deg, lon_deg, alt_m) -> None:
        """QR konum tablosunu paralel dizilerden kurar.

        Args:
            qr_ids: QR numaraları (örn. [1, 2, 3, 4, 5, 6]).
            lat_deg: Her QR'ın enlemi (WGS84 derece).
            lon_deg: Her QR'ın boylamı (WGS84 derece).
            alt_m: Her QR'ın irtifası (metre, AGL, yukarı pozitif).
        """
        table = {}
        for i, qid in enumerate(qr_ids):
            table[int(qid)] = (
                float(lat_deg[i]), float(lon_deg[i]), float(alt_m[i]),
            )
        self._table = table

    def set_origin(self, lat_deg, lon_deg) -> None:
        """Paylaşılan NED origin'ini (SwarmOrigin) günceller.

        Args:
            lat_deg: Origin enlemi (WGS84 derece).
            lon_deg: Origin boylamı (WGS84 derece).
        """
        self._origin = (float(lat_deg), float(lon_deg))

    @property
    def ready(self) -> bool:
        """Hem origin hem de en az bir QR tablosu varsa True."""
        return self._origin is not None and bool(self._table)

    def has(self, qr_id) -> bool:
        """Verilen QR numarası tabloda tanımlıysa True."""
        return int(qr_id) in self._table

    def resolve_ned(self, qr_id):
        """QR numarasını shared-NED hedefine çözer.

        Args:
            qr_id: Çözülecek QR numarası.

        Returns:
            (north_m, east_m, alt_agl_m) demeti; hazır değilse veya QR
            tabloda yoksa None. alt_agl_m yukarı pozitiftir; NED z'ye
            çevirmek çağıranın sorumluluğundadır (down = -alt_agl_m).
        """
        if not self.ready:
            return None
        qid = int(qr_id)
        entry = self._table.get(qid)
        if entry is None:
            return None
        lat, lon, alt = entry
        north, east = latlon_to_ned(
            lat, lon, self._origin[0], self._origin[1],
        )
        return (north, east, alt)
