# YELPENÇE — RTCM Dağıtım Sistemi Teknik Spesifikasyonu

> **Sürüm: REV C** — bu doküman RTK Base'den üretilen RTCM3 düzeltme verisini,
> ESP-NOW üzerinden sürüdeki tüm İHA'lara taşıyıp Pixhawk'a enjekte eden
> sistemin byte-seviyesi sözleşmesidir.

## ⚠ REV C — ÖNCE BUNU OKU

REV B yazıldığında sistem **hiç uçtan uca çalıştırılmamıştı**. 28–29 Temmuz
2026'da çalıştırıldı (bkz `docs/28-29-temmuz.md`) ve aşağıdaki bölümlerin
bir kısmı gerçeği yansıtmaz hale geldi. Spec'in kendi kuralı geçerli:
**kod kazanır.**

Aşağıdaki tablo, dokümanın geri kalanında karşılaşacağın YANLIŞ ifadeleri ve
güncel karşılıklarını verir. Bir bölüm bunlardan birini söylüyorsa, o bölüm
REV B metnidir ve **bu tablo onu geçersiz kılar**.

| REV B'de yazan | REV C gerçeği | Kaynak |
|---|---|---|
| ESP-NOW hava linki **AES-128-GCM şifreli** | **Şifreleme YOK.** Kaldırıldı; zarf 70 → 25 bayt. Gerekçe: şartname §5.4 gizlilik değil **parazit** şartı koyuyor; ayrıca NVS session sayacı sahada üç kez "duyar ama duyulmaz" arızası üretti. | `mesh_config.h` başındaki GÜVENLİK MODELİ notu |
| Fragment payload **191 B**, `RTK_MAX_FRAGS=8` → 1528 B | **238 B**, 8×238 = 1904 B. Şifreleme kalkınca 47 bayt serbest kaldı. En büyük RTCM3 (1029 B) artık **5** parçaya sığıyor, 6 değil. | `rtk_pure.h::RTK_FRAG_PAYLOAD_MAKS` |
| Reassembly buffer **1600 B** | **1920 B** | `rtk_pure.h::RTK_REASSEMBLY_BUF_SIZE` |
| Anti-replay, `session_id`, NVS boot sayacı, fail-closed, "NVS erase tuzağı" | **Tamamı kaldırıldı.** Firmware NVS'e hiç dokunmuyor, provizyon adımı yok. §2.4'ün F1 notu ve §3.1'deki erase prosedürü **geçersiz**. | `mesh_config.h`, `YUKLEME_PROSEDURU.md` |
| Fragment'lar **broadcast** yayınlanır | **Unicast**, mesh'in canlı node tablosuna. Gerekçe: broadcast'te 802.11 ACK yok; RTCM'de tek parça kaybı TÜM mesajı öldürür, yani kayıp olasılığı parça sayısıyla çarpılır. Canlı node yoksa broadcast'e düşülür. | `rtk_handler.h::rtk_mesh_gonder` |
| RTCM base'e **adanmış UART**'tan (Serial1) girer | **YKİ veri hattından `TIP_RTK` çerçevesi olarak** gelir (Serial2, USB-TTL). `RTCM_GIRISI_VAR=0` kalır; adanmış hat açılırsa boşta GPIO gürültüyü çerçeve sanıp hattı doldurur (ölçüldü: 11.6 kB/s). | `RX BASE/src/main.cpp` |
| YKİ **doğrudan seri porta** yazar | **ROS topic'ine yayınlar** (`/swarm/internal/rtcm`); `esp32_bridge` abone olup çerçeveler ve yazar. Sebep: bir portu tek süreç açabilir ve sahibi `esp32_bridge`. Sahada QGC autoconnect'i ile birebir bu çatışma yaşandı. | `yki_rtcm_reader.py --ros-topic` |
| §2.5 MAVLink enjeksiyonu `pi_bridge`'te yapılacak | **Yapıldı**: `px4_bridge` `{ns}/rtcm/in` dinliyor, MAVROS'un `gps_rtk/send_rtcm`'ine veriyor; parçalamayı MAVROS yapıyor. `esp32_bridge`'in yayın topic'i `agent_id`'den türetilir. | `px4_bridge.py` |
| §6'da `yki/`, `pi_bridge/` "henüz yok" | İkisi de var: `src/gcs/backend/rtcm/` ve `src/swarm_control/`. | — |

**Değişmeyenler** (REV B metni hâlâ geçerli): CRC16-CCITT-FALSE + big-endian,
§2.2 UART çerçeve formatı (`COBS(TIP+ID+rtcm+crc16_be)+0x00`), `TIP_RTK=0x0C`,
`BAZ_ID=99`, COBS 254-blok kuralı, `RTK_MAX_FRAGS=8`, 500 ms reassembly
timeout, MSM4 mesaj seti, ağ-seviyesi retransmisyon yasağı, §5.1'deki
"baz linki koptuğunda otonom görevi kesme" kararı.

**Uçtan uca doğrulama (29 Temmuz):** 125 RTCM mesajı yayınlandı → her iki
İHA'da `msg=125 frag=125 sync_kayip=0 cb_hata=0`. Kayıp sıfır.

---

## REV B — değişiklik kaydı ve okuma notu (TARİHSEL — yukarıdaki REV C tablosuyla birlikte oku)

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
| F1 | `session_id` **monoton** (NVS boot sayacı), alıcı küçük olanı reddeder → reboot-replay kapatıldı. Güvenlik state'i **kalıcı** — stateless kuralının bilinçli istisnası. | §1, §2.3, §2.4, §3.1, §4.8, §5 |

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

**Durum (state) ilkesi — İKİ FARKLI STATE, KARIŞTIRMA:**

- **VERİ AKIŞI STATE'İ → kalıcı olması YASAK.** RTCM'de "kaldığı yerden devam"
  yok: yarım mesaj, yarım reassembly, yarım çerçeve reboot'ta düşer ve
  sistem müdahalesiz toparlanır. Stateless kuralı **bunun içindir**.
- **GÜVENLİK STATE'İ → bilinçli İSTİSNA, kalıcı olmak ZORUNDA.** Anti-replay'in
  NVS'te tuttukları (gönderici monoton boot sayacı + alıcının peer→session
  kaydı) buraya girer. **Bunu kaldırmak bir güvenlik gerilemesidir**, sadeleştirme
  değil: kalıcı olmazsa saldırgan "alıcıyı reboot ettir, eski session'ı oynat"
  ile reboot-replay'i geri açar — yani koruma kâğıt üzerinde kalır (bkz §2.4).

Ayrım şu soruyla yapılır: *"Bu state kaybolursa veri mi kaybolur, koruma mı?"*
Veri kaybı kabul (taze RTCM zaten 1 sn sonra gelir); koruma kaybı kabul değil.

**Toparlanma:** Herhangi bir modül yeniden başlarsa sistem müdahalesiz
toparlanmalı — **güvenlik state'i tutarlıyken.** Tutarsızsa (NVS açılamıyor,
boot sayacı 65535'i aştı, bir node'un NVS'i silinmiş) firmware **bilinçli
olarak fail-closed durur veya o peer'i reddeder**; sessizce korumasız devam
etmez. Bu durumlar ve saha prosedürü: §2.4 ve §3.1.

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
0       2      session_id      (anti_replay_t.session_id)           gönderici başına MONOTON ARTAR (NVS boot sayacı) — §2.4
2       4      paket_id        (anti_replay_t.paket_id)             MESH sayacı — her FRAGMENT'ta +1
6       4      msg_id          (rtk_mesh_frag_t.paket_id)           RTCM sayacı — her RTCM MESAJINDA +1
10      1      frag_index      (0'dan başlar)
11      1      frag_total
12      1      frag_uzunluk    (bu parçadaki gerçek veri byte sayısı, 1..238)
13      ≤238   payload         (RTCM mesajının dilimi)
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

**RTK_FRAG_PAYLOAD_MAKS hesabı** — ⚠ **REV C'de DEĞİŞTİ.** Şifreleme
kaldırılınca zarftan 47 bayt serbest kaldı. Güncel hesap (250 byte ESP-NOW
sınırından geriye doğru):

```
önsöz (sihir2 + tip1)                                                 =  3 B
frag başlığı (msg_id4 + frag_index1 + frag_total1 + frag_uzunluk1)    =  7 B
CRC16                                                                 =  2 B
250 - 3 - 7 - 2 = 238 B  →  RTK_FRAG_PAYLOAD_MAKS = 238  (static_assert >= 180)
```

<details>
<summary>REV B'nin (şifreli) hesabı — tarihsel, ARTIK GEÇERLİ DEĞİL</summary>

```
sabit zarf alanları (kaynak_mac6+hedef_mac6+paket_id4+atlama_sayisi1+tip1+iv12+tag16) = 46 B
250 - 46 = 204 B                        (sifreli_veri için kalan yer)
anti_replay (session_id2 + paket_id4)                                 =  6 B
frag başlığı (msg_id4 + frag_index1 + frag_total1 + frag_uzunluk1)    =  7 B
204 - 6 - 7 = 191 B
```
</details>

> Not: frag başlığı **7 B**'dir çünkü `msg_id`'nin 4 byte'ını içerir. Bir ara
> sürüm bu satırı "(idx1+total1+len1) = 7 B" diye etiketliyordu — toplam
> doğru ama etiket yanlıştı (3 ≠ 7); yukarıdaki döküm kodla birebir uyumlu.

- `msg_id` **4 byte** (ilk taslakta 2 byte idi — mesh-geneli `paket_id` alanıyla
  aynı genişlikte tutuldu, tasarım tutarlılığı için).
- MAX_PAYLOAD = **238** (REV B'deki 191 değil — şifreleme kalktı).
- `RTK_MAX_FRAGS = 8` (8×238 = 1904 B). Reassembly buffer **1920 B**.
  - **Yeterlilik kanıtı:** RTCM3'ün uzunluk alanı 10 bit olduğundan (§2.6) bir
    RTCM3 mesajı en fazla `3 + 1023 + 3 = 1029 B`'dir → en kötü durumda
    `ceil(1029/238) = 5` fragment. 8 fragment **her geçerli RTCM3 mesajı için**
    yeterlidir, 3 fragment marj bırakır.
  - Doğrulandı (29 Temmuz): 106 B → 1 parça, 238 B → 1, 239 B → 2, 406 B → 2,
    1029 B → 5.
- Gönderim: **canlı node tablosuna UNICAST** (REV C). Broadcast'te 802.11 ACK
  yoktur ve RTCM'de tek parça kaybı TÜM mesajı öldürür; unicast'te donanım
  ACK + MAC retry devreye girer. Hiç canlı node yoksa broadcast'e düşülür.
- **Fragment'lar arası sabit 2 ms bekleme YOK** (REV B karar #4). Yerine:
  CSMA rastgele bekleme (0–10 ms, `CSMA_GECIKME_MAKS_MS`, mesh geneliyle ortak
  mekanizma) + **3 denemelik yerel radyo retry** (`esp_now_send()` yerel hata
  dönerse 2–7 ms arayla). Bu **ağ-seviyesi ACK DEĞİLDİR** — broadcast'te donanım
  ACK'i yoktur, sadece yerel TX kuyruğu hatası kurtarılır (bkz §1, §5).
  - Gerekçe: REV A'nın "2 ms bekle" önerisi ~23 fragment/mesaj varsayımına
    (243→12 B payload) göre yazılmıştı. 238 B payload ile tipik MSM4 mesajı
    1–2, en kötü 5 fragment eder; her `rtk_mesh_gonder()` zaten kendi CSMA
    beklemesini uyguluyor. Sabit gecikme eklemek RTCM'in 1 sn'lik tazelik
    bütçesini gereksiz tüketirdi.
  - **REV C notu:** CSMA beklemesi artık fragment BAŞINA bir kez uygulanıyor,
    hedef başına değil. Unicast'e geçince aynı fragment N hedefe gidiyor; N kez
    rastgele beklemek gecikmeyi N'e katlar ve hiçbir şey kazandırmaz — 802.11
    MAC her çerçeve için kendi çekişmesini zaten yapıyor.
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

  > **F1 — anti-replay kuralı (session_id MONOTON).** GCM `session_id`'yi
  > authenticated yapar, yani saldırgan onu *uyduramaz* — ama yakaladığı eski
  > bir session'ın paketlerini **aynen tekrar oynatabilir**. Bu yüzden kural
  > "session farklı → reboot varsay, kabul et" DEĞİL:
  >
  > | Gelen | Karar |
  > |---|---|
  > | `session_id < bilinen` | **RED** — eski session = reboot-replay saldırısı |
  > | `session_id == bilinen` | normal sliding-window (pencere 64) |
  > | `session_id > bilinen` | gönderici reboot etti → kabul + pencere sıfırla + **persist** |
  >
  > Kuralın iki yarısı da **zorunlu** (biri eksikse koruma kâğıt üzerinde kalır):
  > - **Gönderici:** `session_id` NVS'te monoton boot sayacı — rastgele DEĞİL,
  >   çünkü rastgele değer "daha küçük" karşılaştırmasını anlamsız kılar.
  > - **Alıcı:** peer→son_session_id kaydı NVS'te kalıcı ve **boot'ta geri
  >   yüklenir**. Yüklenmezse saldırı "alıcıyı reboot ettir, eski session'ı
  >   oynat"a kayar.
  >
  > **Fail-closed durumları** (sessizce korumasız devam etmek YASAK):
  > NVS açılamıyor → firmware durur; boot sayacı 65535'i aştı (uint16 sarması)
  > → firmware durur; bir peer'in session'ı persist edilemiyor → **o peer'in
  > tüm paketleri reddedilir**.
  >
  > **Bilinen boşluk (belgeli):** node tablodan tamamen düşüp slotu başkasına
  > verilirse aynı session içindeki pencere RAM'de sıfırlanır; NVS kaydı eski
  > session'ı yine reddeder ama aynı session'ın eski paketlerini durduramaz.
  > Tam çözüm GPS zaman damgası — session_id'nin *yerine* değil *yanına*
  > (bootstrap sorunu var ve tek başına aynı saniye içindeki replay'i durdurmaz).
  >
  > ⚠️ **NVS erase tuzağı** — sahada bilinmesi şart: bir node'un NVS'ini
  > silerseniz (`erase_flash`) boot sayacı 1'e döner ve diğer node'lar onu
  > **kalıcı reddeder** ("duyar ama duyulmaz" semptomu). Prosedür §3.1'de.
  > **REV B düzeltmesi (karar #1):** İlk taslak burada "gelen chunk'ın CRC16'sı
  > tutmuyorsa at" diyordu. REV B'de hava linkinde **CRC16 YOKTUR**; bütünlüğü
  > ve kimliği GCM tag sağlar (CRC16 yalnızca §2.2'deki UART hatlarında
  > kullanılır). CRC16 zaten kasıtlı sahteciliğe karşı koruma sağlamazdı.
- Fragment başlığı geçersizse at: `frag_total == 0`, `frag_total > 8`,
  `frag_index >= frag_total`, `frag_uzunluk == 0` veya `frag_uzunluk > 238`.
- Çerçeve uzunluğu başlıkla tutarsızsa at: `uzunluk != 7 + frag_uzunluk`.
- `msg_id` mevcut buffer'ınkinden FARKLI ise: buffer'ı sıfırla, yeni mesaja başla
  (yarım eski mesaj düşer — bu bilinçli tasarım).
- Chunk'lar bitmask ile takip edilir; duplicate fragment atlanır; hepsi gelince
  tam mesaj UART'a (§2.2 formatı) yazılır.
- **500 ms** içinde tamamlanmayan mesaj timeout ile temizlenir
  (`RTK_FRAG_TIMEOUT_MS`).
- Reassembly buffer boyutu **1920 B** (`RTK_REASSEMBLY_BUF_SIZE`; 8×238=1904'e
  yuvarlanmış üst sınır). REV B'de 1600 B idi.
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
> aittir ve §2.3'teki mesh fragmantasyon sınırından (8×238 = 1904 B) tamamen
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

### 3.1 YKİ — Donanım Kararı ve Saha Prosedürü

**Donanım kararı (KESİN): Base = CubePilot Here4 Base.**
Kendi USB kablosuyla PC'ye doğrudan bağlanır ve standart COM/seri port
olarak görünür (içi u-blox F9P). CAN adaptörü GEREKMEZ — CAN→USB
adaptörü yalnızca Here4 ROVER'lar (drone üzerindeki, Pixhawk'a DroneCAN
ile bağlı GPS'ler) bağlamında geçerlidir ve YKİ'yi ilgilendirmez.

**Saha kurulum prosedürü (her kurulumda, operasyonel — kod değil):**
1. Mission Planner → Initial Setup → Optional Hardware → RTK/GPS Inject.
2. Here4 Base'in COM portunu seç, bağlan; SurveyIn Accuracy + Time gir,
   Restart.
3. Survey tamamlanıp RTCM göstergeleri yeşil olunca "Save Current Pos"
   ile konumu kaydet — sonraki kurulumlarda "Use" ile Survey-In
   beklemeden sabit modda başlar (yarışma günü zaman kazandırır).
4. Mission Planner'ı KAPAT (COM portunu serbest bırak) → YKİ okuyucusunu
   başlat. ⚠️ Aynı COM portu iki program aynı anda açamaz; MP açıkken
   YKİ port hatası alır.
5. YKİ mesaj setini logdan doğrular: 1005, 1074, 1084, 1094, 1230 @1Hz.
   MSM7 tipi (1077/1087/1097/1127) görülürse Base yanlış
   yapılandırılmıştır — MP'den MSM4'e düzeltilir.
6. (Backlog / v2): YKİ'nin pyubx2 ile UBX-CFG göndererek Survey-In +
   MSM4 setini kendisinin yapılandırması — şimdilik UYGULANMAZ.

#### ⚠️ NVS ERASE TUZAĞI — ESP flaşlamadan ÖNCE oku

Bu kural bir C header'ının içinde yaşarsa sahada kimse bilmez; o yüzden saha
prosedürünün parçası:

**`esptool erase_flash` / "NVS'i temizleyelim" bir ESP'ye tek başına
UYGULANMAZ.** Anti-replay (§2.4) gönderici tarafında NVS'teki monoton boot
sayacına dayanır. Bir node'un NVS'ini silerseniz sayacı 1'e döner; diğer
node'lar onun `session_id`'sini "eski session = replay" sayıp **kalıcı
reddeder**. Semptom sinsi: cihaz açılır, mesh'i **duyar**, ama kimse onu
**duymaz** — RF/anten arızası gibi görünür, saatler yakar.

- **Teşhis:** diğer node'ların konsolunda `[REPLAY] ESKI SESSION reddedildi:
  ... sid=1 < kalici=N` satırı. `sid` 1-2 ise neredeyse kesin budur, saldırı
  değil. Silinen cihazın kendi konsolu da boot'ta uyarı basar.
- **Kurtarma (desteklenen yol):** peer'lerin kaydı da sıfırlanmalı. Pratikte:
  bir node'un NVS'ini silersen **sürünün tamamını** (baz + tüm droneler)
  birlikte erase + yeniden provision + flaşla. Bu zaten "zarf formatı
  değişirse hepsini aynı gün flaşla" kuralıyla aynı operasyonel pencere.
  Sadece `peer_sess` silmek de yeterlidir (AES anahtarına dokunmadan):
  NVS namespace `mesh_sec`, anahtar `peer_sess`.
- **Neden kolay bir "sıfırla" komutu yok:** uzaktan tetiklenebilir bir
  "replay korumasını sıfırla" komutu, korumanın kendisini anlamsız kılardı.
  Kurtarma bilinçli ve yetkili bir işlem olmak zorunda.

#### 3.1.1 `yki/` — PC tarafı yazılımı (Python 3.10+, pyserial, cobs)

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
- `rtk_rtcm_fragment_ve_gonder()`: msg_id artır, **238**'lik dilimlere böl,
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
- **Uçuş kontrolcüsü parametre notu — DÜZELTİLDİ (30 Temmuz).**

  Burada önce **ArduPilot** parametreleri yazıyordu (`GPS_TYPE=9`,
  `CAN_P1_DRIVER=1`, `CAN_D1_PROTOCOL=1`, `GPS_INJECT_TO=127`). **Bu filo için
  geçersiz:** ölçüldü, kartlar **PX4 Pro 1.16.1** koşuyor (params dosyası
  başlığı: `Stack: PX4 Pro`). O parametreler PX4'te yok; arayan kişi hiçbirini
  bulamaz ve yanlış yerde arar.

  PX4 karşılıkları (Here4 = DroneCAN GPS):

  | parametre | değer | ne yapar |
  |---|---|---|
  | `UAVCAN_ENABLE` | 2 | DroneCAN açık (sensör + ESC) |
  | `UAVCAN_SUB_GPS` | 1 | Here4'ten GPS alınır |
  | `UAVCAN_SUB_GPS_R` | 1 | GPS relative/RTK aboneliği |
  | **`UAVCAN_PUB_RTCM`** | **1** | **PX4'ün MAVLink'ten aldığı RTCM'i DroneCAN veriyoluna yayınlaması** |
  | `GPS_1_CONFIG` / `GPS_2_CONFIG` | 0 | seri GPS kapalı (GPS DroneCAN'de) |
  | `UAVCAN_BITRATE` | 1000000 | CAN hızı |

  **`UAVCAN_PUB_RTCM` bu zincirin son halkası ve sessizce kopuyor.** 0 iken:

      u-blox -> YKİ -> mesh -> RPi -> MAVROS -> PX4     buraya kadar AKAR
      PX4 -> DroneCAN -> Here4                          AKMAZ

  Semptomu sinsi: `px4_bridge` "RTCM enjekte ettim" der, sayaçlar artar, hiçbir
  hata çıkmaz — yalnızca `gps_fix_type` 4'te (DGPS) kalır, 5/6'ya (Float/Fixed)
  çıkmaz. 30 Temmuz'da ölçüldü: ylp00'da 1, **ylp02'de 0**; ylp02'nin RTCM'i
  Here4'e hiç ulaşmıyordu.

  > PX4'te `UAVCAN_*` parametrelerinin çoğu **reboot ister** — UAVCAN sürücüsü
  > yayıncılarını açılışta kurar. Değiştirdikten sonra FCU yeniden başlatılmalı.
  > FCU reboot'u MAVLink yayın hızlarını da sıfırlar, o yüzden
  > `mesaj_hizlari.py` tekrar çalıştırılmalı (ya da konteyner yeniden
  > başlatılmalı — `baslat.sh` bunu sırayla yapıyor).

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
   - Bu, **güvenlik state'i tutarlıyken** geçerlidir (§1). Normal kapat-aç
     müdahalesiz toparlanır: gönderici yeni (daha büyük) session_id ile gelir,
     alıcı kabul edip persist eder.
   - **Beklenen fail-closed davranışları** (bunlar hata değil, tasarım): bir
     node'un NVS'i silinmişse diğerleri onu kalıcı reddeder; NVS açılamıyorsa
     veya boot sayacı 65535'i aştıysa firmware başlamaz. Test bunları
     "toparlanmadı" diye raporlamamalı — §2.4'e ve §3.1'deki kurtarma
     prosedürüne bakın.

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
- ❌ **VERİ AKIŞI'nda** kalıcı state / kaldığı yerden devam mantığı (stateless
  tasarım şart) — yarım RTCM mesajı, yarım reassembly reboot'ta düşer.
  - ✅ İstisna (F1, bilinçli): **GÜVENLİK STATE'İ** kalıcıdır ve kalıcı olmak
    zorundadır — anti-replay'in NVS'te tuttukları (gönderici monoton boot
    sayacı, alıcının peer→session kaydı). **Bunu "stateless kuralına aykırı"
    diye sökmek bir güvenlik gerilemesidir**: kalıcı olmazsa saldırgan alıcıyı
    reboot ettirip eski session'ı oynatarak reboot-replay'i geri açar.
    Ayrım ve gerekçe §1'de ("Bu state kaybolursa veri mi kaybolur, koruma mı?").
- ❌ Port yollarını hardcode etme (PC/Pi seri port yolları; ESP GPIO pinleri hariç).
- ❌ Sadece test için var olan, üretimde çalışmayan kod yolları (bkz §4.5
  passthrough reddi).
- ❌ **Node başına ayrı anahtar / anahtar değişimi (key exchange) / çalışma-zamanı
  anahtar rotasyonu** eklemek. Tüm sürü (baz + her drone) **tek bir paylaşılan
  AES-128-GCM anahtarını** kullanır: NVS `mesh_sec/aes_key`, KEY WRITER ile her
  karta AYNI değer yazılır (§3.1, `encryption.h::aes_init()`).
  - **⚠️ AÇIKÇA KABUL EDİLEN RİSK:** bir drone düşer ve ele geçirilirse, NVS'ten
    çıkarılacak anahtar **tüm ağı** açar — hem trafiğin çözülmesi hem de geçerli
    (GCM tag'i tutan) sahte paket üretilmesi mümkün hale gelir. Anti-replay bunu
    **durdurmaz**: saldırgan meşru bir gönderici gibi yeni session/paket_id
    üretebilir. Per-peer anahtar bu yarıçapı daraltırdı; bilinçli olarak alınmadı.
  - **Gerekçe:** ESP-NOW'ın kendi peer şifrelemesi kullanılmadığı için
    (`peer.encrypt=false`, app-layer GCM) peer-limiti argümanı geçersiz — ama
    key exchange'in kendisi boot'a karmaşıklık, yeni fail-closed yolları ve yeni
    bir saha prosedürü ekler. Aşağıdaki koşul geçerliyken kazanç marjinaldir.
  - **KABULÜN DAYANDIĞI KOŞUL — asıl kırılma burada olur:** **tüm node'lar
    fiziksel kontrol altındadır** (uçuş öncesi/sonrası sayılır, saha ekibinde
    kalır, kaybedilen kart aranır). Kabul "tek anahtar yeterlidir"e DEĞİL, bu
    koşula dayanır.
  - **Koşul bugün NEDEN geçerli (TEKNOFEST 2026 şartnamesi):** yarışma ortamı
    bu koşulu kendisi sağlıyor — **sinyal karıştırma diskalifiye sebebi**, uçuş
    alanı **çevrili**, ve alanda **gizli hakemler** var. Yani anahtarı ele
    geçirmek için gereken fiziksel erişim, yarışma kuralları tarafından zaten
    dışlanmış durumda. Kabul bu ortama özgüdür.
  - **Koşul değişirse madde YENİDEN AÇILMALI.** Somut kırılma senaryoları: kart
    kaybı; üçüncü tarafa teslim; uzun süreli gözetimsiz depolama; dış ekiple
    ortak uçuş; **ve en önemlisi — yarışma dışına çıkıp gerçek bir saha
    görevine geçmek** (orada ne çevrili alan, ne hakem, ne de karıştırma yasağı
    vardır). Koşulu kontrol etmeden bu maddeye dayanmayın.
  - **Kompromis/şüphe hâlinde prosedür:** anahtar **tüm sürüde** döndürülür —
    `python tools/nvs_key_gen.py` ile yeni anahtar üretilir, KEY WRITER ile baz
    + her drone'a yazılır. Bu, "zarf formatı değişirse hepsini aynı gün flaşla"
    ile aynı operasyonel pencere; ayrıca planlanacak bir iş değil.
  - **Kısmi rotasyon YOKTUR:** eski anahtarlı bir node mesh'e katılamaz (GCM tag
    tutmaz). Sahada bu, alıcının `[RTK] kayip (gcm=...)` sayacının artması olarak
    görünür — anahtar uyumsuzluğunu RF kaybından ayıran işaret budur.
- ❌ **Pi→mesh yönünde GENEL (tipler-üstü) bir gönderim tavanı** — *şimdilik.*
  Hız limiti **tip BAŞINADIR** (`mesh_config.h::mesh_tip_gecebilir()`; her tip
  50 ms, `TIP_KOMUT` 200 ms). Tipler-üstü ikinci bir tavan YOKTUR.
  - **Neden tip başına:** eskiden TEK paylaşılan damga vardı ve tipler
    birbirinin bütçesini yiyordu — `TIP_QR_DATA` (tek atımlık, s.13 cezalı),
    50 ms içinde çıkan bir POSE/LEADER_HB yüzünden **sessizce** düşebiliyordu.
    Kapının amacı "hatalı Pi mesh'i boğmasın"dı; tiplerin birbirini yemesi
    amaç değil, yan etkiydi.
  - **⚠️ BİLİNEN BEDELİ — açıkça:** tip başına geçmek, en kötü durumdaki
    **TOPLAM** tavanı ~20 msg/s'den (eski tek kapı) **~180 msg/s**'ye çıkardı
    (9 tip × 20/s). **CSMA bunu KURTARMAZ:** `_mesh_gonder()`'in 0–10 ms
    rastgele beklemesi ortalama 5 ms → ~200 msg/s fiziksel tavan; 180/s onun
    hemen ALTINDA ve gerçekten ulaşılabilir. "CSMA geri basınç sağlar" argümanı
    bu senaryoda **ısırmaz** — bağlayıcı kısıt CSMA değil, kapının kendisidir.
  - **Gerçekleşirse ilk kurban RTK olur:** 180/s'te `loop()` saniyede ~900 ms'yi
    `vTaskDelay`'de geçirir; `rtk_mesh_loop()`/`mesh_loop()` açlığa düşer ve
    500 ms'lik reassembly timeout'u ilk patlayan yer olur. Yani kaçak bir Pi,
    mesh'i yormaktan önce **RTK fix'ini öldürür**.
  - **KABULÜN DAYANDIĞI KOŞUL:** gerçek Pi trafiği tavanın ~10 katı altında
    (POSE ~10 Hz + DURUM ~2 Hz + seyrek olaylar ≈ 12 msg/s). Sorun **teoriktir**.
  - **Koşulu izleyen şey ZATEN VAR:** `mesh_tip_dusen_yazdir()` düşen çerçeveyi
    **tip bazında** sayar ve 10 sn'de bir basar. Kaçak Pi artık sessiz değil.
  - **Yeniden aç:** sayaçlarda **beklenmedik bir tipte** düşme görülürse (gerçek
    trafik tavana yaklaşıyor demektir), o gün ~10 ms'lik **gevşek bir genel
    tavan** eklenir — tipler birbirini yemez ama toplam da sınırlanır. Karar
    tasarıma değil, **sayaca** bağlıdır.
- ❌ **Baz (YKİ) linki koptuğunda otonom görevi kesmek / RTL-LAND tetiklemek.**
  ESP'de `son_paket_ms`, bilinen HERHANGİ bir node'dan gelen pakette tazelenir —
  komşu drone trafiği dahil. Yani "baz öldü ama sürü yaşıyor" durumunda failsafe
  merdiveni (3s/8s/15s) **bilerek ateşlemez**. Bu bir boşluk DEĞİL, Görev 1'in
  gereğidir.
  - **Gerekçe (TEKNOFEST 2026 şartnamesi):** Görev 1, s.14 — *"Hakemler görev
    sırasında herhangi bir anda yer kontrol istasyonu bağlantısını **kesecektir**."*
    ("kesebilir" değil.) Tablo 5 ceza kalemi: **Yer İstasyonu Bağlantısı
    Kesilememesi → −50** — tablodaki en ağır kalem. Aynı yöne bakan s.17:
    *"Dağıtık sürü algoritması kullanılması gerekmektedir; merkezi sürü
    algoritmaları eksik puan."* Baz linkinin ölmesi bir arıza senaryosu değil,
    **sınavın kendisidir**.
  - **⚠️ BU MADDEYİ "EKSİK" SANIP KAPATMAYA KALKMA.** `son_paket_ms`'in yanına
    `son_baz_paket_ms` koyup RTL/LAND kararını ona bağlamak teknik olarak ~5
    satırdır, `mac_to_id()` ve `BAZ_MESH_ID` zaten hazırdır ve kod incelemesinde
    "eksik emniyet" gibi görünür. Yapılırsa: hakem linki kestiği saniyede TÜM
    sürü aynı anda RTL'e geçer → −50 + görev kaybı. Bug değil, spec.
  - **Kapsam sınırı (pi_bridge):** `link_ok` DOĞRU raporlamalı (baz-özel liveness
    `_komsu_son_goruldu` ile — bkz F3), ama **otonom görev devamını gate'lemesin**.
    Aksi halde ESP'de yapmaktan kaçındığımız hata bridge'de tekrarlanır.

### 5.1 Üç ayrı link — KARIŞTIRMA (emniyet katmanı bizde DEĞİL)

Şartname üç ayrı bağlantıdan bahsediyor. Bunları tek torbaya koymak, yukarıdaki
RTL kararının yanlış anlaşılmasının kök nedenidir:

| Link | Kim taşıyor | Koptuğunda | Kaynak |
|---|---|---|---|
| **RC kumanda** (her İHA'ya ayrı, ayrı pilot, kill switch) | Pixhawk / RC radyosu | **5 sn → Land**, zorunlu, teknik kontrolde test edilir | s.18, s.24/9 |
| **YKİ ↔ baz** | **bizim mesh (ESP32)** | Görev 1'de **kasten kesilir**, sürü devam etmeli | s.14, Tablo 5 |
| **Droneler arası mesh** | **bizim mesh (ESP32)** | Sürü bütünlüğü — asıl bizim işimiz | s.17 |

> **Kural cümlesi:** *"Kumanda bağlantısı koptuğunda 5 sn → Land"* şartname
> maddesi **RC radyosunu** kastediyor (*"araç radyolarının sinyal kaybında
> otomatik fail-safe"*), **bizim mesh'imizi değil**.
>
> **Bizim mesh bir GÖREV yolu, EMNİYET yolu değil.** Emniyet zaten zorunlu
> (mandated) bir RC katmanındadır ve bizden tamamen bağımsız çalışır. Bu,
> "ESP32 içeriği bilmez, sadece taşır" ilkesinin emniyet karşılığıdır:
> mesh'e emniyet sorumluluğu yüklemek, hem katman ihlali hem de Görev 1
> ihlalidir.

**Bunun sonucu:** ESP'deki failsafe merdiveni (3s/8s/15s), TÜM mesh öldüğünde
çalışan **ikincil ve gevşek** bir katmandır — birincil emniyet değildir. Onu
birincil sanıp sıkılaştırmak (baz-özel liveness, daha kısa eşik) yukarıdaki
−50 tuzağına yürümektir.

#### 5.1.1 Kör RTL'de çarpışma ayrımı — **ROS2/Pi sorumluluğudur, ESP'de DEĞİL**

TÜM mesh öldüğünde ESP 8 sn sonra RTL bildirir. Ama tam o anda droneler
birbirini duymuyordur — yani **çarpışma önleme verisi yoktur** ve eşzamanlı
"kör RTL" tam olarak Tablo 5'teki **çarpışma cezası (−20)** senaryosudur.
Çözüm (ör. `drone_id × 2 m` ile RTL irtifa ayrımı) gereklidir, **ama ESP'de
değil**:

- ESP, Pi'ye yalnızca `[0xFA][iha_id][failsafe_tip]` gönderir (`fail_safe.h::
  _failsafe_rpi_bildir`). **RTL'i ArduPilot uçurur**; irtifa ESP'nin tanım
  gereği bilmediği şeydir — "ESP içeriği bilmez, sadece taşır" ilkesinin ta
  kendisi. İrtifayı buraya koymak, F3'te reddettiğimiz katman ihlalinin aynısı
  olurdu (bkz yukarıdaki RTL maddesi).
- Pi **zaten kendi drone_id'sini bilir**; ayrımı yapmak için mesh'ten hiçbir
  bilgiye ihtiyacı yoktur — katman kayması bedava bile değildir.

> **Bu satır bilerek buradadır:** iki katmanın birbirine bakıp hiçbirinin
> yapmadığı boşluk (F3'te tam olarak bu yaşandı) tekrarlanmasın diye. ESP
> tarafı **yapmayacak**; sorumluluk ROS2/Pi tarafındadır ve orada takip
> edilmelidir.

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
