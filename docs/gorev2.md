# GÖREV 2 — Yarı Otonom Sürü Kontrolü

**Son güncelleme:** 30 Ağustos 2026, 14:52 — 🔴 **SAHA OLAYI: SwD sürüyü ARM etti** (bkz. §2); `EVENT_MISSION_STARTED` kaldırıldı; mesh bütçesi ölçüldü (~57 çerçeve/s, TIP_KOMUT 16,5); deadman ölçüldü: alıcı susmuyor, kanalları MERKEZE alıyor (önceki bulgu yanlıştı); B18 doğrulandı; kalkış kapısına ARM şartı eklendi (açık alan ölçümü açığı gösterdi); G0 madde 16 + 18 geçti; kapının HİÇ AÇILAMAYACAĞI bir kusur bulundu ve kapatıldı; iki gerçek kusur sahada yakalandı (QoS kırığı + yayın hızı); Aşama B bitti (kod dağıtıldı + üç konteyner recreate); i-BUS zinciri uçtan uca çalıştı (130 Hz, 0 checksum hatası); işaret yönleri ölçüldü → **pitch ve yaw TERSTİ**, düzeltildi; **B18** gaz kapısı eklendi

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

### Port kesinleşti: `/dev/ttyAMA2` (30 Ağustos)

`SURU_RC_PORT` env'i duruyor ama artık varsayılanı doğru: `baslat.sh` ve
`run_drone.sh` `/dev/ttyAMA2` kullanıyor. USB-TTL seçeneği **elendi** —
bağlantı doğrudan Pi UART'ına yapıldı, `ttyUSB` numarası kayması derdi yok.

| | |
|---|---|
| Sinyal | i-BUS Servo → **fiziksel pin 29 (GPIO5)** = `uart2` RX |
| Overlay | `dtoverlay=uart2-pi5` → `/dev/ttyAMA2` · ⏳ **henüz yazılmadı** |
| Seviye | **~3 V ölçüldü** → doğrudan bağlanır ✅ |
| Diğer UART'lar | `ttyAMA0` Pixhawk (pin 8/10) · `ttyAMA4` ESP32 (pin 32/33) |

`pi_hazirla.sh` artık `uart2-pi5`'i de yazıyor (yeni Pi'ler için); **mevcut
üç uçakta elle eklenmeli.** Tam tablo `cihazlar.md`, filo dağılımı
`RPI_ESITLEME.md` **A23**.


### 🔬 SAHA ÖLÇÜMÜ — 30 Ağustos 2026, ylp00, FS-i6X #2

i-BUS zinciri **uçtan uca çalıştı.** Düğüm dağıtımı gerekmedi; port doğrudan
okundu (`/dev/ttyAMA2`, 115200 8N1).

```
2597 + 3246 + 5195 cerceve  ·  130 Hz sabit
checksum hatasi 0  ·  atilan bayt 0     <- sinyal seviyesi marjinal DEGIL
```

**Kanal haritası — hepsi doğrulandı:**

| Kanal | Ölçülen | Sonuç |
|---|---|---|
| CH1 roll · CH2 pitch · CH3 gaz · CH4 yaw | 1000–2000 | ✅ |
| **CH5 SwA** emniyet | 1000 / **2000 = AÇIK** | ✅ eşik 300 doğru tarafta |
| CH6 SwB mod | 2 konum (+ tutulunca sahte orta) | ✅ orta `aux=0` → HAREKET, belirsizlik yok |
| **CH7 SwC** formasyon | **1000 / 1500 / 2000** | ✅ **3 konum** → okbaşı / **V** / çizgi |
| CH8 SwD kalkış/iniş | 1000 / 2000 | ✅ |
| CH9–14 | sabit | kullanılmıyor |

🔴 **SwC'nin ortası tam 1500** — yani `aux3 = 0`. **B4 düzeltmesi tam oraya
oturuyor.** Anahtar 2 konumlu çıksaydı şartnamenin *"V formasyonuna geç"*
direktifi kumandadan **karşılanamazdı**.

**İşaret yönleri — iki tanesi TERSTİ:**

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
> belirsizdi ve ben roll'u da ters sanmıştım. Tek yönlü tekrar yapıldı;
> sıra varsayımıyla koda dokunulsaydı **doğru olan roll bozulacaktı.**

🔴 **Deadman — ÖNCEKİ BULGU YANLIŞTI, 30 Ağustos 14:30'da düzeltildi.**

Burada *"kumanda kapanınca i-BUS susuyor, deadman'i sessizlik taşıyor"*
yazıyordu. **Yanlış.** İlk gözlemde 0 bayt okunmuştu ama o sırada alıcı
henüz beslenmiyordu/bind değildi — tek gözlemden mekanizma çıkarmak hataydı.
Kontrollü ölçüm:

```
kumanda ACIK  : [1502, 1500, 1500, 1500, 2000, 1000, 1000, 1000]
kumanda KAPALI: [1503, 1500, 1002, 1500, 1500, 1500, 1500, 1500]
                                         ^^^^  ^^^^  ^^^^  ^^^^
                                         SwA   SwB   SwC   SwD
cerceve akisi : 130 Hz, checksum_hata 0   -> ALICI SUSMUYOR
```

`RPI_ESITLEME` §5'in *"FS-iA6B susmuyor"* notu **doğruymuş**; ben onu
*"yalnız PWM çıkışları için"* diye yanlış yorumlamıştım.

**Deadman yine de düşüyor** — ama sessizlikle değil, alıcının **varsayılan
failsafe'i bütün anahtar kanallarını 1500'e (merkeze) aldığı için.**
`aux1 = (1500−1500)×2 = 0`, eşik 300 → emniyet **KİLİTLİ**. Ölçülen:

```
command_valid: false · deadman_pressed: false · throttle_cmd: 0.0
```

⚠️ **Bu bir VARSAYILAN, garanti değil.** FlySky alıcılarında *"son konumu tut"*
seçeneği de var; biri onu açarsa **SwA 2000'de kalır ve deadman DÜŞMEZ** —
sürü son çubuk komutunu süresiz sürdürür. Alıcı yakın zamanda bind edildi ve
10 kanal için menülere girildi, yani ayarın değişmiş olması uzak ihtimal değil.

*Bu yüzden madde 12'nin failsafe kaydı yapılmalı:* alıcının failsafe'i
**SwA = 1000 (kilitli)** olarak açıkça kaydedilirse kırılganlık kalkar.
🟠 P0 değil (ölçülen varsayılan güvenli), ama **uçuştan önce.**


### ✅ G0 madde 16 — 30 Ağustos 13:45, ylp00

**Kill pilotu izolasyonu — çubuk oynatmadan, yapısal kanıt.**
`ros2 node info /joystick_interpreter_node` abonelikleri:

```
/drone_1/rc/manual_control_KAPALI   <- olu konu, 0 yayinci
/drone_1/rc/suru                    <- SURU alicisi (rc_ibus_kopru)
/joy                                <- 0 yayinci (YKI joystick silinmisti)

/drone_1/mavros/rc/in  LISTEDE YOK
```

`px4_bridge` hâlâ `/drone_1/mavros/rc/in` dinliyor → **kill zinciri bozulmadı.**
İki zincir tam ayrık; kill pilotunun çubuğu sürü zincirine **ulaşamıyor.**

**Sahada yakalanan iki gerçek kusur:**

**D1 — `ic_dis_kopru` QoS kırığı.** `joystick_interpreter` `/swarm/internal/
control/command`'a **BEST_EFFORT** yayınlıyordu; `ic_dis_kopru` o konuyu
**RELIABLE** dinliyor. Eşleşmedi. Ölçülen:

```
/swarm/internal/control/command   46.6 Hz
/swarm/public/control/command     HICBIR SEY      <- kirik
```

Sonucu: **pilotun KENDİ uçağı çubuğa cevap vermezdi**, diğer ikisi mesh'ten
(esp32_bridge BEST_EFFORT, eşleşiyordu) alıp cevap verirdi. Havada teşhisi
çok zor. Kök neden `ic_dis_kopru:80`'deki *"bütün internal yayıncılar
RELIABLE (15 Ağustos'ta tarandı)"* varsayımı — o tarama sırasında bu düğüm
**hiç koşmamıştı.**

*Düzeltme:* yayıncı RELIABLE yapıldı (`INTERFACE_CONTRACT` §3.0.1: RELIABLE
yayıncı + BEST_EFFORT abone **uyumlu**), üç abone de çalışıyor.
Doğrulandı: `/swarm/public/control/command` = **62,8 Hz**.

**D2 — `rc_ibus_kopru` 16 Hz yayınlıyordu, 50 değil.** `read(256)` 4160 B/s'te
**61,5 ms** bloklar; yani yayın hızını `yayin_hz` değil **okuma yığını**
belirliyordu (130/8 = 16,2 Hz — ölçülen tam bu). Üstelik hız sınırlayıcı
yığının **en eski** çerçevesini yayınlıyordu.

*Düzeltme:* okuma 64 bayta indirildi + yığının **en taze** çerçevesi
yayınlanıyor → **32,5 Hz** ölçüldü. Kalan fark nicemleme (15,4 ms döngü,
20 ms sınır → her ikinci tur); tüketicilerin ikisi de 20 Hz olduğu için
sorun değil.

**Mesh için ölçüm:** `/swarm/internal/control/command` **62,8 Hz** akıyor ve
`esp32_bridge` hepsini UART'a yazıyor; firmware kapısı 20 Hz geçiriyor →
**%68 boşa.** Ertelenen `_on_control_out` limiti kararının sayısı bu.


### 🔴 G0 madde 18 — kapının HİÇ AÇILAMAYACAĞI kusur (30 Ağustos)

`mode_manager` üç `agent_id` için de `/swarm/public/drone{N}/status` dinliyordu
— **kendisi dahil.** Ama ölçüldü: o konunun **yayıncı sayısı 0**.

Sebep tasarım: `ic_dis_kopru` tablosu *"drone{N}/status BİLEREK hariç"* diyor;
uçağın kendi durumu kendi public konusuna köprülenmiyor, oraya yalnız
**mesh'ten komşuların** durumu düşüyor.

**Sonucu:** `all_agents_seen()` asla `True` olmuyordu → **kalkış kapısı (B15)
HİÇBİR ZAMAN açılamazdı** → `mode_manager` havada da hiçbir şey yayınlamazdı.
**Görev 2 komple ölü olurdu ve hiçbir yerde hata görünmezdi.**

*Düzeltme:* `formation_node`'un deseni (`formation_node.py:341`) —
kendi durumu `/swarm/agent/drone{ben}/telemetry`'den (px4_bridge, 10 Hz),
komşularınki mesh'ten. `agent_id` parametresi eklendi.

**Asıl ders sessizlikti.** Kapı neden kapalı olduğunu söylemiyordu. Artık
10 saniyede bir sebebini yazıyor ve bu kusuru ilk saniyede yakaladı:

```
t+0.06s  kalkis kapisi KAPALI — durumu HIC GELMEYEN ajan: [2, 3]
t+10s    kalkis kapisi KAPALI — esigin (2.0 m) altindaki ajanlar:
                                {1: -0.5, 2: 0.2, 3: 0.5}
```

🔴 **Yükseklikler paylaşılan origin'e göre, yere göre değil — ve bu ciddi.**
Açık alanda ölçülen: ylp00 **+1,7 m** · ylp01 −0,1 · ylp02 0,0 (üçü de YERDE).
ylp00 sırf **yerleşim** yüzünden 2,0 m eşiğin **%85'ini** tüketti. Bir uçak
origin'in 2,5 m üstüne konsaydı **kapı yerdeyken açık olurdu.**

*Çözüm:* kapıya **ARM ŞARTI** eklendi — disarm bir uçak havada olamaz, şart
irtifa referansından bağımsız. `armed` mesh'ten geçiyor
(`durum_paketle:581` → `esp32_bridge:1348`), komşular için de güvenilir.
Eşiği büyütmek çözüm değildi: ofset de büyüyebilir.

**Doğrulanan durum (üç uçak yerde, `mod` + `mod_test` açık):**

```
formasyon_sustur   20.0 Hz, data:false   <- dugum canli, tikliyor
formation/target   YAYIN YOK             <- kapi tutuyor ✅
setpoint/raw       YAYIN YOK             ✅
FSM                IDLE -> PREFLIGHT     <- B3 calisti, READY'ye GECMEDI
```

B3'ün `test_hazir_atla`'sı B15'i **baypas edemiyor** — birim testte kilitliydi,
sahada da doğrulandı.

---

## 3. Boşluklar — 18 madde · **1-9 + B17 kapandı**

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

**B16 · `mod` anahtarı `fsm`'e bağımlı değil.** ✅ *uygulandı — ama KAPI DEĞİL, UYARI*

Bu madde "`formasyon`'un eşi bir kapı konulmalı" diye yazılmıştı; gerekçe
*"`fsm` kapalıysa centroid `(0,0,0)`'da kalır"* idi. **Uygulamadan önce kod
okundu ve gerekçe çürüdü** (`PLAN.md` §8: *"'N'i 2 yap' türü maddeleri
uygulamadan önce KODU OKU"*):

- **B15** centroid'i uçakların kendi konumundan tohumluyor → `SwarmState` şart değil
- `SwarmState.formation_heading_deg` **zaten hep 0.0** → bkz. B17
- `formation_reached` / `formation_stable` ctx'e yazılıyor ama **hiçbir yerde
  okunmuyor** (ölçüldü)

Yani `fsm` kapalıyken `mode_manager` bugün işlevsel bir şey **kaybetmiyor**.
Çalışan bir yapılandırmayı `HATA` ile durdurmak yanlış olurdu. Sessiz de
bırakılmadı: kanıtlanmış yığından (`origin consensus fsm formasyon ca`) sapma
açılış logunda **UYARI** olarak görünüyor.

**B17 · `SwarmState.formation_heading_deg` HİÇ HESAPLANMIYOR.** ✅ *KAPANDI — hem kökten hem kapıda*

`swarm_fsm/swarm_context.py:73` alanı tanımlıyordu, `swarm_fsm_node.py:696`
yayınlıyordu, **arada atama yapan tek satır yoktu** → kalıcı olarak `0.0`.
Sonucu: kalkış kapısı açıldığında `mode_manager` heading'i **0° = KUZEY**
sanıyor, pilot gerçek bir formasyon seçmişse sürü **kimsenin komut vermediği
bir dönüş** yapıyordu — 7 m aralıkta kanatlar ~10 m.

**İki yerden birden kapatıldı:**

1. **Kök neden** — `swarm_fsm` artık heading'i **hesaplıyor**
   (`AgentStatusCache.heading_deg` eklendi, `compute_heading()` yazıldı,
   `compute_centroid()` ile birlikte çağrılıyor). YKİ arayüzü de artık
   gerçek değer görüyor.
2. **Kapıda** — `mode_manager` kalkış kapısı açılırken heading'i
   **uçakların kendi ölçülen yaw'ından** tohumluyor (centroid tohumlamasının
   eşi). Böylece `swarm_fsm` kapalı olsa bile (B16) doğru çalışır.

**Ortak matematik tek yerde:** `manual_kinematics.dairesel_ortalama_deg`.
🔴 **Aritmetik ortalama olamazdı:** 359/0/1'in ortalaması **0'dır, 120 değil** —
kuzeye bakan bir sürüyü güneye çevirirdi ve hiçbir yerde hata vermezdi.
Fonksiyon ayrıca **tutarlılık (R)** döndürüyor; uçaklar aynı yöne bakmıyorsa
hem düğüm hem kuru test **yüksek sesle uyarıyor**.

> ⚠️ **Birim testi ilk koşuda gerçek bir kusur yakaladı:** `atan2` kuzey için
> çok küçük **negatif** açı döndürebiliyor ve `-1e-15 % 360.0` kayan noktada
> **tam 360.0** veriyor — yani sözleşme `[0,360)` iken çıktı `360.0` oluyor ve
> "kuzey" 0 yerine 360 diye okunuyordu. Eşik karşılaştırması yapan her
> tüketici sessizce yanılırdı. Kapatıldı, gerekçe koda yazıldı.

Geometriden değil **ölçülen yaw'dan** türetiliyor, çünkü çizgi formasyonunun
geometrisi **iki yönlü belirsiz** (hangi uç ön?), ölçülen yaw değil.

`--senaryo manevra` de güncellendi: artık **aynı fonksiyonu** çağırıyor, yani
kuru testin modellediği şey uçulacak şeyin ta kendisi.


**B18 · GAZ ÇUBUĞU ORTALANMIYOR — emniyet açılınca sürü anında alçalırdı.** ✅ *SAHADA DOĞRULANDI 30 Ağu 14:25*

```
SwA ACIK, gaz DIPTE (CH3 1001):
  command_valid: false        <- kapi tutuyor
  deadman_pressed: true       <- SwA dogru okundu
  pitch/roll/throttle_cmd: 0.0
  [WARN] GAZ MERKEZDE DEGIL — suru BEKLIYOR

gaz ORTALANDI (CH3 1501):
  [INFO] gaz merkezlendi — suru komutlari ARTIK GECERLI
  command_valid: true
  throttle_cmd: 0.002         <- merkez
```
Ayrıca **D1 düzeltmesi de doğrulandı:** `/swarm/public/control/command`
**63,3 Hz** — yani `ic_dis_kopru` yerel köprüsü artık çalışıyor ve pilotun
kendi uçağı da komutu alıyor.


30 Ağustos saha ölçümü: gaz çubuğunun **dinlenme konumu PWM 1001** (dipte).
Zincir `1001 → gaz_normalize 0.001 → throttle_cmd = 0.001×2−1 = −1.0`, ve
`movement_mode` bunu `v_up = −1.0 × 2 m/s` yapıyor.

**Yani pilot SwA'yı gaz dipteyken açsa sürü anında 2 m/s ile alçalırdı.**
`mode_manager`'da bunu tutan hiçbir kapı yoktu. Uçuş A'nın ilk saniyesinde
ısırırdı.

FlySky Mod 2'de gaz çubuğu **kendiliğinden ortalanmaz** — bırakıldığı yerde
kalır ve doğal olarak dipte durur. Nötr nokta **orta çubuk** (1500 → 0.0).

*Çözüm (operatör kararı: yordam değil kod kapısı):* emniyet açıldıktan sonra
gaz bir kez merkeze gelene kadar `command_valid = False` → `mode_manager`
HOLD'da bekler. Mandal SwA her kapandığında **sıfırlanır**, yani pilot her
emniyet açışında gazı ortalamak zorunda. Eşik `MOD_GAZ_MERKEZ_PAY` (0,2),
tek kaynak `ucus_ayarlari`.

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

**B8 · RTL durumu bir tik yaşıyor.** ✅ *uygulandı — planlanandan FARKLI çözümle*

`_on_state_entry(RTL)` → `EVENT_RTL_TRIGGERED` yayınlıyor → düğüm
`/swarm/internal/events/system`'e hem **yazıyor hem abone**, yani **kendi
olayını** duyuyor → `land_requested=True` → anında LANDING.

Plan *"land kapısına RTL ekle"* diyordu. **Yanlış olurdu:** `CLAUDE.md`
*"iptal her zaman `land`"* diyor ve pilotun SwD ile verdiği iniş komutu RTL'i
**kesebilmek zorunda**. Kapıyı daraltmak o yolu da kapatırdı.

*Uygulanan:* kaynağı sustur — `_on_event` kendi olayını (`source_module ==
'mode_manager'`) **yok sayıyor**. İkinci kusur da giderildi: iki olay tipi de
hem `rtl` hem `land` isteği kuruyordu; artık RTL olayı → `rtl_requested`,
acil iniş olayı → `land_requested`. Land'in RTL'i kesebildiği ayrı bir
regresyon testiyle **kilitlendi**.

**B9 · YKİ JoystickPanel ikinci üretici VE şartname ihlali.** ✅ *KOMPLE SİLİNDİ*

Laptop `/swarm/internal/control/command`'a yayınlıyordu → base ESP `TIP_KOMUT`
olarak mesh'e basıyordu. Hem çift üretici hem §5.2 *"müdahale → görev
BAŞARISIZ"* riski.

Plan *"görev profilinde kilitle"* diyordu; **operatör kararı (30 Ağustos):
komple sil — o kısım simülasyon için yazılmıştı.** Silinen zincir:

```
frontend  JoystickPanel/ (4 dosya) · services/gamepad.ts
          App.tsx joystickVisible + app--joystick · App.css uc sutunlu duzen
          api.ts SWARM_CONTROL_MODE · SWARM_FORMATION
                 SwarmControlBody · swarmApi.control
arka uc   mission.py  SwarmControlBody + POST /api/swarm/control
          ros_bridge  publish_swarm_control + _control_pub + import
```

Sonuç: **YKİ `SwarmControlCommand`'ı mesh'e hiçbir yoldan basamıyor.**
`tsc` temiz, derleme 357,56 → **344,03 kB**. Geri gerekirse git'te.

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
| **1** | ✅ **B4** V formasyonu (SwC orta → `FORMATION_V`) + **B10** spacing parametresi | ~10 satır |
| **2** | ✅ **B7** `_handle_formation_change` → `_formation_offsets` güncellemesi | ~10 satır |
| **3** | ✅ 🔴 **B3 + B15 BİRLİKTE** — `test_hazir_atla` **ve** kalkış kapısı. **Ayrılamaz** | ~40 satır |
| **4** | ✅ **B17** — kapı değil **uyarı** oldu (gerekçe çürüdü, bkz. §3) | ~25 satır |
| **5** | ✅ **B5** `_on_formation_out`'a `source_module == 'mode_manager'` süzgeci | ~4 satır |
| **6** | ✅ **B8** (kök nedenden: kendi olayını yok say) + **G2-K6** HOLD otomatik inişi kaldırıldı | ~30 satır |
| **7** | ✅ **B9** — panel *kilitlenmedi*, **komple silindi** (operatör: simülasyon artığı) | −1.100 satır |
| **8** | ✅ **`rc_ibus_kopru`** + `baslat.sh` remap tekilleştirmesi + `run_drone.sh` koşullu `--device` | 391 satır |
| **9** | ✅ **`--senaryo manevra`** — zarf tabanlı kuru test + harita + B17 ön-uçuş kapısı | ~190 satır |
| **10** | ✅ **Denetim** — 227 test · `bash -n` · 99-krk · ölü import · **parametre kablolaması uçtan uca** | — |

> 🚦 **Kapı:** testler yeşil olmadan Aşama B'ye geçilmez.
>
> **AŞAMA A BİTTİ — 1-10 + B17 (30 Ağustos 03:01).** `mode_context` + `mode_transitions`
> **227 birim testi** bu laptopta geçiyor; YKİ `tsc` + derleme temiz. Düğüm katmanı
> (`mode_manager_node`, `joystick_interpreter_node`, `esp32_bridge`)
> yalnız **sözdizimi** doğrulandı — `rclpy`/`swarm_interfaces` konteynerde;
> gerçek doğrulama **G0'da** (madde 16-18).

### AŞAMA B — Donanım (ylp00, atölye)

| # | İş |
|---|---|
| **11** | ✅ **Gerilim ölçüldü: ~3 V** → 3,3 V mantık, seviye çevirici **gerekmiyor**. (Kumandadaki `IntV1 5,3 V` alıcının **beslemesi**, sinyal değil.) |
| **12** | ✅ bind ✅ **10 kanal modu** · 🟠 **failsafe SwA kaydı UÇUŞTAN ÖNCE** — deadman bugün alıcının VARSAYILAN merkeze-alma davranışına dayanıyor, garanti değil |
| **13** | ✅ **Kablolama yapıldı** — i-BUS Servo → jumper → **fiziksel pin 29 (GPIO5)** + GND. Port kesinleşti: **`/dev/ttyAMA2`**. ⏳ **Kalan tek satır:** `config.txt`'ye `dtoverlay=uart2-pi5` + **reboot** |
| **14** | ✅ **YAPILDI (30 Ağu 13:30)** — üçü de yeniden oluşturuldu. **A19 kapandı** (`ROS_LOCALHOST_ONLY=1` üçünde de), ylp00'a `--device /dev/ttyAMA2` geçti, konteyner içinden görünüyor. `docker inspect` yedekleri alındı |
| **15** | ✅ **YAPILDI** — `dagit.sh` 3/3, 6 paket, sürüm `193c224`; `baslat.sh` md5 üçünde de **depo ile AYNI**, 11 düğüm, `TEK-URETICI` aktif |

> 🚦 **Kapı:** `drone_bul.sh --durum` → md5 eşit, düğüm sayısı yerinde.
> Bayraklar: `origin consensus fsm formasyon ca mod` üç uçakta ·
> **`joystick` YALNIZ ylp00** · `/ws/gozlem` **takılı** ·
> 🔴 **`/ws/mod_test` takılı** (üç uçakta) — `mission_fsm` kapalıyken
> `mode_manager` FSM'ini READY'ye ulaştırır (B3). **Kalkış kapısını (B15)
> baypas ETMEZ.** Uçuştan önce silinip silinmeyeceği operatör kararı;
> `drone_bul.sh --durum` bayrağı listeliyor.

### AŞAMA C — G0 yerde, pervanesiz *(uçuş yok, en yüksek getirili adım)*

| # | Ölçülecek |
|---|---|
| **16** | ✅ **GEÇTİ.** Port 130 Hz / 0 hata · `/drone_1/rc/suru` **32,5 Hz** · 🔴 **kill pilotu izolasyonu YAPISAL olarak kanıtlandı** (aşağıda) |
| **17** | ✅ **ÖLÇÜLDÜ — pitch ve yaw TERSTİ, düzeltildi.** Tablo §2'de, testlerle kilitlendi (`test_rc_eksen.py`) |
| **18** | ✅ **GEÇTİ.** Kapı yerde tutuyor (hiçbir yayın yok) · B3 IDLE→PREFLIGHT ✓ · 🔴 **kapının hiç açılamayacağı kusur bulundu ve kapatıldı** (aşağıda) |
| **19** | MANEVRA'da **merkez sabitliği** (xy değişmemeli) + `formasyon_sustur` bayrağı |
| **20** | **Centroid sürüklenmesi**: üç uçağın `formation/target.center_*` farkı, 60 sn |
| **21** | **B6 kararı:** çubuk basamağında centroid hızı sıçrıyor mu? Sıçrıyorsa `swarm_movement_step` (ivme rampalı, yazılı ve testli) **uçuştan önce** devreye alınır — osilasyon cezası −10 |
| **22** | ✅ **ÖLÇÜLDÜ** — kumanda kapalı → SwA 2000→1500 → `deadman_pressed: false`. Alıcı susmuyor, merkeze alıyor (§2) |
| **23** | ✅ **ÖLÇÜLDÜ — ~57 çerçeve/s**, `TIP_KOMUT` katkısı **16,5** (§2). ⏳ lider HB + RTCM eksik, uçuş öncesi tekrar |

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
- **`--durum` bayrak listesi 30 Ağu'da düzeltildi** — `gozlem`, `yer_testi`,
  `origin` hiç görünmüyordu, oysa *"uçmadan önce `yer_testi`'ni kaldır"*
  kırmızı çizgi. Başka eskimiş liste var mı, bakılmadı.
- **Uçakların yerdeki yönü artık ÖNEMLİ** (B17 sonrası): formasyon
  burunların baktığı yöne göre kuruluyor. Uçakları aynı yöne diz;
  kuru test tutarlılık < 0,90 ise uyarıyor.
- **Centroid sürüklenmesi** — her uçağın `mode_manager`'ı centroid'i KENDİ
  tik'inde entegre ediyor. Ölçülüp gerekirse ölçülen sürü merkezine yavaş
  düzeltme eklenecek (`_on_swarm_state` bugün yalnız IDLE/PREFLIGHT/TAKEOFF/
  READY'de centroid'i tazeliyor, MOVEMENT'ta **hiç** tazelemiyor)
- **Mesh bütçesi** `TIP_KOMUT` ile birlikte (B13). **Ölçüldü (30 Ağu):**
  zincir `rc_ibus 50 Hz → joystick_interpreter ~80 Hz → esp32_bridge 80 Hz
  UART → firmware 50 ms kapısı → mesh'e 20 Hz`. Mesh **~53 → ~73 çerçeve/s
  (+%38)**; ESP-NOW yayın olduğu için tek gönderim iki uçağa birden gider.
  ⚠️ `_on_control_out`'ta **hiç hız limiti yok** → UART'a yazdığımızın **%75'i**
  ESP'de COBS+CRC çözülüp atılıyor. *Öneri (~8 satır):* `_on_control_out`'a
  40 ms (25 Hz) limit — firmware kapısını doyurur, UART yazımını 80 → 25'e
  indirir, **mesh yükünü değiştirmez**. 🟡 **Operatör kararı (30 Ağu):
  G0 madde 23 ölçümünden SONRA** — ölçmeden değiştirme.
- **Protokol yeterli:** `TIP_KOMUT` Görev 2'nin ihtiyacı olan her şeyi
  taşıyor (mod, 4 çubuk, kalkış/iniş/RTL/acil, deadman, formasyon+aralık).
  Paket **13 bayt dolu / 3 bayt boş**. `max_*` alanları bilerek taşınmıyor —
  her uçak kendi paramından alır. **Tek olası ileri ihtiyaç:** B2'nin kalkış
  irtifası; sıfır-mesh çözümü var (her uçağın kendi paramı, §5.2 görev öncesi
  YKİ ayarına izin veriyor), alternatifi boş 3 bayttan biri (~10 satır).
- **ACİL İNİŞ butonu Görev 2'de hâlâ gizli** (`App.tsx`:
  `selectedMissionId !== MISSION_ID.SEMI_AUTONOMOUS`). Gizlenme sebebi
  joystick panelinin o alanı kaplamasıydı; panel silindi, **sebep kalktı.**
  Görev 2'de gösterilsin mi — operatör kararı (şartname müdahaleyi yasaklıyor,
  ama güvenlik puanın önünde ve kill-switch pilotları asıl çıkış yolu)
- **Slot ataması Macar değil, kimlik sırasıyla** — çapraz yerleşimde kalır
  (KARAR-11 notu, ayrı P2)
