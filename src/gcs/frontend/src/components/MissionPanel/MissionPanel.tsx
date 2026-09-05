import { useState } from "react";
import {
  CommandFailure,
  MISSION_COMMAND,
  MISSION_ID,
  missionApi,
  type TriggerMissionResponse,
  type FlightParams,
} from "../../services/api";
import "./MissionPanel.css";

/**
 * Faz 5 - şartname uyumlu görev tetikleyici.
 *
 * Görev 1 sırasında şartname "GCS'ten görev başlatma DIŞINDA müdahale yasak"
 * der. Bu panel o tek müdahale noktasıdır.
 *
 * Test/güvenlik butonları (ABORT/RTL/LAND) ayrıdır - yarışmada basılırsa
 * görev başarısız sayılır, sadece kaza/acil durumda kullanılır.
 */

const MISSION_LABELS: Record<number, string> = {
  [MISSION_ID.DYNAMIC_SWARM]: "Görev 1 — Dinamik Sürü",
  [MISSION_ID.SEMI_AUTONOMOUS]: "Görev 2 — Yarı Otonom",
  [MISSION_ID.TEST]: "Test Görevi",
};

interface MissionPanelProps {
  missionActive: boolean;
  missionId: number;
  onMissionIdChange: (id: number) => void;
  /* Takım ID App'te tutuluyor: haritadaki acil sonlandırma da aynı değeri
     kullanıyor ve iki yerde ayrı state olsaydı biri güncellenip diğeri
     unutulurdu (CLAUDE.md §9). */
  teamId: string;
  onTeamIdChange: (v: string) => void;
  /* Sürü davranış ayarları Ayarlar panelinde giriliyor ama BAŞLAT
     paketiyle gitmek ZORUNDA (tek taşıma yolu o). Burada okunup Görev 2
     BAŞLAT'ın parameters_json'ına ekleniyor; ikinci bir giriş alanı
     açmıyoruz, yoksa aynı değer iki yerde tutulurdu (CLAUDE.md §9). */
  flightParams: FlightParams;
}

export function MissionPanel({
  flightParams,
  missionActive,
  missionId,
  onMissionIdChange,
  teamId,
  onTeamIdChange,
}: MissionPanelProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<TriggerMissionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 🔴 MADDE 29 — Görev 2 BAŞLAT'tan ÖNCE sorulan iki değer.
  // Başlangıç değeri BOŞ, "7" değil: dolu bir kutu operatöre "bu sayı
  // gönderiliyor" der, oysa boş kutu HİÇBİR ŞEY göndermiyor ve uçak
  // kendi varsayılanını (aralık 7 m) koruyor. İkisi farklı durum.
  const [aralik, setAralik] = useState("");
  const [irtifa, setIrtifa] = useState("");
  // 🔴 GÖREV 1 BAŞLANGIÇ FORMASYONU — 4 Eylül 2026.
  // Şartname: "Sürü ajanları hakemler tarafından başlangıçta yerde
  // istenilen formasyonda dizilir" (madde 1) ve aralık hakem tarafından
  // veriliyor ("Örn: 5m", madde 2). Yani ikisi de görev anında öğrenilir.
  // Önceden bu yalnız baslat.sh parametresiydi: değiştirmek için ÜÇ
  // UÇAKTA dosya yazıp konteyner restart etmek gerekiyordu.
  // BOŞ = uçaktaki varsayılan korunur; boş bırakmak geçerli bir seçim.
  const [g1Formasyon, setG1Formasyon] = useState("");
  const [g1Aralik, setG1Aralik] = useState("");
  const [g1Irtifa, setG1Irtifa] = useState("");

  async function trigger(
    commandCode: number,
    commandLabel: string,
    confirmLevel: "none" | "single" | "double" = "none",
  ) {
    // Geri dönüşü olmayan komutlar (görev iptali) için kazara basmayı önleyen
    // onay zinciri. "double" -> ardışık iki ayrı onay diyaloğu.
    if (confirmLevel !== "none") {
      if (!window.confirm(`${commandLabel} komutu gönderilecek. Emin misin?`)) {
        return;
      }
    }
    if (confirmLevel === "double") {
      if (
        !window.confirm(
          `SON UYARI - ${commandLabel}\n\n` +
            "Bu işlem görevi sonlandırır ve görev BAŞARISIZ sayılır. " +
            "Tüm sürü görevi durdurulacak.\n\nOnaylıyor musun?",
        )
      ) {
        return;
      }
    }
    setBusy(commandLabel);
    setError(null);
    setLastResult(null);
    try {
      // 🔴 MADDE 29 — Görev 2 BAŞLAT'ta aralık/irtifa gönderilir.
      // Boş bırakılan alan JSON'a HİÇ konmaz; uçak o alan için kendi
      // varsayılanını korur (aralık 7 m). Boş bırakmak geçerli bir seçim.
      // Sınır denetimi UÇAKTA (canli_param.g2_ayar_dogrula) — burada
      // ikinci bir kopya tutmuyoruz, kaçınılmaz olarak ayrışırlar.
      let parameters_json = "";
      if (
        missionId === MISSION_ID.SEMI_AUTONOMOUS &&
        commandCode === MISSION_COMMAND.START
      ) {
        const p: Record<string, number> = {};
        const a = parseFloat(aralik);
        const h = parseFloat(irtifa);
        if (isFinite(a)) p.aralik_m = a;
        if (isFinite(h)) p.irtifa_m = h;
        // Ayarlar panelindeki sürü davranışı — 0 = "değiştirme", JSON'a
        // hiç konmaz ve uçak kendi varsayılanını korur.
        const suru: Array<[string, number]> = [
          ["morf_hiz_mps", flightParams.suru_morf_hiz_mps],
          ["hareket_hiz_mps", flightParams.suru_hareket_hiz_mps],
          ["yaw_hiz_deg_s", flightParams.suru_yaw_hiz_deg_s],
          ["egim_tavan_deg", flightParams.suru_egim_tavan_deg],
        ];
        for (const [ad, v] of suru) {
          if (isFinite(v) && v > 0) p[ad] = v;
        }
        if (Object.keys(p).length > 0) parameters_json = JSON.stringify(p);
      }
      // GÖREV 1 BAŞLAT — başlangıç formasyonu + aralık. Aynı kural:
      // seçilmeyen alan JSON'a HİÇ konmaz, uçak kendi varsayılanını korur.
      if (
        missionId === MISSION_ID.DYNAMIC_SWARM &&
        commandCode === MISSION_COMMAND.START
      ) {
        const p: Record<string, number> = {};
        const f = parseInt(g1Formasyon, 10);
        const ga = parseFloat(g1Aralik);
        const gi = parseFloat(g1Irtifa);
        if (isFinite(f) && f > 0) p.formasyon = f;
        if (isFinite(ga)) p.aralik_m = ga;
        if (isFinite(gi) && gi > 0) p.irtifa_m = gi;
        if (Object.keys(p).length > 0) parameters_json = JSON.stringify(p);
      }
      const resp = await missionApi.trigger({
        mission_id: missionId,
        command: commandCode,
        team_id: teamId.trim(),
        parameters_json,
      });
      setLastResult(resp);
    } catch (e) {
      const msg =
        e instanceof CommandFailure
          ? `HTTP ${e.http_status}: ${e.message}`
          : `Hata: ${(e as Error).message}`;
      setError(msg);
    } finally {
      setBusy(null);
    }
  }

  const startDisabled = busy !== null || teamId.trim().length === 0 || missionActive;

  return (
    <section className="mission-panel">
      <div className="mission-panel__row">
        <label className="mission-panel__field">
          <span>Görev:</span>
          <select
            value={missionId}
            onChange={(e) => onMissionIdChange(Number(e.target.value))}
            disabled={busy !== null}
          >
            {Object.entries(MISSION_LABELS).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="mission-panel__field">
          <span>Takım ID:</span>
          <input
            type="text"
            value={teamId}
            onChange={(e) => onTeamIdChange(e.target.value)}
            placeholder="team_1"
            disabled={busy !== null}
            spellCheck={false}
          />
        </label>

        {missionId === MISSION_ID.TEST ? (
          // Yeri ayrildi, isleyisi HENUZ BAGLANMADI. Baslat dugmesini aktif
          // birakmak backend'e tanimsiz bir mission_id gondermek olurdu.
          // TEST GOREVI = DINAMIK SLOT (29 Agustos 2026, operator):
          // "o an yazdigimiz test neyse onu kosturmak icin degistirilecek".
          // Yani burasi kalici bir ozellik degil, her testte YENIDEN
          // BAGLANACAK bir kanca. Bos birakilmasi bilerek — aktif bir
          // BASLAT dugmesi arka uca tanimsiz bir mission_id gonderirdi.
          <div className="mission-panel__hint mission-panel__hint--bekliyor">
            Test görevi boşta — o anki test buraya bağlanır
          </div>
        ) : (
          <button
            className="mission-panel__start"
            disabled={startDisabled}
            onClick={() => trigger(MISSION_COMMAND.START, "GÖREV BAŞLAT")}
            title={
              missionActive
                ? "Görev zaten aktif"
                : startDisabled
                  ? "Takım ID gerekli"
                  : "Görev başlatma servis çağrısı yap"
            }
          >
            {busy === "GÖREV BAŞLAT" ? "GÖNDERİLİYOR..." : "▶ GÖREV BAŞLAT"}
          </button>
        )}
      </div>

      {/* 🔴 GÖREVİ DURDUR — 31 Ağustos 2026, operatör isteği.
          Kumandanın KALKIŞ YETKİSİNİ geri alır (G2-K10 üçüncü kapı kapanır).
          Mesh'ten yayın olarak gider; her uçak kendi mission_fsm'ini
          ABORTED'a alır ve kısa bir soğuma başlatır — yoksa hâlâ 8'de olan
          bir komşunun durum biti onu hemen yeniden başlatırdı (G2-K11).

          ⚠️ UÇAN SÜRÜYÜ DURDURMAZ: mode_manager READY'ye geçtikten sonra
          mission_state'i yeniden okumuyor. Havadaki sürünün inişi SwD ya da
          kill switch. Buton yerde elleçleme için: pervane takarken SwD'ye
          çarpmak üç uçağı birden armlamasın. */}
      {/* 🔴 GÖREV 2 ÖN AYARLARI — madde 29, 31 Ağustos 2026.
          Şartname aralığı ve kalkış irtifasını GÖREV ÖNCESİ veriyor
          ("Örn: 15m") ve hakem başka bir sayı söyleyebilir. Değerler
          BAŞLAT paketiyle mesh'ten ÜÇ UÇAĞA AYNI ANDA gider — görev
          sırasında yeni bir komut yolu AÇILMAZ (şartname §5.2: YKİ
          müdahalesi görevi başarısız yapar).

          Boş bırakmak GEÇERLİ: o alan için uçak kendi varsayılanını
          korur (aralık 7 m). Bu yüzden kutular boş başlıyor — dolu bir
          kutu "bu değer gönderiliyor" izlenimi verirdi.

          Sınır denetimi UÇAKTA (canli_param.g2_ayar_dogrula): aralık
          4-25.5 m (alt sınır çarpışma eşiği, üst sınır mesh tavanı),
          irtifa 3-30 m. Buradaki min/max yalnız tarayıcı yardımı;
          gerçek kapı orada ve ikinci bir kopya TUTULMUYOR.

          ⚠️ VARSAYILAN SAYI BURAYA YAZILMIYOR (§9: aynı sabiti iki yere
          yazma). Varsayılan aralık `ucus_ayarlari.MOD_ARALIK_M` = 7 m ve
          uçağa `baslat.sh` ile gidiyor; buraya "7" yazılsaydı o değer
          değiştiği gün placeholder sessizce yalan söylerdi — operatör
          kutuyu 7 sanıp boş bırakır, sürü başka aralıkta açılırdı. */}
      {missionId === MISSION_ID.SEMI_AUTONOMOUS && !missionActive && (
        <div className="mission-panel__row">
          <label className="mission-panel__field">
            <span>Aralık (m):</span>
            <input
              type="number"
              step="0.5"
              min="4"
              max="25.5"
              placeholder="boş = uçaktaki varsayılan"
              value={aralik}
              onChange={(e) => setAralik(e.target.value)}
              disabled={busy !== null}
            />
          </label>
          <label className="mission-panel__field">
            <span>İrtifa (m):</span>
            <input
              type="number"
              step="0.5"
              min="3"
              max="30"
              placeholder="boş = uçaktaki varsayılan"
              value={irtifa}
              onChange={(e) => setIrtifa(e.target.value)}
              disabled={busy !== null}
            />
          </label>
        </div>
      )}

      {missionId === MISSION_ID.SEMI_AUTONOMOUS && (
        <button
          className="mission-panel__start"
          style={{ background: "#8b2c2c", borderColor: "#8b2c2c" }}
          disabled={busy !== null || teamId.trim().length === 0}
          onClick={() =>
            trigger(MISSION_COMMAND.ABORT, "GÖREVİ DURDUR", "single")
          }
          title="Kumandanın kalkış yetkisini geri alır (uçan sürüyü durdurmaz)"
        >
          {busy === "GÖREVİ DURDUR" ? "GÖNDERİLİYOR..." : "■ GÖREVİ DURDUR"}
        </button>
      )}

      {/* 🔴 GÖREV 2'DE BAŞLAT ≠ KALKIŞ — G2-K8/G2-K10 (30 Ağustos 2026).
          Buraya kadar burada "Görev 2 kumandadan başlatılır (SwD şalteri)"
          yazan bir NOT vardı ve YANLIŞTI: şartname senaryosunda madde 4
          (hakemin komutuyla yarı otonom moda geçiş) ile madde 5 (kumandadan
          kalkış) AYRI adımlar. YKİ'nin izinli tek eylemi görevi başlatmak;
          kalkış §5.2.2 gereği kumandadan.

          Bu buton mode_manager'ın ÜÇÜNCÜ KAPISINI açar (mission_state=8).
          Basılmadan SwD sürüyü ARMLAYAMAZ — bilerek. */}
      {/* 🔴 GÖREV 1 BAŞLANGIÇ FORMASYONU — 4 Eylül 2026.
          Şartname formasyonu ve aralığı görev anında veriyor (madde 1-2),
          yani sabit yazılamaz. Değer BAŞLAT paketiyle mesh'ten ÜÇ UÇAĞA
          AYNI ANDA gider — görev sırasında yeni komut yolu açılmıyor.

          ⚠️ YALNIZ TOPLANMA FORMASYONUNU belirler. QR bir formasyon
          dayattığı anda o EZER (şartname yolu her zaman üstte) — burası
          "kalkıştan sonra hangi düzende toplansınlar" sorusunun cevabı.

          ⚠️ VARSAYILAN SAYI BURAYA YAZILMIYOR (§9: aynı sabiti iki yere
          yazma). Varsayılan `ucus_ayarlari.GOREV_FORMASYON/GOREV_ARALIK_M`
          ve uçağa baslat.sh ile gidiyor; buraya kopyalansaydı o değer
          değiştiği gün bu kutu sessizce yalan söylerdi. */}
      {missionId === MISSION_ID.DYNAMIC_SWARM && !missionActive && (
        <div className="mission-panel__row">
          <label className="mission-panel__field">
            <span>Başlangıç formasyonu:</span>
            <select
              value={g1Formasyon}
              onChange={(e) => setG1Formasyon(e.target.value)}
              disabled={busy !== null}
            >
              <option value="">boş = uçaktaki varsayılan</option>
              <option value="3">Çizgi</option>
              <option value="1">Ok başı</option>
              <option value="2">V</option>
            </select>
          </label>
          <label className="mission-panel__field">
            <span>Aralık (m):</span>
            <input
              type="number"
              step="0.5"
              min="4"
              max="25.5"
              placeholder="boş = uçaktaki varsayılan"
              value={g1Aralik}
              onChange={(e) => setG1Aralik(e.target.value)}
              disabled={busy !== null}
            />
          </label>
          {/* İLK (KALKIŞ) İRTİFASI. Sürü QR'a giderken QR OKUMA
              İRTİFASINA (10 m) iner — yani buradaki değer seyir değil,
              KALKIŞ irtifasıdır. İkisi arasındaki fark kadar alçalma
              olur ve alçalma ROTA_DIKEY_HIZ ile yavaşlatılır (0.5 m/s).
              Boş bırakmak geçerli: uçak baslat.sh'ten gelen kendi
              değerini korur. */}
          <label className="mission-panel__field">
            <span>İlk irtifa (m):</span>
            <input
              type="number"
              step="1"
              min="5"
              max="30"
              placeholder="boş = uçaktaki varsayılan"
              value={g1Irtifa}
              onChange={(e) => setG1Irtifa(e.target.value)}
              disabled={busy !== null}
            />
          </label>
        </div>
      )}

      {missionId === MISSION_ID.SEMI_AUTONOMOUS && (
        <div className="mission-panel__hint mission-panel__hint--bilgi">
          BAŞLAT sürüyü <strong>yarı otonom moda alır</strong>, kalkış
          vermez. Kalkış ve iniş kumandadan (SwD) — şartname §5.2.2.
          Basılmadan kumanda sürüyü armlayamaz.
          <br />
          DURDUR kumandanın <strong>kalkış yetkisini geri alır</strong> —
          ⚠️ uçan sürüyü <strong>durdurmaz</strong>, iniş SwD ya da kill
          switch ile.
        </div>
      )}

      {/* Acil sonlandırma 29 Ağustos 2026'da HARİTANIN ALT ORTASINA taşındı
          (operatör): görev sürerken göz haritada, buton da orada olmalı.
          Bkz. components/AcilSonlandirma/. */}

      {lastResult && (
        <div
          className={
            "mission-panel__result " +
            (lastResult.success
              ? "mission-panel__result--ok"
              : "mission-panel__result--fail")
          }
        >
          {lastResult.success ? "✓" : "✗"} {lastResult.message}
        </div>
      )}
      {error && <div className="mission-panel__error">{error}</div>}
    </section>
  );
}
