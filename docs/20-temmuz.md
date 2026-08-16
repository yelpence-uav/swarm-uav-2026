# 20 Temmuz 2026 — Saha Kurulum Günlüğü

> ## ⚠️ ARŞİV — GÜNCEL DEĞİL, buraya yazma
>
> **20 Temmuz saha günlüğü.** Tarihsel kayıt; **bugünün durumunu anlatmaz.**
>
> **Güncel durum:** [`DURUM.md`](DURUM.md) ·
> **Güncel plan:** [`PLAN.md`](PLAN.md) ·
> **Güncel iş listesi:** [`YAPILACAKLAR.md`](YAPILACAKLAR.md)
>
> Hâlâ değerli olan: Ölçümler ve o günün kararları. Buradan bir bilgi kullanacaksan
> **önce koda bakıp doğrula** — o gün doğru olan bugün yanlış olabilir.
> Çelişki varsa **canlı belge kazanır**.


Yeni YKİ laptopunun sıfırdan kurulması, ESP32 mesh'in iki kartla ayağa
kaldırılması ve Pixhawk'tan YKİ arayüzüne kadar uçtan uca telemetri zincirinin
kanıtlanması.

**Gün sonu durumu:** zincirin tamamı çalışıyor, YKİ `Drone 1: bagli=True`
görüyor.

```
Pixhawk (PX4) → MAVROS → px4_bridge → agent_fsm
   → esp32_bridge (RPi) → ((( ESP-NOW / AES-128-GCM )))
   → esp32_bridge (baz) → YKİ backend → arayüz
```

---

## 1. Donanım envanteri

| Cihaz | Kimlik | Bağlantı |
|---|---|---|
| YKİ laptop | Ubuntu 24.04, x86_64 | — |
| Baz ESP32 | `A4:F0:0F:64:B5:34` | laptop USB (`/dev/ttyUSB0`) |
| Drone ESP32 | `B0:CB:D8:C8:A8:30` | RPi UART (`/dev/ttyAMA4`) |
| Raspberry Pi 5 | RPi OS Lite (Debian 13), 8 GB | `10.207.118.134` |
| Pixhawk 2.4.8 | PX4 firmware | RPi `/dev/ttyAMA0` @ 115200 |

RPi OS Lite bilinçli tercih: `libcamera` yığını burada native çalışıyor, Görev
1'in QR okuma yolu buna bağlı. Ubuntu'ya geçmek kamerayı riske atardı.

---

## 2. YKİ laptopu kurulumu

Simülasyona ihtiyaç kalmadığı için Docker'sız, native kurulum yapıldı.

```bash
# ROS 2 Jazzy (ros-base yeterli, desktop/Gazebo gerekmez)
sudo apt install ros-jazzy-ros-base ros-jazzy-rmw-cyclonedds-cpp \
     python3-colcon-common-extensions python3-rosdep python3-venv git-lfs

# MAVROS (swarm_control bağımlılığı)
sudo apt install ros-jazzy-mavros ros-jazzy-mavros-extras \
     ros-jazzy-mavros-msgs ros-jazzy-geographic-msgs
sudo /opt/ros/jazzy/lib/mavros/install_geographiclib_datasets.sh

# Python ortamı
python3 -m venv ~/gcs-venv
pip install -r src/gcs/backend/requirements.txt
pip install "numpy<2.0.0" pytest lark flake8

colcon build --symlink-install    # 7/7 paket
cd src/gcs/frontend && npm install
```

**GeographicLib veri setleri atlanamaz** — `mavros_node` açılışta istisna ile
ölür.

`numpy<2.0.0` ve `lark` GCS'in `requirements.txt`'inde yok, projenin genel
`src/requirements.txt`'inden geliyorlar. Native kurulumda elle eklendi.

### Ortam betikleri

- `~/yki_env.sh` — ROS + workspace + venv (sıra kritik: ROS → workspace → venv)
- `~/yki.sh` — tek komutla backend + arayüz (`mock` argümanıyla sahte veri)
- Masaüstünde `YKI_BASLATMA.txt` — adım adım terminal rehberi

### Doğrulama

- `colcon test`: swarm_control 80/80, swarm_state_machine 133/133
- Mock uçtan uca: telemetri, WebSocket, TriggerMission (ABORT→disarm,
  START→arm+10 m), QR koordinat yayını

---

## 3. Firmware değişiklikleri

Büşra'nın `feature/esp32-mesh-firmware` branch'i gün içinde main'e alındı
(PR #105). Değişiklikler main tabanlı `feature/mesh-tek-usb-saha` üzerinde.

### 3.1 RX BASE — tek-USB modu (`TEK_USB_MODU`)

YKİ tarafında USB-TTL adaptör olmadığı için telemetri/komut hattı `Serial2`
(GPIO25/26) yerine kartın kendi USB portuna (`Serial0`) taşındı.

- `YKI_SERIAL` makrosu: `Serial2` (varsayılan) ↔ `Serial` (tek-USB)
- Loop içi debug printf'leri susturuldu (`DBG_*`) — binary COBS akışına
  karışıp CRC hatası üretiyorlardı
- Boot'taki `'T'` kanal taraması atlanıyor — YKİ'nin ilk komut baytlarını
  yutuyordu
- **Tek-USB modunda `Serial1` (RTCM) hiç açılmıyor.** Açık kalırsa GPIO16
  floating kalıyor, gürültüyü çerçeve sanıp `rtk_serial_isle()` her hatalı
  çerçevede `Serial.println("[RTK-RX] HATA...")` basıyor ve hat %100 doluyor
  (ölçüldü: 11.6 kB/s, 115200 tavanı). Bu modda RTCM yolu yok, ihtiyaç da yok.

Derleme: `pio run -e esp32dev_tek_usb`

### 3.2 TX DRONE — Serial0 modu (`RPI_SERIAL0_MODU`)

RPi hattı `Serial1` (GPIO18/19) yerine kartın `RX`/`TX` yazan pinlerine
(GPIO3/GPIO1) alındı. Gerekçe: GPIO18/19 üzerinden veri geçmedi, Serial0
pinlerinin çalıştığı ise daha önce QGC testiyle biliniyordu.

**Bedeli:** firmware yüklerken RPi kablolarının sökülmesi gerekiyor (aynı
pinler USB-seri çeviriciyle paylaşımlı).

Derleme: `pio run -e esp32dev_serial0`

Her iki modda da Büşra'nın orijinal tasarımı varsayılan olarak korunuyor,
geçiş derleme bayrağıyla yapılıyor.

### 3.3 MAC adresleri

`drone_tablo[]` gerçek MAC'lerle dolduruldu (her iki firmware'de):

```c
{{0xB0, 0xCB, 0xD8, 0xC8, 0xA8, 0x30}, 1},            // drone
{{0xA4, 0xF0, 0x0F, 0x64, 0xB5, 0x34}, BAZ_MESH_ID},  // baz (TX DRONE'da)
```

Drone 2-4 satırları **yoruma alındı**. Placeholder MAC açık kalırsa
`mac_to_id()` sahte bir adrese ID verir ve olmayan bir drone mesh'te "aktif"
görünüp komşu sayısını şişirir.

### 3.4 Yeni araçlar

- `tools/mac_reader/` — ESP32'ye yüklenip MAC okuyan PlatformIO projesi,
  firmware'e yapıştırılacak satırı hazır formatta veriyor
- `KEY WRITER/src/main.cpp` — AES anahtarını NVS'e yazan sketch (gitignore'lu,
  içinde açık anahtar var). Geri okuma doğrulaması ve parmak izi logu eklendi;
  anahtarın kendisi seri porta basılmıyor.

---

## 4. AES provision

Test anahtarı: `tools/nvs_key_gen.py` ile üretildi, `tools/aes_key.txt`'te
(gitignore'lu). **Yarışma öncesi ekibin ortak anahtarıyla değiştirilmeli** —
farklı anahtarlı kart mesh'e katılamaz (GCM tag düşer, paket sessizce atılır).

NVS sözleşmesi: namespace `mesh_sec`, key `aes_key`, 16 bayt.

---

## 5. ROS 2 tarafı değişiklikleri

### 5.1 `packet_parser.py` — eksik iki mesaj tipi

Firmware `TIP_SWARM_STATE (0x0D)` ve `TIP_QR_DATA (0x0E)` tiplerini taşıyordu
ama Python tarafı tanımıyordu. Sonuç: **YKİ'nin QR paneli ve sürü durumu
paneli mesh üzerinden hiç dolmuyordu.** Şartname §5.1'e göre QR'ın görev
boyunca en az bir kez YKİ'de görünmesi zorunlu (cezalı kalem).

Eklendi: tip sabitleri, `SwarmStateVeri`/`QrVeri` dataclass'ları,
`swarm_state_coz/paketle`, `qr_data_coz/paketle`. Payload formatları firmware
ile birebir (`<BBBBI8x` ve `<BIii3x`, ikisi de tam 16 bayt).

### 5.2 `esp32_bridge_node.py` — her iki uç

| Yön | Topic |
|---|---|
| Mesh → ROS (YKİ'de) | `/swarm/public/state`, `/swarm/public/perception/qr_data` |
| ROS → Mesh (drone'da) | `/swarm/internal/state`, `/swarm/internal/perception/qr_data` |

**Yakalanan QoS hatası:** `SwarmState` publisher'ı ilk yazımda `BEST_EFFORT`
idi, YKİ ise `RELIABLE` dinliyor. DDS'te bu ikisi **hiç bağlanmaz ve hata da
vermez** — panel sessizce boş kalırdı. `_EVENT_QOS`'a (RELIABLE/VOLATILE)
çevrildi.

Ayrıca `_seri_ac()` içine `reset_input_buffer()` eklendi: port kapalıyken
biriken bayat yığın açılışta işleniyordu.

### 5.3 Bilinen sınırlama — QR içeriği

Mesh payload'ı 16 bayt, `QRMissionData` 30+ alanlı. Mesh'ten sadece "kim,
hangi QR, nerede" geçiyor; formasyon tipi, manevra açıları, bekleme süresi
geçmiyor. Bu yüzden `valid=False` set ediliyor — `True` olsaydı `mission_fsm`
eksik veriyi icra edilebilir görev sanabilirdi.

Şartnamenin "QR YKİ'de görünmeli" şartı bu özetle karşılanıyor. Tam içerik
isteniyorsa ikinci bir paket tipi ya da `action_id`'ye bit-packing gerekir —
**Büşra ile konuşulacak tasarım kararı.**

### 5.4 Testler

`test_esp32_qr_swarmstate.py` — 11 test (payload boyutu, alan sırası,
gidiş-dönüş, negatif koordinat, çerçeve entegrasyonu). swarm_control toplam
**91/91** geçiyor.

---

## 6. Raspberry Pi 5 kurulumu

Debian 13 (trixie) için ROS 2 Jazzy binary paketi yok (Jazzy Ubuntu 24.04
hedefli). RPi OS Lite kamera için korunması gerektiğinden **Docker** seçildi.

```bash
sudo apt install docker.io
sudo usermod -aG docker $USER
docker pull ros:jazzy-ros-base          # arm64
docker build -t yelpence-ros .          # ~/yelpence_ws/Dockerfile
```

İmaj içeriği: `ros:jazzy-ros-base` + mavros / mavros-extras / mavros-msgs /
geographic-msgs / cyclonedds / pyserial / colcon + GeographicLib veri setleri.

Workspace `~/yelpence_ws` — `swarm_interfaces`, `swarm_control`,
`swarm_state_machine` (3/3 derlendi). Laptoptaki `packet_parser`
değişiklikleri dahil.

### Kalıcı servis

```bash
docker run -d --name drone1 --restart unless-stopped --network host \
  --device /dev/ttyAMA0 --device /dev/ttyAMA4 \
  -v ~/yelpence_ws:/ws yelpence-ros bash /ws/baslat.sh
```

`baslat.sh` sırayla: `mavros_node` → `px4_bridge` → `agent_fsm_node` →
`esp32_bridge`. RPi yeniden başlasa zincir kendiliğinden ayağa kalkıyor.

### UART yerleşimi (RPi 5)

| Cihaz | GPIO | Fiziksel pin | UART | Cihaz dosyası |
|---|---|---|---|---|
| Pixhawk | 14/15 | 8 / 10 | UART0 | `/dev/ttyAMA0` @ 115200 |
| Drone ESP32 | 12/13 | 32 / 33 | UART4 | `/dev/ttyAMA4` @ 460800 |

`/boot/firmware/config.txt`: `dtoverlay=uart4` → **`dtoverlay=uart4-pi5`**
olarak düzeltildi (yedek: `config.txt.yedek-*`).

---

## 7. Gün içinde çözülen tuzaklar

Sahada tekrar karşımıza çıkabilecekler. Sırası kabaca kaybedilen zamana göre.

### 7.1 `cat` baud rate ayarlamıyor — *(en pahalı hata, bana ait)*

`timeout 10 cat /dev/ttyAMA4 | wc -c` ile saatlerce "0 bayt" görüldü ve kablo
suçlandı. `cat` portun mevcut baud'unu kullanır, ESP ise 460800'de konuşuyordu.
Python ile doğru baud verilince veri hemen göründü.

**Kural:** seri hat testinde her zaman baud'u açıkça veren bir araç kullan
(`python3 -c "serial.Serial(port, baud)"`), `cat`/`wc` ile tanı koyma.

### 7.2 NVS erase tuzağı — *(Büşra'nın spec'inde belgeli)*

Her firmware yüklemesinden sonra NVS'i geri yazdığım için baz'ın `session_id`'si
sıfırlanıyordu. Drone onu daha yüksek bir session ile hatırlıyor ve gelen tüm
paketleri reddediyordu. Drone'un kendi logu birebir söylüyor:

```
[REPLAY] ESKI SESSION reddedildi: B5:34 sid=2 < kalici=5
[REPLAY] ^ sid cok dusuk: B5:34 NVS'i silinmis olabilir (erase tuzagi)
```

Semptom sinsi: **mesh kurulu görünür, "aktif node = 1" der, ama paketler
geçmez.** Spec bunu "duyar ama duyulmaz" diye tarif ediyor.

**Kurtarma (bu sefer uygulanan):** bazı arka arkaya resetleyerek `session_id`'yi
drone'un hatırladığının üstüne çıkarmak (her boot +1).
**Kalıcı çözüm:** sürünün tamamının NVS'ini birlikte sıfırlamak (spec §3.1).

### 7.3 `dtoverlay=uart4` ≠ `uart4-pi5`

RPi'nin kendi dokümanı (`/boot/firmware/overlays/README`):

```
Name: uart4        → GPIOs 8-11.  BCM2711 only.   (RPi 4)
Name: uart4-pi5    → GPIOs 12-13. Pi 5 only.      (RPi 5)
```

`/dev/ttyAMA4` vardı ama yanlış pinlere bakıyordu. Kablolama doğruydu, overlay
yanlıştı.

### 7.4 `Serial.setRxBufferSize()` UART0'da `begin()`'den önce çağrılamaz

Tek-USB modunda kart boot döngüsüne giriyordu (`entry 0x400805e4` → sürekli
`SW_RESET`, uygulama hiç başlamıyor). Büşra'nın orijinal firmware'i aynı kartta
sorunsuz açıldığı için ayırt edildi.

**Doğrusu:** `begin()` → `end()` → `setRxBufferSize()` → `begin()`.

### 7.5 ESP32 yüklemesi `--no-stub` gerektiriyor

Normal yükleme "chip stopped responding" ile kesiliyor. Tüm esptool/pio
çağrılarında `PLATFORMIO_UPLOAD_FLAGS=--no-stub`.

### 7.6 Kart üzerindeki `RX`/`TX` yazısı yanıltıcı

O pinler GPIO3/GPIO1 yani USB debug portu. Firmware `Serial1`'i GPIO18/19'a
atamıştı; "RX/TX yazan yere bağladım" ile veri geçmemesinin sebebi buydu.
Sonunda firmware Serial0'a taşındı (§3.2).

### 7.7 QoS uyumsuzluğu sessizdir

BEST_EFFORT yayıncı ↔ RELIABLE abone **hiç bağlanmaz, hata da vermez.**
Yeni bir publisher eklerken karşı ucun QoS'u mutlaka kontrol edilmeli.

### 7.8 `ros2 topic echo` varsayılanı RELIABLE

`/swarm/public/drone1/status` BEST_EFFORT olduğu için `echo` boş dönüyor —
topic çalışmıyor sanılmasın. `--qos-reliability best_effort` ekle, ya da
doğrudan tüketiciden (YKİ backend) doğrula.

---

## 8. Ölçümler

| Ölçüm | Değer |
|---|---|
| Baz USB hattı (RTCM düzeltmesi öncesi) | 11.611 bayt/s — **%100.8** |
| Baz USB hattı (sonrası) | 4.3 bayt/s — **%0.04** |
| Mesh telemetrisi (baz UART'ında, 15 s) | POSE 268, DURUM 15, MESH_DURUM 3 |
| `esp32_bridge` (RPi, canlı) | `alim_ok=93 crc_fail=3` |
| `agent_fsm` yayın hızı | 10 Hz |
| Firmware testleri (native) | 43/43 |
| swarm_control testleri | 91/91 |

`crc_fail=3` beklenen: Serial0 modunda debug metni binary akışa karışıyor,
desync-güvenli parser onları sessizce atıyor.

---

## 9. Gün sonu YKİ çıktısı

```
Drone 1: bagli=True  armed=False  mod=?  bat=%0  gps=0(0sat)  alt=-0.0m
Drone 2: bagli=False
Drone 3: bagli=False
```

Değerlerin sıfır olması normal: pil takılı değil, GPS fix yok. Telemetri
**yolu** çalışıyor, içeriği donanım hazır olunca dolacak.

---

## 10. Yarına kalanlar

### Kapatılacak borçlar

1. **Baz firmware'inde geçici `[TANI]` logu var** — kaldırılmalı. Yükleme
   sonrası §7.2'deki session resetini tekrarlamak gerekecek.
2. **Commit yok.** Laptopta duran değişiklikler:
   - `firmware/esp32_mesh/RX BASE/` — tek-USB modu, RTCM kapatma, tanı logu
   - `firmware/esp32_mesh/TX DRONE/` — Serial0 modu, MAC'ler
   - `src/swarm_control/.../packet_parser.py` — 0x0D/0x0E
   - `src/swarm_control/.../esp32_bridge_node.py` — publisher/subscriber + QoS
   - `src/swarm_control/test/test_esp32_qr_swarmstate.py` — 11 test
   - `firmware/esp32_mesh/PROVISION_PROSEDURU.md`
   - bu dosya
3. **RPi'deki kod laptoptan rsync ile gitti**, git takibinde değil. Kalıcı bir
   dağıtım yöntemi kararlaştırılmalı.

### Doğrulanmamış

- **Arayüz hiç görsel olarak kontrol edilmedi.** Backend'in veri gönderdiği
  kanıtlı, React'in doğru çizdiği değil.
- **Joystick (Görev 2)** — backend yolu test edildi, fiziksel joystick hiç
  takılmadı. `gamepad.ts` Xbox/PS eksen dizilimine göre yazılı; FLYSKY
  kullanılacaksa eksen haritası muhtemelen tutmaz.
- **GCS'in birim testi yok** (`src/gcs/` altında tek bir `def test_` yok).

### Büşra'ya sorulacaklar

1. Ana firmware ilk çalıştığında **NVS'i neden siliyor?** Ölçümle daraltıldı
   (yükleme masum, çalışma siliyor; partition tablosu ve bootloader iki
   projede md5 düzeyinde aynı; WiFi init hipotezi test edilip çürütüldü). Kök
   sebep hâlâ açık.
2. **QR'ın tam içeriği** mesh'ten nasıl geçmeli? 16 bayt yetmiyor (§5.3).
3. GPIO18/19 üzerinden neden veri geçmedi? Serial0'a taşındı ama kalıcı bedeli
   var (her yüklemede kablo sökme).

### Sıradaki iş

- Pile + GPS ile gerçek telemetri değerlerini görmek
- QR panelinin gerçek veriyle dolduğunu doğrulamak (şartname cezalı kalemi)
- Görev 2 joystick yolunu fiziksel kumandayla test etmek
