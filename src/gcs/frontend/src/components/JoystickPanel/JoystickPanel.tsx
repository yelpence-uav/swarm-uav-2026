import { useEffect, useRef, useState } from "react";
import {
  CommandFailure,
  SWARM_CONTROL_MODE,
  SWARM_FORMATION,
  swarmApi,
  missionApi,
  type SwarmControlBody,
} from "../../services/api";
import { readGamepad, type GamepadFrame } from "../../services/gamepad";
import { FlySkyController } from "./FlySkyController";
import "./JoystickPanel.css";

/**
 * Görev 2 - Yarı Otonom Sürü Kontrolü için joystick paneli (FlySky FS-i6X Kumanda Sanal Modülü).
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
    swA: false,
    swB: false,
    swC: 1,
    swD: false,
    vrA: 0,
    vrB: 0,
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
  const lastSwDRef = useRef<boolean>(false);

  // Frame okuma - animasyon frame'inde sürekli çek (UI rendering için).
  useEffect(() => {
    let raf = 0;
    const loop = () => {
      const g = readGamepad();
      setFrame(g);
      if (g.connected) {
        // Sync SwD physical switch (Kalkış / İniş)
        if (g.swD !== lastSwDRef.current) {
          const isTakeoff = g.swD; // true = KALKIŞ (Aşağı), false = İNİŞ (Yukarı)
          lastSwDRef.current = g.swD;
          missionApi
            .trigger({
              mission_id: 2,
              command: isTakeoff ? 1 : 6,
              team_id: "team_1",
            })
            .catch((err: unknown) => {
              console.warn("Mission trigger error from SwD switch:", err);
            });
        }

        // Sync SwB physical switch (Kanal 6 / axes[5]) -> Mode
        const targetMode = g.swB ? SWARM_CONTROL_MODE.MANEUVER : SWARM_CONTROL_MODE.SWARM_MOVEMENT;
        setMode((prev) => (prev !== targetMode ? targetMode : prev));

        // Sync SwC physical switch (Kanal 7 / axes[6]) -> Formation
        if (g.swC !== undefined && g.swC !== null) {
          setFormation((prev) => {
            if (prev !== g.swC) {
              formationRequestedRef.current = true;
              return g.swC;
            }
            return prev;
          });
        }
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  // Publish loop - sabit hız (30 Hz). enabled + publishing toggle'ına bakar.
  useEffect(() => {
    if (!enabled || !publishing) return;
    let alive = true;

    const tick = async () => {
      if (!alive) return;
      const live = readGamepad();
      seqRef.current += 1;
      const body: SwarmControlBody = {
        sequence_num: seqRef.current,
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
        formationRequestedRef.current = false;
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

  const handleFormationChange = (f: number) => {
    setFormation(f);
    formationRequestedRef.current = true;
  };

  return (
    <section className={"joystick-panel " + (enabled ? "" : "joystick-panel--disabled")}>
      <div className="joystick-panel__header">
        <span className="joystick-panel__title">KUMANDA ARAYÜZÜ (FlySky FS-i6X)</span>
        {!enabled && (
          <span className="joystick-panel__hint">
            Görev 2 - Yarı Otonom modunu seç
          </span>
        )}
        {enabled && (
          <button
            className={
              "joystick-panel__publish " +
              (publishing ? "joystick-panel__publish--on" : "")
            }
            onClick={togglePublishing}
          >
            {publishing ? "■ Yayını Durdur" : "▶ ROS 2 Yayını Başlat"}
          </button>
        )}
      </div>

      <FlySkyController
        frame={frame}
        publishing={publishing}
        pubCount={pubCount}
        mode={mode}
        formation={formation}
        onModeChange={setMode}
        onFormationChange={handleFormationChange}
        onTogglePublish={togglePublishing}
      />

      {errorMsg && <div className="joystick-panel__error">{errorMsg}</div>}
    </section>
  );
}
