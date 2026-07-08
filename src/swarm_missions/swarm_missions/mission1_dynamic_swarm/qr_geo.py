"""qr_geo.py — güncel QR hedefi + SwarmOrigin ile NED konum çözümü.

mission_fsm "gidilecek sıradaki QR"ı çözüp MissionTarget olarak yayınlar
(qr_id + lat/lon). Bu modül o hedefin GPS konumunu, sürünün uçtuğu
shared-NED çerçevesine (metre) çevirir; "hangi QR" kararını VERMEZ.

Neden NED: otopilot metreyle çalışır (formation_control ofsetleri metre).
GPS lat/lon → NED çevirimi ortak bir referans (SwarmOrigin) gerektirir;
origin gelmeden hedef konuma çözülemez.

Kontrol/geometri matematiği yok; yalnızca origin + latlon_to_ned sarmalı.
ROS bağımlılığı yoktur → birim test edilebilir.
"""

from swarm_core.formation_control.formation_geometry import latlon_to_ned


class QrGeoResolver:
    """Güncel QR hedefini (north, east) konumuna çözer.

    Hedef MissionTarget mesajından, origin SwarmOrigin mesajından beslenir.
    İkisi de gelmeden (ve hedef geçerli olmadan) ``ready`` False'tur.
    """

    def __init__(self) -> None:
        """Tanımsız hedef ve origin ile başlatır."""
        self._target: tuple | None = None
        self._origin: tuple | None = None

    def set_target(self, valid, lat_deg, lon_deg) -> None:
        """Güncel hedefi (MissionTarget) günceller.

        Args:
            valid: MissionTarget.valid; False ise hedef temizlenir (konum
                tabloda yok → navigasyon yapılmaz).
            lat_deg: Hedef QR enlemi (WGS84 derece).
            lon_deg: Hedef QR boylamı (WGS84 derece).
        """
        if valid:
            self._target = (float(lat_deg), float(lon_deg))
        else:
            self._target = None

    def set_origin(self, lat_deg, lon_deg) -> None:
        """Paylaşılan NED origin'ini (SwarmOrigin) günceller.

        Args:
            lat_deg: Origin enlemi (WGS84 derece).
            lon_deg: Origin boylamı (WGS84 derece).
        """
        self._origin = (float(lat_deg), float(lon_deg))

    @property
    def ready(self) -> bool:
        """Hem origin hem geçerli bir hedef varsa True."""
        return self._origin is not None and self._target is not None

    def resolve_ned(self):
        """Güncel hedefi shared-NED (north, east) konumuna çözer.

        Returns:
            (north_m, east_m) demeti; origin ya da geçerli hedef yoksa None.
            İrtifa taşınmaz — navigasyon mevcut irtifayı korur; uçuş irtifası
            QR görev adımından (altitude) gelir, konumdan değil.
        """
        if not self.ready:
            return None
        lat, lon = self._target
        north, east = latlon_to_ned(
            lat, lon, self._origin[0], self._origin[1],
        )
        return (north, east)
