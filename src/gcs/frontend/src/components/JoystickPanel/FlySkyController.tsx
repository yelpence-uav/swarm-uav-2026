import { useState } from "react";
import type { GamepadFrame } from "../../services/gamepad";
import "./FlySkyController.css";

interface FlySkyControllerProps {
  frame: GamepadFrame;
  publishing: boolean;
  pubCount: number;
  mode: number;            // 0=Movement, 1=Maneuver
  formation: number;       // 0=OkBaşı, 1=V, 2=Çizgi
  onModeChange: (m: number) => void;
  onFormationChange: (f: number) => void;
  onTogglePublish: () => void;
}

interface SignalSnapshot {
  axes: number[];
  btns: number[];
}

export function FlySkyController({
  frame,
  publishing,
  pubCount,
  mode,
  formation,
  onModeChange,
  onFormationChange,
  onTogglePublish,
}: FlySkyControllerProps) {
  // Kalibrasyon Sihirbazı Durumları (SwA, SwB, SwC, SwD)
  const [calibOpen, setCalibOpen] = useState(false);
  const [step, setStep] = useState(0); 
  // 0=Başlangıç, 1=SwA Up, 2=SwA Down, 3=SwB Up, 4=SwB Down, 5=SwC Up, 6=SwC Mid, 7=SwC Down, 8=SwD Up, 9=SwD Down, 10=Bitti
  const [snap1, setSnap1] = useState<SignalSnapshot | null>(null);
  const [snap2, setSnap2] = useState<SignalSnapshot | null>(null);

  const [swAResult, setSwAResult] = useState<{ type: string; idx: number } | null>(null);
  const [swBResult, setSwBResult] = useState<{ type: string; idx: number } | null>(null);
  const [swCResult, setSwCResult] = useState<{ type: string; idx1: number; idx2: number } | null>(null);
  const [swDResult, setSwDResult] = useState<{ type: string; idx: number } | null>(null);

  const getSnapshot = (): SignalSnapshot => {
    return {
      axes: frame.all_axes ? [...frame.all_axes] : [],
      btns: frame.raw_btns ? [...frame.raw_btns] : [],
    };
  };

  const handleStepNext = () => {
    const current = getSnapshot();

    if (step === 0) setStep(1); // SwA Up
    else if (step === 1) {
      setSnap1(current);
      setStep(2); // SwA Down
    } else if (step === 2) {
      if (snap1) setSwAResult(findDiff(snap1, current));
      setSnap1(null);
      setStep(3); // SwB Up
    } else if (step === 3) {
      setSnap1(current);
      setStep(4); // SwB Down
    } else if (step === 4) {
      if (snap1) setSwBResult(findDiff(snap1, current));
      setSnap1(null);
      setStep(5); // SwC Pos 1 (Ok Başı)
    } else if (step === 5) {
      setSnap1(current);
      setStep(6); // SwC Pos 2 (V)
    } else if (step === 6) {
      setSnap2(current);
      setStep(7); // SwC Pos 3 (Çizgi)
    } else if (step === 7) {
      // SwC 3-konum diff
      if (snap1) {
        const diff1 = findDiff(snap1, current);
        const diff2 = snap2 ? findDiff(snap2, current) : diff1;
        setSwCResult({ type: diff1.type, idx1: diff1.idx, idx2: diff2.idx });
      }
      setSnap1(null);
      setSnap2(null);
      setStep(8); // SwD Up
    } else if (step === 8) {
      setSnap1(current);
      setStep(9); // SwD Down
    } else if (step === 9) {
      if (snap1) setSwDResult(findDiff(snap1, current));
      setSnap1(null);
      setStep(10); // Bitti
    }
  };

  const findDiff = (a: SignalSnapshot, b: SignalSnapshot): { type: string; idx: number } => {
    const bAdded = b.btns.filter(x => !a.btns.includes(x));
    const bRemoved = a.btns.filter(x => !b.btns.includes(x));
    if (bAdded.length > 0) return { type: "btn", idx: bAdded[0] };
    if (bRemoved.length > 0) return { type: "btn", idx: bRemoved[0] };

    for (let i = 0; i < Math.max(a.axes.length, b.axes.length); i++) {
      const valA = a.axes[i] ?? 0;
      const valB = b.axes[i] ?? 0;
      if (Math.abs(valA - valB) > 0.3) {
        return { type: "axis", idx: i };
      }
    }
    return { type: "btn", idx: 0 };
  };

  const saveCalibration = () => {
    if (swAResult) {
      localStorage.setItem("rc_mapping_swA_type", swAResult.type);
      localStorage.setItem("rc_mapping_swA_idx", String(swAResult.idx));
    }
    if (swBResult) {
      localStorage.setItem("rc_mapping_swB_type", swBResult.type);
      localStorage.setItem("rc_mapping_swB_idx", String(swBResult.idx));
    }
    if (swCResult) {
      localStorage.setItem("rc_mapping_swC_type", swCResult.type);
      localStorage.setItem("rc_mapping_swC_idx1", String(swCResult.idx1));
      localStorage.setItem("rc_mapping_swC_idx2", String(swCResult.idx2));
    }
    if (swDResult) {
      localStorage.setItem("rc_mapping_swD_type", swDResult.type);
      localStorage.setItem("rc_mapping_swD_idx", String(swDResult.idx));
    }
    setCalibOpen(false);
    setStep(0);
    window.location.reload();
  };

  const resetCalibration = () => {
    ["swA", "swB", "swC", "swD"].forEach(sw => {
      localStorage.removeItem(`rc_mapping_${sw}_type`);
      localStorage.removeItem(`rc_mapping_${sw}_idx`);
      localStorage.removeItem(`rc_mapping_${sw}_idx1`);
      localStorage.removeItem(`rc_mapping_${sw}_idx2`);
    });
    window.location.reload();
  };

  const leftX = 50 + frame.yaw_cmd * 38;
  const leftY = 50 - frame.throttle_cmd * 38;

  const rightX = 50 + frame.roll_cmd * 38;
  const rightY = 50 - frame.pitch_cmd * 38;

  const formationNames = ["OK BAŞI", "V FORMASYONU", "ÇİZGİ"];
  const modeNames = ["SÜRÜ HAREKET", "MANEVRA"];

  return (
    <div className="flysky-card" style={{ position: "relative" }}>
      {/* Header */}
      <div className="flysky-header">
        <div className="flysky-brand">
          <div className="flysky-title">
            <span style={{ color: "#38bdf8" }}>FLY</span>SKY FS-i6X
          </div>
          <div className="flysky-subtitle">
            2.4GHz AFHDS 2A Digital Proportional R/C System
          </div>
        </div>

        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <button
            onClick={() => { setCalibOpen(true); setStep(0); }}
            style={{
              padding: "6px 12px",
              background: "#0284c7",
              color: "#fff",
              border: "none",
              borderRadius: "4px",
              fontWeight: 600,
              cursor: "pointer",
              fontSize: "12px",
            }}
          >
            ⚡ TÜM ŞALTERLERİ SİNYAL ÖĞREN
          </button>

          <div
            className={
              "flysky-status-badge " +
              (frame.connected
                ? "flysky-status-badge--connected"
                : "flysky-status-badge--simulated")
            }
          >
            <div
              className={
                "flysky-led " +
                (frame.connected ? "flysky-led--green" : "flysky-led--blue")
              }
            />
            {frame.connected
              ? `BAĞLI: ${frame.pad_id?.substring(0, 18)}...`
              : "DONANIM ALGILANDI (Sanal Mod)"}
          </div>
        </div>
      </div>

      {/* Full 4-Switch Calibration Modal */}
      {calibOpen && (
        <div
          style={{
            position: "absolute",
            top: 0, left: 0, right: 0, bottom: 0,
            background: "rgba(15, 23, 42, 0.96)",
            zIndex: 100,
            borderRadius: "12px",
            padding: "24px",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            color: "#f8fafc",
          }}
        >
          <h3 style={{ color: "#38bdf8", marginBottom: "8px" }}>
            🛠️ TÜM ŞALTERLER İÇİN SİNYAL ÖĞRENME (SwA, SwB, SwC, SwD)
          </h3>

          {step === 0 && (
            <div style={{ textAlign: "center", maxWidth: "520px" }}>
              <p style={{ marginBottom: "16px", lineHeight: 1.5 }}>
                Bu sihirbaz sırasıyla <strong>SwA, SwB, SwC ve SwD</strong> şalterlerini hareket ettirmenizi isteyecek ve kumandanızın tüm düğmelerini kusursuz öğrenecektir.
              </p>
              <button
                onClick={handleStepNext}
                style={{ padding: "10px 24px", background: "#10b981", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}
              >
                1. ADIMLA BAŞLAT ▶
              </button>
            </div>
          )}

          {/* SwA Step */}
          {step === 1 && (
            <div style={{ textAlign: "center", maxWidth: "500px" }}>
              <h4 style={{ color: "#fbbf24", marginBottom: "8px" }}>1. ADIM: SwA (Emniyet) Şalteri</h4>
              <p style={{ marginBottom: "16px" }}>Lütfen <strong>SwA (Emniyet)</strong> şalterini <strong>YUKARI (KİLİTLİ)</strong> konumuna getirin.</p>
              <button onClick={handleStepNext} style={{ padding: "10px 24px", background: "#3b82f6", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>YUKARI KAYDET ▶</button>
            </div>
          )}
          {step === 2 && (
            <div style={{ textAlign: "center", maxWidth: "500px" }}>
              <h4 style={{ color: "#fbbf24", marginBottom: "8px" }}>1. ADIM (Devam): SwA (Emniyet) Şalteri</h4>
              <p style={{ marginBottom: "16px" }}>Şimdi <strong>SwA (Emniyet)</strong> şalterini <strong>AŞAĞI (AKTİF)</strong> konumuna getirin.</p>
              <button onClick={handleStepNext} style={{ padding: "10px 24px", background: "#3b82f6", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>AŞAĞI KAYDET ▶</button>
            </div>
          )}

          {/* SwB Step */}
          {step === 3 && (
            <div style={{ textAlign: "center", maxWidth: "500px" }}>
              <h4 style={{ color: "#fbbf24", marginBottom: "8px" }}>2. ADIM: SwB (Mod) Şalteri</h4>
              <p style={{ marginBottom: "16px" }}>Lütfen <strong>SwB (Mod)</strong> şalterini <strong>YUKARI (HAREKET)</strong> konumuna getirin.</p>
              <button onClick={handleStepNext} style={{ padding: "10px 24px", background: "#3b82f6", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>YUKARI KAYDET ▶</button>
            </div>
          )}
          {step === 4 && (
            <div style={{ textAlign: "center", maxWidth: "500px" }}>
              <h4 style={{ color: "#fbbf24", marginBottom: "8px" }}>2. ADIM (Devam): SwB (Mod) Şalteri</h4>
              <p style={{ marginBottom: "16px" }}>Şimdi <strong>SwB (Mod)</strong> şalterini <strong>AŞAĞI (MANEVRA)</strong> konumuna getirin.</p>
              <button onClick={handleStepNext} style={{ padding: "10px 24px", background: "#3b82f6", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>AŞAĞI KAYDET ▶</button>
            </div>
          )}

          {/* SwC Step (3-pos) */}
          {step === 5 && (
            <div style={{ textAlign: "center", maxWidth: "500px" }}>
              <h4 style={{ color: "#fbbf24", marginBottom: "8px" }}>3. ADIM: SwC (Formasyon) Şalteri</h4>
              <p style={{ marginBottom: "16px" }}>Lütfen <strong>SwC (Formasyon)</strong> şalterini <strong>EN YUKARI (OK BAŞI)</strong> konumuna getirin.</p>
              <button onClick={handleStepNext} style={{ padding: "10px 24px", background: "#3b82f6", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>EN YUKARI KAYDET ▶</button>
            </div>
          )}
          {step === 6 && (
            <div style={{ textAlign: "center", maxWidth: "500px" }}>
              <h4 style={{ color: "#fbbf24", marginBottom: "8px" }}>3. ADIM (Devam): SwC (Formasyon) Şalteri</h4>
              <p style={{ marginBottom: "16px" }}>Şimdi <strong>SwC (Formasyon)</strong> şalterini <strong>ORTA (V FORMASYONU)</strong> konumuna getirin.</p>
              <button onClick={handleStepNext} style={{ padding: "10px 24px", background: "#3b82f6", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>ORTA KONUMU KAYDET ▶</button>
            </div>
          )}
          {step === 7 && (
            <div style={{ textAlign: "center", maxWidth: "500px" }}>
              <h4 style={{ color: "#fbbf24", marginBottom: "8px" }}>3. ADIM (Devam): SwC (Formasyon) Şalteri</h4>
              <p style={{ marginBottom: "16px" }}>Şimdi <strong>SwC (Formasyon)</strong> şalterini <strong>EN AŞAĞI (ÇİZGİ)</strong> konumuna getirin.</p>
              <button onClick={handleStepNext} style={{ padding: "10px 24px", background: "#3b82f6", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>EN AŞAĞI KAYDET ▶</button>
            </div>
          )}

          {/* SwD Step */}
          {step === 8 && (
            <div style={{ textAlign: "center", maxWidth: "500px" }}>
              <h4 style={{ color: "#fbbf24", marginBottom: "8px" }}>4. ADIM: SwD (Kalkış / İniş) Şalteri</h4>
              <p style={{ marginBottom: "16px" }}>Lütfen <strong>SwD (Kalkış/İniş)</strong> şalterini <strong>YUKARI (İNİŞ)</strong> konumuna getirin.</p>
              <button onClick={handleStepNext} style={{ padding: "10px 24px", background: "#3b82f6", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>YUKARI KAYDET ▶</button>
            </div>
          )}
          {step === 9 && (
            <div style={{ textAlign: "center", maxWidth: "500px" }}>
              <h4 style={{ color: "#fbbf24", marginBottom: "8px" }}>4. ADIM (Devam): SwD (Kalkış / İniş) Şalteri</h4>
              <p style={{ marginBottom: "16px" }}>Şimdi <strong>SwD (Kalkış/İniş)</strong> şalterini <strong>AŞAĞI (KALKIŞ)</strong> konumuna getirin.</p>
              <button onClick={handleStepNext} style={{ padding: "10px 24px", background: "#3b82f6", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>AŞAĞI KAYDET ▶</button>
            </div>
          )}

          {/* Finished Step */}
          {step === 10 && (
            <div style={{ textAlign: "center", maxWidth: "520px" }}>
              <h4 style={{ color: "#4ade80", marginBottom: "12px" }}>🎉 TÜM ŞALTERLER BAŞARIYLA ÖĞRENİLDİ!</h4>
              <div style={{ background: "#1e293b", padding: "12px", borderRadius: "8px", marginBottom: "16px", textAlign: "left", fontSize: "13px" }}>
                <p><strong>SwA (Emniyet):</strong> {swAResult?.type.toUpperCase()} #{swAResult?.idx}</p>
                <p><strong>SwB (Mod):</strong> {swBResult?.type.toUpperCase()} #{swBResult?.idx}</p>
                <p><strong>SwC (Formasyon):</strong> {swCResult?.type.toUpperCase()} #{swCResult?.idx1} / #{swCResult?.idx2}</p>
                <p><strong>SwD (Kalkış):</strong> {swDResult?.type.toUpperCase()} #{swDResult?.idx}</p>
              </div>
              <div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
                <button onClick={saveCalibration} style={{ padding: "10px 24px", background: "#10b981", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}>KAYDET VE UYGULA ✓</button>
                <button onClick={() => setCalibOpen(false)} style={{ padding: "10px 16px", background: "#64748b", color: "#fff", border: "none", borderRadius: "6px", cursor: "pointer" }}>İPTAL</button>
              </div>
            </div>
          )}

          <button onClick={() => setCalibOpen(false)} style={{ position: "absolute", top: "16px", right: "16px", background: "none", border: "none", color: "#94a3b8", fontSize: "18px", cursor: "pointer" }}>✕</button>
        </div>
      )}

      {/* Switches Bar (SwA, SwB, SwC, SwD) */}
      <div className="flysky-switches-bar">
        {/* SwA: Deadman / Emniyet Switch */}
        <div className="flysky-switch-item" title="SwA: Emniyet Kilidi (Deadman)">
          <span className="flysky-switch-label">SwA (Emniyet)</span>
          <div className="flysky-toggle-btn">
            <div
              className={
                "flysky-toggle-lever " +
                (frame.swA
                  ? "flysky-toggle-lever--down"
                  : "flysky-toggle-lever--up")
              }
            />
          </div>
          <span
            className={
              "flysky-switch-val " +
              (frame.swA
                ? "flysky-switch-val--active"
                : "flysky-switch-val--alert")
            }
          >
            {frame.swA ? "BASTIK (OK)" : "PASİF (HOLD)"}
          </span>
        </div>

        {/* SwB: Mode Selection */}
        <div
          className="flysky-switch-item"
          onClick={() => onModeChange(mode === 0 ? 1 : 0)}
          title="SwB: Mod Değiştir (Tıkla veya Kumandadan Değiştir)"
        >
          <span className="flysky-switch-label">SwB (Mod)</span>
          <div className="flysky-toggle-btn">
            <div
              className={
                "flysky-toggle-lever " +
                ((frame.connected ? frame.swB : mode === 1)
                  ? "flysky-toggle-lever--down"
                  : "flysky-toggle-lever--up")
              }
            />
          </div>
          <span className="flysky-switch-val flysky-switch-val--active">
            {(frame.connected ? frame.swB : mode === 1) ? "MANEVRA" : "HAREKET"}
          </span>
        </div>

        {/* SwC: Formation Selection (3-pos) */}
        <div
          className="flysky-switch-item"
          onClick={() => onFormationChange((formation + 1) % 3)}
          title="SwC: Formasyon Seç (Tıkla veya Kumandadan Değiştir)"
        >
          <span className="flysky-switch-label">SwC (Formasyon)</span>
          <div className="flysky-toggle-btn">
            <div
              className={
                "flysky-toggle-lever " +
                ((frame.connected ? frame.swC : formation) === 0
                  ? "flysky-toggle-lever--up"
                  : (frame.connected ? frame.swC : formation) === 2
                  ? "flysky-toggle-lever--down"
                  : "flysky-toggle-lever--mid")
              }
            />
          </div>
          <span className="flysky-switch-val flysky-switch-val--active">
            {formationNames[frame.connected ? frame.swC : formation]}
          </span>
        </div>

        {/* SwD: Takeoff / Land */}
        <div className="flysky-switch-item" title="SwD: Kalkış / İniş Switch">
          <span className="flysky-switch-label">SwD (Kalkış)</span>
          <div className="flysky-toggle-btn">
            <div
              className={
                "flysky-toggle-lever " +
                (frame.swD
                  ? "flysky-toggle-lever--down"
                  : "flysky-toggle-lever--up")
              }
            />
          </div>
          <span className="flysky-switch-val">
            {frame.swD ? "KALKIŞ" : "İNİŞ/HOLD"}
          </span>
        </div>
      </div>

      {/* Backlit LCD Telemetry Display */}
      <div className="flysky-lcd-screen">
        <div
          className="flysky-lcd-header"
          style={{ cursor: "pointer" }}
          onClick={onTogglePublish}
          title="ROS 2 Yayınını Başlat/Durdur"
        >
          <span>
            STATUS: {publishing ? "ROS 2 PUBLISHING (Durdur)" : "IDLE (Başlat)"}
          </span>
          <span>TX: 6.1V | RX: 5.0V</span>
          <span>PKTS: {pubCount}</span>
        </div>
        <div className="flysky-lcd-grid">
          <div className="flysky-lcd-cell">
            <span className="flysky-lcd-label">AKTİF MOD</span>
            <span className="flysky-lcd-val">{modeNames[mode]}</span>
          </div>
          <div className="flysky-lcd-cell">
            <span className="flysky-lcd-label">FORMASYON</span>
            <span className="flysky-lcd-val">{formationNames[formation]}</span>
          </div>
          <div className="flysky-lcd-cell">
            <span className="flysky-lcd-label">EMNİYET (DEADMAN)</span>
            <span
              className="flysky-lcd-val"
              style={{
                color: frame.deadman_pressed ? "#6ee7b7" : "#f87171",
              }}
            >
              {frame.deadman_pressed ? "AKTİF (R1)" : "HOLD (KİLİTLİ)"}
            </span>
          </div>
          <div className="flysky-lcd-cell">
            <span className="flysky-lcd-label">THROTTLE (GAZ)</span>
            <span className="flysky-lcd-val">
              {((frame.throttle_cmd + 1) * 50).toFixed(0)}%
            </span>
          </div>
          <div className="flysky-lcd-cell">
            <span className="flysky-lcd-label">YAW (SAPMA)</span>
            <span className="flysky-lcd-val">
              {(frame.yaw_cmd * 100).toFixed(0)}%
            </span>
          </div>
          <div className="flysky-lcd-cell">
            <span className="flysky-lcd-label">PITCH / ROLL</span>
            <span className="flysky-lcd-val">
              {(frame.pitch_cmd * 100).toFixed(0)}% / {(frame.roll_cmd * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      </div>

      {/* Dual Gimbals (Sticks) */}
      <div className="flysky-gimbals-row">
        {/* Left Gimbal: Throttle & Yaw */}
        <div className="flysky-gimbal-box">
          <div className="flysky-gimbal-title">SOL STICK (Yaw / Throttle)</div>
          <div className="flysky-gimbal-ring">
            <div className="flysky-gimbal-crosshair-h" />
            <div className="flysky-gimbal-crosshair-v" />
            <div
              className="flysky-stick-head"
              style={{
                left: `${leftX}%`,
                top: `${leftY}%`,
              }}
            />
          </div>
          <div className="flysky-stick-coords">
            <div className="flysky-stick-coord-item">
              Yaw: <span>{frame.yaw_cmd.toFixed(2)}</span>
            </div>
            <div className="flysky-stick-coord-item">
              Thr: <span>{frame.throttle_cmd.toFixed(2)}</span>
            </div>
          </div>
        </div>

        {/* Right Gimbal: Pitch & Roll */}
        <div className="flysky-gimbal-box">
          <div className="flysky-gimbal-title">SAĞ STICK (Roll / Pitch)</div>
          <div className="flysky-gimbal-ring">
            <div className="flysky-gimbal-crosshair-h" />
            <div className="flysky-gimbal-crosshair-v" />
            <div
              className="flysky-stick-head"
              style={{
                left: `${rightX}%`,
                top: `${rightY}%`,
              }}
            />
          </div>
          <div className="flysky-stick-coords">
            <div className="flysky-stick-coord-item">
              Roll: <span>{frame.roll_cmd.toFixed(2)}</span>
            </div>
            <div className="flysky-stick-coord-item">
              Pitch: <span>{frame.pitch_cmd.toFixed(2)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Scrollable Diagnostics Panel Under Stick Indicators */}
      <div className="flysky-diag-panel">
        <div className="flysky-diag-header" style={{ display: "flex", justifyContent: "space-between" }}>
          <span>DONANIM TEŞHİS PANELİ (RAW SIGNALS)</span>
          <button
            onClick={resetCalibration}
            style={{ background: "#ef4444", color: "#fff", border: "none", borderRadius: "3px", padding: "2px 8px", cursor: "pointer", fontSize: "10px" }}
          >
            KALİBRASYONU SIFIRLA
          </button>
        </div>
        <div className="flysky-diag-body">
          {frame.all_axes && (
            <div className="flysky-diag-row" style={{ color: "#60a5fa" }}>
              <strong>TÜM EKSENLER ({frame.all_axes.length}):</strong>{" "}
              [{frame.all_axes.map((v, i) => `${i}:${v.toFixed(2)}`).join(" | ")}]
            </div>
          )}
          {frame.raw_btns && (
            <div className="flysky-diag-row" style={{ color: "#fbbf24" }}>
              <strong>BASILI BUTONLAR:</strong>{" "}
              [{frame.raw_btns.length > 0 ? frame.raw_btns.join(", ") : "Hiçbiri"}]
            </div>
          )}
          {frame.raw_axes && (
            <div className="flysky-diag-row" style={{ color: "#34d399" }}>
              <strong>CH5..8 DİZİSİ:</strong> [{frame.raw_axes.map(v => v.toFixed(2)).join(" | ")}]
            </div>
          )}
          <div className="flysky-diag-row" style={{ color: frame.connected ? "#4ade80" : "#f87171" }}>
            <strong>BAĞLANTI DURUMU:</strong> {frame.connected ? `BAĞLI (${frame.pad_id})` : "BAĞLANTI BEKLENİYOR / SIMULATOR"}
          </div>
        </div>
      </div>
    </div>
  );
}
