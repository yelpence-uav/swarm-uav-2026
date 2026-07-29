import type { DroneState } from "../../types/telemetry";
import { DroneCard } from "./DroneCard";
import "./TelemetryPanel.css";

interface TelemetryPanelProps {
  drones: DroneState[];
  /** Seçili drone (kontrol paneli açık olan). */
  selectedDroneId?: number | null;
  /** Kart "Kontrol" butonu — seçili drone'u değiştirir. */
  onSelectDrone?: (droneId: number) => void;
}

export function TelemetryPanel({
  drones,
  selectedDroneId = null,
  onSelectDrone,
}: TelemetryPanelProps) {
  return (
    <aside className="telemetry-panel">
      {drones.map((d) => (
        <DroneCard
          key={d.drone_id}
          drone={d}
          onSelect={onSelectDrone}
          selected={d.drone_id === selectedDroneId}
        />
      ))}
      {drones.length === 0 && (
        <div className="telemetry-panel__empty">Drone bekleniyor…</div>
      )}
    </aside>
  );
}
