import { useCallback } from "react";

import type { DroneState, IkiliMesafe } from "../../types/telemetry";
import { DroneCard } from "./DroneCard";
import "./TelemetryPanel.css";

interface TelemetryPanelProps {
  drones: DroneState[];
  /** Seçili drone (kontrol paneli açık olan). */
  selectedDroneId?: number | null;
  /** Kart "Kontrol" butonu — seçili drone'u değiştirir. */
  onSelectDrone?: (droneId: number) => void;
  /** Bağlı drone çiftleri arası mesafe; kart başına süzülür. */
  mesafeler?: IkiliMesafe[];
  /* Olay defteri App'ten geliyor — `useGunluk` BİLEREK TEK ÇEKİCİ.
     29 Ağustos 2026: başlıktaki bildirim paneli de aynı defteri okuyor;
     burada ikinci bir useGunluk() çağırmak saniyede iki sorgu demekti. */
  kritikVar: (droneId: number) => boolean;
  /** LOG butonu — bildirim panelini o drone'a süzülmüş açar. */
  onLogAc?: (droneId: number) => void;
  /** RPi butonu — Pi sağlık panelini açar (SSH ile okunur). */
  onRpiAc?: (droneId: number) => void;
}

export function TelemetryPanel({
  drones,
  selectedDroneId = null,
  onSelectDrone,
  mesafeler = [],
  kritikVar,
  onLogAc,
  onRpiAc,
}: TelemetryPanelProps) {

  /** Bir drone'un DİĞER drone'lara yatay mesafeleri, isimleriyle.
   *
   * Yatay mesafe seciliyor cunku carpisma olcutu de yataydir
   * (TUZAKLAR §3.12: "dikey kacinmada catisma olcutu YATAY mesafedir").
   * Ekranda 3B mesafe gostermek, kacinmanin baktigi sayidan FARKLI bir sayi
   * gostermek olurdu. */
  const komsuMesafeleri = useCallback(
    (droneId: number) =>
      mesafeler
        .filter((m) => m.a === droneId || m.b === droneId)
        .map((m) => {
          const digerId = m.a === droneId ? m.b : m.a;
          return {
            id: digerId,
            ad: drones.find((d) => d.drone_id === digerId)?.name ?? `d${digerId}`,
            yatay_m: m.yatay_m,
          };
        })
        .sort((x, y) => x.id - y.id),
    [mesafeler, drones],
  );

  return (
    <aside className="telemetry-panel">
      {drones.map((d) => (
        <DroneCard
          key={d.drone_id}
          drone={d}
          onSelect={onSelectDrone}
          selected={d.drone_id === selectedDroneId}
          kritik={kritikVar(d.drone_id)}
          onLogAc={onLogAc}
          onRpiAc={onRpiAc}
          mesafeler={komsuMesafeleri(d.drone_id)}
        />
      ))}
      {drones.length === 0 && (
        <div className="telemetry-panel__empty">Drone bekleniyor…</div>
      )}
    </aside>
  );
}
