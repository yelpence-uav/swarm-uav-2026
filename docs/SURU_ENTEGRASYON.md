# SÜRÜ ENTEGRASYONU — yol haritası

**Son güncelleme:** 15 Ağustos 2026, 16:10

**Hedef:** Final görevini yapabilir hâle gelmek.
**Kısıt:** Simülasyon yok. Her adım gerçek uçakta, ölçerek, geri alınabilir.

> Bu belge 15 Ağustos'ta **şartname okunarak** baştan yazıldı. Önceki sürüm
> düğümleri tek tek incelemeden faz sırası kuruyordu; şartname okununca
> hangi düğümün neden gerektiği ve **mevcut mimarinin neden yetmediği**
> netleşti.

---

## 0. Şartname ne dayatıyor

Bunlar tercih değil, **kural**. Mimariyi bunlar belirliyor.

### 🔴 İki kural mevcut mimarimizi geçersiz kılıyor

> *"**Dağıtık sürü algoritması** kullanılması gerekmektedir. **Merkezi sürü
> algoritmaları eksik puan** olarak değerlendirilecektir."* (§5.3)

> *"Hakemler görev sırasında herhangi bir anda **yer kontrol istasyonu
> bağlantısını kesecektir**."* (§5.1 Görev kuralları)

> *"Yer Kontrol İstasyonu üzerinden **görevi başlatma komutu dışında**
> herhangi bir müdahale **yasaktır**. Müdahale tespiti halinde görev
> **başarısız** sayılır."*

Bugünkü zincirimiz — YKİ `gorev_kanit_ucus.py` her uçağa mesh'ten `goto`
gönderiyor — **hem merkezi hem YKİ'ye bağımlı.** Hakem bağlantıyı kestiği
anda sürü durur. Uçuş kanıtını geçirdi, **finali geçiremez.**

**Sonuç: onboard sürü düğümleri opsiyonel değil, ZORUNLU.**

YKİ'nin izinli tek rolü **"görevi başlat"** komutu. Ondan sonrası uçakta.

### Görev 1 — Dinamik Sürü Kabiliyeti

| Şart | Karşılığı |
|------|-----------|
| **En az 3 İHA** | **Yalnız FİNAL GÖREVİ için.** Entegrasyon 2 uçakla tam yürür |
| Tek kalkış komutu, eş zamanlı otonom kalkış | `mission1` + `agent_fsm` |
| Formasyonu koruyarak QR noktasına ilerleme | `formation_node` + `path_planner` |
| **En az bir İHA QR'ı görsel algılayıp çözecek** | `camera_driver` + `vision_node` |
| QR görevleri: formasyon değişimi, **pitch/roll manevrası**, irtifa değişimi, **sürüden birey ekleme/çıkarma**, bekleme | `mission_fsm` + `maneuver_executor` + `task_reallocator` |
| **Her bacakta formasyon rotasyonu** — her ajanın heading'i hedefe döner | `formation_node` |
| Ayrılan birey **kırmızı/mavi bölgeye hassas iniş** → disarm → bekle → arm → sürüye katıl | `precision_landing_node` + `vision_node` |
| Rota boyunca renkli bölgeler **kamerayla tespit edilip kaydedilmeli** | `vision_node` (ZoneMap) |
| Çarpışmama | kaçınma düğümü |
| Home'a dönüş + formasyonu bozmadan güvenli iniş | `mission1` |

### Görev 2 — Yarı Otonom Sürü Kontrolü

| Şart | Karşılığı |
|------|-----------|
| **Tek joystick/kumanda ile tüm sürü** | `joystick_interpreter_node` |
| Sürü Hareket Modu / Manevra Modu | `mode_manager_node` |
| Kumandadan kalkış, iniş, formasyon değişimi | `mode_manager` + `formation_node` |
| Tüm İHA'lar **senkronize** tepki | `SwarmControlCommand` mesh'ten |

### Donanım şartları

| Şart | Durum |
|------|-------|
| **Her İHA için ayrı pilot + kumanda** | ✅ **var** |
| **En az bir İHA'da kamera**, FOV ≤ 90° | 🟠 yakında takılacak |
| **En az 3 İHA** | 🟡 **yalnız final görevi için.** Entegrasyonun tamamı 2 uçakla yürütülebilir |
| QR 120×120 cm | bilgi |

> **3. İHA entegrasyonu engellemiyor.** Aşama 0-4 ve 6 iki uçakla tam
> yapılabilir. Yalnız Aşama 5'teki **üyelik testi** (bir uçak ayrılıp inince
> sürü devam etmeli) üç uçak ister — o da ylp01 dönene kadar bekler,
> gerisini durdurmaz.

---

## 1. Düğüm düğüm karar

**21 birinci-parti düğüm var. 19'u gerekli.** Sim paketleri hariç neredeyse
hepsi lazım — çünkü görev dağıtık otonomi, görü, hassas iniş ve sürü üyelik
değişimi istiyor.

### ✅ Zaten sahada koşuyor — korunacak

| Düğüm | Rol | Not |
|-------|-----|-----|
| `px4_bridge` | Setpoint yürütücü + OFFBOARD | **Kanıtlanmış, ölçülmüş, ayarlanmış.** Aktüasyon katmanı bu kalacak |
| `esp32_bridge` | Mesh ↔ ROS köprüsü | **Genişletilecek** — bkz. §2 |
| `agent_fsm_node` | Ajan durum makinesi | Koşuyor |
| `basit_kacinma` | APF kaçınma | Kalması muhtemel — bkz. §3 |

### 🔴 Görev 1 için ZORUNLU — hiç koşmadı

| Düğüm | Satır | Neden zorunlu |
|-------|-------|---------------|
| `formation_node` | 926 | Formasyonu **onboard** hesaplar. Dağıtıklık şartının kalbi |
| `consensus_node` | 341 | Dağıtık lider seçimi. Merkezi lider = eksik puan |
| `path_planner` | 350 | Sonraki QR'a rota; `mission1`'in çıktısını `FormationCommand`'a çevirir |
| `maneuver_executor` | 444 | **Pitch/roll manevrası açık bir QR görevi** |
| `mission_fsm_node` | 598 | QR görev sırası (`team_id` filtresiyle) |
| `mission1_dynamic_swarm` | 499 | Görev 1 orkestratörü |
| `swarm_fsm_node` | 609 | Sürü durumu |
| `camera_driver` | 314 | **Gerçek kamerayı destekliyor** (`cv2.VideoCapture`), sim'e bağlı değil |
| `vision_node` | 407 | QR çözümleme **ve** kırmızı/mavi bölge tespiti — ikisi de şart |
| `precision_landing_node` | 271 | Renkli bölgeye hassas iniş; toleransın dışı = 0 puan |
| `task_reallocator_node` | 289 | Sürüden birey ayrılma/katılma |
| `swarm_origin_publisher` | 197 | Ortak origin |

### 🔴 Görev 2 için ZORUNLU

| Düğüm | Satır | Neden |
|-------|-------|-------|
| `mode_manager_node` | 501 | Sürü Hareket / Manevra modları |
| `joystick_interpreter_node` | 222 | RC → `SwarmControlCommand`; tek kumandayla tüm sürü |

### ⚠️ Karar bekleyen

| Düğüm | Durum |
|-------|-------|
| `collision_avoidance` (353) + `kinematic_fusion` (493) | `basit_kacinma`'nın yerine mi? **Ölçümle karar** — bkz. §3 |

### ❌ Alınmayacak

| Ne | Neden |
|----|-------|
| `network_proxy` (1403) | Simülasyonda ESP-NOW taklidi. Sahada yerini `esp32_bridge` alıyor |
| `sim_rtcm_source` (591) | Sahada yerini gerçek F9P alıyor |
| `gorev_kanit_ucus.py` | **Merkezi.** Finalde kullanılamaz. **Test aracı olarak kalır** — kuru test, çarpışma doğrulama, tek uçak ölçümleri |

`deploy/rpi/dagit.sh` ilk ikisini zaten bilerek dağıtmıyor.

---

## 2. Bilinen engeller ve ÇÖZÜMLERİ

Dört engel var. Dördünün de çözümü belli ve hiçbiri büyük değil.

### Engel 1 — `SwarmState` ve `MissionTarget` mesh'ten geçmiyor

**Ne bozuk:** Sürü düğümleri `/swarm/internal/...`'e yazıp
`/swarm/public/...`'ten okuyor (simülasyonda `network_proxy`, sahada
`esp32_bridge` köprüsü). `esp32_bridge` dokuz mesajı taşıyor ama bu ikisini
taşımıyor:

```
swarm_fsm   -> /swarm/internal/state              ->  ✗  ->  mode_manager, mission1
mission_fsm -> /swarm/internal/mission/next_target ->  ✗  ->  mission1
```

Bu hâliyle `mission1` sürü durumunu ve sıradaki hedefi asla göremez.

**✅ Çözüm: yerel remap. Kod değişikliği YOK, iki satır.**

Kodu okuyunca ortaya çıktı: bu iki değer **mesh'ten gelmesine gerek yok**,
çünkü her uçak kendi başına türetebiliyor:

- `swarm_fsm`, `SwarmState`'i **tüm uçakların `AgentStatus`**'undan üretiyor
  → `AgentStatus` zaten mesh'te
- `mission_fsm`, `MissionTarget`'ı **`QRMissionData`**'dan üretiyor
  → `QRMissionData` zaten mesh'te

```bash
ros2 run swarm_state_machine swarm_fsm_node --ros-args \
    -r /swarm/internal/state:=/swarm/public/state
ros2 run swarm_state_machine mission_fsm_node --ros-args \
    -r /swarm/internal/mission/next_target:=/swarm/public/mission/next_target
```

**Yan faydası:** bu, şartnamenin **dağıtıklık** şartına da uyuyor — ortak bir
durum yok, her uçak kendi hesaplıyor. Mesh'e paket eklemek merkezîleşme
yönünde bir adım olurdu.

**Maliyet:** `baslat.sh`'e iki satır. Geri alınabilir.

### Engel 2 — `px4_bridge` öncelik hakemliği yapmıyor

**Ne bozuk:** Dört düğüm aynı iki konuya setpoint yazacak:

```
/drone_N/control/setpoint/raw  <-  esp32_bridge · formation_node · precision_landing
/drone_N/control/setpoint      <-  basit_kacinma · collision_avoidance · mode_manager
```

`px4_bridge` gelen **son** setpoint'i alıyor; hangisi kazanacağı zamanlamaya
kalıyor.

**✅ Çözüm: mesajın kendi sözleşmesini uygula. ~30 satır.**

`AgentSetpoint`'te **`priority` alanı zaten var** ve sıra tanımlı:

```
FAILSAFE(100) > COLLISION_AVOIDANCE(80) > POSITION(30) > MANEUVER(20) > FORMATION(10)
```

Yani bu yeni bir tasarım değil, **uygulanmamış bir tasarımı uygulamak**.
Değişiklik `px4_bridge`'de tek yerde:

```python
# ONCE: tek slot
self._latest_setpoint = msg

# SONRA: kaynak basina slot
self._setpointler[msg.source] = (msg, simdi)

# Secim: TAZE olanlar arasinda en yuksek priority
def _aktif_setpoint(self):
    taze = [(m, t) for m, t in self._setpointler.values()
            if simdi - t < self._setpoint_bayat_s]
    return max(taze, key=lambda x: x[0].priority)[0] if taze else None
```

Bayatlık denetimi zaten var (`setpoint_fresh`); sadece kaynak başına
uygulanacak. **Bu değişiklik Faz 1'in ön koşulu** — onsuz hiçbir ikinci
üretici güvenle açılamaz.

**Maliyet:** ~30 satır, yerde test edilebilir (iki sahte yayıncı, hangisinin
kazandığına bak).

### Engel 3 — `formation_node` saf hız yayınlıyor, ileri-beslemesi yok

**Ne bozuk:** `formation_node`, `position_valid=False, velocity_valid=True`
yayınlıyor ve kendi denetleyicisi (SVT) **saf oransal**: `v = −0.8 × hata`.
Bu, `NAVIGASYON_KAYMA.md`'deki **Durum 1** — kalıcı kayma `v/0.8`,
`px4_bridge`'in yürütücüsünden (Durum 2, kayma ≈ 0) bile kötü.

Ayrıca `px4_bridge`'de `velocity_only` varsayılanı `False`, yani ikisi de
konum kontrolü yapar ve kazançlar toplanır (0.8 + 0.95 ≈ 1.75).

**✅ Çözüm: `formation_node`'u konum kipine al. Tek satır.**

```python
out = self._build_setpoint_msg(..., position_valid=True, velocity_valid=False)
```

O zaman iş bölümü temiz olur:
- `formation_node` **nereye** gidileceğini hesaplar (sürü zekâsı, onboard)
- `px4_bridge` **nasıl** gidileceğini yürütür (ölçülmüş, ayarlanmış)

Tek konum denetleyicisi kalır, kazanç toplanmaz, kayma ≈ 0'da kalır.

**Maliyet:** bir satır. SVT devre dışı kalır; istenirse sonra geri açılır.

### Engel 4 — İki kaçınma kodu, tek yuva

**Kaçınma ZORUNLU** (şartname: "İHA'ların çarpışmaması sağlanmalıdır").
Soru "kaçınma olsun mu" değil, **hangi kod olsun** — çünkü repoda aynı işi
yapan iki uygulama var ve **ikisi de aynı topic yuvasını** kullanıyor
(`/control/setpoint/raw` → `/control/setpoint`), yani aynı anda koşamazlar.

| | `basit_kacinma` (sahada) | `collision_avoidance` (sürü) |
|---|---|---|
| **Radyal itme** | yalnız **mesafeye** göre | mesafe **+ yaklaşma hızı** |
| Teğet ("sağa geç") | var, kapanma hızıyla ağırlıklı | var (`k_tan=0.9`) |
| **Dikey** | yok (bilerek) | var (`altitude_gate_m`) |
| Çıktı | konum ofseti, 6 m kelepçe | hız tabanlı, slew limitli |
| Komşu kaynağı | ham mesh `AgentStatus` | `NeighborInfo` ← `kinematic_fusion` |
| Varsayılan mesafeler | d0=8, hard=4 | d0=4.5, hard=2.0 |
| Sahada | uçtu | hiç |

**Asıl fark:** `collision_avoidance` radyal itmede **yaklaşma hızını** hesaba
katıyor. 5 m arayla duran iki uçak ile 5 m arayla saniyede 6 m kapanan iki
uçak — `basit_kacinma` ikisine aynı tepkiyi verir, `collision_avoidance`
ikincisinde çok daha erken iter.

**Dört seçenek:**

| | Ne | Artı | Eksi |
|---|----|------|------|
| A | `basit_kacinma` kalsın | Kanıtlanmış, gecikmesiz | Yaklaşma hızı radyalde yok, dikey yok |
| B | `collision_avoidance` + `kinematic_fusion` | Sürünün tam tasarımı | EMA → ~**0.4 s gecikme** |
| **C** | **`collision_avoidance`, ham `AgentStatus`'tan** | **Sürünün algoritması + sıfır gecikme** | ~20 satır adaptör |
| D | `basit_kacinma`'ya yaklaşma hızı ekle | En küçük değişiklik | Sürü kodu kullanılmamış olur |

**✅ Önerilen: C.** `AgentStatus` mesajında `vel_x/vel_y/vel_z` **zaten var**
— `NeighborInfo`'nun taşıdığı bilgi ham veride mevcut. `kinematic_fusion`'ın
tek kattığı EMA yumuşatması, o da gecikme demek. Adaptör:
`AgentStatus` → `NeighborObs`.

⚠️ **Parametreler ayarlanmadan açılmaz:** `collision_avoidance` 4.5 m'de
itmeye başlıyor, oysa `MIN_AYRIM_M` zaten 4.0. `basit_kacinma` 8 m'de
başlıyor. Bizim geometrimize (aralık 12 m) göre yeniden ayarlanmalı.

**Doğrulama — tek uçuş yeter:** ikisi gözlem modunda, aynı girdiyle, çıktılar
kayda. Sonra `--senaryo asili` ile operatör kumandayla yaklaşsın; hangisi ne
zaman ve ne kadar itiyor, kayıttan gör.

---

## 3. Test protokolü — yeterince, fazlası değil

Canlıda çalışıyoruz, o yüzden dikkatliyiz. Ama her aşama için **~2-3 uçuş**
yeter; daha fazlası zaman kaybı.

| Kademe | Ne | Süre | Risk |
|--------|----|----|------|
| **Y — Yerde** | Düğüm açılıyor mu, mantıklı değer üretiyor mu, RAM/CPU ne kadar | ~10 dk, uçuş yok | Yok |
| **G — Gözlem** | Kanıtlanmış zincir uçarken düğüm **arka planda**, çıkışı `/gozlem/`'e remap. Kayıttan karşılaştır | 1 uçuş | Düşük |
| **K — Komutta** | Üretici değişir. Tek uçak, alçak, kısa. Sonra iki uçak | 1-2 uçuş | Gerçek |

**Her uçuştan önce, istisnasız:**
```bash
./deploy/yki/param_karsilastir.py          # parametre ayrışması
python3 src/gcs/gorev_kanit_ucus.py --kuru --senaryo saha ...   # kuru test
```
İkisi de bedava ve saniyeler sürüyor.

**Gözlem modu nasıl kurulur:**
```bash
ros2 run swarm_core formation_node --ros-args -p agent_id:=1 \
    -r /drone_1/control/setpoint/raw:=/gozlem/drone_1/formation/raw
```
Düğüm gerçek telemetriyle gerçek kararlar üretir, ama uçağa ulaşmaz.

**Geri dönüş her zaman tek komut:** `/ws/suru_dugumleri` boşalt +
`docker restart`. Faza başlamadan önce bunun çalıştığı bir kez gösterilir.

---

## 4. Simülasyonun yerine: GÖZLEM MODU

Sim yok. Onun yerine her düğüm **çıkışı hiçbir yere bağlı değilken** gerçek
uçuş verisiyle çalıştırılır:

```bash
ros2 run swarm_core formation_node --ros-args -p agent_id:=1 \
    -r /drone_1/control/setpoint/raw:=/gozlem/drone_1/formation/raw
```

Kod gerçek telemetriyle gerçek kararlar üretir, ama uçağa ulaşmaz. Sonra
kayıttan üretilen ile uçulan karşılaştırılır.

**Her düğüm için dört kademe:**

| | Ne | Risk |
|---|---|---|
| **G0** | Yerde: açılıyor mu, RAM/CPU, parametre kabul ediyor mu | Yok |
| **G1** | Yerde gözlem: telemetri akarken çıktı üretiyor mu, mantıklı mı | Yok |
| **G2** | **Havada gözlem**: kanıtlanmış zincir uçarken arka planda | Düşük |
| **G3** | Havada komutta: üretici değişir, tek uçak, alçak, kısa | Gerçek |

**G2 atlanmaz.** Bu projede en pahalı ders "kod doğru görünüyor" ile "kod
doğru davranıyor" arasındaki farkın uçakla ödenmesi oldu.

**Geri dönüş her zaman tek komut:** `SURU_DUGUMLERI` boşalt + `docker restart`.

---

## 5. Ölçülen kaynak durumu (14 Ağustos, ylp00)

```
RAM 8062 MB toplam · 2094 kullanılan · 5967 kullanılabilir
Yük 0.95 (4 çekirdek) · 55 °C · düğüm başına ~190-218 MB RSS
```

19 düğüm kâğıt üstünde sığar ama **RSS paylaşılan kütüphaneleri sayıyor**;
gerçek artış çok daha az. Asıl darboğaz muhtemelen **CPU ve DDS trafiği**.
Her aşamada, o aşamanın düğümleri için ölç — tahmin etme.

---

## TÜM DÜĞÜMLER OKUNDU — bulgular

15 Ağustos'ta 19 düğümün tamamı okundu. Aşağıdakiler **koddan doğrulandı**,
tahmin değil.

### A. Ortam engeli — görü hiç çalışamaz

🔴 **`cv2` (OpenCV) ve `pyzbar` konteynerde KURULU DEĞİL.**
Canlı denendi: `ModuleNotFoundError`. `numpy` var (1.26.4).

`qr_detector.py` → `from pyzbar.pyzbar import decode`
`landing_zone_detector.py` + `frame_grabber.py` → `cv2`

Kamera gelmeden önce bu ikisi konteyner imajına eklenmeli.

### B. Parametre tuzakları — varsayılanlar bizim kuruluma uymuyor

| Düğüm | Parametre | Varsayılan | Bizde olmalı | Olmazsa |
|-------|-----------|-----------|--------------|---------|
| `consensus` | `battery_min_v` | **14.0** | **0.0** | Uçaklar 3.1 V okuyor → `battery_v > 0 and < 14` → **hiç kimse lider adayı olamaz, formasyon hiç çıkmaz** |
| `consensus` | `agent_count` | 3 | 2 | `full_field` hiç sağlanmaz; `bootstrap_grace_s` (1.5 sn) ile yine seçilir, ama gecikir |
| `swarm_fsm` | `agent_count` | 3 | **2** | 🔴 `formation_reached` şartı `active >= expected` → **2 uçakla ASLA true olmaz**, FORMING'den çıkılamaz. Ayrıca bir uçak bayatlarsa `1/3 < 0.5` → **FAILSAFE** |
| `task_reallocator` | `min_active_for_formation` | 3 | 2 | Formasyon kararı bloke |
| `mission1` | `default_spacing_m` | 5.0 | 12.0 | Aralık uyuşmazlığı |
| `joystick_interpreter` | — | `/mavros/manual_control/control` | remap gerek | Bizimki `/drone_N/mavros/...`, **namespace'siz dinliyor** |

### C. Kod kusurları

🔴 **`swarm_fsm.compute_formation_quality` sabit ofset kullanıyor:**
```python
OKBASI: 1:(0,0,0)  2:(-3,-3,0)  3:(-3,3,0)
CIZGI:  1:(0,0,0)  2:(0,-4,0)   3:(0,4,0)
```
3 m / 4 m aralık ve ajan id 1/2/3 varsayımı **gömülü**. Bizim aralık 12 m,
üstelik ofsetler **heading'e göre döndürülmüyor**. Sonuç:
`formation_max_error_m` daima büyük → `formation_stable` ve
`formation_reached` **yanlış**. Gerçek ofsetler `FormationCommand`'dan
alınmalı.

🔴 **`swarm_fsm._on_election` tek global seq sayacı kullanıyor:**
```python
if msg.sequence_num <= self._max_election_seq: return
```
Bu tam olarak `consensus`'ta **düzeltilmiş** olan hata (kaynak başına +
incarnation). `swarm_fsm`'de düzeltilmemiş → lider değişince ya da bir düğüm
yeniden başlayınca seçim mesajları **sessizce düşer**.

### D. Önceki iki iddiamın düzeltmesi

**1. "Çoklu üretici çakışması var, öncelik hakemliği şart" — abartılıydı.**
Çakışma **zaten çözülmüş**, ama `priority` alanıyla değil, **susturma**yla:
- `formation_node`, QR adımı MANEUVER iken **susuyor** → o an yalnız
  `maneuver_executor` yazar
- `formation_node`, kendi durumu DETACHED/PRECISION_LANDING/WAITING_REJOIN/
  REJOINING iken **susuyor**
- `precision_landing` yalnız `STATE_PRECISION_LANDING` iken yazıyor

Yani tasarım tek-yazıcıyı durum kapılarıyla garanti ediyor. Öncelik
hakemliği **acil değil**; yine de güvenlik ağı olarak değerli (bir kapı
kaçarsa sessiz çakışma yerine belirli davranış).

**2. "`formation_node`'un SVT'si saf oransal, ileri-besleme yok" — YANLIŞ.**
`_vff_x/y/z` var: rampanın 50 Hz hızından türetiliyor, LPF'den geçiyor ve
komuta ekleniyor (`svx + rvx + vff_x`). Yani **Durum 2**, kayma ≈ 0.

**Asıl kip sorunu başka:** `formation_node` C modu (saf hız,
`position_valid=False`) için tasarlanmış, ama **`px4_bridge._velocity_only`
varsayılanı `False`** → A modunda çalışır, PX4 de konum kontrolü yapar,
kazançlar toplanır (SVT 0.8 + MPC_XY_P 0.95).
**Çözüm: `velocity_only:=True`** — `baslat.sh`'te tek satır.

**3. `rel_enable = False` varsayılan** → `NeighborInfo` aboneliği hiç
kurulmuyor → `_peer_positions` None → **dağıtık slot ataması devre dışı**,
liderin ataması kullanılıyor. Kodun kendi notu: rel açıkken en yakın mesafe
**0.28 m** ölçülmüş (near-collision), kapatınca 2.68 m.
⚠️ Şartnamenin "dağıtık" puanı açısından tartışılmalı: mimari zaten dağıtık
(her uçak kendi setpoint'ini hesaplıyor), ama slot ataması liderden geliyor.

### E. Doğrulanmış bağımlılık zinciri

```
px4_bridge ──telemetri (offboard_active dahil, YEREL doğru)──► agent_fsm
     agent_fsm ──AgentStatus (DURUM ekler)──► esp32_bridge ──mesh──► herkes
          │
          ├─► consensus ─── lider seçer (ARMED+ şart, pil şartı)
          │        │
          │        ├─ ElectionResult ──► esp32_bridge LİDER KAPISI açılır
          │        │                     (yerde armlıyken DE olur)
          │        └─ LeaderHeartbeat ── yalnız AIRBORNE iken
          │
          └─► swarm_fsm ──SwarmState──► mission1, mode_manager

vision ──QRMissionData──► mission_fsm ──MissionTarget──► mission1
                                                   (SwarmState + lider şart)
                                                            │
                                            path_planner ◄──┘ (yörünge)
                                                  │
                              FormationCommand ──► esp32_bridge (lider kapısı)
                                                  ──mesh──► formation_node
                                                              │
                                          (origin_synced, xy/z_valid şart)
                                                              ▼
                                              kaçınma ──► px4_bridge
```

**Not:** `maneuver_executor` bir **ROS Action** ile tetikleniyor ve action
mesh'ten geçmiyor — her uçak kendi yerelini çağırır (mission1 her uçakta
koştuğu için mümkün).

---

## ENTEGRASYON SIRASI — 20 düğümün tamamı

Koşmakta olan dördü de listede. "Zaten var" bir düğümü listeden çıkarmak
yanlış olurdu — ikisinde düzeltme gerekiyor.

### ADIM 0 · Zaten koşan temel — ama düzeltmesiz ilerlenemez

| Düğüm | Durum | Gereken |
|-------|-------|---------|
| `px4_bridge` | ✅ koşuyor | Adım 3'te `velocity_only:=True` |
| `esp32_bridge` | ✅ koşuyor | Değişiklik yok — lider kapısı doğru çalışıyor |
| `basit_kacinma` | ✅ koşuyor | Adım 4'te `collision_avoidance` ile değişecek, **silinmeyecek** |
| **`agent_fsm_node`** | ✅ koşuyor | 🔴 **preflight pil düzeltmesi — Adım 1'DEN ÖNCE** |

✅ **`agent_fsm` preflight eşiği — düzeltildi (15 Ağustos).** Eşik artık
`ctx.battery_critical_voltage_v`'den geliyor, `≤ 0 → izleme yok` guard'ı
health_monitor ve `context.healthy` ile tutarlı.

⚠️ **Ama bunu "P0 uçuş engeli" diye sunmak yanlıştı.** Gerekçe olarak
"uçaklar 3.1 V okuyor" denmişti; **canlıda ölçülmedi**. Gerçek okuma
**65.535 V** — MAVLink'in "veri yok" sentineli (UINT16_MAX mV). Eski kodla
`65.535 < 13.6` yanlış olduğu için hata **hiç üretilmiyordu**; preflight
zaten geçiyordu. 3.1 V uydurma değil (`baslat.sh:300` yorumunda d3 için
geçmişte ölçülmüş) ama **bugünkü durum o değil**.

Yani bu **uykuda bir tuzaktı**, aktif bir engel değil. Düzeltme yine de
doğru: gömülü sabiti kaldırdı ve KARAR-03'te pil modülü gelince açmayı tek
parametreye indirdi.

> 📌 **Ders:** bir sayıyı önceki bağlamdan taşıyıp canlıda doğrulamadan
> teşhis kurma. `CLAUDE.md` §9 bunu zaten yasaklıyordu.

### ADIM 0.5 · `swarm_origin_publisher` — **ADIM 1'İN ÖN KOŞULU**

> Bu düğüm bu belgede **ADIM 8**'de yazıyordu. **Yanlıştı**, 15 Ağustos'ta
> yer testinde çıktı: `preflight_checker` `origin_synced` şart koşuyor —
> ```python
> if not ctx.sitl_mode and not ctx.origin_synced:
>     failures.append('Swarm origin senkronize değil')
> ```
> Origin gelmeden `IDLE → ARMING` **olmuyor**; ARMING olmadan ARMED
> olmuyor; ARMED olmadan ajan `ELIGIBLE_STATES`'e girmiyor ve consensus
> **hiç lider seçemiyor.** Sıra bu yüzden değişti.

**Nasıl açılır:** `echo "38.6905999 39.1611543 1216.03" > ~/yelpence_ws/origin`
ve `suru_dugumleri`'ne `origin` ekle. `fixed` modda yayınlanır.
**İki uçakta da AYNI koordinat** olmalı.

⚠️ **Geçici remap:** düğüm normalde `/swarm/internal/origin`'a yazar ve
`esp32_bridge` onu mesh'e verir — ama **yerel olarak `/public`'e geri
koymuyor**, yani uçak kendi origin'ini göremiyor (§2 Engel 1'in aynısı).
Köprü düzelene kadar `baslat.sh` doğrudan `/public`'e remap ediyor.

### ADIM 1 · `consensus_node` — ✅ **GEÇTİ (15 Ağustos, yer testi)**

`esp32_bridge` formasyonu **yalnız lidere** yazıyor; lider yoksa
`FormationCommand` mesh'e hiç çıkmaz.

**Şart:** `battery_min_v:=0.0` (→ `BATARYA_KRITIK_V`), `agent_count:=3`,
origin senkron, uçaklar ARM'lı, `yer_testi` açık.

> ⚠️ **`agent_count` 2 DEĞİL 3.** Önceki not "2 verilmeli" diyordu ve
> uygulansaydı ylp02 sürüden tamamen düşerdi: `consensus_node.py:133`
> `for aid in range(1, agent_count+1)` ile `drone1..droneN`'e abone oluyor,
> yani sayı "kaç uçak uçuyor" değil **"kimlikler 1..N"** demek. Uçaklarımız
> 1 ve 3. Eksik kadro seçimi engellemiyor (`election.py:101`,
> `bootstrap_grace_s` 1.5 sn).

**Ölçülen sonuç:**

```
ylp00: [CONSENSUS] Lider: 0 -> 1 (round=1, ben=1)
ylp02: [CONSENSUS] Lider: 0 -> 1 (round=1, ben=3)      101 ms arayla
ylp00: esp32_bridge  lider 0 -> 1 (BEN)   ← formasyon kapisi ACIK
ylp02: esp32_bridge  lider 0 -> 1
FSM (ikisinde de): ARMING -> ARMED -> (kill) FAILSAFE -> IDLE
```

**Bonus — lider arıza devri gözlendi:** kill switch ylp00'ı FAILSAFE'e
düşürdükten **82 ms sonra** kendi consensus'u
`Lider: 1 -> 3 (round=2)` dedi. `REASON_LEADER_FAULT` yolu çalışıyor.
ylp02 ikinci turu görmedi çünkü 784 ms sonra o da kill'lendi — **iki uçaklı
tam devir teslim testi ayrıca yapılmalı** (birini kill, diğerini armlı bırak).

**🔴 Test sırasında bulunan ve düzeltilen engel:** mesh `AgentStatus`
paketi `healthy` taşımıyordu; alıcı varsayılan `false` bırakıyordu ve
`is_eligible` bunu şart koştuğu için **hiçbir uzak ajan aday olamıyordu**
→ her uçak kendini seçerdi = **split-brain**. Ölçüm:
`ylp02 → mesh'ten drone1: state=4 healthy=FALSE`.
`esp32_bridge` decode'unda `healthy` artık **türetiliyor** (`ekf_ok` ∧
¬`kill_switch` ∧ state≠FAILSAFE); paket biçimi ve firmware değişmedi
(bayrak baytı 8/8 dolu).

### ADIM 2 · `swarm_fsm_node`
**Şart:** `agent_count:=2`, `SwarmState` remap'i
🔴 **Düzeltilmeli:** sabit formasyon ofsetleri, tek global election seq

### ADIM 3 · `path_planner` + `formation_node`
**Şart:** `px4_bridge velocity_only:=True`, `spacing_m` komutta 12 m
`compute_slot_offsets(tip, n, spacing, alpha)` — spacing komuttan geliyor ✅

### ADIM 4 · `collision_avoidance` — KARAR-01
`basit_kacinma` kapanır (aynı yuva), **silinmez**.

### ADIM 5 · `camera_driver` + `vision_node` — paralel
🔴 **Önce `cv2` + `pyzbar` konteynere kurulmalı** (canlı denendi, yok)

### ADIM 6 · `mission_fsm_node`
**Her iki görevi de o sürüyor** — `MissionType.DYNAMIC_SWARM` ve
`SEMI_AUTONOMOUS`. Yani Görev 2 de buna bağlı.

### ADIM 7 · `mission1_dynamic_swarm` — YKİ'nin yerini alır
### ADIM 8 · `swarm_origin_publisher` — YKİ kesilince
### ADIM 9 · `maneuver_executor` — Action, mesh'ten geçmiyor
### ADIM 10 · `precision_landing_node` — `ZoneMap` gerekli (5'e bağlı)
### ADIM 11 · `task_reallocator_node` — `min_active_for_formation:=2`, 3 uçak
### ADIM 12 · `joystick_interpreter` + `mode_manager` — Görev 2
`mode_manager` `/swarm/internal/mission/state` dinliyor (yerel, mesh yok) ✅

### Kullanılmayacak
`kinematic_fusion` · `network_proxy` · `sim_rtcm_source`

⚠️ **`kinematic_fusion` için tek çekince:** `formation_node`'un **dağıtık
slot ataması** `NeighborInfo` istiyor (`_peer_positions`), o da fusion'dan
geliyor. Ama abonelik `rel_enable` bayrağına bağlı ve o bayrak aynı zamanda
**göreli düzeltmeyi** de açıyor — kodun notu: rel açıkken en yakın mesafe
**0.28 m** ölçülmüş (near-collision), kapalıyken 2.68 m.

**Çözüm (~2 satır):** bayrağı ikiye ayır — `NeighborInfo` aboneliği her zaman
kurulsun (atama için), `_compute_relative_correction` `rel_enable`'a bağlı
kalsın. Böylece dağıtık atama açılır, tehlikeli düzeltme kapalı kalır.

---

## Açık sorular

| # | Soru | Faz |
|---|------|-----|
| 1 | `SwarmState`/`MissionTarget` — yerel remap mi, mesh mi? | 0 |
| 2 | `px4_bridge` öncelik hakemliği nasıl kurulmalı (bayatlık + öncelik)? | 0 |
| 3 | `consensus` açılınca `esp32_bridge` lider kapısı değişiyor mu? | 1 |
| 4 | `path_planner` zorunlu halka mı, atlanabilir mi? | 1 |
| 5 | `mode_manager` PX4 uçuş moduna **yazıyor mu**? | 6 |
| 6 | 19 düğüm açıkken CPU ve DDS trafiği yetiyor mu? | 0 |
| 7 | Kamera 120×120 QR'ı hangi irtifadan okuyor? | 3 |
| 8 | Kaçınma: `basit_kacinma` mı `collision_avoidance` mı? | 2 |
