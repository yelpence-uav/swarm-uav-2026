import "./BatteryGauge.css";

interface BatteryGaugeProps {
  percent: number;
  voltage: number;
}

export function BatteryGauge({ percent, voltage }: BatteryGaugeProps) {
  const clamped = Math.max(0, Math.min(100, percent));
  const level = clamped < 20 ? "crit" : clamped < 50 ? "warn" : "ok";

  return (
    <div className="battery-gauge">
      <div className="battery-gauge__head">
        <span className={`battery-gauge__pct battery-gauge__pct--${level}`}>
          %{clamped.toFixed(0)}
        </span>
        <span className="battery-gauge__voltage">{voltage.toFixed(1)} V</span>
      </div>
      <div className="battery-gauge__bar">
        <div
          className={`battery-gauge__fill battery-gauge__fill--${level}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
