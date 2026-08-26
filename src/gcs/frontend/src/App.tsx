import { useEffect, useMemo, useState } from "react";

import { AlertList } from "./components/AlertSystem/AlertList";
import { AppHeader } from "./components/AppShell/AppHeader";
import { DroneControlPanel } from "./components/DroneControlPanel/DroneControlPanel";
import { JoystickPanel } from "./components/JoystickPanel/JoystickPanel";
import { MapView } from "./components/Map/Map";
import { KosucuPanel } from "./components/KosucuPanel/KosucuPanel";
import { MissionControl } from "./components/MissionControl/MissionControl";
import { MissionPanel } from "./components/MissionPanel/MissionPanel";
import { QRPanel } from "./components/QRPanel/QRPanel";
import { QRPositionForm } from "./components/QRPositionForm/QRPositionForm";
import { SettingsPanel } from "./components/SettingsPanel/SettingsPanel";
import { SwarmStatePanel } from "./components/SwarmStatePanel/SwarmStatePanel";
import { TelemetryPanel } from "./components/TelemetryPanel/TelemetryPanel";
import { useQRPositions } from "./hooks/useQRPositions";
import { useTheme } from "./hooks/useTheme";
import { MISSION_ID, guided, params as paramsApi } from "./services/api";
import type { FlightParams } from "./services/api";
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
  rtk: null,
  mesafeler: [],
};

const DEFAULT_PARAMS: FlightParams = {
  default_altitude_m: 5,
  default_speed_ms: 3,
  min_nav_altitude_m: 2,
};

export default function App() {
  useTheme();

  const qr = useQRPositions();

  const [payload, setPayload] = useState<TelemetryPayload>(EMPTY_PAYLOAD);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [selectedMissionId, setSelectedMissionId] = useState<number>(
    MISSION_ID.DYNAMIC_SWARM,
  );

  // Seçili drone (kontrol paneli), ayarlar modalı ve uçuş parametreleri.
  const [selectedDroneId, setSelectedDroneId] = useState<number | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [flightParams, setFlightParams] = useState<FlightParams>(DEFAULT_PARAMS);

  useEffect(() => {
    fetch(SNAPSHOT_URL)
      .then((r) => (r.ok ? r.json() : EMPTY_PAYLOAD))
      .then((data: TelemetryPayload) => setPayload(data))
      .catch(() => undefined);

    paramsApi.get().then(setFlightParams).catch(() => undefined);

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

  const selectedDrone = payload.drones.find(
    (d) => d.drone_id === selectedDroneId,
  );

  const joystickVisible =
    selectedMissionId === MISSION_ID.SEMI_AUTONOMOUS ||
    activeMission === "semi_autonomous";

  return (
    <div className={`app ${joystickVisible ? "app--joystick" : ""}`}>
      <AppHeader
        status={status}
        drones={payload.drones}
        swarmState={payload.swarm_state}
        rtk={payload.rtk ?? null}
        selectedMissionId={selectedMissionId}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      <main className="app__map-area">
        <MapView
          snapshot={payload.drones}
          qrPositions={qr.positions}
          activeQrId={payload.swarm_state?.current_qr_id ?? 0}
          guidedEnabled={!isSimMode && !missionActive}
          onGoto={(id, target) => guided.goto(id, target)}
          params={flightParams}
        />
        <AlertList alerts={payload.alerts} />
      </main>

      {joystickVisible && (
        <aside className="app__joystick">
          <JoystickPanel enabled={true} />
        </aside>
      )}

      <aside className="app__sidebar">
        {selectedDroneId != null ? (
          <DroneControlPanel
            drone={selectedDrone}
            guidedMode={!isSimMode}
            commandsDisabled={missionActive}
            params={flightParams}
            onClose={() => setSelectedDroneId(null)}
          />
        ) : (
          <>
            <KosucuPanel />
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
              <MissionControl anyConnected={anyConnected} disabled={missionActive} />
            )}
          </>
        )}
      </aside>

      <footer className="app__drone-strip">
        <TelemetryPanel
          drones={payload.drones}
          mesafeler={payload.mesafeler ?? []}
          selectedDroneId={selectedDroneId}
          onSelectDrone={(id) =>
            setSelectedDroneId((cur) => (cur === id ? null : id))
          }
        />
      </footer>

      {settingsOpen && (
        <SettingsPanel
          params={flightParams}
          onSaved={setFlightParams}
          onClose={() => setSettingsOpen(false)}
        />
      )}
    </div>
  );
}
