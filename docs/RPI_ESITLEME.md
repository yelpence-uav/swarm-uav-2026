# RPİ EŞİTLEME DEFTERİ — geri gelen drone'u hizaya getirme

**Son güncelleme:** 25 Ağustos 2026, 23:50 — tek-üretici baslat.sh + DTR/RTS köprü düzeltmesi üç uçakta

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
> Ayrıntı: `CA.md` §7.3.
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

**Her uçuştan önce çalıştır.** Farklı olanları kırmızı basar, uçağa özgü
olanları (`MAV_SYS_ID`) ayırır.

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

## 8. DEĞİŞİKLİK DEFTERİ

Her Pi değişikliği buraya, en yeni en üste.

### 2026-08-25 (gece ~23:45) — tek-üretici `baslat.sh` + DTR/RTS'li `esp32_bridge` ÜÇ uçağa

`20c2b01` (baslat.sh: TEK-ÜRETİCİ geçişi + FORMASYON_SURUYOR) ve `89a16cf`
(esp32_bridge: seri açılışta DTR/RTS tutulmaz). Kopya + `colcon build
--packages-select swarm_control` + restart. Doğrulama: açılış logunda
`velocity_only=true`, TEK-URETICI satırı YOK (formasyon gözlemde — davranış
korundu), üçü panele RTK-Fix'le döndü.

| Uçak | Durum |
|------|-------|
| ylp00 | ✅ |
| ylp01 | ✅ |
| ylp02 | ✅ |

### 2026-08-25 (akşam) — `6258eab` körlük muafiyeti ÜÇ uçağa dağıtıldı

Konteyner içine kopyalanan dosyalar: `ca_core.py`,
`collision_avoidance_node.py` (→ `/ws/src/swarm_core/...`), `baslat.sh`
(→ `/ws/baslat.sh`). Ardından `colcon build --packages-select swarm_core`
+ `docker restart`. Doğrulama: üçünde `ros2 param get /collision_avoidance
korluk_yer_esigi_m` = **1.5**.

| Uçak | Durum |
|------|-------|
| ylp00 | ✅ |
| ylp01 | ✅ |
| ylp02 | ✅ |

### 2026-08-20 (5) — açılış sertleştirmesi + kayıt onarımı (ylp00 + ylp02)

Kod tarafı, `dagit.sh` ile gitti. **Etkin olması için konteyner yeniden
başlatıldı** — ikisi de yapıldı, doğrulandı: 11 düğüm, `disarm`,
`gunluk/son/kayit_onar.log` var.

| ne | ylp00 | ylp01 | ylp02 |
|---|---|---|---|
| `baslat.sh` ağ beklemesi (P0.13) | ✅ | ✅ *(klon)* | ✅ |
| `baslat.sh` `gps_saat` sert zaman aşımı (P0.13) | ✅ | ✅ *(klon)* | ✅ |
| `kayit_onar.sh` + açılışta arka planda çağrısı | ✅ | ✅ *(klon)* | ✅ |
| sysctl writeback 1 sn (A8) | ✅ | ✅ *(klon, ölçüldü)* | ✅ |
| `mcap` kurtarma aracı (A11) | ✅ | ✅ *(klon, ölçüldü)* | ✅ |
| docker log döndürme (A12) | ✅ | ✅ *(24 Ağu, drone2)* | ❌ |

**A12 neden ylp02'de yok:** docker'ın log ayarları oluşturma anında
sabitleniyor; `docker restart` yetmiyor, `docker rm -f` + `run_drone.sh`
gerekiyor. ylp02'de bozukluk olmadığı için o adım atlandı — tek kazanç
döndürme. Sırası gelince bölüm 2'deki 4. adım.

**Ölçülen sonuç:** düşüşte kaybedilen uçuş verisi penceresi
**~30 saniyeden ~4 saniyeye** indi. Üç katman birlikte çalışıyor:

```
dugum yazar -> cekirdek RAM'de tutar -> karta yazar
                      ^
               A8: 30 sn yerine 1 sn        <- kapanmis .mcap dosyalari kurtuldu

acilista: kayit_onar.sh -> bozuk son parcayi mcap recover ile kurtar
                        -> reindex ile metadata.yaml'i yeniden uret
```

Ayrıntı, sayılar ve tuzaklar: `docs/TUZAKLAR.md` §1.18 ve §1.19.

### 2026-08-20 (4) — `mcap` kurtarma aracı ylp00 + ylp02'ye kondu, DEPODA YOK

**Elle kopyalandı, `dagit.sh` taşımıyor.** ylp01 döndüğünde bu adım
**hatırlanmak zorunda** — depoya koyup koymamaya karar verilmedi.

| | değer |
|---|---|
| konum | `~/yelpence_ws/bin/mcap` (konteynerde `/ws/bin/mcap`) |
| sürüm | MCAP CLI 0.3.0, `mcap-linux-arm64`, 12 733 936 bayt |
| sha256 | `be9734ef63ada9d0cc7a3aa41378ab65fd482601e5f5b3b52098d8e6553deabf` |
| kaynak | `https://github.com/foxglove/mcap/releases/download/releases%2Fmcap-cli%2Fv0.3.0/mcap-linux-arm64` |
| ylp00 | ✅ | 
| ylp01 | ❌ **dönünce kurulacak** |
| ylp02 | ✅ |

**Ne işe yarıyor:** güç kesildiğinde yazılmakta olan `.mcap` parçası bozuk
kalıyor ve `kayit_onar.sh` onu karantinaya alıyordu — yani o parçadaki veri
okunamıyordu. Bu araçla parça **atılmadan önce kurtarılıyor**: ölçüldü,
831488 baytlık bozuk parçadan **10588 mesaj / 25.8 saniye** geri geldi.
Araç yoksa betik eski davranışına döner ve çalışmaya devam eder — yani
eksikliği **hata vermez**, sessizce daha çok veri kaybettirir.

Ayrıntı ve tuzakları: `docs/TUZAKLAR.md` §1.19.

Kurmak için (dizüstünden, ikili orada mevcut değilse yukarıdaki adresten
indirilir; sha256 **doğrulanmalı**):

```bash
./deploy/yki/drone_bul.sh ylp01 \
  'mkdir -p ~/yelpence_ws/bin && cat > ~/yelpence_ws/bin/mcap \
   && chmod +x ~/yelpence_ws/bin/mcap && sha256sum ~/yelpence_ws/bin/mcap' \
  < mcap-linux-arm64
```

### 2026-08-20 (3) — 🔴 ylp00 konteyneri YENİDEN OLUŞTURULDU, ylp02 OLUŞTURULMADI

**Tek uçakta yapıldı — ylp02 geride kaldı.** Fark şu: konteyner log
döndürmesi (`--log-opt max-size=10m --log-opt max-file=3`) **yalnız
ylp00'da devrede**, çünkü docker log ayarları **oluşturma anında** sabitlenir;
`docker restart` yetmez.

| | ylp00 (drone1) | ylp02 (drone3) |
|---|---|---|
| konteyner kimliği | `931b81f5a62b` (yeni) | `5d5c4915a1b8` (15 Ağu'dan) |
| log döndürme | **VAR** (10m × 3) | **YOK** (sınırsız) |
| json log NUL bozukluğu | temizlendi | zaten yoktu (0 NUL) |

**Neden ylp00:** json-file logunda iki NUL koşusu vardı (1602 + 433 bayt,
16 Ağustos 23:34) ve `docker logs` **tam okumada** çöküyordu. Ayrıntı ve
tuzağın kendisi: `docs/TUZAKLAR.md` §1.18.

**ylp02'yi hizaya getirmek için** (acil değil — orada bozukluk yok, tek
kazanç döndürme):

```bash
./deploy/rpi/dagit.sh ylp02                     # guncel run_drone.sh gitsin
./deploy/yki/drone_bul.sh ylp02 \
  'docker rm -f drone3 && cd ~/yelpence_ws && bash run_drone.sh 3'
```

⚠️ Yeniden oluşturma **disarm halde** yapılır ve ROS yığını ~4 dk kapalı
kalır (`gps_saat` beklemesi dahil). Yapılandırma kaybolmaz: her şey `/ws`
bağlamasında (`suru_dugumleri`, `kacinma`, `tgt_system`, `gozlem`);
yazılabilir katmanda yalnız `.ros`/`.colcon` önbellekleri var (29 MB,
kendiliğinden yeniden üretilir). Env varsayılanları `run_drone.sh` ile
birebir aynı — doğrulandı.

**Doğrulandı (ylp00, 21:15):** `docker logs` tam okuma hatasız, `--since`
çalışıyor, 11 düğüm ayakta, `connected=true armed=false`, açılış
`/ws/suru_dugumleri`'nden aynı düğümleri açtı.

### 2026-08-20 — konteynerler yeniden başlatıldı (ylp00 + ylp02)

**Uçak yazılımına dokunulmadı**, bayraklar değişmedi, kod hâlâ `d9be7c9`.
Yapılan tek şey `docker restart`.

**Neden:** ikisi de **ağdan önce** kalkmıştı ve ROS yığını eski adrese
bağlanmıştı. Ölçüm (ylp00):

```
Pi acilis            15:51      (/proc/uptime = 1523 s)
konteyner + mavros   15:52:41
wlan0 DHCP kirasi    15:56:32   <- DORT DAKIKA SONRA
```

Belirti: her düğüm `ddsi_udp_conn_write to udp/172.19.167.x failed` basıyordu
(bir önceki ağın adresi) ve `mavros.log` **442 MB**'a şişmişti. ylp00 daha
kötüydü: `baslat.sh:211` `gps_saat.py`'yi arka plana atmadan çağırıyor, süreç
`--bekle 150`'ye rağmen 25+ dakika takıldı ve **`baslat.sh`'in geri kalanı hiç
çalışmadı** — yalnız mavros vardı.

**Restart sonrası (ikisinde de):** 12 düğüm ayakta · **0 ddsi hatası** ·
`mavros.log` 20 KB · disk 17 GB boş.

| Ne | ylp00 | ylp02 | ylp01 (dönünce) |
|----|-------|-------|-----------------|
| Konteyner restart (16:37) | **VAR** | **VAR** | — |
| Bayraklar değişti mi | hayır | hayır | — |

🔴 **Kalıcı düzeltme yapılmadı** — `YAPILACAKLAR.md` **P0.13**: `baslat.sh`
mavros'tan önce ağın hazır olmasını beklemeli (~10 satır, ağ yoksa yine devam
etsin) ve `gps_saat.py` başlatmayı **bloke etmemeli**.

> 💡 **Uçuş öncesi tek satırlık kontrol:**
> `docker exec droneN ps | grep -c "ros2 run"` → **12 olmalı.** Bugün bu komut
> bir sabahı kurtarırdı.

### 2026-08-18 (2) — `yer_testi` bayrağı SİLİNDİ (ylp00 + ylp02)

G2 gözlem uçuşu için iki uçaktan da `~/yelpence_ws/yer_testi` **silindi** ve
konteynerler yeniden başlatıldı.

🔴 **Uçaklar bu hâlde bırakıldı: kalkış komutunu artık alıyorlar.** Yer testi
(arm olup kalkmama) yapılacaksa geri konmalı:

```bash
./deploy/yki/drone_bul.sh ylp00 'touch ~/yelpence_ws/yer_testi && docker restart drone1'
./deploy/yki/drone_bul.sh ylp02 'touch ~/yelpence_ws/yer_testi && docker restart drone3'
```

`gozlem` ve `kacinma` bayraklarına dokunulmadı — ikisi de duruyor.

### 2026-08-18 — Berk'in SSH anahtarı (ylp00 + ylp02)

Uçak yazılımına **dokunulmadı**; yalnız `~/.ssh/authorized_keys`'e bir satır
eklendi (`ssh-copy-id`, parolayla). Konteynerler yeniden başlatılmadı,
bayraklar değişmedi. ylp01 için bekliyor.

### 2026-08-17 (3) — uçaklar `main`'e alındı (`dagit.sh`, e012dba)

| Ne | ylp00 | ylp02 | ylp01 (dönünce) |
|----|-------|-------|-----------------|
| `src/` = repo `main` (176 dosya, md5) | **VAR** | **VAR** | gerekli |
| `.surum` = `e012dba` / `main` / `+KIRLI` yok | **VAR** | **VAR** | gerekli |
| `swarm_missions` `build/` temizlenip yeniden derlendi | **VAR** | **VAR** | gerekebilir |
| Konteyner yeniden başlatıldı (yeni kod yüklendi) | 11:35 | 11:41 | — |

**Öncesi:** iki Pi de `commit=0dfa0ad +KIRLI dal=feature/dagitik-suru`
diyordu; o commit ve dal bu depoda yoktu. Eski depodan (`yelpence-2026-swarm`)
Eyüp'ün makinesinden dağıtılmıştı.

> 🗄️ **Silinmeden önce yedeklendi:** `saha/pi-kod-15agustos` (`52ff027`,
> `origin`'de) — uçaklarda gerçekten koşan `src/` ağacının birebir kopyası.
> `dagit.sh` `--delete` ile çalışıyor; yedek olmasa geri dönüşsüz giderdi.
> ylp00'dan alındı, ylp02 ile md5'i aynı çıktı.

**İki tuzak çıktı, ikisi de yazıldı:** `dagit.sh` derleme çökse bile
"başarılı" diyor (`TUZAKLAR.md` §1.14) · depodan silinen dosya bayat `build/`
dizinini kırıyor (§2.8). İkincisi `swarm_missions`'ı ikisinde de çökertti;
elle temizlenip derlendi.

**Dağıtım sonrası doğrulandı (ikisinde de):** 11 düğüm ayakta ·
`/drone_N/control/setpoint[/raw]` konularında **tek üretici** · MAVROS
`connected: true`, `armed: false`, `AUTO.LOITER` · saat dizüstüyle aynı.

⚠️ Bu dağıtımla birlikte `formation_node`'un `sitl_mode` varsayılanı `True`
olarak uçaklara girdi — origin ve konum kapıları atlanıyordu.
✅ **Aynı gün düzeltildi** (17 Ağu 14:30, `600ca65`): kod varsayılanı `False`
yapıldı **ve** `baslat.sh` `-p sitl_mode:=false` açıkça geçiyor. İki uçağa
dağıtıldı, md5 `bd40492c` ile doğrulandı. Tarihçe: `GUNLUK.md` 17 Ağustos.

### 2026-08-17 (2) — GPS saat beklemesi 25 → 150 sn + ylp02'ye SSH anahtarı

| Ne | ylp00 | ylp02 | ylp01 (dönünce) |
|----|-------|-------|-----------------|
| `baslat.sh` → `gps_saat.py --bekle 150` | **VAR** | **VAR** | gerekli |
| Osman'ın `id_ed25519.pub` → `authorized_keys` | **VAR** | **VAR** | gerekli |

**Neden.** Her iki uçağın son açılış logunda aynı satır vardı:

```
[gps_saat] GPS zamani 25 sn icinde gelmedi. Saat DEGISMEDI.
```

Ölçülen zincir: Pi açılışı `01:52:36` → konteyner `01:52:49` → mavros +
`sleep 15` → `gps_saat --bekle 25` pes ediyor `~01:53:30`. Yani GPS'e güç
verildikten sonra topu topu **~54 sn** tanınıyor; Here4 soğuk başlangıçta o
sürede kilitlenmiyor. Sonuç: **ylp00 7 sa 58 dk, ylp02 10 sa 15 dk geride,
ikisi arasında 2 sa 17 dk fark.** Uçuşu bozmuyor (`consensus_node` bütün
tazelik hesabını `time.monotonic()` ile ve yerel alım anına göre yapıyor —
`consensus_context.py:29`), ama çapraz uçak kayıt karşılaştırmasını —
`gps_saat.py`'nin var olma sebebini — imkânsız kılıyor.

Uzatmanın bedeli yok: `gps_saat.py` ilk geçerli örneği alınca hemen çıkıyor,
yani sıcak GPS'te gene saniyeler sürer.

**Nasıl dağıtıldı — `dagit.sh` KULLANILMADI, bilerek.** Yalnız `baslat.sh`
rsync'lendi ve md5 ile doğrulandı (`0dacdf44…`, repo ile birebir). Sebep bir
sonraki maddede.

> ⚠️ **Uçaklardaki ROS kodu bu depodan üretilemiyor.** İki Pi'nin de
> `~/yelpence_ws/.surum` dosyası şunu diyor:
>
> ```
> commit=0dfa0ad +KIRLI   dal=feature/dagitik-suru
> dagitan=egUbuntu        15 Ağustos 20:34
> ```
>
> `0dfa0ad` bu depoda **yok**, `feature/dagitik-suru` dalı da yok —
> `git ls-remote origin` yalnızca `main` döndürüyor. Üstelik `+KIRLI`, yani
> commit elimizde olsa bile birebir yeniden üretilemezdi. Şu an uçan kodu
> okuyabildiğimiz tek yer Pi'lerin kendisi.
>
> **Sonuç: `dagit.sh` çalıştırmak `src/`'yi `main` ile ezer ve uçan kodu
> değiştirir.** Bu dal Eyüp'ten alınana kadar `dagit.sh` çalıştırma. Takip:
> `YAPILACAKLAR.md` P0.

### 2026-08-17 — ylp00'a SSH anahtarı (tek kalıcı değişiklik)

| Ne | ylp00 | ylp02 |
|----|-------|-------|
| Osman'ın `id_ed25519.pub` → `authorized_keys` | **VAR** | yok |

ylp02 açıldığında: `ssh-copy-id yelpence02@<ip>`.

⚠️ Aynı gece `gcs_url` = `udp://:14555@` **denendi ve doğrulandı**, sonra
operatör kararıyla **geri alındı** — iki uçak da `udp-b://:14555@14550`'de,
yani bu konuda ayrışma **yok**. Ölçüm ve gerekçe: `TUZAKLAR.md` §7.1.
Uygulanmasına karar verilirse **iki uçakta birden** yapılmalı, yoksa
düzeltilmemiş olan yayın yapıp ağı boğmaya devam eder.

### 2026-08-15 (2) — ilk iki sürü düğümü açıldı (ADIM 1 geçti)

**Yeni bayrak dosyaları** — ylp01 döndüğünde bunlar da gerekli:

| Dosya | İçerik | ylp00 | ylp01 | ylp02 |
|-------|--------|-------|-------|-------|
| `~/yelpence_ws/suru_dugumleri` | `origin consensus` | ✅ | ❌ | ✅ |
| `~/yelpence_ws/origin` | `38.6905999 39.1611543 1216.03` | ✅ | ❌ | ✅ |
| `~/yelpence_ws/yer_testi` | (boş) ⚠️ | ✅ | ❌ | ✅ |

⚠️ **`origin` üç uçakta da AYNI değer olmalı** — farklı olursa formasyonlar
uçaktan uçağa kayar. Saha değişirse üçünde birden güncelle.

⚠️ **`yer_testi` uçuştan önce SİLİNMELİ** (`rm` + `docker restart`). Açıkken
uçak ARM olur ama kalkmaz.

Kod tarafı `dagit.sh` ile geliyor (commit `712f933` ve sonrası):
`esp32_bridge` `healthy` türetimi, `agent_fsm` `yer_testi` + ARMING reddi
logu, `baslat.sh` origin düğümü ve consensus parametreleri.

### 2026-08-15 — konteyner YENİDEN YARATILDI (`--cap-add SYS_TIME`) + GPS saat

⚠️ **Bu, `docker restart` değil `docker rm -f` + `run_drone.sh` gerektirir.**
ylp01 döndüğünde konteyneri yeniden yaratmadan `SYS_TIME` gelmez ve saat
düzeltmesi sessizce çalışmaz (betik "IZIN YOK" yazıp çıkar).

**Yapılan:**

1. **Kod dağıtıldı** — `dagit.sh`, commit `857db32`. Yeni: `gps_saat.py`,
   düzeltilmiş `preflight_checker.py`, dosyadan düğüm açan `baslat.sh`.
2. **`run_drone.sh` artık Pi'lere dağıtılıyor.** 15 Ağustos'ta görüldü ki
   Pi'lerde **hiç yoktu** — konteyner yaratma tarifi yalnız dizüstündeki
   repoda duruyordu. Sahada dizüstü olmadan konteyner yaratılamazdı.
3. **Konteynerler yeniden yaratıldı**, `--cap-add SYS_TIME` ile.
4. **ylp00'a açık `AGENT_ID=1` verildi.** Önceden env'de hiç yoktu;
   `baslat.sh`'in varsayılanı (1) sayesinde doğru çalışıyordu ama örtüktü.

| Uçak | Durum |
|------|-------|
| ylp00 | ✅ `CAPADD=[SYS_TIME]`, `AGENT_ID=1`, `.surum` `857db32`, 5 düğüm |
| ylp01 | ❌ yerde — **döndüğünde 1-4'ün hepsi gerekli** |
| ylp02 | ✅ `CAPADD=[SYS_TIME]`, `AGENT_ID=3`, `tgt_system=3` korundu, `.surum` `857db32` |

**Yeni bayrak dosyaları** (ikisinde de şu an **yok** = varsayılan davranış):

| Dosya | Etkisi |
|-------|--------|
| `~/yelpence_ws/suru_dugumleri` | Varsa `SURU_DUGUMLERI` env'ini **ezer**. Düğüm açmak: `echo consensus > ...` + `docker restart` |
| `~/yelpence_ws/gps_saat_kapali` | Varsa açılışta GPS'ten saat düzeltmesi yapılmaz |

**Açılış logunda görülmesi gerekenler** (ikisinde de doğrulandı):

```
[baslat] AGENT_ID=<1|3>
[gps_saat] GPS(FCU)=...  sistem=...  fark=+0.125 sn
[gps_saat] fark esigin (3.0 sn) altinda — saate dokunulmadi.
[baslat] ucus ayarlari dosyadan: yatay=3.0 dikey=1.0
[baslat] suru dugumleri KAPALI (SURU_DUGUMLERI bos)
```

**Neden GPS saat:** Pi 5'in RTC'sinde yedek pil yok, açılışta saat ~11 saat
geriden geliyor. Ayrıntı ve ölçüm `cihazlar.md` ⏰ bölümünde.

**Ölçüm:** `ylp00 − ylp02 = +0.121 sn` (ölçüm gürültüsü ±0.3 sn, SSH gidiş
dönüşünden). Yani hassasiyet içinde uyuşuyorlar.

⚠️ **Sahada doğrulanmadı:** internetsiz açılışta saatin gerçekten
düzeldiği henüz görülmedi — NTP her seferinde önce yetişti. İlk saha
çıkışında `gunluk/son/gps_saat.log`'a bak.

### 2026-08-14 (3) — canlı parametre + günlük bekçisi büyütüldü

**Yapılan:**
- `px4_bridge.py`: **canlı parametre geri çağrısı** eklendi. Yürütücü
  ayarları uçak havadayken değiştirilebiliyor; konteyner yeniden başlatmaya
  gerek yok. Dosya iki uçağa dağıtıldı.
  > 🔴 **O gün "`--symlink-install` sayesinde `/ws/src`'e kopyalamak yeterli,
  > derleme gerekmiyor" yazılmıştı — YANLIŞ.** 17 Ağustos'ta ölçüldü: Python
  > kaynağı `build/` altına **kopyalanıyor**, sembolik bağ kurulmuyor. Yani
  > `rsync` tek başına **koşan kodu değiştirmiyor**; `colcon build` şart.
  > `dagit.sh` bunu zaten yapıyor. Ayrıntı: `TUZAKLAR.md` §2.11.
- Günlük bekçisi 100/25 MB → **500/125 MB** + **dizin geneli 3 GB** tavanı.

| Uçak | Durum |
|------|-------|
| ylp00 | ✅ `px4_bridge.py` md5 `e6927180...`, bekçi 500/125+3GB |
| ylp01 | ❌ yerde — **döndüğünde ikisi de gerekli** |
| ylp02 | ✅ aynısı |

**Canlı değiştirilebilenler** (`ros2 param set /px4_bridge <ad> <deger>`,
ya da güvenilir yol `px4_param.py --ns /px4_bridge --yaz <ad>=<deger>`):

```
guided_hiz_yatay_mps      0.1 - 10.0
guided_hiz_dikey_mps      0.1 -  5.0
guided_ivme_yatay_mps2    0.1 -  5.0
guided_ivme_dikey_mps2    0.1 -  5.0
guided_tasma_m            0.5 - 20.0
guided_konum_kp           0.1 -  3.0
guided_telafi_orani       0.0 -  1.0
```

Bunların dışındaki her parametre **reddedilir** (`agent_id`, kill/arm
kanalları, kalkış kilidi — kimlik ve güvenlik kablolaması).

> ⚠️ **Canlı değişiklik KALICI DEĞİL.** Konteyner yeniden başlayınca
> `/ws/ucus_ayarlari.env`'deki değer geçerli olur. Kalıcı istiyorsan
> `ucus_ayarlari.py`'yi düzenle, `--kabuk` ile üret, dağıt.

### 2026-08-14 (2) — uçuş ayarları tek kaynağa bağlandı

**Yapılan:**
- `baslat.sh`: `/ws/ucus_ayarlari.env` varsa **source ediliyor**. Hız/ivme
  artık `src/gcs/ucus_ayarlari.py --kabuk` çıktısından geliyor; `baslat.sh`'te
  elle yazılı değil. Env öncelikli (`docker run -e` dosyayı ezer).
- `/ws/ucus_ayarlari.env` dağıtıldı: `GUIDED_HIZ_YATAY=3.0` (2.0'dan),
  `GUIDED_HIZ_DIKEY=1.0`, `GUIDED_IVME_YATAY=1.5`, `KANAT_ALFA_DEG=45.0`
- **PX4 parametreleri eşitlendi** (`px4_param.py --yaz`, tek düğüm/tek istek):

  | Parametre | ylp00 | ylp02 |
  |-----------|-------|-------|
  | `MPC_XY_VEL_MAX` | 4.0 → **5.0** | 4.0 → **5.0** |
  | `MPC_VEL_MANUAL` | 4 → **3.0** | 2 → **3.0** |
  | `MPC_TILTMAX_AIR` | 45 → **30** | 30 (değişmedi) |
  | `MPC_YAWRAUTO_MAX` | 45 → **25** | 25 (değişmedi) |
  | `MPC_ACC_HOR` | 2.0 (teyit) | 2.0 (teyit) |

- **Konteynerler yeniden başlatıldı**, yeni ayarlar canlıda doğrulandı:
  `guided_hiz_yatay_mps:=3.0`, `[baslat] gunluk bekcisi: tavan 100 MB`,
  `[baslat] ucus ayarlari dosyadan: yatay=3.0`

**Doğrulama:** `param_karsilastir.py` → *"Uçaklar arası ayrışma yok
(16 parametre)"*, yalnız `MAV_SYS_ID` farklı (doğru).

| Uçak | Durum |
|------|-------|
| ylp00 | ✅ tamamlandı |
| ylp01 | ❌ yerde — **döndüğünde `ucus_ayarlari.py --px4` çıktısını uygula** |
| ylp02 | ✅ tamamlandı |

> **`ros2 param set` KULLANMA** — her çağrı yeni düğüm açıp DDS keşfi yapıyor
> ve düğümde 1007 parametre olduğu için yarısı zaman aşımına düşüyor
> (ölçüldü: 5 istekten 3'ü). Bunun yerine `px4_param.py --yaz`.

### 2026-08-14 — günlük boyut bekçisi + disk temizliği

**Sorun:** İki drone'un da kök diski %100 doldu (0 bayt boş).
`gunluk/mavros.log` ylp00'da 18.64 GB, ylp02'de 21.57 GB. Uçuş kayıtları
suçsuz (`kayit/` 4.6 / 3.0 GB). Disk dolunca `ros2 bag` yazamaz →
**uçuş kaydedilmez.**

**Kök neden:** `Warning: mavconn: udp1: sendto: Network is unreachable, retrying`
— 200 bin satırlık örnekte 99.760 tanesi bu. `udp1` = `gcs_url` ile QGC'ye
MAVLink ileten uçnokta. WiFi düştüğünde MAVROS her MAVLink mesajı için bir
uyarı basıyor; 20 Hz yayın hızlarında saniyede yüzlerce satır. Bu satırlar
mavconn kütüphanesinin kendi stderr'inden geliyor, `--log-level` ile susmuyor.

**Yapılan:**
- Eski açılış dizinleri silindi, çalışan açılışın logları boşaltıldı
  (konteyner içinden root olarak — dizinler `root` sahipli, SSH kullanıcısı silemiyor)
- `baslat.sh`: 21 günlük yönlendirmesi `>` → `>>` (O_APPEND; yerinde kırpma
  ancak böyle seyrek dosya üretmeden çalışır — test edildi)
- `baslat.sh`: günlük bekçisi eklendi — 60 sn'de bir tarar, **iki kapı**:
  1. **Dosya başına:** 500 MB'ı aşanın **son 125 MB'ı** korunur
  2. **Dizin geneli:** `/ws/gunluk` 3 GB'ı aşarsa en eski açılışlar silinir
     (en yeni ikisi her zaman kalır)
  Kırpma `bekci.log`'a zaman damgasıyla yazılır.

  **Neden iki kapı:** dosya başına tavan tek başına yetmiyor. Şu an büyüyen
  tek dosya `mavros.log`, ama **sürü düğümleri açılınca 14 log daha olacak**
  ve herhangi biri spam yapabilir → `14 × 500 MB × 5 açılış = 35 GB`, disk
  yine dolar.

  **Neden 500/125:** normal işleyişte log KB mertebesinde (37 KB ölçüldü),
  yani tavan yalnız patlama anında devreye giriyor. Patlamada ~25 MB/dk
  yazılıyor; 25 MB korumak ~1 dakikalık geçmiş bırakıyordu. Korunan oranı
  %25'te tutuluyor çünkü I/O yükü `korunan/(tavan−korunan)` ile belirleniyor
  — 125/500 ile 25/100 **aynı** yükü verir (8.3 MB/dk) ama beş kat geçmiş
  bırakır.
- `baslat.sh`: tutulan açılış dizini 10 → **5**

| Uçak | Durum |
|------|-------|
| ylp00 | ✅ temizlendi (19 GB boş, %34) + `baslat.sh` md5 `51d97b3e...` |
| ylp01 | ❌ yerde — **döndüğünde yapılacak** |
| ylp02 | ✅ temizlendi (21 GB boş, %27) + `baslat.sh` md5 `51d97b3e...` |

⚠️ **Konteynerler yeniden başlatılmadı** — bekçi bir sonraki açılışta devreye
girer. Disk artık boş olduğu için acele yoktu.

**`bekci.log` bir sinyaldir:** orada satır varsa o düğüm saniyede yüzlerce
satır basmış demektir. Sık kırpma = aranacak arızanın kendisi.

### 2026-08-02 — uçuş kanıtı dönemi

- FSM pil eşiği `battery_critical_voltage_v:=0.0` (regülatörden besleme)
- Kayıt sertleştirme: `chunkSize 32768`, `--max-cache-size 100000`,
  52 konuluk `--exclude-regex`
- `izleme_kur.sh` 7/7: sysctl writeback 1 sn
- px4_bridge: goto irtifası kalkış zeminine göreli; yatay kilit arm'dan başlıyor

| Uçak | Durum |
|------|-------|
| ylp00 | ✅ |
| ylp01 | ❌ **hiçbiri yok** — 2 Ağustos'ta düştü, öncesinde eski koddaydı |
| ylp02 | ✅ |

> **ylp01 için not:** düştüğünde üzerinde **eski** `esp32_bridge_node.py` ve
> `basit_kacinma_node.py` vardı — "bayat setpoint bir sonraki kalkışı ele
> geçiriyor" düzeltmesi yoktu ve bu, kalkışta devrilmeye yol açan arızaydı.
> Geri geldiğinde **kod senkronu ilk iş**, uçurmadan önce.
