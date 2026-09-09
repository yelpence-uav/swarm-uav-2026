# Yelpençe — TEKNOFEST 2026 Sürü İHA

**Son güncelleme:** 9 Eylül 2026, 04:30 — **FİNAL GÜNÜ** · 🔴 **saha değişti, origin yenilendi** (eski değer 8.9 km ötedeydi, `origin_synced=0` → görev hiç başlamıyordu) · 🔴 **QR koordinat tablosu ESKİ SAHAYA ait, yeniden girilmeli** · origin irtifası 3.33 m düzeltildi (komut 10 m → gerçek 13.3 m idi) · adım tamamlanma ölçütü mutlak hataya bakmıyordu (8.5 m ile "oturdu" diyordu) · takım slotu artık YKİ'den mesh üzerinden · RTK baz survey'i YKİ açılışında otomatik

> Claude bu dosyayı her oturumda **kendiliğinden okur.** Yeni sohbet açan
> kişinin hiçbir şey söylemesine gerek yok; projeyi buradan anlar.
> Kısa tutuluyor — ayrıntı `docs/` altında, haritası §6'da.

---

## 1. Ne yapıyoruz

Takım **Yelpençe**, takım numarası **752825**. TEKNOFEST 2026 Sürü İHA
Yarışması. Üç çok rotorlu İHA bir sürü olarak otonom görev yapıyor.

**Uçuş kanıtı geçildi. GÖREV 1 ZİNCİRİNİN TAMAMI uçtu** (4 Eylül akşamı):
kalkış 15 m → toplanma merdiveni → formasyon → QR'a seyir (irtifa tam
−10.0 m, alçalma 0.43 m/s) → **QR'ın 0.11 m yanına varış.**

**GÖREV 2 de kumandadan uçtu** (5 Eylül sabahı, iki uçakla): ylp00 **sabit
lider** ve her zaman slot 0 (ortada), çizgi/V/okbaşı geçişleri havada
yapıldı. Yol boyunca **yedi sessiz kusur** ölçülüp kapatıldı — hepsi hata
vermeden yanlış sonuç üreten türdendi. Finale **1 gün** var.

**Sıradaki dört iş — biri hariç hepsi YERDE kapanır:**
① 🔴 **ylp02'ye kod dağıt** (17 commit geride; `command_valid` ve sabit
lider mesh sözleşmesine dokunuyor, karışık kodla üç uçak uçmaz)
② mesh kaybını ölç ve düşür (%6.7 / %21.7) ③ komutun 1 Hz'e seyrelmesini
bul ④ lens ayarından sonra QR'ı yerde okut. Ayrıntı `docs/YAPILACAKLAR.md` P0.

⚠️ **Dağıtım ana makineden koşulur** — `rsync` orada VAR (8 Eylül'de
operatör düzeltti; eski not "yok" diyordu ve gereksiz yere `yki`
konteynerinden dolaşılıyordu):
`./deploy/rpi/dagit.sh --paket <paket> <ylpXX>`

### 🔴 Bugünkü komut yolu finalde KULLANILAMAZ

Şartname iki kural koyuyor:

> *"**Dağıtık** sürü algoritması kullanılması gerekmektedir. **Merkezi**
> sürü algoritmaları **eksik puan** olarak değerlendirilecektir."*
>
> *"Hakemler görev sırasında herhangi bir anda **yer kontrol istasyonu
> bağlantısını kesecektir**."*

Bugün YKİ (`gorev_kanit_ucus.py`) her uçağa mesh'ten `goto` gönderiyor —
**hem merkezi hem YKİ'ye bağımlı.** Hakem bağlantıyı kestiği anda sürü durur.

**Yani onboard görev düğümleri opsiyonel değil, ZORUNLU.** YKİ'nin izinli tek
rolü "görevi başlat". `gorev_kanit_ucus.py` bundan sonra **test aracı** —
kuru test, harita, çarpışma doğrulama, tek uçak ölçümü.

Kalan iş: `docs/YAPILACAKLAR.md` · neden öyle: `docs/PLAN.md`

---

## 2. Donanım ve kimlikler

| İHA | agent_id | Konteyner | ROS ns | ESP mesh ID | Durum |
|-----|----------|-----------|--------|-------------|-------|
| ylp00 | 1 | `drone1` | `/drone_1` | 1 | uçuyor · **kamera bu uçakta** |
| ylp01 | 2 | `drone2` | `/drone_2` | 2 | uçuyor |
| ylp02 | 3 | `drone3` | `/drone_3` | 3 | uçuyor |

> 📷 **Kamera ylp00'da** — 9 Eylül 2026'da ölçüldü: `/vision_node` ve
> `/camera_driver` yalnız ylp00'da koşuyor, ylp02'de "Node not found".
> `GOREV_KAMERA_AJAN = 1` de ylp00'ı gösteriyor ve QR çıpası formasyonu
> **kameralı uçak QR'ın üstüne gelecek** şekilde kaydırıyor. Bu tablo
> 8 Eylül'e kadar ylp02 diyordu; yanlış uçağa bakmak saha vakti yakar.

**İsim ile numara aynı değil:** ylp00 → drone**1**, ylp02 → drone**3**.
Bu karışıklık gerçek ve sürekli hata kaynağı — komut yazmadan önce bak.

Her İHA: ESP32 (ESP-NOW mesh) + Raspberry Pi 5 (ROS 2 Jazzy, Docker) +
Pixhawk FMUv3 (PX4 1.16.1) + Here4 DroneCAN GPS. Base ESP mesh ID = **10**.

### Drone'a bağlanmak — IP ezberleme, betiği kullan

```bash
./deploy/yki/drone_bul.sh ylp00 'komut'   # Claude bunu kullanır
./deploy/yki/drone_bul.sh --durum         # disk, konteyner, bayraklar
./deploy/yki/drone_bul.sh                 # menü, seç, bağlan (insan için)
```

Önbellek → mDNS → MAC taraması sırasıyla dener; sonuncusu her zaman çalışır.
Erişim, MAC'ler, portlar, QGC ayarı: **`docs/cihazlar.md`**.

---

## 3. Şu an sahada gerçekten ne koşuyor

Repoda 19 ROS düğümü var; uçakta **on biri** açık:

```
mavros_node            MAVLink <-> ROS
px4_bridge             setpoint yürütücü + OFFBOARD  (swarm_control)
agent_fsm_node         ajan durum makinesi           (swarm_state_machine)
esp32_bridge           mesh <-> ROS köprüsü          (swarm_control)
collision_avoidance    DİKEY yol verme + yatay son çare  (swarm_core)
ic_dis_kopru           internal -> public yerel döngü
swarm_origin_publisher · consensus_node · swarm_fsm_node
formation_node · path_planner
```

> **Kaçınma yuvası aynı zamanda ZORUNLU BİR AKTARIM KATI** —
> `/control/setpoint/raw` ile `/control/setpoint` arasındaki tek köprü orası.
> "Kaçınmayı kaldır" diye bir seçenek yok; yalnızca *değiştir* var. Boş
> bırakılırsa `formation_node`'un setpoint'leri px4_bridge'e hiç ulaşmaz.
> (`baslat.sh` bunu yakalayıp gözlem modunu zorluyor.)

Görev düğümleri kapalı. `/ws/suru_dugumleri` dosyasına adı yazılıp
`docker restart` ile açılırlar.

### Komut yolu (kanıtlanmış, uçan yol)

```
YKİ: src/gcs/gorev_kanit_ucus.py
  -> REST -> backend (:8000) -> base ESP -> ESP-NOW mesh
  -> esp32_bridge -> /drone_N/control/setpoint/raw
  -> collision_avoidance -> /drone_N/control/setpoint
  -> px4_bridge -> MAVROS -> PX4 (OFFBOARD)
```

---

## 4. En kritik teknik gerçek — görev düğümlerini açmadan önce

`/drone_N/control/setpoint/raw` ve `/drone_N/control/setpoint` konularının
**ikişer olası üreticisi var** ve bunlar birbirini bilmiyor:

| Konu | Guided yolda üretici | Sürü zincirinde üretici |
|------|----------------------|-------------------------|
| `.../setpoint/raw` | `esp32_bridge` (remap ile) | `formation_node` |
| `.../setpoint` | `collision_avoidance` | `collision_avoidance` |

**İkisi aynı anda açılırsa** px4_bridge 50 Hz'de iki farklı algoritmadan
çelişkili setpoint'leri sırayla alır ve hangisinin kazandığı zamanlamaya
kalır. Teori değil — topic adları birebir aynı, doğrulandı.

**Kural: bir konuya aynı anda tek üretici.** `baslat.sh` bunu 25 Ağustos'tan
beri fiziksel olarak sağlıyor (formasyon sürerken esp32_bridge'in çıkışı
`/gozlem/.../mesh_goto`'ya gider). Açılış logunda `TEK-URETICI` satırını gör.

---

## 5. Çalışma düzeni (takım kuralı)

Tek bilgisayar, tek kişi, sırayla. Paralel çalışma yok. Devir teslim **yazıyla**:

**Oturuma başlarken** — Claude bunları okur, sen de oku:
1. `docs/DURUM.md` — şu an ne çalışıyor, ne bozuk, hangi bayrak açık
2. `docs/GUNLUK.md` — en üstteki kayıt: son kişi nerede bıraktı
3. `docs/YAPILACAKLAR.md` — sıradaki iş

**Oturumu bitirirken** — bu adım atlanırsa sistem çöker:
1. `docs/GUNLUK.md`'ye **en üste** yeni kayıt (şablon dosyanın içinde)
2. Değişen bir şey varsa `docs/DURUM.md` güncelle
3. Biten işi `docs/YAPILACAKLAR.md`'de işaretle, yeni çıkanları **önem
   derecesiyle** ekle (🔴P0 · 🟠P1 · 🟡P2 · ⚪P3). Seviyesiz madde ekleme.
4. Uçakta bir ayar değiştiysen **mutlaka** `DURUM.md`'ye yaz — sonraki kişi
   uçağı öyle bulacak

Claude'a **"oturumu kapat"** dersen bu dördünü o yapar.

### ⚠️ Pi'ye elle bir şey yaptıysan → `docs/RPI_ESITLEME.md` §3

Hep bütün uçaklarla çalışmıyoruz. **Geride kalan uçak, dönene kadar yapılan
her şeyi kaçırır.** Bu yüzden bir Pi'de yapılan her değişiklik — paket,
bayrak dosyası, sysctl, Wi-Fi, PX4 parametresi — §3'teki A-matrisine
**hangi uçaklarda olduğu** bilgisiyle yazılır. Yazılmayan değişiklik,
sonradan saatlerce süren "neden bunda çalışmıyor" arayışına dönüşüyor.

---

## 6. Belge haritası

**Tam harita `README.md`'de.** Claude'un sık kullandıkları:

| Dosya | Ne için |
|-------|---------|
| `docs/DURUM.md` | Şu anki durum: ne çalışıyor, ne bozuk, hangi bayrak açık |
| `docs/YAPILACAKLAR.md` | **8 günde yapılacak iş**, öncelikli |
| `docs/GUNLUK.md` | Oturum devir teslim kaydı |
| **`docs/TUZAKLAR.md`** | **Hata vermeden yanlış sonuç üretenler.** Bir şey "çalışmıyor ama hata da vermiyor" ise ÖNCE buraya bak |
| `docs/PLAN.md` | Neden böyle yapıldı — şartname, test kademeleri, kalan ADIM'lar |
| `docs/KARARLAR.md` | **Verilmiş ama henüz uygulanmamış kararlar** — sırası gelince hatırlat |
| 🔴 **`docs/YLP02_DUSME.md`** | **5 Eylül ylp02 düşme raporu** — kök neden, elenen hipotezler, fiziksel kontrol listesi. **ylp02 uçmadan önce OKU** |
| **`docs/KAMERA.md`** | Kamera ve algı — kalibrasyon, QR/renk menzilleri, rolling shutter |
| `docs/RPI_ESITLEME.md` | Hangi uçakta ne var (§3 A-matrisi) |
| `docs/cihazlar.md` | Kimlik tablosu, SSH, MAC, port, QGC, sysid |

**Çelişki varsa:** canlı belge referans belgeyi yener, **kod ikisini de yener.**

> ### 🔒 İKİ BELGE KORUMALI — kendiliğinden OKUMA
>
> `docs/MESH_PROTOKOL_KARARLARI.md` (1542 satır) ve
> `docs/YELPENCE_RTCM_SPEC.md` (841 satır) **yalnız operatör açıkça isteyince**
> okunur. Keşif sırasında, "bir bakayım" diye, grep sonucu ilginç göründü
> diye **açılmaz** — ikisi bağlamı doldurup asıl işe yer bırakmıyor.
> Gerekiyorsa **operatöre sor.** (`.claude/korumali_belgeler.sh` zaten izin
> sorduruyor; operatör reddederse bu bir hata değil, kuralın çalışmasıdır.)

**Ekran görüntüsü**: `ss/` klasörüne at, sohbette söyle.

---

## 7. MİSYON ve çalışma ilkeleri

**Misyon:** repodaki görev yazılımını, **şartnameye uygun** şekilde, **en
güvenli** yoldan drone'lara entegre etmek. Başka hedef yok.

### Hiçbir şey dokunulmaz değil

`px4_bridge`, `esp32_bridge`, `agent_fsm_node`, `collision_avoidance` —
bunlar "en iyisi" oldukları için değil, **uçuş kanıtını geçirdikleri için**
oradalar. Gerekirse tamamı değişir, ESP32 firmware'i dahil. Tek ölçüt
şartnameye uygunluk ve güvenlik. Bir düğümü atıp yeniden yazmak gerekiyorsa
**bu bir başarısızlık değil**, doğru karardır.

### Sorun bildirirken: sorun + çözüm birlikte

Sorunları mutlaka söyle — operatör hangi hatanın çıkacağını önceden bilemez.
**Ama sorunu kucağına bırakma.** Her sorunla birlikte: ① ne bozuk, somut
olarak ② tahmini çözüm ve nasıl uygulanacağı ③ maliyeti (kaç satır, kaç
uçuş, geri alınabilir mi). Yalnız "şu çakışma var" demek işi operatöre
yıkmaktır.

### Karar verildiyse hatırlat, sıfırdan tartışma

Sohbette verilen kararlar oturum bitince kaybolur; `docs/KARARLAR.md` onları
tutuyor. Bir işe gelince ÖNCE oraya bak. Karar varsa: **operatöre söyle**,
önerilen seçeneği ve gerekçesini hatırlat, başka seçenek isterse o an
konuşulur. Kararı sessizce uygulama, ama her seferinde baştan da tartışma.
**Yeni önemli karar çıkarsa oraya yaz** — özellikle *"şimdi değil, sırası
gelince"* denilenleri.

### 🧠 Effort daima `max` (KARAR-02)

`/effort` menüsü **hep `max`** kalır; ultracode menüden açılmaz (ikisi aynı
listede ve ultracode seçilince effort `xhigh`'a düşüyor). Çok ajanlı denetim
gerekirse operatör **o mesajın içine `ultracode` yazar.**

Claude effortunu okuyabilir: `echo $CLAUDE_EFFORT`. **`max` değilse operatöre
hemen söyle.**

> **Ultracode'u Claude ÖNERMEZ.** Eski kural belirli adımlardan önce
> hatırlatma yapmamı istiyordu; operatör 28 Ağustos'ta kaldırdı ve o adımlar
> zaten bitti. İsteyen operatördür, hatırlatan değil.

### 📅 Her .md değişikliğinde en üste tarih-saat

Bir `.md` dosyasını değiştirdiysen başlığın hemen altına damgayı yaz/güncelle:
`**Son güncelleme:** 29 Ağustos 2026, 18:50` (saat **Europe/Istanbul**).
Tek bilgisayarda sırayla çalışıyoruz; belgeyi açanın ilk sorusu "bu ne kadar
taze?" oluyor ve aynı günün sabahı ile gecesi arasında çok şey değişiyor.
İçerik değişip tarih eskiyse belge olduğundan taze görünür — bu yanıltıcıdır.

### Test: en küçük yeterli manevra

Canlıda test ediyoruz. Ölçüt **bir sonraki adımın güvenli olduğunu gösterecek
EN AZ test.** Uçuşu tasarlarken sıra: ① *Bu uçuş hangi tek soruyu
cevaplıyor?* ② *Yerde cevaplanabilir mi?* — cevaplanabiliyorsa **uçulmaz.**
③ *En kısa hangi manevra cevaplar?* — o uçulur.

| Soru | Yeten manevra |
|---|---|
| Düğüm açılıyor mu, mantıklı değer üretiyor mu | **Uçuş yok** — G0/G1 yerde |
| Havada ne üretiyor (komuta bağlı değil) | **Kalk – asılı dur – in** |
| Setpoint takibi, kayma, aşım | **Tek düz bacak, git-gel** |
| Formasyon doğru mu | **Tek formasyon**, tek geçiş |
| Lider seçimi/devri | **Kalk – asılı dur**, kill ile devret |

**Uzun uçuş kendi başına bir değer değil, kendi başına bir risktir.** Her ek
bacak yeni bir arıza yüzeyi açar ve pil yakar. *"Madem havadayız, şunu da
deneyelim"* **yasak** — o bir sonraki uçuşun işi. Aynı uçuşta **iki
değişiklik denenmez.** Kademeler: `docs/PLAN.md` §5.

---

## 8. Uçuş ayarları tek yerden

**Hız, ivme, formasyon aralığı ve eğim tavanları `src/gcs/ucus_ayarlari.py`'de.**
Başka hiçbir yerde elle yazılmaz.

```bash
python3 src/gcs/ucus_ayarlari.py          # çözümleme + tutarlılık denetimi
python3 src/gcs/ucus_ayarlari.py --px4    # uçaklara yazılacak param komutları
python3 src/gcs/ucus_ayarlari.py --kabuk  # baslat.sh için env satırları
```

**Açıları elle ayarlama.** Eğim tavanı ivmeden türetiliyor (`a = g·tan(θ)`),
devrilme dedektörü eşiği de tavandan. Hızı değiştir, betiği çalıştır —
gereken açıyı, frenleme mesafesini ve çarpışma payını kendisi hesaplayıp
tutarsızlık varsa söylüyor. (14 Ağustos'ta `MAKS_EGIM_DEG` kodda 35 sabitti
ve yorumundaki `MPC_TILTMAX_AIR=30` **varsayımı** yanlıştı; ylp00'da 45'ti,
yani dedektör eşiği kontrol tavanının altındaydı ve normal uçuş "devrilme"
sayılıp görev havada kendini iptal edebilirdi.)

Yürütücü ayarları **uçuş sırasında canlı** değiştirilebilir (`src/gcs/px4_param.py`
ile `--ns /px4_bridge --yaz guided_hiz_yatay_mps=4.0`). Yalnız hız/ivme/kp
alanları kabul edilir; kimlik, kill/arm kanalları ve kalkış kilidi
**reddedilir**. ⚠️ Canlı değişiklik **kalıcı değil** — konteyner yeniden
başlayınca `/ws/ucus_ayarlari.env` geçerli olur.

---

## 9. Asla yapılmayacaklar

### 🔴🔴 UÇUŞ ÖNCESİ KIRMIZI ÇİZGİLER — operatör kim olursa olsun

**Bunlara uyulmadan drone testi TAMAMEN YASAKTIR.** Öneri listesi değil.
Operatör değişse de, acele olsa da, hava kararıyor olsa da geçerli.
(15 Ağustos 2026, operatör talimatı.)

**Operatörün yapmak ZORUNDA olduğu — Claude devralamaz:**

1. **Harita kontrolü.** Drone'ların gideceği **tüm** noktalar, kalkış ve
   **iniş noktaları** haritada gösterilmeli ve operatör gözüyle doğrulamalı.
2. **İniş yeri güvenliği.** Hiçbir drone bahçe teline, çite, ağaca, araca ya
   da yanlış başka bir yere indirilmez.
3. **Bilmiyorsan sor.** Bu maddelerden birini bilmiyorsan, uçmadan önce
   **bilen birine sormak zorundasın.** Bilmeden uçmak seçenek değil.

> #### ⚠️ Formasyonda uçaklar kalktıkları yere İNMEZ
>
> En kolay gözden kaçan ve en pahalı madde. **Lider** kalktığı yere iner, ama
> **komşu uçaklar formasyonun o anki dönüş açısına göre bambaşka yerlere
> inebilir.** Formasyon döndüyse slot ofsetleri de dönmüştür; 12 m aralıkta
> bir uçak kalkış noktasından on metrelerce uzağa inebilir. Yani "kalktığı
> yer boştu" **yeterli değil** — her uçağın *muhtemel iniş noktası* ayrı ayrı
> haritada işaretlenmeli ve o alanların hepsi temiz olmalı.

**Claude'un yapmak ZORUNDA olduğu — her uçuştan önce, istisnasız:**

4. 🔴 **EN KÜÇÜK YETERLİ TEST.** Uçuştan önce Claude şu iki soruyu **yazılı**
   cevaplar: *Bu uçuş hangi tek soruyu cevaplıyor?* · *Bu soruyu cevaplayan
   daha kısa bir manevra var mı?* Varsa **o uçulur.**

5. 🔴 **KURU TEST + HARİTA.** İkisi birlikte, **tek komutta**, istisnasız:

   ```bash
   python3 src/gcs/gorev_kanit_ucus.py --kuru --harita \
       --senaryo <senaryo> --dronelar 1,2,3 --lider 3
   ```

   `--kuru` planı kurar, çarpışma denetimi yapar, **hiçbir komut göndermez**;
   `SONUÇ: GEÇTİ` demezse **uçulmaz.** `--harita` uydu görüntüsü üzerine
   `/tmp/yelpence_rota.html` yazar: **yeşil** = sürü merkezinin geçtiği
   noktalar · **mavi** = her drone'un kendi son hedefi, yani **ineceği yer.**

   > 🔴 **Harita operatöre GÖSTERİLİR ve operatör gözüyle doğrular.** Bu adım
   > devredilemez — kod bina, ağaç, tel, araç **göremez**; harita elimizdeki
   > **tek engel kontrolüdür.** Claude "harita üretildi" deyip geçemez.

6. **O uçuşa özgü bir ön test gerekiyorsa iste.** Gerekiyorsa operatörden
   kumandayı açmasını iste — istemek yük değil, görev.
   ⚠️ *"Her türlü ön test"* değil: rutin kontroller aşağıdaki **saha günü**
   listesinde ve **uçuş başına tekrarlanmaz.**
7. **Rotayı doğru tahmin et.** "Sanırım şuraya gider" kabul edilemez;
   belirsizlik varsa uçulmaz, önce ölçülür.
8. **İrtifadan önce yatay hareket YOK.**

> ### ⛔ Bu sekiz madde tamamlanmadan uçuş BAŞLAMAZ
>
> Biri atlanıyorsa Claude **uçuşu durdurur** ve nedenini söyler.

### 🟢 Bunlar uçuş başına DEĞİL — saha günü bir kez

29 Ağustos 2026 operatör kararı. Bu kontroller değerli ama **her uçuşta
tekrarlanmaları ölçülebilir bir şey yakalamadı**, buna karşılık saha
temposunu kesiyorlardı. Claude bunları uçuş başına **istemez ve uçuşu
bunlar için durdurmaz.**

| Kontrol | Ne zaman |
|---|---|
| `./deploy/yki/param_karsilastir.py` | Bir PX4 parametresi **yazıldıktan sonra** + saha günü bir kez |
| `python3 src/gcs/titresim_olc.py <ylpXX>` | Gövdeye **fiziksel iş** yapıldıysa (motor, pervane, kart montajı, düşme sonrası) + saha günü bir kez |
| Pi ayakta mı · disk · bayraklar · **kod senkronu (md5)** · **ros2 düğüm sayısı** | Hepsi `./deploy/yki/drone_bul.sh --durum` içinde — **tek komut**, ayrı adım değil |
| **QGC 14550 link kontrolü** | **Operatörün kendi işi.** Claude sormaz, gate etmez |

> 🔴 **QGC hattı operatöre ait.** `udp-b` yayını 14550'yi dinleyen kimse
> yokken laptopun internetini boğuyor (22 Ağustos'ta ölçüldü) — ama bu
> **operatörün kendi makinesindeki** bir kurulum meselesi ve o kişi süreci
> kendi yönetiyor. Belirtisi de nettir: `fix_type` 6'ya çıkmaz, QGC'de uçak
> görünmez. Ayrıntı `TUZAKLAR.md` §7.1'de duruyor — gerektiğinde bakılır.

### Diğerleri

- **Havadaki uçağa `disarm` gönderme.** Motoru kesmek düşmek demektir.
  İptal her zaman `land`. Kod bunu zorluyor, sen de zorla.
- 🔴 **HOME kayması çözülmeden RTL'li uçuş YOK** — iniş `land` ile.
- **Pixhawk'ta log açma.** RAM sınırda; kayıt Pi'de (rosbag2/mcap).
- **İki üreticiyi aynı konuya bağlama.** Bkz. §4.
- **Ölçmeden teşhis koyma.** Bu projede "muhtemelen şudur" pahalıya patladı.
  Log, telemetri veya ölçüm göster; yoksa "bilmiyorum, şöyle ölçelim" de.
- **Aynı sabiti iki yere yazma.** Filo varsayılanı hem backend hem frontend'de
  duruyordu; biri güncellendi diğeri unutuldu ve düşmüş drone'a komut gitti.
- **`--kuru` atlamama.** Geçmeden uçulmaz.

---

## 10. Dil ve üslup

Kod yorumları ve değişken adları **Türkçe** (ASCII'leştirilmiş: `cikis`,
`irtifa`, `kacinma`). Belgeler Türkçe. Depo boyunca tutarlı — koru.

Yorumlar bu projede **niçin** sorusunu cevaplıyor ve çoğu sahada acıyla
öğrenilmiş. *"2 Ağustos'ta ölçüldü"*, *"yanlıştı, geri alındı"* gibi notları
silme; onlar aynı hatayı iki kez yapmamızı engelliyor.
