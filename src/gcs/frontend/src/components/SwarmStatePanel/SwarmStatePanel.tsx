import {
  FORMATION_LABELS,
  SWARM_STATE_LABELS,
  type SwarmState,
} from "../../types/telemetry";
import "./SwarmStatePanel.css";

interface SwarmStatePanelProps {
  swarmState: SwarmState | null;
}

/** Sürü-seviyesi durum kartı: state + lider + formasyon + ilerleme metrikleri. */
export function SwarmStatePanel({ swarmState }: SwarmStatePanelProps) {
  if (!swarmState) {
    return (
      <section className="swarm-state-panel swarm-state-panel--empty">
        <span className="swarm-state-panel__title">SÜRÜ DURUMU</span>
        <span className="swarm-state-panel__placeholder">
          (henüz SwarmState mesajı yok — swarm_fsm bekleniyor)
        </span>
      </section>
    );
  }

  const stateLabel = SWARM_STATE_LABELS[swarmState.swarm_state] ?? `?(${swarmState.swarm_state})`;
  const formationLabel = FORMATION_LABELS[swarmState.active_formation] ?? "?";

  return (
    <section
      className={
        "swarm-state-panel " +
        (swarmState.emergency_active ? "swarm-state-panel--emergency" : "")
      }
    >
      <div className="swarm-state-panel__row">
        <span className="swarm-state-panel__title">SÜRÜ:</span>
        <span className="swarm-state-panel__state">{stateLabel}</span>
        {swarmState.mission_active && (
          <span className="swarm-state-panel__badge swarm-state-panel__badge--active">
            GÖREV AKTİF
          </span>
        )}
        {swarmState.emergency_active && (
          <span className="swarm-state-panel__badge swarm-state-panel__badge--emergency">
            ACİL DURUM
          </span>
        )}
      </div>
      <div className="swarm-state-panel__row swarm-state-panel__row--compact">
        <Stat label="Lider" value={`Drone ${swarmState.leader_id}`} />
        <Stat label="Aktif" value={`${swarmState.active_agent_count} drone`} />
        <Stat label="Formasyon" value={formationLabel} />
        <Stat
          label="Heading"
          value={`${swarmState.formation_heading_deg.toFixed(1)}°`}
        />
        <Stat
          label="Hata maks/ort"
          value={`${swarmState.formation_max_error_m.toFixed(2)} / ${swarmState.formation_avg_error_m.toFixed(2)} m`}
        />
        <Stat
          label="QR"
          value={
            swarmState.current_qr_id > 0
              ? `#${swarmState.current_qr_id} (${swarmState.current_qr_seq})`
              : "—"
          }
        />
        <Stat
          label="Görev"
          value={swarmState.active_mission || "—"}
        />
      </div>
      {swarmState.status_text && (
        <div className="swarm-state-panel__status">{swarmState.status_text}</div>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="swarm-state-panel__stat">
      <span className="swarm-state-panel__stat-label">{label}</span>
      <span className="swarm-state-panel__stat-value">{value}</span>
    </div>
  );
}
