# Mesh Protokolü — Sürü Kodlarının Entegrasyonu İçin Kararlar

**Tarih:** 30 Temmuz 2026
**Durum:** Kararlar alındı, kod YAZILMADI. Bu belge yazılacak kodun sözleşmesidir.
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
| `target_x`, `target_y` | precision_landing | 196 |

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

**`target_x`/`target_y` bilerek DIŞARIDA bırakıldı** — bkz. §7 açık madde 3.
`team_id` ve `raw_text` de dışarıda, gerekçeleri aşağıda.

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
| `esp32_bridge/esp32_bridge_node.py` | **internal→mesh:** `/swarm/internal/formation/target` (FormationCommand → TIP_FORMASYON [+DEVAM/OFSET]), `/swarm/internal/perception/qr_data` (QRMissionData → TIP_QR_GOREV [+QR_HAM]) aboneliği. **mesh→public:** dispatch dalları; `compute_slot_offsets()` ile offset **geri açma**; `team_id` alanını yerel takım ID'siyle **doldurma** (KARAR 7 tuzağı) |

### Düğüm yerleşimi (`baslat.sh`)

Her dronda koşacaklar (KARAR 1, 2 gereği): `swarm_fsm_node`, `mission_fsm_node`,
`mode_manager_node`, `consensus_node`, `kinematic_fusion`, `formation_node`,
`collision_avoidance`, `maneuver_executor`, `task_reallocator_node`,
`precision_landing_node`, `camera_driver`, `vision_node`.

Yalnız liderde koşacak (KARAR 3): `path_planner_node`.

Karara bağlı (bkz. §7 açık madde 1): `mission1_dynamic_swarm`.

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

Analiz sırasında dört iddia kurulup sonra ölçümle çürütüldü. Kayda geçiyor ki
bu belgeye dayanan biri eski hallerine güvenmesin:

| iddia | gerçek |
|---|---|
| "esp32_bridge'e 6 akış eklenecek, tek dosyada iş" | Yanlış. 3'ü bağlama işi, 2'si protokol tasarımı, 1'i (`SwarmState`) hiç geçmemeli. |
| "`complete_mission` gerekmiyor" | Yanlış. `mission_transitions.py:191,213` okuyor — "görev bitti mi" kararını veriyor. |
| "`raw_text`, `command_type`, `confidence` kimse okumuyor" | Yanlış. YKİ okuyor (`ros_bridge.py:198-213`), gösterim için. |
| "`team_id` gerekmiyor" | Yarı yanlış. İki düğüm filtreliyor; atılabilir ama alıcı köprünün doldurması şart. |

Ayrıca §2'de yazılan üç kör nokta (saklanan nesne, parametre geçişi, `getattr`)
bu hataların kaynağıydı.

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

## 7. Açık maddeler — kod yazmadan önce kapatılacak

1. ~~`mission1_dynamic_swarm` nerede koşacak?~~ **KAPANDI — bkz. KARAR 10.**
   Her dronda koşacak, `TIP_QR_GOREV` broadcast. Mesh maliyeti ölçüldü: %0,024.

2. **`path_planner_node` "lider değilim" durumunu destekliyor mu?** KARAR 3
   yalnız liderde koşmasını gerektiriyor ve lider çalışma zamanında değişebilir.
   Kodda böyle bir kapı var mı **doğrulanmadı**.

3. **`target_x`/`target_y` gerçekten gerekli mi?** `precision_landing_node.py:196`
   okuyor. Ama aynı düğüm `/drone_{id}/perception/landing_zone` ve
   `/swarm/perception/zone_map`'e de abone — yani kameranın kendi tespiti var.
   Şartname "hassas iniş" ve tolerans şartı koyuyor; QR'a gömülü yaklaşık
   koordinat bunu sağlamaz. **Bu ikisinin biri yedek mi, biri asıl mı —
   `precision_landing_node` okunup karar verilecek.** Gerekirse `TIP_QR_GOREV`
   rezervine 4 bayt sığıyor (3 rezerv + 1); sığmazsa ikinci paket.

4. **`qr_seq` genişliği.** Şu an `uint8` planlandı. Bir görevde 6-7 QR var,
   sarma riski yok gibi ama `mission_fsm` bayatlık kapısı olarak kullanıyor
   (`msg.qr_seq` ile eski/sıra dışı QR'ları düşürüyor). Sarma davranışı
   düşünülecek.

5. **`spacing_dm` çözünürlüğü.** `uint8` desimetre → 0.1 m adım, 0–25.5 m.
   Şartname örneği 5 m. Yeterli görünüyor ama 25.5 m üstü aralık istenirse
   yetmez.

6. **Hız sınırı değerleri.** `mesh_tip_gecebilir` her tip için `min_aralik_ms`
   istiyor. `TIP_FORMASYON` için 5 Hz hedeflendiğinden ~150 ms uygun görünüyor
   (200 ms periyoda pay bırakır). Diğer yeni tipler tek atımlık; değerleri
   belirlenecek.

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
