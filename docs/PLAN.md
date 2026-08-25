# PLAN — buradan finale

**Son güncelleme:** 25 Ağustos 2026, 22:40 — Engel 3 koda eşitlendi + TEK-ÜRETİCİ geçişi baslat.sh'e kondu (formasyon sürerken esp32→mesh_goto); ADIM 3 hazırlıkları tamam, dağıtım bekliyor

Bu belge **tüm takımın ortak resmi** ve sürü entegrasyonunun **teknik yol
haritası**. Yeni gelen biri bunu okuyup işe başlayabilir.

> 20 Ağustos'ta `SURU_ENTEGRASYON.md` ve `NAVIGASYON_KAYMA.md` buraya katılıp
> **silindi.** Üçü aynı soruyu üç ayrı yerden cevaplıyordu (nereye gidiyoruz,
> nasıl test ediyoruz, hangi düğüm ne zaman) ve gözlem modu merdiveni
> **üç kez** anlatılıyordu — biri bu belgenin kendi içinde, iki kez.

---

## 1. Tek cümlede

> Repoda finali yapacak bir sürü yazılımı **zaten var**, ama simülasyon için
> yazıldı ve sahada hiç koşmadı. İşimiz onu **kademeli ve canlı testlerle**
> gerçek uçaklara almak.

**Kısıt:** Simülasyon yok. Her adım gerçek uçakta, ölçerek, geri alınabilir.

---

## 2. Neredeyiz

**Uçuş kanıtı geçildi.** Onu geçiren şey sürü yazılımı değil; kısa sürede
yazılmış daha basit bir komut yolu:

```
YKİ (bilgisayar) → mesh → uçak: "şu noktaya git"
```

| | Durum |
|---|---|
| ylp00 (drone 1) | ✅ uçuyor |
| ylp01 (drone 2) | 🟠 zinciri TAM (25 Ağu: yeni Pi+ESP+FC, panelde) — uçuş izni için ESC hattı + kalibrasyonlar kaldı |
| ylp02 (drone 3) | ✅ uçuyor |
| RTK, mesh, kayıt, YKİ arayüzü | ✅ çalışıyor |
| Pilot + kumanda (her uçak için) | ✅ var |
| Kamera | 🟠 yakında takılacak |

---

## ⏭️ SIRADAKİ UÇUŞ — dikey kaçınmanın DÖNÜŞ davranışı (23 Ağustos akşamı)

> ✅✅ **BU UÇUŞ YAPILDI VE GEÇTİ — 25 Ağustos 02:03 (gece).** Üç
> kaçış-dönüş çevrimi: ayrım bırakma **7,2-8,3 m** (dün 4,9'du),
> içerideyken dalış YOK, dönüş 0,5 m/s, tırmanma hızı aynı. Yo-yo
> görüntüsü kapandı; `hist_m=2,5` + `tatmin` düzeltmesi sahada doğru.
> Ölçüm ayrıntısı `CA.md` §7.2. Kaçınmanın DÖNÜŞ davranışı da böylece
> kapandı — ADIM 4 tam. Sıradaki iş operatörle: ADIM 3 (formasyon) ya da
> ylp01'in uçuşa hazırlanması.

✅ **Dikey kaçınma ilk uçuşunda çalıştı** (23 Ağustos akşamı): iki tam
kaçış-dönüş çevrimi, +3,1 / +2,8 m tırmanma, yatay itme hiç açılmadı.
Tam sonuç: **`docs/CA.md` §6.5**.

### Bu uçuş hangi tek soruyu cevaplıyor?

> **Çıkış histerezisi genişletilince "yo-yo" görüntüsü kayboluyor mu?**

Dün çıkış eşiği `d0 + 0,5 = 4,5 m` idi. Komşu hâlâ 5 m'de dururken 3 m'lik
ayrım 2 sn sonra geri veriliyordu; ilk uçuşta operatör bunu yo-yo olarak
gördü (aslında iki ayrı çevrimdi — `CA.md` §6.5).

**Değişen (24 Ağustos 14:30, koda bağlandı):** `hist_m` 0,5 → **2,5**
(çıkış 6,5 m). Tek kaynak zinciri KURULDU: `ucus_ayarlari.py`
(`KACINMA_HIST_M`) → `--kabuk` env → `baslat.sh -p hist_m` → düğüm —
önceden zincir hiç yoktu, düğüm gömülü 0,5 ile koşuyordu.

⚠️ **Bu uçuşta İKİ değişiklik birlikte uçuyor — operatör kararı
(24 Ağustos):** `hist_m` + `tatmin` düzeltmesi (ayrım kuruluyken dikey
yetki bırakılmaz, `ca_core`, dün commit'lendi ama dağıtılmamıştı).
Tek-değişiklik kuralından bilinçli sapma: geniş histerezis uçağı tam
eski kodun hatalı olduğu durumda (ayrım kurulu + çatışma sürüyor, komşu
4,0-6,5 m bandında) çok daha uzun tutuyor; yalnız `hist_m` dağıtmak
ölçülmüş dalış imzasını (-1,48 m/s, gaz %12→%100) SIKLAŞTIRIRDI. İki
değişiklik logda AYRIK gözlenir: çıkış mesafesi davranışı `hist_m`'in,
içerideyken irtifa dalışları `tatmin`in ölçüsü.

### Ölçüt

| | ilk uçuş | beklenen |
|---|---|---|
| 4,5 m sınırından geçiş | 4 (iki çevrim) | **belirgin azalma** |
| ayrım bırakma | komşu 4,9 m'deyken | komşu **6,5 m** çıkınca |
| içerideyken irtifa | bir kez -1,48 m/s dalış | **dalış YOK, tutulur** |
| tırmanma / dönüş | +3,1 m / 0,5 m/s | **aynı kalmalı** |

### 🔴 Uçuş öncesi bu uçuşa özel

- **Depo uçaklardan ileride** — önce karar ver (`CA.md` §7.3)
- **İtki payı ince**: askı %72, geçişlerde %100'e doyuyor. Dikey ivmeyi
  artırma.
- ✅ Kuru testin haritası kaçış zarfını artık **ÇİZİYOR** (24 Ağu 14:50 —
  sarı kesikli daireler, iniş dış halkası, ayak izinde zarflı kutu)
- `uptime -s` (P0.17)

---

## 3. Şartname ne dayatıyor

Bunlar tercih değil, **kural**. Mimariyi bunlar belirliyor.

> *"**Dağıtık sürü algoritması** kullanılması gerekmektedir. **Merkezi sürü
> algoritmaları eksik puan** olarak değerlendirilecektir."* (§5.3)

> *"Hakemler görev sırasında herhangi bir anda **yer kontrol istasyonu
> bağlantısını kesecektir**."* (§5.1)

> *"YKİ üzerinden **görevi başlatma komutu dışında** herhangi bir müdahale
> **yasaktır**. Müdahale tespiti halinde görev **başarısız** sayılır."*

Bugünkü zincirimiz — YKİ `gorev_kanit_ucus.py` her uçağa mesh'ten `goto`
gönderiyor — **hem merkezi hem YKİ'ye bağımlı.** Hakem bağlantıyı kestiği
anda sürü durur. Uçuş kanıtını geçirdi, **finali geçiremez.**

**Sonuç: onboard sürü düğümleri opsiyonel değil, ZORUNLU.** YKİ'nin izinli
tek rolü "görevi başlat". `gorev_kanit_ucus.py` bundan sonra **test aracı** —
kuru test, çarpışma doğrulama, tek uçak ölçümü.

### Görev 1 — Dinamik Sürü Kabiliyeti

| Şart | Karşılığı |
|------|-----------|
| **En az 3 İHA** | **Yalnız FİNAL için.** Entegrasyon 2 uçakla tam yürür |
| Tek komutla eş zamanlı otonom kalkış | `mission1` + `agent_fsm` |
| Formasyonu koruyarak QR noktasına ilerleme | `formation_node` + `path_planner` |
| **En az bir İHA QR'ı görsel algılayıp çözecek** | `camera_driver` + `vision_node` |
| QR görevleri: formasyon değişimi, **pitch/roll manevrası**, irtifa değişimi, **sürüden birey ekleme/çıkarma**, bekleme | `mission_fsm` + `maneuver_executor` + `task_reallocator` |
| **Her bacakta formasyon rotasyonu** — her ajanın heading'i hedefe döner | `formation_node` |
| Ayrılan birey **kırmızı/mavi bölgeye hassas iniş** → disarm → bekle → arm → katıl | `precision_landing_node` + `vision_node` |
| Rota boyunca renkli bölgeler **kamerayla tespit edilip kaydedilmeli** | `vision_node` (ZoneMap) |
| Çarpışmama | kaçınma düğümü |
| Home'a dönüş + formasyonu bozmadan güvenli iniş | `mission1` |

### Görev 2 — Yarı Otonom Sürü Kontrolü

| Şart | Karşılığı |
|------|-----------|
| **Tek kumandayla tüm sürü** | `joystick_interpreter_node` |
| Sürü Hareket / Manevra Modu | `mode_manager_node` |
| Kumandadan kalkış, iniş, formasyon değişimi | `mode_manager` + `formation_node` |
| Tüm İHA'lar **senkronize** tepki | `SwarmControlCommand` mesh'ten |

### Donanım şartları

| Şart | Durum |
|------|-------|
| Her İHA için ayrı pilot + kumanda | ✅ var |
| **En az bir İHA'da kamera**, FOV ≤ 90° | 🟠 yakında |
| En az 3 İHA | 🟡 yalnız final görevi için |
| QR 120×120 cm | bilgi |

> **3. İHA entegrasyonu engellemiyor.** Aşama 0-4 ve 6 iki uçakla tam yürür.
> Yalnız Aşama 5'teki **üyelik testi** üç uçak ister.

---

## 4. Plan: 8 aşama

Her aşamada **çalışan bir sistem kalır.** Bir şey bozulursa tek komutla geri
dönülür (`/ws/suru_dugumleri` boşalt + `docker restart`).

| # | Aşama | Ne yapıyor | Risk | Test |
|---|-------|-----------|------|------|
| **0** | Zemin | Öncelik hakemliği, remap'ler, düğüm aç/kapa altyapısı | Yok | Yerde |
| **1** | Bilgi katmanı | Origin, lider seçimi, sürü durumu, görev durumu | ~Yok | Yerde + 1 uçuş |
| **1B** | Kaçınma değişimi | Sürünün kaçınma algoritmasına geçiş | Orta | 2 uçuş |
| **2** | **Formasyon** 🔴 | Formasyonu uçak kendi hesaplar — **merkeziden dağıtığa** | Yüksek | 3 uçuş |
| **3** | Görü | Kamera, QR okuma, renkli alan tespiti | Yok | Çoğu yerde |
| **4** | Görev mantığı | QR'ı oku → görevi yap → sonrakine git | Yüksek | 3 uçuş |
| **5** | Manevra + iniş + üyelik | Pitch/roll, hassas iniş, sürüden ayrılma | En yüksek | Kademeli |
| **6** | Görev 2 | Tek kumandayla sürü kontrolü | Orta | 2 uçuş |

**Toplam kaba bütçe: ~15 uçuş.**

### Sıra neden böyle

- **Önce komut yoluna dokunmayanlar.** Aşama 1'deki dört düğüm sadece *durum
  yayınlıyor*, uçağa komut vermiyor. Açmak neredeyse risksiz.
- **Sonra üreticiyi değiştirenler**, teker teker. Aynı uçuşta iki değişiklik
  yok — bir şey ters giderse hangisi olduğu bilinsin.
- **En riskli en sona.** Hassas iniş yere temas ediyor; ona en son ve kademeli
  gidilir (önce 3 m'den).
- **Görü paralel** — kimseyi beklemiyor, ama Aşama 4'ün ön koşulu.

```
0 ──► 1 ──► 1B ──► 2 ──► 4 ──► 5
                    │
       3 (görü) ────┘        6 (görev 2) ──► 2'den sonra, paralel
```

---

## 5. Nasıl test ediyoruz — dört kademe

Simülasyon **kullanmıyoruz**. Onun yerine her düğüm, çıkışı hiçbir yere bağlı
değilken gerçek uçuş verisiyle çalıştırılır.

| | Ne | Süre | Risk |
|---|---|---|---|
| **G0** | Yerde: açılıyor mu, RAM/CPU, parametre kabul ediyor mu | ~10 dk | Yok |
| **G1** | Yerde gözlem: telemetri akarken çıktı üretiyor mu, mantıklı mı | ~10 dk | Yok |
| **G2** | **Havada gözlem**: kanıtlanmış zincir uçarken düğüm arka planda | 1 uçuş | Düşük |
| **G3** | Havada komutta: üretici değişir, tek uçak alçak/kısa, sonra iki uçak | 1-2 uçuş | Gerçek |

**Gözlem modu nasıl kurulur:**

```bash
ros2 run swarm_core formation_node --ros-args -p agent_id:=1 \
    -r /drone_1/control/setpoint/raw:=/gozlem/drone_1/formation/raw
```

Düğüm gerçek telemetriyle gerçek kararlar üretir, ama uçağa ulaşmaz. Sonra
kayıttan "ne yapardı" ile "ne oldu" karşılaştırılır. Uçakta `/ws/gozlem`
bayrağı bunu `baslat.sh` üzerinden yapıyor.

**G2 atlanmaz.** Bu projede en pahalı ders, "kod doğru görünüyor" ile "kod
doğru davranıyor" arasındaki farkın uçakla ödenmesi oldu.

İlk kullanımında değerini kanıtladı: `formation_node` yerdeki uçak için
`vz = 1.51 m/s` üretti — gözlem modu olmasaydı bu bir tırmanma komutuydu.

### 🔴 En küçük yeterli manevra

Ölçüt **bir sonraki adımın güvenli olduğunu gösterecek EN AZ test.**

Uçuşu tasarlarken sıra: ① *Bu uçuş hangi tek soruyu cevaplıyor?*
② *Yerde cevaplanabilir mi?* — cevaplanabiliyorsa **uçulmaz.**
③ *En kısa hangi manevra cevaplar?* — **o uçulur.**

| Soru | Yeten manevra |
|---|---|
| Düğüm açılıyor mu, mantıklı değer üretiyor mu | **Uçuş yok** — G0/G1 yerde |
| Havada ne üretiyor (komuta bağlı değil) | **Kalk – asılı dur – in** |
| Setpoint takibi, kayma, aşım | **Tek düz bacak, git-gel** |
| Formasyon doğru mu | **Tek formasyon**, tek geçiş |
| Lider seçimi / arıza devri | **Kalk – asılı dur**, kill ile devret |

**Uzun uçuş kendi başına bir değer değil, kendi başına bir risktir.** Her ek
bacak yeni bir arıza yüzeyi açar ve pil yakar. *"Madem havadayız, şunu da
deneyelim"* **yasak.**

Aynı uçuşta **iki değişiklik denenmez** — ters giderse hangisi olduğu bilinmeli.

Aşama başına kaba bütçe ~2-3 uçuş; ama sayı hedef değil, **soru** hedef.

**Geri dönüş her zaman tek komut:** `/ws/suru_dugumleri` boşalt +
`docker restart`. Faza başlamadan önce bunun çalıştığı bir kez gösterilir.

### 🔴 Her uçuştan önce — kuru test + harita, tek komutta

```bash
python3 src/gcs/gorev_kanit_ucus.py --kuru --harita \
    --senaryo <senaryo> --dronelar 1,3 --lider 3
```

`--kuru` planı kurar ve çarpışma denetimi yapar, **hiçbir komut göndermez**.
`SONUÇ: GEÇTİ` demezse **uçulmaz.**

`--harita` uydu görüntüsü üzerine `/tmp/yelpence_rota.html` yazar:
**yeşil** = sürü merkezinin geçtiği noktalar · **mavi** = her drone'un kendi
son hedefi (= **inecekleri yer**).

> 🔴 **Harita operatöre gösterilir ve operatör gözüyle doğrular.** Kod bina,
> ağaç, tel, araç **göremez** — harita elimizdeki **tek engel kontrolü.**
> Formasyonda uçaklar **kalktıkları yere inmez**; mavi noktalar tam bunun
> içindir.

Ayrıca `./deploy/yki/param_karsilastir.py` — uçaklar aynı ayarda mı.

Uçuş öncesi zorunlu **sekiz madde** ve kırmızı çizgiler: `CLAUDE.md` §9.

---

## 6. Düğüm düğüm karar

**21 birinci-parti düğüm var. 19'u gerekli.** Görev dağıtık otonomi, görü,
hassas iniş ve sürü üyelik değişimi istiyor.

### ✅ Zaten sahada koşuyor

| Düğüm | Rol | Not |
|-------|-----|-----|
| `px4_bridge` | Setpoint yürütücü + OFFBOARD | **Kanıtlanmış, ölçülmüş.** Aktüasyon katmanı bu kalacak |
| `esp32_bridge` | Mesh ↔ ROS köprüsü | Guided ARM → `EVENT_MISSION_STARTED` köprüsü eklendi (19 Ağu) |
| `agent_fsm_node` | Ajan durum makinesi | `kalkis_olayla=false` geçiş döneminde |
| `basit_kacinma` | APF kaçınma | **GEÇİCİ** — Aşama 1B'de `collision_avoidance` ile değişecek |
| `ic_dis_kopru` | internal → public yerel döngü | Herhangi bir sürü düğümü açıksa kendiliğinden açılır |
| `swarm_origin_publisher` · `consensus_node` · `swarm_fsm_node` · `formation_node` · `path_planner` | Sürü bilgi katmanı | 15-17 Ağustos'ta açıldı, **yalnız yerde ve G2 gözleminde** sınandı |

### 🔴 Görev 1 için ZORUNLU — hiç koşmadı

| Düğüm | Satır | Neden zorunlu |
|-------|-------|---------------|
| `maneuver_executor` | 444 | **Pitch/roll manevrası açık bir QR görevi** |
| `mission_fsm_node` | 598 | QR görev sırası (`team_id` filtresiyle) |
| `mission1_dynamic_swarm` | 499 | Görev 1 orkestratörü — YKİ'nin yerini alır |
| `camera_driver` | 314 | Gerçek kamerayı destekliyor (`cv2.VideoCapture`) |
| `vision_node` | 407 | QR çözümleme **ve** kırmızı/mavi bölge tespiti |
| `precision_landing_node` | 271 | Renkli bölgeye hassas iniş; toleransın dışı = 0 puan |
| `task_reallocator_node` | 289 | Sürüden birey ayrılma/katılma |

### 🔴 Görev 2 için ZORUNLU

`mode_manager_node` (501) · `joystick_interpreter_node` (222)

### ❌ Alınmayacak

| Ne | Neden |
|----|-------|
| `kinematic_fusion` (493) | EMA yumuşatması ~0.4 s gecikme ekliyor — KARAR-01 |
| `network_proxy` · `sim_rtcm_source` | Simülasyon bileşeni; sahada yerlerini `esp32_bridge` ve gerçek F9P alıyor. Depodan silindi (16 Ağu) |

---

## 7. Yapısal engeller ve çözümleri

### Engel 1 — `SwarmState` ve `MissionTarget` mesh'ten geçmiyor ✅ çözüldü

`swarm_fsm` → `/swarm/internal/state` ve `mission_fsm` →
`/swarm/internal/mission/next_target` mesh'e taşınmıyordu.

**Çözüm: yerel remap, kod değişikliği yok.** Bu iki değerin mesh'ten gelmesine
gerek yok — her uçak kendi türetebiliyor (`swarm_fsm` `SwarmState`'i tüm
`AgentStatus`'lardan, `mission_fsm` `MissionTarget`'ı `QRMissionData`'dan; ikisi
de zaten mesh'te). **Yan faydası:** şartnamenin dağıtıklık şartına da uyuyor —
ortak durum yok. Mesh'e paket eklemek merkezîleşme yönünde bir adım olurdu.

Kalıcı çözüm 15 Ağustos'ta geldi: **`ic_dis_kopru`** düğümü **12 konuyu**
internal→public taşıyor.

> ⚠️ `drone{N}/status` **bilerek taşınmıyor** — uçak kendini komşu sanıp
> kendinden kaçmaya çalışırdı.

### Engel 2 — `px4_bridge` öncelik hakemliği yapmıyor 🟡 aciliyeti düştü

`AgentSetpoint`'te `priority` alanı **zaten var** ve sıra tanımlı:

```
FAILSAFE(100) > COLLISION_AVOIDANCE(80) > POSITION(30) > MANEUVER(20) > FORMATION(10)
```

Ama kod okununca görüldü ki çakışma **zaten çözülmüş** — `priority` ile değil,
**susturma** ile: `formation_node` MANEUVER adımında ve
DETACHED/PRECISION_LANDING/WAITING_REJOIN/REJOINING durumlarında susuyor;
`precision_landing` yalnız kendi durumunda yazıyor.

Hakemlik yine de **güvenlik ağı** olarak değerli — bir kapı kaçarsa sessiz
çakışma yerine belirli davranış. ~30 satır, yerde test edilebilir.

### Engel 3 — `formation_node` kip uyuşmazlığı ✅ ÇÖZÜLDÜ (21 Ağu; belge 25 Ağu'da koda eşitlendi)

`formation_node` C modu (saf hız, `position_valid=False`) için tasarlanmış, ama
`px4_bridge._velocity_only` varsayılanı `False` → A modunda çalışır, PX4 de
konum kontrolü yapar ve **kazançlar toplanır** (SVT 0.8 + `MPC_XY_P` 0.95).

**Çözüm 21 Ağustos'ta `baslat.sh`'e girmiş** (satır ~470-510, bu belge bayat
kalmıştı): `VELOCITY_ONLY` elle değil **otomatik** hesaplanıyor —
(a) formasyon uçağı sürüyorsa (`/ws/gozlem` yok) **veya** (b) CA koşuyorsa
→ `true`. (b) sayesinde bugünkü uçan yapılandırmada **zaten true**; 25 Ağu
kaçış uçuşlarının saf-hız B dalında temiz çalışması davranışsal kanıt.
Guided yol bozulmaz: `goto` `velocity_valid=False` taşır → yürütücü (C)
dalı, `velocity_only`'ye hiç bakmaz. Ek güvenlik: formasyon sürecekken
aktarım katı boşsa betik gözlem modunu ZORLAR.

**ADIM 3 günü kalan iş: `/ws/gozlem`'i silmek** — bayrak kendiliğinden doğru.

Alternatif: `formation_node`'u konum kipine almak (`position_valid=True`). O
zaman iş bölümü temiz olur — `formation_node` **nereye**, `px4_bridge`
**nasıl** gidileceğini hesaplar.

> Eski bir iddianın düzeltmesi: *"`formation_node`'un SVT'si saf oransal,
> ileri-besleme yok"* **yanlıştı**. `_vff_x/y/z` var, rampanın 50 Hz hızından
> türetiliyor ve komuta ekleniyor. Sorun ileri-beslemenin yokluğu değil,
> **kip uyuşmazlığı**.

### Engel 4 — İki kaçınma kodu, tek yuva ✅ karara bağlandı

Kaçınma **zorunlu** (şartname: "İHA'ların çarpışmaması sağlanmalıdır"). Repoda
aynı işi yapan iki uygulama var ve **ikisi de aynı topic yuvasını** kullanıyor
(`/control/setpoint/raw` → `/control/setpoint`), yani aynı anda koşamazlar.

**Karar: Seçenek C** — `collision_avoidance`, ham `AgentStatus`'tan beslenerek.
Adaptör yazıldı ve test edildi (20 Ağustos, 10/10).

Gerekçe, ölçümler, eşikler (`d0=6.0 / hard=4.0`) ve test protokolü:
**`KARARLAR.md` KARAR-01**. Burada tekrarlanmıyor.

⚠️ Devreye alma **Aşama 1B**: `/ws/kacinma` silinir, `ca` anahtarı açılır.
`basit_kacinma` **silinmez** — beklenmedik davranışta tek dosya değişikliğiyle
geri dönülür.

---

## 8. ENTEGRASYON SIRASI — ADIM ADIM

Koşmakta olanlar da listede; "zaten var" bir düğümü çıkarmak yanlış olurdu.

### ADIM 0 · Zaten koşan temel

| Düğüm | Gereken |
|-------|---------|
| `px4_bridge` | ✅ `velocity_only` otomatik (Engel 3): CA açıkken zaten true; ADIM 3'te `/ws/gozlem` silinince formasyon dalı da devrede |
| `esp32_bridge` | Değişiklik yok — lider kapısı doğru çalışıyor |
| `basit_kacinma` | ADIM 4'te değişecek, **silinmeyecek** |
| `agent_fsm_node` | ✅ preflight pil düzeltmesi yapıldı (15 Ağu) |

> 📌 **Ders (15 Ağustos):** pil düzeltmesi "P0 uçuş engeli" diye sunulmuştu ve
> gerekçe *"uçaklar 3.1 V okuyor"* idi — **canlıda doğrulanmamıştı.** Gerçek
> okuma **65.535 V** (MAVLink "veri yok" sentineli), yani `65.535 < 13.6`
> yanlış → hata hiç üretilmiyordu. **Uykuda bir tuzaktı, aktif engel değildi.**
> Bir sayıyı önceki bağlamdan taşıyıp canlıda doğrulamadan teşhis kurma.

### ADIM 0.5 · `swarm_origin_publisher` — ✅ GEÇTİ (21 Ağustos, mesh yolu dahil)

> Bu düğüm önce **ADIM 8**'de yazıyordu, **yanlıştı.** `preflight_checker`
> `origin_synced` şart koşuyor; origin gelmeden `IDLE → ARMING` olmuyor, ARMED
> olmadan ajan `ELIGIBLE_STATES`'e girmiyor ve consensus **hiç lider
> seçemiyor.**

`echo "<lat> <lon> <alt>" > ~/yelpence_ws/origin` + `suru_dugumleri`'ne
`origin` ekle. **Üç uçakta da AYNI koordinat** olmalı — farklı olursa
formasyonlar uçaktan uçağa kayar.

> ✅ **Origin'in MESH yolu DENENDİ ve AÇIK (21 Ağustos, yer testi).**
>
> Ölçüm: ylp02'nin **kendi** `swarm_origin_publisher`'ı öldürüldü →
> `/swarm/internal/origin` sustu (yerel `ic_dis_kopru` döngüsü de onunla
> birlikte) → ama `/swarm/public/origin` **1,265 Hz'de akmaya devam etti**,
> `valid=true`. Yerel kaynak ölüyken bu veri **yalnızca mesh'ten** gelebilir.
> Ardından yayıncı geri açıldı; `internal/origin` 1,0 Hz'e döndü ve
> `Publisher count: 1` — kopya üretici yok.
>
> Boşluk dağılımı mesh'e yakışır biçimde düzensiz (min 0,199 s · maks
> 2,011 s), yani ~%30 kayıp altında beklenen hâl. Origin 1 Hz ve tekrarlı
> olduğu için bu yeterli.
>
> ⚠️ **Neyi kanıtlamadı:** iki uçak da **aynı sabit değeri** yayınladığı için
> gelen verinin *içeriğinin* ylp00'dan geldiği gösterilemez — kanıtlanan şey
> **mesajların** mesh üzerinden aktığı. Karar için bu yeterli; içerik ayrımı
> ancak uçaklara farklı origin verilerek sınanır ve o NED çerçevesini
> bozacağı için yapılmadı.
>
> ⚠️ Bir dönem burada bir **geçici remap** vardı ve mesh yolunu tamamen
> kapatmıştı — `TUZAKLAR.md` §2.12. `ic_dis_kopru` gelince kaldırıldı.

### ADIM 1 · `consensus_node` — ✅ GEÇTİ (15 Ağustos, yer testi)

`esp32_bridge` formasyonu **yalnız lidere** yazıyor; lider yoksa
`FormationCommand` mesh'e hiç çıkmaz.

**Şart:** `battery_min_v:=0.0`, `agent_count:=3`, origin senkron, uçaklar ARM'lı.

> ⚠️ **`agent_count` 2 DEĞİL 3.** `consensus_node.py:133`
> `for aid in range(1, agent_count+1)` ile `drone1..droneN`'e abone oluyor —
> sayı "kaç uçak uçuyor" değil **"kimlikler 1..N"**. Uçaklarımız 1 ve 3;
> 2 yazılsaydı **drone3 hiç dinlenmezdi.** Eksik kadro seçimi engellemiyor
> (`bootstrap_grace_s` 1.5 sn).

**Ölçülen:** iki uçak da aynı lideri seçti (`Lider: 0 -> 1`, **101 ms**
arayla); `esp32_bridge` lideri öğrendi, formasyon kapısı açıldı. **Lider arıza
devri** de gözlendi: kill ylp00'ı FAILSAFE'e düşürdükten **82 ms** sonra
`Lider: 1 -> 3`.

**Yolda düzeltilen engel:** mesh `AgentStatus` paketi `healthy` taşımıyordu;
alıcı varsayılan `false` bırakıyordu ve `is_eligible` bunu şart koştuğu için
**hiçbir uzak ajan aday olamıyordu** → her uçak kendini seçerdi = **split-brain**.
`esp32_bridge` decode'unda artık türetiliyor (`ekf_ok` ∧ ¬`kill_switch` ∧
state≠FAILSAFE). Paket ve firmware değişmedi.

**Kalan:** iki uçaklı **tam devir teslim** testi — birini kill'le, diğerini
armlı bırak, liderliği devralıyor mu.

### ADIM 2 · `swarm_fsm_node`

**Şart:** `agent_count:=3` (kimlik aralığı) + `expected_agent_count:=2` (filo).

> 🔴 Tek parametre iki işi yapıyordu ve **çelişiyorlardı**: abonelik kimlik
> aralığı 3 olmalı, filo büyüklüğü 2. Tek değerken `formation_reached` için
> `2 >= 3` false (FORMING'de kalıcı takılma) **ve** sağlık oranı `1/3 = 0.33
> < 0.5` (bir uçak bozulunca tüm sürüye acil iniş). 15 Ağustos'ta ikiye
> ayrıldı. **Üç uçak birden uçulunca `SURU_BEKLENEN_UCAK=3`.**

✅ Sabit formasyon ofsetleri düzeltildi — eskiden 3/4 m aralık ve ajan id
1/2/3 varsayımı **gömülüydü**, üstelik ofsetler heading'e göre döndürülmüyordu
ve **sıfır ortalamalı değildi** (12 m'de 6 m sabit yanlılık). Artık
`/swarm/public/formation/target` dinleniyor, ofsetler heading kadar
döndürülüp ortalaması çıkarılıyor.

✅ `_on_election` tek global seq sayacı düzeltildi — `consensus_node` her
yeniden başladığında `sequence_num` 1'e döndüğü için **bütün** seçim mesajları
bayat sayılıp düşüyordu; `docker restart` sonrası `swarm_fsm` lider
değişimlerine kalıcı sağır kalıyordu. Artık kaynak başına `(incarnation, seq)`.

### ADIM 3 · `path_planner` + `formation_node`

**Şart:** ~~`px4_bridge velocity_only:=True`~~ ✅ otomatik (Engel 3 —
`/ws/gozlem` silinince kendiliğinden true; yarın açılışta
`grep velocity_only` ile açılış logundan teyit et), `spacing_m` komutta 12 m.

✅ **Tek-üretici geçişi de `baslat.sh`'te (25 Ağu akşam):** formasyon
SÜRERKEN esp32_bridge'in setpoint çıkışı `/gozlem/.../mesh_goto`ya gider —
mesh goto kayda girer ama uçağı SÜREMEZ; `/raw`'ın tek üreticisi
formation_node olur (CLAUDE.md §4 fiziksel olarak sağlanır). ARM/takeoff/
land/mode komutları AgentCommand kanalından — etkilenmez. Formasyon
sürmüyorken davranış birebir eski. Üç senaryo masada doğrulandı;
⚠️ uçaklara DAĞITILMADI (ADIM 3 gününün ilk işi: baslat.sh dağıt +
açılış logundan `TEK-URETICI` satırını gör).

⚠️ **KARAR-02:** `formation_node` 50 Hz'de uçağa setpoint yazıyor — ilk kez
havaya kalkmadan önce operatöre çok ajanlı denetim önerilecek.

🔴 **`formation_node`'a girdi veren tek düğüm `mission1_node` ve o KAPALI.**
`formation_node` bir hesap makinesi: tarif gelmezse hiçbir şey yayınlamaz
(`formation_node.py:878` → `if msg is None: return`). Ara çözüm var:
`deploy/rpi/teshis/form_yayinla.sh` tarifi **uçakta** üretiyor ve düğümü
besliyor — 18 Ağustos'ta bununla ölçüldü:

```
komut : merkez 12.3 / -45.6 / -8.0   heading 137.5   max_speed 3.5
cikti : x=12.2990  y=-45.6019  z=-8.000   -> merkeze 0.9 mm hata
        |v| = 3.500 m/s (tam tavan)   position_valid: FALSE
```

Düğüm komutu doğru çözüyor, slot hesabı doğru, rampa hedefe oturuyor.

🔴 **`mission1_node` YERDE TEST EDİLEMEZ:** `orchestrator.decide()` yalnız
`NAVIGATE_TO_QR / ROTATE_TO_NEXT / EXECUTE_QR_TASK / RETURN_HOME`
durumlarında komut üretiyor ve o durumlara ancak `SYNCHRONIZED_TAKEOFF` →
tüm ajanlar `IN_SWARM` olduktan sonra geliniyor. **En az 2 uçak ve UÇUŞ ister.**

### ADIM 4 · `collision_avoidance` — ✅ AÇILDI (21 Ağu) + DİKEYE GEÇTİ (23 Ağu)

`basit_kacinma` kapandı (aynı yuva), **silinmedi**. 23 Ağustos'ta kaçış
yönü **dikeye** alındı (KARAR-06): birincil kaçış dikey yol verme, yatay
itme yalnız sert kabukta. Beş yer testi geçti, **havada uçmadı**.

Tasarım, ölçümler, açık sorular: **`docs/CA.md`**.
⚠️ KARAR-02 hatırlatması geçerli — ilk uçuştan önce `ultracode`.

### ADIM 5 · `camera_driver` + `vision_node` — paralel

🔴 **Önce `cv2` + `pyzbar` konteynere kurulmalı** — canlı denendi,
`ModuleNotFoundError`. `numpy` var (1.26.4). Görü zinciri onsuz hiç çalışamaz.

### ADIM 6 · `mission_fsm_node`

**Her iki görevi de o sürüyor** — `MissionType.DYNAMIC_SWARM` ve
`SEMI_AUTONOMOUS`. Yani Görev 2 de buna bağlı.

### ADIM 7 · `mission1_dynamic_swarm` — YKİ'nin yerini alır
### ADIM 8 · `swarm_origin_publisher` — YKİ kesilince
### ADIM 9 · `maneuver_executor` — ROS Action, mesh'ten geçmiyor (her uçak kendi yerelini çağırır)
### ADIM 10 · `precision_landing_node` — `ZoneMap` gerekli (ADIM 5'e bağlı)
### ADIM 11 · `task_reallocator_node` — `min_active_for_formation:=2`, 3 uçak
### ADIM 12 · `joystick_interpreter` + `mode_manager` — Görev 2

> ⚠️ **"N'i 2 yap" maddelerini uygulamadan önce KODU OKU.**
> `consensus.agent_count` için "2 yapılmalı" yazıyordu ve **yanlıştı** —
> uygulansaydı ylp02 sürüden tamamen düşerdi. Her parametrenin o sayıyı **ne
> anlamda** kullandığı (kimlik aralığı mı, canlı sayı mı, çoğunluk eşiği mi)
> sırası gelince tek tek doğrulanacak.

---

## 9. Navigasyon kayması — ölçüldü, kapandı

**Hedef:** uçak yürüyen setpoint'in arkasında kalmasın, hız arttıkça da
bozulmasın.

PX4'ün konum döngüsü: `v_komut = Kp × (hedef − konum) + v_ff`, `Kp = MPC_XY_P = 0.95`.

| | Kalıcı kayma | Hız artınca | Durum |
|---|---|---|---|
| Sadece konum (`v_ff=0`) | `v / Kp` (5 m/s'te **5.3 m**) | doğrusal büyür | `formation_node` SVT böyle |
| **Konum + hız FF** | **≈ 0** | **büyümez** | ✅ `px4_bridge` yürütücüsü |
| + ivme FF | ≈ 0, **geçici rejim de düzelir** | büyümez | ✅ açıldı (20 Ağu) |

### ✅ ADIM 1 ÖLÇÜLDÜ — 20 Ağustos, 30 m bacak, iki uçak

`--senaryo g2 --irtifa 10 --mesafe 30`, seyir 3.0 m/s. Kayıttan
`setpoint_raw/local` ile `local_position/pose` yatay farkı; bacak başına 566
örnek, %74'ü seyir fazında.

| | ortalama |
|---|---|
| **Kalıcı kayma** | **≈ 0.10 m** |
| **Tepe geçici hata** | **≈ 1.12 m** (t+1.8 s) |
| **Oturma süresi** | **≈ 3.5 s** |

**Eski 0.44 m rakamı geçersizdi** — 7 m'lik bacakta alınmıştı ve aslında
geçici rejimi ölçüyordu (rampa 2.7 m, kalan 4.3 m = yalnız 2.1τ; hatanın
~%12'si hâlâ sönmemiş). İki uçak birbirini doğruladı (0.06-0.13 m).

> **Düz bacak ne kadar olmalı:** `rampa = v²/a`, `oturma = 4τ×v`, `τ = 1/Kp ≈ 1.05 s`.
> 2 m/s → 11 m · 3 m/s → 19 m · 4 m/s → **28 m** · 5 m/s → **38 m**.

### ✅ ADIM 2 — ivme ileri-beslemesi A/B ölçüldü

Aynı uçuş, aynı rota, aynı hava. **ylp00 AÇIK, ylp02 KAPALI (referans).**

| Metrik | FF KAPALI | FF AÇIK | Kazanç |
|---|---|---|---|
| Tepe geçici hata | 1.177 / 1.026 m | **0.551 / 0.324 m** | **−60 %** |
| Varış aşımı | 1.18 m | **0.46 m** | **−61 %** |
| Oturma | 3.88 / 3.36 s | **3.1 / 1.0 s** | daha hızlı |

**ylp02 kendi tabanını birebir tekrarladı** (1.173/1.053 → 1.177/1.026), yani
fark rüzgârdan değil **koddan**. Operatör kararıyla varsayılan `1.0` yapıldı.
**Geri alma tek satır:** `GUIDED_IVME_FF=0.0`.

Kod notu: ivme **gecikme telafisinden ÖNCEKİ ham profilden** alınıyor (telafi
bir düzeltme terimi, yörünge ivmesi değil) ve ivme tavanıyla kelepçeleniyor —
varışta hız tek adımda sıfırlandığı için türev absürt büyük çıkıyordu.

### 🔴 Doygunluk payı — kalıcı kaymanın tek şartı

`v_ff + Kp×hata` `MPC_XY_VEL_MAX` tavanını **aşmamalı**. Seyir hızı tavana
eşitse konum düzeltmesine yer kalmaz, PX4 kırpar, kayma geri gelir.

```
seyir 3.0, tavan 5.0  ->  duzeltmeye 2.0 m/s pay    ✅
seyir 5.0, tavan 5.0  ->  duzeltmeye 0 m/s pay      ❌ kayma garanti
```

✅ Kural konuldu: `PX4_HIZ_TAVANI_MPS ≥ GOREV_HIZ_MPS × 1.5`.
`ucus_ayarlari.py` bunu **hata** olarak veriyor.

### Kalan

- `[ ]` 🟠 **İkinci hızda tekrarla** — 2 m/s bu 30 m bacakta ölçülebilir;
  **4 m/s için 40 m bacak şart**
- `[ ]` 🟡 Bir sonraki uçuşta tepe hata / aşım teyit edilsin (0.44 / 0.46 civarı)
- `[ ]` 🟠 **Sürü tarafı Durum 1'e düşmesin** — `formation_node`'un SVT'si saf
  oransal (`v = −0.8 × hata`), kalıcı kayma `v/0.8`. Çözüm Engel 3'te.
- `[ ]` 🟡 Uçuş sonrası kayıttan bacak başına `max |setpoint − konum|` çıkaran
  araç; eşik aşılırsa uyarsın. Kayma sessizce büyürse **kayıttan** görelim.

**Etkilemeyenler:** mesh gecikmesi (yürütücü **yerelde**, kontrol döngüsünün
içinde değil) · EKF konum gecikmesi (sabit küçük ofset) · rüzgâr (PX4'ün hız
döngüsünde integral var).

---

## 10. Ölçülen kaynak durumu (14 Ağustos, ylp00)

```
RAM 8062 MB toplam · 2094 kullanilan · 5967 kullanilabilir
Yuk 0.95 (4 cekirdek) · 55 °C · dugum basina ~190-218 MB RSS
```

19 düğüm kâğıt üstünde sığar ama **RSS paylaşılan kütüphaneleri sayıyor**;
gerçek artış çok daha az. Asıl darboğaz muhtemelen **CPU ve DDS trafiği**.
Her aşamada, o aşamanın düğümleri için ölç — tahmin etme.

---

## 11. Şu an sırada ne var

> **Aşama 0 bitti.** **Aşama 1'in yer yarısı geçti** (ADIM 1, lider seçimi).
> **G2 gözlem uçuşu yapıldı** (18 Ağustos) ve sürü yığınının FSM kopukluğunu
> ortaya çıkardı; kopukluk 19 Ağustos'ta uçak-içi köprüyle kapatıldı ve
> **yerde iki uçakla doğrulandı**.

### 🔵 SIRADAKİ İŞ: G2 tekrarı — havada lider seçimi

İlk G2'de sürü yığını hiç etkinleşmedi: ajan IDLE'da kaldığı için consensus
**638 saniyede sıfır seçim** yaptı. Sebep yapısaldı — YKİ'nin guided yolu
`agent_fsm`'i atlıyordu. Çözüldü (`esp32_bridge` guided ARM'da yerel
`EVENT_MISSION_STARTED` üretiyor) ve yerde iki uçakla doğrulandı: `IDLE →
ARMING → ARMED`, lider mutabakatı, **mesh'ten 499 kalp atışı**.

**Artık havada ölçülebilir:** lider seçimi kararlı mı · kalp atışı sürüyor mu ·
`swarm_fsm` doğru durum üretiyor mu · 11 düğümle RAM/CPU ne.

⚠️ **KARAR-02:** consensus'un ilk gerçek hava görevi — uçuştan önce operatöre
`ultracode` önerilecek.

### Uçmadan önce kapatılacaklar

| | Ne |
|---|---|
| `[ ]` | 🔴 **P0.12** — denetimin doğrulanmış iki P0'ı (yerdeki disarm uçağın sonsuz lider yayını · `land` sonrası bayat GOTO'nun inişi iptal etmesi). ~4 satır |
| `[ ]` | 🔴 **P0.13** — uçaklar ağdan önce kalkıyor, ROS yığını sakat kalıyor |
| `[ ]` | 🟠 **P1.6** — `TUZAKLAR.md` §0'daki bilinmeyenler: ylp00 clipping ölçüm kuralı, hover gazı |
| `[ ]` | 🟠 **ADIM 1'in kalanı** — iki uçaklı tam devir teslim |

Beklemede: **ylp01 onarımı** (ESC güç hattı) ve **kamera montajı**. İkisi de
entegrasyonu durdurmuyor ama finalde şart.

---

## 12. Açık sorular

| # | Soru | Aşama |
|---|------|-------|
| 1 | `px4_bridge` öncelik hakemliği nasıl kurulmalı (bayatlık + öncelik)? | 0 |
| 2 | `path_planner` zorunlu halka mı, atlanabilir mi? | 1 |
| 3 | `mode_manager` PX4 uçuş moduna **yazıyor mu**? | 6 |
| 4 | 19 düğüm açıkken CPU ve DDS trafiği yetiyor mu? | 0 |
| 5 | Kamera 120×120 QR'ı hangi irtifadan okuyor? | 3 |
| 6 | Saf dağıtığa geçilsin mi (liderin slot ataması hiç kullanılmasın)? | 5 |

> **Çelişki varsa:** canlı belge referans belgeyi yener, **kod ikisini de yener.**
