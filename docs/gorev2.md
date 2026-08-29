# GÖREV 2 — Yarı Otonom Sürü Kontrolü

**Son güncelleme:** 30 Ağustos 2026, 01:47 — B15/B16 eklendi (kalkış kapısı + `fsm` bağımlılığı); §4 sıralı iş listesine çevrildi

Şartname **§5.2** · **100 puan** · görev başına **3 hak**, en yüksek puan sayılır.

> Görev 2'nin tek toplanma noktası: ne isteniyor, ne karar verildi, ne eksik,
> sırayla ne yapılacak. Genel plan `PLAN.md`, iş listesi `YAPILACAKLAR.md`.
> Önceki karar: `KARARLAR.md` **KARAR-11** (manevra modu, dört boşluk kapatıldı,
> 28 Ağustos). Bu belge onun **devamı** — KARAR-11'in cevapsız üç sorusu
> 30 Ağustos'ta cevaplandı, aşağıda §2'de.

---

## 1. Şartname ne istiyor

| # | Şart (§5.2.2) | Karşılığı |
|---|---|---|
| G1 | Önce **tam otonom** formasyon kur + stabilize ol, **sonra** kumanda devralır | `mode_manager` TAKEOFF→READY |
| G2 | **Tek** kumanda tüm sürüyü sürer, hepsi **senkronize** tepki verir | `joystick_interpreter` → mesh → 3× `mode_manager` |
| G3 | **Hareket Modu:** pitch=ileri/geri · roll=sağ/sol · yaw=merkez sabit formasyon rotasyonu **+ her İHA kendi heading'ini ayarlar** · throttle=toplu irtifa | `movement_mode` + `formation_node` |
| G4 | **Manevra Modu:** merkez **SABİT** · pitch/roll = formasyon **düzlemi** eğimi · yaw = merkez etrafında dönüş + heading · throttle = toplu irtifa | `maneuver_mode` + `apply_tilt` |
| G5 | **Formasyon değişimi kumandadan** — örnek direktiflerde **çizgi, ok başı ve V** üçü de geçiyor | SwC → `FORMATION_*` |
| G6 | **Kalkış ve iniş kumandadan**, sürü halinde, belirlenen irtifaya (örn. 15 m) | SwD → `TriggerMission` / mod FSM |
| G7 | Başlangıç konumuna dönüş + toplu iniş + disarm | **pilot uçurur, kod işi değil** |
| G8 | En az 3 İHA | ✅ üçü de uçuyor |
| G9 | Görev başladıktan sonra YKİ'den **her türlü müdahale = görev BAŞARISIZ** | ⚠️ bkz. B9 |

**"Eğim" uçağın gövdesini yatırmak DEĞİL** — slot irtifa modülasyonudur (Şekil 4).
Görev 1'in QR-tetikli pitch/roll manevrası aynı hareket ama otonom; karıştırılmayacak.

### 🔴 İki kumanda zorunlu — şartnamenin kendi cümlesi

> *"Her bir İHA için, sürüyü yarı otonom olarak yöneten kumanda **dışında**,
> acil durumlarda kill switch işlemini gerçekleştirebilecek **ayrı bir kumanda**
> ve bu kumandayı kullanacak **yetkili bir pilot** bulunması zorunludur."*

Yani ylp00'da **iki alıcı olmak zorunda.** İkinci alıcı kararı tercih değil, şart.

### Ceza tablosu (Kriter 5)

| Durum | Puan |
|---|---|
| Çarpışma | **−20 × N** (N = İHA sayısı) |
| Kalkışta hata | −5 |
| Görev sırasında düşme | −5 |
| **Osilasyon gözlemlenmesi** | **−10** |

Osilasyon cezası B6'yı (ivme rampası) doğrudan puan meselesi yapıyor.

---

## 2. ALINAN KARARLAR — 30 Ağustos 2026, operatör

| # | Karar | Gerekçe |
|---|-------|---------|
| **G2-K1** | **Pilot/sürücü uçağı: ylp00** | KARAR-11 önerisiydi; ikinci alıcı buraya takılıyor. ⚠️ ylp00 kaçınmada **ÇAPA** (rütbe 0, dikeyde kaçmaz) ve pilot uçağı düşerse sürü komut kaynağını kaybeder — bilerek kabul edildi |
| **G2-K2** | **İkinci FS-iA6B, i-BUS Servo çıkışından Pi'ye** | i-BUS standart UART (115200 8N1, ters değil). PPM/GPIO **elendi**: zamanlama Linux'a kalıyordu ve **checksum yok**. i-BUS'ta `0xFFFF − ilk 30 baytın toplamı` var → bozuk çerçeve **atılabilir**. 14 yuva (i6X 10 gönderir), PPM'de 8 ile tam sınırdaydık |
| **G2-K3** | **Ayrı kumanda + ayrı pilot** (sürü ≠ kill switch) | Şartname §5.2 zorunlu kılıyor. ylp00: 2 kumanda + 2 pilot. ylp01/ylp02: 1'er kill kumandası. Tek kumandayı iki alıcıya bind etmek donanımsal mümkün ama **teknik kontrolde takılır** |
| **G2-K4** | **Test genlikleri: eğim ±10°, yaw ~45° / 12,5°/s** | Tavanlar `ucus_ayarlari` MOD_*'ta eğim 15°, yaw 25°/s. Test bunun altında (çubuk %66 eğim, %50 yaw) — ilk uçuşta muhafazakâr |
| **G2-K5** | **İniş: slot üstüne `land`, EVE fazı YOK** | 🔴 Uçaklar **kalktıkları yere İNMEZ.** `CLAUDE.md` §9 gereği her slotun muhtemel iniş noktası haritada ayrı ayrı doğrulanacak |
| **G2-K6** | **HOLD'dan otomatik iniş KALDIRILIYOR** — sürü HOLD'da kalır | `mode_transitions.py:125` bugün 5 sn komutsuzlukta LANDING'e geçiyor. 5 saniyelik bir **mesh sarsıntısı görev ortasında iniş yaptırırdı.** İniş kararı pilota/hakeme ait |

### 🔴 G2-K6'nın kabul edilen bedeli

Otomatik iniş kalkınca **kumanda kaybında sürü süresiz asılı kalır.**
Kaçınma çalışmaya devam eder, ama **pil izleme üç yerde de KAPALI**
(`BAT1_SOURCE` disabled · `BATARYA_KRITIK_V=0.0` · YKİ'de `PIL_GOSTER=false`)
— yani yazılım tarafında hiçbir otomatik koruma yok.
**Süreyi pilotlar tutar; çıkış yolu kill-switch pilotlarıdır.** Bilerek böyle.

### Sürü alıcısının failsafe'i — deadman'i bu taşıyacak

`RPI_ESITLEME.md` §5'te ölçüldü: **kumanda kapanınca FS-iA6B susmuyor**,
failsafe çerçevesi basmaya devam ediyor. Yani *"veri geliyor mu"* bakmak
deadman için **yetmez**.

Kill-switch alıcısında bu, CH3 üst-uç yöntemiyle çözülmüştü. Sürü alıcısında
daha temiz yol var: **alıcının failsafe'i SwA (emniyet) kanalı KİLİTLİ konuma
gidecek şekilde kaydedilir.**

```
suru kumandasi kapandi -> SwA failsafe = KILITLI -> deadman duser
                       -> mode_manager HOLD     -> suru havada asili bekler
```

Eşik oyunu yok, ek kanal harcanmıyor, mekanizma alıcının kendi özelliği.

### 🔴 Bağlamadan ÖNCE ölçülecek: gerilim seviyesi

FS-iA6B 5 V ile besleniyor. i-BUS çıkışı yaygın olarak 3,3 V bildiriliyor
**ama garanti değil** ve **Pi 5 GPIO'su 5 V toleranslı DEĞİL**.

*Yapılacak:* alıcıyı besle, i-BUS Servo ucunu **multimetreyle ölç.**
3,3 V ise doğrudan; 5 V ise seviye çevirici / dirençli bölücü.
USB-TTL kullanılıyorsa adaptörün 3,3 V–5 V jumper'ı da doğru konumda olmalı.
**Ölçmeden bağlanmaz.**

### Port: env'e bağlı, iki bağlantı da kod değişmeden çalışır

`SURU_RC_PORT` değişkeni — kritik yolu tıkamasın diye seçim ertelenebilir.

| Yol | Artı | Eksi |
|---|---|---|
| **USB-TTL → `/dev/ttyUSB0`** *(öneri)* | reboot yok, `config.txt`'ye dokunmaz, sıcak takılır | numara her takışta değişir → **`by-id` yolu şart** (`cihazlar.md` kuralı) |
| Pi UART → `/dev/ttyAMAn` | ad sabit, `ttyAMA0`/`ttyAMA4` deseniyle tutarlı | `config.txt` + **reboot** + GPIO pin çakışma kontrolü |

---

## 3. Boşluklar — 16 madde, hepsi kodda doğrulandı

Kod `f6f8498`'de (28 Ağu) hazır sayılıyor ama **hiç koşmadı** ve uçaklara
**dağıtılmadı.**

### 🔴 P0 — bunlar olmadan görev hiç çalışmaz

**B1 · İkinci alıcı sisteme GİREMİYOR (mimari).**
`joystick_interpreter` RC'yi yalnız Pixhawk üzerinden okuyor
(`joystick_interpreter_node.py:168` `manual_control`, `:182` `rc/in`;
`baslat.sh:1395-1396` bunları `/drone_1/mavros/*`'a remap ediyor).
Ama ylp00'ın Pixhawk RC girişi **kill-switch pilotuna ait ve dolu**:
`RC_MAP_FAILSAFE=3` · `RC_FAILS_THR=2050` · CH3 failsafe 2100 · **CH5 = kill** ·
CH8 = arm (`RPI_ESITLEME.md` §5, 19 Ağu havada doğrulandı). **PX4'te tek RC girişi vardır.**

> 🔴 **Kanal çakışması — ihmal edilirse TERS çalışır.** Sürü zinciri CH5'i
> *emniyet (SwA)*, CH8'i *kalkış/iniş (SwD)* sanıyor. Kill pilotunun alıcısına
> bağlı kalırsa **kill switch'i kaldırmak sürü komutlarını AÇAR** ve
> **arm switch'i kalkış/iniş tetikler.**

*Çözüm:*
```
FS-iA6B #2 --i-BUS Servo (115200 8N1, 32 bayt / ~7,7 ms)--> ylp00 Pi
  -> YENI dugum: rc_ibus_kopru  (~120 satir, swarm_control)
  -> /drone_1/rc/suru  (mavros_msgs/RCIn)
  -> joystick_interpreter  (-r /mavros/rc/in:=/drone_1/rc/suru)
```
`_on_mavros_rc_in` zaten 1000-2000 PWM bekliyor → **o düğümde tek satır değişmez.**
Seri + çerçeve + checksum deseni `esp32_bridge`'de zaten var, oradan kopyalanır.

🔴 **`manual_control` remap'i de ölü konuya çevrilmeli.** Bırakılırsa PX4 kill
pilotunun çubuklarından `MANUAL_CONTROL` üretir ve **o da sürüyü sürer**
(B11 ile birlikte ters işaretli olarak).

⚠️ Konteyner `--device` gerekiyor → **recreate şart.** `YAPILACAKLAR`'daki
*"Konteyner recreate ×3"* maddesiyle **tek işlem**: A19 (`ROS_LOCALHOST_ONLY`),
A12 (log döndürme), drone1 korupt json logu ve bu, birlikte kapanır.

⚠️ FS-i6X varsayılanı 6 kanal; 8 kanal için kumandada **10-kanal modu açılmalı.**

**B2 · Kumandadan kalkış çalışmıyor (G6 ihlali).**
`kalkis_olayla=false` (`baslat.sh:802`). `mode_manager` TAKEOFF'a girince yalnız
`EVENT_MISSION_STARTED` basıyor; `agent_fsm_node.py:351` bunu **yalnız ARM'a**
çeviriyor, kalkış komutu üretmiyor. Ayrıca `mode_manager`'da **kalkış irtifası
parametresi hiç yok** — şartname "belirlenen irtifaya (örn. 15 m)" diyor.

**B3 · `mode_manager` FSM sahada READY'ye ULAŞAMAZ.**
KARAR-11 #6 olarak biliniyordu; **`test_hazir_atla` kodda hâlâ YOK**
(repo genelinde sıfır eşleşme). `mode_transitions._from_idle` → `mission_state==8`
istiyor (`mission_fsm` **kapalı**); `_from_takeoff` → `all_agents_in_swarm()`
istiyor (ajanlar ARMED'da kalıyor).

**B4 · V formasyonu kumandadan SEÇİLEMİYOR (G5 ihlali).**
`joystick_interpreter_node.py:260-261` — SwC **orta konum → `FORMATION_UNKNOWN (0)`**,
`FORMATION_V (2)` değil. Üstelik `esp32_bridge` formasyon=0 gelen değişiklik
bayrağını **bilerek düşürüyor**. Şartnamenin örnek direktifi birebir:
*"V formasyonuna geç"*. `_on_joy` yorumu *"Hiçbiri = Ortada (V)"* diyor —
**yorum ile kod çelişiyor** ve hangisinin doğru olduğu hiç ölçülmemiş.

**B5 · MOVEMENT'ta `/swarm/public/formation/target`'ta İKİ ÜRETİCİ.**
`CLAUDE.md` §4'ün yasakladığı desenin yenisi:
```
her ucak : kendi mode_manager -> internal/formation/target
                              -> ic_dis_kopru (:108) -> kendi public/   [1]
AYRICA   : LIDERIN mode_manager -> esp32_bridge (:2537 lider kapili)
                              -> mesh TIP_FORMASYON -> digerlerinin public/  [2]
```
`formation_node.py:331` hakemlik yapmıyor — **son gelen kazanıyor.** Centroid her
uçakta AYRI entegre edildiği için [1] ve [2] ayrışır → **formasyon gerilir.**
*Öneri:* `_on_formation_out`'a `source_module == 'mode_manager'` süzgeci —
Görev 2 ortak komut akışıyla sürülür, liderin merkezini dağıtmasına gerek yok.
**Şartnamenin "dağıtık" şartıyla da daha uyumlu.**

**B15 · `mode_manager`'da KALKIŞ KAPISI YOK — B3 tek başına uygulanırsa uçak origin'e gider.**
`swarm_context.compute_centroid():129` aktif ajan yoksa **hiçbir şey yazmadan
dönüyor**; centroid açılıştaki `(0,0,0)`'da kalıyor. `mode_manager` READY'de
`_dispatch_hold()` çağırıyor ve o da `compute_hold_command()` ile
**FormationCommand yayınlıyor.**
```
B3 duzeltmesi (test_hazir_atla) -> FSM yerde READY'ye atlar
  -> _dispatch_hold() -> center=(0,0,0) tarifi yayinlanir
  -> formation_node bunu ucurur -> ARM + OFFBOARD ise ucak NED ORIGIN'E GIDER
```
`formasyon_sekans_node` bunu **doğru** yapıyor: guided ARM olayını bekliyor,
sonra uçak `kalkis_esik_orani × irtifa` (0,8) değerine çıkana kadar **susuyor**
(`:331`, `:379`), ancak ondan sonra yayına başlıyor.
*Çözüm:* aynı kapı `mode_manager`'a taşınır.
🔴 **B3 ile AYNI değişiklikte gitmek zorunda — ayrı yapılamaz.**

**B16 · `baslat.sh` `mod` anahtarı `fsm`'e bağımlı değil.**
`:1355` yalnız `formasyon`'a bakıyor. `fsm` kapalıyken `swarm_fsm` hiç
`SwarmState` yayınlamaz → `mode_manager`'ın centroid'i yine `(0,0,0)`'da kalır
→ **B15'in aynı sonucu, farklı yoldan.** `formasyon` kapısının eşi olarak
`fsm` kapısı da konulmalı (~5 satır).

### 🟠 P1 — puan kaybettirir

**B6 · Hareket modunda ivme rampası YOK → doğrudan osilasyon cezası (−10).**
`mode_context.compute_centroid_delta` çubuk→hızı **anında** uyguluyor.
Oysa `manual_kinematics.swarm_movement_step` ivme sınırlı (`_slew`, `a_max_xy`),
yazılmış, test edilmiş — ve **hiçbir yerden çağrılmıyor** (repo geneli tarandı).
Bu, KARAR-11 #3'ün (eğim matematiği tek kaynağa bağlandı) **hareket tarafındaki
eşdeğeri, yapılmamış hâli.**

**B7 · `_handle_formation_change` `_formation_offsets`'i güncellemiyor.**
KARAR-11 #5, **hâlâ açık**. Formasyon değiştirip manevraya geçince gömülü
ofsetler eğilir → **ışınlanma riski.**

**B8 · RTL durumu bir tik yaşıyor.**
`_on_state_entry(RTL)` → `EVENT_RTL_TRIGGERED` yayınlıyor → düğüm **kendi olayını**
dinliyor (`_on_event`) → `land_requested=True` → `mode_transitions.py:39` land
kapısı **RTL'i dışlamıyor** → anında LANDING. Bugün güvenli tarafa düşüyor
(`CLAUDE.md` RTL yasağıyla uyumlu) ama **kazara, tasarımla değil.**

**B9 · YKİ JoystickPanel ikinci üretici VE şartname ihlali.**
`ros_bridge.py:719` laptop'tan `/swarm/internal/control/command` yayınlıyor →
base ESP `TIP_KOMUT` olarak mesh'e basıyor. Görev sırasında açık kalırsa hem
çift üretici hem **§5.2 "müdahale → görev BAŞARISIZ"**.
Tezgâh aracı olarak kalsın, **görev profilinde kilitlenmeli.**

**B10 · `requested_spacing_m` 5.0 sabit.**
`joystick_interpreter_node.py:84` — parametre değil, gömülü. `MOD_ARALIK=7.0`
ile çelişiyor: **ilk formasyon değişikliğinde aralık 7 → 5 m düşer** ve kimse
fark etmez.

**B14 · HOLD 5 sn → otomatik LANDING.** → **G2-K6 ile kaldırılıyor.**
`mode_transitions.py:125`.

### 🟡 P2

| # | Ne | Nerede |
|---|---|---|
| **B11** | Üç giriş kaynağı (`manual_control`, `rc/in`, `joy`) **aynı callback'i** besliyor ve **pitch işareti ikisinde ters**: `:398` negatifliyor, `:352` negatiflemiyor → ikisi birden akarsa dönüşümlü zıt işaret | `joystick_interpreter_node.py` |
| **B12** | Deadman eşiği tutarsız: `deadman_threshold=0.5` **ham aux** (−1000..1000) ile karşılaştırılıyor, `AUX_SAFETY_THRESH=300`. Bugün emniyet kapısı maskeliyor | aynı dosya |
| **B13** | Mesh bütçesi ölçülmedi: `TIP_KOMUT` drone tarafında 50 ms kapıda (20 Hz), mevcut ~53 çerçeve/s üstüne **+20** | `TX DRONE/main.cpp` |

---

## 4. Yapılacaklar — sırayla

Sıra bozulmaz; her adım bir öncekini **ölçerek** kapatır.
Aşama geçişlerinde 🚦 kapı var — kapı sağlanmadan sonraki aşamaya geçilmez.

### AŞAMA A — Laptop, donanım beklemeden *(uçağa hiç dokunulmaz)*

| # | İş | Boyut |
|---|---|---|
| **1** | **B4** V formasyonu (SwC orta → `FORMATION_V`) + **B10** spacing parametresi | ~10 satır |
| **2** | **B7** `_handle_formation_change` → `_formation_offsets` güncellemesi | ~10 satır |
| **3** | 🔴 **B3 + B15 BİRLİKTE** — `test_hazir_atla` **ve** kalkış kapısı. **Ayrılamaz** | ~40 satır |
| **4** | **B16** `mod` anahtarına `fsm` bağımlılık kapısı (`baslat.sh`) | ~5 satır |
| **5** | **B5** `_on_formation_out`'a `source_module == 'mode_manager'` süzgeci | ~4 satır |
| **6** | **B8** RTL land kapısı + **G2-K6** HOLD otomatik inişini kaldır | ~5 satır |
| **7** | **B9** YKİ JoystickPanel'i görev profilinde kilitle | YKİ tarafı |
| **8** | **`rc_ibus_kopru`** düğümü — çerçeve çözücü **saf fonksiyon**, donanımsız yazılıp test edilir | ~120 satır |
| **9** | `gorev_kanit_ucus.py` → **`manevra` senaryosu** (kuru + eğim zarfı + harita). `CLAUDE.md` §9 uçuşu buna kapıyor | — |
| **10** | Birim testler + `ucus_ayarlari.py` denetimi + `bash -n` | — |

> 🚦 **Kapı:** testler yeşil olmadan Aşama B'ye geçilmez.

### AŞAMA B — Donanım (ylp00, atölye)

| # | İş |
|---|---|
| **11** | 🔴 **i-BUS gerilim ölçümü.** Pi 5 GPIO **5 V toleranslı değil**. Ölçmeden bağlanmaz |
| **12** | Kumanda #2 kurulumu: bind → **10 kanal modu** → **failsafe: SwA = KİLİTLİ** kaydet |
| **13** | Kablolama + port seçimi (`SURU_RC_PORT`: USB-TTL `by-id` ya da Pi UART) |
| **14** | **Konteyner recreate ×3** — `--device` + A19 + A12 + drone1 korupt log, **tek işlem**. ⚠️ önce `docker inspect` ile mevcut ayarları not al |
| **15** | Dağıtım: `dagit.sh` ×3 + `ucus_ayarlari.py --kabuk` → `/ws/ucus_ayarlari.env` |

> 🚦 **Kapı:** `drone_bul.sh --durum` → md5 eşit, düğüm sayısı yerinde.
> Bayraklar: `origin consensus fsm formasyon ca mod` üç uçakta ·
> **`joystick` YALNIZ ylp00** · `/ws/gozlem` **takılı**.

### AŞAMA C — G0 yerde, pervanesiz *(uçuş yok, en yüksek getirili adım)*

| # | Ölçülecek |
|---|---|
| **16** | 🔴 RC akıyor mu: `ros2 topic hz /drone_1/rc/suru` ≈ 130 Hz — **ve kill pilotunun çubuğu oynayınca KIPIRDAMAMALI** |
| **17** | Kanal + **işaret haritası**: çubuk ileri → hangi işaret (B11'in son sözü buradadır) |
| **18** | FSM READY'ye çıkıyor mu · **kalkış kapısı yerde tutuyor mu** (B15 doğrulaması — tarif yayınlanMAMALI) |
| **19** | MANEVRA'da **merkez sabitliği** (xy değişmemeli) + `formasyon_sustur` bayrağı |
| **20** | **Centroid sürüklenmesi**: üç uçağın `formation/target.center_*` farkı, 60 sn |
| **21** | **B6 kararı:** çubuk basamağında centroid hızı sıçrıyor mu? Sıçrıyorsa `swarm_movement_step` (ivme rampalı, yazılı ve testli) **uçuştan önce** devreye alınır — osilasyon cezası −10 |
| **22** | **Deadman**: kumandayı kapat → 0,5 sn'de HOLD (alıcı failsafe'i çalışıyor mu) |
| **23** | Mesh bütçesi: `TIP_KOMUT` açıkken çerçeve/s (mevcut ~53 üstüne +20) |

> 🚦 **Kapı:** işaret yönleri **yazılı**, merkez sabitliği ölçülü, deadman kanıtlı.

### AŞAMA D — Uçuşlar

| # | Uçuş | Cevapladığı **tek** soru |
|---|---|---|
| **24** | **A** — ÇİZGİ 7 m / 8 m, HAREKET modu, yalnız pitch git-gel + roll git-gel | Kumanda girdisi sürüyü **formasyonu bozmadan** hareket ettiriyor mu? |
| **25** | **B** — MANEVRA: roll ±%66, pitch aynı profil, yaw ~45° (G2-K4) | Manevra modu merkezi **sabit** tutuyor mu? |
| **26** | **B2** — kumandadan kalkış + kalkış irtifası parametresi *(A ve B'den SONRA)* | — |
| **27** | **C** — OKBAŞI/V eğim + kumandadan formasyon değişimi + kumandadan kalkış/iniş | Asimetri ve kumanda-kalkış çalışıyor mu? |

**B2 neden sona kaydı:** Uçuş A ve B **kanıtlanmış guided kalkışla** başlayıp
kumandaya devredilebilir. Kumandadan kalkışı ilk uçuşa koymak, aynı uçuşta
iki yeni şey denemek olurdu (`PLAN.md` §5).

> Her uçuş öncesi `--kuru --harita` **zorunlu** · harita operatör gözüyle
> doğrulanır · 🔴 **G2-K5 gereği her slotun iniş noktası ayrı ayrı temiz
> olmalı** — uçaklar kalktıkları yere inmez.

### AŞAMA E — Yarışma profili

| # | İş |
|---|---|
| **28** | Hakem direktifi provası: *"3 sn ileri pitch" → "çizgiye geç" → "4 sn sağ roll" → "V'ye geç" → "manevra moduna geç" → "sola yaw"* |
| **29** | `gorev2.md` + `DURUM.md` + `GUNLUK.md` güncelleme (her oturum sonu) |

### Kritik yol

**1 → 3 → 11 → 14 → 16 → 18 → 24.** Diğer her şey bunun yanında paralel yürür.

En uzun bekleme **14** (konteyner recreate); en riskli **11** (gerilim) ve
**18** (kalkış kapısı). **Aşama A'nın tamamı uçaklara hiç dokunmadan bitebilir.**

---

## 5. Ölçülmemiş / açık uçlar

- **i-BUS gerilim seviyesi** — bağlamadan önce (§2, 🔴)
- **İşaret yönleri** (çubuk ileri = hangi işaret) — G0'da kilitlenecek
- **Centroid sürüklenmesi** — her uçağın `mode_manager`'ı centroid'i KENDİ
  tik'inde entegre ediyor. Ölçülüp gerekirse ölçülen sürü merkezine yavaş
  düzeltme eklenecek (`_on_swarm_state` bugün yalnız IDLE/PREFLIGHT/TAKEOFF/
  READY'de centroid'i tazeliyor, MOVEMENT'ta **hiç** tazelemiyor)
- **Mesh bütçesi** `TIP_KOMUT` ile birlikte (B13)
- **Slot ataması Macar değil, kimlik sırasıyla** — çapraz yerleşimde kalır
  (KARAR-11 notu, ayrı P2)
