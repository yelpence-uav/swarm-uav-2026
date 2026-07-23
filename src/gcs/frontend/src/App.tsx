import { useEffect, useMemo, useState } from "react";

import { AlertList } from "./components/AlertSystem/AlertList";
import { AppHeader } from "./components/AppShell/AppHeader";
import { JoystickPanel } from "./components/JoystickPanel/JoystickPanel";
import { MapView } from "./components/Map/Map";
import { MissionControl } from "./components/MissionControl/MissionControl";
import { MissionPanel } from "./components/MissionPanel/MissionPanel";
import { QRPanel } from "./components/QRPanel/QRPanel";
import { QRPositionForm } from "./components/QRPositionForm/QRPositionForm";
import { SwarmStatePanel } from "./components/SwarmStatePanel/SwarmStatePanel";
import { TelemetryPanel } from "./components/TelemetryPanel/TelemetryPanel";
import { useQRPositions } from "./hooks/useQRPositions";
import { useTheme } from "./hooks/useTheme";
import { MISSION_ID } from "./services/api";
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
  qr: null,
};

export default function App() {
  // Tema hook'unu burada bir kez çağırıp data-theme'i set etmesini garantile.
  useTheme();

  // QR konumları — operatör girer, haritada gösterilir, localStorage'da saklanır.
  const qr = useQRPositions();

  const [payload, setPayload] = useState<TelemetryPayload>(EMPTY_PAYLOAD);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  // Görev tipini App seviyesinde tut — joystick paneli görev başlatılmasa
  // bile Görev 2 seçilince görünmeli (pilot kumandayı önceden test eder).
  const [selectedMissionId, setSelectedMissionId] = useState<number>(
    MISSION_ID.DYNAMIC_SWARM,
  );

  useEffect(() => {
    fetch(SNAPSHOT_URL)
      .then((r) => (r.ok ? r.json() : EMPTY_PAYLOAD))
      .then((data: TelemetryPayload) => setPayload(data))
      .catch(() => undefined);

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
  const activeMission = payload.swarm_state?.active_mission ?? "";
  const isSimMode = payload.connection_mode === "mavlink-sim";

  // Joystick paneli: Görev 2 SEÇİLDİYSE (henüz başlamamış olsa da) ya da
  // backend aktif görevi Yarı Otonom olarak raporluyorsa görünür. Operatör
  // başlatma butonuna basmadan önce de joystick'i test edebilmeli.
  const joystickVisible =
    selectedMissionId === MISSION_ID.SEMI_AUTONOMOUS ||
    activeMission === "semi_autonomous";

  return (
    <div className={`app ${joystickVisible ? "app--joystick" : ""}`}>
      <AppHeader
        status={status}
        drones={payload.drones}
        swarmState={payload.swarm_state}
        selectedMissionId={selectedMissionId}
      />

      <main className="app__map-area">
        <MapView
          snapshot={payload.drones}
          qrPositions={qr.positions}
          activeQrId={payload.swarm_state?.current_qr_id ?? 0}
        />
        <AlertList alerts={payload.alerts} />
      </main>

      {joystickVisible && (
        <aside className="app__joystick">
          <JoystickPanel enabled={missionActive} />
        </aside>
      )}

      <aside className="app__sidebar">
        <MissionPanel
          missionActive={missionActive}
          missionId={selectedMissionId}
          onMissionIdChange={setSelectedMissionId}
        />
        <SwarmStatePanel swarmState={payload.swarm_state} />
        <QRPanel qr={payload.qr ?? null} />
        <QRPositionForm
          positions={qr.positions}
          update={qr.update}
          add={qr.add}
          remove={qr.remove}
        />
        {isSimMode && (
          <MissionControl
            anyConnected={anyConnected}
            disabled={missionActive}
          />
        )}
      </aside>

      <footer className="app__drone-strip">
        <TelemetryPanel
          drones={payload.drones}
          commandsDisabled={missionActive}
          showCommands={true}
          guidedMode={!isSimMode}
        />
      </footer>
    </div>
  );
}
