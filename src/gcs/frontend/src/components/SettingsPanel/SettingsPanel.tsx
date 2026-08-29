import { useState } from "react";

import { CommandFailure, FlightParams, params as paramsApi, rtk as rtkApi } from "../../services/api";
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
  {
    key: "default_altitude_m",
    label: "Varsayılan irtifa",
    unit: "m",
    hint: "Kalkışta ve bir noktaya giderken kullanılan irtifa",
  },
  {
    key: "default_speed_ms",
    label: "Varsayılan hız",
    unit: "m/s",
    hint: "Noktalar arası seyir hızı. Uçak salınım yapıyorsa düşür",
  },
  {
    key: "min_nav_altitude_m",
    label: "En düşük seyir irtifası",
    unit: "m",
    hint: "Uçak bunun altındaysa önce otomatik kalkış yapılır",
  },
];

export function SettingsPanel({ params, onSaved, onClose }: SettingsPanelProps) {
  const [form, setForm] = useState<Record<string, string>>({
    default_altitude_m: String(params.default_altitude_m),
    default_speed_ms: String(params.default_speed_ms),
    min_nav_altitude_m: String(params.min_nav_altitude_m),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // RTK reset — İKİ ADIMLI onay. Tek tıkla resetlenmesin: komut RTCM akışını
  // kesiyor ve uçaklar RTK-FIX düşürüyor. window.confirm KULLANILMADI; sahada
  // tarayıcı diyalogları tabletlerde bazen engelleniyor ve buton sessizce
  // hiçbir şey yapmıyormuş gibi görünüyor.
  const [rtkOnay, setRtkOnay] = useState(false);
  const [rtkBusy, setRtkBusy] = useState(false);
  const [rtkSonuc, setRtkSonuc] = useState<string | null>(null);

  const rtkReset = async () => {
    setRtkBusy(true);
    setRtkSonuc(null);
    try {
      const r = await rtkApi.reset("sicak");
      setRtkSonuc(`Yeniden başlatma komutu gönderildi (${r.kip}). ${r.uyari}`);
      setRtkOnay(false);
    } catch (e) {
      setRtkSonuc(e instanceof CommandFailure ? `HATA: ${e.message}` : "Komut gönderilemedi");
    } finally {
      setRtkBusy(false);
    }
  };

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
          <h2>Uçuş ayarları</h2>
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

          <div className="settings-bakim">
            <h3 className="settings-bakim__baslik">RTK baz istasyonu</h3>
            <p className="settings-bakim__not">
              Baz istasyonunun alıcısını yeniden başlatır. <strong>Düzeltme yayını
              birkaç saniye kesilir</strong>; uçaklar RTK kilidini kaybedip yeniden
              yakalar. Uçuş sırasında kullanma.
            </p>
            {!rtkOnay ? (
              <button
                className="settings-btn settings-btn--uyari"
                onClick={() => { setRtkOnay(true); setRtkSonuc(null); }}
                disabled={rtkBusy}
              >
                Yeniden başlat
              </button>
            ) : (
              <div className="settings-bakim__onay">
                <span>Emin misin?</span>
                <button
                  className="settings-btn settings-btn--tehlike"
                  onClick={rtkReset}
                  disabled={rtkBusy}
                >
                  {rtkBusy ? "…" : "Evet, yeniden başlat"}
                </button>
                <button
                  className="settings-btn settings-btn--ghost"
                  onClick={() => setRtkOnay(false)}
                  disabled={rtkBusy}
                >
                  Vazgeç
                </button>
              </div>
            )}
            {rtkSonuc && <div className="settings-bakim__sonuc">{rtkSonuc}</div>}
          </div>
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
