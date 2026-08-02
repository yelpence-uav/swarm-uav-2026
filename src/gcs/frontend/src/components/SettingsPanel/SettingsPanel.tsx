import { useState } from "react";

import { CommandFailure, FlightParams, params as paramsApi } from "../../services/api";
import "./SettingsPanel.css";

interface SettingsPanelProps {
  params: FlightParams;
  onSaved: (p: FlightParams) => void;
  onClose: () => void;
}

interface FieldDef {
  key: keyof FlightParams;
  label: string;
  unit: string;
  hint: string;
}

const FIELDS: FieldDef[] = [
  { key: "default_altitude_m", label: "Basic irtifa", unit: "m", hint: "Takeoff / nokta-git için varsayılan irtifa" },
  { key: "default_speed_ms", label: "Basic hız", unit: "m/s", hint: "Nokta-git seyir hızı (yalpalama için düşür)" },
  { key: "min_nav_altitude_m", label: "Min. navigasyon irtifası", unit: "m", hint: "Altındayken önce oto-kalkış yapılır" },
];

export function SettingsPanel({ params, onSaved, onClose }: SettingsPanelProps) {
  const [form, setForm] = useState<Record<string, string>>({
    default_altitude_m: String(params.default_altitude_m),
    default_speed_ms: String(params.default_speed_ms),
    min_nav_altitude_m: String(params.min_nav_altitude_m),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    const patch: Partial<FlightParams> = {};
    for (const f of FIELDS) {
      const v = parseFloat(form[f.key]);
      if (!Number.isNaN(v)) patch[f.key] = v;
    }
    setBusy(true);
    setError(null);
    try {
      const saved = await paramsApi.update(patch);
      onSaved(saved);
      onClose();
    } catch (e) {
      setError(e instanceof CommandFailure ? e.message : "Kaydedilemedi");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()} role="dialog">
        <header className="settings-modal__head">
          <h2>⚙ Ayarlar — Parametreler</h2>
          <button className="settings-modal__close" onClick={onClose} aria-label="Kapat">✕</button>
        </header>
        <div className="settings-modal__body">
          {FIELDS.map((f) => (
            <label key={f.key} className="settings-field">
              <span className="settings-field__label">
                {f.label} <em>({f.unit})</em>
              </span>
              <input
                type="number"
                step="0.1"
                value={form[f.key]}
                onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))}
              />
              <span className="settings-field__hint">{f.hint}</span>
            </label>
          ))}
          {error && <div className="settings-modal__error">{error}</div>}
        </div>
        <footer className="settings-modal__foot">
          <button className="settings-btn settings-btn--ghost" onClick={onClose} disabled={busy}>
            İptal
          </button>
          <button className="settings-btn settings-btn--primary" onClick={save} disabled={busy}>
            {busy ? "…" : "Kaydet"}
          </button>
        </footer>
      </div>
    </div>
  );
}
