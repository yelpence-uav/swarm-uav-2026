# GÖREV 2 — Yarı Otonom Sürü Kontrolü

**Son güncelleme:** 30 Ağustos 2026, 15:39 — devir teslim için sadeleştirildi;
plan kalan işe indirildi, saha ölçümleri §7 arşivine taşındı.

Şartname **§5.2** · **100 puan** · görev başına **3 hak**, en yüksek puan sayılır.

> **Görev 2'nin tek toplanma noktası burası.** Devralan §0'dan başlar.
> Genel plan `PLAN.md`, iş listesi `YAPILACAKLAR.md`, günlük `GUNLUK.md`.

---

## 0. Devralan için — 5 dakikada durum

**Ne yapıyoruz:** Üç İHA otonom kalkıp formasyon kuruyor, sonra **tek kumanda**
sürüyü yönetiyor. Kumanda ylp00'a takılı **ikinci bir FS-iA6B alıcıya** bağlı;
o alıcı i-BUS ile Pi'ye giriyor, komut mesh üzerinden diğer iki uçağa dağılıyor.

**Bugün ne çalışıyor:**

| | Durum |
|---|---|
| Donanım zinciri (kumanda → alıcı → Pi → ROS) | ✅ **130 Hz, 0 checksum hatası** |
| Komut zinciri (ROS → mesh → üç uçağın `mode_manager`'ı) | ✅ ölçüldü, 62,8 Hz |
| Kanal + işaret haritası | ✅ ölçüldü, iki ters işaret düzeltildi |
| Kalkış kapısı (yerdeyken hiçbir şey yayınlamama) | ✅ yerde doğrulandı |
| **Kumandadan iniş** | 🔧 **kod yazıldı, uçakta DOĞRULANMADI** (madde 24) |
| **Kumandadan kalkış** | ❌ **YOK** (madde 25) — şartname zorunluluğu |
| Formasyon değişimi (SwC) | ✅ kod var · 🟠 debounce eksik (madde 26) |
| YKİ'den görevi başlatma | ❌ **YOK** (madde 27-28) |

**Sıradaki iş:** §4'teki **madde 24**'ün uçakta doğrulanması, sonra **25**.
Kritik yol: `24 → 25 → 27 → 28 → ilk uçuş`.

### 🔴 Dokunmadan önce bunları oku

1. **`mod` düğümü açıkken sürü ARM olabilir.** 30 Ağustos'ta oldu (§7.6).
   `mod` açıksa **kill pilotları başında olacak.**
2. **Uçuştan önce `--kuru --harita` zorunlu**, harita operatör gözüyle
   doğrulanacak. `CLAUDE.md` §9 — sekiz kırmızı çizgi.
3. **Uçaklar kalktıkları yere İNMEZ** (G2-K5). Her slotun iniş noktası ayrı
   ayrı temiz olmalı.
4. **RTL yok.** HOME kayması açık; iniş her zaman `land`.
5. **Ölçmeden teşhis koyma.** Bu belgedeki her sayı ölçülmüştür; tahminler
   ayrıca işaretlidir.

---

## 1. Şartname ne istiyor

| # | Şart (§5.2.2) | Karşılığı |
|---|---|---|
| G1 | Önce **tam otonom** formasyon kur + stabilize ol, **sonra** kumanda devralır | `mode_manager` TAKEOFF→READY |
| G2 | **Tek** kumanda tüm sürüyü sürer, hepsi **senkronize** tepki verir | `joystick_interpreter` → mesh → 3× `mode_manager` |
| G3 | **Hareket Modu:** pitch=ileri/geri · roll=sağ/sol · yaw=merkez sabit formasyon rotasyonu **+ her İHA kendi heading'ini ayarlar** · throttle=toplu irtifa | `movement_mode` + `formation_node` |
| G4 | **Manevra Modu:** merkez **SABİT** · pitch/roll = formasyon **düzlemi** eğimi · yaw = merkez etrafında dönüş + heading · throttle = toplu irtifa | `maneuver_mode` + `apply_tilt` |
| G5 | **Formasyon değişimi kumandadan** — örnek direktiflerde **çizgi, ok başı ve V** üçü de geçiyor | SwC → `FORMATION_*` |
| G6 | **Kalkış ve iniş kumandadan**, sürü halinde, belirlenen irtifaya (örn. 15 m) | SwD → `px4_bridge` `takeoff:H` / `land` |
| G7 | Başlangıç konumuna dönüş + toplu iniş + disarm | **pilot uçurur**, kod işi değil |
| G8 | En az 3 İHA | ✅ üçü de uçuyor |
| G9 | Görev başladıktan sonra YKİ'den **her türlü müdahale = görev BAŞARISIZ** | YKİ joystick paneli **silindi** |

**"Eğim" uçağın gövdesini yatırmak DEĞİL** — slot irtifa modülasyonudur (Şekil 4).
Görev 1'in QR-tetikli pitch/roll manevrası aynı hareket ama otonom; karıştırılmayacak.

### 🔴 G6 — şartnamenin birebir cümlesi, yorum payı yok

> §5.2.2: *"**Takeoff ve land komutları da kumanda üzerinden yapılır**; sürü
> halinde kalkış ve iniş gerçekleştirilmelidir."*
>
> Senaryo madde 5: *"**Kumanda üzerinden kalkış komutu** ile sürü, **başlangıç
> formasyonunu koruyarak** belirlenen irtifaya (Örn: 15m) yükselir."*

İki sonucu var:

1. **Kalkışı YKİ başlatamaz.** YKİ yalnız görev moduna alır (G2-K8) — senaryo
   madde 4 ile madde 5 **ayrı adımlar**.
2. **Tırmanış dikey olmalı.** Uçaklar hakemlerin dizdiği yerden kalkar,
   hesaplanan slota **koşmaz.** Bunu `px4_bridge`'in yatay çapası
   (`px4_bridge.py:1352`) ve kalkış kapısının `olculen_ofsetler()`'i birlikte
   sağlıyor — **ölçülen** konum, hesaplanan değil.

### 🔴 İki kumanda zorunlu

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

## 2. Kumanda tasarımı (G2-K7)

```
CH1 roll · CH2 pitch · CH3 throttle · CH4 yaw
CH5 SwA  emniyet / deadman            2 konum   1000 / 2000=ACIK
CH6 SwB  mod: hareket / manevra       2 konum
CH7 SwC  formasyon: okbasi/V/cizgi    3 konum   1000/1500/2000 + DEBOUNCE
CH8 SwD  kalkis / inis                2 konum   (notr YOK)
CH9-10   BOS (olculdu: sabit 1000)  ·  VrA/VrB potlar kullanilmiyor
```

Bu 8 kanal §5.2'nin **bütün örnek hakem direktiflerini** karşılıyor:
mod geçişi, üç formasyon, dört eksen, kalkış/iniş.

**İptal iki kademeli — ayrı butona gerek yok:**

```
SwA kapat -> deadman duser -> mode_manager HOLD (suru asili kalir)
SwD asagi -> inis
```

İkisi **bağımsız** çalışmak zorunda: pilot önce SwA'yı kapatıp *sonra* SwD ile
inebilmeli. (30 Ağustos'a kadar kod SwA kapalıyken iniş bayrağını siliyordu —
düzeltildi, `test_swd_mandal.py` ile kilitlendi.)

### 🔴 SwC debounce — dikkatle önlenemeyen tek sorun

SwC detentli 3 konumlu; okbaşı (1000) → çizgi (2000) giderken **fiziksel olarak
ortadan (1500) geçmek zorunda**. El hareketi 200-400 ms, örnekleme 32 Hz →
orta bölgede 6-12 örnek ve kod her ayrı geçişte formasyon değişimi tetikliyor.

Sonuç: hakem *"çizgiye geç"* der, sürü **önce V'ye morf olmaya başlar.**
Kendi kuru testimiz `okbaşı→V` en dar anını **4,95 m** ölçtü, kaçınma eşiği
4,0 m — istenmeyen ara morf kaçınmanın kucağına giriyor (çarpışma −20×N).

*Çözüm:* SwC yeni konumda **N ms kararlı kalmadan** değişim tetiklenmez.
Donanım değişikliği yok. **Eşik ÖLÇÜLEREK konacak** (madde 26).

**SwD'ye nötr konum EKLENMEDİ** (operatör kararı): dinlenme konumu yok, kazara
dokunmak iniş/kalkış demek. Dokunmamak operatörün sorumluluğunda.

### 🔁 RTL — kumandada YOK, ama failsafe olarak ZORUNLU

Şartname §5.2 madde 11: *"**Pilotun kontrolünde** sürü... başlangıç konumuna
geri dönüş rotasını izler"* → dönüş **pilot uçuruyor**. Kumandada RTL butonu
**gerekmiyor.**

Ama §5.4 ayrı bir şey söylüyor:

> *"Kumanda bağlantısı koptuğunda... failsafe **hakem kurulu tarafından
> belirlenecektir**. RTL veya Land'den biri olabilir. Belirlenen failsafe
> davranışını doğru gerçekleştiremeyen takımların **uçuşuna izin
> verilmeyecektir**."*

Bu **PX4 seviyesinde**, kill pilotunun linkine bağlı, zaten yapılandırılmış
(`RC_MAP_FAILSAFE=3`, `RC_FAILS_THR=2050`; 19 Ağu havada doğrulandı).

> 🔴 **AMA HOME KAYMASI AÇIK (P0).** RTL üç uçağı kalkış yerine değil ~9 m
> KD'ya indirmişti. Hakem failsafe olarak **RTL derse bu bir UÇUŞ İZNİ
> sorunudur**, puan değil. Hakem brifinginde netleştirilmeli (madde 35).

---

## 3. Kararlar

| # | Karar | Gerekçe (özet) |
|---|-------|----------------|
| **G2-K1** | **Pilot uçağı: ylp00** | İkinci alıcı buraya takıldı. ⚠️ ylp00 kaçınmada **ÇAPA** (dikeyde kaçmaz) ve düşerse sürü komut kaynağını kaybeder — bilerek kabul edildi |
| **G2-K2** | **i-BUS Servo → Pi UART** | Standart UART (115200 8N1) + **checksum var** → bozuk çerçeve atılabilir. PPM elendi: zamanlama Linux'a kalıyordu, checksum yok, 8 kanalla tam sınırdaydık |
| **G2-K3** | **Ayrı kumanda + ayrı pilot** | Şartname zorunlu kılıyor. ylp00: 2 kumanda + 2 pilot. Tek kumandayı iki alıcıya bind etmek mümkün ama **teknik kontrolde takılır** |
| **G2-K4** | **Test genlikleri: eğim ±10°, yaw ~45° / 12,5°/s** | Tavanlar `ucus_ayarlari` MOD_*'ta 15° / 25°/s. Test bunun altında — ilk uçuşta muhafazakâr |
| **G2-K5** | **İniş: slot üstüne `land`, EVE fazı YOK** | 🔴 Uçaklar kalktıkları yere **inmez.** Her slotun iniş noktası haritada ayrı doğrulanacak |
| **G2-K6** | **HOLD'dan otomatik iniş KALDIRILDI** | 5 sn komutsuzluk LANDING'e geçiriyordu. **5 saniyelik mesh sarsıntısı görev ortasında iniş yaptırırdı.** İniş kararı pilota/hakeme ait. ⚠️ **Bedeli aşağıda** |
| **G2-K7** | **Kumanda tuş tasarımı** (§2) | 8 kanal bütün örnek direktifleri karşılıyor. SwD'ye nötr yok (operatör kararı); SwC'ye yazılım debounce |
| **G2-K8** | **Görev 2 YKİ'den başlatılır**, SwD'den DEĞİL | Senaryo madde 4 *"Hakemin komutuyla... yarı otonom kontrol moduna geçirilir"*; YKİ'ye izinli tek eylem "görevi başlatma". Kalkış AYRI adım (madde 5) ve **kumandadan** |
| **G2-K9** | **Aralık YKİ'den, GÖREV ÖNCESİ** (SSH ile canlı param) | Şartname aralığı sabit veriyor, görev içinde değişmiyor. Bugünkü yol (env + restart) saha gününde dakikalar alır. Mesh'e dokunmaz, **canlı komut yolu açmaz** |

### ⚠️ G2-K6'nın kabul edilen bedeli

Otomatik iniş kalkınca **kumanda kaybında sürü süresiz asılı kalır.**
Kaçınma çalışmaya devam eder, ama **pil izleme üç uçakta da KAPALI**
(`BAT1_SOURCE` disabled · `BATARYA_KRITIK_V=0.0` · YKİ'de `PIL_GOSTER=false`)
— yani yazılım tarafında hiçbir otomatik koruma yok.

> **Süreyi pilotlar tutar; çıkış yolu kill-switch pilotlarıdır.** Bilerek böyle.

### ⏳ Karara bağlanmamış: ARM yetkisi (madde 25'in konusu)

Şartname arm'dan hiç söz etmiyor — seçim bize ait. 30 Ağustos olayının kökü
tam olarak **arm'ın örtük gerçekleşmesiydi**, o yüzden açıkça tasarlanacak.

| Seçenek | Artı | Eksi |
|---|---|---|
| **(a) SwD → `arm` + `takeoff:H` atomik** *(öneri)* | Pilotun tek hareketi, her normal RC multirotor böyle. Armlı bekleme penceresi **yok** | Tek şalter üç uçağı armlar — ama artık **etiketli ve kapılı** |
| (b) YKİ arm eder, SwD kaldırır | Arm yerde, göz önünde | Uçaklar **pervaneleri dönerken** belirsiz süre bekler |

Öneri **(a)**, üç koşulla kapılı: SwA açık · gaz merkezde · görev YKİ'den
başlatılmış. **Operatör kararı bekliyor.**

---

## 4. PLAN — kalan iş

**Bitti:** Aşama A (kod, 10 madde) · Aşama B (donanım, 5 madde) ·
Aşama C (yerde ölçüm, 16-18 + 22-23). Ayrıntı §7.

**Kalan üç aşama:**

### 🎛 AŞAMA D — uçuştan önce kapatılacaklar

| # | İş | Öncelik | Durum |
|---|---|---|---|
| **24** | **`mode_manager` LANDING gerçekten indirsin** | 🔴 | 🔧 **kod yazıldı, uçakta doğrulanmadı** |
| **25** | **Kumandadan kalkış** (B2) + `MOD_KALKIS_IRTIFA` | 🔴 | ❌ açık · **önce ARM yetkisi kararı** (§3) |
| **26** | **SwC debounce** — önce ÖLÇ, sonra eşik | 🟠 | ❌ açık |
| **27** | **`mission_fsm` aç** (ADIM 6) | 🟠 | ❌ açık — G2-K8'in ön koşulu |
| **28** | **YKİ "Görev 2 BAŞLAT" butonu** + `joystick_interpreter`'dan `_call_trigger_mission` kaldır | 🟠 | ❌ açık |
| **29** | **YKİ aralık alanı** (SSH ile canlı param) | 🟡 | ❌ açık |
| **30** | **Alıcı failsafe kaydı: SwA = 1000** | 🟠 | ❌ açık — kumandada yapılır |

> 🚦 **KAPI: 24 ve 25 bitmeden UÇUŞ YOK.**
> İkisi de birim testle kilitlenir; 24 ayrıca **yerde** doğrulanır.

**Kritik yol:**

```
24 -> 25 -> 27 -> 28 -> 31
inis   kalkis  mission_fsm  YKI BASLAT  ilk ucus
```

Sıra tesadüf değil: **iptal yolu olmadan `mod` ile test yapılmaz.**
26 · 29 · 30 paralel yürür; kritik yolu tutmaz ama **ilk uçuştan önce** biter.

### AŞAMA E — Uçuşlar

| # | Uçuş | Cevapladığı **tek** soru |
|---|---|---|
| **31** | **A** — ÇİZGİ 7 m, HAREKET modu, yalnız pitch git-gel + roll git-gel | Kumanda girdisi sürüyü **formasyonu bozmadan** hareket ettiriyor mu? *(G0 19-21 burada ölçülür)* |
| **32** | **B** — MANEVRA: roll ±%66, pitch aynı profil, yaw ~45° | Manevra modu merkezi **sabit** tutuyor mu? |
| **33** | **C** — OKBAŞI/V + kumandadan formasyon değişimi + kalkış/iniş | Asimetri ve kumanda-kalkış çalışıyor mu? |

> Her uçuş öncesi `--kuru --harita` **zorunlu** · harita operatör gözüyle
> doğrulanır · her slotun iniş noktası ayrı temiz olmalı (G2-K5) ·
> 🔴 **kill pilotları başında.**

### AŞAMA F — Yarışma profili

| # | İş |
|---|---|
| **34** | Hakem direktifi provası: *"3 sn ileri pitch" → "çizgiye geç" → "4 sn sağ roll" → "V'ye geç" → "manevra moduna geç" → "sola yaw"* |
| **35** | 🔴 **HOME kayması** — hakem failsafe olarak RTL derse **uçuş izni** sorunu. Brifingde netleştir |
| **36** | `/ws/mod_test` **SİL** — yarışma profilinde test bayrağı kalmaz |
| **37** | Belge güncelleme (her oturum sonu): `gorev2.md` · `DURUM.md` · `GUNLUK.md` |

---

## 5. Açık boşluklar

### 🔴 P0

**B2 · Kumandadan kalkış YOK (G6 ihlali).** → madde 25.
`mode_manager` TAKEOFF'a giriyor ama **kalkış komutu üretmiyor** (30 Ağustos'ta
`EVENT_MISSION_STARTED` bilerek kaldırıldı, §7.6). `MOD_KALKIS_IRTIFA`
parametresi de yok; şartname *"belirlenen irtifaya (örn. 15 m)"* diyor,
bizim test irtifamız `MOD_TEST_IRTIFA_M = 8.0`. **İkisi ayrı parametre olmalı.**

**B19 · `COMPLETED` terminal — çıkışı yok.** *(30 Ağustos'ta bulundu)*
`mode_transitions._TERMINAL_STATES = {COMPLETED}` ve `evaluate_transitions`
oradan hiçbir geçiş döndürmüyor. İniş bitince (ya da 90 sn LANDING zaman
aşımında) `mode_manager` COMPLETED'a girip **orada kalıyor** — ikinci kalkış
için konteyner yeniden başlatmak gerekir. **Görev başına 3 hakkımız var**,
yani saha gününde denemeler arası bu yaşanacak.
*Çözüm önerisi:* COMPLETED'dan IDLE'a dönüş — tüm ajanlar disarm **ve**
`land` mandalı düşmüşse (~6 satır). Kararı verilmedi.

### 🟠 P1

**B6 · Hareket modunda ivme rampası YOK → doğrudan osilasyon cezası (−10).**
`mode_context.compute_centroid_delta` çubuk→hızı **anında** uyguluyor.
Oysa `manual_kinematics.swarm_movement_step` ivme sınırlı (`_slew`, `a_max_xy`),
yazılmış, test edilmiş — ve **hiçbir yerden çağrılmıyor.**
Uçuş A'da (madde 31) ölçülüp karar verilecek.

**B13 · `_on_control_out`'ta hız limiti yok.** UART'a yazdığımızın **~%75'i**
ESP'de COBS+CRC çözülüp atılıyor (ölçüldü). Mesh yükünü değiştirmiyor, yalnız
boşa iş. *Öneri (~8 satır):* 40 ms (25 Hz) limit. 🟡 Operatör: **mesh bütçesi
artık önemsiz, göz ardı edildi.**

### 🟡 P2

| # | Ne | Nerede |
|---|---|---|
| **B11** | Üç giriş kaynağı (`manual_control`, `rc/in`, `joy`) aynı callback'i besliyor; ikisi birden akarsa dönüşümlü zıt işaret. Bugün remap ile yalıtıldı ama kod hâlâ öyle | `joystick_interpreter_node.py` |
| **B12** | Deadman eşiği tutarsız: `deadman_threshold=0.5` **ham aux** (−1000..1000) ile karşılaştırılıyor, `AUX_SAFETY_THRESH=300`. Bugün emniyet kapısı maskeliyor | aynı dosya |

### ✅ Kapananlar

| # | Neydi | Nasıl kapandı |
|---|---|---|
| B1 | İkinci alıcı sisteme giremiyordu (PX4'te **tek** RC girişi var, o da kill pilotunun) | `rc_ibus_kopru` düğümü + `/drone_1/rc/suru` remap'i. ⚠️ **Bkz. aşağıdaki kanal çakışması** |
| B3 | FSM sahada READY'ye ulaşamıyordu | `test_hazir_atla` (`/ws/mod_test` bayrağı) |
| B4 | SwC ortası `FORMATION_UNKNOWN` veriyordu → **V seçilemiyordu** | orta → `FORMATION_V`; ölçümde ortanın tam 1500 olduğu doğrulandı |
| B5 | `formation/target`'ta iki üretici | `_on_formation_out`'a `source_module` süzgeci |
| B7 | Formasyon değişince `_formation_offsets` güncellenmiyordu → ışınlanma riski | `_publish_formation_command`'da eşitlendi |
| B8 | Düğüm **kendi olayını** duyup RTL'i bir tikte LANDING'e çeviriyordu | kaynağı sustur: `source_module == 'mode_manager'` yok sayılıyor |
| B9 | YKİ JoystickPanel ikinci üretici **ve** şartname ihlali riski | **komple silindi** (−1.430 satır); YKİ artık mesh'e komut basamıyor |
| B10 | `requested_spacing_m` 5.0 sabitti, `MOD_ARALIK=7.0` ile çelişiyordu | parametre yapıldı |
| B14 | HOLD 5 sn → otomatik LANDING | G2-K6 ile kaldırıldı |
| B15 | Kalkış kapısı yoktu → B3 tek başına uygulansa **uçak NED origin'e giderdi** | kapı eklendi: hepsi görülmüş + **hepsi ARMED** + eşik üstünde |
| B16 | "`mod`, `fsm`'e bağımlı olsun" | kod okundu, **gerekçe çürüdü** → kapı değil **uyarı** oldu |
| B17 | `formation_heading_deg` hiç hesaplanmıyordu → kuzey sanılıyordu | `swarm_fsm` hesaplıyor + kapıda ölçülen yaw'dan tohumlama |
| B18 | Gaz çubuğu dipteyken SwA açılırsa sürü **anında 2 m/s alçalırdı** (FlySky Mod 2'de gaz **kendiliğinden ortalanmaz**, doğal olarak dipte durur — ölçülen dinlenme PWM **1001**) | gaz merkez kapısı; SwA her kapanışta sıfırlanır |
| G1 | LANDING gerçekten indirmiyordu | madde 24 — kod yazıldı, doğrulama bekliyor |

> ### 🔴 Kanal çakışması — "neden mevcut alıcıyı kullanmıyoruz?"
>
> ylp00'ın Pixhawk RC girişi **kill pilotuna ait ve dolu**: `RC_MAP_FAILSAFE=3`,
> `RC_FAILS_THR=2050`, **CH5 = kill**, CH8 = arm (`RPI_ESITLEME.md` §5,
> 19 Ağu havada doğrulandı). Sürü zinciri ise CH5'i *emniyet (SwA)*, CH8'i
> *kalkış/iniş (SwD)* sanıyor.
>
> Yani sürü zinciri o alıcıya bağlansaydı **kill switch'i kaldırmak sürü
> komutlarını AÇAR** ve **arm switch'i kalkış/iniş tetiklerdi.**
> İkinci alıcı bu yüzden tercih değil, **zorunluluk.**

---

## 6. Sistem — zincir ve dosyalar

**Komut yolu (Görev 2):**

```
FS-i6X #2  --2.4 GHz-->  FS-iA6B #2
  --i-BUS Servo (115200 8N1, 32 bayt, ~130 Hz)-->  pin 29 / GPIO5
  --/dev/ttyAMA2-->  rc_ibus_kopru          -> /drone_1/rc/suru  (RCIn)
  -> joystick_interpreter                   -> /swarm/internal/control/command
  -> ic_dis_kopru                           -> /swarm/public/control/command
  -> esp32_bridge -> mesh (TIP_KOMUT) ------> diger iki ucagin public konusu
  -> her ucakta mode_manager                -> /drone_N/control/setpoint/raw
  -> collision_avoidance                    -> /drone_N/control/setpoint
  -> px4_bridge -> MAVROS -> PX4 (OFFBOARD)
```

**İptal yolu (durumdan bağımsız olmak ZORUNDA):**

```
SwD asagi -> inis mandali -> mode_manager LANDING
          -> /swarm/agent/droneN/commands: "land"  (1 Hz TEKRARLI)
          -> px4_bridge -> AUTO.LAND
```

**Hangi dosya ne yapıyor:**

| Dosya | İş |
|---|---|
| `swarm_control/rc_ibus/ibus_cozucu.py` | Saf i-BUS çözücü — checksum, çerçeve ayıklama. Testli |
| `swarm_control/rc_ibus/rc_ibus_kopru_node.py` | Seri → `RCIn` |
| `mode_manager/rc_eksen.py` | Eksen işaretleri — **ölçüm gerekçeleri burada** |
| `mode_manager/swd_mandal.py` | SwD kenar/mandal mantığı. Testli |
| `mode_manager/joystick_interpreter_node.py` | RC → `SwarmControlCommand` |
| `mode_manager/mode_context.py` | Kalkış kapısı, centroid/heading tohumlama |
| `mode_manager/mode_transitions.py` | FSM geçiş kuralları |
| `mode_manager/mode_manager_node.py` | Düğüm: abonelik, yayın, iniş komutu |
| `swarm_core/formation_control/manual_kinematics.py` | `dairesel_ortalama_deg`, eğim matematiği |
| `src/gcs/ucus_ayarlari.py` | **Bütün MOD_* tavanları — başka yerde elle yazılmaz** |
| `deploy/rpi/baslat.sh` | Düğüm başlatma, remap, `TEK-URETICI` kuralı |

**Uçakta açık düğümler için:** `/ws/suru_dugumleri` →
`origin consensus fsm formasyon ca mod` (üçünde) + `joystick` (yalnız ylp00).
Bayrak dosyası `/ws/mod_test` üçünde de takılı.

**Test:**

```bash
PYTHONPATH=src/swarm_state_machine:src/swarm_core \
  python3 -m unittest discover -s src/swarm_state_machine/test
```

---

## 7. Arşiv — saha ölçümleri ve kapanmış kusurlar

### 7.1 Donanım

| | |
|---|---|
| Sinyal | i-BUS Servo → **fiziksel pin 29 (GPIO5)** = `uart2` RX |
| Overlay | `dtoverlay=uart2-pi5` → `/dev/ttyAMA2` |
| Seviye | **~3 V ölçüldü** → doğrudan bağlanır ✅ (Pi 5 GPIO'su 5 V toleranslı DEĞİL, ölçmeden bağlanmaz) |
| Diğer UART'lar | `ttyAMA0` Pixhawk (pin 8/10) · `ttyAMA4` ESP32 (pin 32/33) |
| Konteyner | `--device /dev/ttyAMA2` gerekiyor → recreate şart (30 Ağu yapıldı) |

Kumandadaki `IntV1 5,3 V` alıcının **beslemesi**, sinyal değil.
FS-i6X varsayılanı 6 kanal; 8 kanal için **10-kanal modu açıldı.**
Filo dağılımı: `RPI_ESITLEME.md` **A23**.

### 7.2 SAHA ÖLÇÜMÜ — 30 Ağustos 2026, ylp00, FS-i6X #2

```
2597 + 3246 + 5195 cerceve  ·  130 Hz sabit
checksum hatasi 0  ·  atilan bayt 0     <- sinyal seviyesi marjinal DEGIL
```

**Kanal haritası:**

| Kanal | Ölçülen | Sonuç |
|---|---|---|
| CH1 roll · CH2 pitch · CH3 gaz · CH4 yaw | 1000–2000 | ✅ |
| **CH5 SwA** emniyet | 1000 / **2000 = AÇIK** | ✅ eşik 300 doğru tarafta |
| CH6 SwB mod | 2 konum (+ tutulunca sahte orta) | ✅ orta `aux=0` → HAREKET |
| **CH7 SwC** formasyon | **1000 / 1500 / 2000** | ✅ **3 konum** → okbaşı / **V** / çizgi |
| CH8 SwD kalkış/iniş | 1000 / 2000 | ✅ |
| CH9–14 | sabit | kullanılmıyor |

🔴 **SwC'nin ortası tam 1500** — B4 düzeltmesi tam oraya oturuyor. Anahtar
2 konumlu çıksaydı *"V formasyonuna geç"* direktifi karşılanamazdı.

**İşaret yönleri — ikisi TERSTİ:**

| Çubuk | Yön | PWM | Eski kod | Sözleşme | |
|---|---|---|---|---|---|
| pitch | İLERİ | **1974** | −0,95 | `>0 = ileri` | 🔴 **TERSTİ** |
| roll | SAĞA | **1981** | +0,96 | `>0 = sağa` | ✅ doğruydu |
| yaw | SAĞA | **1014** | −0,97 | `>0 = saat yönü` | 🔴 **TERSTİ** |
| gaz | YUKARI | 1988 | +0,98 | `>0 = tırmanış` | ✅ |

Eski kodda *"genellikle RCIn pitch ileri itince pwm düşer"* diye bir **varsayım**
yazılıydı; bu kumandada tersi çıktı. Düzeltilmeseydi **Uçuş A'da sürü çubuğun
tersine giderdi.**

> ⚠️ İlk ölçümde her çubuk **iki yöne birden** oynatıldığı için sonuç
> belirsizdi ve roll de ters sanıldı. Tek yönlü tekrar yapıldı; sıra
> varsayımıyla koda dokunulsaydı **doğru olan roll bozulacaktı.**

### 7.3 Deadman — önceki bulgu YANLIŞTI

Bir ara *"kumanda kapanınca i-BUS susuyor"* yazılmıştı. **Yanlış.** İlk gözlemde
0 bayt okunmuştu ama alıcı o sırada beslenmiyordu. Kontrollü ölçüm:

```
kumanda ACIK  : [1502, 1500, 1500, 1500, 2000, 1000, 1000, 1000]
kumanda KAPALI: [1503, 1500, 1002, 1500, 1500, 1500, 1500, 1500]
                                         ^SwA  ^SwB  ^SwC  ^SwD
cerceve akisi : 130 Hz, checksum_hata 0   -> ALICI SUSMUYOR
```

**Deadman yine de düşüyor** — sessizlikle değil, alıcının **varsayılan
failsafe'i bütün anahtar kanallarını 1500'e aldığı için.** `aux1 = 0`,
eşik 300 → emniyet **KİLİTLİ.**

⚠️ **Bu bir VARSAYILAN, garanti değil.** FlySky'da *"son konumu tut"* seçeneği
de var; biri onu açarsa **SwA 2000'de kalır ve deadman DÜŞMEZ.**
→ madde 30: failsafe **SwA = 1000** olarak açıkça kaydedilecek.

### 7.4 Kill pilotu izolasyonu — yapısal kanıt (G0 madde 16)

Çubuk oynatmadan, `ros2 node info /joystick_interpreter_node` abonelikleri:

```
/drone_1/rc/manual_control_KAPALI   <- olu konu, 0 yayinci
/drone_1/rc/suru                    <- SURU alicisi (rc_ibus_kopru)
/joy                                <- 0 yayinci (YKI joystick silinmisti)

/drone_1/mavros/rc/in  LISTEDE YOK
```

`px4_bridge` hâlâ `/drone_1/mavros/rc/in` dinliyor → **kill zinciri bozulmadı.**
İki zincir tam ayrık; kill pilotunun çubuğu sürü zincirine **ulaşamıyor.**

### 7.5 G0'da yakalanan üç kusur

**D1 — `ic_dis_kopru` QoS kırığı.** `joystick_interpreter`
`/swarm/internal/control/command`'a **BEST_EFFORT** yayınlıyordu; `ic_dis_kopru`
o konuyu **RELIABLE** dinliyor. Eşleşmedi:

```
/swarm/internal/control/command   46.6 Hz
/swarm/public/control/command     HICBIR SEY      <- kirik
```

Sonucu: **pilotun KENDİ uçağı çubuğa cevap vermezdi**, diğer ikisi mesh'ten
alıp cevap verirdi. Havada teşhisi çok zor. Yayıncı RELIABLE yapıldı →
**62,8 Hz** doğrulandı.

**D2 — `rc_ibus_kopru` 16 Hz yayınlıyordu, 50 değil.** `read(256)` 4160 B/s'te
**61,5 ms** bloklar; yayın hızını `yayin_hz` değil **okuma yığını** belirliyordu.
Üstelik yığının **en eski** çerçevesi yayınlanıyordu. → `read(64)` + en taze
çerçeve → **32,5 Hz.**

**G0 madde 18 — kalkış kapısının HİÇ AÇILAMAYACAĞI kusur.**
`mode_manager` kendi durumunu da `/swarm/public/drone{N}/status`'tan bekliyordu;
o konunun **yayıncı sayısı 0** (tasarım: uçağın kendi durumu kendi public
konusuna köprülenmiyor). Sonuç: `all_agents_seen()` asla `True` olmuyordu →
**Görev 2 komple ölü olurdu ve hiçbir yerde hata görünmezdi.**
Düzeltme: kendi durumu `/swarm/internal/drone{ben}/status`'tan.

**Asıl ders sessizlikti.** Kapı neden kapalı olduğunu söylemiyordu; artık
10 saniyede bir sebebini yazıyor ve bu kusuru **ilk saniyede** yakaladı.

🔴 Aynı ölçümde çıkan ikinci gerçek: **yükseklikler paylaşılan origin'e göre,
yere göre değil.** Üçü de YERDEyken ylp00 **+1,7 m** okundu — 2,0 m eşiğin
%85'i. Bir uçak origin'in 2,5 m üstüne konsaydı **kapı yerdeyken açık olurdu.**
Çözüm: kapıya **ARM ŞARTI** eklendi (disarm uçak havada olamaz, irtifa
referansından bağımsız). Eşiği büyütmek çözüm değildi — ofset de büyüyebilir.

### 7.6 🔴 30 Ağustos saha olayı — pervanesiz ARM

**Ne oldu:** SwD kalkışa alındı → üç `mode_manager` TAKEOFF'a girdi →
`EVENT_MISSION_STARTED` yayınlandı → `agent_fsm` bunu **ARM'a çevirdi** →
`px4_bridge` OFFBOARD + ARM yapıp irtifayı kilitledi → **pervanesiz** uçak o
irtifayı tutamayınca konum denetleyicisinin integrali sardı, gaz tırmandı,
PX4 kendini *"flying"* saydı ve **yazılım disarm'ını REDDETTİ** (`MAV_RESULT=1`).
Kumandadan iniş yolu da yoktu. Olay ancak `agent_fsm`'in zaman aşımıyla bitti.
Pervaneler sökülüydü, fiziksel hasar yok. Tam kayıt: `DURUM.md` §3.

**Alınan üç ders — üçü de koda girdi:**

1. **`mode_manager` görev başlatıcısı değil.** `EVENT_MISSION_STARTED`
   yayınlaması *"SwD'ye dokunmak sürüyü ARM eder"* demekti. **Kaldırıldı.**
   Kalkış yetkisi artık madde 25'in işi ve **açıkça tasarlanacak.**
2. **İptal yolu duruma bağlı olamaz.** *"Hiçbir tuşla iniş veremedim"*in sebebi
   ölçüldü: zincir aslında **vardı** —
   `LANDING → EVENT_EMERGENCY_LAND → agent_fsm.pending_state = LANDING` — ama
   `agent_transitions` bunu **yalnız 3 durumdan** kabul ediyor
   (`IN_SWARM:207`, `RETURN_HOME:316`, `FAILSAFE:387`) ve uçaklar **ARMED**'daydı.
   `agent_fsm_node.py:232` tick sonunda isteği **koşulsuz siliyor** → istek tek
   tick yaşayıp **sessizce kayboluyor.**
   → madde 24: `land` artık **doğrudan `px4_bridge`'e**, **1 Hz tekrarlı.**
3. **`mod` açıkken kill pilotları başında olacak.** Kural haline geldi.

**Madde 24'te kapatılan dört kusur:**

| | Neydi | Sonucu olurdu |
|---|---|---|
| a | LANDING yalnız olay yayınlıyordu | ARMED'dayken iniş **hiç gitmiyordu** |
| b | İniş bayrağı **tek tick** yaşıyordu | mesh'in 200 ms kapısı ya da tek paket kaybı iptali **tamamen** yutardı |
| c | SwA kapalıyken `cmd.land` **siliniyordu** | pilot önce SwA'yı kapatırsa SwD ile **bir daha inemezdi** |
| d | LANDING'de `formation_node` susmuyordu | biri offboard'ı geri açarsa uçak formasyon slotuna **fırlardı** |

Ayrıca RTL durumu artık `EVENT_RTL_TRIGGERED` **yayınlamıyor**: `agent_fsm` onu
RETURN_HOME'a çevirip `offboard` yolluyordu ve bu **inişi iptal ederdi.**

---

## 8. Ölçülmemiş / açık uçlar

- **Uçakların yerdeki yönü artık ÖNEMLİ** (B17 sonrası): formasyon burunların
  baktığı yöne göre kuruluyor. Uçakları **aynı yöne diz**; kuru test
  tutarlılık < 0,90 ise uyarıyor.
- **Centroid sürüklenmesi** — her uçağın `mode_manager`'ı centroid'i KENDİ
  tik'inde entegre ediyor. `_on_swarm_state` bugün MOVEMENT'ta centroid'i
  **hiç tazelemiyor.** Uçuş A'da ölçülecek (madde 31).
- **`TIP_KOMUT` protokolü yeterli:** mod, 4 çubuk, kalkış/iniş/RTL/acil,
  deadman, formasyon+aralık — **13 bayt dolu / 3 bayt boş.** Kalkış irtifası
  için **mesh'e gerek yok**: her uçağın kendi paramı (§5.2 görev öncesi YKİ
  ayarına izin veriyor).
- **ACİL İNİŞ butonu Görev 2'de hâlâ gizli** (`App.tsx`). Gizlenme sebebi
  joystick panelinin o alanı kaplamasıydı; panel silindi, **sebep kalktı.**
  Görev 2'de gösterilsin mi — operatör kararı.
- **Slot ataması Macar değil, kimlik sırasıyla** — çapraz yerleşimde kalır
  (KARAR-11 notu, ayrı P2).
- **`--durum` bayrak listesi 30 Ağu'da düzeltildi** — `gozlem`, `yer_testi`,
  `origin` hiç görünmüyordu. Başka eskimiş liste var mı, bakılmadı.
