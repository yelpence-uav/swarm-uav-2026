# DURUM — şu an ne çalışıyor, ne bozuk

**Son güncelleme:** 30 Ağustos 2026, 00:05 — §2 düzeltildi: `TIP_OLAY` 27 Ağustos'ta eklendi, olaylar YKİ'ye ULAŞIYOR (belge 3 gündür yanlıştı)


## 1. Filo

**Üçü de uçuyor.** 28 Ağustos akşamı üç uçak birlikte, tek uçuşta formasyon
geçiş sekansını tamamladı.

| İHA | agent_id | Konteyner | Kadro rütbesi (CA) | Durum |
|-----|----------|-----------|--------------------|-------|
| ylp00 | 1 | `drone1` | **0 = ÇAPA** — dikeyde kaçmaz | Uçar. CA testlerinde yaklaştıran uçak bu olmalı |
| ylp01 | 2 | `drone2` | 1 = YUKARI kaçar | Uçar. 25 Ağu'da onarım zinciri kapandı (yeni Pi + ESP + Pixhawk). ⏳ Pil sensör kartı yok — tok pil + süre sınırıyla uçuluyor |
| ylp02 | 3 | `drone3` | 2 = birincil AŞAĞI | Uçar. **Kamera bu uçakta** (IMX477). 4,8 m altında taban aynası YUKARI'ya çevirir |

> ⚠️ **İsim ile numara aynı değil:** ylp00 → drone**1**, ylp02 → drone**3**.

> 🔴 **ylp02 PX4 güç soketi — kabul testi HENÜZ kayda geçmedi.** Operatör
> 28 Ağustos akşamı "halledildi" dedi. Uçuş sabahı: **kabloyu bilerek 3 kez
> oynat, üçünde de reboot gelmemeli.** Gevşek temas yerde kusursuz, titreşimde
> bozuk — ve güç kesilirse uçuş kontrolcüsü ölür.
>
> ⚠️ 2 Ağustos'ta ylp01'in düşüşü **hâlâ tam aydınlanmadı** (sebep elektrikseldi:
> ESC güç/sinyal hattı; log'da yalnız motorlar durmuştu). Aynı sınıf arıza.

---

## 2. Ağ ve erişim

**IP'ler her ağda değişiyor — ezberleme, `drone_bul.sh` kullan.**
Son ölçülen: **20 Ağustos, `10.205.4.x`** — ylp00 `.134`, ylp02 `.189`.
(17 Ağustos'ta telefon hotspot'u `172.19.167.x` idi.)

**MAC'ler sabit** ve betik onlardan buluyor — 20 Ağustos'ta doğrulandı,
`cihazlar.md` kimlik tablosundakiyle birebir aynı.

> ⚠️ **Yeni ağa geçişte SSH host key uyarısı normaldir** — yeni IP,
> `known_hosts`'ta yok. Panik yapma: canlı anahtarı eski IP kayıtlarıyla
> karşılaştır (`ssh-keygen -F` hash'li olduğu için anahtar gövdesini
> `grep -F` ile ara); aynıysa MITM değil, yalnız yeni IP'dir.

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

### 🖥 QGC — operatörün kendi işi

**29 Ağustos 2026 operatör kararı:** QGC kurulumu ve 14550 link kontrolü
**uçuş öncesi listede değil.** Operatör bu süreci kendi makinesinde kendisi
yönetiyor; Claude sormaz, uçuşu bunun için durdurmaz.

Yine de bilinmesi gereken üç ayar — bir şey ters giderse buraya bak:

| Ayar | Doğrusu | Yanlışsa belirtisi |
|---|---|---|
| Comm Links → UDP, **dinleme portu 14550** | elle eklenmiş, bağlı | Uçaklar `udp-b` ile **süresiz yayında** kalır; telefon hotspot'unda laptopun interneti ölür (ölçülen tepe 14,5 sn). Tek link üç uçağı birden taşır |
| AutoConnect → **RTK GPS kapalı** | kapalı | QGC u-blox baz istasyonunun seri portunu kapar, `yki_rtcm_reader` açamaz (`Resource busy`), **RTCM hiç akmaz** — tek işaret `fix_type`'ın 6 yerine 3-5'te takılması |
| AutoConnect → **UDP kapalı** | kapalı | Otomatik link elle eklenenle çakışır |

```bash
ss -ulnp | grep 14550     # QGroundControl gorunmuyorsa link YOK/kopuk
```

⚠️ QGC'nin **açık olması yetmez** — `[LinkConfigurations]` boş ve
`autoConnectUDP=false` bir QGC kurulumunun **varsayılan hâlidir.**
Keşfedilen karşı taraf unutulmadığı için QGC'yi **sonradan kapatmak sorun
değil**; ama her `docker restart` MAVROS'u yeniden başlatıp pencereyi
yeniden açar. Tam ölçümler ve kök neden: `TUZAKLAR.md` §7.1 · §6.6.


## 🛡️ KAÇINMA KÖRLÜĞÜ ALARMI — 21-22 Ağustos'ta eklendi, ÇALIŞIYOR

**Ne işe yarıyor:** çarpışma önleme uçağın *gözü değil kulağıdır* — komşusunu
ancak mesh yayınından bilir. Yayın kesilirse gökyüzü **boş görünür** ve
kaçınma sessizce devre dışı kalır. Bu alarm o sessizliği bitiriyor.

**Neden var:** 21 Ağustos uçuşunda operatör ylp02'yi ylp00'a **3 metreye**
kadar yaklaştırdı, kaçınma **hiç tetiklenmedi**. Sebep algoritma değildi:
ylp00 komşusunu **46,4 saniye** hiç görmedi — mesh linki **tek yönlü** ölmüştü
(ters yön aynı anda kusursuz çalışıyordu, YKİ ylp02'yi sağlıklı görüyordu).
O 47 saniye boyunca **hiçbir alarm yoktu.**

**Nasıl çalışıyor:**

```
komsu 2 sn goremiyor  ->  ucak kendi DURUM paketinde bayragi kurar
                          (DURUM2_BAYRAK_KACINMA_KORU = 0x04)
                      ->  baz kopru bayragi cozer, SystemEvent yayinlar
                      ->  YKI: KRITIK uyari + SESLI alarm + masaustu bildirimi
```

Ekranda görünen: **"Çarpışma riski: droneN KOMŞUSUNU GÖREMİYOR — o komşuya
karşı çarpışma koruması YOK"**. Düzelince kendiliğinden temizleniyor.

| ayar | değer | anlamı |
|---|---|---|
| `korluk_alarm_s` | **2,0 sn** | bu kadar görmezse alarm |
| `korluk_tut_s` | **0,0 = KAPALI** | operatör kararı: uçak durmasın, haber versin |
| `komsu_durum_bayat_s` | 5,0 sn | mesh bayrağının eşiği |

> `korluk_tut_s` açılırsa (örn. `5.0`) uçak körlükte **yatay hareketi
> durdurur**, dikey serbest kalır. Otonom finalde operatör müdahalesi
> olmayacaksa düşünülmeli. Mekanizma yazılı ve testli, tek parametre.

**Eşikler ölçümden:** sağlıklı linkte komşu verisi boşluğu maks **0,4 sn**
(21 Ağustos uçuş kaydı). 2 sn alarm eşiği bunun 5 katı — geçici mesh
sarsıntısı yanlış alarm üretmez.

### Test etme — uçmadan, konteyner yeniden başlatmadan

```bash
# ylp00 ylp02'yi DUYMASIN (ylp02 YKİ'de görünmeye devam eder)
docker exec drone1 ros2 param set /esp32_bridge sahte_kayip_ajanlar "[3]"
# geri al
docker exec drone1 ros2 param set /esp32_bridge sahte_kayip_ajanlar "[0]"
```

🔴 **Bir düğümü öldürmek bu testi KARŞILAMAZ** — uçak YKİ'den de kaybolur ve
gerçek arızanın en önemli yanı (*ekranda sağlıklı görünen uçak*) hiç oluşmaz.
Bkz. `TUZAKLAR.md` §2.16.

⚠️ **YKİ tarafında iki şart:** tarayıcı sesi için sayfaya **bir kez tıklamak**
(otomatik-oynatma politikası), masaüstü bildirimi için **izin vermek**. İkisi
de 22 Ağustos'ta sahada doğrulandı.

**Bu sınır KALKTI (27 Ağustos 2026).** Eskiden burada "diğer `SystemEvent`'ler
YKİ'ye ulaşmıyor, mesh'te `TIP_EVENT` yok" yazıyordu; **artık yanlış** —
`TIP_OLAY` (0x16) eklendi ve uçağın **kendi ürettiği bütün** olaylarını
YKİ'ye taşıyor (`esp32_bridge._on_olay_out`). Alıcı taraf komşunun olayını
`/swarm/public/events/system`'e düşürüyor, YKİ oradan okuyor.

İki bilinçli süzgeç var:
- `EVENT_UNKNOWN` (0) mesh'e **çıkmaz** — `_diag_yayinla` saniyede bir bu
  tiple yerel sağlık sayacı yayınlıyor, mesh'i boşuna doldururdu (27 Ağustos
  canlı testinde bulundu).
- Yalnız **kendi** olayımız gider (`source_agent_id` ∈ {0, kendi id}); biri
  public'i internal'a köprülerse geri besleme döngüsü kurulmasın diye.

⚠️ Mesh 16 bayt taşıdığı için olayın **metni gitmiyor**, yalnız kodu. YKİ
etiketi enum'dan kuruyor (`SYSTEM_EVENT_LABELS`, 29 etiket) ve `value` +
`source_module` alanlarını ekliyor. Yani YKİ'de gördüğün olay metni uçakta
yazılmış cümle değil, YKİ'nin kod karşılığı.

---
## 3. Uçakta açık olan bayraklar

Bunlar **dosya varlığıyla** çalışıyor; uçağı bulan kişi böyle bulacak.
Aksi yazmıyorsa **üç uçakta da aynı.**

| Bayrak | Değer | Anlamı |
|--------|-------|--------|
| `~/yelpence_ws/suru_dugumleri` | **`origin consensus fsm formasyon ca`** | Varsa `SURU_DUGUMLERI` env'ini ezer. Düğüm açmak: `echo ... > dosya` + `docker restart`. `sekans` anahtarı 28 Ağu testinden sonra SİLİNDİ |
| `~/yelpence_ws/gozlem` | **YOK** | Formasyon uçağı **DOĞRUDAN SÜRER**. Bu yüzden mesh `goto` uçağa gitmez (tek-üretici geçişi). Eski düzen için `touch /ws/gozlem` + restart |
| `~/yelpence_ws/yer_testi` | **YOK** | Uçaklar kalkış komutunu **ALIR**. Yer testine dönüş: `touch` + restart |
| `~/yelpence_ws/origin` | **var** | `38.6904758 39.1610188 1216.96` — tek kaynak `deploy/saha_origin.env`. Elle yazma, `dagit.sh` dağıtır. **Üçünde de AYNI olmalı**, yoksa formasyonlar uçaktan uçağa kayar |
| `~/yelpence_ws/ucus_ayarlari.env` | **var** | Seyir 3.0 m/s. `ucus_ayarlari.py --kabuk` üretir — elle yazma |
| `~/yelpence_ws/gcs_url` | var | MAVLink QGC'ye iletiliyor (`udp-b://:14555@14550`) |
| `~/yelpence_ws/tgt_system` | ylp02'de `3` | ylp02'nin FCU sysid'i 3 |
| `BATARYA_KRITIK_V` | `0.0` | FSM bataryaya bakmıyor (regülatörden besleme) |
| `~/yelpence_ws/gps_saat_kapali` | yok | Varsa GPS'ten saat düzeltmesi yapılmaz |
| ~~`~/yelpence_ws/kacinma`~~ | **kaldırıldı** | 🔴 `basit_kacinma` 29 Ağu'da silindi. Dosya bir uçakta duruyorsa **`baslat.sh` hata verip durur** — sessizce korumasız kalmasın diye |


### 🔴 UÇMADAN ÖNCE: `yer_testi` bayrağını kaldır

```bash
./deploy/yki/drone_bul.sh ylp00 'rm -f ~/yelpence_ws/yer_testi ~/yelpence_ws/gozlem && docker restart drone1'
./deploy/yki/drone_bul.sh ylp02 'rm -f ~/yelpence_ws/yer_testi ~/yelpence_ws/gozlem && docker restart drone3'
```

Açık kaldığı sürece "görev başladı" komutu uçağı ARM eder ve **orada
bırakır** — kalkış komutu gönderilmez. Yer testleri için var.

### 🔴 Yer testinden çıkış: **kumandadan kill switch** — 20 Ağu'da yeniden yaşandı

Yazılım disarm'ı OFFBOARD'dayken PX4 tarafından reddediliyor (`result=1`).
**20 Ağustos yer testinde tekrar oldu:** `guided/3/disarm` tuttu sanıldı,
ylp02 disarm olmadı, operatör kumandadan kesti. `guided arm` uçağı OFFBOARD'a
sokuyor — ayrıntı `TUZAKLAR.md` §3.11.
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
## 4. Kod senkronu

```
ucaklarda (uc de) : 04f3828 +KIRLI    29 Agustos 19:15'te dagitildi ve
                                       konteynerler yeniden baslatildi
repoda            : 04f3828 + commit'lenmemis degisiklikler
                    (kural sadelestirmesi, --paket/--yalniz, --durum eklentileri)
```

**29 Ağustos dağıtımının doğrulanmış hâli** (üç uçakta da aynı):

| | ylp00 | ylp01 | ylp02 |
|---|---|---|---|
| `baslat.sh` md5 | depo ile AYNI | AYNI | AYNI |
| `ros2 node list` | 79 | 79 | 79 |
| bizim düğümler | 11 | 11 | 11 |
| mesh komşu tazeleme | 10,7 / 10,8 Hz | 10,7 / 11,9 Hz | 10,8 / 11,7 Hz |
| `basit_kacinma` · `kinematic_fusion` | silindi | silindi | silindi |

⚠️ **`.surum` dosyasına tek başına güvenme** — `dagit.sh` derleme başarısız
olsa bile `.surum` yazıyor (`TUZAKLAR.md` §1.14). Senkron kontrolü artık
`drone_bul.sh --durum` içinde (md5 + düğüm sayısı).

### ⚡ Kod değişikliğinde tam restart gerekmiyor (29 Ağustos)

```bash
./deploy/rpi/dagit.sh --paket swarm_core ylp00          # yalnız o paket derlenir
./deploy/yki/drone_bul.sh ylp00 \
    'docker exec -d drone1 bash /ws/baslat.sh --yalniz ca'   # yalnız o düğüm
```

`--yalniz` **mavros, px4_bridge, agent_fsm, esp32_bridge, uçuş kaydı ve
günlük bekçisine dokunmaz**; yeni günlük dizini de açmaz (mevcut `son`
dizinine yazar). Gating değişkenleri (`SP_REMAP`, `VELOCITY_ONLY`, boş yuva
kapısı) normal açılıştaki gibi `/ws/suru_dugumleri`'nden hesaplanır — yani
`--yalniz formasyon` derken CA kapalı sanılmaz.

| | Tam `docker restart` | `--yalniz <düğüm>` |
|---|---|---|
| Sabit `sleep` | ~50 sn | ~2 sn |
| MAVROS / PX4 el sıkışması | yeniden | dokunulmaz |
| RTK kilidi · consensus seçimi | yeniden | korunur |
| `colcon build` | 6 paket | `--paket` ile 1 |

> 🔴 **Uçuş sırasında kullanma.** Düğüm saniyelerce yok olur; kaçınma ya da
> formasyon o pencerede sessizce devre dışı kalır.
>
> ⚠️ Bir `.msg`/`.srv`/`.action` değiştiyse `--paket` **kullanma** — arayüz
> değişip bağımlılar yeniden derlenmezse eski başlıklarla koşarlar ve hata
> yerine **yanlış veri** alırsın.

🔴 **29 Ağustos sadeleştirmesi `baslat.sh`'i değiştirdi** (`basit_kacinma` ve
`fusion` blokları kalktı). Dağıtımdan sonra açılış logunda şu satırlar
görülmeli: `CARPISMA KACINMASI ACIK (collision_avoidance)` ve
`TEK-URETICI (ADIM 3)`.

---

## 5. Sahada koşan düğümler

```
mavros_node · px4_bridge · agent_fsm_node · esp32_bridge
+ collision_avoidance · ic_dis_kopru · swarm_origin_publisher
+ consensus_node · swarm_fsm_node · formation_node · path_planner
```

**11 düğüm.** (`ros2 node list` toplam ~80 gösterir; fazlası MAVROS'un
eklenti alt düğümleri, normal.)

`ic_dis_kopru` herhangi bir sürü düğümü açıksa kendiliğinden kalkıyor —
sözleşmenin `internal → public` yerel döngüsünü o kuruyor.

**Görev düğümleri KAPALI** — Görev 1'in tamamı bunlara bağlı:
`mission1`, `mission_fsm`, `camera_driver`, `vision_node`,
`precision_landing`, `task_reallocator`, `maneuver_executor`.
Görev 2 için: `mode_manager`, `joystick_interpreter`.

### Lider seçimi — ölçülmüş davranış

Consensus hem yerde hem havada çalışıyor. Yerde iki uçak **aynı lideri**
101 ms arayla seçti; kill switch lideri FAILSAFE'e düşürünce devir
**82 ms**'de oldu. Havada 21 Ağustos'ta ölçüldü: split-brain sıfır, kalp
atışı boşluğu maks **218 ms** (eşik 1000), DURUM maks **408 ms** (eşik 5000).

⚠️ Guided yolda ajan `agent_fsm`'i atlıyordu ve consensus hiç seçim
yapamıyordu; `esp32_bridge` guided ARM'da yerel `EVENT_MISSION_STARTED`
üretince kapandı. Kalkış otoritesi guided'da (`kalkis_olayla=false`).

⚠️ **P1.14 açık:** lider kimliği mesh'e kalp atışıyla taşınıyor, seçim
çerçevesiyle değil → **asimetrik kopmada iki lider kalıcı olabilir.**
Bugün zararsız değil — formasyon uçağı sürüyor. Görev düğümleri açılmadan
önce çözülmeli.

---


## 6. Kanıtlanmış / doğrulanmış olanlar

Bunlar sahada ölçüldü, tekrar sorgulanmasın:

- **Uçuş kanıtı videosu geçildi.**
- **Üç uçaklı formasyon geçiş sekansı uçtu** (28 Ağustos): çizgi→ok→V→çizgi→EVE,
  tamamen uçakta, tek YKİ butonuyla. `avoid=0`, en yakın çift ~8,0 m, 123 s.
- **Otonom çarpışma önleme havada** (22-26 Ağustos): dikey yol verme, üç uçaklı
  testte 4/4 kaçış-dönüş, taban aynası ×2, sıfır körlük.
- **Görev koşucusu** `--senaryo saha`: 5 nokta, 8→15 m, çizgi↔okbaşı formasyon
  değişimi, rotasyonlar, 135° güneydoğuya dönüp iniş. ~187 s görev / ~222 s video.
- **Kuru test** kritik ayrım **8.41 m** (eşik 4.0 m) — `SONUÇ: GEÇTİ`
  (aralık 12 m'ye çıkınca 7.07'den yükseldi)
- **RTK-FIX üç uçakta birden** (25 Ağustos, taze survey, 1005 canlı); baz
  `1005` dahil tam RTCM seti yayınlıyor.
  **18 Ağustos'ta baz MSM4'e alındı** — akış artık `1005, 1074, 1084, 1094,
  1124, 1230` @ ~1 Hz, `crc_err=0` (öncesinde MSM7 vardı ve okuyucu uyarıyordu;
  `YELPENCE_RTCM_SPEC.md` §401 MSM4 bekliyor).
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
  bkz. `PLAN.md` §9

---
## 7. Bilinen açık sorunlar

| # | Sorun | Etki | Nerede |
|---|-------|------|--------|
| 1 | 🔴 **HOME kayması — RTL'e güvenilmez** | RTL üç uçağı kalkışa değil aynı yanlış civara indirdi (~9 m KD). **Çözülmeden RTL'li uçuş YOK**; iniş `land` + göz önü alanla | `YAPILACAKLAR` P0 |
| 2 | 🔴 **MAVROS GCS denetimi yalnız açılışa bakıyor** | Taşkın sonradan başlıyor: 27 Ağu'da üçü de "temiz" raporlanmışken 5 M hata / 522 MB. Otomatik onarım **yalnız Pi uptime < 15 dk**; sonrası operatörde (SSH + restart) | `YAPILACAKLAR` P0 |
| 3 | 🟠 Görev düğümleri hiç uçmadı | Görev 1'in tamamı bunlara bağlı: `mission1`, `mission_fsm`, `vision_node`, `precision_landing`, `task_reallocator`, `maneuver_executor` | `PLAN.md` §8 |
| 4 | 🟠 Görev 2 zinciri hiç koşmadı | `mode_manager` + `joystick_interpreter` kod hazır, dağıtılmadı | `KARARLAR` KARAR-11 |
| 5 | 🟡 Drone'larda repoda olmayan betikler | Bilgi versiyonsuz, kaybolabilir | `YAPILACAKLAR` P2 |
| 6 | 🟡 ESC telemetrisi kapalı | ylp01'in 2 Ağustos düşüşünün sebebini doğrudan verirdi | `YAPILACAKLAR` P2 |
| 7 | 🟡 Wi-Fi düşünce MAVROS log patlıyor | Bekçi kırpıyor ama **kök neden hâlâ bilinmiyor** | `TUZAKLAR` §2.23 |
| 8 | 🟡 Pi saati açılışta geriden | Çapraz uçak log karşılaştırması bozulur | aşağıda |
| 9 | ⚪ `iPhone` SSID'si doğrulanmadı | Telefon açılınca teyit gerekir | `RPI_ESITLEME.md` §7 |

### 🟡 #8 — Pi saati: kök neden bulundu, düzeltme dağıtıldı, **henüz etkin değil**

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

**Ne zaman çalıştır:** bir PX4 parametresi **yazıldıktan sonra** ve saha
gününde bir kez — *uçuş başına değil* (29 Ağu operatör kararı, `CLAUDE.md` §9).
Ayrışma ancak biri parametre yazdığında oluşur; 14 Ağustos'tan beri tekrarı
görülmedi.

```bash
./deploy/yki/param_karsilastir.py
```

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