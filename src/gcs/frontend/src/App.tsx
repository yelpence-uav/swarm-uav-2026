import { useEffect, useMemo, useState } from "react";

import { AcilSonlandirma } from "./components/AcilSonlandirma/AcilSonlandirma";
import { AlertList } from "./components/AlertSystem/AlertList";
import { AppHeader } from "./components/AppShell/AppHeader";
import { DroneControlPanel } from "./components/DroneControlPanel/DroneControlPanel";
import { MapView } from "./components/Map/Map";
import { MissionControl } from "./components/MissionControl/MissionControl";
import { MissionPanel } from "./components/MissionPanel/MissionPanel";
import { QRPanel } from "./components/QRPanel/QRPanel";
import { QRPositionForm } from "./components/QRPositionForm/QRPositionForm";
import { BildirimPanel } from "./components/BildirimPanel/BildirimPanel";
import { RpiPanel } from "./components/RpiPanel/RpiPanel";
import { SettingsPanel } from "./components/SettingsPanel/SettingsPanel";
import { TelemetryPanel } from "./components/TelemetryPanel/TelemetryPanel";
import { useGunluk } from "./hooks/useGunluk";
import { useQRPositions } from "./hooks/useQRPositions";
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

  const qr = useQRPositions();

  const [payload, setPayload] = useState<TelemetryPayload>(EMPTY_PAYLOAD);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [selectedMissionId, setSelectedMissionId] = useState<number>(
    MISSION_ID.DYNAMIC_SWARM,
  );

  // Seçili drone (kontrol paneli), ayarlar modalı ve uçuş parametreleri.
  const [selectedDroneId, setSelectedDroneId] = useState<number | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Takim ID: gorev karti VE haritadaki acil sonlandirma ayni degeri
  // kullaniyor, o yuzden burada tutuluyor (iki ayri state bir sure sonra
  // ayrisirdi — CLAUDE.md §9).
  const [teamId, setTeamId] = useState("team_1");
  const [bildirimlerOpen, setBildirimlerOpen] = useState(false);
  // RPi paneli — acik oldugu drone'un kimligi (null = kapali).
  const [rpiDrone, setRpiDrone] = useState<number | null>(null);
  // Panel hangi kaynakla acilacak: "hepsi" (baslik dugmesi) ya da drone id
  // (kart LOG butonu). Kart ici log katmani 29 Agustos'ta kaldirildi.
  const [bildirimKaynak, setBildirimKaynak] = useState<"hepsi" | number>("hepsi");

  // Olay defteri TEK yerden cekiliyor (hook'un kendi notu: "NEDEN TEK
  // CEKICI"). Hem drone kartlarindaki log hem basliktaki bildirim paneli
  // ayni veriyi kullaniyor.
  const olaylar = useGunluk();
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
  const isSimMode = payload.connection_mode === "mavlink-sim";

  const selectedDrone = payload.drones.find(
    (d) => d.drone_id === selectedDroneId,
  );

  return (
    <div className="app">
      <AppHeader
        status={status}
        rtk={payload.rtk ?? null}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenBildirimler={() => {
          setBildirimKaynak("hepsi");
          setBildirimlerOpen(true);
          olaylar.hepsiniOkunduIsaretle();
        }}
        okunmamisBildirim={olaylar.okunmamis}
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
        {selectedMissionId !== MISSION_ID.SEMI_AUTONOMOUS && (
          <AcilSonlandirma
            missionId={selectedMissionId}
            teamId={teamId}
            missionActive={missionActive}
          />
        )}
        {/* Kontrol paneli 29 Agustos 2026'da sag kenar cubuğundan HARITAYA
            tasindi (operator): komut verirken bakilan sey harita, panel de
            orada olsun. Sag alt kose Leaflet atif yazisinin ustune biniyor,
            bu bilerek — atif zorunlu degil ve panel gecici. */}
        {selectedDroneId != null && (
          <DroneControlPanel
            drone={selectedDrone}
            guidedMode={!isSimMode}
            commandsDisabled={missionActive}
            params={flightParams}
            onClose={() => setSelectedDroneId(null)}
          />
        )}
      </main>

      <aside className="app__sidebar">
            <MissionPanel
              missionActive={missionActive}
              missionId={selectedMissionId}
              onMissionIdChange={setSelectedMissionId}
              teamId={teamId}
              onTeamIdChange={setTeamId}
            />
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
      </aside>

      <footer className="app__drone-strip">
        <TelemetryPanel
          drones={payload.drones}
          mesafeler={payload.mesafeler ?? []}
          selectedDroneId={selectedDroneId}
          onSelectDrone={(id) =>
            setSelectedDroneId((cur) => (cur === id ? null : id))
          }
          kritikVar={olaylar.kritikVar}
          onRpiAc={(id) => setRpiDrone(id)}
          onLogAc={(id) => {
            setBildirimKaynak(id);
            setBildirimlerOpen(true);
            olaylar.okunduIsaretle(id);
          }}
        />
      </footer>

      {rpiDrone != null && (
        <RpiPanel
          droneId={rpiDrone}
          droneAdi={
            payload.drones.find((d) => d.drone_id === rpiDrone)?.name ??
            `Drone ${rpiDrone}`
          }
          onClose={() => setRpiDrone(null)}
        />
      )}

      {bildirimlerOpen && (
        <BildirimPanel
          kayitlar={olaylar.kayitlar}
          droneler={payload.drones.map((d) => d.drone_id)}
          baslangicKaynak={bildirimKaynak}
          aktif={olaylar.aktif}
          hata={olaylar.hata}
          onClose={() => setBildirimlerOpen(false)}
        />
      )}

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
