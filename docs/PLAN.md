# PLAN — buradan finale

**Son güncelleme:** 29 Ağustos 2026, 19:40 — G2 kapsamı daraltıldı, param kontrolü saha gününe indi

## 1. Neredeyiz

> Repoda finali yapacak sürü yazılımı **zaten var**, ama simülasyon için
> yazıldı. İşimiz onu **kademeli ve canlı testlerle** gerçek uçaklara almak.

**Kısıt:** simülasyon yok. Her adım gerçek uçakta, ölçerek, geri alınabilir.

| | Durum |
|---|---|
| ylp00 · ylp01 · ylp02 | ✅ üçü de uçuyor (28 Ağustos'ta birlikte uçtular) |
| RTK · mesh · kayıt · YKİ arayüzü | ✅ çalışıyor |
| Kamera (ylp02) | ✅ takılı, QR **6-9 m**'de okunuyor |
| Pilot + kumanda (her uçak için) | ✅ var |

**Kapanan aşamalar:** ADIM 0 (zemin) · 0.5 (origin, mesh yolu dahil) ·
1 (consensus — lider seçimi + 82 ms'de arıza devri) · 2 (`swarm_fsm`) ·
**3 (formasyon — 26 Ağu ilk uçuş, 28 Ağu beş fazlı tam sekans)** ·
**4 (çarpışma önleme — dikey yol verme, üç uçaklı canlı testle)**.

Ölçümleri ve gerekçeleri git'te: `git show 783afab:docs/PLAN.md`

**Kalan iş `YAPILACAKLAR.md`'de**, öncelik sırasıyla. Bu belge *neden* öyle
yapıldığını anlatır, *bugün ne yapılacağını* değil.

> ℹ️ **Bölüm numaralarındaki boşluklar bilinçli.** §5 (test kademeleri),
> §6 (düğüm düğüm karar), §8 (ADIM'lar) ve §9 (navigasyon kayması) numaraları
> **kodun içinden** atıf alıyor (`px4_bridge.py`, `ucus_ayarlari.py`,
> `gorev_kanit_ucus.py`, `baslat.sh`, teşhis betikleri). 29 Ağustos
> sadeleştirmesinde kapanan bölümler çıkarıldı ama **kalanların numarası
> değiştirilmedi** — yoksa sadeleştirme koda taşardı.

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

## 4. Kalan aşamalar

| # | Aşama | Ne yapıyor | Risk |
|---|-------|-----------|------|
| **3** | Görü | Kamera, QR okuma, renkli alan tespiti | Yok — çoğu yerde |
| **4** | Görev mantığı | QR'ı oku → görevi yap → sonrakine git | Yüksek |
| **5** | Manevra + iniş + üyelik | Pitch/roll, hassas iniş, sürüden ayrılma | **En yüksek** |
| **6** | Görev 2 | Tek kumandayla sürü kontrolü | Orta |

**Sıra neden böyle:** en riskli en sona. Hassas iniş yere temas ediyor; ona
kademeli gidilir (önce 3 m). Görü kimseyi beklemiyor ama Aşama 4'ün ön koşulu.
Görev 2 formasyondan sonra paralel yürür.

**Geri dönüş her zaman tek komut:** `/ws/suru_dugumleri` boşalt +
`docker restart`.

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

**G2 uçağı SÜRECEK düğümler için atlanmaz.** Bu projede en pahalı ders,
"kod doğru görünüyor" ile "kod doğru davranıyor" arasındaki farkın uçakla
ödenmesi oldu. İlk kullanımında değerini kanıtladı: `formation_node` yerdeki
uçak için `vz = 1.51 m/s` üretti — gözlem modu olmasaydı bu bir tırmanma
komutuydu.

> **🟢 29 Ağustos 2026 — kapsam daraltıldı (operatör kararı).** Kural
> yazıldığında sürü zincirinin hiçbir parçası uçmamıştı; bugün formasyon ve
> kaçınma uçuyor. Artık:
>
> | Düğüm ne yapıyor | Kademe |
> |---|---|
> | Uçağa **setpoint yazıyor** (formasyon, kaçınma, mod yöneticisi) | G0 → **G2** → G3 |
> | Yalnız **hesap/durum** üretiyor (consensus, fsm, planner, görü) | G0 → G3 (G2 isteğe bağlı) |
>
> **G0 hiçbir koşulda atlanmaz** — uçuş gerektirmiyor ve en yüksek getirili
> kontrol o: 28 Ağustos'ta tek oturumda **dört gerçek hatayı** uçuşa
> çıkmadan yakaladı.

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

`./deploy/yki/param_karsilastir.py` — uçaklar aynı ayarda mı. **Uçuş başına
değil**: parametre yazıldıktan sonra ve saha gününde bir kez (`CLAUDE.md` §9).

Uçuş öncesi zorunlu **sekiz madde** ve kırmızı çizgiler: `CLAUDE.md` §9.

---

## 6. Düğüm düğüm karar

**19 birinci-parti düğüm var, hepsi gerekli.** Görev dağıtık otonomi, görü,
hassas iniş ve sürü üyelik değişimi istiyor. (Alınmayan iki düğüm — `basit_kacinma`
ve `kinematic_fusion` — 29 Ağustos'ta depodan **silindi**.)

### ✅ Zaten sahada koşuyor

| Düğüm | Rol | Not |
|-------|-----|-----|
| `px4_bridge` | Setpoint yürütücü + OFFBOARD | **Kanıtlanmış, ölçülmüş.** Aktüasyon katmanı bu kalacak |
| `esp32_bridge` | Mesh ↔ ROS köprüsü | Guided ARM → `EVENT_MISSION_STARTED` köprüsü eklendi (19 Ağu) |
| `agent_fsm_node` | Ajan durum makinesi | `kalkis_olayla=false` geçiş döneminde |
| `collision_avoidance` | Kaçınma + **zorunlu aktarım katı** | Dikey yol verme (KARAR-06). `/raw` → `/setpoint` köprüsü burası; boş bırakılamaz |
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
| `kinematic_fusion` | EMA yumuşatması ~0,4 s gecikme ekliyor — KARAR-01. **Silindi (29 Ağu)** |
| `basit_kacinma` | Yalnız `position_valid=True` setpoint'lerde çalışıyordu; formasyon saf hız kipinde sürdüğü için sürü zincirinde **zaten ölüydü**. **Silindi (29 Ağu)** |
| `network_proxy` · `sim_rtcm_source` | Simülasyon bileşeni; yerlerini `esp32_bridge` ve gerçek F9P alıyor. Silindi (16 Ağu) |

---

## 8. Kalan ADIM'lar — açılış sırası ve tuzakları

> ⚠️ **"N'i 2 yap" türü maddeleri uygulamadan önce KODU OKU.**
> `consensus.agent_count` için "2 yapılmalı" yazıyordu ve **yanlıştı** —
> uygulansaydı ylp02 sürüden tamamen düşerdi. `agent_count` "kaç uçak
> uçuyor" değil **"kimlikler 1..N"** demek. Her parametrenin o sayıyı hangi
> anlamda kullandığı (kimlik aralığı mı, canlı sayı mı, çoğunluk eşiği mi)
> tek tek doğrulanır.

### ADIM 5 · `camera_driver` + `vision_node`

Konteynerde `opencv` + `pyzbar` + **`zxing-cpp`** (birincil çözücü) artık
imaja gömülü — ama **yalnız ylp02'de**. Diğer ikisi `imaj_esitle.sh` bekliyor.
Ölçülmüş menziller ve rolling-shutter bulgusu: `KAMERA.md`.

### ADIM 6 · `mission_fsm_node`

**Her iki görevi de o sürüyor** — `MissionType.DYNAMIC_SWARM` ve
`SEMI_AUTONOMOUS`. Yani Görev 2 de buna bağlı. `team_id` filtresi
`vision_params.yaml`'daki `team_slot`'a bakıyor ve o değer **henüz bilinmiyor**.

### ADIM 7 · `mission1_dynamic_swarm` — YKİ'nin yerini alır

**Dağıtıklık şartının karşılığı bu adım.** `formation_node`'a girdi veren tek
düğüm bu ve KAPALI; `formation_node` bir hesap makinesi, tarif gelmezse hiçbir
şey yayınlamaz (`formation_node.py:878`).

🔴 **Yerde test EDİLEMEZ:** `orchestrator.decide()` yalnız
`NAVIGATE_TO_QR / ROTATE_TO_NEXT / EXECUTE_QR_TASK / RETURN_HOME`
durumlarında komut üretiyor; oraya ancak `SYNCHRONIZED_TAKEOFF` → tüm ajanlar
`IN_SWARM` olduktan sonra geliniyor. **En az 2 uçak ve UÇUŞ ister.**

Ara çözüm var: `deploy/rpi/teshis/form_yayinla.sh` tarifi **uçakta** üretip
düğümü besliyor — 18 Ağustos'ta bununla ölçüldü, slot hesabı 0,9 mm hatayla
doğru çıktı.

### ADIM 9 · `maneuver_executor`

ROS Action, mesh'ten geçmiyor — her uçak kendi yerelini çağırır.

### ADIM 10 · `precision_landing_node`

`ZoneMap` gerekli (ADIM 5'e bağlı). Toleransın dışı = 0 puan.

### ADIM 11 · `task_reallocator_node`

`min_active_for_formation:=2`, üç uçak ister.

### ADIM 12 · `mode_manager` + `joystick_interpreter` — Görev 2

Kod hazır, dört boşluğu kapatıldı (KARAR-11), **hiç koşmadı.** Sıra ve onay
soruları `YAPILACAKLAR`'da.

---

## 9. Navigasyon kayması — ölçüldü, kapandı

Uçak yürüyen setpoint'in arkasında kalmasın diye `px4_bridge` konum + hız +
ivme ileri-beslemesi yapıyor. 20 Ağustos'ta 30 m bacakta, iki uçakla ölçüldü:

| | ortalama |
|---|---|
| Kalıcı kayma | **≈ 0,10 m** |
| Tepe geçici hata | **≈ 1,12 m** (t+1,8 s) → ivme FF açıkken **0,55/0,32 m** |
| Oturma süresi | **≈ 3,5 s** → FF açıkken 3,1/1,0 s |

İvme ileri-beslemesi A/B ölçüldü (ylp00 açık, ylp02 kapalı referans): tepe
hata **−%60**, varış aşımı **−%61**. Varsayılan `1.0`; geri alma tek satır:
`GUIDED_IVME_FF=0.0`.

> **Düz bacak ne kadar olmalı:** `rampa = v²/a`, `oturma = 4τ×v`, `τ ≈ 1,05 s`.
> 2 m/s → 11 m · 3 m/s → 19 m · 4 m/s → **28 m** · 5 m/s → **38 m**.

### 🔴 Doygunluk payı — kalıcı kaymanın tek şartı

`v_ff + Kp×hata` `MPC_XY_VEL_MAX` tavanını **aşmamalı**. Seyir hızı tavana
eşitse konum düzeltmesine yer kalmaz, PX4 kırpar, kayma geri gelir.

```
seyir 3.0, tavan 5.0  ->  duzeltmeye 2.0 m/s pay    ✅
seyir 5.0, tavan 5.0  ->  duzeltmeye 0 m/s pay      ❌ kayma garanti
```

Kural: `PX4_HIZ_TAVANI_MPS ≥ GOREV_HIZ_MPS × 1.5`. `ucus_ayarlari.py` bunu
**hata** olarak veriyor.

---

## 12. Açık sorular

| # | Soru | Aşama |
|---|------|-------|
| 1 | `px4_bridge` öncelik hakemliği nasıl kurulmalı (bayatlık + öncelik)? | 4 |
| 2 | `path_planner` zorunlu halka mı, atlanabilir mi? | 4 |
| 3 | `mode_manager` PX4 uçuş moduna **yazıyor mu**? | 6 |
| 4 | 19 düğüm açıkken CPU ve DDS trafiği yetiyor mu? | hepsi |
| 5 | Saf dağıtığa geçilsin mi (liderin slot ataması hiç kullanılmasın)? | 5 |

> Ölçülen kaynak (14 Ağu, ylp00): RAM 8062 MB toplam / 2094 kullanılan,
> yük 0,95 (4 çekirdek), 55 °C, düğüm başına ~190-218 MB RSS. RSS paylaşılan
> kütüphaneleri sayıyor, gerçek artış daha az. **Her aşamada kendi düğümleri
> için ölç — tahmin etme.**

> **Çelişki varsa:** canlı belge referans belgeyi yener, **kod ikisini de yener.**
