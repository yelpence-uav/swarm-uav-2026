import L from "leaflet";

interface IconOptions {
  color: string;
  yawDeg: number;
  offline: boolean;
  label: string;
  isLeader?: boolean;
}

export function droneIcon({ color, yawDeg, offline, label, isLeader = false }: IconOptions): L.DivIcon {
  const fill = offline ? "#5b6677" : color;
  const opacity = offline ? 0.55 : 1;
  const glow = offline ? "transparent" : color;

  // Lider drone'u marker etrafında nabız atan halka ile vurgula.
  // Çevrimdışı liderde halka gösterilmez.
  const leaderRing =
    isLeader && !offline
      ? `<circle class="drone-marker__leader-ring" cx="20" cy="20" r="18"
                 fill="none" stroke="${color}" stroke-width="2" opacity="0.9"/>`
      : "";

  const html = `
    <div class="drone-marker ${isLeader ? "drone-marker--leader" : ""}" style="opacity: ${opacity};">
      <svg class="drone-marker__ring-layer" viewBox="0 0 40 40" width="40" height="40">
        ${leaderRing}
      </svg>
      <div class="drone-marker__rot" style="transform: rotate(${yawDeg}deg); filter: drop-shadow(0 0 6px ${glow}) drop-shadow(0 2px 4px rgba(0,0,0,0.6));">
        <svg viewBox="0 0 40 40" width="40" height="40">
          <polygon points="20,3 35,36 20,27 5,36"
                   fill="${fill}"
                   stroke="rgba(0,0,0,0.65)"
                   stroke-width="1.5"
                   stroke-linejoin="round"/>
          <circle cx="20" cy="20" r="3" fill="white" opacity="0.85"/>
        </svg>
      </div>
      <div class="drone-marker__label" style="border-color: ${color};">${
        isLeader ? "★ " : ""
      }${label}</div>
    </div>
  `;

  return L.divIcon({
    className: "drone-marker-wrapper",
    html,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  });
}
