import { useEffect, useState } from "react";

import { AlertList } from "./components/AlertSystem/AlertList";
import { MapView } from "./components/Map/Map";
import { MissionControl } from "./components/MissionControl/MissionControl";
import { StatusBar } from "./components/StatusBar/StatusBar";
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

const EMPTY_PAYLOAD: TelemetryPayload = { drones: [], alerts: [] };

export default function App() {
  const [payload, setPayload] = useState<TelemetryPayload>(EMPTY_PAYLOAD);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");

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

  return (
    <div className="app">
      <StatusBar status={status} drones={payload.drones} />
      <MissionControl anyConnected={anyConnected} />
      <main className="app__main">
        <div className="app__map">
          <MapView snapshot={payload.drones} />
          <AlertList alerts={payload.alerts} />
        </div>
        <div className="app__panel">
          <TelemetryPanel drones={payload.drones} />
        </div>
      </main>
    </div>
  );
}
