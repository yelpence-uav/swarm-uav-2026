import type { GunlukKaydi } from "../../services/api";
import "./DroneLog.css";

const SIDDET_ETIKET: Record<string, string> = {
  info: "BİLGİ",
  warning: "UYARI",
  critical: "KRİTİK",
  emergency: "ACİL",
};

interface DroneLogProps {
  kayitlar: GunlukKaydi[];
  /** Arka uçla bağlantı yok — kullanıcı boş listeyi "sorun yok" sanmasın. */
  hata?: boolean;
  /** Arka uçta defter kurulmamış. */
  aktif?: boolean;
}

/** Drone kartının içindeki olay listesi.
 *
 * Kart dar olduğu için tek satır = saat + şiddet + mesaj. Drone adı YOK:
 * zaten o drone'un kartındayız. Sistem olayları (drone_id = 0) burada da
 * görünüyor ve "SİS" ile işaretleniyor.
 */
export function DroneLog({ kayitlar, hata = false, aktif = true }: DroneLogProps) {
  const saat = (epoch: number) =>
    new Date(epoch * 1000).toLocaleTimeString("tr-TR", { hour12: false });

  return (
    <div className="drone-log">
      {hata && <div className="drone-log__iz">arka uçla bağlantı yok</div>}
      {!hata && !aktif && <div className="drone-log__iz">defter kapalı</div>}
      {!hata && aktif && kayitlar.length === 0 && (
        <div className="drone-log__iz">henüz olay yok</div>
      )}
      {kayitlar.map((k) => (
        <div
          key={k.sira}
          className={`drone-log__satir drone-log__satir--${k.siddet}`}
          title={`${k.kod}${k.drone_id === 0 ? " · sistem geneli" : ""}`}
        >
          <span className="drone-log__saat">{saat(k.zaman)}</span>
          <span className={`drone-log__siddet drone-log__siddet--${k.siddet}`}>
            {k.drone_id === 0 ? "SİS" : SIDDET_ETIKET[k.siddet] ?? k.siddet}
          </span>
          <span className="drone-log__mesaj">{k.mesaj}</span>
        </div>
      ))}
    </div>
  );
}
