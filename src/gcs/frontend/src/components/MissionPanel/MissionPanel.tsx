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
 * Faz 5 - şartname uyumlu görev tetikleyici.
 *
 * Görev 1 sırasında şartname "GCS'ten görev başlatma DIŞINDA müdahale yasak"
 * der. Bu panel o tek müdahale noktasıdır.
 *
 * Test/güvenlik butonları (ABORT/RTL/LAND) ayrıdır - yarışmada basılırsa
 * görev başarısız sayılır, sadece kaza/acil durumda kullanılır.
 */

const MISSION_LABELS: Record<number, string> = {
  [MISSION_ID.DYNAMIC_SWARM]: "Görev 1 — Dinamik Sürü",
  [MISSION_ID.SEMI_AUTONOMOUS]: "Görev 2 — Yarı Otonom",
  [MISSION_ID.TEST]: "Test Görevi",
};

interface MissionPanelProps {
  missionActive: boolean;
  missionId: number;
  onMissionIdChange: (id: number) => void;
  /* Takım ID App'te tutuluyor: haritadaki acil sonlandırma da aynı değeri
     kullanıyor ve iki yerde ayrı state olsaydı biri güncellenip diğeri
     unutulurdu (CLAUDE.md §9). */
  teamId: string;
  onTeamIdChange: (v: string) => void;
}

export function MissionPanel({
  missionActive,
  missionId,
  onMissionIdChange,
  teamId,
  onTeamIdChange,
}: MissionPanelProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<TriggerMissionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function trigger(
    commandCode: number,
    commandLabel: string,
    confirmLevel: "none" | "single" | "double" = "none",
  ) {
    // Geri dönüşü olmayan komutlar (görev iptali) için kazara basmayı önleyen
    // onay zinciri. "double" -> ardışık iki ayrı onay diyaloğu.
    if (confirmLevel !== "none") {
      if (!window.confirm(`${commandLabel} komutu gönderilecek. Emin misin?`)) {
        return;
      }
    }
    if (confirmLevel === "double") {
      if (
        !window.confirm(
          `SON UYARI - ${commandLabel}\n\n` +
            "Bu işlem görevi sonlandırır ve görev BAŞARISIZ sayılır. " +
            "Tüm sürü görevi durdurulacak.\n\nOnaylıyor musun?",
        )
      ) {
        return;
      }
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
            onChange={(e) => onTeamIdChange(e.target.value)}
            placeholder="team_1"
            disabled={busy !== null}
            spellCheck={false}
          />
        </label>

        {missionId === MISSION_ID.TEST ? (
          // Yeri ayrildi, isleyisi HENUZ BAGLANMADI. Baslat dugmesini aktif
          // birakmak backend'e tanimsiz bir mission_id gondermek olurdu.
          // TEST GOREVI = DINAMIK SLOT (29 Agustos 2026, operator):
          // "o an yazdigimiz test neyse onu kosturmak icin degistirilecek".
          // Yani burasi kalici bir ozellik degil, her testte YENIDEN
          // BAGLANACAK bir kanca. Bos birakilmasi bilerek — aktif bir
          // BASLAT dugmesi arka uca tanimsiz bir mission_id gonderirdi.
          <div className="mission-panel__hint mission-panel__hint--bekliyor">
            Test görevi boşta — o anki test buraya bağlanır
          </div>
        ) : missionId !== MISSION_ID.SEMI_AUTONOMOUS ? (
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
        ) : (
          <div className="mission-panel__hint mission-panel__hint--bilgi">
            Görev 2 kumandadan başlatılır (SwD şalteri)
          </div>
        )}
      </div>

      {/* Acil sonlandırma 29 Ağustos 2026'da HARİTANIN ALT ORTASINA taşındı
          (operatör): görev sürerken göz haritada, buton da orada olmalı.
          Bkz. components/AcilSonlandirma/. */}

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
