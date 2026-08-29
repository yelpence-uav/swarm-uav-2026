import { PIL_GOSTER } from "../../services/gorunum";
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
  /** Kart sağ üstündeki buton — seçili drone kontrol panelini açar. */
  onSelect?: (droneId: number) => void;
  selected?: boolean;
  /** Görülmemiş kritik olay var mı — LOG butonu kırmızı. */
  kritik?: boolean;
  /** RPi paneli — Pi sağlık değerleri (SSH ile, mesh'ten GEÇMEZ). */
  onRpiAc?: (droneId: number) => void;
  /** LOG: bildirim panelini BU drone'a süzülmüş açar.
   *
   *  29 Ağustos 2026: kart içindeki log katmanı KALDIRILDI. Kartlar alt
   *  şeritte kısa; log oraya sığmıyordu ve her düzen denemesinde daha da
   *  daralıyordu. Aynı defteri başlıktaki bildirim paneli zaten drone
   *  süzgeciyle gösteriyor — iki ayrı log yüzeyi tutmanın karşılığı yoktu. */
  onLogAc?: (droneId: number) => void;
  /** Diğer drone'lara YATAY mesafe (m). Boşsa satır hiç çizilmez. */
  mesafeler?: { id: number; ad: string; yatay_m: number }[];
}

/** Kart başlığı — YALNIZ kimlik ve durum. 29 Ağustos 2026'da eylem
 *  butonları (LOG, Kontrol) buradan alt şeride taşındı: başlıkta altı
 *  öğe vardı ve "bu ne durumda" ile "ne yapabilirim" iç içe geçmişti. */
function CardHead({
  drone,
  badge,
  canFly,
  durum,
}: {
  drone: DroneState;
  badge: React.ReactNode;
  /** undefined = gosterme (offline kartta OFFLINE rozeti zaten yeterli). */
  canFly?: boolean;
  /** agent_fsm durum etiketi ("Boşta", "Armed", "Sürüde"...). */
  durum?: string;
}) {
  return (
    <header className="drone-card__head">
      {/* Renkli canli noktasi 29 Agustos 2026'da KALDIRILDI (operator):
          "bagli mi" bilgisini zaten OFFLINE rozeti ve kartin solmasi
          veriyordu; nokta ayrica surekli yanip sonup dikkat dagitiyordu. */}
      <h3 className="drone-card__title">{drone.name}</h3>
      {canFly !== undefined && (
        <span
          className={
            "drone-card__fly-rozet " +
            (canFly ? "drone-card__fly-rozet--ok" : "drone-card__fly-rozet--no")
          }
          title={
            canFly
              ? "Ön kontroller tamam, kill switch kapalı, kumanda bağlı"
              : "Ön kontrol, kill switch ya da kumanda bağlantısı engelliyor"
          }
        >
          {canFly ? "UÇABİLİR" : "UÇAMAZ"}
        </span>
      )}
      {durum && (
        <span
          className="drone-card__durum-rozet"
          title="Sürü ajanının görev durumu (agent_fsm) — PX4 arm durumundan ayrı"
        >
          {durum}
        </span>
      )}
      {badge}
    </header>
  );
}

/** Kart eylemleri — alt şeridin sağında, bilgiden ince bir çizgiyle ayrı. */
function CardActions({
  drone,
  onSelect,
  selected,
  onLogAc,
  kritik,
  onRpi,
}: {
  drone: DroneState;
  onSelect?: (id: number) => void;
  selected?: boolean;
  onLogAc?: (id: number) => void;
  kritik?: boolean;
  /** Raspberry Pi paneli. Verilmezse buton GORUNUR ama pasif — yeri
   *  simdiden ayrilsin, isleyisi sonra baglanacak. Baglamak icin tek
   *  yapilacak: bu prop'u gecmek. */
  onRpi?: (id: number) => void;
}) {
  return (
    <span className="drone-card__eylemler">
      {onLogAc && (
        <button
          type="button"
          className={
            "drone-card__eylem-btn drone-card__log" +
            (kritik ? " drone-card__log--kritik" : "")
          }
          onClick={() => onLogAc(drone.drone_id)}
          title={
            kritik
              ? "GÖRÜLMEMİŞ KRİTİK OLAY VAR — bildirimleri bu drone için aç"
              : "Bildirimleri bu drone için aç"
          }
        >
          LOG
        </button>
      )}
      {onSelect && (
        <button
          type="button"
          className={
            "drone-card__eylem-btn drone-card__ctrl" +
            (selected ? " drone-card__ctrl--active" : "")
          }
          onClick={() => onSelect(drone.drone_id)}
          title="Kontrol panelini aç (arm, kalkış, nokta-git…)"
        >
          Kontrol
        </button>
      )}
      <button
        type="button"
        className="drone-card__eylem-btn drone-card__rpi"
        onClick={onRpi ? () => onRpi(drone.drone_id) : undefined}
        disabled={!onRpi}
        title={
          onRpi
            ? "Raspberry Pi paneli"
            : "Raspberry Pi paneli — henüz bağlanmadı"
        }
      >
        RPi
      </button>
    </span>
  );
}

export function DroneCard({
  drone,
  onSelect,
  selected = false,
  kritik = false,
  onLogAc,
  onRpiAc,
  mesafeler = [],
}: DroneCardProps) {
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
            </div>
        {/* Offline kartta da eylemler dursun: bagli olmayan drone'un
            defterine bakmak tam da o an gerekiyor. */}
        <footer className="drone-card__footer">
          <CardActions
            drone={drone}
            onSelect={onSelect}
            selected={selected}
            onLogAc={onLogAc}
            onRpi={onRpiAc}
            kritik={kritik}
          />
        </footer>
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
        canFly={canFly}
        durum={stateLabel}
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
      {/* ALT SERIT: solda koordinat, sagda komsu mesafeleri. Ikisi ayni
          hizada (29 Agu, operator) — mesafe kendi satirinda dururken kart
          bir satir daha uzuyordu ve iki bilgi de "yardimci" oldugu icin
          ayni seride yakisiyor. */}
      </div>
      </div>

      <footer className="drone-card__footer">
        <CardActions
          drone={drone}
          onSelect={onSelect}
          selected={selected}
          onLogAc={onLogAc}
          onRpi={onRpiAc}
          kritik={kritik}
        />
        {/* Konum ve mesafeler YAN YANA, sagda; aralarinda ince cubuk.
            Mesafe sarmalayicisi kaldirildi ki cubuk kurali (`> * + *`)
            konum ile her mesafe ogesi arasinda ESIT calissin. */}
        <span className="drone-card__footer-bilgi">
          <span className="drone-card__footer-konum mono">
            {drone.lat.toFixed(5)}, {drone.lon.toFixed(5)}
          </span>
          {mesafeler.map((m) => (
            <span key={m.id} className="drone-card__mesafe-oge mono">
              {m.ad} <b>{m.yatay_m.toFixed(2)}</b> m
            </span>
          ))}
        </span>
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
