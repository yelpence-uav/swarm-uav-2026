import { useState } from "react";

import { CommandFailure, api } from "../../services/api";
import "./MissionControl.css";

type ActionKey = "takeoff" | "land" | "rtl" | "disarm";

const ACTION_LABEL: Record<ActionKey, { label: string; icon: string }> = {
  takeoff: { label: "Hepsine Kalkış", icon: "▲" },
  land: { label: "Hepsine İniş", icon: "▼" },
  rtl: { label: "Hepsine Eve Dön", icon: "⌂" },
  disarm: { label: "ACİL DUR", icon: "■" },
};

const CONFIRM_MSG: Record<ActionKey, string | null> = {
  takeoff: null,
  land: "TÜM drone'ları indir? Onay?",
  rtl: "TÜM drone'ları başlangıca geri çağır? Onay?",
  disarm:
    "ACİL DUR — TÜM drone'ların motorları kesilir. Havadakiler düşer!\n\nOnaylıyor musun?",
};

interface MissionControlProps {
  anyConnected: boolean;
}

export function MissionControl({ anyConnected }: MissionControlProps) {
  const [busy, setBusy] = useState<ActionKey | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (action: ActionKey) => {
    const confirm = CONFIRM_MSG[action];
    if (confirm && !window.confirm(confirm)) return;

    setBusy(action);
    setError(null);

    try {
      switch (action) {
        case "takeoff":
          await api.takeoffAll();
          break;
        case "land":
          await api.landAll();
          break;
        case "rtl":
          await api.rtlAll();
          break;
        case "disarm":
          await api.disarmAll(true);
          break;
      }
    } catch (e) {
      const msg =
        e instanceof CommandFailure
          ? `${e.message} (${e.http_status})`
          : e instanceof Error
            ? e.message
            : "Bilinmeyen hata";
      setError(msg);
      window.setTimeout(() => setError(null), 5000);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mc">
      <span className="mc__label">SÜRÜ KOMUTU:</span>
      {(Object.keys(ACTION_LABEL) as ActionKey[]).map((key) => {
        const meta = ACTION_LABEL[key];
        const isBusy = busy === key;
        const isDanger = key === "disarm";
        return (
          <button
            key={key}
            type="button"
            className={`mc__btn ${isDanger ? "mc__btn--danger" : ""} ${isBusy ? "is-busy" : ""}`}
            onClick={() => run(key)}
            disabled={!anyConnected || busy !== null}
          >
            <span aria-hidden="true">{meta.icon}</span> {meta.label}
          </button>
        );
      })}
      {error && <span className="mc__error">{error}</span>}
    </div>
  );
}
