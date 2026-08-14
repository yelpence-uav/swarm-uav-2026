# Kanıt uçuşu videosu — görev planı ve hazırlık durumu

> ## ⚠️ ARŞİV — GÜNCEL DEĞİL, buraya yazma
>
> **Kanıt videosu koreografi planı.** Tarihsel kayıt; **bugünün durumunu anlatmaz.**
>
> **Güncel durum:** [`DURUM.md`](DURUM.md) ·
> **Güncel plan:** [`PLAN.md`](PLAN.md) ·
> **Güncel iş listesi:** [`YAPILACAKLAR.md`](YAPILACAKLAR.md)
>
> Hâlâ değerli olan: Video çekildi ve GEÇİLDİ. Buradan bir bilgi kullanacaksan
> **önce koda bakıp doğrula** — o gün doğru olan bugün yanlış olabilir.
> Çelişki varsa **canlı belge kazanır**.


**2 Ağustos 2026.** Operatörün tarif ettiği koreografi, mevcut kodun ne kadarını
karşıladığı, neyin değişmesi gerektiği ve uçuştan önce kapatılması gereken
engeller.

---

## 1. İstenen koreografi (operatörün tarifi)

1. İki drone **rastgele noktalarda** duruyor
2. İkisi de kalkıyor
3. Operatör **lideri seçiyor** ("bu lider" diye önceden söylenecek)
4. Lider olmayan drone, liderin yanına **seçilen formasyonda** geliyor
5. Formasyonu bozmadan **bir noktaya** gidiyorlar
   — nokta, bulundukları yerden **mesafe + yön** olarak veriliyor
6. O noktada **roll** yapıyorlar
7. Roll'u **koruyarak** başka bir noktaya gidiyorlar
8. Orada roll'u **düzeltip irtifa artırıyorlar**
9. **Formasyon değiştirip** kalktıkları yere dönüyorlar

---

## 2. Mevcut kod bunun ne kadarını yapıyor

`--senaryo kanit` (`src/gcs/gorev_kanit_ucus.py`, `plan_kur()`) **12 adımlık**
koreografiyi zaten kuruyor:

```
 1) kalkış → ok başı dizilişi   (yeniden_ata=True: uçaklar EN YAKIN slota gider)
 2) P1'e git
 3) P1'de ROLL 30°
 4) P2 yönüne dön, roll KORUNARAK
 5) roll'lu halde P2'ye git
 6) P2'de roll düzelt
 7) P2'de FORMASYON DEĞİŞİMİ (ok başı → çizgi), slot yeniden atanır
 8) P3 yönüne dön
 9) P3'e git
10) P3'te İRTİFA 12 → 18 m
11) eve yönel
12) kalkış noktasına dön
```

Yani **6, 7, 8, 9 numaralı istekler zaten var.**

### Hazır olan parçalar

| Parça | Nerede | Not |
|---|---|---|
| Rastgele başlangıç → en yakın slot | `hedefler_uret(..., yeniden_ata=True)` | Uçaklar kesişmez |
| Formasyonlar | `formasyon_ofsetleri()` | `okbasi`, `cizgi`, `kolon` |
| Roll | `egim_dz(ofsetler, pitch, roll)` | Formasyon düzlemi eğilir |
| Roll'u koruyarak hareket | `plan_kur` adım 4-5 | Roll parametresi adımlar arası taşınıyor |
| Formasyon değişimi | `plan_kur` adım 7 | Slot yeniden ataması ŞART (yoksa kafa kafaya) |
| İrtifa değişimi | `plan_kur` adım 10 | |
| Çarpışma kanıtı | `plan_dogrula()` | Her adım + her geçiş, üç senaryo (eş zamanlı / A donmuş / B donmuş) |

### Roll'un irtifa etkisi — planlarken unutma

30° roll'da kanatlar merkezden `dz = 0.408 × ARALIK_M` ayrışıyor.
10 m aralıkta **±4.1 m**. `GOREV_IRTIFA_M = 12` bu yüzden seçildi: 10 m'de
alttaki uçak 5.9 m'ye inerdi. 12 m'de yayılım **7.9 – 16.1 m** arasında kalıyor.

---

## 3. Değişmesi gereken üç şey

Üçü de küçük — yeni mekanizma değil, mevcut yapının parametrelenmesi.

| İstenen | Şu anki durum | Yapılacak |
|---|---|---|
| **Lideri operatör seçecek** | Slot ataması "en yakına göre" (`yeniden_ata`) | `plan_kur`'a lider parametresi; lider slot 0'a sabitlenir, diğerleri en yakına |
| **İrtifa artışı İKİNCİ noktada** | Üçüncü noktada (P3, adım 10) | Adım sırası: roll düzeltme + irtifa artışı P2'de birleştirilir |
| **Noktalar "şu yöne şu kadar"** | Sabit üçgen (`KENAR_M`, `ROTA_YONU_DEG`) | Nokta listesi CLI'dan: her nokta (mesafe, yön) çifti olarak |

---

## 4. Uçuştan önce kapatılması gereken engeller

**Bunlar koddan daha kritik.** Sıralama önem sırasına göre.

### 4.1. ylp00 ağ dışı ve bu gecenin HİÇBİR kodu onda yok — ENGELLEYİCİ

2 Ağustos gecesi yapılan bütün düzeltmeler **yalnız ylp01'de**:

- yerel yörünge yürütücüsü (`_yurutucu_ilerlet`) + ivme sınırlı rampa
- origin doğrulaması (`_origin_dogrula`) + mesh'te gerçek `origin_synced`
- irtifa ofsetinin tırmanış OTURDUKTAN sonra ölçülmesi
- `MPC_LAND_SPEED` 0.4

İki dronlu uçuşta ikisi **aynı kodda ve aynı parametrelerde** olmalı. Aksi
halde biri yürütücülü, öteki yürütücüsüz uçar — aynı komuta farklı tepki
verirler ve formasyon sessizce ayrışır.

`dagit.sh ylp00` denendi: `No route to host`. Telemetride `bagli=False`,
`GPS fix=0`, `pil %0`.

### 4.2. `kanit` senaryosu HİÇ UÇMADI

2 Ağustos gecesinin sekiz uçuşunun **hepsi tek drone** (`--senaryo tekli`).
Son iki dronlu uçuş 1 Ağustos'taki `lider` senaryosuydu ve o gece **çerçeve
ayrışması yüzünden kaçış** yaşandı (bkz. `31temmuz-1agustos.md`).

12 adımlık koreografi ilk kez uçacaksa, arada bir **prova** olmalı:
roll'suz, kısa mesafeli, azaltılmış kapsam.

### 4.3. ylp00'ın sağlığı doğrulanmadı

- **Kalibrasyon sonrası** "high accelerometer bias" ve "vertical velocity
  unstable" uyarıları verdi — **temizlendiği doğrulanmadı**
- **Aralıklı titreşim** çözülmedi (1 Ağustos'ta ivmeölçer clipping ölçüldü)
- **Hover gazı %66** — itki payı yok

Roll manevrası ve 18 m irtifa itki payı isteyen şeyler. Uçuştan önce
`titresim_olc.py` koşulmalı ve clipping sıfır görülmeli.

### 4.4. Çarpışma önleme asimetrik

- ylp00: `/ws/kacinma` VAR, `basit_kacinma` düğümü koşuyor
- ylp01: dosya YOK, düğüm koşmuyor

İki dronlu uçuşa girmeden **eşitlenmeli** — ya ikisinde açık ya ikisinde
kapalı. Aksi halde çarpışma anında biri kenara çekilir, öteki düz gider ve
manevranın yarısı eksik kalır.

Açılacaksa şu sayı bilinerek açılmalı: kaçınma komşu konumlarına dayanıyor ve
o veri mesh'ten **7.24 Hz, en büyük boşluk 203 ms** geliyor (ölçüldü). İki
uçak 4 m/s ile yaklaşıyorsa ~0.8 m kör alan; sert sınır 3.0 m.

### 4.5. Süre ve pil

12 adım + rampalar. `GOREV_ASIM_S = 285` (5 dk sınırı). Yürütücünün ivme
rampaları her geçişi ~1 sn uzattı. ylp00'ın hover gazı %66 olduğu için
dayanma süresi ylp01'den kısa — kritik olan o.

---

## 5. Önerilen sıra

1. **ylp00'ı ağa al** → `dagit.sh ylp00` → konteyner restart
2. **Doğrula**: `origin DOGRULANDI` satırı, yürütücü parametreleri, EKF
   uyarılarının temizlenmesi, `titresim_olc.py` clipping = 0
3. **Kaçınmayı eşitle** (ikisinde de aynı)
4. **Koreografiyi istenen hale getir** (lider seçimi, irtifa sırası, nokta
   parametreleri — bkz. §3)
5. **Kuru koşu**: çarpışma doğrulayıcı 12 adımı ve her geçişi denetler;
   harita üretilir ve gözle engel kontrolü yapılır
6. **Prova uçuşu**: roll'suz, kısa mesafe
7. **Tam görev + video**

---

## 6. Bu gecenin (2 Ağustos) bıraktığı durum

**ylp01'de çalışan ve doğrulanan:**

| | |
|---|---|
| Yörünge üretimi | Drone'da, 50 Hz, ivme sınırlı yamuk profil |
| Hız / ivme | 2.0 m/s yatay, 1.0 m/s dikey; 1.5 / 1.0 m/s² |
| Gecikme telafisi | **KAPALI** (denendi, %7 kazanç / %70 konum sertliği kaybı — bkz. `baslat.sh` notu) |
| Origin | Ölçülerek doğrulanıyor, yerde otomatik yeniden gönderiliyor |
| İrtifa ofseti | Tırmanış oturduktan sonra ölçülüyor (−0.20 m) |
| İniş | `MPC_LAND_SPEED` 0.4 m/s (son 5 m) |
| Ölçülen kalan kusur | Yatay tepe hız komut 2.00 → uçak 2.42 (varışta <1 m kayma) |

**Kalan kusur kanıt videosu için sorun DEĞİL:** video otonomluğu, uçuş modunu
ve RC müdahalesizliğini gösteriyor; hız izlenmiyor. Yarım metrelik kayma
görünmez. Çok dronlu formasyonda mesafe salınımı yaratır ama çarpışma eşiği
(`MIN_AYRIM_M` = 4.0 m) yanında önemsiz.

**Kalan kusurun gerçek çözümü** (ileride): yürüyen noktanın hızını uçağın
GERÇEK hızına bağlamak. Gecikme `hız × iç döngü zaman sabiti` ile ölçekli
(~0.5 m @ 2 m/s) ve ivmeden bağımsız — ölçüldü: ivme 1.5 → 0.8 yapmak aşımı
%25'ten yalnız %21'e indirdi.
