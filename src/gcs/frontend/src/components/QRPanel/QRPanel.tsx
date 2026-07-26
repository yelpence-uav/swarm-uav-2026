import {
  FORMATION_LABELS,
  QR_COLOR_LABELS,
  type QRMissionData,
} from "../../types/telemetry";
import "./QRPanel.css";

interface QRPanelProps {
  qr: QRMissionData | null;
}

/**
 * Çözülmüş QR görev içeriği kartı.
 *
 * Şartname V2 zorunluluğu: görev süresince QR mesajı en az 1 kez YKİ'de
 * gösterilmelidir (aksi halde -20 puan). Bu panel qr_detector'ın çözdüğü
 * QRMissionData'yı (formasyon / manevra / irtifa / ayrılma + ham metin)
 * operatöre gösterir.
 */
export function QRPanel({ qr }: QRPanelProps) {
  if (!qr || (!qr.decoded && !qr.detected)) {
    return (
      <section className="qr-panel qr-panel--empty">
        <span className="qr-panel__title">QR GÖREV</span>
        <span className="qr-panel__placeholder">
          (henüz QR okunmadı - qr_detector bekleniyor)
        </span>
      </section>
    );
  }

  const formationLabel = FORMATION_LABELS[qr.formation_type] ?? "?";
  const colorLabel = QR_COLOR_LABELS[qr.detach_color] ?? "?";
  const invalid = qr.decoded && !qr.valid;

  return (
    <section
      className={"qr-panel " + (invalid ? "qr-panel--invalid" : "")}
    >
      <div className="qr-panel__row">
        <span className="qr-panel__title">QR</span>
        <span className="qr-panel__id">
          #{qr.qr_id}
          {qr.qr_seq > 0 && (
            <span className="qr-panel__seq"> · sıra {qr.qr_seq}</span>
          )}
        </span>
        {qr.valid && (
          <span className="qr-panel__badge qr-panel__badge--ok">ÇÖZÜLDÜ</span>
        )}
        {invalid && (
          <span className="qr-panel__badge qr-panel__badge--invalid">
            GEÇERSİZ
          </span>
        )}
        {qr.complete_mission && (
          <span className="qr-panel__badge qr-panel__badge--done">
            GÖREV SONU
          </span>
        )}
      </div>

      <div className="qr-panel__grid">
        {qr.formation_active && (
          <Task
            label="Formasyon"
            value={`${formationLabel} · ${qr.spacing_m.toFixed(0)}m`}
          />
        )}
        {qr.altitude_active && (
          <Task label="İrtifa" value={`${qr.altitude_agl_m.toFixed(0)} m`} />
        )}
        {qr.maneuver_active && (
          <Task
            label="Manevra"
            value={`P${fmtDeg(qr.pitch_deg)} R${fmtDeg(qr.roll_deg)} Y${fmtDeg(qr.yaw_deg)}`}
          />
        )}
        {qr.detach_active && (
          <Task
            label="Ayrılma"
            value={`Drone ${qr.target_agent_id} -> ${colorLabel}`}
            highlight={qr.detach_color}
          />
        )}
        <Task
          label="Sonraki QR"
          value={qr.next_qr > 0 ? `#${qr.next_qr}` : "yok (home)"}
        />
        {qr.wait_s > 0 && (
          <Task label="Bekleme" value={`${qr.wait_s.toFixed(0)} sn`} />
        )}
        {qr.team_id && <Task label="Takım" value={qr.team_id} />}
        <Task
          label="Güven"
          value={`%${(qr.confidence * 100).toFixed(0)}`}
        />
      </div>

      {qr.raw_text && (
        <details className="qr-panel__raw">
          <summary>Ham QR metni</summary>
          <pre>{qr.raw_text}</pre>
        </details>
      )}
      {invalid && qr.error_message && (
        <div className="qr-panel__error">{qr.error_message}</div>
      )}
    </section>
  );
}

function fmtDeg(v: number): string {
  const s = v > 0 ? "+" : "";
  return `${s}${v.toFixed(0)}°`;
}

function Task({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: number; // detach_color: 1=kırmızı, 2=mavi vurgu
}) {
  const cls =
    "qr-panel__task" +
    (highlight === 1 ? " qr-panel__task--red" : "") +
    (highlight === 2 ? " qr-panel__task--blue" : "");
  return (
    <div className={cls}>
      <span className="qr-panel__task-label">{label}</span>
      <span className="qr-panel__task-value">{value}</span>
    </div>
  );
}
