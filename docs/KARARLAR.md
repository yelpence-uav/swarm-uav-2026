# KARARLAR — verilmiş ama henüz uygulanmamış kararlar

**Son güncelleme:** 25 Ağustos 2026, 17:30 — KARAR-04 UYGULANDI (kadro 1 2 3, rütbeler ölçüldü)

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

# KARAR-01 — Çarpışma önleme: Seçenek C

> ### ⚠️ 23 AĞUSTOS DÜZELTMESİ — aşağıdaki tabloda İKİ HATA vardı
>
> Kod sıfırdan okununca çıktı:
>
> 1. *"Dikey: `basit_kacinma` yok / `collision_avoidance` var"* — **YANLIŞ,
>    ikisinde de yoktu.** `ca_core.compute()` gelen `vfz`'yi değiştirmeden
>    geri veriyordu; `rel_z` yalnız 3B mesafe hesabında kullanılıyordu.
>    Dikey kaçış **23 Ağustos'ta yazıldı** (KARAR-06).
> 2. *"Teğet: ikisinde de var"* — **eksik.** CA'nınki kendi hızımıza bağlı
>    olduğu için asılıyken çalışmıyordu. Artık konu dışı: `k_tan = 0`.
>
> Seçim (Seçenek C) yine de doğruydu ve yürürlükte. Eşikler KARAR-06 ile
> değişti: `d0 6.0 → 4.0`, `hard 4.0 → 2.5` (anlamı da değişti).

**Durum:** 🟢 **KOD HAZIR** — adaptör yazıldı ve test edildi (20 Ağustos 2026)
**Ne zaman:** `PLAN.md` §4 **Aşama 1B** — `basit_kacinma` kapatılarak
**Karar veren:** Operatör (15 Ağustos 2026; eşikler 20 Ağustos'ta revize edildi)

## Karar

**`collision_avoidance` kullanılacak, ham `AgentStatus`'tan beslenerek.**
`kinematic_fusion` devreye alınmayacak.

## Neden

Repoda aynı işi yapan iki kod var ve **ikisi de aynı topic yuvasını**
kullanıyor (`/control/setpoint/raw` → `/control/setpoint`), yani aynı anda
koşamazlar. Birini seçmek zorunlu.

| | `basit_kacinma` (sahada) | `collision_avoidance` (sürü) |
|---|---|---|
| **Radyal itme** | yalnız **mesafeye** göre | mesafe **+ yaklaşma hızı** |
| Teğet ("sağa geç") | var | var |
| Dikey | yok | var |
| Komşu kaynağı | ham `AgentStatus` | `NeighborInfo` ← `kinematic_fusion` |

**Belirleyici fark:** `collision_avoidance` radyal itmede **yaklaşma hızını**
hesaba katıyor. 5 m arayla *duran* iki uçak ile 5 m arayla saniyede 6 m
*kapanan* iki uçak — `basit_kacinma` ikisine aynı tepkiyi verir,
`collision_avoidance` ikincisinde çok daha erken iter.

**`kinematic_fusion` neden atlanıyor:** EMA yumuşatması
(`alpha_pos=0.3`) ~2.33 örnek gecikme ekliyor; mesh ~5-7 Hz'de bu **0.35-0.47 s**
demek. 3 m/s'te komşunun **1.2 m önceki** yerine bakmak. Kaçınmada ödenecek
bir bedel değil.

**Atlanabilir olmasının sebebi:** `AgentStatus` mesajında `vel_x/vel_y/vel_z`
**zaten var** — `NeighborInfo`'nun taşıdığı bilgi ham veride mevcut. Fusion'ın
tek kattığı yumuşatma, o da gecikme.

### 🔴 15 Ağustos 21:30 — ölçüldü: bu bir tercih değil, ÖN KOŞUL

Yukarıdaki tablo seçimi *"`basit_kacinma` daha zayıf"* diye çerçeveliyor.
Ölçüm bundan sert: **sürü zincirinde `basit_kacinma` hiçbir şey yapmıyor.**

| Ölçüm | Yer |
|-------|-----|
| `basit_kacinma` gövdesi `if self._kendi is not None and msg.position_valid:` ile başlıyor | `basit_kacinma_node.py:302` |
| `formation_node` `position_valid=False` gönderiyor (tasarım: "C MODU: SAF HIZ-TABANLI") | `formation_node.py:928` |
| `collision_avoidance` girdiyi `if raw.velocity_valid` ile alıyor | `collision_avoidance_node.py:285` |

Yani kapı hiç açılmıyor: düğüm `cik = msg` ile mesajı aynen geçiriyor.
İki uçakla formasyona `basit_kacinma` ile çıkılırsa **koruma katmanı sıfırdır**
ve log yine "basit_kacinma basladi" yazar — yanıltıcı olan tam bu.

İkisi rakip değil, **farklı zincirlere göre yazılmışlar**: `basit_kacinma`
pozisyon-goto yoluna (kanıtlanmış zincir), `collision_avoidance` hız yoluna
(sürü zinciri). Sürü zinciri açılırken adaptör + geçiş **isteğe bağlı değil**.

**Tek uçakta fark yok** — komşu yokken ikisi de geçirgen (`taze` boş → itme 0;
`obstacles` boş → risk yok → `_relay`). Bu yüzden tek drone testleri
`basit_kacinma` ile yapılabilir; sınır **iki uçak havalanınca** başlıyor.

## Nasıl uygulanacak

1. ✅ **Adaptör YAZILDI** (15 Ağustos, `saha`'ya alındı 20 Ağustos) —
   `swarm_core/collision_avoidance/komsu_adaptoru.py`.
   `collision_avoidance_node`'un komşu aboneliği artık
   `/swarm/public/drone{N}/status` (BEST_EFFORT, mesh kaynağı).
   `neighbor_stale_ms` parametresi kaldırıldı (`AgentStatus`ta `data_age_ms`
   yok; tazelik ölçüsü tek: mesajın bize **ulaştığı** an).
2. ✅ **YAPILDI (21 Ağustos, yerde).** `basit_kacinma` kapatıldı,
   `collision_avoidance` açıldı. İki uçakta da:

   ```
   CARPISMA KACINMASI ACIK (collision_avoidance) — cikis /raw'a yonlendirildi
   collision_avoidance basladi (d0=6.0 hard=4.0, basit_kacinma KAPALI)
   11 dugum · basit_kacinma=0 · collision_avoidance=1
   raw tek uretici · setpoint tek uretici · velocity_only=False · armed=false
   tani: skip_adaptor=- komsu_veri=1/2 ben=var
   ```

   **Tek değişken:** `/ws/gozlem` bilerek **duruyor** — formasyon hâlâ uçağı
   sürmüyor, `velocity_only` hâlâ `false`. Değişen tek şey kaçınma düğümü.
   Aynı uçuşta iki değişiklik denenmez (`CLAUDE.md` §9).

   **Geri alma tek komut** — dosyalar silinmedi, kenara alındı:
   `mv ~/yelpence_ws/kacinma.adim4_oncesi ~/yelpence_ws/kacinma` +
   `cp ~/yelpence_ws/suru_dugumleri.adim4_oncesi ~/yelpence_ws/suru_dugumleri`
   + `docker restart droneN`.

   ⏳ **Uçuşta doğrulanmadı.** Sıradaki: KARAR-02 denetimi → kuru test +
   harita → tek uçak kısa git-gel. Tek soru: *`collision_avoidance` guided
   yolda `basit_kacinma` gibi şeffaf mı?*

   > ### 🔴 21 Ağustos — ADIM 4 TEK BAŞINA AÇILAMAZ (ölçüldü)
   >
   > `/ws/kacinma` yalnız *hangi düğümün koştuğunu* değil, **esp32_bridge'in
   > çıkışının nereye gittiğini** de belirliyor (`baslat.sh:471-479`):
   >
   > ```
   > BUGUN  : esp32_bridge -> /raw -> basit_kacinma -> /setpoint   (kacinma CALISIR)
   > SILINCE: esp32_bridge ---------DOGRUDAN--------> /setpoint    (kacinma YOK)
   >          collision_avoidance /raw'i dinler, oraya kimse yazmaz -> ATIL
   > ```
   >
   > ### ⚠️ Bu kutunun ikinci yarısı YANLIŞTI — düzeltildi (21 Ağustos, aynı gün)
   >
   > İlk yazımda *"`collision_avoidance` girdiyi `velocity_valid` ile alıyor,
   > guided setpoint'lerde kapısı hiç açılmaz"* demiştim ve bu kararın
   > yukarıdaki **"`collision_avoidance_node.py:285`"** atfına dayanıyordu.
   > **O satır artık öyle değil** — adaptör commit'i (`076fc21`) dosyayı
   > yeniden yapılandırdı. Bugün ölçüldü: `velocity_valid` dosyada **yalnız
   > iki yerde** geçiyor ve **hiçbiri kapı değil**:
   >
   > ```python
   > 309:  base = (vx,vy,vz) if raw.velocity_valid else (0.0, 0.0, 0.0)
   > 327:  out.velocity_valid = True        # cikis alani
   > ```
   >
   > Yani `collision_avoidance` konum setpoint'ini **işlemeye devam ediyor**:
   > taban hızı 0 alıp riski hesaplıyor, risk yoksa `_relay` ile aynen
   > geçiriyor, **risk varsa hız kaçışıyla eziyor.** Kapı yok.
   >
   > | | girdi kapısı | guided (konum) | sürü (hız) |
   > |---|---|---|---|
   > | `basit_kacinma` | `position_valid` (`:302`) | ✅ çalışır | ❌ ölü |
   > | `collision_avoidance` | **yok** | ✅ çalışır | ✅ çalışır |
   >
   > **`collision_avoidance` üst küme.** Doğru sonuç şu: ADIM 4 tek başına
   > açılabilir ve guided yol için bir **yükseltmedir** (mesafeye ek olarak
   > yaklaşma hızı + dikey bileşen).
   >
   > Tek gerçek engel yönlendirmeydi ve **21 Ağustos'ta giderildi**:
   > `baslat.sh` artık yönlendirmeyi düğüm seçiminden ayırıyor, `ca` açıkken
   > de esp32_bridge çıkışı `/raw`'a gidiyor. Üstüne boş yuva kapısı eklendi.
   >
   > ⚠️ Birlikte açılınca da bir çakışma kalıyor: `/ws/kacinma` silinince
   > esp32_bridge **doğrudan** `/control/setpoint`'e yazar, `collision_avoidance`
   > da oraya yazar (`collision_avoidance_node.py:173`) → **iki üretici**,
   > `CLAUDE.md` §4 ihlali. `baslat.sh`'te "esp32_bridge → collision_avoidance"
   > veren bir yapılandırma yok; yönlendirme anahtarı düğüm seçimine bağlı.
   > **Çözüm:** yönlendirmeyi düğüm seçiminden ayır — esp32_bridge *herhangi
   > bir* kaçınma düğümü açıksa `/raw`'a yazsın. ~5 satır, yerde doğrulanır.
   > Pratikte bugün ısırmıyor çünkü esp32_bridge setpoint'i yalnız aktif bir
   > `goto` varken üretiyor; sürü görevinde goto gönderilmezse sessiz kalır.
   > 🛡️ **`baslat.sh` bunu zorluyor:** `ca` anahtarı, `/ws/kacinma` dosyası
   > **varken `collision_avoidance`'ı açmayı REDDEDER** ve uyarı basar.
   > Yani ikisini yanlışlıkla birden açmak mümkün değil — `CLAUDE.md` §4
   > çakışması kod tarafından engelleniyor. (15 Ağustos'ta eklendi; eskiden
   > `formasyon` anahtarı `collision_avoidance`'ı **da** açıyordu.)
3. ✅ **Parametreler bağlandı** — `ucus_ayarlari.py` tek kaynak,
   `baslat.sh` hem `basit_kacinma`'yı hem `collision_avoidance`'ı oradan
   besliyor.

### ✅ Test 2 (yerde, CANLI mesh) — GEÇTİ, uçuş gerekmedi (21 Ağustos)

Test 1 adaptörün **işaret yönünü** dizüstünde doğruluyordu. Adaptörün
**gerçek mesh `AgentStatus`'unu** kabul edip etmediği ayrı bir soruydu ve
ancak uçakta ölçülür. Araç: `deploy/rpi/teshis/ca_gozlem.sh` — uçan yola
dokunmadan `collision_avoidance` kopyasını gözlem konularına bağlıyor.

```
tani: passthrough=303 avoid=0 gate_alt=303 skip_state=0
      skip_stale=0 skip_adaptor=- komsu_veri=1/2 ben=var
```

| ölçüm | anlamı |
|---|---|
| `skip_adaptor=-` | **adaptör canlı mesh verisini hiç reddetmedi** — asıl kanıt |
| `komsu_veri=1/2` | iki komşuya abone, birinden veri (ylp01 yerde) |
| `ben=var` | kendi durumu alınıyor |
| `passthrough=303` | zincir uçtan uca aktı (formation_node → CA) |
| `gate_alt=303` | 3 m altında kaçınma KAPALI — `altitude_gate_m` tasarımı, arıza değil |
| `avoid=0` | uçaklar 12,4 m ayrıktı, `d0=6.0`'ın dışı — beklenen |

⚠️ **Ne ölçülmedi:** gerçek bir itme. Uçaklar `d0`'ın dışındaydı ve yerdeki
irtifa kapısı zaten kapalıydı. İtme davranışı ancak havada, komşu 6 m'nin
içine girince görülür.

### ✅ Test 1 (yerde, işaret yönü) — GEÇTİ, uçuş gerekmedi

`src/swarm_core/test/test_komsu_adaptoru.py`, **10/10**.
Adaptör `TYPE_CHECKING` importuyla ROS'suz yüklenebilir yazıldı, böylece
**yön doğrulaması dizüstünde** koşuyor. Ters işaret uçağı komşusunun üstüne
gönderir; bunu ilk kez havada görmek kabul edilebilir değil.

Kilitlenen davranışlar: `rel = komşu − ben` · itme komşudan uzağa ·
d0 dışında itme yok · yaklaşan komşuya duran komşudan **sert** tepki ·
origin ayrışıksa lat/lon yolu doğru cevabı veriyor (pos_x 100 m yanıltıcı
olsa bile) · çerçeve yoksa komşu atlanıyor · `v_xy_valid` düşükse hız 0
alınıp sert kabuk çalışmaya devam ediyor.

## 🔬 ALGORİTMA İNCELEMESİ — 21 Ağustos, uçuş öncesi tam okuma

Operatör talimatı: *"Bu çarpışma önleme algoritması tam iyi olmayabilir,
tüm bu kodu oku."* Üç dosyanın tamamı okundu (751 satır) ve çekirdek
**dizüstünde sayısal olarak koşturuldu** (`d0=6.0 hard=4.0`, sahadaki
değerler). Aşağıdakiler okuma + benzetim sonucudur.

### ✅ Çalışan çekirdek davranış

Benzetimde uçak komşuyu **`hard` kabuğunda (3B ≈ 4,0 m) tutuyor** ve hiçbir
senaryoda çarpışma olmadı:

| yaklaşma hızı | en yakın 3B mesafe |
|---|---|
| 0,5 m/s | 4,00 m |
| 1,0 m/s | 3,96 m |
| 2,0 m/s | 3,97 m |
| 3,0 m/s | 3,90 m |
| **5,0 m/s** | **2,00 m** ← kaçış tavanı 4 m/s, daha hızlıya yetişemiyor |

### 🔴 B1 — Asılı dururken TEĞET BİLEŞEN ÇALIŞMIYOR

`ca_core._tangent`:

```python
vf_h = math.sqrt(vfx*vfx + vfy*vfy)
if vf_h < 1e-3 or mag_rep < 1e-9:
    return 0.0, 0.0
```

Teğet, **kendi formasyon hızımıza** kapılı. Asılı duran uçakta `v_form=(0,0,0)`
→ teğet **sıfır**. Benzetimde doğrulandı: bütün satırlarda `teget vy = 0.00`.

**Bu tam olarak `plan_kur_asili` docstring'inin `basit_kacinma` için
şikâyet ettiği kusur:** *"biz asılı duruyorsak teğeti hiç açmıyor. Oysa
asılı dururken üstümüze gelen bir uçak, teğete en çok ihtiyaç duyduğumuz
durum."* **Aynı kusur `collision_avoidance`'ta da var.**

Sonucu: asılı uçak yalnız **düz geriye** itiliyor. Kovalayan bir uçak
karşısında en zayıf geometri — sürekli geri iter, hiç yana kaçmaz.

### 🔴 B2 — TAM TEPEDEN yaklaşmada koruma SIFIR

`ca_core.compute`:

```python
if d_xy < p.xy_guard:   # xy_guard = 0.3 m
    continue            # komsu TAMAMEN atlanir
```

Yatay mesafe 0,3 m'nin altındaki komşu **hiç değerlendirilmiyor**. Kaçış
zaten yalnız yataydır, yani dikey kaçış da yok. Benzetim (1 m üstte,
1 m/s alçalan komşu):

```
yatay 0.31 m -> kacis -4.00 m/s   (tam itme)
yatay 0.29 m -> kacis  0.00 m/s   risk=False   <-- KORUMA YOK
yatay 0.00 m -> kacis  0.00 m/s   risk=False   <-- KORUMA YOK
```

Tekillik koruması olarak konmuş (yatay kaçış yönü hesaplanamaz), ama sonucu
**dikey istiflenmede tam kör nokta**. 🔴 **Uçuş kuralı: asılı uçağa
TEPEDEN yaklaşılmaz.**

### 🟠 B3 — Uzaklaşan komşu ÇEKİM üretiyor (sönümleme tabanı yok)

```python
damp = p.c_damp * c * dist_scale     # c < 0 ise damp < 0
f_radial = mag + damp                # negatif olabilir -> komsuya DOGRU
```

`c` kapanma hızı; komşu uzaklaşırken negatif. `hard` ile `d0` arasında
kapanma hızı kapısı `mag`'ı sıfırlıyor, geriye yalnız negatif `damp`
kalıyor → **net çekim** (2 m/s uzaklaşmada ~1,2 m/s komşuya doğru).

Benzetimde kendini "zıplama" olarak gösteriyor: kaçış `-2,97 → +0,03 →
-2,97` diye değişiyor, uçak `hard` kabuğunda **titriyor**. Çarpışmaya yol
açmıyor (kabuğun içinde `mag` baskın) ama temiz bir geri çekilme yerine
sınır çevrimi üretiyor.

Düzeltmesi tek satır: `damp = max(0.0, ...)` — yalnız yaklaşırken sönümle.

### 🟡 B4 — Yavaş yaklaşmada koruma `d0`'da değil `hard`'da başlıyor

`gate = smoothstep((c - c_dead) / c_ref)`, `c_dead=0.2 c_ref=1.0`. Yavaş
yaklaşan (0,5 m/s) komşu için `gate ≈ 0,09` → itme neredeyse yok. Gerçek
koruma ancak `d3 < hard` olunca (`gate=1.0` zorlanıyor) başlıyor.

Yani **`d0=6.0` yalnız hızlı yaklaşmalarda anlamlı**; yavaşta etkin yarıçap
`hard=4.0`. Benzetim: 4,5 m'de 0,5 m/s yaklaşmada kaçış yalnız **0,21 m/s**.

### 🟡 B5 — `hard` eşiğinde süreksizlik

`d3 <= hard` iken `gate` **1.0'a zorlanıyor**. 4,01 m'de kaçış ~0,2 m/s,
3,99 m'de 4,0 m/s. Slew (4 m/s²) gerçek ivmeyi sınırlıyor ama niyet
basamak biçiminde. B3 ile birleşince yukarıdaki titreme çıkıyor.

### ✅ İyi yazılmış olanlar

`lat/lon` birincil (origin ayrışmasından bağışık, gerekçesi yazılı) ·
adaptör atlama sayaçları (*"neden tetiklenmedi"* ölçümle cevaplanıyor) ·
mesh kaynağıyla eşleşen BEST_EFFORT QoS (bu depoda birkaç kez düşülen tuzak,
burada yorumla korunmuş) · `r_min < hard < d0` açılışta doğrulanıyor ·
`r_min` altında yaklaşma hızını sıfırlayan son çare · her yerde `finite`
denetimi · muhafazakâr geri düşüşler (`rel_z=0`, hız 0).

## 🔴 Parametreler — operatör talimatı

**Önce güvenli mesafeden başla, sonra kıs.**

| Parametre | `collision_avoidance` varsayılanı | 15 Ağu | **YÜRÜRLÜKTEKİ (20 Ağu)** |
|-----------|-----------------------------------|--------|---------------------------|
| `d0_m` (itme başlar) | 4.5 | 8.0 | **6.0** |
| `hard_m` (doyum) | 2.0 | 4.0 | **4.0** |

Varsayılan 4.5 m bizim geometrimize göre **çok dar** — `MIN_AYRIM_M` zaten
4.0.

> ### ✅ 8.0 mı 6.0 mı — KARARA BAĞLANDI (20 Ağustos 2026, operatör)
>
> 15 Ağustos'ta `d0=8.0 / hard=4.0` seçilmişti; 18 Ağustos'ta bu `6.0/3.0`
> diye düzeltilmişti. **İkisi de ayrı bir arıza biçiminde haklıydı** ve
> tartışma bu yüzden kapanmıyordu:
>
> | Arıza biçimi | Nerede çıkar |
> |---|---|
> | `hard` < `MIN_AYRIM_M` | Koruma **geç** — tam kuvvet, kabul edilen sınır zaten aşıldıktan sonra başlıyor |
> | `d0` ≈ formasyon yaklaşması | Koruma **fazla** — normal formasyon geçişinde tetikleniyor, formasyonla çekişiyor |
>
> Çözüm ikisini ayırmak: `hard`'ı sınıra, `d0`'ı formasyona göre seç.
>
> ```
> hard = MIN_AYRIM_M       = 4.0 m   -> tam kuvvet TAM SINIRDA
> d0   = 1.5 x MIN_AYRIM_M = 6.0 m   -> 8.49 m yaklasmaya 2.49 m pay
> ```
>
> **Bedeli:** rampa 4.0 m yerine **2.0 m** (3 m/s'te 1.33 s yerine 0.67 s).
> Dar ama yeterli. Türetme `ucus_ayarlari.py`'de, `baslat.sh` `--kabuk`
> çıktısından besleniyor — değer **tek yerde**.
>
> ⚠️ 18 Ağustos notundaki "8.41 m" rakamı bugün **8.49 m**
> (`ucus_ayarlari.py` denetimi); sonucu değiştirmiyor.

> ⚠️ **İlk iki uçaklı uçuşta ÖLÇÜLECEK.**
> Kayıttan kaçınmanın **ne zaman tetiklendiğine** bak:
> - Yalnız gerçek yakınlaşmalarda tetikleniyorsa → 6.0 doğru
> - Her formasyon geçişinde tetikleniyorsa → `d0` 5.0'a indirilir ya da
>   `ARALIK_M` büyütülür
> - Hiç tetiklenmiyor ve yakınlaşma oluyorsa → 2.0 m'lik rampa dar kalmış,
>   `d0` 7.0'a çıkarılır (o zaman `ARALIK_M` de büyümeli)

## 🔴 Test — zorunlu, atlanmayacak

**1. Yerde (Y):** Adaptör doğru mu — komşu 10 m'deyken itme 0, 6 m'deyken
sıfırdan büyük ve **doğru yöne** mi. Uçuş yok.

**2. Gözlem (G) — tek uçuş:** `basit_kacinma` komutta kalır,
`collision_avoidance` gözlem modunda (`-r .../control/setpoint:=/gozlem/...`).
İkisi **aynı girdiyi** alır. Kayıttan karşılaştır: aynı anlarda mı, benzer
yönde mi, büyüklük farkı ne kadar. Beklenmeyen fark varsa sebebi bulunmadan
ilerlenmez.

**3. Komutta (K) — `--senaryo asili`:** Bir uçak havada asılı durur,
operatör diğerini **kumandayla yaklaştırır**. Bu test zaten yazılı ve tam bu
iş için var. Kayıttan gör: ne zaman itti, ne kadar itti, geri döndü mü.

**4. İki uçak, saha senaryosu:** Kritik ayrım eşiğin üstünde kaldı mı, ve
kaçınma normal formasyon geçişlerinde tetiklendi mi.

## Diğer seçenekler (operatör isterse)

| | Ne | Neden seçilmedi |
|---|----|-----------------|
| A | `basit_kacinma` kalsın | Yaklaşma hızını radyalde görmüyor, dikey yok |
| B | `collision_avoidance` + `kinematic_fusion` | 0.4 s gecikme |
| D | `basit_kacinma`'ya yaklaşma hızı ekle | Sürü kodu kullanılmamış olur |

`basit_kacinma` **silinmeyecek** — C beklenmedik davranırsa tek dosya
değişikliğiyle geri dönülür.

---

# KARAR-02 — Claude effort seviyesi: hep `max`, ultracode noktasal

**Durum:** 🟡 BEKLİYOR — kural yürürlükte, hatırlatma anları henüz gelmedi
**Ne zaman:** Her oturum (kural) + `PLAN.md` §8 **ADIM 1, 3, 4** (hatırlatma)
**Karar veren:** Operatör (15 Ağustos 2026)

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

## 🔴 Claude'un yapacağı — hatırlatma anları

Şu üç adıma gelindiğinde, **uçmadan önce** operatöre söyle:

| Adım | Düğüm | Neden fan-out gerekli |
|------|-------|------------------------|
| **ADIM 1** | `consensus_node` | Kayıplı mesh'te lider seçimi; iki lider senaryosu aranmalı |
| **ADIM 3** | `formation_node` | 50 Hz'de uçağa setpoint yazıyor |
| **ADIM 4** | `collision_avoidance` | İki uçak arasındaki tek koruma katmanı |

Söylenecek cümle: *"Bu düğüm ilk kez havaya kalkacak. KARAR-02 gereği burada
çok ajanlı denetim öneriliyor — bu mesaja `ultracode` yazar mısın?"*

Operatör istemezse tartışılmaz, tek kanalda ilerlenir.

**Genel kural:** havaya kalkacak bir düğüm **ilk kez** açılmadan önce denetim
önerilir. Belge, config, kurulum, düzeltme işlerinde önerilmez — orada israf.

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

# KARAR-04 — Üç uçak birden uçunca değişecek parametreler

**Durum:** ✅ **UYGULANDI (25 Ağustos 2026, 17:25)** — ylp01 onarılıp
kaldırma testini geçince. Ölçülerek doğrulandı: `SURU_KADRO="1 2 3"` +
`SURU_BEKLENEN_UCAK=3` üç uçağa dağıtıldı; canlı rütbeler **0/1/2**,
`expected_agent_count=3` üçünde de. `min_active_for_formation` kod
okumasıyla kapandı: canlı-üye eşiği, varsayılanı zaten 3 ve düğüm
kapalı — değişiklik gerekmedi. ⚠️ YAN ETKİ: ylp02'nin kaçış yönü
YUKARIDAN AŞAĞIYA döndü (rütbe 1→2); alçakta 4 m taban kelepçesi
korur. ⏳ ARM'lı yer testi (FORMING + sağlık oranı 2/3) İÇ MEKÂN
yasağı nedeniyle ilk açık alan oturumuna kaldı.
**Ne zaman:** ylp01 dönüp üç uçakla ilk uçuş yapıldığında
**Karar veren:** Operatör (15 Ağustos 2026, "sırası gelince")

## Karar

Bugün filo **iki uçak** (drone 1 ve 3) ama ajan **kimlikleri 1..3**. Bu ayrım
üç parametreye yansıyor ve üçüncü uçak katıldığında **elle** değişecek:

| Env / parametre | Bugün | Üç uçakla | Anlamı |
|---|---|---|---|
| `SURU_AJAN_SAYISI` → `agent_count` | **3** | 3 (değişmez) | **Kimlik aralığı** `1..N` — abone olunacak `droneN` konuları |
| `SURU_BEKLENEN_UCAK` → `expected_agent_count` | **2** | **3** | **Filo büyüklüğü** — `formation_reached` ve sağlık oranı |
| `task_reallocator.min_active_for_formation` | 2 | **3?** | ⚠️ hangi anlamda kullandığı **doğrulanmadı** |
| `SURU_KADRO` (`baslat.sh`) | **`"1 3"`** | **`"1 2 3"`** | 🔴 Dikey kaçışın RÜTBESİ bundan türüyor. Yanlış kadro kaçış **yönünü ters çevirir** (23 Ağu, KARAR-06) |

## Neden ayrı bir karar

Tek parametre iki işi yapıyordu ve **çelişiyorlardı**. Tek değerken:
`formation_reached` için `2 >= 3` false → **FORMING'de kalıcı takılma**; ve
sağlık oranı `1/3 = 0.33 < 0.5` → **bir uçak bozulunca tüm sürüye acil iniş**.
15 Ağustos'ta ikiye ayrıldı.

🔴 **`agent_count` 2 YAPILMAZ.** Bir kez "2 olmalı" diye yazılmıştı ve
uygulansaydı **ylp02 sürüden tamamen düşerdi**: `consensus_node.py:133`
`for aid in range(1, agent_count+1)` ile `drone1..droneN`'e abone oluyor,
uçaklarımız **1 ve 3**.

## Nasıl uygulanacak

`deploy/rpi/baslat.sh` → `SURU_BEKLENEN_UCAK=3` (üç uçakta da), konteyner
restart. `min_active_for_formation` için **önce kodu oku** — o sayının kimlik
aralığı mı, canlı sayı mı, çoğunluk eşiği mi olduğu doğrulanmadı.

## Test

Üç uçak yerde, pervanesiz, ARM'lı: `swarm_fsm` FORMING'e geçip
`formation_reached` üretebiliyor mu; bir uçak kill'lenince sağlık oranı
`2/3 = 0.67 > 0.5` kalıyor mu (acil iniş **tetiklenmemeli**).

---

# KARAR-05 — Konteyner imajı: Dockerfile geri gelmeyecek, `docker save` yeter

**Durum:** ✅ **UYGULANDI** — yedek alındı ve doğrulandı (20 Ağustos)
**Ne zaman:** ylp01 döndüğünde · `cv2`+`pyzbar` eklenirken (`PLAN.md` §8 ADIM 5)
**Karar veren:** Operatör (20 Ağustos 2026)

## Karar

**`docker/rpi/` geri alınmayacak.** 16 Ağustos'ta silindi (`87e95c2`) ve
`yelpence-ros:latest` imajının tek tarifi oydu. İhtiyaç olduğunda **çalışan
imajın `docker save` kopyası** kullanılacak.

## Neden — yeniden üretmek değil, birebir çoğaltmak

Dockerfile'dan yeniden derleme `apt`'tan **güncel** paketleri çeker; ortam
sessizce kayar ve uçan yapılandırmayla aynı olduğu garanti edilemez. Yarışmada
elimizdeki şey **bilinen-iyi** bir ortam: uçuş kanıtını o geçirdi.

`docker save` onun **donmuş, birebir** kopyası. Bu bağlamda yeniden
üretilebilirlikten daha değerli.

**Ölçüldü (20 Ağustos):**

```
yelpence-ros:latest   1.26 GB   ID 661296d759c2
ylp00 ve ylp02'de AYNI ID -> ayrisma yok, hangisinden alinsa fark etmez
disk: iki Pi'de de 17 GB bos
```

İmaj **yalnız ortam**: ROS Jazzy + mavros + geographiclib + python venv.
**Kod içinde değil** — host'taki `~/yelpence_ws` konteynere `/ws` olarak
bind-mount ediliyor. Bu yüzden kod değişince imaj yeniden üretilmiyor zaten.

## Nasıl uygulanacak

**Yedek alma** (referans uçaktan, bir kez):

```bash
./deploy/yki/drone_bul.sh ylp00 \
  'docker save yelpence-ros:latest | gzip -1 > ~/yelpence-ros-<tarih>.tar.gz'
# sonra dizustune cek — Pi'de birakmanin anlami yok, ayni ariza alani
```

**Yeni Pi'ye yükleme:** `docker load < yelpence-ros-<tarih>.tar.gz`
Gerisi `deploy/rpi/README.md` (provizyon → kod rsync → `run_drone.sh <N>`).

**Paket eklemek** (`cv2`, `pyzbar` — ADIM 5'in ön koşulu):

```bash
docker run -it --name imaj_yeni yelpence-ros:latest bash
#   ... apt/pip ile kur ...
docker commit imaj_yeni yelpence-ros:latest
```

🔴 **Ne eklediğini `RPI_ESITLEME.md`'ye YAZ.** Dockerfile yokken imajın içinde
ne olduğunu söyleyen tek kayıt orası olacak. Yazılmazsa altı ay sonra kimse
bilmiyor.

## Kabul edilen bedel

| Ne kaybediliyor | Karşılığı |
|---|---|
| İmajın içeriği koddan okunamıyor | `RPI_ESITLEME` değişiklik defteri |
| Sıfırdan yeniden üretilemez | Zaten istenmiyor — kayma riski |
| ~600 MB'lık dosya git'e giremez | Dizüstünde + harici yedek |

🔴 **Bu kararın şartı:** yedek **gerçekten alınmış olmalı.** Alınmazsa imaj
yalnız SD kartlarda kalır ve ikisi de giderse ortam **ne yeniden üretilebilir
ne kopyalanabilir**.

## ✅ Yedek alındı ve doğrulandı (20 Ağustos 18:15)

```
~/yelpence-yedek/yelpence-ros-20260820.tar.gz
378 MB · md5 98c7f7c92be72e51b2215b552e54e9ce
13 katman · config 661296d… (ucaklarda kosanla BIREBIR)
gzip -t: saglam · alma suresi 1m34s (gzip -1, Pi 5)
```

Uçaktaki geçici kopya silindi — aynı arıza alanında tutmanın anlamı yok.

> 🔎 **Yolda çıkan düzeltme:** *"yedek hiç alınmamış"* demiştim, **yanlıştı.**
> `~/yelpence-yedek/` içinde **30 Temmuz'dan kalma** bir kopya zaten varmış
> (`yelpence-ros_20260730.tar.gz`) ve config hash'i aynı: `661296d…`. Yani
> imaj 30 Temmuz'dan beri değişmemiş ve yedek o gün de alınmış — **hiçbir
> belgede yazmadığı için kimse bilmiyordu.** Asıl eksik yedek değil, kaydıydı.
> Klasöre artık `README.md` konuldu.

⚠️ **Bu klasör git'e girmiyor** (378 MB × 2). Harici bir yedeği yok — tek
kopya bu dizüstünde. Makine giderse imaj yine yalnız SD kartlarda kalır.

## Test

- Yeni bir Pi'de (ya da ylp01 dönünce) `docker load` → `run_drone.sh <N>` →
  `docker exec droneN ps | grep -c "ros2 run"` **12 olmalı**
- `cv2`+`pyzbar` eklendikten sonra: `python3 -c "import cv2, pyzbar"` hatasız

## Diğer seçenekler (operatör isterse)

| | Ne | Neden seçilmedi |
|---|----|-----------------|
| A | `docker/rpi/Dockerfile.rpi` geri alınsın | Yeniden derleme ortamı kaydırır; uçan yapılandırma birebir korunmaz |
| B | Hiç yedek yok, gerekince elle kurulur | ROS Jazzy + mavros elle kurulumu saatler sürer ve aynısı çıkmaz |

---

# KARAR-06 — Çarpışma önlemede kaçış yönü: DİKEY birincil, yatay son çare

**Durum:** ✅ **UYGULANDI VE UÇTU** — 23 Ağustos akşamı, ilk uçuşta çalıştı
**Ne zaman:** Uygulandı ve uçuruldu 23 Ağustos 2026
**Karar veren:** Operatör (23 Ağustos 2026)

## Karar

Çarpışma önlemenin birincil kaçış yönü **dikey** olacak. Çatışan uçaklardan
kimliği büyük olan, küçüğün **ölçülen** irtifasından `katman` kadar uzağa
gider. **Yatay itme yalnız sert kabuğun (`hard`) içinde** açılır.

```
d0 = 4.0 m (SABIT) · hard = 2.5 m · katman = 3.0 m
v_dikey = 1.2 m/s (= PX4 MPC_Z_VEL_MAX_UP) · a = 2.0 · kp = 2.0
rutbe: kadrodan (SURU_KADRO), DONUSUMLU merdiven (+k, -k, +2k...)
```

## Neden

**Operatörün gerekçesi:** yatay düzlem görev geometrisinin kendisi
(formasyon slotları, rota, QR konumları); yatay itmek formasyonu bozar,
dikey eksen boş. Ayrıca yatay "sağa geç" kuralı n=3'te döngüsel, dikeyde
kimlik sıralaması döngüyü imkânsız kılıyor.

**Ölçümle doğrulandı** (formasyon yakın geçişi, benzetim):

```
yanal aralik  bagil hiz   en yakin 3B   YATAY KAYMA
     3.0 m      3.0 m/s      3.09 m       0.00 m
     3.5 m      3.0 m/s      3.54 m       0.00 m
```

Formasyon geometrisi hiç bozulmuyor — hedeflenen davranış tam olarak bu.

**Neden yatay tamamen kapalı değil** (operatör kararı, ölçüme dayalı):

```
yaklasma    SAF DIKEY   SAF YATAY   DIKEY + SON CARE
 2.5 m/s      1.01 m      2.02 m        2.06 m
 4.0 m/s      0.47 m      1.53 m        1.20 m
```

Dikey yetkiyi gerçekçi olmayan değerlere çıkarmak bile açığı kapatmıyor
(v=5 a=5 → 1,83 m). Sebep ayar değil **geometri**: dikey kaçışın
kazanabileceği en fazla mesafe `katman` kadar ve onu kurmak 2-3 sn alıyor.

**Neden a=2.0, 3.0 değil:** hız tavanı (1,2) baskın olduğu için a=3.0'ın
kazancı yalnız 0,04 m; bedeli ~%75 gaz (askı %66) ve `MPC_ACC_DOWN_MAX=3.0`
sınırına basmak. Operatör "en dengeli değer" dedi.

## Nasıl uygulandı

`ca_core.py` (dikey çekirdek + `xy_guard` kör noktası + son çare kapısı) ·
`komsu_adaptoru.py` (dikey datum) · `collision_avoidance_node.py` ·
`ucus_ayarlari.py` (tek kaynak + PX4 kırpma denetimi) · `baslat.sh` (rütbe).

**Geri alma tek parametre:** `k_dikey=0` → düğüm eski davranışına birebir
döner. Saf dikey isteniyorsa `k_yatay=0`.

## Test

**Birim: 78/78.** **Yer testi: 5/5** — datum · rütbe/işaret · son çare ·
geçirgenlik · körlükte tutma. Ayrıntı `CA.md` §6.

## ✅ İLK UÇUŞ SONUCU (23 Ağustos akşamı)

İki tam kaçış-dönüş çevrimi, ikisi de temiz:

```
tirmanma +3,1 m ve +2,8 m  (hedef 3,0)  ·  tepe hiz 1,25 m/s (tavan 1,2)
donus 0,50 m/s -> nominale 4,79 m (iki kez)  ·  yatay itme HIC ACILMADI
en yakin yatay 3,20 m  ·  alarmlar temiz
```

Ayrıntı: `CA.md` §6.5.

## 🔴 Uçuştan çıkan ve KARARA BAĞLANAN

### `MPC_Z_VEL_MAX_UP` 1,2 → 3,0 — ❌ VAZGEÇİLDİ, ölçümle

Sabah "yanal kaymayı 4,8 → 1,9 m indirir" diye tartışılmıştı. Uçuş kaydı
kapattı:

```
aski gazi %72 (belgede %66 yaziyordu)  ·  p90 %77
gaz >= %100 : ~2.5 sn toplam, en uzun kesintisiz blok 0.7 sn
```

1,2 m/s tırmanmak zaten itki payını tüketiyor. **Yükseltilemez.** Aynı
gerekçeyle `a_dikey`'i 2,0'ın üstüne çıkarmak da ölçülmeden yapılmaz.

## 🔴 Kalan

1. ✅✅ **`hist_m` 0,5 → 2,5 — UÇUŞTA DOĞRULANDI (25 Ağu 02:03):**
   bırakma 7,2-8,3 m, dalış yok, yo-yo kapandı (`CA.md` §7.2).
   (24 Ağustos 14:30'da koda bağlanmıştı:) Zincir
   kuruldu: `ucus_ayarlari.py` → env → `baslat.sh` → düğüm (önceden
   zincir YOKTU, düğüm gömülü 0,5 ile koşuyordu). **2,5 seçildi, 3,0
   değil:** çıkış eşiği (d0+hist = 6,5 m) formasyonun planlı en yakın
   yaklaşmasına (8,49 m) 1,99 m pay bırakıyor, 3,0 yalnız 1,49 m
   bırakıyordu; denetime "çıkış ≥ kritik yaklaşma = HATA" koşulu
   eklendi. Uçuş doğrulaması akşam.
2. ✅ ylp01 dönünce `SURU_KADRO="1 2 3"` — **YAPILDI (25 Ağu 17:25,
   KARAR-04 tam kaydına bak; rütbeler 0/1/2 ölçüldü).**
3. ✅ **Depo/uçak farkı — KARAR (24 Ağustos, operatör): `tatmin`
   düzeltmesi ile `hist_m` akşam uçuşuna BİRLİKTE dağıtılacak.**
   Tek-değişiklik kuralından bilinçli sapma: geniş histerezis uçağı
   eski kodun hatalı olduğu "ayrım kurulu + çatışma sürüyor" durumunda
   (komşu 4,0-6,5 m bandı) çok daha uzun tutuyor; yalnız `hist_m`
   dağıtmak ölçülmüş dalış imzasını (-1,48 m/s) SIKLAŞTIRIRDI. İki
   değişiklik logda ayrık gözlenir: çıkış mesafesi ↔ içerideyken
   irtifa dalışı.

> ### ✅ `KARAR-02` denetimi bu uçuş için ATLANDI — operatör kararı (23 Ağu)
>
> Çok ajanlı denetim `KARAR-02` gereği önerildi. Operatör **atladı**:
> *"Bu test bana çok ağır ve lüzumsuz geliyor. Uçuş testleri ile direkt
> nokta atışı şeyleri yakalayabiliriz."*
>
> Gerekçesi savunulabilir: bugün beş tasarım kusurunu **birim testler**
> yakaladı, denetim değil; ve kod zaten beş yer testinden geçti.
>
> **Bir daha sorulmayacak** — bu uçuş için karar verildi. Sonraki
> düğümlerde (ADIM 3 `formation_node`) `KARAR-02` yeniden geçerli.

## Diğer seçenekler (operatör isterse)

| | Ne | Neden seçilmedi |
|---|----|-----------------|
| A | Saf dikey (`k_yatay=0`) | Hızlı yaklaşmada koruma çöküyor (4 m/s'te 0,47 m) |
| B | Saf yatay (eski kip) | Formasyon geometrisini bozuyor; görevin kendisi o düzlem |
| C | Göreli rütbe (yalnız çatışanlar sıralanır) | Çizgi formasyonunda iki uçak **aynı katmanı** seçiyor — mesh kusursuz olsa bile |
| D | "En yüksek komşunun üstüne çık" | Benzetimde yarış: drone2 ve drone3 aynı irtifada buluştu (0,00 m ayrım) |

---

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
