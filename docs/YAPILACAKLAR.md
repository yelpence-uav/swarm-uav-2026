# YAPILACAKLAR

**Son güncelleme:** 30 Ağustos 2026, 15:45 — madde 24 kodu yazıldı (uçakta doğrulanmadı); G1 teşhisi düzeltildi, **B19** eklendi; `gorev2.md` devir teslim için sadeleştirildi.

> **Finale 8 gün.** Bu liste artık "her fikir" değil, **bu 8 günde
> yapılacak iş.** Bir madde buraya giriyorsa birinin onu yapması planlanıyor
> demektir. 135 maddelik eski liste 29 Ağustos'ta kesildi — tamamı git'te:
> `git show 783afab:docs/YAPILACAKLAR.md`

**Önem:** 🔴P0 uçuş engeli · 🟠P1 finalde puan kaybı · 🟡P2 önemli · ⚪P3 ileride

---

## 🔴 P0 — bunlar kapanmadan ilgili uçuş yapılmaz

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
- `[ ]` 🔴 **AŞAMA D — TASARIM GEREĞİ (SIRADAKİ İŞ).** `gorev2.md` §4 madde
  24-30. **İptal yolu olmadan `mod` ile test yapılmaz:**
  ① 🔧 **G1** LANDING gerçekten indirsin — **kod yazıldı, uçakta
  DOĞRULANMADI.** (Teşhis düzeltildi: olayın *tüketicisi vardı*, ama
  `agent_transitions` `pending_state=LANDING`'i **yalnız 3 durumdan** kabul
  ediyor ve uçaklar ARMED'daydı → istek tek tick yaşayıp kayboluyordu.
  Artık `land` **doğrudan `px4_bridge`'e, 1 Hz tekrarlı**.)
  ② 🔴 **B2** kumandadan kalkış AÇIKÇA (30 Ağu olayının kökü)
  ⚠️ **önce ARM yetkisi kararı** — `gorev2.md` §3'te iki seçenek + öneri
  ③ 🟠 SwC debounce (önce ÖLÇ) ④ 🟠 ADIM 6 `mission_fsm`
  ⑤ 🟠 YKİ Görev 2 BAŞLAT butonu ⑥ 🟡 YKİ aralık alanı
  ⑦ 🟠 alıcı failsafe kaydı SwA=1000
- `[ ]` 🔴 **B19 — `COMPLETED` terminal, çıkışı yok.** İniş bitince
  `mode_manager` orada kalıyor; **ikinci kalkış konteyner restart istiyor** ve
  görev başına **3 hakkımız var**. ~6 satır (COMPLETED→IDLE: hepsi disarm **ve**
  iniş mandalı düşmüş). Karar verilmedi. `gorev2.md` §5.
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
