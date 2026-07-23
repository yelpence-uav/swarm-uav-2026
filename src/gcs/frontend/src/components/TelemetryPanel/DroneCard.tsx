import type { DroneState } from "../../types/telemetry";
import { AGENT_STATE_LABELS } from "../../types/telemetry";
import { CommandButtons } from "../CommandButtons/CommandButtons";
import { BatteryGauge } from "./BatteryGauge";
import "./DroneCard.css";

const ACCENT_VARS: Record<number, string> = {
  1: "var(--color-drone-1)",
  2: "var(--color-drone-2)",
  3: "var(--color-drone-3)",
};

const GPS_LABEL: Record<number, string> = {
  0: "yok",
  1: "yok",
  2: "2D",
  3: "3D",
  4: "DGPS",
  5: "RTK-F",
  6: "RTK-Fix",
};

interface DroneCardProps {
  drone: DroneState;
  commandsDisabled?: boolean;
  showCommands?: boolean;
  guidedMode?: boolean;
}

export function DroneCard({
  drone,
  commandsDisabled = false,
  showCommands = false,
  guidedMode = false,
}: DroneCardProps) {
  const accent = ACCENT_VARS[drone.drone_id] ?? "var(--color-accent)";
  const stateLabel = AGENT_STATE_LABELS[drone.state] ?? drone.mode;

  if (!drone.connected) {
    return (
      <article
        className="drone-card drone-card--offline"
        style={{ "--accent": accent } as React.CSSProperties}
      >
        <header className="drone-card__head">
          <span className="drone-card__dot" />
          <h3 className="drone-card__title">{drone.name}</h3>
          <span className="drone-card__badge drone-card__badge--offline">OFFLINE</span>
        </header>
        <div className="drone-card__offline-body">
          <span className="drone-card__offline-icon">⚠</span>
          <span className="drone-card__offline-text">Son paket gelmiyor</span>
        </div>
        {showCommands && (
          <CommandButtons
            droneId={drone.drone_id}
            connected={false}
            disabled={commandsDisabled}
            guidedMode={guidedMode}
          />
        )}
      </article>
    );
  }

  const armed = drone.armed;
  const gpsLabel = GPS_LABEL[drone.gps_fix_type] ?? "?";

  // Operatorun sordugu tek soru "su an ucabilir mi". Kill switch'i, on-kontrolu
  // (PREARM_CHECK / emniyet anahtari) ve kumanda baglantisini AYRI isaretler
  // olarak gostermiyoruz — hepsi tek bir "ucamaz" sebebi; hangisi olursa olsun
  // cevap ayni. Sebep kirilimi gerekince telemetriden bakilir, kartta yer tutmaz.
  const canFly = drone.ready_to_arm && !drone.kill_switch_active && drone.rc_link_ok;

  return (
    <article
      className="drone-card"
      style={{ "--accent": accent } as React.CSSProperties}
    >
      <header className="drone-card__head">
        <span className="drone-card__dot drone-card__dot--live" />
        <h3 className="drone-card__title">{drone.name}</h3>
        <span
          className={`drone-card__badge drone-card__badge--${armed ? "armed" : "ground"}`}
        >
          {armed ? "ARMED" : "YERDE"}
        </span>
      </header>

      {/* Ucus hazirligi: tek bakista ucabilir/ucamaz. Ucamazken nokta yanip
          soner ki gozden kacmasin. */}
      <div
        className={`drone-card__fly ${canFly ? "drone-card__fly--ok" : "drone-card__fly--no"}`}
      >
        <span className="drone-card__fly-dot" />
        {canFly ? "UÇABİLİR" : "UÇAMAZ"}
      </div>

      <div className="drone-card__state">
        <span className="drone-card__state-label">{stateLabel}</span>
      </div>

      <BatteryGauge
        percent={drone.battery_percent}
        voltage={drone.battery_voltage}
      />

      <dl className="drone-card__stats">
        <Stat label="ALT" value={`${drone.alt_m.toFixed(1)} m`} />
        <Stat label="HIZ" value={`${drone.groundspeed_mps.toFixed(1)} m/s`} />
        <Stat label="YAW" value={`${drone.yaw_deg.toFixed(0)}°`} />
        <Stat label="GPS" value={`${gpsLabel} · ${drone.gps_satellites}`} />
      </dl>

      <footer className="drone-card__footer mono">
        {drone.lat.toFixed(5)}, {drone.lon.toFixed(5)}
      </footer>

      {showCommands && (
        <CommandButtons
          droneId={drone.drone_id}
          connected={true}
          disabled={commandsDisabled}
          guidedMode={guidedMode}
        />
      )}
    </article>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="drone-card__stat">
      <dt>{label}</dt>
      <dd className="mono">{value}</dd>
    </div>
  );
}
