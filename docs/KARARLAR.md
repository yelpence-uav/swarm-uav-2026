# KARARLAR — verilmiş ama henüz uygulanmamış kararlar

**Son güncelleme:** 7 Eylül 2026, 11:57 — **KARAR-18 UYGULANDI** (kumanda-kaybı failsafe: LAND, ~3.5-4 sn, üç uçak; hakem RTL derse geri dönüş adımı içinde). Eski: KARAR-17 uçtu (sabit lider ylp00) · KARAR-16 (tek-yayıncı) · KARAR-15 (kaçınma eşikleri 5 m'de kilitleniyor)

Sohbette verilen kararlar oturum bitince kayboluyor. Bu defter onları
tutuyor: **ne karar verildi, neden, ne zaman uygulanacak, nasıl test edilecek.**

---

## ⚠️ CLAUDE İÇİN KURAL

**Bir aşamaya/işe geldiğinde ÖNCE buraya bak.**

O işle ilgili bir karar varsa:

1. **Operatöre söyle** — "bu konuda şu karar verilmişti"
2. **Önerilen seçeneği belirt** ve gerekçesini hatırlat
3. Operatör farklı bir seçenek isterse **o an detaylıca konuşulur**

Kararı sessizce uygulama, ama her seferinde sıfırdan da tartışma. Karar
zaten verilmiş; işin senin tarafın onu **hatırlatmak** ve **uygulamak**.

Yeni bir önemli karar verilirse **buraya yaz** — özellikle "şimdi değil,
sırası gelince" denilen şeyleri. Onlar en kolay kaybolanlar.

---

## Durum işaretleri

`🟡 BEKLİYOR` — karar verildi, sırası gelmedi
`🔵 SIRASI GELDİ` — aşamaya ulaşıldı, uygulanacak
`✅ UYGULANDI` — bitti, sonucu yazıldı
`❌ VAZGEÇİLDİ` — gerekçesiyle

---

# KARAR-18 — Kumanda-kaybı failsafe: RTL değil LAND, ~3.5-4 sn'de

**Durum:** ✅ UYGULANDI (7 Eylül 2026 — üç uçakta geri-okumayla doğrulandı)
**Ne zaman:** uygulandı; hakem brifinginden sonra yeniden ele alınabilir
**Karar veren:** operatör (7 Eylül 2026)

## Karar

Kumanda kapanınca uçaklar RTL değil **olduğu yerde LAND** yapar; failsafe
kapanıştan **3-4 sn sonra** devreye girer, daha fazla beklemez.

## Neden

- HOME kayması P0 hâlâ açık — RTL bir kez üç uçağı ~9 m KD'ya indirmişti.
  LAND home kullanmaz; bu yoldan o riski tamamen kaldırır.
- Eski `COM_FAIL_ACT_T=5.0` ile toplam tepki ~6-6.5 sn idi; hakem
  kapattığında uçak 5 sn "hiçbir şey yapmıyormuş" gibi görünürdü.
  (19 Ağu "1-2 sn'de RTL" kaydı bu 5 sn'lik beklemeyle uyumsuzdu; o gün
  görülen muhtemelen HOLD aşamasıydı.)

## Nasıl uygulandı

Üç uçakta `NAV_RCL_ACT` 2→**3**, `COM_FAIL_ACT_T` 5.0→**2.5** (MAVLink,
QGC kapalıyken; PX4 kalıcı saklar). Zincirin kalanı ölçülüp aynı çıktı:
alıcı CH3=2100 (~0.5-1 sn) + `COM_RC_LOSS_T=0.5` + bekleme 2.5 =
**~3.5-4 sn**. `COM_RCL_EXCEPT=0` → OFFBOARD'da da tetiklenir.

## Test

- Yerde (saha günü kontrolü, değişmedi): kumanda kapat → QGC SARI.
- 🟠 Havada bir kez: alçak askıda kumanda kapat → ~4 sn'de iniş
  başlamalı (YAPILACAKLAR'da).

## Diğer seçenekler (operatör isterse)

| Seçenek | Neden seçilmedi |
|---|---|
| RTL (eski) | HOME kayması açık. Hakem RTL derse `NAV_RCL_ACT=2` GERİ yazılır ve HOME riski geri gelir — brifingde netleşecek (gorev2.md madde 35) |
| Bekleme < 2.5 sn | Kısa RC kesintisi anında iniş tetiklerdi; 2.5 sn "3-4 sn" hedefini tutturan en küçük pay |

# KARAR-17 — Lider SEÇİLMEZ, VERİLİR: ylp00 (sistem geneli) + Görev 2'de slot 0

**Durum:** ✅ UYGULANDI ve **UÇTU** (5 Eylül 2026) — ylp00 + ylp01'e dağıtıldı, birden çok uçuşta lider hiç değişmedi, lider slot 0'da (formasyonun ortasında) kaldı. Ek olarak **en-yakın-slot ataması (Macar)** yazıldı: lider slot 0'a çivili, kalanlar Macar ile (çizgide toplam yol **0.00 m**; kimlik sırası 24.00 m). 🔴 **ylp02'ye DAĞITILMADI** — o uçak 5 Eylül'de ulaşılamadı ve hâlâ eski kodda.
**Ne zaman:** Görev 2 çalışmasının ilk maddesi
**Karar veren:** Operatör (4 Eylül 2026) — önce *"YLP00'ı kalıcı lider seçeceğiz ve o her zaman ortaya koyulacak"* (Görev 2), aynı gün genişletildi: *"tüm sistemi kapsayacak şekilde olsun. Yani hem Görev 1 hem Görev 2 sabit lider YLP00."*

## Karar

**Lider seçim konusu değildir:** `ylp00` (agent_id **1**) liderdir ve süreç
boyunca değişmez. **Kapsam: hem Görev 1 hem Görev 2** — görev bazlı
dallanma yok, tek profil tek davranış.

Ayrıca **Görev 2'de** lider formasyon tarifinde **slot 0**'a oturur. Slot 0
üç formasyonun da tepe/merkez noktası (çizgi → hattın ortası, okbaşı → uç,
V → arka köşe), yani "ortada" bu tek kuralla sağlanıyor.

⚠️ **"Ortada" kuralı Görev 1'e uygulanmadı** — ayrı bir karar. Görev 1'in
slot ataması **Macar** (en yakın slot, `formation_cmd.build_slot_assignment`)
ve o zincir **4 Eylül akşamı uçtan uca uçtu**; kanıtlanmış geometriyi
değiştirmek için sebep yok. İstenirse ayrıca konuşulur.

**Neden Görev 1'de de güvenli:** `SURU_LIDER_KILIDI` **zaten görevden
bağımsız** ve sahada `true` — yani Görev 1'de de devir çoktan kapalıydı.
Sabit lider **yeni bir kısıt getirmiyor**, yalnızca kimliği yarışa bırakmak
yerine belirli kılıyor. Kilidin "yanlış lideri kalıcı yapma" riski böylece
Görev 1'de de kapanıyor — net etki **risk azaltması**.

Lider zinciri tek parametreyle iki görevi de kapsıyor:
`consensus` → `ElectionResult` → `swarm_fsm` → `SwarmState.leader_id` →
`mission1`. Görev 1 tarafında **ek kod gerekmedi**.

## Neden

Lider kilidi (KARAR öncesi, 3 Eylül) **ilk seçimi nihai** yapıyor. Ama o ilk
seçimin ylp00'a düşmesi **tesadüfe bağlıydı**: `candidate = min(effective)`
+ tam kadro beklemesi. Tam kadro `kilit_tam_kadro_s` (**8 sn**) içinde
oluşmazsa yedek yol devreye giriyor ve **o an uygun olan kim varsa kalıcı
lider oluyordu.** Uçaklar arası evre kayması 3 Eylül uçuşunda **25 saniye**
ölçüldü — yani 8 sn'lik pencere güvenilir tutmuyor ve yanlış lider bir daha
düzelmiyor.

Görev 2'de bunun bedeli doğrudan formasyondur: tarifi **yalnız lider** basar
(KARAR-16 tek-yayıncı), slot ataması **kimlik sırasına** bağlıdır.

## Nasıl uygulandı

Lider **dört ayrı yoldan** değişebiliyordu; dördü de kapatıldı — biri
atlansaydı mesh'ten gelen tek bir kalp atışı sabit lideri devirirdi:

| # | Yol | Nerede kapatıldı |
|---|-----|------------------|
| 1 | `election.decide_change` (seçim/devir) | erken dal: sabit kuruluysa `None` |
| 2 | `_liderligi_birak` (uygunluk yitimi) | `_tick`'te atlanıyor + kısılmış WARN |
| 3 | `_adopt_leader` / `_on_election` / `_on_heartbeat` (mesh) | aykırı kimlik reddediliyor + bir kez WARN |
| 4 | `_rakip_tahkim` (rakibe boyun eğme) | `_tick`'te atlanıyor |

Slot 0 kuralı: `tek_yayinci.lider_onde()` (saf fonksiyon) tarifteki
`agent_ids` sırasını **lider başta** üretiyor; `mode_manager` onu kullanıyor.
`mode_manager` yalnız Görev 2'de koştuğu için bu kısım kendiliğinden
Görev-2 kapsamlı kalıyor. **Mesh protokolü değişmedi** — `TIP_FORMASYON` payload'ı
zaten `slot_ajan[i] = i. slottaki ajan` şeklinde sırayı taşıyor
(`packet_parser:1085`), alıcı ofsetleri aynı sırada yeniden üretiyor.

Yan kazanç: `mode_manager` artık `agent_ids`'i **sıralı** okuyor. Önce sıra
doğrudan `SURU_KADRO`'dan geliyordu; kadro `"3 1"` yazılsaydı slot 0
sessizce ylp02'ye giderdi.

## Ayar

`ucus_ayarlari.SURU_SABIT_LIDER = 1` → env `SURU_SABIT_LIDER`.
`0` yazmak özelliği tamamen kapatır (eski davranışa döner).
Tutarlılık denetimi eklendi: sabit lider `UCAN_KADRO` içinde değilse
`ucus_ayarlari.py` **hata** veriyor — o uçak hiç tarif basmaz ve formasyon
sessizce kurulmazdı.

## 🔴 Bedeli — bilerek kabul edildi

Lider kilidiyle **aynı** bedel: sabit lider gerçekten düşerse **devir olmaz**,
takipçiler son formasyon komutunda kalır. Çıkış yolu **kill switch
pilotlarıdır**. Parametre olduğu için yarışma günü tek satırla kapanır.

İkinci bedel: ylp00 Görev 2'nin **tek arıza noktası** hâline geliyor —
zaten kumanda alıcısı orada (G2-K1) ve kaçınmada ÇAPA. Yani ylp00 düşerse
Görev 2 zaten bitiyordu; bu karar o bağımlılığı artırmıyor, görünür kılıyor.

## Test

- `swarm_core/test/test_sabit_lider.py` — 11 test. Yarısı **kapatma
  anahtarı regresyonu**: `sabit_lider=0` iken ilk seçim, LEADER_FAULT devri
  ve grace beklemesi eski hâliyle çalışıyor (yarışma günü tek satırla geri
  dönülebilsin diye test altında).
- `swarm_state_machine/test/test_lider_slot_sifir.py` — 13 test. Slot 0'ın
  üç formasyonda da merkez olduğunu ve kadro sırasının artık önemsiz
  olduğunu kilitliyor.
- Tüm paketler: **1058 geçti** (277 + 407 + 62 + 312), 28 atlandı.
  (`origin/main`'in 19 commit'i üzerine rebase edildi, çakışma çıkmadı.)
  Görev 1 paketi (`swarm_missions`) **62/62 değişmedi**.
- **Canlı düğüm ölçümü** (`ros:jazzy` konteyneri, gerçek `ConsensusNode`):

  | Ayar | Uygun olan | Sonuç |
  |---|---|---|
  | `sabit_lider=0` | yalnız ajan 3 | `leader_id=3`, seçim yayını `[3]` — **eski davranış** |
  | `sabit_lider=1` | yalnız ajan 3 | `leader_id=1` — ylp00 hiç görülmemişken bile |
  | `sabit_lider=1`, ylp00 tarafı | — | `is_leader=True`, `ElectionResult(1)` **yayınlandı** (esp32_bridge mesh kapısı açılır) |
  | mesh'ten drone3 "ben liderim" | — | **REDDEDİLDİ**, lider 1 kaldı |

## Sırada — uçakta doğrulanacak

Dağıtımdan sonra **açılış logunda** görülmeli:
`[baslat] 🔒 SABIT LIDER = drone1 (Gorev 1 + Gorev 2)` ve
`[consensus] SABIT LIDER ACIK: drone1`. `SURU_SABIT_LIDER=0` ile
kapatıldığında aynı satır `sabit lider KAPALI — normal secim (eski davranis)`
olmalı.

🔴 **Uçakta ölçülecek:** `ros2 param get /consensus_node sabit_lider` → **1**
(iki uçakta da) ve `docker logs` içinde lider `1` seçilmiş olmalı — 8 sn'lik
tam kadro beklemesi artık hiç işlemediği için seçim **anında** olmalı.

---

# KARAR-16 — Formasyon tarifini YALNIZ lider basar (tek-yayıncı)

**Durum:** ✅ UYGULANDI (2 Eylül 2026) — kod uçaklarda ve depoda (`tek_yayinci.py`, commit `29cdf2c`)
**Ne zaman:** 2 Eylül küme-toplanma saha olayının doğrudan sonucu
**Karar veren:** Claude önerdi, operatör "yap" dedi (2 Eylül 2026)

## Karar

MOVEMENT/HOLD/formasyon-değişimi — üçünde de `FormationCommand`'ı yalnız
**lider** mode_manager yayınlar. Takipçilerin formation_node'u tarifi
mesh'ten (liderinkini) alır; bu yol zaten kanıtlı. Lider kaynağı
consensus'un ElectionResult'i; election hiç gelmemişse deterministik
yedek = `min(agent_ids)` (üçü de aynı sonuca varır, çelişki üretmez).

## Neden

2 Eylül olayında env artığı `SURU_KADRO` iki uçakta farklıydı (ylp00+ylp02
`"1 3"`, ylp01 `"1 2 3"`); her uçak KENDİ tarifini basınca **çelişkili
tarifler** çıktı ve sürü havada ~1 m kümeye toplandı (çarpışma olmadı,
operatör kumandayla indirdi). Kadro düzeltildi ama kök mimari: her uçak
tarif basabildiği sürece HER görüş ayrılığı (kadro, centroid, atama)
çelişkiye döner. Tek yayıncı bunu yapısal kapatır. Yan fayda: MOVEMENT
tarif trafiği üçte bire iner.

## Nasıl uygulandı

`mode_manager/tek_yayinci.py` (saf modül) + `_publish_formation_command`
başına kapı + election aboneliği (internal+public, RELIABLE+TRANSIENT_LOCAL).
Ayrıca `degisim_islenir_mi`: aynı tip+aralık tekrarını yutar (1 Eylül'ün
50 ms tekrar fırtınası). 82/82 test geçti. Kod uçaklardan depoya alındı
(`29cdf2c`).

## Açık uç

Test B (formasyon değişimli, tek-yayıncı ile) uçakta doğrulanacak —
beklenen: yalnız lider "Formasyon degisikligi", diğerleri
"TEK-YAYINCI: tarif BASMAZ". Ayrıca env eşitleme boşluğu ayrı iş
(RPI_ESITLEME B31).

---

# KARAR-10 — Formasyon testlerinde GOTO YASAK: uçağı yalnız formation_node sürer

**Durum:** 🔵 SIRASI GELDİ — geçerli (⚠️ bu kayıt 2 Eylül'de bir kez daha
pull sırasında kaybolup yeniden yazıldı; kaybolursa yine ekle)
**Ne zaman:** ADIM 3 ve sonrası tüm formasyon/sürü testleri
**Karar veren:** Operatör (28 Ağustos 2026): *"goto komutu asla kullanma,
formasyon node'u var onu kullanarak yapılacak"*

## Karar

Formasyon/sürü testlerinde uçağı süren TEK üretici `formation_node` (mesh
tarif → slot → `/control/setpoint/raw` → CA → px4_bridge). YKİ `goto` yolu
test aracı olarak bile kullanılmaz. Kalkış/iniş komut kanalından (arm/
takeoff/land TIP_KOMUT) — bunlar goto değildir.

## Neden

Testlerin amacı sürü düğümlerini kanıtlamak; finalde YKİ/goto yok. Goto
ile "çalışıyor" görüntüsü test edilmemiş kodu kanıtlanmış sayma hatası
üretir. `baslat.sh` (20c2b01) formasyon sürerken goto çıkışını gözleme
bağlayarak bunu fiziksel olarak da zorluyor.

---

# KARAR-12 — `mission_active` YKİ'ye lider kalp atışıyla gelecek (mesh'e 0 bayt)

**Durum:** 🟡 BEKLİYOR
**Ne zaman:** ADIM 6-7 — `mission_fsm` `suru_dugumleri`'ne eklendiği an. Öncesinde
test edilemez, çünkü olayı üreten düğüm kapalı.
**Karar veren:** Operatör (29 Ağustos 2026), `SwarmState` kartı kaldırıldıktan sonra

## Karar

YKİ `mission_active` bilgisini **`LeaderHeartbeat` üzerinden** alacak
(`TIP_LEADER_HB`). `SwarmState` mesh'e **çıkarılmayacak** — o karar 29 Ağustos'ta
verildi ("mesh sade kalsın") ve bu yol onu bozmadan aynı sonucu veriyor.

## Neden

**Ölçüldü (29 Ağustos), zincirin tamamı zaten kurulu — tek kopuk halka kaynak:**

```
LeaderHeartbeat.msg              bool mission_active alanı       ✅ VAR
consensus_node.py:541            kalp atışına koyuyor            ✅
leader_hb_paketle():781          16 bayta paketliyor             ✅
esp32_bridge:2714                TIP_LEADER_HB ile yolluyor      ✅  10 Hz, yalnız lider
esp32_bridge:1782                alıcıda çözüyor                 ✅
esp32_bridge:478                 /swarm/public/leader/heartbeat  ✅
backend                          o konuya abone DEĞİL            ❌
consensus_context.py:86          = False, bir daha HİÇ set edilmiyor  ❌  ← tek kopukluk
```

Doğru değeri tutan `mission_active` **başka düğümde**: `swarm_fsm_node.py:586/590`,
`EVENT_MISSION_STARTED` / `EVENT_MISSION_COMPLETED` olaylarından. `consensus`'unki
`__init__`'te `False` yapılıp unutulmuş.

**Mesh maliyeti tam olarak sıfır:**

```
TIP_LEADER_HB payload = 16 bayt (mesh sabit)
  kullanılan  8   ← mission_active bunun İÇİNDE, zaten uçuyor
  boş dolgu   8   ← ileride mission_id (uint8) için yer var
```

Paket saniyede 10 kez zaten gidiyor, bayt zaten içinde, sadece hep `0` yazıyor.

**Neden olay (`SystemEvent`) yolu değil — ikisi de mesh'e 0 bayt:**
Olay **kenar tetikli**. Şartname *"hakemler görev sırasında YKİ bağlantısını
kesecektir"* diyor; yeniden bağlanan YKİ'de kenar tetikli bayrak `false` başlar —
yani **ACİL İNİŞ butonu tam ihtiyaç duyulan anda pasif kalır.** Kalp atışı
**seviye tetikli**, 10 Hz: paket kaybı 100 ms'de kendini onarır, geç bağlanan YKİ
doğruyu 100 ms'de öğrenir.

**Lider devri kendiliğinden güvenli:** `swarm_fsm` olayları
`/swarm/public/events/system`'den dinliyor (`:229`) ve mesh'ten gelen **komşu
olayları da oraya** düşüyor (`_event_pub_public`). `consensus` da aynı konuyu
dinlerse her uçak `mission_active`'i **bağımsız** tutar; yeni seçilen lider doğru
değerle yayına başlar. Düğümler arası yeni bağımlılık doğmaz.

## Nasıl uygulanacak

| # | Nerede | İş | Satır |
|---|--------|----|-------|
| 1 | `consensus_node.py` | `/swarm/public/events/system`'e abone ol, `EVENT_MISSION_STARTED/COMPLETED` ile `ctx.mission_active` set et (`swarm_fsm_node.py:584-590` ile birebir aynı mantık) | ~8 |
| 2 | `ros_bridge.py` | `/swarm/public/leader/heartbeat` → `LeaderHeartbeat` aboneliği, `mission_active`'i durumda tut | ~10 |
| 3 | `ros_bridge.py` | Olay yolunu **teyit katmanı** olarak ekle: `EVENT_MISSION_COMPLETED` gelince hemen düşür (kalp atışını beklemeden) | ~5 |

Geri alınabilir: üçü de eklemeli, hiçbir mevcut davranışı değiştirmiyor.

### 🔴 Zaman aşımında SON DEĞERİ KORU — sıfırlama

Kalp atışını **yalnız lider** yayınlıyor. Lider düşerse yeni seçime kadar
(`heartbeat_timeout_ms = 1000`) YKİ hiçbir şey almaz.

Buradaki refleks yanlış yön: drone bağlantı zaman aşımlarında yaptığımız gibi
durumu **sıfırlarsak, lider düştüğü saniyede ACİL İNİŞ butonu ölür.** Tam
gerektiği anda.

Doğrusu: zaman aşımında **son değeri koru**, "bilmiyorum" durumunda buton **açık**
kalsın. Ters yöndeki hata (görev bittiği halde komutların kilitli kalması) hem
güvenli taraf, hem de 3. adımdaki olay teyidi onu zaten düşürüyor.

## Bu ne düzeltiyor

Arayüzde **beş kapı** `missionActive`'e bağlı ve bugün hepsi kalıcı olarak `false`
(`App.tsx`) — çünkü `payload.swarm_state` hiç dolmuyor:

```
:134  guidedEnabled    = !isSimMode && !missionActive   → "buraya git" çubuğu
:143  missionActive                                     → ACİL İNİŞ (kalıcı PASİF)
:154  commandsDisabled = missionActive                  → tekil komutlar (hiç kilitlenmiyor)
:169  missionActive
:183  disabled         = missionActive                  → görev kartı
```

`:154` şartname açısından önemli: *görev sırasında YKİ'den müdahale görevi
BAŞARISIZ sayar* — bugün arayüz bunu **uygulamıyor.** Görev zinciri kapalı olduğu
için şu an zararsız, ADIM 6'da değil.

## Kapsam dışı — bilerek

| Alan | Neden gelmiyor | Etkisi |
|---|---|---|
| `activeMission` (metin, `App.tsx:104`) | Mesh 16 baytta metin taşımıyor | Tek kullanımı joystick görünürlüğü (`:113`) ve orada zaten **VEYA** var: operatörün liste seçimi joystick'i açıyor. Yalnız görev ortasında yeniden bağlanan YKİ'de eksik. İstenirse boş 8 bayta `mission_id` (uint8) konur — o da 0 bayt |
| `activeQrId` (`App.tsx:133`) | Mesh işi değil | `payload.qr`'dan geliyor, `goru` açılınca kendiliğinden dolar |

## Test

**Uçuş YOK — hepsi yerde (CLAUDE.md §7: yerde cevaplanıyorsa uçulmaz).**

1. **G0:** `mission_fsm` açık, iki uçak yerde. Görevi başlat → YKİ'de ACİL İNİŞ
   butonu **aktifleşsin**, tekil komutlar **kilitlensin**.
2. **G0:** Görevi tamamla → ikisi de geri dönsün.
3. **G0 — asıl sınav (şartname senaryosu):** görev sürerken YKİ'yi kapat, aç.
   Buton **≤1 sn içinde yeniden aktif** olmalı. Kenar tetikli çözüm burada kalır.
4. **G0 — lider devri:** görev sürerken lideri `kill` ile düşür. Yeni lider
   seçilene kadar buton **pasifleşmemeli**; seçim sonrası doğru değerle sürmeli.

## Diğer seçenekler (operatör isterse)

| Seçenek | Neden seçilmedi |
|---|---|
| **`SystemEvent` (kenar tetikli)** — mesh'e yine 0 bayt, yalnız arka uçta ~10 satır, uçakta hiç değişiklik yok | Tek paket kaybı = durum sonsuza kadar yanlış. Yeniden bağlanan YKİ `false` başlar — hakem bağlantıyı **kesecek**. Elenmedi, **B'nin üstüne teyit katmanı** olarak alındı (3. adım) |
| **`SwarmState`'i mesh'e çıkar** | 29 Ağustos operatör kararı: "mesh sade kalsın". Ayrıca paketleyici + köprü aboneliği + alıcı yayını **sıfırdan** yazılacaktı; kalp atışında üçü de hazır |
| **YKİ'de türet** | Ölçüldü: `swarm_state` fazı, `formation_reached/stable` ve metin alanları YKİ'de **türetilemez.** `mission_active` türetilebilirdi ama kaynak yine mesh olurdu |

---

# KARAR-11 — Görev 2 manevra modu: dört boşluk kapatıldı, devreye alma bekliyor

**Durum:** 🔵 **KOD HAZIR (28 Ağustos 2026, 20:40) — dağıtım + G0 + uçuş operatör komutu bekliyor**
**Ne zaman:** Operatör "başla" deyince (uçaklar şarjda, dağıtım yapılamadı)
**Karar veren:** Operatör (28 Ağustos 2026): şartname incelemesi + "4 boşluğu kapat sonra benden komut bekle"

> ➡️ **DEVAMI: [`docs/gorev2.md`](gorev2.md)** — aşağıdaki üç ONAY SORUSU
> 30 Ağustos 2026'da cevaplandı (G2-K1/K4/K5) ve ikinci RC alıcı kararıyla
> birlikte **16 boşluk + 29 maddelik sıralı iş listesi** oraya yazıldı. Görev 2'ye
> gelen ÖNCE o belgeyi okur; burası yalnız 28 Ağustos'un kaydı.
>
> **Görev 2 kararları G2-K1…G2-K10 orada, tek yerde — buraya kopyalanmıyor.**
> En yenisi **G2-K10 (30 Ağustos, operatör): ARM yetkisi = SwD tek harekette
> `arm`+`takeoff:H`, üç kapılı** (SwA açık · gaz merkezde · görev YKİ'den
> başlatılmış). Gerekçesi ve uygulaması `gorev2.md` §3 + madde 25.

## Bağlam

Şartname 5.2 (Görev 2, 100 puan) iki mod tanımlıyor: **Sürü Hareket Modu**
(çubuklar = öteleme) ve **MANEVRA MODU** (merkez sabit; pitch/roll =
formasyon DÜZLEMİ eğimi, yaw = formasyon rotasyonu + heading, throttle =
toplu irtifa). Görev 1'in QR-tetikli pitch/roll eğim manevrası AYNI hareket
ama otonom; karıştırılmayacak. "Eğim" uçağın gövdesini yatırmak DEĞİL —
slot irtifa modülasyonu (Şekil 4). Ceza: osilasyon -10, çarpışma -20×N.

Zincir zaten yazılmıştı (1685 satır mode_manager paketi + köprü TIP_KOMUT
iki yönde + FlySky FS-i6X kanal eşlemeli joystick_interpreter) ama hiç
koşmamıştı ve dört boşluğu vardı. 28 Ağu akşamı kapatıldı:

## Kapatılan dört boşluk

1. **`joystick` anahtarı eklendi** (`baslat.sh`) — 🔴 YALNIZ PİLOT
   UÇAĞINDA açılır (üç uçakta açılırsa üç kumanda birden sürüye komut
   basar). Düğümün KÖKSÜZ `/mavros/*` abonelikleri `/drone_N/mavros/*`'a
   remap'lendi (remapsız sessizce veri gelmiyordu).
2. **mode_manager çıkışı `/control/setpoint` → `/control/setpoint/raw`** —
   eskisi kaçınmanın ÇIKIŞ konusuna yazıyordu (iki üretici + CA baypası).
   Artık CA zorunlu aktarım katı olarak arada (formasyon zinciriyle aynı).
   **+ formasyon susturması:** MANEVRA'da (ve eğik HOLD'da) mode_manager
   `/swarm/internal/mode/formasyon_sustur` (Bool, 20 Hz) basar;
   formation_node susar. 3 sn tazelenmezse bayrak DÜŞER (yayıncı ölürse
   formasyon sürücülüğe döner — sahipsiz uçak yok). Görev 1'deki
   qr_step=MANEUVER kapısının Görev 2 karşılığı.
3. **Eğim matematiği tek kaynağa bağlandı:** `maneuver_mode` artık
   `manual_kinematics.apply_tilt` kullanıyor. Eski kopya (a) ortalama
   çıkarmıyordu → asimetrik formasyonda (okbaşı/V) bütün sürü kayıyordu —
   Görev 1'de sahada ölçülmüş hatanın aynısı (14→10,5 m); (b) roll işareti
   Görev 1 sözleşmesinin TERSİYDİ. İki regresyon testi kilitledi
   (merkez-sabitliği + roll işareti); kumanda-çubuk yönünün son sözü
   G0 işaret testinde.
4. **Limitler `ucus_ayarlari` MOD_* bölümünde** (KARAR gerekçeleriyle):
   eğim 15° · yaw **25°/s = PX4_DONUS_HIZI'ndan türetildi** (iki gömülü
   kopya 30 ve 45 idi; PX4 MPC_YAWRAUTO_MAX üstünü sessizce kırpar) ·
   hız 2,0 m/s · varsayılan aralık 7,0 m · deadman 0,5 s. `--kabuk` →
   env → baslat.sh → her iki düğüm. `wing_alpha_deg` de paramlandı
   (45.0 gömülüydü). Sayısal skalerler dynamic_typing (sekans dersi).

`mod` anahtarına `formasyon` bağımlılık kapısı kondu (hareket modu tarifi
formation_node uçurur). Testler: 11/11 (2 yeni regresyon dahil), denetim
0 hata, bash -n temiz. Commit: bkz. git.

## Bilinen açık uçlar (test planına girecek, kod değil)

- Hareket modunda her uçağın mode_manager'ı centroid'i KENDİ tik'inde
  entegre ediyor — uçaklar arası yavaş sürüklenme olasılığı G0/uçuşta
  ölçülecek (sekanstaki gibi tek-yayıncı değil, hesap-herkeste deseni).
- Kumanda→PX4→MAVROS→interpreter zincirinde `manual_control` mü `rc/in`
  mi gerçekte akıyor — pilot uçağında G0'da ölçülecek (rc/in kanıtlı,
  19 Hz; manual_control hiç ölçülmedi).
- İşaret yönleri (çubuk ileri = ?) G0'da kilitlenecek.

## MANEVRA TESTİ PLANI — 🟡 YARINA KALDI (operatör, 28 Ağu 21:35; plan sunuldu, ONAY BEKLİYOR)

Tek buton, SSH'siz, kumandasız otomatik test: sekans deseninin kardeşi
**`manevra_test_surucusu`** (GEÇİCİ, yalnız BİR uçakta yayın — pilot-uçağı
deseni) zamanlanmış SwarmControlCommand basar → mesh → üç mode_manager.
Akış: kalkış 8 m → ÇİZGİ 7 m kur (MOVEMENT, 10 sn) → **ROLL** ±%66
4+4 sn → **PITCH** aynı profil (çizgide dz üretmez — MERKEZ-KAYMASI
regresyon ölçümü) → **YAW** ~45° sola-geri (%50 çubuk = 12,5°/s) →
düzle → YKİ land (slot üstüne). Genlik: eğim ±10°, toplam ~2 dk. Eğim
yalnız z'yi modüle eder — yatay 7 m ayrım hiç değişmez.

### Plan sırasında koddan çıkan İKİ YENİ ENGEL (kod yazılırken kapatılacak)

5. 🔴 `_handle_formation_change` kendi `_formation_offsets`'ini
   GÜNCELLEMİYOR → formasyon değiştirip manevraya geçince gömülü okbaşı
   ofsetleri eğilir ve x-y de ona göre basılır — uçaklar çizgiden okbaşı
   konumlarına IŞINLANMAYA kalkardı (~10 satır düzeltme).
6. 🔴 mode_manager FSM'i sahada READY'ye ULAŞAMAZ: IDLE→PREFLIGHT kapısı
   mission_fsm'in SEMI_AUTONOMOUS'unu (düğüm kapalı), TAKEOFF→READY
   kapısı IN_SWARM'ı (ajanlar ARMED'da kalıyor) istiyor. Çözüm:
   sekans deseninde `test_hazir_atla` parametresi (varsayılan false).
   Tam Görev 2 akışı (kumandadan kalkış + mission_fsm) ADIM 6'nın işi.
   ⚠️ Ayrıca: komut akışı kesilip 5 sn geçince FSM kendiliğinden
   LANDING'e geçip iniş OLAYI basıyor (bugün etkisiz — agent_fsm
   ARMED'da işlemiyor) — sürücü bu yüzden sonda yayını kesmeyip
   çubukları sıfırda tutacak.

Atama notu: mode_manager slotları KİMLİK SIRASIYLA dağıtıyor (Macar yok)
— kuru denetim aynı kuralla çizer, çapraz yerleşimde KALIR der; Macar
iyileştirmesi ayrı P2.

### Operatöre ONAY SORULARI (yarın ilk iş)

1. Sürücü uçağı hangisi? (öneri: ylp00)
2. Genlikler: eğim ±10°, yaw ~45°/12,5°/s — uygun mu?
3. İniş slot üstüne land (EVE fazı YOK) — uygun mu?

### Test merdiveni (onaydan sonra)

1. ⏳ Kod: 5+6 düzeltmeleri + sürücü düğümü + kosucu `manevra` senaryosu
   (kuru: çizgi + eğim zarfı + harita) + panel butonu + birim testler
2. ⏳ Dağıtım (dagit.sh ×3 + env) — uçaklar açılınca
3. ⏳ G0: `/ws/gozlem` + `mod`(3 uçak) + `manevratest`(yalnız sürücü
   uçağı): işaret yönleri, merkez sabitliği, susturma, deadman
4. ⏳ Uçuş A: yukarıdaki çizelge (ÇİZGİ'de roll/pitch/yaw)
5. ⏳ Uçuş B: OKBAŞI/V eğim (asimetri) + tam yaw · ayrıca gerçek
   kumandayla `joystick` zinciri (G0'dan sonra)

---

# KARAR-09 — Kamera hangi uçaklarda, konteynerler eşitlensin mi

**Durum:** 🔵 **İKİSİ DE KARARA BAĞLANDI — (B) kısmen uygulandı, (A) mimari zaten hazır**
**Ne zaman:** ylp00 ve ylp01 ağa geldiğinde tek komut
**Karar veren:** Operatör (28 Ağustos 2026): *"hepsinin konteynerini eşitle"*
**Soruyu soran:** Operatör (28 Ağustos 2026) — *"Bütün dronelara kamera
takmayabiliriz... Ama eğer hepsi eşit olsun dersen hepsinin konteynerini
eşitleyebiliriz."*

## Ayrılması gereken iki soru

Bunlar **bağımsız** ve karıştırılırsa gereksiz iş çıkar:

| | Soru | Bugün |
|---|---|---|
| **A** | Hangi uçaklarda **kamera donanımı** olacak | yalnız ylp02 |
| **B** | Hangi uçaklarda **konteyner ortamı** algı paketlerini taşıyacak | yalnız ylp02 |

Kamerası olmayan bir uçakta `opencv`+`pyzbar`+`zxing` bulunması **hiçbir
şeye mal olmuyor**: 760 MB disk (Pi'lerde 18-19 GB boş) ve o kadar. Düğümler
zaten açılmıyor — `SURU_DUGUMLERI` listesinde yoklar.

## Öneri: B'yi EŞİTLE, A'yı ayrı karar ver

**Gerekçe — bu deponun kendi geçmişi.** `RPI_ESITLEME.md` tam olarak
ayrışma yüzünden var ve `CLAUDE.md` şunu yazıyor: *"Yazılmayan değişiklik,
sonradan saatlerce süren 'neden bunda çalışmıyor' arayışına dönüşüyor."*
28 Ağustos'ta ayrışma **başladı**: 20 Ağustos'ta ylp00 ve ylp02'de imaj
kimliği aynıydı (`661296d…`), artık değil (ylp02 `ea2c1b1e…`).

Eşitlemenin bedeli **uçak başına tek komut**:

```bash
scp ~/yelpence-yedek/yelpence-ros-algi-20260828.tar.gz ylpNN:~/
./deploy/yki/drone_bul.sh ylpNN 'docker load < ~/yelpence-ros-algi-20260828.tar.gz'
```

Kazandırdığı: hangi uçağa kamera takılırsa takılsın ortam hazır; bir uçak
düşüp yerine başkası girdiğinde imaj derdi çıkmıyor; hata ayıklarken
"bunda var, ötekinde yok" sorusu hiç doğmuyor.

## Karşı görüş

Disk ve 628 MB'lık transfer. Bir de imajı güncellersek **üç uçakta birden**
güncellemek gerekir — bugün tek uçakta.

## Kamera donanımı (A) için ayrı düşünce

Şartname üç uçağın da QR okumasını **gerektirmiyorsa**, tek kameralı bir
sürü çalışabilir: kamerası olan uçak QR'ı okur, sonucu mesh'ten paylaşır.
Ama o zaman **o uçak tek hata noktası** olur — düşerse görev biter.
Bu, mesh protokolü ve görev mantığıyla birlikte konuşulmalı; şu an
`QRMissionData` yalnız yerel yayınlanıyor, mesh'e çıkmıyor.

- `[x]` ~~Operatör: B eşitlensin mi?~~ → **EVET, eşitlensin** (28 Ağu).
  `deploy/yki/imaj_esitle.sh` yazıldı ve ylp02'de sınandı. ylp00 ve ylp01
  **kapalı olduğu için yapılamadı** — açılınca uçak başına tek komut:
  `./deploy/yki/imaj_esitle.sh ylp00`
- `[x]` ~~Operatör: A — kaç uçağa kamera?~~ → **Sayı önemli değil.**
  Operatör (28 Ağu): *"kamera tek droneda da olsa birden fazla droneda da
  olsa, hangi drone QR'ı okursa diğer dronelara görevi söyleyecek
  meshten."*
- `[x]` ~~A birden azsa: QR sonucu mesh'ten paylaşılacak mı?~~ → **EVET, ve
  mimari BUNU ZATEN YAPIYOR.** 28 Ağu'da kod okunarak doğrulandı:

  ```
  qr_detector (okuyan drone)
     → /swarm/internal/perception/qr_data
     → esp32_bridge · qr_gorev_paketle()  →  TIP_QR_GOREV (0x14), 16 bayt
     → ESP-NOW yayın (tüm sürü duyar)
     → diğer dronelarda esp32_bridge · _isle_qr_gorev()
     → /swarm/internal/perception/qr_data   ← yerel okumuş gibi
  ```

  204 baytlık QR 16 bayta sığıyor çünkü **ham JSON gönderilmiyor**: okuyan
  drone çözüp yapısal alanları yolluyor (`qr_gorev_veri_t`, static_assert
  ile 16 bayta kilitli). Geçmeyen alanların gerekçesi `mesh_config.h`'de
  satır satır yazılı.

  Ayrıca `TIP_QR_HAM` (0x15) düşünülmüş: **ayrıştırma hatasında** ham metnin
  ilk 52 karakteri gidiyor. Şartname *"QR içeriği örnektir, nihai format
  sonra paylaşılacaktır"* dediği için — format değişirse `json.loads`
  patlar ve sahada elinde hiçbir şey kalmaz; o dilim en azından formatı
  gösterir.

  Firmware her iki tarafta tanıyor (`TX DRONE/main.cpp:238`,
  `RX BASE/main.cpp:242`), köprüde TX (`:2672`) ve RX (`:2459`) var,
  sayaçlar bile duruyor (`qr_tx=`, `qr_rx=`).

  ⚠️ **AMA SAHADA HİÇ KOŞMADI** — bkz. `YAPILACAKLAR` — Görev 1 bloğu, ADIM 5.

---

# KARAR-02 — Claude effort seviyesi: hep `max`, ultracode noktasal

**Durum:** 🟢 **KISMEN YÜRÜRLÜKTE** — `effort=max` kuralı geçerli;
**hatırlatma görevi 29 Ağustos 2026'da KALDIRILDI** (aşağıda)
**Ne zaman:** Her oturum (yalnız `effort=max`)
**Karar veren:** Operatör (15 Ağustos 2026 · daraltma 29 Ağustos 2026)

## Karar

**`/effort` menüsü daima `max` kalır. Ultracode menüden AÇILMAZ.**

Çok ajanlı denetim gerektiğinde operatör **o mesajın içine `ultracode`
kelimesini yazar** — o tur çok ajanlı çalışılır, sonraki tur kendiliğinden
`max`'a döner. Menü hiç kurcalanmaz.

## Neden

`/effort` menüsünde ikisi **aynı listede ve birbirini dışlıyor.** Ultracode
seçilince effort `xhigh`'a düşüyor (ayar şemasındaki tanımı birebir:
*"xhigh effort plus standing dynamic-workflow orchestration"*). Yani ultracode
açmak, düşünme derinliğinden bir kademe feragat etmek demek.

| | Düşünme derinliği | Ajan sayısı |
|---|---|---|
| `max` | en derin | 1 |
| `ultracode` | xhigh (bir kademe altı) | çok + karşıt doğrulama |

**Günlük iş neden `max`:** entegrasyon işi sıralı ve cerrahi — üç satırlık
düzeltme, telemetriden teşhis, komut çalıştırma. Bunlar *derinlik* problemi.
Ayrıca ultracode arka planda dakikalarca sürüyor; sahada pervaneler dönerken
beklenecek şey değil, ve alt ajanlar sohbet bağlamını görmüyor.

**Denetimler neden ultracode:** "%30 paket kaybında hangi senaryoda iki lider
çıkar" bir *kapsama* problemi. Orada 8 bağımsız avcı, 1 derin düşünenden iyi.
Gerekçe somut: Claude bu depoda üç kez çapalama hatası yaptı —
`formation_node`'da ileri-besleme yok dedi (vardı), ylp02'nin eğim değerleri
PX4 varsayılanı dedi (tersiydi), çoklu üretici çakışması çözülmemiş dedi
(susturma ile çözülmüştü). Üçü de tek kanalda bulunamadı. Onu hiç duymamış
bağımsız bir ajan o çapayı miras almıyor.

## ❌ Hatırlatma görevi KALDIRILDI (29 Ağustos 2026, operatör)

Karar başlangıçta Claude'a şunu yüklüyordu: ADIM 1 (`consensus`),
ADIM 3 (`formation_node`) ve ADIM 4 (`collision_avoidance`) ilk kez havaya
kalkmadan önce operatöre *"bu mesaja `ultracode` yazar mısın?"* diye sor.

**Bugün geçersiz, iki sebeple:**

1. **Üç adım da bitti** — üçü de uçtu ve sahada doğrulandı.
2. Operatör 28 Ağustos akşamı denetimi zaten atlamıştı (*"bir daha
   sorulmayacak"*), 29 Ağustos'ta da genel olarak kaldırdı.

**Yürürlükte kalan:** `/effort` hep `max`; ultracode'u **operatör** ister,
o mesajın içine kelimeyi yazarak. Claude önermez, uçuşu bunun için durdurmaz.

## Ayrıca — Claude effort'unu kendi okuyabilir

```bash
echo $CLAUDE_EFFORT      # max / xhigh / high / ...
```

Ultracode'un açık olup olmadığı Claude'a zaten her turda sistem tarafından
bildiriliyor, komut gerekmiyor.

## ✅ Uygulandı — otomatik uyarı (Claude'un hatırlamasına bağlı değil)

`.claude/settings.json` → `UserPromptSubmit` hook'u → `.claude/effort_bekcisi.sh`.
Effort `max` değilse **her mesajda** operatöre uyarı basıyor, `max` iken
tamamen sessiz. Dosya repoda, yani takımdaki herkeste çalışıyor.

**15 Ağustos'ta ölçülenler** (betiğin başında da yazılı, silme):

| Bulgu | Sonuç |
|-------|-------|
| `$CLAUDE_EFFORT` hook ortamında **yok** (68 değişkene bakıldı) | Oradan okunamaz. İlk deneme bunu varsaymıştı ve max'tayken bile bağırıyordu |
| `$CLAUDE_EFFORT` **Bash aracında canlı ve doğru** | Kesin doğrulama yolu bu |
| Seviye transkriptte her `assistant` kaydında yazılı | Hook oradan okuyor |
| Transkript **bir tur geriden** geliyor | Uyarı bir mesaj gecikmeli çıkabilir |
| Hook'ta `$CLAUDE_PROJECT_DIR` ve `$CLAUDE_CODE_SESSION_ID` **var** | Transkript tahminle değil kesin bulunuyor |

Bu yüzden iki katmanlı: **hook** hızlı ama gecikmeli tripwire (operatöre
ekranda uyarı), **Claude** `echo $CLAUDE_EFFORT` ile kesin doğrulama.
Betik okuyamadığında operatörü rahatsız etmiyor, yalnız Claude'a
"doğrula ve bildir" diyor — bozuk okuma kurt masalına dönüşmesin.

Hook çalışmıyorsa: bir kez `/hooks` menüsünü aç (ayar dosyasını yeniden
okutuyor) ya da oturumu yeniden başlat.

## Diğer seçenekler (operatör isterse)

| | Ne | Neden seçilmedi |
|---|----|-----------------|
| A | Menüde hep ultracode | Her turda xhigh; sahada arka plan beklemesi; belge işinde israf |
| B | Aşamaya göre menüden gidip gel | Aynı sonucu veriyor ama elle iş; tek kelime yazmak daha ucuz |
| C | Hiç fan-out yok | Denetimler tek kanalda kalır — çapalama riski karşılıksız |

---

# KARAR-03 — Pil failsafe'i, ölçer modül gelince açılacak

**Durum:** 🟡 BEKLİYOR — donanım alınmadı
**Ne zaman:** LiPo pil ölçer modül alınıp RPi'ye bağlandığında
**Karar veren:** Operatör (15 Ağustos 2026)

## Karar

**Pil failsafe'i şimdi açılmayacak.** İleride bir **LiPo pil ölçer modül**
alınacak, voltaj verisi doğrudan **RPi'ye** verilecek. O zaman:

1. Pil değerleri YKİ arayüzünde görünecek
2. Pil failsafe'i o zaman devreye alınacak

## Neden şimdi değil

Uçaklar **regülatörden** besleniyor, PX4'te `BAT1_SOURCE` disabled. Okunan
3.1 V gerçek pil voltajı değil. Bu yüzden pil izleme **üç yerde birden**
kapalı (`BATARYA_KRITIK_V=0.0`). Olmayan bir ölçüme dayanarak failsafe
açmak, uçağı yerde tutan sahte bir alarm üretir.

## Nasıl uygulanacak — açılması artık TEK parametre

15 Ağustos'taki `preflight_checker` düzeltmesinden sonra eşik üç yerde de
`ctx.battery_critical_voltage_v`'den geliyor. Modül gelince yapılacak:

| Adım | Ne |
|------|-----|
| 1 | Modülün voltajını yayınlayan küçük bir düğüm (I2C/UART, ~60 satır) |
| 2 | `AgentStatus.battery_voltage_v` bu kaynaktan beslensin (şu an MAVROS'tan) — **ve `px4_bridge.py:546`'daki 12.6 V sahtesi kaldırılsın**: 21 Ağustos'ta ölçüldü, PX4 "bilmiyorum" (65.535 V) derken AgentStatus'a 12.6/%100 basılıyor ve pil "dolu" görünüyor (TUZAKLAR 1.20) |
| 3 | `deploy/rpi/baslat.sh` → `BATARYA_KRITIK_V=13.6` |
| 4 | `src/gcs/frontend/src/services/gorunum.ts` → `PIL_GOSTER = true` |
| 5 | `src/gcs/backend/config.yaml` → `alerts.susturulan`'dan batarya kodlarını çıkar |
| 6 | 🔴 **`esp32_bridge`'in `healthy` türetimine pil eşiğini ekle** — aşağıya bak |

> 🔴 **6. adım kolayca atlanır ve sessizce yanlış sonuç verir.** Mesh'te
> `healthy` bir **bit olarak taşınmıyor**; alıcı tarafta türetiliyor:
> `ekf_ok ∧ ¬kill_switch ∧ state≠FAILSAFE` (`esp32_bridge_node.py:974`).
> Pil izleme açıldığında **pil düşüşü bu türetime yansımaz** — komşular pili
> bitmiş bir uçağı `healthy=True` görmeye devam eder ve o uçak lider adayı
> kalır. İki seçenek: ya mesh paketine bir bit eklenecek (firmware
> değişikliği) ya da eşik **alıcı tarafta da** uygulanacak (yalnız ROS,
> firmware'e dokunmaz — tercih edilen).

⚠️ **3, 4, 5 birlikte yapılmazsa** sistem tutarsız davranır: biri pili
umursar, diğeri umursamaz. `DURUM.md` §3'te de yazılı.

## Test

- **Yerde:** modül takılı, pil takılı → okunan voltaj çok metreyle uyuşuyor mu
- **Yerde:** eşiği geçici olarak okunan voltajın üstüne çek → preflight
  arming'i engelliyor mu (`test_esik_baglamdan_gelir` bunu zaten kilitliyor)
- **Yerde:** eşiği 0.0'a çek → engel kalkıyor mu
- Uçuş testi **gerekmiyor**; failsafe yolu zaten ölçülmüş kod

---

# Uygulanmış kararlar — özet

Bunlar **bitti ve sahada doğrulandı.** Gerekçeleri, ölçümleri ve elenen
seçenekleri git'te duruyor: `git show 783afab:docs/KARARLAR.md`

| Karar | Ne | Durum |
|---|---|---|
| **KARAR-01** | Çarpışma önleme **Seçenek C** — `collision_avoidance`, komşu verisi ham `AgentStatus`'tan (yumuşatma yok) | ✅ 21 Ağu açıldı, 22 Ağu'dan beri her uçuşta çalışıyor |
| **KARAR-04** | Üç uçak birden uçunca değişecek parametreler (`SURU_BEKLENEN_UCAK=3`, kadro `1 2 3`) | ✅ 25 Ağu, ylp01 dönünce uygulandı |
| **KARAR-05** | Konteyner imajı: Dockerfile geri gelmeyecek, `docker save` yeter | ✅ 20 Ağu, yedek alındı ve doğrulandı |
| **KARAR-06** | Kaçınmada kaçış yönü: **DİKEY birincil**, yatay itme yalnız sert kabukta | ✅ 23 Ağu uygulandı, aynı akşam uçtu |
| **KARAR-07** | Körlükte dönüş tutması: **yerde + disarm** kayıp komşu MUAF | ✅ 25 Ağu (`6258eab`), uçuşla doğrulandı |
| **KARAR-10** | Formasyon geçiş testi: sekans **UÇAKTA**, YKİ yalnız başlatır | ✅ 28 Ağu uçtu (5 faz, `avoid=0`). Aparat geçici — `mission1` sahaya alınınca silinecek (`YAPILACAKLAR` P3) |

---

---

# KARAR-12 — Kaçınmanın 3 m altındaki körlüğü

**Durum:** 🟡 BEKLİYOR
**Ne zaman:** Alçak irtifada karşılaşma ihtimali olan ilk uçuştan önce
**Karar veren:** açık — operatöre sunuldu 31 Ağu, ertelendi

## Karar
`collision_avoidance.altitude_gate_m = 3.0` altında kaçınma setpoint'e
**hiç dokunmuyor** (ham setpoint aynen geçiriliyor). Bu körlük kalsın mı,
yoksa kapı arm+havada şartıyla mı düşürülsün?

## Neden
31 Ağustos 12:50 uçuşunda üç uçak **0,36 m**'ye kadar yaklaştı ve kaçınma
**hiç ateşlemedi** — ylp00 tam o kapının altında alçalıyordu (`gate_alt`
sayacı artıyor, `avoid=0`). Yani son savunma hattı, en çok gerektiği anda
— yere ve birbirine yakınken — kapalı.

Kapının gerekçesi de geçerli ve belgeli: irtifa `alt_amsl - home_amsl`'den
okunuyor çünkü **EKF yerel z ~10 m kayabiliyor**; kayma yukarı yönlüyse
uçak YERDEYKEN kapı açılır ve kaçınma yerdeki uçağı "komşu" sanıp yatay
itme üretir.

## Nasıl uygulanacak (öneri)
Kapıyı düşürmek yerine **şart eklemek**: `irtifa >= 1.5 m VE armed VE
uçuş modu otomatik`. Disarm bir uçak havada olamaz — bu, irtifa
referansından bağımsız bir doğrulama (aynı numara B15 kalkış kapısında
zaten kullanılıyor, `mode_context.kalkis_kapisi_degerlendir`).
Maliyet ~15 satır + test.

## Test
- G0 yerde: üç uçak disarm, kapı KAPALI kalmalı (`gate_alt` artmalı)
- G1 yerde: bir uçak armlı ve 1,5 m üstünde taşınırken kapı AÇILMALI
- Uçuşta: `ca.log` `avoid` sayacı ve `gate_alt` sayacı birlikte okunmalı

## Diğer seçenekler (operatör isterse)

| Seçenek | Neden seçilmedi |
|---|---|
| Kapıyı olduğu gibi bırak | 31 Ağu'da 36 cm'ye kadar korumasız kalındı; tek dayanak "karşılaşmayan uçuş tasarlamak" |
| Kapıyı 0'a indir | EKF kayması yerdeki uçağı komşu yapar — 1 Ağustos pervane kıran arızanın sınıfı |
| Yalnız DİKEY yol vermeyi aç, yatayı kapalı tut | Ara çözüm; alçakta dikey kaçış zaten tabana takılır (`dikey_taban_m`) |

---

# KARAR-13 — Formasyon uçuşunda YER DİZİLİMİ kuralı

**Durum:** 🟢 UYGULANACAK (bir sonraki formasyon uçuşunda)
**Karar veren:** ölçümden çıktı, 31 Ağu
⚠️ **Aralık kısmı ÇELİŞİYOR — bkz. KARAR-14.** Yer dizilimi kuralı aynen
geçerli; tartışmalı olan yalnız 9 m mi 7 m mi.

## Karar
Kumandadan formasyona geçilecek uçuşlarda uçaklar yere **hedef formasyonun
şeklinde** dizilir. Rastgele dizilim kabul edilmez.

## Neden
Ölçüldü (`gorev_kanit_ucus.plan_dogrula`, sahte telemetriyle taranarak):

* Rastgele dizilim → ilk morf (`YER → ÇİZGİ`) en dar an **4,83 m**,
  kaçınma girişine pay **0,83 m**. **Aralığı büyütmek BU PAYI DÜZELTMEZ** —
  darboğaz merkez slotu, aralıkla ölçeklenmiyor (7→14 m taramasında sayı
  sabit kaldı).
* Formasyon şeklinde dizilim → darboğaz `okbaşı→V` morfuna kayıyor ve
  **aralıkla ölçekleniyor**: 7 m → 4,95 m (pay 0,95) · **9 m → 6,36 m
  (pay 2,36)** · 10 m → 7,07 m.

Bu yüzden aralık 9 m'ye çıkarıldı **ve** dizilim kuralı kondu; ikisi
birlikte anlamlı, tek başına biri yetmiyor.

## Test
`--senaryo formasyon_gecis --aralik 9 --kuru --harita` — `SONUÇ: GEÇTİ` ve
en kritik an ≥ 6 m olmalı.

# KARAR-14 — Varsayılan formasyon aralığı: 9 m mi 7 m mi

**Durum:** 🔴 OPERATÖR ONAYI BEKLİYOR — şu an kodda **7 m**
**Karar veren:** operatör talimatı (31 Ağu, madde 29) ile ölçüm çelişti

## Karar
`ucus_ayarlari.MOD_ARALIK_M` **9.0 → 7.0 geri alındı.** Operatörün madde 29
talimatı birebir şöyleydi: *"hiç bişey girmezsek varsayılan değer 7m
olsun."* Talimat açık ve yeni olduğu için uygulandı.

## Neden bu bir ÇELİŞKİ
KARAR-13 aynı gün aralığı **7 → 9 m** çıkarmıştı ve gerekçesi ölçümdü:

| aralık | `okbaşı→V` en dar an | kaçınma girişine (d0 = 4 m) pay |
|--------|----------------------|----------------------------------|
| 7 m    | 4,95 m               | **0,95 m**                       |
| 9 m    | 6,36 m               | 2,36 m                           |

31 Ağustos kalkışında ölçülen sürüklenme: ylp01 **2,17 m** · ylp00 0,90 m ·
ylp02 0,18 m. Yani 7 m'de pay, ölçülen sürüklenmenin **altında** —
`okbaşı→V` morfunda kaçınma **tetiklenebilir.** Çarpışma değil: formasyon
bozulur, ölçüm kirlenir. İkinci etki: durgun formasyonda uçaklar kaçınma
**çıkış** eşiğinin (6,5 m) yalnız 0,5 m üstünde kalır — bir kez açılan
kaçınma uzun süre kapanmaz.

`python3 src/gcs/ucus_ayarlari.py` bu iki uyarıyı **kendisi basıyor**.

## Operatörün seçeceği
- **(A) 7 m kalsın** — talimat aynen. Formasyon geçişli uçuşta kaçınma
  tetiklenebileceği bilinerek uçulur; kayıttan `avoid` sayacına bakılır.
- **(B) 9 m'ye dönülsün** — KARAR-13 korunur, saha ~%29 daha geniş ister.
- **(C) Varsayılan 7 kalsın, formasyon geçişli uçuşlarda kutuya 9 yazılsın**
  — 🟢 **önerilen.** Madde 29 zinciri sayıyı BAŞLAT paketiyle üç uçağa
  birden gönderiyor, yani tek kutuya `9` yazmak yeterli; kod değişmiyor.

## Test
`--senaryo formasyon_gecis --aralik <7 ya da 9> --kuru --harita`; ayrıca
`python3 src/gcs/ucus_ayarlari.py` uyarıları okunur.

# KARAR-15 — Kaçınma eşikleri 5 m aralıkta KİLİTLENİYOR

**Durum:** 🔴 OPERATÖR KARARI BEKLİYOR — görev günü riski
**Karar veren:** şartname okumasından çıktı, 1 Eylül 2026

## Sorun

Şartname senaryo madde 3: *"Formasyon sırasında ajanlar arası X (**Örn: 5m**)
metre olacaktır."* Aralığı hakem söylüyor.

Bizim kaçınma eşiklerimiz:

| | |
|---|---|
| giriş (`d0`) | 4,0 m |
| **çıkış** (`d0 + hist`) | **6,5 m** |
| hakemin örnek aralığı | **5,0 m** |

5 m aralıkta uçaklar nominal olarak **çıkış eşiğinin altında** durur. Yani
kaçınma bir kez açılırsa **hiçbir zaman kapanamaz** — formasyon kurulamaz.
Üstelik giriş eşiğine pay yalnız 1,0 m, oysa ölçülen sürüklenme 2,17 m'ye
kadar çıktı; kaçınma rutin olarak tetiklenir.

**Bu teorik değil:** 31 Ağustos V geçişinde birebir yaşandı — kaçınma
ylp01'de 666, ylp02'de 633 kare açık kaldı ve V formasyonu hiç kurulamadı.

`canli_param.ARALIK_ALT_M = 4.0` olduğu için kutuya 5 yazmak **kabul edilir**,
yani hata vermeden başarısız oluruz.

## Seçenekler

- **(A) Görev 2 için eşikleri küçült** — giriş 3,0 m / çıkış 4,0 m. 5 m'de
  çıkış eşiğinin 1 m üstünde kalınır. Uçak gövdesi ~0,5 m, yani 3 m hâlâ altı
  gövde genişliği. 🟢 **önerilen**, ama bir EMNİYET eşiği ve KARAR-12
  (kaçınmanın 3 m altı körlüğü) ile doğrudan ilişkili.
- **(B) Alt sınırı yükselt** — `ARALIK_ALT_M`'i 7 m yap, 5 m talebini reddet.
  Şartnameye aykırı; hakem 5 m derse görev başarısız.
- **(C) Dokunma** — 5 m gelirse kaçınma kilitlenir, bilerek uçulur.

## Test

`--senaryo formasyon_gecis --aralik 5 --kuru` + `ucus_ayarlari.py` uyarıları;
sonra tek formasyon geçişli kısa uçuşta `ca.log` `avoid=` sayacı sıfır kalmalı.

# Karar şablonu (yeni karar eklerken kopyala)

```markdown
# KARAR-NN — <konu>

**Durum:** 🟡 BEKLİYOR
**Ne zaman:** <hangi aşama / hangi iş>
**Karar veren:** <kim> (<tarih>)

## Karar
<tek cümle: ne yapılacak>

## Neden
<gerekçe, ölçüm varsa sayılarla>

## Nasıl uygulanacak
<adımlar, maliyet>

## Test
<zorunlu testler>

## Diğer seçenekler (operatör isterse)
<tablo: seçenek, neden seçilmedi>
```
