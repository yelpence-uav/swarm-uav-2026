# KAMERA ve ALGI — sahada ölçülmüş sonuçlar

**Son güncelleme:** 28 Ağustos 2026, 12:10

> Bu belge **28 Ağustos 2026'da tek oturumda** yapılan kamera kurulumu,
> kalibrasyonu ve dört uçuşluk QR tespit testinin sonucudur. Her sayı
> **gerçek uçakta, gerçek uçuşta** ölçüldü — simülasyon yok, tahmin yok.
>
> Bir sayıya güvenmeden önce yanındaki "nasıl ölçüldü" satırını oku.

---

## 1. Tek cümlelik sonuç

**4056x3040 (4K) + titreşim yalıtımı ile, 1,5 m'lik QR 5-11 m irtifada
karelerin %38-69'unda okunuyor. Tepe 7-8 m'de %69. Tavanı belirleyen şey
çözünürlük değil, kalan titreşim.**

Saha kuralı: **QR okuması gerekiyorsa 6-9 m'de uç.**

---

## 2. Donanım

| | |
|---|---|
| Sensör | Arducam IMX477 (12,3 MP), ylp02'de |
| Bağlantı | Pi 5 CAM portu, **22 pin 0,5 mm** mavi flex |
| Mercek | C/CS, diyafram tam açık, odak elle |
| IR-cut | Elektromekanik, ışık sensörü ile — **çalışıyor** |

### Flex tuzağı

Pi 5 CAM/DISP girişi **22 pin 0,5 mm**; Pi 4 CSI girişi **15 pin 1,0 mm**.
İkisi birbirine takılmaz. Kamera modülünün girişi de dar olduğu için "iki
ucu da dar" mavi flex doğru kablodur — **ama ters takılırsa güç gelmez ve
hiçbir hata mesajı çıkmaz.** 28 Ağustos'ta tam olarak bu oldu; teşhis
"kablo yanlış" sanıldı, gerçekte flex tersti.

### IR-cut nasıl doğrulanır (10 saniye)

Telefonun/TV kumandasının IR LED'ini kameraya tut, tuşa bas, yayına bak:

- LED **parlak beyaz/mor** → filtre DIŞARIDA (gece kipi)
- **Nokta kadar zayıf ışık** → filtre İÇERİDE (gündüz kipi) ✅

Gündüz kipinde küçük bir nokta kalması **normaldir** — IR-cut filtreleri
850-940 nm kuyruğunda tam kesmez ve yakın mesafedeki IR LED çok parlaktır.
Sensörü elle kapatıp açarak iki kipi de görebilirsin; mekanizma mandallıdır.

> ⚠️ **Renk oranlarından IR sızıntısı teşhisi koyma.** R/G ve B/G'nin
> ikisinin birden yüksek olması IR ile *uyumludur* ama ona *özgü değildir* —
> kırmızımsı bir sahne ya da kayık AWB aynı oranları verir. 28 Ağustos'ta
> bu yüzden yanlış teşhis kondu; kumanda testi düzeltti.

---

## 3. Kamera ayarları — hepsi ölçümle seçildi

`deploy/rpi/kamera_yayin.py` içindeki varsayılanlar:

```python
PROFILLER = {'hotspot': {'mod': 'tamfov', 'onizleme': 0, 'kalite': 75, 'yayin': 640}}
KALIBRE_KAZANC  = '2.5923,1.2225'   # sabit beyaz dengesi
KALIBRE_POZLAMA = 'sport'           # otomatik, kısa deklanşör eğilimli
```

### 3.1 Pozlama — `sport`, sabit sayı DEĞİL

| deneme | sonuç |
|---|---|
| Sabit 1/250 (`4000`) | ❌ ortalama parlaklık **240/255**, karelerin **%37-45'i tam beyaza kırpık** |
| `sport` (otomatik) | ✅ kırpık **%0,0**, ortalama 117-189 |

**Neden sabit sayı yanlıştı:** deklanşör 1/250'ye hareket bulanıklığına
karşı sabitlenmişti ve o ölçüm doğruydu (4 m/s, 20 m: 1/250 okunuyor,
1/125 okunamıyor). **Ama ölçüm gölgede alınmıştı.** Kamera aşağı çevrilip
güneşli zemine bakınca sahne 3178 lux'ten **46 671 lux'e** çıktı — 15 kat.
Sabit deklanşör kısamadı, kare doydu.

Kırpılmış alanda kontrast **yoktur**: QR modülleri birbirine karışır,
kenar gradyanı sıfırdır. Renk dedektörü de o uçuşta hiçbir şey bulamadı.

`sport` aynı koşulda **1/3300 – 1/4739** seçiyor: hem doymuyor hem hareket
bulanıklığında hedefimizin 13 katı iyi. Sabit bir sayı ikisinden yalnız
birini verebiliyordu.

> **Ders:** ışık koşulunu ölçtüğün yer, uçtuğun yer değilse ölçüm geçersiz.

### 3.2 Beyaz dengesi — sabit kazanç, AWB DEĞİL

Beyaz kâğıt karşısında ölçüldü (merkez %40, doymamış, tekdüze %1):

| beyaz ayarı | R/G | B/G | sapma |
|---|---|---|---|
| auto | 1,255 | 1,253 | %25 |
| indoor | 1,248 | 1,246 | %25 |
| fluorescent | 1,243 | 1,247 | %25 |
| daylight | 1,260 | 1,191 | %26 |
| tungsten | 1,220 | 1,585 | %58 (doymuş) |
| cloudy | 1,643 | 1,224 | %64 (doymuş) |
| **sabit [2,5923 · 1,2225]** | **1,004** | **1,004** | **%0** |

**Ön ayarların hiçbiri düzeltmiyor** — yani seçim sorunu değil. Sebep:
libcamera resmî HQ kamera için yazılmış `imx477.json` ayar dosyasını
kullanıyor; Arducam'ın mercek + IR-cut geçirgenliği farklı olduğu için AWB
dosyaya göre "doğru" ama modüle göre yanlış kazanç hesaplıyor.

Sonuç magenta ton: beyaz kâğıt **R 210 · G 168 · B 211** çıkıyordu.

**Yeniden kalibrasyon (30 saniye):** beyaz kâğıt tut, `/tmp/kalibre.py`
çalıştır. Kapalı döngü — JPEG gama kodlu, kazançlar doğrusal ham üzerinde
çarptığı için tek adımlık düzeltme sapar; betik ölçüp tekrar düzeltiyor,
2 turda %0'a iniyor.

> ⚠️ **Bu kazanç gün ışığına (~4500 K) bağlıdır.** Akşam, kapalı hava ya da
> farklı mevsimde kayar. Renk dedektörünün eşikleri de bu renk dengesinde
> kalibre edilmeli.

### 3.3 Görüş açısı — 56,4°, config'deki 60° DEĞİL

`fov_horizontal_rad: 0.98437` (`src/swarm_perception/config/camera_params.yaml`).
Ölçüldü. Piksel/metre hesapları buna dayanıyor:

```
px/m = kare_genisligi / (2 · h · tan(FOV/2))
     = 4056 / (1,072 · h)     -> 4K
     = 2028 / (1,072 · h)     -> 2K
```

### 3.4 JPEG kalitesi — tespite etkisi YOK

q45 de q90 da **aynı mesafede** okuyor. Sadece dosyayı büyütür ve çözmeyi
yavaşlatır. Kaliteyi menzil için yükseltme.

4056x3040'ta ölçülen kare boyutları: q90 2574 KB · q75 1350 · q60 930 ·
q45 670. SD kart **25,3 MB/s** yazıyor; 4K q90 30 fps'te sınırı aşar.

---

## 4. 🔴 ASIL BULGU — rolling shutter

IMX477 satır satır okur. Bir karenin okunması sürerken gövde titrerse
**her satır farklı kayar** ve kare içinde "jöle" dalgalanması oluşur. QR'ın
modül ızgarası bozulunca çözücü örnekleme yapamaz.

### Kanıt zinciri

1. **Aynı QR durağan fotoğrafta okunuyor** — pankart fotoğrafı, 663 px,
   Laplacian yalnızca 15, zxing anında çözdü:
   `{"qr":5,"w":4,"mis":[[["frm","v",6],["mnv",10,-5],["alt",20]],...`
2. **Motorlar dönerken 200 karenin sıfırında okunuyor** — aynı QR, benzer
   piksel boyutu, daha keskin (Laplacian 89), doymamış.
3. **Operatör gözlemi:** "kaldırım taşlarında bile dalgalanma var" — sert
   zemin dalgalanıyorsa sebep rüzgâr/esneme değil, kameradır.
4. **Bant ölçümü:** ardışık karelerde satıra bağlı düzenli kayma rampası
   (b1→b5: −41 → −14 px).
5. **Kip değiştirince düzeldi** (aşağıdaki tablo).

### ⚠️ KARE HIZI JÖLEYİ DEĞİŞTİRMEZ

Raspberry Pi kamera sürücüsü kare hızını **VBLANK'i (bekleme) uzatıp
kısaltarak** ayarlar; **satır okuma süresi sabittir.** 10 fps'te sensör
yavaş okumaz — hızlı okuyup bekler.

10 → 30 fps denendi. Operatör: *"dalgalanma bir gram bile azalmamıştı."*
Doğru. Tek kazanç saniyede daha çok deneme oldu; disk ve CPU maliyeti
karşılığında.

**Okuma süresini KİP değiştirir:**

| kip | satır | okuma süresi | jöle |
|---|---|---|---|
| 4056x3040 | 3040 | ~33 ms | taban |
| 2028x1520 | 1520 | ~16 ms | yarısı |
| 1332x990 | 990 | ~11 ms | üçte biri |

---

## 5. QR TESPİT SONUÇLARI — dört uçuş

Hedef: **1,5 m'lik, 74 modüllü QR**, yere serili. Çözme tabanı
**2,25 px/modül** (daha önce ölçüldü; ders kitabı kuralı 4'tür).

Ölçüm: her uçuştan 240-800 kare örneklendi, `zxingcpp` ile çözüldü,
irtifa rosbag'den (`/drone_3/mavros/altitude`) eşleştirildi.

### 5.1 Yapılandırma karşılaştırması

| irtifa | 4K yalıtımsız | 2K yalıtımsız | 2K + yalıtım | **4K + yalıtım** |
|---|---|---|---|---|
| 1-4 m | %0 | %0 | %0-24 | %0 |
| 4-5 m | %0 | %4 | **%76** | %0 |
| 5-6 m | %0 | %22 | %67 | %53 |
| 6-7 m | %0 | %19 | %69 | %62 |
| 7-8 m | %0 | %25 | %62 | **%69** |
| 8-9 m | %0 | %15 | %20 | **%38** |
| 9-10 m | %0 | %18 | %0 | **%42** |
| 10-11 m | %0 | %0 | %0 | **%8** |
| 11 m üstü | %0 | %0 | %0 | %0 |
| **tavan** | **yok** | ~8 m | ~9 m | **~11 m** |

**Okunma:**

- **Yalıtımsız 4K hiçbir irtifada okumadı** — 200 karede sıfır.
- **Yalıtım 3-4 kat kazandırdı** (2K'da %4-25 → %62-76).
- **4K yukarıda daha iyi** (8-10 m'de %38-42'ye karşı %0-20), alçakta 2K
  biraz daha iyi.
- **En iyi yapılandırma: 4K + yalıtım.**

### 5.2 İki kenardaki iki ayrı sebep

**Altta (1-4 m): %0 — ama px/modül 11-25, kalite fazlasıyla yeterli.**
Sorun **kadraj**: 2 m irtifada karenin yer genişliği 2,1 m; 1,5 m'lik QR
azıcık kaymada dışarı taşıyor. **Alçak uçmak fayda etmiyor.**

**Üstte (11-15 m): px/modül 5,3-6,1 — taban 2,25, yani bol pay var.**
Üstelik QR'ın **%67-78'i BULUNUYOR** (konum desenleri saptanıyor, dörtgen
kuruluyor) ama **veri okunamıyor.** Yani yukarıda bizi kesen şey
çözünürlük değil, **kalan titreşim.**

### 5.3 Sıradaki kaldıraçlar

> 🔒 **QR'IN BOYUTU SABİT — 1,5 m, 74 modül. Büyütülemez.**
> Hedefi yarışma veriyor; boyutu ve modül sayısı bizim elimizde değil.
> Yani px/modül yalnızca **irtifa** ve **çözünürlük** ile oynanabilir,
> ikisi de tükenmiş durumda (4K zaten en yükseği, irtifayı da 11 m'nin
> üstüne çıkaramıyoruz).

Geriye kalan tek eksen **titreşim**:

1. **Daha fazla yalıtım.** Şu anki yalıtım 3-4 kat kazandırdı ve tavanı
   8'den 11 m'ye taşıdı. Daha yumuşak/ağır bir göbek, jel ped, kademeli
   yalıtım — kalan genliği düşüren her şey doğrudan tavana yazılır.
2. **Pervane balansı ve motor durumu.** Titreşimin kaynağı orası;
   dengesiz tek pervane bütün yalıtımı boşa çıkarır.
3. **Uçuş tarzı.** Sabit asılı kalmak, hızlı manevradan daha az titreşim
   üretir. QR okunacak noktada **durup beklemek** oranı yükseltir.
4. **Çözünürlük tükendi** — 4K zaten en iyisi.

**Yapılamayacak olan:** QR'ı büyütmek. Bu yüzden 6-9 m bandı bir tercih
değil, **kısıt** — görev planı bu irtifada QR'ın üstünden geçmeyi
sağlamak zorunda.

### 5.4 Boyut tavanı (jöle olmasaydı)

```
gereken piksel = modül_sayısı × 2,25
QR piksel      = QR_boyu × px/m
```

| QR | 4K'da teorik tavan |
|---|---|
| **1,5 m · 74 modül (yarışmanın verdiği)** | **~34 m** |

**Bugünkü gerçek tavan 11 m** — yani boyuttan değil titreşimden sınırlıyız.
Boyut tarafında 23 m'lik kullanılmayan pay duruyor; onu açacak tek şey
titreşimi düşürmek.

---

## 6. TESPİT ZİNCİRİ — algoritmalar ve hız

### 6.1 Veri yolu

```
rpicam-vid (libcamera)  ->  MJPEG akışı  ->  HTTP :8080/akis
   -> HttpMjpegGrabber      FFD8..FFD9 sınırlarından kareye böler
   -> camera_driver_node    JPEG'i ÇÖZMEDEN CompressedImage yayınlar
   -> vision_node           tek noktada çözer, iki dedektöre dağıtır
```

JPEG düğümler arasında **çözülmeden** taşınıyor: 4K ham `Image` **37 MB**
eder ve DDS'ten geçmez.

### 6.2 Hız sınırı — çözmeden ÖNCE

```python
run_qr = (now - son_qr) >= 1/5.0      # QR   5 Hz
run_lz = (now - son_lz) >= 1/15.0     # renk 15 Hz
if not run_qr and not run_lz: return  # <- ÇÖZMEDEN çık
```

**4056x3040 bir JPEG'i çözmek 106 ms.** İşlenmeyecek kareyi çözmek o süreyi
boşa yakar ve QR'a ayrılan çekirdeği tüketirdi.

**Tek tam çözme, iki yol paylaşıyor.** Ayrı ayrı çözmek (bulucu için 1/4,
renk için 1/2) denendi ve **geri alındı** — ölçüldü: 415 → 442 ms (seyir),
212 → 251 ms (askıda). Tek çözmeden sonra renk yolunun küçültmesi yalnızca
9 ms; ayrı çözmek aynı kareyi iki-üç kez çözmek demek.

### 6.3 QR — Aşama 1: varyans bulucu

QR'ın imzası **dokusudur**: küçük alanda çok sık siyah-beyaz geçiş.
Kayan pencereyle ölçülüyor:

```python
küçük = resize(kare, 1/4, INTER_AREA)      # 4056 -> 1014
gri   = BGR2GRAY(küçük).astype(float32)

ort = blur(gri,     (12,12))               # E[x]
sq  = blur(gri*gri, (12,12))               # E[x²]
std = sqrt(max(sq - ort², 0))              # yerel standart sapma

eşik  = percentile(std, 99) * 0.55         # KAREYE GÖRE UYARLANIR
maske = MORPH_CLOSE(std > eşik, 9x9)
konturlar = findContours(maske, RETR_EXTERNAL)
```

Alanca en büyük **2 kontur** alınıp kutuları **%25 payla** genişletiliyor ve
**×4 ile tam çözünürlüğe** geri haritalanıyor.

- **Eşik neden 99. yüzdelikten türetiliyor:** sabit bir sayı parlak betonla
  gölgeli çimde farklı davranırdı. Kareye göre kendini ayarlıyor.
- **`sqrt` öncesi `max(…, 0)`:** yuvarlama yüzünden E[x²]−E[x]² küçük negatif
  çıkabiliyor, NaN üretirdi.

> **Neden `cv2.QRCodeDetector` DEĞİL:** o dedektör üç köşe desenini ve
> zamanlama desenini **doğrulayarak** arıyor. 74 modüllü yoğun bir QR'da 1/4
> ölçekte modül 2,25 piksele düşüyor ve desen ayırt edilemiyor. **Ölçüldü:
> 1/4'te de 1/8'de de bulamadı.** Varyans bulucu QR yapısına hiç bakmıyor,
> yalnız anormal yüksek yerel değişintiyi arıyor.

### 6.4 QR — Aşama 2: çözücü kaskadı

Aday bölge **tam çözünürlükte** kırpılıp çözücüye veriliyor. Ölçüldü
(gerçek şartname QR'ı, 1,5 m, 8,5 m mesafe, 4056x3040, 74 modül):

| | pyzbar | **zxing** | wechat |
|---|---|---|---|
| tam kare, QR VAR | 695 ms | **268 ms** | 122 ms |
| tam kare, QR YOK | 628 ms | **275 ms** | **11 619 ms** ⚠️ |
| kırpma (~1272 px) | 61 ms | **34 ms** | 11 ms |
| menzil (1,5 m QR) | ~25 m | **~25 m** | ~40 m |

**Birincil zxing-cpp:** pyzbar ile aynı menzil, yarı süre, QR yokken de sabit
süre. **Yedek pyzbar:** zxing pip paketi (konteyner yeniden oluşturulunca
gider), pyzbar apt paketi (hep var). İşlevsel fark yok.

```
kırpmada bulunamadı -> başarısız++
   her N'inci başarısızlıkta:
      1) wechat'i YALNIZ KIRPMADA dene     (11 ms, ~40 m menzil)
      2) sonra TAM KARE taraması           (güvenlik ağı)
   wechat TAM KAREDE ASLA çalıştırılmaz    (boş karede 11,6 SANİYE)
```

İki incelik ölçümle bulundu:

- **Başarıdan sonra sayaç sıfırlanmıyor.** Sıfırlarken her başarıdan sonraki
  ilk başarısızlık hep tam taramaya giriyordu: **508 → 237 ms/kare.**
- **İlk başarısızlıkta mutlaka tam tarama** (`(n-1) % periyot`). Önce
  `n % periyot` yazılmıştı ve `detect()` tek başına çağrıldığında boş
  dönüyordu — iki birim test yakaladı.

### 6.5 🚀 HIZ — ilk sisteme göre kaç kat

İlk sistem: **tam karede pyzbar taraması.** Bugünkü: iki aşamalı + zxing.

| durum | ESKİ (tam kare pyzbar) | YENİ (iki aşamalı) | kazanç |
|---|---|---|---|
| **QR kadrajda** | 697 ms | **140 ms** | **5,0×** |
| **Gerçekçi karışım** (10 karenin 3'ünde QR) | 648 ms | **237 ms** | **2,7×** |
| QR yok (tam tarama turu) | 628 ms | 275 ms | 2,3× |

**Menzil kaybı YOK** — okuma yine tam çözünürlükte yapılıyor, sadece karenin
tamamı değil QR'ın bulunduğu bölge taranıyor.

#### Saniyede kaç okuma

| | eski | **yeni** |
|---|---|---|
| QR kadrajdayken | 1,4 Hz | **7,1 Hz** |
| Gerçekçi karışım | 1,5 Hz | **4,2 Hz** |

Düğüm **5 Hz'e ayarlı** (`qr_processing_rate_hz: 5.0`). Kritik nokta şu:
**eski sistem 5 Hz isteyip 1,5 Hz verebiliyordu** — ayar bir kurgudan
ibaretti, düğüm sürekli geride kalırdı. Yeni sistem 5 Hz'i **gerçekten
tutuyor**.

#### Uçuşta uçtan uca ölçülen (2K, JPEG çözme + QR + renk birlikte)

| irtifa | kare başına | Hz |
|---|---|---|
| 5-10 m (QR bulunuyor) | **123 ms** | 8,1 |
| 10-15 m | 171 ms | 5,8 |
| 0-5 m (bulunamıyor, tam tarama) | 438 ms | 2,3 |

Yani QR kadrajdayken zincir **hız sınırından daha hızlı**; kadrajda yokken
tam tarama turları devreye girdiği için yavaşlıyor. Bu doğru davranış —
hızlı olması gereken durum, QR'ın görüldüğü durum.

## 7. Renk (iniş bölgesi) tespiti

Klasik HSV eşikleme + şekil süzgeci. Öğrenme tabanlı değil.

```python
kare = GaussianBlur(kare, k)                # gürültü konturu bozmasın
hsv  = BGR2HSV(kare)

# KIRMIZI İKİ ARALIK — hue 0/180'de sarmalanıyor, tek aralık yetmez
maske_k = inRange(hsv, [  0,100,100], [ 10,255,255]) \
        | inRange(hsv, [160,100,100], [180,255,255])
maske_m = inRange(hsv, [100,150, 50], [140,255,255])

konturlar = findContours(maske, RETR_EXTERNAL)
```

Her kontur **iki** süzgeçten geçiyor:

**(a) Alan — mutlak değil, ORANLI**

```python
eşik = max(min_alan_px, min_alan_frac × kare_alanı)
```

Sabit piksel sayısı yanlış olurdu: aynı hedef 5 m'de 40 m'dekinin 64 katı
piksel kaplıyor.

**(b) Dairesellik — ayrımı yapan tek ölçüt**

```python
(x, y), r    = minEnclosingCircle(kontur)
dairesellik  = kontur_alanı / (π · r²)
if dairesellik < 0.75: ele
```

Kusursuz daire 1,0; **kare 0,64**. Ölçüldü: gerçek hedef **0,985**,
bayrak **0,281**, poster **0,130**. Kırmızı bir bayrağı ya da posteri
eleyen şey renk değil, **şekil**.

⚠️ Renk yolu kareyi **1/2'ye küçültüp** işliyor (9 ms). Kritik incelik:
`radius_px` **tam çözünürlük pikselinde** olmak zorunda — aşağıda odak
uzaklığıyla metreye çevriliyor ve `fx` tam kare için hesaplanmış.
Küçültülmüş karede bulunan yarıçap geri büyütülmezse bölgenin metrik
yarıçapı **sessizce yarı** çıkardı.

| pozlama | renk bulma |
|---|---|
| Sabit 1/250 (doymuş) | %0 her irtifada |
| `sport` (doymamış) | 5-10 m **%20**, 10-15 m **%30** |

Pozlama düzeltmesi renk tespitini de kurtardı. Ama **eşikler yeniden
kalibre edilmeli** — magenta tonda yapılmışlardı, renk dengesi değişti.

⚠️ `min_zone_area_frac` **kare alanına oranlıdır.** 40 m'de 1 m'lik daire
karenin sadece **%0,057**'sidir; köprünün gönderdiği %5'lik eşik her şeyi
eler. Doğru değer 0,0005 mertebesinde.

---

## 8. Kayıt ve yayın mimarisi

```
rpicam-vid --codec mjpeg -o -
      |
      +--> diske ham JPEG akışı (.mjpeg + .idx)     <- KAYIT, tam boy
      +--> /akis                (parametresiz)      <- ROS, tam boy
      +--> /akis?kucult=1       (PIL ile küçültme)  <- yalnız TARAYICI
```

**Tek çıkış, üç tüketici.** Kayıt ve ROS her zaman tam boyu alır; küçültme
yalnızca tarayıcının istediği uçta olur.

`.idx` her karenin **epoch zamanını, bayt konumunu ve uzunluğunu** tutar —
irtifa eşleştirmesi ve rastgele kare erişimi bununla yapılıyor. **Silme.**

### 7.1 CPU — önizleme pahalı, kayıt ucuz

4 çekirdek. 30 fps'te ölçüldü:

| yayın boyu | kare başına | çekirdek |
|---|---|---|
| 640 px | 33 ms | 0,99 |
| 960 px | 39 ms | 1,17 |
| 1280 px | 70 ms | 2,10 |
| **1920 px** | **115 ms** | **3,46** |

Tarayıcı sekmesi açıkken toplam CPU %90,7, yük 8,11 (4 çekirdekte %203
aşırı yük) ve **mavros %74'te CPU için yarışıyor.**

Sekme kapatılınca: kamera servisi **%83 → %4**, toplam **%67,5**.

> 🔴 **UÇUŞ SIRASINDA TARAYICI SEKMESİNİ KAPAT.** Kayıt sunucu tarafında
> sürer, kesilmez. Önizleme için uçuş kontrolünden çekirdek çalınmaz.
> Başlat/durdur için sekmeyi aç, sonra kapat.

### 7.2 PIL sudo'suz kuruldu

Pi host'unda hiçbir görüntü aracı yoktu (PIL, ffmpeg, ImageMagick,
GStreamer, **pip bile** yok). `apt-get download` + `dpkg -x` ile ev
dizinine açıldı, `ctypes` ile ön yükleniyor — `LD_LIBRARY_PATH`
gerekmiyor. Ayrıntı: `docs/RPI_ESITLEME.md`.

4K→640 px küçültme **33 ms** (DCT alanında `draft()` ile; tam çözüp
küçültmek 116 ms).

---

## 9. Çözümleme araçları

### `deploy/rpi/teshis/kayit_coz.py`

Uçuş kaydını irtifa bandı bandı çözümler.

```bash
# Uçakta (bag ile)
python3 /ws/teshis/kayit_coz.py --kayit /ws/kayit_disi/<ad>.mjpeg \
    --bag '/ws/kayit/<bag>/*.mcap' --ajan 3 --ornek 15

# Laptopta (ROS GEREKMEZ — CSV ile)
python3 deploy/rpi/teshis/kayit_coz.py --kayit ~/yelpence_kayitlar/<ad>.mjpeg \
    --irtifa-csv ~/yelpence_kayitlar/<ad>.irtifa.csv --ornek 15
```

**Üç girdi biçimi kabul eder:** `metadata.yaml`'lı bag dizini, **hâlâ
yazan** bag (parçaları tek tek okur), ya da tek `.mcap`/glob.

> ⚠️ **Bag koşarken `metadata.yaml` YOKTUR** — rosbag2 onu kapanışta
> yazıyor. Bag'i durdurmak uçuş loglamasını keseceği için parçalar tek tek
> okunuyor; mcap kendi kendini tanımlayan bir biçimdir.

> ⚠️ **Tüm bag'i taramak dakikalar sürer** (yüzlerce parça). Kaydın
> ilk/son epoch'una denk gelen parçaları `mtime` ile süz — saniyeye iner.

### Laptopta pip'siz kurulum

```bash
# Wheel bir zip arşividir; pip'in yaptığı iş bizim için gereksiz.
python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall('$HOME/pylib_laptop')" x.whl
PYTHONPATH=$HOME/pylib_laptop python3 ...
```

Doğru wheel etiketi PyPI JSON API'sinden bulunur (`cp312`, `x86_64`,
`musllinux` olmayan).

### `deploy/rpi/teshis/kamera_zincir.sh`

ROS algı zincirini (camera_driver + vision_node + algi_kopru) elle açar.
**Konteynerde koşar**, `$1` = agent_id:

```bash
docker exec drone3 bash /ws/teshis/kamera_zincir.sh 3 basla|dur|durum|qr
```

⚠️ Kayıtla birlikte açılınca CPU **%97**'ye çıkıyor (kayıt fps'i düşmedi
ama pay kalmıyor). Uçuş testinde **kapalı tut** — çözümlemeyi kayıttan yap.

---

## 10. Yanlış giden teşhisler — tekrarlanmasın

Bu bölüm bilerek duruyor. Her biri zaman kaybettirdi.

| yanlış teşhis | gerçek | nasıl anlaşıldı |
|---|---|---|
| "Kablo yanlış, 22↔15 adaptör lazım" | Flex **ters takılıydı** | Operatör baktı |
| "IR-cut filtresi dışarıda" | İçerideydi, çalışıyordu | **Kumanda testi** |
| "Odak bozuk, tek sorun bu" | Odak yeterliydi (Laplacian 89) | Doymamış bölgede ölçüm |
| "Basılı QR geçersiz" | Geçerliydi, okundu | Operatörün pankart fotoğrafı |
| "30 fps jöleyi 3 kat azaltır" | **Hiç azaltmadı** (VBLANK) | Operatör gözlemi |
| "QR A4'te, 8 m'den yukarı okunmaz" | Hedef 1,5 m'lik pankarttı | İrtifa + piksel ölçümü |

**Ortak ders:** ölçümü *yorumlamadan* önce, ölçtüğün şeyin gerçekten o
olduğunu doğrula. Kare ortalamasından IR, kırpılmış kareden odak,
kare hızından okuma süresi çıkarılamaz.

---

## 11. Açık işler

- 🟠 **Yalıtımı derinleştir.** QR büyütülemediği için tavanı açacak tek eksen bu; boyut tarafında 23 m'lik kullanılmayan pay var.
- 🟠 **Renk eşiklerini yeni renk dengesinde kalibre et.**
- 🟠 **Konteynerdeki `swarm_perception` eski derleme** —
  `min_zone_area_frac` parametresi yok, canlı eşik ayarı çalışmıyor.
- 🟡 Beyaz dengesini farklı ışıkta (akşam/kapalı) yeniden ölç.
- 🟡 1332x990 kipini dene — okuma süresi üçte bire iner, px/modül
  3,3'e düşer. Alçak irtifa için bir seçenek olabilir.
- 🟡 Renk hedefini kadraja alan bir uçuş — renk irtifa eğrisi henüz yok.
