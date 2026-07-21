# ESP32 Yükleme Prosedürü (saha notu)

Bir ESP32'yi sıfırdan mesh'e hazır hale getirme.

> **Bu doküman `PROVISION_PROSEDURU.md`'nin yerini aldı.** Eski prosedür AES
> anahtarını NVS'e yazmayı ve sıralamayı anlatıyordu. Şifreleme kaldırıldı
> (bkz `common/mesh_shared/mesh_config.h` başındaki GÜVENLİK MODELİ notu), o
> yüzden provizyon diye bir adım artık **yok**. Firmware NVS'e hiç dokunmuyor.

## Adımlar

Tek adım: derle ve yükle.

```bash
# Baz istasyonu (USB-TTL adaptör varken — varsayılan)
cd "RX BASE" && pio run -t upload

# Baz istasyonu (adaptör yokken, tek kablo yedek yolu)
cd "RX BASE" && pio run -e esp32dev_tek_usb -t upload

# Drone
cd "TX DRONE" && pio run -e esp32dev_serial0 -t upload
```

Yükleme "chip stopped responding" verirse:

```bash
PLATFORMIO_UPLOAD_FLAGS=--no-stub pio run -t upload
```

## Yeni bir ESP32 eklerken

Tek gereken MAC adresini tabloya yazmak:

1. `tools/mac_reader` projesini karta yükle, MAC'i konsoldan oku
2. MAC'i **iki** dosyadaki `drone_tablo[]`'ya ekle:
   - `RX BASE/src/main.cpp`
   - `TX DRONE/src/main.cpp`
3. Tüm kartları (baz + her drone) yeniden yükle

Tablolar elle senkron tutuluyor. Birini güncelleyip diğerini unutmak kolay ve
semptomu sessiz: `[MESH] Bilinmeyen MAC, paket reddedildi`. Boot'ta
`_drone_tablo_dogrula()` yalnızca **aynı dosya içindeki** çakışmaları yakalar,
dosyalar arası tutarsızlığı göremez.

## Bir şey değiştirdiğinde hepsini birlikte yükle

Şu üçünden biri değişirse **tüm kartlar aynı anda** yeniden yüklenmeli:

| Değişen | Nerede |
|---|---|
| `MESH_SIHIR` | `mesh_config.h` |
| `MESH_KANAL` | `mesh_config.h` |
| `mesh_paket_t` alan düzeni | `mesh_config.h` |

Karışık filo (biri eski, biri yeni) **tamamen sağır** olur ve hiçbir hata
mesajı vermez — iki taraf da karşıdakinin paketini "yabancı" sayıp atar.

## Bağlantı yerleşimi

**Baz (varsayılan `esp32dev`)**

| Hat | Port | Nereye |
|---|---|---|
| Debug konsolu | Serial0 (USB) | laptop, 115200 |
| YKİ verisi | Serial2 GPIO25/26 | USB-TTL, 460800 |
| RTCM girişi | — | açılmıyor (`RTCM_GIRISI_VAR=0`) |

USB-TTL bağlantısı — TX↔RX çaprazlanır, GND zorunlu, VCC bağlanmaz:

```
USB-TTL TXD ──> ESP32 GPIO25
USB-TTL RXD <── ESP32 GPIO26
USB-TTL GND ─── ESP32 GND
```

⚠️ Adaptörün mantık seviyesi **3.3V** olmalı. 5V ise GPIO'yu yakar. Bağlamadan
önce TX–GND arasını ölç.

**Drone (`esp32dev_serial0`)**

| Hat | Port | Nereye |
|---|---|---|
| RPi verisi | Serial0 GPIO3/GPIO1 | RPi `/dev/ttyAMA4`, 460800 |
| Debug | — | yok (hat binary taşıyor) |

⚠️ Firmware yüklerken RPi kablolarını çıkar — aynı pinler USB-seri çeviriciyle
paylaşımlı, iki sürücü aynı hatta konuşur.

## Port karışması

İki USB seri cihaz takılıyken `ttyUSB0`/`ttyUSB1` numaraları her takışta yer
değiştirebilir. Script'lerde her zaman sabit yolu kullan:

```bash
ls -l /dev/serial/by-id/
# ...CP2102... -> ESP32
# ...CH340...  -> USB-TTL
```
