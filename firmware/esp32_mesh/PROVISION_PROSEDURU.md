# ESP32 Provision Prosedürü (saha notu)

Bir ESP32'yi sıfırdan mesh'e hazır hale getirme adımları. Sıra önemli —
"önce KEY WRITER, sonra ana firmware" şeklindeki sezgisel sıra **çalışmıyor**.

## Neden sıradan sapıyoruz

Ana firmware (RX BASE / TX DRONE) **ilk çalıştığında NVS'i siliyor**. KEY WRITER
anahtarı doğru yazıyor ve doğruluyor, ama ana firmware yüklenip bir kez
çalıştıktan sonra `mesh_sec` namespace'i tamamen kayboluyor. Semptom:

```
[CRYPTO] KRITIK HATA: NVS'de AES anahtari bulunamadi!
[CRYPTO] PROVISION BEKLENIYOR...
```

Ölçümle daraltıldı (2026-07-20, ESP32-D0WD-V3):

| Adım | NVS'te `aes_key` |
|---|---|
| KEY WRITER yüklendi + çalıştı | VAR |
| Ana firmware yüklendi, `--after no_reset` ile **çalıştırılmadı** | **VAR** |
| Ana firmware bir kez çalıştı | YOK |

Yani yükleme masum; NVS'i firmware'in çalışması siliyor. Partition tablosu ve
bootloader iki projede birebir aynı (md5 eşit), o yüzden sebep partition
uyumsuzluğu değil. WiFi init'in NVS'i formatladığı hipotezi de test edildi ve
**çürütüldü** (KEY WRITER'a WiFi eklendi, sonuç değişmedi). Kök sebep hâlâ açık
— Büşra'ya sorulacak.

Kabul edilen çözüm: **NVS'i ana firmware'den SONRA yaz.**

## Prosedür

Aşağıda `PIO=~/gcs-venv/bin/pio`. Seri porta erişim için `dialout` üyeliği
gerekiyor; oturum yenilenmediyse komutları `sg dialout -c "..."` içine al.

### 0. Yükleme bayrağı: `--no-stub` şart

Normal yükleme "chip stopped responding" ile kesiliyor. Tüm esptool/pio
çağrılarında `--no-stub` kullan:

```bash
PLATFORMIO_UPLOAD_FLAGS=--no-stub $PIO run -t upload --upload-port /dev/ttyUSB0
```

### 1. Anahtarı üret (bir kez, tüm sürü için ortak)

```bash
python3 tools/nvs_key_gen.py     # tools/aes_key.txt (gitignore'lu)
```

Çıkan hex'i `KEY WRITER/src/main.cpp` içindeki `SAHA_ANAHTARI`'na yapıştır.
**Tüm node'larda aynı anahtar olmalı**; farklı anahtarlı kart mesh'e katılamaz
(GCM tag düşer, paket sessizce atılır).

### 2. KEY WRITER'ı yükle, NVS imajını yedekle

```bash
cd "firmware/esp32_mesh/KEY WRITER"
PLATFORMIO_UPLOAD_FLAGS=--no-stub $PIO run -t upload --upload-port /dev/ttyUSB0
# monitörde "PROVISION TAMAMLANDI" ve "[OK] Anahtar yazildi ve dogrulandi" bekle

# NVS'i dosyaya al — sonraki adımda geri yazılacak
$PIO pkg exec -p tool-esptoolpy -- esptool.py --port /dev/ttyUSB0 \
    --baud 115200 --no-stub read_flash 0x9000 0x5000 nvs_anahtarli.bin
```

`nvs_anahtarli.bin` bu andan sonra **her kart için yeniden kullanılabilir** —
aynı anahtarı taşır. Sakla (repoya koyma, anahtar içerir).

### 3. Ana firmware'i yükle

```bash
cd "../RX BASE"      # ya da "../TX DRONE"
PLATFORMIO_UPLOAD_FLAGS=--no-stub $PIO run -e esp32dev_tek_usb -t upload \
    --upload-port /dev/ttyUSB0
```

Bu noktada kart "PROVISION BEKLENIYOR" der — normal, henüz NVS boş.

### 4. NVS'i geri yaz

```bash
$PIO pkg exec -p tool-esptoolpy -- esptool.py --port /dev/ttyUSB0 \
    --baud 115200 --no-stub write_flash 0x9000 nvs_anahtarli.bin
```

### 5. Doğrula

Kart resetlendikten sonra monitörde şunlar görünmeli:

```
[CRYPTO] AES-128-GCM anahtari NVS'den yuklendi.
[MESH] MAC: A4:F0:0F:64:B5:34
[MESH] Hazir.
```

`[MESH] UYARI: boot sayaci ~sifirdan basladi` satırı ilk kurulumda normaldir
(bkz. mesh_config.h NVS ERASE TUZAĞI). Kart daha önce mesh'te çalıştıysa
peer'lerin de sıfırlanması gerekir — spec §3.1.

## Bilinen tuzaklar

**`Serial.setRxBufferSize()` UART0'da `begin()`'den ÖNCE çağrılamaz.** Tek-USB
modunda kart boot döngüsüne giriyor (`entry 0x400805e4` → sürekli `SW_RESET`,
uygulama hiç başlamıyor). Doğrusu: `begin()` → `end()` → `setRxBufferSize()` →
`begin()`. Kodda uygulandı.

**Boot mesajları binary akışı bozmuyor.** Tek-USB modunda aynı port hem ASCII
boot logu hem COBS binary taşıyor. `esp32_bridge` ile 270k çerçeve alındı,
`crc_fail=0` — desync-güvenli parser ASCII'yi sessizce atıyor. Boot mesajları
bu yüzden kasıtlı bırakıldı (MAC tablosu hatasını görmek kritik).
