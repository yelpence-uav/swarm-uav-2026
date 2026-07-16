import { useState } from "react";

import { isQRPositionSet, type QRPosition } from "../../hooks/useQRPositions";
import { CommandFailure, missionApi } from "../../services/api";
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
 *
 * "Drone'lara Gönder" → backend POST /api/mission/qr_coords → QRCoordinates
 * mesajı /swarm/internal/mission/qr_coords'a (latched) → proxy/mesh →
 * mission_fsm tabloyu saklar (next_qr → konum çözümü).
 */
export function QRPositionForm({
  positions,
  update,
  add,
  remove,
}: QRPositionFormProps) {
  const [sending, setSending] = useState(false);
  const [sendMsg, setSendMsg] = useState<{ ok: boolean; text: string } | null>(
    null,
  );

  const ready = positions.filter(isQRPositionSet);
  const setCount = ready.length;

  async function handleSend() {
    if (ready.length === 0) {
      setSendMsg({ ok: false, text: "Önce en az bir QR konumu gir." });
      return;
    }
    setSending(true);
    setSendMsg(null);
    try {
      const res = await missionApi.sendQrCoords({
        qr_ids: ready.map((p) => p.qr_id),
        lat_deg: ready.map((p) => p.lat),
        lon_deg: ready.map((p) => p.lon),
      });
      setSendMsg({
        ok: true,
        text: `${res.count} QR konumu sürüye gönderildi ✓`,
      });
    } catch (e) {
      const msg = e instanceof CommandFailure ? e.message : String(e);
      setSendMsg({ ok: false, text: `Gönderilemedi: ${msg}` });
    } finally {
      setSending(false);
    }
  }

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

      <button
        className="qr-form__send"
        onClick={handleSend}
        disabled={sending || ready.length === 0}
      >
        {sending
          ? "Gönderiliyor…"
          : `📡 Drone'lara Gönder (${ready.length})`}
      </button>

      {sendMsg && (
        <p
          className={
            "qr-form__send-status " +
            (sendMsg.ok
              ? "qr-form__send-status--ok"
              : "qr-form__send-status--err")
          }
        >
          {sendMsg.text}
        </p>
      )}

      <p className="qr-form__hint">
        Konumlar tarayıcıda saklanır. Haritada işaretlenir; "Gönder" ile
        sürüye iletilir.
      </p>
    </details>
  );
}
