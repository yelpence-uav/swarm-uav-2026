import { useState } from "react";

import { CommandFailure, FlightParams, GotoTarget, api, guided } from "../../services/api";
import "./CommandButtons.css";

interface CommandButtonsProps {
  droneId: number;
  connected: boolean;
  /** Görev aktif iken bireysel komutlar yasak (şartname). */
  disabled?: boolean;
  /**
   * true: ESP mesh guided komutları (connection_mode=ros2) — Arm + Nokta-git dahil.
   * false: mavlink-sim doğrudan MAVLink komutları.
   */
  guidedMode?: boolean;
  /** Uçuş parametreleri — takeoff/goto varsayılanları buradan ön-doldurulur. */
  params?: FlightParams;
}

const VARSAYILAN_IRTIFA = 5;

type ActionKey = "arm" | "takeoff" | "land" | "rtl" | "disarm";

interface ActionMeta {
  label: string;
  className: string;
  confirm?: string;
}

// 29 Agustos 2026 (operator): ikon glifleri KALDIRILDI, metinler sadelesti.
// Onay metinleri artik "emin misin" demek yerine OPERATORUN BAKMASI GEREKEN
// SEYI soruyor — sahada tek anlamli soru o.
const ACTIONS: Record<ActionKey, ActionMeta> = {
  arm: {
    label: "Arm",
    className: "btn--primary",
    confirm: "Motorlar arm edilecek. Pervanelerin çevresi boş mu?",
  },
  takeoff: {
    label: "Kalkış",
    className: "btn--primary",
  },
  land: {
    label: "İniş",
    className: "btn--neutral",
    confirm: "Drone bulunduğu noktaya inecek. Aşağısı boş mu?",
  },
  rtl: {
    label: "Kalkışa dön",
    className: "btn--neutral",
    confirm: "Drone kalkış noktasına dönüp inecek. Onaylıyor musun?",
  },
  disarm: {
    label: "Motor kes",
    className: "btn--danger",
    confirm:
      "DİKKAT: Drone havadaysa motorlar durur ve DÜŞER.\n\n" +
      "Yere inmiş bir drone için güvenlidir. Devam edilsin mi?",
  },
};

const ORDER_GUIDED: ActionKey[] = ["arm", "takeoff", "rtl", "land", "disarm"];
const ORDER_SIM: ActionKey[] = ["takeoff", "land", "rtl", "disarm"];

export function CommandButtons({
  droneId,
  connected,
  disabled = false,
  guidedMode = false,
  params,
}: CommandButtonsProps) {
  const varAlt = params?.default_altitude_m ?? VARSAYILAN_IRTIFA;
  const [busy, setBusy] = useState<ActionKey | "goto" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gotoOpen, setGotoOpen] = useState(false);
  // Nokta-git formu — x=Kuzey, y=Doğu (m), z=İrtifa (m, yukarı), yön opsiyonel.
  // Hız YKİ'den ayarlanmıyor; drone MPC_XY_VEL_MAX (QGC) ile sınırlı.
  const [gx, setGx] = useState("");
  const [gy, setGy] = useState("");
  const [gz, setGz] = useState(String(varAlt));
  const [gh, setGh] = useState("");

  const order = guidedMode ? ORDER_GUIDED : ORDER_SIM;

  const showError = (msg: string) => {
    setError(msg);
    window.setTimeout(() => setError(null), 4000);
  };

  const runCall = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
    } catch (e) {
      const msg =
        e instanceof CommandFailure
          ? `${e.message} (${e.http_status})`
          : e instanceof Error
            ? e.message
            : "Beklenmeyen hata";
      showError(msg);
    }
  };

  const run = async (action: ActionKey) => {
    const meta = ACTIONS[action];
    if (meta.confirm && !window.confirm(meta.confirm)) return;

    // Guided kalkış: irtifa sor (iptal edilebilir).
    let takeoffAlt = 0;
    if (action === "takeoff" && guidedMode) {
      const s = window.prompt("Kalkış irtifası (metre)", String(varAlt));
      if (s === null) return;
      takeoffAlt = parseFloat(s);
      if (!(takeoffAlt > 0)) {
        showError("İrtifa değeri geçersiz");
        return;
      }
    }

    setBusy(action);
    await runCall(() => {
      if (guidedMode) {
        switch (action) {
          case "arm":
            return guided.arm(droneId);
          case "takeoff":
            return guided.takeoff(droneId, takeoffAlt);
          case "land":
            return guided.land(droneId);
          case "rtl":
            return guided.rtl(droneId);
          case "disarm":
            return guided.disarm(droneId);
        }
      }
      switch (action) {
        case "takeoff":
          return api.takeoff(droneId);
        case "land":
          return api.land(droneId);
        case "rtl":
          return api.rtl(droneId);
        case "disarm":
          return api.disarm(droneId, true);
        case "arm":
          return api.arm(droneId);
      }
      return Promise.resolve();
    });
    setBusy(null);
  };

  const sendGoto = async () => {
    const x = parseFloat(gx);
    const y = parseFloat(gy);
    if (Number.isNaN(x) || Number.isNaN(y)) {
      showError("Kuzey ve Doğu değerleri zorunlu");
      return;
    }
    const z = parseFloat(gz);
    const target: GotoTarget = { x, y, z: Number.isNaN(z) ? varAlt : z };
    if (gh.trim() !== "") {
      const h = parseFloat(gh);
      if (!Number.isNaN(h)) target.heading_deg = h;
    }
    setBusy("goto");
    await runCall(() => guided.goto(droneId, target));
    setBusy(null);
  };

  const busyAny = busy !== null;

  return (
    <div className="cmd-buttons">
      <div className="cmd-buttons__row">
        {order.map((key) => {
          const meta = ACTIONS[key];
          const isBusy = busy === key;
          return (
            <button
              key={key}
              type="button"
              className={`cmd-btn ${meta.className} ${isBusy ? "is-busy" : ""}`}
              onClick={() => run(key)}
              disabled={!connected || busyAny || disabled}
              aria-label={meta.label}
              title={
                !connected
                  ? "Drone bağlı değil"
                  : disabled
                    ? "Görev sürerken tek drone'a komut verilemez (şartname)"
                    : meta.label
              }
            >
              <span className="cmd-btn__label">{meta.label}</span>
            </button>
          );
        })}

        {/* Guided'da eylem sayisi 5 -> iki sutunlu izgarada altinci hucre
            bos kaliyordu. "Noktaya git" o bosluğa YERLESTI (29 Agu,
            operator); acilan form asagida tam genislikte kaliyor. */}
        {guidedMode && (
          <button
            type="button"
            className="cmd-btn cmd-goto__toggle"
            onClick={() => setGotoOpen((v) => !v)}
            disabled={!connected || disabled}
            aria-expanded={gotoOpen}
          >
            Noktaya git {gotoOpen ? "▾" : "▸"}
          </button>
        )}
      </div>

      {guidedMode && (
        <>
          {gotoOpen && (
            <div className="cmd-goto__form">
              <label>
                Kuzey (m)
                <input
                  value={gx}
                  onChange={(e) => setGx(e.target.value)}
                  inputMode="decimal"
                  placeholder="0"
                />
              </label>
              <label>
                Doğu (m)
                <input
                  value={gy}
                  onChange={(e) => setGy(e.target.value)}
                  inputMode="decimal"
                  placeholder="0"
                />
              </label>
              <label>
                İrtifa (m)
                <input
                  value={gz}
                  onChange={(e) => setGz(e.target.value)}
                  inputMode="decimal"
                  placeholder={String(varAlt)}
                />
              </label>
              <div className="cmd-goto__hint">
                Hız uçağın kendi ayarından gelir
              </div>
              <label>
                Yön (°, isteğe bağlı)
                <input
                  value={gh}
                  onChange={(e) => setGh(e.target.value)}
                  inputMode="decimal"
                  placeholder="serbest"
                />
              </label>
              <button
                type="button"
                className="cmd-btn btn--primary cmd-goto__go"
                onClick={sendGoto}
                disabled={!connected || busyAny || disabled}
              >
                Git
              </button>
            </div>
          )}
        </>
      )}

      {error && (
        <div className="cmd-buttons__error" title={error}>
          {error}
        </div>
      )}
    </div>
  );
}
