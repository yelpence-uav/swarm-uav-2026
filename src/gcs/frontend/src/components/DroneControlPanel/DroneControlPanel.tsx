import type { FlightParams } from "../../services/api";
import type { DroneState } from "../../types/telemetry";
import { CommandButtons } from "../CommandButtons/CommandButtons";
import "./DroneControlPanel.css";

interface DroneControlPanelProps {
  drone: DroneState | undefined;
  guidedMode: boolean;
  commandsDisabled: boolean;
  params: FlightParams;
  onClose: () => void;
}

const ACCENT: Record<number, string> = {
  1: "var(--color-drone-1)",
  2: "var(--color-drone-2)",
  3: "var(--color-drone-3)",
};

export function DroneControlPanel({
  drone,
  guidedMode,
  commandsDisabled,
  params,
  onClose,
}: DroneControlPanelProps) {
  if (!drone) return null;
  const accent = ACCENT[drone.drone_id] ?? "var(--color-accent)";

  return (
    <section
      className="ctrl-panel"
      style={{ "--accent": accent } as React.CSSProperties}
    >
      <header className="ctrl-panel__head">
        <span className="ctrl-panel__dot" />
        <h2 className="ctrl-panel__title">{drone.name} — Kontrol</h2>
        <button className="ctrl-panel__close" onClick={onClose} aria-label="Kapat">
          ✕
        </button>
      </header>

      {!drone.connected && (
        <div className="ctrl-panel__warn">Drone bağlı değil — komutlar beklemede.</div>
      )}

      <CommandButtons
        droneId={drone.drone_id}
        connected={drone.connected}
        disabled={commandsDisabled}
        guidedMode={guidedMode}
        params={params}
      />
    </section>
  );
}
