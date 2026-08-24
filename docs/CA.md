# CA — Çarpışma Önleme: dikey yol verme

**Son güncelleme:** 25 Ağustos 2026, 02:25 — 🎯 hist_m + tatmin GECE UÇUŞUNDA DOĞRULANDI (§7.2)

> Bu belge çarpışma önlemenin **bugünkü tasarımı ve durumu**. 23 Ağustos
> sabahki sürümü yatay/dikey karşılaştırmasıydı; karar verildi ve uygulandı,
> belge ona göre yeniden yazıldı.
>
> Sayıların hepsi ya **koddan okunarak** ya **benzetimle** ya da **sahada
> ölçülerek** çıkarıldı. Varsayım olanlar 🔴 ile işaretli.

---

## 0. Otuz saniyede

- 🎯 **İLK UÇUŞTA ÇALIŞTI** (23 Ağustos akşamı). İki kaçış çevrimi, ikisi de
  temiz: +3,1 m ve +2,8 m tırmanma, nominale dönüş, **yatay itme hiç
  açılmadı**. Ayrıntı ve sayılar: **§6.5**.
- 🔴 Uçuştan çıkan iki bulgu: **itki payı ince** (askı %72, geçişlerde
  %100'e doyuyor) ve **dönüş fazla aceleci** (§7).
- **Birincil kaçış DİKEY.** Çatışan uçaklardan kimliği büyük olan, küçüğün
  **ölçülen** irtifasından `katman` kadar uzağa gider.
- **Yatay itme SON ÇARE** — yalnız sert kabuğun (`hard`) içinde açılır.
  Normal çatışmada formasyon geometrisine hiç dokunulmaz.
- Rütbe **kadrodan** gelir (`SURU_KADRO`), anlık çatışma kümesinden değil.
  Merdiven **dönüşümlü**: +katman, −katman, +2×katman…
- Beş yer testi geçti (§6), **birim test 81/81**.
- 🔴 Depo uçaklardan İLERİDE — §7 son madde.

```
d0 = 4.0 m    catisma yaricapi (YATAY mesafe, cikis 4.5 m)
hard = 2.5 m  yatay son carenin acildigi kabuk
katman = 3.0 m  ardisik rutbeler arasi dikey ayrim
v_dikey = 1.2 m/s (= PX4 MPC_Z_VEL_MAX_UP)  a = 2.0  kp = 2.0
```

---

## 1. Kural

Her uçak 20 Hz'de şunu hesaplar:

```
1. CATISMA KUMESI
   d_yatay(j) < d0  olan komsular.  (3B DEGIL — gerekce TUZAKLAR §3.12)
   Histerezis: giris d0, cikis d0 + 0.5 m

2. YOL VERECEK MIYIM
   Yalnizca BENDEN KUCUK kimlikli catisan komsuya yol veririm.
   Yoksa CAPAYIM: dikeye hic dokunmam, gorev ne diyorsa o.

3. ZATEN AYRIK MIYIM
   Hepsinden |rel_z| >= katman ise yapacak bir sey YOK.
   (Iki komsunun ARASINDA olup ikisinden de uzak olmak da gecerli.)

4. NEREYE
   hedef = referansin OLCULEN irtifasi + rutbe ofseti
   rutbe 0 -> +0     (capa)
   rutbe 1 -> +katman
   rutbe 2 -> -katman
   rutbe 3 -> +2*katman ...
   Yon YAPISKAN: catisma boyunca degismez.

5. NASIL
   vz = gorev_vz - kp * (hedef - simdi)     NED: yukari = NEGATIF
   hiz ve ivme tavanlariyla kirpilir
```

**Dönüş:** çatışma bittikten (4,5 m yatay) **2 sn** sonra, 0,5 m/s ile
nominale iniş, 0,3 m toleransta bırakma. Toplam ~8 sn.
**Körlükte dönülmez** — §4.

### Neden rütbe kadrodan, komşunun kararından değil

İki uçağın birbirinin *çatışma listesini* tahmin etmesi gerekseydi listeler
tutmazdı. Kusursuz mesh'le bile, 4 m aralıkta çizgi formasyonu:

```
drone1 gorur {2}    -> siralamada 1. -> +0
drone2 gorur {1,3}  -> siralamada 2. -> +1 katman
drone3 gorur {2}    -> siralamada 2. -> +1 katman    <-- 2 ve 3 AYNI KATMANDA
```

Kimse paket kaybetmedi; sorun "çatışma" ikili bir ilişki ama rütbe sıralı bir
liste. **Sabit rütbe** bu sorunu kaldırıyor.

### Neden dönüşümlü merdiven

İlk tasarım "benden küçüklerin en yükseğinin `katman` üstüne çık" diyordu.
Benzetimde çöktü:

```
t=1.45 s -> drone2 13.16 m, drone3 13.16 m, DIKEY AYRIM 0.00 m
```

Bir **yarış**: t=0'da ikisi de yalnız drone1'i görüyor, ikisi de aynı hedefi
hesaplıyor ve aynı hızla oraya tırmanıyor. Kaskad sıralı ama uçaklar eş
zamanlı. Dönüşümlü merdivende hedefler baştan farklı olduğu için uçaklar ilk
andan itibaren **birbirinden ayrılıyor** — ve üç uçakta en büyük sapma
6 m yerine **3 m**.

### Neden yatay tamamen kapalı değil

Benzetim (bir uçak asılı, diğeri üzerine sürülüyor — 22 Ağustos saha
testinin birebir karşılığı), en yakın 3B mesafe:

```
yaklasma    SAF DIKEY   SAF YATAY   DIKEY + SON CARE
 1.0 m/s      2.63 m      2.27 m        2.79 m
 2.5 m/s      1.01 m      2.02 m        2.06 m
 4.0 m/s      0.47 m      1.53 m        1.20 m
```

Dikey yetkiyi gerçekçi olmayan değerlere çıkarmak bile kapatmıyor
(v=5 a=5 → 1,83 m). **Sebep ayar değil geometri:** dikey kaçışın
kazanabileceği en fazla mesafe `katman` kadardır ve onu kurmak 2-3 saniye
alır. Yatay itmenin böyle bir tavanı yok.

Karar: normal çatışmada saf dikey, sert kabukta yatay da açılır.

---

## 2. Görevdeki asıl kullanım — formasyon yakın geçişi

Kafa kafaya karşılaşma görevde nadir (operatör, 23 Ağustos). Asıl yük
formasyon geçişlerinde. Benzetim:

```
yanal aralik  bagil hiz   en yakin 3B   kazanilan dikey   YATAY KAYMA
     3.0 m      3.0 m/s      3.09 m         0.75 m          0.00 m
     3.5 m      3.0 m/s      3.54 m         0.51 m          0.00 m
     2.0 m      3.0 m/s      2.61 m         0.75 m          0.92 m
```

Yatay kayma **sıfır** — formasyon geometrisi bozulmuyor, ayrım yalnız
dikeyden geliyor. Tasarımın hedeflediği davranış tam olarak bu.

---

## 3. Aralık ve şartname

Şartname ajanlar arası mesafeyi **hakemlere** bırakıyor; değer çalışma
anında QR/`FormationCommand` ile geliyor (§5.1: *"Ajanlar arası X (Örn: 5m)"*,
QR örneğinde 6 m). Operatör hakemlerden **3-10 m** aralığını duymuş.

**`d0` = 4,0 SABİT** (operatör kararı). Aralığa bağlanmadı. Aralık `d0`'ın
altına inerse kaçınma normal formasyonda sürekli tetikli olur ve **merdiven
kalıcı hâle gelir** — davranış doğru ama bilinmeli, o yüzden
`_on_formation_command` uyarı logluyor ve `SystemEvent` yayıyor.

---

## 4. Körlükte ayrım bırakılmaz

"Çatışma bitti" kararı komşunun uzakta olmasına dayanıyor. **Komşuyu
kaybetmek de aynı görünüyordu:** bayat veri listeden düşer, çatışma false
olur ve uçak 2 saniye sonra kazandığı ayrımı geri verir — hem de komşusunun
nerede olduğunu bilmediği anda. 21 Ağustos'ta mesh **46,4 saniye** tek yönlü
ölmüştü (`TUZAKLAR` §2.15).

Artık: körlük bayrağı kalkmışken **irtifa tutulur**, dönüş sayacı ilerlemez,
`donus_kor` sayacı artar ve uyarı basılır. Komşu tekrar görülünce normal
akış sürer. Mesh kalıcı koparsa uçak katmanında kalır — güvenli taraf.

---

## 5. Mesh gerçeği — 23 Ağustos'ta ölçüldü

Kaçınmanın gördüğü dünyanın tazeliği. Eskiden "%30 kayıp" varsayılıyordu;
ölçüldü ve **kaynağı radyo değil kendi köprümüz** çıktı (`TUZAKLAR` §2.20).

| | önce | sonra |
|---|---|---|
| komşu tazeleme | 7,1 Hz | **10,5 Hz** |
| en büyük boşluk | 0,41 s | **0,31 s** |
| gerçek havadan kayıp | — | **%1-5** |

Benzetim artık bu sayılarla besleniyor (10 Hz, %5). Tohum taramasında sapma
0,05 m'nin altında — **mesh kalitesi CA sonucunu neredeyse hiç
değiştirmiyor**, sorun bilgi değil manevra.

---

## 6. Yer testleri — hepsi geçti (23 Ağustos)

Gerçek mesh verisiyle, gerçek uçaklarda, **uçuş yoluna dokunmadan** (gözlem
modu: ikinci bir CA örneği, girdi/çıktı `/g0…`'a yönlendirilmiş).

| test | ne doğruladı | sonuç |
|---|---|---|
| **G0-1** datum | `rel_z` iki uçaktan zıt işaretli, 3 cm farkla (−0,428 / +0,397) | ✅ |
| **G0-2** rütbe + işaret | çapa 0,000 · rütbe 1 → −1,184 (tavanda doyuyor) | ✅ |
| **G0-3** yatay son çare | 0,6 m arayla açıldı, **zıt yönlerde** (+3,74 / −3,65) | ✅ |
| **G0-4** geçirgenlik | çatışma yokken çıktı girdiyle **birebir**, damga değişmemiş | ✅ |
| **G0-5** körlükte tutma | `donus_kor=1`, uyarı çıktı, ayrım bırakılmadı | ✅ |

Araçlar: `deploy/rpi/teshis/g0_dikey_datum.py` ·
`g0_dikey_gozlem.sh` · `g0_korluk_tutma.sh`

Ek doğrulamalar: uçan düğüm yerde tamamen sessiz (`passthrough=0 avoid=0`) ·
`/control/setpoint` **tek yayıncı** · test kancaları temiz.

**Birim test: 78/78** (`test_ca_dikey.py` 26 + mevcutlar).

---

## 6.5 🎯 İLK UÇUŞ — 23 Ağustos 2026 akşamı

**Düzen:** ylp02 (rütbe 1) guided'da 4,8 m'de asılı · ylp00 (rütbe 0, çapa)
operatör kumandasında ~4,9 m'de, yandan yaklaştı. `--senaryo asili`,
90 sn, tek uçak otonom.

### Ölçülen — tasarımla yan yana

| ölçüt | tasarım | **uçuşta ölçülen** |
|---|---|---|
| kaçış yönü | saf dikey | **vx = vy = 0,00 baştan sona** ✅ |
| tırmanma tepe hızı | 1,2 m/s (PX4 tavanı) | **1,25 m/s, tavanda doygun** ✅ |
| merdiven yüksekliği | 3,0 m | **+3,1 m** ve **+2,8 m** ✅ |
| dönüş hızı | 0,5 m/s | **0,50 m/s** ✅ |
| nominale dönüş | 4,8 m | **4,79 m (iki kez)** ✅ |
| yatay son çare | açılmamalı | **hiç açılmadı** ✅ |
| alarmlar | temiz | `dikey_yetersiz=0 donus_kor=0 korluk=0` ✅ |
| en yakın yatay mesafe | — | **3,20 m** |

`avoid = 563` tik (20 Hz → ~28 sn etkin).

### Zaman çizelgesi (kayıttan)

```
t=11.9s  d_xy 4.60          ben_h 4.75   disarida
t=13.6s  d_xy 3.67 ICERIDE  ben_h 4.96   girdi, tirmanma basladi
t=18.7s  d_xy 3.25 ICERIDE  ben_h 7.70   ayrim kuruldu
t=22.1s  d_xy 3.29 ICERIDE  ben_h 7.50   ICERIDEYKEN IRTIFASINI TUTTU
t=23.8s  d_xy 4.91          ben_h 6.98   komsu CIKTI -> donus
t=30.6s  d_xy 5.02          ben_h 4.79   nominale dondu
         ... ayni dongu bir kez daha, birebir ...
4.5 m sinirindan gecis sayisi: 4  (iki tam giris-cikis)
```

### 🔴 "Yo-yo" — operatör gözlemi ve ölçümün söylediği

Operatör uçuşta yo-yo gördü: *"02 sürekli kendini aşağı bırakıyor ama 00
risk alanında durduğu için tekrar yukarı atıyor."*

**İlk teşhis YANLIŞTI.** "CA ayrım sağlanınca yetkiyi bırakıyor, görev geri
çekiyor" diye açıklandı; iki ayrı benzetimle **çürütüldü** (genlik 0,00 ve
0,05 m — yo-yo üretilemedi).

**Ölçümün söylediği:** ylp00 içerideyken ylp02 **irtifasını tuttu**
(t=18,7-22,1 arası 7,70 → 7,50 m). İnişler yalnız `d_xy` 4,5 m'yi
**aştıktan sonra** başladı. Sınırdan **tam 4 geçiş** var: iki tam
kaçış-dönüş çevrimi.

Yani sistem doğru davrandı. Yo-yo gerçek ama **operatör kaynaklı**:
"bölgedeyim" ile "çıktım" arasındaki fark **1,2 m** (3,3 ↔ 4,5 m) ve bir
uçağı uçururken diğerini gözle takip ederken bu ayırt edilemiyor.

> **Ders:** tetik sınırı pilotun gözle kestirebileceğinden dar. Çıkış
> histerezisi (`hist_m`) bunu doğrudan etkiliyor — §7.


## 7. 🔴 Açık — sıradaki uçuş öncesi

### 1. 🔴 İTKİ PAYI İNCE — ölçüldü, kapandı ama sonucu iyi değil

Uçuş kaydından (`vfr_hud.throttle`, 763 örnek, 80 sn):

```
aski gazi ortanca : %72        (TUZAKLAR §0.3 "%66" diyordu — GUNCELLENDI)
p90               : %77
gaz >= %100       : 24 ornek · toplam ~2.5 sn
gaz >= %95        : ~3.8 sn
en uzun KESINTISIZ >=%90 blok : 0.7 sn
```

Tek sıçrama değil: kaçış geçişlerinde doyum **tekrarlanıyor**. Blokların
hiçbiri 0,7 sn'yi geçmediği için uçak düşmez, ama o anlarda **rezerv yok**.

**Sonucu:** `MPC_Z_VEL_MAX_UP` 1,2 → 3,0 fikri **KAPANDI, yapılamaz.**
1,2 m/s tırmanmak zaten payı tüketiyor. (Bu, yanal kaymayı 4,8 → 1,9 m
indirecek tek koldu; artık yok.)

### 2. 🟠 DÖNÜŞ FAZLA ACELECİ — sıradaki iyileştirme

Çıkış eşiği `d0 + hist_m = 4,5 m`, ardından 2 sn bekleyip 0,5 m/s ile
iniyor. Komşu hâlâ 5 m'de dururken 3 m'lik ayrımı 6 saniyede geri vermek
savurgan — ve operatörün gördüğü "yo-yo" görüntüsü tam bundan doğuyor
(§6.5).

✅✅ **UÇUŞTA DOĞRULANDI (25 Ağustos 02:03 gece uçuşu).** ylp02 4,8 m
asılı, operatör ylp00'ı kumandayla üç kez yaklaştırıp uzaklaştırdı.
Kayıttan (mcap, rel_alt + mesh pos):

```
inis baslarken d_xy : 7,19 / 8,25 / 7,46 m   (hedef >= 6,5 — dun 4,9'du)
icerideyken dalis   : YOK (inis yalniz operator uzaklasinca basladi)
donus hizi          : 0,50 / 0,51 / 0,51 m/s (tasarim 0,5)
tirmanma tepe hizi  : 1,27-1,32 m/s          (dunle ayni)
en yakin yaklasma   : 3,52 m
```

Operatör gözlemi: "yaklaşınca yukarı kalktı, uzaklaşınca yerine döndü,
gayet stabildi." **Yo-yo görüntüsü kapandı.** Not: tırmanmalar +4,6 m
ölçüldü (dün +3,1) — hata değil: operatör bu kez daha yüksekte uçtu,
hedef "komşunun ölçülen irtifası + katman" olduğu için merdiven onu
izledi (tepe 9,1 m AGL).

✅ **YAPILDI (24 Ağustos 14:30): `hist_m` 0,5 → 2,5, çıkış 6,5 m.**
Zincir kuruldu: `ucus_ayarlari.py` (`KACINMA_HIST_M`) → `--kabuk` env →
`baslat.sh -p hist_m` → düğüm — önceden zincir HİÇ yoktu, düğüm gömülü
0,5 ile koşuyordu. 2,5 seçildi, 3,0 değil: çıkış eşiği formasyonun
planlı en yakın yaklaşmasına (8,49 m) 1,99 m pay bırakmalı (3,0 → 1,49);
denetime "çıkış ≥ kritik yaklaşma = HATA" koşulu eklendi. Birim 82/82
(geniş-histerezis regresyonu eklendi). Uçuş doğrulaması akşam.

⚠️ Bedeli: çatışma daha uzun sürer, merdiven daha uzun kalır. Sıkı
formasyonda (aralık ≤ 7 m) kalıcı merdivene yaklaşır — `d0` ile birlikte
düşünülmeli.

### 3. 🔴 DEPO UÇAKLARDAN İLERİDE — sonraki kişi buna dikkat

Uçuştan **sonra** `ca_core`'a bir değişiklik yapıldı ve **dağıtılmadı**:

```
ucaklarda : 1d1048e
depoda    : cbf948c + commit'siz ca_core degisikligi
```

Değişiklik: ayrım sağlandığında (`tatmin`) CA artık dikey yetkiyi
bırakmıyor, görevin dikey **hızını** geçirip yetkide kalıyor.

⚠️ **Bu değişiklik uçuşta görülen yo-yo'yu DÜZELTMİYOR** (§6.5 — o
operatör kaynaklıydı). Ayrı ve daha nadir bir durumu sertleştiriyor:
uçuşta bir kez, `rel_z = 3,06` olduğunda o yol tetiklendi. Testleriyle
duruyor (3 yeni regresyon testi) ama sahada **doğrulanmadı**.

✅ **KARAR (24 Ağustos, operatör): `hist_m` ile BİRLİKTE dağıtılacak.**
"Daha nadir durum" `hist_m` genişleyince nadir olmaktan çıkıyor: uçak
"ayrım kurulu + çatışma sürüyor" hâlinde artık komşu 4,0-6,5 m bandında
olduğu sürece kalıyor ve eski kod tam o hâlde yetkiyi bırakıp -1,48 m/s
dalışa izin veriyordu. Yalnız `hist_m` dağıtmak o imzayı sıklaştırırdı.
İki değişiklik logda ayrık gözlenir: çıkış mesafesi ↔ içerideyken dalış.

### 4. Kalanlar

| # | konu | not |
|---|---|---|
| a | ylp01 dönünce `SURU_KADRO="1 2 3"` | yanlış kadro kaçış **yönünü ters çevirir** (KARAR-04) |
| b | Üç uçağın aynı noktadan geçtiği çapraz slot değişimi | hiçbir ayar eşiği tutturmuyor (1,76 m); `formation_node` o geometriyi üretmemeli |
| c | ✅ Kuru test kaçış zarfını **ÇİZİYOR** (24 Ağu 14:50) | sarı kesikli daire (`KACINMA_ZARF_YANAL_M`=5 m) + iniş 5+5 m dış halka; dikey +3 m lejantta |
| d | PX4'ün kendi titreşim/clipping sayacı okunamıyor | `vibration` konusu akmıyor; ölçüt olarak konum sıçraması kullanıldı |

---

## 8. Bilinen algoritma zayıflıkları

| | ne | durum |
|---|---|---|
| B1 | Asılıyken teğet sıfır | ⚪ konu dışı — `k_tan=0`, teğet kapalı |
| B2 | `xy_guard` altı komşu tamamen atlanıyordu | ✅ **kapatıldı** — artık yalnız yön vektörünü koruyor |
| B3 | Uzaklaşan komşuya çekim | ✅ 22 Ağu'da düzeltildi (kabuk içinde geçerli) |
| B4 | Yavaş yaklaşmada koruma `hard`'da başlıyor | açık — dikey kip bunu telafi ediyor |
| B5 | `hard` eşiğinde süreksizlik | ✅ 22 Ağu'da düzeltildi |
| B6 | Merdiven kurulma süresi (3,1 sn) kafa kafaya kapanmadan (0,7 sn) uzun | bilinen, `ucus_ayarlari.py` uyarıyor |

---

## 9. Nerede ne var

| | |
|---|---|
| Çekirdek | `src/swarm_core/swarm_core/collision_avoidance/ca_core.py` |
| Düğüm | `collision_avoidance_node.py` |
| Komşu adaptörü | `komsu_adaptoru.py` (dikey datum düzeltmesi burada) |
| **Benzetim** | `src/gcs/ca_benzetim.py` — gerçek `ca_core`'u koşturur |
| Parametre kaynağı | `src/gcs/ucus_ayarlari.py` (PX4 tavan denetimleri dahil) |
| Başlatma | `deploy/rpi/baslat.sh` — rütbe `SURU_KADRO`'dan |
| Yer testleri | `deploy/rpi/teshis/g0_*.sh|py` |
| Birim testler | `src/swarm_core/test/test_ca_dikey.py` |
| Yedek düğüm | `swarm_control/.../basit_kacinma_node.py` (kapalı, silinmedi) |
| Tuzaklar | `TUZAKLAR` §2.20 §2.21 §2.22 §3.12 §1.23 §1.24 |
