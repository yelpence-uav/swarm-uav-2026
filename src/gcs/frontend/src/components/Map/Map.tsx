import { useEffect, useRef, useState } from "react";
import L from "leaflet";

import type { DroneState } from "../../types/telemetry";
import { droneIcon } from "./droneIcon";
import "./Map.css";

// PX4 SITL default home (Zürich Hönggerberg) — test publisher burayı kullanıyor.
// Saha'da ilk gerçek pozisyon gelince auto-fit zaten doğru yere alır.
const ZURICH: L.LatLngTuple = [47.397742, 8.545594];
const DEFAULT_ZOOM = 19;
const MIN_FOLLOW_ZOOM = 18;        // auto-follow bu zoom'un altına inmesin
const TRAIL_MAX_POINTS = 80;       // drone başına iz çizgisi uzunluğu

// DroneCard'taki --color-drone-* ile eşleşmeli (cyan/violet/orange tematik aksent).
const COLORS: Record<number, string> = {
  1: "#38bdf8",  // cyan — Drone 1
  2: "#a78bfa",  // violet — Drone 2
  3: "#fb923c",  // orange — Drone 3
};

interface DroneVisuals {
  marker: L.Marker;
  trail: L.Polyline;
  trailPoints: L.LatLngTuple[];
  lastLat: number;
  lastLon: number;
}

export interface MapProps {
  snapshot: DroneState[];
}

export function MapView({ snapshot }: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const visualsRef = useRef<Map<number, DroneVisuals>>(new Map());
  const formationLineRef = useRef<L.Polyline | null>(null);
  const followRef = useRef<boolean>(true);
  const [followUI, setFollowUI] = useState<boolean>(true);

  // Map ilk kurulum
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: ZURICH,
      zoom: DEFAULT_ZOOM,
      zoomControl: true,
    });

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 22,
      attribution: "&copy; OpenStreetMap",
    }).addTo(map);

    // Kullanıcı haritayı manuel sürüklerse auto-follow'u devre dışı bırak.
    map.on("dragstart", () => {
      followRef.current = false;
      setFollowUI(false);
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      visualsRef.current.clear();
    };
  }, []);

  // Snapshot her güncellendiğinde marker + trail + formation güncelle
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const validDrones = snapshot.filter(hasValidPosition);

    // Marker + trail güncelle
    for (const drone of snapshot) {
      updateDroneVisuals(map, visualsRef.current, drone);
    }

    // Formation çizgisi — 2+ drone varsa aralarına bağlantı
    updateFormationLine(map, formationLineRef, validDrones);

    // Auto-follow: drone'ların etrafına otomatik zoom
    if (followRef.current && validDrones.length > 0) {
      const points = validDrones.map(
        (d) => [d.lat, d.lon] as L.LatLngTuple,
      );
      if (validDrones.length === 1) {
        map.setView(points[0], Math.max(map.getZoom(), MIN_FOLLOW_ZOOM));
      } else {
        const bounds = L.latLngBounds(points);
        map.fitBounds(bounds.pad(0.4), {
          maxZoom: DEFAULT_ZOOM,
          animate: true,
          duration: 0.5,
        });
      }
    }
  }, [snapshot]);

  const toggleFollow = () => {
    const next = !followRef.current;
    followRef.current = next;
    setFollowUI(next);
  };

  return (
    <div className="map-wrapper">
      <div ref={containerRef} className="map-container" />
      <button
        className={
          "map-follow-toggle " +
          (followUI ? "map-follow-toggle--on" : "map-follow-toggle--off")
        }
        onClick={toggleFollow}
        title={followUI ? "Otomatik takip açık" : "Otomatik takip kapalı"}
      >
        {followUI ? "📍 Takip AÇIK" : "📍 Takip KAPALI"}
      </button>
    </div>
  );
}

function hasValidPosition(d: DroneState): boolean {
  return d.lat !== 0 || d.lon !== 0;
}

function updateDroneVisuals(
  map: L.Map,
  visuals: Map<number, DroneVisuals>,
  drone: DroneState,
): void {
  if (!hasValidPosition(drone)) return;

  const color = COLORS[drone.drone_id] ?? "#999";
  const existing = visuals.get(drone.drone_id);
  const newPos: L.LatLngTuple = [drone.lat, drone.lon];

  if (!existing) {
    const marker = L.marker(newPos, {
      icon: droneIcon({
        color,
        yawDeg: drone.yaw_deg,
        offline: !drone.connected,
        label: String(drone.drone_id),
      }),
      title: drone.name,
    }).addTo(map);
    marker.bindPopup(buildPopup(drone));

    const trail = L.polyline([newPos], {
      color,
      weight: 2.5,
      opacity: 0.65,
      dashArray: "4, 4",
    }).addTo(map);

    visuals.set(drone.drone_id, {
      marker,
      trail,
      trailPoints: [newPos],
      lastLat: drone.lat,
      lastLon: drone.lon,
    });
    return;
  }

  // Pozisyon değiştiyse marker + trail güncelle
  if (existing.lastLat !== drone.lat || existing.lastLon !== drone.lon) {
    existing.marker.setLatLng(newPos);
    existing.lastLat = drone.lat;
    existing.lastLon = drone.lon;

    existing.trailPoints.push(newPos);
    if (existing.trailPoints.length > TRAIL_MAX_POINTS) {
      existing.trailPoints.shift();
    }
    existing.trail.setLatLngs(existing.trailPoints);
  }

  existing.marker.setIcon(
    droneIcon({
      color,
      yawDeg: drone.yaw_deg,
      offline: !drone.connected,
      label: String(drone.drone_id),
    }),
  );

  existing.marker.setPopupContent(buildPopup(drone));
}

function updateFormationLine(
  map: L.Map,
  ref: React.MutableRefObject<L.Polyline | null>,
  drones: DroneState[],
): void {
  if (drones.length < 2) {
    if (ref.current) {
      map.removeLayer(ref.current);
      ref.current = null;
    }
    return;
  }

  // Drone ID sırasına göre bağla + ilk noktayı tekrar ekleyerek üçgen kapat
  const sorted = [...drones].sort((a, b) => a.drone_id - b.drone_id);
  const points: L.LatLngTuple[] = sorted.map((d) => [d.lat, d.lon]);
  if (points.length >= 3) {
    points.push(points[0]);  // kapalı çokgen
  }

  if (!ref.current) {
    ref.current = L.polyline(points, {
      color: "#a78bfa",
      weight: 2,
      opacity: 0.7,
      dashArray: "6, 6",
      interactive: false,
    }).addTo(map);
  } else {
    ref.current.setLatLngs(points);
  }
}

function buildPopup(d: DroneState): string {
  const status = d.connected ? (d.armed ? "ARMED" : "yerde") : "OFFLINE";
  return `
    <div style="font-family: ui-monospace, monospace; font-size: 12px;">
      <div style="font-weight: 600; margin-bottom: 4px;">${d.name}</div>
      <div>${status} — ${d.mode}</div>
      <div>alt: ${d.alt_m.toFixed(1)} m</div>
      <div>hız: ${d.groundspeed_mps.toFixed(1)} m/s</div>
      <div>yaw: ${d.yaw_deg.toFixed(1)}°</div>
      <div>bat: %${d.battery_percent.toFixed(0)} (${d.battery_voltage.toFixed(1)} V)</div>
      <div>gps: fix=${d.gps_fix_type} sat=${d.gps_satellites}</div>
      <div>${d.lat.toFixed(5)}, ${d.lon.toFixed(5)}</div>
    </div>
  `;
}
