import { useEffect, useRef, useState } from "react";
import {
  CommandFailure,
  SWARM_CONTROL_MODE,
  SWARM_FORMATION,
  swarmApi,
  type SwarmControlBody,
} from "../../services/api";
import { readGamepad, type GamepadFrame } from "../../services/gamepad";
import "./JoystickPanel.css";

/**
 * Görev 2 — Yarı Otonom Sürü Kontrolü için joystick paneli.
 *
 * Gamepad API'den okur (Xbox/PS), 30 Hz hızında SwarmControlCommand POST'lar.
 * Deadman switch (R1 default) basılı değilken backend'e command_valid=false
 * gönderilir → drone HOLD'a geçer (kontrat kuralı).
 */

const PUBLISH_HZ = 30;
const PUBLISH_MS = 1000 / PUBLISH_HZ;

interface JoystickPanelProps {
  enabled: boolean;   // sadece Görev 2 modundayken true geçilir
}

export function JoystickPanel({ enabled }: JoystickPanelProps) {
  const [frame, setFrame] = useState<GamepadFrame>({
    connected: false,
    pad_index: null,
    pad_id: null,
    pitch_cmd: 0,
    roll_cmd: 0,
    yaw_cmd: 0,
    throttle_cmd: 0,
    deadman_pressed: false,
    emergency_button: false,
  });
  const [mode, setMode] = useState<number>(SWARM_CONTROL_MODE.SWARM_MOVEMENT);
  const [formation, setFormation] = useState<number>(SWARM_FORMATION.V);
  const [publishing, setPublishing] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [pubCount, setPubCount] = useState<number>(0);

  const seqRef = useRef<number>(0);
  const formationRequestedRef = useRef<boolean>(false);

  // Frame okuma — animasyon frame'inde sürekli çek (UI rendering için).
  useEffect(() => {
    let raf = 0;
    const loop = () => {
      setFrame(readGamepad());
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  // Publish loop — sabit hız (30 Hz). enabled + publishing toggle'ına bakar.
  useEffect(() => {
    if (!enabled || !publishing) return;
    let alive = true;

    const tick = async () => {
      if (!alive) return;
      const live = readGamepad();
      seqRef.current += 1;
      const body: SwarmControlBody = {
        sequence_num: seqRef.current,
        // Kontrat (SwarmControlCommand.msg §6-9): command_valid AND deadman_pressed
        // ikisi de true olmadan drone'lar HOLD'a düşmeli. Sadece pad bağlantısı
        // yetmez — pilot R1'i bıraktığında hareket komutu iptal edilmeli.
        command_valid: live.connected && live.deadman_pressed,
        deadman_pressed: live.deadman_pressed,
        deadman_timeout_s: 0.5,
        mode,
        pitch_cmd: live.pitch_cmd,
        roll_cmd: live.roll_cmd,
        yaw_cmd: live.yaw_cmd,
        throttle_cmd: live.throttle_cmd,
        emergency_stop: live.emergency_button,
        formation_change_requested: formationRequestedRef.current,
        requested_formation: formation,
        source_module: "gcs-joystick",
      };
      try {
        await swarmApi.control(body);
        if (alive) setPubCount((c) => c + 1);
        formationRequestedRef.current = false;  // tek seferlik flag
      } catch (e) {
        if (!alive) return;
        const msg =
          e instanceof CommandFailure
            ? `HTTP ${e.http_status}: ${e.message}`
            : (e as Error).message;
        setErrorMsg(msg);
      }
    };

    const id = window.setInterval(tick, PUBLISH_MS);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [enabled, publishing, mode, formation]);

  const togglePublishing = () => {
    setErrorMsg(null);
    setPublishing((p) => !p);
  };

  const requestFormationChange = () => {
    formationRequestedRef.current = true;
  };

  return (
    <section className={"joystick-panel " + (enabled ? "" : "joystick-panel--disabled")}>
      <div className="joystick-panel__header">
        <span className="joystick-panel__title">JOYSTICK (Görev 2)</span>
        {!enabled && (
          <span className="joystick-panel__hint">
            Görev 2 — Yarı Otonom modunu seç
          </span>
        )}
        {enabled && !frame.connected && (
          <span className="joystick-panel__hint">Gamepad bağla</span>
        )}
        {enabled && frame.connected && (
          <span className="joystick-panel__pad-id">{frame.pad_id}</span>
        )}
      </div>

      <div className="joystick-panel__sticks">
        <Stick label="Sol stick (pitch/roll)" x={frame.roll_cmd} y={-frame.pitch_cmd} />
        <Stick label="Sağ stick (yaw/throttle)" x={frame.yaw_cmd} y={-frame.throttle_cmd} />
      </div>

      <div className="joystick-panel__row">
        <label>
          Mod:
          <select value={mode} onChange={(e) => setMode(Number(e.target.value))} disabled={!enabled}>
            <option value={SWARM_CONTROL_MODE.SWARM_MOVEMENT}>Sürü Hareket</option>
            <option value={SWARM_CONTROL_MODE.MANEUVER}>Manevra</option>
          </select>
        </label>
        <label>
          Formasyon:
          <select
            value={formation}
            onChange={(e) => setFormation(Number(e.target.value))}
            disabled={!enabled}
          >
            <option value={SWARM_FORMATION.OKBASI}>Ok Başı</option>
            <option value={SWARM_FORMATION.V}>V</option>
            <option value={SWARM_FORMATION.CIZGI}>Çizgi</option>
          </select>
        </label>
        <button
          onClick={requestFormationChange}
          disabled={!enabled || !publishing}
          title="Formasyon değişikliği bayrağını bir sonraki frame'de gönder"
        >
          ↻ Formasyonu Uygula
        </button>
      </div>

      <div className="joystick-panel__row">
        <button
          className={
            "joystick-panel__publish " +
            (publishing ? "joystick-panel__publish--on" : "")
          }
          onClick={togglePublishing}
          disabled={!enabled}
        >
          {publishing ? "■ Yayını Durdur" : "▶ Yayını Başlat"}
        </button>
        <span className="joystick-panel__deadman">
          Deadman (R1):{" "}
          <strong className={frame.deadman_pressed ? "ok" : "off"}>
            {frame.deadman_pressed ? "BASILI" : "BIRAK"}
          </strong>
        </span>
        <span className="joystick-panel__counter">
          Yayın: {pubCount} pkt
        </span>
      </div>

      {errorMsg && <div className="joystick-panel__error">{errorMsg}</div>}
    </section>
  );
}

function Stick({ label, x, y }: { label: string; x: number; y: number }) {
  // x,y ∈ [-1,+1] — SVG'de ortadan offset.
  const cx = 50 + x * 40;
  const cy = 50 + y * 40;
  return (
    <div className="joystick-panel__stick">
      <span className="joystick-panel__stick-label">{label}</span>
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="45" fill="#0f172a" stroke="#334155" />
        <line x1="50" y1="5" x2="50" y2="95" stroke="#1e293b" />
        <line x1="5" y1="50" x2="95" y2="50" stroke="#1e293b" />
        <circle cx={cx} cy={cy} r="8" fill="#3b82f6" />
      </svg>
      <span className="joystick-panel__stick-coord">
        ({x.toFixed(2)}, {(-y).toFixed(2)})
      </span>
    </div>
  );
}
