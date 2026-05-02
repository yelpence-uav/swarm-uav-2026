import type { ConnectionStatus } from "../../services/websocket";
import type { TelemetrySnapshot } from "../../types/telemetry";
import "./StatusBar.css";

interface StatusBarProps {
  status: ConnectionStatus;
  snapshot: TelemetrySnapshot;
}

const STATUS_LABEL: Record<ConnectionStatus, string> = {
  connecting: "BAĞLANIYOR",
  open: "BAĞLI",
  closed: "KOPUK",
};

export function StatusBar({ status, snapshot }: StatusBarProps) {
  const online = snapshot.filter((d) => d.connected).length;
  const total = snapshot.length;

  return (
    <header className="status-bar">
      <div className="status-bar__brand">YELPENCE GCS</div>
      <div className={`status-bar__pill status-bar__pill--${status}`}>
        WS: {STATUS_LABEL[status]}
      </div>
      <div className="status-bar__drones">
        {snapshot.map((d) => (
          <span
            key={d.drone_id}
            className={`status-bar__drone ${d.connected ? "online" : "offline"}`}
            title={`${d.name} — ${d.connected ? d.mode : "OFFLINE"}`}
          >
            {d.name}: {d.connected ? d.mode : "OFFLINE"}
          </span>
        ))}
      </div>
      <div className="status-bar__count">
        {online}/{total} online
      </div>
    </header>
  );
}
