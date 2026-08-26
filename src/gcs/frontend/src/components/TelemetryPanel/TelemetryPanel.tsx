import { useCallback, useEffect, useState } from "react";

import { useGunluk } from "../../hooks/useGunluk";
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
}

export function TelemetryPanel({
  drones,
  selectedDroneId = null,
  onSelectDrone,
  mesafeler = [],
}: TelemetryPanelProps) {
  const { droneKayitlari, kritikVar, okunduIsaretle, aktif, hata } = useGunluk();

  // BIRDEN COK kart ayni anda acilabilir: iki drone'un olaylarini yan yana
  // karsilastirmak, loglari kartlara koymanin asil kazanci.
  const [acikLoglar, setAcikLoglar] = useState<Set<number>>(new Set());

  const logToggle = useCallback((droneId: number) => {
    setAcikLoglar((eski) => {
      const yeni = new Set(eski);
      if (yeni.has(droneId)) yeni.delete(droneId);
      else yeni.add(droneId);
      return yeni;
    });
  }, []);

  // Log acikken gelen olaylar GORULMUS sayilir — buton yanip sonmesin.
  useEffect(() => {
    acikLoglar.forEach((id) => okunduIsaretle(id));
  }, [acikLoglar, okunduIsaretle]);

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
          kayitlar={droneKayitlari(d.drone_id)}
          kritik={kritikVar(d.drone_id)}
          logAcik={acikLoglar.has(d.drone_id)}
          onLogToggle={logToggle}
          gunlukHata={hata}
          gunlukAktif={aktif}
          mesafeler={komsuMesafeleri(d.drone_id)}
        />
      ))}
      {drones.length === 0 && (
        <div className="telemetry-panel__empty">Drone bekleniyor…</div>
      )}
    </aside>
  );
}
