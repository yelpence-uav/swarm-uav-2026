# GÖREV 2 — Yarı Otonom Sürü Kontrolü

**Son güncelleme:** 4 Eylül 2026, 23:15 — 🔒 **G2-K13: lider SEÇİLMEZ, VERİLİR
(ylp00).** Sabit liderlik **SİSTEM GENELİ** (operatör kararı: hem Görev 1 hem
Görev 2); **slot 0 = ortada** kuralı yalnız Görev 2. Kod yazıldı, 1058 test
geçti, canlı düğümde ölçüldü; 🔴 **uçaklara dağıtılmadı** (KARAR-17).
Eski: 4 Eylül 06:50 — **B5 süzgeci kaldırıldı** (tek-yayıncı ile çatışıp
takipçileri tarifsiz bırakıyordu; uçuşta ölçüldü). Eski: 1 Eylül — **§7.19:
manevra irtifa datumu düzeltildi** (uçakta doğrulanmadı) + iki saha olayı
(ylp02 düştü, ylp00 roll arızası). Eski: 🔴 **§7.18: SÜRÜ HAREKETİ HİÇ
ÇALIŞMIYORMUŞ** — mesh `deadman_timeout_s`'i taşımıyor, komşular READY'de
kalıyordu. Düzeltildi ve dağıtıldı. Eski: 🔴 **SAHA OLAYI §7.16: formasyon
morfunda 1,65 m yaklaşma.** Kaçınma doğru çalıştı, hız çok yüksekti; morf hızı
seyirden ayrıldı (`MOD_MORF_HIZ=0,6`), üç uçağa dağıtıldı. Eski: **B6 ve MADDE 29
(aralık/irtifa girişi) KOD OLARAK BİTTİ**, üçüncü bir taşıma yolu seçildi:
değerler **BAŞLAT paketinin içinde** mesh'ten gidiyor (SSH yok, betik yok).
🔴 **Hiçbiri uçakta yok — uçaklar kapalı, dağıtım yapılamadı.** Eski: kumandadan
üç uçaklı kalkış/iniş uçtu (§7.14) · VrB formasyon ana anahtarı (§7.15).

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
| **Kumanda kaybında deadman** | ✅ **DÜŞÜYOR** — yeni alıcıda failsafe çalışıyor (madde 30, §7.12) |
| Eksen işaretleri | ✅ yeniden ölçüldü — **yaw artık ters DEĞİL** (§7.12) |
| SwC debounce | ✅ yeniden ölçüldü — **1300 ms** (muhafazakâr, §7.12) |
| **Kumandadan iniş** | ✅ **GERÇEK KOŞULDA DOĞRULANDI** — armlı uçağı anında indirdi (§7.13) |
| **Kumandadan kalkış** | 🔧 komut zinciri doğrulandı (ylp00 armlandı, motorlar döndü) · **pervaneli uçuş YAPILMADI** |
| Formasyon değişimi (SwC) | ✅ kod + debounce 1300 ms (madde 26) |
| Görevi başlatma (üç uçağa birden) | ✅ **UÇAKTA DOĞRULANDI** — mesh yayılımı, ~1 sn (§7.13) |

**Sıradaki iş: PERVANELİ UÇUŞ — kalk · asılı dur · in.** Aşama D bitti,
üç uçağa dağıtıldı ve yerde doğrulandı. Kalan tek kod maddesi **29**
(canlı param taşıma yolu, 🟡).

> 🔴 **UÇUŞTAN ÖNCE, sırayla:**
> pervaneleri tak · uçakları **7 m** aralıkla **aynı yöne** diz ·
> **kill pilotunun kumandasını AÇ** (31 Ağu gecesi kapalıydı, kuru test
> `ARM'A HAZIR DEĞİL` dedi) · `--kuru --harita` tekrarla ve haritayı
> **gözle doğrula** · **SwC'ye DOKUNMA** (formasyon UNKNOWN kalsın, yoksa
> uçaklar slotlara koşar ve iniş noktaları değişir).
>
> ⚠️ **Konteynerleri yeniden başlat.** `active_formation` 31 Ağu gecesi
> ÇİZGİ'ye ayarlandı ve düğümde duruyor; READY'ye geçilince sürü çizgi
> slotlarına giderdi. Restart onu UNKNOWN'a döndürür.
>
> 🔴 **SwA bu kumandada AŞAĞI = AÇIK** — kill kumandasıyla ters (§7.13e).

Kuru test komutu (bu profil için doğrulanmış):
```bash
python3 src/gcs/gorev_kanit_ucus.py --kuru --harita \
    --senaryo asili --dronelar 1,2,3 --irtifa 8
```

### 🔴 Dokunmadan önce bunları oku

1. **`mod` düğümü açıkken sürü ARM olabilir.** 30 Ağustos'ta oldu (§7.6).
   `mod` açıksa **kill pilotları başında olacak.**
2. **Uçuştan önce `--kuru --harita` zorunlu**, harita operatör gözüyle
   doğrulanacak. `CLAUDE.md` §9 — sekiz kırmızı çizgi.
3. **Uçaklar kalktıkları yere İNMEZ** (G2-K5). Her slotun iniş noktası ayrı
   ayrı temiz olmalı.
4. **RTL yok.** HOME kayması açık; iniş her zaman `land`.
4b. ⚠️ **KUMANDA 31 AĞUSTOS'TA DEĞİŞTİ.** Eksen işaretleri, failsafe ve
   SwC debounce **yeniden ölçüldü** (§7.12). Kumanda bir daha değişirse
   üçü de yeniden ölçülmek ZORUNDA.
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
Donanım değişikliği yok.

✅ **ÖLÇÜLDÜ (30 Ağustos, §7.11): N = 500 ms.** Ölçülen geçiş tavanı 342 ms
— ve anahtar **detentli** olduğu için yavaş çevirmeye çalışınca da değişmedi.
Yani geçiş süresi elin hızına değil anahtarın mekaniğine bağlı; debounce'un
güvenilirliği buradan geliyor.

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
| **G2-K11** | **Görev başlatma MESH'ten yayılır** (SSH ile üçe ayrı ayrı DEĞİL) | Operatör kararı, 31 Ağu. Başlatma tek uçağa gelir, durum paketindeki bir bitle komşulara duyurulur; **her uçak kendi preflight'ını koşar.** Ölçüldü: tek tetikten üçüne **~1 sn**. Wi-Fi'siz çalışır. ⚠️ `EVENT_MISSION_STARTED` KULLANILMAZ — `agent_fsm` onu ARM'a çevirir (30 Ağu olayı) |
| **G2-K10** | **ARM yetkisi: SwD → `arm`+`takeoff:H` atomik**, üç kapılı | 30 Ağu olayının kökü arm'ın **örtük** olmasıydı. Armlı bekleme penceresi yok; yetki tek, etiketli, kapılı bir insan hareketinde. Ayrıntı aşağıda |
| **G2-K13** | 🔒 **Lider SEÇİLMEZ, VERİLİR: ylp00 (id 1) — ve Görev 2'de her zaman SLOT 0 (ortada)** | Operatör kararı, 4 Eylül. Lider kilidi ilk seçimi nihai yapıyordu ama o seçimin ylp00'a düşmesi TESADÜFTÜ (`min(effective)` + 8 sn tam kadro; evre kayması **25 sn** ölçüldü). Artık kimlik dışarıdan veriliyor ve liderin değişebildiği **dört yol** da kapalı. ⚠️ **Sabit LİDERLİK sistem geneli** (Görev 1 dahil — `SURU_LIDER_KILIDI` zaten görevden bağımsızdı, bu yalnız kimliği belirli kılıyor). **SLOT 0 kuralı ise yalnız Görev 2**; Görev 1'in Macar ataması 4 Eylül akşamı uçtu, dokunulmadı. Ayrıntı ve bedel: **KARAR-17** |
| **G2-K9** | **Aralık YKİ'den, GÖREV ÖNCESİ** (SSH ile canlı param) | Şartname aralığı sabit veriyor, görev içinde değişmiyor. Bugünkü yol (env + restart) saha gününde dakikalar alır. Mesh'e dokunmaz, **canlı komut yolu açmaz** |

### ⚠️ G2-K6'nın kabul edilen bedeli

Otomatik iniş kalkınca **kumanda kaybında sürü süresiz asılı kalır.**
Kaçınma çalışmaya devam eder, ama **pil izleme üç uçakta da KAPALI**
(`BAT1_SOURCE` disabled · `BATARYA_KRITIK_V=0.0` · YKİ'de `PIL_GOSTER=false`)
— yani yazılım tarafında hiçbir otomatik koruma yok.

> **Süreyi pilotlar tutar; çıkış yolu kill-switch pilotlarıdır.** Bilerek böyle.

### ✅ G2-K10 — ARM yetkisi: **seçenek (a)** (operatör, 30 Ağustos 2026)

Şartname arm'dan hiç söz etmiyor; seçim bizimdi. 30 Ağustos olayının kökü
**arm'ın örtük gerçekleşmesiydi** — çözüm arm'ı gizlemek değil, **açıkça
tasarlamak**.

**Karar: SwD tek harekette `arm` + `takeoff:H`, üç kapıyla.**

| # | Kapı | Nerede zorlanıyor |
|---|---|---|
| 1 | **SwA açık** | `deadman_pressed` — `_on_control_command` geçersiz pakette `takeoff`'u zaten düşürüyor |
| 2 | **Gaz merkezde** | `command_valid` (B18 kapısı) |
| 3 | **Görev YKİ'den başlatılmış** | `mission_state == 8`; `test_hazir_atla` **kabul edilmiyor** |

Reddedilen (b) — YKİ armlar, SwD kaldırır: uçakları **pervaneleri dönerken**
belirsiz süre bekletiyordu.

> 🔴 **Üçüncü kapı `test_hazir_atla` ile AÇILMAZ.** O bayrak FSM'i
> `mission_fsm` olmadan READY'ye ulaştırmak için var; ARM yetkisi de
> verseydi 30 Ağustos'un aynısını "test" adı altında tekrarlardık.
> **Bedeli kabul edildi:** madde 27+28 bitene kadar SwD sürüyü armlayamaz.
> Kritik yolun sırası (`25 → 27 → 28`) tam bu yüzden.

> 🔴 **SwD artık görevi BAŞLATMIYOR.** `joystick_interpreter`'daki
> `_call_trigger_mission(1)` kaldırıldı — kalsaydı SwD önce görevi başlatır,
> sonra kalkış isterdi; **üçüncü kapı kendi kendini açardı.**

---

## 4. PLAN — kalan iş

**Bitti:** Aşama A (kod, 10 madde) · Aşama B (donanım, 5 madde) ·
Aşama C (yerde ölçüm, 16-18 + 22-23). Ayrıntı §7.

**Kalan üç aşama:**

### 🎛 AŞAMA D — uçuştan önce kapatılacaklar

| # | İş | Öncelik | Durum |
|---|---|---|---|
| **24** | **`mode_manager` LANDING gerçekten indirsin** | 🔴 | ✅ **GERÇEK KOŞULDA DOĞRULANDI** — armlı uçağı SwD-aşağı anında indirdi (§7.13) |
| **25** | **Kumandadan kalkış** (B2) + `MOD_KALKIS_IRTIFA` | 🔴 | 🔧 **kod yazıldı, uçakta doğrulanmadı** (G2-K10) |
| **26** | **SwC debounce** — önce ÖLÇ, sonra eşik | 🟠 | ✅ **KAPANDI** — 1300 ms, yeni kumandayla ölçüldü (§7.12) |
| **27** | **`mission_fsm` aç** (ADIM 6) | 🟠 | ✅ **KAPANDI ve UÇAKTA DOĞRULANDI** — üçünde de SEMI_AUTONOMOUS (§7.13) |
| **28** | **Görev başlatma — üç uçağa birden** | 🟠 | ✅ **KAPANDI ve UÇAKTA DOĞRULANDI** — mesh yayılımı, ~1 sn (§7.13) |
| **29** | **YKİ aralık alanı** (SSH ile canlı param) | 🟡 | 🔧 **canlı param kapısı yazıldı** (§7.10) · taşıma yolu (betik mi YKİ alanı mı) **operatör kararı** |
| **30** | **Kumanda kaybında deadman düşmeli** | 🔴 | ✅ **KAPANDI** — yeni alıcıda doğrulandı (§7.12) |
| **17b** | **Eksen işaretleri — yeni kumanda** | 🔴 | ✅ **ÖLÇÜLDÜ, kod güncellendi** (§7.12) |

> 🚦 **KAPI: 24 ve 25 bitmeden UÇUŞ YOK.**
> İkisi de birim testle kilitlendi (256 test); **ikisi de yerde doğrulanacak.**
> 25'in yer doğrulaması 27+28'i beklemez — mission_state konusuna elle 8
> basmak yeter (§3 G2-K10).

**Kritik yol:**

```
24 -> 25 -> 27 -> 28 -> 31
inis   kalkis  mission_fsm  YKI BASLAT  ilk ucus
```

Sıra tesadüf değil: **iptal yolu olmadan `mod` ile test yapılmaz.**
26 ✅ bitti. 29 kritik yolu tutmuyor. 🔴 **30 artık P0 ve kritik yolda:**
kumanda kaybında sürü durmuyor, son komutla uçmaya devam ediyor.

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

*(P0 kalmadı. **B20 kapandı** — kumanda değiştirilerek: yeni alıcı i-BUS'ta
failsafe uyguluyor, CH5 düşüyor ve kalıcı kalıyor (§7.12). B2 ve B19 de
kapandı, ikisi uçakta doğrulama bekliyor.)*

### 🟠 P1

**Madde 29 — ÇÖZÜLDÜ (31 Ağu, kod bitti; uçakta YOK).** Operatör: *"görev 2 yi
başlatmadan önce bize dronelar kalktıktan sonra kaç m açılsın diye sorsun...
ayrıca kaç m irtifa istediğimizi de sorsun."*

Yukarıdaki (a)/(b) seçeneklerinin ikisi de **seçilmedi**; üçüncü bir yol çıktı:

**(c) Değerler `BAŞLAT` paketinin KENDİ İÇİNDE mesh'ten gider.** Ne SSH ne betik.
`_GOREV_FMT` rezervinden iki alan yendi — `aralik_dm` (uint8, 0,1 m, tavan
25,5 m) + `irtifa_dm` (uint16) — paket **hâlâ 16 bayt**, firmware değişmedi.
Neden (b)'den iyi: G2-K9'un lafzını da tutuyor (değer YKİ'de girilir) ama
backend'e SSH yeteneği eklemiyor. Neden (a)'dan iyi: `ROS_LOCALHOST_ONLY=1`
yüzünden YKİ'nin ROS servisleri uçaklardan zaten görünmüyor; mesh Wi-Fi'ye de
bağımlı değil ve **üç uçağa tek pakette** gider.

Zincir: YKİ formu → `parameters_json` → backend → `/swarm/public/mission/g2_ayar`
(mandallı) **→ BAŞLAT Bool'undan ÖNCE** → base ESP → mesh → `esp32_bridge`
→ `mode_manager` (irtifa + aralık) ve `joystick` (aralık).
Sınır denetimi **uçakta**: aralık 4–25,5 m · irtifa 3–30 m
(`canli_param.g2_ayar_dogrula`). Boş bırakmak geçerli: o alan için uçak kendi
varsayılanını korur.

🔴 **HAVADAYKEN UYGULANMAZ — iki ayrı kapı.** `mode_manager` `ctx.kalkis_tamam`
ile, `joystick` `_kalkis_istendi` ile reddeder. İkisi de gerekli: aralık uçuşta
ctx'e mode_manager'ın kendi alanından değil, formasyon değişikliğinde joystick
komutundan giriyor — tek kapı kâğıt üzerinde kalırdı.

⚠️ **Varsayılan aralık 7 m mi 9 m mi — KARAR-14 açık.** Operatör 7 dedi, aynı
günün ölçümü (KARAR-13) 9 diyor. Şu an kodda **7**; formasyon geçişli uçuşta
kutuya `9` yazmak yeterli.

**B6 · İvme rampası — ✅ YAZILDI (31 Ağu), uçakta YOK.**
`mode_context.compute_centroid_delta` artık çubuğu doğrudan hıza çevirmiyor;
hız `MOD_IVME=1,30 m/s²` (yatay) ve `1,00 m/s²` (dikey) ile rampalanıyor.
2,0 m/s'e ~1,54 sn'de çıkılıyor, çubuk merkeze dönünce aynı rampayla iniliyor.

🔴 `manual_kinematics.swarm_movement_step` **olduğu gibi kullanılamadı**:
heading ile döndürmüyor, pitch'i doğrudan KUZEY sayıyor. `mode_manager` gövde
çerçevesinde çalışıyor (çubuk ileri = sürünün BAKTIĞI yön); körlemesine
değiştirmek "ileri"nin anlamını kuzeye çevirirdi — sessiz ve tehlikeli.
Bu yüzden ivme sınırı **mevcut yola** eklendi, `slew` tek kaynaktan alındı.
`test_ivme_rampasi.py` ikisini birden kilitliyor (gövde çerçevesi testleri dâhil).

İvme eğim tavanıyla tutarlı: `a = g·tan(15°)/2 = 1,31` → 1,30 seçildi.
`ucus_ayarlari.py` bu tutarlılığı artık gerçekten denetliyor — denetim
yazılmıştı ama liste adı yanlıştı (`hatalar` ≠ `hata`) ve koşul hiç
sağlanmadığı için **NameError görünmemişti**; 31 Ağu düzeltildi.

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
| B5 | `formation/target`'ta iki üretici | ~~`_on_formation_out`'a `source_module` süzgeci~~ 🔴 **4 Eylül'de KALDIRILDI:** tek-yayıncı gelince süzgeç takipçileri tarifsiz bıraktı (lider bastı, mesh'e çıkmadı, formasyonlar kurulamadı — uçuşta ölçüldü). İki-üretici riskini artık tek-yayıncı + lider kapısı çözüyor; ic_dis_kopru'nun `formation/target` köprüsü de aynı sebeple kaldırıldı |
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
| B19 | `COMPLETED` terminal, çıkışı yoktu → **ikinci kalkış için konteyner restart** gerekiyordu (görev başına 3 hakkımız var) | COMPLETED → IDLE: **SwD iniş konumundan çıkmış** + **hepsi disarm**. Dönüşte uçuş defteri sıfırlanıyor (`kalkis_tamam` mandalı dâhil — temizlenmezse ikinci denemede yayın kapısı uçaklar YERDEYKEN açık sayılırdı) |
| B2 | Kumandadan kalkış YOK (G6 ihlali): `mode_manager` TAKEOFF'a giriyor ama komut üretmiyordu | madde 25 — `arm`+`takeoff:H` **doğrudan px4_bridge'e**, G2-K10'un üç kapısı, `MOD_KALKIS_IRTIFA` eklendi. Kod yazıldı, doğrulama bekliyor |

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

**Kalkış yolu (G2-K10 — üç kapı, madde 25):**

```
SwD yukari  ->  SwA acik? + gaz merkezde? + gorev YKI'den baslatildi mi?
            ->  mode_manager PREFLIGHT -> TAKEOFF
            ->  /swarm/agent/droneN/commands:  "arm"  sonra  "takeoff:H"
                (kapi acilana kadar 1 Hz TEKRAR)
            ->  px4_bridge: OFFBOARD -> ARM -> yatay CAPA donduruldu
            ->  TIRMANIS DIKEY  (formasyon SUSTURULDU)
            ->  hepsi 0.8 x H'yi gecince  ->  READY (centroid TAZELENIR)
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
| `mode_manager/tek_yayinci.py` | **Kim tarif basar** (lider) + **`lider_onde()`: lider slot 0'a** (G2-K13). Testli |
| `swarm_core/consensus/election.py` | **Sabit lider** kapısı (sistem geneli) — `sabit_lider=0` iken eski davranış birebir |
| `mode_manager/canli_param.py` | **Görev öncesi canlı ayar kapısı** — neyin değişebileceği. Testli |
| `mode_manager/swc_debounce.py` | **SwC debounce** — saha ölçümü ve 500 ms'nin gerekçesi burada. Testli |
| `src/gcs/kumanda_olc.py` | Kumanda ölçüm aracı — terminalden |
| **`src/gcs/kumanda_web.py`** | **Kumanda ölçüm arayüzü — tarayıcıdan.** Canlı kanallar + madde 17/26/30 panelleri; sonuçlar uçakta saklanır |
| `mode_manager/joystick_interpreter_node.py` | RC → `SwarmControlCommand` |
| `mode_manager/mode_context.py` | Kalkış kapısı, centroid/heading tohumlama |
| `mode_manager/mode_transitions.py` | FSM geçiş kuralları |
| `mission_fsm/mission_transitions.py` | **Görev 2'de PREFLIGHT → SEMI_AUTONOMOUS** (kalkış atlanır — madde 27) |
| `mode_manager/mode_manager_node.py` | Düğüm: abonelik, yayın, **kalkış ve iniş komutu** |
| `swarm_core/formation_control/manual_kinematics.py` | `dairesel_ortalama_deg`, eğim matematiği |
| `src/gcs/ucus_ayarlari.py` | **Bütün MOD_* tavanları — başka yerde elle yazılmaz** |
| `deploy/rpi/baslat.sh` | Düğüm başlatma, remap, `TEK-URETICI` kuralı |

**Uçakta açık düğümler için:** `/ws/suru_dugumleri` →
`origin consensus fsm formasyon ca mod` (üçünde) + `joystick` (yalnız ylp00).
🔧 **Madde 27 dağıtılınca `gorevfsm` de eklenecek** (üçünde).
Bayrak dosyası `/ws/mod_test` üçünde de takılı.

**Test:**

```bash
PYTHONPATH=src/swarm_state_machine:src/swarm_core \
  python3 -m unittest discover -s src/swarm_state_machine/test
```

---

## 7. Arşiv — saha ölçümleri ve kapanmış kusurlar

### 7.14 🟢 KUMANDADAN ÜÇ UÇAKLI KALKIŞ/İNİŞ UÇTU — 31 Ağustos 2026, 15:52

**Aşama D'nin son doğrulanmamış halkası kapandı.** Pervaneli, üç uçak,
tek müdahale yok. Uçuş 122 sn; 20 sn'si 5 m'de asılı.

| Ölçüm | 30 Ağustos (başarısız) | 31 Ağustos 15:52 |
|---|---|---|
| Kalkan uçak | 1 / 3 | **3 / 3** (0,24 sn içinde ARM) |
| En dar uçak arası | **0,36 m** | **6,70 m** (20 sn boyunca sabit) |
| Gerçek roll / pitch tepe | 19,5° / **−27,4°** | **3,3° / 5,3°** |
| Mod kavgası (AUTO.LAND↔POSCTL) | 6 geçiş | **0** |
| "Pilot took over using sticks" | 13 kez | **0** |
| Sürüye giden dikey komut | **−1,00** (2 m/s alçalma) | **+0,00** |
| İniş | 89 sn, kavgalı | **17 sn**, temiz |

Aynı uçuşta doğrulanan dört düzeltme: **madde 24** (pilot kapısı,
TUZAKLAR §3.16) · **tek atış serisi** (mesh'te kaybolan kalkış) ·
**sarmal düzeltmesi** (§3.17) · **dikey yetki mandalı** (§3.18).

🔴 **Dikey mandalın kanıtı kontrollü:** ham gaz kanalı (ch3) uçuşun
tamamında **1000 (dipte)** ölçüldü — dünkü arıza koşulu birebir
tekrarlandı — ama sürüye giden değer 0,00 kaldı. Şanslı kaçış değil.

**B19 çıkışı da doğrulandı:** üçü de `COMPLETED → IDLE → PREFLIGHT`'e
döndü (0,14 sn içinde), konteyner yeniden başlatmaya gerek kalmadan.

---

### 7.19 🔴 MANEVRA MODU — irtifa datumu + iki saha olayı (1 Eylül 2026)

**① Manevraya geçince üç uçak da ~1,7 m alçaldı — BİZİM HATA, DÜZELTİLDİ.**

`px4_bridge.py:838` zemin ofsetini **tüm** setpoint'lere uyguluyordu:
```python
target_z = self._takeoff_baslangic_z + float(sp.z)
```
Bu kural **guided goto** için doğru (2 Ağustos dersi: YKİ "8 m" derken kalkış
zeminini kasteder), **formasyon/manevra** için yanlış — mode_manager centroid'i
uçakların o anki konumundan tohumluyor, yani **mutlak NED** gönderiyor.

Ölçüm (ylp02): `sp.z = −6,97` + zemin `1,68` → PX4'e giden hedef **−5,29**.
Komut edilen irtifa 6,72 → 5,74 → **5,29 m**, uçaklar takip etti.

🔴 **Neden aylarca görünmedi:** hareket modunda maske hız modunda (`0x09C7`),
PX4 konum alanını **hiç kullanmıyor**. Hata oradaydı ama ölüydü. Manevra
maskeyi konuma çevirince gizli hata gerçekleşti.

**Düzeltme:** ofset yalnız `not sp.heading_valid` iken uygulanıyor —
`heading_valid` formasyon/manevrada her zaman true (`formation_node:1072`),
guided goto'da false. Yeni bayrak gerekmedi.
Testler: `test_manevra_irtifa_datumu.py` (ölçülen sayılarla aritmetik dâhil).

🔴 **UÇAKTA DOĞRULANMADI** — sonraki uçuşların hiçbiri manevraya ulaşmadı.

**② ylp02 saha dışına düştü — SEBEP BİLİNMİYOR.**

Alçalmanın ardından PX4 `Failsafe activated` verdi ve **ALTCTL**'e düştü
(konum kestirimi geçersiz → PX4'ün geri düşüş modu). ALTCTL'de yatay konum
tutma **yoktur**; uçak sürüklendi ve saha dışına düştü (kırık yok).

Elenenler — hepsi ölçüldü:
* RC kanalları **sabit**, rssi 41, 15 Hz → kimse switch'e dokunmadı, link kopmadı
* setpoint zinciri **50 Hz** akıyordu → OFFBOARD'ı yazılım bırakmadı
* kaçınma **hiç girmedi** (`avoid=0`, `yatay_tut=0`)
* Here4 konnektörü **elle sarsıldı** — pusula 10 Hz sabit, kopma 0, fix düşüşü 0

`px4_bridge` modu geri zorlamadı (*"land REDDEDILDI — pilot kumandada mod=2"*)
— 22 Ağustos'ta konan pilot-devralma kapısı **doğru çalıştı**.

PX4 ulog kapalı (`CLAUDE.md`: Pixhawk'ta log açma, RAM sınırı), o yüzden
failsafe gerekçesi okunamıyor. **Açık madde.**

**③ ylp00 kalkışta kendini yere bıraktı — YAZILIM DEĞİL.**

```
Takeoff detected → 5,6 sn → Attitude failure (roll) → Failsafe activated
```
**İkinci denemede birebir tekrarladı.** Uçak fiziksel olarak yattı.
Kill switch 168 sn SONRA, uçak zaten yerde ve disarm'ken basıldı — sebep değil.
Motor kalkışında pil **15,29 → 14,72 V** çöktü (0,57 V, 3,68 V/hücre; pil %58).

### 7.18 🔴 SÜRÜ HAREKETİ ÇALIŞMIYORDU — `deadman_timeout_s` mesh'te 0 (1 Eylül 2026)

**Belirti (operatör):** *"formasyon oluşturup ileri hareketi verdiğimde
sadece lider drone hareket ediyordu."*

**Ölçüm** (31 Ağu uçuşu, t=209513-209537, çubuk ±0,73'e kadar):

| | yol aldığı mesafe |
|---|---|
| ylp00 (pilot uçağı) | **2,82 m** |
| ylp01 | 0,40 m — yerinde |
| ylp02 | 0,25 m — yerinde |

**Zincir:**

1. `mode_context.deadman_timed_out()` → `elapsed > deadman_timeout_s`
2. `esp32_bridge._isle_komut` mesh paketinden `SwarmControlCommand` kurarken
   **bu alanı doldurmuyor** (mesh'te taşınmıyor) → komşulara **0.0** gidiyor
3. 0 ile koşul **her zaman doğru** → `command_active` **hep False**
4. `mode_transitions._from_ready` MOVEMENT döndürmüyor → uçak **READY'de kalıyor**
5. READY `compute_hold_command` yayınlıyor: merkez **sabit**, `max_speed 0.0`

Ölçülen kanıt: ylp01'e giden `FormationCommand`'in merkezi tüm uçuş boyunca
**(+6.32, −1.43)**'te dondu, `hiz=0.00`. Durum geçişleri de birebir gösteriyor:
ylp00 `READY → MOVEMENT`, ylp01 **`READY → LANDING`** (MOVEMENT hiç yok).

🔴 **Neden gözden kaçtı:** formasyon *değişimi* çalışıyordu, çünkü o
`command_active`'e bağlı değil. Arıza "yarım çalışıyor" gibi göründü.

**Düzeltme:** alıcı kendi politikasını koyuyor —
`deadman_timeout_s` 0 geldiğinde `mode_manager` `deadman_zaman_asimi_s`
(0,5 sn) kullanıyor. Taşıma katmanında **düzeltilmedi**, çünkü esp32_bridge'in
kendi kuralı *"taşıma katmanı politika üretmemeli"* (`requested_spacing_m`'de
birebir aynı gerekçe).

**0,5 sn ölçümle seçildi:** mesh komut aralığında en kötü boşluk **0,203 sn**
(200 örnek, std 0,05) — 2,5 kat pay. Fail-safe yön korundu: yedek değer sonlu,
link koparsa sürü yine durur.

**Sonraki uçuşta doğrulanacak:** ylp01 ve ylp02'nin logunda
`READY -> MOVEMENT` satırı görünmeli.

### 7.17 Kaçınma: dikey ayrım kurulana kadar YAKLAŞMA YOK (1 Eylül 2026)

**Operatör önerisi:** *"Kaçınma devreye girerse drone yatayda ilerlemeyi
durduracak ve farklı bir irtifaya geçip öyle yatayda harekete devam edecek."*

`ca_core`'un kendi ölçüm tablosu (23 Ağustos benzetimi) bunu doğruluyor:

| yaklaşma | saf dikey | saf yatay |
|---|---|---|
| 1,0 m/s | 2,63 m | 2,27 m |
| 2,5 m/s | 1,01 m | 2,02 m |
| 4,0 m/s | **0,47 m** | 1,53 m |

Kodun kendi yorumu: *"Sebep AYAR DEĞİL GEOMETRİ: dikey kaçışın
kazanabileceği en fazla mesafe katman kadardır (3 m) ve onu kurmak **2-3
saniye alır**."* Yani dikey strateji yanlış değil, **zaman bulamıyor.**
Yaklaşmayı durdurmak o zamanı veriyor.

**Uygulama:** `ca_core._dikey_bekleme_projeksiyonu` — mevcut
`_safety_projection`'ın genelleştirilmişi (o zaten "r_min içinde komşuya
yaklaşan bileşeni sıfırla" diyor ve sahada kanıtlanmış). Aynı işlem d0
yarıçapında, **yalnız dikey ayrımı henüz kurulmamış** komşular için.
`KACINMA_DIKEY_BEKLE = 0,8` → 2,4 m ayrım sağlanınca yatay serbest.

🔴 **Tüm yatay hız sıfırlanmıyor, yalnız komşuya doğru olan bileşen.** Sürü
çubukla 2 m/s ilerlerken bir uçağı tamamen dondurmak onu formasyondan 2-6 m
geride bırakır ve ÜÇÜNCÜ uçakla yeni bir çatışma açar. Morf hâlinde
(kafa kafaya yaklaşma) hızın tamamı zaten o bileşendir — operatörün tarif
ettiği davranış birebir oluşur.

Yatay son çare (`hard` = 2,5 m itme) tutmadan **sonra** ekleniyor, yani
mekanizma kaçmayı hiçbir zaman engellemiyor; yalnızca yaklaşmayı kesiyor.

**Sahada ölçülecek:** `ca.log` → `yatay_tut=` sayacı. Sıfır değilse
mekanizma çalışmıştır.

🔴 **İRTİFA KISITI:** dikey inişin tabanı `altitude_gate_m + 1 = 4,0 m`.
5 m'de aşağı rütbeli uçak yalnız 1 m inebilir, 2,4 m'lik ayrımı kuramaz ve
yatay tutma o çift için hiç bırakılmaz. **Kalkış irtifası ≥ 8 m olmalı.**

### 7.16 🔴 SAHA OLAYI — formasyon morfunda 1,65 m YAKINLAŞMA (1 Eylül 2026)

**Uçuş:** kumandadan formasyon geçişi. Kalkış 5 m → VrB açıldı (SwC okbaşında)
→ SwC V'ye → iniş. 109 s havada.

**Olay:** VrB açılıp ilk formasyon istendiğinde ylp01 ile ylp02 **7,36 m'den
1,65 m'ye** düştü. Üç uçağın kaydından ayrı ayrı ölçüldü: 1,53 · 1,56 · 1,65 m
(ylp01 ve ylp02 kendi telemetrileriyle de doğruladı — telemetri hatası değil).

**Kayıttan çıkan sayılar:**

| | |
|---|---|
| duruştan tepe hıza | 2,71 m/s'e **1,2 saniyede** |
| tepe kapanma hızı | **4,13 m/s** |
| kaçınma giriş eşiği | 4,00 m |
| frenleme mesafesi | 4,13² / (2·3,58) = **2,38 m** |
| kalması gereken | 4,00 − 2,38 = **1,62 m** |
| **ÖLÇÜLEN en yakın** | **1,65 m** — 3 cm fark |

🔴 **KAÇINMA BOZUK DEĞİL.** Kitabına göre çalıştı, frenleme mesafesi teoriyle
3 cm uyuştu. 4 m'lik eşik **4 m/s'lik bir kapanma için tasarlanmamış.**

**İkinci olay — kaçınma kilitlendi.** V'ye geçişte mesafeler 3,65 m'ye indi;
kaçınma ylp01'de 666, ylp02'de 633 kare (~30-35 sn) **açık kaldı ve
kapanmadı**, V formasyonu hiç kurulamadı. `ucus_ayarlari.py` bunu uçuştan önce
uyarmıştı: 7 m aralıkta çıkış eşiği (6,5 m) nominal aralığın yalnız 0,5 m
altında — bir kez açılınca kapanacak yer yok.

**Üçüncü bulgu — yaw dağınıklığı.** Kalkış anında sistem kendisi uyardı:
`UCAKLARIN YAW'LARI DAGINIK (tutarlilik 0.34 < 0.90)`. Formasyon yönü burun
yönlerinin ortalamasından türetiliyor; 218,7° çıktı, oysa uçaklar yere ~164°
doğrultusunda dizilmişti. Yuvalar **55° dönük** kuruldu ve iki uçak yuvalarına
giderken birbirinin önünden geçmek zorunda kaldı. **Yolların kesişmesinin
sebebi bu; hız ise kesişmeyi tehlikeli yaptı.** İkisi ayrı sorun.

**Yapılan (operatör kararı: "bayağı yavaş yapsın formasyonları"):**
`MOD_MORF_HIZ_MPS = 0,6` — formasyon **değişimi** sırasındaki slot hızı seyir
hızından (2,0) **ayrıldı.** 0,6 m/s'de kapanma 1,2 m/s, frenleme 0,20 m,
kaçınmaya **3,80 m** kalır.

Kilit `_publish_formation_command` içinde, yani **yayın sınırında** — B15
kalkış kapısıyla aynı gerekçe: ileride eklenen her formasyon yolu
kendiliğinden yavaşlar. Mantık `morf_kilidi.py`'de (saf modül, `rc_eksen` ·
`swd_mandal` · `formasyon_kilidi` kardeşi), testleri `test_morf_kilidi.py`.

🔴 **Kilit çubukla DÜŞER.** Sürü merkezi çubukla ötelenirken slot hızı 0,6'da
kalırsa formasyon merkezin **gerisinde** kalır — `formation_node`'da bir kez
yaşanmış hata ("merkez 3.00 iken komut 1.05, bacak başına 5 → 20 m açık").
Aynı tuzağı morf kilidiyle yeniden açmıyoruz. Süre tavanı 25 sn.

**Hâlâ açık:** ① yaw hizalaması — şimdilik dizilim disiplini, kalıcı çözüm
formasyon yönünü yaw ortalaması yerine yer geometrisinden türetmek
② `formation_control.max_speed_mps` uçakta **3.0**, `MOD_HIZ` ise 2.0 —
komuttan gelen değer kazanıyor ama iki sayı hâlâ ayrı yerlerde duruyor (§9).

### 7.15 VrB = formasyon ANA ANAHTARI (G2-K12) — 31 Ağustos 2026

**Sorun:** SwC'nin kapalı konumu yok; üç konumu da bir formasyon. Kumanda
açılır açılmaz salterin durduğu yer **formasyon talebi** olarak okunuyordu.
Ölçüldü: kimse dokunmadan `requested_formation` 0→3 oldu ve
`formation_change_requested` mesh'e çıktı.

**Operatör kararı (tam ifadesiyle):**
* VrB KAPALI iken hiçbir formasyon aktif olmaz
* İlk kalkışta VrB kapalıysa, açılana kadar formasyon oluşmaz
* VrB açılınca SwC'nin gösterdiği formasyon aktif olur
* Havada formasyon aktifken VrB kapatılırsa uçaklar **olduğu yerde** kalır

**Kanal ölçümü:** VrB → **ch10 → `aux6`**, tam aralık PWM 1000..2000,
pürüzsüz analog; aynı yakalamada diğer 13 kanalın genliği 0 (çapraz
karışma yok). Eşik **aux 800 (~PWM 1900)**.

🔴 **Seviye değil GEÇİŞ:** VrB detentsiz, tam çevrili unutulabilir
(ölçüme başlarken ch10 zaten 2000'di). Bu yüzden `KAPALI → AÇIK` geçişi
ayrı durum (`YENI_ACILDI`) ve formasyon o anda **aktif ediliyor** —
`SwcDebounce` duran salter için hiç tetiklemediğinden, ayrılmasaydı kilit
açıldığında formasyon **hiç oluşmazdı**.

**Mesh engeli de kapatıldı:** `esp32_bridge`/`packet_parser`
`formasyon=0 + değişim bayrağı`nı "eski sürüm gönderici" sayıp
**düşürüyordu** (30 Temmuz koruması). VrB kapatınca bu istek meşru;
düşürülseydi pilot uçağı formasyondan çıkar, komşular eski formasyonda
kalır — **sürü bölünürdü**. Ayırt edici ölçümle bulundu: eski gönderici
**iki alanı da** boş bırakır, bilinçli istekte aralık dolu gelir (uçuş
kaydında `requested_formation=0` iken bile `spacing=7.0`).

Kod: `mode_manager/formasyon_kilidi.py` (saf mantık + testler).

---


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

~~**Deadman yine de düşüyor** — alıcının varsayılan failsafe'i bütün anahtar
kanallarını 1500'e aldığı için.~~

> 🔴 **BU YORUM YANLIŞ ÇIKTI — 31 Ağustos 2026, §7.11.**
>
> O ölçümde alıcı muhtemelen **hiç link kurmamıştı** (açılış varsayılanı
> 1500), yani ölçülen şey failsafe değildi. Kontrollü tekrarda gerçek
> davranış çıktı: **alıcı link kaybında son çerçeveyi TUTUYOR** ve
> **SwA 2000'de kalıyor, deadman DÜŞMÜYOR.**
>
> O zaman *"bu bir varsayılan, garanti değil"* diye yazılan uyarı doğruydu —
> ama korkulan şey zaten gerçekleşmiş durumdaydı. **B20 / madde 30.**

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

### 7.7 Madde 25 — kumandadan kalkış yazılırken kapanan üç kusur

Üçü de **kod okunurken** bulundu, hiçbiri uçuş gerektirmedi.

| | Neydi | Sonucu olurdu |
|---|---|---|
| a | `test_hazir_atla` + kalkış kapısı, **2 m'de READY** veriyordu | `_dispatch_hold` kapının açıldığı 2 m'yi hedef gösteren tarif yayınlar → **tırmanış 8 m yerine 2 m'de durur**, hiçbir hata görünmeden. Kalkışı biz sürüyorsak ölçüt artık **hedef irtifa** |
| b | Centroid **kapıda (2 m)** tohumlanıp bir daha tazelenmiyordu | READY 6,4 m'de geliyor; ilk `_dispatch_hold` `center_z`'yi hâlâ 2 m yayınlardı → sürü **kontrol pilota geçer geçmez 2 m'ye geri dalardı.** Aynısı x/y için: tırmanışta sürüklenme varsa yanal sıçrama. → READY girişinde centroid **tazeleniyor** |
| c | `MOD_GAZ_MERKEZ_PAY` **yanlış düğüme** veriliyordu (`baslat.sh`) | Parametre `mode_manager`'a geçiliyordu ama kapıyı `joystick_interpreter` uyguluyor. Bugün ikisi de 0.2 olduğu için görünmüyordu; **ayar değiştirilseydi hiçbir etkisi olmazdı.** Sahibine taşındı |

Ayrıca TAKEOFF sırasında `formasyon_sustur` artık **basılı**: mode_manager o
durumda zaten hiçbir şey yayınlamıyor, ama `formation_node`'un elinde önceki
denemeden kalma bir tarif varsa `px4_bridge` taze setpoint'i kalkış hedefinin
**önüne alır** (`px4_bridge.py:705`) ve tırmanış yerine yatay kaçış olurdu —
madde 24'teki (d) kusurunun aynı sınıfı. (CLAUDE.md §9: *"irtifadan önce
yatay hareket YOK"*.)

---

### 7.8 Madde 27 — `mission_fsm` açılırken bulunan üç engel

Üçü de **kod okunurken** bulundu. `gorevfsm` bayrağı bugün olduğu gibi
açılsaydı üçü birden vururdu ve **hiçbiri hata vermezdi.**

| | Neydi | Sonucu olurdu |
|---|---|---|
| a | `mission_fsm` **kendi durumunu** `/swarm/public/drone{ben}/status`'tan bekliyordu | 🔴 **G0 madde 18'in birebir aynısı.** O konunun yayıncısı 0 (`ic_dis_kopru`: *"drone{N}/status BİLEREK hariç"*) → `all_agents_seen` asla true olmaz → **PREFLIGHT hiç geçilmez** → `mission_state` 8 olmaz → sürü kumandadan **kalkamaz.** Düzeltme aynı: kendi durumu `internal`'dan (`agent_id` parametresi eklendi ve `baslat.sh`'te geçiliyor) |
| b | PREFLIGHT → **SYNCHRONIZED_TAKEOFF** girişi `EVENT_MISSION_STARTED` yayınlıyor | `agent_fsm` onu **ARM'a çeviriyor** → *"YKİ'de BAŞLAT'a basmak sürüyü armlar"* = **30 Ağustos saha olayının tekrarı**, bu sefer başka düğümden |
| c | SYNCHRONIZED_TAKEOFF → SEMI_AUTONOMOUS çıkışı `all_agents_in_swarm()` | Görev 2'de kalkışı `mode_manager` sürüyor ve `agent_fsm` **IDLE'da kalıyor** → o koşul hiç gerçekleşmez → **sessiz kilitlenme** |

**b ve c'nin tek çözümü aynı:** Görev 2'de `PREFLIGHT` → **doğrudan**
`SEMI_AUTONOMOUS`. Şartname zaten böyle diyor — senaryo madde 4 (*YKİ: yarı
otonom moda geç*) ile madde 5 (*kumandadan kalkış*) **ayrı adımlar**.
Görev 1'in yolu değişmedi (`mission_type` ile ayrıştı, regresyon testi var).

> ✅ **Yan kazanç:** PREFLIGHT denetimleri (sağlık + GPS fix + origin + home)
> yerinde kaldı. Yani G2-K10'un üçüncü kapısı artık sadece *"operatör butona
> bastı"* değil, **"operatör bastı VE üç uçak da preflight'ı geçti"** demek.

### 7.9 Madde 28 — YKİ BAŞLAT ve kaldırılan servis çağrısı

**YKİ paneli Görev 2 için YANLIŞ bilgi gösteriyordu.** `MissionPanel` şunu
yazıyordu: *"Görev 2 kumandadan başlatılır (SwD şalteri)"* ve BAŞLAT butonunu
gizliyordu. Şartname senaryosu tam tersi: madde 4 **hakemin komutuyla yarı
otonom moda geçiş**, madde 5 **kumandadan kalkış** — ayrı adımlar (G2-K8).
Buton açıldı; altına "BAŞLAT kalkış vermez" notu kondu.

**`_call_trigger_mission` komple kaldırıldı — ölçülen sebep:**

`baslat.sh:117` `ROS_LOCALHOST_ONLY=1` ile koşuyor. `joystick_interpreter`'ın
`TriggerMission` istemcisi bu yüzden **yalnız kendi uçağındaki** `mission_fsm`'e
ulaşır ve o düğüm **sadece ylp00'da** koşuyor. Yani SwD ile iniş verildiğinde:

```
ylp00 mission_fsm  ->  LANDING -> MISSION_COMPLETE
ylp01 / ylp02      ->  SEMI_AUTONOMOUS'ta KALIR
```

İkinci denemede (görev başına **üç hak**) ylp00'ın üçüncü kapısı kapalı,
diğer ikisininki açık olurdu: SwD'ye basınca **iki uçak kalkar, biri yerde
kalırdı.** Sessiz ve pahalı.

İniş zaten `mission_fsm`'e ihtiyaç duymuyor: SwD → mesh → **üç** `mode_manager`
→ her biri kendi `px4_bridge`'ine `land` (madde 24). Dağıtık yol simetrik,
servis yolu değildi.

> Yan sonuç — **istenen davranış:** iniş artık `mission_fsm`'i
> SEMI_AUTONOMOUS'tan çıkarmıyor. B19 ile `mode_manager` COMPLETED → IDLE →
> PREFLIGHT'a döner ve **ikinci deneme için YKİ'ye tekrar basmak gerekmez.**

### 7.10 Madde 29 — `ros2 param set` SESSİZ BİR NO-OP'tu

G2-K9 *"aralık YKİ'den, SSH ile canlı param"* diyor. Ölçüldü: o yol bugün
**çalışmıyordu ve çalışmadığını söylemiyordu.**

`mode_manager` ve `joystick_interpreter`'da **parametre geri çağrısı yoktu**;
ikisi de bütün parametreleri `__init__`'te `self._*`'a kopyalıyor. Yani:

```
ros2 param set /joystick_interpreter_node default_spacing_m 5.0
  -> "Set parameter successful"          <- YALAN
  -> dugum 7.0 kullanmaya DEVAM eder
```

Saha günü karşılığı: hakem *"aralık 5 m"* der, YKİ'de değer değişir,
**sürü 7 m'de uçar ve kimse anlamaz.**

**Kapı `canli_param.py`'de** — `rc_eksen.py`/`swd_mandal.py` ile aynı gerekçe:
düğümler bu laptopta import edilemiyor, kapı ise birim testle kilitlenmek
zorunda. Yanlış açılması *"uçuş sırasında B15'i ya da G2-K10'un üçüncü
kapısını canlı canlı devre dışı bırakmak"* demek.

| Canlı | Neden |
|---|---|
| `default_spacing_m` | Şartname aralığı görev öncesi veriyor (G2-K9) |
| `kalkis_irtifa_m` | Hakem irtifayı söylüyor — *"Örn: 15m"* (§5.2.2). `mode_manager`'da; joystick'te karşılığı yok |

**Reddedilenler:** `kalkis_esik_m` · `test_hazir_atla` · `agent_id(s)` ·
`deadman_threshold` · `gaz_merkez_pay` … `px4_bridge`'in kuralı birebir
kopyalandı (CLAUDE.md §8). Red sebebi `ros2 param set` çıktısında görünüyor
ve **ne yapılabileceğini** de yazıyor.

> 🔴 **Aralığın gerçek kaynağı `joystick_interpreter`.** `mode_manager`'ınki
> yalnızca yedek: her çerçevede `cmd.requested_spacing_m` ylp00'dan gidiyor ve
> `mode_manager` onu *">0 ise kabul et"* kuralıyla alıyor. Yani ylp00'daki bu
> tek sayı mesh üzerinden (`talep_spacing_dm`) **üçünü birden** sürüyor.
> Düğümde iki alan var (`_default_spacing_m` ve `_requested_spacing_m`) ve
> **ikisi de yazılmalı** — yalnız ilki güncellenseydi ayar kabul edilmiş
> görünür ama sürüye hiç ulaşmazdı.

**Kalan:** taşıma yolu. İki seçenek §5'te.

### 7.11 SAHA ÖLÇÜMÜ — 30 Ağustos 2026 gecesi, ylp00, FS-i6X #2

Yalnız ylp00 açıktı; ikinci alıcı orada olduğu için iki madde de tek uçakla
ölçüldü. **Uçuş yok, pervaneler sökük, kill pilotu hazır.**
Araç: `src/gcs/kumanda_olc.py` (uçakta, konteyner içinde koşar).

#### madde 26 — SwC geçiş süresi → debounce = 500 ms ✅

İki bağımsız kayıt, 32,5 Hz örnekleme, **11 geçiş**:

```
 92 · 94 · 154 · 185 · 185 · 216 · 246 · 246 · 339 · 339 · 342 ms
 ortanca 216                                        EN UZUN 342
```

🔴 **İkinci kayıtta anahtar BİLEREK YAVAŞ çevrildi ve tavan değişmedi**
(339 → 342 ms). Sebebi mekanik: SwC **detentli**, orta konumda durulmadıkça
kendini geçiriyor. Yani geçiş süresi elin hızına değil **anahtarın
mekaniğine** bağlı — bu, yazılım debounce'unu korktuğumuzdan çok daha
güvenilir yapıyor. (Dokümandaki *"200-400 ms"* tahmini de doğrulanmış oldu.)

**Eşik 500 ms** = ölçülen tavana %46 pay. Bu eşikle 342 ms'lik en uzun geçiş
bile tetiklemiyor; kasıtlı V seçimi 500 ms gecikiyor — fark edilmez. Zaten
500 ms'den uzun süre ortada duruluyorsa bu **V seçildi** demektir: orta bir
detent, orada kazara dinlenilmiyor.

Kod `mode_manager/swc_debounce.py` (saf, 12 test — **ölçülen 11 geçişin
gerçek süreleri testin içinde**). Tek kaynak `MOD_SWC_DEBOUNCE_MS`;
`ucus_ayarlari` denetimi eşik 342 ms'nin altına düşerse **HATA** veriyor.

#### madde 30 — 🔴 ALICI SON KONUMU TUTUYOR, deadman DÜŞMÜYOR

**İlk ölçüm yanıltıcıydı ve düzeltildi.** Kumanda kapalıyken bütün anahtar
kanalları 1500 okundu ve bu "failsafe" sanıldı. Değildi: alıcı o sırada
**hiç link kurmamıştı** (açılış varsayılanı). §7.3'ün *"alıcı bütün anahtar
kanallarını 1500'e alıyor"* yorumu da aynı sebeple şüpheli — o da muhtemelen
link kurulmamış hâlin ölçümüydü.

**Gerçek davranış, DÖRT bağımsız teyitle:**

| SwA konumu | Kumanda | CH5 sonucu |
|---|---|---|
| 2000 | kapalı (operatör teyitli) | **2000 — tutuldu** |
| 1000 | kapalı | **1000 — tutuldu** |
| 2000 → kapatıldı | 120 sn izlendi | **2000, hiç düşmedi** |
| 2000 | kapalı | **2000 — tutuldu** |

🔴 **Alıcı, link kaybında i-BUS akışında SON ÇERÇEVEYİ TUTUYOR.** CH5'e
failsafe kaydı yapıldı (operatör, kumanda menüsünden) ama **i-BUS çıkışına
yansımıyor.** Muhtemel sebep: bazı FlySky alıcılarında failsafe **PWM servo
çıkışlarına** uygulanıyor, i-BUS akışı son bilinen değerleri yayınlamayı
sürdürüyor. Doğrulanmadı — ama gözlenen davranış bununla birebir uyumlu.

**Sonucu ağır:** deadman düşmezse `joystick_interpreter` emniyeti açık görür,
`command_valid` her çerçevede tazelenir, `mode_manager` MOVEMENT'ta kalır ve
centroid'i entegre etmeye devam eder. Yani **kumanda kaybında sürü HOLD'a
geçmez — çubuk nerede kaldıysa o komutla uçmaya devam eder.** Çubuklar
ortadaysa yerinde durur; ileri itilmişken koptuysa sabit hızla uzaklaşır.

> 🔴 **MADDE 30 KAPANMADAN UÇULMAZ.** Bu, G2-K6'nın kabul ettiği "süresiz
> asılı kalma" bedelinden farklı ve çok daha kötü: orada sürü *durur*,
> burada *gider*.

**i-BUS'ta link-kaybı bayrağı YOK.** 14 kanalın tamamı canlı ve ölü hâlde
karşılaştırıldı; CH9–CH14 de aynen tutuluyor:

```
kumanda AÇIK  : 1502 1500 1001 1500 1000 1000 1000 1000  2000 2000 1500 1500 1500 1500
kumanda KAPALI: 1502 1500 1001 1500 2000 1000 1000 1000  2000 2000 1500 1500 1500 1500
```

**Ama kullanılabilir tek ayırıcı var: TİTREŞİM.**

| | Canlı (eller çekik) | Ölü |
|---|---|---|
| CH3 | 2 ayrık değer (1001–1002) | tek değer |
| **CH9** | **2 ayrık değer (1999–2000)** | tek değer |
| **CH10** | **2 ayrık değer (1999–2000)** | tek değer |
| diğer 11 kanal | donuk | donuk |

🔴 Kritik nokta: **CH9 ve CH10 kimsenin dokunmadığı kanallar** ve yine de
titriyorlar — bu RF/alıcı gürültüsü, pilotun çubuk oynatmasına bağlı değil.
Yani "pilot hareketsizse dedektör yanılır" sorunu yok. *(Bu fikir önce
8 kanala bakılarak reddedilmişti; 14 kanal ölçümü dayanağı değiştirdi.)*

**Hata yönü doğru tarafa düşüyor:** yanlış pozitif → deadman düşer → sürü
HOLD (G2-K6 otomatik inişi zaten kaldırdı, sürü asılı kalır ve pilot fark
eder). Bugünkü hâlin yanlış negatifi ise **uçup gitmek**.

**Yapılacaklar — sırayla:**
1. **ÖLÇ:** 60 sn, kumanda açık, eller tamamen çekik. Ölçüt: 14 kanalın
   bit-birebir aynı kaldığı **en uzun kesintisiz süre**. Eşik onun belirgin
   üstüne konur (madde 26'da yapılanın aynısı).
2. **YAZ:** `rc_ibus_kopru` → "N sn hiçbir kanal 1 µs oynamadı" = BAYAT;
   `joystick_interpreter` bayat çerçevede emniyeti düşürsün.
3. **DONANIM yolunu da kovala:** yeniden bind, failsafe'i PWM çıkışında
   test, ya da farklı alıcı. Yazılım dedektörü bunun yerine geçmez,
   **ikinci hat** olur.

#### ⚠️ SwA'nın fiziksel yönü belirsiz — DEĞERE bak, "yukarı/aşağı"ya değil

Ölçüm sırasında operatörün "SwA yukarıda" dediği konum tekrar tekrar
**CH5 = 1000** (emniyet KİLİTLİ) verdi. Anahtar sağlam: ayrı bir testte
1000 ↔ 2000 arasında temiz geçiş yaptı. Sorun adlandırmada.

**Kodun ölçütü değerdir:** `AUX_SAFETY_THRESH = 300`, yani `CH5 > 1650`
→ emniyet **AÇIK**. Saha brifinginde "yukarı = açık" diye ezberletmek
tehlikeli; doğrusu **"CH5 2000 okuyan konum açıktır"** ve uçuş öncesi
`kumanda_olc.py --izle` ile bir kez GÖRÜLMELİ.

### 7.12 SAHA ÖLÇÜMÜ — 31 Ağustos 2026, **YENİ KUMANDA**

Eski kumandanın alıcısı link kaybında i-BUS'ta son çerçeveyi tutuyordu ve
deadman düşmüyordu (§7.11, B20 — uçuş engeliydi). Operatör **yeni bir kumanda
bind etti**; bütün kumandaya özgü ölçümler tekrarlandı.

Araç: **`src/gcs/kumanda_web.py`** — uçakta koşan, tarayıcıdan kullanılan
ölçüm arayüzü. *(Aynı ölçümler önce terminalden denendi ve üst üste boşa
gitti: `grep` boru ucunda blok tamponluyor, "şimdi başla" talimatı operatöre
kayıt bittikten sonra ulaşıyordu. Sebep teknik değil koordinasyondu; arayüz
o sorunu tamamen ortadan kaldırdı.)*

#### madde 17 — eksen işaretleri: 🔴 YAW DEĞİŞTİ

| Eksen | Yön | Ölçülen | Sonuç |
|---|---|---|---|
| PITCH | ileri | **2000** | `TERS_PITCH = False` |
| ROLL | sağa | **1998** | `TERS_ROLL = False` |
| **YAW** | **sağa** | **2000** | **`TERS_YAW = False`** ← eskiden `True` |
| GAZ | yukarı | **2000** (dip 1000) | ✅ çevrilmiyor |

**Dördü de üst uç → hiçbir kanal çevrilmiyor.**

🔴 Önceki kumandada yaw sağa **1014** (alt uç) veriyordu ve kod onu
**çeviriyordu**. Sabit güncellenmeseydi pilot sağa çevirir, **sürü sola
dönerdi** — ve hiçbir yerde hata görünmezdi. `rc_eksen.py` ile
`test_rc_eksen.py` yeni ölçüme göre güncellendi; eski ölçüm tarihçe olarak
dosyada duruyor.

#### madde 30 — ✅ FAILSAFE ÇALIŞIYOR, B20 KAPANDI

```
sonuc: CALISIYOR   ·   CH5 = 1000   ·   kalici_s = 6
```

Kumanda kapatılınca CH5 **1000'e düştü ve 6 saniye boyunca orada kaldı.**
Yani yeni alıcı failsafe'i **i-BUS çıkışına uyguluyor** — eskisi uygulamıyordu.

Kumanda kaybında artık: `aux1 = -1000` < eşik 300 → **deadman DÜŞER** →
`joystick_interpreter` emniyet-kapalı dalına girer → çubuklar sıfırlanır →
`mode_manager` **HOLD**'a geçer. G2-K6'nın kabul ettiği "süresiz asılı kalma"
davranışı; sürü *durur*, gitmez.

> Bu, §7.11'de önerilen yazılım dedektörünü (donuk çerçeve) **gereksiz
> kılıyor.** Donanım doğru davranıyorsa ±1 LSB titreşime dayanan bir deadman
> yazmak gereksiz risk olurdu. Fikir arşivde kalsın, uygulanmıyor.

#### madde 26 — SwC debounce: 500 → **1300 ms** (muhafazakâr)

İki kayıt alındı ve **birbiriyle çelişiyorlar:**

```
kayıt 1:  852 · 364 · 215 · 214 · 200 · 158 ms    → tavan 852
kayıt 2:  321 · 162 · 120 · 100 ·  92       ms    → tavan 321
```

🔴 Tavanlar arasında **2,6 kat** fark var. 852 ms'nin gerçek bir geçiş mi
yoksa ortada **duraklamış bir el** mi olduğu **çözülmedi**. Ayrıca web
arayüzü 50 ms'de bir örnekliyor (akış 32,5 Hz), bu yüzden birkaç geçiş
**0 ms** okundu — çözünürlüğün altında kaldılar.

**Eşik 1300 ms yapıldı — bilerek muhafazakâr.** Hata yönü asimetrik:

| Eşik | Sonuç |
|---|---|
| **düşük** | gerçek geçiş eşiği aşar → sahte V morfu → en dar an 4,95 m, kaçınma girişi 4,0 m → **çarpışma −20×N** |
| **yüksek** | hakem "V'ye geç" der, sürü 1,3 sn sonra başlar — görev temposunda fark edilmez |

Bilmediğimiz için güvenli tarafta duruluyor. Eski kumandanın 342 ms'lik
tavanı ve kayıt 2'nin 321'i tutarlıydı; 852 tek başına ayrık.

> ⚠️ **AÇIK MADDE:** çerçeve zaman damgalarından hesaplayan bir ölçüm
> (tarayıcı anketi değil) 852'nin duraklama olup olmadığını ayırt eder ve
> eşiği muhtemelen ~500 ms'ye indirir. Gerekli değil ama V seçimini
> hızlandırır.

### 7.13 SAHA GECESİ — 31 Ağustos 2026, üç uçak, DAĞITIM + YER DOĞRULAMASI

Aşama D'nin tamamı dağıtıldı ve **uçakta koşturuldu.** Uçuş yok; pervaneler
sökük. 🔴 Kill switch **hiç aktif değildi** — bu, aşağıdaki (c) maddesinin
hem sebebi hem de beklenmedik kanıtı oldu.

#### a) 🔴 `home_set` MESH'TE TAŞINMIYORDU — Görev 2 hiç başlayamazdı

`mission_fsm` PREFLIGHT → SEMI_AUTONOMOUS için `all_agents_home_set()`
istiyor ve komşuların durumunu **mesh'ten** okuyor. Ölçüldü:

```
ylp01 KENDİ iç durumu :  home_set = true
ylp00'ın mesh kopyası :  home_set = false     ← kaybolan bilgi
```

Durum paketinde (16 bayt, REV C) `home_set` alanı **yoktu**; alıcı tarafta
hep `false` kalıyordu. Sonuç: **PREFLIGHT hiçbir zaman geçilemez, Görev 2
hiç başlayamaz, hiçbir yerde hata görünmez.** G0 madde 18'in birebir aynı
sınıfı — ve yine ancak *denendiğinde* ortaya çıktı.

Düzeltme: `bayraklar2`'deki boş bitlerden biri (`DURUM2_BAYRAK_HOME_SET`).
**Paket 16 bayt kaldı**, firmware'e dokunulmadı, iki yönde de geriye dönük
uyumlu. `origin_synced` ve `kacinma_koru` da aynı şekilde eklenmişti.

#### b) 🔴 GÖREV BAŞLATMA TEK UÇAĞA ULAŞIYORDU — sürü bölündü

`TriggerMission` bir ROS **servisi** ve `baslat.sh` `ROS_LOCALHOST_ONLY=1`
ile koşuyor. Tetik ylp00'a verildi; ölçülen sonuç:

```
ylp00 : mission_state=8  →  SwD ile ARMLANDI, motorlar döndü
ylp01 : mission_state=1  →  "SwD KALKIS istendi ama YETKI YOK"
ylp02 : mission_state=1  →  "SwD KALKIS istendi ama YETKI YOK"
```

**Sürü bölündü.** G2-K10'un üçüncü kapısı eksik kalkışı önledi — doğru
davranış, ve kapının kendisinin kanıtı — ama görev de başlayamadı.

**Çözüm (G2-K11, operatör kararı): mesh yayılımı.** Durum paketine ikinci
bir bit (`DURUM2_BAYRAK_GOREV_YARI_OTONOM`); `esp32_bridge` komşunun bitini
görünce `/swarm/public/mission/suru_yari_otonom` basıyor; `mission_fsm`
bunu **emir değil TETİK** olarak alıyor ve **kendi preflight'ını** koşuyor.

Ölçülen yayılım — tek tetikten üçüne:

```
ylp00  trigger  →  SEMI_AUTONOMOUS     +0,20 sn
ylp01  YAYILIM  →  SEMI_AUTONOMOUS     +1,04 sn
ylp02  YAYILIM  →  SEMI_AUTONOMOUS     +1,00 sn
```

⚠️ **`EVENT_MISSION_STARTED` KULLANILMADI** — o olay mesh'ten zaten geçiyor
ama `agent_fsm` onu **ARM'a çeviriyor** (30 Ağustos olayının tetiği). Görev
başlatmak armlamak değildir; ayrı kanal şart.

#### c) ✅ MADDE 24 GERÇEK KOŞULDA DOĞRULANDI (kazara)

Kill switch aktif olmadığı için ylp00 **gerçekten armlandı** ve
`takeoff:8.0` hedefiyle pervanesiz kaldı — yani **30 Ağustos senaryosunun
birebir aynısı.** Fark:

```
30 Ağustos : pilot HİÇBİR TUŞLA durduramadı; olay agent_fsm'in
             42-95 sn'lik zaman aşımıyla bitti
31 Ağustos : SwD-aşağı  →  land (1 Hz)  →  AUTO.LAND  →  DISARM   ANINDA
```

`mode_manager -> land (tekrar)` 1 Hz akıyor, `px4_bridge: MOD(AUTO.LAND)
KABUL edildi`. Bu doğrulamayı planlamamıştık; ama kanıtlanması gereken tam
olarak buydu ve kanıtlandı.

#### d) Kuru test uçuşu DURDURDU — ve haklıydı

İlk dizilimde uçaklar **0,98 m** aralıktaydı (eşik 4,0 m). Hepsi kendi
yerinde dikey kalksa havada da o mesafede kalırlardı; asılı durma testi
istemeden bir kaçınma testine dönerdi. Uçaklar açıldıktan sonra
**4,53 m** ile `SONUÇ: GEÇTİ`. *(Pay 0,53 m — kaçınma girişi 4,0 m ve takip
hatası ~1 m olduğu için 7 m önerildi.)*

Kullanılan senaryo: **`--senaryo asili --dronelar 1,2,3 --irtifa 8`.** Yeni
senaryo yazmaya gerek yok — `plan_kur_asili` zaten N uçağa genelleştirilmiş
ve "her uçağın hedefi KENDİ ölçülen x,y'si, yatayda hiçbir komut yok"
diyor; kalkış = iniş noktası, tam Görev 2'nin ilk uçuş profili.

#### e) 🔴 SwA kutbu: bu kumandada AÇIK = AŞAĞI

Ölçüldü: SwA **yukarı = 1000 = KİLİTLİ**, **aşağı = 2000 = AÇIK**.
Kumandada reverse denendi, o kanala işlemedi. **Değiştirilmedi ve
değiştirilmemeli** — çünkü korunması gereken değişmez şu:

```
KİLİTLİ konum = 1000     ve     failsafe = 1000
```

Kodda ters çevirmek failsafe'in 1000'ini "açık" yapardı; yani **kumanda
kaybında deadman düşmezdi.** Bedeli ergonomik: **sürü kumandasında emniyet
AŞAĞI, kill kumandasında tersi.** 🔴 Pilot brifingine yazılacak.

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
