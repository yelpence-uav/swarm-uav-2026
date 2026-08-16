# YAPILACAKLAR

**Son güncelleme:** 16 Ağustos 2026, 20:57

## Önem dereceleri

Her madde bir seviyeyle işaretlenir. **Seviye vermeden madde ekleme** —
seviyesiz liste bir süre sonra kimsenin okumadığı bir yığına dönüşüyor.

| | Seviye | Anlamı | Kural |
|---|--------|--------|-------|
| 🔴 | **P0 — UÇUŞ ENGELİ** | Uçağı, görevi veya kanıtı doğrudan riske atar | **Çözülmeden uçulmaz** |
| 🟠 | **P1 — ACİL** | Takımı bloke ediyor ya da kısa sürede P0'a dönüşecek | Bu hafta |
| 🟡 | **P2 — ÖNEMLİ** | Gerçek iş, ama bekleyebilir | Planla |
| ⚪ | **P3 — İLERİDE** | İyileştirme | Vakit olursa |

Durum: `[ ]` yapılmadı · `[~]` kısmen · `[B]` başka işe bağlı · `[?]` karar bekliyor · `[x]` bitti

---

## 🔴 P0 — UÇUŞ ENGELİ

### ✅ P0.1 — TAMAMLANDI (14 Ağustos)

`MAKS_EGIM_DEG` artık sabit değil, `ucus_ayarlari.py`'de **ivmeden
türetiliyor** (`MPC_TILTMAX_AIR + 5°`). Ayrıca `MPC_TILTMAX_AIR` iki uçakta
da 30'a eşitlendi, yani eşik (35°) tavanın 5° üstünde — dedektör geçerli.

- `[x]` 🔴 `gorev_kanit_ucus.py` sabiti kaldırıldı, config'den okuyor
- `[x]` 🔴 `MPC_TILTMAX_AIR` ylp00'da 45 → 30

### ✅ P0.2 / P0.3 — TAMAMLANDI (14 Ağustos)

PX4 parametreleri eşitlendi ve uçuş ayarları tek kaynağa bağlandı.
`param_karsilastir.py` → *"Uçaklar arası ayrışma yok"*. Ayrıntı:
`RPI_ESITLEME.md` §8.

- `[x]` 🔴 `MPC_TILTMAX_AIR` 45→30, `MPC_YAWRAUTO_MAX` 45→25,
  `MPC_VEL_MANUAL` 4/2→3.0, `MPC_XY_VEL_MAX` 4.0→5.0 (iki uçakta da)
- `[x]` 🔴 `baslat.sh` artık `/ws/ucus_ayarlari.env` okuyor; hız 3.0 canlıda
- `[x]` 🔴 Konteynerler yeniden başlatıldı, günlük bekçisi de devrede
- `[ ]` 🟠 **ylp01 döndüğünde aynısını uygula** — `RPI_ESITLEME.md` §8

### P0.4 Navigasyon kayması — ölçülmedi

Tam plan: **`NAVIGASYON_KAYMA.md`**. Özet:

Sistem teorik olarak doğru yerde (konum + hız ileri-beslemesi → kalıcı
kayma ≈ 0, hızla büyümez). **Ama bunu doğrulayan ölçüm yok.** Elimizdeki
tek sayı 7 m'lik bir bacaktan geldi, yani geçici rejimi ölçüyor.

- `[ ]` 🔴 **ÖLÇ:** tek uçak, **en az 40 m düz bacak**, iki hızda (2 ve 4 m/s).
  Kayıttan `setpoint_raw/local` ile `local_position/pose` farkını çıkar.
  Üç sayı: kalıcı kayma · tepe geçici hata · oturma süresi.
  Bu ölçüm hızı yükseltmenin önünü açar ya da kapatır.
- `[x]` 🔴 ~~Doygunluk payı denetimi~~ → `ucus_ayarlari.py` artık
  `tavan ≥ seyir × 1.5` şartını **hata** olarak veriyor
- `[ ]` 🟠 **İvme ileri-beslemesini aç** — kanal mesajda var
  (`ax/ay/az`, `acceleration_valid`) ama `mavros_command_sender`'ın
  **dört type_mask'ında da** `IGNORE_AFX|AFY|AFZ` var. Geçici rejimdeki
  kaymayı kaldırır. Adım 1'in ölçümü değip değmeyeceğini söyleyecek.
- `[ ]` 🟠 **Sürü tarafı Durum 1'e düşmesin** — `formation_node`'un SVT'si
  saf oransal (`v = −0.8 × hata`), yani ileri-besleme YOK. Kalıcı kayma
  `v/0.8`, PX4'ün 0.95'inden bile kötü. Çözüm: `formation_node`'u
  konum kipine al (`position_valid=True`).

---

### P0.5 Final görevi donanım şartları

Şartname okundu (15 Ağustos). Üç şart yazılımla çözülemez:

- `[x]` ✅ Her İHA için ayrı pilot + kumanda — **var**
- `[ ]` 🟠 **Kamera** takılacak. FOV ≤ 90°. QR 120×120 cm; hangi irtifadan
  okunduğu **ölçülmeli** (Aşama 3'ün ön koşulu, diğer aşamaları engellemez)
- `[ ]` 🟡 **ylp01** — final görevinde **3 İHA şart**, ama entegrasyonu
  engellemiyor. Yalnız Aşama 5'teki üyelik testi üç uçak istiyor

### ✅ ADIM 1 GEÇTİ (15 Ağustos) — ve iki engel yolda düzeltildi

İki uçak yerde, pervanesiz, ARM'lı: ikisi de **aynı lideri** seçti
(`Lider: 0 -> 1`, 101 ms arayla). `esp32_bridge` lideri öğrendi, formasyon
kapısı açıldı. Lider arıza devri de gözlendi (`1 -> 3`, 82 ms).

- `[x]` 🔴 ~~mesh `AgentStatus` `healthy` taşımıyor~~ → **düzeltildi.**
  Alıcı varsayılan `false` bırakıyordu; `is_eligible` bunu şart koştuğu için
  hiçbir uzak ajan aday olamıyor, her uçak kendini seçip **split-brain**
  üretiyordu. `esp32_bridge` decode'unda artık türetiliyor
  (`ekf_ok` ∧ ¬`kill_switch` ∧ state≠FAILSAFE). Paket ve firmware değişmedi
  (bayrak baytı 8/8 dolu).
- `[x]` 🔴 ~~`swarm_origin_publisher` ADIM 8'de~~ → **ADIM 0.5'e alındı.**
  `preflight` `origin_synced` şart koşuyor; origin gelmeden ARMING olmuyor,
  dolayısıyla consensus hiç lider seçemiyor.
- `[x]` 🟡 `agent_fsm`: IDLE'da ARMING reddi artık **loglanıyor** — eskiden
  tamamen sessizdi ve testte yarım saat kaybettirdi

**Kalan iş:**

- `[ ]` 🟠 **İki uçaklı tam devir teslim testi** — birini kill'le, diğerini
  armlı bırak; ikincisi liderliği devralıyor mu? Bugün tek taraflı gözlendi
- `[x]` 🟡 ~~Origin `/public`'e remap ile gidiyor~~ → **remap kaldırıldı.**
  `ic_dis_kopru` gelince (P0.6) düğüm sözleşmeye uygun şekilde
  `/swarm/internal/origin`'a yazmaya döndü; origin artık **hem** yerel
  düğümlere **hem de** `esp32_bridge` üzerinden mesh'e gidiyor. Remap
  varken mesh yolu tamamen kapalıydı.
- `[ ]` 🟡 Origin'in **mesh yolu** hâlâ denenmedi — bir uçağın origin'i
  diğerine ulaşıyor mu? Şu an ikisi de aynı sabit değeri yayınladığı için
  fark görünmez; test için birini kapatıp diğerininkini bekle
- `[ ]` 🟡 Mesh `healthy` bir **türetim**, gönderenin kendi değeri değil.
  Pil izleme açılınca (KARAR-03) pil düşüşü buraya yansımaz — o gün ya
  pakete bit eklenecek ya da eşik burada da uygulanacak
- `[ ]` 🟡 `ARMED → KALKIS(2) → TAKEOFF(4)`: yerde armlı uçak komşularına
  **havada** görünüyor (`AIRBORNE_STATES`). Kaçınma ve formasyon buna bakıyor

### P0.6a Kod okuma bulguları — entegrasyondan önce düzeltilecek

19 düğümün tamamı okundu (15 Ağustos). Tam liste: `SURU_ENTEGRASYON.md`.

- `[ ]` 🔴 **`cv2` + `pyzbar` konteynerde YOK** — canlı denendi,
  `ModuleNotFoundError`. Görü zinciri hiç çalışamaz. Kamera gelmeden önce
  imaja eklenmeli
- `[x]` 🔴 ~~**`agent_fsm` preflight pil tuzağı**~~ → **düzeltildi (15 Ağu).**
  Eşik artık `ctx.battery_critical_voltage_v`'den geliyor, `≤ 0 → izleme yok`
  guard'ı eklendi; `agent_health_monitor:234` ve `AgentContext.healthy` ile
  üçü de tutarlı. 9/9 test geçti, 2 yeni test eklendi
  (`test_izleme_kapali_gercek_voltaj_gecis`, `test_esik_baglamdan_gelir`).
  Uçaklara dağıtıldı.
  > ⚠️ **Bunu "P0 uçuş engeli" diye sunmak yanlıştı.** Gerekçe "uçaklar
  > 3.1 V okuyor" idi ve **canlıda doğrulanmadı**. Gerçek okuma **65.535 V**
  > (MAVLink "veri yok" sentineli), yani `65.535 < 13.6` yanlış → hata hiç
  > üretilmiyordu, preflight zaten geçiyordu. **Uykuda bir tuzaktı, aktif
  > engel değildi.** 3.1 V uydurma değil (`baslat.sh:300` yorumunda d3 için
  > geçmişte ölçülmüş) ama bugünkü durum o değil.
- `[ ]` 🟡 **Sentinel 65.535 "pil harika" diye yorumlanıyor.** Eşik 13.6
  olduğunda `65.535 > 13.6` geçer — veri yokken sistem pili sağlıklı sanır.
  Pil modülü gelince (KARAR-03) sentinel açıkça "veri yok" sayılmalı
- `[x]` 🔴 ~~**`formation_node.rel_enable` iki özelliği birden kapatıyor**~~
  → **düzeltildi ve sahada doğrulandı (15 Ağustos).**

  > ⚠️ **"ADIM 3'ü kilitleyen tek madde" demiştim, yanlıştı.** Zincir gerçek
  > üreticiyle zaten çalışıyordu (`mission1_node.py:349` ofsetleri gömüyor);
  > benim test komutumda ofset yoktu ve `formation_node` onu **doğru şekilde**
  > reddetti. Gerçek sorun başkaydı — aşağıda.

  **Asıl kusur:** bayrak kapalıyken komşu konumu hiç gelmiyordu → yerel slot
  hesabı **hiç çalışmıyordu** → `formation_node` her zaman liderin atamasını
  kopyalıyordu, yani fiilen **merkezi** çalışıyordu. Şartname merkezi olanı
  "eksik puan" sayıyor.

  **Yapılanlar:** `rel_enable` artık yalnız göreli düzeltmeyi kapatıyor
  (0.28 m yakınlaşma koruması duruyor); abonelikler bayraktan bağımsız
  kuruluyor. `_peer_positions`'a **ikinci kaynak** eklendi: mesh
  `AgentStatus.pos_*` zaten ortak NED'de (`esp32_bridge` GPS'i origin'le
  çeviriyor). `NeighborInfo`'yu yalnız `kinematic_fusion` yayınlıyor ve o
  KARAR-01 gereği kapalı — yani bayrağı açmak tek başına yetmezdi.

  **Sahada doğrulandı:**
  ```
  dagitik atama: yerel hesap lider ile UYUSTU -> yerel kullaniliyor
  TAM ATAMA: a1->(+0.0,+0.0)  a3->(+0.0,+12.0)
  /gozlem/drone_1/formation/raw: vx=-2.068 vy=-1.719 vz=1.330
  ```

  **Tasarım notu — sigorta:** yerel hesap ancak liderinkiyle **uyuşursa**
  kabul ediliyor, uyuşmazsa lidere düşülüyor. Yani "dağıtık hesap + merkezi
  doğrulama". Sebebi: iki uçak komşu verisini farklı anlarda alırsa farklı
  sonuç bulabilir ve ikisi de kendini aynı slotta sanabilir → çarpışma.
  Lider mesajı artık doğruluk kaynağı değil, **doğrulama aracı**.
- `[ ]` 🟠 **`path_planner`'da yavaşlama rampası YOK** — ivmelenme var,
  yavaşlama yok. `generate_waypoints` çıktısı ölçüldü (40 m bacak, 3 m/s):
  ```
  adim  1: 0.06 m -> 0.30 m/s   ← ease-in rampasi
  adim 10: 0.60 m -> 3.00 m/s   ← 2 sn'de seyir hizi
  adim 11..71: 0.60 m -> 3.00 m/s SABIT
  adim 72: 0.10 m               ← artan, sonra ANIDEN bitiyor
  ```
  Hedef tam hızda gidip aniden duruyor. Uçak `MPC_ACC_HOR=2.0` ile durmak
  zorunda: **aşım = 3.0²/(2×2.0) = 2.25 m**, oturma 1.5 s.

  Bu, kodun kendi düzelttiği hatanın **simetriği**. Yorumda yazıyor:
  *"merkez de dron gibi yumuşak hızlansın"* — yavaşlama tarafı yapılmamış.
  Başta 0'dan tam hıza sıçrayınca uçak geride kalıyordu; sonda tam hızdan
  0'a düşünce ileri taşıyor.

  **Neden acil değil:** üç uçak da aynı anda aynı miktar taşar, aralarındaki
  mesafe korunur — çarpışma riski yok.
  **Neden yine de önemli:** `TOLERANS_M = 1.0` yani "vardı" yarıçapımız 1 m,
  aşım onun iki katı → "vardım" kararı gecikiyor. QR noktalarında hassasiyet
  gerekiyorsa sorun. Her bacak sonunda 1.5 s oturma video bütçesine ekleniyor.

  - `[ ]` 🟠 **G2'de ÖLÇ:** bacak sonunda gerçek aşım kaç metre, oturma kaç
    saniye? Kayıttan `setpoint_raw/local` ile `local_position/pose` farkı.
    Hesap 2.25 m diyor ama PX4'ün kendi frenlemesi devrede — ölçmeden
    düzeltme yazılmayacak.
  - `[ ]` 🟡 Ölçüm doğrularsa: `generate_waypoints`'e simetrik ease-out
    (~10 satır). Aynı ivme, ters yön.
- `[ ]` 🟡 Saf dağıtığa geçilsin mi (liderin ataması hiç kullanılmasın)?
  Şartname puanlaması için gerekli olup olmadığı yorum meselesi. Aşama 5
  üyelik testinde konuşulacak — şimdiki hâli hem puanı hem güvenliği veriyor.

### ✅ QoS sınıf hatası — 5 abonelik düzeltildi (15 Ağustos)

`esp32_bridge` **dört** konuyu `_MESH_QOS` yani **BEST_EFFORT** yayınlıyor:
`formation/target`, `perception/qr_data`, `control/command`,
`drone{N}/status`. RELIABLE abone + BEST_EFFORT yayıncı **eşleşmez** ve konu
**sessizce boş kalır** — düğüm mesh'ten gelen veriyi hiç almaz.

- `[x]` 🔴 `formation_node` → `formation/target` (ADIM 3'ü kilitliyordu)
- `[x]` 🔴 `collision_avoidance` → `formation/target` (ADIM 4'te patlardı)
- `[x]` 🟠 `maneuver_executor` → `formation/target` (ADIM 9)
- `[x]` 🟠 `mission1_node` → `perception/qr_data` (ADIM 7)
- `[x]` 🟠 `mission_fsm_node` → `perception/qr_data` (ADIM 6)
- `[x]` 🔴 **`gcs/backend/ros_bridge.py` → `perception/qr_data`** — YKİ
  tarafında, 15 Ağustos akşamı YKİ ilk kez açılınca çıktı. Burada özellikle
  ironikti: **kasıtlı RELIABLE yapılmıştı**, gerekçesi *"QR mesajı GCS'te en
  az 1 kez görünmeli (şartname V2, −20 ceza)"*. Niyet doğru, etki tam tersi —
  BEST_EFFORT yayıncıdan **hiçbir şey almıyordu**, yani "hiç kaçırmayalım"
  ayarı her zaman hepsini kaçırıyordu. Aynı dosyanın 40 satır altında doğru
  not zaten yazılıydı.

> **Kural:** `/swarm/public/…` dinleyen herkes **BEST_EFFORT** olmalı.
> Ters yön sorunsuz (RELIABLE yayıncı + BEST_EFFORT abone uyumlu), o yüzden
> `ic_dis_kopru` RELIABLE yayınlamaya devam ediyor.
>
> Bulunuş yolu: `formation_node` açılınca ROS'un kendi uyarısı çıktı, sonra
> **bütün** public abonelikleri ve `esp32_bridge` yayıncıları tarandı.
> Adım adım gidilseydi beşi ayrı ayrı, sahada aranacaktı.

### ✅ `baslat.sh` toplu anahtarları ayrıldı (15 Ağustos)

- `[x]` 🔴 `formasyon` anahtarı `collision_avoidance`'ı **da** açıyordu —
  `basit_kacinma` ile aynı topic yuvası, yani ADIM 3'ü açarken
  `CLAUDE.md` §4 çakışması kendi elimizle kurulacaktı. Ayrı anahtar `ca`,
  üstelik `/ws/kacinma` varken **açmayı reddediyor** ve uyarı basıyor.
- `[x]` 🟡 `fsm` anahtarı üç düğümü birden açıyordu (ADIM 2/6/12) →
  `fsm` / `gorevfsm` / `mod`

### ✅ Gözlem modu kuruldu (15 Ağustos) — `SURU_ENTEGRASYON.md` §4

- `[x]` 🟡 `/ws/gozlem` bayrağı: `formation_node` setpoint'i
  `/gozlem/drone_N/formation/raw`'a gider, **uçağa ulaşmaz**
- `[x]` 🟡 Kayıt include regex'ine `/gozlem/` eklendi — önceden yalnız
  `^(/drone_N/|/swarm/)` kaydediliyordu, yani gözlem çıktısı **hiçbir yere
  yazılmıyordu** ve gözlemin anlamı kalmazdı
- İlk kullanımda değerini kanıtladı: `formation_node` yerdeki uçak için
  `vz = 1.51 m/s` üretti. Gözlem modu olmasaydı bu tırmanma komutuydu.
- `[x]` 🔴 ~~**`consensus.battery_min_v = 14.0`**~~ → **düzeltildi (15 Ağu).**
  `baslat.sh` artık `battery_min_v`'i **`BATARYA_KRITIK_V`'den** geçiyor —
  `agent_fsm` ile aynı değişken. Pil ölçer modül gelince (KARAR-03) tek
  değeri 13.6 yapmak ikisini birden açacak.
- `[!]` 🔴 **`consensus.agent_count` 3 KALMALI — önceki not yanlıştı.**
  `agent_count` "kaç uçak uçuyor" değil, **"ajan kimlikleri 1..N"** demek:
  `consensus_node.py:133` → `for aid in range(1, agent_count+1)` ile
  `drone1..droneN` status konularına abone oluyor. Uçaklarımız **1 ve 3**
  (ylp01 yerde ama kimliği 2), yani `2` yazılsaydı **drone3 hiç
  dinlenmezdi**. Eksik kadro seçimi engellemiyor: `election.py:101` tam
  kadro yoksa `bootstrap_grace_s` (1.5 sn) sonrası yine seçim yapıyor.
  `SURU_AJAN_SAYISI` env'i eklendi, varsayılan 3.
- `[x]` 🔴 ~~**`swarm_fsm.agent_count`**~~ → **ikiye ayrıldı (15 Ağu).**
  Tek parametre iki işi yapıyordu ve **çelişiyorlardı**: abonelik kimlik
  aralığı (`range(1, N+1)` → **3 olmalı**, yoksa drone3 hiç dinlenmez) ve
  filo büyüklüğü (**2 olmalı**). Tek değerken `formation_reached` için
  `2 >= 3` false (FORMING'de kalıcı takılma) **ve** sağlık oranı
  `1/3 = 0.33 < 0.5` (bir uçak bozulunca tüm sürüye acil iniş).
  Artık `agent_count` + `expected_agent_count`; `baslat.sh`
  `SURU_AJAN_SAYISI` / `SURU_BEKLENEN_UCAK` ile geçiyor.
  **Üç uçak birden uçulunca `SURU_BEKLENEN_UCAK=3` yapılacak.**
- `[x]` 🔴 ~~**`swarm_fsm` sabit formasyon ofsetleri**~~ → **düzeltildi.**
  Not eksikti: o ofsetler zaten **hiç çalışmıyordu** (ölü kod), çünkü
  `ctx.active_formation` bu düğümde **hiçbir yerde atanmıyordu** ve
  `FormationCommand` aboneliği yoktu. Kalite metriği her ajanı merkeze göre
  ölçüyor, 12 m aralıkta hata ~6 m çıkıyor, eşikler 1.5/1.0 m — yani
  `formation_stable`/`formation_reached` **her zaman false**.
  Artık `/swarm/public/formation/target` dinleniyor; ofsetler liderin
  gömdüğü atamadan (yoksa `compute_slot_offsets`), heading kadar döndürülüp
  **ortalaması çıkarılıyor**. Sonuncusu şart: slotlar lider merkezli, sıfır
  ortalamalı değil — 12 m'de **6 m sabit yanlılık**, eşiği kıran sayı o.
  Doğrulandı: 2 uçak çizgi → `(0,-6)`/`(0,+6)`, heading=90 → `(+6,0)`/`(-6,0)`,
  ofset toplamı heading=33'te bile tam sıfır.
- `[x]` 🟠 ~~**`swarm_fsm._on_election` tek global seq sayacı**~~ →
  **düzeltildi.** `consensus_node` her yeniden başladığında `sequence_num`
  1'e döner, `1 <= max` olduğu için **bütün** seçim mesajları bayat sayılıp
  düşüyordu — `docker restart` sonrası `swarm_fsm` lider değişimlerine
  kalıcı sağır kalıyordu. Artık kaynak başına `(incarnation, seq)` ve
  consensus'un kendi `election.seq_kabul` fonksiyonu.
- `[x]` 🟡 ~~`baslat.sh` `fsm` anahtarı~~ → **ayrıldı.** Üç düğümü birden
  açıyordu (`swarm_fsm` ADIM 2, `mission_fsm` ADIM 6, `mode_manager`
  ADIM 12) ve `swarm_fsm_node`'a **hiç parametre geçmiyordu**. Artık
  `fsm` / `gorevfsm` / `mod`.
- `[ ]` 🟠 **`px4_bridge velocity_only:=True`** — `formation_node` C modu için
  tasarlanmış, varsayılan `False` → kazançlar toplanır (0.8 + 0.95)
- `[ ]` 🟠 `task_reallocator.min_active_for_formation:=2`,
  `mission1.default_spacing_m:=12.0`, `joystick_interpreter` remap

> ⚠️ **Yukarıdaki "N'i 2 yap" maddelerini uygulamadan önce KODU OKU.**
> `consensus.agent_count` için "2 yapılmalı" yazıyordu ve **yanlıştı** —
> uygulansaydı ylp02 sürüden tamamen düşerdi. Aynı şüphe
> `swarm_fsm.agent_count` ve `task_reallocator.min_active_for_formation`
> için de geçerli: her birinin o sayıyı **ne anlamda** kullandığı
> (kimlik aralığı mı, canlı sayı mı, çoğunluk eşiği mi) sırası gelince
> tek tek doğrulanacak.

### P0.6 Sürü entegrasyonunun yapısal engelleri

Tam analiz: `SURU_ENTEGRASYON.md` §2 ve §3.

- `[x]` ✅ **Çarpışma önleme seçimi KARARA BAĞLANDI** → `KARARLAR.md` KARAR-01
  (Seçenek C: `collision_avoidance` + ham `AgentStatus`, `d0=8 m` ile başla).
  Uygulama Aşama 1B'de.
- `[x]` 🔴 ~~**internal/public köprüsü eksik**~~ → **kalıcı çözüldü (15 Ağu).**
  Yeni düğüm: `swarm_control/ic_dis_kopru.py`, **12 konu** taşıyor.
  Sözleşme gereği düğümler kendi çıktısını `internal`'a yazıp
  başkalarınınkini `public`'ten okuyor; simülasyonda bu köprüyü
  `network_proxy` kuruyordu ve **iki** işi yapıyordu (yerel döngü +
  ajanlar arası). Sahada `esp32_bridge` yalnız ikincisini yapıyordu.
  Ölçülen sonuçlar: `swarm_fsm` kendi consensus'unun seçimini hiç
  görmüyordu · `agent_fsm` origin'i göremiyordu (ADIM 1'de geçici remap
  ile aşılmıştı, o remap artık **kaldırıldı**) · `swarm_fsm`'in
  `SwarmState` çıktısı kimseye ulaşmıyordu.
  Doğrulandı: `kopru gecen: events/system=60 origin=59` (60 sn),
  `/swarm/public/state` yayıncı sayısı 0 → 1.
  ⚠️ `drone{N}/status` **bilerek taşınmıyor** — uçak kendini komşu sanıp
  kendinden kaçmaya çalışırdı.
- `[ ]` 🟡 **`px4_bridge` öncelik hakemliği** — `priority` alanı var ama
  kullanılmıyor. **Aciliyeti düştü:** kod okununca görüldü ki çakışma zaten
  **susturma** ile çözülmüş (`formation_node` MANEUVER adımında ve
  DETACHED/PRECISION_LANDING durumlarında susuyor; `precision_landing` yalnız
  kendi durumunda yazıyor). Hakemlik yine de güvenlik ağı olarak değerli —
  bir kapı kaçarsa sessiz çakışma yerine belirli davranış.

---

## 🟠 P1 — ACİL

### ✅ P1.1 — TAMAMLANDI (15 Ağustos)

`iPhone` hotspot'u iki uçağa da eklendi, güç tasarrufu kapalı,
`rpissid` öncelikli (10) kalacak şekilde. Ayrıntı: `RPI_ESITLEME.md` §7.

- `[x]` 🟠 iPhone hotspot eklendi (ylp00 + ylp02)
- `[ ]` 🟠 **SSID doğrulanmadı** — telefon kapalıydı. Açıldığında bir kez
  bağlanıp teyit et; farklıysa `nmcli connection modify iphone-hotspot
  wifi.ssid "..."`
- `[ ]` 🟠 ylp01 döndüğünde aynısını uygula

### P1.2 SSH anahtarları

Parola girişi **açık** (doğrulandı), kullanıcı adları `yelpence00/01/02`,
parola takım içinde paylaşılıyor (**repoya yazılmadı, yazılmayacak**).
Yani her üye kendi anahtarını **kendisi** kurabilir, Eyüp'ün orada olması
gerekmiyor.

- `[ ]` 🟠 Her üye kendi bilgisayarında bir kez:
  ```bash
  ssh-keygen -t ed25519
  ssh-copy-id yelpence00@<ip>    # üç drone için de
  ```
- `[ ]` 🟡 Anahtarlar dağıtıldıktan sonra parola girişini kapatmayı düşün
  (ama sahada kilitli kalma riskine karşı acil çıkış olarak bırakmak da savunulabilir)

### ✅ P1.3 — TAMAMLANDI (15 Ağustos)

Her şey `feature/dagitik-suru` dalında commit'li ve push'lu.

### P1.5 Konteyner ağdan önce kalkıyor → QGC bağlantısı ölü kalıyor

**15 Ağustos'ta yaşandı ve teşhisi ~yarım saat aldı.** ylp02 sahaya
götürüldü, WiFi koptu, atölyeye dönünce bağlanmadı, Pi tuşla yeniden
başlatıldı. Ağa girdi ama **QGC'de görünmedi**. Konteyner `docker restart`
edilince düzeldi.

Sebep: konteyner `--restart unless-stopped` ile Pi açılır açılmaz kalkıyor,
WiFi henüz hazır değilken MAVROS'un `gcs_url` UDP ucu düzgün kurulamıyor.
Logdaki izi: `link[1000] removed stale remote address ...`.

Ölçülenler — **hiçbiri suçlu değildi**, hepsi sağlıklı çıktı:
seri çerçeveleme @921600 (67 ardışık geçerli çerçeve) · FCU `sysid=3
compid=1` · sıcaklık 54.3 °C, throttle `0x0` · UDP tekil **ve** yayın.

- `[ ]` 🟠 `baslat.sh`, `gcs_url` ile mavros'u başlatmadan önce ağın hazır
  olmasını beklesin (wlan0'da IP var mı / ağ geçidine ping, en fazla ~30 sn).
  **Ağ yoksa yine devam etsin** — mesh ve uçuş WiFi'ye bağlı değil, yalnız
  QGC bağlı. ~10 satır
- `[ ]` 🟡 `drone_bul.sh --durum`'a "QGC akışı canlı mı" satırı ekle, bu
  belirti tek komutla görünsün

> 💡 **Teşhis notu — iki kez düştüğüm tuzak:**
> 1. `ros2 topic echo/hz` **QoS eşleşmesi** ister. BEST_EFFORT yayıncıya
>    varsayılan RELIABLE ile bakınca "yayınlanmıyor" der. `topic info -v`
>    QoS'tan bağımsız, önce ona bak.
> 2. Konteyner içinde `source /opt/ros/jazzy/setup.bash` **yetmez**;
>    `/ws/install/setup.bash` de gerekiyor, yoksa
>    `swarm_interfaces/msg/... is invalid` der ve boş sanırsın.

### P1.4 Pi saati — sahada doğrulanmadı

Pi 5'in RTC'sinde yedek pil yok; açılışta saat ~11 saat geriden geliyor
(ölçüldü). `gps_saat.py` PX4'ün GPS zamanından düzeltiyor, internet
gerekmiyor. Ayrıntı `cihazlar.md` ⏰ bölümü.

- `[ ]` 🟠 **İlk saha çıkışında doğrula:** internetsiz açılışta
  `gunluk/son/gps_saat.log` ne diyor — saat düzeldi mi, fark kaçtı
- `[ ]` 🟡 İki uçağın saatini uçuştan önce karşılaştırmayı alışkanlık yap
  (`drone_bul.sh --durum`'a eklenebilir)
- `[ ]` ⚪ Kalıcı donanım çözümü: Pi 5 RTC konnektörüne düğme pil.
  Operatör "pil bağlayamam" dedi (15 Ağu) — GPS yolu bu yüzden seçildi

---

## 🟡 P2 — ÖNEMLİ

### P2.1 Log patlamasının kök nedeni duruyor

Günlük bekçisi eklendi ve disk açıldı, ama bekçi **belirtiyi** kesiyor.
WiFi düşünce MAVROS `gcs_url` uçnoktasına her MAVLink mesajı için
`Network is unreachable` basmaya devam edecek.

- `[ ]` 🟡 QGC kullanılmadığında `gcs_url` dosyasını kaldır, ya da mavconn
  stderr'ini ayrı dosyaya ayır
- `[ ]` 🟡 Konteyner yeniden başlatılınca bekçinin çalıştığını doğrula
  (`gunluk/son/bekci.log`)
- `[ ]` 🟡 `izleme_kur.sh`'teki disk bekçisi bunu neden yakalamadı?

### P2.2 ylp01 onarımı

- `[ ]` 🟡 Güç modülü çıkışı → PDB → ESC güç lehimleri
- `[ ]` 🟡 ESC sinyal kablo demeti
- `[ ]` 🟡 RPi neden açılmıyor (SD kart sağlam)
- `[ ]` 🟡 Onarım sonrası **`RPI_ESITLEME.md`'yi baştan sona yürüt** —
  düştüğünde üzerinde eski `esp32_bridge_node.py` ve `basit_kacinma_node.py`
  vardı, kalkışta devrilmeye yol açan düzeltme yoktu. **Kod senkronu ilk iş.**

Üç uçak olmadan n=3 okbaşı geometrisi ve rol dağıtımı denenemez.

### P2.3 Sürü entegrasyonu — Faz 0

Tamamı `SURU_ENTEGRASYON.md`'de. Uçuşsuz hazırlık:

- `[x]` 🟡 ~~Kayıt filtresine `/gozlem/` ekle~~ → yapıldı (yukarıda)
- `[x]` 🟡 ~~`SURU_DUGUMLERI` dosyadan okunsun~~ → **yapıldı (15 Ağu).**
  `/ws/suru_dugumleri` varsa env'i ezer; yorum satırı ve çok satır destekli,
  6 senaryoda test edildi. Düğüm açmak artık:
  `echo consensus > ~/yelpence_ws/suru_dugumleri && docker restart drone1`
  — yeniden **yaratma** değil, **restart**; mavros/RTK korunuyor
- `[x]` 🟡 ~~`dagit.sh` eski subnet'i tarıyordu~~ → **düzeltildi (15 Ağu).**
  IP tablosu iki yerdeydi (`dagit.sh` 10.158.16.x, gerçek ağ 10.188.209.x);
  artık `drone_bul.sh --ip`'ye delege ediyor, kendi taraması kaldırıldı
- `[B]` 🟡 Faz 1 (`kinematic_fusion`) — Faz 0'a bağlı

### P2.4 Güvenlik ve dayanıklılık

- `[ ]` 🟡 **ESC telemetrisini aç** — 2 Ağustos kazasının sebebini doğrudan
  cevaplardı. Kayıt filtresi `esc_status/*` ve `esc_telemetry/*`'yi zaten
  bilerek tutuyor, veri akınca otomatik kaydedilir.
- `[ ]` 🟡 Kill switch kontrolünü ön kontrole taşı — şu an operatör bunu
  ancak arm denemesinde görüyor
- `[ ]` 🟡 **Pil failsafe'i** — LiPo pil ölçer modül alınınca. Karar ve
  5 adımlı uygulama listesi: `KARARLAR.md` **KARAR-03**

### P2.5 Belge borcu

- `[ ]` 🟡 Drone'lardaki **21 betiği** repoya al ya da sil
  (`COP_TEMIZLIK.md` §D). Sahada yazılmış teşhis araçları — versiyonsuz,
  kaybolabilir, kimse ne olduklarını bilmiyor.
- `[x]` 🟡 ~~`README.md` sim kurulumu anlatıyor~~ → giriş noktası olarak yeniden yazıldı
- `[x]` 🟡 ~~`ARCHITECTURE.md` yanıltıcı~~ → başına uyarı kondu

---

## ⚪ P3 — İLERİDE

- `[ ]` ⚪ Kalkış öncesi **otomatik ön kontrol listesi** — pil, RTK, kill,
  parametre eşitliği tek komutta. Parçaları var (`on_ucus_kontrol.py`,
  `param_karsilastir.py`), birleştirilmedi.
- `[ ]` ⚪ Uçuş kaydı çözümleme aracı (rosbag2 → grafik). Her kazadan sonra
  elle sorgu yazılıyor.
- `[?]` ⚪ `sim/` klasörü ve `scripts/` sim betikleri — sil mi, arşiv dalına mı
  (`COP_TEMIZLIK.md` §B). **Karar operatörün.**
- `[ ]` ⚪ `src/gcs/qgc_proxy.py` sil — `cihazlar.md` "KULLANILMIYOR" diyor
- `[ ]` ⚪ Kök dizindeki 4 görsel ve 2 PDF'i yerleştir (`ss/` ve `docs/sartname/`)
- `[ ]` ⚪ `.surum` dosyasını güvenilir yap — `dagit.sh` senkron sonrası yazmıyor,
  bu yüzden senkron kontrolü md5 gerektiriyor

---

## ✅ Yakında bitenler

- `[x]` 🔴 **Disk %100 doluydu** → temizlendi + günlük bekçisi
  (100 MB tavan, son 25 MB korunur). ylp00 19 GB boş, ylp02 21 GB boş.
- `[x]` 🟠 **Drone bulma** → `deploy/yki/drone_bul.sh` (mDNS + MAC taraması)
- `[x]` 🔴 **PX4 parametresi okunamıyor** → `src/gcs/px4_param.py` +
  `deploy/yki/param_karsilastir.py`. Sorun `param/get` servisinin var
  olmamasıydı; doğrusu yerel `ros2 param get`, ama tek tek çağırınca zaman
  aşımına düşüyor — araç toplu `get_parameters` kullanıyor.
