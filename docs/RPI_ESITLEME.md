# RPİ EŞİTLEME DEFTERİ — geri gelen drone'u hizaya getirme

**Son güncelleme:** 30 Ağustos 2026, 03:45 — **A23 eklendi**: ikinci RC alıcısı ylp00'a takıldı (pin 29, sinyal ~3 V ölçüldü), overlay bekliyor; eski damga: 29 Ağustos 19:45 — param karşılaştırması saha gününe indirildi

## Kamera ayarları — ylp02'de kalibre edildi · 28 Ağustos 2026

**Hangi uçaklarda:** ylp02 ✅ · ylp00 ❌ · ylp01 ❌ (o uçaklarda kamera yok)

Bunlar `deploy/rpi/kamera_yayin.py` içinde **kodda** duruyor, yani dosyayı
dağıtmak yetiyor — uçakta elle bir ayar yok. Ama **kalibrasyon değerleri
ylp02'nin kamerasına özeldir**; başka bir modüle takılırsa yeniden ölçülmeli.

| ayar | değer | nasıl bulundu |
|---|---|---|
| `KALIBRE_KAZANC` | `2.5923,1.2225` | beyaz kâğıt, kapalı döngü, sapma %0 |
| `KALIBRE_POZLAMA` | `sport` | sabit 1/250 kareyi doyuruyordu (%37-45 kırpık) |
| Varsayılan kip | `tamfov` (2028x1520) | rolling shutter — okuma süresi yarıya |
| `fps` (tam kip) | 30 | jöleye faydası yok, sadece daha çok deneme |

**Yeniden kalibrasyon (kamera değişirse ZORUNLU):**

```bash
# beyaz kâğıt kameraya doğru tutulurken:
docker cp ... ; python3 /tmp/kalibre.py      # bkz. docs/KAMERA.md §3.2
```

⚠️ Kazanç **gün ışığına (~4500 K) bağlıdır.** Akşam/kapalı havada kayar.

---

## PIL (Pillow) — Pi host'una sudo'suz kuruldu · 28 Ağustos 2026

**Hangi uçaklarda:** ylp02 ✅ · ylp00 ❌ · ylp01 ❌

**Neden:** `kamera_yayin.py` kaydı TAM çözünürlükte tutup tarayıcıya
küçültülmüş kare gönderiyor (operatör isteği: "kaydı hangi çözünürlükte
alıyorsak o çözünürlükte yap, sadece hotspottan gelende küçültme olsun").
rpicam-vid'in tek çıkışı var, küçültme Python tarafında olmak zorunda.
Host'ta hiçbir görüntü aracı yoktu — PIL, ffmpeg, ImageMagick, GStreamer,
jpegtran, **pip bile** yok.

**Kök yetkisi GEREKMEDİ:**

```bash
mkdir -p ~/pylib_indir && cd ~/pylib_indir
apt-get download python3-pil python3-pil.imagetk libfreetype6 \
  libimagequant0 liblcms2-2 libopenjp2-7 libraqm0 libwebpdemux2 libwebpmux3
mkdir -p ~/yelpence_ws/pylib
for d in *.deb; do dpkg -x "$d" ~/yelpence_ws/pylib; done
cd ~ && rm -rf ~/pylib_indir
```

Toplam **5,5 MB**, `~/yelpence_ws/pylib` altında. Sisteme hiçbir şey yazılmadı.

**LD_LIBRARY_PATH GEREKMİYOR.** `kamera_yayin.py` içindeki `_pil_yukle()`
paylaşımlı kütüphaneleri `ctypes.CDLL(..., RTLD_GLOBAL)` ile ön yüklüyor.
Sebep: LD_LIBRARY_PATH süreç başlamadan ayarlanmak zorunda; öyle olsaydı
servisi kim nasıl başlattıysa küçültme sessizce kaybolabilirdi.

`libraqm` yüklenemiyor (karmaşık metin şekillendirme) — gerekmiyor.

**Doğrulama:**

```bash
python3 -c "import sys; sys.path.insert(0,'$HOME/yelpence_ws/pylib/usr/lib/python3/dist-packages')"
curl -s http://127.0.0.1:8080/olcum | grep -o '"pil": [a-z]*'   # true olmalı
```

**PIL yoksa ne olur:** çökmez — küçültme kapanır, yayın tam boyda gider
(4K'da 24,5 Mbps, hotspot taşımaz). Arayüzde kırmızı uyarı çıkar.

**ÖLÇÜLDÜ (28 Ağustos, Pi 5, gerçek 4056x3040 kare):**

| hedef | draft (DCT) | draftsiz |
|-------|-------------|----------|
| 640px | **33 ms** | 116 ms |
| 960px | 39 ms | — |
| 1280px | 70 ms | — |
| 1920px | 95 ms | — |

Canlıda: 299,5 KB → 13,7 KB/kare, 24,5 → 1,12 Mbps, 26,8 ms/kare.

## Bu belge ne için

Her zaman bütün uçaklarla çalışamıyoruz. Şu an **ylp01 yerde** ve ylp00 ile
ylp02 üzerinde çalışıyoruz. Yarın ylp01 dönüp ylp02 gidebilir. Sonunda üçü
birden ayakta olacak.

**Geride kalan uçak, dönene kadar yapılan her şeyi kaçırır.** Bu belge o
farkı kapatmak için: Pi'lerde yapılan her değişiklik **hangi uçaklarda var**
bilgisiyle burada tutulur. Geri gelen uçak için tek yapılacak, aşağıdaki
listeyi yukarıdan aşağı yürütmek.

> ⚠️ **KURAL: Bir Pi'ye elle bir şey yaptıysan, BURAYA YAZ.**
> Yazılmayan değişiklik, geri gelen uçakta saatlerce süren "neden bunda
> çalışmıyor" arayışına dönüşüyor. Bu belgenin tek işi o.

---

## 1. Uçağa özgü değerler

Aşağıdaki komutlarda `<N>`, `<KULLANICI>`, `<KONTEYNER>` geçen yerlere
**`docs/cihazlar.md` kimlik tablosundan** bak — agent_id, SSH kullanıcısı,
konteyner adı, ROS ns, MAC'ler, mesh ID, `MAV_SYS_ID`, `tgt_system`, hepsi
orada ve **tek kaynak orası**.

> ⚠️ **ylp00 → drone1, ylp01 → drone2, ylp02 → drone3.** İsimdeki sayı bir
> eksik ve karıştırılması en kolay şey bu.

---

## 2. Geri gelen uçak için hızlı yol

```bash
# 1) Ağda mı, hangi IP'de
./deploy/yki/drone_bul.sh --liste

# 2) Genel sağlık (disk, konteyner, bayraklar)
./deploy/yki/drone_bul.sh --durum

# 3) Kod senkronu — .surum dosyasina GUVENME, md5 karsilastir
./deploy/yki/drone_bul.sh <ylpXX> 'md5sum ~/yelpence_ws/baslat.sh'
md5sum deploy/rpi/baslat.sh          # ikisi ayni olmali
```

Sonra aşağıdaki bölümleri sırayla geç. Her satırın yanında **hangi uçaklarda
olduğu** yazıyor.

### 🔴 En çok atlanan ayrım: `dagit.sh` neyi taşır, neyi taşımaz

Bu belgenin var olma sebebi tam olarak bu. `dagit.sh` çoğu şeyi taşıyor, o
yüzden "dağıttım, tamamdır" hissi oluşuyor — ama **dört şey elle yapılıyor**
ve hiçbiri eksikken hata vermiyor.

| | `dagit.sh` taşır mı? | etkin olması için |
|---|---|---|
| ROS paketleri, `baslat.sh`, `run_drone.sh`, teşhis betikleri | ✅ **evet** | konteyner **yeniden başlat** |
| PX4 parametreleri | ❌ hayır | `param_karsilastir.py`, bölüm C |
| **`mcap` kurtarma aracı** (A11) | ❌ **hayır** | elle kopyala, bölüm 8 |
| **sysctl writeback** (A8) | ❌ **hayır** | elle + `sudo`, bölüm 3 |
| **docker log döndürme** (A12) | ❌ **hayır** | konteyneri **yeniden OLUŞTUR** |
| Wi-Fi ağları, SSH anahtarları (A9/A10) | ❌ hayır | bölüm 7 |

> **"Yeniden başlat" ile "yeniden oluştur" aynı şey değil.**
> `docker restart` çalışan konteyneri döndürür — kod ve betik değişiklikleri
> için bu yeter. Ama docker'ın **log ayarları oluşturma anında sabitlenir**;
> onları değiştirmek için `docker rm -f <ad>` + `run_drone.sh <N>` gerekir.
> 20 Ağustos'ta ylp00'da yapıldı, ylp02'de yapılmadı.

### ylp01 döndüğünde — 20 Ağustos işlerinin listesi

> ✅ **BU LİSTE 24 AĞUSTOS 20:35'TE KAPANDI — KLON YÖNTEMİYLE.**
> ylp02'nin SD imajı **yeni bir Pi'ye** klonlandı (eski Pi ölü) ve
> `deploy/rpi/ylp01_donusum.sh` kimliği çevirdi: kullanıcı `yelpence01`,
> hostname `ylp01`, SSH host anahtarları yeniden üretildi, `tgt_system=2`.
> Aşağıdaki adımların karşılığı: (1) kod klonla `7645d83` geldi ·
> (2) mcap klonla, sha birebir ölçüldü · (3) sysctl klonla, 100 ölçüldü ·
> (4) `drone2` yeni oluşturuldu, log döndürme 10m×3 ölçüldü ·
> (5) doğrulama yapıldı. Yeni wlan0 MAC: `88:a2:9e:67:6e:ff`
> (`drone_bul.sh` + `cihazlar.md` güncellendi).
>
> **Kalan işler UÇAK tarafında** (Pi değil): ESC güç hattı onarımı,
> Pi'nin uçağa montajı, ESP↔Pi jumper (A16), PX4 parametre karşılaştırma
> (bölüm C), RC-kayıp failsafe kurulumu. Ve ⚠️ kalıntılar: `~/yelpence_ws/kayit/`
> altında **ylp02'nin eski uçuş kayıtları** duruyor (karışıklık kaynağı,
> ilk fırsatta temizle) · `/usr/local/bin/ylp01_donusum.sh` root'ta kaldı
> (ikinci koşumda kendini iptal eder, zararsız; sudo'lu ilk işte silinebilir).

Sırayla, yukarıdan aşağı (tarihçe için duruyor):

```bash
# 1) Kod, betikler, paketler  (otomatik)
./deploy/rpi/dagit.sh ylp01

# 2) mcap kurtarma araci  (ELLE — dagit tasimaz, bkz. A11 / bolum 8)
./deploy/yki/drone_bul.sh ylp01 \
  'mkdir -p ~/yelpence_ws/bin && cat > ~/yelpence_ws/bin/mcap \
   && chmod +x ~/yelpence_ws/bin/mcap && sha256sum ~/yelpence_ws/bin/mcap' \
  < mcap-linux-arm64
#    be9734ef63ada9d0cc7a3aa41378ab65fd482601e5f5b3b52098d8e6553deabf gormeli

# 3) sysctl writeback  (ELLE + root, ETKILESIMLI baglanti sart)
./deploy/yki/drone_bul.sh ylp01        # komut vermeden -> kabuk acilir
#    Pi'de: bolum 3'teki A8 komutlari, sonra `cat /proc/sys/vm/dirty_expire_centisecs` -> 100

# 4) Konteyneri YENIDEN OLUSTUR  (log dondurmesi ancak boyle devreye girer)
./deploy/yki/drone_bul.sh ylp01 'docker rm -f drone2 && cd ~/yelpence_ws && bash run_drone.sh 2'
#    ONCE DISARM oldugundan emin ol. ROS yigini ~4 dk kapali kalir.

# 5) Dogrula
./deploy/yki/drone_bul.sh ylp01 \
  'docker exec drone2 bash -lc "source /opt/ros/jazzy/setup.bash; \
   ROS_LOCALHOST_ONLY=1 ros2 node list" | grep -v mavros | sort'
```

**Neden bu sıra:** 2 ve 3 konteynerden bağımsız (host tarafı), 4 onları
kapsayan yeniden oluşturma. 4'ü önce yaparsan 2 ve 3 yine gerekir.

**Hepsinin ortak özelliği: eksikken HATA VERMEZ.** `mcap` yoksa onarım
betiği sessizce eski davranışına döner ve daha çok veri kaybettirir; sysctl
yoksa düşüşte son ~30 saniye gider; log döndürme yoksa bozuk bir docker logu
kalıcı olur. Üçü de ancak **ölçerek** görülür.

---

## 3. A — Pi ana sistem (konteyner dışı)

| # | Ne | ylp00 | ylp01 | ylp02 | Nasıl |
|---|----|-------|-------|-------|-------|
| A1 | Hostname + kullanıcı | ✅ | ✅ | ✅ | `deploy/rpi/pi_hazirla.sh <id>` |
| A2 | Docker + konteyner | ✅ | ✅ *(24 Ağu, drone2 yeni)* | ✅ | `deploy/rpi/run_drone.sh` (`-e AGENT_ID=<N>`, ad `<KONTEYNER>`) |
| A3 | Saat dilimi Europe/Istanbul | ✅ | ✅ *(klon, ölçüldü)* | ✅ | `izleme_kur.sh` 1/7 |
| A4 | Wi-Fi güç tasarrufu kapalı | ✅ | ✅ *(klon)* | ✅ | `izleme_kur.sh` 2/7 — **kapatılmazsa Pi boşta SSH'a cevap vermiyor** |
| A5 | Kalıcı journald | ✅ | ✅ *(klon)* | ✅ | `izleme_kur.sh` 3/7 — dosya adı `10-` ile başlarsa İŞE YARAMAZ |
| A6 | `yelpence-izle` servis + timer | ✅ | ✅ *(klon, timer active ölçüldü)* | ✅ | `izleme_kur.sh` 4-5/7 |
| A7 | Kayıt disk temizlik timer'ı | ✅ | ✅ *(klon)* | ✅ | `izleme_kur.sh` 6/7 |
| A8 | **sysctl writeback (1 sn)** | ✅ *(20 Ağu 23:15)* | ✅ *(klon, `dirty_expire=100` ölçüldü)* | ✅ | `izleme_kur.sh` 7/7 → `/etc/sysctl.d/60-yelpence-writeback.conf` · **elle, root** |
| A11 | **`mcap` kurtarma aracı** | ✅ | ✅ *(klon, sha birebir ölçüldü)* | ✅ | `~/yelpence_ws/bin/mcap` · **elle kopyalanır, `dagit.sh` taşımaz** |
| A12 | **docker log döndürme** | ✅ | ✅ *(24 Ağu, drone2 yeni oluşum — 10m×3 ölçüldü)* | ❌ | `run_drone.sh` içinde — **yalnız konteyner YENİDEN OLUŞTURULUNCA** devreye girer |
| A13 | 🔴 **Çökme kaydı (ramoops) + `kernel.panic=10`** | ✅ | ✅ *(klon, cmdline ölçüldü)* | ✅ | `izleme_kur.sh` **8/8** · **sahada sınandı** (sysrq paniği yakalandı) |
| A14 | **Çökme izlerini okunabilir kopyala** | ✅ | ✅ *(klon, enabled ölçüldü)* | ✅ | `yelpence-cokme.service` → `~/yelpence_ws/gunluk/cokme/` |
| A15 | **İzleme aralığı 60 → 10 sn** | ✅ | ✅ *(klon)* | ✅ | 22 Ağu 03:36'da doğrulandı — `OnUnitActiveSec=10s`, timer aktif |
| A16 | 🔴 **ESP↔Pi UART jumper'ı yeniden oturtuldu** | ✅ *(23 Ağu 00:50, ELLE)* | ❌ | ❔ **bakılmadı** | P0.15'in kök nedeni — `TUZAKLAR` §2.19. **Geçici**: jumper yine gevşer |
| A18 | **esptool — host tarafı, venv içinde** | ✅ | ✅ | ✅ | `python3 -m venv ~/esptool_venv && ~/esptool_venv/bin/pip install esptool` → **v5.3.1** · **sudo GEREKMEZ** · `dagit.sh` TAŞIMAZ · 26 Ağu. Konteynerdeki apt kopyası (yalnız `drone2`, v4.7.0, stub'sız) artık kullanılmıyor — kurtarma aracı, kurtaracağı şeyin içinde durmamalı |
| A19 | 🔴 **`-e ROS_LOCALHOST_ONLY=1` konteyner ortamında** | ❌ | ❌ | ❌ | `run_drone.sh`'te (26 Ağu `dd5a1e6`) — **yalnız konteyner YENİDEN OLUŞTURULUNCA** devreye girer, tıpkı A12 gibi. O ana kadar elde `docker exec -e ROS_LOCALHOST_ONLY=1 ...` verilmeli · `TUZAKLAR` §1.25. **A12 ylp02'de ❌ — tek recreate ikisini birden kapatır** |
| A20 | **IMX477 kamera + `config.txt` overlay'i** | ❌ | ❌ | ✅ | `/boot/firmware/config.txt`: `camera_auto_detect=0` + `dtoverlay=imx477,cam0` + `dtoverlay=imx477,cam1`. **Oto-tespit bu Arducam kartini TANIMIYOR** — overlay elle verilmezse `No cameras available!` disinda hicbir belirti yok. Flex tuzagi: `KAMERA.md` §2 |
| A21 | 🔒 **IR-CUT suzgeci GUNDUZ konumunda kilitli** | — | — | ✅ | 28 Agu gece, operator: suzgec gunduz konumuna alindi ve **kablosu sokuldu**, isik sensoru artik ceviremiyor. Gece konumunda kare magentaya kayiyor ve renk tespiti **6 sahte KIRMIZI bolge** uretmisti (27 Agu olcumu) |
| A23 | 🔴 **İkinci RC alıcısı (Görev 2 sürü kumandası)** | ⏳ kablo ✅ / overlay ❌ | ❌ | ❌ | **30 Ağu, operatör ylp00'a fiziksel olarak taktı.** FS-iA6B **i-BUS Servo** çıkışı → jumper → **fiziksel pin 29 (GPIO5) = uart2 RX** + GND. ✅ **Sinyal ölçüldü: ~3 V** → 3,3 V mantık, **seviye çevirici GEREKMİYOR** (Pi 5 GPIO'su 5 V toleranslı değil, bu yüzden ölçüldü). Kumanda `IntV1 5,3 V` gösteriyor = alıcının BESLEMESİ, sinyal değil; telemetri geldiğine göre **bind tamam**. ⏳ **KALAN:** `/boot/firmware/config.txt`'ye `dtoverlay=uart2-pi5` + reboot → `/dev/ttyAMA2`. Sonra konteyner **recreate** (`--device`, restart yetmez). Ayrıntı: `gorev2.md` B1 |
| A22 | **Algi paketleri (imaj icinde)** | ❌ | ❌ | ✅ | `yelpence-ros:latest` (`ea2c1b1e9154`, 2,02 GB) — opencv 4.6 + pyzbar + **zxing-cpp** (birincil QR cozucu) GOMULU, konteyner yeniden olusturmada kaybolmuyor. Eski bilinen-iyi imaj `yelpence-ros:temiz-20260828` korundu. Esitleme: `./deploy/yki/imaj_esitle.sh <ylpXX>` — **KARAR-09 (B), ylp00 + ylp01 bekliyor** |

> ### 🔴 A16 — konnektör: yapılan iş ve durumu
>
> **ylp00:** ESP32 ↔ Pi UART kablosunun **ESP ucundaki jumper** marjinal
> oturuyordu; uçuş titreşiminde kesikli temas yapıp baytları bozuyordu
> (uçuşta `crc_fail` 868, yerde 0). Elle kontrol sırasında **iki tel çıktı**,
> yeniden oturtuldu. Doğrulama: tek uçaklı ve iki uçaklı uçuşta **crc_fail 0**.
>
> ⚠️ **Bu geçici bir düzeltme.** Jumper sürtünmeyle tutar — kilit yok, gerilim
> boşaltma yok. Titreşimde yeniden gevşemesi beklenir.
>
> **ylp02 / ylp01:** aynı jumper dizilimi onlarda da var. ylp02 22 Ağustos
> uçuşunda **0 hata** verdi, ama bu "sağlam" değil **"henüz gevşememiş"**
> demektir — kontrol edilmedi.
>
> Kontrol yolu (uçuş gerekmez, ~1 dk): uçuş sonrası `mesh_diag`'da
> `crc_fail` bak. **Yerde 0, uçuşta da 0 olmalı.**

### Kod tarafı — 21-22 Ağustos (hepsi `dagit.sh` ile gider)

Bunlar Pi ayarı değil **depo değişikliği**; `./deploy/rpi/dagit.sh <ad>` +
konteyner yeniden başlatma yeterli. ylp01 döndüğünde tek yapılacak
`dagit.sh ylp01`.

| | ne | ylp00 | ylp01 | ylp02 |
|---|---|---|---|---|
| K1 | **ADIM 4** — `basit_kacinma` KAPALI, `collision_avoidance` açık | ✅ | ✅ | ✅ |
| K2 | Kaçınma eşikleri **test değerleri** `d0=10 hard=6` (üretim: 6/4) | ✅ | ✅ | ✅ |
| K3 | `velocity_only` artık CA'yı da kapsıyor | ✅ | ✅ | ✅ |
| K4 | **Körlük alarmı** — 2 sn'de KRİTİK olay + YKİ sesli uyarı | ✅ | ✅ | ✅ |
| K5 | Mesh `DURUM2_BAYRAK_KACINMA_KORU` (0x04) | ✅ | ✅ | ✅ |
| K6 | `sahte_kayip_ajanlar` test kancası (tek yönlü kayıp benzetimi) | ✅ | ✅ | ✅ |
| K7 | **Sönümleme tabanı** — uzaklaşan komşuya çekim YOK | ✅ | ✅ | ✅ |
| K8 | `px4_bridge` setpoint hız/ivme tavanlarını okuyor | ✅ | ✅ | ✅ |
| K9 | 🔴 **Pilot devraldıysa mod geri alınmaz** | ✅ | ✅ | ✅ |
| K10 | 🔴 **Kaçınma ivmeleri eğim tavanına bağlandı** (30→5,66) | ✅ | ✅ | ✅ |
| K11 | `hard` sınırındaki süreksizlik giderildi | ✅ | ✅ | ✅ |
| K12 | Kaçınma sonrası dönüş yumuşatma (0,5 m/s²) | ✅ | ✅ | ✅ |
| K13 | 🔴 **DİKEY yol verme** — birincil kaçış dikeye alındı | ✅ *(23 Ağu 20:10)* | ✅ | ✅ |
| K14 | 🔴 **Yatay itme SON ÇARE** — yalnız `hard` içinde (`k_tan=0`) | ✅ | ✅ | ✅ |
| K15 | 🔴 **Dikey datum düzeltmesi** — `alt_amsl − home`, EKF yerel z DEĞİL | ✅ | ✅ | ✅ |
| K16 | 🔴 **`d0/hard` 10/6 → 4,0/2,5** — geçici test değeri geri alındı | ✅ | ✅ | ✅ |
| A17 | 🔴 **POSE kapısı `0.100 → 0.095`** — komşu tazeleme 7,1 → 10,5 Hz | ✅ *(23 Ağu 18:10)* | ✅ | ✅ |

> ylp01 sütunu 24 Ağustos 20:35'te ✅ oldu: kod klonla **`7645d83`**
> geldi — üstelik bu, K listesinin tamamından DAHA YENİ (dikey kaçınma
> dönüş paketi `hist_m=2,5` ve `tatmin` düzeltmesi dahil). `.surum`
> dosyasından ölçüldü.


> ### 🔴🔴 23 AĞUSTOS 22:15 — DEPO UÇAKLARDAN İLERİDE
>
> ```
> ucaklarda : commit 1d1048e   (ucan, dogrulanmis kod)
> depoda    : cbf948c + ca_core degisikligi
> ```
>
> Uçuştan **sonra** `ca_core`'a yapılan değişiklik (`tatmin` durumunda dikey
> yetkiyi bırakmama) **dağıtılmadı**. Uçaklar uçtukları kodla duruyor.
> Sonraki oturumun ilk işi: dağıt ya da farkı bilinçli olarak belgele.
> Ayrıntı: `git show 783afab:docs/CA.md` §7.3 (belge 29 Ağu'da kaldırıldı).
>
> ### 🔀 K13-K16 — DİKEY KAÇINMA (23 Ağustos 2026) — ✅ UÇTU
>
> Birincil kaçış yönü **dikey** oldu. Uçakta bunun karşılığı iki şey:
>
> **1. Kod** (`dagit.sh` ile gitti, `.surum = 9e8ee4f +KIRLI`):
> `ca_core.py` · `collision_avoidance_node.py` · `komsu_adaptoru.py` ·
> `baslat.sh` · `esp32_bridge_node.py`
>
> **2. Ayar dosyası** — `~/yelpence_ws/ucus_ayarlari.env` YENİDEN ÜRETİLDİ:
>
> ```
> KACINMA_D0=4.0        KACINMA_HARD=2.5      KACINMA_KATMAN=3.0
> KACINMA_DIKEY_HIZ=1.2 KACINMA_DIKEY_IVME=2.0 KACINMA_DIKEY_KP=2.0
> ```
>
> 🔴 **K2 BURADA KAPANDI:** dosyanın sonundaki elle eklenmiş
> `KACINMA_D0=10.0 / KACINMA_HARD=6.0` geçici test bloğu artık YOK.
> Eski dosya `ucus_ayarlari.env.23agu_oncesi` olarak yedeklendi.
>
> **Geri gelen uçakta yapılacak:**
> ```bash
> ./deploy/rpi/dagit.sh ylp01
> python3 src/gcs/ucus_ayarlari.py --kabuk | \
>   ./deploy/yki/drone_bul.sh ylp01 'cat > ~/yelpence_ws/ucus_ayarlari.env'
> ./deploy/yki/drone_bul.sh ylp01 'docker restart drone2'
> ```
>
> 🔴 **VE `SURU_KADRO`:** `baslat.sh`'te varsayılan **`"1 3"`**. ylp01
> dönünce **üç uçakta da `"1 2 3"`** olmalı — rütbe bundan türüyor ve yanlış
> kadro **kaçış yönünü ters çevirir** (ylp02 yukarı yerine aşağı kaçar).
> `KARAR-04`'ün listesine eklendi.
>
> ### A17 — POSE kapısı (23 Ağustos)
>
> `esp32_bridge._pose_periyot_s` 0,100 → **0,095**. 10 Hz kaynağı 10 Hz
> kapıdan geçirmek örneklerin ~%26'sını yutuyordu (`TUZAKLAR` §2.20).
> Ölçülen: komşu tazeleme **7,1 → 10,5 Hz**, `gonderim_drop=0`.
> Kod değişikliği — `dagit.sh` ile gider, elle bir şey gerekmez.

> ✅ **ylp00'da K10-K12 ETKİNLEŞTİ (22 Ağustos 17:31).** Bekleyen
> `docker restart drone1` yapıldı ve açılış logundan doğrulandı:
>
> ```
> collision_avoidance basladi (komsular: 2,3, d0=10.0 hard=6.0,
>   ivme normal=3.58 acil=5.66 donus=0.50, basit_kacinma KAPALI)
> ```
>
> Sonrasında 11 `ros2 run` süreci ayakta, YKİ drone1'i yeniden gördü.
> Artık iki uçak da aynı ivme sınırlarında — ayrışma yok.

🔴 **K2 GEÇİCİ.** `d0=10 hard=6` yalnız kaçınma testi için; uçaktaki
`~/yelpence_ws/ucus_ayarlari.env` dosyasının sonuna elle eklendi.
**Formasyon uçuşundan önce geri alınacak** — 12 m aralıkta formasyonun
planlı en yakın yaklaşması 8,49 m, `d0=10` normal geçişte tetiklenir:

```bash
python3 src/gcs/ucus_ayarlari.py --kabuk > /tmp/ucus_ayarlari.env
./deploy/yki/drone_bul.sh <ad> 'cat > ~/yelpence_ws/ucus_ayarlari.env' < /tmp/ucus_ayarlari.env
# + docker restart
```
| A9 | **Wi-Fi ağları (SSID/şifre)** | ✅ 2 ağ | ❌ | ✅ 2 ağ | aşağıda §7 |
| A10 | **SSH authorized_keys** | ✅ Osman+Berk | ❌ | ✅ Osman+Berk | aşağıda §7 |

**A8 açıklama:** güç kesintisinde veri kaybının üçüncü katmanı. Bu ayar
olmadan `baslat.sh`'teki kayıt sertleştirmesi anlamsız — veri kullanıcı
alanından çekirdek alanına taşınır, yine RAM'de bekler.

> ### 🔴 20 Ağustos 2026 — ylp00'da A8 YOK, bu tablo yanlış diyordu
>
> Ölçüldü: `/etc/sysctl.d/60-yelpence-writeback.conf` ylp00'da **mevcut
> değil** ve canlı değerler varsayılanda:
>
> | | ylp00 | ylp02 |
> |---|---|---|
> | `vm.dirty_expire_centisecs` | **3000 (30 sn)** | 100 (1 sn) |
> | `vm.dirty_writeback_centisecs` | **500** | 100 |
>
> **Sonucu somut:** İHA düşüp güç anında giderse, **ylp00'da son ~30
> saniyelik uçuş verisi RAM'de olduğu için kaybolur** — yani kaza
> analizinde bakacağın tam o kısım. ylp02'de bu ~1 saniye.
>
> ylp00'da A5, A6, A7 **var** — `izleme_kur.sh` koşmuş, yalnız 7/7 adımı
> uygulanmamış (ya da sonradan eklenip bir daha koşulmamış). Bu tablo o
> yüzden ✅ diyordu; **tablo doğrulanmadan yazılmıştı.**
>
> **✅ 20 Ağustos 23:15'te operatör uyguladı ve doğrulandı** — ylp00 ve
> ylp02'de `dirty_expire_centisecs = 100`. **ylp01'de HÂLÂ YOK.**
>
> Dersi kalıcı: bu satır ✅ diyordu ama **ölçülmemişti.** Bu tabloda bir
> hücreyi ✅ yapmadan önce uçakta doğrula, yoksa defter kendi kendini
> yanıltıyor.
>
> `sudo` parola sorduğu için **etkileşimli** bağlanmak gerekiyor;
> `drone_bul.sh <ad> '<komut>'` biçimi `-t` vermediği için ÇALIŞMAZ
> ("sudo: a password is required"). Doğrusu:
>
> ```bash
> ./deploy/yki/drone_bul.sh ylp01          # komut vermeden -> etkilesimli kabuk
> # sonra Pi'de:
> sudo tee /etc/sysctl.d/60-yelpence-writeback.conf <<'EOF'
> vm.dirty_expire_centisecs = 100
> vm.dirty_writeback_centisecs = 100
> EOF
> sudo sysctl -q --load=/etc/sysctl.d/60-yelpence-writeback.conf
> cat /proc/sys/vm/dirty_expire_centisecs      # 100 gormeli
> ```

```bash
# A8 tek başına:
sudo tee /etc/sysctl.d/60-yelpence-writeback.conf <<'EOF'
vm.dirty_expire_centisecs = 100
vm.dirty_writeback_centisecs = 100
EOF
sudo sysctl -q --load=/etc/sysctl.d/60-yelpence-writeback.conf
```

---

## 4. B — Çalışma alanı (`~/yelpence_ws` = konteynerde `/ws`)

| # | Ne | ylp00 | ylp01 | ylp02 | Nasıl |
|---|----|-------|-------|-------|-------|
| B1 | `baslat.sh` (14 Ağu sürümü, bekçili) | ✅ | ❌ | ✅ | `scp deploy/rpi/baslat.sh <KULLANICI>@<ip>:~/yelpence_ws/` |
| B2 | `mesaj_hizlari.py` | ✅ | ❓ | ✅ | `deploy/rpi/dagit.sh` |
| B3 | ROS paketleri (`src/` + `build/` + `install/`) | ✅ | ❌ | ✅ | `deploy/rpi/dagit.sh` |
| B4 | `gcs_url` = `udp-b://:14555@14550` | ✅ | ❓ | ✅ | `echo 'udp-b://:14555@14550' > ~/yelpence_ws/gcs_url` |
| B5 | `tgt_system` | yok | `2` | `3` | tabloya bak — **ylp00'da dosya OLMAMALI** |
| B6 | `kacinma` (boş dosya) | ✅ | ❓ | ✅ | `touch ~/yelpence_ws/kacinma` |
| B7 | Teşhis betikleri (**22 adet**) | ✅ | ❌ | ✅ | `deploy/rpi/teshis/*.sh` → `dagit.sh` **kendiliğinden taşır**, `/ws/` köküne |
| B8 | `kayit_onar.sh` + açılışta çağrısı | ✅ | ❌ | ✅ | `dagit.sh` taşır; **etkin olması için konteyner yeniden başlatılmalı** |

**B3 doğrulama** (`.surum`'a güvenme, eskiyor):

```bash
cd src && find swarm_control swarm_core swarm_state_machine swarm_missions \
  swarm_perception swarm_interfaces -name '*.py' -not -path '*/build/*' \
  -not -path '*__pycache__*' -not -path '*.pytest_cache*' | sort | xargs md5sum
# aynısını uçakta ~/yelpence_ws/src içinde çalıştır, çıktıları karşılaştır
```

**B3 not:** `network_proxy` ve `sim_rtcm_source` **bilerek dağıtılmıyor** —
ikisi de simülasyon bileşeni. Uçakta 6 paket olmalı, 8 değil.

---

## 5. C — Pixhawk / PX4 parametreleri

### ✅ Okuma ve karşılaştırma aracı var

```bash
./deploy/yki/param_karsilastir.py              # uçuşu etkileyenler, tüm uçaklar
./deploy/yki/param_karsilastir.py --hepsi      # 1007 parametrenin tamamı
./deploy/yki/param_karsilastir.py --al MPC_XY_VEL_MAX
```

**Ne zaman:** bir parametre **yazıldıktan sonra** ve saha gününde bir kez —
*uçuş başına değil* (29 Ağu operatör kararı, `CLAUDE.md` §9). Farklı olanları
kırmızı basar, uçağa özgü olanları (`MAV_SYS_ID`) ayırır.

**Neden özel bir araç gerekti** (14 Ağustos'ta çözüldü):

- `/drone_<N>/mavros/param/get` diye bir servis **YOK**. MAVROS 2, PX4
  parametrelerini **yerel ROS 2 parametresi** olarak sunuyor. Eski
  `mavros_msgs/srv/ParamGet` yolunu çağırmak "waiting for service to become
  available" ile takılır — ilk teşhiste tam bu tuzağa düşüldü ve
  "parametre okunamıyor" sanıldı.
- Doğrusu `ros2 param get /drone_<N>/mavros/param <AD>`. **Ama** her çağrı
  yeni bir düğüm açıp DDS keşfi yapıyor ve düğümde 1007 parametre var;
  ard arda çağrıların yarısı zaman aşımına düşüyor (ölçüldü: 4 istekten 2'si).
- Araç **tek düğüm** açıp `get_parameters` servisine **toplu** istek atıyor.

Araç drone üzerinde, konteynerin içinde koşar — `baslat.sh`
`ROS_LOCALHOST_ONLY=1` ile DDS'i loopback'e kapattığı için YKİ drone'un ROS
grafiğini görmez. `param_karsilastir.py` betiği SSH ile boru üzerinden
geçiriyor, drone'a dosya kopyalamaya gerek yok.

### Hedef değerler tek kaynaktan gelir

**Elle yazma.** Uçaklara yazılacak komutları üret:

```bash
python3 src/gcs/ucus_ayarlari.py --px4
```

Çıktı (14 Ağustos yapılandırması — seyir 3 m/s, aralık 12 m):

```
MPC_XY_VEL_MAX  5.0     MPC_VEL_MANUAL   3.0     MPC_ACC_HOR  2.0
MPC_TILTMAX_AIR 30.0    MPC_YAWRAUTO_MAX 25.0
```

`MAV_SYS_ID` bu listede **yok** — uçağa özgü olmalı, eşitlenmez.

**Yazarken `ros2 param set` KULLANMA** — her çağrı yeni düğüm açıp DDS keşfi
yapıyor, 1007 parametreli düğümde yarısı zaman aşımına düşüyor (ölçüldü:
5 istekten 3'ü). Bunun yerine tek düğüm / tek istek:

```bash
./deploy/yki/drone_bul.sh ylp00 \
  'docker exec -i -e AGENT_ID=1 drone1 bash -lc "source /opt/ros/jazzy/setup.bash && python3 - \
   --yaz MPC_XY_VEL_MAX=5.0 MPC_VEL_MANUAL=3.0 MPC_ACC_HOR=2.0 \
        MPC_TILTMAX_AIR=30.0 MPC_YAWRAUTO_MAX=25.0"' < src/gcs/px4_param.py
```

### Ölçülen değerler (14 Ağustos)

| Parametre | ylp00 | ylp02 | Hedef | Not |
|-----------|-------|-------|-------|-----|
| `MPC_XY_VEL_MAX` | ~~4.0~~ **5.0** | ~~4.0~~ **5.0** | `5.0` | ✅ 14 Ağu — kaçış payı + doygunluk payı |
| `MPC_Z_VEL_MAX_UP` | 1.2 | 1.2 | eşit | ✅ |
| `MPC_Z_VEL_MAX_DN` | 1.5 | 1.5 | eşit | ✅ |
| `MPC_TKO_SPEED` | 1.0 | 1.0 | eşit | ✅ |
| `MPC_LAND_SPEED` | 0.4 | 0.4 | `0.4` | ✅ 5 dk video bütçesine giriyor |
| `MPC_ACC_HOR` | 2.0 | 2.0 | `2.0` | ✅ Yürütücü ivmesi (1.5) altında |
| `MPC_XY_P` | 0.95 | 0.95 | eşit | ✅ Yürütücü hesabı buna dayanıyor |
| `COM_OBL_RC_ACT` | 0 | 0 | `0` | ✅ Offboard kaybında motor kesilmez |
| `BAT1_SOURCE` | -1 | -1 | `-1` | ✅ Regülatör; pil takılınca geri aç |
| `MC_YAWRATE_MAX` | 200 | 200 | eşit | ✅ Uçağın toparlama yeteneği |
| `MPC_TILTMAX_AIR` | ~~45~~ **30** | 30 | `30` | ✅ 14 Ağu eşitlendi |
| `MPC_YAWRAUTO_MAX` | ~~45~~ **25** | 25 | `25` | ✅ 14 Ağu eşitlendi |
| `MPC_VEL_MANUAL` | ~~4~~ **3** | ~~2~~ **3** | `3.0` | ✅ 14 Ağu eşitlendi |
| `MAV_SYS_ID` | 1 | 3 | uçağa özgü | ✅ Farklı olması ŞART |

> **Neden `MPC_TILTMAX_AIR` önemliydi:** `gorev_kanit_ucus.py`'deki
> `MAKS_EGIM_DEG` bir devrilme dedektörü ve eşiği tavanın ÜSTÜNDE olmak
> zorunda. ylp00'da tavan 45, eşik 35'ti — yani dedektör tavanın altında
> kalmıştı ve normal uçuş "devrilme" sayılıp görev havada kendini iptal
> edebilirdi. Artık ikisi de 30, eşik 35 ve `ucus_ayarlari.py` eşiği
> tavandan **türetiyor** — varsayım bir daha eskimez.

| # | Parametre | Hedef değer | Neden |
|---|-----------|-------------|-------|
| C1 | `MAV_SYS_ID` | **uçağa özgü** (tabloya bak) | İkisi de 1 olursa QGC bunları TEK araç sanar |
| C2 | `MPC_XY_VEL_MAX` | `4.0` | Kaçınmanın kaçış payı buradan; görev hızına eşitlenmez |
| C3 | `MPC_Z_VEL_MAX_UP` | eşit olmalı | Uçaklar aynı anda tırmanmalı |
| C4 | `MPC_TKO_SPEED` | eşit olmalı | — |
| C5 | `MPC_LAND_SPEED` | `0.4` | İniş süresi 5 dk video bütçesine giriyor |
| C6 | `MPC_ACC_HOR` | `2.0` | Yürütücü ivmesi (1.5) bunun altında kalmalı |
| C7 | `COM_OBL_RC_ACT` | `0` (POSCTL) | Offboard kaybında **motor kesilmez** |
| C8 | `BAT1_SOURCE` | **disabled** | Regülatörden besleme; pil takılınca geri aç |
| C9 | Pusula + ivmeölçer kalibrasyonu | geçerli | ylp02 31 Tem'de 143 µT okuyordu (sağlamı 48) |

**`MAV_SYS_ID` değiştirme yordamı `docs/cihazlar.md`'de** — üç adım
(param + FCU reboot + `tgt_system`) birlikte yapılmazsa drone sessizce kopar.
Belirti aldatıcı: paketler akar ama içerik boşalır (`mod=?`, `sat=0`).

### ✅ RC-kayıp tespiti (19 Ağustos) — İKİ UÇAKTA DA KURULU (ylp00 havada, ylp02 yerde doğrulandı)

Kumanda kapanınca FS-iA6B **susmuyor**, failsafe çerçevesini basmaya devam
ediyor; PX4 kaybı göremiyordu (`YAPILACAKLAR` P1.9). Gün içinde iki yöntem
denendi: CH6 işaret kanalı (çalıştı ama kanal harcıyordu) → **CH3 üst-uç
yöntemi** (nihai). Mantık: kayıpta alıcı gaz kanalına **2100** basar — canlı
uçuşta ulaşılamaz bir değer (tavan 2000):

```
canlı gaz tavanı 2000  <  eşik 2050  <  failsafe 2100
```

**Hava testi (19 Ağu ~19:45, ylp00):** alçak askıda kumanda kapatıldı →
**1-2 sn içinde RTL**. Motor kesilmedi. Uçtan uca doğrulandı.

**1) Alıcı tarafı** (kumanda menüsünden, alıcının flash'ına yazılır):
`End points → Ch3` üst ucu **geçici 120%** → gaz çubuğu TAM YUKARI →
`RX Setup → Failsafe → Ch3` kaydet (2100 yakalanır; FlySky kaydı **mutlak**
tutar) → üst ucu **100%'e GERİ AL**. Ölçülen: failsafe 2100, canlı tavan
2000-2001. ⚠️ Menü düzenlemesi yanlış kanala inebilir — sonrasında MUTLAKA
`rc/in` ölç (`TUZAKLAR` §0.4; bugün CH5=+100% kazası uçak düşürdü).

**2) PX4 parametreleri** (`px4_param.py --yaz` ile, tek toplu istek):

| Parametre | Değer | Neden |
|-----------|-------|-------|
| `RC_MAP_FAILSAFE` | `3` | işaret kanalı = gaz (CH3) |
| `RC_FAILS_THR` | `2050` | CH3 > 2050 → sinyal kayıp (v1.16.1 iki yönlü koşulun ÜST dalı, `rc_update.cpp:437`; eşik `RC3_MAX`'ın üstünde olmalı) |
| `RC6_MAX` / `RC6_TRIM` | `2001` / `1500` | CH6 denemesinden kalan değerler fabrikaya döndü; CH6 artık boş |

| Uçak | Alıcı Ch3 failsafe (2100) | PX4 parametreleri |
|------|---------------------------|-------------------|
| ylp00 | ✅ 19 Ağu | ✅ 19 Ağu — HAVADA doğrulandı (kumanda kapandı → 1-2 sn'de RTL) |
| ylp02 | ✅ 19 Ağu gece (2101; **CH5 kill'i de -100'e kaydedildi** — fabrika +100 bırakmıştı, P0.9) | ✅ 19 Ağu gece — bit iki yönde ölçüldü (0x1320C83F ↔ 0x1321C83F) |
| ylp01 | ✅ 25 Ağu (2100 — İKİ YÖNDE bit ölçümüyle doğrulandı) | ✅ kopya paramla gelmişti (`RC_FAILS_THR=2050`, `RC_MAP_FAILSAFE=3` ölçüldü) |

Not: ylp02'de yalnız 2 parametre yazıldı (`RC_FAILS_THR=2050`,
`RC_MAP_FAILSAFE=3`) — `RC6_*` orada zaten fabrika değerindeydi (CH6
denemesi yalnız ylp00'a yazılmıştı). İki uçağın canlı gaz tavanı da
ölçüldü: 2000-2001 < 2050 ✓.

**Doğrulama:** kumanda kapalı → `/drone_N/mavros/sys_status` →
`sensors_health`'ta RC_RECEIVER biti (`0x10000`) düşer, QGC üst barı **SARI**
olur; açık → bit 1, yeşil. (Disarmed'da yazı "Ready To Fly" kalır — normal,
`TUZAKLAR` §1.16.)

**Kalıcı kurallar:**
- **Ch3 üst ucu daima 100'de kalmalı** — 120 yapılırsa canlı tam gaz 2100'e
  ulaşır ve uçuşta yanlış "kayıp" (=habersiz RTL) tetikler
- RC yeniden kalibrasyonu `RC3_MAX`'ı canlı tavana (~2000) yazdığı sürece
  yöntem **kalibrasyona dayanıklı** (eşik 2050 üstte kalır)
- Uçuş öncesi: kumanda kapat → QGC SARI olmalı (tespit canlı mı denetimi)

⚠️ **Açık pürüz:** 19 Ağu'da bir kez, kumanda AÇIKKEN bit "kayıp"ta takılı
kaldı (CH3=1296'da bile) ve güç çevrimi ile temizlendi. Şüpheli:
`COM_RC_IN_MODE=3`'ün "ilk kaynağı tut" kilidi. Tekrar ederse QGC konsolunda
`commander check` çıktısı alınmalı — `YAPILACAKLAR` P1.9.

---

## 6. D — ESP32 mesh

| # | Ne | Nasıl |
|---|----|-------|
| D1 | Firmware yüklü (`TX DRONE`) | `firmware/esp32_mesh/TX DRONE/` |
| D2 | MAC → ID tablosu **iki firmware'de de aynı** | `RX BASE/src/main.cpp` ~128, `TX DRONE/src/main.cpp` ~71 |
| D3 | Yeni ESP takıldıysa MAC'i tabloya ekle | Tabloda olmayan MAC'ten gelen paket **reddedilir** |
| D4 | 🔴 **Firmware `eabe59f` — DÖRT kartta** (3 drone + baz) | 27 Ağu ~03:00-03:40. `TIP_OLAY` taşıyan sürüm. **Pi üzerinden**, kablo/konnektör sökmeden: konteyner durdur → operatör **BOOT tut + EN'e dokun** → `esptool --before no-reset write-flash` → EN → konteyner başlat. Baz USB'den (`--no-stub` şart, `TUZAKLAR` §4.4). Dördünde de **hash doğrulandı** |
| D5 | **Uçandaki firmware artık BİLİNEN bir commit** | D4'ten önce belirsizdi: ylp01'in `.bin`'i 25 Ağu 00:52'de, `ccb915c` ise 00:56'da — binary commit'ten ESKİYDİ. ⚠️ `.bin` dosya boyutu hizalama yüzünden yuvarlanıyor, **provenans göstergesi olarak kullanılamaz** (eski ve yeni kaynak aynı boyutu veriyor). Doğrulama davranıştan yapılır |

---

## 7. Herkese açık erişim (bekleyen iş)

Bunlar henüz **hiçbir uçakta tam değil** — `YAPILACAKLAR.md` §1.

### Wi-Fi ağları

**ylp00 ve ylp02'de kayıtlı** (15 Ağustos):

| Bağlantı adı | SSID | Öncelik | Güç tasarrufu |
|--------------|------|---------|---------------|
| `rpissid` | `rpissid` | **10** (tercih edilen) | kapalı |
| `iphone-hotspot` | `iPhone` | 0 (yedek) | kapalı |

Şifreler **repoda yok**, takım içinde paylaşılıyor. Gerekirse çalışan bir
uçaktan okunabilir: `sudo nmcli -s -g 802-11-wireless-security.psk
connection show <ad>`.

**Öncelik neden böyle:** büyük sayı önce denenir. Bugüne kadar çalışan ağ
(`rpissid`) tercih edilen kalsın ki mevcut kurulum değişmesin; iPhone yalnız
o yokken devreye girsin. İkisi de açıksa drone tanıdık ağa gider.

**Güç tasarrufu KAPALI olmak zorunda** — açık kalırsa Pi boşta kalınca SSH'a
cevap vermiyor, uyanması ~30 sn ping istiyor (yaşandı).

⚠️ **`iPhone` SSID'si doğrulanmadı** — ekleme sırasında telefon kapalıydı,
tarayıp teyit edemedik. iPhone hotspot'ları cihaz adını alır
(**Ayarlar → Genel → Hakkında → Ad**) ve SSID'ler **büyük/küçük harfe
duyarlıdır**. "Ahmet'in iPhone'u" gibiyse düzelt:

```bash
sudo nmcli connection modify iphone-hotspot wifi.ssid "GERÇEK AD"
```

**Yeni ağ eklemek:**

```bash
sudo nmcli connection add type wifi con-name <ad> ssid '<SSID>' \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk '<sifre>' \
    connection.autoconnect yes connection.autoconnect-priority 0
sudo nmcli connection modify <ad> 802-11-wireless.powersave 2
```

> **sudo parolası ≠ WiFi parolası.** İkisi ayrı; karıştırıldı ve bir tur
> kaybettirdi. Parolalar takım içinde paylaşılıyor, repoya yazılmıyor.

### SSH anahtarları

**İkisinde de Osman'ın ve Berk'in anahtarı var:**

| Anahtar | ylp00 | ylp01 | ylp02 |
|---------|-------|-------|-------|
| Osman | ✅ 17 Ağu gecesi | ❌ | ✅ 17 Ağu sabahı |
| Berk (MacBook) `berk@github` | ✅ 18 Ağu | ❌ | ✅ 18 Ağu |

🔴 **ylp01 döndüğünde İKİSİNİ BİRDEN kur** — yoksa aynı "bağlanamıyorum"
turu üçüncü uçakta baştan yaşanır. Berk'in parmak izi:
`SHA256:ADq8YfUQqzqkKQC+4FXkBf8AmQbyCPsn5BgpI+FvXi0`

Parola girişi **açık** (doğrulandı), yani her üye kendi anahtarını
**kendisi** kurabilir:

```bash
ssh-keygen -t ed25519                  # kendi bilgisayarında, bir kez
ssh-copy-id <KULLANICI>@<ip>           # parolayla girer, anahtarını ekler
```

---

### 🔴 A13-A15 — çökme kaydı, okunabilirlik, izleme sıklığı (22 Ağustos)

**Neden:** 21 Ağustos'ta ylp00'ın Pi'si uçuştan ~2 dk sonra **öldü ve öyle
kaldı** (kırmızı ışık, elle açmak gerekti). Sebep **bulunamadı** çünkü
çökme izi hiç tutulmuyordu. Ayrıntı: `YAPILACAKLAR.md` **P0.17**,
teşhis yöntemi: `TUZAKLAR.md` **§2.17**.

**Ne kuruldu:**

| | ne yapar |
|---|---|
| `kernel.panic=10` + `panic_on_oops=1` | panikte sonsuza kadar durmak yerine 10 sn'de yeniden başlar |
| `ramoops` (overlay **+** cmdline) | çekirdeğin son sözünü RAM'de saklar, yeniden başlatmada bulunur |
| `yelpence-cokme.service` | izleri `~/yelpence_ws/gunluk/cokme/` altına **644** kopyalar |
| izleme `OnUnitActiveSec` 60 → 10 sn | gerilim/ısı/yük örneklemesi sıklaştı |

⚠️ **Pi 5'te `ramoops` overlay TEK BAŞINA YETMİYOR.** İlk denemede yalnız
`dtoverlay=ramoops` konuldu, iki uçakta uygulandı, yeniden başlatıldı ve
ölçüldü: bellek ayrıldı ama **sürücü bağlanmadı**:

```
OF: reserved mem: invalid reg property size in 'ramoops@b000000'
/proc/iomem'de ramoops: YOK · /sys/fs/pstore bagli ama ARKASINDA DEPO YOK
```

Overlay'in `reg` adres biçimi Pi 5'in 64-bit ağacıyla uyuşmuyor. Sürücü
çekirdeğe **gömülü**, o yüzden `cmdline.txt`'den doğrudan adreslenmeli:

```
ramoops.mem_address=0x0b000000 ramoops.mem_size=0x10000
ramoops.record_size=0x2000 ramoops.console_size=0x2000 ramoops.dump_oops=1
```

`izleme_kur.sh` 8/8 artık **ikisini birden** yapıyor.

**Uygulamak için** (`sudo` parola sorduğu için **etkileşimli** bağlan —
`drone_bul.sh <ad> '<komut>'` biçimi ÇALIŞMAZ):

```bash
./deploy/yki/drone_bul.sh ylp00       # komut vermeden -> kabuk acilir
sudo bash ~/yelpence_ws/izleme_kur.sh
sudo reboot                            # ramoops/cmdline degistiyse SART
```

Betik uçakta yoksa: `./deploy/rpi/dagit.sh <ad>` **taşımaz** —
`izleme_kur.sh` ve `cokme_kopyala.sh` elle kopyalanır:

```bash
./deploy/yki/drone_bul.sh <ad> 'cat > ~/yelpence_ws/izleme_kur.sh'   < deploy/rpi/izleme_kur.sh
./deploy/yki/drone_bul.sh <ad> 'cat > ~/yelpence_ws/cokme_kopyala.sh' < deploy/rpi/cokme_kopyala.sh
```

**Doğrulama:**

```bash
cat /proc/sys/kernel/panic                     # 10
dmesg | grep -i 'Registered ramoops'           # satir CIKMALI
systemctl cat yelpence-izle.timer | grep OnUnit  # 10s
ls ~/yelpence_ws/gunluk/cokme/                 # cokme yoksa BOS olmasi normal
```

> ℹ️ `dmesg`'de `ramoops ...: probe with driver ramoops failed with error -22`
> görürsen **panik yok**: overlay'in ikinci kez kaydolma denemesi,
> `already initialized` diyor. Asıl kanıt `Registered ramoops` satırı.

**SAHADA SINANDI (ylp02, 22 Ağustos):** `sudo bash -c 'echo c > /proc/sysrq-trigger'`
→ Pi paniğe girdi → **10 sn'de kendi döndü** → `console-ramoops-0` (8 KB) ve
`dmesg-ramoops-0` (13,3 KB) kopyalandı ve **okundu**. Çağrı yığını net:
`sysrq_handle_crash / write_sysrq_trigger / vfs_write / el0_svc`.
Gerçek bir ölümde bu yığın asıl suçlu sürücüyü gösterecek.

🔴 **Pi öldüğünde GÜCÜ KESME** — `ramoops` izi RAM'de, güç giderse silinir.

## 8. Değişiklik defteri — git'te

Bu bölümde 23 kayıtlık, 762 satırlık bir Pi değişiklik defteri vardı.
**29 Ağustos 2026'da çıkarıldı**: taşıdığı *durum* bilgisi zaten yukarıdaki
A-matrisinde (§3) uçak uçak duruyor; geri kalanı "ne zaman yapıldı" kaydıydı
ve onu git zaten tutuyor.

```bash
git show 783afab:docs/RPI_ESITLEME.md     # kesimden önceki tam defter
```

> ⚠️ **Yeni bir Pi değişikliği yaptığında buraya değil, §3'teki A-matrisine
> satır ekle** — okunması gereken tek yer orası. "Hangi uçakta var" sütunu
> boş bırakılmaz; bu belgenin var olma sebebi o sütun.
