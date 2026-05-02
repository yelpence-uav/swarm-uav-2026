import L from "leaflet";

interface IconOptions {
  color: string;
  yawDeg: number;
  offline: boolean;
  label: string;
}

export function droneIcon({ color, yawDeg, offline, label }: IconOptions): L.DivIcon {
  const fill = offline ? "#888" : color;
  const opacity = offline ? 0.5 : 1;

  const html = `
    <div class="drone-marker" style="opacity: ${opacity};">
      <div class="drone-marker__rot" style="transform: rotate(${yawDeg}deg);">
        <svg viewBox="0 0 32 32" width="32" height="32">
          <polygon points="16,2 28,28 16,22 4,28" fill="${fill}" stroke="#000" stroke-width="1.5" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="drone-marker__label">${label}</div>
    </div>
  `;

  return L.divIcon({
    className: "drone-marker-wrapper",
    html,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
  });
}
