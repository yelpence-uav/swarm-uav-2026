import { useEffect, useState } from "react";

import { MapView } from "./components/Map/Map";
import { StatusBar } from "./components/StatusBar/StatusBar";
import { TelemetryWS } from "./services/websocket";
import type { ConnectionStatus } from "./services/websocket";
import type { TelemetrySnapshot } from "./types/telemetry";
import "./App.css";

const WS_URL =
  (import.meta.env.VITE_WS_URL as string | undefined) ??
  `ws://${window.location.hostname}:8000/ws/telemetry`;

const SNAPSHOT_URL =
  (import.meta.env.VITE_API_URL as string | undefined)
    ? `${import.meta.env.VITE_API_URL}/telemetry/snapshot`
    : `http://${window.location.hostname}:8000/api/telemetry/snapshot`;

export default function App() {
  const [snapshot, setSnapshot] = useState<TelemetrySnapshot>([]);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");

  useEffect(() => {
    fetch(SNAPSHOT_URL)
      .then((r) => (r.ok ? r.json() : []))
      .then((data: TelemetrySnapshot) => setSnapshot(data))
      .catch(() => {
        // backend henüz ayakta değil — WS reconnect halleder
      });

    const ws = new TelemetryWS(WS_URL);
    const offMsg = ws.onMessage(setSnapshot);
    const offStatus = ws.onStatus(setStatus);
    ws.connect();

    return () => {
      offMsg();
      offStatus();
      ws.disconnect();
    };
  }, []);

  return (
    <div className="app">
      <StatusBar status={status} snapshot={snapshot} />
      <main className="app__main">
        <MapView snapshot={snapshot} />
      </main>
    </div>
  );
}
