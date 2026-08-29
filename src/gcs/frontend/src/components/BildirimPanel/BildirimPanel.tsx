import { useMemo, useState } from "react";

import type { GunlukKaydi } from "../../services/api";
import "./BildirimPanel.css";

/** Kaynak süzgeci: "hepsi" · 0 = yalnız sistem · N = yalnız o drone. */
type Kaynak = "hepsi" | number;

interface BildirimPanelProps {
  kayitlar: GunlukKaydi[];
  /** Filodaki drone kimlikleri — süzgeç düğmeleri buradan çizilir.
   *  Kaydı olmayan drone'un düğmesi de görünsün diye ayrı geliyor. */
  droneler?: number[];
  /** Arka uçla bağlantı yok — boş liste "sorun yok" sanılmasın. */
  hata?: boolean;
  /** Arka uçta defter kurulmamış. */
  aktif?: boolean;
  /** Açılışta seçili kaynak süzgeci — drone kartındaki LOG buradan geliyor. */
  baslangicKaynak?: Kaynak;
  onClose: () => void;
}

const SIDDET_ETIKET: Record<string, string> = {
  info: "BİLGİ",
  warning: "UYARI",
  critical: "KRİTİK",
  emergency: "ACİL",
};

type Suzgec = "hepsi" | "uyari" | "kritik";

const SUZGEC_ETIKET: Record<Suzgec, string> = {
  hepsi: "Tümü",
  uyari: "Uyarı ve üstü",
  kritik: "Yalnız kritik",
};

const UYARI_USTU = new Set(["warning", "critical", "emergency"]);
const KRITIK = new Set(["critical", "emergency"]);

/** Bütün bildirimlerin zaman damgalı listesi.
 *
 * NEDEN VAR (29 Ağustos 2026, operatör): haritanın sağ üstündeki uyarılar
 * geçici — kapanınca ya da 10 saniye sonra kayboluyor ve "az önce ne
 * yazıyordu" sorusunun cevabı kalmıyordu. Defter zaten arka uçta diske
 * yazılıyordu (`gunluk/yki_olaylar.jsonl`); burada yalnızca görünür oluyor.
 *
 * Kaynak `useGunluk` — drone kartlarındaki log ile AYNI çekici. İkinci bir
 * sorgu açmıyoruz.
 */
export function BildirimPanel({
  kayitlar,
  droneler = [],
  hata = false,
  aktif = true,
  baslangicKaynak = "hepsi",
  onClose,
}: BildirimPanelProps) {
  const [suzgec, setSuzgec] = useState<Suzgec>("hepsi");
  const [kaynak, setKaynak] = useState<Kaynak>(baslangicKaynak);

  // Dugmeler: filodan gelenler + defterde gecen kimlikler. Ikisinin birlesimi,
  // cunku (a) kaydi olmayan drone'un dugmesi de dursun, (b) filoda olmayan
  // ama defterde gecen bir kimlik gizlenmesin.
  const droneKimlikleri = useMemo(() => {
    const s = new Set<number>(droneler);
    for (const k of kayitlar) if (k.drone_id !== 0) s.add(k.drone_id);
    return [...s].sort((a, b) => a - b);
  }, [droneler, kayitlar]);

  const gosterilen = useMemo(() => {
    let liste = kayitlar;
    // KAYNAK SUZGECI KESIN: "Drone 2" secilince YALNIZ drone 2 gorunur.
    // Drone kartindaki log sistem olaylarini da katiyor (orada dogru: "Pi
    // diski doldu" o drone'u ilgilendirir), ama burada operator izole
    // bakmak istedigini soyledi — sistem icin ayri dugme var.
    if (kaynak !== "hepsi") {
      liste = liste.filter((k) => k.drone_id === kaynak);
    }
    if (suzgec === "kritik") return liste.filter((k) => KRITIK.has(k.siddet));
    if (suzgec === "uyari") return liste.filter((k) => UYARI_USTU.has(k.siddet));
    return liste;
  }, [kayitlar, suzgec, kaynak]);

  /** O kaynakta kac kayit var — dugmenin yanindaki sayi. */
  const kaynakSayisi = (k: Kaynak) =>
    k === "hepsi"
      ? kayitlar.length
      : kayitlar.filter((r) => r.drone_id === k).length;

  return (
    <div className="bildirim-overlay" onClick={onClose}>
      <div
        className="bildirim-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Bildirimler"
      >
        <header className="bildirim-modal__head">
          <h2>Bildirimler</h2>
          <span className="bildirim-modal__sayi">{gosterilen.length} kayıt</span>
          <button
            className="bildirim-modal__close"
            onClick={onClose}
            aria-label="Kapat"
          >
            ✕
          </button>
        </header>

        <div className="bildirim-suzgec">
          {(Object.keys(SUZGEC_ETIKET) as Suzgec[]).map((s) => (
            <button
              key={s}
              className={
                "bildirim-suzgec__btn" +
                (suzgec === s ? " bildirim-suzgec__btn--aktif" : "")
              }
              onClick={() => setSuzgec(s)}
            >
              {SUZGEC_ETIKET[s]}
            </button>
          ))}
        </div>

        <div className="bildirim-suzgec bildirim-suzgec--kaynak">
          <button
            className={
              "bildirim-suzgec__btn" +
              (kaynak === "hepsi" ? " bildirim-suzgec__btn--aktif" : "")
            }
            onClick={() => setKaynak("hepsi")}
          >
            Tüm kaynaklar
            <span className="bildirim-suzgec__sayi">{kaynakSayisi("hepsi")}</span>
          </button>
          {droneKimlikleri.map((id) => (
            <button
              key={id}
              className={
                "bildirim-suzgec__btn" +
                (kaynak === id ? " bildirim-suzgec__btn--aktif" : "")
              }
              onClick={() => setKaynak(id)}
            >
              Drone {id}
              <span className="bildirim-suzgec__sayi">{kaynakSayisi(id)}</span>
            </button>
          ))}
          <button
            className={
              "bildirim-suzgec__btn" +
              (kaynak === 0 ? " bildirim-suzgec__btn--aktif" : "")
            }
            onClick={() => setKaynak(0)}
            title="Belirli bir drone'a ait olmayan olaylar"
          >
            Sistem
            <span className="bildirim-suzgec__sayi">{kaynakSayisi(0)}</span>
          </button>
        </div>

        <div className="bildirim-modal__body">
          {hata && (
            <div className="bildirim-iz">
              Yer istasyonuna bağlanılamıyor — liste eksik olabilir
            </div>
          )}
          {!hata && !aktif && (
            <div className="bildirim-iz">Olay defteri arka uçta kapalı</div>
          )}
          {!hata && aktif && gosterilen.length === 0 && (
            <div className="bildirim-iz">Bu süzgeçte kayıt yok</div>
          )}

          {gosterilen.map((k) => (
            <div
              key={k.sira}
              className={`bildirim-satir bildirim-satir--${k.siddet}`}
              title={`kod: ${k.kod}`}
            >
              <span className="bildirim-satir__zaman">{zamanYaz(k.zaman)}</span>
              <span
                className={`bildirim-satir__siddet bildirim-satir__siddet--${k.siddet}`}
              >
                {SIDDET_ETIKET[k.siddet] ?? k.siddet}
              </span>
              <span className="bildirim-satir__kaynak">
                {k.drone_id === 0 ? "Sistem" : `Drone ${k.drone_id}`}
              </span>
              <span className="bildirim-satir__mesaj">{k.mesaj}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Aynı günse yalnız saat, değilse gün de. Uçuş günü boyunca saat yeter;
 *  dünkü bir kayıt yanlışlıkla "az önce" gibi okunmasın diye tarih ekleniyor. */
function zamanYaz(epoch: number): string {
  const d = new Date(epoch * 1000);
  const saat = d.toLocaleTimeString("tr-TR", { hour12: false });
  const bugun = new Date();
  const ayniGun =
    d.getDate() === bugun.getDate() &&
    d.getMonth() === bugun.getMonth() &&
    d.getFullYear() === bugun.getFullYear();
  if (ayniGun) return saat;
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")} ${saat}`;
}
