import { useEffect, useMemo, useRef, useState } from "react";

import type { Alert } from "../../types/telemetry";
import { AlertItem } from "./AlertItem";
import "./AlertList.css";

interface AlertListProps {
  alerts: Alert[];
}

const REFRESH_AGE_MS = 1000;
const ALERT_SOUND_URL = "/alert-critical.wav";

export function AlertList({ alerts }: AlertListProps) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [, setTick] = useState(0);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const seenCriticalRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const audio = new Audio(ALERT_SOUND_URL);
    audio.preload = "auto";
    audioRef.current = audio;
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), REFRESH_AGE_MS);
    return () => window.clearInterval(id);
  }, []);

  // Yeni kritik alert geldiğinde tek seferlik bip. Aynı (drone_id,code)
  // aktif kaldığı sürece tekrar çalmaz; düşüp yeniden aktive olursa çalar.
  useEffect(() => {
    const current = new Set(
      alerts.filter((a) => a.severity === "critical").map(keyOf),
    );
    const prev = seenCriticalRef.current;
    const fresh = Array.from(current).some((k) => !prev.has(k));
    if (fresh && audioRef.current) {
      audioRef.current.currentTime = 0;
      // Browser autoplay policy: operatör sayfayla etkileşmediyse reject olur.
      audioRef.current.play().catch(() => undefined);
    }
    seenCriticalRef.current = current;
  }, [alerts]);

  const visible = useMemo(() => {
    const activeKeys = new Set(alerts.map((a) => keyOf(a)));
    if (dismissed.size > 0) {
      const cleaned = new Set(
        Array.from(dismissed).filter((k) => activeKeys.has(k)),
      );
      if (cleaned.size !== dismissed.size) {
        setDismissed(cleaned);
      }
    }
    return alerts.filter((a) => !dismissed.has(keyOf(a)));
  }, [alerts, dismissed]);

  const handleDismiss = (key: string) => {
    setDismissed((prev) => {
      const next = new Set(prev);
      next.add(key);
      return next;
    });
  };

  if (visible.length === 0) return null;

  return (
    <ul className="alert-list">
      {visible.map((a) => (
        <AlertItem key={keyOf(a)} alert={a} onDismiss={handleDismiss} />
      ))}
    </ul>
  );
}

function keyOf(a: Alert): string {
  return `${a.drone_id}:${a.code}`;
}
