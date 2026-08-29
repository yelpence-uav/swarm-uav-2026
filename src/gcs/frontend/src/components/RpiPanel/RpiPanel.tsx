import { useCallback, useEffect, useRef, useState } from "react";

import { rpi, type RpiDurum } from "../../services/api";
import "./RpiPanel.css";

interface RpiPanelProps {
  droneId: number;
  droneAdi: string;
  onClose: () => void;
}

/** Panel açıkken yenileme aralığı. Her tur bir SSH açıyor — sık sorgulamak
 *  Pi'yi meşgul eder ve uçuş sırasında CPU zaten dar (28 Ağu: tarayıcı sekmesi
 *  açıkken toplam %90,7). 5 sn, bakarken taze kalmaya yeter. */
const YENILE_MS = 5000;

type Renk = "ok" | "uyari" | "kritik" | "notr";

interface Satir {
  etiket: string;
  deger: string;
  renk: Renk;
  ipucu?: string;
}

const yok = "bilinmiyor";

function sn_metin(sn: number): string {
  if (sn < 60) return `${sn} sn`;
  if (sn < 3600) return `${Math.floor(sn / 60)} dk`;
  if (sn < 86400) return `${Math.floor(sn / 3600)} sa ${Math.floor((sn % 3600) / 60)} dk`;
  return `${Math.floor(sn / 86400)} gün ${Math.floor((sn % 86400) / 3600)} sa`;
}

/** Ham `anahtar=deger` haritasını okunur satırlara çevirir.
 *
 * EŞİKLER ÖLÇÜMDEN: Pi 5 boşta 56-64 °C ölçüldü (27 Ağustos), uyarı 70 /
 * kritik 80 oradan geliyor. Disk eşiği 14 Ağustos'ta iki dronun da diski
 * %100 dolduğu için var — dolu diskte bir sonraki uçuş KAYDEDİLMEZ. */
function satirlar(d: Record<string, number | string>): Satir[] {
  const s: Satir[] = [];
  const say = (k: string) => (typeof d[k] === "number" ? (d[k] as number) : undefined);

  const t = say("sicaklik_c");
  s.push({
    etiket: "Sıcaklık",
    deger: t === undefined ? yok : `${t.toFixed(1)} °C`,
    renk: t === undefined ? "notr" : t >= 80 ? "kritik" : t >= 70 ? "uyari" : "ok",
    ipucu: "Pi 5 boşta 56-64 °C ölçüldü; uyarı 70, kritik 80",
  });

  const thr = d["throttled"];
  s.push({
    etiket: "Güç / ısıl kısıtlama",
    deger: thr === undefined ? yok : thr === "0x0" ? "yok" : String(thr),
    renk: thr === undefined ? "notr" : thr === "0x0" ? "ok" : "kritik",
    ipucu: "vcgencmd get_throttled — 0x0 dışı her değer besleme ya da ısı kısıtlaması",
  });

  const v = say("gerilim_v");
  s.push({
    etiket: "Besleme",
    deger: v === undefined ? yok : `${v.toFixed(2)} V`,
    renk: v === undefined ? "notr" : v < 4.8 ? "kritik" : v < 4.95 ? "uyari" : "ok",
  });

  const cpu = say("cpu_yuzde");
  const yuk = say("yuk_1dk");
  const cek = say("cekirdek");
  s.push({
    etiket: "CPU",
    deger:
      cpu === undefined
        ? yok
        : `%${cpu}` + (yuk !== undefined && cek ? `  ·  yük ${yuk.toFixed(2)}/${cek}` : ""),
    renk: cpu === undefined ? "notr" : cpu >= 90 ? "kritik" : cpu >= 75 ? "uyari" : "ok",
    ipucu: "Anlık örnek (0,3 sn). Yük = 1 dk ortalaması / çekirdek sayısı",
  });

  const bos = say("mem_bos_mb");
  const top = say("mem_toplam_mb");
  const kullanim = bos !== undefined && top ? Math.round(((top - bos) / top) * 100) : undefined;
  s.push({
    etiket: "Bellek",
    deger:
      bos === undefined || !top ? yok : `${bos} MB boş / ${top} MB  (%${kullanim} dolu)`,
    renk:
      kullanim === undefined ? "notr" : kullanim >= 90 ? "kritik" : kullanim >= 80 ? "uyari" : "ok",
  });

  const dy = say("disk_yuzde");
  s.push({
    etiket: "Disk (kök)",
    deger: dy === undefined ? yok : `%${dy} dolu` + (d["disk_bos"] ? `  ·  ${d["disk_bos"]} boş` : ""),
    renk: dy === undefined ? "notr" : dy >= 90 ? "kritik" : dy >= 80 ? "uyari" : "ok",
    ipucu: "Disk dolarsa bir sonraki uçuş KAYDEDİLMEZ (14 Ağustos'ta yaşandı)",
  });

  const kayit = say("kayit_mb");
  if (kayit !== undefined) {
    s.push({
      etiket: "Uçuş kayıtları",
      deger: kayit >= 1024 ? `${(kayit / 1024).toFixed(1)} GB` : `${kayit} MB`,
      renk: "notr",
    });
  }

  const dbm = say("wifi_dbm");
  s.push({
    etiket: "Wi-Fi",
    deger:
      dbm === undefined
        ? yok
        : `${dbm} dBm` + (d["wifi_ssid"] ? `  ·  ${d["wifi_ssid"]}` : ""),
    renk: dbm === undefined ? "notr" : dbm <= -75 ? "uyari" : "ok",
    ipucu: "Wi-Fi yalnız SSH ve QGC içindir; uçuş mesh üzerinden sürer",
  });

  const kd = d["konteyner_durum"];
  s.push({
    etiket: "Konteyner",
    deger: kd === undefined ? yok : String(kd).replace(/\|/g, "  ·  "),
    renk: kd === undefined ? "notr" : String(kd).includes("Up") ? "ok" : "kritik",
  });

  const ros = say("ros_surec");
  s.push({
    etiket: "ROS süreçleri",
    deger: ros === undefined ? yok : String(ros),
    renk: ros === undefined ? "notr" : ros === 0 ? "kritik" : ros < 10 ? "uyari" : "ok",
  });

  const up = say("uptime_sn");
  s.push({
    etiket: "Açık kalma süresi",
    deger: up === undefined ? yok : sn_metin(up),
    renk: "notr",
    ipucu: "Beklenmedik şekilde küçükse Pi yeniden başlamıştır",
  });

  const iy = say("izleme_yas_sn");
  if (iy !== undefined) {
    s.push({
      etiket: "Sistem izleme tazeliği",
      deger: `${sn_metin(iy)} önce`,
      renk: iy > 120 ? "uyari" : "ok",
      ipucu: "yelpence-izle 10 sn'de bir yazıyor; eskiyse timer durmuş",
    });
  }
  return s;
}

/** Pi sağlık paneli — veri YALNIZ SSH ile gelir, mesh'ten geçmez. */
export function RpiPanel({ droneId, droneAdi, onClose }: RpiPanelProps) {
  const [durum, setDurum] = useState<RpiDurum | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState<string | null>(null);
  const iptal = useRef(false);

  const cek = useCallback(async () => {
    setYukleniyor(true);
    try {
      const c = await rpi.oku(droneId);
      if (!iptal.current) {
        setDurum(c);
        setHata(null);
      }
    } catch (e) {
      if (!iptal.current) {
        setHata(e instanceof Error ? e.message : "Yer istasyonuna ulaşılamadı");
      }
    } finally {
      if (!iptal.current) setYukleniyor(false);
    }
  }, [droneId]);

  useEffect(() => {
    iptal.current = false;
    void cek();
    const t = setInterval(() => void cek(), YENILE_MS);
    return () => {
      iptal.current = true;
      clearInterval(t);
    };
  }, [cek]);

  const veri = durum?.ssh_ok ? satirlar(durum.degerler) : [];

  return (
    <div className="rpi-overlay" onClick={onClose}>
      <div
        className="rpi-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={`${droneAdi} Raspberry Pi durumu`}
      >
        <header className="rpi-modal__head">
          <h2>{droneAdi} — Raspberry Pi</h2>
          <span className="rpi-modal__kaynak">
            {yukleniyor ? "okunuyor…" : durum?.ssh_ok ? "SSH" : "bağlantı yok"}
          </span>
          <button className="rpi-modal__close" onClick={onClose} aria-label="Kapat">
            ✕
          </button>
        </header>

        <div className="rpi-modal__body">
          {hata && <div className="rpi-iz rpi-iz--hata">{hata}</div>}

          {!hata && durum && !durum.ssh_ok && (
            <div className="rpi-iz rpi-iz--hata">
              {durum.hata ?? "SSH bağlantısı yok"}
            </div>
          )}

          {!hata && !durum && yukleniyor && (
            <div className="rpi-iz">Pi'ye bağlanılıyor…</div>
          )}

          {veri.map((r) => (
            <div key={r.etiket} className="rpi-satir" title={r.ipucu}>
              <span className="rpi-satir__etiket">{r.etiket}</span>
              <span className={`rpi-satir__deger rpi-satir__deger--${r.renk} mono`}>
                {r.deger}
              </span>
            </div>
          ))}
        </div>

        <footer className="rpi-modal__foot">
          <span className="rpi-modal__not">
            Bu veri mesh'ten geçmez — yalnız SSH ile okunur.
          </span>
          <button className="rpi-modal__yenile" onClick={() => void cek()} disabled={yukleniyor}>
            {yukleniyor ? "…" : "Yenile"}
          </button>
        </footer>
      </div>
    </div>
  );
}
