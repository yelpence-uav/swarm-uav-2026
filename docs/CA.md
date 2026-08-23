# CA — Çarpışma Önleme: durum, karşılaştırma ve açık sorular

**Son güncelleme:** 23 Ağustos 2026, 14:45

> Bu belge 23 Ağustos oturumunda çarpışma önleme (CA) üzerine yapılan
> incelemenin **tamamı**. Yeni bir oturum sohbet geçmişi olmadan buradan
> devam edebilir.
>
> Sayıların hepsi ya **koddan okunarak** ya da **benzetimle ölçülerek**
> çıkarıldı. Varsayım olanlar 🔴 ile işaretli — onlara güvenilmez.

---

## 0. Otuz saniyede

- Sahada **`collision_avoidance`** koşuyor (`basit_kacinma` kapalı, silinmedi).
- Kodu sıfırdan okuyunca **`KARARLAR.md` KARAR-01'de iki hata bulundu** — §2.
- Operatör **dikey yol verme** önerdi (çatışanlardan biri irtifa alsın).
  Gerekçesi güçlü ve 3 m ölçeğinde **benzetimle desteklendi** — §3, §4.
- Aralık **6 m → 3 m** inecek. Bugünkü ayar 3 m'de **8 mesh tohumunun
  3'ünde eşiği ihlal ediyor.** Önerilen ayar 0/8 — §5.
- 🔴 Öneri, uçağın **3 m/s tırmanabildiği** varsayımına dayanıyor ve bu
  **ölçülmedi** — §6. Sıradaki iş bu.

---

## 1. Bugün ne koşuyor

| | |
|---|---|
| Aktif düğüm | `collision_avoidance` (ADIM 4, 21 Ağustos'ta açıldı) |
| Kapalı ama duruyor | `basit_kacinma` — geri dönüş tek dosya değişikliği |
| Uçaktaki eşikler | `d0=10 hard=6` ⚠ **GEÇİCİ test değeri**, üretim 6/4 |
| İvme sınırları | `normal=3.58 acil=5.66 donus=0.50` (22 Ağu'da eğim tavanına bağlandı) |
| Yuva | `/control/setpoint/raw` → CA → `/control/setpoint` — **tek üretici kuralı**, `CLAUDE.md` §4 |

Sahada doğrulanmış tek gerçek tetikleme: 22 Ağustos, operatör ylp02'yi
6,5 m'ye yaklaştırdı, ylp00 **3,88 m kaçtı**.

---

## 2. İki uygulama — koddan karşılaştırma

`KARAR-01`'e bakılmadan, iki düğümün kaynağı baştan okunarak çıkarıldı.

| | `basit_kacinma` | `collision_avoidance` |
|---|---|---|
| Çalışma alanı | **konum** — setpoint'e metre ofset | **hız** — kaçış hızı |
| Girdi kapısı | `position_valid` **şart** (`:302`) | yok |
| Mesafe ölçümü | **yalnız yatay (2B)** | **3B** (`rel_z` dahil) |
| Radyal büyüklük | yalnız mesafe | mesafe **+ yaklaşma hızı** |
| Teğet ölçeği | **yaklaşma hızı** → asılıyken çalışır | **kendi hızımız** → asılıyken **sıfır** |
| Teğet tarafı | sabit −90° | sabit −90° — **aynı** |
| **Dikey kaçış** | **yok** | **yok** |
| İrtifa kapısı | yok | var (3 m altında kapalı) |
| Yetki sınırı | 6 m ofset → `Kp×6 ≈ 2,85 m/s` | `v_max` 4 m/s + ivme sınırı |
| Satır | 386 | 1040 + adaptör |

### 🔴 KARAR-01'de bulunan iki hata

**a) *"Dikey: `basit_kacinma` yok / CA var"* — YANLIŞ, ikisinde de yok.**

```python
# ca_core.compute() son satiri:
return (vx, vy, vfz), True      # vfz = GELEN dikey hiz, DEGISTIRILMEDEN
```

`rel_z` yalnız 3B mesafeyi (`d3`) ve yaklaşma hızını hesaplamakta
kullanılıyor; çıkışa **hiç** dikey bileşen konmuyor. Kaçış yönü
`ux, uy = away_x/d_xy, away_y/d_xy` ile **saf yatay**.

**b) *"Teğet: ikisinde de var"* — eksik.** CA'nınki asılıyken **çalışmıyor**:

```python
vf_h = math.sqrt(vfx*vfx + vfy*vfy)
if vf_h < 1e-3 or mag_rep < 1e-9:
    return 0.0, 0.0              # ASILIYKEN TEGET SIFIR
```

`basit_kacinma`'nın docstring'i bunu bilerek yazmış:
> *"repodaki `ca_core._tangent` teğeti KENDİ hızımıza bağlıyor ve biz asılı
> duruyorsak teğeti hiç açmıyor. Oysa asılı dururken üstümüze gelen bir
> uçak, teğete en çok ihtiyaç duyduğumuz durum."*

### Sonuç: yine de CA

Görev senaryolarına göre (dördü CA, biri karşı taraf):

| görev gereği | hangisi | neden |
|---|---|---|
| Formasyonu koruyarak ilerleme | **CA** | `formation_node` `position_valid=False` gönderiyor (`:999`) → `basit_kacinma` **fiilen ölü** |
| **İrtifa değişimi** (QR görevi) | **CA** | 2B ölçen `basit_kacinma`, 10 m dikey ayrık iki uçağa **tam itme** uygular |
| Sürüden ayrılma / katılma | **CA** | aynı dikey istifleme sorunu |
| Hassas iniş | **CA** | 3 m altı irtifa kapısı yalnız onda |
| **Bekleme / asılı durma** | 🔴 `basit_kacinma` | CA'nın teğeti asılıyken sıfır |

**Kapatılması gereken tek gerçek boşluk (~5 satır):** CA'nın teğet ağırlığı
kendi hızımıza değil **yaklaşma hızına** bağlanmalı — `basit_kacinma`'nın
zaten yaptığı şey.

---

## 3. Dikey yol verme önerisi (operatör)

> *"Yol veren İHA irtifasını artırarak yol verse."*

**Lehine dört argüman:**

1. **Yatay düzlem görev geometrisinin kendisi** — formasyon slotları, rota,
   QR konumları. Yatay yol vermek formasyonu bozar; dikey eksen boş.
2. **Taraf anlaşmazlığı yok.** Yatay "sağa geç" kuralı n=3'te **döngüsel**
   (A→B→C→A). Dikeyde **kimlik sıralaması** var, döngü matematiksel olarak
   imkânsız: rütbe r → ofset `r × KATMAN`.
3. **Asılıyken çalışır** — kendi hızımızı hiç kullanmaz, §2b'deki boşluğu
   kapatır.
4. **Ölçek küçüldükçe güçlenir.** 3 m aralıkta yatayda kaçacak yer yok
   (komşular her yönde), dikey eksen hâlâ boş.

Emsal: **TCAS** ticari havacılıkta çarpışmayı dikey çözer — aynı gerekçeyle.

**Doğrulanan bir endişe daha (koddan):** dikey manevra CA'nın yaklaşma hızı
ölçüsünde sahte "yaklaşma" üretmiyor —
`c = -(rel_x*rel_vx + rel_y*rel_vy + rel_z*rel_vz)/d3`; tırmanan komşuda
çarpım pozitif, baştaki eksi ile `c` düşüyor → doğru şekilde *uzaklaşıyor*.

### Rotor akışı — eleme sebebi değil

Pervane **8045 (8" = 0,203 m)**, 4S.

| mesafe | çap cinsinden | etki |
|---|---|---|
| ~1 m | 5 çap | güçlü iz burada biter |
| ~2 m | 10 çap | büyük ölçüde dağılmış |
| 4 m | ~20 çap | ihmal edilebilir |

21 Ağustos gözlemi uyuyor: **2 m dikey + 3 m yatay** ayrıkta sorun görülmedi.
🔴 Bu sayılar **bizim uçağımızdan ölçülmedi**, genel multikopter pratiğinden.

**Asıl kısıt downwash değil, itki payı:** `TUZAKLAR` §0.3 → askı gazı %66,
itki payı yok. Dikey yol verme tırmanma yetkisi ister; yatay kaçış mevcut
itkiyi yönlendirir.

---

## 4. Benzetim — ne yapıldı, ne çıktı

Araç: **`src/gcs/ca_benzetim.py`** (gerçek `ca_core` koşturulur, taklit değil).

```bash
python3 src/gcs/ca_benzetim.py            # yatay vs dikey
python3 src/gcs/ca_benzetim.py --tarama   # hangi kol ne kazandiriyor
python3 src/gcs/ca_benzetim.py --tohum    # tohum duyarliligi — ATLAMA
```

### 4.1 — 6 m ölçeğinde: dikey **seçtirmedi**

Üç uçak, `d0=6 hard=4`, kusursuz mesh. **Öngörülen n=3 kilidi oluşmadı** —
her iki kipte de üçü de hedefine vardı. Dikeyin ayrım kazancı küçüktü
(+0,09…+0,42 m) ve **6,8–8,0 m irtifa** bedeli vardı.

Beklenmedik bulgu: üç senaryonun ikisinde **iki kip de 4 m eşiğini ihlal
etti** (3,57–3,99 m) — yani sorun yol verme biçiminden bağımsız olabilir.

### 4.2 — 3 m ölçeğinde: dikey **kazanıyor**

`d0=3 hard=2 r_min=1`, kabul eşiği 🔴 **1,5 m (varsayım)**, mesh 7 Hz / %30 kayıp:

```
 seyir   kip      en_kucuk   irtifa
 1,0m/s  YATAY      2,35m      0,0m
 1,0m/s  DIKEY      2,38m      4,0m
 2,0m/s  YATAY      1,87m      0,0m
 2,0m/s  DIKEY      2,19m      4,0m
 3,0m/s  YATAY      1,36m ⚠    0,0m
 3,0m/s  DIKEY      1,54m      4,0m
```

Üstünlük **hızla büyüyor** ve 3 m/s'te **geçti/kaldı farkına** dönüşüyor.

### 4.3 — Hangi kol ne kazandırıyor (taban 1,54 m)

```
d0  3,0 -> 4,0 m              +0,75   <- en buyuk AMA 3 m araligi asar
seyir 3 -> 2 m/s              +0,65   <- gorev kisiti
dikey hiz 2 -> 4 m/s          +0,34
dikey hiz 2 -> 3 m/s          +0,25   <- 3'te DOYUYOR, 4 bos itki
hard 2,0 -> 2,5 m             +0,23
egim tavani 3,58 -> 5,66      +0,19
mesh 7 -> 14 Hz               +0,07   <- neredeyse etkisiz
mesh kayip %30 -> %5          +0,04   <- neredeyse etkisiz
kacis tavani 4 -> 6 m/s       +0,00   <- HIC
yavas-yaklasma kapisi ac      +0,00
katman 2 -> 3 m               -0,02   <- 6 m irtifa yer, KAZANC YOK
yatay teget de acik           -0,12 ⚠ <- IKISI BIRLIKTE KOTULESTIRIYOR
```

**Beş çıkarım:**

1. **Kaçış hız tavanı bağlayıcı değil** (+0,00) → sorun hız değil **ivme**.
2. **Dikey ivme eğim gerektirmiyor**, yatay gerektiriyor — asıl fark burada.
3. **Mesh iyileştirmesi işe yaramıyor.** "3 m'de tazelik baskın olur"
   tahmini **iki kez çürüdü**. Sorun bilgi değil **manevra**.
4. **Katman yüksekliği yanlış kol** — önemli olan ne kadar yükseldiğin değil
   **ne kadar hızlı kaçtığın**.
5. 🔴 **Yatay + dikey birlikte KÖTÜ.** Dikeye geçilirse `k_tan` **0** olmalı.

### 4.4 — Tohum taraması (atlanmaz)

```
yapilandirma                ortanca  en_kotu  en_iyi   ihlal
TABAN (bugunku)              1,55m   1,45m   1,63m   3/8  ⚠
ONERI (dikey3 + hard2,5)     1,87m   1,80m   1,95m   0/8
ONERI + egim 5,66            2,01m   1,86m   2,10m   0/8
ONERI, seyir 2 m/s           2,44m   2,36m   2,48m   0/8
```

🔴 **Tek tohum yanıltır.** Bugünkü ayar tek tohumda "1,54 m, sınırda geçti"
görünüyordu; 8 tohumda **3'ünde ihlal**. Mesh kaybı rastgele — bu tarama
her parametre kararında tekrarlanmalı.

---

## 5. Öneri

**`v_dikey = 3.0` + `hard = 2.5`** → 8/8 geçiyor, en kötü durumda **0,30 m pay**.

| kol | karar | neden |
|---|---|---|
| dikey hız 2 → **3 m/s** | ✅ | 4 m/s hiçbir şey katmıyor, boşuna itki |
| `hard` 2,0 → **2,5 m** | ✅ | saf parametre, bedava |
| eğim 3,58 → 5,66 | ❌ | en kötü durumda yalnız +0,06; 22 Ağustos'ta tam bunu düşürdük (34° sorunu) |
| `k_tan` | **0** | yatay teğet dikeyle birlikte kötüleştiriyor |

**Uygulama biçimi:** dikey bileşen `ca_core`'a **parametreyle açılıp
kapanabilir** eklenmeli (`k_dikey = 0` → bugünkü davranış aynen). Böylece
yerde G0/G1 ile aynı uçakta karşılaştırılabilir ve geri dönüş tek parametre.

---

## 6. 🔴 Doğrulanmamış varsayım — sıradaki iş

**Her şey uçağın 3 m/s tırmanabildiği varsayımına dayanıyor.**

Bugün bilinen tek şey `guided_hiz_dikey_mps = 1.0`. `TUZAKLAR` §0.3 askı
gazını %66 ve itki payını "yok" diyor (durumu **bilinmiyor** rafında).

**Ölçüm:** kısa uçuş — kalk, 3 m/s komutla tırman, kayıttan gerçekleşen
dikey hızı ve gaz yüzdesini çıkar. Çıkmıyorsa öneri 1,87 m'nin altına düşer
ve baştan konuşulur.

---

## 7. Açık sorular

| # | soru | kim |
|---|---|---|
| 1 | 🔴 Uçak 3 m/s tırmanabiliyor mu? | ölçüm, kısa uçuş |
| 2 | 3 m aralıkta kabul eşiği **gerçekten** 1,5 m mi? Benzetimde varsayım | operatör |
| 3 | 3 m aralıkta katman merdiveni **sürekli açık** kalıyor (tetik 6 m > aralık 3 m). Formasyon kalıcı merdivene dönüşür — kabul mü, tetik mi daraltılmalı? | operatör |
| 4 | CA'nın teğet körlüğü (asılıyken sıfır) kapatılacak mı? ~5 satır | karar |
| 5 | `xy_guard = 0.3` kör noktası — tepeden yaklaşan komşu **tamamen atlanıyor**. Dikey yol verme uçakları oraya sürer | 🔴 dikeyden ÖNCE |
| 6 | `ca_core.py` sınıf varsayılanı hâlâ `slew_emergency = 30.0` (**71,9° eğim**). Sahada güvenli çünkü `baslat.sh` eziyor; düğüm tek başına koşarsa imkânsız değer devreye girer | düzeltilmeli |
| 7 | `d0=10 hard=6` geçici test değeri — formasyon öncesi 6/4'e dönülecek | `RPI_ESITLEME` K2 |

---

## 8. Bilinen algoritma zayıflıkları

KARAR-01'in 21 Ağustos incelemesinden, bugün koddan doğrulananlar:

| | ne | durum |
|---|---|---|
| B1 | Asılıyken teğet **sıfır** | 🔴 açık — §2b |
| B2 | `xy_guard=0.3` altı komşu **tamamen atlanıyor**, tepeden koruma yok | 🔴 açık |
| B3 | Uzaklaşan komşuya çekim (sönümleme tabanı) | ✅ 22 Ağu'da düzeltildi |
| B4 | Yavaş yaklaşmada koruma `d0`'da değil `hard`'da başlıyor | açık — ama 3 m/s'te etkisi **+0,00** ölçüldü |
| B5 | `hard` eşiğinde süreksizlik | ✅ 22 Ağu'da düzeltildi |

Kaçış tavanı 4 m/s: benzetimde 5 m/s yaklaşmada en yakın mesafe 2,00 m'ye
düşüyordu (KARAR-01) — daha hızlıya yetişemiyor.

---

## 9. Nerede ne var

| | |
|---|---|
| Aktif düğüm | `src/swarm_core/swarm_core/collision_avoidance/` |
| Çekirdek algoritma | `ca_core.py` (282 satır) |
| Komşu adaptörü | `komsu_adaptoru.py` — ham `AgentStatus`'tan besler |
| Yedek düğüm | `src/swarm_control/swarm_control/kacinma/basit_kacinma_node.py` |
| **Benzetim** | **`src/gcs/ca_benzetim.py`** |
| Parametre kaynağı | `src/gcs/ucus_ayarlari.py` → `baslat.sh --kabuk` |
| Karar geçmişi | `docs/KARARLAR.md` KARAR-01 (⚠ iki hatası §2'de düzeltildi) |
| Saha tuzakları | `docs/TUZAKLAR.md` §2.15, §2.16, §2.18 |
| Devreye alma | `docs/PLAN.md` §8 ADIM 4 |
