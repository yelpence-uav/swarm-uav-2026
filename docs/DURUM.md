# DURUM — şu an ne çalışıyor, ne bozuk

**Son güncelleme:** 19 Ağustos 2026, 20:10

> Bu belge **şimdiki hâli** anlatır, tarihçe değil. Bir şey değişince burayı
> güncelle, eskisini sil. Ne olduğunun hikâyesi `GUNLUK.md`'de kalır.

---

## 1. Filo

| İHA | agent_id | Durum | Not |
|-----|----------|-------|-----|
| ylp00 | 1 | **Uçar** | Repo ile %100 senkron (`600ca65`, 17 Ağu). **RC-kayıp tespiti kuruldu ve HAVADA doğrulandı (19 Ağu):** kumanda kapanınca 1-2 sn'de RTL — Ch3 üst-uç yöntemi, bkz. `RPI_ESITLEME.md` §5. ⚠️ 19 Ağu'da kill-failsafe kazasıyla alçaktan düştü (sonra uçtu) — pervane/GPS/titreşim kontrolü bekliyor. ⚠️ RC kalibrasyonu 19 Ağu'da yenilendi (`RC3_MIN` 1016→906). ⚠️ `core.50` 353 MB silinmeli |
| ylp01 | 2 | **YERDE** | 2 Ağustos'ta 20 m'den düştü, RPi açılmıyor |
| ylp02 | 3 | **Uçar** | Repo ile %100 senkron (doğrulandı 14 Ağu). ⚠️ Alıcı failsafe'i 18 Ağu'da iki kez ele alındı: düzeltildi → kumanda sıfırlaması geri aldı → operatör tekrar düzelttiğini bildirdi ama **doğrulama ölçümü YAPILMADI**. `YAPILACAKLAR` P0.9. RC-kayıp tespiti **YOK** (19 Ağu'da yalnız ylp00'a kuruldu — P1.9) |

**Uçuş yapılandırması:** drone **1 ve 3**, lider **3**.
YKİ koşucu paneli varsayılanı buna ayarlı (`backend/api/kosucu.py`).

### ylp01 (drone 2) — düşme durumu

Kaza analizi bitti, **sebep elektriksel**. Log kanıtı: serbest düşüş boyunca
pil 15.4→16.0 V (yükseliyor), RTK-FIX 31 uydu, EKF sağlam, `armed=1`,
`failsafe=0`, `kill=0`. Uçuş kontrolcüsü düşerken bile yayın yapıyordu.
**Yalnız motorlar durdu** → ESC güç/sinyal hattı. Yazılım kusuru değil,
hiçbir yazılım kontrolü bunu yakalayamazdı.

**Kalan fiziksel iş** (yapılmadı):
- Güç modülü çıkışı → PDB → ESC güç lehimleri
- ESC sinyal kablo demeti
- RPi neden açılmıyor (SD kart okunuyor, kart sağlam)

Motorların sağlam olduğu operatör tarafından doğrulandı.

---

## ✅ Disk sorunu çözüldü (14 Ağustos)

Sabah iki drone'un da diski **%100 doluydu** (0 bayt boş). Sebep tek dosya:
`gunluk/mavros.log` — ylp00'da 18.64 GB, ylp02'de 21.57 GB.

Kök neden `gcs_url` uçnoktası: WiFi düştüğünde MAVROS **her MAVLink mesajı
için** `Network is unreachable` uyarısı basıyor, 20 Hz'de saniyede yüzlerce satır.

**Yapıldı:** loglar temizlendi, `baslat.sh`'e **iki kapılı** günlük bekçisi
eklendi — dosya başına 500 MB tavan (son 125 MB korunur) **ve** dizin geneli
3 GB tavan (aşılırsa en eski açılışlar silinir, en yeni iki tanesi kalır).
Açılış dizini 10 → 5, 21 yönlendirme `>>`'ye çevrildi.

Dizin tavanı sürü entegrasyonu için: 14 düğüm açılınca 14 log olacak ve
dosya başına tavan tek başına `14 × 500 MB × 5 = 35 GB`'a izin verirdi.

```
ylp00: 19 GB boş (%34)      ylp02: 21 GB boş (%27)
```

✅ **Konteynerler yeniden başlatıldı, bekçi canlıda:**
`[baslat] gunluk bekcisi: dosya 500 MB (son 125 MB korunur), dizin 3000 MB`. Ayrıntı ve kök neden:
`RPI_ESITLEME.md` §8.

---

## 2. Ağ ve erişim

**IP'ler her ağda değişiyor — bu tabloyu ezberleme, `drone_bul.sh` kullan.**
Son ölçülen (17 Ağustos, telefon hotspot'u `172.19.167.x`):

| Cihaz | IP (17 Ağu) | Kullanıcı |
|-------|-------------|-----------|
| ylp00 | `172.19.167.134` | `yelpence00` |
| ylp02 | `172.19.167.189` | `yelpence02` |
| YKİ laptop | `172.19.167.178` | — |
| ağ geçidi (telefon) | `172.19.167.123` | — |

Son eki değişse de **MAC'ler sabit** ve betik onlardan buluyor:
ylp00 `88:a2:9e:71:60:ed` · ylp02 `88:a2:9e:71:60:24`.

### IP ezberleme — betik var

```bash
./deploy/yki/drone_bul.sh            # menü, seç, bağlan
./deploy/yki/drone_bul.sh ylp00 'komut'
./deploy/yki/drone_bul.sh --durum    # disk, konteyner, bayraklar
```

Önbellek → mDNS (`ylp00.local`) → MAC taraması sırasıyla dener.

⚠️ **mDNS makineye bağlı.** Eyüp'ün Ubuntu'sunda çalışıyordu; Osman'ın
Arch'ında **çalışmıyor** (`nss-mdns` kurulu değil, avahi kapalı). MAC
taraması yedeği her iki makinede de sorunsuz — engel değil, sadece birkaç
saniye yavaş. İstenirse: `sudo pacman -S nss-mdns avahi` +
`nsswitch.conf`'a `mdns_minimal`.

**Kayıtlı Wi-Fi ağları** (ikisinde de): `rpissid` (öncelik 10, tercih edilen)
ve `iPhone` (öncelik 0, yedek). İkisinde de güç tasarrufu kapalı.
⚠️ `iPhone` SSID'si henüz **doğrulanmadı** — eklerken telefon kapalıydı.

**Parola girişi AÇIK** (sshd varsayılanı, override yok) → arkadaşlar kendi
anahtarlarını kendileri kurabilir. **Osman'ın anahtarı 17 Ağustos'ta, Berk'in (MacBook)
anahtarı 18 Ağustos'ta ikisine de kuruldu.**

⚠️ ylp02 **mDNS'e cevap vermiyor** ve host key'i IP tabanlı kaydedildi. IP
değişip aynı adresi başka cihaz alırsa SSH *"REMOTE HOST IDENTIFICATION HAS
CHANGED"* diye bağırır — panik yapma, `ssh-keygen -R <ip>` ile temizlenir.

### 🔴 QGC'de `AutoConnect → RTK GPS` KAPALI olmalı

**18 Ağustos'ta ölçüldü.** QGC'nin RTK oto-bağlanması u-blox baz istasyonunun
seri portunu **kapıyor**; `yki_rtcm_reader` portu açamıyor (`Resource busy`)
ve **RTCM hiç akmıyor**. Belirti sessiz: telemetri normal, arayüz sağlıklı,
tek işaret uçakların `fix_type`'ının 6 yerine 3-5'te takılması.

Port sahibi `lsof` ile bulundu (`QGroundControl PID 6245`). Kapatılınca RTCM
9-10 msg/s'e döndü ve iki uçak da **RTK-FIXED (fix=6)** oldu.

QGC → Application Settings → General → *AutoConnect* → **RTK GPS kapalı**,
**UDP kapalı**. MAVLink bağlantısı elle eklenen 14550 UDP link'inden.
Ayrıntı: `TUZAKLAR.md` §6.6.

### 🔴 Dronlara güç vermeden ÖNCE QGC'yi aç

**17 Ağustos'ta ölçüldü.** `gcs_url` = `udp-b://…` **yayın** demek ve QGC
açık değilken MAVROS durmadan `255.255.255.255:14550`'ye yayın yapıyor.
Telefon hotspot'u bu akış altında **tüm istemcilere** teslimatı saniyede
~1.25 pakete düşürüyor: ağ geçidine ping 14 saniyeye çıkıyor, laptopta
internet ölüyor. Trafik küçük (14 paket/s) — sorun hacim değil, **yayın
olması**. Radyo tarafı tamamen sağlıklıydı: hava %0-3, yeniden gönderim ~0,
hız sabit 72.2 Mbit.

QGC bağlanınca MAVROS **tekil** gönderime geçiyor ve sorun anında bitiyor.
Keşfettiği karşı tarafı unutmadığı için QGC'yi **sonradan kapatmak sorun
değil** (ölçüldü). Ama her `docker restart droneN` MAVROS'u yeniden başlatıp
pencereyi tekrar açıyor.

Kalıcı çözüm tek satır — `gcs_url` = `udp://:14555@` (uçak yayın yapmaz,
sadece dinler; bağlantıyı QGC kurar, uçakta IP yazılı olmaz). Denendi ve
doğrulandı, **uygulanmadı**: operatör kararıyla uçak `udp-b`'de bırakıldı.
Ayrıntı: `GUNLUK.md` 17 Ağustos kaydı.

---

## 3. Uçakta açık olan bayraklar

Bunlar **dosya varlığıyla** çalışıyor; uçağı bulan kişi böyle bulacak.

| Bayrak | ylp00 | ylp02 | Anlamı |
|--------|-------|-------|--------|
| `~/yelpence_ws/kacinma` | **var** | **var** | `basit_kacinma` açık, esp32_bridge çıkışı `/raw`'a yönlendirilmiş |
| `~/yelpence_ws/gcs_url` | var | var | MAVLink QGC'ye iletiliyor (`udp-b://:14555@14550`) |
| `~/yelpence_ws/tgt_system` | yok | `3` | ylp02'nin FCU sysid'i 3 |
| `BATARYA_KRITIK_V` | `0.0` | `0.0` | FSM bataryaya bakmıyor (regülatörden besleme) |
| `~/yelpence_ws/ucus_ayarlari.env` | **var** | **var** | seyir 3.0 m/s, ivme 1.5 — `ucus_ayarlari.py --kabuk` üretti |
| `~/yelpence_ws/suru_dugumleri` | **`origin consensus fsm formasyon`** | **`origin consensus fsm formasyon`** | 17 Ağu'da ikisinde de ölçüldü, **aynı**. Varsa `SURU_DUGUMLERI` env'ini ezer. Düğüm açmak: `echo ... > dosya` + `docker restart` |
| `~/yelpence_ws/origin` | **var** | **var** | `38.6904758 39.1610188 1216.96` — tek kaynak `deploy/saha_origin.env`, ylp00'da doğrulandı (17 Ağu). Elle yazma, `dagit.sh` dağıtır |
| `~/yelpence_ws/yer_testi` | **YOK** 🔴 | **YOK** 🔴 | 18 Ağu'da G2 uçuşu için **SİLİNDİ** + restart. Uçak artık kalkış komutunu ALIR. Yer testi yapacaksan `touch` ile geri koy |
| `~/yelpence_ws/gozlem` | **VAR** ⚠️ | **VAR** ⚠️ | `formation_node` setpoint'i `/gozlem/...`'e gidiyor, **uçağa ULAŞMIYOR**. Uçuştan önce SİL + restart |
| `~/yelpence_ws/gps_saat_kapali` | yok | yok | Varsa GPS'ten saat düzeltmesi yapılmaz |

### 🔴 UÇMADAN ÖNCE: `yer_testi` bayrağını kaldır

```bash
./deploy/yki/drone_bul.sh ylp00 'rm -f ~/yelpence_ws/yer_testi ~/yelpence_ws/gozlem && docker restart drone1'
./deploy/yki/drone_bul.sh ylp02 'rm -f ~/yelpence_ws/yer_testi ~/yelpence_ws/gozlem && docker restart drone3'
```

Açık kaldığı sürece "görev başladı" komutu uçağı ARM eder ve **orada
bırakır** — kalkış komutu gönderilmez. Yer testleri için var.

### Yer testinden çıkış: **kumandadan kill switch**

Yazılım disarm'ı OFFBOARD'dayken PX4 tarafından reddediliyor (`result=1`).
Sebep ölçüldü: pervanesiz OFFBOARD'da konum denetleyicisi irtifayı tutmaya
çalışıp integrali sarıyor, gaz tırmanıyor ve PX4 kendini "yerde" saymıyor.
**Armlı bekleme süresini kısa tut.**

⚠️ `ucus_ayarlari.env` **dosya öncelikli** — `docker run -e` ile verilen
değeri **ezer**. (`baslat.sh`'te bunun tersi yazıyordu, 15 Ağustos'ta ölçülüp
düzeltildi.) Tek uçakta hızlı deneme için `-e` değil, canlı parametre yolunu
kullan — bkz. `CLAUDE.md` §8.

### Pil izleme KAPALI — üç yerde birden

Uçaklar regülatörden besleniyor, PX4'te `BAT1_SOURCE` disabled. Pil geri
takılınca **üçünü birden** aç, biri unutulursa tutarsız davranır:

1. `deploy/rpi/baslat.sh` → `BATARYA_KRITIK_V=13.6`
2. `src/gcs/frontend/src/services/gorunum.ts` → `PIL_GOSTER = true`
3. `src/gcs/backend/config.yaml` → `alerts.susturulan`'dan batarya kodlarını çıkar

---

## 🔴 DEPO DEĞİŞTİ (16 Ağustos)

Sim'siz saha sürümü ayrı bir repoya taşındı:

| Repo | İçerik | Rol |
|------|--------|-----|
| **`yelpence-2026-saha`** | Sim'siz, 344 dosya | **Çalışılacak repo** |
| `yelpence-2026-swarm` | Her şey, sim dahil | Arşiv — dokunulmadı |

Yeni repoda olmayanlar: `sim/`, `docker/`, `network_proxy`,
`sim_rtcm_source`, `scripts/`, `ARCHITECTURE.md`, `COP_TEMIZLIK.md`.
Hepsi eski repoda ve git geçmişinde duruyor.

⚠️ **`dagit.sh` ile kod dağıtmadan önce hangi repoda olduğunu doğrula.**

### Belge düzeni sadeleşti (16 Ağustos akşamı)

Temmuz–Ağustos saha günlükleri (`docs/arsiv/`, 5 dosya) **silindi**; hâlâ
geçerli olan her şey yeni **`docs/TUZAKLAR.md`**'ye çıkarıldı ve koda
bakılarak doğrulandı. `docs/`: 17 md → **12 md**.

🔴 `TUZAKLAR.md` **§0'da durumu bilinmeyen üç güvenlik maddesi** var
(ylp00 clipping ölçüm kuralı, alıcı failsafe'inin kill tetiklemesi,
hover gazı %66). Uçuş öncesi cevaplanmalı — `YAPILACAKLAR.md` P1.6.

---


## 4. Kod senkronu

### ✅ Uçaklar `main`'de — 17 Ağustos'ta dağıtıldı ve doğrulandı

```
ylp00 / ylp02   .surum:  commit=600ca65   dal=main   (+KIRLI YOK)
                src/  :  176 dosya, repo main ile BIREBIR (md5)
                install/: 6 paketin hepsi
```

İki dağıtım yapıldı: `e012dba` (11:35, kod devri) ve `600ca65` (14:30,
P0.8 `sitl_mode` düzeltmesi). İkisinde de konteynerler yeniden başlatıldı.

Bundan önce iki Pi de `commit=0dfa0ad +KIRLI dal=feature/dagitik-suru`
diyordu; o commit ve dal bu depoda **yoktu** (eski depodan, Eyüp'ün
makinesinden). Yani uçan yazılımı okuyabildiğimiz tek yer Pi'lerin SD
kartlarıydı. `dagit.sh` `--delete` ile çalıştığı için dağıtım o kodu geri
dönüşsüz silecekti.

> 🗄️ **Silinmeden önce git'e alındı:** `saha/pi-kod-15agustos` dalı
> (`52ff027`, `origin`'de). 17 Ağustos sabahı uçaklarda **gerçekten koşan**
> `src/` ağacının birebir kopyası — ylp00'dan alındı, ylp02 ile md5'i aynı.
> Çalıştırılabilir sürüm değil, **karşılaştırma referansı**: "saha böyle
> davranıyordu" sorusunun cevabı burada.

`baslat.sh` md5 `0dacdf44...` : repo = ylp00 = ylp02.

`/ws/src`'te 6 paket var; `network_proxy` ve `sim_rtcm_source` **bilerek yok**
(ikisi de simülasyon bileşeni, bkz. `deploy/rpi/dagit.sh`).

⚠️ Senkron kontrolü için `.surum`'a tek başına **güvenme**, md5 karşılaştır —
`dagit.sh` derleme başarısız olsa bile `.surum` yazıyor (bkz. `TUZAKLAR.md` §1.14).

---

## 5. Sahada koşan düğümler

```
mavros_node · px4_bridge · agent_fsm_node · esp32_bridge · basit_kacinma
+ ic_dis_kopru · swarm_origin_publisher · consensus_node
+ swarm_fsm_node · formation_node · path_planner           (15 Ağustos)
```

`collision_avoidance` **kapalı** — `basit_kacinma` ile aynı topic yuvası,
ikisi birden açılmaz (`CLAUDE.md` §4). ADIM 4'te değişecek.

**İlk sürü düğümleri sahada koşuyor.** `ic_dis_kopru` herhangi bir sürü
düğümü açıksa kendiliğinden açılıyor — sözleşmenin `internal → public`
yerel döngüsünü o kuruyor (bkz. `YAPILACAKLAR` P0.6).

### 🔴 ADIM 1'in HAVADAKİ karşılığı çalışmıyor — G2'de ölçüldü (18 Ağustos)

15 Ağustos'taki test uçakları **elle ARM ederek** yapılmıştı. G2 gözlem
uçuşunda ölçüldü ki **guided uçuşta ajan durumu IDLE'da kalıyor**;
`ELIGIBLE_STATES` IDLE'ı içermediği için consensus hiç seçim yapmıyor.
638 saniyelik kayıtta iki uçakta da `election/result` = 0,
`leader/heartbeat` = 0. Sebep: YKİ'nin guided yolu `agent_fsm`'i atlıyor.
Ayrıntı ve çözüm: `YAPILACAKLAR.md` **P0.11**. ADIM 3'ün ön koşulu.

### ✅ ADIM 1 YERDE geçti — consensus çalışıyor (15 Ağustos)

Pervanesiz, yerde, ARM'lı yapılan testte iki uçak da **aynı lideri** seçti:

```
ylp00: [CONSENSUS] Lider: 0 -> 1 (round=1, ben=1)
ylp02: [CONSENSUS] Lider: 0 -> 1 (round=1, ben=3)      101 ms arayla
ylp00: esp32_bridge  lider 0 -> 1 (BEN)   ← formasyon kapisi ACIK
```

Ayrıca **lider arıza devri** gözlendi: kill switch ylp00'ı FAILSAFE'e
düşürdükten 82 ms sonra `Lider: 1 -> 3 (round=2)`.

Ayrıntı ve sınırlar: `SURU_ENTEGRASYON.md` ADIM 1.

---

## 6. Kanıtlanmış / doğrulanmış olanlar

Bunlar sahada ölçüldü, tekrar sorgulanmasın:

- **Uçuş kanıtı videosu geçildi.**
- **Görev koşucusu** `--senaryo saha`: 5 nokta, 8→15 m, çizgi↔okbaşı formasyon
  değişimi, rotasyonlar, 135° güneydoğuya dönüp iniş. ~187 s görev / ~222 s video.
- **Kuru test** kritik ayrım **8.41 m** (eşik 4.0 m) — `SONUÇ: GEÇTİ`
  (aralık 12 m'ye çıkınca 7.07'den yükseldi)
- **RTK-FIX** iki uçakta 32 uydu; baz `1005` dahil tam RTCM seti yayınlıyor.
  **18 Ağustos'ta baz MSM4'e alındı** — akış artık `1005, 1074, 1084, 1094,
  1124, 1230` @ ~1 Hz, `crc_err=0` (öncesinde MSM7 vardı ve okuyucu uyarıyordu;
  `YELPENCE_RTCM_SPEC.md` §401 MSM4 bekliyor). İki uçak da `fix=6` (RTK-FIXED).
- **Bazın kendi konumu** RTCM 1005'ten okundu (18 Ağu):
  `38.6905395 39.1610681 1217.58` — origin'den **8.29 m yatay, +0.62 m dikey**.
  Fiziksel ayrım olarak makul. ⚠️ Ama RTK, **bazın mutlak konum hatasını
  bütün uçaklara aynen aktarır**: harita üzerinde hepsi aynı yöne kayar.
  Anten son survey'den beri taşındıysa `src/gcs/rtk_baz_survey.py` çalıştırılmalı
  (betiğin başlığı: *"anteni her taşıdığında bunu koştur"*). **Bugün taşınıp
  taşınmadığı bilinmiyor — operatöre soruldu, cevap bekleniyor.**
- **Kalkış irtifa çerçevesi** düzeltildi: goto artık kalkış zeminine göreli
- **Yatay kilit** arm'dan başlıyor (2.5 m'ye kadar yatay konum tutma yok)
- **Uçuş kaydı sertleştirildi**: en kötü kayıp ~14.7 sn → ~2-3 sn
- **Ölçülen hızlar**: yatay 1.83 m/s, dikey 0.85 m/s (komut 2.0/1.0 iken).
  Seyir 14 Ağu'da **3.0**'a çıkarıldı, bu hızda henüz ölçüm YOK —
  bkz. `NAVIGASYON_KAYMA.md` Adım 1

---

## 7. Bilinen açık sorunlar

| # | Sorun | Etki | Nerede |
|---|-------|------|--------|
| 1 | `iPhone` SSID'si doğrulanmadı | Telefon açılınca teyit gerekir | `RPI_ESITLEME.md` §7 |
| 2 | ~~Repo commit'siz ve push'suz~~ | ✅ 15 Ağu commit'lendi | — |
| 3 | ylp01 yerde | Üç değil iki uçakla çalışıyoruz | bu belge §1 |
| 4 | Sürü düğümleri hiç uçmadı | Final görevi bunlara bağlı | `SURU_ENTEGRASYON.md` |
| 5 | Drone'larda repoda olmayan 21 betik | Bilgi versiyonsuz, kaybolabilir | `YAPILACAKLAR.md` P2.5 |
| 6 | ~~PX4 parametreleri ayrışmış~~ | ✅ 14 Ağu eşitlendi | `RPI_ESITLEME.md` §8 |
| 7 | ESC telemetrisi kapalı | Kaza sebebini doğrudan verirdi | `YAPILACAKLAR.md` P2.4 |
| 8 | `ARCHITECTURE.md` sim dönemine ait | Kodla çelişiyor, yanıltır | `YAPILACAKLAR.md` P2.5 |
| 9 | Wi-Fi düşünce MAVROS log patlıyor | Bekçi kırpıyor ama kök neden duruyor | `RPI_ESITLEME.md` §8 |
| 10 | Pi saati açılışta ~11 saat geriden | Çapraz uçak log karşılaştırması bozulur | `cihazlar.md` ⏰ |

### 🟠 #10 — Pi saati: kök neden bulundu, düzeltme dağıtıldı, **henüz etkin değil**

Pi 5'in RTC'sinde yedek pil yok; açılışta saat bayat geliyor. `gps_saat.py`
açılışta PX4'ün GPS zamanından düzeltiyor — internet gerekmiyor.

**17 Ağustos'ta ölçüldü:** iki uçakta da düzeltme **çalışmamıştı**. Her
ikisinin son açılış logunda aynı satır:
`[gps_saat] GPS zamani 25 sn icinde gelmedi. Saat DEGISMEDI.`
GPS'e güç verildikten sonra topu topu ~54 sn tanınıyor (Pi açılışı → konteyner
13 sn → mavros + `sleep 15` → bekleme 25 sn) ve Here4 soğukta o sürede
kilitlenmiyor. Sonuç: **ylp00 7 sa 58 dk, ylp02 10 sa 15 dk geride, aralarında
2 sa 17 dk fark.**

**Uçuşu bozmuyor** — `consensus_node` bütün tazelik hesabını
`time.monotonic()` ile ve komşunun yerel alım anına göre yapıyor
(`consensus_context.py:29`). Bozduğu şey çapraz uçak kayıt karşılaştırması.

**Yapıldı:** `baslat.sh` → `--bekle 150`, iki uçağa da dağıtıldı, md5
doğrulandı, konteynerler 11:35–11:41'de yeniden başlatıldı.

**Şu anki hâl (11:41):** her iki uçağın saati dizüstüyle **saniyesi saniyesine
aynı**, `NTPSynchronized=yes`. Yeni açılış logları:
`fark=+0.487 sn` (ylp00) / `+0.438 sn` (ylp02) → eşiğin altında, `gps_saat`
saate haklı olarak dokunmadı.

⚠️ Bu sefer saati NTP düzeltti, GPS değil — o sırada Pi'lerin interneti
gelmişti. **`--bekle 150` hâlâ sınanmadı:** asıl sınav internetsiz bir soğuk
açılış. Takip: `YAPILACAKLAR.md` P1.4.

### ✅ #6 — Parametre ayrışması giderildi (14 Ağustos)

`param_karsilastir.py` üç ayrışma buldu, üçü de eşitlendi:

| Parametre | önce (ylp00/ylp02) | şimdi |
|-----------|--------------------|-------|
| `MPC_TILTMAX_AIR` | 45 / 30 | **30** |
| `MPC_YAWRAUTO_MAX` | 45 / 25 | **25** |
| `MPC_VEL_MANUAL` | 4 / 2 | **3.0** |
| `MPC_XY_VEL_MAX` | 4.0 / 4.0 | **5.0** (ikisi de) |

Doğrulama: *"Uçaklar arası ayrışma yok (16 parametre)"* — yalnız
`MAV_SYS_ID` farklı, doğru.

**Uçuş ayarları artık tek kaynakta:** `src/gcs/ucus_ayarlari.py`.
`baslat.sh` `/ws/ucus_ayarlari.env`'i okuyor, seyir hızı **3.0 m/s** canlıda.

**Her uçuştan önce çalıştır:** `./deploy/yki/param_karsilastir.py`

## 8. Yerel servisler (YKİ laptop)

| Servis | Adres | Log |
|--------|-------|-----|
| Arayüz | http://localhost:5173/ | `/tmp/yki_frontend.log` |
| Backend | http://localhost:8000/ | `/tmp/yki_backend.log` |
| Base köprü | — | `/tmp/yki_base_bridge.log` |

Başlat/durdur: `src/gcs/yki_baslat.sh` · `src/gcs/yki_durdur.sh`
**Elle başlatma** — ROS ortamı kaybolur, backend telemetri alamaz.

### YKİ üç makinede koşuyor — kurulum yolu makineye göre değişiyor

| Makine | ROS nereden | Başlatma |
|--------|-------------|----------|
| Ubuntu 24.04 | apt (`/opt/ros/jazzy`) | `src/gcs/yki_baslat.sh` |
| Arch | `ros:jazzy` konteyneri | `yki` alias (bkz. `arch-docker/`) |
| **macOS (Apple Silicon)** | **pixi/RoboStack** | **`~/yelpence-yki-mac/yki_mac.sh`** |

**macOS 18 Ağustos'ta eklendi.** Sanal makine/konteyner **kullanılmadı**:
makine 8 GB M1, VM 3-4 GB RAM alıp QGC + tarayıcı + Vite + backend'e yer
bırakmıyordu. Seri port native çalışıyor — CH340 @460800'de 6 saniyede
79 POSE + 12 DURUM çerçevesi, **0 bozuk**. Kurulum, ölçümler ve geri alma
adımları makinedeki `~/yelpence-yki-mac/README.md`'de (kişisel, depoya girmiyor).

`yki_baslat.sh` bunun için **env ile parametrelendi** (`ROS_SETUP`, `DDS_URI`,
`BASE_ESP_PORT`, `RTK_GPS_PORT`) — ikinci bir başlatma betiği yazılmadı,
Ubuntu davranışı birebir aynı kaldı. Platform tuzakları: `TUZAKLAR.md` §9.

Kurulum `deploy/yki/kur_yki.sh`, **Ubuntu 24.04 (noble) ister** ve başka
dağıtımda bilerek durur. Ubuntu olmayan bir laptopta çalışıyorsan yol,
`ros:jazzy` konteynerinin içinde aynı betiği koşturmak — ikinci bir kurulum
betiği yazma. (17 Ağustos'ta Arch'ta yapıldı ve çalıştı; o makinenin
konteyner dosyaları kişisel olduğu için depoya girmiyor.)

Telemetri: `curl -s http://localhost:8000/api/telemetry/snapshot`

### 🛰 u-blox reset butonu (18 Ağustos)

Arayüzde `⚙ Ayarlar` → **RTK baz istasyonu** bölümünde, iki adımlı onaylı.
Komut seri porta doğrudan gitmiyor — port tek sahipli ve sahibi
`yki_rtcm_reader.py`; komut ROS'tan (`/swarm/internal/rtk/komut`) ona gidiyor,
UBX-CFG-RST'i o yazıyor.

⚠️ **Reset RTCM'i keser**, uçaklar RTK-FIX düşürüp yeniden yakalar. Baz
survey-in modundaysa toparlanma **dakikalar** sürebilir. Havadayken kullanma.

```bash
curl -X POST 'http://localhost:8000/api/rtk/reset?kip=sicak'   # ilik | soguk
```
