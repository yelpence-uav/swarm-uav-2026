# DURUM — şu an ne çalışıyor, ne bozuk

**Son güncelleme:** 17 Ağustos 2026, 10:21

> Bu belge **şimdiki hâli** anlatır, tarihçe değil. Bir şey değişince burayı
> güncelle, eskisini sil. Ne olduğunun hikâyesi `GUNLUK.md`'de kalır.

---

## 1. Filo

| İHA | agent_id | Durum | Not |
|-----|----------|-------|-----|
| ylp00 | 1 | **Uçar** | Repo ile %100 senkron (doğrulandı 14 Ağu) |
| ylp01 | 2 | **YERDE** | 2 Ağustos'ta 20 m'den düştü, RPi açılmıyor |
| ylp02 | 3 | **Uçar** | Repo ile %100 senkron (doğrulandı 14 Ağu) |

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

**14 Ağustos itibarıyla ağ `10.188.209.x`** (telefon hotspot'u).

| Cihaz | IP (14 Ağu) | Kullanıcı |
|-------|-------------|-----------|
| ylp00 | `10.188.209.134` | `yelpence00` |
| ylp02 | `10.188.209.189` | `yelpence02` |
| YKİ laptop | `10.188.209.115` | — |

### IP ezberleme — betik var

```bash
./deploy/yki/drone_bul.sh            # menü, seç, bağlan
./deploy/yki/drone_bul.sh ylp00 'komut'
./deploy/yki/drone_bul.sh --durum    # disk, konteyner, bayraklar
```

Önbellek → mDNS (`ylp00.local`) → MAC taraması sırasıyla dener. Dördü de
14 Ağustos'ta test edildi ve çalışıyor. **mDNS bu hotspot'ta çalışıyor.**

**Kayıtlı Wi-Fi ağları** (ikisinde de): `rpissid` (öncelik 10, tercih edilen)
ve `iPhone` (öncelik 0, yedek). İkisinde de güç tasarrufu kapalı.
⚠️ `iPhone` SSID'si henüz **doğrulanmadı** — eklerken telefon kapalıydı.

**Parola girişi AÇIK** (sshd varsayılanı, override yok) → arkadaşlar kendi
anahtarlarını kendileri kurabilir. ylp00'ın `authorized_keys`'inde **iki
satır** var (Osman'ınki 17 Ağustos'ta eklendi); ylp02'de hâlâ tek satır.

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
| `SURU_DUGUMLERI` | boş | boş | 14 sürü düğümünün hiçbiri açık değil |
| `BATARYA_KRITIK_V` | `0.0` | `0.0` | FSM bataryaya bakmıyor (regülatörden besleme) |
| `~/yelpence_ws/ucus_ayarlari.env` | **var** | **var** | seyir 3.0 m/s, ivme 1.5 — `ucus_ayarlari.py --kabuk` üretti |
| `~/yelpence_ws/suru_dugumleri` | **`origin consensus fsm formasyon`** | `origin consensus` (16 Ağu bilgisi) | Varsa `SURU_DUGUMLERI` env'ini ezer. Düğüm açmak: `echo ... > dosya` + `docker restart` |
| `~/yelpence_ws/origin` | **var** | **var** | `38.6904758 39.1610188 1216.96` — tek kaynak `deploy/saha_origin.env`, ylp00'da doğrulandı (17 Ağu). Elle yazma, `dagit.sh` dağıtır |
| `~/yelpence_ws/yer_testi` | **VAR** ⚠️ | **VAR** ⚠️ | Uçak ARM olur ama **KALKMAZ**. Uçuştan önce SİL + restart |
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

### 🔴 Uçaklardaki ROS kodu bu depodan üretilemiyor (17 Ağustos, ölçüldü)

İki Pi'nin de `~/yelpence_ws/.surum` dosyası:

```
commit=0dfa0ad +KIRLI   dal=feature/dagitik-suru
dagitan=egUbuntu        15 Ağustos 20:34
```

`git cat-file -t 0dfa0ad` → **yok.** `git ls-remote --heads origin` →
**yalnız `main`.** Dal ve commit erişilemez, üstelik `+KIRLI` olduğu için
commit elimizde olsa bile birebir üretilemezdi. **Şu an uçan yazılımı
okuyabildiğimiz tek yer Pi'lerin kendisi.**

> ⛔ **`dagit.sh` ÇALIŞTIRMA.** `src/`'yi `main` ile ezer, uçan kodu
> değiştirir. Dal Eyüp'ten alınıp `origin`'e itilene kadar geçerli.
> Tek dosyalık acil değişiklik: `rsync` + md5 doğrulaması.
> Takip: `YAPILACAKLAR.md` **P0.7**.

### `baslat.sh` — repo ile birebir

md5 `0dacdf44...` : repo = ylp00 = ylp02 (17 Ağustos 10:21'de doğrulandı,
`--bekle 150` değişikliğinden sonra).

`/ws/src`'te 6 paket var; `network_proxy` ve `sim_rtcm_source` **bilerek yok**
(ikisi de simülasyon bileşeni, bkz. `deploy/rpi/dagit.sh`).

⚠️ Senkron kontrolü için `.surum`'a **güvenme**, md5 karşılaştır.

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

### ✅ ADIM 1 geçti — consensus çalışıyor (15 Ağustos)

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
- **RTK-FIX** iki uçakta 32 uydu; baz `1005` dahil tam RTCM seti yayınlıyor
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
doğrulandı.

> ⏳ **Henüz etkin değil.** `baslat.sh` yalnız konteyner açılışında okunuyor.
> Şu anda ayakta olan konteynerler hâlâ eski değerle koştu, yani **iki uçağın
> saati şu an hâlâ yanlış.** Etkin olması ve saatlerin GPS'e oturması için:
> `docker restart drone1` / `drone3` (QGC yeniden bağlanmalı — §2 kuralı).

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

Kurulum `deploy/yki/kur_yki.sh`, **Ubuntu 24.04 (noble) ister** ve başka
dağıtımda bilerek durur. Ubuntu olmayan bir laptopta çalışıyorsan yol,
`ros:jazzy` konteynerinin içinde aynı betiği koşturmak — ikinci bir kurulum
betiği yazma. (17 Ağustos'ta Arch'ta yapıldı ve çalıştı; o makinenin
konteyner dosyaları kişisel olduğu için depoya girmiyor.)

Telemetri: `curl -s http://localhost:8000/api/telemetry/snapshot`
