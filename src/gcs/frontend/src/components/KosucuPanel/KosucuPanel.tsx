import { useCallback, useEffect, useRef, useState } from "react";

import { kosucuApi, type KosucuDurum } from "../../services/api";
import "./KosucuPanel.css";

/**
 * Kanıt uçuşu koşucusu — gorev_kanit_ucus.py'yi YKİ'den başlat/durdur.
 *
 * NEDEN BURADA: koreografi sürünün kendi durum makinesinde değil, YKİ'de
 * koşan bir betikte. Sahada onu ayrı terminalden elle başlatmak gerekiyordu;
 * kanıt videosu çekilirken laptop başında komut yazmak hem yavaş hem videoda
 * kötü duruyor (şartname YKİ ekranının videoda görünmesini şart koşuyor).
 *
 * İKİ AYRI DÜĞME, BİLEREK: "kuru test" komut göndermez, "GÖREV BAŞLAT"
 * gerçekten uçurur. Aynı düğmeye bayrak koysaydık yanlış tıklama tek
 * karakterlik bir hataya inerdi.
 *
 * DURDUR = İNİŞ: backend SIGINT gönderiyor, betik onu yakalayıp indir()
 * çalıştırıyor. Motor kesme DEĞİL.
 */

const YOKLAMA_MS = 1000;

export function KosucuPanel() {
  const [durum, setDurum] = useState<KosucuDurum | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);
  const logRef = useRef<HTMLPreElement | null>(null);

  const yokla = useCallback(async () => {
    try {
      setDurum(await kosucuApi.durum(120));
    } catch {
      /* YKİ yeniden başlıyorsa sessiz geç; bir sonraki yoklama toparlar. */
    }
  }, []);

  useEffect(() => {
    void yokla();
    const t = window.setInterval(() => void yokla(), YOKLAMA_MS);
    return () => window.clearInterval(t);
  }, [yokla]);

  // Yeni satır geldikçe en alta yapış.
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [durum?.satirlar.length]);

  const calisiyor = durum?.calisiyor ?? false;

  const baslat = async (kuru: boolean) => {
    if (
      !kuru &&
      !window.confirm(
        "GERÇEK UÇUŞ başlatılacak.\n\n" +
          "• Kumandalar açık ve kill switch ulaşılabilir mi?\n" +
          "• Kuru test geçti mi?\n" +
          "• Piller yeterli mi?\n\nBaşlatılsın mı?",
      )
    ) {
      return;
    }
    setMesgul(true);
    setHata(null);
    try {
      setDurum(await kosucuApi.baslat({ kuru }));
    } catch (e) {
      setHata(e instanceof Error ? e.message : String(e));
    } finally {
      setMesgul(false);
    }
  };

  const durdur = async () => {
    if (!window.confirm("Görev durdurulacak — uçaklar İNİŞ yapacak. Onay?")) {
      return;
    }
    setMesgul(true);
    setHata(null);
    try {
      const r = await kosucuApi.durdur();
      setDurum(r);
      if (r.mesaj) setHata(r.mesaj);
    } catch (e) {
      setHata(e instanceof Error ? e.message : String(e));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <section className="kp">
      <header className="kp__head">
        <span className="kp__title">Kanıt Uçuşu Koşucusu</span>
        {/* HANGI UCAKLAR UCACAK, BASMADAN ONCE GORUNSUN. 2 Ağustos'ta bu
            bilgi gizliydi ve arayüz backend'den farklı bir filo gönderiyordu;
            hata ancak ön kontrol patlayınca anlaşıldı. */}
        {durum?.varsayilan && (
          <span className="kp__filo">
            {durum.varsayilan.senaryo} · d
            {durum.varsayilan.dronelar.replace(/,/g, ",d")} · lider d
            {durum.varsayilan.lider}
          </span>
        )}
        {calisiyor && (
          <span
            className={`kp__rozet ${
              durum?.kuru ? "kp__rozet--kuru" : "kp__rozet--canli"
            }`}
          >
            {durum?.kuru ? "KURU" : "CANLI"} · {durum?.gecen_s ?? 0}s
          </span>
        )}
      </header>

      <div className="kp__btns">
        <button
          className="kp__btn"
          disabled={mesgul || calisiyor}
          onClick={() => void baslat(true)}
        >
          KURU TEST
        </button>
        <button
          className="kp__btn kp__btn--canli"
          disabled={mesgul || calisiyor}
          onClick={() => void baslat(false)}
        >
          GÖREV BAŞLAT
        </button>
        <button
          className="kp__btn kp__btn--dur"
          disabled={mesgul || !calisiyor}
          onClick={() => void durdur()}
        >
          DURDUR (İNİŞ)
        </button>
      </div>

      {hata && <div className="kp__hata">{hata}</div>}

      {durum && !calisiyor && durum.cikis_kodu != null && (
        <div
          className={`kp__sonuc ${
            durum.cikis_kodu === 0 ? "kp__sonuc--ok" : "kp__sonuc--kotu"
          }`}
        >
          {durum.cikis_kodu === 0
            ? `Bitti (${durum.gecen_s}s)`
            : `Hata ile bitti — çıkış kodu ${durum.cikis_kodu}`}
        </div>
      )}

      <pre className="kp__log" ref={logRef}>
        {durum?.satirlar.length
          ? durum.satirlar.join("\n")
          : "— çıktı yok —"}
      </pre>
    </section>
  );
}
