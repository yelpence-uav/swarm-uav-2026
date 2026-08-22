# YAPILACAKLAR

**Son güncelleme:** 23 Ağustos 2026, 01:30 — P0.15 KAPANDI (kök neden bulundu)

## 🚨 SONRAKİ OPERATÖRE — ÖNCE BUNLAR (22 Ağustos gecesi bırakıldı)

> Bu blok bir oturumun sonunda, **uçuş yarıda kalmışken** yazıldı. Aşağıdaki
> sıra rastgele değil: 1 ve 2 yapılmadan uçulmaz.

### 1. ✅ `docker restart drone1` — YAPILDI (22 Ağustos 17:31)

Kaçınmanın ivme sınırları (`30 → 5,66 m/s²`) artık **ylp00'da da etkin**.
Açılış logundan doğrulandı:

```
collision_avoidance basladi (komsular: 2,3, d0=10.0 hard=6.0,
  ivme normal=3.58 acil=5.66 donus=0.50, basit_kacinma KAPALI)
```

11 düğüm ayakta, YKİ drone1'i yeniden görüyor. **İki uçak da aynı
ivme sınırlarında** — ayrışma kalmadı.

### 2. 🔴 Uçuş öncesi `uptime -s` (P0.17)

ylp00'ın Pi'si bir kez **öldü ve öyle kaldı** (kırmızı ışık, elle açıldı).
Sebep bilinmiyor. Pi son 10 dakikada açılmışsa **uçma.** Çökme kaydı artık
kurulu, bir daha olursa iz bırakacak → `TUZAKLAR.md` §2.17.

🔴 **Pi ölürse GÜCÜ KESME** — iz RAM'de, güç giderse silinir.

### 3. 🔴 Sıradaki uçuş: üç düzeltmenin doğrulanması

Tam tarifi `PLAN.md` **"SIRADAKİ UÇUŞ"** bölümünde. Özet:

| | önceki uçuş | beklenen |
|---|---|---|
| kaçış maks eğim | **34,0°** | **≤ 20°** |
| dönüş tepe hızı | 3,21 m/s | ~1,73 m/s |
| **kaçışın gücü** | 3,88 m kaçtı | **aynı kalmalı** |

Son satır kritik: kaçış **zayıflarsa düzeltme yanlış** demektir.

Ölçüm `/mavros/imu/data` quaternion'undan roll/pitch, **evrelere ayrılmış**
(asılı / kaçış / dönüş / asılı). ⚠️ Konum ve hız verisi bu sorunu
**gizler** — `TUZAKLAR.md` §2.18.

Manevra: tek uçak asılı, ikinci uçak kumandayla **yandan** yaklaşır.
**Tepeden yaklaşılmaz** (`xy_guard=0.3` kör noktası), **altından geçilmez.**

### 4. 🔴 Formasyon uçuşundan ÖNCE: `d0=10 hard=6` GERİ ALINACAK

Bu değerler yalnız kaçınma testi için, uçaklara **elle** kondu. 12 m
aralıkta formasyonun planlı en yakın yaklaşması 8,49 m — `d0=10` normal
formasyon geçişinde tetiklenir ve formasyonla çekişir.
Geri alma komutu: `RPI_ESITLEME.md` **K2**.

### 5. 🟠 Kumanda hangi uçağa bağlı — NETLEŞMEDİ

ylp00'da `rc_link_ok: true`. İkinci uçağı kumandayla kaldırırken ylp00'ın
modunun alınıp alınmadığı ölçülmedi. **Uçuşsuz, 30 saniyelik yer testiyle**
kesinleşir: iki uçak yerde ve disarm dururken çubuğu oynat, ylp00'ın RC
girişi değişiyor mu bak.

Bu netleşmeden aynı test düzeni üçüncü kez aynı yerde kesilebilir. (Not:
mod geri alma açığı kapatıldı, yani pilot müdahalesi artık **kalıcı** —
ama kumandanın hangi uçağı sürdüğü hâlâ bilinmiyor.)

### 6. 🟠 YKİ uyarılarının kalıcı kaydı yok → **P1.16**

Bir oturumda **~32 bildirim** gitti ve **hiçbiri kayıtlı değil**.
`AlertManager` yalnız bellekte tutuyor. ~20 satırlık iş, uçuş sonrası
"ne oldu" sorusunu cevaplanabilir kılıyor.

### Bilinmesi gereken, düzeltilmemiş
- Kaçınma **asılı dururken teğet bileşen üretmiyor** (yalnız düz geriye iter)
- **Tepeden yaklaşmada koruma YOK** (`xy_guard=0.3` altı komşu tamamen atlanır)
- Uçakta üretilen `SystemEvent`'lerin çoğu YKİ'ye **ulaşmıyor** (mesh'te
  `TIP_EVENT` yok) — yalnız kaçınma körlüğü bayrakla taşınıyor → P1.15

---

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

### ✅ P0.12 TAMAMEN KAPANDI — (a) 20 Ağustos yerde, (b) 21 Ağustos uçuşta

`WORKFLOW_BULGULAR.md`'deki 42 bulgunun yalnız 7'si doğrulanabilmişti
(denetim maliyet yüzünden kesildi). Bu ikisi **20 Ağustos'ta kod okunarak
doğrulandı** — iddia değil, mekanizma satırıyla duruyor. İkisi de tek
dosyada, toplamı ~4 satır, ikisi de geri alınabilir.

**(a) Yerdeki disarm uçak sonsuza kadar "ben liderim" yayınlıyor**

`consensus_node.py:183` — `own_airborne` kapısı `c3068c8` ile kalktı, yayın
artık yalnız `ctx.is_leader`'a bağlı. Ama `ctx.is_leader` **hiçbir yerde geri
alınmıyor**. `election.py:decide_change` ilk satırı:

```python
candidate = min(effective) if effective else 0
if candidate == 0:
    return None          # herkes IDLE -> _set_leader HIC cagrilmiyor
```

İniş sonrası iki uçak da IDLE olunca `effective` boşalır, fonksiyon hemen
`None` döner, lider bayrağı **True kalır**. Yerde duran disarm uçak mesh'e
10 Hz `LeaderHeartbeat` basmaya devam eder. İkinci uçuşta konteyner yeniden
başlatılmadan diğer uçak arm edilirse liderlik 5–10 Hz'de gidip gelir —
pervaneler dönerken, guided komutlarla **aynı ESP-NOW kanalında**.

- `[x]` 🔴 ~~Düzeltme~~ → **YAPILDI.** Bir satırlık kapı yetmedi: bayrağı
  susturmak uçağın kendini lider **sanmasını** engellemiyordu. Kök nedene
  gidildi — `_tick`'e `_liderligi_birak()` dalı eklendi:
  `decide_change` devralacak birini bulamadıysa **ve** biz uygun değilsek
  liderlik bırakılır (`is_leader=False`, `leader_id=0`, kalp atışı kesilir).
  > **Yerleşim bilinçli:** dal `decide_change`'den **sonra**, yani normal
  > devir yolu öncelikli kalıyor — havada çalışan lider değişimi mantığına
  > dokunulmadı. Ayrıca `election_round` **artırılmıyor**: çekilme bir seçim
  > değil; turu artırmak komşunun meşru seçimini `msg.election_round <
  > ctx.election_round` filtresine takardı.
  > İkinci kapı olarak kalp atışına da `self._agent_id in elig` şartı kondu.
- `[x]` 🔴 **Test: 8/8** — `swarm_core/test/test_lider_birakma.py`.
  Kilitlenenler: iniş sonrası bırakma · tekrar tick'te olay yayılmaması ·
  round artmaması · **uygun liderin liderliği KORUMASI** · devralacak biri
  varsa normal devir yolunun çalışması · yeniden seçilebilme.
- `[x]` 🔴 **YER TESTİ GEÇTİ — iki uçak, pervanesiz, 20 Ağustos 20:05.**
  Sıfır sahte veri; komut zinciri gerçek (YKİ → mesh → köprü → FSM →
  consensus).

  **Önce hata mevcut kodda gösterildi:** 12 sn sahte ARMED enjeksiyonundan
  **2.8 DAKİKA** sonra ylp00 `state=1` (IDLE), `armed=false` iken mesh'e
  **10.0 Hz** `LeaderHeartbeat(leader_id=1)` basıyordu.

  **Düzeltme sonrası, iki uçakla:**

  ```
  ylp00                                  ylp02
  Lider: 0 -> 1  (secildi, HB 10.2 Hz)   Lider: 0 -> 1 (takip, kendi yayini 0,
                                                        mesh'ten 40 HB aldi)
  --- yalniz ylp00 disarm ---
  Lider: 1 -> 3  (DEVRETTI)              Lider: 1 -> 3 (DEVRALDI, HB 41)
  BIRAKILDI satiri YOK  <-- kritik
  --- ylp02 de disarm ---
  HB = 0                                 liderlik BIRAKILDI · HB = 0
  ```

  🔴 **En önemli satır: ylp00'da `BIRAKILDI` YOK.** Devralacak biri varken
  yeni dal **devreye girmiyor**, `decide_change`'in normal devir yolu
  çalışıyor — dalın `decide_change`'den sonraya konmasının sebebi buydu ve
  sahada doğrulandı. Tek uçakla bu ölçülemezdi.

  Tek `BIRAKILDI` satırı — histerezis çalışıyor, seç-bırak döngüsü yok.

**(b) `land` sonrası kuyrukta kalan GOTO tekrarları inişi iptal ediyor**

`esp32_bridge_node.py:1688` — kuyruk ayıklaması yalnız **aynı hedefe giden
GOTO** için çalışıyor; `land` bir `TIP_KOMUT` ve bekleyen GOTO tekrarlarını
temizlemiyor (yorumu da bunu açıkça söylüyor: *"TIP_KOMUT'ta ayiklama YOK"*).

Zincir: `land` gider → uçak AUTO.LAND'e geçer, `_guided_hedef=None` →
0.25 s sonra bayat GOTO kopyası varır → `_isle_goto` **koşulsuz**
`_guided_string('offboard')` çağırır (`:1204`) ve `_guided_hedef`'i yeniden
kurar → 10 Hz `_guided_hedef_tekrar` onu sonsuza kadar tazeler. **İniş iptal
olur**, üstelik `px4_bridge`'in 0.5 s bayatlama koruması hiç tetiklenmez
çünkü hedef sürekli tazeleniyor.

- `[x]` 🔴 ~~Düzeltme~~ → **YAPILDI.** `_guided_gonder`'e `goto_iptal`
  parametresi eklendi; `land`/`rtl`/`disarm` kuyruğa girerken **o hedefe ait**
  bekleyen `TIP_GOTO` kayıtları düşürülüyor ve kaç tane düştüğü loglanıyor.
  > **Kapsam dar tutuldu:** yalnız aynı hedefin GOTO'ları. Diğer uçağın
  > kuyruğuna dokunulmuyor — bir uçağı indirmek diğerinin görevini kesmez.
  > `TIP_KOMUT`'ta genel ayıklama hâlâ YOK (arm/takeoff/land birbirini ezmez).
- `[x]` 🟠 **UÇUŞTA DOĞRULANDI (21 Ağustos sabahı, ylp00, tek bacak + iptal).**
  Bacağın 0,7. saniyesinde `land` gönderildi. Üç kanıt birden:

  ```
  KOPRU : iptal komutu: drone1 icin bekleyen 1 kayit / 3 gonderilmemis
          kopya (GOTO/ARM/TAKEOFF) dusuruldu
  UCAK  : 818.601 goto -> 818.603 land -> 818.9/819.3/819.6 land
          (land'den sonra SIFIR goto cercevesi)
  DAVRANIS: AUTO.LAND kesintisiz, t+24 sn'de yerde ve disarm, geri
          tirmanma YOK
  ```

  Zamanlama şansı da kanıtı güçlendirdi: ilk goto kopyası iptalden 2 ms
  önce uçağa varmıştı — düşürülen 3 kopya gitseydi hata **kesin**
  tetiklenirdi.

  > İlk deneme (aynı sabah) tetikleme hatası yüzünden boşa uçtu: görev
  > çıktısı dosyaya yönlendirilince python blok tamponluyor, "bacak
  > başladı" satırı dosyaya görev biterken düştü ve iptal ölü sürece
  > gitti. Ders: dosyadan an yakalayacaksan `python3 -u`. O uçuş da boşa
  > gitmedi — tekli senaryo zinciri (kalkış-bacak-tırmanış-iniş) temiz
  > uçtu, varış 0,9 m.
- `[x]` 🔴 **Test: 9/9** — `swarm_control/test/test_guided_kuyruk_iptal.py`.
  Kilitlenenler: land/rtl/disarm düşürüyor · **diğer uçağa dokunmuyor** ·
  takeoff/arm **düşürmüyor** · eski davranış (yeni GOTO eskisini ezer) korundu.
- `[ ]` 🟡 İkinci kapı olarak `_isle_goto`, son `land`'den sonra gelen GOTO'yu
  yok sayabilir (zaman damgası) — mesh yeniden sıralaması için kuşak ve
  pantolon askısı. Baz tarafı ayıklama gerçekçi durumu zaten kapatıyor.
- `[x]` 🔴 ~~Aynı mekanizma DISARM → bekleyen ARM/TAKEOFF için de gerekli~~
  → **YAPILDI ve SAHADA DOĞRULANDI (20 Ağustos 20:16).**

  İki uçaklı yer testi sırasında **ölçüldü** — artık iddia değil:

  ```
  ONCE (duzeltmesiz)                SONRA (duzeltmeli)
  784.475  land                     202.975  takeoff:5.0  <- land'den ONCE
  784.779  takeoff  <- 0.3 sn SONRA 203.280  land
  785.182  takeoff  <- 0.7 sn SONRA 203.686  land  (takeoff YOK)
  ```

  Havadaki karşılığı: operatör iniş komutu verir, uçak alçalmaya başlar,
  bayat `takeoff` varır ve **uçak geri tırmanır.**

  Baz köprüsü logu: *"iptal komutu: drone1 icin bekleyen 1 kayit /
  3 gonderilmemis kopya (GOTO/ARM/TAKEOFF) dusuruldu"*.

  ⚠️ **Bu düzeltme BAZ tarafında koşuyor** — uçaklara dağıtmak YETMEZ,
  dizüstünün de `colcon build` + YKİ restart olması gerekir. Aynı tuzağa iki
  kez düşüldü (bkz. `TUZAKLAR` §2.11).

### ✅ P0.14 DÜZELTİLDİ (20 Ağustos 20:45) — yer testi bekliyor

`WORKFLOW_BULGULAR.md`'deki 42 bulgunun yalnız 7'si doğrulanabildi. Bu ikisi
**iki bağımsız doğrulayıcının da onayladığı** tek P0 çiftidir ve
**birbirini büyütüyorlar** — üstelik hiçbir iş listesine girmemişlerdi.

**(a) 300 ms'lik lider kaybı yolu hiç çalışmıyor** — `election.py:47`

```python
if not ctx.is_leader and ctx.leader_id != 0 and own_airborne:   # <- hep False
```

`own_airborne = own.state in AIRBORNE_STATES` ve `AIRBORNE_STATES =
{TAKEOFF, IN_SWARM, EXECUTING_TASK}`. Ama `kalkis_olayla=false` olduğu için
FSM **uçuş boyunca ARMED'da kalıyor** ve ARMED o kümede yok. Yani
`heartbeat_timeout_ms = 300` hiçbir kararda kullanılmıyor — `hb_timeout_s`'in
repoda başka tüketicisi de yok.

**(b) Yedek olan bayatlık denetimi YANLIŞ AKIŞI ölçüyor** — `consensus_context.py:93`

`update_status` her `AgentStatus`'ta `last_update`'i yazıyor. Ama komşunun
`AgentStatus`'unun **iki ayrı mesh kaynağı** var:

```
TIP_POSE   10 Hz  -> yalniz konum/hiz tasir, AMA tum kaydi yeniden yayinliyor
TIP_DURUM   1 Hz  -> state/healthy/estimator_ok BURADAN gelir, tekrari YOK
```

Yani `rec.is_stale(now, 3.0)` **POSE akışının** tazeliğini ölçüyor, koruduğu
alanlarınkini değil. Liderin DURUM paketleri mesh'te düşerse (broadcast'te
~%30 kayıp) POSE geçmeye devam eder ve takipçiler onu **süresiz "taze + ARMED
+ healthy"** görür.

**Birleşik sonuç:** lider FAILSAFE'e düşse, disarm olsa, IDLE'a dönse bile
takipçiler bunu **hiç fark etmez**. Birincil yol (300 ms) ölü, yedek yol
(3 sn) yanlış akışı ölçüyor. **Düşmüş bir lider süresiz olarak sürünün lideri
kalır** ve kimse yeni seçim yapmaz.

- `[x]` 🔴 ~~(a) `own_airborne`~~ → **`own_aday` yapıldı.** Doğru şart havada
  olmak değil **ADAY** olmak; uygun değilsek zaten seçim yapamayız.
  > 🔎 **İkinci ölü kapı çıktı:** aynı fonksiyonda `leader_airborne` da vardı
  > ve o da ARMED'ı dışlıyordu. Bugün **tesadüfen** çalışıyordu, çünkü mesh
  > ARMED'ı KALKIS'a eşleyip karşı tarafta TAKEOFF'a çözüyor
  > (`TUZAKLAR` §4.9) — o eşleme ADIM 3/4'te **değişecek** ve değiştiği gün
  > kapı sessizce kapanırdı. `lider_yayinlamali` (ELIGIBLE_STATES) oldu.
  > Dayandığı varsayım da geçersizdi: "yerdeki lider yayın yapmaz" — 19
  > Ağustos'tan beri yapıyor, üstelik P0.12(a) ile uygunluğunu yitiren lider
  > yayını **kendisi** kesiyor.
- `[x]` 🔴 **Eşik 300 → 1000 ms.** Bu yol ilk kez gerçekten devreye giriyor,
  yani 300 hiç **sınanmamıştı**. Kalp atışı 10 Hz ve mesh kaybı ~%30:
  300 ms = 3 ardışık kayıp, olasılığı `0.3³ = %2.7` → birkaç saniyede bir
  yanlış "lider kayıp", yani **lider yalpası**. 1000 ms = 10 ardışık kayıp
  (`6e-6`), yine de yedek yoldan (3 sn) **üç kat hızlı**.
- `[x]` 🔴 ~~(b) alan başına tazelik~~ → **kök nedende çözüldü.** `AgentRec`'e
  ikinci damga eklemek yetmezdi: consensus hangi alanın hangi akıştan
  geldiğini **bilemez**. Onu yalnız köprü bilir. `esp32_bridge` artık komşu
  başına **son DURUM paketinin** anını tutuyor ve yayınlarken bayatsa
  `healthy=False` yapıyor. Her tüketici birden faydalanıyor.
  > Eşik **5.0 sn** (parametre `komsu_durum_bayat_s`). DURUM 1 Hz ve
  > tekrarsız: 3 sn = 3 ardışık kayıp = **%2.7** → dakikada bir yanlış alarm.
  > 5 sn = %0.24 → ~7 dakikada bir. Kalp atışı yolu artık birincil dedektör
  > olduğu için bu **yedek** yol muhafazakâr olabilir.
- `[x]` 🔴 **Test: 12 yeni** — `test_lider_kaybi.py` (6) +
  `test_durum_bayatligi.py` (6). Bozulmaması gerekenler de kilitli: taze kalp
  atışında lider düşmüyor · aday değilsek karışmıyoruz · kendimiz liderken dal
  çalışmıyor · yerdeki lider düşürülmüyor · eşik altında healthy korunuyor.
- `[x]` 🟠 **YER TESTİ GEÇTİ (21 Ağustos 00:59, iki uçak, gerçek arm).**
  Araç: `deploy/rpi/teshis/lider_kaybi_test.sh` + `lider_kaybi_izle.py`
  (ölçüm tek uçağın tek saatinde — SSH/ağ gecikmesi ölçüme giremez).

  Zincir: görev olayı → FSM gerçek ARMED → `Lider: 3 -> 1` → liderin
  consensus'u `kill -9` → takipçi **1.063 sn** sonra kendini seçti
  (`Lider: 1 -> 3`, sebep=LEADER_FAULT) → ilk kalp atışı **+6 ms**.
  Bonus kanıtlar: inişle uygunluğunu yitiren lider liderliği BIRAKTI
  (P0.12 canlı) ve incarnation sıfırlama doğru işledi. Eskiden bu yol
  hiç çalışmıyordu.
- `[x]` 🟡 **İKİ EŞİK DE UÇUŞTA ÖLÇÜLDÜ (21 Ağustos, iki uçak, 10 m, g2).**
  Kayıttan (`mcap`, uçuş penceresi):

  | | bench (yerde) | **UÇUŞTA** | eşik | pay | aşan |
  |---|---|---|---|---|---|
  | HB boşluğu | maks 301 ms | ortanca 101 · p99 201 · **maks 218 ms** | 1000 ms | **4.6×** | **0** |
  | DURUM boşluğu | ölçülmemişti | ortanca 104 · p99 302 · **maks 408 ms** | 5000 ms | **12.3×** | **0** |

  595 kalp atışı / 59,7 sn · 858 DURUM / 119,8 sn. **Uçuştaki boşluklar
  bench'ten DAHA İYİ çıktı** (218 < 301 ms) — motor gürültüsü ve mesafe
  eşiği zorlamadı. İki eşik de olduğu gibi kalıyor.

### 🟠 P0.13 Uçaklar ağdan önce kalkınca ROS yığını sakat kalıyor — İKİ DÜZELTME YAPILDI (20 Ağustos)

P1.5'in gerçek kapsamı belgelenenden geniş: semptom "QGC bağlantısı ölü
kalıyor" diye yazılmıştı, **bütün DDS grafiğini** etkiliyor.

Ölçüm (ylp00, 20 Ağustos 16:00):

```
Pi acilis            15:51      (/proc/uptime = 1523 s)
konteyner + mavros   15:52:41
wlan0 DHCP kirasi    15:56:32   <- 4 DAKIKA SONRA
```

NetworkManager günlüğü: iki kez `no lease`, sonra
`new lease, address=10.205.4.134`. ROS ağ yokken kalktı; her düğüm **eski**
adrese yazmaya çalıştı (`ddsi_udp_conn_write to udp/172.19.167.189:7424
failed`) ve `mavros.log` **442 MB**'a şişti (bekçi tavanı 500 MB).

Üstüne ylp00'da `baslat.sh:211` `gps_saat.py`'yi **arka plana atmadan**
çağırıyor; süreç `--bekle 150`'ye rağmen 25+ dakika takılı kaldı ve
`baslat.sh`'in geri kalanı **hiç çalışmadı** — px4_bridge, esp32_bridge,
agent_fsm yok, yalnız mavros vardı. `docker restart` ikisini de düzeltti
(0 ddsi hatası, 12 düğüm, log 20 KB).

- `[x]` 🔴 **YAPILDI (20 Ağustos 21:00, `1c8f14e`).** `baslat.sh` mavros'tan
  önce ağı bekliyor: `AG_BEKLE_SN=30`, gelmezse **uyarıp devam ediyor** —
  mesh ve uçuş WiFi'ye bağlı değil, beklemede kilitlenmek daha kötü olurdu.
  Konteynerde `ip` komutu **yok** (ölçüldü), `hostname -I` kullanıldı;
  loopback ve docker köprüsü (`172.17.x`) dışarılandı. Mantık gerçek saha
  ağlarına karşı 8/8 doğrulandı (10.x, 172.19.x, 192.168.x, 172.20.x).
- `[x]` 🔴 **YAPILDI (20 Ağustos 21:00, `1c8f14e`).** `gps_saat.py` artık
  `timeout -s INT -k 15 200` ile sarılı; kesilirse uyarı basıp devam ediyor.

  **`-k 15` şart, `-s INT` tek başına YETMİYOR** — düzeltme yazılırken denendi
  ve tam da önlemeye çalıştığı şekilde takıldı: `timeout` sinyali gönderip
  çıkıyor, ama süreç SIGINT'i yutarsa ölmüyor ve boru `tee`'ye açık kaldığı
  için `baslat.sh` **yine** bloke oluyor. Üç vakayla doğrulandı: `-k` yokken
  sonsuz bekleme, `-k` varken 137 ile kesiliyor, normal biten süreç bozulmuyor.
  `timeout` (coreutils 9.4) iki konteynerde de `-k` destekliyor (ölçüldü).

  Dağıtıldı ve doğrulandı: iki uçak da yeniden başlatıldı, `gps_saat` ~2 sn'de
  normal bitti, **11 düğüm** ayakta.
- `[ ]` 🟠 Uçuş öncesi listesine düğüm sayısı denetimi.
  **Sabit sayı yazma** — `SURU_DUGUMLERI` ile değişiyor: 20 Ağustos'ta
  `origin consensus fsm formasyon` ile **11** `ros2 run` süreci var, belgede
  yazan "12" başka bir yapılandırmadan kalmış. Doğrusu ada bakmak:

  ```bash
  docker exec droneN bash -lc 'source /opt/ros/jazzy/setup.bash; \
      ROS_LOCALHOST_ONLY=1 ros2 node list' | grep -v mavros | sort
  ```

  Beklenen (bugünkü yapılandırma): `agent_fsm_node`, `basit_kacinma`,
  `consensus_node`, `esp32_bridge`, `formation_control`, `ic_dis_kopru`,
  `path_planner_node`, `px4_bridge`, `rosbag2_recorder`, `swarm_fsm_node`,
  `swarm_origin_publisher`.

### 🔴 P0.17 ylp00'ın Pi'si UÇUŞTAN SONRA ÖLDÜ ve ÖYLE KALDI — sebep bilinmiyor

**22 Ağustos 02:02, iniş tamamlandıktan ~2 dakika sonra.** ylp00 ağdan ve
mesh'ten düştü. **Operatör gidip baktığında Pi kapalıydı, kırmızı ışık
yanıyordu** ve **elle açmak gerekti.**

> ⚠️ İlk yazımda "kendiliğinden sıfırlandı" demiştim — **yanlıştı.**
> Açılış listesindeki yeni kayda bakıp otomatik yeniden başlama sandım;
> oysa o kaydı **operatörün elle açması** oluşturmuş. Fark kritik:
> sıfırlanan Pi ~40 sn'de geri gelir, **ölen Pi hiç gelmez.**

**Neden P0:** Pi uçuş sırasında ölürse `px4_bridge` durur, OFFBOARD
setpoint akışı kesilir, PX4 failsafe'e düşer — ve **Pi kendiliğinden geri
gelmez.** Uçak iner ama telemetri, kayıt ve sürü katmanı biter. Bugün iniş
sonrası oldu; 30 saniye önce olsaydı uçak havadaydı.

**Ölçülenler — bilinen adayların hepsi elendi.** Ölümden 40 sn önce:

```
02:01:36  v=5.18V  t=47.2°C  thr=0x0  load=1.60  mem=3923MB  disk=40%
02:02:16  <- log ANIDEN kesiliyor, PID 1'den kapatma dizisi YOK
```

| aday | ölçüm | sonuç |
|---|---|---|
| düşük gerilim | `5.18V`, `thr=0x0`, boot boyunca **0** uyarı | ❌ |
| ısınma | 47,2 °C | ❌ |
| bellek (OOM) | 3,9/8 GB, OOM kaydı yok | ❌ |
| disk | %40 | ❌ |
| SD kart | `mmc error` / `I/O error`: **0** | ❌ |
| temiz kapatma | PID 1'den shutdown dizisi **yok** | ❌ |
| çekirdek paniği | `panic`/`Oops`/`BUG`/`lockup`: **0** kayıt | ⚠️ *aşağı bak* |

🔴 **En kritik bulgu — kanıt TOPLANMIYOR:**

```
kernel.panic = 0        -> panik olursa SONSUZA KADAR DURUR (yeniden baslamaz)
pstore bagli ama BOS    -> panik izi HIC kaydedilmiyor
```

`panic=0` tam olarak gözlenen tabloyu üretir: kırmızı ışık yanar, sistem
ölüdür, kendiliğinden dönmez. Ama panik anında journald diske yazamadığı
için **hiçbir iz kalmıyor** — yani "panik yok" diyemeyiz, *"panik olsa da
göremezdik"* diyebiliriz.

**ylp02'de YOK:** ylp00 akşam iki kez öldü (22:56 ve 02:02), ylp02 aynı
saatlerde kesintisiz koştu. İki uçakta da bekçi ayarı aynı.

- `[ ]` 🔴 **`kernel.panic=10`** — panikte sonsuza kadar durmak yerine
  10 sn sonra yeniden başlasın. Havada Pi ölürse en azından **geri gelir**;
  kayıt, telemetri ve tanı sürer. Tek satır, `/etc/sysctl.d/`.
- `[ ]` 🔴 **`ramoops` aç** — `dtoverlay=ramoops` (`.dtbo` uçakta MEVCUT,
  doğrulandı). Bir sonraki ölümde panik izi RAM'de kalır ve açılışta
  `/sys/fs/pstore/` altından okunur. **Şu an hiçbir iz kalmıyor**; bu
  olmadan sebep bulunamaz.
- `[ ]` 🔴 **Uçuş öncesi kontrol:** kalkıştan önce `uptime -s`. Pi son
  10 dakikada açılmışsa **uçma**, sebebi anlaşılana kadar.
- `[ ]` 🟠 **Fiziksel kontrol:** güç kablosu/konnektör, SD kart oturması,
  kart sağlığı (`fsck`). Gerilim yazılımdan temiz görünüyor ama ani bir
  kopma yazılıma yansımaz.
- `[ ]` 🟠 **Desen izle:** her ölümde `journalctl --list-boots` + izleme
  logunun son satırı kaydedilsin. İki veri noktası az; uçuşla mı, saatle
  mi, yükle mi ilişkili — ayırt edilemiyor.


### ✅ P0.15 KAPANDI — kök neden bulundu ve iki uçuşla doğrulandı (22-23 Ağustos)

**Neydi:** 21 Ağustos akşamı ylp00, komşusunu **46,4 saniye** hiç görmedi;
`collision_avoidance` 3 metrede bile tetiklenmedi. Ters yön aynı anda
kusursuzdu (maks boşluk **0,4 sn**).

**🔑 Kök neden: ESP32 ↔ Pi UART kablosunun ESP ucundaki JUMPER konnektörü.**
Marjinal oturuyordu; uçuş titreşiminde kesikli temas yapıp baytları bozuyordu.

```
ylp00 :  19.007 paket  ->  crc_fail = 868   (hepsi ucus sirasinda)
ylp02 :  19.505 paket  ->  crc_fail =   0   (ayni ucus, ayni kod)
yerde :  ~19.000 paket ->  crc_fail =   0   (her iki ucakta)
```

Tek yönlü olmasının sebebi: gevşek pin ESP'nin **TX**'i — uçağın *aldığı*
bozuluyor, *gönderdiği* sağlam. Üç olayda da aynı yön öldü (**ylp02 → ylp00**).

**Doğrulama:** konnektör oturtuldu → tek uçaklı uçuş **0 hata**, iki uçaklı
uçuş **0 hata**, `alim_ok` hiç düşmedi (önce 13,5 → 7,6 düşüyordu).

Mekanizma, on elenen hipotez ve neden yerde hiçbir testin üretmediği:
**`TUZAKLAR.md` §2.19**.

- `[x]` 🔴 Kök neden bulundu, düzeltildi, iki uçuşla doğrulandı
- `[x]` ✅ Bayatlık dedektörü **çalıştı** — 46,8 sn'yi yakalayıp
  `healthy=False` yaptı ve uyardı (20 Ağustos'ta P0.14(b) için eklenmişti).
  Teorik diye eklenen koruma, bir gün sonra gerçek olayı yakaladı.
- `[ ]` 🔴 **Körlükte davranış kararı — HÂLÂ AÇIK.** Kök neden kapandı ama
  mesh her zaman kayıplı; komşu kayıpken "koruma yok" kabul edilebilir mi?
  (a) olduğu gibi bırak, alarm yeter · (b) son bilinen konumu **büyüyen
  belirsizlik yarıçapıyla** engel say · (c) körlük X saniyeyi geçerse konum
  tut / görevi durdur. **Operatör kararı.**

### ✅ P0.16 ÇÖZÜLDÜ — kaçınma körlüğü artık YKİ'ye ulaşıyor (21 Ağustos gecesi)

**Bulgu:** körlük alarmı uçakta çalışıyordu ama **YKİ'ye hiç ulaşmıyordu.**
Uçtan uca izlendi: uçağın kendi `public/events` konusunda VAR, dizüstünde
BOŞ, YKİ websocket `"alerts": []`.

**Kök neden:** mesh protokolünde **`TIP_EVENT` yok** (`packet_parser` 21 tip
taşıyor, olay yok). `esp32_bridge` olayları yalnız yayınlıyor; mesh'e
göndermek için abonelik hiç kurulmamış. Yani uçakta üretilen **hiçbir**
`SystemEvent` YKİ'ye ulaşmıyor — bu körlükten geniş bir boşluktu.

**Çözüm — firmware GEREKMEDİ.** Belirleyici gerçek: **DURUM paketini Pi
oluşturuyor** (`esp32_bridge → durum_paketle`), ESP yalnız bayt taşıyor.
`bayraklar2` uint8'inde 6 boş bit vardı.

```
DURUM2_BAYRAK_KACINMA_KORU = 0x04
```

- Uçak: komşularından birini `komsu_durum_bayat_s` (5 sn) süredir göremiyorsa
  kendi giden DURUM paketinde biti kurar (`_kacinma_koru_var`).
- Baz köprüsü: biti çözüp **`SystemEvent` yayınlar** — ve baz dizüstünde,
  backend'le **aynı ROS grafiğinde**, yani doğrudan `AlertManager`'a ulaşır.
  **Kenar tetikli**: bayrak 1 Hz geliyor, yalnız değişimde olay basılıyor.

**Neden bayrak, neden olay değil:** *"şu an koruyamıyorum"* bir **durum**,
olay değil. Kendiliğinden temizlenir, YKİ sürekli gösterebilir, ve paket
boyutu değişmediği için eski alıcılar biti yok sayar (geriye uyumlu).

**UÇTAN UCA DOĞRULANDI (simülasyon, iki uçak):** ylp02'nin mesh yayını
kesildi → YKİ websocket'inde, frontend'in aldığı hâliyle:

```
[alerts] sev=critical
  "Çarpışma riski: drone1 KOMSUSUNU GOREMIYOR — o komsuya karsi
   carpisma korumasi YOK (mesh tek yonlu olmus olabilir)"
```

`sev=critical` → **KRİTİK etiketi + sesli alarm** (`alert-critical.wav`).
Köprü geri açılınca körlük temizlendi (`kor_komsu=-`).

- `[x]` 🔴 Bayrak biti + uçak tarafı + baz tarafı olay üretimi
- `[x]` 🔴 **Test: 6 yeni** (`test_kacinma_koru_biti.py`) — bit değeri
  sözleşmesi · çakışma yok · kuruluyor/çözülüyor · varsayılan kapalı ·
  **paket boyutu değişmedi** · diğer bayrakları bozmuyor · geriye uyumlu.
  Paket 151/151 geçti.
- `[x]` 🔴 Uçtan uca sahada doğrulandı (yukarıdaki çıktı)
- `[ ]` 🟡 **Kalıcı çözüm ileride: mesh'e `TIP_EVENT`.** Bugünkü bayrak
  yalnız kaçınma körlüğünü taşıyor; `agent_fsm` durum olayları, consensus
  lider değişimi (P1.14'ün tek-yönlü kopma olayı dahil) hâlâ YKİ'ye
  ulaşmıyor. Firmware + 3 ESP flash gerektirir — 👤 **Eyüp** (bkz. P1.15).


### 🟠 P1.16 YKİ uyarılarının KALICI KAYDI YOK — ekranda kayıp gidiyor

**22 Ağustos'ta bulundu.** Operatör *"benim verdiklerin dışında da bildirim
geldi"* dedi ve haklıydı — sayınca **~32 bildirim** çıktı, ben 4 sanıyordum.

```
/tmp/yki_base_bridge.log:
  KOMSUSUNU GOREMIYOR : 11      (11 korluk dongusu)
  tekrar goruyor      : 11
  DURUM paketi bayat  : 21      (ayri kaynak, P0.14b)
```

**İki ayrı kaynak var** ve ikisi de operatöre bildirim gönderiyor:
kaçınma körlüğü (P0.15) ve DURUM bayatlığı (P0.14b).

🔴 **Ama `AlertManager` uyarıları YALNIZ BELLEKTE tutuyor:**

```python
self._events: list[Alert] = []     # diske hicbir sey yazilmiyor
```

Doğrulandı: `alert_manager.py`'de **sıfır** dosya işlemi, `yki_backend.log`
içinde 4,6 MB'da **sıfır** uyarı izi. YKİ yeniden başlayınca hepsi gidiyor.

**Neden önemli:** operatör uçuş sırasında bildirimleri görüyor ama sonradan
*"kaç kez, ne zaman, hangi uçak"* diye bakamıyor. Bugün ancak uçak ve baz
loglarından geriye dönebildim — o da tesadüfen orada oldukları için.

- `[ ]` 🟠 `AlertManager.push_event` uyarıyı `/tmp/yki_uyarilar.log`'a da
  yazsın: zaman damgası, drone_id, severity, code, mesaj. Satır başına bir
  JSON — sonradan sayılabilsin, süzülebilsin.
- `[ ]` 🟡 Uçuş sonu özeti: görev bitince o uçuşta kaç uyarı, hangi tür.
- `[ ]` 🟡 `config.yaml`'da susturulan listesi var (`link_timeout`,
  `low_battery`, `critical_battery`) — **susturulanlar da loga yazılmalı**,
  yalnız ekrana çıkmasın. Şu an tamamen kayboluyorlar.

### 🟠 P1.18 Köprüde ÇERÇEVE-KAYBI sayacı yok — kayıp bayt sessizce yok oluyor

**22 Ağustos'ta bulundu**, P0.15'in kök nedeni aranırken. `esp32_bridge`
seri hattı şöyle sayıyor:

```
alim_ok · crc_fail · gonderim_ok · gonderim_drop ·
rtk_alindi · bilinmeyen_tip · id_uyumsuz
```

Bayt **bozulursa** `crc_fail` artar. Ama **kaybolursa** COBS bir sonraki
`0x00` ayracında yeniden senkron olur ve yarım çerçeve **hiçbir sayaca
yansımadan** yok olur.

**Neden önemli:** iki farklı arıza biçimini ayırt edemiyoruz —

```
alim_ok duser + crc_fail ARTAR      ->  bozuk bayt   (kablo/konnektor)
alim_ok duser + crc_fail ARTMAZ     ->  KAYIP bayt   (?) — bugun goremiyoruz
```

P0.15'te şanslıydık: arıza bozuk-bayt biçimindeydi ve `crc_fail` gösterdi.
Kayıp-bayt biçiminde olsaydı elimizde hiçbir iz olmazdı.

- `[ ]` 🟠 COBS ayrıştırıcısına çerçeve-kaybı/desync sayacı ekle ve
  `mesh_diag`'a koy. ~10 satır. Tuzağın kendisi: `TUZAKLAR.md` §1.21.

### 🟠 P1.15 Mesh RSSI'yi doldur + YKİ arayüzüne komşu sinyal gücü — 👤 **YALNIZ EYÜP**

> 👤 **Bu maddeyi YALNIZ EYÜP yapacak.** Firmware değişikliği ve üç ESP'nin
> yeniden flashlanmasını gerektiriyor; başkası girmesin.

**Neden gerekli:** 21 Ağustos'ta mesh linki tek yönlü öldü (P0.15) ve kök
nedeni **ölçemiyoruz**, çünkü `rssi` alanı boş geliyor:

```
mesh durum=1 rssi=0 link=True komsu=2      <- rssi HEP 0
```

**Durum tespiti (21 Ağustos, kod okundu):**

- `rssi` alanı DURUM paketinde **zaten var** (`mesh_config.h:293`,
  `int8_t`, 16 baytlık sözleşmenin içinde) → **paket boyutu değişmez**,
  `packet_parser.py::_DURUM_FMT` sözleşmesi bozulmaz.
- 🔴 **Ama ESP-NOW alım geri çağrısı RSSI VERMİYOR.**
  `platform = espressif32@6.13.0` → Arduino core 2.x → eski imza:
  `_esp_now_recv_cb(mac_addr, data, len)` (`mesh_config.h:679`).
  RSSI alanı yok.
- Veri **elde edilebilir**: kanal tarama onu promiscuous moddan alıyor —
  `paket->rx_ctrl.rssi` (`mesh_config.h:800`).

**İki yol var, ikisi de flash gerektirir:**

| yol | ne | risk |
|---|---|---|
| A | Promiscuous modu ESP-NOW'la birlikte koştur, paketleri MAC ile eşleştir | orta — iki mod aynı anda, CPU yükü |
| B | Platformu Arduino core 3.x'e yükselt (`esp_now_recv_info_t` → `rx_ctrl->rssi` verir) | **yüksek** — bütün firmware'i etkiler |

- `[ ]` 🟠 Yol seçilecek (A önerilir), `rssi` doldurulacak, **üç ESP de**
  yeniden flashlanacak (ylp00, ylp02, baz — hepsi aynı kaynaktan)
- `[ ]` 🟠 YKİ arayüzü: her uçak için **komşularının RSSI'si** görünsün.
  Değer zaten `AgentStatus.status_text` içinde taşınıyor
  (`esp32_bridge_node.py:1022`), doldurulunca arayüz tarafı küçük iş.
- `[ ]` 🟡 Doldurulduktan sonra P0.15'in kök nedeni ölçülebilir: körlük
  anında RSSI çöküyor mu, yoksa sinyal iyiyken mi paket kayboluyor?

⚠️ **Bu bir TEŞHİS aracı, çözüm değil.** Çarpışma önlemenin körlüğe karşı
dayanıklılığı P0.15'te ayrıca çözülüyor ve o firmware gerektirmiyor.

### 🔴 P0.11 Guided yol `agent_fsm`'i ATLIYOR — sürü yığını hiç etkinleşmiyor

**G2 gözlem uçuşunda ölçüldü (18 Ağustos 21:45).** Uçuşun kendisi kusursuz
geçti ama asıl soruyu cevaplayamadı, ve sebebi yapısal.

**Ölçüm** (`/swarm/internal/droneN/status`, iki uçakta da aynı):

```
state=1 (IDLE)  armed=False   5476 mesaj (ylp00)  3478 (ylp02)
state=1 (IDLE)  armed=True     899 mesaj ( 90 s)   880 ( 88 s)   <- UCUS
```

Uçak arm oldu, 20 m'ye kalktı, 15 m gitti, döndü, indi — `agent_fsm_node`
**hiç IDLE'dan çıkmadı**.

**Zincir:**

```
ELIGIBLE_STATES = { ARMED, TAKEOFF, IN_SWARM, EXECUTING_TASK }   (IDLE YOK)
        v
ajan IDLE'da  ->  hicbir aday yok  ->  consensus HIC secim yapmiyor
        v
lider yok  ->  esp32_bridge'in formasyon kapisi hic acilmiyor
```

Kayıtta karşılığı: `/swarm/*/election/result` **0**,
`/swarm/*/leader/heartbeat` **0** — iki uçakta da, 638 saniyede.

**Neden:** `IDLE → ARMING` geçişi `EVENT_MISSION_STARTED` istiyor
(`agent_fsm_node.py:314`). YKİ'nin guided yolu
(`/api/guided/arm` → mesh → `px4_bridge` → MAVROS) `agent_fsm`'i **hiç
görmüyor**. Yani kanıtlanmış komut yolu ile sürü yığını **FSM katmanında
kopuk**; guided uçuşta consensus'un çalışması imkânsız — bu uçuşu on kez
tekrarlasak sonuç değişmezdi.

**Neden bu kadar önemli:** ADIM 3'te (`formation_node` komutta) formasyon
yayını liderin varlığına bağlı. Lider hiç seçilmezse formasyon mesh'e çıkmaz
ve bu, uçak formasyon düğümünün emrindeyken keşfedilirdi.

- `[x]` 🔴 ~~Ajanı sürü yolundan ARMED'a sür~~ → **YERDE GEÇTİ (19 Ağu
  akşamı, ylp00, pervanesiz, `yer_testi` bayraklı).** `EVENT_MISSION_STARTED`
  yayınlanınca: durum izi `IDLE→ARMING→ARMED`, PX4 OFFBOARD+armlı,
  **consensus lider seçti** (`Lider: 0 -> 1, round=1`) ve — kalp atışı yerde
  de yayınlansın değişikliğinden sonra (`c3068c8`) — **lider kalp atışı İLK
  KEZ ölçüldü: 399 mesaj @ ~10 Hz**, seq düzgün artıyor, `active_agent_count=1`.
  Not: `yer_testi` bayrağı ARMED'da bilerek durduruyor (kalkış komutu
  gitmez, `agent_fsm_node.py:314` — 15 Ağu emniyeti); yer testi çıkışı
  kumandadan kill + `docker restart`.
- `[x]` 🔴 **İKİ UÇAKLI yer testi de GEÇTİ (19 Ağu gece, ikisi de `b33e878`):**
  olay iki uçakta da yerel verildi; ikisi de `IDLE→ARMING→ARMED` yürüdü,
  lider mutabakatı tam — ylp02 logu `Lider: 0 -> 1 (round=1, ben=3)`,
  split-brain yok. **Mesh kalp atışı yolu İLK KEZ ölçüldü:** ylp00 439 hb
  yayınladı, ylp02 mesh'ten **499 hb aldı** (`leader_id=1`).
  `active_agent_count` ylp02 armlanınca **1→2** — mesh AgentStatus ile
  kadro sayımı çalışıyor.
- `[ ]` 🟡 Yan gözlem: ylp02'de `election/result` izleyicisi mesaj
  yakalamadı ama consensus logu lideri benimsediğini gösteriyor — yayının
  zamanlaması/QoS'u sırası gelince netleştirilecek (davranışsal sorun yok,
  iki ajan aynı liderde).
- `[ ]` 🟡 **`tam_kalkis.sh`'te iki kusur bulundu (19 Ağu):** ① consensus'u
  **parametresiz** yeniden başlatıyor → `battery_min_v` varsayılana (14.0)
  dönüyor ve 12.6 V okuyan ajan seçime giremiyor (ilk koşuda seçim bu yüzden
  olmadı; yönetilen consensus ile anında seçildi). ② Kapanış disarm'ı FSM'e
  yenik: FSM ARMED'dayken zorla disarm bile tutmuyor (ölçüldü: `armed:true`
  kaldı) — temizlik kill switch + konteyner restart ister. Betiğe not/düzeltme.
- `[ ]` 🔴 **Sonra G2 tekrar** — artık lider seçimi VE kalp atışı havada
  ölçülebilir. ⚠️ KARAR-02: consensus ilk gerçek hava görevi — uçuştan önce
  operatöre `ultracode` önerilecek.
- `[ ]` 🟡 **İlk G2 kaydından `swarm_fsm`'in ürettiği durumları incele** —
  geçişler gerçek uçuşla uyuşuyor mu. Veri elde: ilk G2'de 3154 / 2559
  `SwarmState` yayınlandı, kayıtlar `~/yelpence-kayitlar/g2_20260818/`.

  **G2 sabahı kontrol listesi (19 Ağu gece hazırlandı, her şey hazır):**
  1. Pervaneleri tak (ikisi de sökük bırakıldı) → hemen ardından
     `titresim_olc.py` (STABILIZED + arm + gaz eşik altı ~5 sn; clipping
     artıyorsa UÇMA — TUZAKLAR §0.1)
  2. `yer_testi` bayraklarını SİL + `docker restart` (ikisinde de VAR)
  3. `./deploy/yki/param_karsilastir.py` (her uçuş öncesi standart)
  3b. 🔴 **KURU TEST + HARİTA** (`CLAUDE.md` §9 madde 5 — atlanamaz):
     ```bash
     python3 src/gcs/gorev_kanit_ucus.py --kuru --harita \
         --senaryo g2 --irtifa 10 --mesafe 30 --dronelar 1,3 --lider 3
     ```
     `SONUÇ: GEÇTİ` şart. `/tmp/yelpence_rota.html` **operatöre gösterilir** —
     mavi noktalar iki uçağın **ineceği** yerler, o alanlar temiz olmalı.
  3c. 🔴 **Bu uçuş hangi TEK soruyu cevaplıyor?** → *"Havada lider seçimi
     kararlı mı, kalp atışı sürüyor mu?"* Cevap için **kalk – asılı dur – in**
     yeterli olabilir; 30 m'lik bacak yalnız **kayma ölçümü de** isteniyorsa
     eklenir. İki soruyu tek uçuşa bindirmek zorunlu değil (`PLAN.md` §5).
  4. İki kumandada "kapat → QGC SARI" kontrolü (RC-kayıp tespiti canlı mı)
  5. Baz anteni taşındıysa `rtk_baz_survey.py` (18 Ağu'dan beri cevapsız soru)
  6. Uçuş mesajına `ultracode` (KARAR-02) — **yapıldı, 20 Ağu 01:00:**
     denetim kaydı `WORKFLOW_BULGULAR.md`'de (42 bulgu). Uçuştan önce oradaki
     açık P0/P1'lere bir göz at.
  7. İki uçakta `ros2 param get /agent_fsm_node kalkis_olayla` → **False**
     olmalı (kalkış otoritesi guided yolda kalsın; 20 Ağu 01:40'ta ikisinde
     de doğrulandı, kod varsayılanı da artık False)
  8. 🟠 **`formation_node`'un origin kapısını DOĞRULA** — origin senkronsuzken
     `/gozlem/…/formation/raw` **susmalı**. Kayıtta aranacak dize:
     `origin senkronlanmadi; setpoint bekletiliyor` (`formation_node.py:887`).
     ⚠️ İlk G2'de bu **ölçülmedi**: düğüm zaten girdisiz olduğu için (P0.10)
     sustu, yani kapının çalıştığı gösterilmedi. `sitl_mode` düzeltmesinin
     (17 Ağu) tek doğrulanmamış ayağı bu.
  9. 🟡 **Uçuş sırasında RAM/CPU ölç** — ilk G2'de atlandı. Paralel
     `drone_bul.sh --durum`, ya da mevcut kayıttan çıkar.
- `[x]` 🟠 ~~Karar gerekiyor: guided yol ile sürü yolu nasıl birleşecek~~ →
  **KARAR VERİLDİ ve UYGULANDI (19 Ağu gece, operatör: uçak-içi köprü).**
  `esp32_bridge` guided ARM'ı işlerken yerel `EVENT_MISSION_STARTED` üretiyor
  (`b469871`) — firmware'e dokunmadan, teslimatı kanıtlanmış guided yolun
  aynısı. `agent_fsm`'e `kalkis_olayla` parametresi eklendi (sahada `false`):
  olay ajanı yalnız **ARMED'a taşır, TAKEOFF'u tetiklemez** — takeoff
  komutunun tek kaynağı guided yolda kalıyor. `mission1` kalkışı
  devraldığında `SURU_KALKIS_OLAYLA=true` yapılacak (baslat.sh'te yorumlu).

  **Uçtan uca DOĞRULANDI (23:00, ylp00, elle olay YOK):** YKİ API
  `POST /api/guided/1/arm` → mesh → köprü **4 olay** üretti (4-kopya
  teslimat) → `IDLE→ARMING→ARMED` (TAKEOFF'a geçmedi ✓) → **lider seçildi**
  → **535 kalp atışı**. Çıkış: kill → FAILSAFE → IDLE (belgeli yol).
  ylp02'de aynı kod dağıtılı (`c6c75b2`); onun köprü doğrulaması G2 günü
  yapılır. **G2 tekrarının önünde yazılım engeli kalmadı.**

---

### ~~🔴 P0.9 ylp02'nin alıcı failsafe'i KILL tetikliyor~~ — ✅ **KAPANDI**

> **19 Ağustos gece kapandı, ölçümle:** kumandada kayıtlı `+100%` bulundu →
> `-100%`'e çevrildi → kumanda kapalıyken **`CH5=1000`** ölçüldü. Üstüne
> ylp02'ye RC-kayıp tespiti kuruldu (Ch3 üst-uç, `RPI_ESITLEME` §5) —
> **kumanda kaybında artık kill değil RTL.** İki uçağın failsafe davranışı
> aynı. **Aşağısı TARİHÇE**, açık bir uçuş engeli değil; içindeki iki 🟡
> madde (CH6 hâlâ 2000 · ylp00'ın failsafe'i tanımlı mı) hâlâ açık.

`TUZAKLAR.md` §0.2'nin cevabı çıktı ve **beklenenin tersi**: sorun ylp00'da
değil, **ylp02'de**. YKİ telemetrisinden ölçüldü, iki kez tekrarlandı:

| | ylp00 (drone1) | ylp02 (drone3) |
|---|---|---|
| kumanda **kapalı** | `kill=False` `healthy=True` | **`kill=True` `healthy=False`** |
| kumanda **açık** | `kill=False` `healthy=True` | `kill=False` `healthy=True` |

`rc_link_ok` iki durumda da `True` — alıcı susmuyor, hafızasındaki failsafe
değerlerini yayınlamaya devam ediyor ve ylp02'de bunlardan biri CH5'i kill'e
atıyor. Diğer bütün sağlık bayrakları (`estimator_ok`, `xy/z_valid`, `imu`,
`mag`, `baro`) temiz; `healthy=False`'un **tek** sebebi kill.

**Neden uçuş engeli:** havada kumanda kapanır ya da pili biterse sonuç RTL
değil **anında motor kesme** olur. `NAV_RCL_ACT=2` bunu kurtarmaz, çünkü
alıcı yayına devam ettiği için PX4 kaybı hiç görmez.

**İkinci etkisi:** `healthy=False` olan ajan `election.py`'de lider adayı
**olamıyor** (`if not rec.healthy: return False`). G2'nin tek sorusu havada
lider seçimi — kumanda bir an kapanırsa ylp02 seçimden düşer.

> 🔴 **YENİDEN AÇILDI (18 Ağustos 18:40).** Düzeltme yapıldı ve doğrulandı,
> ama sonra **ylp02'nin kumandası fabrika ayarlarına döndürüldü** ve alıcıya
> varsayılan failsafe geri yazıldı. Ölçüm:
> ```
> ylp02 (kumanda KAPALI): 1501 1501 964 1499  2000  1000 1000 1000
>                                              ^^^^ CH5 = 2000 = KILL
> ```
> **Uçak bu hâlde bırakıldı.** Uçuştan önce yeniden yapılmalı.
> Sıfırlama sonrası FlySky varsayılan failsafe çerçevesi (bilinsin diye):
> `1501 1501 964 1499 2000 1000 1000 1000` — switch kanallarının varsayılanı
> `+100%`, yani kill. ylp02'nin en baştaki bozukluğunun sebebi de bu olabilir.
>
> ⚠️ **Sıfırlama yalnız failsafe'i bozmadı:** kumandanın model ayarlarının
> tamamı (reverse, End Points, switch atamaları) varsayılana döndü, oysa
> PX4'ün RC kalibrasyonu eskisine göre yapılmıştı. Uçuştan önce **çubuk
> yönleri, ARM (CH8) ve KILL (CH5) switch'leri, gaz uçları** tek tek
> doğrulanmalı — hepsi `rc/in` okunarak, uçuş gerekmeden yapılabilir.

- `[x]` ~~**DÜZELTİLDİ (18 Ağustos 17:30).**~~ Kumandanın `RX Setup → Failsafe`
  ekranında **Ch5 `+100%` yazılıydı** — yani failsafe kapalı değil, **açık ve
  kill değeriyle kayıtlıydı**. `-100%`'e çevrilip kaydedildi.
  Ölçüm (kumanda KAPALI, `/drone_3/mavros/rc/in`):
  ```
  önce : 1488 1496 1017 1500  2001  2000 1000 1000   → CH5 2001 = KILL
  sonra: 1488 1496 1018 1500  1000  2000 1000 1000   → CH5 1000 = kill kapalı
  ```
  Telemetri: `kill=False  rc_link=True  healthy=True`. Uçuş gerekmedi.
- `[ ]` 🟡 **CH6 hâlâ 2000 dönüyor** (aux2 = Görev 2 mod seçimi). Bugün
  zararsız — `mode_manager` kapalı. **Görev 2'ye (ADIM 12) geçmeden önce**
  CH6/CH7/CH8'in failsafe'leri de emniyetli konumda kaydedilmeli.
- `[ ]` 🟡 **ylp00'ın failsafe'i TANIMLI mı, tesadüfen mi emniyetli?**
  Kumanda kapalıyken `CH5=1000` ölçüldü (18 Ağu) — sonuç doğru. Ama bunun
  açıkça `-100%` kayıtlı olmasından mı yoksa "son değeri tut" davranışından mı
  geldiği bilinmiyor. Kumanda menüsünden 2 dakikada bakılır.

---

### P0.4 Navigasyon kayması — ölçülmedi

Tam plan: **`PLAN.md` §9**. Özet:

Sistem teorik olarak doğru yerde (konum + hız ileri-beslemesi → kalıcı
kayma ≈ 0, hızla büyümez). **Ama bunu doğrulayan ölçüm yok.** Elimizdeki
tek sayı 7 m'lik bir bacaktan geldi, yani geçici rejimi ölçüyor.

- `[x]` 🔴 ~~ÖLÇ~~ → **ÖLÇÜLDÜ (20 Ağustos 02:15, 30 m bacak, İKİ uçak,
  3.0 m/s).** Sonuç `PLAN.md` §9'da:
  **kalıcı kayma ≈ 0.10 m · tepe geçici hata ≈ 1.12 m (t+1.8s) ·
  oturma ≈ 3.5 s.** İki uçak birbirini doğruladı (0.06-0.13 m).
  **Eski 0.44 m rakamı geçersizdi** (7 m'lik bacakta geçici rejim ölçülmüş).
  Sonuç: kalıcı kayma pratikte yok → **hız artırmanın önündeki engel kayma
  değil**; sınırlayıcı geçici rejim ve yavaşlama rampası eksiği.
- `[ ]` 🟠 **İkinci hızda tekrarla.** 2 m/s bu 30 m bacakta ölçülebilir;
  **4 m/s için 40 m bacak şart** (28 m oturma + ölçüm penceresi).
- `[x]` 🔴 ~~Doygunluk payı denetimi~~ → `ucus_ayarlari.py` artık
  `tavan ≥ seyir × 1.5` şartını **hata** olarak veriyor
- `[x]` 🟠 ~~İvme ileri-beslemesini aç~~ → **YAZILDI ve A/B ÖLÇÜLDÜ
  (20 Ağustos 03:00).** Aynı uçuşta ylp00 açık / ylp02 kapalı:
  **tepe geçici hata −60 % (1.10 → 0.44 m), varış aşımı −61 %
  (1.18 → 0.46 m), oturma 3.6 → 2.1 s.** ylp02 kendi tabanını birebir
  tekrarladı, yani fark koddan. Ayrıntı `PLAN.md` §9.
  `guided_ivme_ff` **varsayılan 0.0 (kapalı)** — tek uçuşluk kanıtla uçuş
  yolunun varsayılanı değiştirilmez.
- `[x]` 🟠 ~~İkinci doğrulama uçuşu, sonra varsayılan~~ → **operatör
  kararıyla varsayılan 1.0 YAPILDI (20 Ağu 03:45)**, `baslat.sh`'e
  `GUIDED_IVME_FF` env'i eklendi, iki uçakta restart sonrası doğrulandı.
- `[ ]` 🟡 **Bir sonraki uçuşta teyit et:** kayıttan tepe hata ve aşım
  yeniden ölçülsün (0.44 / 0.46 m civarında kalmalı). Bozulursa geri alma
  tek satır: `GUIDED_IVME_FF=0.0`.
- `[ ]` 🟠 **Sürü tarafı Durum 1'e düşmesin** — `formation_node`'un SVT'si
  saf oransal (`v = −0.8 × hata`), yani ileri-besleme YOK. Kalıcı kayma
  `v/0.8`, PX4'ün 0.95'inden bile kötü. Çözüm: `formation_node`'u
  konum kipine al (`position_valid=True`).

---

### 🔴 P0.10 G2 gözlem uçuşu bu hâliyle BOŞ kayıt üretir — kaynak yok

18 Ağustos'ta kod okunarak bulundu, ölçümle doğrulandı.

`formation_node` bir **hesap makinesi**: "merkez şurada, yön şu, formasyon şu"
tarifini alır ve kendi slot hedefini hesaplar. Tarif gelmezse hiçbir şey
yayınlamaz — `formation_node.py:878` → `if msg is None: return`.

**Tarifi üreten tek düğüm `mission1_node` ve o KAPALI** (`gorev1` anahtarı;
`mode_manager` da kapalı). Yani G2'ye bu hâliyle çıkılırsa
`/gozlem/drone_N/formation/raw` **boş kaydedilir** ve uçuşun asıl sorusu
cevapsız kalır.

**Denendi ve ELENDİ — YKİ'den tarif enjekte etmek:** ROS tarafı yazıldı ve
uçtan uca çalıştı (base `form_tx=4`), ama uçak `form_rx=0`. Sebep RX BASE
firmware whitelist'i: 0x11-0x15 **bilerek** dışarıda bırakılmış (KARAR 3) —
formasyonu lider üretir, YKİ aynı tipi yayınlarsa çift kaynak olur. Yazılan
kod **geri alındı**; ayrıntı `GUNLUK.md` 18 Ağustos kaydı.

**Karar (operatör, 18 Ağustos):**

- `[ ]` 🔵 **G2 yine de uçulacak** — 4 sorudan 2'si cevaplanıyor (havada
  lider seçimi kararlılığı, 11 düğümle RAM/CPU). Bedeli sıfır, bugün hazır.
- `[x]` ✅ **`formation_node` yerde GERÇEK komutla ölçüldü (18 Ağu 19:10).**
  Konteyner yeniden başlatılmadı, yeni düğüm açılmadı: uçakta zaten duran
  **`~/yelpence_ws/form_yayinla.sh`** kullanıldı (bir takım arkadaşı yazmış,
  P2.5'teki "listesi kayboldu" denen betiklerden). O betik komutu **uçakta**
  üretiyor — lideri `/swarm/internal/election/result`'a bildirip formasyonu
  `/swarm/internal/formation/target`'a basıyor, köprü loopback ile
  `/swarm/public/formation/target`'a koyuyor. **Firmware whitelist'ine
  takılmıyor** çünkü yer→hava yönü kullanılmıyor.

  Ölçüm (`/gozlem/drone_1/formation/raw`, 383 örnek ≈ 14 Hz):
  ```
  komut : merkez 12.3 / -45.6 / -8.0   heading 137.5   max_speed 3.5
  cikti : x=12.2990  y=-45.6019  z=-8.000   -> merkeze 0.9 mm hata
          vx=0.3749  vy=-3.2972  vz=-1.1125  -> |v| = 3.500 m/s (tam tavan)
          heading_deg=137.5  max_speed_mps=3.5  priority=10
          position_valid: FALSE   velocity_valid: true
  ```
  **Sonuç:** düğüm komutu doğru çözüyor, slot hesabı doğru (V'de ajan 1 tepe),
  rampa hedefe oturuyor, hız oransal düzeltmede tavana dayanıyor. Uçak yerde
  olduğu için 44 m'lik hata doygunluk üretiyor — beklenen davranış.
  ⚠️ `position_valid=false`, yani **saf hız kipi** — ADIM 3'ün açık maddesi
  (`px4_bridge velocity_only`) ilk kez gerçek telemetriyle doğrulandı.
  ⚠️ Gözlem modu olmasaydı yerdeki uçağa 3.5 m/s ile 44 m ötesine gitme komutu
  gidecekti — 15 Ağustos'taki `vz=1.51` olayının aynısı.

- `[!]` 🔴 **`mission1_node` YERDE TEST EDİLEMEZ — 18 Ağustos'ta kod okundu.**
  Bağımlılık zinciri:
  ```
  IDLE --(START)--> PREFLIGHT --(tum ajanlar: seen+healthy+gps+origin+home_set)-->
  SYNCHRONIZED_TAKEOFF --(tum ajanlar IN_SWARM)--> ROTATE_TO_NEXT
                                                   ^ formasyon komutu ANCAK burada
  ```
  `orchestrator.decide()` yalnız `NAVIGATE_TO_QR / ROTATE_TO_NEXT /
  EXECUTE_QR_TASK / RETURN_HOME` durumlarında komut üretiyor; `mission1_node`
  durum 0'da başlıyor ve durumu `mission_fsm` veriyor.
  **Yani tarif üretmesi için uçağın gerçekten kalkmış ve sürüde olması gerek.**
  Ek engeller: `PREFLIGHT` `home_set` istiyor (arm anında set ediliyor;
  ylp00'da şu an `false`) ve tek uçak açıkken `all_agents_seen` sağlanmıyor.
  → **Bu adım en az 2 uçakla ve UÇUŞLA yapılır.** Yerde yapılabilecek tek şey
  G0: düğüm açılıyor mu, RAM/CPU ne.
- `[ ]` 🟠 **Ara çözüm var:** `deploy/rpi/teshis/form_yayinla.sh` formasyon
  tarifini uçakta üretiyor ve `formation_node`'u besliyor (18 Ağu'da ölçüldü).
  G2 gözlem uçuşunda `formation_node`'a girdi vermek için `mission1`
  beklemeden bu kullanılabilir — tarif sabit olur, uçulan yolu takip etmez,
  ama düğümün havada ne ürettiği yine de görülür.

---

### P0.5 Final görevi donanım şartları

Şartname okundu (15 Ağustos). Üç şart yazılımla çözülemez:

- `[x]` ✅ Her İHA için ayrı pilot + kumanda — **var**
- `[ ]` 🟠 **Kamera** takılacak. FOV ≤ 90°. QR 120×120 cm; hangi irtifadan
  okunduğu **ölçülmeli** (Aşama 3'ün ön koşulu, diğer aşamaları engellemez)
- `[ ]` 🟡 **ylp01** — final görevinde **3 İHA şart**, ama entegrasyonu
  engellemiyor. Yalnız Aşama 5'teki üyelik testi üç uçak istiyor

### 🟡 P0.7-kalan · `dagit.sh` dağıtılacak commit'i doğrulamıyor

`dagit.sh` kirli ağacı yalnız **uyarıyor**; `git cat-file` / `git ls-remote`
denetimi betikte **hiç yok**. P0.7'yi doğuran hatanın (uçaklarda `origin`'de
bulunmayan, `+KIRLI` bir kodun aylarca koşması) tek korkuluğu bu olurdu.

- `[ ]` 🟡 Dağıtılacak commit `origin`'de yoksa **ya da** ağaç kirliyse
  betik **sorsun ya da dursun**. İlgili tuzak: `TUZAKLAR.md` §1.14.

### P0.6a Kod okuma bulguları — entegrasyondan önce düzeltilecek

19 düğümün tamamı okundu (15 Ağustos). Tam liste: `PLAN.md` §6.

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
- `[ ]` 🟠 **`px4_bridge velocity_only:=True`** — `formation_node` C modu (saf
  hız) için tasarlanmış, varsayılan `False` → ikisi de konum kontrolü yapıyor
  ve kazançlar toplanıyor (SVT 0.8 + `MPC_XY_P` 0.95). **ADIM 3'ün şartı**,
  `baslat.sh`'te tek satır. Ayrıntı: `PLAN.md` §7 Engel 3.
- `[ ]` 🟠 `task_reallocator.min_active_for_formation:=2` ·
  `mission1.default_spacing_m:=12.0` · `joystick_interpreter` remap
  (bizimki `/drone_N/mavros/...`, düğüm **namespace'siz** dinliyor).
  ⚠️ **Uygulamadan önce KODU OKU** — `consensus.agent_count` için "2 olmalı"
  yazılmıştı ve **yanlıştı**; uygulansaydı ylp02 sürüden tamamen düşerdi. Her
  parametrenin o sayıyı hangi anlamda kullandığı (kimlik aralığı · canlı sayı ·
  çoğunluk eşiği) tek tek doğrulanacak. Bkz. `KARARLAR.md` **KARAR-04**.
- `[ ]` 🟡 **`ARMED → KALKIS(2) → TAKEOFF(4)` eşlemesi — ADIM 3/4 ön koşulu.**
  Yerde armlı uçak komşularına **havada** görünüyor (`AIRBORNE_STATES`).
  Tüketicileri yalnız lider seçimi değil: **kaçınma ve formasyon da** buna
  bakıyor, yani ADIM 3/4 açıldığında doğrudan aktüatör yoluna bağlanır.
  Olgu ve yan etkileri: `TUZAKLAR.md` §4.9.

### ✅ ADIM 4 kodu HAZIR (20 Ağustos) — devreye alma bekliyor

KARAR-01 Seçenek C'nin uygulaması `saha/main`'de: `komsu_adaptoru.py` (129
satır) + testi (198 satır, **10/10**) + `collision_avoidance_node` yeniden
bağlandı + eşikler `ucus_ayarlari.py`'de tek kaynağa.

**Eşikler karara bağlandı:** `hard=4.0` (= `MIN_AYRIM_M`, tam kuvvet tam
sınırda) + `d0=6.0` (formasyonun 8.49 m yaklaşmasına 2.49 m pay).
Gerekçe: `KARARLAR.md` KARAR-01.

- `[ ]` 🟠 **Uçaklara dağıt** — `dagit.sh`. Şu an uçaklarda `d9be7c9` var,
  adaptör **yok**.
- `[ ]` 🟠 `/ws/kacinma` sil + `ca` anahtarını aç (`baslat.sh` ikisini birden
  açmayı zaten reddediyor).
- `[ ]` 🔴 **KARAR-02:** `collision_avoidance` iki uçak arasındaki tek koruma
  katmanı — ilk kez havaya kalkmadan önce operatöre `ultracode` önerilecek.
- `[ ]` 🟠 Test sırası Y → G → K, `KARARLAR.md` KARAR-01 §Test.

### 🟠 ADIM 1 kalanları — consensus yerde geçti, bunlar açık

ADIM 1 (lider seçimi) 15 Ağustos'ta yerde geçti (`PLAN.md` §8 ADIM 1).
Kapanmayanlar:

- `[x]` 🟠 ~~İki uçaklı tam devir teslim testi~~ → **GEÇTİ (20 Ağustos 20:05,
  pervanesiz).** ylp00 disarm → `Lider: 1 -> 3` ikisinde de; ylp02 liderliği
  devraldı ve yayına başladı (HB 41), ylp00 sustu. 15 Ağustos'ta yalnız tek
  taraflı gözlenebilmişti. Ayrıntı: P0.12(a).
  ⚠️ Not: bu test **devir** yolunu doğruluyor; **lider KAYBI** tespiti
  (heartbeat zaman aşımı) hâlâ ölü — P0.14.
- `[x]` 🟡 **Origin'in MESH yolu DENENDİ ve AÇIK (21 Ağustos, yer testi).**
  ylp02'nin kendi yayıncısı öldürüldü → `internal/origin` sustu ama
  `public/origin` **1,265 Hz'de akmaya devam etti** (`valid=true`). Yerel
  kaynak ölüyken bu veri yalnızca mesh'ten gelebilir. Yayıncı geri açıldı,
  `Publisher count: 1` — kopya yok. Ayrıntı: `PLAN.md` §8 ADIM 0.5.

### P0.6 Sürü entegrasyonunun yapısal engelleri

Tam analiz: `PLAN.md` §7.

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

### ✅ P1.14 DÜZELTİLDİ (21 Ağustos) — tek yönlü kopmada kalıcı iki lider

**Kusur:** iki lider oluştuğunda **yalnız büyük-id tarafı** fark edip
çözüyordu. Küçük-id tarafı rakibi tamamen yok sayıyordu — log bile yok:

```python
elif ctx.leader_id == 0 or msg.leader_id < ctx.leader_id:
    self._adopt_leader(...)      # BUYUK id kucuge uyar
                                 # kucuk-id tarafi icin DAL YOKTU
```

İki sonucu vardı: (1) split-brain küçük-id tarafta **görünmez**, uçuş
kaydında hiç iz yok; (2) çözüm rakibin **bizim** kalp atışımızı duymasına
bağlı — yani kurtuluş yolu, kopmuş olan yönün ta kendisi. Asimetrik
linkte kalıcı ve sessiz iki lider.

21 Ağustos uçuşu bunu büyüttü: lider kimliği mesh'e **kalp atışıyla**
taşınıyor (seçim çerçevesi hiç gelmedi), yani yakınsamanın fiilî tek
yolu buydu.

**Düzeltme — tahkim.** Büyük-id bir rakip, kalp atışlarımıza rağmen
`rakip_grace_s` (3.0 sn) boyunca iddiada ısrar ederse "kalp atışım ona
ulaşmıyor" deyip **boyun eğiyoruz.**

> **Küçük-id kuralı neden bozuluyor:** o bizi duymuyor ama biz onu
> **duyuyoruz** — yani çalışan yön O→BİZ. Liderin işi komut *yollamak*;
> yollaması işe yarayan taraf O. Küçük-id'de ısrar iki lideri **kalıcı**
> kılar; boyun eğmek bölünmeyi tek lidere indirir ve seçilen lider,
> komutu fiilen ulaştırabilen taraf olur.

Yanlış tetiklenme payı: normal işleyişte büyük-id taraf **tek** bir kalp
atışı duyar duymaz uyuyor (~100 ms; 21 Ağustos uçuşunda 80 ms ölçüldü).
3 sn ≈ 30 atışın ard arda ulaşmaması — ölçülen en büyük gerçek boşluğun
(218 ms) **13 katı**.

Ardından küçük-id **önalması 10 sn bastırılıyor** (`onalma_bastir_until`),
yoksa `decide_change` bir sonraki tikte liderliği geri alır ve 10 Hz'de
titrerdik. 🔴 **`LEADER_FAULT` dalı bilerek bastırma dışında** — orası da
susturulsaydı boyun eğmenin ardından gelen 10 sn boyunca lider gerçekten
ölse bile kimse devralmazdı.

- `[x]` 🔴 Kod: `consensus_node._on_heartbeat` (rakip tespiti + uyarı),
  `_rakip_tahkim` (karar), `consensus_context.onalma_bastir_until`,
  `election.decide_change` (önalma kapısı). Rakip susarsa izleme
  **kendiliğinden sıfırlanır** ve boyun eğilmez.
- `[x]` 🔴 Görünürlük: tahkim `WARNING` log + `SEVERITY_WARNING` SystemEvent
  basıyor (normal devrin INFO olayından ayrılsın diye) — artık kayıtta iz var.
- `[x]` 🔴 **Test: 12 yeni** (`test_rakip_lider.py`) + **125/125 paket geçti**.
  Kilitlenenler: tek atışta boyun eğilmiyor · grace dolunca eğiliyor · rakip
  susarsa eğilmiyor · büyük-id yolu bozulmadı · takipçiyken tahkim yok ·
  boyun eğdikten sonra liderlik geri alınmıyor (titreme) · **bastırma
  `LEADER_FAULT`'u engellemiyor** · bootstrap engellenmiyor.
- `[x]` 🟠 İki uçağa dağıtıldı ve **yüklü kodda doğrulandı** (`_rakip_tahkim`
  konteyner içinde görünüyor). Etkin olması için konteyner yeniden başlatılır.
- `[ ]` 🟡 **Saha doğrulaması yapılmadı.** Tek yönlü kopma üretmek gerekiyor
  (bir ESP'nin TX'ini kapatmak ya da uçağı gölgeye almak). Üretilebilirse
  yer testi yazılabilir; üretilemezse tahkim yalnız birim testleriyle
  doğrulanmış kalır — **bu bilinerek kabul edildi.**


### 🟠 P1.13 px4_bridge bilinmeyen pili "12.6 V / %100" SAHTESİYLE örtüyor

Pil okuma PX4'te **bilerek kapalı** — operatör kararı, sorunlu okuma;
kalıcı plan harici LiPo ölçer modül → RPi → YKİ. **Tamamı KARAR-03'te**,
buradan yönetilmiyor.

Bu maddenin konusu yalnız şu: `px4_bridge.py:546`, PX4 "bilmiyorum"
(`/mavros/battery` = 65.535 V, %-1) derken `AgentStatus`'a **12.6 V / %100
basıyor** — sim döneminden kalma. Ölçülmüş zararı (21 Ağustos, koşu 2):
consensus varsayılan `battery_min_v=14.0` ile açılınca sahte 12.6 herkesi
**sessizce aday dışı** bıraktı. Ayrıca YKİ/sürü katmanı pili "dolu" sanıyor.

- `[ ]` 🟠 Sahteyi kaldır: bilinmeyen pil "bilinmiyor" olarak aksın
  (KARAR-03 adım 2 zaten kaynağı değiştirecek; sahtenin kaldırılması o
  adımın parçası sayılmalı). Uçuş yolu kodu: ölçerek, ayrı yer testiyle.


### 🟠 P1.11 `mcap` kurtarma aracı depoda YOK — eksikliği hata vermiyor

20 Ağustos'ta `~/yelpence_ws/bin/mcap` **elle** ylp00 ve ylp02'ye kondu.
`dagit.sh` taşımıyor, depoda yok. `kayit_onar.sh` aracı bulamazsa **sessizce**
eski davranışına döner: bozuk son parçayı kurtarmak yerine karantinaya alır
ve o parçadaki veri okunamaz kalır (ölçüldü: **25,8 saniyelik** uçuş verisi).

Karar verilmedi. Seçenekler ve maliyetleri:

| | depo boyutu | risk |
|---|---|---|
| arm64 + amd64 depoya | 17 → ~43 MB | yok |
| yalnız arm64 depoya | 17 → ~29 MB | dizüstünde gerekirse indirilir |
| depoya koyma, elle | 17 MB | **yeni uçakta unutulur, hata vermez** |

- `[ ]` 🟠 Operatörle karara bağla, sonucu `KARARLAR.md`'ye yaz.
- `[ ]` 🟠 ylp01 dönünce kur — `RPI_ESITLEME.md` bölüm 2, adım 2.
  sha256: `be9734ef63ada9d0cc7a3aa41378ab65fd482601e5f5b3b52098d8e6553deabf`

### 🟠 P1.12 Uçuş kayıtları tavanda — eski kayıtlar SÜREKLİ siliniyor

Ölçüldü (ylp00, 20 Ağustos): `~/yelpence_ws/kayit` **4,9 GB**, tavan
**5,0 GB** (`yelpence_kayit_temizlik.sh`, saatlik timer). Tavan aşılınca **en
eski kayıt siliniyor** — ylp00'daki en eski kayıt bu yüzden 15 Ağustos'tan.

Yani **saklanmayan her uçuş kaydı er geç gidiyor** ve bunu haber veren bir
şey yok. Uçuş kanıtı ve G2 gözlem uçuşlarının kayıtları da bu tavanın altında.

- `[ ]` 🟠 Saklanacak uçuşlar belirlensin ve dizüstüne/harici diske alınsın.
  Bir kez yapılacak iş; hangi uçuşların önemli olduğunu operatör bilir.
- `[ ]` 🟡 Tavanı yükseltmek çözüm değil (kart 29 GB, %41 dolu) — asıl soru
  hangi kaydın saklanacağı. Karar verilene kadar silme sürüyor.

### P1.2 Takım erişimi — SSH anahtarları ve Wi-Fi

- `[ ]` 🟠 **`iPhone` SSID'si doğrulanmadı** — eklerken telefon kapalıydı,
  tarayıp teyit edilemedi. iPhone hotspot'ları **cihaz adını** alır
  (Ayarlar → Genel → Hakkında → Ad) ve SSID'ler **büyük/küçük harfe
  duyarlıdır**. Telefon açılınca bir kez bağlan; farklıysa:
  `sudo nmcli connection modify iphone-hotspot wifi.ssid "GERÇEK AD"`
- `[ ]` 🟠 **ylp01 döndüğünde:** iki Wi-Fi ağı + iki SSH anahtarı + **PX4
  parametreleri** (`ucus_ayarlari.py --px4` çıktısı) + `ucus_ayarlari.env` +
  RC-kayıp failsafe kurulumu. **`RPI_ESITLEME.md` baştan sona yürütülür** —
  tek tek hatırlamaya çalışılmaz, belgenin tek işi bu.

#### SSH anahtarları — Berk'inki de kuruldu (18 Ağustos)

Parola girişi **açık** (doğrulandı), kullanıcı adları `yelpence00/01/02`,
parola takım içinde paylaşılıyor (**repoya yazılmadı, yazılmayacak**).
Yani her üye kendi anahtarını **kendisi** kurabilir, Eyüp'ün orada olması
gerekmiyor.

- `[x]` 🟠 Her üye kendi bilgisayarında bir kez:
  ```bash
  ssh-keygen -t ed25519
  ssh-copy-id yelpence00@<ip>    # üç drone için de
  ```
  **Osman → ylp00 ve ylp02 tamam (17 Ağu).**
  **Berk (MacBook) → ylp00 ve ylp02 tamam (18 Ağu)**, parmak izi
  `SHA256:ADq8YfUQqzqkKQC+4FXkBf8AmQbyCPsn5BgpI+FvXi0` (`berk@github`).
  Kalan: **ylp01 dönünce ikisini birden kur** (→ `RPI_ESITLEME.md`), ve
  Osman/Berk dışındaki üyeler kendi anahtarlarını kursun.
- `[ ]` 🟡 Anahtarlar dağıtıldıktan sonra parola girişini kapatmayı düşün
  (ama sahada kilitli kalma riskine karşı acil çıkış olarak bırakmak da savunulabilir)

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

> 💡 **`gcs_url` = `udp://:14555@` bunu kendiliğinden çözebilir:** başlangıçta
> kurulacak bir karşı taraf yok, dolayısıyla `removed stale remote address`
> da olmaz. Doğrulanmadı; o değişiklik operatör kararıyla **uygulanmadı**
> (`TUZAKLAR.md` §7.1). Bir gün uygulanırsa bu maddeyi tekrar sına.

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

- `[x]` 🟠 ~~İlk saha çıkışında doğrula~~ → **17 Ağustos sabahı ölçüldü ve
  kök neden bulundu.** İki uçağın da `gunluk/son/gps_saat.log` dosyasında
  aynı satır vardı:
  `[gps_saat] GPS zamani 25 sn icinde gelmedi. Saat DEGISMEDI.`
  Zincir: Pi açılışı `01:52:36` → konteyner `01:52:49` → mavros + `sleep 15`
  → `gps_saat --bekle 25` pes ediyor `~01:53:30`. GPS'e güç verildikten sonra
  **~54 sn** tanınıyor, Here4 soğuk başlangıçta o sürede kilitlenmiyor.
  Sonuç: ylp00 **7 sa 58 dk**, ylp02 **10 sa 15 dk** geride, aralarında
  **2 sa 17 dk** fark. Sıcak açılışta çalıştığı için aylarca görülmedi
  (önceki açılışın logunda `fark=+0.151 sn`).
  **Düzeltildi:** `baslat.sh` → `--bekle 150`, iki uçağa da dağıtıldı ve
  md5 ile doğrulandı (`RPI_ESITLEME.md` §8). Uzatmanın bedeli yok —
  `gps_saat.py` ilk geçerli örneği alınca hemen çıkıyor.
- `[ ]` 🟠 **Soğuk açılışta doğrula:** uçaklar bir sonraki kez sıfırdan
  açıldığında `gunluk/son/gps_saat.log` "kaydirildi" demeli. 150 sn de
  yetmezse sıradaki seçenek GPS kilidini beklemek (fix alınana kadar).
- `[ ]` 🟡 Not: saat kayması **uçuşu bozmuyor** — `consensus_node` bütün
  tazelik/zaman aşımı hesabını `time.monotonic()` ile ve komşunun *yerel
  alım anına* göre yapıyor (`consensus_context.py:29`). Bozduğu şey çapraz
  uçak kayıt karşılaştırması.
- `[ ]` 🟡 İki uçağın saatini uçuştan önce karşılaştırmayı alışkanlık yap
  (`drone_bul.sh --durum`'a eklenebilir)
- `[ ]` ⚪ Kalıcı donanım çözümü: Pi 5 RTC konnektörüne düğme pil.
  Operatör "pil bağlayamam" dedi (15 Ağu) — GPS yolu bu yüzden seçildi

### 🟠 P1.9 Kumanda kapalıyken PX4 "uçuşa hazır" diyordu — ylp00'da ÇÖZÜLDÜ (19 Ağu), ylp02 BEKLİYOR

FS-iA6B kumanda ölünce **susmuyor**, failsafe çerçevesini basmaya devam
ediyor; PX4 bağlantıyı sağlıklı sanıyordu. 19 Ağustos'ta ylp00'a **Ch3
üst-uç yöntemi** kuruldu (gün içinde önce CH6 işaret kanalı denendi ve iki
yönde çalıştı; kanalı boşaltmak için nihai yöntem CH3 üst ucuna taşındı) ve
**hava testiyle doğrulandı: alçak askıda kumanda kapatıldı → 1-2 sn'de RTL,
motor kesilmedi.** Kurulum, değerler, kalıcı kurallar ve uçak tablosu:
`RPI_ESITLEME.md` §5. Donanım tabanı ve mutlak failsafe kaydı: `TUZAKLAR` §0.5.

**Doğrulama zinciri (19 Ağu, ylp00):** `sys_status.sensors_health`
RC_RECEIVER biti kumanda kapalıyken 0, açıkken 1 · QGC sarı ↔ yeşil ·
*Vehicle Messages*'ta "Manual control lost / regained" çiftleri · hava
testi (RTL). ⚠️ Disarmed'da yazı **"Ready To Fly" kalıyor** — PX4 kayıpta
modu Hold'a düşürüp otonom kiplerle uçuşa-hazır sayıyor. YKİ'nin
`rc_link_ok`/`ready_to_arm` alanları tespiti GÖSTERMİYOR → `TUZAKLAR` §1.16.

**Havadaki zincir (koddan doğrulandı):** `signal_lost` → `rc_update`,
`manual_control_input` yayınını keser (`rc_update.cpp:484`) →
`COM_RC_LOSS_T` (0.5 sn) sonra manuel kontrol kayıp → `NAV_RCL_ACT=2` → RTL.
`COM_RCL_EXCEPT=0` olduğu için **OFFBOARD'da (görevde) da** tetiklenir.

- `[x]` 🟠 ylp00: Ch3 üst-uç kurulumu (`RC_FAILS_THR=2050`,
  `RC_MAP_FAILSAFE=3`) + hava testi — kumanda kapandı, 1-2 sn'de RTL (19 Ağu)
- `[x]` 🟠 ~~ylp02'ye aynısı~~ → **KURULDU ve DOĞRULANDI (19 Ağu gece).**
  Ch3 failsafe 2101, canlı tavan 2000, 2 parametre yazıldı, bit iki yönde
  ölçüldü. P0.9 da aynı oturumda kapandı (CH5 kayıtlı +100 çıktı → -100'e
  kaydedildi → `CH5=1000` ölçüldü). İki uçağın failsafe davranışı artık AYNI.
- `[ ]` 🟠 **Açıklanamayan yanlış-kayıp (bir kez görüldü):** kumanda AÇIKKEN
  RC biti "kayıp"ta takılı kaldı (CH3=1296'da bile), güç çevrimiyle geçti,
  sonraki uçuş normaldi. Şüpheli: `COM_RC_IN_MODE=3` "ilk kaynağı tut"
  kilidi. Tekrar ederse QGC konsolunda `commander check` çıktısı al.
  **Operatör kararı:** `COM_RC_IN_MODE` 3→0 (yalnız RC) yapılsın mı —
  YKİ joystick kullanmıyor, kaynak karmaşasını kökten keser.
- `[x]` 🟠 ~~Pervanesiz arm-reddi testi~~ → **CEVAPLANDI (19 Ağu): PX4
  kumandasız arm'ı KABUL EDİYOR.** QGC'den ölçüldü — kayıpta mod Hold'a
  düşüyor, otonom kipler RC istemediği için arm geçiyor; v1.16.1'de bunu
  yasaklayan parametre YOK (1007 parametrelik döküm tarandı).
- `[ ]` 🟡 **Yazılımsal arm kapısı: yazıldı, operatör kararıyla GERİ ALINDI
  (19 Ağu, commit'lenmedi).** `px4_bridge`'in `arm` dalına SYS_STATUS
  RC_RECEIVER bitine bakan fail-closed kapı + 9 test yazılmıştı;
  dağıtılmadan geri alındı, repoda izi yok. İstenirse yeniden yazılır
  (~1 saat). Bilinen tek PX4-yerlisi alternatif `COM_ARM_AUTH_*`
  (arm yetkilendirme) — mavros'ta cevaplayıcı yazmayı gerektirir.
- `[ ]` 🟠 **Operatör kararı (bir sonraki uçuştan önce):** `COM_RC_LOSS_T`
  0.5 → 2.0 sn (anlık parazit sürüden uçak koparmasın) ve OFFBOARD istisnası
  (`COM_RCL_EXCEPT`) istenip istenmediği — sürü uçuşunda ani RTL,
  formasyonun içinden geçmek demek
- `[ ]` 🟡 Uçuş öncesi listesine iki madde: "kumandayı kapat → QGC SARI
  olmalı" (tespit canlı mı) · "Ch3 üst ucu 100'de mi + kalibrasyon
  yenilendiyse eşik (2050) hâlâ `RC3_MAX`'ın üstünde mi"
- `[ ]` ⚪ **B — SBUS/CRSF alıcıya geç.** Kaybı çerçevede bildirir, bu hilelere
  gerek kalmaz. Kalıcı ve temiz çözüm ama donanım + yeniden RC kalibrasyonu.

18 Ağustos ölçüm tablosu (tarihçe; ylp00 CH6 failsafe artık **2000**):

| kanal | ylp00 canlı | ylp00 failsafe | ylp02 canlı | ylp02 failsafe |
|---|---|---|---|---|
| CH3 gaz | 909 | 1005 | ~1003 | 1017 |
| CH5 kill | 1000 | 1000 | 1000 | **2000** |
| CH6 | 1000 | ~~1000~~ **2000** (19 Ağu) | 1000 | 2000 |

---

### 🟠 P1.8 QR koordinat tablosu YKİ→uçak zinciri KOPUK — firmware gerekiyor

18 Ağustos'ta firmware okunurken çıktı. `mesh_config.h`'te şu satır var:

```c
// 0x0F: packet_parser.py::TIP_QR_COORDS'a rezerve (YKİ->drone QR konumlari).
```

**Rezerve edilmiş ama hiç tanımlanmamış.** Zincirin iki ucu yazılmış, ortası
yazılmamış — o yüzden bugüne kadar kimse fark etmemiş:

| Katman | Durum |
|--------|-------|
| YKİ arayüzü (`QRPositionForm`) | ✅ var |
| backend (`/swarm/internal/mission/qr_coords`) | ✅ yayınlıyor |
| uçak ROS tarafı (`_isle_qr_coords`) | ✅ alıp işliyor |
| **base bridge → UART** | ❌ **gönderim yolu hiç yazılmamış** |
| **RX BASE firmware whitelist** | ❌ **0x0F yok, çerçeve sessizce atılıyor** |

**Neden P1:** kamera takılıp Aşama 3'e (görü) geçildiği gün karşımıza çıkacak
ve o an firmware yüklemek zorunda kalacağız. Şimdiden planlanmalı.

- `[ ]` 🟠 `mesh_config.h`'e `TIP_QR_COORDS 0x0F` tanımı + `qr_koord_veri_t`
- `[ ]` 🟠 RX BASE whitelist'ine 0x0F (YKİ→mesh yönü)
- `[ ]` 🟠 TX DRONE alış tarafına boyut eşlemesi
- `[ ]` 🟠 `esp32_bridge`'e `/swarm/internal/mission/qr_coords` aboneliği +
  `_uart_yaz(TIP_QR_COORDS, ...)` gönderim yolu
- `[ ]` 🟠 İki ESP'ye de yükleme (`firmware/esp32_mesh/YUKLEME_PROSEDURU.md`)

⚠️ Alternatif: QR konumlarını uçağa **dosyayla** vermek (origin gibi).
Firmware'e dokunmaz ama YKİ'den canlı değiştirilemez. Sırası gelince karar.

---

### P1.6 Durumu bilinmeyen üç güvenlik maddesi — `TUZAKLAR.md` §0

Arşiv sadeleştirilirken çıktılar (16 Ağu). Üçü de **hiçbir canlı belgede
yoktu**, o yüzden bugünkü halleri bilinmiyor. Uçuş kanıtı geçildiğine göre
bir kısmı düzelmiş olabilir — ama bunu kimse yazmamış.

- `[?]` 🟠 **ylp00 clipping ölçüm kuralı hâlâ geçerli mi?** 1 Ağu'da uçağı
  deviren zincirin göstergesiydi (`clipping +80`, titreşim z tepe
  33.84 m/s²). Kural şuydu: her uçuştan önce `titresim_olc.py`, clipping
  artıyorsa **UÇMA**. Araç repoda duruyor, kural hiçbir ön kontrol
  listesinde yok. Geçerliyse uçuş öncesi listesine gir (bkz. P3 otomatik
  ön kontrol maddesi)
- `[x]` ✅ **CEVAPLANDI (18 Ağustos) — sorun ylp00'da DEĞİL, ylp02'de.**
  Ölçüm ve yapılacaklar: **P0.9**. ylp00 kumanda kapalıyken temiz çıktı.
  Aşağıdaki eski madde tarihçe olarak duruyor:
- `[?]` 🟠 ~~**ylp00'ın alıcı failsafe'i hâlâ kill mi tetikliyor?**~~ 29 Tem'de
  ölçüldü: kumanda kapalıyken CH5=2000 → kill açık, yani havada RC kaybı
  RTL değil **motor kesme** demekti. Uçuş izninin kapısıydı. Ayar alıcının
  flash'ında — QGC göstermez, parametre karşılaştırması bulamaz
- `[?]` 🟡 **ylp00 hover gazı %66 mı?** İtki payı yok; motor yakan ve
  devrilmeyi kolaylaştıran yapısal sorun olarak yazılmıştı

Cevap "düzeldi" ise `TUZAKLAR.md` §0'dan silinir; "hâlâ açık" ise buraya
somut madde olarak açılır.

---

## 🟡 P2 — ÖNEMLİ

### 🟡 P2.10 rosbag2 önbelleği küçük olabilir — ÖLÇÜLMEDİ

Kayıt düğümü **normal çalışırken** her 30 saniyede bir
`Writing remaining messages from cache to the bag. It may take a while`
basıyor. Bu satır normalde kapanışta çıkar. `--max-cache-size 100000`
(100 KB) küçük geliyor olabilir.

Sonucu bilinmiyor: yazma geride kalıyorsa güç kesildiğinde önbellekteki
veri de gider. **Ölçmeden değiştirme** — önce mesaj hızı ile önbellek
doluluk oranına bak.

- `[ ]` 🟡 Kayıt sırasında gerçek mesaj hızını ölç, önbelleğin dolma
  süresini hesapla, gerekiyorsa `--max-cache-size` büyüt.

### 🟡 P2.11 docker log döndürmesi ylp02'de yok

`run_drone.sh`'e eklendi ama docker log ayarları **oluşturma anında**
sabitleniyor; `docker restart` yetmiyor. ylp00 yeniden oluşturuldu, ylp02
oluşturulmadı (orada bozukluk yoktu, tek kazanç döndürme).

Döndürme olmadan bozuk bir docker logu konteyner yeniden oluşturulana kadar
**kalıcı** olur — bkz. `TUZAKLAR.md` §1.18.

- `[ ]` 🟡 Sırası gelince (bir sonraki doğal yeniden oluşturmada):
  `docker rm -f drone3 && cd ~/yelpence_ws && bash run_drone.sh 3`.
  **Disarm halde**, ROS yığını ~4 dk kapalı kalır.

### 🟡 P2.12 `[SWARM] Stale ajanlar` 5 Hz'de kısıtsız loglanıyor

22 Ağustos'ta tek yönlü körlük benzetimi sırasında ölçüldü: `swarm_fsm_node`
komşu bayatladığı sürece **her tikte** (5 Hz) uyarı basıyor —

```
59 saniyelik korlukte  ->  295 satir  "[SWARM] Stale ajanlar: [3]"
```

Gerçek bir 46 saniyelik kopmada ~230 satır. Bilgi değeri ilk satırdan sonra
sıfır; log bekçisinin tavanını (500 MB) boşuna yiyor ve asıl satırları
gömüyor.

- `[ ]` 🟡 `throttle_duration_sec` ekle (10 sn yeterli) ya da yalnız
  **değişimde** bas — komşu listesi değiştiğinde.

### 🟡 P2.13 Sağlık oranı dalı İKİ UÇAKLA bıçak sırtında

`swarm_fsm_node.py` sağlık kontrolü:

```python
ratio = healthy / ctx.expected_agent_count      # expected = 2
if ratio < ctx.min_healthy_ratio:               # 0.5
    -> SWARM FAILSAFE + EVENT_EMERGENCY_LAND
```

Bir komşu körleşince `healthy = 1` (yalnız kendisi) → `ratio = 1/2 = 0,50` →
`0,50 < 0,50` **false** → ateşlemiyor. **Sıfır payla geçiyor.**

🔴 Kendi `healthy`'si bir tikte düşerse (örn. `estimator_ok` kaybı) oran
`0/2 = 0` olur ve bu dalın **havada olma şartı var** — yani tam uçuşta
ateşler ve tüm sürüye acil iniş yayınlar.

22 Ağustos'ta ölçüldü: gerçek körlükte `active_agent_count` 2 → 1 → 2 gitti,
`EVENT_EMERGENCY_LAND` **yayınlanmadı** (15 Ağustos'taki `agent_id`
düzeltmesi tutuyor). Yani bugün ateşlemiyor — ama payı yok.

- `[ ]` 🟡 İki uçaklı filoda `min_healthy_ratio`'yu gözden geçir, ya da
  eşiği "en az bir sağlıklı komşu" gibi mutlak bir kurala çevir.
  Üç uçakla sorun kalmıyor (2/3 = 0,67).

### P2.6 Pi'lerin interneti bir sabah tamamen kesildi, sebebi bilinmiyor

17 Ağustos sabahı iki Pi'de de veri **hiç akmıyordu**; 11:35'te kendiliğinden
düzeldi. Pi tarafında hiçbir şey değiştirilmedi, yani değişen şey **Pi'nin
dışında** — telefonda ya da operatörde.

**Parmak izi (tekrarlarsa buna bak):** TCP el sıkışması dizüstü kadar hızlı
tamamlanıyor (0.06–0.24 sn, RTT 102 ms) ama **tek bayt veri gelmiyor** —
`bytes_sent:164 bytes_retrans:123 bytes_acked:1 cwnd:1 backoff:2`. TLS,
UDP DNS, UDP NTP hepsi zaman aşımı. `ping` bu ağda hüküm veremez
(`TUZAKLAR.md` §1.2), `ss -tin` ile bak.

**Ölçümle elenenler** (bir daha araştırılmasın): Pi ağ yapılandırması ·
yerel güvenlik duvarı (`iptables`/`nft` kurulu bile değil) · yerel proxy ·
MTU · araya giren sahte cevaplayıcı · TTL tabanlı tethering tespiti ·
MAVLink yayını (trafik %100 tekil ölçüldü).

- `[ ]` 🟡 Tekrarlarsa **kesin deney:** dizüstünü hotspottan düşür, Pi'den
  dene. Çalışırsa sebep "aynı anda kaç cihaz internet alabiliyor" sınırıdır;
  çalışmazsa telefonun cihaz bazlı engellemesine bakılır.
- ℹ️ **Görevi engellemiyor** — `gps_saat.py` zaten "sahada internet
  olmayabilir" diye yazıldı. Etkilediği şey `apt` ve NTP.

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

Tamamı `PLAN.md` §8'de. Uçuşsuz hazırlık:

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

- `[x]` ✅ **Drone'lardaki betikler repoya alındı (18 Ağustos):**
  `deploy/rpi/teshis/` — 21 betik + README (hangisi ARM eder, hangisi sahte veri
  enjekte eder, hangisi güvenli; kategorilere ayrıldı). Parola/anahtar/sabit IP
  taraması yapıldı, temiz. **Liste ylp00'dan geri çekildi** (`COP_TEMIZLIK.md` silinince kaybolmuştu):
  ```
  arm_dene.sh  arm_secim.sh  consensus_baslat.sh  durum_enjekte.sh
  form_izle.sh  form_sayac.sh  form_yayinla.sh  gorev_baslat.sh
  gps_led_teshis.sh  gps_ornek.sh  inc_dogrula.sh  inc_kanit.sh
  offboard_armed.sh  offboard_deney.sh  offboard_once.sh  prearm_teshis.sh
  rtk_param.sh  rtk_zincir.sh  seq_deney.sh  tam_kalkis.sh  tam_zincir.sh
  mesaj_hizlari.py  gps_saat.py  run_drone.sh  Dockerfile
  + baslat.sh.yedek_20260802_184714  baslat.sh.yedek_20260814_212708
  + bozuk_223218  core.50   (ikisi de artık gereksiz, silinebilir)
  ```
  🔴 **`form_yayinla.sh` en değerlisi** — `formation_node`'u uçakta gerçek
  komutla besleyen tek araç; 18 Ağustos'taki ölçüm onunla yapıldı. İçindeki
  QoS tuzağı `TUZAKLAR.md` §2.9'a geçti.
- `[x]` ✅ ~~Uçaktaki kopyalar dağıtım yolunun dışında~~ → **`dagit.sh`'e
  eklendi (18 Ağu):** `deploy/rpi/teshis/*.sh` uçağın `~/yelpence_ws/` köküne
  yazılıyor (alt dizine değil — mevcut kopyaların üzerine geçsin, iki kopya
  olmasın). `--delete` yok, bayrak dosyaları korunuyor.
  ⚠️ **Bu Mac'ten dağıtım yapılamıyor:** `dagit.sh` `declare -A` kullanıyor,
  macOS'un bash 3.2'si desteklemiyor ve **sessizce yanlış uçağa eşliyor**
  (`TUZAKLAR` §9.6). `brew install bash` + `/opt/homebrew/bin/bash` ile
  çalıştırılmalı; değişiklik **henüz uçakta sınanmadı**.
- `[ ]` 🟡 ~~Uçaktaki kopyalar dağıtım yolunun DIŞINDA~~ (eski hâli) `dagit.sh`
  `deploy/rpi/teshis/`'i uçağa yazmıyor; depodaki ve uçaktaki kopyalar
  ayrışabilir. Ya dağıtıma eklenmeli ya da "tek kaynak depo" kuralı yazılmalı.
- `[ ]` 🟡 **ylp00'da `core.50` — 353 MB core dump, silinmeli.** Disk 14
  Ağustos'ta %100 dolmuştu; bu dosya boşuna yer kaplıyor. Yanında
  `bozuk_223218/` (303 KB bozuk mcap) ve iki eski `baslat.sh.yedek_*` var.
- `[ ]` 🟡 **Kalan kırık referanslar.** 16 Ağu'da tarama yapıldı, yalnız
  `COP_TEMIZLIK.md` temizlendi; şunlar duruyor:
  - `INTERFACE_CONTRACT.md` — `maneuver_executor` `formation_control/`
    içinde, `precision_landing` `swarm_missions/` altında gösteriliyor;
    **ikisi de gerçekte başka pakette** (12 atıf). Ayrıca `member_manager`,
    `neighbor_monitor`, `failsafe_handler` depoda **hiç yok** — sözleşmede
    tasarım niyeti olarak duruyorlar, akış şemalarını okuyan yanılıyor
  - `YELPENCE_RTCM_SPEC.md` — §3.1.1 ve §3.4 planlanan modül adlarını
    kullanıyor (`uart_framer.py`, `rtcm_parser.py`, `mavlink_injector.py`);
    hiçbiri o adla yazılmadı. Spec'in kendi kuralı: **kod kazanır**
- `[x]` 🟡 ~~Arşiv belgeleri güncel değil, kimse okumuyor~~ → 16 Ağu'da
  silindi; geçerli içerik `TUZAKLAR.md`'ye çıkarıldı (`docs/`: 17 → 12 md)
- `[x]` 🟡 ~~`README.md` sim kurulumu anlatıyor~~ → giriş noktası olarak yeniden yazıldı
- `[x]` 🟡 ~~`ARCHITECTURE.md` yanıltıcı~~ → başına uyarı kondu

---

### 🟡 P2.9 Konteyner imajının harici yedeği yok

KARAR-05 gereği `docker/rpi/` geri gelmiyor; imaj `docker save` kopyasıyla
korunuyor. Kopya **alındı ve doğrulandı** (`~/yelpence-yedek/`, 378 MB,
config `661296d…`, `gzip -t` sağlam).

Ama o klasör **git'e girmiyor** ve **tek kopya bu dizüstünde**. Dizüstü
giderse imaj yine yalnız iki SD kartta kalır — Dockerfile da olmadığı için
ortam yeniden üretilemez.

- `[ ]` 🟡 Harici bir yere kopyala (USB bellek, bulut, ikinci makine).
  378 MB, tek `rsync`.
- `[ ]` ⚪ İmaja `cv2`+`pyzbar` eklendiğinde (ADIM 5) **yeni yedek al** ve
  ne eklendiğini `RPI_ESITLEME.md`'ye yaz.

### 🟠 P2.7 Denetim kaydının yarısı yalnız Berk'in Mac'inde

`WORKFLOW_BULGULAR.md`'deki **16 bulgunun mekanizma metni kesik**
(`*(tam metin journal.jsonl)*`). O dosya depoda yok:
`~/.claude/projects/-Users-berk-Desktop-yelpence-2026-saha/.../
wf_635b637e-bd2/journal.jsonl`.

O makine giderse 16 bulgunun gerekçesi kaybolur — ve bunlar uçuş öncesi
denetlenmesi gereken iddialar.

- `[ ]` 🟠 **Berk:** `journal.jsonl`'i depoya al ya da kesik metinleri
  `WORKFLOW_BULGULAR.md`'ye tam hâliyle yapıştır.

### 🟡 P2.8 ylp00'ın 1. bacak kalıcı kayması anormal

20 Ağustos A/B ölçümünde (`PLAN.md` §9) fark edildi:

| | bacak 1 | bacak 2 |
|---|---|---|
| ylp00 (FF açık) | **0.254 m** | 0.092 m |
| ylp02 (FF kapalı) | 0.073 m | 0.083 m |

2. bacakta ikisi eşit, 1. bacakta ylp00 **3.5 kat** kötü. Muhtemelen oturma
penceresi seyir ortalamasına karışıyor (ylp00'ın oturması 3.1 s, bacak 11.3 s).
Ama bu sayı Berk'in özetinde yok ve ivme FF'in bir yan etkisi olabilir.

- `[ ]` 🟡 Sonraki uçuşta bacak başına kalıcı kaymayı yeniden çıkar; ylp00'ın
  1. bacağı yine ayrışıyorsa `kayma_coz.py`'nin seyir penceresi denetlensin.

## ⚪ P3 — İLERİDE

- `[ ]` ⚪ Kalkış öncesi **otomatik ön kontrol listesi** — pil, RTK, kill,
  parametre eşitliği tek komutta. Parçaları var (`on_ucus_kontrol.py`,
  `param_karsilastir.py`), birleştirilmedi.
- `[ ]` ⚪ Uçuş kaydı çözümleme aracı (rosbag2 → grafik). Her kazadan sonra
  elle sorgu yazılıyor.
- `[?]` ⚪ `sim/` klasörü ve `scripts/` sim betikleri — sil mi, arşiv dalına mı?
  **Karar operatörün.**
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

---

## ✅ Kapananlar — tam kayıt `GUNLUK.md`'de

Bu maddeler bitti ve **anlatıları `GUNLUK.md`'de duruyor** (tarih tarih).
İçlerinde kalan açık işler yukarıdaki canlı bölümlere taşındı; buradan
silinmeleri onları kapatmıyor.

| Ne | Kapandı | Anlatı |
|---|---|---|
| P0.1 `MAKS_EGIM_DEG` ivmeden türetiliyor | 14 Ağu | `GUNLUK` 14 Ağu · `PLAN` §9 |
| P0.2 / P0.3 PX4 parametreleri eşitlendi | 14 Ağu | `GUNLUK` 14 Ağu · `RPI_ESITLEME` §5 |
| P1.1 iPhone hotspot iki uçağa eklendi | 15 Ağu | `RPI_ESITLEME` §7 |
| P1.3 Repo commit'lendi ve push'landı | 15 Ağu | `GUNLUK` 15 Ağu |
| ADIM 1 — consensus lider seçimi yerde geçti | 15 Ağu | `PLAN` §8 ADIM 1 |
| QoS sınıf hatası — 5 abonelik + YKİ düzeltildi | 15 Ağu | **`TUZAKLAR` §2.10** |
| `baslat.sh` toplu anahtarları ayrıldı (`ca`/`fsm`) | 15 Ağu | `KARARLAR` KARAR-01 |
| Gözlem modu kuruldu (`/ws/gozlem`) | 15 Ağu | `PLAN` §5 |
| P0.7 uçaklar `main`'e alındı | 17 Ağu | `GUNLUK` 17 Ağu · `RPI_ESITLEME` §8 |
| P0.8 `formation_node sitl_mode` düzeltildi | 17 Ağu | `formation_node.py:189` yorumu |
| G2 gözlem uçuşu yapıldı (62 sn) | 18 Ağu | `GUNLUK` 18→19 Ağu |
| P0.9 ylp02 kill failsafe'i düzeltildi | 19 Ağu | `TUZAKLAR` §0.2 · `RPI_ESITLEME` §5 |

> 🔎 **20 Ağustos budaması:** bu 12 bölüm 285 satırdı ve içlerinde
> **10 işaretlenmemiş açık iş** saklıydı. Çok ajanlı bir koruma denetimi
> (12 bağımsız kontrol) her bölümün içeriğinin başka belgede durup durmadığını
> tek tek doğruladı; **8 madde başka hiçbir yerde yoktu** ve silinmeden önce
> taşındı. Başlığa bakıp silmek onları sessizce düşürecekti.
