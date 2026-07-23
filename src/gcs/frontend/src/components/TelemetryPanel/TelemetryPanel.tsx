import type { DroneState } from "../../types/telemetry";
import { DroneCard } from "./DroneCard";
import "./TelemetryPanel.css";

interface TelemetryPanelProps {
  drones: DroneState[];
  /** Görev aktif iken kart üzerindeki bireysel komut butonları yasak. */
  commandsDisabled?: boolean;
  /** Komut butonlarını göster (ros2 guided veya mavlink-sim). */
  showCommands?: boolean;
  /** true: ESP mesh guided komutları (ros2). false: mavlink-sim. */
  guidedMode?: boolean;
}

export function TelemetryPanel({
  drones,
  commandsDisabled = false,
  showCommands = false,
  guidedMode = false,
}: TelemetryPanelProps) {
  return (
    <aside className="telemetry-panel">
      {drones.map((d) => (
        <DroneCard
          key={d.drone_id}
          drone={d}
          commandsDisabled={commandsDisabled}
          showCommands={showCommands}
          guidedMode={guidedMode}
        />
      ))}
      {drones.length === 0 && (
        <div className="telemetry-panel__empty">Drone bekleniyor…</div>
      )}
    </aside>
  );
}
