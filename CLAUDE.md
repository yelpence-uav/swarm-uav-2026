# Yelpençe — TEKNOFEST 2026 Sürü İHA

**Son güncelleme:** 23 Ağustos 2026, 20:30

> Bu dosyayı Claude Code her oturumda **kendiliğinden okur**. Yeni bir sohbet
> açan kişinin hiçbir şey söylemesine gerek yok; buradan projeyi anlar.
> Kısa tutuluyor — ayrıntı `docs/` altında, aşağıda haritası var.

---

## 1. Ne yapıyoruz

Takım **Yelpençe**, takım numarası **752825**. TEKNOFEST 2026 Sürü İHA
Yarışması. Üç çok rotorlu İHA bir sürü olarak otonom görev yapıyor.

**Uçuş kanıtı geçildi.** Sıradaki hedef **final görevi**.

### 🔴 Bugünkü mimari finalde KULLANILAMAZ

Şartname iki kural koyuyor ve ikisi de mevcut komut yolumuzu geçersiz kılıyor:

> *"**Dağıtık** sürü algoritması kullanılması gerekmektedir. **Merkezi**
> sürü algoritmaları **eksik puan** olarak değerlendirilecektir."*
>
> *"Hakemler görev sırasında herhangi bir anda **yer kontrol istasyonu
> bağlantısını kesecektir**."*

Bugün YKİ (`gorev_kanit_ucus.py`) her uçağa mesh'ten `goto` gönderiyor —
**hem merkezi hem YKİ'ye bağımlı.** Hakem bağlantıyı kestiği anda sürü durur.

**Yani onboard sürü düğümleri opsiyonel değil, ZORUNLU.** YKİ'nin izinli tek
rolü "görevi başlat" komutu. `gorev_kanit_ucus.py` bundan sonra **test aracı**
(kuru test, çarpışma doğrulama, tek uçak ölçümü) — yarışma yolu değil.

Ayrıntı ve düğüm düğüm karar: `docs/PLAN.md` §6.

Yol şu: repoda finali yapmak için yazılmış tam bir sürü yazılımı var, ama o
yazılım **simülasyon için yazıldı ve sahada hiç koşmadı**. Uçuş kanıtı için
onun yerine daha basit, doğrudan bir komut yolu yazıldı ve o uçtu. Şimdi iş,
sürü kodlarını **kademeli ve canlı testlerle** sahaya almak.

**Simülasyon kullanılmayacak.** Karar operatörün: her şey gerçek uçakta,
ölçerek, küçük ve geri alınabilir adımlarla. Bu yüzden "sim'de dene" asla
geçerli bir cevap değil — bkz. `docs/PLAN.md` §5.

---

## 2. Donanım ve kimlikler

| İHA   | agent_id | Konteyner | ROS ns      | ESP mesh ID | Durum |
|-------|----------|-----------|-------------|-------------|-------|
| ylp00 | 1        | `drone1`  | `/drone_1`  | 1           | uçuyor |
| ylp01 | 2        | `drone2`  | `/drone_2`  | 2           | **YERDE — 2 Ağustos'ta düştü** |
| ylp02 | 3        | `drone3`  | `/drone_3`  | 3           | uçuyor |

**İsim ile numara aynı değil**: ylp00 → drone**1**, ylp02 → drone**3**.
Bu karışıklık gerçek ve sürekli hata kaynağı — komut yazmadan önce bak.

Her İHA: ESP32 (ESP-NOW mesh) + Raspberry Pi 5 (ROS 2 Jazzy, Docker) +
Pixhawk FMUv3 (PX4 1.16.1) + Here4 DroneCAN GPS.
YKİ = yer istasyonu dizüstü. Base ESP mesh ID = **10**.

### Drone'a bağlanmak

**IP ezberleme, betiği kullan.** IP'ler her ağda değişiyor:

```bash
./deploy/yki/drone_bul.sh ylp00 'komut'   # Claude bunu kullanır
./deploy/yki/drone_bul.sh --durum         # disk, konteyner, bayraklar
./deploy/yki/drone_bul.sh                 # menü, seç, bağlan (insan için)
```

Önbellek → mDNS → MAC taraması sırasıyla dener; sonuncusu her zaman çalışır.
Erişim, MAC'ler, portlar, QGC ayarı: **`docs/cihazlar.md`**.

---

## 3. Şu an sahada gerçekten ne koşuyor

Bu listeyi ezberle. Repoda 19 ROS düğümü var; uçakta **on biri** açık:

```
mavros_node            MAVLink <-> ROS
px4_bridge             setpoint yürütücü + OFFBOARD  (swarm_control)
agent_fsm_node         ajan durum makinesi           (swarm_state_machine)
esp32_bridge           mesh <-> ROS köprüsü          (swarm_control)
collision_avoidance    DİKEY yol verme + yatay son çare  (swarm_core)
ic_dis_kopru           internal -> public yerel döngü
swarm_origin_publisher · consensus_node · swarm_fsm_node
formation_node · path_planner            (yalnız hesap, uçağı sürmüyor)
```

**11 düğüm** (+ MAVROS eklentileri). 23 Ağustos'ta ölçüldü.

> **`basit_kacinma` 21 Ağustos'ta KAPATILDI** (ADIM 4, KARAR-01). Yerine
> `collision_avoidance` koşuyor; 23 Ağustos'ta **dikey yol vermeye**
> geçirildi (KARAR-06, `docs/CA.md`). Silinmedi — beklenmedik davranışta
> tek dosya değişikliğiyle geri dönülür.
>
> Dikkat: o yuva aynı zamanda **zorunlu bir aktarım katı** —
> `/control/setpoint/raw` ile `/control/setpoint` arasındaki tek köprü orası.
> "Kaçınmayı kaldır" diye bir seçenek yok; yalnızca *değiştir* var. Boş
> bırakılırsa `formation_node`'un setpoint'leri px4_bridge'e hiç ulaşmaz.

Diğer **sürü düğümleri kapalı**. `deploy/rpi/baslat.sh` içindeki
`SURU_DUGUMLERI` değişkeniyle adı verilerek açılırlar; varsayılan boş.

### Komut yolu (kanıtlanmış, uçan yol)

```
YKİ: src/gcs/gorev_kanit_ucus.py
  -> REST -> backend (:8000) -> base ESP -> ESP-NOW mesh
  -> esp32_bridge -> /drone_N/control/setpoint/raw
  -> collision_avoidance -> /drone_N/control/setpoint
  -> px4_bridge -> MAVROS -> PX4 (OFFBOARD)
```

Kaçınma düğümü `collision_avoidance` (`suru_dugumleri`'nde `ca`).
`/ws/kacinma` dosyası **YOK** — `kacinma.adim4_oncesi` olarak kenarda.

---

## 4. En kritik teknik gerçek — sürü kodlarını açmadan önce

`/drone_N/control/setpoint/raw` ve `/drone_N/control/setpoint` konularının
**ikişer olası üreticisi var** ve bunlar birbirini bilmiyor:

| Konu | Bugünkü üretici (saha) | Sürü tasarımındaki üretici |
|------|------------------------|----------------------------|
| `.../setpoint/raw` | `esp32_bridge` (remap ile) | `formation_node` |
| `.../setpoint`     | `collision_avoidance`      | `collision_avoidance` |

**İkisi aynı anda açılırsa** px4_bridge 50 Hz'de iki farklı algoritmadan
gelen çelişkili setpoint'leri sırayla alır ve hangisinin kazandığı zamanlamaya
kalır. Bu bir teori değil, topic adları birebir aynı — doğrulandı.

**Kural: bir konuya aynı anda tek üretici.** Sürü zincirini açarken karşılığı
olan mevcut düğümü KAPATMAK zorundasın. Ayrıntı ve geçiş sırası:
`docs/PLAN.md` §7.

---

## 5. Çalışma düzeni (takım kuralı)

Tek bilgisayar, tek kişi, sırayla. Paralel çalışma yok. Bu yüzden **devir
teslim yazıyla oluyor**:

**Oturuma başlarken** — Claude bunları okur, sen de oku:
1. `docs/DURUM.md` — şu an ne çalışıyor, ne bozuk, hangi bayrak açık
2. `docs/GUNLUK.md` — en üstteki kayıt: son kişi ne yaptı, nerede bıraktı
3. `docs/YAPILACAKLAR.md` — sıradaki iş

**Oturumu bitirirken** — bu adım atlanırsa sistem çöker:
1. `docs/GUNLUK.md`'ye **en üste** yeni kayıt (şablon dosyanın içinde)
2. Değişen bir şey varsa `docs/DURUM.md` güncelle
3. Biten işi `docs/YAPILACAKLAR.md`'de işaretle, yeni çıkanları ekle —
   **her maddeye önem derecesi ver**: 🔴P0 uçuş engeli · 🟠P1 acil ·
   🟡P2 önemli · ⚪P3 ileride. Seviyesiz madde ekleme; seviyesiz liste bir
   süre sonra kimsenin okumadığı bir yığına dönüşüyor.
4. Uçakta bir ayar değiştiysen (`/ws/kacinma`, parametre, `tgt_system`)
   **mutlaka** `DURUM.md`'ye yaz — sonraki kişi uçağı öyle bulacak

Claude'a "oturumu kapat" dersen bu dördünü o yapar.

### ⚠️ Pi'ye elle bir şey yaptıysan → `docs/RPI_ESITLEME.md`

Hep bütün uçaklarla çalışmıyoruz. Şu an ylp01 yerde; yarın o dönüp başkası
gidebilir. **Geride kalan uçak, dönene kadar yapılan her şeyi kaçırır.**

Bu yüzden bir Pi'de yapılan her değişiklik — paket, bayrak dosyası, sysctl,
Wi-Fi, PX4 parametresi — `RPI_ESITLEME.md`'ye **hangi uçaklarda olduğu**
bilgisiyle yazılır. Geri gelen uçak için tek yapılacak o listeyi yürütmek.
Yazılmayan değişiklik, sonradan saatlerce süren "neden bunda çalışmıyor"
arayışına dönüşüyor.

---

## 6. Belge haritası

**Tam harita `README.md`'de** — hangi soruya hangi belge, tek tabloda.
Burada yalnız Claude'un sık kullandıkları:

| Dosya | Ne için |
|-------|---------|
| **`docs/PLAN.md`** | **Ana plan + teknik yol haritası** — 8 aşama, düğüm düğüm karar, ADIM 0-12, navigasyon kayması. Yeni gelen buradan başlar |
| `docs/DURUM.md` | Şu anki durum: ne çalışıyor, ne bozuk, hangi bayrak açık |
| `docs/GUNLUK.md` | Oturum devir teslim kaydı — kim, ne zaman, ne yaptı |
| `docs/YAPILACAKLAR.md` | Öncelikli iş listesi (🔴P0 · 🟠P1 · 🟡P2 · ⚪P3) |
| `docs/KARARLAR.md` | **Verilmiş ama henüz uygulanmamış kararlar** — sırası gelince operatöre hatırlat |
| **`docs/CA.md`** | **Çarpışma önleme** — dikey yol verme tasarımı, yer testleri, açık sorular |
| **`docs/TUZAKLAR.md`** | **Hata vermeden yanlış sonuç üretenler.** Bir şey "çalışmıyor ama hata da vermiyor" ise ÖNCE buraya bak |
| `docs/RPI_ESITLEME.md` | Pi'lerde ne yapıldı, hangi uçakta var |
| `docs/cihazlar.md` | Kimlik tablosu, SSH, MAC, port, QGC, sysid |

**Çelişki varsa:** canlı belge referans belgeyi yener, **kod ikisini de yener.**

> ### 🔒 İKİ BELGE KORUMALI — kendiliğinden OKUMA
>
> `docs/MESH_PROTOKOL_KARARLARI.md` (1542 satır) ve
> `docs/YELPENCE_RTCM_SPEC.md` (841 satır) **yalnız operatör açıkça
> isteyince** okunur. Keşif sırasında, "bir bakayım" diye, grep sonucu
> ilginç göründü diye **açılmaz.**
>
> **Neden:** ikisi toplam ~2400 satır ve bağlamı doldurup asıl işe yer
> bırakmıyor. İçerikleri değerli ama **nadiren** gerekli — mesh paket
> formatı ya da RTCM zinciri üzerinde çalışılmadıkça.
>
> Bir soru bu belgelerden birini gerektiriyorsa **operatöre sor**, kendin
> açma. (`.claude/korumali_belgeler.sh` bekçisi zaten izin sorduruyor;
> istem çıktığında operatör istemediyse **reddeder** — bu bir hata değil,
> kuralın çalışması demektir.)

> 🔀 **20 Ağustos birleştirmesi:** `SURU_ENTEGRASYON.md` ve
> `NAVIGASYON_KAYMA.md` **SİLİNDİ** — içerikleri `PLAN.md`'nin içinde
> (§6-§8 entegrasyon sırası, §9 navigasyon kayması). Kodda o adlara yapılan
> atıflar da `PLAN.md`'ye çevrildi.
>
> ⚠️ `ARCHITECTURE.md` bu depoda **yok** — sim dönemine ait. Birisi bu üç
> addan birini ararsa `PLAN.md`'ye yönlendir.

**Ekran görüntüsü**: `ss/` klasörüne at, sohbette söyle. Bkz. `ss/README.md`.

---

## 7. MİSYON ve çalışma ilkeleri

**Misyon:** Repodaki sürü kodlarını, **şartnameye uygun** şekilde, **en
güvenli** yoldan drone'lara entegre etmek. Başka bir hedef yok; kararlar
buna göre verilir.

### Hiçbir şey dokunulmaz değil

`px4_bridge`, `esp32_bridge`, `agent_fsm_node`, `basit_kacinma` — bunlar
"en iyisi" oldukları için değil, **uçuş kanıtını geçirdikleri için**
oradalar. Gerekirse tamamı değişir. ESP32 firmware'i de dahil. Tek ölçüt
şartnameye uygunluk ve güvenlik.

Bir düğümün tamamını atıp yeniden yazmak gerekiyorsa **bu bir başarısızlık
değil**, doğru karardır. "Mevcut kod böyle" bir gerekçe değildir.

### Sorun bildirirken: sorun + çözüm birlikte

Sorunları mutlaka söyle — operatör hangi hatanın çıkacağını önceden bilemez.
**Ama sorunu kucağına bırakma.** Her sorunla birlikte:

1. Ne bozuk, somut olarak
2. **Tahmini çözüm** ve nasıl uygulanacağı
3. Maliyeti (kaç satır, kaç uçuş, geri alınabilir mi)

Çözülemeyecek bir şey değilse **kara haber gibi verme.** "Şu çakışma var,
çözümü şu, maliyeti şu kadar" — bu doğru biçim. Sadece "şu çakışma var"
demek işi operatöre yıkmaktır.

### 🧠 Effort daima `max` (KARAR-02)

`/effort` menüsü **hep `max`** kalır; ultracode menüden açılmaz. İkisi aynı
listede ve birbirini dışlıyor — ultracode seçilince effort `xhigh`'a düşüyor.

Çok ajanlı denetim gerektiğinde operatör **o mesajın içine `ultracode`
kelimesini yazar**; sonraki tur kendiliğinden `max`'a döner.

**Claude'un görevi:**

- Effortunu okuyabilirsin: `echo $CLAUDE_EFFORT`. **`max` değilse operatöre
  hemen söyle.** (`.claude/settings.json`'daki hook bunu zaten uyarıyor, ama
  uyarıyı gördüğünde sen de yaz.)
- **ADIM 1 (`consensus`), ADIM 3 (`formation_node`), ADIM 4
  (`collision_avoidance`)** — bu düğümler ilk kez havaya kalkmadan önce
  operatöre "bu mesaja `ultracode` yazar mısın?" diye sor. Gerekçe ve diğer
  seçenekler `docs/KARARLAR.md` **KARAR-02**'de.
- Belge, config, kurulum işlerinde **önerme** — orada israf.

### 📅 Her .md değişikliğinde en üste tarih-saat

Bir `.md` dosyasında değişiklik yaptıysan, **dosyanın en başına**
(başlıktan hemen sonra) güncelleme damgasını yaz veya güncelle:

```markdown
# <Başlık>

**Son güncelleme:** 15 Ağustos 2026, 01:28
```

**Neden:** tek bilgisayarda sırayla çalışıyoruz. Bir belgeyi açan kişinin
ilk sorusu "bu ne kadar taze?" oluyor. Saat-dakika olmadan aynı günün
sabahı ile gecesi ayırt edilemiyor — ve bu projede bir gün içinde çok şey
değişiyor.

**Kural:**
- **Her canlı belge** (`PLAN`, `DURUM`, `GUNLUK`, `YAPILACAKLAR`,
  `KARARLAR`, `TUZAKLAR`, `RPI_ESITLEME`, `cihazlar`, `CLAUDE.md`,
  `README.md`) bu damgayı taşır
- **Arşiv belgelerine dokunma** — onlar zaten donduruldu
- Saat **Europe/Istanbul**
- Damgayı güncellemeyi unutma: içerik değişti ama tarih eskiyse belge
  olduğundan taze görünür, bu yanıltıcıdır

### Karar verildiyse hatırlat, sıfırdan tartışma

Sohbette verilen kararlar oturum bitince kaybolur. `docs/KARARLAR.md` onları
tutuyor.

**Bir aşamaya/işe gelince ÖNCE oraya bak.** O işle ilgili karar varsa:

1. **Operatöre söyle** — "bu konuda şu karar verilmişti"
2. **Önerilen seçeneği belirt** ve gerekçesini hatırlat
3. Operatör başka bir seçenek isterse **o an detaylıca konuşulur**

Kararı sessizce uygulama, ama her seferinde baştan da tartışma.

**Yeni önemli karar çıkarsa oraya yaz** — özellikle *"şimdi değil, sırası
gelince"* denilenleri. Kaybolması en kolay olanlar onlar.

### Test: en küçük yeterli manevra

Canlıda test ediyoruz. Ölçüt **bir sonraki adımın güvenli olduğunu gösterecek
EN AZ test** — ne fazlası ne eksiği.

**Uçuşu tasarlarken sıra:**

1. *Bu uçuş hangi tek soruyu cevaplıyor?* — bir soru, bir uçuş
2. *Yerde cevaplanabilir mi?* — cevaplanabiliyorsa **uçulmaz** (G0/G1)
3. *En kısa hangi manevra cevaplar?* — o uçulur

| Soru | Yeten manevra |
|---|---|
| Düğüm açılıyor mu, mantıklı değer üretiyor mu | **Uçuş yok** — G0/G1 yerde |
| Havada ne üretiyor (komuta bağlı değil) | **Kalk – asılı dur – in** |
| Setpoint takibi, kayma, aşım | **Tek düz bacak, git-gel** |
| Formasyon doğru mu | **Tek formasyon**, tek geçiş |
| Lider seçimi/devri | **Kalk – asılı dur**, kill ile devret |

**Uzun uçuş kendi başına bir değer değil, kendi başına bir risktir.** Her ek
bacak yeni bir arıza yüzeyi açar ve pil yakar. *"Madem havadayız, şunu da
deneyelim"* **yasak** — o bir sonraki uçuşun işi.

Aynı uçuşta **iki değişiklik denenmez.**

Kademeler ve gözlem modu: `docs/PLAN.md` §5.
🔴 Uçuş öncesi zorunlu sekiz madde: **§9**.

## 8. Uçuş ayarları tek yerden

**Hız, ivme, formasyon aralığı ve eğim tavanları `src/gcs/ucus_ayarlari.py`'de.**
Başka hiçbir yerde elle yazılmaz — `gorev_kanit_ucus.py` bunları oradan alıyor.

```bash
python3 src/gcs/ucus_ayarlari.py          # çözümleme + tutarlılık denetimi
python3 src/gcs/ucus_ayarlari.py --px4    # uçaklara yazılacak param komutları
python3 src/gcs/ucus_ayarlari.py --kabuk  # baslat.sh için env satırları
```

### Uçuş sırasında ayar değiştirmek

Yürütücü ayarları **canlı** değiştirilebilir; konteyner yeniden başlatmaya
gerek yok (14 Ağustos'ta eklendi):

```bash
./deploy/yki/drone_bul.sh ylp00 \
  'docker exec -i drone1 bash -lc "source /opt/ros/jazzy/setup.bash && \
   python3 - --ns /px4_bridge --yaz guided_hiz_yatay_mps=4.0"' < src/gcs/px4_param.py
```

Canlı olanlar: `guided_hiz_yatay_mps`, `guided_hiz_dikey_mps`,
`guided_ivme_yatay_mps2`, `guided_ivme_dikey_mps2`, `guided_tasma_m`,
`guided_konum_kp`, `guided_telafi_orani`. Diğer her parametre **reddedilir**
(kimlik, kill/arm kanalları, kalkış kilidi).

⚠️ **Canlı değişiklik kalıcı değil** — konteyner yeniden başlayınca
`/ws/ucus_ayarlari.env` geçerli olur. Kalıcı istiyorsan config'i düzenle,
`--kabuk` ile üret, dağıt.

**Açıları elle ayarlama.** Eğim tavanı ivmeden türetiliyor
(`a = g·tan(θ)`), devrilme dedektörü eşiği de tavandan. Hızı değiştir,
betiği çalıştır — gereken açıyı, frenleme mesafesini ve çarpışma payını
kendisi hesaplayıp tutarsızlık varsa söylüyor.

Bu, 14 Ağustos'ta yaşanan hatanın tekrarını engelliyor: `MAKS_EGIM_DEG`
kodda 35 sabitti ve yorumunda "`MPC_TILTMAX_AIR=30`" **varsayımı** vardı;
ylp00'da 45'ti, yani dedektör eşiği kontrol tavanının altında kalmıştı ve
normal uçuş "devrilme" sayılıp görev havada kendini iptal edebilirdi.

## 9. Asla yapılmayacaklar

### 🔴🔴 UÇUŞ ÖNCESİ KIRMIZI ÇİZGİLER — operatör kim olursa olsun

**Bunlara uyulmadan drone testi TAMAMEN YASAKTIR.** Bu bir öneri listesi
değil. Operatör değişse de, acele olsa da, hava kararıyor olsa da geçerli.
(15 Ağustos 2026, operatör talimatı.)

**Operatörün yapmak ZORUNDA olduğu — Claude devralamaz:**

1. **Harita kontrolü.** Drone'ların gideceği **tüm** noktalar, kalkış noktası
   ve **iniş noktaları** bir harita üzerinde gösterilmeli ve operatör bunu
   gözüyle doğrulamalı. Bu adım devredilemez.
2. **İniş yeri güvenliği.** Hiçbir drone bahçe teline, çite, ağaca, araca ya
   da yanlış başka bir yere indirilmez.
3. **Bilmiyorsan sor.** Operatör bu maddelerden birini bilmiyorsa, uçmadan
   önce **bilen birine sormak zorundadır.** Bilmeden uçmak seçenek değil.

> #### ⚠️ Formasyonda uçaklar kalktıkları yere İNMEZ
>
> En kolay gözden kaçan ve en pahalı madde. **Lider** kalktığı yere iner, ama
> **komşu uçaklar formasyonun o anki dönüş açısına göre bambaşka yerlere
> inebilir.** Formasyon döndüyse slot ofsetleri de dönmüştür; 12 m aralıkta
> bir uçak kalkış noktasından on metrelerce uzağa inebilir.
>
> Yani "kalktığı yer boştu" **yeterli değil**. Her uçağın *muhtemel iniş
> noktası* ayrı ayrı haritada işaretlenmeli ve o alanların hepsi temiz olmalı.

**Claude'un yapmak ZORUNDA olduğu — her uçuştan önce, istisnasız:**

4. 🔴 **EN KÜÇÜK YETERLİ TEST.** Bir düğümü sınamak için **soruyu cevaplayan
   en kısa manevra** uçulur. Basit bir git-gel yetiyorsa git-gel uçulur. Tek
   bir formasyon yetiyorsa tek formasyon uçulur.

   > **Uzun uçuş kendi başına bir değer değil, kendi başına bir risktir.**
   > Her ek bacak, her ek manevra yeni bir arıza yüzeyi açar ve pil yakar.
   > "Madem havadayız, şunu da deneyelim" **yasak** — o "şu" bir sonraki
   > uçuşun işidir.

   Uçuştan önce Claude şu iki soruyu **yazılı** cevaplar:
   - *Bu uçuş hangi tek soruyu cevaplıyor?*
   - *Bu soruyu cevaplayan daha kısa bir manevra var mı?* Varsa **o uçulur.**

   Aynı uçuşta **iki değişiklik denenmez** — bir şey ters giderse hangisi
   olduğu bilinmeli.

5. 🔴 **KURU TEST + HARİTA.** İkisi birlikte, **tek komutta**, istisnasız:

   ```bash
   python3 src/gcs/gorev_kanit_ucus.py --kuru --harita \
       --senaryo <senaryo> --dronelar 1,3 --lider 3
   ```

   `--kuru` planı kurar, çarpışma denetimi yapar, **hiçbir komut göndermez**;
   `SONUÇ: GEÇTİ` demezse **uçulmaz.**

   `--harita` uydu görüntüsü üzerine `/tmp/yelpence_rota.html` yazar:
   **yeşil** = sürü merkezinin geçtiği noktalar · **mavi** = her drone'un
   kendi son hedefi, yani **inecekleri yer**.

   > 🔴 **Harita operatöre GÖSTERİLİR ve operatör gözüyle doğrular.** Bu adım
   > devredilemez — kod bina, ağaç, tel, araç **göremez**; harita elimizdeki
   > **tek engel kontrolüdür.** Claude "harita üretildi" deyip geçemez;
   > operatörün baktığını teyit etmeden uçuş başlamaz.

6. **Uçakla ilgili her türlü ön testi yap.** Gerekiyorsa operatörden
   kumandayı açmasını iste — istemek yük değil, görev.
7. **Rotayı doğru tahmin et.** Uçağın izleyeceği yolu Claude **kesinlikle**
   doğru bilmek zorunda. "Sanırım şuraya gider" kabul edilemez; belirsizlik
   varsa uçulmaz, önce ölçülür.
8. **İrtifadan önce yatay hareket YOK.** Uçak hedef irtifaya ulaşmadan yatay
   hareket komutu verilmez.

> ### ⛔ Bu sekiz madde tamamlanmadan uçuş BAŞLAMAZ
>
> Acele olsa da, hava kararıyor olsa da, "küçük bir test" olsa da geçerli.
> Biri atlanıyorsa Claude **uçuşu durdurur** ve nedenini söyler.

### Diğerleri

- **Havadaki uçağa `disarm` gönderme.** Motoru kesmek düşmek demektir.
  İptal her zaman `land`. Kod bunu zorluyor, sen de zorla.
- **Pixhawk'ta log açma.** RAM sınırda; kayıt Pi'de tutuluyor (rosbag2/mcap).
- **İki üreticiyi aynı konuya bağlama.** Bkz. bölüm 4.
- **Uçmadan önce kuru test atlamama.** `--kuru` planı doğrular ve çarpışma
  denetimi yapar; geçmeden uçulmaz.
- **Ölçmeden teşhis koyma.** Bu projede "muhtemelen şudur" pahalıya patladı.
  Log, telemetri veya ölçüm göster; yoksa "bilmiyorum, şöyle ölçelim" de.
- **Aynı sabiti iki yere yazma.** Filo varsayılanı hem backend hem frontend'de
  duruyordu; biri güncellendi diğeri unutuldu ve düşmüş drone'a komut gitti.

---

## 10. Dil ve üslup

Kod yorumları ve değişken adları **Türkçe** (ASCII'leştirilmiş: `cikis`,
`irtifa`, `kacinma`). Belgeler Türkçe. Bunu koru — depo boyunca tutarlı.

Yorumlar bu projede **niçin** sorusunu cevaplıyor ve çoğu sahada acıyla
öğrenilmiş. "2 Ağustos'ta ölçüldü", "yanlıştı, geri alındı" gibi notları
silme; onlar aynı hatayı iki kez yapmamızı engelliyor.
