import { isQRPositionSet, type QRPosition } from "../../hooks/useQRPositions";
import "./QRPositionForm.css";

interface QRPositionFormProps {
  positions: QRPosition[];
  update: (index: number, patch: Partial<QRPosition>) => void;
  add: () => void;
  remove: (index: number) => void;
}

/**
 * QR konum giriş formu.
 *
 * Şartname V2 s.14: QR lat/lon'ları yarışma öncesi hakemlerce paylaşılır,
 * sahada doğrulanabilir. Operatör buradan girer — config dosyası açmaya
 * gerek kalmaz (Şeyda kararı). Dinamik: QR sayısı 5/6/7 olabilir, ekle/çıkar.
 * Girilen konumlar haritada işaretlenir + (mesaj tipi gelince) mesh üzerinden
 * mission_fsm'e yayınlanacak.
 */
export function QRPositionForm({
  positions,
  update,
  add,
  remove,
}: QRPositionFormProps) {
  const setCount = positions.filter(isQRPositionSet).length;

  return (
    <details className="qr-form" open>
      <summary className="qr-form__summary">
        <span className="qr-form__title">QR KONUMLARI</span>
        <span
          className={
            "qr-form__count " +
            (setCount === positions.length && setCount > 0
              ? "qr-form__count--ok"
              : "")
          }
        >
          {setCount}/{positions.length} girildi
        </span>
      </summary>

      <div className="qr-form__rows">
        {positions.map((qr, i) => (
          <div
            key={i}
            className={
              "qr-form__row " +
              (isQRPositionSet(qr) ? "qr-form__row--set" : "")
            }
          >
            <input
              className="qr-form__id"
              type="number"
              min={0}
              value={qr.qr_id}
              onChange={(e) =>
                update(i, { qr_id: Number(e.target.value) || 0 })
              }
              title="QR numarası"
            />
            <input
              className="qr-form__coord"
              type="number"
              step="0.000001"
              placeholder="enlem"
              value={qr.lat || ""}
              onChange={(e) => update(i, { lat: Number(e.target.value) || 0 })}
            />
            <input
              className="qr-form__coord"
              type="number"
              step="0.000001"
              placeholder="boylam"
              value={qr.lon || ""}
              onChange={(e) => update(i, { lon: Number(e.target.value) || 0 })}
            />
            <button
              className="qr-form__remove"
              onClick={() => remove(i)}
              title="QR'ı sil"
              aria-label={`QR ${qr.qr_id} sil`}
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      <button className="qr-form__add" onClick={add}>
        + QR Ekle
      </button>
      <p className="qr-form__hint">
        Konumlar tarayıcıda saklanır. Haritada işaretlenir; mesh üzerinden
        sürüye iletilecek.
      </p>
    </details>
  );
}
