"""qr_geo.py — güncel QR hedefi + SwarmOrigin ile NED konum çözümü."""

from swarm_core.formation_control.formation_geometry import latlon_to_ned


class QrGeoResolver:
    """Güncel QR hedefini (north, east) konumuna çözer."""

    def __init__(self) -> None:
        """Tanımsız hedef ve origin ile başlatır."""
        self._target: tuple | None = None
        self._origin: tuple | None = None

    def set_target(self, valid, lat_deg, lon_deg) -> None:
        """Güncel hedefi (MissionTarget) günceller."""
        if valid:
            self._target = (float(lat_deg), float(lon_deg))
        else:
            self._target = None

    def set_origin(self, lat_deg, lon_deg) -> None:
        """Paylaşılan NED origin'ini (SwarmOrigin) günceller."""
        self._origin = (float(lat_deg), float(lon_deg))

    @property
    def ready(self) -> bool:
        """Hem origin hem geçerli bir hedef varsa True."""
        return self._origin is not None and self._target is not None

    def resolve_ned(self):
        """Güncel hedefi shared-NED (north, east) konumuna çözer."""
        if not self.ready:
            return None
        lat, lon = self._target
        north, east = latlon_to_ned(
            lat, lon, self._origin[0], self._origin[1],
        )
        return (north, east)
