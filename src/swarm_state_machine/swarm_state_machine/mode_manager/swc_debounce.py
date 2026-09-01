# Copyright 2026 Yelpence
"""SwC (formasyon salteri) debounce. Saf mantik, ROS yok.

NEDEN AYRI MODUL: kardesleri rc_eksen.py · swd_mandal.py · canli_param.py
ile ayni gerekce — dugum rclpy olmadan import edilemiyor, bu mantik ise
birim testle KILITLENMEK ZORUNDA.

═══════════════════════════════════════════════════════════════════
NEDEN VAR (gorev2.md madde 26)

SwC detentli 3 konumlu: okbasi (1000) · V (1500) · cizgi (2000).
Okbasindan cizgiye giderken ORTADAN GECMEK ZORUNLU ve orta = V
FORMASYONU. Debounce olmadan kod her ayri geciste formasyon degisimi
tetikliyordu, yani hakem "cizgiye gec" dedigi anda suru ONCE V'ye morf
olmaya BASLIYORDU.

Bedeli olculmustu: kuru test okbasi->V en dar anini 4,95 m verdi,
kacinma girisi 4,0 m. Yani istenmeyen ara morf kacinmanin kucagina
giriyor ve carpisma -20xN.

═══════════════════════════════════════════════════════════════════
GECERLI OLCUM — 31 Agustos 2026, ylp00, YENI KUMANDA
(kumanda_web.py "madde 26" paneli, iki ayri kayit)

    kayit 1:  852 · 364 · 215 · 214 · 200 · 158 ms   -> tavan 852
    kayit 2:  321 · 162 · 120 · 100 ·  92       ms   -> tavan 321

🔴 IKI KAYIT CELISIYOR — tavanlar arasinda 2,6 KAT fark var. 852 ms'nin
gercek bir gecis mi yoksa ortada DURAKLAMIS bir el mi oldugu
COZULMEDI. Ayrica web arayuzu 50 ms'de bir ornekliyor (akis 32,5 Hz),
yani birkac gecis "0 ms" okundu: cozunurlugun altinda kaldilar.

ESIK = 1300 ms — BILEREK MUHAFAZAKAR. Hata yonu asimetrik:
  * esik DUSUK kalirsa  -> gercek gecis esigi asar -> sahte V morfu ->
    okbasi->V en dar an 4,95 m, kacinma girisi 4,0 m -> CARPISMA -20xN
  * esik YUKSEK olursa  -> hakem "V'ye gec" der, suru 1,3 sn sonra
    baslar. Gorev temposunda fark edilmez.
Bilmedigimiz icin guvenli tarafta duruyoruz (852 x ~1,5).

⚠️ DAHA IYI OLCUM MUMKUN ve esigi dusurebilir: cerceve zaman
damgalarindan hesaplayan bir olcum 852'nin duraklama olup olmadigini
ayirt eder. gorev2.md §7.12'de acik madde olarak duruyor.
═══════════════════════════════════════════════════════════════════
ESKI KUMANDA (30 Agustos, FS-i6X #2) — TARIHCE, artik gecerli DEGIL

11 gecis: 92 · 94 · 154 · 185 · 185 · 216 · 246 · 246 · 339 · 339 · 342
Tavan 342 ms ve salter BILEREK YAVAS cevrilince de degismedi — o
salterin detenti gecisi kendisi tamamliyordu. Esik 500 ms idi.
═══════════════════════════════════════════════════════════════════

⚠️ Kumanda ya da salter degisirse BU SAYI GECERSIZ olur — 31 Agustos'ta
tam bu yasandi. Olcumu tekrarla: `src/gcs/kumanda_web.py` arayuzu.
"""

# Olculen tavan 852 ms; ~%50 pay. Gerekce ve celiski yukarida.
VARSAYILAN_ESIK_MS = 1300.0


class SwcDebounce:
    """SwC bolgesi N ms KARARLI kalmadan formasyon degisimi tetiklemez."""

    def __init__(self, esik_ms: float = VARSAYILAN_ESIK_MS) -> None:
        self.esik_s = max(0.0, float(esik_ms)) / 1000.0
        # None = henuz hicbir bolge kararlilasmadi (acilis).
        self.kararli = None
        self._aday = None
        self._aday_t = 0.0

    def guncelle(self, bolge, simdi: float) -> bool:
        """Yeni bolge ornegini isler.

        Args:
            bolge: o anki formasyon secimi (SwarmControlCommand.FORMATION_*).
            simdi (float): saniye cinsinden monotonik zaman.

        Returns:
            bool: YENI bir formasyon kararlilastiysa True (tek atis).
        """
        if bolge != self._aday:
            # Bolge degisti: sayac BASTAN baslar. Gecerken ortada gecen
            # 342 ms bu yuzden hicbir zaman esige ulasamiyor — ulasmadan
            # obur uca varip adayi degistiriyor.
            self._aday = bolge
            self._aday_t = simdi
            return False

        if bolge == self.kararli:
            return False

        if (simdi - self._aday_t) < self.esik_s:
            return False

        self.kararli = bolge
        return True

    def esitle(self, bolge, simdi: float) -> None:
        """Tetiklemeden durumu hizalar.

        Emniyet (SwA) KAPALIYKEN kullanilir: salter izlenmeye devam eder
        ama formasyon degisimi URETILMEZ. Hizalanmasaydi emniyet acildigi
        anda "bolge degisti" gorunur ve SAHTE bir degisim tetiklenirdi —
        joystick_interpreter'in emniyet dalindaki mevcut kural bu.
        """
        self.kararli = bolge
        self._aday = bolge
        self._aday_t = simdi
