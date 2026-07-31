# Cihaz ve erişim tablosu

Sahada IP'ler DHCP ile değişir (29 Temmuz'da ağ `10.207.118.x`'ten `10.158.16.x`'e
kaydı ve bütün SSH komutları kırıldı). **Değişmeyen kimlik MAC adresidir** —
IP'yi her seferinde MAC'ten bul, ezberleme.

IP'yi MAC'ten bulmak için:

    sudo arp-scan --localnet --interface=wlan0     # ya da laptopta wlp0s20f3
    # arp-scan yoksa, 22. portu tara:
    for i in $(seq 1 254); do (timeout 1 bash -c "echo > /dev/tcp/10.158.16.$i/22" \
      2>/dev/null && echo "SSH: 10.158.16.$i") & done; wait

## Raspberry Pi 5 (drone bilgisayarları)

Kullanıcı adı **drone başına ayrı** — hepsi `yelpence` değil. Karıştırılırsa
`Permission denied (publickey,password)` alırsın; anahtar sorunu sanma, önce
kullanıcı adını doğrula.

| Drone | Hostname | SSH kullanıcı | wlan0 MAC          | eth0 MAC           | Docker konteyner | IP (30 Tem) |
|-------|----------|---------------|--------------------|--------------------|------------------|-------------|
| ylp00 | `ylp00`  | `yelpence00`  | `88:a2:9e:71:60:ed`| `88:a2:9e:71:60:ec`| `drone1`         | 10.158.16.134 |
| ylp01 | `ylp01`  | `yelpence01`  | `88:a2:9e:da:04:2d`| (bilinmiyor)       | `drone2` (kurulacak) | 10.158.16.211 |
| ylp02 | `ylp02`  | `yelpence02`  | `88:a2:9e:71:60:24`| `88:a2:9e:71:60:23`| `drone3`         | 10.158.16.189 |

Not: ylp01'in wlan0 MAC öneki diğer ikisinden farklı (`da:04:2d` ↔ `71:60:xx`) —
farklı parti Raspberry Pi. Yine de `88:a2:9e` (Raspberry Pi Trading) önekiyle
bulunur.

**Pi bir süre boşta kalınca SSH'a cevap vermiyorsa** sebebi Wi-Fi güç
tasarrufudur (uyanması için ~30 sn ping gerekiyordu). Üçünde de kapatıldı:

    nmcli connection modify rpissid 802-11-wireless.powersave disable

Yeni bir Pi kurarken bunu ve diğer bütün adımları
`deploy/rpi/pi_hazirla.sh` yapıyor (Pi üzerinde `sudo bash pi_hazirla.sh <id>`).

YKİ dizüstü: `10.158.16.115`, MAC `5c:b4:7e:af:b3:83`, arayüz `wlp0s20f3`.

SSH anahtarı (`~/.ssh/id_ed25519`) ylp00 ve ylp02'de kurulu — parola sorulmaz.
**ylp01'de kurulmadıysa** bir kez:

    ssh-copy-id -i ~/.ssh/id_ed25519.pub yelpence01@<ylp01-ip>

Kullanım:

    ssh yelpence00@<ylp00-ip>      # ylp00
    ssh yelpence01@<ylp01-ip>      # ylp01
    ssh yelpence02@<ylp02-ip>      # ylp02

Konteyner içinde ROS komutu:

    ssh yelpence02@<ip> 'docker exec drone3 bash -lc "source /opt/ros/jazzy/setup.bash && ros2 topic list"'

**Dikkat:** konteyner adı ile drone numarası aynı değil —
ylp00 → `drone1`, ylp02 → `drone3`. MAVROS namespace'i de konteyner numarasını
izler (`/drone_1/...`, `/drone_3/...`).

## ESP32 mesh (ESP-NOW, kanal 11)

MAC → ID eşlemesi iki firmware'de de birebir aynı tabloda duruyor; birini
değiştirirsen diğerini de değiştir:

- `firmware/esp32_mesh/RX BASE/src/main.cpp` (~satır 128)
- `firmware/esp32_mesh/TX DRONE/src/main.cpp` (~satır 71)

| Drone | Mesh ID | ESP32 MAC           |
|-------|---------|---------------------|
| ylp00 | 1       | `B0:CB:D8:C8:A8:30` |
| ylp01 | 2       | `D4:E9:F4:FB:13:88` |
| ylp02 | 3       | `A4:F0:0F:64:A9:90` |

Base ESP mesh ID = **10** (`agent_id:=10`, `yki_baslat.sh`). Firmware'de `BAZ_ID = 99`
ayrı bir sentinel'dir — RTK UART yolu için kullanılır, drone ID'si değildir.
Tabloda olmayan MAC'ten gelen paket reddedilir (kapı kimliği), yani yeni bir ESP
takarsan MAC'i buraya eklemeden mesh'e giremez.

## Yer istasyonu (laptop) USB portları

`ttyUSB` numaraları her takışta değişir — **by-id yolunu kullan**, numarayı değil.

| İşlev            | Adaptör | by-id yolu                                                    | Baud   |
|------------------|---------|---------------------------------------------------------------|--------|
| base ESP **veri**| CH340   | `usb-1a86_USB_Serial-if00-port0`                              | 460800 |
| base ESP **log** | CP2102  | `usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0` | 115200 |
| RTK GPS (u-blox) | —       | `usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00`    | —      |

Seri portu Python'dan açarken **açar açmaz** DTR/RTS'yi bırak, yoksa ESP resette
kalır ve "kart bozuk" sanırsın (bkz. saha günlüğü §5.6):

    s = serial.Serial(port, baud, timeout=0.4)
    s.setDTR(False); s.setRTS(False)

## QGroundControl bağlantısı

Kanıt videosu yönergesi "uçuş modunun ve yönelimlerin açıkça göründüğü"
QGC/Mission Planner ekranını şart koşuyor. Mesh 16 baytlık özet taşır ve
QGC'nin HUD'una yetmez — tam MAVLink gerekir. Yol WiFi üzerinden:

1. Her Pi'de `~/yelpence_ws/gcs_url` → `udp-b://:14555@14550`
2. QGC → Comm Links → Add → **UDP, port 14550** → Connect
   (**AutoConnect UDP kapalı** olsun; açıksa QGC portu iki kez almaya çalışır)

**MAV_SYS_ID her drone'da AYRI olmak zorunda.** QGC araçları sysid ile ayırır;
ikisi de 1 olursa QGC bunları **tek araç** sanar ve iki uçağın telemetrisi
aynı araca akar — HUD arada git gel yapar (30 Tem'de yaşandı, ölçüldü:
14550'ye iki farklı IP'den ~2350'şer paket, hepsi sysid=1).

| Drone | MAV_SYS_ID | `/ws/tgt_system` |
|-------|-----------|------------------|
| ylp00 | 1         | (dosya yok, MAVROS varsayılanı 1) |
| ylp01 | 2         | `2` |
| ylp02 | 3         | `3` |

Değiştirme yordamı — **üçü birden yapılmazsa drone sessizce kopar**:

    ros2 param set /drone_N/mavros/param MAV_SYS_ID <N>
    # FCU'yu YENIDEN BASLAT — PX4 bu parametreyi ancak boyle uygular.
    # (ilk denemede "yazilmadi" sanilmasinin sebebi budur)
    ros2 service call /drone_N/mavros/cmd/command mavros_msgs/srv/CommandLong \
      "{command: 246, param1: 1.0}"
    echo <N> > ~/yelpence_ws/tgt_system    # MAVROS da ayni sistemi hedeflesin
    docker restart <konteyner>

`tgt_system` FCU ile uyuşmazsa semptom aldatıcıdır: paketler akmaya devam
eder ama **içerik boşalır** — `mod=?`, `sat=0`, `pil %0`, arayüzde FAILSAFE.
İpucu `mavros.log`'daki `detected remote address <sysid>.1` satırıdır.

**`src/gcs/qgc_proxy.py` KULLANILMIYOR.** sysid çakışması için yazılmıştı ama
MAVROS'un `udp-b` uçnoktası bir karşı taraf keşfedince yayını bırakıp o adrese
tekil gönderime geçiyor; proxy'ye kilitlenip proxy ölünce telemetri tamamen
kesiliyor. Ayrıntı dosyanın başlığında.

## Yerel servisler

| Servis   | Adres                   | Log                        |
|----------|-------------------------|----------------------------|
| Arayüz   | http://localhost:5173/  | `/tmp/yki_frontend.log`    |
| Backend  | http://localhost:8000/  | `/tmp/yki_backend.log`     |
| Base köprü | —                     | `/tmp/yki_base_bridge.log` |

Telemetri anlık görüntüsü: `curl -s http://localhost:8000/api/telemetry/snapshot`

Başlat / durdur: `src/gcs/yki_baslat.sh` · `src/gcs/yki_durdur.sh`
