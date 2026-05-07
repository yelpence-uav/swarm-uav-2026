import { useEffect, useRef } from "react";
import L from "leaflet";

import type { DroneState } from "../../types/telemetry";
import { droneIcon } from "./droneIcon";
import "./Map.css";

const ISTANBUL: L.LatLngTuple = [41.0441, 29.0017];
const DEFAULT_ZOOM = 18;

const COLORS: Record<number, string> = {
  1: "#2196F3",
  2: "#4CAF50",
  3: "#FF9800",
};

interface DroneMarker {
  marker: L.Marker;
  lastLat: number;
  lastLon: number;
}

export interface MapProps {
  snapshot: DroneState[];
}

export function MapView({ snapshot }: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<Map<number, DroneMarker>>(new Map());
  const fittedRef = useRef(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: ISTANBUL,
      zoom: DEFAULT_ZOOM,
      zoomControl: true,
    });

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 22,
      attribution: "&copy; OpenStreetMap",
    }).addTo(map);

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      markersRef.current.clear();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    for (const drone of snapshot) {
      updateMarker(map, markersRef.current, drone);
    }

    if (!fittedRef.current) {
      const valid = snapshot.filter(hasValidPosition);
      if (valid.length > 0) {
        const bounds = L.latLngBounds(valid.map((d) => [d.lat, d.lon] as L.LatLngTuple));
        map.fitBounds(bounds.pad(0.5), { maxZoom: DEFAULT_ZOOM });
        fittedRef.current = true;
      }
    }
  }, [snapshot]);

  return <div ref={containerRef} className="map-container" />;
}

function hasValidPosition(d: DroneState): boolean {
  return d.lat !== 0 || d.lon !== 0;
}

function updateMarker(
  map: L.Map,
  markers: Map<number, DroneMarker>,
  drone: DroneState,
): void {
  if (!hasValidPosition(drone)) return;

  const color = COLORS[drone.drone_id] ?? "#999";
  const existing = markers.get(drone.drone_id);

  if (!existing) {
    const marker = L.marker([drone.lat, drone.lon], {
      icon: droneIcon({
        color,
        yawDeg: drone.yaw_deg,
        offline: !drone.connected,
        label: String(drone.drone_id),
      }),
      title: drone.name,
    }).addTo(map);

    marker.bindPopup(buildPopup(drone));
    markers.set(drone.drone_id, {
      marker,
      lastLat: drone.lat,
      lastLon: drone.lon,
    });
    return;
  }

  if (existing.lastLat !== drone.lat || existing.lastLon !== drone.lon) {
    existing.marker.setLatLng([drone.lat, drone.lon]);
    existing.lastLat = drone.lat;
    existing.lastLon = drone.lon;
  }

  existing.marker.setIcon(
    droneIcon({
      color,
      yawDeg: drone.yaw_deg,
      offline: !drone.connected,
      label: String(drone.drone_id),
    }),
  );

  if (existing.marker.isPopupOpen()) {
    existing.marker.setPopupContent(buildPopup(drone));
  } else {
    existing.marker.setPopupContent(buildPopup(drone));
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
