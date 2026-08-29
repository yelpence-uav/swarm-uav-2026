import { useState } from "react";

import { CommandFailure, MISSION_COMMAND, missionApi } from "../../services/api";
import "./AcilSonlandirma.css";

interface AcilSonlandirmaProps {
  missionId: number;
  teamId: string;
  missionActive: boolean;
}

/** ACİL İNİŞ — haritanın alt ortasında.
 *
 * NEDEN BURADA (29 Ağustos 2026, operatör): görev sürerken operatörün gözü
 * haritada. Buton kenar çubuğundaki görev kartındaysa acil durumda önce onu
 * aramak gerekiyordu.
 *
 * 🔴 KOMUT `LAND`, `ABORT` DEĞİL — bilerek. Buton "acil iniş" diyorsa
 * gerçekten indirmeli. Koda bakıldı: `ABORT` yalnız MissionState.ABORTED'a
 * geçiriyor ve `_from_terminal` sürünün ZATEN inmiş olmasını BEKLİYOR —
 * hiçbir yerde iniş komutu üretmiyor (mission1/orchestrator'da ABORT
 * işleyicisi hiç yok). İndiren komut `LAND`: MissionState.LANDING,
 * "burada in" (mission_transitions.py:76).
 *
 * ⚠️ Şartname: görev sırasında YKİ'den müdahale görevi BAŞARISIZ sayar. Bu
 * yüzden iki aşamalı onay var ve düğme görev aktif değilken pasif.
 *
 * Harita alt ortası "buraya git" çubuğuyla aynı yer, ama ikisi hiç birlikte
 * görünmez: guided goto görev aktifken zaten kapalı
 * (`guidedEnabled={!isSimMode && !missionActive}`). Yine de z-index bir üstte
 * — güvenlik denetimi hiçbir koşulda örtülmemeli.
 */
export function AcilSonlandirma({
  missionId,
  teamId,
  missionActive,
}: AcilSonlandirmaProps) {
  const [busy, setBusy] = useState(false);
  const [hata, setHata] = useState<string | null>(null);

  const inisVer = async () => {
    if (
      !window.confirm(
        "Tüm sürü BULUNDUĞU NOKTAYA inecek.\n\n" +
          "Uçakların altı boş mu? Şartnameye göre bu müdahale görevi " +
          "BAŞARISIZ sayar.",
      )
    ) {
      return;
    }
    if (
      !window.confirm(
        "SON UYARI — ACİL İNİŞ\n\nSürü eve dönmez, olduğu yerde iner.\n\n" +
          "Onaylıyor musun?",
      )
    ) {
      return;
    }
    setBusy(true);
    setHata(null);
    try {
      await missionApi.trigger({
        mission_id: missionId,
        command: MISSION_COMMAND.LAND,
        team_id: teamId.trim(),
      });
    } catch (e) {
      setHata(
        e instanceof CommandFailure
          ? `HTTP ${e.http_status}: ${e.message}`
          : (e as Error).message,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="acil">
      <button
        type="button"
        className="acil__btn"
        onClick={inisVer}
        disabled={busy || !missionActive}
        title={
          missionActive
            ? "Sürü bulunduğu noktaya iner — şartnameye göre görev BAŞARISIZ sayılır"
            : "Görev aktif değil"
        }
      >
        {busy ? "GÖNDERİLİYOR…" : "ACİL İNİŞ"}
      </button>
      {hata && <div className="acil__hata">{hata}</div>}
    </div>
  );
}
