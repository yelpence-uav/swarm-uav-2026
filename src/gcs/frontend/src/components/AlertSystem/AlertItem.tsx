import type { Alert } from "../../types/telemetry";

interface AlertItemProps {
  alert: Alert;
  onDismiss: (key: string) => void;
}

const SEVERITY_LABEL: Record<Alert["severity"], string> = {
  critical: "KRİTİK",
  warning: "UYARI",
  info: "BİLGİ",
};

export function AlertItem({ alert, onDismiss }: AlertItemProps) {
  const key = `${alert.drone_id}:${alert.code}`;
  const ageSec = Math.max(0, (Date.now() / 1000) - alert.timestamp);

  return (
    <li className={`alert-item alert-item--${alert.severity}`}>
      <div className="alert-item__head">
        <span className="alert-item__severity">{SEVERITY_LABEL[alert.severity]}</span>
        <span className="alert-item__drone">Drone {alert.drone_id}</span>
        <span className="alert-item__age">{formatAge(ageSec)}</span>
        <button
          className="alert-item__close"
          aria-label="Kapat"
          onClick={() => onDismiss(key)}
        >
          ×
        </button>
      </div>
      <div className="alert-item__msg">{alert.message}</div>
    </li>
  );
}

function formatAge(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(0)}d`;
  return `${(seconds / 3600).toFixed(0)}sa`;
}
