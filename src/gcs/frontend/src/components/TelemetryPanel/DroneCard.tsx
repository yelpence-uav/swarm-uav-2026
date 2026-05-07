import type { DroneState } from "../../types/telemetry";
import { BatteryGauge } from "./BatteryGauge";
import "./DroneCard.css";

const COLORS: Record<number, string> = {
  1: "#2196F3",
  2: "#4CAF50",
  3: "#FF9800",
};

const GPS_LABEL: Record<number, string> = {
  0: "yok",
  1: "yok",
  2: "2D",
  3: "3D",
  4: "DGPS",
  5: "RTK-Float",
  6: "RTK-Fix",
};

interface DroneCardProps {
  drone: DroneState;
}

export function DroneCard({ drone }: DroneCardProps) {
  const color = COLORS[drone.drone_id] ?? "#999";

  if (!drone.connected) {
    return (
      <article className="drone-card drone-card--offline">
        <header className="drone-card__head">
          <span className="drone-card__dot" style={{ background: "#666" }} />
          <h3 className="drone-card__title">{drone.name}</h3>
          <span className="drone-card__badge drone-card__badge--offline">OFFLINE</span>
        </header>
        <p className="drone-card__offline-msg">Son paket gelmiyor</p>
      </article>
    );
  }

  const armed = drone.armed;
  const gpsLabel = GPS_LABEL[drone.gps_fix_type] ?? "?";

  return (
    <article className="drone-card">
      <header className="drone-card__head">
        <span className="drone-card__dot" style={{ background: color }} />
        <h3 className="drone-card__title">{drone.name}</h3>
        <span
          className={`drone-card__badge drone-card__badge--${armed ? "armed" : "ground"}`}
        >
          {armed ? "ARMED" : "yerde"}
        </span>
      </header>

      <div className="drone-card__mode">{drone.mode}</div>

      <BatteryGauge
        percent={drone.battery_percent}
        voltage={drone.battery_voltage}
      />

      <dl className="drone-card__stats">
        <div>
          <dt>alt</dt>
          <dd>{drone.alt_m.toFixed(1)} m</dd>
        </div>
        <div>
          <dt>hız</dt>
          <dd>{drone.groundspeed_mps.toFixed(1)} m/s</dd>
        </div>
        <div>
          <dt>yaw</dt>
          <dd>{drone.yaw_deg.toFixed(0)}°</dd>
        </div>
        <div>
          <dt>gps</dt>
          <dd>
            {gpsLabel} ({drone.gps_satellites})
          </dd>
        </div>
      </dl>

      <footer className="drone-card__footer">
        {drone.lat.toFixed(5)}, {drone.lon.toFixed(5)}
      </footer>
    </article>
  );
}
