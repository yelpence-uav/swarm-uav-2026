import type { KumandaVerisi } from "../../types/telemetry";
import "./KumandaGorunum.css";

/**
 * SÜRÜ KUMANDASI — sanal görünüm (Görev 2).
 *
 * Veri kaynağı MESH: pilot uçağı (ylp00) `SwarmControlCommand` yayınlıyor,
 * base ESP köprüsü `/swarm/public/control/command`'a düşürüyor, backend
 * telemetri anlık görüntüsünde `kumanda` alanı olarak veriyor.
 * **Yeni mesh trafiği YOK** — zaten uçan veri gösteriliyor.
 *
 * 🔴 NEDEN HAM PWM DEĞİL YORUMLANMIŞ KOMUT: gösterdiğimiz şey sürünün
 * GÖRDÜĞÜ değerler, yani `rc_eksen`'den geçmiş hâlleri. Ham kanala bakmak
 * işaret hatalarını gizler — 31 Ağustos'ta kumanda değişince `TERS_YAW`
 * True'dan False'a döndü ve bu ancak yorumlanmış komuta bakınca görülüyordu.
 *
 * 🔴 NEDEN İKİ KAPI AYRI GÖSTERİLİYOR: "çubuğu oynatıyorum bir şey olmuyor"
 * durumunun sebebi hep bu ikisinden biri —
 *   deadman  : SwA emniyet anahtarı (bu kumandada AŞAĞI = AÇIK)
 *   geçerli  : gaz merkez kapısı (B18) — gaz bir kez ortaya getirilmeli
 * Biri kapalıysa eksenler sıfırlanır ve sürü komut almaz.
 */


const FORMASYON_AD: Record<number, string> = {
  0: "belirsiz",
  1: "ok başı",
  2: "V",
  3: "çizgi",
};

/** Kumanda kapanınca alıcı son çerçeveyi tutuyor (TUZAKLAR §9.5 sınıfı):
 *  donuk veri canlı görünür. Yaş eşiği o yüzden var. */
const BAYAT_ESIK_S = 1.5;

function Eksen({
  ad,
  deger,
  arti,
  eksi,
  aktif,
}: {
  ad: string;
  deger: number;
  arti: string;
  eksi: string;
  aktif: boolean;
}) {
  const yuzde = Math.max(-1, Math.min(1, deger)) * 50;
  const notr = Math.abs(deger) < 0.08;
  return (
    <div className="kg-eksen">
      <span className="kg-eksen__ad">{ad}</span>
      <div className="kg-eksen__yol">
        <div className="kg-eksen__merkez" />
        <div
          className={"kg-eksen__dolgu" + (aktif ? "" : " kg--sonuk")}
          style={{
            left: deger >= 0 ? "50%" : `${50 + yuzde}%`,
            width: `${Math.abs(yuzde)}%`,
          }}
        />
      </div>
      <span className="kg-eksen__deger">
        {deger >= 0 ? "+" : ""}
        {deger.toFixed(2)}
      </span>
      <span className={"kg-eksen__yon" + (notr ? " kg--sonuk" : "")}>
        {notr ? "—" : deger > 0 ? arti : eksi}
      </span>
    </div>
  );
}

function Salter({
  ad,
  acik,
  acikYazi,
  kapaliYazi,
  uyari,
}: {
  ad: string;
  acik: boolean;
  acikYazi: string;
  kapaliYazi: string;
  uyari?: boolean;
}) {
  return (
    <div className="kg-salter">
      <span className="kg-salter__ad">{ad}</span>
      <span
        className={
          "kg-salter__durum " +
          (acik ? (uyari ? "kg--uyari" : "kg--ok") : "kg--kapali")
        }
      >
        {acik ? acikYazi : kapaliYazi}
      </span>
    </div>
  );
}

export function KumandaGorunum({ kumanda }: { kumanda: KumandaVerisi | null }) {
  const bayat = !kumanda || kumanda.yas_s > BAYAT_ESIK_S;
  const aktif = !!kumanda && kumanda.deadman && kumanda.gecerli && !bayat;

  return (
    <section className="kg">
      <div className="kg-baslik">
        <h2>Sürü Kumandası</h2>
        <span className={"kg-rozet " + (bayat ? "kg--kapali" : "kg--ok")}>
          {!kumanda
            ? "veri yok"
            : bayat
              ? `bayat ${kumanda.yas_s.toFixed(1)} s`
              : "canlı"}
        </span>
      </div>

      {!kumanda ? (
        <div className="kg-bos">
          Kumanda komutu mesh'ten gelmiyor.
          <br />
          Pilot uçağında <code>joystick</code> düğümü açık mı?
        </div>
      ) : (
        <>
          {/* Kapılar en üstte: eksenler ölüyse sebebi burada görünür. */}
          <div className="kg-kapilar">
            <Salter
              ad="SwA emniyet"
              acik={kumanda.deadman}
              acikYazi="AÇIK"
              kapaliYazi="KİLİTLİ"
            />
            <Salter
              ad="gaz kapısı"
              acik={kumanda.gecerli}
              acikYazi="GEÇERLİ"
              kapaliYazi="gazı ORTAYA getir"
            />
          </div>

          <div className="kg-eksenler">
            <Eksen ad="pitch" deger={kumanda.pitch} arti="▲ ileri" eksi="▼ geri" aktif={aktif} />
            <Eksen ad="roll" deger={kumanda.roll} arti="▶ sağa" eksi="◀ sola" aktif={aktif} />
            <Eksen ad="yaw" deger={kumanda.yaw} arti="↻ saat yönü" eksi="↺ ters" aktif={aktif} />
            <Eksen ad="gaz" deger={kumanda.gaz} arti="▲ tırmanış" eksi="▼ alçalma" aktif={aktif} />
          </div>

          <div className="kg-alt">
            <div className="kg-alan">
              <span className="kg-alan__ad">mod</span>
              <span className="kg-alan__deger">
                {kumanda.mod === 2 ? "MANEVRA" : "HAREKET"}
              </span>
            </div>
            <div className="kg-alan">
              <span className="kg-alan__ad">formasyon</span>
              <span className="kg-alan__deger">
                {FORMASYON_AD[kumanda.formasyon] ?? kumanda.formasyon}
                {kumanda.aralik_m > 0 ? ` · ${kumanda.aralik_m} m` : ""}
              </span>
            </div>
            <Salter
              ad="SwD kalkış"
              acik={kumanda.takeoff}
              acikYazi="İSTENDİ"
              kapaliYazi="—"
              uyari
            />
            <Salter
              ad="SwD iniş"
              acik={kumanda.land}
              acikYazi="MANDAL BASILI"
              kapaliYazi="—"
              uyari
            />
          </div>
        </>
      )}
    </section>
  );
}
