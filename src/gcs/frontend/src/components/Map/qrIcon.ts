import L from "leaflet";

interface QRIconOptions {
  qrId: number;
  active?: boolean; // swarm o an bu QR'ı icra ediyorsa vurgula
}

/**
 * QR nokta işaretçisi - haritada sabit QR konumlarını gösterir (şartname
 * V2: QR kodları sabit konumlarda, 150×150cm). Aktif QR (mission_fsm'in
 * icra ettiği) nabız atan halka ile vurgulanır.
 */
export function qrIcon({ qrId, active = false }: QRIconOptions): L.DivIcon {
  const color = active ? "#22c55e" : "#eab308"; // aktif yeşil, pasif amber
  const ring = active
    ? `<circle class="qr-marker__ring" cx="18" cy="18" r="16"
               fill="none" stroke="${color}" stroke-width="2" opacity="0.9"/>`
    : "";

  const html = `
    <div class="qr-marker ${active ? "qr-marker--active" : ""}">
      <svg viewBox="0 0 36 36" width="36" height="36">
        ${ring}
        <rect x="6" y="6" width="24" height="24" rx="3"
              fill="rgba(10,14,20,0.85)" stroke="${color}" stroke-width="2"/>
        <!-- basit QR göz deseni -->
        <rect x="10" y="10" width="6" height="6" fill="${color}"/>
        <rect x="20" y="10" width="6" height="6" fill="${color}"/>
        <rect x="10" y="20" width="6" height="6" fill="${color}"/>
        <rect x="21" y="21" width="4" height="4" fill="${color}"/>
      </svg>
      <div class="qr-marker__label" style="border-color: ${color}; color: ${color};">
        QR${qrId}
      </div>
    </div>
  `;

  return L.divIcon({
    className: "qr-marker-wrapper",
    html,
    iconSize: [36, 36],
    iconAnchor: [18, 18],
  });
}
