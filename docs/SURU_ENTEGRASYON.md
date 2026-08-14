# SÜRÜ ENTEGRASYONU — yol haritası

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
G0 taramasında ölç, tahmin etme.

---

## SIRA — neden bu sırayla

İlke: **her adımda çalışan bir sistem kalsın.** Komut yoluna dokunmayanlar
önce, üretici değiştirenler sonra, en riskli en sona.

---

### AŞAMA 0 — Zemin (uçuş yok)

Bunlar sonraki her şeyi güvenli kılıyor; atlanırsa üstüne bir şey konmaz.

| # | İş | Maliyet |
|---|----|---------|
| 0.1 | **`px4_bridge` öncelik hakemliği** (Engel 2) | ~30 satır |
| 0.2 | `/ws/suru_dugumleri` dosyadan okunsun (env yerine) | ~10 satır `baslat.sh` |
| 0.3 | Kayıt filtresine `/gozlem/` ekle | 1 satır |
| 0.4 | İki remap (Engel 1) | 2 satır |
| 0.5 | **G0 taraması:** 19 düğümü tek tek Pi'de başlat | ~1 saat |

**Test (Y):** 0.1 için yerde iki sahte yayıncı — biri `priority=10`, biri
`priority=80`. `px4_bridge` hangisini seçiyor, logdan bak. Uçuş yok.

**Bilinen tuzak:** `path_planner`, `task_reallocator`, `swarm_fsm`,
`mission_fsm`, `mode_manager` **`agent_id` kabul etmiyor** (`baslat.sh`'te
not edilmiş). G0'da çıkacak.

**Çıkış şartı:** 19 düğüm de açılışta çökmüyor, RAM/CPU ölçüldü, hakemlik
çalışıyor.

---

### AŞAMA 1 — Bilgi katmanı (komut yolu DEĞİŞMEZ)

`swarm_origin_publisher` · `consensus_node` · `swarm_fsm` · `mission_fsm`

Bu dördü **setpoint üretmiyor** — sadece durum yayınlıyor. Yani açmak komut
yolunu değiştirmiyor. Sıfıra yakın risk, ve Aşama 2'nin girdisini hazırlıyor.

**Dikkat edilecek tek şey:** `consensus` açılınca `esp32_bridge`'in **lider
kapısı** davranışı değişebilir (seçim/heartbeat görmeden formasyon
yayınlamıyor). "Açınca hiçbir şey değişmez" varsayımının en zayıf olduğu yer.

**Test**
- **Y:** dördü açılıyor mu; `consensus` bir lider seçiyor mu; `swarm_fsm`
  mantıklı `SwarmState` üretiyor mu (uçak sayısı, centroid doğru mu)
- **G:** normal bir görev uçuşu, dördü arka planda. Kayıttan bak: lider
  seçimi uçuş boyunca stabil mi, formasyon yayını bozuldu mu

**Çıkış şartı:** İki uçak havadayken lider seçimi kararlı, `SwarmState`
akıyor, kanıtlanmış zincir etkilenmemiş.

---

### AŞAMA 1B — Kaçınma değişimi

📋 **KARAR VERİLDİ** — `docs/KARARLAR.md` → **KARAR-01**.
Bu aşamaya gelince operatöre hatırlat ve önerilen seçeneği söyle.

**Karar özeti:** `collision_avoidance`, **ham `AgentStatus`'tan** beslenerek
(`kinematic_fusion` atlanır). `basit_kacinma` kapatılır ama **silinmez**.

**Parametreler — operatör talimatı:** `d0_m = 8.0`, `hard_m = 4.0` ile başla
(varsayılan 4.5/2.0 bizim geometrimize göre çok dar). Güven oluştukça kısılır.

⚠️ Aralık 12 m'de planlanan en yakın yaklaşma **8.41 m**; `d0=8.0` ile pay
yalnız 0.49 m. İlk uçuşta kaçınmanın **ne zaman** tetiklendiğine bak —
her formasyon geçişinde tetikleniyorsa `d0` 7.0'a inecek.

**Neden Aşama 2'den önce:** kaçınma değişimi **kanıtlanmış komut zinciri
uçarken** test edilir. Bir şey ters giderse sebebi tektir. Aşama 2 ile
birleştirmek "bir aşamada bir üretici değişir" kuralını bozardı.

**Test (KARAR-01'de ayrıntılı, zorunlu):**
- **Y:** adaptör doğru mu — 10 m'de itme 0, 6 m'de doğru yönde
- **G:** ikisi yan yana, `collision_avoidance` gözlem modunda, çıktılar karşılaştırılır
- **K:** `--senaryo asili` + operatör kumandayla yaklaştırır
- **K2:** iki uçak, saha senaryosu

---

### AŞAMA 2 — Formasyon üreticisi değişimi 🔴 EN BÜYÜK

`formation_node` — setpoint kaynağı YKİ'den uçağa geçiyor.

Bu, **görevi merkeziden dağıtığa çeviren adım.** Şartnamenin asıl istediği şey.

**Ön koşullar:** Aşama 0.1 (hakemlik) + Aşama 1 (lider seçimi) +
Engel 3 çözümü (konum kipine al).

**Test**
- **Y:** `formation_node` gözlem modunda, uçaklar yerde. Ürettiği slot
  konumları mantıklı mı (aralık 12 m, doğru geometri)
- **G:** normal görev uçuşu, `formation_node` gözlem modunda.
  **Kayıttan karşılaştır:** onun ürettiği slot ile YKİ'nin gönderdiği hedef
  arasındaki sapma kaç metre. Bu sayı Aşama 2'nin geçme kriteri
- **K1:** tek uçak, alçak (5 m), kısa. Setpoint kaynağı `formation_node`
- **K2:** iki uçak, tam saha senaryosu

**Çıkış şartı:** İki uçak, formasyon onboard hesaplanarak, formasyon
rotasyonu dahil bir rotayı uçtu. Kritik ayrım eşiğin üstünde kaldı.

---

### AŞAMA 3 — Görü (PARALEL KOL, komut yolu dışında)

`camera_driver` · `vision_node`

Aşama 1-2 ile **aynı anda** ilerleyebilir; kimseyi beklemiyor. Ama Aşama 4'ün
ön koşulu.

**Test — çoğu yerde yapılır, uçuş gerekmez**
- **Y1:** kamera açılıyor mu, görüntü akıyor mu
- **Y2:** **QR'ı elde tutup okut.** 120×120 cm QR'ı hangi mesafeden
  okuyabiliyoruz — ölç. Bu sayı görev irtifasını belirleyecek
- **Y3:** kırmızı/mavi bölge tespiti, gerçek zeminde, gerçek ışıkta
- **G:** bir uçuşta kamera açık, QR üzerinden geç, kayıttan doğrula

**Kritik ayar:** `team_id` üç yerde de `752825` olmalı (`esp32_bridge`,
`mission_fsm`, `mission1`) — ayrışırsa gelen her QR reddedilir.

---

### AŞAMA 4 — Görev mantığı

`path_planner` · `mission1_dynamic_swarm`

Artık YKİ "başlat" der, gerisini uçak yapar. Görev 1'in kendisi.

**Test**
- **Y:** kuru koşum — orkestratör adım üretiyor mu, sıra şartnameye uygun mu
  (formasyon → pitch/roll → irtifa → üyelik → sonraki QR)
- **G:** iki QR'lık kısa rota, gözlem modunda
- **K:** iki QR'lık rota, gerçek. Sonra dört, sonra tamamı

**Adım adım:** tüm görevi tek seferde denemek yerine iki QR ile başla.

---

### AŞAMA 5 — Manevra, hassas iniş, üyelik

`maneuver_executor` · `precision_landing_node` · `task_reallocator_node`

Bunlar QR görevlerinin kendisi. En riskli olan hassas iniş — yere temas var.

**Test**
- **Y:** `precision_landing` gözlem modunda, uçak yerde, renkli hedef önünde.
  Ürettiği düzeltme doğru yöne mi
- **K (kademeli):** önce 3 m'den renkli bölgeye iniş denemesi, tek uçak.
  Sonra tam senaryo: ayrıl → in → disarm → bekle → arm → katıl

**`task_reallocator` üç uçak gerektiriyor** — ylp01 dönmeden tam denenemez.

---

### AŞAMA 6 — Görev 2: yarı otonom kumanda

`joystick_interpreter_node` · `mode_manager_node`

Görev 1'den bağımsız; istenirse Aşama 4 ile paralel yürütülebilir.

**Test**
- **Y:** kumandayı oynat, `SwarmControlCommand` üretiliyor mu, mesh'e çıkıyor mu
- **K1:** tek uçak, kumandayla sürü hareket modu
- **K2:** iki uçak, senkron tepki. Hakem direktiflerinden birkaçını dene
  (3 sn ileri pitch, çizgi formasyonuna geç, yaw manevrası)

---

## Bağımlılık haritası

```
AŞAMA 0  zemin (hakemlik, remap, G0 taraması)
   |
AŞAMA 1  origin + consensus + swarm_fsm + mission_fsm ...... komut yolu değişmez
   |
AŞAMA 1B kaçınma değişimi (KARAR-01) ...................... komut yolunda, izole
   |
AŞAMA 2  formation_node ................................... MERKEZİ -> DAĞITIK
   |
AŞAMA 4  path_planner + mission1 .......................... GÖREV 1
   |
AŞAMA 5  manevra + hassas iniş + üyelik ................... GÖREV 1 tamamlanır

AŞAMA 3  görü ............... PARALEL, Aşama 4'ün ön koşulu
AŞAMA 6  görev 2 ............ PARALEL, Aşama 2'den sonra

```

**Kaba bütçe:** aşama başına 2-3 uçuş → toplam ~15 uçuş. Aşama 0 ve 3'ün
çoğu yerde yapılıyor.

---

## Her aşamada uyulacak kurallar

1. **Bir aşamada bir üretici değişir.** İki değişiklik aynı uçuşa girmez
2. **Y → G → K sırası atlanmaz.** Özellikle G
3. **Her kademe ölçümle kapanır.** "Çalıştı" değil, sayı
4. **Geri dönüş aşamaya başlamadan önce bir kez gösterilir**
5. **Uçuştan önce:** `param_karsilastir.py` + kuru test
6. **Aşama sonunda** `DURUM.md` + `GUNLUK.md` + `RPI_ESITLEME.md` güncellenir

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
