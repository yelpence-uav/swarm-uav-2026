# GÜNLÜK — oturum devir teslim kaydı

**Son güncelleme:** 15 Ağustos 2026, 16:10

Tek bilgisayar, sırayla çalışıyoruz. Biri kalkıp diğeri oturduğunda **hem
kişi hem Claude** nerede kalındığını buradan anlar.

**En yeni kayıt en üstte.** Her oturumun sonunda yeni bir kayıt ekle —
atlanırsa sistem çöker, çünkü sohbet geçmişi sonraki kişiye geçmiyor.

Claude'a **"oturumu kapat"** dersen bu kaydı o yazar.

---

## Şablon (kopyala, en üste yapıştır)

```markdown
## YYYY-AA-GG SS:DD — <isim>

**Ne yapıldı**
- (somut, ölçülmüş sonuçlarla; "denedik" değil "şu çıktı")

**Ne değişti**
- kod: `dosya:satır` — ne, neden
- uçakta: hangi bayrak/parametre/dosya değişti (SONRAKİ KİŞİ ÖYLE BULACAK)
- belge: hangi md güncellendi

**Yarım kalan / tuzak**
- (bir sonraki kişinin bilmediğinde zaman kaybedeceği her şey)

**Sıradaki adım**
- (tek cümle, net; YAPILACAKLAR.md'deki madde numarasıyla)

**Uçakların bırakıldığı hâl**
- ylp00: (kill switch? pil? nerede? konteyner ayakta mı?)
- ylp02:
```

---

## 2026-08-15 16:10 — Eyüp + Claude

**Ne yapıldı**

- 🎉 **ADIM 1 GEÇTİ — sürü kodlarının ilk düğümü sahada çalıştı.**
  İki uçak pervanesiz, ARM'lı, yerde: ikisi de **aynı lideri** seçti.
  ```
  ylp00: [CONSENSUS] Lider: 0 -> 1 (round=1, ben=1)
  ylp02: [CONSENSUS] Lider: 0 -> 1 (round=1, ben=3)     101 ms arayla
  ylp00: esp32_bridge  lider 0 -> 1 (BEN)  ← formasyon kapisi ACIK
  ```
- **Lider arıza devri gözlendi (planlanmamıştı):** kill switch ylp00'ı
  FAILSAFE'e düşürdükten **82 ms sonra** kendi consensus'u
  `Lider: 1 -> 3 (round=2)` dedi. `REASON_LEADER_FAULT` çalışıyor.
- **ylp02 QGC'ye gelmiyordu, çözüldü.** Sahaya götürülüp WiFi kopunca
  Pi tuştan yeniden başlatıldı; konteyner ağdan önce kalktı ve MAVROS'un
  `gcs_url` ucu kurulamadı. `docker restart` düzeltti.
  **Ölçülüp elenen suçlular:** seri çerçeveleme @921600 (67 ardışık geçerli
  çerçeve), FCU `sysid=3 compid=1`, sıcaklık 54.3 °C / throttle `0x0`,
  UDP tekil **ve** yayın. Hiçbiri arızalı değildi.
- Sabah: `agent_fsm` preflight eşiği, GPS'ten saat düzeltme,
  `/ws/suru_dugumleri` dosya anahtarı, `dagit.sh` IP tablosu, `run_drone.sh`
  dağıtımı, konteynerlere `--cap-add SYS_TIME`.

**Ne değişti**

- kod: `preflight_checker.py` (eşik bağlamdan) · `agent_fsm_node.py`
  (`yer_testi` bayrağı + ARMING reddi artık loglanıyor) ·
  `esp32_bridge_node.py` (`healthy` türetiliyor) · `baslat.sh`
  (origin düğümü, consensus parametreleri, dosyadan düğüm açma, GPS saat) ·
  `dagit.sh` · `run_drone.sh` · yeni `deploy/rpi/gps_saat.py`
- **uçakta (SONRAKİ KİŞİ ÖYLE BULACAK):**
  - `~/yelpence_ws/yer_testi` — **AÇIK** ⚠️
  - `~/yelpence_ws/suru_dugumleri` = `origin consensus`
  - `~/yelpence_ws/origin` = `38.6905999 39.1611543 1216.03`
  - konteynerler **yeniden yaratıldı** (`--cap-add SYS_TIME`)
- belge: `SURU_ENTEGRASYON` (sıra düzeltildi), `DURUM`, `YAPILACAKLAR`,
  `KARARLAR` (KARAR-02, KARAR-03), `cihazlar.md`, `RPI_ESITLEME`

**Yarım kalan / tuzak**

- 🔴 **`yer_testi` iki uçakta da AÇIK.** Bu haldeyken uçak arm olur ama
  **kalkmaz**. Uçuştan önce `rm ~/yelpence_ws/yer_testi` + `docker restart`.
- **Yazılım disarm'ı OFFBOARD'dayken reddediliyor** (`result=1`).
  Sebep ölçüldü: pervanesiz OFFBOARD'da PX4 irtifayı tutmaya çalışıp
  integrali sarıyor, gaz tırmanıyor, PX4 kendini "yerde" saymıyor.
  **Yer testinden çıkış: kumandadan kill switch.** Ayrıca armlı bekleme
  süresini kısa tut — 140 sn bekletildi, gereksizdi.
- **İki uçaklı tam devir teslim testi yapılmadı** — birini kill'leyip
  diğerini armlı bırakmak gerekiyor.
- Origin şu an `/public`'e **remap** ile gidiyor; mesh yolu denenmedi.
- `mesh healthy` **türetim**, gönderenin kendi değeri değil. Pil izleme
  açılınca (KARAR-03) pil düşüşü buraya yansımaz.

**Sıradaki adım**

ADIM 2 — `swarm_fsm_node`. Ama önce P0.6a'daki iki düzeltme:
sabit formasyon ofsetleri ve tek global election seq sayacı. **`agent_count`
için "2 yap" notuna uymadan önce kodu oku** — consensus'ta aynı not
yanlıştı ve uygulansaydı ylp02 sürüden düşerdi.

**Uçakların bırakıldığı hâl**

- ylp00: IDLE, disarm, kill switch serbest, kumanda HOLD, atölyede
- ylp02: aynı — bugün sahaya çıkıp döndü, QGC bağlantısı çalışıyor

---

## 2026-08-14 20:15 — Eyüp + Claude

**Ne yapıldı**
- Takım çalışma sistemi kuruldu: `CLAUDE.md`, `docs/DURUM.md`,
  `docs/GUNLUK.md`, `docs/YAPILACAKLAR.md`, `docs/SURU_ENTEGRASYON.md`,
  `docs/COP_TEMIZLIK.md`, `ss/` klasörü.
- **ylp00 ve ylp02 SSH ile denetlendi.** Sonuç: kod drift'i **yok**.
  `baslat.sh` md5 `c99462c3...` repo = her iki uçak, birebir aynı.
  Python kaynakları 131/131 ve 132/132 dosya repo ile aynı.
- Sahada koşan düğümler `ps` ile doğrulandı: **mavros, px4_bridge,
  agent_fsm_node, esp32_bridge, basit_kacinma** — beş düğüm.
  14 sürü düğümünün hiçbiri açık değil.
- **Kritik bulgu:** `basit_kacinma` ve `collision_avoidance` **birebir aynı
  topic yuvasını** kullanıyor (`/control/setpoint/raw` → `/control/setpoint`).
  Aynı anda açılırlarsa px4_bridge iki farklı algoritmadan çelişkili setpoint
  alır. Aynı çakışma `esp32_bridge` ile `formation_node` arasında da var.
  Sürü entegrasyonunun tamamı bu çakışmayı çözmek üzerine kuruldu.
- Ağ değişmiş: `10.158.16.x` → `10.188.209.x`. Son oktetler sabit kaldı
  (134 / 189 / 115) — hotspot MAC'e göre adres veriyor.
- `~/yelpence_ws/.surum` dosyasının **eskimiş** olduğu görüldü; senkron
  kontrolünde ona güvenilmemeli.

**Ne değişti**
- kod: değişmedi
- uçakta: **hiçbir şey değiştirilmedi** — yalnız okundu
- belge: yukarıdaki altı dosya yeni; `.gitignore`'a `ss/` ve üretilen
  harita HTML'leri eklendi

- **`deploy/yki/drone_bul.sh` yazıldı ve test edildi.** MAC'ten IP bulup SSH
  bağlıyor. Dört kip de doğrulandı: `--liste`, `--ip`, komut kipi, `--durum`;
  ayrıca mDNS devre dışı bırakılıp MAC tarama yolu ayrıca test edildi.
  **mDNS bu hotspot'ta çalışıyor** (`ylp00.local` çözüldü).
- **🔴 `--durum` ilk çalıştırmada kritik arıza yakaladı: İKİ DRONE'DA DA DİSK
  %100 DOLU.** Sebep `mavros.log` — ylp00'da 18.64 GB, ylp02'de 21.57 GB
  (29 GB disk). Uçuş kayıtları suçlu değil (`kayit/` 4.6 / 3.0 GB).
  ylp02'de şu anki açılışın logu 1 saatte 1.56 GB. **`ros2 bag` yazamaz →
  bir sonraki uçuş kaydedilmez.**
- Parola girişinin **açık** olduğu doğrulandı (sshd varsayılanı, override yok)
  → arkadaşlar kendi anahtarlarını kendileri kurabilir.
- Her iki Pi'de **tek kayıtlı Wi-Fi ağı** (`rpissid`) ve `authorized_keys`'te
  **tek satır** olduğu görüldü.

- **Disk sorunu ÇÖZÜLDÜ.** Loglar temizlendi (konteyner içinden root olarak —
  dizinler `root` sahipli, SSH kullanıcısı silemiyor). `baslat.sh`'e günlük
  bekçisi eklendi: 60 sn'de bir tarar, 100 MB'ı aşanın **son 25 MB'ını**
  korur, kırpmayı `bekci.log`'a zaman damgasıyla yazar. 21 yönlendirme
  `>` → `>>` çevrildi (O_APPEND olmadan kırpma seyrek dosya üretiyor —
  mekanizma yerelde test edildi: 10.7 MB → 100 KB, sonraki yazma yeni sona gitti).
  Açılış dizini 10 → 5. İki drone'a dağıtıldı, md5 `51d97b3e...` üçünde de aynı.
  **Sonuç: ylp00 19 GB boş (%34), ylp02 21 GB boş (%27).**
- **`docs/RPI_ESITLEME.md` oluşturuldu** — Pi'lerde yapılan her değişikliğin
  hangi uçakta olduğunu tutan defter. Geri gelen drone'u hizaya getirmek için.
- **PX4 parametre okuma ÇÖZÜLDÜ.** Önce "okunamıyor" sandım — yanlıştı.
  Gerçek sebep: `/drone_N/mavros/param/get` diye bir servis **yok**;
  MAVROS 2 parametreleri **yerel ROS 2 parametresi** olarak sunuyor.
  Doğrusu `ros2 param get /drone_N/mavros/param <AD>` — ama her çağrı yeni
  düğüm açıp DDS keşfi yaptığı ve düğümde 1007 parametre olduğu için
  ard arda çağrıların yarısı zaman aşımına düşüyor (4 istekten 2'si).
  **Çözüm:** tek düğüm + toplu `get_parameters` isteği.
  Araçlar: `src/gcs/px4_param.py` (drone üzerinde koşar) ve
  `deploy/yki/param_karsilastir.py` (uçakları yan yana koyar).
  `drone_bul.sh`'e `--tablo` kipi eklendi ki drone listesi tek kaynaktan gelsin.
- **🔴 Araç ilk çalıştırmada gerçek ayrışma buldu:**
  `MPC_TILTMAX_AIR` ylp00=**45** / ylp02=30, `MPC_YAWRAUTO_MAX` ylp00=**45** /
  ylp02=25. Diğer 10 uçuş parametresi eşit, `MAV_SYS_ID` doğru şekilde farklı.
  **Tehlikeli olan:** `gorev_kanit_ucus.py:1980`'deki `MAKS_EGIM_DEG = 35.0`
  gerekçesi "`MPC_TILTMAX_AIR=30`" — ylp00 45°'ye eğilebildiği için normal
  uçuşta bunu geçip görevi boş yere iptal ettirebilir. Kimse bilmiyordu.
- **`YAPILACAKLAR.md` öncelik şemasıyla yeniden yazıldı** (🔴P0 / 🟠P1 / 🟡P2 / ⚪P3).
- **`src/gcs/ucus_ayarlari.py` kuruldu — hız/ivme/aralık/açı tek kaynak.**
  Açılar artık elle yazılmıyor, ivmeden türetiliyor (`a = g·tan θ`) ve
  dedektör eşiği tavandan. `gorev_kanit_ucus.py`'deki 7 sabit oradan okuyor
  (`ARALIK_M`, `KANAT_ACISI_DEG`, `TOLERANS_M`, `MIN_AYRIM_M`,
  `GOREV_HIZ_MPS`, `GOREV_DIKEY_HIZ_MPS`, `MAKS_EGIM_DEG`).
  Kipler: çözümleme · `--px4` · `--kabuk`.
- **Yeni yapılandırma:** seyir 2.0 → **3.0 m/s**, aralık 10 → **12 m**,
  PX4 tavanı 4.0 → **5.0**, eğim tavanı **30°**, dedektör **35°**.
  Kuru testle doğrulandı: kritik ayrım 7.07 → **8.41 m**, eşiğe pay
  3.07 → **4.41 m**, `SONUÇ: GEÇTİ`.
- **Bir ayrışma daha:** `MPC_VEL_MANUAL` ylp00=**4**, ylp02=**2** —
  kumandayla POSCTL hızı. Aynı çubuk hareketi iki uçakta farklı hız
  üretiyor; operatörün kas hafızası biri için yanlış.
- **5 m/s incelendi.** İlk analizim yanlıştı (frenleme mesafesini ayrım
  payına ekleyip 17 m aralık çıkardım — gerçek izleme gecikmesinin yedi
  katı). Düzeltildi: model artık izleme gecikmesine dayanıyor ve **12 m
  aralık 6 m/s'e kadar yetiyor.** 5 m/s'in tek gerçek şartı hız tavanının
  7.5'e çıkarılması (doygunluk payı).

- **Navigasyon kayması incelendi** (`docs/NAVIGASYON_KAYMA.md` yazıldı).
  Sonuç: sistem doğru yerde — `px4_bridge` yürütücüsü PX4'e hız
  ileri-beslemesi veriyor, yani `v = Kp·hata + v_ff` ve `v_ff = v` olduğu
  için **kalıcı kayma teorik olarak 0 ve hızla büyümüyor.**
  Kalan kayma yalnız hızlanma fazında.
- **İvme ileri-beslemesi kanalı var ama kapalı:** `AgentSetpoint`'te
  `ax/ay/az` + `acceleration_valid` alanları mevcut, ama `px4_bridge` hiç
  dokunmuyor ve `mavros_command_sender`'ın **dört type_mask'ında da**
  `IGNORE_AFX|AFY|AFZ` var. Açılırsa geçici rejimdeki kayma da kalkar.
- **`formation_node`'un SVT'si Durum 1** — saf oransal (`v = −0.8 × hata`),
  ileri-besleme yok. Kalıcı kayma `v/0.8`, PX4'ün 0.95'inden bile kötü.
  Bu, "formation_node'u konum kipine al" önerisini kayma açısından da
  destekliyor.
- **Doygunluk payı denetimi eklendi:** `tavan ≥ seyir × 1.5` artık **hata**.
  Seyir tavanla eşitse konum düzeltmesine yer kalmaz, PX4 kırpar ve kayma
  geri gelir. 5 m/s denendiğinde config "tavanı 7.5 yap" diyor.

- **Uçuş ayarları uçaklara UYGULANDI ve canlıda doğrulandı.**
  `baslat.sh` artık `/ws/ucus_ayarlari.env` okuyor; env dosyası dağıtıldı.
  PX4 parametreleri `px4_param.py --yaz` ile eşitlendi (tek düğüm/tek istek —
  `ros2 param set` 5 istekten 3'ünde zaman aşımına düşüyordu).
  Konteynerler yeniden başlatıldı, açılış çıktısı doğrulandı:
  `guided_hiz_yatay_mps:=3.0`,
  `[baslat] gunluk bekcisi: dosya 500 MB (son 125 MB korunur), dizin 3000 MB`,
  `[baslat] ucus ayarlari dosyadan: yatay=3.0`.
  `param_karsilastir.py` → **"Uçaklar arası ayrışma yok (16 parametre)"**.
- **`px4_param.py`'ye `--yaz` kipi eklendi** — toplu `set_parameters`.
- **Günlük bekçisi büyütüldü ve ikinci kapı eklendi.** 100/25 → **500/125**
  (normal log KB mertebesinde, tavan yalnız patlamada devreye giriyor;
  korunan oranı %25'te kalınca I/O yükü aynı ama beş kat geçmiş). Ayrıca
  **dizin geneli 3 GB tavanı** — sürü düğümleri açılınca 14 log olacak ve
  dosya başına tavan tek başına 35 GB'a izin verirdi. Dizin silme mantığı
  yerelde sahte açılış dizinleriyle test edildi (1201 MB → 401 MB, en yeni
  iki açılış ve `son` bağı korundu).
- **Kök dizin toparlandı:** PDF'ler `docs/sartname/`'ye, görseller `ss/`'ye.

- **CANLI PARAMETRE eklendi (`px4_bridge`).** Yürütücü ayarları artık uçak
  havadayken değiştirilebiliyor — yeniden başlatma gerekmiyor.
  Canlı olanlar: `guided_hiz_yatay_mps`, `guided_hiz_dikey_mps`,
  `guided_ivme_yatay_mps2`, `guided_ivme_dikey_mps2`, `guided_tasma_m`,
  `guided_konum_kp`, `guided_telafi_orani`.
  Kimlik (`agent_id`), kill/arm kanalları ve kalkış kilidi **bilerek dışarıda**.
  Doğrulama: sınır dışı değer (99) reddedildi, listede olmayan (`agent_id`)
  reddedildi, geçerli değişiklik `CANLI PARAMETRE: guided_hiz_yatay_mps
  3.0 -> 4.0` diye loglandı. İkisinde de 3.0'a geri alındı.
- **🪤 Bulunan tuzak (eski davranış):** `ros2 param set` "Set parameter
  successful" diyordu, `ros2 param get` yeni değeri gösteriyordu, **ama uçak
  eski hızda uçuyordu** — değerler `__init__`'te bir kez okunup örnek
  değişkenine yazılıyordu. Komut başarılı, gösterge doğru, davranış yanlış.
- **🪤 Uygularken düştüğüm tuzak:** geri çağrı `declare_parameter`'da **da**
  tetikleniyor. Geri çağrıyı `__init__` ortasında kaydedince, sonrasında
  `_setup_rtk()`'in tanımladığı `rtk_makul_payload` beyaz listede olmadığı
  için reddedildi ve **düğüm açılışta çöktü**
  (`InvalidParameterValueException`). Çözüm: `_parametre_kurulumu_bitti`
  bayrağı, `__init__`'in sonunda açılıyor — ileride biri yeni bir
  `declare_parameter` eklerse de kırılmaz.

**Yarım kalan / tuzak**
- ~~Konteynerler yeniden başlatılmadı~~ — bekçi bir sonraki açılışta devreye
  girer. Disk boş olduğu için acele yoktu, ama çalıştığı doğrulanmalı.
- **Bekçi belirtiyi kesiyor, kök nedeni değil.** WiFi düşünce MAVROS
  `gcs_url` uçnoktasına her mesaj için uyarı basmaya devam edecek.
- **Arkadaşların SSID + şifreleri Pi'lere eklenmedi** — Eyüp getirecek.
  Bu olmadan hiç kimse bağlanamaz.
- **`yelpence00`/`yelpence02` parolaları biliniyor mu?** Bilinmiyorsa
  anahtarlar erişim varken ŞİMDİ kurulmalı.
- **Repo hâlâ commit'siz.**

- **⚠️ `IZLEME_GECIKME_S = 0.22` DOĞRULANMAMIŞ.** Tek ölçümden türetildi ve
  o ölçüm 7 m'lik bir bacakta, yani geçici rejimde alındı. Teori kalıcı
  kaymanın ≈0 olduğunu söylüyor; sabit ölçüm yapılana kadar güvenli tarafta
  duruyor (ayrım payını gereğinden geniş tutuyor). Config'de işaretlendi.
  **40 m'lik bacakta ölçüm yapılmalı** — `NAVIGASYON_KAYMA.md` Adım 1.
- **🔴 `MPC_TILTMAX_AIR` / `MPC_YAWRAUTO_MAX` ayrışması KARARA BAĞLI.**
  Hangisi referans olacak (ylp02'nin 30/25 değerleri PX4 varsayılanı ve kodun
  varsaydığı değerler)? Eşitlenmeden ya da `MAKS_EGIM_DEG` düzeltilmeden
  uçulmamalı — `YAPILACAKLAR.md` P0.1/P0.2.

**Sıradaki adım**
- P0'ları kapat (parametre ayrışması), sonra SSID'ler (P1.1), sonra commit (P1.3).

**Uçakların bırakıldığı hâl**
- ylp00: ağda, konteyner `drone1` ayakta (3 saattir), `/ws/kacinma` var
- ylp02: ağda, konteyner `drone3` ayakta (3 saattir), `/ws/kacinma` var
- Son bilinen durumda **iki uçakta da kill switch AÇIK** idi (2 Ağu kuru testi)

---

## 2026-08-02 — Eyüp (kanıt uçuşu, geriye dönük yazıldı)

> Bu kayıt sonradan, sohbet özetinden derlendi. Ayrıntı:
> `docs/31temmuz-1agustos.md` ve `docs/BEKLEYEN_ISLER.md`.

**Ne yapıldı**
- **Uçuş kanıtı videosu çekildi ve geçildi.**
- ylp01 (drone 2) 20 m'den düştü. Kaza analizi: yalnız motorlar durdu, FC
  düşerken bile yayın yapıyordu → ESC güç/sinyal hattı, yazılım değil.
- Üç ciddi arıza kapatıldı:
  1. **Devrilme** — d1'de eski `esp32_bridge_node.py`/`basit_kacinma_node.py`
     vardı; bayat setpoint yerdeyken yatay konum kontrolü tetikliyordu.
     Ayrıca yatay kilit yalnız takeoff sonrası devredeydi, ölçülen 6.2 sn'lik
     arm→takeoff penceresi korumasızdı.
  2. **"Kalktılar, alçaldılar, asılı kaldılar"** — `takeoff` yere göreli,
     `goto` mutlaktı. Zemin NED −1.4'te olunca uçak 1.4 m alçalıyor, hata
     `TOLERANS_M`'i aşıyor ve adım 70 sn zaman aşımına kadar dönmüyordu.
  3. **d1 hiç ayarlanmamış** — `MPC_XY_VEL_MAX` 12.0 iken d3'te 4.0.
- Uçuş kaydı sertleştirildi (üç tampon katmanı kapatıldı).
- FSM pil failsafe'i kapatıldı (regülatörden besleme).

**Uçakların bırakıldığı hâl**
- ylp00, ylp02: uçar; ylp01: yerde
