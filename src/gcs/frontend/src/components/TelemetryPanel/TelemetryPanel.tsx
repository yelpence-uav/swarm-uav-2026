import type { DroneState } from "../../types/telemetry";
import { DroneCard } from "./DroneCard";
import "./TelemetryPanel.css";

interface TelemetryPanelProps {
  drones: DroneState[];
}

export function TelemetryPanel({ drones }: TelemetryPanelProps) {
  return (
    <aside className="telemetry-panel">
      {drones.map((d) => (
        <DroneCard key={d.drone_id} drone={d} />
      ))}
      {drones.length === 0 && (
        <div className="telemetry-panel__empty">Drone bekleniyor…</div>
      )}
    </aside>
  );
}
