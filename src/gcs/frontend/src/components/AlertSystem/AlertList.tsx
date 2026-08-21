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

    // SES KILIDINI AC — 22 Agustos 2026, sahada olculdu.
    //
    // Tarayici otomatik-oynatma politikasi: operator sayfayla ETKILESMEDIYSE
    // play() reddediliyor. 21 Agustos gecesi kritik alarm ekranda gorundu
    // ama SES CIKMADI, cunku operator o sekmeye hic tiklamamisti.
    //
    // Cozum: ilk kullanici etkilesiminde sesi bir kez SESSIZ calip durdur.
    // Tarayici bunu "kullanici izin verdi" sayiyor ve sonraki play()
    // cagrilari serbest kaliyor. Operatorun ayrica bir sey yapmasi gerekmez;
    // YKI'ye her oturumda zaten tiklaniyor.
    const kilidiAc = () => {
      const a = audioRef.current;
      if (!a) return;
      const eskiSes = a.volume;
      a.volume = 0;
      a.play()
        .then(() => {
          a.pause();
          a.currentTime = 0;
          a.volume = eskiSes;
        })
        .catch(() => {
          a.volume = eskiSes;
        });
      window.removeEventListener("pointerdown", kilidiAc);
      window.removeEventListener("keydown", kilidiAc);
    };
    window.addEventListener("pointerdown", kilidiAc);
    window.addEventListener("keydown", kilidiAc);

    // MASAUSTU BILDIRIMI — operator YKI basinda DEGILKEN de duysun.
    // Operator istegi (22 Agustos): "YKI basinda olmadigimda bildirim
    // vermeli." Web Notification API sekme ARKA PLANDAYKEN de calisiyor;
    // isletim sistemi bildirimi olarak cikiyor.
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission().catch(() => undefined);
    }
    return () => {
      window.removeEventListener("pointerdown", kilidiAc);
      window.removeEventListener("keydown", kilidiAc);
    };
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
      // Autoplay politikasi: kilit yukarida ilk etkilesimde aciliyor.
      audioRef.current.play().catch(() => undefined);
    }
    // MASAUSTU BILDIRIMI — sekme arka plandayken de gorunur (22 Agustos).
    if (fresh && "Notification" in window && Notification.permission === "granted") {
      const yeni = alerts.filter(
        (a) => a.severity === "critical" && !prev.has(keyOf(a)),
      );
      for (const a of yeni) {
        try {
          new Notification("🔴 YELPENÇE — KRİTİK", {
            body: a.message ?? "Kritik uyarı",
            tag: keyOf(a), // ayni uyari tekrar tekrar yigilmasin
            requireInteraction: true, // operator kapatana kadar ekranda kalsin
          });
        } catch {
          // Bildirim basarisiz olursa sessiz gec — ses ve ekran uyarisi duruyor.
        }
      }
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
