import L from "leaflet";

interface IconOptions {
  color: string;
  yawDeg: number;
  offline: boolean;
  label: string;
}

export function droneIcon({ color, yawDeg, offline, label }: IconOptions): L.DivIcon {
  const fill = offline ? "#5b6677" : color;
  const opacity = offline ? 0.55 : 1;
  const glow = offline ? "transparent" : color;

  const html = `
    <div class="drone-marker" style="opacity: ${opacity};">
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
      <div class="drone-marker__label" style="border-color: ${color};">${label}</div>
    </div>
  `;

  return L.divIcon({
    className: "drone-marker-wrapper",
    html,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  });
}
