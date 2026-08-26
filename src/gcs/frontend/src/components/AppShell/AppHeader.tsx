import type {DroneState, RtkStatus, SwarmState} from "../../types/telemetry";
import type { ConnectionStatus } from "../../services/websocket";
import { useTheme } from "../../hooks/useTheme";
import { MISSION_ID } from "../../services/api";
import "./AppHeader.css";

interface AppHeaderProps {
  status: ConnectionStatus;
  drones: DroneState[];
  swarmState: SwarmState | null;
  rtk: RtkStatus | null;
  selectedMissionId: number;
  onOpenSettings?: () => void;
}

const STATUS_LABEL: Record<ConnectionStatus, string> = {
  connecting: "Bağlanıyor",
  open: "Çevrimiçi",
  closed: "Çevrimdışı",
};

function missionTone(
  active: boolean,
): "success" | "warning" | "danger" | "neutral" {
  return active ? "success" : "neutral";
}

function missionLabel(
  active: boolean,
  selectedMissionId: number,
): string {
  if (active) {
    return selectedMissionId === MISSION_ID.SEMI_AUTONOMOUS ? "G2 AKTİF" : "G1 AKTİF";
  }
  return selectedMissionId === MISSION_ID.SEMI_AUTONOMOUS ? "G2 HAZIR" : "G1 HAZIR";
}

export function AppHeader({
  status,
  drones,
  swarmState,
  rtk,
  selectedMissionId,
  onOpenSettings,
}: AppHeaderProps) {
  const { theme, toggleTheme } = useTheme();

  const online = drones.filter((d) => d.connected).length;
  const total = drones.length;

  const allArmed = drones.length > 0 && drones.every((d) => d.armed);
  const anyArmed = drones.some((d) => d.armed);

  const missionActive = swarmState?.mission_active ?? false;

  // RTK/RTCM akisi. 31 Temmuz'da u-blox sonradan takildi, YKI acilista portu
  // goremeyip RTCM okuyucusunu hic baslatmamisti ve arayuzde bunu gosteren
  // hicbir sey yoktu — akmadigi ancak drone'a SSH atip px4_bridge logundaki
  // 'rtk: msg=0' sayacina bakinca anlasildi. Artik burada gorunuyor.
  const rtkLabel = rtk?.bagli ? `${rtk.msg_hz.toFixed(0)} Hz` : "YOK";
  const rtkTone: "success" | "danger" = rtk?.bagli ? "success" : "danger";

  return (
    <header className="app-header">
      <div className="app-header__brand">
        <div className="app-header__logo">
          <img
            src="/logo.png"
            alt="Yelpence"
            className="app-header__logo-img"
            draggable={false}
          />
        </div>
        <div className="app-header__title">
          <span className="app-header__title-main">YELPENCE</span>
          <span className="app-header__title-sub">Sürü Kontrol Merkezi</span>
        </div>
      </div>

      <div className="app-header__metrics">
        <Metric
          label="Sürü"
          value={`${online}/${total}`}
          tone={online === total ? "success" : online === 0 ? "danger" : "warning"}
        />
        <Metric
          label="Arm"
          value={allArmed ? "TÜMÜ" : anyArmed ? "KISMI" : "YERDE"}
          tone={allArmed ? "warning" : "neutral"}
        />
        <Metric
          label="Görev"
          value={missionLabel(missionActive, selectedMissionId)}
          tone={missionTone(missionActive)}
          pulse={missionActive}
        />
        <Metric
          label="RTK"
          value={rtkLabel}
          tone={rtkTone}
        />
        <Metric
          label="Bağlantı"
          value={STATUS_LABEL[status]}
          tone={
            status === "open"
              ? "success"
              : status === "connecting"
                ? "warning"
                : "danger"
          }
          pulse={status !== "open"}
        />
      </div>

      <div className="app-header__actions">
        {onOpenSettings && (
          <button
            type="button"
            className="app-header__theme-toggle"
            onClick={onOpenSettings}
            aria-label="Ayarlar"
            title="Ayarlar — parametreler (irtifa, hız, min-nav)"
          >
            ⚙
          </button>
        )}
        <button
          type="button"
          className="app-header__theme-toggle"
          onClick={toggleTheme}
          aria-label={theme === "dark" ? "Açık temaya geç" : "Koyu temaya geç"}
          title={theme === "dark" ? "Açık tema" : "Koyu tema"}
        >
          {theme === "dark" ? "☾" : "☀"}
        </button>
      </div>
    </header>
  );
}

interface MetricProps {
  label: string;
  value: string;
  tone: "success" | "warning" | "danger" | "neutral";
  mono?: boolean;
  pulse?: boolean;
}

function Metric({ label, value, tone, mono, pulse }: MetricProps) {
  return (
    <div className={`metric metric--${tone} ${pulse ? "metric--pulse" : ""}`}>
      <span className="metric__label">{label}</span>
      <span className={`metric__value ${mono ? "mono" : ""}`}>{value}</span>
    </div>
  );
}
