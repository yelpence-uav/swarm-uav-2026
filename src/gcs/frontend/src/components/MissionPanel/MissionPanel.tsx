import { useState } from "react";
import {
  CommandFailure,
  MISSION_COMMAND,
  MISSION_ID,
  missionApi,
  type TriggerMissionResponse,
} from "../../services/api";
import "./MissionPanel.css";

/**
 * Faz 5 — şartname uyumlu görev tetikleyici.
 *
 * Görev 1 sırasında şartname "GCS'ten görev başlatma DIŞINDA müdahale yasak"
 * der. Bu panel o tek müdahale noktasıdır.
 *
 * Test/güvenlik butonları (ABORT/RTL/LAND) ayrıdır — yarışmada basılırsa
 * görev başarısız sayılır, sadece kaza/acil durumda kullanılır.
 */

const MISSION_LABELS: Record<number, string> = {
  [MISSION_ID.DYNAMIC_SWARM]: "Görev 1 — Dinamik Sürü",
  [MISSION_ID.SEMI_AUTONOMOUS]: "Görev 2 — Yarı Otonom",
};

interface MissionPanelProps {
  missionActive: boolean;
  missionId: number;
  onMissionIdChange: (id: number) => void;
}

export function MissionPanel({
  missionActive,
  missionId,
  onMissionIdChange,
}: MissionPanelProps) {
  const [teamId, setTeamId] = useState<string>("team_1");
  const [busy, setBusy] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<TriggerMissionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function trigger(commandCode: number, commandLabel: string, confirm = false) {
    if (confirm && !window.confirm(`${commandLabel} komutunu göndermek üzeresin. Emin misin?`)) {
      return;
    }
    setBusy(commandLabel);
    setError(null);
    setLastResult(null);
    try {
      const resp = await missionApi.trigger({
        mission_id: missionId,
        command: commandCode,
        team_id: teamId.trim(),
      });
      setLastResult(resp);
    } catch (e) {
      const msg =
        e instanceof CommandFailure
          ? `HTTP ${e.http_status}: ${e.message}`
          : `Hata: ${(e as Error).message}`;
      setError(msg);
    } finally {
      setBusy(null);
    }
  }

  const startDisabled = busy !== null || teamId.trim().length === 0 || missionActive;

  return (
    <section className="mission-panel">
      <div className="mission-panel__row">
        <label className="mission-panel__field">
          <span>Görev:</span>
          <select
            value={missionId}
            onChange={(e) => onMissionIdChange(Number(e.target.value))}
            disabled={busy !== null}
          >
            {Object.entries(MISSION_LABELS).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="mission-panel__field">
          <span>Takım ID:</span>
          <input
            type="text"
            value={teamId}
            onChange={(e) => setTeamId(e.target.value)}
            placeholder="team_1"
            disabled={busy !== null}
            spellCheck={false}
          />
        </label>

        <button
          className="mission-panel__start"
          disabled={startDisabled}
          onClick={() => trigger(MISSION_COMMAND.START, "GÖREV BAŞLAT")}
          title={
            missionActive
              ? "Görev zaten aktif"
              : startDisabled
                ? "Takım ID gerekli"
                : "Görev başlatma servis çağrısı yap"
          }
        >
          {busy === "GÖREV BAŞLAT" ? "GÖNDERİLİYOR..." : "▶ GÖREV BAŞLAT"}
        </button>

        {missionId === MISSION_ID.SEMI_AUTONOMOUS && !missionActive && (
          <div className="mission-panel__hint">
            ⓘ Görev başlayınca joystick paneli sağda açılacak. Pilot kumandayı
            hazır tutmalı (deadman R1).
          </div>
        )}
      </div>

      {/* Şartname §5.1: görev başladıktan sonra GCS müdahalesi yasak. Tek
          istisna operatörün görevi sonlandırması — acil senaryoda kullanılır,
          basıldığında görev başarısız sayılır. */}
      <div className="mission-panel__row mission-panel__row--safety">
        <span className="mission-panel__safety-label">
          ⚠ Acil sonlandırma (görev başarısız sayılır):
        </span>
        <button
          className="mission-panel__safety-btn mission-panel__safety-btn--abort"
          disabled={busy !== null || !missionActive}
          onClick={() => trigger(MISSION_COMMAND.ABORT, "GÖREVİ İPTAL", true)}
        >
          ✕ Görevi İptal Et
        </button>
      </div>

      {lastResult && (
        <div
          className={
            "mission-panel__result " +
            (lastResult.success
              ? "mission-panel__result--ok"
              : "mission-panel__result--fail")
          }
        >
          {lastResult.success ? "✓" : "✗"} {lastResult.message}
        </div>
      )}
      {error && <div className="mission-panel__error">{error}</div>}
    </section>
  );
}
