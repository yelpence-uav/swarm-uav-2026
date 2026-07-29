import type { GamepadFrame } from "../../services/gamepad";
import "./FlySkyController.css";

interface FlySkyControllerProps {
  frame: GamepadFrame;
  publishing: boolean;
  pubCount: number;
  mode: number;            // 0=Movement, 1=Maneuver
  formation: number;       // 0=OkBaşı, 1=Formasyonsuz, 2=Çizgi
  onModeChange: (m: number) => void;
  onFormationChange: (f: number) => void;
  onTogglePublish: () => void;
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
  const leftX = 50 + frame.yaw_cmd * 38;
  const leftY = 50 - frame.throttle_cmd * 38;

  const rightX = 50 + frame.roll_cmd * 38;
  const rightY = 50 - frame.pitch_cmd * 38;

  const formationNames = ["OK BAŞI", "FORMASYONSUZ", "ÇİZGİ"];
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

      {/* Switches Bar (SwA, SwB, SwC, SwD) */}
      <div className="flysky-switches-bar">
        {/* SwA: Deadman / Emniyet Switch */}
        <div className="flysky-switch-item" title="SwA: Emniyet Kilidi (Yukarı: Kilitli, Aşağı: Açık)">
          <span className="flysky-switch-label">SwA (Emniyet)</span>
          <div className="flysky-toggle-btn">
            <div
              className={
                "flysky-toggle-lever " +
                (frame.swA
                  ? "flysky-toggle-lever--up"
                  : "flysky-toggle-lever--down")
              }
            />
          </div>
          <span
            className={
              "flysky-switch-val " +
              (frame.swA
                ? "flysky-switch-val--alert"
                : "flysky-switch-val--active")
            }
          >
            {frame.swA ? "YUKARI (KİLİTLİ)" : "AŞAĞI (AÇIK)"}
          </span>
        </div>
      </div>

      {/* Main Controls Section with Mist Overlay when SwA is Locked */}
      <div className="flysky-controls-container">
        {frame.swA && (
          <div className="flysky-locked-overlay">
            <div className="flysky-locked-badge">
              <span>🔒</span> EMNİYET KİLİTLİ (SwA YUKARIDA)
            </div>
            <div className="flysky-locked-subtext">
              Sürü komut akışına kapalıdır. Mod ve formasyon komutlarını çalıştırmak için <strong>SwA şalterini AŞAĞI</strong> indirin.
            </div>
          </div>
        )}

        <div className="flysky-switches-bar">
          {/* SwB: Mode Selection */}
          <div
            className="flysky-switch-item"
            onClick={() => !frame.swA && onModeChange(mode === 0 ? 1 : 0)}
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
            onClick={() => !frame.swA && onFormationChange((formation + 1) % 3)}
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

      {/* Dual Gimbals (Sticks) - Placed directly below switches */}
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

      {/* Backlit Green LCD Telemetry Display (Moved below sticks) */}
      <div className="flysky-lcd-screen" style={{ marginTop: "12px" }}>
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

      {/* Scrollable Diagnostics Panel Under Stick Indicators */}
      <div className="flysky-diag-panel">
        <div className="flysky-diag-header">
          <span>DONANIM TEŞHİS PANELİ (RAW SIGNALS)</span>
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
    </div>
  );
}
