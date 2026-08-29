import type { RtkStatus } from "../../types/telemetry";
import type { ConnectionStatus } from "../../services/websocket";
import "./AppHeader.css";

interface AppHeaderProps {
  status: ConnectionStatus;
  rtk: RtkStatus | null;
  onOpenSettings?: () => void;
  /** Bildirim panelini acar. */
  onOpenBildirimler?: () => void;
  /** Panelde henuz gorulmemis uyari/kritik sayisi; 0 ise rozet cizilmez. */
  okunmamisBildirim?: number;
}

// 29 Agustos 2026 (operator): baslikta ARM ve GOREV kutulari KALDIRILDI.
//   ARM   -> zaten her drone kartinda ayri ayri takip ediliyordu.
//   GOREV -> sonra geri gelecek; geldiginde swarmState + selectedMissionId
//            proplari ve missionLabel/missionTone yardimcilari da geri gelir
//            (git: `git show e4eceb9:src/gcs/frontend/src/components/AppShell/AppHeader.tsx`).
//   SURU  -> kaldirildi, sartname 3'ten fazla IHA'ya izin veriyor.
// Kalan iki bilgi kenarlara yaslandi: baglanti solda basligin altina,
// RTK sagda ayarlar dugmesinin soluna.

const STATUS_LABEL: Record<ConnectionStatus, string> = {
  connecting: "Bağlanıyor",
  open: "Çevrimiçi",
  closed: "Çevrimdışı",
};

const STATUS_TONE: Record<ConnectionStatus, "success" | "warning" | "danger"> = {
  connecting: "warning",
  open: "success",
  closed: "danger",
};

export function AppHeader({
  status,
  rtk,
  onOpenSettings,
  onOpenBildirimler,
  okunmamisBildirim = 0,
}: AppHeaderProps) {
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
          <span
            className={`app-header__conn app-header__conn--${STATUS_TONE[status]}`}
            title={`Bağlantı: ${STATUS_LABEL[status]}`}
          >
            {STATUS_LABEL[status]}
          </span>
        </div>
      </div>

      <div className="app-header__actions">
        <Metric label="RTK" value={rtkLabel} tone={rtkTone} />
        {onOpenBildirimler && (
          <button
            type="button"
            className="app-header__action-btn app-header__action-btn--bildirim"
            onClick={onOpenBildirimler}
            aria-label={
              okunmamisBildirim > 0
                ? `Bildirimler — ${okunmamisBildirim} yeni`
                : "Bildirimler"
            }
            title="Bildirimler — zaman damgalı tam liste"
          >
            <BildirimIkon />
            {okunmamisBildirim > 0 && (
              <span className="app-header__rozet">
                {okunmamisBildirim > 99 ? "99+" : okunmamisBildirim}
              </span>
            )}
          </button>
        )}
        {onOpenSettings && (
          <button
            type="button"
            className="app-header__action-btn"
            onClick={onOpenSettings}
            aria-label="Ayarlar"
            title="Ayarlar — parametreler (irtifa, hız, min-nav)"
          >
            ⚙
          </button>
        )}
      </div>
    </header>
  );
}

/** Zil ikonu — emoji degil inline SVG: emojiler platformdan platforma
 *  farkli ciziliyor ve operator arayuzden emojileri kaldirtti. */
function BildirimIkon() {
  return (
    <svg
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18 8a6 6 0 1 0-12 0c0 6-2 7-2 7h16s-2-1-2-7" />
      <path d="M13.7 20a1.9 1.9 0 0 1-3.4 0" />
    </svg>
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
