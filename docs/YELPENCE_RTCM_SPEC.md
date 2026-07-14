# YELPENÇE — RTCM Dağıtım Sistemi Teknik Spesifikasyonu

> **Sürüm: REV B** — bu doküman RTK Base'den üretilen RTCM3 düzeltme verisini,
> ESP-NOW üzerinden sürüdeki tüm İHA'lara taşıyıp Pixhawk'a enjekte eden
> 4 modüllü sistemin byte-seviyesi sözleşmesidir.

## REV B — değişiklik kaydı ve okuma notu

REV A (ilk taslak) yazıldığında ESP tarafı henüz uygulanmamıştı; uygulama
sırasında takım dört karar aldı ve bunlar ilk taslağın bazı kurallarını
**tersine çevirdi**. Bir ara sürümde bu kararlar yalnızca §2.2 ve §2.3'e
işlenmiş, §1 / §2.1 / §2.4 / §3.2 / §5 ise REV A metnini taşımaya devam
etmişti — yani doküman **kendi içinde çelişiyordu** (§2.1 "little-endian"
derken §2.2 "big-endian", §5 "şifreleme YASAK" derken §2.3 "şifreleme VAR").
Kendi içinde çelişen bir spec, spec'sizden tehlikelidir: okuyan hangi
bölüme denk gelirse ona inanır. Bu sürümde **tüm bölümler REV B'ye
senkronlanmıştır** ve REV A→B iz notları korunmuş, ama her bölümde tutarlı
hale getirilmiştir.

| # | REV B kararı | Etkilenen bölümler |
|---|---|---|
| 1 | ESP-NOW hava linki **şifreli** (AES-128-GCM büyük zarf). İlk taslağın "şifreleme YOK" kuralı tersine döndü. | §1, §2.3, §2.4, §3.2, §5 |
| 2 | Fragment payload **191 B** (243 değil) — GCM zarf ek yükü düşüldükten sonraki gerçek pay. `RTK_MAX_FRAGS = 8`. | §2.3, §3.2 |
| 3 | Her iki UART hattı da **TIP+ID prefiksli**, CRC16 **big-endian** ve TIP+ID dahil hesaplanır. | §2.1, §2.2, §3.1, §3.3, §3.4 |
| 4 | Fragment'lar arası sabit 2 ms bekleme YOK — **CSMA rastgele bekleme + 3 denemelik yerel radyo retry**. | §2.3, §3.2, §5 |

**Bu doküman ile kod arasında çelişki görürsen kod kazanır ve spec bug'dır —
lütfen bildir.** Aşağıdaki her sabit, koddaki tek kaynağına referansla
verilmiştir.

### Modül adı eşlemesi (ÖNEMLİ — isimler yanıltıcı)

Spec'in modül adları ile repodaki dizin adları **ters düşüyor**; bu tuzağa
düşmemek için:

| Spec'teki ad | Repodaki gerçek yer | Rolü |
|---|---|---|
| `esp_tx/` (Base ESP) | `firmware/esp32_mesh/RX BASE/` | RTCM'i **alır**, chunk'lar, yayınlar |
| `esp_rx/` (İHA ESP) | `firmware/esp32_mesh/TX DRONE/` | chunk'ları birleştirir, Pi'ye **yazar** |
| `yki/` | *(henüz yok — YKİ sorumlusunda)* | PC tarafı, F9P'den okur |
| `pi_bridge/` | *(henüz yok — Pi sorumlusunda)* | MAVLink enjeksiyonu |

Dizin adları RTK'den önceki genel sürü mesh'inden miras: "RX BASE" yer
istasyonundaki kart (sürü telemetrisini **alır**), "TX DRONE" İHA üstündeki
kart. RTK akışında rolleri terstir.

---

## 1. Sistem Mimarisi

```
[F9P RTK Base] --USB seri--> [PC: YKİ Python] --UART 460800 (COBS)--> [Base ESP32 = "RX BASE"]
     |                                                                        |
     |                                                    ESP-NOW broadcast (CH 11, AES-128-GCM)
     |                                                                        |
     v                                                                        v
  (RTCM3 üretir)                                              [İHA ESP32 = "TX DRONE"] (her İHA'da)
                                                                              |
                                                                    UART 460800 (COBS)
                                                                              |
                                                                  [Raspberry Pi: bridge Python]
                                                                              |
                                                                  MAVLink GPS_RTCM_DATA (ID 233)
                                                                              |
                                                                        [Pixhawk] --> GPS (Here4, DroneCAN)
```

**Temel ilke:** RTCM verisi uçtan uca AYNI ham binary'dir. Hiçbir katman içeriği
değiştirmez, sadece çerçeveler/taşır. GPS alıcısı orijinal, CRC'si bozulmamış
RTCM ister; tek bit hata mesajı geçersiz kılar.

**Kayıp stratejisi:** **Ağ seviyesinde retransmisyon YOK.** RTCM her saniye
yenilenir; eksik/geç mesaj DÜŞÜRÜLÜR. Düzeltme yaşı < 2 sn kaldıkça RTK Fixed
korunur.

> REV B netleştirmesi (karar #4): §2.3'teki "3 denemelik retry" bu kuralı
> ihlal ETMEZ. O retry yalnızca `esp_now_send()` **yerel** hata dönerse
> (TX kuyruğu dolu) çalışır — havada kaybolan paketi kurtarmaz, ağ-seviyesi
> ACK değildir. Broadcast'te donanım ACK'i zaten yoktur.

**Durum (state) ilkesi:** Hiçbir katmanda kalıcı state yok. Herhangi bir modül
yeniden başlarsa sistem müdahalesiz toparlanmalı.

---

## 2. Protokol Tanımları (BYTE SEVİYESİ — DEĞİŞMEZ)

### 2.1 CRC16 (tüm modüllerde ortak)

- Varyant: **CRC-16/CCITT-FALSE**
- Polinom: `0x1021`, Init: `0xFFFF`, RefIn: false, RefOut: false, XorOut: `0x0000`
- Test vektörü: `crc16(b"123456789") == 0x29B1` — her implementasyon bu testi geçmeli.
- Kablodaki byte sırası: **BÜYÜK-ENDIAN** (MSB önce).

> **REV B düzeltmesi (karar #3):** İlk taslak burada "little-endian" diyordu ve
> bu §2.2 ile açıkça çelişiyordu. Doğru ve uygulanan değer **big-endian**'dır.
> Gerekçe §2.2'de.
>
> Referans: `common/mesh_shared/uart_cobs.h::cobs_crc16` (ESP tarafı, test
> vektörü native testte doğrulanıyor: `test_crc16_test_vektoru`).

### 2.2 UART Çerçevesi (YKİ→Base-ESP ve İHA-ESP→Pi hatlarında AYNI format)

> **REV B güncellemesi (karar #3):** İlk taslakta bu hat prefiks'siz varsayılmıştı.
> Takım kararıyla her iki UART hattı da Base-ESP'nin Pi/genel-sürü protokolüyle
> **aynı fiziksel deseni** paylaştığı için (ESP tarafında hat gerçekten çoklanmış
> — RTK dışındaki sürü trafiğini de taşıyor) TIP+ID prefiksi eklendi ve CRC byte
> sırası big-endian'a çekildi (uygulamadaki genel `uart_gonder()` deseniyle
> tutarlı olsun diye). Aşağıdaki format gerçek implementasyonu yansıtır.

```
frame_on_wire = COBS_encode( TIP + ID + rtcm_message + crc16_be(TIP + ID + rtcm_message) ) + 0x00
```

- `TIP` (1 byte): mesaj tipi ayırıcısı — RTK için sabit `0x0C` (`TIP_RTK`).
- `ID` (1 byte): kaynak/baz kimliği — RTK için sabit `99` (`BAZ_ID`).
- `rtcm_message`: tam bir RTCM3 mesajı (0xD3 ile başlar, kendi CRC-24Q'su dahil).
- CRC16, **TIP + ID + rtcm_message'ın TAMAMI üzerinden** hesaplanır (COBS
  öncesi, CRC'nin kendisi hariç), sonuna 2 byte **BÜYÜK-ENDIAN** (MSB önce)
  eklenir.
- Sonra tamamı COBS ile kodlanır, `0x00` sınırlayıcı eklenir.
- Alıcı: `0x00`'a kadar biriktir → COBS decode → TIP/ID'yi ayır → kalan
  CRC16'yı (TIP+ID+payload üzerinden, BE) doğrula → tutmazsa çerçeveyi
  SESSİZCE at (log'a düş), tutarsa ve `TIP==0x0C && ID==99` ise rtcm_message
  hazır.
- Baud: **460800**, 8N1. Port yolları config/CLI parametresi olmalı, hardcode YASAK.
  *(Bu kural PC/Pi tarafındaki seri port YOLLARI içindir — ESP32'nin GPIO pin
  numaraları derleme zamanı sabitidir ve kapsam dışıdır.)*

**COBS 254 blok kuralı** (her implementasyon uygulamalı): kod baytı 1..255'e
sığmak zorunda olduğundan bir blok en fazla 254 sıfırsız bayt taşır. Blok
dolunca `0xFF` yazılır ("254 bayt izliyor, sonuna örtük 0x00 EKLEME") ve yeni
bloğa geçilir. Bu kuralı atlayan encoder ≥254 ardışık sıfırsız baytta bozulur
— gerçek MSM4 mesajları (~100-300 B, çoğunlukla sıfırsız) bu sınırı rutin
olarak aşar.

- Referans implementasyon: `common/mesh_shared/uart_cobs.h`
  (`cobs_cerceve_olustur` / `cobs_cerceve_coz`) — ESP tarafında bu iki
  fonksiyon her iki hatta da ortak kullanılıyor.
- Smoke-test göndericisi: `firmware/esp32_mesh/tools/test_sender.py`
  (üretim kodu değil; kanonik Python implementasyonu YKİ'nin `common/`
  paketinde olacak).

### 2.3 ESP-NOW Zarf Formatı (Base-ESP → İHA-ESP hava linki)

> **REV B güncellemesi (karar #1):** İlk taslak bu hat için şifresiz, ham bir
> ESP-NOW chunk formatı öngörüyordu ("Şifreleme YOK"). Takım kararıyla bu
> **tersine çevrildi**: RTK artık genel sürü mesh'inin AES-128-GCM şifreli
> zarf ailesinin **büyük** (değişken payload'lı) bir üyesi olarak taşınıyor.
>
> Gerekçe: mevcut app-layer GCM zaten ESP-NOW'ın kendi peer-şifreleme sınırına
> hiç girmiyordu (`peer.encrypt=false`, tek paylaşılan anahtar), bu yüzden ilk
> taslağın "peer limiti ölçeklenmeyi bozar" endişesi bu tasarımda geçerli
> değildi; buna karşın kasıtlı sahte RTCM enjeksiyonuna karşı (GPS spoofing
> riski) kimlik doğrulama korunması tercih edildi.
>
> Referans: `common/mesh_shared/rtk_pure.h` (saf sabitler/hesap) ve
> `rtk_handler.h::rtk_mesh_gonder()` / `rtk_mesh_loop()`.

Maksimum ESP-NOW payload 250 byte. Zarf, genel mesh paketiyle (`mesh_paket_t`)
AYNI önsöz düzenini kullanan, değişken uzunluklu **büyük** bir kardeş yapı:

```
offset  boyut  alan                (şifresiz / açık)
0       6      kaynak_mac
6       6      hedef_mac           (RTK için hep broadcast FF:FF:FF:FF:FF:FF)
12      4      paket_id            (mesh-geneli anti-replay/dedup sayacı — RTCM msg_id DEĞİL)
16      1      atlama_sayisi
17      1      tip                 (sabit TIP_RTK=0x0C — ISR bu offset'e bakarak yönlendirir)
18      12     iv                  (GCM nonce)
30      N      sifreli_veri        (AES-128-GCM ciphertext, N değişken — aşağıya bkz)
30+N    16     tag                 (GCM auth tag)
------  -----  toplam = 30 + N + 16, en fazla 250
```

`sifreli_veri` (deşifre edildiğinde) şu düzende:

```
offset  boyut  alan                                                 kaynak
0       2      session_id      (anti_replay_t.session_id)           reboot'ta değişir
2       4      paket_id        (anti_replay_t.paket_id)             MESH sayacı — her FRAGMENT'ta +1
6       4      msg_id          (rtk_mesh_frag_t.paket_id)           RTCM sayacı — her RTCM MESAJINDA +1
10      1      frag_index      (0'dan başlar)
11      1      frag_total
12      1      frag_uzunluk    (bu parçadaki gerçek veri byte sayısı, 1..191)
13      ≤191   payload         (RTCM mesajının dilimi)
------  -----  toplam = 13 + frag_uzunluk, en fazla 204
```

> **REV B düzeltmesi (spec bug):** Bir ara sürümde bu tablo `msg_id`'yi
> `anti_replay_t.paket_id` ile **aynı alan sanıyordu**, dolayısıyla 4 byte
> eksikti (tablo 200 B gösteriyordu, gerçek 204 B). Kodda bunlar **iki ayrı
> 4 byte'lık sayaçtır** ve karıştırılmamalıdır:
>
> - `anti_replay_t.paket_id` — mesh-geneli dedup/replay sayacı
>   (`++_paket_sayaci`), **her fragment'ta** artar. Açık önsözdeki offset 12
>   ile aynı değerdir. `_replay_kontrol()` bunu kullanır.
> - `rtk_mesh_frag_t.paket_id` (= `msg_id`) — RTCM mesaj kimliği
>   (`++_rtk_paket_sayaci`), **her RTCM mesajında** artar; aynı mesajın tüm
>   fragment'larında AYNIdır. Reassembly bunu kullanır (§2.4).
>
> İki sayacı birleştirmek reassembly'yi bozardı: mesh sayacı fragment başına
> arttığı için aynı mesajın parçaları farklı `msg_id` taşır görünürdü.

**RTK_FRAG_PAYLOAD_MAKS hesabı** (250 byte ESP-NOW sınırından geriye doğru):

```
sabit zarf alanları (kaynak_mac6+hedef_mac6+paket_id4+atlama_sayisi1+tip1+iv12+tag16) = 46 B
250 - 46 = 204 B                        (sifreli_veri için kalan yer)
anti_replay (session_id2 + paket_id4)                                 =  6 B
frag başlığı (msg_id4 + frag_index1 + frag_total1 + frag_uzunluk1)    =  7 B
204 - 6 - 7 = 191 B  →  RTK_FRAG_PAYLOAD_MAKS = 191  (static_assert >= 180)
```

> Not: frag başlığı **7 B**'dir çünkü `msg_id`'nin 4 byte'ını içerir. Bir ara
> sürüm bu satırı "(idx1+total1+len1) = 7 B" diye etiketliyordu — toplam
> doğru ama etiket yanlıştı (3 ≠ 7); yukarıdaki döküm kodla birebir uyumlu.

- `msg_id` **4 byte** (ilk taslakta 2 byte idi — mesh-geneli `paket_id` alanıyla
  aynı genişlikte tutuldu, tasarım tutarlılığı için).
- MAX_PAYLOAD = **191** (ilk taslaktaki 243 değil — GCM zarf ek yükü düşüldükten
  sonraki gerçek pay).
- `RTK_MAX_FRAGS = 8` (8×191 = 1528 B). Reassembly buffer **1600 B**.
  - **Yeterlilik kanıtı:** RTCM3'ün uzunluk alanı 10 bit olduğundan (§2.6) bir
    RTCM3 mesajı en fazla `3 + 1023 + 3 = 1029 B`'dir → en kötü durumda
    `ceil(1029/191) = 6` fragment. 8 fragment **her geçerli RTCM3 mesajı için**
    yeterlidir, 2 fragment marj bırakır.
- Gönderim: broadcast MAC `FF:FF:FF:FF:FF:FF`.
- **Fragment'lar arası sabit 2 ms bekleme YOK** (REV B karar #4). Yerine:
  CSMA rastgele bekleme (0–10 ms, `CSMA_GECIKME_MAKS_MS`, mesh geneliyle ortak
  mekanizma) + **3 denemelik yerel radyo retry** (`esp_now_send()` yerel hata
  dönerse 2–7 ms arayla). Bu **ağ-seviyesi ACK DEĞİLDİR** — broadcast'te donanım
  ACK'i yoktur, sadece yerel TX kuyruğu hatası kurtarılır (bkz §1, §5).
  - Gerekçe: REV A'nın "2 ms bekle" önerisi ~23 fragment/mesaj varsayımına
    (243→12 B payload) göre yazılmıştı. 191 B payload ile tipik MSM4 mesajı
    1–2, en kötü 6 fragment eder; her `rtk_mesh_gonder()` zaten kendi CSMA
    beklemesini uyguluyor. Sabit gecikme eklemek RTCM'in 1 sn'lik tazelik
    bütçesini gereksiz tüketirdi.
  - Referans: `rtk_handler.h::rtk_mesh_gonder()`.
- WiFi kanalı: **sabit CH 11** (`MESH_KANAL`). İlk taslakta örnek olarak CH 6
  verilmişti; gerçek değer önemli değil, **tüm ESP'lerde AYNI ve sabit olması**
  önemli — CH11 "TR ISM bandında sahada en az meşgul kanal" gerekçesiyle
  önceden seçilmişti. `MESH_KANAL_YEDEK = 6` uçuş öncesi spektrum taraması
  olumsuzsa kullanılır (otomatik geçiş YOK; tüm cihazlar aynı değerle yeniden
  flaşlanır).

### 2.4 İHA-ESP Reassembly Kuralları

- **Zarfın bütünlüğü GCM auth tag ile doğrulanır** — tag tutmuyorsa zarf
  reddedilir. Ardından mesh anti-replay kontrolü (`_replay_kontrol`) uygulanır.
  > **REV B düzeltmesi (karar #1):** İlk taslak burada "gelen chunk'ın CRC16'sı
  > tutmuyorsa at" diyordu. REV B'de hava linkinde **CRC16 YOKTUR**; bütünlüğü
  > ve kimliği GCM tag sağlar (CRC16 yalnızca §2.2'deki UART hatlarında
  > kullanılır). CRC16 zaten kasıtlı sahteciliğe karşı koruma sağlamazdı.
- Fragment başlığı geçersizse at: `frag_total == 0`, `frag_total > 8`,
  `frag_index >= frag_total`, `frag_uzunluk == 0` veya `frag_uzunluk > 191`.
- Çerçeve uzunluğu başlıkla tutarsızsa at: `uzunluk != 7 + frag_uzunluk`.
- `msg_id` mevcut buffer'ınkinden FARKLI ise: buffer'ı sıfırla, yeni mesaja başla
  (yarım eski mesaj düşer — bu bilinçli tasarım).
- Chunk'lar bitmask ile takip edilir; duplicate fragment atlanır; hepsi gelince
  tam mesaj UART'a (§2.2 formatı) yazılır.
- **500 ms** içinde tamamlanmayan mesaj timeout ile temizlenir
  (`RTK_FRAG_TIMEOUT_MS`).
- Reassembly buffer boyutu **1600 B** (`RTK_REASSEMBLY_BUF_SIZE`; ≥1200 şartını
  karşılar, 8×191=1528'e yuvarlanmış üst sınır).
- Referans: `common/mesh_shared/rtk_pure.h::rtk_asm_fragment_isle()` — Arduino'dan
  bağımsız saf durum makinesi, native testlerle doğrulanıyor.

### 2.5 MAVLink Enjeksiyonu (Pi → Pixhawk, GPS_RTCM_DATA / ID 233)

*(REV B bu bölümü değiştirmedi — `pi_bridge/` sorumluluğunda.)*

- data alanı maks 180 byte, `flags` byte'ı:
  - bit0: fragmented (1 = parçalı)
  - bit1-2: fragment id (0-3, maks 4 fragment)
  - bit3-7: sequence id (her RTCM mesajında +1, 0-31 sarar)
- Mesaj ≤180B: tek paket, `flags = seq << 3`, data 180'e sıfırla doldurulur (padding).
- Mesaj >180B: 180'lik dilimler, `flags = 1 | (frag_idx << 1) | (seq << 3)`.
- **ÖZEL KURAL:** veri 180'in tam katıysa sona 0 uzunluklu terminatör fragment eklenir.
- 4 fragment'tan (>720B) büyük mesaj: DÜŞÜR ve logla (MSM4 setinde olmamalı).
- Pixhawk bağlantısı: TELEM2, 921600 baud (config'den ayarlanabilir).

> **Karıştırmayın:** buradaki 720 B / 4 fragment sınırı **MAVLink katmanına**
> aittir ve §2.3'teki mesh fragmantasyon sınırından (8×191 = 1528 B) tamamen
> ayrıdır. İkisi farklı katmanların farklı limitleridir.

### 2.6 RTCM3 Çerçeve Yapısı (referans)

```
0xD3 | 2 byte (6 bit reserved + 10 bit payload uzunluğu) | payload | 3 byte CRC-24Q
```
- CRC-24Q: poly 0x1864CFB, init 0, yansımasız; CRC-24Q hariç tüm baytlar üzerinden.
- Mesaj tipi = payload'ın ilk 12 biti: `(frame[3] << 4) | (frame[4] >> 4)`.
- Uzunluk alanı 10 bit → payload ≤ 1023 B → **tam mesaj ≤ 1029 B**. Bu üst sınır
  §2.3'teki fragment yeterlilik kanıtının dayanağıdır.
- Beklenen mesaj seti: **1005, 1074, 1084, 1094, 1230 @ 1 Hz** (MSM4; MSM7
  KULLANILMAZ çünkü 720B MAVLink tavanını aşabilir).

> **Uygulama notu (ekip kararı):** Base-ESP, MSM7 (1077/1087/1097/1127) görürse
> **UYARI loglar ama mesajı DÜŞÜRMEZ** — iletir. Gerekçe: bu bir yapılandırma
> hatasının erken teşhisidir (Base yanlış kurulmuş); asıl 720 B düşürme kararı
> §2.5'e göre `pi_bridge`'in işidir. ESP'nin sessizce düşürmesi sahada teşhisi
> zorlaştırırdı.

---

## 3. Modüller ve Sorumlulukları

### 3.1 `yki/` — PC tarafı (Python 3.10+, pyserial, cobs)

> ⚠️ **EKSİK İÇERİK:** Bu bölümün daha kapsamlı bir sürümü (CubePilot Here4 Base
> donanım kararı ve adım adım Mission Planner Survey-In prosedürü) sohbete
> yapıştırılmış, ancak elimizdeki dosya kopyasında yer almıyor. Aşağıdaki metin
> mevcut kopyadan alınmıştır; **Here4/Mission Planner prosedürü YKİ sorumlusu
> tarafından buraya eklenmelidir.**

Görev: F9P seri akışından tam RTCM mesajları ayrıştır → CRC-24Q doğrula →
§2.2 formatıyla Base-ESP'ye gönder.

- `rtcm_parser.py`: byte-byte 0xD3 senkronlu durum makinesi; CRC-24Q doğrulaması;
  bozuk çerçevede senkrona geri dön.
- `crc.py`: crc16_ccitt_false + crc24q; her ikisinin test vektörlü unit testi.
- `uart_framer.py`: gönderici tarafı — **§2.2'ye birebir uy**: TIP(0x0C) + ID(99)
  prefiksi, CRC16 bu prefiks DAHİL hesaplanır ve **big-endian** yazılır, sonra
  COBS + 0x00. COBS encoder **254 blok kuralını uygulamalı** (§2.2).
- `main.py`: CLI: `--gps-port`, `--gps-baud` (vars. 115200), `--esp-port`,
  `--esp-baud` (vars. 460800). Loglama: saniyede mesaj sayısı, tip dağılımı,
  toplam byte, CRC hata sayacı.
- **YKİ PARÇALAMA YAPMAZ** — tam mesaj gönderir; chunk'lama Base-ESP'nin işi.

### 3.2 `esp_tx/` — Base ESP32 = repoda **`RX BASE/`** (Arduino / PlatformIO)

Görev: UART'tan COBS çerçevesi al → decode + CRC16 doğrula → §2.3 formatında
chunk'la → ESP-NOW broadcast.

- UART RX buffer ≥ 2048 byte. **`setRxBufferSize()` `begin()`'DEN ÖNCE
  çağrılmalı** — ESP32 Arduino core'da sonra çağrılırsa SESSİZCE etkisiz kalır
  (varsayılan 256 B ring buffer kullanılmaya devam eder). Baud **460800**.
- COBS decode + CRC16 doğrulama (TIP+ID dahil, BE); TIP/ID kontrolü; hata sayaçları.
- Giriş savunmaları: `payload[0] == 0xD3`, RTCM uzunluk alanı ile çerçeve
  boyutu tutarlılığı, MSM7 uyarısı (§2.6).
- `rtk_rtcm_fragment_ve_gonder()`: msg_id artır, **191**'lik dilimlere böl,
  her fragment'ı §2.3 büyük GCM zarfıyla broadcast et. **Sabit 2 ms bekleme YOK**
  — CSMA + 3 denemelik yerel retry (§2.3, karar #4).
- WiFi: `WIFI_STA` mod, **kanal 11 sabit**, `esp_now_init`, broadcast peer ekle.
- Durum LED'i: veri akarken yanıp sönsün (saha teşhisi için).
- **Port uyarısı:** bu firmware'de `Serial1` YKİ/RTCM **giriş** hattıdır; Pi
  protokolü `Serial2`'de yürür. Pi'ye yazan ortak fonksiyonlar
  (`failsafe_kontrol`, `rtk_mesh_loop`) hedef portu **parametre olarak** alır ve
  bu firmware `Serial2`'yi açıkça geçer.

### 3.3 `esp_rx/` — İHA ESP32 = repoda **`TX DRONE/`** (Arduino / PlatformIO)

Görev: ESP-NOW zarfı al → §2.4 kurallarıyla birleştir → §2.2 formatıyla Pi'ye UART.

- `esp_now_register_recv_cb` içinde MINIMUM iş (kopyala+bayrak); işleme loop()'ta.
  ISR, zarfın offset 17'sindeki `tip` baytına bakarak TIP_RTK'yi ayrı ring
  buffer'a yönlendirir (önsöz düzeni `mesh_paket_t` ile ortak olduğu için tam
  parse gerekmez).
- Reassembly: GCM tag doğrula → replay kontrol → msg_id karşılaştır, bitmask,
  500 ms timeout (§2.4).
- Tam mesajı **TIP(0x0C)+ID(99) prefiksli**, CRC16 (BE, prefiks dahil) + COBS +
  0x00 ile UART'a (460800) yaz.
- **Bu Serial1 hattı RTK'nin yanı sıra joystick/pose/vb. TÜM Pi↔mesh protokolünü
  de taşır** — Pi tarafı da 460800'de olmalı.
- İstatistik: alınan/düşen mesaj sayacı, periyodik debug satırı (ayrı debug UART
  veya derleme bayrağıyla kapatılabilir: `-D RTK_ISTATISTIK_LOGLAMA_KAPALI`).

### 3.4 `pi_bridge/` — Raspberry Pi (Python 3.10+, pyserial, cobs, pymavlink)

Görev: İHA-ESP'den UART çerçevelerini çöz → §2.5 kurallarıyla Pixhawk'a enjekte.

- `uart_framer.py`: alıcı tarafı (0x00'a kadar biriktir, decode, CRC doğrula) —
  YKİ ile AYNI dosya olmalı (ortak `common/` paketi önerilir).
  - ⚠️ **REV B'de değişti:** RTK çerçevesinin CRC16'sı artık **TIP(0x0C) +
    BAZ_ID(99) prefiksi DAHİL** hesaplanıyor ve **big-endian** yazılıyor. Daha
    önce YKİ/Pi ekibine "prefiks yok, little-endian" denmişti — o bilgi
    GEÇERSİZ.
  - Hat çoklanmış: aynı porttan TIP_RTK dışında sürü protokolü tipleri de gelir;
    TIP'e göre dispatch edin.
- `mavlink_injector.py`: `inject_rtcm(data)` — §2.5'teki flags/seq/fragment/terminatör
  mantığı; bunun için AYRINTILI unit test yaz (özellikle 180, 360, 540 byte'lık
  tam-kat durumları ve 181 byte sınır durumu).
- `main.py`: CLI: `--esp-port`, `--mav-port`, `--mav-baud`. Loglama: enjekte edilen
  mesaj/sn, düşen mesaj, son mesajdan bu yana geçen süre (staleness uyarısı >2 sn).
- ArduPilot parametre notu (koda değil README'ye): `GPS_TYPE=9` (DroneCAN/Here4),
  `CAN_P1_DRIVER=1`, `CAN_D1_PROTOCOL=1`, `GPS_INJECT_TO=127`.

### 3.5 `common/` — Paylaşılan Python kodu

- `crc.py`, `cobs_framing.py`: YKİ ve Pi aynı implementasyonu kullanır.
- ESP tarafındaki C implementasyonları da aynı test vektörlerini geçmeli
  (`crc16(b"123456789") == 0x29B1` — ESP tarafında doğrulandı).

---

## 4. Kabul Testleri (bu sırayla)

1. **Unit — CRC:** `crc16(b"123456789") == 0x29B1`; CRC-24Q bilinen RTCM örneğiyle.
2. **Unit — COBS round-trip:** rastgele 1-1200 byte veri, encode→decode kimlik testi;
   içinde 0x00 olan veriler dahil; **254 blok sınırları (253/254/255/507/508/509)
   ayrıca test edilmeli**.
3. **Unit — MAVLink fragmantasyon:** 100 / 180 / 181 / 360 / 540 / 700 / 721 byte
   girişleri için flags/fragment/terminatör doğrulaması (721 → düşürülmeli).
4. **Unit — Reassembly:** eksik chunk, msg_id sıçraması, duplicate chunk, timeout
   senaryoları.
5. **Entegrasyon — kablolu köprü (REV B'de yeniden tanımlandı, aşağıya bkz).**
6. **Entegrasyon — RF menzil testi:** kart aralığı gerçek uçuş mesafesine
   çıkarılır; Pi'de msg_id sürekliliğinden kayıp oranı ölçülür.
7. **Sistem — Pixhawk:** QGC/Mission Planner'da GPS durumu RTK Float(5) → Fixed(6);
   düzeltme yaşı < 2 sn.
8. **Dayanıklılık:** her modülü tek tek kapat-aç; sistem müdahalesiz toparlanmalı.

> ESP tarafında 1, 2 ve 4 `pio test -e native` altında (ASan/UBSan açık, donanımsız)
> koşuyor: `firmware/esp32_mesh/RX BASE/test/test_rtk_pure/`. 3 ve 5-8 sırasıyla
> `pi_bridge` ve saha ekibindedir.

### 4.5 Entegrasyon — kablolu köprü (REV B tanımı)

**Kurulum:** YKİ→Base-ESP **kablolu** + Base-ESP↔İHA-ESP **masada ~30 cm
ESP-NOW** + İHA-ESP→Pi **kablolu**. Uçtan uca YKİ'den Pi'ye mesajların CRC'li
ve eksiksiz geldiği doğrulanır.

**Amaç:** RF sorunlarını yazılımdan ayırmak. Masa mesafesinde RF kaybı pratikte
sıfırdır, dolayısıyla yazılım zinciri yine izole edilmiş olur — **ama gerçek
yoldan.**

> **REV A'nın passthrough önerisi REDDEDİLDİ (takım kararı).** İlk taslak bu
> testi "ESP-NOW yerine geçici UART passthrough derlemesi" ile tanımlıyordu.
> Bu öneri **kendi amacını baltalıyor**: passthrough, tam da test etmek
> istediğimiz zarf/fragmantasyon/GCM/reassembly yolunu baypas eder. "Geçen" bir
> passthrough testi, gerçek yol hakkında hiçbir şey kanıtlamaz — üstelik
> yalnızca test için var olan, üretimde hiç çalışmayan bir kod yolu bakım yükü
> ve kendine ait bug'lar getirirdi.

**Beklenen sonuç:** msg_id sürekliliğinde boşluk yok, CRC hata sayacı 0,
Pi'ye ulaşan RTCM byte'ları YKİ'nin gönderdikleriyle birebir aynı.

---

## 5. Yapılmayacaklar (bilinçli kararlar — SORGULAMADAN UYGULA)

- ❌ **Ağ-seviyesi retransmisyon / ACK mekanizması** ekleme (taze veri > eksiksiz veri).
  - ✅ İstisna (REV B karar #4): `esp_now_send()` **yerel** hatasında 3 denemelik
    retry VAR. Bu ağ ACK'i değildir — havada kaybolan paketi kurtarmaz, sadece
    dolu TX kuyruğunu kurtarır. Ayrım için §2.3'e bakın.
- ~~❌ ESP-NOW şifreleme~~ → **REV B karar #1 ile TERSİNE DÖNDÜ: şifreleme VAR.**
  RTK, AES-128-GCM'li büyük zarfla taşınır (§2.3). İlk taslağın gerekçesi
  ("broadcast'te desteklenmez; peer limiti ölçeklenmeyi bozar") bu tasarımda
  geçersizdi: app-layer GCM kullanılıyor, ESP-NOW'ın kendi peer şifrelemesi
  değil (`peer.encrypt=false`).
- ❌ YKİ tarafında chunk'lama (çift parçalama olur).
- ❌ MSM7 mesajları (720B MAVLink tavanını aşabilir) — Base yapılandırması MSM4
  olmalı. ESP uyarır ama düşürmez (§2.6); düşürme kararı `pi_bridge`'de (§2.5).
- ❌ Kalıcı state / kaldığı yerden devam mantığı (stateless tasarım şart).
- ❌ Port yollarını hardcode etme (PC/Pi seri port yolları; ESP GPIO pinleri hariç).
- ❌ Sadece test için var olan, üretimde çalışmayan kod yolları (bkz §4.5
  passthrough reddi).

---

## 6. Repo Yapısı

**Mevcut (bu repo):**

```
yelpence-2026-swarm/
├── docs/YELPENCE_RTCM_SPEC.md      # bu doküman
└── firmware/esp32_mesh/
    ├── common/mesh_shared/          # iki firmware'in ORTAK header'ları
    │   ├── uart_cobs.h              # §2.1/§2.2 — CRC16 + COBS + çerçeve kur/çöz
    │   ├── uart_frame_parser.h      # desync-güvenli çerçeve ayrıştırıcı
    │   ├── rtk_pure.h               # §2.3/§2.4 — sabitler + saf fragman/reassembly
    │   ├── rtk_handler.h            # büyük GCM zarfı gönder/al
    │   ├── mesh_config.h            # TIP_*, BAZ_ID, MESH_KANAL, GCM/AAD/replay
    │   ├── encryption.h
    │   └── fail_safe.h
    ├── RX BASE/                     # = spec'in esp_tx/ (Base ESP)
    │   ├── include/rtk_sender.h     # §3.2
    │   └── test/test_rtk_pure/      # native unit testler (§4.1/4.2/4.4)
    ├── TX DRONE/                    # = spec'in esp_rx/ (İHA ESP)
    ├── KEY WRITER/                  # NVS anahtar provision (src/ bilerek ignore'lu)
    └── tools/test_sender.py         # §2.2 smoke-test göndericisi
```

**Planlanan (henüz yok — YKİ/Pi sorumlularında):**

```
├── common/            # paylaşılan Python: crc.py, cobs_framing.py + testler
├── yki/               # PC tarafı (§3.1)
├── pi_bridge/         # Raspberry Pi tarafı (§3.4)
└── tests/             # Python unit + entegrasyon testleri
```
