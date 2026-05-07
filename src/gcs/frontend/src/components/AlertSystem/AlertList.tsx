import { useEffect, useMemo, useState } from "react";

import type { Alert } from "../../types/telemetry";
import { AlertItem } from "./AlertItem";
import "./AlertList.css";

interface AlertListProps {
  alerts: Alert[];
}

const REFRESH_AGE_MS = 1000;

export function AlertList({ alerts }: AlertListProps) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), REFRESH_AGE_MS);
    return () => window.clearInterval(id);
  }, []);

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
