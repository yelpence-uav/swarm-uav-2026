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
        <svg viewBox="0 0 40 40" width="40" height="40">
          <polygon points="20,3 35,36 20,27 5,36" fill="${fill}" stroke="#000" stroke-width="2" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="drone-marker__label">${label}</div>
    </div>
  `;

  return L.divIcon({
    className: "drone-marker-wrapper",
    html,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  });
}
