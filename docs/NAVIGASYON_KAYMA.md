# NAVİGASYON — kaymayı sıfırlama planı

**Son güncelleme:** 20 Ağustos 2026, 03:15

**Hedef:** Uçak, yürüyen setpoint'in **arkasında kalmasın.** Ne seyirde,
ne hızlanırken. Hız arttıkça da bozulmasın.

Bu belge neyin niye kaydığını, neyin şu an doğru olduğunu ve **sırayla ne
yapacağımızı** tutuyor.

---

## 1. Kayma nereden gelir — üç durum

PX4'ün konum döngüsü, eksen başına:

```
v_komut = Kp × (hedef − konum) + v_ff        Kp = MPC_XY_P = 0.95  (uçaktan okundu)
```

Hız döngüsü de bunu ivmeye çevirir:

```
a_komut = Kv × (v_komut − v) + a_ff
```

### Durum 1 — sadece konum (`v_ff = 0`)

Sabit hızda uçmak için `v_komut = v` olması gerekir:

```
Kp × hata = v      →      hata = v / Kp
```

| hız | kalıcı kayma |
|-----|--------------|
| 2 m/s | 2.1 m |
| 3 m/s | 3.2 m |
| 5 m/s | **5.3 m** |

**Hızla doğru orantılı.** Kaçınılmaz: uçağı ileri iten tek şey hatanın
kendisi, hata sıfırlanırsa uçak durur.

### Durum 2 — konum + hız ileri-beslemesi ✅ **şu an buradayız**

```
v = Kp × hata + v_ff      ve      v_ff = v
→  hata = 0
```

**Kalıcı halde kayma sıfır ve hızla BÜYÜMEZ.** Çünkü `v_ff` hızın kendisi;
otomatik ölçekleniyor. Hata artık uçağı taşımıyor, yalnız bozulmayı
düzeltiyor.

`px4_bridge._yurutucu_ilerlet` bunu yapıyor (50 Hz) ve
`publish_position_velocity_setpoint` ile PX4'e gönderiyor.

### Durum 3 — üstüne ivme ileri-beslemesi ❌ **yapılmamış**

Kalıcı halde sıfır, ama **hızlanırken** hâlâ hata var: hız döngüsünün ivme
üretmesi için hız hatası birikmeli (`hız hatası = a / Kv`), o da rampa
boyunca konum hatasına integre olur.

`a_ff` verilirse ivme doğrudan komut edilir; geçici rejimdeki kayma da
büyük ölçüde kalkar.

**Kanal var ama kapalı:**

- `AgentSetpoint.msg` → `ax, ay, az` + `acceleration_valid` alanları **mevcut**
- `formation_node` → `out.acceleration_valid = False`
- `px4_bridge` → ivmeye **hiç dokunmuyor** (`grep .ax` boş)
- `mavros_command_sender` → **dört type_mask'ın hepsinde**
  `IGNORE_AFX | IGNORE_AFY | IGNORE_AFZ`

---

## 2. Şu anki durumun dürüst değerlendirmesi

**İyi:** Sistem Durum 2'de. Teorik olarak kalıcı kayma sıfır ve hızı
5 m/s'e çıkarmak bunu bozmaz.

**Bilinmeyen:** Bunu **doğrulayan bir ölçümümüz yok.** Elimizdeki tek sayı
(2 m/s'te 0.44 m) **7 metrelik bir bacakta** alındı ve kodun kendi notu
diyor ki *"7 m'lik geçişin neredeyse tamamı geçici rejim"*. Yani o sayı
seyir kayması değil, hızlanma fazının artığı.

> ⚠️ `ucus_ayarlari.py`'deki `IZLEME_GECIKME_S = 0.22` bu yanlış okumadan
> türedi ve **doğrulanmamıştır.** Kalıcı hâl kayması teoriye göre ≈ 0
> olmalı; 0.22 s'lik doğrusal model muhtemelen fazla karamsar. Adım 1
> bunu ya doğrulayacak ya çöpe atacak.

---

## 3. YAPILACAKLAR — sırayla

### Adım 1 — ÖLÇ (kod değişikliği YOK) 🔴

Modellemeyi bırakıp ölçmek. Bu konuşmada iki kez model uydurup iki kez
yanıldık (önce frenleme mesafesi, sonra doğrusal gecikme); sebebi hep aynı:
ölçülmemiş bir şeyi modellemek.

**Kurulum**
- Tek uçak (ikinci uçak yerde, riski azalt)
- **En az 40 m DÜZ BACAK** — aşağıda neden
- `--senaryo tekli` uyarlanabilir (şu an `TEKLI_ILERLEME_M = 7.0`, büyütülecek)
  ya da tek bir `goto`

#### "Düz bacak" nedir, 40 m nereden geliyor

**Bacak** = rotanın bir noktadan diğerine giden tek düz parçası. Saha
görevinde dört tane var: 41.7 / 22.4 / 19.9 / 19.4 m.
**Düz bacak** = içinde dönüş, formasyon değişimi, irtifa değişimi olmayan
bacak — yoksa ölçtüğün şey kayma değil, o manevra olur.

Her bacak üç fazdan oluşur ve kalıcı kayma **yalnız seyir fazında** ölçülür:

```
|<-- hızlanma -->|<-------- SEYİR -------->|<-- yavaşlama -->|
0 ─────────────> v sabit ────────────────> v ─────────────> 0
                        ↑ ÖLÇÜM BURADA
```

İki mesafe gerekiyor:

```
rampa  = v² / a          a = 1.5 m/s² (yürütücü ivmesi)
oturma = 4τ × v          τ = 1/Kp = 1/0.95 ≈ 1.05 s
```

| hız | rampa | oturma (4τ) | **gereken bacak** |
|-----|-------|-------------|-------------------|
| 2 m/s | 2.7 m | 8.4 m | 11 m |
| 3 m/s | 6.0 m | 12.6 m | 19 m |
| 4 m/s | 10.7 m | 16.8 m | 28 m |
| 5 m/s | 16.7 m | 21.0 m | **38 m** |

**40 m, ileride 5 m/s'i de ölçebilmek için seçildi.** Daha kısa bacakta
yüksek hız ölçülemez — uçak seyre oturmadan yavaşlamaya başlar.

**Eski ölçüm neden geçersiz:** 0.44 m, **7 m**'lik bir bacakta 2 m/s'te
alındı. Rampa 2.7 m, kalan 4.3 m = 2.2 sn = yalnız **2.1 τ**. Hatanın
~%12'si hâlâ sönmemiş; yani uçak seyir fazına hiç oturmamış.

**Kayıttan çıkarılacaklar** (ikisi de zaten bag'de)
```
/drone_N/mavros/setpoint_raw/local     -> yürüyen setpoint (nereye dedik)
/drone_N/mavros/local_position/pose    -> gerçek konum   (nereye gitti)
```

**Çıkarılacak üç sayı**
1. **Kalıcı hâl kayması** — seyir fazının ortasında, ortalama `|sp − konum|`.
   Teoriye göre ≈ 0 olmalı. Değilse `v_ff` doğru gitmiyor demektir.
2. **Tepe geçici hata** — hızlanma fazındaki en büyük fark.
   Adım 2'nin ne kadar kazandıracağını bu söyler.
3. **Oturma süresi** — hatanın sönme zaman sabiti. Teori `1/Kp ≈ 1.05 s`.

**En az iki hızda tekrarla** (örn. 2 ve 4 m/s). ✅ **Bu artık ucuz:**
14 Ağustos'ta `px4_bridge`'e canlı parametre eklendi, yani uçak havadayken
hız değiştirilebiliyor:

```bash
./deploy/yki/drone_bul.sh ylp00 \
  'docker exec -i drone1 bash -lc "source /opt/ros/jazzy/setup.bash && \
   python3 - --ns /px4_bridge --yaz guided_hiz_yatay_mps=4.0"' < src/gcs/px4_param.py
```

Öncesinde her hız için konteyner yeniden başlatmak gerekiyordu — MAVROS'un
FCU el sıkışması, EKF oturması, RTK yeniden fix. Yani uçağı indirip kaldırmak.
Artık tek uçuşta 2/3/4 m/s denenebilir. Kalıcı kayma hızla
büyümüyorsa Durum 2 doğrulanmış olur ve **hızı yükseltmenin önü açılır.**

### Adım 2 — Doygunluk payını koru 🔴

Kalıcı kaymanın sıfır olması **tek şarta bağlı**: `v_ff + Kp×hata`
`MPC_XY_VEL_MAX` tavanını aşmamalı.

Seyir hızı tavana eşitse konum düzeltmesine **hiç yer kalmaz** — PX4 kırpar,
hata kapanamaz ve kayma geri gelir.

```
seyir 3.0, tavan 5.0  ->  düzeltmeye 2.0 m/s pay    ✅
seyir 5.0, tavan 5.0  ->  düzeltmeye 0 m/s pay      ❌ kayma garanti
```

- `[x]` ✅ **Kural konuldu:** `PX4_HIZ_TAVANI_MPS ≥ GOREV_HIZ_MPS × 1.5`.
  `ucus_ayarlari.py` bunu artık **hata** olarak veriyor (uyarı değil).
  5 m/s denenince: *"Tavani 7.5 yap ya da hizi dusur."*
- `[ ]` Seyir 5 m/s'e çıkarılacaksa tavan **7.0-7.5** olmalı.
  Bu da `MPC_TILTMAX_AIR`'ı etkiler mi diye config'e baktır.

### Adım 3 — İvme ileri-beslemesini aç 🟠

Geçici rejimdeki kaymayı kaldırır. Adım 1'in tepe hata ölçümü buna değip
değmeyeceğini söyleyecek.

- `[ ]` `mavros_command_sender.py`: konum+hız maskesinden
  `IGNORE_AFX | IGNORE_AFY | IGNORE_AFZ` bitlerini çıkar, yeni bir
  `publish_position_velocity_accel_setpoint` ekle
- `[ ]` `px4_bridge._yurutucu_ilerlet`: yürütücü zaten ivme rampasını
  biliyor (`guided_ivme_yatay_mps2`), o anki ivme vektörünü döndürsün
- `[ ]` **Yalnız rampa fazında ver, seyirde sıfırla.** Seyirde `a_ff`
  vermek gürültü ekler, faydası yok
- `[ ]` Adım 1'i tekrarla, tepe hatayı karşılaştır

> **Dikkat:** PX4'ün ivme ileri-beslemesi eğim komutuna doğrudan gidiyor.
> Yanlış işaret ya da ölçek, kalkışta sert bir yatma demek. İlk deneme
> **havada, irtifada**, yerde değil.

### Adım 4 — Sürü tarafı Durum 1'e düşmesin 🟠

`formation_node`'un SVT'si **saf oransal**:

```python
vx -= self._svt_k * ex * s_xy        # svt_k = 0.8
```

Yani `v = −0.8 × hata` — bu **Durum 1**. İçinde ayrı bir `v_ff` var ama o
sürü merkezinin hızı için ve bayatlık kapısıyla sıfırlanıyor. Kalıcı
kayma `v / 0.8`, yani PX4'ün 0.95'inden bile **kötü**.

- `[ ]` `formation_node`'u **konum kipine** al: `position_valid=True`,
  `velocity_valid=False`. O zaman `px4_bridge`'in kanıtlanmış yürütücüsü
  (Durum 2) devreye girer, SVT devre dışı kalır.
  `formation_node` **nereye** gidileceğini hesaplar, `px4_bridge` **nasıl**
  gidileceğini yürütür.
- `[ ]` Alternatif (tercih edilmez): SVT'ye gerçek hız ileri-beslemesi ekle.
  Daha çok iş, kazancı yok.

Bkz. `SURU_ENTEGRASYON.md` Faz 3.

### Adım 5 — Kaymayı sürekli izle 🟡

Bir kez düzeltip unutmamak için.

- `[ ]` Uçuş sonrası kayıttan bacak başına `max |setpoint − konum|` çıkaran
  bir araç. `param_karsilastir.py` gibi, uçuştan sonra çalıştırılır.
- `[ ]` Eşik aşılırsa uyar. Kayma sessizce büyürse (ayar bozulması, rüzgâr,
  itki düşmesi) bunu **kayıttan** görelim, uçuşta değil.

---

## 4. Kaymayı sıfırlamayı engelleyebilecekler

Teori sıfır diyor ama gerçekte kalan artıklar:

| Kaynak | Etkisi | Ne yapılır |
|--------|--------|-----------|
| **Hız tavanı doygunluğu** | Kayma geri gelir | Adım 2 — pay bırak |
| **EKF konum gecikmesi** | Sabit küçük ofset | Ölçülür, telafi edilmez |
| **Rüzgâr** | Kalıcı sapma (integral yoksa) | PX4'ün hız döngüsünde integral var |
| **İtki yetmemesi** | Rampa hedefe yetişemez | İvmeyi düşür ya da yükü azalt |
| **Mesh gecikmesi** | Etkilemez — yürütücü **yerelde** | — |

Son satır önemli: mesh kontrol döngüsünün **içinde değil**. Kayma tartışması
tamamen uçağın kendi içinde geçiyor; paket kaybı buraya karışmıyor.

---

## 5. Özet tablo

| | Kalıcı kayma | Hız artınca | Durum |
|---|---|---|---|
| Sadece konum | `v / Kp` (5 m/s'te 5.3 m) | doğrusal büyür | `formation_node` SVT böyle |
| **Konum + hız FF** | **≈ 0** | **büyümez** | ✅ `px4_bridge` yürütücüsü |
| + ivme FF | ≈ 0, geçici rejim de düzelir | büyümez | ❌ kanal var, kapalı |

**Kısa cevap:** Hızı yükseltmek kaymayı büyütmez — sistem zaten Durum 2'de.
Yeter ki (a) hız tavanına pay kalsın, (b) sürü kodları bizi Durum 1'e
düşürmesin. İkisi de yukarıda maddelendi.

---

## ✅ ADIM 1 ÖLÇÜLDÜ — 20 Ağustos 2026, 30 m bacak, iki uçak

**Uçuş:** `--senaryo g2 --irtifa 10 --mesafe 30 --dronelar 1,3`, seyir 3.0 m/s,
59 sn, iki uçak. Kayıttan `setpoint_raw/local` (nereye dedik) ile
`local_position/pose` (nereye gitti) yatay farkı çıkarıldı; bacak başına
566 örnek, %74'ü seyir fazında (komut tepe hızı tam 3.00 m/s).

| | ylp00 gidiş | ylp00 dönüş | ylp02 gidiş | ylp02 dönüş | **ortalama** |
|---|---|---|---|---|---|
| **Kalıcı kayma** | 0.130 m | 0.102 m | 0.063 m | 0.112 m | **≈ 0.10 m** |
| **Tepe geçici hata** | 1.223 m | 1.013 m | 1.173 m | 1.053 m | **≈ 1.12 m** |
| **Oturma süresi** | 3.52 s | 3.16 s | 3.72 s | 3.42 s | **≈ 3.5 s** |

### Ne öğrendik

1. **Kalıcı kayma pratikte YOK (≈10 cm).** Teorinin öngörüsü doğrulandı:
   konum + hız ileri-beslemesi kalıcı gecikmeyi kaldırıyor. **Eski 0.44 m
   rakamı geçersizdi** — 7 m'lik bacakta alınmıştı ve aslında geçici rejimi
   ölçüyordu. Bu belgenin ana şüphesi kapandı.
2. **Asıl hata geçici rejimde: ~1.1 m**, hızlanmanın ilk ~1.8 saniyesinde.
   İvme ileri-beslemesinin (`IGNORE_AFX|AFY|AFZ` kaldırılması) kazandıracağı
   pay işte bu — artık sayısı var, "değer mi" sorusu ölçüyle tartışılabilir.
3. **Oturma 3.5 s** — teori 4τ ≈ 4.2 s diyordu, gerçek biraz daha iyi.
4. **İki uçak birbirini doğruluyor** (0.06-0.13 m aralığı), yani sonuç tek
   uçağın tesadüfü değil.

### Hız artırmaya etkisi

Kalıcı kayma hızdan bağımsız ve zaten ihmal edilebilir; **hız artırmanın
önündeki engel kayma DEĞİL.** Sınırlayıcılar başka: geçici rejim tepe hatası
(hızla büyür), `path_planner`'daki yavaşlama rampası eksiği (aşım ~2.25 m
hesaplanmıştı) ve formasyon ayrım payı.

**Kalan:** ikinci hızda tekrar (plan 2 ve 4 m/s diyor). 30 m bacak 4 m/s için
28 m oturma istiyor — ölçüm penceresi 2 m'ye düşer, yani 4 m/s için **40 m**
bacak gerekiyor. 2 m/s ise bu bacakta rahat ölçülür.

---

## ✅ ADIM 2 UYGULANDI ve A/B ÖLÇÜLDÜ — 20 Ağustos 2026, ivme ileri-beslemesi

**Deney tasarımı:** aynı uçuş, aynı rota (30 m, 10 m irtifa, 3.0 m/s), aynı
hava. **ylp00 ivme FF AÇIK, ylp02 KAPALI (referans).** Tek değişken: kod.

| Metrik | ylp02 — FF KAPALI | ylp00 — FF AÇIK | Kazanç |
|---|---|---|---|
| **Tepe geçici hata** | 1.177 / 1.026 m | **0.551 / 0.324 m** | **−60 %** |
| **Varış aşımı** | 1.18 m *(ylp00 tabanı)* | **0.46 m** | **−61 %** |
| **Oturma süresi** | 3.88 / 3.36 s | **3.1 / 1.0 s** | daha hızlı |
| Kalıcı kayma | 0.073 / 0.083 m | 0.254 / 0.092 m | değişmedi (gürültü) |

### Deneyin güvenilirliği

**ylp02 kendi tabanını birebir tekrarladı:** bir saat önceki uçuşta 1.173 /
1.053 m, bu uçuşta 1.177 / 1.026 m. Yani ölçüm tekrarlanabilir ve ylp00'daki
fark gerçekten **koddan** geliyor — rüzgârdan, pilden ya da şanstan değil.

### Ne değişti (kod)

`_yurutucu_ilerlet` yamuk hız profilinin **türevini** de döndürüyor; ivme
**gecikme telafisinden ÖNCEKİ ham profilden** alınıyor (telafi bir düzeltme
terimi, yörünge ivmesi değil) ve yapılandırılmış ivme tavanıyla kelepçeleniyor
(varışta hız tek adımda sıfırlandığı için türev absürt büyük çıkardı).
`mavros_command_sender` `IGNORE_AF*` bitleri olmayan ikinci bir maske
kullanıyor; ivme, konum/hızla **aynı NED→ENU dönüşümünden** geçiyor.

`guided_ivme_ff` parametresi — **0.0 = kapalı (varsayılan), 1.0 = açık**, canlı
değiştirilebilir. Varsayılan bilerek kapalı bırakıldı: tek uçuşluk kanıtla
uçuş yolunun varsayılanı değiştirilmez.

### Kalan

- `[ ]` İkinci doğrulama uçuşu; sonra `guided_ivme_ff` varsayılanı **1.0**
  yapılabilir (ve `baslat.sh`'e env olarak eklenir).
- `[ ]` 4 m/s ölçümü hâlâ yapılmadı — 40 m bacak ister.
- Kalıcı kayma zaten ihmal edilebilirdi (≈0.1 m); bu düzeltme onu değil
  **geçici rejimi** hedefliyordu ve tam orada kazandırdı.
