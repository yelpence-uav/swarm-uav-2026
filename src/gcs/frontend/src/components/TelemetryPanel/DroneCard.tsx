import type { DroneState } from "../../types/telemetry";
import { AGENT_STATE_LABELS } from "../../types/telemetry";
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

// Fix tipine karşılık gelen tipik yatay doğruluk.
//
// NEDEN eph DEĞİL: Here4 DroneCAN üzerinden gelen kovaryansı RTK çözümünü
// yansıtacak şekilde güncellemiyor. Sahada ölçüldü (29 Temmuz): RTK-Fixed
// durumdayken GPS eph'i 66 cm bildiriyordu, oysa hareketsiz drone'un gerçek
// konum saçılımı 345 örnekte std 0.2 cm, tepe sapma 1.5 cm idi. eph'i
// göstermek operatörü 300 kat yanıltırdı.
//
// fix_type ise doğruluk SINIFININ kendisidir ve güvenilir — QGC ve Mission
// Planner da doğruluğu böyle raporlar. "~" işareti bunun ölçüm değil sınıf
// olduğunu belli ediyor.
const GPS_DOGRULUK: Record<number, string> = {
  2: "~10 m",
  3: "~2 m",
  4: "~1 m",
  5: "~30 cm",
  6: "~2 cm",
};

interface DroneCardProps {
  drone: DroneState;
  /** Kart sağ üstündeki tek buton — seçili drone kontrol panelini açar. */
  onSelect?: (droneId: number) => void;
  selected?: boolean;
}

/** Kart başlığı — sadece telemetri kartlarında ortak; tek aksiyon: Kontrol. */
function CardHead({
  drone,
  badge,
  onSelect,
  selected,
}: {
  drone: DroneState;
  badge: React.ReactNode;
  onSelect?: (id: number) => void;
  selected?: boolean;
}) {
  return (
    <header className="drone-card__head">
      <span
        className={`drone-card__dot ${drone.connected ? "drone-card__dot--live" : ""}`}
      />
      <h3 className="drone-card__title">{drone.name}</h3>
      {badge}
      {onSelect && (
        <button
          type="button"
          className={`drone-card__ctrl ${selected ? "drone-card__ctrl--active" : ""}`}
          onClick={() => onSelect(drone.drone_id)}
          title="Kontrol panelini aç (arm, kalkış, nokta-git…)"
        >
          ⚙ Kontrol
        </button>
      )}
    </header>
  );
}

export function DroneCard({ drone, onSelect, selected = false }: DroneCardProps) {
  const accent = ACCENT_VARS[drone.drone_id] ?? "var(--color-accent)";
  const stateLabel = AGENT_STATE_LABELS[drone.state] ?? drone.mode;

  if (!drone.connected) {
    return (
      <article
        className={`drone-card drone-card--offline ${selected ? "drone-card--selected" : ""}`}
        style={{ "--accent": accent } as React.CSSProperties}
      >
        <CardHead
          drone={drone}
          onSelect={onSelect}
          selected={selected}
          badge={
            <span className="drone-card__badge drone-card__badge--offline">OFFLINE</span>
          }
        />
        <div className="drone-card__offline-body">
          <span className="drone-card__offline-icon">⚠</span>
          <span className="drone-card__offline-text">Son paket gelmiyor</span>
        </div>
      </article>
    );
  }

  const armed = drone.armed;
  const gpsLabel = GPS_LABEL[drone.gps_fix_type] ?? "?";
  const gpsDogruluk = GPS_DOGRULUK[drone.gps_fix_type] ?? "";

  // Operatorun sordugu tek soru "su an ucabilir mi". Kill switch'i, on-kontrolu
  // ve kumanda baglantisini tek "ucamaz" sebebi olarak birlestiriyoruz.
  const canFly = drone.ready_to_arm && !drone.kill_switch_active && drone.rc_link_ok;

  return (
    <article
      className={`drone-card ${selected ? "drone-card--selected" : ""}`}
      style={{ "--accent": accent } as React.CSSProperties}
    >
      <CardHead
        drone={drone}
        onSelect={onSelect}
        selected={selected}
        badge={
          <span
            className={`drone-card__badge drone-card__badge--${armed ? "armed" : "ground"}`}
          >
            {armed ? "ARMED" : "YERDE"}
          </span>
        }
      />

      <div
        className={`drone-card__fly ${canFly ? "drone-card__fly--ok" : "drone-card__fly--no"}`}
      >
        <span className="drone-card__fly-dot" />
        {canFly ? "UÇABİLİR" : "UÇAMAZ"}
      </div>

      <div className="drone-card__state">
        <span className="drone-card__state-label">{stateLabel}</span>
      </div>

      <BatteryGauge percent={drone.battery_percent} voltage={drone.battery_voltage} />

      <dl className="drone-card__stats">
        <Stat label="ALT" value={`${drone.alt_m.toFixed(1)} m`} />
        <Stat label="HIZ" value={`${drone.groundspeed_mps.toFixed(1)} m/s`} />
        <Stat label="YAW" value={`${drone.yaw_deg.toFixed(0)}°`} />
        <Stat
          label="GPS"
          value={`${gpsLabel} · ${drone.gps_satellites}${
            gpsDogruluk ? ` · ${gpsDogruluk}` : ""
          }`}
        />
      </dl>

      <footer className="drone-card__footer mono">
        {drone.lat.toFixed(5)}, {drone.lon.toFixed(5)}
      </footer>
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
