# RPİ EŞİTLEME DEFTERİ — geri gelen drone'u hizaya getirme

**Son güncelleme:** 15 Ağustos 2026, 14:05

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

## 1. Uçağa özgü değerler — HER ADIMDA BUNLARI YERİNE KOY

Aşağıdaki komutlarda `<N>`, `<KULLANICI>`, `<KONTEYNER>` geçen yerlere bu
tablodan bak. **Karıştırılması en kolay şey bu**, çünkü isim ile numara
aynı değil:

| İHA | `<N>` (agent_id) | `<KULLANICI>` | `<KONTEYNER>` | ROS ns | Mesh ID | MAV_SYS_ID | `/ws/tgt_system` |
|-----|------------------|---------------|---------------|--------|---------|------------|------------------|
| ylp00 | **1** | `yelpence00` | `drone1` | `/drone_1` | 1 | 1 | (dosya yok) |
| ylp01 | **2** | `yelpence01` | `drone2` | `/drone_2` | 2 | 2 | `2` |
| ylp02 | **3** | `yelpence02` | `drone3` | `/drone_3` | 3 | 3 | `3` |

**ylp00 → drone1, ylp01 → drone2, ylp02 → drone3.** İsimdeki sayı bir eksik.

ESP32 MAC'leri ve Pi MAC'leri: `docs/cihazlar.md`.

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

---

## 3. A — Pi ana sistem (konteyner dışı)

| # | Ne | ylp00 | ylp01 | ylp02 | Nasıl |
|---|----|-------|-------|-------|-------|
| A1 | Hostname + kullanıcı | ✅ | ✅ | ✅ | `deploy/rpi/pi_hazirla.sh <id>` |
| A2 | Docker + konteyner | ✅ | ❓ | ✅ | `deploy/rpi/run_drone.sh` (`-e AGENT_ID=<N>`, ad `<KONTEYNER>`) |
| A3 | Saat dilimi Europe/Istanbul | ✅ | ❓ | ✅ | `izleme_kur.sh` 1/7 |
| A4 | Wi-Fi güç tasarrufu kapalı | ✅ | ❓ | ✅ | `izleme_kur.sh` 2/7 — **kapatılmazsa Pi boşta SSH'a cevap vermiyor** |
| A5 | Kalıcı journald | ✅ | ❓ | ✅ | `izleme_kur.sh` 3/7 — dosya adı `10-` ile başlarsa İŞE YARAMAZ |
| A6 | `yelpence-izle` servis + timer | ✅ | ❓ | ✅ | `izleme_kur.sh` 4-5/7 |
| A7 | Kayıt disk temizlik timer'ı | ✅ | ❓ | ✅ | `izleme_kur.sh` 6/7 |
| A8 | **sysctl writeback (1 sn)** | ✅ | ❌ | ✅ | `izleme_kur.sh` 7/7 → `/etc/sysctl.d/60-yelpence-writeback.conf` |
| A9 | **Wi-Fi ağları (SSID/şifre)** | ✅ 2 ağ | ❌ | ✅ 2 ağ | aşağıda §7 |
| A10 | **SSH authorized_keys** | ⚠️ tek satır | ❌ | ⚠️ tek satır | aşağıda §7 |

**A8 açıklama:** güç kesintisinde veri kaybının üçüncü katmanı. Bu ayar
olmadan `baslat.sh`'teki kayıt sertleştirmesi anlamsız — veri kullanıcı
alanından çekirdek alanına taşınır, yine RAM'de bekler.

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
| B7 | Teşhis betikleri (21 adet) | ✅ | ❌ | ❓ | repoda yok — `COP_TEMIZLIK.md` §D |

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

**MAV_SYS_ID değiştirme — üçü birden yapılmazsa drone sessizce kopar:**

```bash
ros2 param set /drone_<N>/mavros/param MAV_SYS_ID <N>
# FCU'yu YENIDEN BASLAT — PX4 bu parametreyi ancak boyle uygular
ros2 service call /drone_<N>/mavros/cmd/command mavros_msgs/srv/CommandLong \
  "{command: 246, param1: 1.0}"
echo <N> > ~/yelpence_ws/tgt_system
docker restart <KONTEYNER>
```

Uyuşmazlığın belirtisi aldatıcı: paketler akar ama **içerik boşalır** —
`mod=?`, `sat=0`, arayüzde FAILSAFE. İpucu `mavros.log`'daki
`detected remote address <sysid>.1` satırı.

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

`authorized_keys`'te şu an **tek satır** var. Parola girişi **açık**
(doğrulandı), yani her üye kendi anahtarını **kendisi** kurabilir:

```bash
ssh-keygen -t ed25519                  # kendi bilgisayarında, bir kez
ssh-copy-id <KULLANICI>@<ip>           # parolayla girer, anahtarını ekler
```

---

## 8. DEĞİŞİKLİK DEFTERİ

Her Pi değişikliği buraya, en yeni en üste.

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
  gerek yok. Dosya iki uçağa dağıtıldı (`--symlink-install` sayesinde
  `/ws/src`'e kopyalamak yeterli, derleme gerekmiyor).
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
