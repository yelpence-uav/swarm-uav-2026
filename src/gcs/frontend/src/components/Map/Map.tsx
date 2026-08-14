import { useEffect, useRef, useState } from "react";
import L from "leaflet";

import type { QRPosition } from "../../hooks/useQRPositions";
import { isQRPositionSet } from "../../hooks/useQRPositions";
import type { FlightParams, GotoTarget } from "../../services/api";
import { PIL_GOSTER } from "../../services/gorunum";
import type { DroneState } from "../../types/telemetry";
import { droneIcon } from "./droneIcon";
import { qrIcon } from "./qrIcon";
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
  qrPositions?: QRPosition[];
  activeQrId?: number; // swarm_state.current_qr_id — aktif QR'ı vurgula
  /** true iken haritaya tıklayınca QGC tarzı "buraya git" onay çubuğu açılır. */
  guidedEnabled?: boolean;
  /** Nokta-git komutu — Map, tıklanan lat/lon + irtifa + hızı buradan gönderir. */
  onGoto?: (droneId: number, target: GotoTarget) => Promise<unknown>;
  /** Uçuş parametreleri — pop-up'ta irtifa/hız varsayılanları buradan gelir. */
  params?: FlightParams;
}

export function MapView({
  snapshot,
  qrPositions = [],
  activeQrId = 0,
  guidedEnabled = false,
  onGoto,
  params,
}: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const visualsRef = useRef<Map<number, DroneVisuals>>(new Map());
  const qrMarkersRef = useRef<Map<number, L.Marker>>(new Map());
  const formationLineRef = useRef<L.Polyline | null>(null);
  const followRef = useRef<boolean>(true);
  const [followUI, setFollowUI] = useState<boolean>(true);

  // --- QGC tarzı tıkla-git (guided) ---
  const pendingMarkerRef = useRef<L.Marker | null>(null);
  const pendingLineRef = useRef<L.Polyline | null>(null);
  // Leaflet click callback'i son props/state'i görsün diye ref üzerinden çağrılır.
  const clickHandlerRef = useRef<((e: L.LeafletMouseEvent) => void) | null>(null);
  const [pending, setPending] = useState<{ lat: number; lon: number } | null>(null);
  const [gotoDrone, setGotoDrone] = useState<number | null>(null);
  const [gotoAlt, setGotoAlt] = useState("5");
  const [gotoSending, setGotoSending] = useState(false);
  const [gotoError, setGotoError] = useState<string | null>(null);

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

    // Haritaya tıklama → guided nokta-git (son props için ref üzerinden).
    map.on("click", (e: L.LeafletMouseEvent) => clickHandlerRef.current?.(e));

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

  // QR nokta işaretçileri — operatörün girdiği sabit konumlar. qrPositions
  // veya aktif QR değişince güncellenir. Sadece lat/lon girilmiş olanlar çizilir.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const markers = qrMarkersRef.current;
    const seen = new Set<number>();

    for (const qr of qrPositions) {
      if (!isQRPositionSet(qr)) continue;
      seen.add(qr.qr_id);
      const pos: L.LatLngTuple = [qr.lat, qr.lon];
      const active = qr.qr_id === activeQrId;
      const existing = markers.get(qr.qr_id);
      if (!existing) {
        const marker = L.marker(pos, {
          icon: qrIcon({ qrId: qr.qr_id, active }),
          title: `QR ${qr.qr_id}`,
          interactive: true,
          zIndexOffset: -100, // drone marker'larının altında kalsın
        }).addTo(map);
        marker.bindPopup(
          `<b>QR ${qr.qr_id}</b><br>${qr.lat.toFixed(6)}, ${qr.lon.toFixed(6)}`,
        );
        markers.set(qr.qr_id, marker);
      } else {
        existing.setLatLng(pos);
        existing.setIcon(qrIcon({ qrId: qr.qr_id, active }));
        existing.setPopupContent(
          `<b>QR ${qr.qr_id}</b><br>${qr.lat.toFixed(6)}, ${qr.lon.toFixed(6)}`,
        );
      }
    }

    // Silinen / koordinatı sıfırlanan QR'ların marker'ını kaldır
    for (const [id, marker] of markers) {
      if (!seen.has(id)) {
        map.removeLayer(marker);
        markers.delete(id);
      }
    }

    // Kurulum aşaması: henüz uçan drone yokken haritayı QR noktalarına
    // odakla ki operatör girdiği konumu görsün. Drone gelince snapshot
    // effect'i devralır (o zaman bu blok atlanır).
    const hasDrones = snapshot.some((d) => d.lat !== 0 || d.lon !== 0);
    if (followRef.current && !hasDrones && markers.size > 0) {
      const pts = [...markers.values()].map((m) => m.getLatLng());
      if (pts.length === 1) {
        map.setView(pts[0], Math.max(map.getZoom(), MIN_FOLLOW_ZOOM));
      } else {
        map.fitBounds(L.latLngBounds(pts).pad(0.4), { maxZoom: DEFAULT_ZOOM });
      }
    }
  }, [qrPositions, activeQrId, snapshot]);

  // Bekleyen hedef değişince: geçici işaret + drone'dan noktaya çizgi çiz/güncelle.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (!pending) {
      if (pendingMarkerRef.current) {
        map.removeLayer(pendingMarkerRef.current);
        pendingMarkerRef.current = null;
      }
      if (pendingLineRef.current) {
        map.removeLayer(pendingLineRef.current);
        pendingLineRef.current = null;
      }
      return;
    }

    const tgt: L.LatLngTuple = [pending.lat, pending.lon];
    if (!pendingMarkerRef.current) {
      pendingMarkerRef.current = L.marker(tgt, {
        icon: gotoTargetIcon(),
        interactive: false,
        zIndexOffset: 1000,
      }).addTo(map);
    } else {
      pendingMarkerRef.current.setLatLng(tgt);
    }

    const d = snapshot.find(
      (x) => x.drone_id === gotoDrone && hasValidPosition(x),
    );
    const pts: L.LatLngTuple[] = d ? [[d.lat, d.lon], tgt] : [tgt, tgt];
    if (!pendingLineRef.current) {
      pendingLineRef.current = L.polyline(pts, {
        color: "#22d3ee",
        weight: 2,
        opacity: 0.9,
        dashArray: "6, 6",
        interactive: false,
      }).addTo(map);
    } else {
      pendingLineRef.current.setLatLngs(pts);
    }
  }, [pending, gotoDrone, snapshot]);

  const connectedDrones = snapshot.filter((d) => d.connected);

  // Her render'da güncellenir → Leaflet click callback'i güncel değerleri görür.
  clickHandlerRef.current = (e) => {
    if (!guidedEnabled || !onGoto || connectedDrones.length === 0) return;
    // Hedef koyarken auto-follow'u durdur (harita kaçmasın).
    followRef.current = false;
    setFollowUI(false);
    const chosen =
      gotoDrone != null && connectedDrones.some((d) => d.drone_id === gotoDrone)
        ? gotoDrone
        : connectedDrones[0].drone_id;
    setGotoDrone(chosen);
    // Varsayılan irtifa = Ayarlar parametresi (operatör pop-up'ta değiştirebilir).
    // Hız YKİ'den ayarlanmıyor; drone MPC_XY_VEL_MAX (QGC) ile sınırlı.
    setGotoAlt(String(params?.default_altitude_m ?? 5));
    setGotoError(null);
    setPending({ lat: e.latlng.lat, lon: e.latlng.lng });
  };

  const sendGoto = async () => {
    if (!pending || gotoDrone == null || !onGoto) return;
    const alt = parseFloat(gotoAlt);
    if (Number.isNaN(alt) || alt <= 0) {
      setGotoError("İrtifa > 0 olmalı");
      return;
    }
    setGotoSending(true);
    setGotoError(null);
    try {
      const target: GotoTarget = { lat: pending.lat, lon: pending.lon, alt };
      await onGoto(gotoDrone, target);
      setPending(null);
    } catch (err) {
      setGotoError(err instanceof Error ? err.message : "Komut gönderilemedi");
    } finally {
      setGotoSending(false);
    }
  };

  const cancelGoto = () => {
    setPending(null);
    setGotoError(null);
  };

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

      {pending && (
        <div className="map-goto-bar" role="dialog">
          <div className="map-goto-bar__title">🎯 Buraya git</div>
          <div className="map-goto-bar__coords">
            {pending.lat.toFixed(6)}, {pending.lon.toFixed(6)}
          </div>
          <label className="map-goto-bar__field">
            İrtifa
            <input
              value={gotoAlt}
              onChange={(e) => setGotoAlt(e.target.value)}
              inputMode="decimal"
            />
            m
          </label>
          <div className="map-goto-bar__hint">
            Hız: MPC_XY_VEL_MAX (QGC'den)
          </div>
          {connectedDrones.length > 1 && (
            <label className="map-goto-bar__field">
              Drone
              <select
                value={gotoDrone ?? ""}
                onChange={(e) => setGotoDrone(Number(e.target.value))}
              >
                {connectedDrones.map((d) => (
                  <option key={d.drone_id} value={d.drone_id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button
            type="button"
            className="map-goto-bar__go"
            onClick={sendGoto}
            disabled={gotoSending}
          >
            {gotoSending ? "…" : "Git"}
          </button>
          <button
            type="button"
            className="map-goto-bar__cancel"
            onClick={cancelGoto}
            disabled={gotoSending}
          >
            İptal
          </button>
          {gotoError && <div className="map-goto-bar__error">{gotoError}</div>}
        </div>
      )}
    </div>
  );
}

function gotoTargetIcon(): L.DivIcon {
  return L.divIcon({
    className: "goto-target-wrapper",
    html:
      '<div class="goto-target">' +
      '<svg viewBox="0 0 24 24" width="30" height="30">' +
      '<circle cx="12" cy="12" r="8" fill="none" stroke="#22d3ee" stroke-width="2"/>' +
      '<circle cx="12" cy="12" r="2" fill="#22d3ee"/>' +
      '<line x1="12" y1="1" x2="12" y2="6" stroke="#22d3ee" stroke-width="2"/>' +
      '<line x1="12" y1="18" x2="12" y2="23" stroke="#22d3ee" stroke-width="2"/>' +
      '<line x1="1" y1="12" x2="6" y2="12" stroke="#22d3ee" stroke-width="2"/>' +
      '<line x1="18" y1="12" x2="23" y2="12" stroke="#22d3ee" stroke-width="2"/>' +
      "</svg></div>",
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
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
  const isLeader = drone.role === 1; // AgentStatus.ROLE_LEADER
  const existing = visuals.get(drone.drone_id);
  const newPos: L.LatLngTuple = [drone.lat, drone.lon];

  if (!existing) {
    const marker = L.marker(newPos, {
      icon: droneIcon({
        color,
        yawDeg: drone.yaw_deg,
        offline: !drone.connected,
        label: String(drone.drone_id),
        isLeader,
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
      isLeader,
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
      ${PIL_GOSTER ? `<div>bat: %${d.battery_percent.toFixed(0)} (${d.battery_voltage.toFixed(1)} V)</div>` : ""}
      <div>gps: fix=${d.gps_fix_type} sat=${d.gps_satellites}</div>
      <div>${d.lat.toFixed(5)}, ${d.lon.toFixed(5)}</div>
    </div>
  `;
}
