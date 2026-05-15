import { useState } from "react";

import { CommandFailure, api } from "../../services/api";
import "./CommandButtons.css";

interface CommandButtonsProps {
  droneId: number;
  connected: boolean;
  /** Görev aktif iken bireysel komutlar yasak (şartname). */
  disabled?: boolean;
}

type ActionKey = "takeoff" | "land" | "rtl" | "disarm";

interface ActionMeta {
  label: string;
  icon: string;
  className: string;
  confirm?: string;
}

const ACTIONS: Record<ActionKey, ActionMeta> = {
  takeoff: {
    label: "Kalkış",
    icon: "▲",
    className: "btn--primary",
  },
  land: {
    label: "İniş",
    icon: "▼",
    className: "btn--neutral",
    confirm: "Drone'u indirmek istediğinden emin misin?",
  },
  rtl: {
    label: "Eve Dön",
    icon: "⌂",
    className: "btn--neutral",
    confirm: "Drone başlangıç noktasına dönecek. Onay?",
  },
  disarm: {
    label: "Acil Dur",
    icon: "■",
    className: "btn--danger",
    confirm:
      "DİKKAT: Drone havadaysa motor kesilir ve düşer.\n\nAcil durumu onaylıyor musun?",
  },
};

export function CommandButtons({ droneId, connected, disabled = false }: CommandButtonsProps) {
  const [busy, setBusy] = useState<ActionKey | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (action: ActionKey) => {
    const meta = ACTIONS[action];
    if (meta.confirm && !window.confirm(meta.confirm)) return;

    setBusy(action);
    setError(null);

    try {
      switch (action) {
        case "takeoff":
          await api.takeoff(droneId);
          break;
        case "land":
          await api.land(droneId);
          break;
        case "rtl":
          await api.rtl(droneId);
          break;
        case "disarm":
          await api.disarm(droneId, true);
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
      window.setTimeout(() => setError(null), 4000);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="cmd-buttons">
      {(Object.keys(ACTIONS) as ActionKey[]).map((key) => {
        const meta = ACTIONS[key];
        const isBusy = busy === key;
        return (
          <button
            key={key}
            type="button"
            className={`cmd-btn ${meta.className} ${isBusy ? "is-busy" : ""}`}
            onClick={() => run(key)}
            disabled={!connected || busy !== null || disabled}
            aria-label={meta.label}
            title={
              !connected
                ? "Drone bağlı değil"
                : disabled
                  ? "Görev aktif iken bireysel komut yasak (şartname)"
                  : meta.label
            }
          >
            <span className="cmd-btn__icon">{meta.icon}</span>
            <span className="cmd-btn__label">{meta.label}</span>
          </button>
        );
      })}
      {error && <div className="cmd-buttons__error" title={error}>{error}</div>}
    </div>
  );
}
