# 28–29 Temmuz 2026 — RTCM Dağıtım Zinciri Saha Günlüğü

RTK düzeltme verisinin (RTCM3) YKİ'den mesh üzerinden her iki İHA'nın
Pixhawk'ına kadar taşınması. Başlangıçta zincirin ~%85'i yazılmıştı ama
**hiç uçtan uca çalıştırılmamıştı**; çalıştırınca arka arkaya on bir kusur
çıktı.

**Gün sonu durumu:** RTCM taşıma zinciri uçtan uca doğrulandı.

```
125 RTCM mesajı yayınlandı  →  ylp00: msg=125 frag=125 kayıp=0
                            →  ylp02: msg=125 frag=125 kayıp=0
```

```
u-blox F9P → yki_rtcm_reader → ROS → esp32_bridge → USB-TTL → base ESP
                                                                  │ ESP-NOW (unicast)
                                                  ┌───────────────┴───────────────┐
                                                ylp00                           ylp02
                                                  │                               │
                                        RPi → esp32_bridge → px4_bridge → MAVROS → PX4
```

---

## 1. Bulunan kusurlar

Hepsi bu oturumdan **önce** vardı. RTCM hiç akmadığı için hiçbiri
görünmemişti. Sırası kabaca zincirdeki yerlerine göre.

### 1.1 Base ESP: `TIP_RTK` dispatch'te yok

`RX BASE/src/main.cpp` loop'undaki YKİ hattı whitelist'i `TIP_KOMUT`,
`TIP_RENK`, `TIP_DURUM`, `TIP_SWARM_STATE`, `TIP_QR_DATA`, `TIP_ORIGIN`,
`TIP_GOREV`, `TIP_GOTO` içeriyordu. `TIP_RTK` yoktu → çerçeve
`else: tanınmayan tip sessizce atılır` dalına düşüyordu. **Hata sayacı bile
artmıyordu.**

### 1.2 Ortak ayrıştırıcı tamponu 32 bayt

`uart_frame_parser.h::UART_FRAME_BUF_SIZE = 32`. Bir RTCM3 mesajı en fazla
1029 B; çerçeveye girince `TIP+ID+1029+CRC16 = 1033`, COBS ile ~1040 B.
Whitelist'e eklense bile her RTCM çerçevesi taşma dalında düşerdi.

Boyut artık derleme parametresi: RX BASE `-D UART_FRAME_BUF_SIZE=1100`,
TX DRONE 32'de kalıyor (drone'un RPi hattı büyük çerçeve taşımıyor).

### 1.3 `uart_frame_parser_t.idx` `uint8_t` idi — **gizli olan bu**

1.2'yi düzeltip bunu görmeseydik semptom "büyük çerçeveler bozuk geliyor"
olurdu ve teşhis RF'e giderdi. `idx` 255'te sarıyor, ama taşma kontrolü
(`idx < BUF_SIZE`) sarma sonrası **hep doğru** kalıyor: ayrıştırıcı
çerçeveyi baştan yazmaya başlıyor ve hiçbir sayaç artmıyor.

`uint16_t`'ye çıkarıldı. Regresyon testi eklendi
(`test_frame_parser_255_bayt_ustu_idx_sarmaz`) ve **dişli olduğu
doğrulandı**: eski `uint8_t` ile 8 assert patlıyor.

### 1.4 `loop()` başına 32 bayt okuma sınırı

Küçük mesh çerçeveleri (~27 B) için doğru, RTCM için değil: tek mesaj 32+
loop turu sürerdi ve `loop()` yayın yaparken CSMA beklemesi (0–10 ms)
barındırdığından tek mesaj yüzlerce ms'ye yayılırdı — RTCM'in 1 sn'lik
tazelik bütçesi orada biterdi.

`YKI_LOOP_MAKS_BAYT = 1200` yapıldı. Sınır **kaldırılmadı**: sınırsız okuma,
hat doygunken `mesh_loop()`/`rtk_mesh_loop()`'u aç bırakırdı.

> Bu sayı yük testinden geldi: base UART'tan ancak ~35 çerçeve/sn
> alabiliyordu (bkz §3).

### 1.5 Paylaşılan header'larda 39+ koşulsuz `Serial` çıkışı

`mesh_config.h` (21) + `rtk_handler.h` (12) + `fail_safe.h` (6) +
`rtk_sender.h`. Bazı derlemelerde `Serial` debug konsolu **değil**, binary
veri hattı:

| Derleme | `Serial` ne? |
|---|---|
| TX DRONE + `RPI_SERIAL0_MODU=1` | RPi'nin COBS hattı (460800) |
| RX BASE + `TEK_USB_MODU=1` | YKİ'nin COBS hattı (460800) |

Her printf düz metni binary akışın ortasına sokuyor; alıcı bir sonraki
`0x00`'a kadar biriktirdiği için metin mevcut çerçeveye yapışıyor ve o
çerçeve CRC'de düşüyor. 20 Temmuz'daki `crc_fail=3` bundandı.

RTCM ile teorik olmaktan çıkıyordu: `rtk_handler.h` **fragment başına** log
basıyor ve RTCM ~7 fragment/sn üretiyor.

**Çözüm:** `mesh_log.h` — `MESH_LOG_PRINT/PRINTLN/PRINTF`, `RPI_SERIAL0_MODU`
veya `TEK_USB_MODU` aktifken no-op. **Boot mesajlarına dokunulmadı** (mevcut
tasarımın bilinçli kararı: bir kez, mesh trafiği başlamadan önce basılıyorlar
ve MAC tablosu hatasını görmek kritik).

Doğrulama binary düzeyinde: `esp32dev_serial0`, `esp32dev`'den **2756 B**,
`esp32dev_tek_usb` ise **3208 B** daha az flash kullanıyor — susturulan log
string'leri binary'den düşmüş. Sahada ölçüm: 61 çerçeve, **0 CRC hatası**.

### 1.6 `rtk_mesh_loop()` yanlış porta yazıyordu

```c
// "Port varsayilani (Serial1) burada dogru: TX DRONE'da Serial1 Pi hattidir."
rtk_mesh_loop();          // argümansız → Serial1
```

Yorum `RPI_SERIAL0_MODU` eklenmeden **önce** doğruydu. O mod RPi hattını
Serial0'a taşıdı, bu çağrı yeri kaldı. Drone RTCM'i havadan alıyor, doğru
birleştiriyor, sonra **RPi'ye bağlı olmayan Serial1'e yazıyordu.**

Semptomun sinsiliği: baz "gönderdim" der, drone ESP'si "aldım" der, RPi'de
sayaç 0 kalır → teşhis doğal olarak RF'e yönelir.

### 1.7 `failsafe_kontrol()` — aynı hata, **emniyet yolunda**

```c
failsafe_kontrol();       // argümansız → Serial1
```

RX BASE bunu doğru yapıyordu (`failsafe_kontrol(YKI_SERIAL)`), TX DRONE
atlamıştı. Sonucu: mesh koptuğunda drone'un `0xFA` RTL/LAND bildirimi RPi'ye
**hiç ulaşmıyordu**; `esp32_bridge::_isle_failsafe` ateşlenmiyordu. Bu,
`RPI_SERIAL0_MODU` eklendiğinden beri kırıktı.

İkisi de `rtk_mesh_loop(RPI_SERIAL)` / `failsafe_kontrol(RPI_SERIAL)` oldu.

### 1.8 Seri port sahipliği çatışması

Bir seri portu tek süreç açabilir. Portu isteyen üç taraf vardı:
`esp32_bridge` (sahibi), `yki_rtcm_reader` (yazmak istiyor), **ve QGC**
(autoconnect ile kapıyor — sahada `Device or resource busy` olarak yaşandı).

`RX BASE/src/main.cpp` bunu zaten not etmişti: *"Aynı portu iki süreç açamaz
… birleşik süreç yazılana kadar Aşama 2."*

**Çözüm:** RTCM doğrudan porta değil **ROS topic'ine** gidiyor
(`/swarm/internal/rtcm`); `esp32_bridge` abone olup çerçeveleyerek yazıyor.
Port sahipliği tek elde kalıyor, çatışma yapısal olarak imkânsızlaşıyor.
Okuyucu **ayrı süreç** kalıyor: çökerse telemetri ve komut yolu etkilenmez.

### 1.9 RTCM topic ismi uyuşmazlığı — **zincirin son halkası**

```
esp32_bridge  yayınlıyor  →  /rtcm/in             (varsayılan, mutlak)
px4_bridge    dinliyor    →  /drone_{id}/rtcm/in  (ns = agent_id'den)
```

Hiç bağlanmıyorlardı ve `baslat.sh` de `rtcm_out_topic` parametresini
geçmiyordu. Base "185 mesaj gönderdim" derken drone'da sayaç 0 kalıyordu.

Varsayılan artık boş = `agent_id`'den türetilir. Parametreyi hatırlamak
zorunda kalmamak için: px4_bridge ad alanını agent_id'den ürettiği sürece
ikisi kendiliğinden eşleşir.

### 1.10 `yki_rtcm_reader` SIGTERM'i yok sayıyordu

Ana döngü `while True` idi. `yki_durdur.sh` düz `kill` (SIGTERM) kullanıyor →
okuyucu durmuyor, portu bırakmıyor, sonraki başlatma `Device or resource
busy` alıyordu. Sahada `kill -9` gerekti. Sinyal işleyici + temiz kapanış
eklendi.

### 1.11 `yki_baslat.sh` idempotent değildi

Çalışan örnekleri kontrol etmeden yenilerini başlatıyordu. Art arda birkaç
başlatmadan sonra ölçüldü: **12 tane `esp32_base`**, 22 origin yayıncısı —
hepsi aynı seri portu istiyor, biri tutuyor, diğerleri saniyede bir hata
döngüsünde. Sahada teşhisi çok zor bir "bazen çalışıyor" arızası olurdu.
Script artık önce `yki_durdur.sh` çağırıyor.

---

## 2. Tasarım değişikliği: RTCM artık unicast

`rtk_mesh_gonder()` broadcast yapıyordu. RTCM'e özgü gerekçeyle unicast'e
çevrildi:

Broadcast'te 802.11 ACK yoktur; kaybolan paket telafi edilmez. Normal
telemetride kabul edilebilir (POSE/DURUM periyodiktir, kayıp bir sonraki
turda kapanır). **RTCM'de kapanmaz:** mesaj N parçaya bölünmüştür ve TEK
parçanın kaybı mesajın TAMAMINI öldürür (reassembly timeout'a düşer). Yani
kayıp olasılığı parça sayısıyla çarpılır.

Hedefler mesh'in canlı node tablosundan (`_bilinen_nodlar`) geliyor —
kapalı/menzil dışı drone'a boşuna retry harcanmıyor. Hiç canlı node yoksa
broadcast'e düşülüyor (soğuk başlangıç).

**CSMA beklemesi fragment başına bir kez** uygulanıyor, hedef başına değil:
aynı fragment'ı N hedefe yollarken N kez rastgele beklemek gecikmeyi N'e
katlar ve hiçbir şey kazandırmaz — 802.11 MAC her çerçeve için kendi
çekişmesini zaten yapıyor.

---

## 3. Mesh yük testi

RTCM eklemeden önce mesh'in yük altındaki davranışı ölçüldü. Yük base'den
verildi (RTCM'in kullanacağı yön), yalnız zararsız tipler (`TIP_ORIGIN`,
`TIP_DURUM`) — uçuş komutu taşıyan topic'lere dokunulmadı.

| | alınan/sn | gönderilen/sn | CRC | drop | komşu | link_ok |
|---|---|---|---|---|---|---|
| TABAN | 14.8 | 1.0 | 0 | 0 | 2 | %100 |
| YÜK (50 msg/sn) | **14.7** | **35.1** | **0** | **0** | 2 | %100 |
| TOPARLANMA | 14.6 | 1.0 | 0 | 0 | 2 | %100 |

ESP'nin kendi sayaçları: `crc_hatasi=0 paket_dustu=0`, `Aktif: 2/8` — test
boyunca değişmedi.

**Kritik sonuç:** yük 35 kat arttığı halde gelen telemetri etkilenmedi
(14.8 → 14.7). `mesh_config.h`'deki "kaçak bir Pi mesh'i boğarsa ilk kurban
RTK olur" endişesi gerçekleşmedi.

`tip0x08` hız-limiti sayacının artması **arıza değil**: `TIP_ORIGIN` kasten
25 Hz'de basıldı, ESP'nin 50 ms'lik tip başına kapısı fazlasını eledi ve
bunu **sayarak** yaptı. Diğer tiplerde hiç düşme yok — tip başına limite
geçme kararı burada karşılığını verdi.

### 3.1 Yanlış başlayan ilk deneme — QoS tuzağı tekrarladı

İlk yük denemesi `ros2 topic pub` ile yapıldı ve hiç bağlanmadı:
`ros2 topic pub` **VOLATILE** yayınlıyor, `_ORIGIN_QOS` ise
**TRANSIENT_LOCAL**. İkisi hiç bağlanmaz ve **hata da vermez** — 20 Temmuz
§7.7'nin birebir tekrarı. Doğru QoS'lu rclpy üreteci yazılıp tekrarlandı.

Yeni eklenen `_RTCM_QOS` bu yüzden açıkça yazıldı ve gerekçesi yorumda:
varsayılana güvenmek bu projede iki kez yandı.

---

## 4. Ölçümler

| Ölçüm | Değer |
|---|---|
| Uçtan uca RTCM (ylp00) | 125 gönderildi / **125 alındı**, kayıp 0 |
| Uçtan uca RTCM (ylp02) | 125 gönderildi / **125 alındı**, kayıp 0 |
| Base ESP fragmantasyon | `mesaj=185 frag=185`, tüm hata sayaçları 0 |
| Drone RPi hattı (flash sonrası) | 61 çerçeve, **0 CRC hatası** |
| Firmware birim testleri | 32/32 (ASan + UBSan) |
| Hedef derleme | 4/4 env, sıfır uyarı |
| RAM / Flash (RX BASE) | %16.7 / %56.7 |

Fragment sınırları test edildi: 106 B (1 parça), 238 B (tam bir parça),
239 B (bir bayt taşar → 2), 406 B (2), 1029 B (en büyük RTCM3 → 5).

---

## 5. Tuzaklar — sahada tekrar karşımıza çıkabilecekler

### 5.1 `ping` bu ağda güvenilmez

ylp02 saatlerce "ağda yok" sanıldı; `arp-scan` onu anında buldu ve SSH
çalıştı. Drone'lar ICMP'ye cevap vermiyor. **Tarama için `arp-scan` kullan,
`ping` ile "yok" hükmü verme.**

### 5.2 `pkill -f` kendi kabuğunu öldürüyor

`pkill -f "esp32_base"` çalıştıran komut satırının kendisi de deseni içerdiği
için kabuk ölüyor. Köşeli parantez numarası: `pkill -f "esp32[_]base"`.

### 5.3 `/tools` dizini `.gitignore`'da

`.gitignore:352` bütün `/tools`'u yok sayıyor. Oraya konan yeni bir script
**sessizce commit'lenmez**. `f9p_base_yapilandir.py` bu yüzden
`src/gcs/backend/rtcm/` altına alındı.

### 5.4 ROS setup.bash zsh altında bozuluyor

`source /opt/ros/jazzy/setup.bash` zsh'ta kendi yolunu bulamıyor ve
`ament_cmake` bulunamıyor. `colcon build` her zaman `bash -c` içinde.

### 5.5 `timeout ros2 topic echo` apport çökme raporu üretiyor

SIGTERM'de `ros2` CLI çöküyor ve masaüstünde "System program problem
detected" popup'ı çıkıyor. Zararsız ama korkutucu. `--once` kullan ya da
düzgün kapanan bir rclpy script'i yaz.

### 5.6 CP2102 portunu açmak ESP'yi resetliyor

`dtr=False`/`rts=False` ile açmak denendi, **tutmadı**. Base ESP'nin
konsolunu izlerken bunu hesaba kat; portu tekrar tekrar açıp kapatmak
kartı sürekli resetler ve 10 sn'lik istatistik periyoduna hiç ulaşamazsın.
Bir kez aç, bırakma.

---

## 6. Yarına kalanlar

### Kod tarafı — bitti
Kalan bir şey yok. Dört firmware env'i ve ROS paketi derleniyor, testler
geçiyor, iki drone'a ve base'e yüklendi.

### Donanım / saha
1. **u-blox base modu.** Modül fabrika ayarında, sadece NMEA basıyor
   (`TMODE=0`, hiçbir RTCM mesajı açık değil). `MOD=NEO-F9P`, `PROTVER=27.40`
   → yapılandırma arayüzü destekleniyor. `src/gcs/backend/rtcm/f9p_base_yapilandir.py`
   yazıldı ve salt-okunur modda doğrulandı. **Survey-In açık gökyüzü
   gerektirir**, kapalı alanda yakınsamaz.
2. **RTK Fixed doğrulaması.** GPS fix 3D → Float → Fixed.
3. **ylp00 pusulası.** Alan büyüklüğünü 16.9 µT okuyor (Elazığ'da ~47
   olmalı), ylp02 46.8 µT ile doğru. İki kez kalibre edildi, düzelmedi.
   Manyetik gürültü **değil** (ylp00 std 0.07 µT ile en sessiz kart).
   Kalibrasyon değerlerinin mertebesi iki kartta farklı → Here4 ünitelerinin
   firmware/donanım revizyonu farklı olabilir. **Takas testi** önerildi:
   üniteleri değiştirip ölçmek, sorunun cihazla mı gövdeyle mi gittiğini
   kesin söyler.
   > Pusula RTK'yı **engellemiyor** — RTK Fixed tamamen GNSS faz ölçümüne
   > dayanır. Pusula formasyon ve heading için gerekli.

### Doküman borcu
`docs/YELPENCE_RTCM_SPEC.md` hâlâ **REV B** ve şunları yanlış anlatıyor:
şifreleme var (kaldırıldı), fragment 191 B (238), broadcast (unicast), RTCM
adanmış UART'tan gelir (YKİ veri hattından `TIP_RTK` olarak gelir), YKİ
doğrudan seri porta yazar (ROS topic'ine yayınlar). Spec'in kendi kuralı:
*"kod ile spec çelişirse kod kazanır ve spec bug'dır — bildir."* Bildirildi,
REV C güncellemesi bekliyor.
