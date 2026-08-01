# 31 Temmuz – 1 Ağustos gecesi — kanıt uçuşu hazırlığı

**Takım:** Yelpence (752825) · ylp00, ylp01, ylp02
**Yazıldığı an:** 1 Ağustos 2026, 04:20

Bu gecenin amacı kanıt uçuşu videosunu çekmekti. Çekilemedi. Ama sürüyü
ayakta tutan üç ayrı sessiz hata ölçümle bulundu ve düzeltildi; birinin
bedeli devrilen bir uçak ve kırılan pervaneler oldu.

Bu belge **ne ölçüldüğünü** yazar. Tahmin ve teşhis ayrımı bilerek korunmuştur:
"ölçüldü" yazan yerde sayı vardır, "muhtemelen" yazan yerde yoktur.

---

## 1. Mesh komutları sessizce düşüyordu — **iki dronlu her uçuşu bozardı**

### 1.1 Belirti

İki drone'a art arda `takeoff` gönderildi. ylp00 kalktı, **ylp01 ARMLI halde
yerde kaldı**. Hiçbir hata dönmedi: backend `200 OK` verdi.

### 1.2 Ölçüm

ylp01'in kendi ESP logu, drone 1'e giden **dört** takeoff paketini duyduğunu,
kendisine gelen **sıfır** paket olduğunu gösterdi. Aynı 0.7 saniyede drone 1'in
paketlerini alıyordu — yani mesh çalışıyordu, paketler ona hiç gönderilmemişti.

### 1.3 Sebep — hız limiti TİP başına, HEDEF başına değil

`firmware/esp32_mesh/common/mesh_shared/mesh_config.h:597`

```c
static uint32_t _son_tip_gonderim_ms[MESH_TIP_TABLO_BOYU] = {};
if (simdi - _son_tip_gonderim_ms[tip] < min_aralik_ms) { _tip_dusen[tip]++; return false; }
```

`RX BASE/src/main.cpp:186-187`

| tip | sınır |
|---|---|
| `TIP_KOMUT` (arm/takeoff/land/rtl) | `JOYSTICK_MIN_ARALIK_MS = 200` |
| `TIP_GOTO` | `MESH_GONDERIM_MIN_MS = 50` |

İki drone aynı yuvayı paylaşıyor. Üstüne, her guided komut güvenilirlik için
**4 kopya** gönderiliyor (`esp32_bridge_node._guided_gonder`, 250 ms arayla).
O fonksiyonun yorumu şöyle diyordu:

> "Base ESP JOYSTICK rate limiti 200ms olduğundan 250ms aralık hepsinin
> geçmesini sağlar."

Bu **tek drone için** doğru, iki drone için yanlış. İki uçağın tekrar dizileri
çakışıyor:

```
drone1 -> 0.00  0.25  0.50  0.75
drone2 -> 0.30  0.55  0.80  1.05      (YKİ 300 ms aralıklı gönderse bile)
kapı   -> geçer geçer DÜŞER geçer DÜŞER geçer DÜŞER ... geçer
```

İkinci uçak 4 çerçeveden 3'ünü kaybediyor; kalan tek şans havada düşerse komut
hiç ulaşmıyor.

### 1.4 Düzeltme — tek kuyruk, sırayla gönderim

`esp32_bridge_node._guided_gonder` artık komut başına ayrı timer açmıyor.
Bütün guided çerçeveler **tek kuyruğa** giriyor, tek bir 20 Hz zamanlayıcı
boşaltıyor, kuyruk **tip başına** en az `_GUIDED_TIP_ARALIK_S` bırakıyor
(TIP_KOMUT 0.30 > firmware 0.200; TIP_GOTO 0.10 > firmware 0.050) ve
gönderdiği kaydı **kuyruğun sonuna** atıyor — uçaklar sırayla gönderiyor.

**Yerde ölçülen sonuç** (iki drone da disarm, `disarm` komutu gönderildi —
tamamen etkisiz ama `TIP_KOMUT` yolunu kullanır):

| | drone 1'e | drone 2'ye | sıra |
|---|---|---|---|
| eski (land, 0x02) | 3/4 | **1/4** | d1 d1 d1 d2 |
| yeni (disarm, 0x80) | **4/4** | **4/4** | d1 d2 d1 d2 d1 d2 d1 d2 |

Firmware kapısını birebir taklit eden simülasyon aynı sonucu verdi (eski 4/4 ve
1/4, yeni 4/4 ve 4/4) — yani log ile model örtüşüyor.

**Neden tek drone uçuşlarında hiç görünmedi:** çakışacak ikinci komut yoktu.

Commit: `33d1e7a`, `61cc1b2`

### 1.5 Ek koruma — kalkış teyide bağlandı

`takeoff` artık bir kez gönderilip umulmuyor. Her uçak için tırmanış teyit
ediliyor, başlamayana komut tekrarlanıyor (3 deneme), yine olmuyorsa **görev
hiç başlamıyor** ve hepsi iniyor. Armlı+OFFBOARD halde yerde beklemek
motorları hover itkisinde tutuyor — motor yaktığımız durumun aynısı.

İlk uçuşta bu düzeltme **tam öngördüğü yerde devreye girdi**: drone 2'nin ilk
takeoff'u düştü, tekrar kurtardı.

---

## 2. Uçuş hızı 4 m/s'ti, sebebi hız tavanı değildi

### 2.1 Ölçüm

Görev logundan, 1 sn aralıklı mesafeler:

```
d1: 8.3 -> 5.1 -> 2.1 m   = 3.2 ve 3.0 m/s
d2: 7.6 -> 4.6 -> 2.0 m   = 3.0 ve 2.6 m/s
```

Uçaktaki parametreler (iki uçakta birebir aynı):

| | değer | | değer |
|---|---|---|---|
| `MPC_XY_VEL_MAX` | 4.0 | `MPC_ACC_HOR` | 2.0 |
| `MPC_XY_CRUISE` | 4.0 | `MPC_ACC_HOR_MAX` | 5.0 |
| `MPC_JERK_AUTO` | 4.0 | `MPC_JERK_MAX` | 8.0 |
| `MPC_TKO_SPEED` | 1.0 | `MPC_TILTMAX_AIR` | 30.0 |

### 2.2 Sebep — komutun veriliş şekli

`git()` hedefi **tek adımda** veriyordu. OFFBOARD'da PX4 konum setpoint'ini
yumuşatmaz; Auto'daki yörünge üreteci (`MPC_JERK_AUTO`, `MPC_ACC_HOR`) o yolda
**devrede değildir**. 8 m ötedeki bir nokta = anında `MPC_XY_VEL_MAX` kadar hız
talebi. Uçak tam yetkiyle atılıyor, varınca aynı sertlikte frenliyor.

### 2.3 Düzeltme — setpoint yürütülüyor

`git_ve_bekle()` setpoint'i `GOREV_HIZ_MPS` (2.0) ile, irtifayı
`GOREV_DIKEY_HIZ_MPS` (1.0) ile yürütüyor. Simülasyonla doğrulandı: tepe hız
tam **2.00 m/s**, aşma yok. Sahada ölçülen: **1.3–1.9 m/s**.

**Taşma freni:** setpoint uçaktan en fazla `TASMA_M` (3 m) önde olabilir.
Olmasaydı rüzgâr/kaçınma yüzünden geride kalan uçağın önünde setpoint kaçar,
sonra uçak onu yakalamak için hızlanırdı. İlk hali "ilerlemeden önce bak"
şeklindeydi ve bir adım geç kalıp sınırı 4.0 m yapıyordu (ölçüldü); şimdi
ilerledikten **sonra** geri çekiyor, sınır tam **3.00 m**.

### 2.4 Uçaktaki parametre bilerek düşürülmedi

`MPC_XY_VEL_MAX` 4.0 kalıyor:

- çarpışma kaçınmasının kaçış payı o tavandan geliyor; görev hızına eşitlersek
  kaçış manevrası da 2 m/s'e iner
- aynı parametre kumandadaki POSCTL'i de sınırlar, pilotun manevra
  kabiliyetini almak güvenliği azaltır

Commit: `774a766`

---

## 3. `rc_link_ok` kumandanın açık olduğunu göstermiyor

Kumandalar **kapalıyken** ölçüldü:

```
rc_link_ok = True
/mavros/rc/in akıyor, rssi sabit 41, kanallar donmuş
```

Alıcı "son değerleri tut" failsafe'inde, dolayısıyla PX4 kumandanın kapandığını
**göremiyor**. Bu bayrak ön koşul olarak kullanılamaz.

Ön kontrol kapısı PX4'ün kendi hükmüne bağlandı: `ready_to_arm`,
`kill_switch_active`, `rc_signal_failsafe_active`, `failsafe_active`. O anki
durumda doğru çalıştı — ylp00 KILL, ikisi de ARM'A HAZIR DEĞİL.

> Not: bu, `docs/28-29-temmuz.md §7.1`'de yazılan "alıcı failsafe'i kill
> switch'i tetikliyor" bulgusuyla aynı kökten. Alıcı failsafe davranışı hâlâ
> düzeltilmedi.

---

## 4. ylp00 kalkışta devrildi — **gecenin en pahalı olayı**

### 4.1 Zaman çizelgesi (1 Ağustos 03:13)

```
03:13:23  arm (4 kopya) — kabul
03:13:28  takeoff #1 -> hedef z=-3.3   çapa=(5.51, 3.32)
03:13:29                               çapa=(5.63, 2.96)
03:13:33  takeoff #2 (görev koşucusunun tekrarı)  çapa=(6.10, 2.81)
03:13:34                               çapa=(6.04, 2.69)
03:13:35  FCU: Kill engaged   (operatör)
03:14:37  görev hâlâ komut gönderiyor — AUTO.LAND
03:15:02  FCU: Kill disengaged
```

**Altı saniye boyunca `z` hiç değişmedi** (hedef hep −3.2/−3.3, yani
`_cached_pos_z` sabit): uçak yerden kesilmedi. Ama yatay çapa 0.9 m kaydı —
yerde kayıyordu.

### 4.2 Aynı uçağın başarılı kalkışlarıyla karşılaştırma

```
00:52 başarılı   çapa (2.53,-10.39) -> (2.54,-10.39)   oynama 0.01 m
02:19 başarılı   çapa (2.22,-13.26) -> (2.23,-13.24)   oynama 0.02 m
02:33 başarılı   çapa (2.27,-13.43) -> (2.27,-13.44)   oynama 0.01 m
03:13 DEVRİLDİ   çapa (5.51,  3.32) -> (6.04,  2.69)   oynama 0.90 m
                 ilk 0.3 saniyede 0.34 m
```

Yerde duran uçak 0.3 sn'de 34 cm gidemez. Bu uçağın hareketi değil, **konum
kestiriminin sıçraması**. Ayrıca ön kontrolde (DISARM) `(5.29, 4.74)` okunmuştu,
kalkış anında çapa `(5.51, 3.32)` — uçak hiç kımıldamadan **1.42 m** kaymış.
Kayma **arm ile kalkış arasında**, yani motorlar döndüğü anda.

### 4.3 Zincir

```
titreşim -> ivmeölçer doyuyor -> EKF konumu sapıyor
   -> OFFBOARD yerde YATAY KONUM tutuyor -> hatayı düzeltmek için EĞİLİYOR
   -> pervane yere vuruyor -> devriliyor
```

Sayıyla: 1.42 m konum hatası, `MPC_XY_P` ile ~1.3 m/s hız talebi,
`MPC_XY_VEL_P_ACC` ile ~2.4 m/s² ivme talebi → **~14° eğim**. Yerde duran,
gazı kalkış itkisinde olan uçakta 14° pervaneyi yere sokar.

### 4.4 Titreşim ölçümü — `src/gcs/titresim_olc.py`

Kalkış yapmadan ölçen araç yazıldı: kumanda STABILIZED (konum tutma yok,
dolayısıyla kaçak döngü oluşamaz), gaz kalkış eşiğinin altında.

| | ylp00 1. ölçüm | ylp00 2. ölçüm | ylp01 |
|---|---|---|---|
| DISARM sıçrama | 0.070 m | 0.052 m | 0.021 m |
| **ARMED sıçrama** | **0.111 m** | **0.017 m** | 0.024 m |
| titreşim z tepe | **33.84 m/s²** | 9.46 m/s² | 9.99 m/s² |
| **yeni clipping** | **+80** | **0** | **0** |
| clipping (kümülatif başlangıç) | 188 | 268 | **0** |

**Clipping = ivmeölçerin doyması.** PX4 dokümanı bunun sıfır olmasını ister;
doyma anında sensör gerçek ivmeyi değil ölçebildiği tavanı bildirir, yani
EKF'e giren veri zaten bozuktur. Titreşim genliği "gürültü" ise clipping
"veri kaybı" — ikisi farklı şey. Operatörün "yarım gazda titreşim normal"
itirazı doğru ama clipping normal değil.

**ylp01 açıldığından beri bir kez bile doymamış (kümülatif 0).** Aynı çerçeve,
aynı motorlar, aynı pervaneler.

**Arıza aralıklı.** İki ylp00 ölçümü arasında operatör pervaneleri kontrol
etti; ikinci ölçüm temiz çıktı. Muhtemelen pervanelerden biri tam oturmamıştı,
ama bu **kanıtlanmadı** — ve iki ölçümdeki gaz seviyesinin aynı olduğu da
doğrulanmadı. Aralıklı arıza sabit arızadan tehlikelidir: uçarken geri gelebilir.

Commit: `a3b36ee`

---

## 5. Kalkışta yatay konum tutma kaldırıldı

Operatörün sorusu: *"offboard'da belli bir irtifaya gelene kadar yatayda
harekete izin vermesek, kalkış sırasında dronu sabitlemeye çalışırken bir şey
olur mu?"*

Cevap: **"sabitlemenin" nasıl yapıldığı belirleyici**, ve o ana kadarki yöntem
tam olarak deviren şeydi.

| | ne yapar | kestirim sıçrarsa |
|---|---|---|
| **konum tutma** (`_MASK_POSITION`) | "şu noktada olmalıyım" | gerçek olmayan hatayı kovalar, **eğilir** |
| **hız sıfırlama** (`_MASK_KALKIS`) | "yatayda durgun olayım" | kovalanacak birikmiş hata yok, eğim küçük |

`_MASK_KALKIS = 2531`, uçtaki `mavros_msgs` ile doğrulandı:

```
konum X/Y  YOK SAY      hız X/Y  KULLAN
konum Z    KULLAN       hız Z    YOK SAY      yaw KULLAN
```

**Kilit ne zaman açılır:** kalkışın başladığı z'den itibaren yükseklik
`kalkis_kilit_irtifa_m` (varsayılan **2.5 m**) olunca. Açılış anında yatay çapa
uçağın o anki yerine **bir kez** yenilenir — kilit boyunca rüzgârla birkaç
santim sürüklenmiş olabilir ve eski çapaya dönmek sıçrama komutu olurdu.
Açıldıktan sonra alçalsa bile geri kilitlenmez.

Durum makinesi kaynaktan çıkarılıp altı senaryoyla test edildi (komut yok /
yerde / 1.0 m / 2.4 m / 2.6 m açılır ve çapa yenilenir / açıldıktan sonra
alçalma).

**Eğimli zeminde:** hız sıfırlama eğimin ürettiği şeye — hıza — doğrudan tepki
verir, konum tutmanın aksine hatanın birikmesini beklemez. Kaybedilen tek şey
uçağın kalkış noktasına geri **dönmemesi**; kilit açılınca görev zaten mutlak
koordinat verdiği için sorun değil.

**Sahada ölçülen sonuç (03:50 uçuşu):**

```
Offboard kalkış hedefi: 5.0m  çapa=(5.15, 4.94)      <- TEK çapa satırı
yatay kilit AÇILDI (2.5 m) — çapa (5.22, 5.06)       <- sürüklenme 0.14 m
```

Commit: `01413dd`

---

## 6. Tekrarlanan takeoff çapayı bozuyordu

`px4_bridge.py:810` her `takeoff` komutunda hedefi ve yatay çapayı **yeniden**
donduruyordu. Guided komutlar 4 kopya gittiği ve görev tırmanmayana komutu
tekrarladığı için tek bir kalkış isteği buraya **6-8 kez** ulaşıyor. Her
gelişinde:

- hedef irtifa o anki z'ye göre yeniden hesaplanıyor
- yatay çapa o anki konuma taşınıyor — **uçak kayarken tutması gereken nokta da
  kayıyor**

Artık çapa bir kez kuruluyor; `land`/`disarm` temizleyene kadar sabit.
Doğrulandı: devrilme sonrası uçuşta günlükte **tek** çapa satırı var (öncekinde 8).

Commit: `622b7b4`

---

## 7. Görev artık kill switch'i, failsafe'i ve devrilmeyi görüyor

Devrilme anında kill switch **uçakta çalıştı** — log kanıtlıyor:
`FCU: Kill engaged` 03:13:35, `Flight termination active` kesintisiz, motorlar
kesildi. Durmayan şey **görev koşucusuydu**: 62 saniye boyunca komut
göndermeye devam etti, hatta 03:14:37'de AUTO.LAND yolladı (PX4 yok saydı).
`kill_switch_active` mesh telemetrisinde zaten geliyordu, kimse bakmıyordu.

`guvenlik_ihlali()` eklendi, her turda denetleniyor:

- **kill switch** — operatör "hemen kes" dedi, beklemek saçma
- **failsafe** — PX4 kontrolü devraldı
- **aşırı eğim** — 35° (`MPC_TILTMAX_AIR` 30 iken normal uçuşta görülmez)

Ayrıca **yerden kesilemeyen uçak erken indiriliyor**: 8 sn'de 1.5 m'ye
çıkamayan uçak için beklemek durumu sadece kötüleştirir.

Tırmanış teyidi 0.8 m tek ölçümden **1.5 m + ardışık iki ölçüme** çıkarıldı:
devrilince EKF dikey kanalı saptı ve irtifa yerde dururken −1.5 ile +1.7 m
arasında gezindi; eski eşik bu gürültüyü "tırmanış" saydı.

Commit: `622b7b4`

---

## 8. `--senaryo lider` — lider yerinde asılı, takipçi yanına

Lider yönü ve konumu **telemetriden okunur**, elle girilmez. Takipçi liderin
burnunun sağına (`yaw + 90°`) `ARALIK_M` mesafeye gider, liderle aynı yöne
döner, bir süre tutar ve **olduğu yere** iner.

> İlk yazımda lider **yerde kalıyordu** — istenen bu değildi. Düzeltildi: lider
> de kalkar, kendi noktasının üstünde asılı durur (yatayda kımıldamaz).

**1 Ağustos 03:50 uçuşu — başarılı, 40 saniye:**

```
arm teyit  d1 3.5s   d2 2.5s
takeoff deneme 1 -> ikisi de tırmanmadı -> tekrar -> tırmanış başladı
irtifa tamam: d1=4.9m  d2=4.7m
formasyon: d1 13.9 m -> 2.0 m   (hız 1.3-1.9 m/s)
lider yerinde: 0.4-1.6 m
iniş: ikisi de
```

Devrilme yok, kayma yok. Lider kalkış noktasından **1.6 m** sapmış olarak
oturdu — kilit boyunca konum düzeltmesi yapılmadığı için beklenen ödünç
(tolerans 2.5 m).

Commit: `867939c`, `6a35628`

---

## 9. Uçuş sonrası bildirilen iki kusur — ikisi de düzeltildi

### 9.1 Aşırı hızlı yön düzeltmesi

İlk yön kademelendirmesi tek drone durumuna göre yazılmıştı:

```python
onceki_heading = yawlar[0] if len(yawlar) == 1 else None
```

İki drone varken `None` oluyor → **ilk adımda hiç dilimleme yok** → uçaklar park
yönünden hedefe tek hamlede dönüyor. Ölçüldü: d1 ~183°'den 238.4°'ye, 55°,
`MC_YAWRATE_MAX` (200 °/s) hızında.

Uçaklar farklı yönlerde park edildiği için tek skaler yetmiyor. Yön artık **her
drone için ayrı** dilimleniyor, adımlar birlikte yürüyor, dilimi önce biten uçak
son yönünde bekliyor. Doğrulandı: 183→238.4 = 2 ara adım, 138→238.4 = 5 ara adım.

### 9.2 İrtifa sıçraması (birden fazla görevde bildirildi)

İki ayrı referans çerçevesi vardı:

```
kalkış (px4_bridge:810)  _target_altitude_ned = _cached_pos_z - altitude  -> ZEMİNE göre
goto   (guided.py:128)   z = -irtifa                                       -> ORIGIN'e göre
```

Zemin origin'in `z=0`'ında değilse ikisi ayrışır. Uçuş logu: zemin `z=+1.6`,
kalkış uçağı zeminden 5 m'ye çıkardı (`z=−3.4`), ilk goto origin'den 5 m istedi
(`z=−5.0`) → uçak kalkışı bitirir bitirmez **1.6 m fırladı**.

Origin'i düzeltmek yerine ofset **ölçülüyor**: kalkış bitince uçağın okuduğu
irtifa ile nominal kalkış irtifası arasındaki fark ofsettir ve plandaki bütün
irtifalara eklenir. Komut edilen irtifa uçağın **zaten olduğu yer** olur,
sıçrayacak bir şey kalmaz. Kendi kendini kalibre eder — `ORIGIN_ALT` yanlış
olsa da çalışır, ki şu anda yanlış (`yki_baslat.sh` → 1218.5).

Ofset bütün uçaklara aynı eklendiği için aralarındaki dikey ayrım ve dolayısıyla
`plan_dogrula` sonucu değişmez.

Commit: `6a35628`

---

## 10. Kapatılmayan konular

- `[!]` **ylp00 titreşimi aralıklı.** İkinci ölçüm temiz çıktı ama sebebi
  bulunmadı. Uçmadan önce her uçuşta `titresim_olc.py` ile bakılmalı; clipping
  artıyorsa uçulmamalı. Fiziksel kontrol sırası: motor yatakları (bu uçakta bir
  motor yandı ve bir köşe 89 PWM fazla çalışıyordu), uçuş kartı montaj köpüğü,
  kol/gövde vidaları.
- `[!]` **ylp00 hover gazı %66.** İtki payı yok. Motor yakan ve devrilmeyi
  kolaylaştıran asıl yapısal sorun bu.
- `[ ]` **ylp02 pusula arızası** — 143.5 µT / std 62.85 (sağlam uçak 48 µT /
  std ~1). Here4 takası ile ünite mi gövde mi ayrılmalı. Üç dronlu çekim buna
  bağlı.
- `[ ]` **`ORIGIN_ALT` yanlış** (1218.5). §9.2'deki ofset bunu görev tarafında
  sarıyor ama kaynağı düzeltilmedi.
- `[ ]` **Alıcı failsafe'i hâlâ kill tetikliyor** (`28-29-temmuz.md §7.1`).
  `rc_link_ok`'in kullanılamaz olmasının da kökü bu.
- `[ ]` **Üçüncü irtifa sıçraması** ("yerlerine geldiklerinde") — muhtemelen 1.
  adımda 2.0 m kala "vardı" sayılıp kalan farkın 2. adımda kapanması. Ofset
  düzeltmesi sonrası izlenecek; kalırsa `TOLERANS_M` düşürülür.
- `[ ]` **RTK uçuş sonrası Float'a düştü**, FIX'e dönmesi beklenmeli.
- `[ ]` **Kanıt videosu çekilmedi.**

---

## 11. Bu gece yazılan/değişen dosyalar

| dosya | ne |
|---|---|
| `src/swarm_control/.../esp32_bridge_node.py` | guided komut tekrar kuyruğu (§1.4) |
| `src/swarm_control/.../px4_bridge.py` | çapa idempotent (§6), yatay kalkış kilidi (§5) |
| `src/swarm_control/.../mavros_command_sender.py` | `_MASK_KALKIS` + `publish_kalkis_setpoint` (§5) |
| `src/gcs/gorev_kanit_ucus.py` | setpoint yürütme (§2), güvenlik kesicileri (§7), `--senaryo lider` (§8), yaw ve irtifa düzeltmeleri (§9) |
| `src/gcs/titresim_olc.py` | **yeni** — titreşim/EKF kararlılık ölçümü (§4.4) |

Commit sırası: `61cc1b2` → `33d1e7a` → `774a766` → `867939c` → `622b7b4` →
`a3b36ee` → `01413dd` → `6a35628`
