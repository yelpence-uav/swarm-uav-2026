import { PIL_GOSTER } from "../../services/gorunum";
import type { DroneState } from "../../types/telemetry";
import { AGENT_STATE_LABELS } from "../../types/telemetry";
import type { GunlukKaydi } from "../../services/api";
import { BatteryGauge } from "./BatteryGauge";
import { DroneLog } from "./DroneLog";
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
  /** Kart sağ üstündeki buton — seçili drone kontrol panelini açar. */
  onSelect?: (droneId: number) => void;
  selected?: boolean;
  /** Bu drone'un olay kayıtları (sistem geneli dahil). */
  kayitlar?: GunlukKaydi[];
  /** Görülmemiş kritik olay var mı — LOG butonu kırmızı yanıp söner. */
  kritik?: boolean;
  logAcik?: boolean;
  onLogToggle?: (droneId: number) => void;
  gunlukHata?: boolean;
  gunlukAktif?: boolean;
  /** Diğer drone'lara YATAY mesafe (m). Boşsa satır hiç çizilmez. */
  mesafeler?: { id: number; ad: string; yatay_m: number }[];
}

/** Kart başlığı — sadece telemetri kartlarında ortak; tek aksiyon: Kontrol. */
function CardHead({
  drone,
  badge,
  onSelect,
  selected,
  logAcik,
  onLogToggle,
  kritik,
}: {
  drone: DroneState;
  badge: React.ReactNode;
  onSelect?: (id: number) => void;
  selected?: boolean;
  logAcik?: boolean;
  onLogToggle?: (id: number) => void;
  kritik?: boolean;
}) {
  return (
    <header className="drone-card__head">
      <span
        className={`drone-card__dot ${drone.connected ? "drone-card__dot--live" : ""}`}
      />
      <h3 className="drone-card__title">{drone.name}</h3>
      {badge}
      {onLogToggle && (
        <button
          type="button"
          className={
            "drone-card__log" +
            (logAcik ? " drone-card__log--acik" : "") +
            // Yanip sonme YALNIZ kapaliyken: acikken olay zaten goz onunde,
            // yanip sonen buton orada dikkat dagitir.
            (kritik && !logAcik ? " drone-card__log--kritik" : "")
          }
          onClick={() => onLogToggle(drone.drone_id)}
          title={
            kritik
              ? "GÖRÜLMEMİŞ KRİTİK OLAY VAR — olay defterini aç"
              : "Bu drone'un olay defterini aç/kapa"
          }
        >
          ▤ LOG
        </button>
      )}
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

export function DroneCard({
  drone,
  onSelect,
  selected = false,
  kayitlar = [],
  kritik = false,
  logAcik = false,
  onLogToggle,
  gunlukHata = false,
  gunlukAktif = true,
  mesafeler = [],
}: DroneCardProps) {
  const accent = ACCENT_VARS[drone.drone_id] ?? "var(--color-accent)";
  const stateLabel = AGENT_STATE_LABELS[drone.state] ?? drone.mode;

  if (!drone.connected) {
    return (
      <article
        className={`drone-card drone-card--offline ${selected ? "drone-card--selected" : ""} ${logAcik ? "drone-card--log" : ""}`}
        style={{ "--accent": accent } as React.CSSProperties}
      >
        <CardHead
          drone={drone}
          onSelect={onSelect}
          selected={selected}
          logAcik={logAcik}
          onLogToggle={onLogToggle}
          kritik={kritik}
          badge={
            <span className="drone-card__badge drone-card__badge--offline">OFFLINE</span>
          }
        />
        <div className="drone-card__govde">
          <div className="drone-card__telemetri">
            <div className="drone-card__offline-body">
              <span className="drone-card__offline-icon">⚠</span>
              <span className="drone-card__offline-text">Son paket gelmiyor</span>
            </div>
          </div>
          {logAcik && (
            <div className="drone-card__log-katman">
              <DroneLog kayitlar={kayitlar} hata={gunlukHata} aktif={gunlukAktif} />
            </div>
          )}
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
      className={`drone-card ${selected ? "drone-card--selected" : ""} ${logAcik ? "drone-card--log" : ""}`}
      style={{ "--accent": accent } as React.CSSProperties}
    >
      <CardHead
        drone={drone}
        onSelect={onSelect}
        selected={selected}
        logAcik={logAcik}
        onLogToggle={onLogToggle}
        kritik={kritik}
        badge={
          <span
            className={`drone-card__badge drone-card__badge--${armed ? "armed" : "ground"}`}
          >
            {armed ? "ARMED" : "YERDE"}
          </span>
        }
      />

      {/* GOVDE — telemetri ile defter AYNI grid hucresinde ust uste.
          Kartin yuksekligi HER ZAMAN telemetriye gore belirlenir; defter o
          kutuyu doldurur. Boylece LOG'a basinca serit KIPIRDAMIYOR ve
          "defter ne kadar uzun olsun" diye sihirli bir sayi tutmak
          gerekmiyor — telemetri kartinin icerigi degisirse defter de
          kendiliginde ona uyar. */}
      <div className="drone-card__govde">
      <div className="drone-card__telemetri">
      <div
        className={`drone-card__fly ${canFly ? "drone-card__fly--ok" : "drone-card__fly--no"}`}
      >
        <span className="drone-card__fly-dot" />
        {canFly ? "UÇABİLİR" : "UÇAMAZ"}
      </div>

      <div className="drone-card__state">
        <span className="drone-card__state-label">{stateLabel}</span>
      </div>

      {PIL_GOSTER && (
        <BatteryGauge percent={drone.battery_percent} voltage={drone.battery_voltage} />
      )}

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

      {/* KOMSU MESAFELERI.
          Ust basliktan buraya tasindi (27 Agu): tek bir "2.41 / 12.03" dizisi
          hangi cifte ait oldugunu SOYLEMIYORDU. Kartta durunca soru kendiliginden
          cevaplaniyor — bu kart hangi drone ise, digerlerine uzakligi yaninda. */}
      {mesafeler.length > 0 && (
        <div className="drone-card__mesafe">
          <span className="drone-card__mesafe-label">MESAFE</span>
          {mesafeler.map((m) => (
            <span key={m.id} className="drone-card__mesafe-oge mono">
              {m.ad} <b>{m.yatay_m.toFixed(2)}</b> m
            </span>
          ))}
        </div>
      )}

      <footer className="drone-card__footer mono">
        {drone.lat.toFixed(5)}, {drone.lon.toFixed(5)}
      </footer>
      </div>
      {logAcik && (
        <div className="drone-card__log-katman">
              <DroneLog kayitlar={kayitlar} hata={gunlukHata} aktif={gunlukAktif} />
            </div>
      )}
      </div>
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
