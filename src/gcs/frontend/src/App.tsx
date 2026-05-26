import { useEffect, useMemo, useState } from "react";

import { AlertList } from "./components/AlertSystem/AlertList";
import { JoystickPanel } from "./components/JoystickPanel/JoystickPanel";
import { MapView } from "./components/Map/Map";
import { MissionControl } from "./components/MissionControl/MissionControl";
import { MissionPanel } from "./components/MissionPanel/MissionPanel";
import { StatusBar } from "./components/StatusBar/StatusBar";
import { SwarmStatePanel } from "./components/SwarmStatePanel/SwarmStatePanel";
import { TelemetryPanel } from "./components/TelemetryPanel/TelemetryPanel";
import { TelemetryWS } from "./services/websocket";
import type { ConnectionStatus } from "./services/websocket";
import type { TelemetryPayload } from "./types/telemetry";
import "./App.css";

const WS_URL =
  (import.meta.env.VITE_WS_URL as string | undefined) ??
  `ws://${window.location.hostname}:8000/ws/telemetry`;

const SNAPSHOT_URL = (import.meta.env.VITE_API_URL as string | undefined)
  ? `${import.meta.env.VITE_API_URL}/telemetry/snapshot`
  : `http://${window.location.hostname}:8000/api/telemetry/snapshot`;

const EMPTY_PAYLOAD: TelemetryPayload = {
  drones: [],
  alerts: [],
  swarm_state: null,
};

export default function App() {
  const [payload, setPayload] = useState<TelemetryPayload>(EMPTY_PAYLOAD);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [joystickVisible, setJoystickVisible] = useState<boolean>(false);

  useEffect(() => {
    fetch(SNAPSHOT_URL)
      .then((r) => (r.ok ? r.json() : EMPTY_PAYLOAD))
      .then((data: TelemetryPayload) => setPayload(data))
      .catch(() => {
        // backend henüz ayakta değil — WS reconnect halleder
      });

    const ws = new TelemetryWS(WS_URL);
    const offMsg = ws.onMessage(setPayload);
    const offStatus = ws.onStatus(setStatus);
    ws.connect();

    return () => {
      offMsg();
      offStatus();
      ws.disconnect();
    };
  }, []);

  const anyConnected = payload.drones.some((d) => d.connected);
  const missionActive = useMemo(
    () => payload.swarm_state?.mission_active ?? false,
    [payload.swarm_state],
  );
  // MAVLink yan-yolu butonları (MissionControl, bireysel CommandButtons) sadece
  // dev/sim modunda görünür — yarışmada bunlar şartname §5.1 "müdahale yasak"
  // ihlali sayılır. Production ros2 modunda gizli.
  const isSimMode = payload.connection_mode === "mavlink-sim";

  return (
    <div className="app">
      <StatusBar status={status} drones={payload.drones} />
      <SwarmStatePanel swarmState={payload.swarm_state} />
      <MissionPanel missionActive={missionActive} />
      {isSimMode && (
        <MissionControl
          anyConnected={anyConnected}
          disabled={missionActive}
        />
      )}
      <main className="app__main">
        <div className="app__map">
          <MapView snapshot={payload.drones} />
          <AlertList alerts={payload.alerts} />
        </div>
        <div className="app__panel">
          <TelemetryPanel
            drones={payload.drones}
            commandsDisabled={missionActive}
            showCommands={isSimMode}
          />
        </div>
      </main>
      <button
        className="app__joystick-toggle"
        onClick={() => setJoystickVisible((v) => !v)}
        title="Görev 2 — Yarı Otonom için joystick paneli"
      >
        {joystickVisible ? "▼ Joystick gizle" : "▲ Joystick göster (Görev 2)"}
      </button>
      {joystickVisible && <JoystickPanel enabled={true} />}
    </div>
  );
}
