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

// 🔴 İKİ KÜME AYRI TUTULUYOR — 5 Eylül 2026.
//
// Panelde eskiden yalnız GUIDED alanları vardı ve bunu HİÇBİR YERDE
// söylemiyordu. Operatör "varsayılan hız"ı değiştirip görevin hızlandığını
// sanabilirdi; oysa mode_manager ve mission1 o alanı hiç okumuyor. Saha
// gününde bu "ayarladım ama olmadı" dakikaları üretir.
const GUIDED_FIELDS: FieldDef[] = [
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

// Bunlar GÖREV 2 BAŞLAT paketiyle mesh'ten uçaklara gider ve
// mode_manager ROS parametresi olarak uygular. Boş/0 = "belirtilmedi",
// uçak kendi varsayılanını korur — aralık/irtifa ile aynı sözleşme.
// Sınır denetimi UÇAKTA (canli_param); buradaki min/max yalnız tarayıcı
// yardımı, tek kaynak uçaktır.
const SURU_FIELDS: FieldDef[] = [
  {
    key: "suru_hareket_hiz_mps",
    label: "Hareket hızı",
    unit: "m/s",
    hint: "Çubukla öteleme hızı. Sürü hızlı geliyorsa düşür (0.3-5.0)",
  },
  {
    key: "suru_morf_hiz_mps",
    label: "Formasyon değişim hızı",
    unit: "m/s",
    hint: "Morf sırasındaki slot hızı. Yüksekse kaçınma payı azalır (0.2-3.0)",
  },
  {
    key: "suru_yaw_hiz_deg_s",
    label: "Dönüş hızı tavanı",
    unit: "°/s",
    hint: "Sürünün merkez etrafında dönme hızı (2-25)",
  },
  {
    key: "suru_egim_tavan_deg",
    label: "Manevra eğim tavanı",
    unit: "°",
    hint: "Manevra modunda formasyon düzleminin eğim genliği (3-30)",
  },
];

const FIELDS: FieldDef[] = [...GUIDED_FIELDS, ...SURU_FIELDS];

export function SettingsPanel({ params, onSaved, onClose }: SettingsPanelProps) {
  const [form, setForm] = useState<Record<string, string>>(
    Object.fromEntries(
      FIELDS.map((f) => [
        f.key,
        String((params as unknown as Record<string, number>)[f.key] ?? 0),
      ]),
    ),
  );
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
          <h3 className="settings-grup__baslik">Sürü davranışı — Görev 2</h3>
          <p className="settings-grup__not">
            BAŞLAT paketiyle uçaklara gider. Boş/0 = değiştirme, uçak kendi
            varsayılanını korur. Havadayken uygulanmaz.
          </p>
          {SURU_FIELDS.map((f) => (
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

          <h3 className="settings-grup__baslik">Test yolu (guided) — göreve etki etmez</h3>
          <p className="settings-grup__not">
            Yalnız YKİ'nin takeoff/goto test komutlarını besler. Görev 1 ve
            Görev 2 bu değerleri okumaz.
          </p>
          {GUIDED_FIELDS.map((f) => (
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
