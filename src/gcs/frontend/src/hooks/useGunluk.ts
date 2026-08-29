import { useCallback, useEffect, useRef, useState } from "react";

import { gunluk, type GunlukKaydi } from "../services/api";

/** Bellekte tutulan en fazla kayıt. Arka uçtaki defter daha derin (2000);
 *  buradaki sınır DOM'u ve belleği şişirmemek için. Daha eskisi gerekirse
 *  `gunluk/yki_olaylar.jsonl` dosyasından okunur. */
const BELLEK_SINIRI = 400;

const ARALIK_MS = 2000;

const KRITIK = new Set(["critical", "emergency"]);

/** Olay defterini TEK yerden çeker ve bütün kartlara dağıtır.
 *
 * NEDEN TEK ÇEKİCİ: her drone kartı kendi sorgusunu atsaydı üç uçakta
 * saniyede 1,5 istek olurdu ve her kart defteri ayrı ayrı tutardı. Defter
 * zaten küçük; bir kez çekip süzmek hem ucuz hem tutarlı.
 *
 * OKUNDU İZLEME: kart açıkken gelen kritik olay yanıp sönmemeli — zaten
 * gözünün önünde. Bu yüzden "görülen sıra" drone başına tutuluyor.
 */
export function useGunluk() {
  const [kayitlar, setKayitlar] = useState<GunlukKaydi[]>([]);
  const [aktif, setAktif] = useState(true);
  const [hata, setHata] = useState(false);
  // drone_id -> bu sira numarasina kadar gorulmus sayilir
  const [gorulen, setGorulen] = useState<Record<number, number>>({});
  // Basliktaki bildirim butonu icin AYRI imlec: kart bazli `gorulen`den
  // bagimsiz, cunku panel butun dronelarin olaylarini birlikte gosteriyor.
  const [panelGorulen, setPanelGorulen] = useState(0);

  // Artimli imlec. State degil ref: her turda degisiyor ama yeniden cizim
  // gerektirmiyor.
  const sonSira = useRef(0);

  useEffect(() => {
    let iptal = false;

    const tur = async () => {
      try {
        const c = await gunluk.oku({ sonra: sonSira.current, limit: 200 });
        if (iptal) return;
        setAktif(c.aktif);
        setHata(false);
        if (c.kayitlar.length > 0) {
          sonSira.current = Math.max(
            sonSira.current,
            ...c.kayitlar.map((k) => k.sira),
          );
          // En yeni USTTE: operator ucus sirasinda goz atiyor, az once ne
          // oldugunu gormek icin kaydirmak zorunda kalmamali.
          setKayitlar((eski) =>
            [...c.kayitlar].reverse().concat(eski).slice(0, BELLEK_SINIRI),
          );
        }
      } catch {
        // Arka uc kapaliysa sessizce beklemeye devam: kirmizi kutuyla ekrani
        // mesgul etmiyoruz, kartta kucuk bir iz yeter.
        if (!iptal) setHata(true);
      }
    };

    void tur();
    const t = setInterval(tur, ARALIK_MS);
    return () => {
      iptal = true;
      clearInterval(t);
    };
  }, []);

  /** Bir drone'un kayıtları + sistem geneli (drone_id = 0).
   *
   * Sistem olaylarını da veriyoruz: "Pi diski doldu" o drone'u ilgilendirir
   * ve ayrı bir yerde aranmak zorunda kalmamalı. */
  const droneKayitlari = useCallback(
    (droneId: number) =>
      kayitlar.filter((k) => k.drone_id === droneId || k.drone_id === 0),
    [kayitlar],
  );

  /** O drone için HENÜZ GÖRÜLMEMİŞ kritik/acil olay var mı. */
  const kritikVar = useCallback(
    (droneId: number) => {
      const esik = gorulen[droneId] ?? 0;
      return kayitlar.some(
        (k) =>
          (k.drone_id === droneId || k.drone_id === 0) &&
          KRITIK.has(k.siddet) &&
          k.sira > esik,
      );
    },
    [kayitlar, gorulen],
  );

  /** Bildirim panelinde HENÜZ GÖRÜLMEMİŞ kayıt sayısı (uyarı ve üstü).
   *
   * `info` sayılmıyor: rozet sürekli dolu görünürse kimse bakmaz. Operatörün
   * fark etmesi gereken şey uyarı/kritik/acil. */
  const okunmamis = kayitlar.filter(
    (k) => k.siddet !== "info" && k.sira > panelGorulen,
  ).length;

  /** Paneldeki her şeyi görülmüş say (panel açılınca çağrılır). */
  const hepsiniOkunduIsaretle = useCallback(() => {
    const enBuyuk = kayitlar.reduce((mx, k) => (k.sira > mx ? k.sira : mx), 0);
    setPanelGorulen((g) => (g >= enBuyuk ? g : enBuyuk));
  }, [kayitlar]);

  /** O drone'un kayıtlarını görülmüş say (log açıkken çağrılır). */
  const okunduIsaretle = useCallback(
    (droneId: number) => {
      const enBuyuk = kayitlar.reduce((m, k) => (k.sira > m ? k.sira : m), 0);
      setGorulen((g) =>
        g[droneId] === enBuyuk ? g : { ...g, [droneId]: enBuyuk },
      );
    },
    [kayitlar],
  );

  return {
    kayitlar,
    droneKayitlari,
    kritikVar,
    okunduIsaretle,
    okunmamis,
    hepsiniOkunduIsaretle,
    aktif,
    hata,
  };
}
