# YAPILACAKLAR

**Son güncelleme:** 1 Eylül 2026, 22:48 — kamera onarıldı, jöle ÖLÇÜLÜYOR · 🔴 ylp02 MAVROS bağlı değil · 🔴 ylp00 roll · 🔴 HOME kayması

> **Finale 5 gün.** Bu liste artık "her fikir" değil, **bu 8 günde
> yapılacak iş.** Bir madde buraya giriyorsa birinin onu yapması planlanıyor
> demektir. 135 maddelik eski liste 29 Ağustos'ta kesildi — tamamı git'te:
> `git show 783afab:docs/YAPILACAKLAR.md`

**Önem:** 🔴P0 uçuş engeli · 🟠P1 finalde puan kaybı · 🟡P2 önemli · ⚪P3 ileride

---

## 🔴 P0 — bunlar kapanmadan ilgili uçuş yapılmaz

- `[ ]` 🔴 **ylp02'de MAVROS PX4'E BAĞLI DEĞİL.** 1 Eylül 22:30 ölçümü:
  `/drone_3/mavros/state` → `connected:false`, `mode:""`; snapshot'ta
  `imu_healthy`/`baro_healthy`/`mag_healthy` **üçü de False**, `mode:"?"`;
  `imu/mag` ve `global_position/raw/fix` konularında **yayın yok**.
  Karşılaştırma: ylp00 aynı anda fix 3, 28 uydu, hepsi True.
  ⚠️ Barometre ve IMU **iç mekânda da çalışır** — bu "GPS yok" değil,
  **FCU ile hiç konuşulmuyor.** `/dev/ttyAMA0` yerinde.
  *Şüpheli:* açık P0 olan **gevşek PX4 güç soketi** (aynı sınıf arıza) —
  uçak 1 Eylül'de çok elden geçti (ters çevrildi, kamera 2 kez söküldü,
  defalarca kapatılıp açıldı). *Operatör çözeceğini söyledi.*
  **Bu kapanmadan ylp02 UÇMAZ.**

- `[ ]` 🔴 **ylp00 ROLL ARIZASI — uçmadan önce kapat.** PX4 iki bağımsız
  denemede `Attitude failure (roll)` → `Failsafe activated` verdi (kalkıştan
  5,6 sn sonra, ikisinde de). Uçak fiziksel olarak yattı, motorlar kesildi.
  Kill switch 168 sn sonra, uçak zaten yerdeyken basıldı — sebep değil.
  *Yapılacak:* ① **şarjlı pil** — kalkışta 15,29 → **14,72 V** çöktü (%58'di)
  ② pervaneler: gevşek/ters/hasarlı mı ③ motor yatakları ④ kollarda çatlak.
  Ayrıntı `GUNLUK.md` 1 Eylül kaydı.

- `[ ]` 🔴 **ylp02'nin havadaki failsafe sebebi BİLİNMİYOR.** `Failsafe
  activated` → **ALTCTL** (konum kestirimi geçersiz). Elenenler: RC sabit ve
  rssi 41 · setpoint 50 Hz · kaçınma hiç girmedi (`avoid=0`) · Here4
  konnektörü sarsıldı, arıza tekrar üretilemedi. PX4 ulog kapalı olduğu için
  gerekçe okunamıyor. *Karar gerekiyor:* ylp02 tekrar uçsun mu, yoksa önce
  ulog'u geçici açıp mı uçalım (`CLAUDE.md` "Pixhawk'ta log açma" diyor —
  RAM sınırı; geçici istisna operatör kararı).

- `[ ]` 🔴 **MANEVRA MODU DÜZELTİLDİ, UÇAKTA DOĞRULANMADI.** `px4_bridge:838`
  zemin ofseti artık yalnız guided goto'ya uygulanıyor; dağıtıldı, md5 üçünde
  de aynı, 4 regresyon testi var. Ama hiçbir uçuş manevraya ulaşmadı.
  *Tek soru:* "manevraya geçince sürü irtifasını koruyor mu?" *En kısa test:*
  kalkış → 5 m → **SwB manevra, çubuklar merkezde, 10 sn irtifayı izle** →
  hareket moduna dön → in. ~90 sn.


- `[x]` ✅ **DAĞITIM YAPILDI (31 Ağu 06:00)** — üç uçağa `swarm_state_machine`
  + `swarm_control`, `gorevfsm` bayrağı, yeni env. Parametreler doğrulandı.
  Eski madde:
- `[x]` ~~🔴 **DAĞITIM — uçaklardaki `TERS_YAW` YANLIŞ.**~~ 31 Ağustos'ta sürü
  kumandası değişti ve `rc_eksen.TERS_YAW` True→False çekildi (yeni kumandada
  yaw sağı ÜST uca veriyor). Uçaklardaki kod hâlâ eski hâlde: **dağıtmadan
  uçulursa pilot sağa çevirir, sürü SOLA döner** ve hiçbir yerde hata
  görünmez.
  *Yapılacak:* `swarm_state_machine` dağıt (tek paket yeter) ·
  `/ws/suru_dugumleri`'ne **`gorevfsm`** ekle (üçüne) ·
  `MOD_SWC_DEBOUNCE_MS=1300` env'e geçsin · `RPI_ESITLEME.md` §3'e yaz.
  Aynı dağıtımda madde 24·25·26·27·28 + B19 de gider.

- `[x]` ✅ **PERVANELİ UÇUŞ — kalk · asılı dur · in. (31 Ağu 15:52)**
  Üç uçak birlikte kalktı (0,24 sn), 5 m'de 20 sn asılı durdu, birlikte
  indi (0,14 sn). En dar ayrım 6,70 m sabit; roll/pitch tepe 3,3°/5,3°;
  mod kavgası sıfır; dikey komut +0,00. Ayrıntı `GUNLUK.md` 16:24 kaydı.

- `[x]` ✅ **DAĞITIM YAPILDI (1 Eylül).** B6 + madde 29 + morf hızı +
  kaçınma dikey beklemesi + deadman düzeltmesi + manevra datumu. md5 üç
  uçakta da depoyla aynı, parametreler `ros2 param get` ile doğrulandı.
  Eski madde:
- `[ ]` ~~🔴 DAĞITIM — B6 + MADDE 29 + yeni env~~
  31 Ağustos gecesi yazıldı, yerelde 350+270 test geçti, uçaklar **kapalı**
  olduğu için dağıtılamadı (`drone_bul.sh --durum` → "hiçbir drone
  bulunamadı"). *Yapılacak:* `swarm_state_machine` **ve** `swarm_control`
  (ikisi de değişti, tek paket yetmez) → `ucus_ayarlari.py --kabuk >
  ucus_ayarlari.env` üç Pi'ye → `docker restart` → doğrula:
  `ros2 param get /mode_manager_node default_spacing_m` (**7.0**) ·
  `... max_accel_mps2` (**1.3**) · `... kalkis_irtifa_m` (**5.0**).
  ⚠️ Aralık **7 mi 9 mu — KARAR-14 açık.** Formasyon geçişli uçuşta YKİ'de
  "Aralık (m)" kutusuna **9** yazmak yeterli, dağıtım değişmiyor.

- `[ ]` 🔴 **KUMANDADAN FORMASYON GEÇİŞİ — bir sonraki uçuş.**
  Sıra: kalk (VrB KAPALI, formasyon yok) → 5 m'de asılı dur → **VrB aç**
  (SwC'nin gösterdiği formasyon oluşsun) → SwC ile bir geçiş → **VrB kapat**
  (uçaklar olduğu yerde donsun) → in.
  Ön koşullar:
  · `MOD_ARALIK=9.0` dağıtılmış olmalı (üstteki madde)
  · 🔴 **Uçakları hedef formasyonun ŞEKLİNDE diz** — ölçüldü: rastgele
    dizilimde ilk morf 4,83 m'ye kadar yaklaşıyor (pay 0,83 m), formasyon
    şeklinde dizilirse darboğaz okbaşı→V morfuna kayıyor ve 9 m'de
    **6,36 m** (pay 2,36 m) oluyor. Aralık büyütmek ilk morfu DÜZELTMEZ.
  · Kuru test **yeni bayrakla**: `--senaryo formasyon_gecis --aralik 9
    --kuru --harita` — bayrak 31 Ağu'da eklendi çünkü senaryolar
    `MOD_ARALIK`'ı kullanmıyordu, yani doğrulanan geometri uçulanla
    aynı DEĞİLDİ.
  · Harita gözle doğrulanmalı (formasyon kutusu ~18 × 18 m + kaçış zarfı)

- `[ ]` 🟡 **ylp02 diski %88 (3,6 GB).** Rosbag ~190 MB/saat yazıyor.
  Finalden önce eski kayıtlar temizlenmeli; uzun görev kaydı dolduruyor.

- `[~]` 🟡 **ylp00 — mavros SEGFAULT.** 31 Ağu 21:12'de bir kez görüldü;
  sonraki üç restart'ta TEKRARLAMADI. İzlemede kalsın.
  Eski madde:
- `[ ]` ~~🔴 **ylp00 — mavros SEGFAULT.**~~ 31 Ağu 21:12 yeniden başlatmasından
  sonra `[ros2run]: Segmentation fault`; yığın 11 yerine 2 düğümle kaldı.
  px4_bridge mavros'suz iş göremez. **Dağıtımdan önce bakılmalı** —
  tekrarlanıyor mu, yoksa o açılışa özgü müydü?

- `[ ]` 🔴 **HOME kayması — RTL'e güvenilmez.** 26 Ağustos gece testinde RTL
  üç uçağı kalkış yerine değil **aynı yanlış civara** indirdi (~9 m KD,
  birbirine 1-2 m). PX4 home kayıtları = iniş noktaları → RTL doğru uçtu,
  **home'lar yanlıştı.**
  *Yapılacak:* o uçuşun rosbag'inden `/drone_N/mavros/home_position/home`
  zaman serisi + statustext "home" mesajları → home NE ZAMAN, HANGİ konumla
  set edilmiş? Şüpheliler: ARM anında EKF/origin oturmamış konum · önceki
  uçuştan kalma home · `set_gp_origin` etkileşimi.
  *Bu kapanana kadar:* **RTL'li uçuş YOK.** İniş `land` + göz önü alanla.

- `[ ]` 🔴 **MAVROS GCS denetimi yalnız açılışa bakıyor.** Taşkın sonradan da
  başlıyor: 27 Ağustos'ta üç uçak da açılışta TEMİZ raporlanmışken
  ylp00 1,2 M hata/131 MB · ylp01 4,5 M/467 MB · ylp02 5,0 M/522 MB, bayrak
  üçünde de YOK.
  *Yapılacak:* denetimi `yelpence-izle`'ye taşı (zaten 10 sn'de bir koşuyor).
  ⚠️ Otomatik onarım **yalnız yerde + disarm** iken; havada mavros'u yeniden
  başlatmak px4_bridge'i keser — havada SADECE uyarı.
  *Yan zarar:* `mavros.log`'un başı siliniyor, teşhis kaynağı yok oluyor.

- `[~]` 🔴 **ylp02 PX4 güç soketi — kabul testi.** Operatör 28 Ağustos akşamı
  "halledildi" dedi, test kayda geçmedi. **Uçuş sabahı: kabloyu bilerek 3 kez
  oynat, üçünde de reboot GELMEMELİ.** Kabul ölçütü bant DEĞİL, lehim ya da
  kilitli konnektör.

---

## 🟠 P1 — GÖREV 2 · **ayrıntılı liste `docs/gorev2.md` §4'te**

> Bu blok 30 Ağustos'ta **`docs/gorev2.md`'ye devredildi** — orada 29 maddelik,
> aşamalara bölünmüş, kapılı liste var. Burada yalnız **özet ve sıradaki iş**.

**✅ AŞAMA A BİTTİ (30 Ağustos, madde 1-10 + B17).** Kod tarafı tamam:
V formasyonu kumandadan seçilebiliyor · kalkış kapısı (uçak artık origin'e
gidemez) · `rc_ibus_kopru` (ikinci RC alıcısı) · `--senaryo manevra` ·
YKİ joystick zinciri silindi · heading artık hesaplanıyor. **293 birim testi.**
⚠️ Düğüm katmanı yalnız **sözdizimi** doğrulandı — gerçek doğrulama G0'da.

- `[x]` ✅ **AŞAMA B — donanım BİTTİ (30 Ağu).** i-BUS 130 Hz / 0 hata ·
  işaret yönleri ölçüldü (**pitch + yaw TERSTİ, düzeltildi**) · kod
  `193c224` üç uçağa dağıtıldı · **üç konteyner yeniden oluşturuldu**
  (A19 kapandı, ylp00'a `/dev/ttyAMA2`).
- `[~]` 🔴 ~~**AŞAMA B — donanım (SIRADAKİ İŞ).**~~ `gorev2.md` §4 madde 11-15:
  ① 🔴 **i-BUS gerilim ölçümü** — Pi 5 GPIO **5 V toleranslı DEĞİL**,
  multimetresiz bağlanmaz ② kumanda #2: bind + **10 kanal modu** +
  **failsafe SwA=KİLİTLİ** ③ kablolama + `SURU_RC_PORT`
  ④ **konteyner recreate ×3** (`--device` + A19 + A12 + korupt log, tek işlem)
  ⑤ dağıtım — ⚠️ `swarm_core` ve `swarm_state_machine` ikisi de değişti,
  `--paket` ile tek paket **yetmez**.
- `[x]` ✅ **AŞAMA C — G0'ın yerde yapılabilen kısmı BİTTİ.** 16 (RC + kill
  izolasyonu) · 17 (işaretler — **pitch ve yaw TERSTİ**, düzeltildi) ·
  18 (kalkış kapısı) · 22 (deadman) · 23 (mesh). Kalan 19-21 **uçuş ister.**
- `[x]` ✅ **AŞAMA D — KOD TARAFI BİTTİ (31 Ağustos).** `gorev2.md` §4 madde
  24-30 + B19. **Hiçbiri uçakta doğrulanmadı** — dağıtım yukarıdaki P0.
  ✅ **Madde 29'un taşıma yolu ÇÖZÜLDÜ:** ne betik ne SSH — değerler
  **BAŞLAT paketinin içinde** mesh'ten gidiyor, paket hâlâ 16 bayt
  (`gorev2.md` §5, seçenek (c)). YKİ'de iki kutu; boş bırakmak geçerli.
  Aşağıdaki eski liste tarihçe:
  ① 🔧 **G1** LANDING gerçekten indirsin — **kod yazıldı, uçakta
  DOĞRULANMADI.** (Teşhis düzeltildi: olayın *tüketicisi vardı*, ama
  `agent_transitions` `pending_state=LANDING`'i **yalnız 3 durumdan** kabul
  ediyor ve uçaklar ARMED'daydı → istek tek tick yaşayıp kayboluyordu.
  Artık `land` **doğrudan `px4_bridge`'e, 1 Hz tekrarlı**.)
  ② 🔴 **B2** kumandadan kalkış AÇIKÇA (30 Ağu olayının kökü)
  ⚠️ **önce ARM yetkisi kararı** — `gorev2.md` §3'te iki seçenek + öneri
  ③ 🟠 SwC debounce (önce ÖLÇ) ④ 🟠 ADIM 6 `mission_fsm`
  ⑤ 🟠 YKİ Görev 2 BAŞLAT butonu ⑥ ✅ YKİ aralık alanı (+ irtifa) — bitti
  ⑦ 🟠 alıcı failsafe kaydı SwA=1000
- `[x]` ✅ **B19 — `COMPLETED` çıkışı YAZILDI (31 Ağu).** COMPLETED→IDLE:
  SwD iniş konumundan çıkmış **ve** hepsi disarm. Dönüşte uçuş defteri
  sıfırlanıyor (`kalkis_tamam` mandalı dâhil). Uçakta doğrulanmadı.
- `[ ]` 🟠 **AŞAMA E — uçuşlar** (31-33): A (çizgi, pitch/roll) → B (manevra)
  → C (asimetri + kumandadan kalkış/iniş). G0 19-21 Uçuş A'da ölçülür.
  🔴 **`mod` açıkken kill pilotları başında olmalı.**
- `[ ]` 🟡 **`_on_control_out` hız limiti** — ölçüldü: UART'a yazdığımızın
  **%75'i** ESP'de atılıyor. ~8 satır. **Operatör kararı: G0 madde 23
  ölçümünden SONRA** (`gorev2.md` §5).
- `[ ]` 🟡 **ACİL İNİŞ butonu Görev 2'de hâlâ gizli** — gizlenme sebebi
  joystick paneliydi, panel silindi, **sebep kalktı**. Gösterilsin mi:
  operatör kararı.
- `[ ]` 🟡 **`--durum` gibi başka eskimiş liste var mı?** 30 Ağustos'ta
  `drone_bul.sh --durum`'un bayrak listesinde `gozlem`/`yer_testi`/`origin`
  eksikti (kırmızı çizgi olmalarına rağmen). Benzeri aranmadı.

---

## 🟠 P1 — GÖREV 1 (görev zinciri hiç koşmadı)

**Şartname dağıtık algoritma dayatıyor ve hakem YKİ bağlantısını kesecek.**
Bugünkü komut yolu (YKİ → mesh → goto) finali GEÇEMEZ. Bu blok o yüzden var.

- `[ ]` 🟠 **ADIM 5 — görü zinciri sahaya.** `camera_driver` + `vision_node`
  ylp02'de koşuyor ama sürü zincirine bağlı değil.
  *En küçük test, uçuş gerekmez:* iki uçak yerde, mesh açık, QR'ı ylp02'ye
  göster → ylp00 mesh'ten `QRMissionData` alsın.
- `[ ]` 🟠 **Takım slot numarasını öğren** (şartname/düzenleyici) ve
  `vision_params.yaml`'a `team_slot` yaz. **Tek satır ama bilinmeden QR
  görevleri filtrelenemez.**
- `[ ]` 🟠 **ADIM 6 — `mission_fsm`.** QR görev sırası. Görev 2 de buna bağlı.
  ↳ Açılınca **KARAR-12** sırası gelir: `mission_active` YKİ'ye lider kalp
  atışıyla (mesh'e **0 bayt** — bayt zaten uçuyor, hep `0` yazıyor).
  Bugün YKİ'de **beş kapı** kalıcı `false`; en görünürü **ACİL İNİŞ butonu
  hiç aktifleşmiyor**, en önemlisi görev sırasında tekil komutların
  kilitlenmemesi (şartname: müdahale görevi BAŞARISIZ sayar). ~23 satır.
- `[ ]` 🟠 **ADIM 7 — `mission1_dynamic_swarm`.** YKİ'nin yerini alan
  orkestratör; **dağıtıklık şartının karşılığı bu.**
  ⚠️ Yerde test edilemez: `decide()` ancak `SYNCHRONIZED_TAKEOFF` → tüm
  ajanlar `IN_SWARM` olduktan sonra komut üretiyor. **En az 2 uçak + UÇUŞ.**
- `[ ]` 🟠 **ADIM 9 — `maneuver_executor`.** QR görevlerinden biri açıkça
  pitch/roll manevrası.
- `[ ]` 🟠 **ADIM 10 — `precision_landing`.** Renkli bölgeye hassas iniş;
  toleransın dışı = 0 puan. `ZoneMap` gerekli (ADIM 5'e bağlı).
  🔴 En riskli adım — yere temas ediyor, kademeli git (önce 3 m).
- `[ ]` 🟠 **ADIM 11 — `task_reallocator`.** Sürüden birey ayrılma/katılma.
  `min_active_for_formation:=2`, üç uçak ister.

### Kamera / QR — Görev 1'in fiziksel kısıtı

- `[ ]` 🟠 **P1.27 — Flex servis kıvrımı denemesi (GÜNDÜZ uçuşu).**
  Operatör hipotezi: flex uçuşta sallanıp **yalıtımı köprülüyor**, gövde
  titreşimi yumuşak göbeği atlayıp kabloyla kameraya giriyor.
  *Yapılacak:* kameraya yakın bol servis kıvrımı, iki yakada ayrı
  sabitleme, aradaki kıvrım serbest. **Bantla gövdeye yapıştırma** — kabloyu
  tekrar sert köprüye çevirir.
  *Ölçüt:* `deploy/rpi/teshis/jole_olc.py` — 28 Ağustos seviyesi **1,04 px**,
  motorsuz taban **0,73 px**, hedef **≤ 0,8**.
  🔴 **Kayıt GÜNDÜZ olmalı** — karanlıkta metrik geçersiz (`KAMERA.md` §12.3).

- `[x]` ✅ ~~`kamera_yayin.py` `dagit.sh`'e eklenmeli~~ → **KAPANDI (1 Eylül).**
  Dağıtıma girdi; ylp02'deki bayat kopya `~/kamera_yayin.py.bayat_28agu`
  adına alındı.

- `[ ]` ⚪ **Kamera servisi açılışta başlamıyor — BİLİNÇLİ, acele yok.**
  Otomatik başlatmak cazip ama riskli: 4K'da `rpicam-vid` ~1,4 çekirdek
  yiyor (1 Eylül: yük 5,08, `mavros` %52-55'te yarışıyor). Açılışta kalkması
  uçuş düğümlerini sıkıştırır. Yapılacaksa **düşük kiple ve kapalı
  varsayılanla** yapılmalı, karar operatörün.

- `[ ]` 🟠 **P1.22 — Yalıtımı derinleştir. QR tavanını açacak TEK eksen bu.**
  🔒 QR büyütülemez (1,5 m, 74 modül — yarışma sabitliyor), çözünürlük de
  tükendi (4K en yükseği). Teorik tavan 34 m, **gerçek tavan 11 m** ve
  aradaki farkın tamamı titreşim.
  *Denenecek:* daha yumuşak/ağır göbek, jel ped, kademeli yalıtım,
  **pervane balansı**. *Ölçüt:* 11-15 m'de okuma sıfırdan farklı olmalı —
  o bantta QR'ın %67-78'i zaten BULUNUYOR, yalnız veri okunamıyor.
- `[ ]` 🟠 **P1.26 — Görev planı 6-9 m kısıtına uymalı.** QR bandı tercih
  değil **kısıt**: altında kadraj taşıyor, üstünde titreşim kesiyor. Şu anki
  `ucus_ayarlari` irtifaları bu bandı gözetmiyor.
- `[ ]` 🟠 **P1.23 — Renk eşiklerini yeni renk dengesinde kalibre et.**
  Mevcut eşikler **magenta tondayken** ölçülmüştü; beyaz dengesi sabit
  kazanca alındı. *Ölçüt:* kırmızı ve mavi daire, 5-15 m, sahte pozitif yok.
- `[ ]` 🟡 **P1.25 — Renk hedefini kadraja alan bir uçuş.** Son dört uçuşta
  yalnız QR üzerinde uçuldu; rengin irtifa eğrisi **yok**.

---

## 🟠 P1 — altyapı (uçuşları engellemiyor ama biriktikçe pahalı)

- `[ ]` 🟠 **29 Ağustos değişikliklerini dağıt.** `baslat.sh` iki kez değişti:
  ① `basit_kacinma` + `fusion` blokları kalktı ② **`--yalniz <düğüm>`** eklendi.
  ⚠️ **DÜZELTME (30 Ağu):** "ikisi de görülmeli" YANLIŞTI — `baslat.sh`'te
  bunlar **birbirini dışlayan dallar**. Formasyon sürerken yalnız
  `TEK-URETICI (ADIM 3)` basılır; kaçınma yine koşar (düğüm listesinde
  `collision_avoidance` görünür). 30 Ağustos dağıtımında üçünde de böyle.
  *Sonra bir kez sahada doğrula:* `docker exec -d drone1 bash /ws/baslat.sh --yalniz ca`
  → `ca.log`'da düğüm yeniden kalkmalı, `mavros`/`px4_bridge` **kesintisiz**
  kalmalı (`ros2 node list` sayısı düşmemeli). Masada konteynerde doğrulandı,
  **gerçek uçakta koşmadı.**
- `[ ]` 🟡 `drone_bul.sh --durum`'un yeni iki satırı (md5 senkronu, düğüm
  sayısı) canlı uçakta hiç koşmadı — ilk fırsatta bak.
- `[x]` ✅ **Konteyner recreate ×3 — YAPILDI 30 Ağustos 13:30.**
  A19 üçünde de kapandı, A12 zaten ✅'ti (belge yanlıştı), ylp00'a
  `--device /dev/ttyAMA2` eklendi. Eski madde:
  `docker rm -f <kon>` + `~/yelpence_ws/run_drone.sh`. Kapattıkları:
  **A19** `-e ROS_LOCALHOST_ONLY=1` (üçünde de ❌; olmadan `docker exec ros2`
  düğümleri **sessizce göremiyor**, `TUZAKLAR` §1.25) · **A12** docker log
  döndürme (ylp02'de ❌) · drone1'in korupt json logu.
  ⚠️ Öncesinde `docker inspect` ile mevcut ayarları not al.
- `[ ]` 🟠 **Algı imajını eşitle** — `./deploy/yki/imaj_esitle.sh ylp00` ve
  `ylp01`. KARAR-09 (B); şu an opencv/zxing yalnız ylp02'de.
- `[ ]` 🟠 **Körlükte davranış kararı — finale kadar verilmeli.**
  `korluk_tut_s = 0` (kapalı): uçak körken durmuyor, haber veriyor. Otonom
  finalde operatör müdahalesi olmayacak. Mekanizma yazılı ve testli, **tek
  parametre** — açılsın mı, operatör kararı.

---

## 🟡 P2

- `[ ]` 🟡 `collision_avoidance_node` birim testlerinin 10'u düşüyor
  (`_korluk_muaf_bildirildi` test kurgusunda yok). Kod sahada çalışıyor,
  testler kodun gerisinde kalmış. 29 Ağustos'ta görüldü.
- `[ ]` 🟡 **ylp02 geçiş sonrası dönüş tutukluğu:** 26 Ağustos'ta 6,4 m'de
  bekledi (körlük yok). Aynı bag + `ca.log`'dan sebep çıkarılacak.
- `[ ]` 🟡 **OFFBOARD'da RC'siz uçuş:** kumandalar kapalıyken RC-loss
  failsafe'in tetiklenmemesi bilinçli mi (`COM_RCL_EXCEPT`)? Ölç, karara
  bağla, yaz.
- `[ ]` 🟡 **Hareket modunda centroid sürüklenmesi** (KARAR-11 açık ucu):
  her uçağın mode_manager'ı centroid'i KENDİ tik'inde entegre ediyor —
  uçaklar arası yavaş sürüklenme olasılığı G0/uçuşta ölçülecek.
- `[ ]` 🟡 **`path_planner`'da yavaşlama rampası yok** — ivmelenme var,
  yavaşlama yok; bacak sonunda aşım.
- `[ ]` 🟡 **Pil sentinel'i:** `px4_bridge` bilinmeyen pili **12,6 V / %100**
  sahtesiyle yayınlıyor. YKİ'de pil görürsen inanma. Sahteyi kaldır,
  "bilinmiyor" olarak aksın.
- `[ ]` 🟡 **TUZAKLAR'a yaz:** ros2 `-p x:=90` tam sayıyı INTEGER yapar,
  double declare edilmiş düğümü **açılışta öldürür**. İki kez yaşandı.
- `[ ]` 🟡 **MAVROS taşkınının kök nedeni** (`mavconn/udp.cpp:325`, yayın
  soketinde ENETUNREACH). Kendini onarıyor, acil değil — ama tek oturumda
  876 MB yiyen şeyin sebebi bilinmiyor.
- `[ ]` 🟡 28 Ağustos formasyon uçuşunun kaydı: slot oturma hataları + faz
  geçiş temizliği (mcap → metrik; kayıtlar dizüstünde).

---

## ⚪ P3

- `[ ]` ⚪ `mission1` sahaya alınınca **sekans aparatını sil** (KARAR-10 §5).
- `[ ]` ⚪ PIL'i ylp00 ve ylp01'e de kur (şu an yalnız ylp02'de).
- `[ ]` ⚪ `EVENT_PX4_REBOOT` (kod 69) yazılmadı — taşıma yolu hazır.
- `[ ]` ⚪ Belge sadeleştirmesinin 2. adımı: `TUZAKLAR` · `PLAN` · `CLAUDE.md`.
