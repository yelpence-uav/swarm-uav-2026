import { useCallback, useEffect, useState } from "react";

/**
 * QR nokta konumları - operatör yarışma öncesi hakemlerin verdiği lat/lon'ları
 * arayüzden girer (şartname V2 s.14: konumlar önceden paylaşılır, sahada
 * doğrulanıp yeniden kaydedilebilir).
 *
 * Şeyda kararı: QR sayısı SABİT değil - soru-cevapta "6-7 olabilir" dendi,
 * şartname örneğinde 5 var. Dinamik ekle/çıkar tasarlandı. localStorage'da
 * saklanır ki yarışma stresinde config dosyası açmaya gerek kalmasın.
 */
export interface QRPosition {
  qr_id: number;
  lat: number;
  lon: number;
}

const STORAGE_KEY = "gcs.qr_positions";
const DEFAULT_COUNT = 5; // şartname örneği; operatör ekler/çıkarır

function defaultPositions(): QRPosition[] {
  return Array.from({ length: DEFAULT_COUNT }, (_, i) => ({
    qr_id: i + 1,
    lat: 0,
    lon: 0,
  }));
}

function load(): QRPosition[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultPositions();
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.length > 0) {
      return parsed
        .filter((p) => typeof p?.qr_id === "number")
        .map((p) => ({
          qr_id: Number(p.qr_id),
          lat: Number(p.lat) || 0,
          lon: Number(p.lon) || 0,
        }));
    }
  } catch {
    /* bozuk kayıt - varsayılana dön */
  }
  return defaultPositions();
}

export function useQRPositions() {
  const [positions, setPositions] = useState<QRPosition[]>(load);

  // Her değişiklikte kalıcı kaydet (yarışmada tekrar girmemek için).
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(positions));
    } catch {
      /* localStorage dolu/engelli - sessiz geç */
    }
  }, [positions]);

  const update = useCallback(
    (index: number, patch: Partial<QRPosition>) => {
      setPositions((prev) =>
        prev.map((p, i) => (i === index ? { ...p, ...patch } : p)),
      );
    },
    [],
  );

  const add = useCallback(() => {
    setPositions((prev) => {
      const nextId = prev.length
        ? Math.max(...prev.map((p) => p.qr_id)) + 1
        : 1;
      return [...prev, { qr_id: nextId, lat: 0, lon: 0 }];
    });
  }, []);

  const remove = useCallback((index: number) => {
    setPositions((prev) => prev.filter((_, i) => i !== index));
  }, []);

  return { positions, update, add, remove };
}

/** lat ve lon 0'dan farklıysa "girilmiş" say. */
export function isQRPositionSet(p: QRPosition): boolean {
  return p.lat !== 0 && p.lon !== 0;
}
