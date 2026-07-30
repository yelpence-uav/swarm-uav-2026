# Mesh Protokolü — Sürü Kodlarının Entegrasyonu İçin Kararlar

**Tarih:** 30 Temmuz 2026
**Durum:** 12 karar alındı, 6 açık madde kapatıldı, **kod YAZILMADI**.
Bu belge yazılacak kodun sözleşmesidir. Kod yazmaya engel kalmadı — sıra
§7.5'teki bağımlılık sırasına göre ilerlemek.
**Bağlam:** Sürü düğümleri (formasyon, çarpışma önleme, navigasyon, görev) repoda
duruyor ama sahada birbirine bağlı değil. Simülasyonda `network_proxy` bütün
topic'leri olduğu gibi taşıdığı için sorun görünmüyor; sahada mesh yükü 16 bayt
ve bu, hangi verinin gerçekten geçmesi gerektiğini sormaya zorluyor.

---

## 0. Bu belge neden var

Firmware (C++) ile `packet_parser.py` **birebir aynı** olmak zorunda. Kodda bunu
zorlayan `static_assert`'ler var ama bunlar yalnız boyutu tutar, anlamı tutmaz.
Protokolü sonradan değiştirmek iki tarafı birden değiştirmek demek. Bu yüzden
kod yazmadan önce sözleşme burada yazılıyor.

İkinci sebep: aşağıdaki kararların çoğu **ölçümle** alındı ve ölçüm yöntemi de
kayda geçiyor. Altı ay sonra "neden böyle" diye soran biri (biz dahil) hem kararı
hem gerekçesini hem de nasıl doğrulandığını burada bulsun.

---

## 1. Ölçülen sert kısıtlar

Bunlar tercih değil, verili durum.

### 1.1 Paket zarfı

    // firmware/esp32_mesh/common/mesh_shared/mesh_config.h:296
    struct mesh_paket_t {          // 25 bayt toplam
        uint16_t sihir;            // yabanci paket filtresi
        uint8_t  tip;              // TIP_*
        uint16_t paket_id;         // duplikat tespiti
        uint8_t  veri[18];         // YUK
        uint16_t crc;              // CRC16-CCITT-FALSE
    };

UART çerçevesi (RPi ↔ ESP) ayrı: `[tip 1B][iha_id 1B][payload 16B][crc16 2B]` = 20 B.

**Kullanılabilir yük 16 bayttır.** `TIP_POSE` tek istisna, 18 bayt kullanıyor.
Diğer 11 tipin hepsi 16. `struct.calcsize` ile doğrulandı.

### 1.2 Birim kuralları (mevcut koddan)

| büyüklük | kodlama | aralık/çözünürlük |
|---|---|---|
| konum (NED) | `int16` desimetre | ±3276.7 m / 0.1 m |
| açı | `int16` desi-derece | 0.1° |
| lat/lon | `int32` × 1e7 | ~1 cm |
| voltaj | `uint8` × 10 | 0–25.5 V |
| HDOP | `uint8` × 10 | — |

Kaynak: `goto_veri_t` (mesh_config.h:918), `_ORIGIN_FMT`, `_DURUM_FMT`.
**Yeni paketler bu kurallara uyacak** — ayrı bir kodlama icat etmiyoruz.

### 1.3 Tasarım ilkesi (kodda yazılı)

    // mesh_config.h:915 — goto_veri_t üzerine
    // Bir KEZ gonderilir — PX4'un istedigi 50Hz OFFBOARD akisi drone'da LOKAL
    // uretilir (mesh'e cikmaz), bu yuzden mesh yuku ihmal edilebilir.

Aşağıdaki kararların çoğu bu ilkenin uygulanmasıdır: **mesh tarifi taşır,
akışı uç üretir.**

### 1.4 Hız sınırlayıcı ve tip tablosu

`mesh_tip_gecebilir(tip, simdi, min_aralik_ms)` — tip başına ayrı zaman damgası,
düşen çerçeve tip bazında sayılıyor (`_tip_dusen[]`). `MESH_TIP_TABLO_BOYU = 24`,
en büyük mevcut tip `TIP_GOTO = 0x10`. **Yeni tipler 0x11–0x14 aralığında;
tablo büyütmeye gerek yok** (0x14 = 20 < 24).

### 1.5 Parçalama

Değişken uzunluklu zarf **yalnız `TIP_RTK`'de** var (`rtk_pure.h`):
`RTK_ENV_MAKS_TOPLAM = 250`, 8 parça × 238 B = 1904 B kapasite. Mekanizma
geneldir, başka tipe bağlanabilir; ama şu an RTK'ye kilitli.

### 1.6 Mevcut mesh yükü (ölçüm)

| trafik | hesap | yük |
|---|---|---|
| POSE (3 drone × ~10 Hz) | 30 × 25 B | **750 B/s** |
| DURUM (3 drone × 2 Hz) | 6 × 25 B | 150 B/s |
| RTCM (1 Hz'de) | — | ~440 B/s |

Mesh gecikmesi ölçüldü (29 Tem): iki peer için **67 ms** ve **42 ms**.
Drone tarafı UART 460800 baud = 46 kB/s. Base UART'ın YKİ→base yönündeki
~35 çerçeve/sn sınırı (§3, 28-29-temmuz.md) **drone-drone trafiğini
etkilemez** — o yol base UART'a girmiyor.

### 1.7 Zarfı büyütme seçeneği — ERTELENDİ, analizi hazır

Soru soruldu (30 Tem): *"ESP kodlarında gönderilen paketlerde artış yapmak daha
sağlıklıysa ve müsaademiz varsa, zamanı gelince konuşalım."* Cevap ve maliyet
zinciri burada duruyor ki o gün sıfırdan araştırma gerekmesin.

**Telsizde yer var.** `static_assert(sizeof(mesh_paket_t) <= 250)` — şu an 25
bayt. ESP-NOW tavanı 250, yani **225 bayt boş**. Yani soru "yer var mı" değil,
"maliyeti ne".

**Bağlayıcı kısıt telsiz değil, TX DRONE'un UART tamponu:**

    uart_frame_parser.h:36   #define UART_FRAME_BUF_SIZE 32      (varsayilan)
    RX BASE/platformio.ini   -D UART_FRAME_BUF_SIZE=1100          (ezilmis)
    TX DRONE                 ezilmemis -> 32 bayt

UART çerçevesi `[tip][iha_id][payload][crc16]` = payload + 4, artı COBS payı.
Payload 18 → çerçeve ~23 bayt → **TX DRONE'da ~9 bayt pay var**. Yani payload
**27 bayta kadar bedava** büyür. Ötesinde TX DRONE'un `platformio.ini`'sine de
`-D UART_FRAME_BUF_SIZE=...` girmek şart — **girilmezse §1.2 kusurunun
aynısı olur**: her çerçeve sessizce taşma dalına düşer, hiçbir sayaç artmaz.

**`veri[18]` beş yerde sabit** — hepsi birlikte değişmeli:

| yer | ne |
|---|---|
| `mesh_config.h:300` | struct alanı |
| `mesh_config.h` `mesh_gonder()` | `memcpy(tam_veri+6, veri, 18)` — **sabit uzunluk okuma** |
| `RX BASE/src/main.cpp:449` | `uint8_t veri[18] = {0}` — yorumu uyarıyor: 16 olsaydı 2 bayt stack over-read (UB) |
| `RX BASE/src/main.cpp:450` | `min(payload_uzunluk, 16)` — base→drone tipleri 16 |
| `TX DRONE/src/main.cpp:318` | `min(payload_uzunluk, 18)` — POSE 18 bayt olduğu için |

> Asimetri bilinçli: POSE (18 B) drone→base yönünde akıyor, base→drone tiplerinin
> hepsi 16 B. Büyütürken bu asimetri korunmalı yoksa bir yön sessizce kırpar.

**Airtime bedeli:** 25 → 40 bayt paket başına +%60. POSE 30 paket/sn'de gerçek
ama öldürücü değil; CSMA çekişmesi artar (§1.4'teki 0–10 ms bekleme).

**Şu anki ihtiyaç: YOK.** KARAR 4/5/6'daki her şey 16 bayta sığıyor. Sığmayan
iki şey var ve ikisi de periyodik değil: CUSTOM offsetleri (kalkışta bir kez,
2 paket) ve QR hata dilimi (yalnız ayrıştırma patlarsa).

**Ne zaman değer:** **periyodik** bir mesaj 16 baytı aşarsa. O gün
`veri[18] → veri[26]` neredeyse bedava (TX DRONE'un 32 baytlık tamponunun
altında kalır) ve yalnız yukarıdaki beş yeri günceller. 26'nın üstü isteniyorsa
TX DRONE `platformio.ini` de girer ve iş büyür.

---

## 2. Yöntem ve karşılaştığım kör noktalar

Alan listelerini çıkarırken üç kez yanıldım. Yöntemi ve tuzakları yazıyorum ki
tekrar edilebilir olsun ve aynı hatalara düşülmesin.

**Adım 1 — callback taraması (AST).** `create_subscription(<Tip>, <topic>,
<callback>)` çağrılarından callback adı alınıp gövdesindeki `msg.<alan>`
erişimleri toplandı.

> **Kör nokta 1:** Callback mesajın tamamını saklıyorsa (`self._x = msg`)
> gövdede `msg.<alan>` erişimi olmaz ve alan listesi **boş** çıkar.
> `maneuver_executor` tam bu yüzden listede hiç görünmedi.

**Adım 2 — saklanan nesne izleme.** `self._x = msg` kalıbı arandı, sonra
dosyada `self._x.<alan>` erişimleri toplandı.

> **Kör nokta 2:** Nesne başka bir metoda **parametre** olarak geçiyorsa
> (`self._leader_offsets(msg)`) bu da yakalanmaz.

**Adım 3 — ters tarama.** Mesajın alan adları `.msg` dosyasından okundu ve
tüketici dosyalarında `\.<alan>\b` olarak arandı. Yanlış pozitif verir (aynı
adlı başka mesaj alanı) — o yüzden her eşleşmenin **satırı** basıldı ve tek
tek okundu.

> **Yanlış pozitif örneği:** `formation_node._build_setpoint_msg` içinde
> `out.position_tolerance_m = self._position_tolerance_m` var. Alan adı geçiyor
> ama **giden** `AgentSetpoint`'e yazılıyor, gelen `FormationCommand`'dan
> okunmuyor. Satır okunmadan "gerekli" sanılırdı.

> **Kör nokta 3:** `orchestrator.py` QR alanlarını `getattr(qr, 'pitch_deg',
> 0.0)` ile **metin adıyla** okuyor. Hiçbir AST attribute taraması bunu
> görmez. Manevra açıları, irtifa komutu ve ayrılma parametreleri hep orada.
> Ayrı bir `getattr(` taraması gerekti.

**Ders:** Bir mesajın "hangi alanı gerekli" sorusu tek yöntemle cevaplanmıyor.
Dört tarama birlikte yapılmalı: callback AST → saklanan nesne → alan adı ters
tarama → `getattr` metin taraması.

---

## 3. Kararlar

### KARAR 1 — `SwarmState` mesh'ten GEÇMEZ

**Ne değişiyor:** `/swarm/public/state` mesh üzerinden taşınmayacak. Her drone
kendi `swarm_fsm_node`'unu koşturup kendi `SwarmState`'ini **yerel üretecek**.

**Neden:**

1. *Girdileri zaten geçiyor.* Tüketicilerin okuduğu alanlar ölçüldü:

   | tüketici | okuduğu alanlar |
   |---|---|
   | `mission1_node` | `leader_id`, `centroid_x/y/z`, `active_agent_ids`, `agent_pos_x/y/z`, `active_agent_count` |
   | `mode_manager_node` | `active_formation`, `centroid_x/y/z`, `formation_heading_deg`, `formation_reached`, `formation_stable` |
   | `ros_bridge` (YKİ) | `active_agent_count`, `active_formation`, `leader_id`, `mission_active`, `swarm_state` |

   Bunların tamamı mesh'in **zaten taşıdığı** `TIP_POSE` + `TIP_DURUM` +
   `TIP_ELECTION` + `TIP_LEADER_HB` akışından yerel hesaplanabilir. Sürü
   merkezi = konumların ortalaması; aktif ajan = son 3 sn'de POSE gönderen;
   lider = election sonucu.

2. *Sığmıyor.* İçinde `AgentStatus[] agents` var — drone başına 84 alanlı
   mesaj. 3 drone için yüzlerce bayt → 20+ paket, saniyede 5-10 kez. Mesh'i
   boğar.

3. *Şartname.* Tek düğümün `SwarmState` üretip diğerlerinin ona uyması merkezi
   mimaridir. Şartname 5.3: *"Dağıtık sürü algoritması kullanılması
   gerekmektedir. Merkezi sürü algoritmaları eksik puan olarak
   değerlendirilecektir."* Ayrıca o düğüm düşerse sürü kör kalır.

**Sebep olduğu değişiklik:** `swarm_fsm_node` her dronda koşacak → `baslat.sh`
güncellenecek. `esp32_bridge`'e `SwarmState` için hiçbir şey eklenmeyecek.
Mevcut `TIP_SWARM_STATE` (0x0D) olduğu gibi kalıyor — komşunun sürü görüşünü
`SystemEvent` olarak taşıyor, YKİ göstergesi için yeterli.

---

### KARAR 2 — Görev 2'de `formation/target` mesh'ten GEÇMEZ

**Ne değişiyor:** Yarı otonom görevde kumanda girdisi mesh'ten geçecek
(zaten geçiyor), formasyon hedefi geçmeyecek.

**Neden:** Pilot çubuğu ileri ittiğinde iki yol var:

- **(a)** "sürü merkezi artık 2 m kuzeyde" hesaplanıp saniyede 20 kez herkese
  gönderilir
- **(b)** çubuğun kendisi (roll/pitch/yaw/throttle) gönderilir, her drone
  "ileri çubuk = merkez kuzeye" hesabını **kendi** yapar

(b) hem daha az trafik hem **zaten kurulu**: `TIP_KOMUT` (`komut_veri_t`)
roll/pitch/yaw/throttle'ı ×100 taşıyor ve `/swarm/internal/control/command` →
`/swarm/public/control/command` yolu `esp32_bridge`'de çalışıyor.

`mode_manager_node` 20 Hz tick'liyor — bu 20 Hz mesh'e **hiç çıkmayacak**.

**Sebep olduğu değişiklik:** `mode_manager_node` her dronda koşacak →
`baslat.sh`. Mesh'e ekleme yok.

---

### KARAR 3 — Görev 1'de formasyon merkezini LİDER yayınlar (5 Hz)

**Ne değişiyor:** `path_planner_node` yalnız liderde koşar, ürettiği formasyon
hedefini mesh'e yayınlar. Takipçiler kendi `path_planner`'ını koşturmaz.

**Değerlendirilen alternatif (B):** Her drone `path_planner`'ı aynı QR
hedefiyle koşturur, mesh yükü sıfır olur.

**B neden reddedildi:** `path_planner` bir **açık çevrim yörünge üreticisi**.
Ölçülen ayarları: `control_rate_hz = 5.0`, `max_speed_mps = 3.0`,
`max_heading_slew_deg_s = 90.0`, ve kendi iç durumu (`_current_slew_rate`).
İki bağımsız örnek şu sebeplerle ayrışır:

- farklı anlarda başlarlar (mesh gecikmesi ölçüldü: 42–67 ms; düğüm başlangıç
  zamanları da farklı)
- 5 Hz zamanlayıcıları bağımsız kayar
- biri bir girdiyi geç alırsa diğerinin atmadığı bir adım atar

**RTK bunu kurtarmaz** — bu soru açıkça soruldu, cevabı hayır. RTK
*"ben neredeyim"* sorusunu 2 cm'e indirir. Ayrışma ise *"merkez şu anda nerede
olmalı"* sorusundan geliyor ve bu bir **komut üretme** problemi, ölçüm problemi
değil. 200 ms'lik zamanlama kayması × 3 m/s = **60 cm merkez farkı**, ve açık
çevrim olduğu için kendini düzeltmez, birikir. `spacing_m = 5.0` ile bu gerçek
bir formasyon hatası; şartname çarpışmama şartı koyuyor.

> Dürüst kayıt: B'yi güvenli hale getirmenin bir yolu var — merkezi yörünge
> integre etmek yerine **gerçek konumların ağırlık merkezi** olarak hesaplamak
> (kapalı çevrim, kendini düzeltir; `use_current_centroid` bunun için var).
> Ama o zaman sürünün *nereye gideceği* kararı hâlâ üretilmeli ve ayrışacak
> olan tam o karar.

**A'nın ölçülen maliyeti:** 5 Hz × 25 B = **125 B/s**. Mevcut POSE trafiği
750 B/s → **%17'si.** Drone-drone yolunda, base UART'a dokunmuyor.

**Yayın broadcast olacak, unicast değil.** RTCM'de unicast'e geçme gerekçesi
"tek parça kaybı mesajın tamamını öldürüyor"du (§2, 28-29-temmuz.md). Formasyon
periyodik: kaybolan paket 200 ms sonra kendini kapatır, tıpkı POSE gibi. Tek
iletim üç drona ulaşır.

**Lider düşerse:** Lider seçimi zaten dağıtık (`consensus_node`, `TIP_ELECTION`,
`TIP_LEADER_HB`). Yeni lider yayına başlar. Devir teslim boşluğu kabul edildi.

**Sebep olduğu değişiklik:** `path_planner_node` yalnız liderde koşacak → hangi
düğümün lider olduğu çalışma zamanında değişebildiği için `path_planner`'ın
"lider değilim, yayınlamıyorum" durumunu desteklemesi gerekir. **Bu yeni bir
davranış, kodda var mı doğrulanmadı — açık madde (bkz. §7).**

---

### KARAR 4 — `TIP_FORMASYON` paketi (yeni, 0x11)

Mesh **tarifi** taşır, offsetleri değil. Gerekçe:

`_compute_local_offsets` iki parçadan oluşuyor ve ayrımı kritik:

- `compute_slot_offsets(tip, n, spacing, alpha)` → **saf fonksiyon**
  (`formation_geometry.py`, sadece `math` import ediyor, 231 satır). Konum
  girdisi yok, her dronda birebir aynı sonucu verir. Doğrulandı.
- `hungarian_assignment(cost)` → `cost` **komşu konumlarından** geliyor. İki
  drone farklı anda/farklı kestirimle hesaplarsa **farklı atama** çıkabilir →
  iki drone aynı slotu hedefler → **çarpışma.**

Kodun kendi yorumu (`formation_node.py:~340`): *"Aynıysa yereli kullan (dağıtık
→ puan); farklı/eksikse lidere düş (güvenli → çakışma yok)."*

**Sonuç: gönderilmesi gereken şey offsetler değil, ATAMA.** Ve atama zaten
`agent_ids`'in **sırasında** kodlu — `_slot_offset` şöyle yapıyor:
`idx = agent_ids.index(self._agent_id)` sonra `offset_*[idx]`. Yani `agent_ids`
ile `offset_*` paralel diziler.

    TIP_FORMASYON = 0x11                                    16 bayt
    ------------------------------------------------------------------
    uint8   formasyon_tipi     1   1=OKBASI 2=V 3=CIZGI 99=CUSTOM
                                   bit7 = devam paketi var (5+ ajan)
    int16   merkez_kuzey_dm    2   NED, desimetre
    int16   merkez_dogu_dm     2
    int16   merkez_asagi_dm    2   pozitif = aşağı
    int16   heading_ddeg       2   desi-derece
    uint8   spacing_dm         1   0.1 m adım, 0–25.5 m
    uint8   maks_hiz_x10       1   0.1 m/s; 0 = alıcı yerel varsayılanı
    uint8   kanat_alfa_deg     1   1° adım; OKBASI/V için
    uint8   slot_ajan[4]       4   slot sırasına göre ajan ID; 0 = boş slot
                              ---
                              16

    TIP_FORMASYON_DEVAM = 0x12   (YALNIZ 5+ ajanda)          16 bayt
    uint8   slot_ajan[4]       4   slot 4..7
    uint8   rezerv[12]        12

**`kanat_alfa_deg` pakete bilerek konuldu.** `wing_alpha_deg = 45.0` şu anda
`formation_node` ve `mission1_node`'da **ayrı ayrı** parametre olarak tanımlı.
Varsayılanlar aynı ama zorlanmıyor; bir dronda farklı kalırsa slot geometrisi
ayrışır ve bu **sessiz** bir hata olur (uçuşta fark edilir, yerde fark
edilmez). 1 bayt bu riski kapatıyor.

**Kullanıcı kararı:** 8 ajana kadar tanımlı, 3 ile kullanılacak. 3 drone ile
devam paketi **hiç gönderilmez** → sahada bedava, protokolde ölçeklenebilir
(şartname 5.3: *"istenilen sayıda İHA'yı yönetebilme"*).

---

### KARAR 5 — `TIP_FORM_OFSET` paketi (yeni, 0x13) — yalnız CUSTOM

**`FORMATION_CUSTOM` gerekiyor.** Şartname ile doğrulandı:

Görev 1: *"İHA'lar karışık ve rastgele şekilde alanda konumlandırılacaktır"* →
*"Kalkışın ardından İHA'lar, **başlangıç formasyonunu koruyarak** belirlenen
irtifaya yükselir"* → *"Sürü, **başlangıç formasyonunu koruyarak** 1 numaralı QR
noktasına doğru ilerler."*
Görev 2: *"Sürü ajanları hakemler tarafından başlangıçta yerde istenilen
formasyonda dizilir."*

Yani başlangıç dizilişini **jüri** belirliyor. Adı yok, tarifi yok, formülden
türetilemez — `compute_slot_offsets` CUSTOM için `ValueError` atıyor.
`orchestrator.py:49`: *"FORMATION_CUSTOM — jüri dizilişi snapshot'ı (dayatılan
tip yok); formation_node sağlanan ofsetleri doğrudan kullanır."*

    TIP_FORM_OFSET = 0x13                                    16 bayt
    ------------------------------------------------------------------
    uint8   slot_bas           1   bu paketteki ilk slot indeksi
    uint8   slot_sayisi        1   1 veya 2
    int16   ofset[2][3]       12   (kuzey, doğu, aşağı) dm × 2 slot
    uint8   rezerv[2]          2

3 ajan → 2 paket (slot 0-1, slot 2). **Kalkışta bir kez** gönderilir, periyodik
değil. `TIP_FORMASYON`'daki `formasyon_tipi = 99` bu paketlerin geldiğini
haber verir.

---

### KARAR 6 — `TIP_QR_GOREV` paketi (yeni, 0x14)

`QRMissionData` 37 alan. Saha kontrol mantığının okuduğu alanlar ölçüldü
(satır referanslarıyla):

| alan | okuyan | satır |
|---|---|---|
| `qr_id` | mission_fsm, mission1 | 342, 436 / 209, 240 |
| `qr_seq` | mission_fsm, mission1, orchestrator | 351 / 213 / 600 |
| `valid`, `decoded` | mission_fsm, mission1 | 339 / 207 |
| `formation_active` | mission_transitions | 322, 339 |
| `maneuver_active` | mission_transitions | 324, 340 |
| `altitude_active` | mission_transitions | 326, 341 |
| `detach_active` | mission_transitions, precision_landing | 328, 342 / 158 |
| `complete_mission` | mission_transitions | **191, 213** |
| `next_qr` | mission_transitions, mission_fsm | 195, 213 / 395-413 |
| `wait_s` | mission_transitions, mission_fsm | 193 / 283 |
| `formation_type` | orchestrator | 887 |
| `spacing_m` | orchestrator | 889 |
| `pitch_deg`, `roll_deg`, `yaw_deg` | orchestrator | 919-921 |
| `altitude_agl_m` | orchestrator | 957 |
| `target_agent_id` | orchestrator, mission_fsm, precision_landing | 982 / 579 / 158 |
| `detach_wait_s` | orchestrator | 985 |
| `detach_color` | precision_landing | 159 |

`target_x` / `target_y` bu listede **YOK** — ilk taramada göründüler ama yanlış
pozitifti (bkz. §5). `precision_landing_node.py:196` satırı `cmd.target_x`, yani
**çıktı** nesnesi; QR mesajından okuma değil. `msg.target_x` / `qr.target_x`
saha kodunda hiçbir yerde yok. İniş hedefi kameradan geliyor
(`zone_map`, `live_zone` → `self._core.update(...)`).

    TIP_QR_GOREV = 0x14                                      16 bayt
    ------------------------------------------------------------------
    uint8   qr_id              1
    uint8   qr_seq             1   sıralama/bayatlık kapısı
    uint8   sonraki_qr         1   0 = görev bitti
    uint8   bayraklar          1   bit0 valid, bit1 decoded,
                                   bit2 formation_active, bit3 maneuver_active,
                                   bit4 altitude_active, bit5 detach_active,
                                   bit6 complete_mission, bit7 rezerv
    uint8   formasyon_tipi     1
    uint8   spacing_dm         1
    int8    pitch_deg          1   tam derece (±127)
    int8    roll_deg           1
    int8    yaw_deg            1
    uint8   irtifa_m           1   AGL metre; orchestrator bandı 5–30
    uint8   bekleme_s          1   wait_s, tam saniye
    uint8   ayrilan_ajan       1   target_agent_id
    uint8   renk_ve_bekleme    1   bit0-1 detach_color, bit2-7 detach_wait_s (0-63 s)
    uint8   rezerv[3]          3
                              ---
                              16

13 bayt kullanılıyor, **3 bayt rezerv**. `target_x`/`target_y` çıkarıldığı için
(§5 yanlış pozitif) yer rahat; QR formatı nihai hale gelince ek alan buradan
çıkar. `team_id` ve `raw_text` de dışarıda (KARAR 7, KARAR 8).

**`qr_seq` neden `uint8` yeterli — ve ne zaman yetmez.** Ölçüldü: `qr_seq`
hiçbir yerde **karşılaştırılmıyor**. `mission_fsm_node.py:351` onu
`last_accepted_qr_seq`'e yazıyor ama o değişken yalnız yazılıyor (satır 224 ve
278'de 0'a sıfırlanıyor), **hiç okunmuyor**. Gerçek tekrar-QR kapısı `qr_id`
üzerinden (satır 342-348). `qr_seq`'in tek gerçek işlevi
`orchestrator.py:600`'deki emit-once anahtarı: `(mission_state, qr_step, qr_seq)`
— yani sadece **değişmesi** yeterli, küresel monotonluk gerekmiyor. 6 QR'lık bir
görevde 256'ya yaklaşmak imkânsız.

> **UYARI — ileride tuzak olur.** `QRMissionData.msg:15` ve `:50` şunu
> **iddia ediyor**: *"mission_fsm drops out-of-order/stale QRs"*,
> *"monotonically increasing"*. **Bu davranış uygulanmamış — belge kodu
> anlatmıyor.** Biri ileride belgeye bakıp
> `if msg.qr_seq <= last_accepted_qr_seq: return` yazarsa, `uint8` sarması
> (255 → 0) her şeyi "bayat" sayıp reddeder. O gün ya alan genişletilecek ya
> sarma açıkça ele alınacak. Bu, saha günlüğü §1.3'teki
> `uart_frame_parser_t.idx` `uint8_t` sarmasının **aynı sınıfı** — orada da
> taşma kontrolü sarma sonrası hep doğru kalıyordu ve hiçbir sayaç artmıyordu.

**`spacing_dm` sınırı ve zorunlu koruma.** Ölçüldü: `formation_geometry.py:31`
yalnız `spacing > 0` doğruluyor, **üst sınır yok**. Değer QR'dan geliyor
(`qr_detector.py:163`, `frm` komutunun 3. elemanı); şartname *"ajanlar arası X
(Örn: 5m)"* diyor — X'i hakem söylüyor. Varsayılan 5.0 m.
`uint8` desimetre = 0.1 m çözünürlük, **25.5 m tavan**. Çitli yarışma alanında
3 drone için fazlasıyla yeterli **ama sessizce sarmamalı**: köprü 25.5 m üstünü
**kırpacak ve UYARI basacak** (aynı kural `maks_hiz_x10` ve merkez koordinatları
için de geçerli). Sessiz sarma bu projenin tekrar tekrar ısırıldığı hata sınıfı.

---

### KARAR 7 — `team_id` mesh'ten GEÇMEZ (ama tuzağı var)

**Ne değişiyor:** QR'ı okuyan drone takım filtresini **yerelde** uygular.
Bizim takıma ait değilse mesh'e hiç çıkarmaz.

**Neden:** QR JSON'u **bütün takımların** görevini içeriyor
(`qr_detector.py:_parse_qr_text`): `data['team']` bir slot→(paket, sonraki_qr)
tablosu, `data['mis']` ise paket listesi. Okuyan drone kendi slotunu bulur.
Mesh'e çıkan her QR zaten filtrelenmiş olur; alıcının tekrar kontrolüne gerek
kalmaz. `team_id` bir **metin** — 16 baytlık pakette en az 1 fazla paket, sıfır
faydaya.

> **TUZAK — atlanırsa sessizce her şey reddedilir.**
> `mission_fsm_node.py:336`: `elif msg.team_id != self._ctx.team_id: return`
> `mission1_node.py:205`: `if self._team_id and msg.team_id != self._team_id:`
> `team_id`'yi boş bırakırsan bu iki satır **gelen her QR'ı reddeder**. Alıcı
> köprü, `QRMissionData`'yı yayınlarken `team_id` alanını **kendi yapılandırılmış
> takım ID'siyle doldurmak zorunda.** Bu, kodda açık yorumla işaretlenecek.

---

### KARAR 8 — `raw_text` normalde GEÇMEZ, hata halinde SINIRLI geçer

**Kullanıcı isteği:** QR YKİ'de kesinlikle görünmeli, minimum kaynakla, tek
sefer gönderim yeterli.

**Çözüm — normal durumda 0 ekstra bayt.** YKİ'nin ekranda göstereceği şey
"QR ne dedi"dir ve bu bilgi `TIP_QR_GOREV`'de **zaten** geçiyor. YKİ okunabilir
metni yapısal alanlardan **yerel olarak kurar**:

    "QR3 · Okbaşı 5.0 m · pitch 10° · irtifa 15 m · sonraki QR4"

`formasyon_tipi`, `spacing_dm`, `pitch/roll/yaw_deg`, `irtifa_m`, `sonraki_qr`
hepsi pakette var. Ham metni göndermeye gerek yok.

**Hata durumunda ham dilim gerekiyor — ve bu ciddi.** Şartname diyor:

> *"Şekil 2: QR içeriği örnektir **nihai format sonrasında paylaşılacaktır**."*

Yani `qr_detector.py`'deki JSON şeması bir **tahmin**. Nihai format farklı
gelirse `json.loads` patlar, yapısal alanlar boş kalır ve sahada elinde hiçbir
şey olmaz. O anda ham metnin ilk baytlarını görmek tek teşhis yoludur
(`{"QR":` mi `{"qr":` mi gibi).

    TIP_QR_HAM = 0x15  (YALNIZ ayrıştırma hatasında, tek sefer)   16 bayt
    ------------------------------------------------------------------
    uint8   hata_kodu          1   1=JSON çözülemedi 2=şema eksik
                                   3=takım slotu yok 4=tablo bozuk
                                   5=paket listede yok 6=komut hatası
    uint8   parca_no           1   0..3
    uint8   toplam_parca       1
    char    dilim[13]         13   ham metnin UTF-8 dilimi
                              ---
                              16

En fazla 4 paket = **52 karakter**, QR başına bir kez, yalnız hata halinde.
Formatı teşhis etmeye yeter, mesh'i etkilemez.

`error_message` metni yerine `hata_kodu` (1 bayt enum) gidiyor — `qr_detector`
6 ayrı hata üretiyor, hepsi numaralandırılabilir.

**Geçmeyecek diğer alanlar:** `confidence`, `image_x/y/width/height`
(hiçbir uçuş kararı okumuyor; `image_*`'ı YKİ bile okumuyor),
`command_type` (hiçbir saha mantığı okumuyor — bayraklar kullanılıyor ve
bayraklar daha güçlü: bir QR aynı anda "formasyon değiştir VE manevra yap"
diyebilir, tek enum bunu ifade edemez), `detector_agent_id` ve `target_active`
(yalnız YKİ göstergesi).

---

### KARAR 9 — Köprü, tarifi tam mesaja GERİ AÇAR

**Bu karar, aşağı akıştaki hiçbir düğüme dokunmamayı sağlıyor.**

`esp32_bridge`, `TIP_FORMASYON`'u alınca `compute_slot_offsets()` çağırıp
`offset_x/y/z` dizilerini **doldurarak** tam `FormationCommand`'ı yayınlar.
CUSTOM ise offsetler `TIP_FORM_OFSET`'ten gelir.

**Neden bu şekilde:** `maneuver_executor_node.py:335-338` şunu yapıyor —

    idx = agent_ids.index(self._agent_id)
    if (idx >= len(msg.offset_x) or idx >= len(msg.offset_y)
            or idx >= len(msg.offset_z)):
        return                      # <-- offset yoksa SESSIZCE hiçbir şey yapmaz

Ayrıca satır 370-378'de **tüm slotların** offsetini okuyor (merkez sabit kalsın
diye z ortalamasını çıkarıyor). Yani offsetsiz `FormationCommand` yayınlarsak
`maneuver_executor` sessizce ölür.

**Bağımlılık uygun:** `swarm_control/package.xml` zaten `<depend>swarm_core</depend>`
içeriyor ve `formation_geometry.py` yalnız `math` import ediyor — ROS bağımlılığı
yok, döngüsel bağımlılık riski yok. Doğrulandı.

**Kazanç:** `formation_node`, `collision_avoidance_node`, `maneuver_executor_node`
**hiç değişmiyor.** Değişiklik köprüde yoğunlaşıyor.

---

### KARAR 10 — `mission1_dynamic_swarm` HER DRONDA koşar

**Soru neydi:** Her dronda koşarsa mesh'e ne kadar yük biner, verileri
geciktirip çarpışmaya sebep olur mu?

**Cevap: mesh maliyeti ~sıfır. Ölçümler:**

Mesh'te değişen tek şey QR verisinin dağıtım yönü:

| yerleşim | iletim sayısı |
|---|---|
| yalnız liderde | okuyan drone → lider, **unicast** = 1 iletim |
| her dronda | okuyan drone → herkes, **broadcast** = 1 iletim |

**Aynı.** Broadcast hatta daha ucuz: 2 peer'a unicast 2 iletim, broadcast 1
(ESP-NOW broadcast tek iletimde herkese ulaşır).

Şartname örnek rotası: `QR1 → QR4 → QR2 → QR3 → QR5 → QR6` = **6 QR**. Yani
bütün görev boyunca **6 paket**. Karşılaştırma: POSE 30 paket/sn × 14 dk =
**25.200 paket**. Oran **%0,024**.

**Olaylar mesh'e HİÇ çıkmıyor — ölçüldü.** Endişenin ana kaynağı "3 mission1 =
3 kat olay trafiği" olabilirdi. `esp32_bridge_node.py:289`:

    self._event_pub_internal = self.create_publisher(   # PUBLISHER
        ... '/swarm/internal/events/system' ...

Abone değil, **yayıncı**. Yerel olaylar mesh'e çıkmıyor. mission1 ne kadar olay
üretirse üretsin havada tek bayt fazla trafik olmuyor. YKİ'ye olaylar ters
yönden geliyor (`TIP_GOREV` / `TIP_QR_DATA` / `TIP_SWARM_STATE` → `SystemEvent`).

**Çarpışma zinciri korunmuş, 3 kat pay var.** `collision_avoidance_node`
parametreleri (satır 108-110):

    raw_timeout_s       = 0.5 s
    neighbor_stale_ms   = 500 ms     # 500 ms'den eski komsuyu ATIYOR
    neighbor_rx_stale_s = 0.5 s
    _n_skip_stale                    # atilani sayiyor, gorunur

Gerçek durum: POSE periyodu 100 ms + ölçülen mesh gecikmesi 42–67 ms → komşu
konumu en fazla **~170 ms** eski. Kapı 500 ms → **3 kat pay**. 6 ekstra paket
bunu oynatamaz. Ayrıca tip başına hız sınırlayıcı POSE'un açlıktan ölmesini
zaten engelliyor (mesh_config.h:528-543, bilinçli tasarım kararı).

**Korku yersiz değil ama hedefi yanlış — asıl kaldıraç RTCM:**

| kaynak | paket/sn |
|---|---|
| bütün telemetri (POSE + DURUM) | ~36 |
| formasyon yayını (KARAR 3) | +5 |
| **RTCM 10 Hz'de (29 Tem'deki hali)** | **~176** |
| RTCM 1 Hz'de (olması gereken) | ~18 |
| **mission1 yerleşim kararı** | **0,02** |

RTCM'i 1 Hz'e çekmek 158 paket/sn kazandırır, mission1 kararı 0,02 paket/sn.
**7000 kat fark.** Mesh yükü endişesi varsa iş `f9p_base_yapilandir.py`
(`CFG_RATE_MEAS = 1000`) tarafında — saha günlüğü §8 madde 6 zaten bunu
listeliyor.

**Karşılığında kazanç: SICAK YEDEK.** Lider düştüğünde yeni lider görev
durumunu (hangi QR'dayız, hangi adımdayız) **zaten biliyor** çünkü aynı QR
broadcast'ini ve aynı telemetriyi izliyordu. Yalnız liderde koşarsa yeni lider
bu durumu sıfırdan kurmak zorunda — ve durumu devretmek için protokolde
hiçbir mekanizma yok.

**Güvenlik gereği (zaten sağlanıyor):** Takipçilerin mission1'i hiçbir şeyi
tetiklemez, çünkü `path_planner_node` yalnız liderde koşuyor (KARAR 3) →
takipçide `/swarm/path_planning/target`'ın abonesi yok. mission1 `tick_hz = 5.0`
ile döner, çıktısı boşa gider, durum sıcak kalır.

**Sebep olduğu değişiklik:**
- `TIP_QR_GOREV` **broadcast** gönderilecek (unicast değil)
- `swarm_missions` paketi Pi'lere kopyalanıp derlenecek (şu an **yok**)
- `baslat.sh`'e `mission1_dynamic_swarm` eklenecek
- Pi başına bir düğüm daha: ölçülen yük 0.5–1.3 / 4 çekirdek, yer var

---

### KARAR 11 — Lider kapısı KÖPRÜDE olur, `path_planner`'da değil

**Sorun:** KARAR 3, `path_planner_node`'un yalnız liderde yayınlamasını
gerektiriyor. **Ölçüldü: böyle bir yetenek YOK.** `path_planner_node`'un tek
aboneliği var (satır 106, `/swarm/path_planning/target`) ve tek yayıncısı
(satır 113). Ne `agent_id` parametresi, ne seçim/lider aboneliği, ne
etkinleştirme kapısı. Lider çalışma zamanında değişebildiği için düğümü
"sadece liderde başlat" da çözüm değil.

**İki seçenek vardı:**

- **(A)** `path_planner`'a lider kapısı eklemek — seçim sonucuna abone olup
  lider değilse yayınlamamak
- **(B)** Her dronda koşsun, kapı **köprüde** olsun — `esp32_bridge`
  `TIP_FORMASYON`'u yalnız lider isem gönderir

**Seçilen: (B).** Gerekçeler:

1. `path_planner` saf bir planlayıcı olarak kalır; ulaşım kaygısı ulaşım
   katmanında kalır
2. Kapı **tek yerde** olur. Köprü seçim mesajlarını (`TIP_ELECTION`,
   `TIP_LEADER_HB`) zaten elden geçiriyor, lideri mandallaması küçük bir ek
3. **Sıcak yedek** — KARAR 10 ile aynı kazanç: takipçinin `path_planner`'ı
   çalışır durumda bekler, lider düşünce yeni lider gecikmeden yayına geçer
4. Takipçinin yerel çıktısı **atıl** — ölçüldü: `/swarm/internal/formation/target`
   yalnız köprü tarafından tüketiliyor, başka yerel abonesi yok. Kapı kapalıyken
   hiçbir yere gitmez. `formation_node` `public` tarafını dinliyor.

**Sebep olduğu değişiklik:** `esp32_bridge`'e "şu an lider miyim" durumu
eklenecek (gelen/giden `ElectionResult`'tan mandallanır) ve `TIP_FORMASYON` /
`TIP_FORMASYON_DEVAM` / `TIP_FORM_OFSET` gönderimi bu kapıya bağlanacak.
`path_planner_node` **değişmiyor**.

---

### KARAR 12 — RTCM 1 Hz'e dönecek: mesh yetersiz değil, TASARIM VARSAYIMI ihlal ediliyor

**Bu madde bir düzeltme.** Daha önce RTCM hızını "mesh tıkanıklığı" gerekçesiyle
düşürmeyi önerdim. **Çerçeve yanlıştı ve şu iddiam da yanlıştı:** "RTCM
10 Hz'de ~176 paket/sn ile telemetriyle hız sınırlayıcı üzerinden yarışıyor."

**Ölçüm — RTK hız sınırlayıcıyı HİÇ kullanmıyor.** `RX BASE/src/main.cpp:422-428`
bunu açıkça yazıyor:

    // TIP_RTK: asagidaki 18 baytlik mesh yolundan ONCE ayrilmali.
    // ... RTK kendi buyuk zarfini ve fragmantasyonunu kullanir (rtk_sender.h),
    // mesh_gonder() yolunu HIC kullanmaz. Hiz limiti de uygulanmaz: RTCM zaten
    // ~1Hz uretilir ve `mesh_tip_gecebilir` 50ms kapisi cok fragmentli bir
    // mesajin parcalarini birbirine dusururdu.

Yani RTK ayrı yoldan gidiyor, `mesh_tip_gecebilir` kapısına girmiyor. Tiplerin
birbirini yemesi konusundaki korumanın **dışında**. Bu, "yarışıyor" iddiamı
çürütüyor — ama aynı zamanda daha ciddi bir şeyi ortaya koyuyor.

**Mesh 10 Hz'i kaldırıyor — ölçüldü.** 29 Temmuz'da RTK Fixed elde edildi:
345 örnek, %100 Fixed, yatay std 0.2 cm. Yani **sorun bant genişliği değil.**

**Sorun şu: 10 Hz, kodun üzerine kurulduğu varsayımı ihlal ediyor.**

1. *Hız sınırı yok.* RTK bilerek kapının dışında bırakıldı, gerekçesi
   "RTCM zaten ~1Hz üretilir". 10 Hz'de RTK trafiğini sınırlayan **hiçbir şey
   kalmıyor** — ne kapı, ne sayaç.

2. *Yeniden birleştirme TEK YUVALI.* `rtk_pure.h:133`'teki yapı yalnız
   `paket_id` ile anahtarlanıyor; `RTK_FRAG_TIMEOUT_MS = 500`. Ön koşul (a)
   açıkça yazıyor: *"Yuva kaynağa göre anahtarlanmıyor."* Ve (b)/(c) bozulursa:

       // gecikmis bir kopya yeni mesajin ilerlemesini siler ve ARQ olmadigi
       // icin o RTCM bir daha gelmez; kayip timeout'a duser ve RF PARAZIT
       // GIBI GORUNUR.

   1 Hz'de mesajlar arası 1000 ms var, timeout 500 ms — rahat. 10 Hz'de 100 ms
   var. Mesaj tamamlanmadan yenisi başlarsa ikisi de ölür ve **arıza RF
   parazitine benzer**, yani yanlış yerde aranır.

3. *10 Hz sıfır fayda getiriyor.* RTCM düzeltmeleri uydu saati/yörüngesi ve
   atmosfer hatalarını anlatıyor; bunlar yavaş değişir ve **baz sabit**. Rover
   düzeltmeler arasını interpole ediyor. 10 kat veri, aynı 2 cm.

4. *1 Hz zaten TASARIM NİYETİ.* `f9p_base_yapilandir.py:212`
   `("CFG_RATE_MEAS", 1000)` yazıyor — yani 1 Hz. 10 Hz bir **regresyon**:
   29 Temmuz'da ayarların RAM-only yazıldığı ve güç kesilince kaybolduğu
   bulundu, modül flash'taki eski 10 Hz konfigine döndü.

**Sonuç:** "1 Hz'e düşür" bir optimizasyon değil, **kaybedilen konfigürasyonu
geri almak**. Doğru cümle şu: mesh 10 Hz'i taşıyor ama RTK yolu 1 Hz için
tasarlandı; 10 Hz'de sessizce mesaj kaybı riski var ve o kayıp RF sorunu gibi
görünüyor.

**Sebep olduğu değişiklik:** `f9p_base_yapilandir.py` `--gecici` **olmadan**
çalıştırılacak (kalıcı flash), survey bitince `--sabitle`. Kod değişikliği yok,
işletim adımı. Saha günlüğü §8 madde 5-6 ile aynı iş.

---

## 4. Değişecek kodların tam listesi

### Firmware (C++) — iki taraf birebir tutulacak

| dosya | ne yapılacak |
|---|---|
| `common/mesh_shared/mesh_config.h` | `TIP_FORMASYON=0x11`, `TIP_FORMASYON_DEVAM=0x12`, `TIP_FORM_OFSET=0x13`, `TIP_QR_GOREV=0x14`, `TIP_QR_HAM=0x15` sabitleri; `formasyon_veri_t`, `form_ofset_veri_t`, `qr_gorev_veri_t`, `qr_ham_veri_t` struct'ları; her biri için `static_assert(sizeof(...) == 16)` ve alan offset assert'leri (mevcut `goto_veri_t` kalıbı) |
| `RX BASE/src/main.cpp` | YKİ hattı **whitelist**'ine yeni tipler eklenecek — **§1.1 kusurunun aynısı** (`TIP_RTK` whitelist'te olmadığı için sessizce düşüyordu, hata sayacı bile artmıyordu) |
| `TX DRONE/src/main.cpp` | drone hattı whitelist'i; aynı gerekçe |
| — | `MESH_TIP_TABLO_BOYU = 24` yeterli (en büyük yeni tip 0x15 = 21). Büyütme gerekmiyor ama `static_assert` kontrol edilecek. |
| — | `uart_frame_parser.h` **değişmiyor** — tüm yeni çerçeveler 20 bayt, mevcut tampon yeter |

### Python köprü

| dosya | ne yapılacak |
|---|---|
| `esp32_bridge/packet_parser.py` | yeni `_FMT` string'leri (`struct.calcsize == 16` doğrulanacak), dataclass'lar, `*_paketle` / `*_coz` fonksiyonları; `_LIVENESS_TIPLERI`'ne eklenmeyecek (bunlar periyodik telemetri değil) |
| `esp32_bridge/esp32_bridge_node.py` | **internal→mesh:** `/swarm/internal/formation/target` (FormationCommand → TIP_FORMASYON [+DEVAM/OFSET]), `/swarm/internal/perception/qr_data` (QRMissionData → TIP_QR_GOREV [+QR_HAM]) aboneliği. **mesh→public:** dispatch dalları; `compute_slot_offsets()` ile offset **geri açma** (KARAR 9); `team_id` alanını yerel takım ID'siyle **doldurma** (KARAR 7 tuzağı); **lider kapısı** — `ElectionResult`'tan lideri mandalla, formasyon paketlerini yalnız lider isem gönder (KARAR 11); **sınır kırpma + UYARI** — `spacing_dm`, `maks_hiz_x10`, merkez koordinatları tavanı aşarsa sessizce sarmasın (KARAR 6) |
| `esp32_bridge/` yeni parametre | `takim_id` — KARAR 7'nin doldurma adımı için gerekli. Yapılandırılmadığı sürece gelen QR'lar `mission_fsm:336`'da reddedilir. |

### Düğüm yerleşimi (`baslat.sh`)

Her dronda koşacaklar: `swarm_fsm_node` (KARAR 1), `mode_manager_node` (KARAR 2),
`mission_fsm_node`, `mission1_dynamic_swarm` (KARAR 10), `consensus_node`,
`kinematic_fusion`, `formation_node`, `collision_avoidance`,
`maneuver_executor`, `task_reallocator_node`, `precision_landing_node`,
`camera_driver`, `vision_node`.

`path_planner_node` de **her dronda** koşacak (KARAR 11) — lider kapısı köprüde
olduğu için düğümün kendisi kısıtlanmıyor; takipçinin çıktısı atıl kalır ve
lider değişiminde sıcak yedek olarak hazır bekler.

**Sahada ASLA çalıştırılmayacak ikisi:** `network_proxy_node` (mesh simülatörü,
yerini `esp32_bridge` alıyor), `sim_rtcm_source` (yerini gerçek F9P alıyor).
Yanlışlıkla açılırsa `/swarm/public/*` topic'lerine ikinci bir yayıncı girer ve
teşhisi çok zor bir çift-kaynak durumu oluşur.

> **`swarm_missions` paketi Pi'lerde YOK** — ölçüldü, `~/yelpence_ws/src` altında
> `swarm_control`, `swarm_core`, `swarm_interfaces`, `swarm_perception`,
> `swarm_state_machine` var. `mission1` drone'da koşacaksa paket kopyalanıp
> derlenecek.

### Değişmeyecek olanlar (bilerek)

`formation_node.py`, `collision_avoidance_node.py`, `maneuver_executor_node.py`,
`mission_fsm_node.py`, `precision_landing_node.py` — KARAR 9 sayesinde tam
`FormationCommand`/`QRMissionData` görmeye devam edecekler.

---

## 5. Düzeltilen hatalı iddialar (kayıt için)

Analiz sırasında altı iddia kurulup sonra ölçümle çürütüldü. Kayda geçiyor ki
bu belgeye dayanan biri eski hallerine güvenmesin:

| iddia | gerçek |
|---|---|
| "esp32_bridge'e 6 akış eklenecek, tek dosyada iş" | Yanlış. 3'ü bağlama işi, 2'si protokol tasarımı, 1'i (`SwarmState`) hiç geçmemeli. |
| "`complete_mission` gerekmiyor" | Yanlış. `mission_transitions.py:191,213` okuyor — "görev bitti mi" kararını veriyor. |
| "`raw_text`, `command_type`, `confidence` kimse okumuyor" | Yanlış. YKİ okuyor (`ros_bridge.py:198-213`), gösterim için. |
| "`team_id` gerekmiyor" | Yarı yanlış. İki düğüm filtreliyor; atılabilir ama alıcı köprünün doldurması şart. |
| "`target_x`/`target_y` gerekli (precision_landing:196 okuyor)" | **Yanlış — yanlış pozitif.** Satır 196 `cmd.target_x`, yani ÇIKTI nesnesi. `msg.target_x` / `qr.target_x` saha kodunda hiç yok. İniş hedefi kameradan (`zone_map`). Pakette 4 bayt boşaldı. |
| "RTCM 10 Hz telemetriyle hız sınırlayıcı üzerinden yarışıyor (~176 paket/sn)" | **Yanlış.** RTK `mesh_tip_gecebilir`'i HİÇ kullanmıyor — `RX BASE/src/main.cpp:426` bunu açıkça yazıyor. Asıl sorun tek yuvalı reassembly (KARAR 12). |

Ayrıca §2'de yazılan üç kör nokta (saklanan nesne, parametre geçişi, `getattr`)
ilk dört hatanın kaynağıydı; beşincisi ters taramanın yanlış pozitifi,
altıncısı da kodu okumadan hızlıca kurulmuş bir çıkarım.

### Belge ile kodun uyuşmadığı iki yer (bu analizin yan ürünü)

Bunlar mesh işiyle ilgili değil ama ölçüm sırasında çıktı; **düzeltilmedi**,
çünkü davranış değişikliği olur ve ayrı bir karar gerektirir:

1. **`QRMissionData.msg:15,50`** *"mission_fsm drops out-of-order/stale qr_seq"*
   ve *"monotonically increasing"* diyor. **Uygulanmamış.** Gerçek tekrar
   kapısı `qr_id` üzerinden (`mission_fsm_node.py:342-348`);
   `last_accepted_qr_seq` yazılıyor, hiç okunmuyor.

2. **`network_proxy` ile `esp32_bridge` aynı akışları taşımıyor.** Simülasyon
   9 akış taşıyor, saha 6. Bu belgenin varlık sebebi bu fark. Simülasyonda
   geçen bir senaryonun sahada geçeceği **garanti değil** — §8'deki
   karşılaştırma adımı bu yüzden var.

---

## 6. Kullanıcı kararları (30 Temmuz)

| soru | karar |
|---|---|
| Ajan sayısı | 8'e kadar tanımlı, 3 ile kullanılacak |
| Formasyon merkezi | **A** — lider yayınlar (RTK'nın B'yi kurtarmadığı açıklandıktan sonra) |
| `FORMATION_CUSTOM` | Gerekli (şartname ile doğrulandı) |
| QR → YKİ | Kesinlikle görünecek, minimum kaynak, tek sefer |
| Global düğümler | Drone'larda koşacak, YKİ'de değil |
| `mission1` yerleşimi | Her dronda (mesh maliyeti ölçüldü: %0,024) |

---

## 7. Açık maddelerin kapanışı — 6/6 KAPANDI

Hepsi ölçümle kapatıldı. Kod yazmaya engel kalmadı.

| # | madde | sonuç |
|---|---|---|
| 1 | `mission1` nerede koşacak | **Her dronda** → KARAR 10. Mesh maliyeti %0,024 |
| 2 | `path_planner` lider kapısı var mı | **YOK** → KARAR 11, kapı köprüye kondu |
| 3 | `target_x`/`target_y` gerekli mi | **GEREKSİZ** → yanlış pozitifti (§5), pakette 4 bayt boşaldı |
| 4 | `qr_seq` genişliği | **`uint8` yeterli** → hiçbir yerde karşılaştırılmıyor; ileriye uyarı yazıldı (KARAR 6) |
| 5 | `spacing_dm` çözünürlüğü | **`uint8` dm yeterli** → 0.1 m / 25.5 m; köprü kırpıp UYARACAK |
| 6 | Hız sınırı değerleri | **Yeni sabit gerekmiyor** → mevcut `MESH_GONDERIM_MIN_MS = 50` kullanılacak |

**Madde 6'nın ayrıntısı.** Ölçülen mevcut değerler:
`MESH_GONDERIM_MIN_MS = 50` (her iki firmware, genel kapı = tip başına en fazla
20 Hz), `JOYSTICK_MIN_ARALIK_MS = 200` (yalnız `TIP_KOMUT`, 5 Hz).
`TIP_FORMASYON` 5 Hz (200 ms periyot) hedefliyor; 50 ms kapısı bunu **rahat
geçiriyor**, hiçbir çerçeve düşmez. Ayrı bir sabit tanımlamak gereksiz
karmaşıklık olur. Diğer yeni tipler (`FORM_OFSET`, `QR_GOREV`, `QR_HAM`) tek
atımlık, 50 ms fazlasıyla yeter.

> **Sınır notu:** `mode_manager` 20 Hz tick'liyor = 50 ms, yani genel kapının
> **tam sınırında**. KARAR 2 gereği onun formasyon hedefi mesh'e çıkmadığı için
> sorun yok — ama biri ileride onu mesh'e bağlamaya kalkarsa çerçeveler
> düşmeye başlar ve `_tip_dusen[]` sayacında görünür.

---

## 7.5 Etki zinciri — hangi karar neyi zorunlu kılıyor

Kararlar birbirini tetikliyor. Hiçbir halka atlanmasın diye tam zincir:

### Zincir A: formasyonu mesh'e taşımak

    KARAR 3 (lider yayınlar, 5 Hz)
      → KARAR 4 gerekli: 16 bayta sığan bir formasyon paketi tasarlanmalı
        → offsetler sığmıyor (3 ajan için 85+ bayt, ajan sayısıyla büyür)
          → tarif gönderme fikri: compute_slot_offsets() saf mı? ÖLÇÜLDÜ, saf
            → ama hungarian_assignment konum bağımlı → ATAMA gönderilmeli
              → atama zaten agent_ids SIRASINDA kodlu → ek alan gerekmiyor
        → CUSTOM formasyon tarifle anlatılamaz
          → KARAR 5 gerekli: TIP_FORM_OFSET, kalkışta bir kez
        → wing_alpha iki düğümde ayrı parametre, sessizce ayrışabilir
          → pakete kondu (1 bayt)
      → KARAR 9 gerekli: köprü tarifi TAM mesaja geri açmalı
        → çünkü maneuver_executor:335-338 offset boşsa SESSİZCE return ediyor
          → köprü compute_slot_offsets import edecek
            → bağımlılık uygun mu? ÖLÇÜLDÜ: swarm_control zaten swarm_core'a
              bağımlı, formation_geometry saf matematik → uygun
        → SONUÇ: formation_node / collision_avoidance / maneuver_executor
          HİÇ DEĞİŞMİYOR
      → KARAR 11 gerekli: "lider isem yayınla" kapısı
        → path_planner'da lider farkındalığı var mı? ÖLÇÜLDÜ: YOK
          → kapı köprüye kondu → path_planner değişmiyor
            → köprü ElectionResult'tan lideri mandallayacak (yeni durum)

### Zincir B: QR'ı mesh'e taşımak

    KARAR 10 (mission1 her dronda)
      → QR içeriği tüm dronlara gitmeli → KARAR 6 gerekli
        → hangi alanlar? DÖRT tarama gerekti (§2), üç kör nokta çıktı
          → orchestrator getattr ile okuyor → ayrı tarama şart oldu
        → team_id metin, sığmaz → KARAR 7: okuyan drone filtreler
          → TUZAK: mission_fsm:336 boş team_id'de HER QR'ı reddeder
            → köprü alanı kendi takım ID'siyle DOLDURACAK (zorunlu)
        → raw_text 300-800 bayt (JSON, tüm takımların görevi) → KARAR 8
          → YKİ metni yapısal alanlardan yerel kurar → 0 ekstra bayt
          → ama şartname "nihai format sonra paylaşılacak" diyor
            → şema tahmin → ayrıştırma patlarsa teşhis lazım
              → TIP_QR_HAM: hata kodu + 52 karakter, yalnız hatada
      → swarm_missions paketi Pi'lerde YOK (ölçüldü)
        → kopyalanıp derlenecek → baslat.sh güncellenecek

### Zincir C: SwarmState'i taşımamak

    KARAR 1 (SwarmState geçmez)
      → her drone kendi SwarmState'ini üretmeli
        → swarm_fsm_node her dronda koşacak → baslat.sh
      → mode_manager de SwarmState okuyor (KARAR 2 ile birlikte)
        → mode_manager her dronda koşacak → baslat.sh
      → esp32_bridge'e SwarmState için EKLEME YOK
        → mevcut TIP_SWARM_STATE olduğu gibi kalıyor (YKİ göstergesi)

### Zincir D: firmware/Python eşleşmesi (her yeni tip için)

    Yeni TIP tanımı
      → mesh_config.h: sabit + struct + static_assert(sizeof == 16)
      → packet_parser.py: _FMT + struct.calcsize == 16 testi
      → RX BASE whitelist  ← ATLANIRSA çerçeve SESSİZCE düşer, sayaç bile artmaz
      → TX DRONE whitelist ← aynısı (§1.1 kusurunun tekrarı olur)
      → MESH_TIP_TABLO_BOYU kontrolü (24; en büyük yeni tip 0x15 = 21 → yeterli)
      → hız limiti: MESH_GONDERIM_MIN_MS = 50 (yeni sabit yok)

### Zincir E: RTCM (kod değil, işletim)

    KARAR 12 (1 Hz'e dön)
      → f9p_base_yapilandir.py --gecici OLMADAN çalıştırılacak (flash'a yaz)
        → survey tamamlanınca --sabitle
      → gerekçe: RTK hız sınırlayıcı dışında + tek yuvalı reassembly
        → 10 Hz'de mesaj üstüne mesaj → sessiz kayıp → RF parazit gibi görünür
      → kod değişikliği YOK

### Bağımlılık sırası (hangi iş neyi bekliyor)

    1. mesh_config.h struct'ları + packet_parser _FMT'leri   (temel)
    2. firmware whitelist'leri (RX BASE + TX DRONE)          (1'i bekler)
    3. esp32_bridge abonelik/yayın + geri açma + lider kapısı (1'i bekler)
    4. baslat.sh düğüm listesi                                (3'ü bekler)
    5. swarm_missions'ı Pi'lere kur                           (4 ile birlikte)
    6. RTCM 1 Hz (bağımsız, şimdi yapılabilir)

---

## 8. Doğrulama planı (uçuşsuz)

Kod yazıldıktan sonra, pervanesiz, yerde:

1. `packet_parser` birim testleri: her yeni tip için `paketle → coz` gidiş-dönüş,
   `struct.calcsize == 16`, sınır değerler (±3276.7 m, 0 ajan, 8 ajan)
2. Firmware native testi (`test_rtk_pure` kalıbı): struct boyutları ve offset'ler
3. Tek drone: `/swarm/internal/formation/target` yayınla → base ESP log'unda
   `TIP_FORMASYON` görünüyor mu, `_tip_dusen[0x11]` artıyor mu
4. İki drone: liderden yayınla → takipçide `/swarm/public/formation/target`
   çıkıyor mu, `offset_x/y/z` **dolu** mu (KARAR 9 geri açma çalışıyor mu)
5. `maneuver_executor` sessizce dönmüyor mu — offsetler dolu olduğu için
   satır 335-338'deki `return` tetiklenmemeli
6. Simülasyon karşılaştırması: `network_proxy` ile çalışan senaryo, sahada
   `esp32_bridge` ile de aynı davranmalı

---

## 10. Uygulama günlüğü — sistem sağlıklı bütün olana kadar

Her adımda: ne değişti, nasıl doğrulandı, bu değişim neyi zorunlu kıldı, sıradaki
halka ne. **Bir adım "bitti" sayılmaz — doğrulaması yazılana kadar.**

Durum özeti:

| adım | iş | durum |
|---|---|---|
| 1a | firmware struct'ları + TIP sabitleri | **BİTTİ** ✓ |
| 1b | `packet_parser.py` format/veri sınıfı/paketleyici | **BİTTİ** ✓ |
| 1c | YKİ/kumanda formasyon seçimi — **kusur düzeltmesi** | **BİTTİ** ✓ |
| 2 | firmware geçitleri (**4 geçit**, 2 değil) | **BİTTİ** ✓ |
| 3 | `esp32_bridge_node` abonelik/yayın + geri açma + lider kapısı | **BİTTİ** ✓ |
| 4 | `baslat.sh` düğüm listesi | bekliyor |
| 5 | `swarm_missions`'ı Pi'lere kur | bekliyor |
| 6 | RTCM 1 Hz (bağımsız) | bekliyor |

### Adım 1a — firmware struct'ları (BİTTİ)

**Değişen dosya:** `firmware/esp32_mesh/common/mesh_shared/mesh_config.h`

**Ne eklendi:**
- 5 TIP sabiti: `TIP_FORMASYON` 0x11, `TIP_FORMASYON_DEVAM` 0x12,
  `TIP_FORM_OFSET` 0x13, `TIP_QR_GOREV` 0x14, `TIP_QR_HAM` 0x15
- 5 struct: `formasyon_veri_t`, `formasyon_devam_veri_t`, `form_ofset_veri_t`,
  `qr_gorev_veri_t`, `qr_ham_veri_t` — hepsi 16 bayt
- Bayrak sabitleri: `FORMASYON_BAYRAK_DEVAM`, `QR_BAYRAK_*` (7), `QR_HATA_*` (6)
- 11 `static_assert` (boyut + alan offset'leri)

**Zincirde yakalanan ve düzeltilen halka:**
`static_assert(TIP_GOTO < MESH_TIP_TABLO_BOYU)` → `static_assert(TIP_QR_HAM < ...)`.
Eski hali en büyük tipe bakmıyordu. Dokunulmasaydı yeni tipler tabloya
**sığıyor ama assert onları kontrol etmiyor** olurdu; ileride bir tip 24'ü
aşsa `mesh_tip_gecebilir()` fail-closed dalına düşüp o tipi **komple
reddederdi** ve derlemede uyarı çıkmazdı.

**Doğrulama:** Struct tanımları ve `static_assert`'ler çıkarılıp `g++ -std=c++17`
ile derlendi — **hepsi geçti**. Çalıştırılarak boyut ve offset'ler basıldı:

    formasyon_veri_t 16   formasyon_devam_veri_t 16   form_ofset_veri_t 16
    qr_gorev_veri_t  16   qr_ham_veri_t          16
    offsetler: merkez_kuzey_dm 1, spacing_dm 9, slot_ajan 12,
               ofset_dm 2, pitch_deg 6, renk_ve_bekleme 12

> Not: bu, PlatformIO ile tam firmware derlemesinin yerine geçmez. Tam derleme
> Adım 2'den sonra yapılacak (whitelist'ler de girince).

### Adım 1b — `packet_parser.py` (BİTTİ)

**Değişen dosyalar:**
`src/swarm_control/swarm_control/esp32_bridge/packet_parser.py` (+~430 satır),
`src/swarm_control/test/test_esp32_parser.py` (+13 test)

**Ne eklendi:** 5 TIP sabiti, 5 `_FMT`, 14 bayrak/hata sabiti, 4 veri sınıfı
(`FormasyonVeri`, `FormOfsetVeri`, `QrGorevVeri`, `QrHamVeri`) ve 9 fonksiyon
(`formasyon_coz/paketle`, `formasyon_devam_coz/paketle`,
`form_ofset_coz/paketle`, `qr_gorev_coz/paketle`, `qr_ham_coz/paketle`).

**Bilinçli sapma — paketleyiciler `tuple[bytes, list[str]]` döndürüyor.**
Diğer `*_paketle` fonksiyonları sınır aşımını sessizce kırpıyor ve orada bu
güvenli (`durum_paketle`'deki HDOP sentineli: kırpılan değer zaten kullanılamaz
kalitede). Burada kırpılan şey **gerçek bir hedef** — sessizce kırpmak sürüyü
yanlış yere uçurur. İstisna fırlatmak da yanlış: köprü yakalamazsa formasyon
akışı komple durur, ki daha kötü. Çözüm: kırp ama **neyi kırptığını döndür**.
Köprü loglar; liste göz ardı edilirse bu kodda görünür olur.

**Doğrulama:** 13 yeni test, toplam **40 test geçiyor**. Kapsam:
- 5 formatın hepsi `struct.calcsize == 16`
- formasyon gidiş-dönüş; **slot sırasının korunduğu** (= atama bozulmuyor)
- heading sarması: 350° → −10°, 181° → −179°
- 8 ajan → devam paketi, bit7'nin tipe **sızmadığı**
- 4'ten fazla slot + `devam_var=False` → uyarı şart
- kırpma: merkez 5000 m, spacing 30 m, hız 40 m/s → 3 uyarı, `32767`'de
  **kırpıldı, sarmadı**
- CUSTOM offsetleri gidiş-dönüş; 3 offset verilince uyarı
- QR görev: 19 alan + 7 bayrak; `renk` ve `bekleme` aynı bayttan **doğru
  ayrışıyor**
- QR kırpma: pitch 200° → 127, ayrılma bekleme 99 s → 63
- QR ham metin: 4 parçaya bölünüp birleştiriliyor, boş metin çökmüyor
- tam UART çerçevesi (CRC + COBS) üzerinden uçtan uca

**flake8:** Eklenen ~430 satırda **tek uyarı yok**. Dosyada iki uyarı var
(`I100` satır 14, `E501` satır 85) ama ikisi de `origin/main`'de de mevcut —
bu değişiklikle gelmedi, dokunulmadı.

### Adım 1c — YKİ/kumanda formasyon seçimi (BİTTİ) — KUSUR DÜZELTMESİ

**Tetikleyen soru:** *"YKİ'den formasyon seçebilmek sorun olmazsa testlerde
güzel olur; gereksiz yük katarsa koymayabiliriz."*

**Cevap: yol ZATEN VAR ve sıfır yeni yük.** Ölçüldü, uçtan uca:

    YKİ arayüz (api.ts:195 formation_change_requested, requested_formation)
      -> backend api/mission.py:138-139
      -> ros_bridge.py:434-436  (SwarmControlCommand doldurur)
      -> /swarm/internal/control/command
      -> esp32_bridge  (KOMUT_FLAG_FORMATION_CHANGE)
      -> TIP_KOMUT  (mesh; İKİ whitelist'te de ZATEN VAR)
      -> esp32_bridge  (bayrağı çözer)
      -> /swarm/public/control/command
      -> mode_manager_node:367 -> :196-199 -> _handle_formation_change():316

Yeni paket tipi gerekmiyor, yeni whitelist girdisi gerekmiyor, ek periyodik
trafik yok — tek atımlık bir komut.

**AMA yol KIRIKTI.** `TIP_KOMUT` yalnız bayrağı taşıyordu:

- `esp32_bridge` paketlerken `msg.requested_formation` ve
  `msg.requested_spacing_m`'i **hiç paketlemiyordu**
- çözerken `msg.formation_change_requested = True` yapıyor ama iki alan
  **ROS varsayılanında (0)** kalıyordu
- `mode_manager_node:369-370` bunları `ctx`'e kopyalıyor
- `_handle_formation_change` `formation_type=0` (FORMATION_UNKNOWN) ve
  `spacing_m=0.0` ile formasyon hedefi kuruyor
- `compute_slot_offsets()` `spacing > 0 olmali` diye **ValueError** atıyor

Yani "V formasyonuna geç" komutu gidiyor, sürüye "bilinmeyen formasyona,
0 aralıkla geç" olarak varıyor ve formasyon hesabı patlıyor. **Sessiz kırık.**

**Düzeltme — `komut_veri_t` rezervinden iki bayt:**

    uint8_t  target_id;         // offset 10 (zaten Python kullanıyordu)
    uint8_t  talep_formasyon;   // offset 11: requested_formation (1/2/3/99)
    uint8_t  talep_spacing_dm;  // offset 12: requested_spacing_m * 10
    uint8_t  rezerv[3];         // toplam 16 byte

`_KOMUT_FMT`: `'<BBhhhhB5x'` -> `'<BBhhhhBBB3x'` (yine 16 bayt).
`offsetof` assert'leri 10/11/12 için eklendi.

> **Yan fayda:** `target_id` offset 10'da Python tarafından zaten
> kullanılıyordu ama firmware struct'ında `rezerv[0]` olarak duruyordu.
> Belge kayması giderildi ve assert'e bağlandı.

**Firmware davranışı DEĞİŞMİYOR.** ESP `komut_veri_t`'yi hiç okumuyor; tek
referans `TX DRONE/src/main.cpp:167`'de `sizeof()` ile uzunluk doğrulaması.
Yani bu, rezervin isimlendirilmesi + sözleşmenin görünür kılınmasıdır.

**Üç katmanda savunma — sürüm uyumsuzluğu sessiz kalmasın:**

1. `komut_paketle` **imzası korundu** (`-> bytes`). 10 çağrı yeri var, kırmaya
   değmez. Ayrım ilkeli: aralık kırpma codec'in işi (sessizce), **anlamsal**
   doğrulama uygulama katmanının işi (loglayarak).
2. **Köprü, gönderirken:** `FORMATION_CHANGE` bayrağı `requested_formation=0`
   ile geldiyse **bayrağı düşürür ve UYARIR** — anlamsız talebi yaymaz.
3. **Köprü, alırken:** `KomutVeri.formasyon_talebi_gecerli` bayrak + formasyon
   birlikte kontrol eder. Bayrak set ama formasyon 0 ise gönderen **eski
   sürümdür**; talep reddedilir ve uyarı basılır.

**`mode_manager` tek satır değişti** — ve dosyanın kendi kuralına uydu:

    - ctx.requested_spacing_m = msg.requested_spacing_m
    + if msg.requested_spacing_m > 0.0:
    +     ctx.requested_spacing_m = msg.requested_spacing_m

İki satır aşağıda `if msg.max_speed_mps > 0.0:` ve
`if msg.max_yaw_rate_deg_s > 0.0:` zaten aynı kuralı uyguluyor: **0 =
belirtilmedi, üzerine yazma.** `requested_spacing_m` bu kuralın dışında
kalmıştı. Koşulsuz atama 0.0'ı `ctx`'e taşıyıp `ValueError`'a yol açıyordu.
Bu düzeltme mesh yolundan bağımsız da değer taşıyor: simülasyonda
`network_proxy` üzerinden gelen 0 da artık zarar vermez.

**Doğrulama:** 4 yeni test, **toplam 44 geçiyor**:
- formasyon + aralık mesh'ten geçiyor (V formasyonu, 7.5 m gidiş-dönüş)
- bayrak set ama formasyon 0 -> `formasyon_talebi_gecerli is False`
- yeni alanlar mevcut joystick/guided alanlarının **offsetlerini kaydırmıyor**
- 25.5 m üstü aralık **kırpılıyor, sarmıyor**

Firmware yeniden derlendi: `komut_veri_t` 16 bayt,
`target_id@10 talep_formasyon@11 talep_spacing@12`.

flake8: değiştirilen 4 dosyada **yeni uyarı yok** (mevcut 4 uyarı `origin/main`
ile birebir aynı; `mode_manager_node.py` iki durumda da sıfır uyarı).

**Yarışma notu:** Bu bir **test/geliştirme kolaylığı**, yarışma özelliği değil.
Şartname Görev 1: *"Yer Kontrol İstasyonu üzerinden görevi başlatma komutu
dışında herhangi bir müdahale yapılması yasaktır."* Görev 2:
*"Formasyon değişimleri kumanda üzerinden gerçekleştirilir."* Yani sahada
formasyon seçimi **kumandadan** olacak — aynı yol (`joystick_interpreter_node`
zaten `formation_change_requested` üretiyor). YKİ butonu arayüzde
**yarışma-dışı** olarak işaretlenmeli; `telemetry.ts`'de bunun için zaten bir
kalıp var (`connection_mode` -> "UI yarışma-dışı butonları gizler").


### Adım 2 — firmware geçitleri (BİTTİ)

**Plan "2 whitelist" diyordu. Ölçünce DÖRT geçit çıktı.** Bu, planın en
tehlikeli eksiğiydi: gönderme whitelist'lerini eklesem ve alma taraflarını
atlasam, paketler mesh'i geçip ESP'de ölürdü — ne log, ne sayaç.

| geçit | dosya:satır | ne yapar |
|---|---|---|
| TX DRONE **alma** | `TX DRONE/main.cpp:167-184` | mesh → takipçinin RPi'si |
| TX DRONE **gönderme** | `TX DRONE/main.cpp:327` | liderin RPi'si → mesh |
| RX BASE **alma** | `RX BASE/main.cpp:225-234` | mesh → YKİ |
| RX BASE **gönderme** | `RX BASE/main.cpp:463-474` | YKİ → mesh |

Dördünün de sonu aynı: `else return;` — **sessiz düşüş, sayaç yok.**

**Hangi tip hangi geçitte — ve neden:**

| tip | TX alma | TX gönderme | RX alma | RX gönderme |
|---|---|---|---|---|
| `TIP_FORMASYON` | ✅ | ✅ | ⬜ ertelendi | ⬜ çift kaynak |
| `TIP_FORMASYON_DEVAM` | ✅ | ✅ | ⬜ ertelendi | ⬜ çift kaynak |
| `TIP_FORM_OFSET` | ✅ | ✅ | ⬜ ertelendi | ⬜ çift kaynak |
| `TIP_QR_GOREV` | ✅ | ✅ | ✅ | ⬜ QR'ı drone okur |
| `TIP_QR_HAM` | ⬜ bilinçli | ✅ | ✅ | ⬜ QR'ı drone okur |

Boş kutuların hepsi **bilinçli**, gerekçeleri kodda yorum olarak duruyor:

- **`TIP_QR_HAM` takipçinin RPi'sine iletilmiyor:** ham QR metnini hiçbir uçuş
  kararı okumuyor (KARAR 8). Broadcast olduğu için takipçiler alır ama Pi'ye
  taşımak boşa UART trafiği olurdu. YKİ'ye ise **iletiliyor** — asıl amacı o.
- **Formasyon tipleri RX BASE almada yok:** base UART'ın YKİ yönü ~35 çerçeve/sn
  ile sınırlı (§3) ve formasyon 5 Hz akıyor → bütçenin %14'ü. Karşılığında YKİ
  tarafında **henüz tüketici yok**. "Önce taşı, sonra belki kullanırım" boşa
  trafik olur. Adım 3'te YKİ tarafı netleşince tekrar bakılacak.
- **Formasyon tipleri RX BASE göndermede yok:** formasyon hedefini **lider**
  üretir (KARAR 3). YKİ'nin aynı tipi yayınlaması **çift kaynak** olur — lider
  5 Hz akıtırken YKİ araya girerse hangisi kazanır belirsiz. YKİ'nin formasyon
  **talebi** zaten `TIP_KOMUT` ile gidiyor (Adım 1c) ve lider onu kendi akışına
  katıyor. Doğru katman orası.

**Lider kapısı firmware'e girmedi.** Aynı firmware her dronda koşuyor ve lider
çalışma zamanında değişiyor → whitelist tüm dronlarda izin vermeli. "Şu an lider
miyim" kapısı Pi tarafında (KARAR 11). Firmware'e lider bilgisi taşımak, lider
değişiminde iki tarafı senkron tutmayı gerektirirdi.

**Tampon kontrolü (ölçüldü, hepsi sığıyor):**

    RX BASE  uart_mesaj_t.payload[18]   <- yeni yükler 16 bayt      OK
    TX DRONE uart_gonder: >18 reddediyor, ham[24], cobs_buf[32]     OK
    TX DRONE UART_FRAME_BUF_SIZE = 32   <- cerceve 20B + COBS ~21B  OK

### Adım 2 doğrulaması — ve testin DİŞLİ olduğunun kanıtı

PlatformIO laptopta kurulu değil, tam firmware derlemesi yapılamadı. Onun
yerine iki katman doğrulama:

**1. Statik çapraz kontrol.** `main.cpp`'lerdeki her `sizeof(*_veri_t)` ve her
`TIP_*` referansı `mesh_config.h`'de tanımlı mı? (yorumlar atılarak)

    RX BASE : 11 struct, 16 TIP  -> hepsi tanimli
    TX DRONE: 16 struct, 19 TIP  -> hepsi tanimli

**2. Yeni regresyon testi: `test_mesh_tip_kapsama.py` (7 test).**
Bu kusur sınıfının özelliği çalışma zamanında hiçbir sinyal üretmemesi. Test
firmware kaynağını okuyup dört geçidi ayrı ayrı kontrol ediyor ve hem
**varlığı** hem **bilinçli yokluğu** doğruluyor — bir tipi bilerek dışarıda
bıraktıysak tabloda yazılı, biri eklerse test patlar ve gerekçeyi güncellemek
zorunda kalır. Ayrıca:
- `TIP_*` değerleri firmware ile `packet_parser` arasında birebir mi
- `MESH_TIP_TABLO_BOYU` en büyük tipi kapsıyor mu (derleyici olmadan da)

Pi'lerde `firmware/` dizini yok, o yüzden test orada **atlanıyor** (`skipif`).

**Test dişli mi — üç sabotaj denendi, üçü de yakalandı** (saha günlüğü §1.3'teki
"dişli olduğu doğrulandı" kalıbı):

| sabotaj | sonuç |
|---|---|
| TX alma'dan `TIP_FORMASYON` çıkarıldı | ✅ yakalandı, mesajda §1.1 atfı var |
| TX gönderme'den `TIP_QR_GOREV` çıkarıldı | ✅ yakalandı |
| `mesh_config.h`'de `TIP_QR_GOREV` 0x14 → 0x16 | ✅ "iki taraf AYRIŞMIŞ" |

Geri alındı, `git diff --stat` yalnız amaçlanan değişiklikleri gösteriyor.

**Toplam:** `swarm_control` paketinde **95 test geçiyor**, 20 atlanıyor
(`test_mavros_command_sender.py` — laptopta ROS yok, önceden de böyle).

### Adım 3 — sıradaki halka ve bilinen riskleri

`esp32_bridge_node`: abonelikler, yayınlar, **offset geri açma** (KARAR 9),
**lider kapısı** (KARAR 11), `team_id` doldurma (KARAR 7 tuzağı), sınır
kırpma uyarıları (KARAR 6).

Bu adımın kendine özgü riski: köprü `swarm_core.formation_control.
formation_geometry`'den `compute_slot_offsets` import edecek. Bağımlılık uygun
(ölçüldü: `swarm_control/package.xml` zaten `<depend>swarm_core</depend>`
içeriyor, `formation_geometry` yalnız `math` import ediyor) **ama** import
sırası ROS paket kurulumunda ayrışabilir — `colcon build` sırası ve
`install/` altındaki yerleşim doğrulanmalı.


### Adım 3 — köprü (BİTTİ)

**Değişen/eklenen dosyalar:**

| dosya | ne |
|---|---|
| `esp32_bridge/formasyon_montaj.py` | **YENİ** — çok parçalı montaj, saf modül |
| `esp32_bridge/esp32_bridge_node.py` | 2 abonelik, 2 yayıncı, 8 metot, 2 parametre, lider takibi, 8 teşhis sayacı |
| `test/test_formasyon_montaj.py` | **YENİ** — 22 birim testi |
| `test/test_entegrasyon_formasyon.py` | **YENİ** — uçtan uca, sanal seri portla |
| `test/conftest.py` | entegrasyon testinde gerçek ROS mesajları kullanılsın |

#### Adım 3'ün ortaya çıkardığı EN ÖNEMLİ ŞEY: liderin loopback boşluğu

Kod yazmadan önce şunu sordum: **liderin kendi `formation_node`'u formasyon
hedefini nasıl alacak?** Zincir şöyleydi:

    lider path_planner -> /swarm/internal/formation/target -> köprü -> mesh
      -> takipçilerin köprüsü -> /swarm/public/formation/target -> formation_node

Liderde son satır **hiç oluşmuyor**. İki ölçümle doğrulandı:

1. Köprü dispatch'i kendi yayınını filtreliyor:
   `if cerceve.iha_id == self._agent_id: return`
2. `deploy/rpi/baslat.sh:8` → `ROS_LOCALHOST_ONLY=1`, yani her Pi'nin ROS
   grafiği ayrı. Liderin `/swarm/public/formation/target`'ının yayıncısı yok.

**Simülasyon bu boşluğu GİZLİYOR.** `network_proxy` internal→public
aktarırken göndereni dışlamıyor ve sim'de bütün dronlar tek ROS grafiğinde —
orada liderin `formation_node`'u hedefi alıyor. Yani sim'de çalışan senaryo
sahada liderin formasyona hiç girmemesiyle sonuçlanırdı.

**Çözüm: LOOPBACK.** Lider kendi paketini codec'ten **geri geçirip** yerel
`/swarm/public/formation/target`'a yayınlıyor. İkinci bir faydası da var ve
zorunluluktan bağımsız değerli: codec `int16` desimetre / `int8` derece
kuantize ediyor. Loopback olmasa lider **tam hassasiyetli**, takipçiler
**kuantize** hedefe uçar ve aralarında sistematik kayma olurdu. Aynı yoldan
geçirince bütün sürü **birebir aynı** hedefi görüyor.

#### Montaj ayrı modülde — neden

`FormasyonMontaj` (`formasyon_montaj.py`) `swarm_interfaces`'a bağımlı DEĞİL:
girdi `packet_parser` veri sınıfları, çıktı düz bir dataclass (`TamFormasyon`).
`cobs.py` / `crc16.py` ile aynı kalıp — ROS ortamı kurmadan test edilebiliyor.
22 birim testi bu sayede mümkün oldu.

Zaman aşımı **1.0 sn** (formasyon 5 Hz = 200 ms → 5 tur pay). Daha kısası ağ
dalgalanmasında sağlam montajı düşürür; daha uzunu bayat parçayı yeni başlıkla
karıştırma riskini büyütür. Yeni başlık eski yarım montajı **bilerek düşürür**:
5 Hz akışta yarım eski turu yeni turla karıştırmak slot atamasını bozar ve iki
drone aynı slotu hedefleyebilir.

#### Lider takibi DÖRT kaynaktan

`_lider_kaydet()` şu dördünden de çağrılıyor ve gerekçesi ayrı:

| kaynak | neden gerekli |
|---|---|
| `_isle_leader_hb` (mesh) | en sık gelen lider sinyali; köprü yeniden başlarsa bir sonraki heartbeat'te öğrenir |
| `_isle_election` (mesh) | lider değişimi anı |
| `_on_election_out` (yerel) | **kritik** — bu drone lider seçildiyse kendi yayınımız mesh'ten geri gelmez (dispatch filtreler), yalnız buradan öğrenilir |
| `_on_leader_hb_out` (yerel) | yerel heartbeat'i yalnız lider yayınlar |

`_lider_id` **0 başlıyor** ve kimse lider değilken formasyon yayınlanmıyor —
iki dronun aynı anda yayınlaması riskini doğurur. Ama sessiz kalmasın diye
kapıda throttle'lı uyarı basılıyor: *"formasyon hedefi geldi ama LİDER
BİLİNMİYOR — consensus_node çalışıyor mu?"*

#### Teşhis sayaçları: "formasyon neden gelmiyor" sorusunu bölmek için

`mesh_diag` satırına 8 alan eklendi. Ayrım şeması:

    form_tx=0              -> lider yayınlamıyor (lider kapısı / path_planner)
    form_lider_degil>0     -> bu drone lider değil, NORMAL
    form_rx=0 ama form_tx>0-> mesh/whitelist sorunu
    form_yarim>0           -> çok parçalı montaj tamamlanmıyor
    form_sahipsiz>0        -> başlığı görülmemiş devam/offset parçası
    lider=N                -> kimin lider olduğu

#### Adım 3 doğrulaması

**Birim: 137 test geçiyor** (22 yeni montaj testi dahil). Kapsam: offsetlerin
`compute_slot_offsets` ile **birebir** olduğu (ayrışırsa lider ve takipçi farklı
geometri kullanır), slot sırasının korunduğu, 5+ ajan devam paketi, CUSTOM
offset bekleme, zaman aşımı, yeni başlığın eskiyi düşürmesi, kaynakların
birbirini bozmaması, sahipsiz parça sayımı, geçersiz tip/spacing/boş slot.

**Entegrasyon: `test_entegrasyon_formasyon.py` — GERÇEK bayt akışı.**
socat ile sanal pty çifti kurulup köprünün bir ucunu o, testin diğerini
tutuyor. 33 kontrol, hepsi geçti:

| senaryo | doğrulanan |
|---|---|
| A) lider kapısı | lider bilinmezken **0 bayt** çıktı, yerel yayın yok, **uyarı basıldı** |
| B) lider olunca | 22 bayt çıktı, yalnız `0x11` (devam/offset yok — 3 ajan + adlandırılmış), slot sırası `[3,1,2]` korundu, kanat açısı pakete kondu, **loopback yayınlandı, offsetler dolu, merkez kuantize** |
| C) komşudan alma | `/swarm/public/formation/target` yayınlandı, **offsetler DOLU** (KARAR 9), çizgi genişliği 8.00 m (3 ajan × 4 m — geometri doğru) |
| D) QR | `team_id` **dolduruldu**, `detector_agent_id` kaynaktan, tüm alanlar kayıpsız |
| E) sayaçlar | `lider=1 form_tx=1 form_rx=1 form_lider_degil=1 qr_rx=1` — tam isabet |

Test **varsayılan olarak atlanıyor** (`YELPENCE_ENTEGRASYON=1` gerekiyor):
socat, ROS ve süreç başlatma istiyor, birim test değil.

#### Yolda düşülen iki tuzak (kayda geçiyor)

1. **`conftest.py` ROS mesajlarını taklit ediyor.** `MagicMock` ile
   `create_publisher()` *"_TYPE_SUPPORT yok"* diye patlıyor. Entegrasyon testi
   gerçek mesaj gerektirdiği için conftest'e hedefli bir kapı kondu:
   `YELPENCE_ENTEGRASYON=1` iken taklit yapılmıyor. Birim testlerin davranışı
   değişmedi (137 test aynı).

2. **`pkill -f <desen>` kendi kabuğunu öldürüyor** — desen çağıran kabuğun
   komut satırında da geçtiği için (exit 144, iki kez yaşandı). Temizlik
   `/proc` okunup kendi PID ve ata zinciri dışlanarak yapılıyor. Ayrıca artık
   süreç bırakmak testi **sessizce bozuyor**: eski köprü aynı pty'ye yazıyor ve
   lider kapısı testi 0 yerine 44 bayt görüyor (*"multiple access on port"*).
   Temizlik artık testin ilk adımı. YKİ'nin base köprüsü (`agent_id:=10`)
   bilinçli olarak korunuyor.

### Adım 4-6 — kalanlar

    4  baslat.sh dugum listesi + takim_id/kanat_alfa parametreleri
    5  swarm_missions'i Pi'lere kur (paket Pi'lerde YOK)
    6  RTCM 1 Hz (bagimsiz, KARAR 12)
    +  UC ESP'yi YENIDEN YUKLE - yeni TIP'ler eski firmware'de else return'e
       dusuyor. Drone ESP'si icin RPi kablolari SOKULMELI (YUKLEME_PROSEDURU.md)


### Adım 1c'nin ortaya çıkardığı AÇIK İŞ — kumanda formasyon yolu YOK

Adım 1c'yi yazarken "sahada formasyon kumandadan gelecek" dedim; sonra ölçtüm ve
**o yol henüz kurulmamış.** Dört eksik, hepsi doğrulandı:

| eksik | ölçüm |
|---|---|
| `set_formation()` çağıranı yok | repoda **tek çağrı yok** (`grep`, `def` hariç) |
| aux kanalı formasyona eşlenmemiş | `aux1..aux6` yalnız `deadman_channel` için okunuyor (satır 71, 124) |
| `joystick_interpreter_node` başlatılmıyor | ne `deploy/rpi/baslat.sh`'te ne `src/gcs/yki_baslat.sh`'te |
| topic adı **mutlak** | `/mavros/manual_control/control`; dronda MAVROS `/drone_N/mavros/...` altında yayınlıyor, remap yok |

Son satır **§1.9'daki RTCM topic uyuşmazlığının aynı sınıfı**: düğüm
başlatılsa bile hiçbir şey almaz ve sebebi hiçbir günlükte görünmez.

**Şartname Görev 2:** *"Formasyon değişimleri kumanda üzerinden
gerçekleştirilir."* Yani bu yol yarışma şartı, opsiyonel değil.

**İyi haber:** protokol tarafı bitti. Kumanda yolu da aynı `TIP_KOMUT` +
`KOMUT_FLAG_FORMATION_CHANGE` + `talep_formasyon` zincirini kullanacak. Kalan
iş üç madde ve hiçbiri mesh'e dokunmuyor:

1. bir aux kanalını formasyon seçimine eşle (`deadman_channel` kalıbı hazır:
   parametreyle kanal adı verilip `_read_aux_channel` ile okunuyor)
2. `joystick_interpreter_node`'u `baslat.sh`'e ekle
3. topic'i `/drone_{AGENT_ID}/mavros/manual_control/control`'e çevir (ya da
   `--ros-args -r` ile remap et)

**Durum:** açık, Adım 3'ten sonra ele alınacak. Adım 2/3'ü bloke etmiyor.

### Mevcut formasyon değiştirme yolları — özet

Karışmasın diye tek yerde:

| yol | durum | not |
|---|---|---|
| **YKİ butonu** (`JoystickPanel`: seçici + "↻ Formasyonu Uygula") | ✅ var, Adım 1c ile **onarıldı** | test/geliştirme; şartname yarışmada YKİ müdahalesini yasaklıyor |
| **QR** (Görev 1, otonom) | protokol hazır (`TIP_QR_GOREV`), bağlanması Adım 3 | `mission1` → `path_planner` → `TIP_FORMASYON` |
| **Kumanda** (Görev 2, şartname şartı) | ❌ yok — yukarıdaki 4 eksik | protokol hazır, düğüm/topic işi kaldı |

### Sıradaki halka — Adım 2 ve neden riskli

`RX BASE/src/main.cpp` ve `TX DRONE/src/main.cpp` whitelist'leri.

**Bu, zincirin atlanması en kolay ve en sessiz halkası.** Saha günlüğü §1.1
tam olarak bu kusuru anlatıyor: `TIP_RTK` whitelist'te olmadığı için her RTCM
çerçevesi `else: tanınmayan tip sessizce atılır` dalına düşüyordu ve **hata
sayacı bile artmıyordu**. Aynısı olursa formasyon paketleri hiç gitmez ve
sebebi hiçbir günlükte görünmez.

Adım 2'de ayrıca cevaplanacak: `TIP_FORMASYON` **drone→drone** akıyor, yani
asıl yol `TX DRONE`. `RX BASE` whitelist'i YKİ→mesh yönü için; YKİ formasyon
yayınlamayacaksa base tarafına eklemek gerekmez. Karar Adım 2'de, kodu okuyarak
verilecek — şimdiden varsayılmıyor.
