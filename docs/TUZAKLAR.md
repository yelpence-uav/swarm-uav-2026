# TUZAKLAR — hata vermeden yanlış sonuç üretenler

**Son güncelleme:** 31 Ağustos 2026, 16:24 — §3.16 (görev yazılımı emniyet pilotunu eziyordu) · §3.17 (formasyonsuz ofsetler içe sarmal) · §3.18 (gaz çubuğu dinlenme konumu = tam alçal) eklendi

> **Bu belge CANLI.** Arşiv değil — buradaki her madde **bugün de geçerli.**
>
> 16 Ağustos'ta Temmuz–Ağustos saha günlüklerinden çıkarıldı ve maddelerin
> tamamı **koda bakılarak yeniden doğrulandı**; geçersizleşenler alınmadı
> (bkz. en alttaki "Artık geçerli olmayanlar"). O günlükler artık yok —
> **bu belge onların yerine geçer.**
>
> Buradakiler **hata değil.** Hata verse zaten görürdün. Bunlar hata vermeden,
> uyarı vermeden, sayaç artırmadan yanlış sonuç üretenler. Her biri en az bir
> kez saatler yaktı, biri bir uçağı devirdi.
>
> **Yeni bir tuzak bulursan buraya yaz.** Parantez içindeki tarih o şeyin
> ölçüldüğü gündür — sayı görüyorsan ölçülmüştür, görmüyorsan tahmindir.

---

## En pahalı beşi — bunları ezberle

1. **QoS uyumsuzluğu sessizdir.** Yayıncı ile abone bağlanmaz ve **hata
   çıkmaz.** Topic ölü görünür. → §2.1
2. **Kumanda açıkken sürü otonomisi tamamen durur** ve hiçbir yere loglanmaz.
   → §3.1
3. **Ölçüm aracının kendisi yalan söylüyor olabilir** — `cat`, `ping`,
   `ros2 topic echo`, `ros2 topic pub`. → §1
4. **Kalkışta yatay konum tutmak uçağı devirir.** → §3.7
5. **Mesh hız limiti tip başına**, hedef başına değil — ikinci uçak komutların
   çoğunu kaybeder. → §4.1

---

## 🔴 0. Durumu BİLİNMİYOR — uçuştan önce cevaplanmalı

Bu üçü arşivde "çözülmedi" diye duruyor ve hiçbir canlı belgede yoktu.
**18 Ağustos'ta biri (0.2) cevaplandı** — cevabı beklenenin tersi çıktı.
Kalan ikisi hâlâ bilinmiyor.
Uçuş kanıtı geçildiğine göre bir kısmı düzelmiş olabilir — ama bunu kimse
yazmamış. Cevaplanınca ya buradan silinir ya doğru bölüme taşınır.

### 0.1 ylp00 titreşimi aralıklıydı — uçuş öncesi ölçüm kuralı hâlâ geçerli mi?

1 Ağustos'ta ylp00 kalkışta devrildi, pervaneleri kırıldı. Zincir ölçüldü:

```
titreşim -> ivmeölçer DOYUYOR -> EKF konumu sapıyor
   -> OFFBOARD yerde yatay konum tutuyor -> hatayı düzeltmek için EĞİLİYOR
   -> pervane yere vuruyor -> devriliyor
```

|  | ylp00 1. ölçüm | ylp00 2. ölçüm | ylp01 |
|---|---|---|---|
| ARMED konum sıçraması | **0.111 m** | 0.017 m | 0.024 m |
| titreşim z tepe | **33.84 m/s²** | 9.46 m/s² | 9.99 m/s² |
| **yeni clipping** | **+80** | 0 | 0 |

**Clipping = ivmeölçerin doyması**, gürültü değil **veri kaybı**: sensör
gerçek ivmeyi değil ölçebildiği tavanı bildirir, EKF'e giren veri zaten
bozuktur. "Yarım gazda titreşim normal" doğrudur; **clipping normal değildir.**

İkinci ölçüm temiz çıktı ama **sebep bulunamadı.** Aralıklı arıza sabit
arızadan tehlikelidir — uçarken geri gelebilir. O günün kuralı:

> `python3 src/gcs/titresim_olc.py <ylpXX>` — clipping artıyorsa **UÇMA.**
> Fiziksel kontrol sırası: motor yatakları → uçuş kartı montaj köpüğü →
> kol/gövde vidaları. ⚠️ **Pervane TAKILI ölçülür** — pervanesiz ölçüm
> yanıltır.

**🟢 29 Ağustos 2026 — kural uçuş başınadan saha gününe indirildi.** Eski
hâli *"her uçuştan önce"* idi ve **yazıldığı 1 Ağustos'tan beri bir kez
bile koşulmadı** (28 Ağustos'a kadar ~20 uçuş yapıldı). Uygulanmayan bir
kural koruma sağlamaz, yalnız listeyi şişirir.

**Yeni kural:** gövdeye **fiziksel iş** yapıldıysa (motor, pervane, kart
montajı, düşme/devrilme sonrası) **ve** saha gününde bir kez.
Sebep hâlâ bulunamadı, o yüzden ölçüm tamamen bırakılmıyor.
*(1 Ağustos 2026'da ölçüldü)*

### ✅ 0.2 CEVAPLANDI ve DÜZELTİLDİ (18-19 Ağustos)

*Soru: alıcı failsafe'i kill mi tetikliyor?* Cevap beklenenin tersi çıktı —
sorun ylp00'da değil **ylp02'deydi**: kumanda kapanınca `kill=True`,
`healthy=False` oluyordu. Alıcı failsafe'i düzeltildi (kayıtlı +100 → -100,
`CH5=1000` ölçüldü) ve **P0.9 kapandı**. Ölçüm dökümü git'te.

### 0.4 Kumandayı fabrika ayarlarına döndürmek ALICININ failsafe'ini de bozar

18 Ağustos'ta yaşandı: ylp02'nin CH5 failsafe'i düzeltildi ve doğrulandı,
sonra kumanda sıfırlandı ve düzeltme **geri gitti**.

```
duzeltilmis : 1488 1496 1017 1500  1000  2000 1000 1000
sifirlama sonrasi: 1501 1501  964 1499  2000  1000 1000 1000
                                        ^^^^ kill geri geldi
```

Failsafe değerleri kumandada değil **alıcının flash'ında** durur; sıfırlama
onları temizlemez, bağlantı kurulunca **varsayılanları geri yazar**. FlySky'ın
switch kanalları için varsayılanı `+100%`, yani **kill**. ylp02'nin en baştaki
bozukluğunun sebebi de büyük olasılıkla eski bir sıfırlama/model kurulumu.

⚠️ Sıfırlama yalnız failsafe'i bozmaz: reverse, End Points ve switch atamaları
da varsayılana döner, oysa **PX4'ün RC kalibrasyonu eski ayarlara göre**
yapılmıştır. Sıfırlama sonrası uçmadan önce `rc/in` okunarak doğrulanacaklar:
çubuk yönleri · ARM switch'i (CH8) · KILL switch'i (CH5) · gaz alt/üst uçları.

**Kural: kumanda sıfırlandıysa alıcı failsafe'i de yeniden kurulmadan uçulmaz.**
*(18 Ağustos 2026'da ölçüldü)*

⚠️ **Sıfırlama olmasa bile: failsafe menüsündeki düzenleme YANLIŞ KANALA
inebilir.** 19 Ağustos'ta ylp00'ın kumandasında niyet "CH6 → +100%" idi;
ölçümde CH6 hiç değişmemiş, **CH5 +100% (= KILL) ve CH7 0% olmuş** çıktı.
QGC'nin "Not Ready" gibi görünmesi de bu yüzdendi (kill tetiklenmişti) ve
bir an "sorun çözüldü" sanıldı — tespit değil, kill'di. **Kural: failsafe
menüsüne HER dokunuştan sonra kumanda kapatılıp `rc/in` çerçevesi 8 kanal
birden ölçülür.** *(19 Ağustos 2026'da ölçüldü)*

🔴 **Aynı gün bu kural ihlal edildi ve bedeli düşen uçak oldu:** CH5=+100%
duran kumanda, yerde ölçüm yapılmadan HAVADA kapatıldı → alıcı "kill'e bas"
çerçevesi bastı → **bütün motorlar anında kesildi, ylp00 alçak irtifadan
düştü.** RTL ayarlı olması kurtarmadı — kill her şeyi ezer. Yerdeki 2
dakikalık `rc/in` ölçümü bu düşüşü engellerdi. *(19 Ağustos 2026, ~17:30)*

### 0.5 FlySky hattı 900-2100 dışına ÇIKAMAZ; failsafe kaydı MUTLAK saklanır

19 Ağustos'ta ölçüldü (ylp00, iki uçta da):

- Telsiz protokolünün (AFHDS-2A) taşıma bandı **1500±600 = [900, 2100]**,
  yani tam ±120%. Uç noktalar 120'ye açılınca QGC'de 2100 ve 900 görülür;
  ötesi **hattan geçmez** (kumanda ekranı ne derse desin — ekran niyeti
  gösterir, hattı değil).
- Bu yüzden klasik "gaz failsafe'i canlı dibin altına" numarası bu takımda
  **çalışmaz**: canlı gaz dibi ~906-908'de (taban 900'ün 8 µs üstü), araya
  eşik sığmaz. Çalışan varyant ÜST uçtur: canlı tavan 2000 < eşik 2050 <
  failsafe 2100 (`RPI_ESITLEME` §5).
- Failsafe kaydı **mutlak değer** olarak saklanır: uç nokta 120'deyken
  yakalanan 2100, uç nokta 100'e geri alınsa da 2100 kalır. Dans şu: uç
  120 → çubuk uca → failsafe kaydet → uç 100'e geri (geri almayı unutursan
  canlı tavan 2100'e çıkar ve uçuşta tam gazda yanlış "kayıp" tetiklenir).
- QGC Radio kalibrasyonu `RC*_MIN/MAX/TRIM`'i yeniden yazar (19 Ağu'da
  `RC3_MIN` 1016→906 oldu). Her kalibrasyondan sonra failsafe eşiklerinin
  hâlâ aralığın DIŞINDA kaldığı denetlenmeli.

### ✅ 0.3 CEVAPLANDI (23 Ağustos) — hover gazı %66 DEĞİL, **%72**

Uçuş kaydından ölçüldü (ylp02, `vfr_hud.throttle`, 763 örnek):
**ortanca %72 · p90 %77.** Yani itki payı sanılandan **6 puan**
daha dar. Ayrıntı: `git show 783afab:docs/CA.md` §7.1.

### 0.3 (eski soru) ylp00 hover gazı %66 — hâlâ öyle mi?

İtki payı yok. Motor yakan ve devrilmeyi kolaylaştıran **yapısal** sorun
olarak yazılmıştı; roll manevrası ve yüksek irtifa itki payı ister. Ağırlık
ya da motor/pervane seçimi. *(1 Ağustos 2026)*

---

## 1. Ölçüm aracının kendisi yalan söylüyor

Bu projede en çok zaman burada kaybedildi: araç sessizce yanlış cevap verdi,
teşhis yanlış yere gitti.

### 1.1 `cat` baud rate ayarlamaz

`timeout 10 cat /dev/ttyAMA4 | wc -c` saatlerce "0 bayt" gösterdi ve kablo
suçlandı. `cat` portun **mevcut** baud'unu kullanır; ESP 460800'de
konuşuyordu. Python ile doğru baud verilince veri anında göründü.

> Seri hat testinde **her zaman** baud'u açıkça veren araç kullan
> (`python3 -c "serial.Serial(port, baud)"`). `cat`/`wc` ile tanı koyma.

*(20 Temmuz 2026 — o günün en pahalı hatası)*

### 1.2 `ping` bu ağda "yok" hükmü veremez

Drone'lar ICMP'ye cevap vermiyor. ylp02 saatlerce "ağda yok" sanıldı;
`arp-scan` onu anında buldu ve SSH çalıştı. **Tarama için `arp-scan`**,
Raspberry Pi MAC öneki `88:a2:9e`. Bugün doğrusu:
`./deploy/yki/drone_bul.sh`. *(28 Temmuz 2026)*

### 1.3 `ros2 topic echo` varsayılanı RELIABLE

BEST_EFFORT bir topic'te `echo` boş döner — topic çalışmıyor sanılır.
`--qos-reliability best_effort` ekle, ya da doğrudan gerçek tüketiciden
doğrula. *(20 Temmuz 2026)*

### 1.4 `ros2 topic pub` varsayılanı VOLATILE

TRANSIENT_LOCAL abonesi olan bir topic'e `ros2 topic pub` ile yayın yapmak
**hiç ulaşmaz**, hata da vermez. `ElectionResult` ve `TIP_ORIGIN` yolunda
iki kez yaşandı. Elle yayında şart:

```bash
ros2 topic pub ... --qos-reliability reliable --qos-durability transient_local
```

`esp32_bridge_node` `ElectionResult`'ı RELIABLE + TRANSIENT_LOCAL dinliyor
(kod yorumu: *"depth=10, geç gelen alır"*), `consensus_node` da aynısını
yayınlıyor — **sistemde uyumsuzluk yok**, uyumsuzluk yalnız elle test
ederken doğuyor. *(20 ve 28 Temmuz 2026)*

### 1.5 `f9p_base_yapilandir.py --durum` "kapalı" ile "cevap gelmedi"yi ayırmaz

Durum ekranı `d.get(k)` ile bakıyor; anahtar CFG-VALGET cevabında hiç
gelmediyse de `None` döner ve **kapalı** raporlanır. Toplu sorguda cevap
bölünürse ekran yanıltır — kritik anahtarları (`1005`, `1230`) **tek tek**
sor. *(29 Temmuz 2026)*

### 1.6 `status_text` bayat kalır

`pilot_override_active` false'a döndükten sonra da
`status_text: Pilot override active` okunmaya devam ediyor; alan yalnız
belirli olaylarda üzerine yazılıyor. Sahada yanıltıcı — **bayrağın kendisine
bak**, metne değil. *(30 Temmuz 2026)*

### 1.7 `kill_switch_active` fiziksel kill switch'i GÖRMEZ

O alan RC kanalından türetiliyor. `kill_switch_active: false` okunurken arm
reddediliyordu; gerçek sebep uçağın üzerindeki fiziksel switch'ti. Bu alana
bakıp "kill sorunu yok" demek yanlış. *(30 Temmuz 2026)*

### 1.8 `esp32_bridge` tanısı log dosyasına yazmaz

Sayaçlar `/swarm/internal/events/system` topic'ine `mesh_diag ...` olarak
gider. `esp.log`'da yalnız açılış satırları vardır; oraya bakmak "sayaç yok"
yanılgısı yaratır.

### 1.9 `_on_election` hiçbir şey loglamaz

`ctx.leader_id`'yi doğrudan yazıyor, `_set_leader`'ı çağırmıyor — ne log ne
event çıkıyor. **Bir takipçinin lideri öğrenip öğrenmediği consensus
logundan anlaşılamaz.** Dolaylı gözlem: yanlış lider enjekte edilirse bir
sonraki tick `REASON_LEADER_FAULT` ile geri alır, o **loglanır**.
*(30 Temmuz 2026)*

### 1.10 PX4 1.16 arm reddini `STATUSTEXT` ile değil MAVLink Events ile bildirir

MAVROS'ta metadata olmadığı için `FCU: EVENT 3087815 with args ...` gibi
çıplak ID basar, `statustext/recv` boş kalır. **Gerekçeyi düz metin görmek
için QGroundControl** gerekir. Bunu bilmeden MAVROS logunda saatler harcanır.

### 1.11 HDOP'a bakıp "GPS mükemmel" deme — bakılacak sayı `h_acc`

Yeni/eski GPS standı karşılaştırması, aynı anda aynı binada:

|  | ylp00 (yeni stand) | ylp02 (eski stand) | PX4 barajı |
|---|---|---|---|
| `h_acc` | **2.65 m** | 4.42 m | `EKF2_REQ_EPH` = **3.0 m** |
| uydu | 26 | 25 | — |
| HDOP | 0.54 | 0.58 | — |
| `estimator_ok` | **True** | **False** | — |

Uydu sayısı ve HDOP **ikisinde de aynı.** Stand uydu görüşünü değil sinyal
kalitesini iyileştiriyor. HDOP 0.58 iken alıcının kendi doğruluk tahmini
4.42 m — baraj 3.0 m. *(29 Temmuz 2026)*

### 1.12 `ros2 node list` EKSİK liste döndürür ve hata vermez

Uçakta düğümlerin ayakta olup olmadığına bakarken ilk çağrı **tek bir düğüm**
döndürdü; aynı konteynerde `--spin-time 12` ile aynı komut **11 düğüm + 68
mavros alt düğümü** listeledi. Hiçbir uyarı yok, çıkış kodu 0.

Sebep: `ros2` CLI kendi DDS katılımcısını yeni yaratıyor ve keşif oturmadan
listeyi basıyor. Varsayılan bekleme, 11 düğümlü bir grafiğe yetmiyor.

**Kural:** uçakta düğüm sayarken **her zaman** `--spin-time` ver:

```bash
ros2 node list --spin-time 12
```

Bu tuzak "düğüm ölmüş / sürü düğümleri açılmamış" teşhisi koydurur ve o
teşhis yanlıştır. *(17 Ağustos 2026, ylp00)*

### 1.13 Açılış logu dizinlerinde `mtime` sıralaması YALAN söyler

`gunluk/` altındaki dizinler açılış anındaki saatle **adlandırılıyor**, ama
`gps_saat.py` açılışın ortasında saati ileri atlatabiliyor. Sonuç: dizin
**adı** ile `mtime` birbirini tutmuyor, `ls -t` yanlış dizini "en yeni"
gösteriyor. 17 Ağustos'ta tam bu yüzden **başka bir açılışın** logu okundu ve
"saat düzelmiş" sanıldı; gerçekte o açılışta düzelmemişti.

Aynı hatanın ikinci yolu: `find ... -name gps_saat.log | head -1` — `find`
sıralama yapmaz, rastgele birini verir.

**Doğrusu — ikisinden birini kullan:**

```bash
~/yelpence_ws/gunluk/son/            # baslat.sh'in baktigi isaretci
docker inspect -f '{{.State.StartedAt}}' drone1   # dizin adiyla eslestir
```

*(17 Ağustos 2026)*

### 1.14 `dagit.sh` derleme çökse bile "başarılı" der

17 Ağustos'ta iki uçakta da `swarm_missions` derlemesi **çöktü**, betik
`basarili: 2` yazdı ve `.surum` dosyasını yine de güncelledi. Sebep:

```bash
colcon build ... 2>&1 | tail -15     # boru hattinin cikis kodu = tail'inki = 0
```

`if ! ssh ...` bu yüzden hiç tetiklenmiyor. Çıktıyı okumasaydık uçakta bir
paketin **eski install/** ile koştuğunu bilmeden uçacaktık — ve `.surum`
"e012dba (main)" diyeceği için sonraki kişi de sorgulamayacaktı.

✅ **18 Ağustos'ta düzeltildi:** uzak `bash -lc` içine `set -o pipefail`
eklendi; boru hattı artık `colcon`'un çıkış kodunu taşıyor ve derleme
çökerse `.surum` da yazılmıyor. Mekanizma kabukta doğrulandı — pipefail
kapalı → çıkış 0, açık → 1.

**Kural yine de geçerli:** `dagit.sh` çıktısındaki `Summary:` satırını gözünle
oku. *(17 Ağustos 2026'da ölçüldü, 18 Ağustos'ta düzeltildi)*

### 1.15 `hostname` Arch'ta kurulu değil — `.surum`'un `dagitan` alanı boşalır

`dagit.sh:169` `dagitan=$(hostname)` kullanıyor; Arch'ta `inetutils` varsayılan
gelmiyor, komut bulunamıyor ve alan **sessizce boş** kalıyor. Kim dağıttı
bilgisi kayboluyor.
✅ **18 Ağustos'ta düzeltildi:** `hostname → /etc/hostname → "bilinmiyor"`
zinciri. *(17 Ağustos 2026'da ölçüldü)*

### 1.16 YKİ'deki `rc_link_ok` ve `ready_to_arm` PX4'ün RC-kayıp kararını GÖSTERMEZ

P1.9 doğrulanırken çıktı: parametreler yazıldı, PX4 kaybı görmeye başladı,
ama YKİ telemetrisi hiç kıpırdamadı.

- `rc_link_ok` = "RCIn mesajında kanal var mı" (`mavros_telemetry_mapper.py:299`).
  FS-iA6B kumanda kapalıyken de failsafe çerçevesi bastığı için **hep True**.
- `ready_to_arm` = SYS_STATUS'un PREARM biti; RC kaybında **düşmediği ölçüldü**.
- `rc_signal_failsafe_active` yalnız armlıyken anlam taşıyor.
- (`kill_switch_active` ise doğrudan CH5 değerinden türetiliyor — o doğru çalışıyor.)

PX4'ün RC-kayıp kararının gerçek göstergeleri:

- `/drone_N/mavros/sys_status` → `sensors_health` içindeki **RC_RECEIVER
  biti (`0x10000`)**: kayıpta 0 (19 Ağu'da iki yönde de ölçüldü)
- QGC üst barı **SARI** + tıklayınca *Vehicle Messages*'ta **"Manual control
  lost / regained"** çiftleri, *Overall Status*'ta **"No manual control
  input"** (her aç-kapada düştüğü ölçüldü)
- Yazı "Ready To Fly" kalır çünkü PX4 kayıpta modu **PosCtl → Hold'a
  düşürüyor** ve otonom kipler RC istemediği için uçuşa-hazırlık geçiyor.
  Bu, "arm reddedilir" demek DEĞİL — pervanesiz arm testi ayrıca yapılacak
  (`YAPILACAKLAR` P1.9)

*(19 Ağustos 2026'da ölçüldü)*

### 1.17 `build/lib/` BAYAT kopya tutuyor — senkron kontrolünü yanıltır

20 Ağustos'ta "ylp02'ye yeni kod gitti mi" sorusunda çıktı. Konteynerde
`px4_bridge.py`'nin **iki** kopyası var ve md5'leri FARKLI:

```
/ws/build/swarm_control/build/lib/swarm_control/... -> BAYAT, kimse yuklemiyor
/ws/build/swarm_control/swarm_control/...           -> GERCEKTEN YUKLENEN
```

Yanlış olana bakan "kod eski kalmış" sanır ve dağıtımı boşuna tekrarlar.
`find ... -name px4_bridge.py` ikisini birden döndürür, hangisinin
koştuğunu söylemez.

**Kesin yol — Python'un kendisine sor:**

```bash
docker exec drone1 bash -lc 'source /opt/ros/jazzy/setup.bash && \
  source /ws/install/setup.bash && python3 -c \
  "import swarm_control.px4_interface.px4_bridge as m; print(m.__file__)"'
```

Dönen yolu md5'le, repo ile karşılaştır. *(20 Ağustos 2026'da ölçüldü)*

### 1.18 `docker logs` tek bir NUL baytıyla ÇÖKÜYOR — `--tail` çalışıyor, gerisi hayır

Konteynerin ne bastığına bakarken en doğal komut bu, ve **sessizce eksik
cevap veriyor.** ylp00'da ölçüldü (20 Ağustos):

```
docker logs --tail 5    drone1   ->  OK
docker logs --tail 3000 drone1   ->  OK
docker logs --tail 4000 drone1   ->  BOZUK — 61 satir verip kesildi
docker logs --since 15m drone1   ->  BOZUK (hic satir vermedi)
docker logs            drone1   ->  BOZUK
```

Hata metni: `error from daemon in stream: Error grabbing logs: invalid
character '\x00' looking for beginning of value`.

**Neden — ve bu SİSTEMİK:** json-file sürücüsünün dosyasında **NUL boşluğu**
var. Ölçüldü: iki koşu, 1602 + 433 bayt, `d8673388...-json.log`'un %7'sinde,
ikisi de **16 Ağustos 23:34**. Boşluktan sonraki zaman damgası öncekinden
**15 sn geriye** gidiyor (RTC pili yok, saat kayıtlı damgadan geri dönüyor)
ve hemen ardından `[baslat] AGENT_ID=1` geliyor.

Sebep **pil değişimi**. Operatör doğruladı (20 Ağustos): pil değiştirmek
için güç kesiliyor, sayfa önbelleğindeki veri diske hiç yazılmıyor, ext4
dosya boyutunu uzatmış ama blokları boş — okununca sıfır geliyor. Bu
projede pil değişimi günde defalarca oluyor, **yani kural dışı değil,
normal yol.** Aynı gün 20 Ağustos 21:30'daki pil değişimi ylp00'da dört
log dosyasında daha aynı boşluğu açtı (`gunluk/20260820_211430/`).

İlk yazımda "drone3'te 0 NUL, sistemik değil" demiştim — **yanlıştı**;
drone3 yalnızca kötü ana denk gelmemişti.

**Tuzağın kendisi:** `--tail` çalıştığı için araç "sağlam" görünüyor, ama
`--since` **boş dönüyor**. Boş çıktıya bakıp "konteyner hiçbir şey basmamış"
diye yorumlarsan yanlış yoldasın. 20 Ağustos'ta tam olarak bu oldu: yeniden
başlatmanın başarılı olup olmadığını `docker logs --since 15m` ile
sormuştum, boş döndü.

**Ne yapmalı:**

- Tanı için `docker logs --tail N` kullan, `--since` kullanma.
- **Asıl kaynak zaten `docker logs` değil**: `baslat.sh` her düğümü ayrı
  dosyaya yazıyor — `~/yelpence_ws/gunluk/<damga>/{mavros,px4b,esp,consensus,
  formation,...}.log`. Bozulma bunları etkilemedi.
- Log dosyasını **yerinde `truncate` etme** — daha kötü olur: docker dosyayı
  `O_APPEND` ile açık tutuyor, kesince eski ofsetten yazmaya devam eder ve
  başında dev bir NUL bloğu olan seyrek dosya oluşur.
- Kalıcı çözüm konteyneri **yeniden oluşturmak** (`docker rm -f drone1` +
  `run_drone.sh 1`); yeni dosya temiz başlar. Bütün durum `/ws` bağlamasında
  olduğu için kayıp yok (yazılabilir katmanda yalnız `.ros`/`.colcon`
  önbellekleri var, 29 MB, kendiliğinden yeniden üretilir).
- `run_drone.sh`'e `--log-opt max-size=10m --log-opt max-file=3` eklendi:
  döndürme olmadan bozuk parça **sonsuza kadar** kalıyordu.

### 1.19 Uçuş kaydı açılmıyorsa panik yapma — veri duruyor olabilir

Bir dönem uçuş kayıtlarının **hepsi** `ros2 bag` ile açılamıyordu; veri
sağlamdı, sarmalayıcı bozuktu. Bugün iki koruma var: açılışta
`kayit_onar.sh` ve `~/yelpence_ws/bin/mcap` kurtarma aracı.

> ⚠️ **`mcap` ikilisi `dagit.sh` ile GİTMEZ** ve depoda yok (A11, elle
> kopyalanır). Yeni bir uçakta yoksa onarım **sessizce** eski davranışına
> döner. Tam teşhis öyküsü: `git show 783afab:docs/TUZAKLAR.md`

### 1.19b Kuru testi HER fiziksel dokunuştan sonra TEKRARLA — plan sessizce geçersizleşir

21 Ağustos'ta **iki kez** uçuşu durdurdu, ikisi de gerçek tehlikeydi:

1. Operatör ylp02'yi taşıdı; ylp00'ın bacak koridoruna **4,9 m** kaldı.
   `basit_kacinma` komşunun **yalnız konumuna** bakıyor — kodda armed/state
   kontrolü **YOK** (`kacinma/basit_kacinma_node.py` `_on_komsu`). Yani
   **disarm, motorsuz, yerde duran uçak da engel sayılıyor** ve havadakini
   iter. Etki eşiği `d0_m=6.0` m; 6 m üstünde sıfır.
2. Titreşim testindeki zıplama ylp00'ı **~100° döndürdü** (244° → 344°).
   Bacak yönü uçağın burnundan alınıyor, yani **operatörün gözüyle
   onayladığı harita geçersizleşti** ve yeni bacak ucu ylp02'ye **1,2 m**
   kaldı. Uçak kalksa neredeyse üstüne uçacaktı.

İkisi de yalnız **taze** kuru testte göründü; eski harita ikisini de
"temiz" gösteriyordu. Kural: uçağa dokunulduysa (taşıma, döndürme, arm
denemesi, pil değişimi) **kuru test + harita yeniden üretilir ve operatör
yeniden bakar.** Maliyeti 30 saniye.

### 1.20 Bench'te AgentStatus pili HEP "12.6 V / %100" der — SAHTE

Ölçüldü (21 Ağustos, iki uçakta birebir aynı):

```
/mavros/battery      voltage: 65.535  percentage: -0.01   <- PX4: "bilmiyorum"
AgentStatus          battery_voltage_v: 12.600000381...   <- uydurma sabit
```

`65.535` = UINT16_MAX/1000, MAVLink'in "geçersiz" değeri. Pil okuma PX4'te
**bilerek kapalı** (operatör kararı — sorunlu okuma; kalıcı plan harici
modül → RPi → YKİ, **KARAR-03**). Tuzak şurada: `px4_bridge.py:546` sim
döneminden kalma davranışla `percent<=0` görünce **12.6 V / %100 basıyor**
— yani "bilerek kapalı" durumu "pil dolu" gibi görünüyor. İki uçağın bire
bir aynı float'ı göstermesi tek ipucuydu.

**Isırdığı yer (ölçüldü):** consensus varsayılan `battery_min_v=14.0` ile
elle başlatılınca sahte 12.6 < 14.0 → **iki uçak da aday dışı** → sıfır
seçim, sıfır hata, sıfır log. Teşhis betikleri bu yüzden consensus'u
`baslat.sh:748` ile **birebir aynı parametrelerle** başlatmak zorunda
(`agent_count:=3 battery_min_v:=0.0`) — üçü de düzeltildi.

Sahtenin kaldırılması `YAPILACAKLAR.md` P1.13'te; pil izlemenin bütünü
**KARAR-03**'te (üç yerde birden kapalı, modül gelince altı adımda açılacak).

### 1.21 `crc_fail = 0` "veri eksiksiz geldi" DEMEK DEĞİL

`esp32_bridge` seri hattı şöyle sayıyor:

```
alim_ok     COBS+CRC dogrulanmis paket
crc_fail    CRC eslesmemis paket        <- bayt BOZULDUYSA
```

Bayt **bozulursa** `crc_fail` artar. Ama **kaybolursa** COBS bir sonraki
`0x00` ayracında yeniden senkron olur ve yarım çerçeve **sessizce yok olur** —
hiçbir sayaca yansımaz. Köprüde çerçeve-kayması sayacı **yok** (22 Ağustos'ta
sayaç listesi tek tek okundu: `alim_ok · crc_fail · gonderim_ok ·
gonderim_drop · rtk_alindi · bilinmeyen_tip · id_uyumsuz`).

Sonuç: **"CRC sıfır" bir kanıt değil, yarım kanıttır.** Kayıp bayt arıyorsan
sayaca değil, **beklenen paket hızıyla ölçüleni** karşılaştır (POSE 10 Hz
yollanır; alınan 5,8/s ise fark oradadır). *(22 Ağustos 2026)*

### 1.22 "DURUM paketi N sn'dir gelmedi" uyarısı YANILTABİLİR

`esp32_bridge_node.py`'de yaş şöyle hesaplanıyor:

```python
yas = time.monotonic() - self._komsu_durum_ts.get(drone_id, 0.0)
```

🔴 **Anahtar YOKSA `.get` 0.0 döner** ve `yas` = sürecin çalışma süresi olur.
Yani uyarı "o komşudan hiç DURUM gelmedi" halinde de çıkar, üstelik
uydurma bir sayıyla.

22 Ağustos'ta ylp00 *"drone3: DURUM paketi **27.8 sn**dir gelmedi"* dedi ve
27,8 gerçek bayatlık değil, köprünün o anki çalışma süresiydi. Bu satıra
bakıp "27 saniyedir kopuk" sonucu çıkarmak yanlış olurdu.

**Kural:** bu uyarıyı görünce önce o komşudan **hiç** DURUM gelip gelmediğini
doğrula. *(22 Ağustos 2026)*

---

### 1.23 `set -u` ile ROS `setup.bash` = script TEK SATIR çıktı vermeden ölür

**23 Ağustos 2026, yer testi betiğinde yaşandı.** Betik `set -uo pipefail`
ile başlıyordu ve `source /opt/ros/jazzy/setup.bash` satırında **sessizce**
ölüyordu: çıkış kodu 1, stdout boş, stderr boş, log dosyası bile yok.

Sebep: `setup.bash` tanımsız değişkenlere dokunuyor
(`AMENT_TRACE_SETUP_FILES`, `COLCON_TRACE`…) ve `set -u` altında ilk temas
kabuğu bitiriyor. `>/dev/null 2>&1` ile susturulmuş olması izi tamamen yok
ediyor.

`bash -x` olmadan bulunması çok zor — teşhis yolu buydu:

```bash
docker exec drone1 bash -x /tmp/betik.sh ... > /tmp/iz.txt 2>&1
# ⚠️ yonlendirme KONTEYNER DISINDA calisir: dosyayi Pi'de ara, icerde degil
```

**Kural:** ROS kaynaklayan betiklerde `set -u` **kullanma**. `set -o pipefail`
yeterli.

### 1.24 `kill` `ros2 run`'ı öldürür, ÇOCUĞU öksüz bırakır

**23 Ağustos 2026'da yer testinden sonra yakalandı.** Test betikleri
`ros2 run swarm_core collision_avoidance ... &` ile düğüm açıp `kill $PID`
ile kapatıyordu. Ama `ros2 run` bir **sarmalayıcı**: gerçek düğüm ayrı bir
süreç (`/ws/install/.../collision_avoidance`). Sarmalayıcı ölünce çocuk
yaşamaya devam ediyor.

Üç yer testinden sonra ylp02'de **üç artık düğüm** ayaktaydı:

```
PID  261/265  942 sn   <- gercek ucus dugumu (dogru)
PID  1007     403 sn   <- G0-2 artigi
PID  1264     164 sn   <- G0-5 artigi
PID  1493      75 sn   <- G0-4 artigi
```

Bu sefer zararsızdı çünkü hepsinin çıktısı `-r` ile `/g0…` konularına
yönlendirilmişti. **Yönlendirme olmasaydı** `/drone_N/control/setpoint`'e
dört yayıncı olurdu — `CLAUDE.md` §4'ün tam olarak yasakladığı hâl.

**Kural:** test düğümünü desenle öldür ve **doğrula**:

```bash
pkill -f "collision_avoidance.*[/]g0"
ros2 topic info /drone_N/control/setpoint     # "Publisher count: 1" OLMALI
```

⚠️ `ros2 node list` bu işte yanıltıcı: MAVROS ~70 eklenti alt düğümü
kaydediyor, toplam 80 görünüyor. Sürü düğümü sayısını `mavros` filtreleyerek
say.


### 1.25 `docker exec` ROS ortamını MİRAS ALMAZ — düğümleri göremez, hata da vermez

`baslat.sh` konteynerin **komutudur**; içindeki `export ROS_LOCALHOST_ONLY=1`
yalnız o komutun çocuklarına geçer. `docker exec` ise konteynerin
**yapılandırmasındaki** ortamı alır — yani `docker run -e` ile verilenleri.
İkisi aynı şey değil ve fark hiçbir yerde belirtilmiyor.

Ölçüm (26 Ağustos 2026, ylp01):

```
docker exec drone2 env | grep ROS
    ROS_DOMAIN_ID=0             <- run_drone.sh'te -e ile verilmis
    ROS_DISTRO=jazzy            <- imaj ENV'i
    RMW_IMPLEMENTATION=...      <- imaj ENV'i
    (ROS_LOCALHOST_ONLY YOK)

tr '\0' '\n' < /proc/211/environ | grep ROS     # calisan esp32_bridge
    ROS_LOCALHOST_ONLY=1        <- baslat.sh export etmis
```

`ROS_LOCALHOST_ONLY=1` DDS'i loopback'e kapatır. Değişkeni almayan bir kabuk
**başka bir DDS alanında** olur; düğümler oradadır ama görünmezler.

**Belirti sessizdir:** `docker exec ... ros2 topic echo /drone_2/mavros/state`
hiçbir şey basmadan çıkar. Düğüm ayakta, konu yayında, komut sıfır döner.
`ros2 node list` de eksik ya da boş döner (§1.12 ile aynı yüzey).

26 Ağustos'ta canlı uçtan `armed` durumu okunamadı ve önce **"MAVROS ölmüş"**
sanıldı; teşhis bir tur geciktirdi.

**Çözüm iki katmanlı:**
- Kalıcı: `run_drone.sh`'te `-e ROS_LOCALHOST_ONLY=1` (26 Ağu, `dd5a1e6`).
  ⚠️ **Yalnız konteyner YENİDEN OLUŞTURULUNCA** geçerli — restart yetmez.
- O ana kadar elde: `docker exec -e ROS_LOCALHOST_ONLY=1 <konteyner> ...`

---

### 1.26 `docker ps` durmuş konteyneri GÖSTERMEZ — ve elle durdurulan, Pi kapa-aç ile GERİ GELMEZ

İki ayrı gerçek üst üste binince uçak sessizce **sıfır düğümle** kalıyor:

1. **`--restart unless-stopped`, elle durdurulmuş bir konteyneri Pi yeniden
   başlasa bile geri getirmez.** Bu doğru davranıştır — kasten durdurulan bir
   konteynerin kendiliğinden geri gelmesi daha tehlikeli olurdu. Ama "kapat-aç
   düzeltir" refleksi bu durumda **çalışmaz**.
2. **`docker ps` yalnız çalışanları listeler.** `drone_bul.sh --durum` bunu
   kullanıyordu; durmuş konteyner **boş satır** olarak geçiyordu.

26 Ağustos 2026: ylp00'ın `drone1`'i ESP testi için durdurulmuştu. Operatör
Pi'leri kapatıp açtı — ylp01 ve ylp02 kendiliğinden geldi, **ylp00 gelmedi** ve
43 dakika `Exited (137)` kaldı. Durum tablosunda hiçbir uyarı yoktu; fark
edilmeseydi uçak mesh'siz, px4_bridge'siz sahaya çıkacaktı.

**Çözüm:** `--durum` artık `docker ps -a` kullanıyor ve çalışmıyorsa düzeltme
komutuyla birlikte `>> SORUN` satırı basıyor. Politika **değişmedi**.

---

### 1.27 Pi'nin ritmik yanıp sönen ışığı UYKU DEĞİL — SD'ye yazıyor demek

**27 Ağustos 2026, operatör gözlemi.** *"RPi'ler ağa bağlı değilken ışıkları
yarım saniyede bir yanıp sönüyor, sanki uyku moduna girmişler."*

Gözlem gerçek ve önemliydi, ama **ters okunmuştu**. Ölçüldü:

```
ACT LED tetikleyicisi        : [mmc0]   = SD KART AKTIVITESI
PWR LED                      : kapali
vm.dirty_writeback_centisecs : 100      = her 1 SANIYEDE geri-yazim
uptime                       : uc ucakta da kesintisiz
powersave / sleep.target     : kapali / etkin degil
```

Yani Pi uyumuyor — **tam tersine, durmadan SD karta yazıyor.** Çekirdek her
saniye geri-yazım turu atıyor (`izleme_kur.sh` 7/7, güç kesilince log
kaybolmasın diye bilinçli). Normalde yazacak veri olmadığı için LED sessiz.

**Ritmi yaratan şey MAVROS taşkını** (§2.23): ağ kopunca GCS yayın hattı
bozuluyor, saniyede binlerce satır üretiliyor, her geri-yazım turunda yazacak
veri buluyor → düzenli, ritmik LED.

**Ders:** "ağ yokken ışık yanıp sönüyor" doğru bir korelasyondu; yanlış olan
"demek ki uyuyor" çıkarımıydı. Bu projede LED, sistemin **en ucuz telemetri
kanalı** — ama neyi gösterdiği tetikleyiciye bakılarak doğrulanmalı
(`cat /sys/class/leds/ACT/trigger`).

**Yan zarar:** SD kart boşuna yıpranıyor. Taşkın halinde saatte yüzlerce MB
yazılıyor ve geri-yazım 1 sn'de bir olduğu için bu yazımlar tampona toplanıp
seyrekleştirilemiyor.

---

## 2. ROS 2 / DDS / kabuk

### 2.1 QoS uyumsuzluğu SESSİZDİR — bu belgedeki en pahalı tek kural

BEST_EFFORT yayıncı ↔ RELIABLE abone, ya da VOLATILE ↔ TRANSIENT_LOCAL:
**hiç bağlanmazlar ve hata da vermezler.** Panel boş kalır, sayaç 0 kalır,
hiçbir yerde bir satır çıkmaz.

Bu projede en az üç kez yaşandı: `SwarmState` publisher'ı (YKİ paneli boş
kalıyordu), yük testi üreteci, RTCM okuyucusu. Yeni bir publisher/subscriber
eklerken **karşı ucun QoS'unu oku.** *(20 ve 28 Temmuz 2026)*

> ⚠️ **Nüans (15 Ağustos):** "hiçbir yerde bir satır çıkmaz" tam doğru değil —
> düğüm **açılırken** ROS'un kendi uyarısı çıkabiliyor. Sessiz olan **çalışma
> zamanı**: bir kez açıldıktan sonra hiçbir sayaç, hiçbir log uyumsuzluğu
> göstermiyor. Açılış logunu okumak bu yüzden değerli.

### 2.2 `RMW_IMPLEMENTATION` + `CYCLONEDDS_URI` vermeden düğüm başlatma

Topic hiç bağlanmaz, sayaç 0 kalır, **hata çıkmaz.** YKİ tarafında RTCM
okuyucusunda tam bunu yaşadık.

### 2.3 ROS `setup.bash` zsh altında bozulur

`source /opt/ros/jazzy/setup.bash` zsh'ta kendi yolunu bulamıyor,
`ament_cmake` bulunamıyor. `colcon build` **her zaman `bash -c` içinde.**
(Bu makinenin kabuğu zsh.)

### 2.4 `timeout` ile `ros2` kesmek çökme raporu üretir

SIGTERM ile ölen `ros2` CLI'ı Ubuntu apport "System program problem detected"
popup'ı olarak gösteriyor. Zararsız ama korkutucu. `timeout -s INT` kullan
(SIGINT temiz kapatıyor) ya da `--once`.

### 2.5 `pkill -f` kendi kabuğunu öldürür

`pkill -f "esp32_base"` çalıştıran komut satırının kendisi de deseni içerdiği
için kabuk ölüyor. Köşeli parantez numarası: `pkill -f "esp32[_]base"`.

### 2.6 `ROS_LOCALHOST_ONLY` Jazzy'de deprecated

`deploy/rpi/baslat.sh` hâlâ `ROS_LOCALHOST_ONLY=1` veriyor ve her düğüm
açılışta uyarı basıyor. **Çalışıyor**, sadece gürültü. İleride
`ROS_AUTOMATIC_DISCOVERY_RANGE` + `ROS_STATIC_PEERS`'a geçilmeli.

### 2.7 `while read` döngüsünün içindeki `ssh` döngüyü SESSİZCE bitirir

İki uçağa sırayla dosya göndermek için yazılan döngü **yalnız ilkini** işledi,
hata vermeden:

```bash
drone_bul.sh --tablo | while read -r isim ip kul kon aid; do
    ssh "$kul@$ip" 'md5sum ...'      # <-- kalan satirlari YUTAR
done
```

`ssh` stdin'i okur ve döngüyü besleyen borudaki kalan satırları tüketir.
Çıktıya bakan kişi "ikinci uçak ağda değilmiş" sanır. Aynısı `ffmpeg`,
`mysql`, `docker exec -i` için de geçerli.

**Çözüm:** `ssh -n` (stdin'i `/dev/null`'a bağlar) ya da `ssh ... < /dev/null`.
*(17 Ağustos 2026)*

### 2.8 Depodan dosya silinince bayat `build/` dizini derlemeyi kırar

`main` dağıtıldığında iki uçakta da:

```
error: can't copy '/ws/build/swarm_missions/launch/gorev1.launch.py':
       doesn't exist or not a regular file
```

`setup.py` glob kullanıyor (`glob('launch/*.launch.py')`), yani **depoda hata
yok**. Hata Pi'de: `rsync --delete` kaynağı sildi ama `--symlink-install` ile
oluşmuş `build/swarm_missions/` hâlâ o dosyanın kaydını tutuyordu ve yeniden
kopyalamaya çalıştı.

**Kural:** depodan bir dosya silindikten sonraki ilk dağıtımda o paketin
`build/` + `install/` dizinini temizle:

```bash
docker exec <KONTEYNER> bash -lc \
  'rm -rf /ws/build/<paket> /ws/install/<paket> &&
   source /opt/ros/jazzy/setup.bash && cd /ws &&
   colcon build --symlink-install --packages-select <paket>'
```

`dagit.sh` bunu kendiliğinden yapmıyor ve §1.14 yüzünden çöküşü de
yutuyor — ikisi birleşince paket sessizce **eski install/** ile kalır.
*(17 Ağustos 2026)*

---

### 2.9 `ros2 topic pub` VOLATILE yayınlar — TRANSIENT_LOCAL abone HİÇ almaz

`/swarm/internal/election/result` aboneliği `_ELECTION_QOS` = **RELIABLE +
TRANSIENT_LOCAL** (`esp32_bridge_node.py:110`; `consensus_node.py:118` de aynı).
`ros2 topic pub`'ın varsayılanı **VOLATILE**, yani bayraksız elle yayın
DURABILITY uyumsuzluğundan **hiç ulaşmıyor** ve hata da vermiyor.

Sahada ölçülen belirti: `form_lider_degil=9  lider=0` — köprü "lider bilinmiyor"
diyor, oysa yayın yapılıyor sanılıyor.

```bash
ros2 topic pub --qos-reliability reliable --qos-durability transient_local ...
```

⚠️ Bu yalnız **elle yayında** çıkan bir tuzak; gerçek düğümler arasında
uyumsuzluk yok. `~/yelpence_ws/form_yayinla.sh` içinde yazılı — o betik
repoya alınmalı (`YAPILACAKLAR` P2.5). *(18 Ağustos 2026'da bulundu)*

### 2.10 KURAL: `/swarm/public/…` dinleyen HERKES BEST_EFFORT olmalı

`esp32_bridge` mesh'ten gelen **dört** konuyu `_MESH_QOS` yani **BEST_EFFORT**
yayınlıyor:

```
formation/target · perception/qr_data · control/command · drone{N}/status
```

RELIABLE abone + BEST_EFFORT yayıncı **eşleşmez** ve konu **sessizce boş
kalır**. Ters yön sorunsuz (RELIABLE yayıncı + BEST_EFFORT abone uyumlu), o
yüzden `ic_dis_kopru` RELIABLE yayınlamaya devam ediyor.

15 Ağustos'ta **beş abonelik** birden bu yüzden bozuktu: `formation_node`,
`collision_avoidance`, `maneuver_executor`, `mission1_node`, `mission_fsm_node`
— artı YKİ tarafında `gcs/backend/ros_bridge.py`. Sonuncusu özellikle ironikti:
**kasıtlı RELIABLE yapılmıştı**, gerekçesi *"QR mesajı GCS'te en az 1 kez
görünmeli (şartname V2, −20 ceza)"*. Niyet doğru, etki tam tersi — BEST_EFFORT
yayıncıdan **hiçbir şey almıyordu**.

> 🔎 **Yöntem dersi:** biri `formation_node` açılınca ROS'un kendi uyarısıyla
> bulundu, sonra **bütün** public abonelikleri ve `esp32_bridge` yayıncıları
> tarandı ve dördü daha çıktı. **Bir tane bulduysan hepsini tara** — adım adım
> gidilseydi beşi ayrı ayrı, sahada aranacaktı.

⚠️ `src/swarm_interfaces/INTERFACE_CONTRACT.md` bu dört konu için hâlâ
"RELIABLE, event" diyor. **Sözleşme sahadaki gerçeği yansıtmıyor**; kod kazanır.

### 2.11b 🔴 Bir arayüz SİLİNİRSE artımlı `colcon build` YETMEZ — üç uçak birden düştü

**29 Ağustos 2026'da yaşandı, sahada.** `swarm_interfaces/action/ExecuteFormation.action`
depodan silindi (kodda sıfır referansı vardı). `dagit.sh` dağıttı,
`colcon build` **"Finished <<< swarm_interfaces [4.70s] · 6 packages finished"**
dedi, hata vermedi. Konteyner yeniden başlatıldı ve **bizim on düğümümüzün
hepsi açılışta öldü.**

```
UnsupportedTypeSupport: Could not import 'rosidl_typesupport_c'
                        for package 'swarm_interfaces'
  -> ctypes ile dogrudan yuklenince gercek sebep cikti:
     undefined symbol: swarm_interfaces__action__execute_formation__send_goal__request...
```

**Mekanizma:** artımlı derleme C kütüphanesini (`libswarm_interfaces__rosidl_typesupport_c.so`)
ExecuteFormation olmadan yeniden ürettti, ama **Python uzantısını
(`swarm_interfaces_s__rosidl_typesupport_c.so`) yeniden üretmedi.** Eski uzantı
artık var olmayan sembolü aramaya devam etti → yükleme anında `undefined symbol`.

**Belirti neden yanıltıcı:** hata `swarm_interfaces`'i *import eden* her düğümde
çıkıyor, yani suçlu `formation_node`/`consensus`/`px4_bridge` sanılıyor. Hepsi
aynı satırla ölüyor. `colcon` da **başarılı** dedi.

**Süre farkı tek başına bir işaret:** artımlı derleme **4,7 sn**, temiz derleme
**1 dk 19 sn**. `swarm_interfaces` saniyeler içinde "derlendi" diyorsa
üretim adımlarını atlamıştır.

> **Kural:** `.msg` / `.srv` / `.action` **silindiğinde ya da yeniden
> adlandırıldığında** temiz derleme şart:
>
> ```bash
> docker exec <kon> bash -lc 'rm -rf /ws/build/swarm_interfaces /ws/install/swarm_interfaces &&
>   source /opt/ros/jazzy/setup.bash && cd /ws &&
>   colcon build --symlink-install --packages-select swarm_interfaces'
> ```
>
> Alan **eklemek** artımlıda sorun çıkarmıyor; **kaldırmak** çıkarıyor.
> `dagit.sh --paket` da bunu çözmez — o yalnız hangi paketin derleneceğini
> seçer, temizlik yapmaz.

### 2.11 `--symlink-install`'a rağmen Python kaynağı KOPYALANIYOR

17 Ağustos'ta ölçüldü: `colcon build --symlink-install` kullanılmasına rağmen
Python dosyaları `build/` altına **kopyalanıyor**, sembolik bağ kurulmuyor.

**Sonucu:** `rsync` ile `src/`'yi güncellemek **koşan kodu değiştirmiyor**.
`colcon build` şart. `dagit.sh` bunu zaten yapıyor, ama elle dosya kopyalayan
herkes bu tuzağa düşer — dosya yenidir, koşan kod eskidir, md5 karşılaştırması
`src/`'ye bakarsa "senkron" der.

İlgili: §1.17 (`build/lib/` bayat kopya tutuyor).

### 2.13 Konteyner açılışından DAKİKALAR sonra bile `agent_fsm` UNKNOWN'da olabilir

Ölçüldü (21 Ağustos): konteyner 00:33'te açıldı, 00:36'daki testte ylp00'un
`agent_fsm`'i hâlâ `state=0` (UNKNOWN) yayınlıyordu ve ancak ~00:37'de
IDLE'a geçti. UNKNOWN'dayken **görev olayı sessizce boşa gider**: arm yok,
adaylık yok, hata yok — test "hiçbir şey olmadı" diye biter.

Aynı anda öteki uçak (ylp02) çoktan hazırdı; yani "biri çalışıyorsa ikisi de
hazırdır" varsayımı yanlış. Testten önce **kendi iç status'unda** `state=1`
+ `healthy=true` bekle — `lider_kaybi_test.sh`'taki hazırlık kapısı örnek.

---

### 2.14 `FormationCommand`'da `offset_z`'yi atlamak SESSİZCE setpoint'i öldürür

`formation_node._slot_offset` (`formation_node.py:851`) **üç** ofset dizisini
birden istiyor ve **uzunluk kontrolü** yapıyor:

```python
if (i < len(msg.offset_x) and i < len(msg.offset_y)
        and i < len(msg.offset_z)):
```

`offset_x` ve `offset_y` doğru, `offset_z` boş bırakılırsa koşul düşer ve
düğüm `slot ofseti yok (yerel/komut); setpoint atlandi` der. Uyarı **ofsetin
hiç gelmediğini** ima ediyor, oysa ikisi gelmiştir — üçüncüsü eksiktir.
21 Ağustos'ta bu ayrım yarım saat kaybettirdi: komut kabul ediliyor
(`FormationCommand alindi: ... atama=[1, 3]` basılıyor) ama setpoint yine
çıkmıyordu.

Normal işleyişte görünmez, çünkü ofsetleri **köprü** hesaplayıp mesh
paketine koyuyor (`esp32_bridge._on_formation_out`) ve üçünü de doldurur.
Tuzak yalnız `FormationCommand`'ı **elle** yayınlarken çıkar — teşhis
betikleri ve gözlem zinciri bunu yapıyor.

---

### 2.15 🔴 Mesh linki TEK YÖNLÜ ölebilir — kaçınma sessizce KÖR kalır

**21 Ağustos akşamı, uçuşta ölçüldü.** Operatör ylp02'yi kumandayla ylp00'a
**3 metreye** kadar yaklaştırdı (irtifalar 10 m ve 8 m).
`collision_avoidance` **hiç tetiklenmedi**. Sebep kaçınma algoritması değil —
**ylp00 komşusunu görmüyordu.**

Kayıttan iki tarafı yan yana koyunca:

| | kendi durumu | komşudan aldığı |
|---|---|---|
| **ylp02** | maks 0,2 sn | **maks 0,4 sn** ✅ |
| **ylp00** | maks 0,2 sn | **MAKS 46,4 sn** 🔴 |

`/swarm/public/drone3/status` ylp00'da normalde 10 Hz akıyor (ortanca
0,10 sn · p90 0,20 sn), sonra **tek seferde 46,4 saniye** hiçbir şey. Aynı
anda ters yön (ylp00 → ylp02) **kusursuz** çalışıyordu.

🔴 **Tek yönlü mesh kopmasının sahada kanıtı.** Aynı gün sabah `consensus`
kodunda teorik olarak bulunmuştu (P1.14: *"asimetrik linkte iki lider kalıcı
olabilir"*); akşam gerçekleşti ve bu kez **çarpışma önlemeyi** kör etti.

**Neden fark edilmesi zor:** uçan uçağın kendi telemetrisi kusursuz akar, YKİ
onu sorunsuz görür, komşusu da onu görür. **Yalnız bir yön ölür ve o yönü
yalnız kör kalan uçak bilir.**

**Yakalayan şey:** `esp32_bridge`'in DURUM bayatlık dedektörü (20 Ağustos'ta
P0.14(b) için eklendi):

```
[WARN] drone3: DURUM paketi 46.8 sndir gelmedi (esik 5.0) —
       healthy DUSURULDU. POSE akiyor olabilir ama saglik bilgisi bayat.
```

**Yakalamayan şey:** `collision_avoidance` bunu yalnız `skip_stale` sayacında
**sessizce** sayıyor; 5 saniyede bir basılan tanı satırının içinde kayboluyor.
47 saniyelik körlük **hiçbir alarm üretmedi**.

**Doğru tarafı:** CA bayat veriyle *yanlış yöne itmedi* — veri yoksa hiç
itmiyor (`neighbor_rx_stale_s=1.5`). Arıza biçimi "yanlış koruma" değil
"koruma yok". Doğru takas, ama koruma yok yine de koruma yok.

**Ne yapılmalı:** `YAPILACAKLAR.md` P0.15.

---

### 2.16 Bir düğümü öldürmek TEK YÖNLÜ kopmayı taklit ETMEZ

22 Ağustos'ta operatör yakaladı ve haklıydı. Tek yönlü mesh kopmasını
(§2.15) sınamak için ylp02'nin `esp32_bridge`'ini öldürüyordum. Ama:

| | gerçek arıza (21 Ağu) | düğümü öldürmek |
|---|---|---|
| ylp00 → ylp02'yi duyuyor mu | ❌ hayır | ❌ hayır |
| **YKİ ylp02'yi görüyor mu** | **✅ EVET, sapasağlam** | ❌ ekrandan kayboluyor |

Gerçek arızada ylp02 → baz yönü **çalışmaya devam etti**; operatör onu
ekranda sağlıklı görüyordu. Alarmın asıl değeri tam orada: *ekranda
sorunsuz görünen bir uçağa karşı komşusunun koruması yok.* Düğümü
öldürünce o hâl **hiç oluşmuyor** — uçak zaten kayboluyor, operatör
"tabii ki göremiyor" diyor.

**Doğru benzetim ALIM tarafında olmalı:** `esp32_bridge`'e
`sahte_kayip_ajanlar` parametresi eklendi (varsayılan boş = etkisiz).
Yalnız o uçağın **aldığı** paketleri düşürür; uçak kendi yayınını normal
sürdürür, baz onu görür.

```bash
docker exec drone1 ros2 param set /esp32_bridge sahte_kayip_ajanlar "[3]"   # kor
docker exec drone1 ros2 param set /esp32_bridge sahte_kayip_ajanlar "[0]"   # normal
```

⚠️ **Parametre çalışma anında okunmalı.** İlk yazımda yalnız açılışta
okunuyordu: `ros2 param set` *"successful"* diyor, düğüm eski değeri
kullanmaya devam ediyor ve benzetim **sessizce hiçbir şey yapmıyordu**
(kanca sayacı 0 kaldı). `add_on_set_parameters_callback` ile düzeltildi.

---

### 2.17 🔧 Pi ölü bulunduğunda: ÜÇ YERE BAK, sebep ayırt edilebilir

22 Ağustos'ta kuruldu ve **sahada sınandı** (`sysrq` ile kasıtlı panik).
Öncesinde yazılım ölümü ile güç kesilmesi **birebir aynı görünüyordu**;
artık ayırt ediliyor.

**Sırayla üç yere bak:**

```bash
# 1. Cekirdek son ne dedi  (BOS olmasi da BILGIDIR — asagi bak)
ls  ~/yelpence_ws/gunluk/cokme/
tail -25 ~/yelpence_ws/gunluk/cokme/dmesg-ramoops-0

# 2. Gerilim olumden once ne yapiyordu  (10 sn'de bir ornek)
tail -20 /var/log/yelpence_izle.log

# 3. Sistem gunlugu nerede kesildi
journalctl -b -1 --no-pager | tail -20
```

**Tablo:**

| | izleme logu (`v=`, `thr=`) | `gunluk/cokme/` | teşhis |
|---|---|---|---|
| Yavaş gerilim düşüşü | `v=` **düşüyor**, `thr` bayrağı yanmış | boş | **güç — kademeli** (BEC, gevşek konnektör, biten pil) |
| **Ani kesilme** | son örnek **normal**, sonra hiçbir şey | **boş** | **güç — ani** (kopan kablo, çıkan konnektör) |
| Çekirdek paniği | gerilim **normal** | **yığın izi VAR** | **yazılım** — çağrı yığını suçluyu gösterir |
| Temiz kapatma | normal | boş | `journalctl`'de PID 1'den shutdown dizisi görünür |

⚠️ **`v=` uydurma değil:** `vcgencmd pmic_read_adc EXT5V_V` — Pi'ye **giren**
5 V beslemesi, PMIC'in kendi ADC'sinden. `thr` ise
`vcgencmd get_throttled`: bit 0 = *şu an* düşük gerilim, bit 16 = *açılıştan
beri oldu mu*. `thr=0x0` → hiç düşük gerilim yaşanmamış.

**Ani kesilmenin doğrudan izi YOKTUR — olamaz da:** işlemci o anda durur,
yazacak zaman yoktur. Ama **imzası** vardır: gerilim son ana kadar normal +
çökme izi boş + günlük aniden kesik. Bu üçlü birlikte "güç gitti" demektir.
**İzin yokluğu da bir bilgidir** — yeter ki iz tutulabiliyor olsun.

🔴 **Pi öldüğünde GÜCÜ KESME.** `ramoops` izi RAM'de duruyor; güç tamamen
giderse **silinir**. `kernel.panic=10` sayesinde gerçek bir panikse Pi
10 saniyede kendi döner ve izi getirir. Dönmezse bile önce gücü kesmeden
yeniden başlatmayı dene.

**Örnek — 21 Ağustos ylp00 ölümü** (bu düzenek kurulmadan önce): son
örnekte `thr=0x0` idi, yani açılıştan beri hiç düşük gerilim olmamıştı.
Buradan *"kademeli gerilim düşüşü DEĞİLDİ"* sonucu çıkarılabildi — ama ani
kesilme mi yazılım mı, ayırt edilemedi. Çökme izi olmadığı için.
Bkz. `YAPILACAKLAR.md` P0.17.

---

### 2.18 🔴 Kaçınma, uçağın YAPAMAYACAĞI ivme isteyebilir — eğim tavanına bağla

**22 Ağustos 2026, uçuşta.** Operatör: *"baya bildiğin sağ sol yaptı,
devrilecek gibi."* Konuma ve hıza bakıp "sakin" demiştim — **yanlış yere
bakmıştım.** Operatör eğim açılarını söyledi ve haklıydı:

| evre | roll aralığı | genlik | **maks eğim** |
|---|---|---|---|
| asılı (önce) | −5,0 … +6,1 | 11° | 11,6° |
| **KAÇIŞ** | **−24,7 … +28,3** | **53°** | **34,0°** |
| dönüş | −15,7 … +5,2 | 21° | 22,0° |
| asılı (sonra) | −2,7 … −0,3 | 2° | 4,6° |

🔴 **Kök neden:** `ca_core.CaParams` ivme sınırları `ucus_ayarlari.py`'ye
**hiç bağlanmamıştı**. Özgün tasarımdan kalma sabitlerdi:

```
slew_normal    =  4.0 m/s2  ->  22.2 derece
slew_emergency = 30.0 m/s2  ->  71.9 derece   <-- IMKANSIZ
```

`slew_emergency`, komşu `hard`ın içine girince devreye giriyor. Operatör
6,14 m'ye geldi, `hard=6.0` — tam devreye girdi. **Uçak 72 derece
eğilemez**; elinden geleni yaptı (34°), yetişemedi, komut değişti, ters
yöne eğildi. Yalpa bu — arıza değil, **imkânsız bir komutu takip etme
çabası.**

⚠️ **`CLAUDE.md` §8 bunu zaten söylüyordu:** *"Açıları elle ayarlama. Eğim
tavanı ivmeden türetiliyor (`a = g·tan(θ)`)"*. Hız, ivme, eğim hepsi
`ucus_ayarlari.py`'de türetiliyordu — **kaçınma hariç.** Bir modülün
"kendi varsayılanı" olması, o varsayılanın fizikle uyumlu olduğu anlamına
gelmiyor.

**Ders:** uçağı hareket ettiren **her** düğümün ivme/hız sınırı
`ucus_ayarlari.py`'den türetilmeli. Yeni bir düğüm açarken ilk soru:
*"bu düğüm ne kadar ivme isteyebilir ve o kaç derece eğim eder?"*

**Nasıl fark edilir:** konum ve hız verisi bunu **gizler** — uçak yerinde
durup sallanabilir. `/mavros/imu/data` quaternion'undan roll/pitch çıkar,
evrelere göre genlik karşılaştır. Asılı evre ile kaçış evresi arasında
3 kattan fazla fark varsa sorun vardır.

---

### 2.19 🔴 JUMPER konnektör: YERDE kusursuz, HAVADA bozuk — P0.15'in kök nedeni

**22 Ağustos 2026'da bulundu ve iki uçuşla doğrulandı.** 21 Ağustos'ta
ylp00'ın komşusunu **46,4 saniye** hiç görmemesinin (§2.15) sebebi buydu:
ESP32 ile Pi arasındaki UART kablosunun **ESP ucundaki jumper konnektörü**
marjinal oturuyordu.

```
ylp00 :  19.007 paket  ->  crc_fail = 868   (hepsi UCUS sirasinda)
ylp02 :  19.505 paket  ->  crc_fail =   0   (ayni ucus, ayni kod)
yerde :  ~19.000 paket ->  crc_fail =   0   (her iki ucakta)
```

**Neden bu kadar sinsi — yerde HİÇBİR test üretmiyor:**

| denenen | sonuç |
|---|---|
| kabloyu elle bükmek, konnektörleri kımıldatmak (120 sn) | 0 |
| pervanesiz motorlar (180 sn) | 0 |
| **pervaneli**, kalkış eşiği altı gaz (180 sn) | 0 |
| uçağı eğmek, kolları bükmek, ESP'ye bastırmak | 0 |
| **UÇUŞ** (motorlar yüklü, titreşim) | **5,95/s** |

Yani rölanti akımı da, elle bükmek de yetmiyor; **yalnız uçuş titreşimi**
üretiyor. Yerdeki her negatif sonuç yanıltıcıdır.

> #### 🔑 CRC hatası nereden geldiğini KESİN söyler
>
> Mesh'te **iki bağımsız CRC katmanı** var ve ikisini de ESP doğruluyor:
>
> ```
> radyo   ESP-NOW / 802.11 FCS  +  mesh CRC16 (_recv_isle)
>              -> bozuk cerceve ESP'de ATILIR, Pi'ye hic ulasmaz
> UART    cobs_cerceve_coz — TIP+ID dahil CRC16 (uart_cobs.h)
>              -> Pi'de sayilan crc_fail YALNIZ BURADAN gelebilir
> ```
>
> Gönderen uçağın Pi→ESP hattı bozulsaydı, o çerçeve **gönderilmeden**
> reddedilirdi (eksik paket görünürdü, bozuk değil). Havada bozulsaydı alıcı
> ESP atardı. **Dolayısıyla Pi'de `crc_fail` artıyorsa suçlu, o uçağın KENDİ
> ESP→Pi UART hattıdır.** Bu çıkarım şüpheliyi tek uçağa ve tek kabloya indirir.

**Neden TEK YÖNLÜ:** gevşek olan tek pin ESP'nin TX'i. Uçağın **aldığı**
bozuluyor, **gönderdiği** başka telden gidiyor ve sağlam. Üç ayrı olayda
(21 Ağustos + 22 Ağustos'ta iki uçuş) hep aynı yön öldü: **ylp02 → ylp00**.

**Elenenler — bir daha araştırılmasın** (hepsi ölçüldü):
anten yönelimi · LiPo pilin araya girmesi (180°'de maks boşluk 0,40 → 0,31,
yani **iyileşti**) · mesafe (3,7 / 6 / 16 m) · FlySky vericisi (%5-7 gerçek
ama iki mertebe küçük, kapatınca geri geliyor) · besleme gerilimi (±0,02 V
düz) · ısınma (uçuşta **düşüyor**) · irtifa farkı · CPU yükü (yerde daha
yüksekti) · `collision_avoidance` (iki uçakta da aynı kod, birinde 0 hata).

**Doğrulama:** konnektör elle oturtuldu → tek uçaklı uçuş **0**, iki uçaklı
uçuş **0**, `alim_ok` hiç düşmedi (önce 13,5 → 7,6 düşüyordu).

⚠️ **Elle sıkıştırmak kalıcı çözüm değil** — jumper sürtünmeyle tutar, kilit
ve gerilim boşaltma yoktur, titreşimde yeniden gevşer. Kalıcı yol: **lehim +
gerilim boşaltma** ya da **JST-GH** kilitli konnektör. Aynı dizilim diğer
uçaklarda da var; birinde sıfır hata çıkması "sağlam" değil **"henüz
gevşememiş"** demektir.

**Teşhis aracı hazır:** `crc_fail`, `mesh_diag` içinde 1 Hz akıyor ve her
uçuş kaydında duruyor. Uçuş sonrası tek bakışta kontrol edilebilir —
**yerdeki değeri 0 olmalı, uçuştaki de 0 kalmalı.**

---

### 2.20 🔴 10 Hz kaynağı 10 Hz kapıdan geçirmek örneklerin ÇEYREĞİNİ yutar

**23 Ağustos 2026'da ölçüldü.** Aylardır "mesh %30 kaybediyor" sanılan şeyin
kaynağı radyo değil, kendi köprümüzdü.

`esp32_bridge._on_own_status` POSE'u 10 Hz tavanla mesh'e veriyordu:

```python
if now - self._son_pose_gonderim_ts >= self._pose_periyot_s:   # 0.100
    self._son_pose_gonderim_ts = now
```

Kaynak (`agent_fsm` iç durum yayını) **tam 10,00 Hz** ama ±3 ms jitter'lı.
Ölçüldü: ardışık boşlukların **%51,4'ü 0,100 s'nin ALTINDA**. Eşiğin altına
düşen örnek tamamen düşüyor — POSE kuyruklanmıyor, gönder-ya-da-atla.

```
kaynak                       10,00 /s
Pi->ESP yazilan (once)        8,08 /s (ylp00)   8,44 /s (ylp02)
karsi tarafin aldigi          7,09 Hz           7,11 Hz
  -> HAVADAN kayip ~%0-4, KAPIDAN kayip ~%26
```

**Düzeltme tek sabit:** `_pose_periyot_s = 0.095`. Kapı kaynakla vuruşmaz,
hız kaynağın kendi 10 Hz'i olur. Sonuç ölçüldü:

```
Pi->ESP yazilan  11,91 /s · 11,94 /s      (gonderim_drop = 0)
karsi tarafin aldigi 10,46 Hz · 10,89 Hz  (en buyuk bosluk 0,41 -> 0,31 s)
```

⚠️ **Faz biriktirme (`son += periyot`) SEÇİLMEDİ**: kaynak bir an duraklarsa
birikmiş tikleri peş peşe gönderip UART'a patlama yapar. Eşiği kaynağın
altına çekmek hiçbir koşulda kaynaktan hızlı gönderemez.

> **Genel ders:** periyodik bir kaynağı **aynı periyotlu** bir kapıdan
> geçirme. Kapı ya kaynaktan hızlı olmalı ya da faz kilitli. Aradaki jitter
> hangi tarafa düşerse örneği o yutar ve hiçbir sayaç artmaz.

### 2.21 🔴 İki uçağın `pos_z`'si AYNI REFERANSTA DEĞİL

**23 Ağustos 2026.** Dikey çarpışma önleme yazılırken bulundu; o güne kadar
uykudaydı çünkü `rel_z` yalnız 3B mesafeyi biraz kaydırıyordu.

| | kaynak | sıfır noktası |
|---|---|---|
| **kendi** `pos_z` | MAVROS odometry (EKF yerel NED) | EKF açılış origin'i — **boot'a bağlı ~10 m kayar, uçuş boyunca sürer** |
| **komşunun** `pos_z` | mesh POSE → `-(alt_amsl − home_amsl)` | komşunun **kendi kalkış noktası** |

`rel_z = komsu.pos_z - ben.pos_z` bu ikisini karıştırıyordu. Yatay tarafta
aynı tuzağın uyarısı `komsu_adaptoru.py` başlığında upuzun yazılı; dikeyde
yoktu. Aynı hata `esp32_bridge`'de POSE için bir kez yaşanmış ve orada
düzeltilmişti (`:1697` — *"yerdeyken YKİ 10 m gösteriyordu"*).

**Doğrusu: iki tarafta da GÖNDERENİN formülünü kullan.**

```python
ben_h  = ben.alt_amsl_m - ben.home_alt_amsl_m
komsu_h = -komsu.pos_z
rel_z  = ben_h - komsu_h
```

Geriye kalan tek hata iki kalkış noktası arasındaki **kot farkı**. Yer
testinde ölçüldü (G0-1): ylp00 −0,428 / ylp02 +0,397 — zıt işaretli, 3 cm
farkla tutarlı. 0,4 m'nin kaynağı ylp00'ın **bayat home kaydı**
(`alt_amsl 1219,31` vs `home 1219,72`), kot farkı değil.

⚠️ **CA'nın irtifa kapısı da aynı sebeple `-pos_z`'den bu formüle çevrildi** —
EKF yukarı kayarsa uçak YERDEYKEN kapı açılırdı.

**Ölçme aracı:** `deploy/rpi/teshis/g0_dikey_datum.py`. İki uçak yerdeyken
`|rel_z| < 0,5 m` olmalı.

### 2.22 🔴 PX4 dikey hız komutunu SESSİZCE kırpar — `MPC_Z_VEL_MAX_UP`

**23 Ağustos 2026'da uçaktan okundu.** Dikey kaçışa 3,0 m/s yazılacaktı;
uçaklarda tavan **1,2 m/s** çıktı.

```
MPC_Z_VEL_MAX_UP  = 1.2     MPC_ACC_UP_MAX    = 4.0
MPC_Z_VEL_MAX_DN  = 1.5     MPC_ACC_DOWN_MAX  = 3.0
```

Üstünü yazmak demek: **ayar 3,0 gösterir, log 3,0 gösterir, uçak 1,2
tırmanır.** `MPC_TILTMAX_AIR`'ın kodda 30 varsayılıp ylp00'da 45 çıkmasıyla
birebir aynı sınıf.

**Kapatıldı:** dört tavan `ucus_ayarlari.py`'ye girdi ve denetim eklendi —
kaçınmanın dikey hızı PX4 tavanını aşarsa **HATA** veriyor. Ayrıca
"merdiven kurulma süresi > çatışma süresi" uyarısı da orada.

> Kural: uçağa komut veren her yeni büyüklük için PX4'ün karşılık gelen
> tavanını **oku ve tek kaynağa yaz**. "Varsayılan şudur" bu depoda iki kez
> yanlış çıktı.


### 2.23 🔴 MAVROS'un GCS yayın hattı HER AÇILIŞTA ZAR — tutmazsa saatte yüzlerce MB

`gcs_url=udp-b://:14555@14550` ile açılan GCS hattı bazen kuruluyor, bazen
kurulamıyor. Kurulamazsa **ilk saniyeden** itibaren şunu basar ve
kendiliğinden **düzelmez**:

```
Warning: mavconn: udp1: sendto: Network is unreachable, retrying
         at line 325 in ./src/udp.cpp
```

Ölçülen bedel (26 Ağustos 2026, tek oturum):

| Açılış | `mavros.log` | hata satırı |
|--------|--------------|-------------|
| ylp00 18:35 | **876 MB** | 8.275.479 |
| ylp02 19:49 | 289 MB | 2.805.206 |
| ylp01 19:51 | 131 MB | 1.267.045 |

Tarihsel tepe: `mavros.log` tek başına **18,64 GB** (`baslat.sh` başındaki not).

**Uçuşu etkilemez** — mesh seri hattan gider, WiFi'ye bağlı değildir. Asıl zarar
**teşhis**: `mavros.log` uçuş sonrası bakılan kaynaktır ve gürültü onu yutar.
Log döndürme devreye girince açılış satırları tamamen silinir — 26 Ağustos'ta
ylp01'in logunun başı zaten yok olmuştu.

**Uçağa özgü DEĞİL:** üçünün de hem temiz hem kirli açılışları var.

**Elenenler** (hepsi aynı gün ölçüldü):
- `gcs_url` farkı yok — üçünde birebir aynı
- ağ modu üçünde de `host`; arayüz, rota aynı; `14555` üçünde de bağlı
- **yayın adresi sağlam**: ylp02'den `10.x.x.255`, `172.17.255.255` ve
  `255.255.255.255` hedeflerine test paketi **sorunsuz gitti** → yönlendirme
  ya da `docker0` sebep değil
- **P0.13'ün ağ bekleme döngüsü yetmiyor**: ağ tamamen ayaktayken elle yapılan
  restart'lar (19:49, 19:51) da bozuk çıktı

🔴 **Kök neden hâlâ bilinmiyor** — `mavconn/udp.cpp` okunmalı. Bilinen tek
çözüm yeniden başlatmak; 26 Ağustos'ta iki uçakta da temizledi.

**Bugünkü koruma** (`baslat.sh`, 26 Ağu `dd5a1e6`): mavros açıldıktan 15 sn
sonra hata sayılır; varsa mavros **bir kez** yeniden başlatılır ve yalnız
**YENİ** satırlar sayılır. Yine bozuksa gürültülü uyarı basılıp
`/ws/mavros_gcs_bozuk` bayrağı bırakılır; `drone_bul.sh --durum` onu
`>> SORUN` satırı olarak gösterir. Konum bilinçli: o noktada `gps_saat` ve
sürü düğümleri henüz açılmamıştır, yani mavros'a bağlı hiçbir şey yoktur.

---

## 3. PX4 ve uçuş davranışı

### 3.1 Kumanda AÇIKKEN sürü otonomisi TAMAMEN durur — ve loglanmaz

Kumanda açıkken PX4 **POSCTL**'e geçiyor.
`PILOT_FLIGHT_MODES = {1,2,3,9,10}` (MANUAL/ALTCTL/POSCTL/ACRO/STABILIZED)
olduğu için `pilot_override_active = true`, o da `autonomous_control_paused`
yapıyor ve `agent_transitions.py` ilk satırında duruyor:

```python
if ctx.autonomous_control_paused or ctx.hold_active:
    return None
```

**Hiçbir geçiş olmuyor, hiçbir yere loglanmıyor.** Ölçüm: görev başlatma
olayı 14 kez teslim edildi, `state` IDLE'da dondu.

Tasarım doğru (pilotla kavga etmesin). Operasyonel sonucu net: **otonom uçuş
için PX4 pilot olmayan bir modda olmalı** — OFFBOARD(4), AUTO_MISSION(5),
AUTO_LOITER(6). `AUTO.LOITER`'a alınca otonomi anında devam etti.

> Kumandayı **kapatmak** çözüm değil — RC kayıp failsafe'i devreye girer ve
> ylp00'da o failsafe kill tetikliyordu (§0.2). Doğru yol kumandanın mod
> switch'ini pilot olmayan bir moda almak.

*(30 Temmuz 2026)*

### 3.2 FCU'yu doğrudan arm etmek sürü FSM'ini ARMED yapmaz

ylp00 MAVROS'tan gerçekten arm edildi (`armed: true`) ama `AgentStatus.state`
**IDLE'da kaldı** ve lider seçimi olmadı.

Sebep tasarımda: `_from_idle` geçişi `ctx.pending_state == ARMING` istiyor ve
bunu **yalnız `EVENT_MISSION_STARTED`** kuruyor. QGC'den, MAVROS'tan **veya
kumandayla** arm etmek FSM'i atlar.

Sonuç: pilot kumandayla arm ederse sürü yığını kendini armlı saymaz →
`ELIGIBLE_STATES` sağlanmaz → **lider seçilmez → formasyon mesh'e çıkmaz.**
Uçuş prosedürü buna göre yazılmalı: arm **görev başlatma olayı üzerinden**
gelmeli. *(30 Temmuz 2026 — yarışma açısından en kritik operasyonel bulgu)*

### 3.3 Tezgâhta görev başlatmak bir KALKIŞ denemesidir

FSM `ARMED`'a girince PX4'e `offboard` veriyor, `px4_bridge` sürekli offboard
setpoint yayınladığı için PX4 kabul ediyor, ardından `ARMED → TAKEOFF` koşulu
sağlanıyor ve `takeoff:<irtifa>` gidiyor. **Pervane takılıyken bu gerçek bir
kalkıştır.**

Bugün `~/yelpence_ws/yer_testi` bayrağı tam bunun için var: uçak ARM olur,
kalkmaz (bkz. `DURUM.md` §3).

### 3.4 OFFBOARD'dayken disarm REDDEDİLEBİLİR

OFFBOARD konum tutmak hover gazı ister (~%40-50); PX4 bunu görüp iniş
dedektörüyle "havadayım" der ve normal disarm'ı reddeder
(`success=False, result=1`).

**Önce `AUTO.LOITER`'a al, sonra disarm et.** Son çare zorla disarm
(`param2=21196`) yalnız YKİ'nin operatör yolunda var; otonom yığın **asla**
kullanmıyor.

> Pervanesiz tezgâh testinde şaşırtıcı: dron "uçuyor" sanılır, motorlar
> hızlanır, disarm tutmaz. Kumandayı elde tut.

Bugünkü yer testi çıkışı: **kumandadan kill switch** (`DURUM.md` §3).

### 3.11 GUIDED arm eden uçak OFFBOARD'a girer — GUIDED disarm ARTIK TUTMAZ

20 Ağustos yer testinde yaşandı: `POST /api/guided/3/disarm` gönderildi,
uçak **disarm olmadı**, operatör kumandadan kesmek zorunda kaldı.

Zincir: `guided arm` yalnız arm etmiyor — `esp32_bridge` önce
`_guided_string('offboard')` yolluyor. PX4 OFFBOARD'da konum tutmak için
hover gazı ister; iniş dedektörü "havadayım" der ve **normal disarm'ı
reddeder** (§3.4). Pervanesiz tezgâhta bu daha da belirgin: konum
denetleyicisi irtifayı tutmaya çalışıp integrali sarıyor.

> **Kural: guided ile arm ettiysen yer testinden çıkış KUMANDADAN KILL.**
> Yazılım disarm'ını dene, ama ona güvenme ve **operatörden kill switch'i
> elinde tutmasını iste.** `DURUM.md` §3 bunu zaten söylüyordu; 20 Ağustos'ta
> uyulmadı ve bedeli operatörün kumandaya koşması oldu.

⚠️ **İkinci ders — komutun CEVABINI OKU.** O gün disarm `curl ... >/dev/null`
ile gönderildi, yani PX4'ün reddi hiç görülmedi ve test "disarm oldu"
varsayımıyla sürdü. Aynı oturumda üç kez araç çıktısı gizlendi ve üçünde de
yanlış sonuca gidildi (`ros2 topic hz`, `durum_enjekte.sh`, bu). Bu belgenin
§1'i tam olarak bunun için var: **ölçüm aracının kendisi yalan söyler —
susturursan hep yalan söyler.**

### 3.5 PX4 ARMLIYKEN yerde OFFBOARD'a geçmez

Tek değişkenli deney:

| durum | `offboard` komutu | sonuç |
|---|---|---|
| disarm + kumanda kapalı | tek sefer | OFFBOARD ✓ |
| disarm + kumanda açık | tek sefer | OFFBOARD ✓ |
| **armlı** | tek sefer | **reddedildi** ✗ |

FSM önce armlayıp sonra mod istediği için dron `ARMED`'da sonsuza kadar
takılıyordu. **Düzeltildi** (`ea80852`): `px4_bridge` artık `arm` komutunda
önce OFFBOARD istiyor, aktifleşince ARM gönderiyor (ölçülen: 72 ms).
Sıralama kısıtı PX4'e özgü olduğu için FSM'e sızdırılmadı.

Tuzak olarak duruyor çünkü **PX4'ün davranışı hâlâ bu** — benzer bir yol
yazan herkes aynı duvara çarpar. *(30 Temmuz 2026)*

### 3.6 Yerde disarm haldeyken lider seçimi OLMAZ — ve bu doğrudur

`ELIGIBLE_STATES = {ARMED, TAKEOFF, IN_SWARM, EXECUTING_TASK}`; yerdeki dron
`IDLE`. Ölçüldü: iki dronda `consensus_node` 12 sn koştu, **seçim sayısı 0.**
"Consensus bozuk" diye aramaya başlamadan önce bunu hatırla. Yerde test için
tek yol `AgentStatus` enjekte etmek. *(30 Temmuz 2026)*

### 3.7 Kalkışta yatay KONUM TUTMAK uçağı devirir — hız sıfırlama devirmez

|  | ne yapar | kestirim sıçrarsa |
|---|---|---|
| **konum tutma** (`_MASK_POSITION`) | "şu noktada olmalıyım" | gerçek olmayan hatayı kovalar, **eğilir** |
| **hız sıfırlama** (`_MASK_KALKIS`) | "yatayda durgun olayım" | kovalanacak birikmiş hata yok, eğim küçük |

1 Ağustos devrilmesinde: uçak hiç kımıldamadan konum kestirimi **1.42 m**
kaydı → `MPC_XY_P` ile ~1.3 m/s hız talebi → ~2.4 m/s² ivme → **~14° eğim**
→ yerde, kalkış itkisindeki uçakta pervane yere girdi.

`_MASK_KALKIS` (`mavros_command_sender.py`): konum X/Y **yok say**, hız X/Y
**kullan**, konum Z kullan, yaw kullan. Kilit, kalkışın başladığı z'den
itibaren `kalkis_kilit_irtifa_m` (2.5 m) yükselince açılır ve yatay çapa o an
**bir kez** yenilenir. Sahada ölçülen sürüklenme: **0.14 m.**

Eğimli zeminde de doğrusu bu: hız sıfırlama eğimin ürettiği şeye — hıza —
doğrudan tepki verir, hatanın birikmesini beklemez. *(1 Ağustos 2026)*

### 3.8 İçeride arm olmuyorsa sebep GPS doğruluğu — kod değil

|  | eşik | ylp00 | ylp01 |
|---|---|---|---|
| `EKF2_REQ_EPH` | **3.0 m** | `h_acc` 3.09 m ✗ | `h_acc` 3.43 m ✗ |

Zincir: `h_acc > EKF2_REQ_EPH` → EKF yatay GPS'i **hiç füzyona sokmaz**
(`pos_horiz_abs`, `pos_horiz_rel`, `velocity_horiz` hepsi false) →
`estimator_ok=false` → *"Konum tahmini (EKF2) hazır değil"* → `ready_to_arm=false`.

`gps_glitch_status_flag: false` — yani **arıza değil**, sadece yeterince
doğru değil. Çözüm açık alana çıkmak.

> **`EKF2_REQ_EPH`'i büyütmek arm'ı açar ama kötü konumla uçmak demektir;**
> otonom formasyonda çarpışma riski doğurur. Eşiği gevşetme.

*(30 Temmuz 2026)*

### 3.9 `rc_link_ok` kumandanın açık olduğunu göstermez

Kumandalar kapalıyken ölçüldü: `rc_link_ok = True`, `/mavros/rc/in` akıyor,
RSSI sabit 41, kanallar donmuş. Alıcı "son değerleri tut" failsafe'inde,
PX4 kumandanın kapandığını **göremiyor.** Bu bayrak ön koşul olarak
kullanılamaz.

Ön kontrol PX4'ün kendi hükmüne bağlanmalı: `ready_to_arm`,
`kill_switch_active`, `rc_signal_failsafe_active`, `failsafe_active`.
*(1 Ağustos 2026)*

### 3.10 `UAVCAN_*` reboot ister, reboot MAVLink yayın hızlarını sıfırlar

FCU reboot'undan sonra `mesaj_hizlari.py` tekrar koşmalı. Konteyner restart
bunu zaten sırayla yapıyor.

---

### 3.12 Dikey kaçınmada çatışma ölçütü YATAY mesafedir — 3B DEĞİL

**23 Ağustos 2026, tasarım kararı.** Sezgiye ters geldiği için burada.

Dikey yol vermede "çatışma var mı" sorusu **yalnız yatay** mesafeye bakar
(giriş `d0`, çıkış `d0 + 0,5`). 3B mesafeye bakılsaydı şu döngü oluşurdu:

```
ucak tirmanir -> 3B mesafe buyur -> catisma biter -> iner
             -> mesafe kuculur -> yine tirmanir     ... SALINIM
```

Yatay mesafe tırmanmaktan etkilenmediği için tetik kararlı kalıyor; çatışma
ancak uçaklar gerçekten **yanal** ayrıldığında bitiyor.

**Güvenlik açısından yeterli:** çıkış 4,5 m *yatay* istiyor ve 3B mesafe
yataydan asla küçük olamaz. Yani iniş sırasında irtifalar ne olursa olsun
arada en az 4,5 m var.

**Yan etkisi (bilinmeli):** dikeyde ayrık ama yatayda yakın iki uçak
"çatışma sürüyor" sayılır ve kaçan uçak **nominaline dönmez**. Sıkı
formasyonda (aralık ≤ `d0`) merdiven kalıcı hâle gelir — `collision_avoidance`
bunu açılışta uyarı olarak logluyor.

**Yararlı bir sonucu:** komşu tam altına park ederse yatay mesafe ~0 kalır,
çatışma hiç bitmez ve kaçan uçak **üstüne inmez**. Yerde ölçüldü: komşu
0,3 m yatayda iken uçak 35 saniye boyunca 13,00 m'de kaldı.


### 3.13 🔴 Benzetim "görevi" HIZ komutu sanır, guided gerçekte KONUM hedefidir

**23 Ağustos 2026.** Dikey kaçınmanın ilk uçuşunda bir davranışı
benzetimle açıklamaya çalışırken çıktı ve **iki ayrı benzetim denemesi de
gerçeği üretemedi.**

`ca_benzetim.py`'de her uçağın "görevi" bir **hız** vektörü (`vf`). Kaçınma
yetkiyi bırakınca uçak o hızı uygular — asılı durmada bu **sıfır**, yani
uçak **yerinde kalır**.

Sahada guided asılı durma bir **konum** setpoint'i. Kaçınma yetkiyi
bırakınca PX4 o hedefi görür ve uçağı oraya **aktif olarak geri çeker**
(`MPC_Z_VEL_MAX_DN` = 1,5 m/s'ye kadar).

```
BENZETIM : yetki birakildi -> vz = 0        -> ucak DURUR
SAHA     : yetki birakildi -> konum hedefi  -> ucak GERI CEKILIR
```

Yani "yetkiyi bırakmanın bedeli" benzetimde **sıfır**, sahada **3 metre**.
Bırakma/tutma kararlarını benzetimle sınamak bu yüzden yanıltıcı.

**Kural:** kaçınmanın *yetki devri* davranışını benzetimle doğrulama;
benzetim yalnız **manevra** sorularını (ne kadar, ne kadar hızlı, ne kadar
ayrım) cevaplayabilir.

### 3.14 Tetik sınırı pilotun GÖZLE kestirebileceğinden dar

**23 Ağustos 2026, ilk uçuşta yaşandı.** Operatör ylp00'ı "risk alanında
tuttuğunu" söyledi ve ylp02'nin yo-yo yaptığını gözledi. Kayıttan ölçüldü:

```
4.5 m sinirindan gecis sayisi : 4   (iki tam giris-cikis)
icerideyken d_xy : 3.25 - 3.67 m    -> ylp02 irtifasini TUTTU
disariya cikis   : 4.91 ve 5.01 m   -> donus BURADA basladi
```

Sistem doğru davranmıştı; yo-yo **operatör kaynaklıydı**. "İçerideyim" ile
"çıktım" arasındaki fark **yalnız 1,2 m** (3,3 ↔ 4,5 m) — bir uçağı
uçururken diğerini gözle takip ederken ayırt edilemiyor.

**İki sonucu var:**
1. Kaçınma testlerinde "bölgede tuttum" beyanı **ölçümle doğrulanmalı**;
   gözlem tek başına yeterli değil.
2. Çıkış histerezisi (`hist_m`) dar olduğunda sistem pilotun gözünde
   kararsız görünür, oysa değildir. (`git show 783afab:docs/CA.md` §7.2)


### 3.15 🔴 `MAV_SYS_ID` bozulması — üç belirti, tek arıza

31 Ağustos: uçaklar saatlerce açık kaldı, piller bitti, ylp01 brownout
yaşadı. Sonrasında **`MAV_SYS_ID` 2 iken 3 oldu** — yani ylp02 ile aynı.
Diğer 16 uçuş-kritik parametre sağlamdı (`param_karsilastir.py` ile
doğrulandı); bozulan yalnız buydu.

Üç ayrı belirti üretti ve hiçbiri sebebi göstermiyordu:

| Belirti | Görünen |
|---|---|
| QGC'de **vehicle 2 hiç yok** | ylp01 kendini 3 diye tanıtıyor |
| QGC'de **vehicle 3 sürekli kayıyor** | İki fiziksel uçak tek araca akıyor, HUD arada gidip geliyor |
| YKİ'de **"GPS yok"** | `tgt_system=2` ≠ FCU'nun 3'ü → MAVROS `connected: false` → GPS konuları boş |

🔴 **Teşhisin anahtarı ham seri akışı okumaktır.** MAVROS bağlı olmadığı için
hiçbir ROS konusu bilgi vermiyor; ama porttan gelen MAVLink başlıkları
sysid'yi doğrudan söylüyor:

```bash
ssh <pi> 'timeout 4 dd if=/dev/ttyAMA0 bs=1 count=600 2>/dev/null | od -An -tu1'
# MAVLink v2: 0xFD(253) len incompat compat seq SYSID COMPID ...
#   -> 6. bayt sysid.  Ölçülen: 14 başlığın 9'unda sysid=3, compid=1
```

**Tavuk-yumurta:** `ros2 param set` MAVROS'un bağlı olmasını ister, ama
bağlanmıyor. Çözüm — önce FCU'nun kimliğine **geçici olarak uy**:

```bash
echo 3 > ~/yelpence_ws/tgt_system   &&  docker restart drone2   # bağlan
ros2 param set /drone_2/mavros/param MAV_SYS_ID 2
ros2 service call /drone_2/mavros/cmd/command mavros_msgs/srv/CommandLong \
  "{command: 246, param1: 1.0}"                                 # FCU reboot ŞART
echo 2 > ~/yelpence_ws/tgt_system  &&  docker restart drone2    # kalıcı
```

⚠️ **Brownout'tan sonra `param_karsilastir.py` çalıştır.** Bir parametre
bozulduysa başkaları da bozulmuş olabilir; bu sefer bozulmamıştı ama bunu
**ölçerek** öğrendik.

---

### 3.16 🔴 Görev yazılımı emniyet pilotunu EZEBİLİR — `land` tekrarı

**Belirti:** Pilot çubuklara asılıyor, uçak bir an ona geliyor, sonra
**geri alınıyor.** Dışarıdan "uçak yalpalıyor, kontrol tutmuyor" görünür.
Hiçbir yerde hata yok.

**30 Ağustos 2026, ylp00 — rosbag ölçümü:**

```
 4,94 sn  mode_manager 'land'  -> AUTO.LAND
 4,99 sn  emniyet pilotu çubuklara astı (RC ch1 1501 -> 2000)
 5,94 sn  PX4: "Pilot took over using sticks" -> POSCTL
 6,94 sn  px4_bridge AUTO.LAND'i GERİ ZORLADI
 ... aynı döngü 20 saniye boyunca SANİYEDE BİR ...
```

20 sn'de **6 mod değişimi**. Her geçiş hem pilotun çubuk girdisini hem
konum denetleyicisini sıfırladı: istenen roll ±19,5°, **gerçek pitch
−27,4°**. PX4 statustext'te **13 kez** "Pilot took over using sticks".

**Neden oldu:** `px4_bridge._on_fsm_command` içinde 22 Ağustos'ta `offboard`
dalına pilot kapısı konmuştu, ama yorumu AUTO.LAND/RTL'yi **bilerek** muaf
tutuyordu ("onlar görevin kendi akışının parçası"). Bu muafiyet yanlıştı:
görev akışı pilotun **önüne geçemez**. Üstelik `mode_manager` inişi 1 Hz
tekrarlıyor (doğru bir tasarım — tek atışlık iptal mesh'e takılabiliyor).
Tekrar doğruydu; yanlış olan tekrarın pilotu ezmesiydi.

**Düzeltildi (31 Ağustos):** `land` ve `rtl` dallarına da
`PILOT_FLIGHT_MODES` kapısı. **İlk `land` geçer** (o an mod OFFBOARD,
pilot henüz devralmamış); kapıya yalnız **tekrarlar** takılır. Defter
tutma (streaming kapatma, çapa temizleme) kapının önünde, koşulsuz.

**Test:** `swarm_control/test/test_pilot_devralma.py` — üç dalın (offboard ·
land · rtl) kapılı olduğunu ve kapının çağrıdan ÖNCE geldiğini kilitliyor.

---

### 3.17 🔴 "Formasyonsuz = yerinde kal" komutu SÜRÜYÜ İÇE SARMAL YAPTI

**Belirti:** Kalkış bitip `formasyon_sustur` bırakıldığı anda üç uçak
birbirine kapanmaya başlıyor. Kimse formasyon istemiyor, formasyon tipi 0.

**31 Ağustos 2026 — rosbag ölçümü (uçak arası mesafe):**

```
t =  8,45 sn  (susturma AÇIK)   8,35 / 6,91 / 7,40 m
t =  9,05 sn  (BIRAKILDI)       8,38 / 6,92 / 7,44 m
t = 10,74 sn                    5,05 / 4,54 / 4,21 m
t = 12,34 sn                    0,36 / 1,54 / 1,19 m   <-- 36 SANTİM
```

Kaçınma 3 m altında kapalı olduğu için (`altitude_gate_m = 3.0`, bkz. §3.12
ailesi) hiçbir şey durdurmadı; operatör elle indirdi.

**İki kusur BİRLİKTE çalışıyordu:**

1. `mode_manager` `FORMATION_UNKNOWN` dalında ofsetleri **her yayında**
   (~19 Hz) yeniden ölçüyordu.
2. Ölçüm **dünya çerçevesinde**, tüketim **formasyon çerçevesinde**:
   `formation_node._publish_setpoint` gömülü ofseti `heading` ile
   **döndürüyor**.

Kapalı döngü: ölç(dünya) → hedef = merkez + Rot(+214°)·ofset → uçak dönen
hedefin peşinden yetişemiyor, geriden geliyor → yeniden ölç → ofset TEKRAR
döndürülüyor → yarıçap her turda küçülüyor. **İçe doğru sarmal.**

Slot mesafelerinin kendisi de çöküyordu — komuttan ölçüldü:
`t=1,05 → 8,38/6,92/7,44 m` · `t=3,79 → 1,75/2,20/0,94 m`.

> ⚠️ **Döndürme tek başına çarpıştırmaz** — döndürme bir izometridir,
> mesafeleri korur. Çarpıştıran şey döndürme **+ her turda yeniden ölçüm**.
> Teşhiste bu ikisini ayırmak şart.

**Düzeltildi (31 Ağustos), iki parçalı:**
- **Ters döndürme:** ofsetler `Rot(−heading)` ile gömülüyor; `formation_node`
  `Rot(+heading)` uygulayınca dünya çerçevesine geri geliyor → hedef =
  uçağın kendi konumu → kimse kımıldamıyor. Tek başına döngüyü kırar.
- **Dondurma:** ofsetler bir kez ölçülüp sabitleniyor; READY girişinde
  (centroid ile aynı anda) ve gerçek formasyona geçince çözülüyor.

**Doğrulandı:** 31 Ağustos 15:52 uçuşunda en dar çift 20 sn boyunca
**6,7 m'de sabit**. Üç uçak ofsetleri bağımsız hesaplayıp **3 cm içinde**
aynı sonucu üretti.

**Test:** `swarm_state_machine/test/test_formasyon_sarmali.py` — `formation_node`
ile AYNI `rotate_offset` kullanılarak `Rot(+h)·Rot(−h) = birim` kanıtlanıyor.

---

### 3.18 🔴 Gaz çubuğu YAYLI DEĞİL — dinlenme konumu "tam alçal" demek

**Belirti:** Sürü irtifaya varıp çubuklara yetki verdiği anda **saniyede
2 m alçalmaya** başlıyor. Kimse çubuğa dokunmuyor.

**31 Ağustos 2026 — komut ve ham kanal ölçümü:**

```
throttle_cmd = -1,00     ← uçuşun TAMAMINDA sabit, çubuk hiç oynamadı
max_speed_mps = 2,00     → dikey komut = -1,00 x 2,0 = 2 m/s ALÇAL
command_valid = True
```

Setpoint tarafında birebir karşılığı: `vz = +2,00 m/s` (NED, doyumda) ve
formasyon merkezinin irtifası aynı hızda kaçıyor (`center_z 20,7 → 22,3`).

**Neden:** FS-i6X'in gaz çubuğu **ortalanmıyor**, bırakıldığı yerde kalır ve
doğal yeri **dip** (ölçülen dinlenme PWM 1001 → `throttle_cmd = −1,0`).
B18 gaz-merkez kapısı bunu biliyordu ama **tek atışlık mandal**: yalnız SwA
kapanınca sıfırlanıyor. Pilot bir kez ortaya getirip bırakınca kapı açık
kalıyor, çubuk dibe dönüyor ve kimse fark etmiyor.

**Düzeltildi (31 Ağustos):** AYRI bir **dikey yetki mandalı**. SwD kalkış
kenarında sıfırlanır; açılana kadar `throttle_cmd = 0` yazılır.

> 🔴 **B18 `command_valid`'i YENİDEN KURMAK ÇÖZÜM DEĞİL:** `command_valid`
> aynı zamanda G2-K10'un üç kalkış kapısından biri. Kalkış kenarında
> sıfırlansaydı **kalkışın kendisi bloke olurdu.** Bu yüzden ayrı mandal,
> ve o mandal `command_valid`'e dokunmaz.

**Kontrollü doğrulama (31 Ağustos 15:52):** ham gaz kanalı (ch3) uçuşun
tamamında **1000 (dipte)** ölçüldü — yani arıza koşulu birebir tekrarlandı —
ama sürüye giden değer **`+0,00`** kaldı.

---

## 4. Mesh ve ESP32

### 4.1 Hız limiti TİP başına, HEDEF başına değil

İki drone'a art arda `takeoff` gönderildi; ylp00 kalktı, **ylp01 ARMLI halde
yerde kaldı.** Backend `200 OK` verdi, hiçbir hata dönmedi.

`mesh_config.h`: `_son_tip_gonderim_ms[tip]` — sayaç **tip** başına. İki uçak
aynı yuvayı paylaşıyor. Üstüne her guided komut 4 kopya gönderiliyordu:

```
drone1 -> 0.00  0.25  0.50  0.75
drone2 -> 0.30  0.55  0.80  1.05
kapı   -> geçer geçer DÜŞER geçer DÜŞER geçer DÜŞER geçer
```

| | drone 1'e | drone 2'ye |
|---|---|---|
| eski | 3/4 | **1/4** |
| yeni (tek kuyruk) | **4/4** | **4/4** |

**Düzeltildi:** `esp32_bridge_node._guided_gonder` artık komut başına timer
açmıyor; bütün guided çerçeveler tek kuyruğa girip 20 Hz'de sırayla
boşalıyor, `_GUIDED_TIP_ARALIK_S` firmware kapısının üstünde tutuluyor
(TIP_KOMUT 0.30 > 0.200) ve gönderilen kayıt kuyruğun **sonuna** atılıyor.

**Neden tek drone uçuşlarında hiç görünmedi:** çakışacak ikinci komut yoktu.
Yeni bir mesh tipi eklerken bu paylaşımı hatırla. *(1 Ağustos 2026)*

### 4.2 NVS erase tuzağı — "duyar ama duyulmaz"

Firmware yüklemesinden sonra NVS geri yazılınca baz'ın `session_id`'si
sıfırlanıyor; drone onu daha yüksek bir session ile hatırlıyor ve **gelen tüm
paketleri reddediyor.**

```
[REPLAY] ESKI SESSION reddedildi: B5:34 sid=2 < kalici=5
[REPLAY] ^ sid cok dusuk: B5:34 NVS'i silinmis olabilir (erase tuzagi)
```

Semptom sinsi: **mesh kurulu görünür, "aktif node = 1" der, paketler geçmez.**
Kurtarma: bazı arka arkaya resetleyerek `session_id`'yi drone'un
hatırladığının üstüne çıkar (her boot +1). Kalıcı çözüm: sürünün tamamının
NVS'ini birlikte sıfırlamak. *(20 Temmuz 2026 — `MESH_PROTOKOL_KARARLARI.md` §3.1)*

### 4.3 Doğru cihaza yüklediğinden emin ol — tahmin etme, MAC oku

Dizüstünde birden fazla USB seri cihaz olur (base'in CH340 veri hattı,
base'in CP2102'si, dron ESP'si) ve `by-id` adları aynı olabilir
(`CP2102_..._0001`).

```bash
python3 ~/.platformio/packages/tool-esptoolpy/esptool.py \
    --port /dev/ttyUSBx --no-stub read_mac
```

Ortam `esp32dev_serial0` olmalı (RPi hattı Serial0'da).

### 4.4 ESP32 yüklemesi `--no-stub` ister

Normal yükleme "chip stopped responding" ile kesiliyor. Tüm esptool/pio
çağrılarında `PLATFORMIO_UPLOAD_FLAGS=--no-stub`. *(20 Temmuz 2026)*

### 4.5 Kart üzerindeki `RX`/`TX` yazısı yanıltıcı

O pinler GPIO3/GPIO1, yani USB debug portu. Firmware `Serial1`'i GPIO18/19'a
atamıştı; "RX/TX yazan yere bağladım" ile veri geçmemesinin sebebi buydu.
Firmware sonunda Serial0'a taşındı — **bedeli:** firmware yüklerken RPi
kablolarının sökülmesi gerekiyor (aynı pinler paylaşımlı). *(20 Temmuz 2026)*

### 4.6 `Serial.setRxBufferSize()` UART0'da `begin()`'den önce çağrılamaz

Kart boot döngüsüne giriyor (`entry 0x400805e4` → sürekli `SW_RESET`,
uygulama hiç başlamıyor). Doğrusu: `begin()` → `end()` → `setRxBufferSize()`
→ `begin()`. *(20 Temmuz 2026)*

### 4.7 Binary hatta `printf` = CRC hatası

Bazı derlemelerde `Serial` debug konsolu **değil**, binary veri hattıdır
(TX DRONE + `RPI_SERIAL0_MODU`, RX BASE + `TEK_USB_MODU`). Her düz metin
akışın ortasına giriyor, alıcı bir sonraki `0x00`'a kadar biriktirdiği için
metin çerçeveye yapışıyor ve o çerçeve CRC'de düşüyor.

Çözüm `mesh_log.h` — `MESH_LOG_PRINT/PRINTLN/PRINTF`, bu modlarda no-op.
Doğrulama binary düzeyinde yapıldı: susturulan string'ler flash'tan düştü
(2756 B / 3208 B). **Boot mesajlarına bilerek dokunulmadı** (bir kez, mesh
trafiği başlamadan basılıyorlar ve MAC tablosu hatasını görmek kritik).

> Yeni bir `Serial.print` eklemeden önce o derlemede `Serial`'in ne olduğuna
> bak. *(28 Temmuz 2026)*

### 4.8 Formasyon paketinde `sequence_num` mesh üzerinden TAŞINMAZ

16 baytlık yükte yer yok (`formasyon_veri_t` tam dolu); alıcı kendi sayacını
üretir. Test: 42 gönderildi, 12 alındı — **hata değil.** Hiçbir tüketici
formasyonun `sequence_num`'ını dronlar arası karşılaştırmada kullanmamalı.

### 4.9 `STATE_ARMED` mesh'te ayrı kod taşımaz

`KALKIS`'a eşlenir, karşı tarafta `STATE_TAKEOFF` olarak çözülür. İkisi de
`ELIGIBLE_STATES` içinde olduğu için uygunluk korunur (split-brain yok).
*(21 Ağustos'ta canlı doğrulandı: uçak kendine ARMED=3 derken komşu izinde
state=4 göründü ve yarım saat "hata" diye kovalandı — önce buraya bak.)*
**Yan etki:** komşular yerde armlı bir dronu `AIRBORNE_STATES` içinde görür;
lider yerde armlı, takipçi havadaysa takipçi lideri "havada ama heartbeat
yok" sayıp düşürür. Savunulabilir ama bilinmesi gerekir.

⚠️ **Sahte TAKEOFF'un tüketicileri yalnız lider seçimi değil:** çarpışma
kaçınması ve formasyon da komşunun durumuna bakıyor (`AIRBORNE_STATES`).
ADIM 3/ADIM 4 açıldığında bu doğrudan aktüatör yoluna bağlanır — o yüzden
`ARMED → KALKIS(2) → TAKEOFF(4)` eşlemesi ikisinin de **ön koşulu** arasında.

### 4.10 Base ESP'yi çıkarıp taktıysan RESETLE

Köprü portu geri açıyor (`fd 32 → /dev/ttyUSB0`) ama telemetri gelmiyor, üç
drone da `connected=False`. ESP resetlenince mesh anında geri geldi.
**Köprünün portu geri açması yeterli değil.** *(29 Temmuz 2026)*

---

### 4.11 Kadro uçağını AÇ-KAPAT yapmak CA körlüğü kurar — "hiç açma ya da açık bırak"

25 Ağustos: sabah mesh'te görülen ylp02 test öncesi kapatıldı. Uçan
ylp01'in CA'sı onu "görülmüş-ama-kayıp" saydı (körlük) ve **çatışma
bittikten sonra dönüşü 34 sn blokladı** — uçak d_xy 13,5 m'yken 7,4 m'de
asılı kaldı. Hata yok, alarm var, ama davranış şaşırtıcı.

Bir gece önce AYNI test dönmüştü — çünkü o gece ylp01 mesh'e hiç
girememişti: **hiç görülmemiş komşu körlük sayılmaz.** Yani "üçüncü uçağın
ESP'si bozukken test temiz, sağlamken kirli" paradoksu yaşandı.

`6258eab` (KARAR-07) yerde+disarm kayıp komşuyu dönüş tutmasından muaf
tuttu; yine de kural: **test dışı kadro uçağı ya HİÇ açılmaz ya AÇIK
bırakılır** — aç-kapat, alarm gürültüsü ve (havada/arm'lı son görülme
durumunda) gerçek tutma üretir.

### 4.12 Uçak ELDE taşınırken ESP gölgelenir — "sürekli KRİTİK" alıcı arızası değildir

25 Ağustos: YKİ art arda "drone1 KOMŞUSUNU GÖREMİYOR" KRİTİK'leri bastı.
Ölçüm: drone1 VE drone3, drone2'yi **21 ms arayla aynı anda** kaybetti —
iki bağımsız alıcı aynı anda kaybediyorsa suç vericide: drone2 o dakikada
ELDE TAŞINIYORDU (anten el/vücut/yönelimle gölgelenir, 2 sn'lik kesinti
körlük alarmı basar, yere konunca düzelir).

Teşhis kalıbı: kayıp olayının zamanını iki alıcıda karşılaştır — eşzamanlı
kayıp = verici/taşıma; tek alıcıda kayıp = o alıcının RX'i.

**Uçuş kuralı: körlük KRİTİĞİ ekrandayken yaklaştırma YAPILMAZ** — görmeyen
uçak kaçamaz; alarm tam bunu söylüyor.

## 5. Raspberry Pi ve seri portlar

### 5.1 `dtoverlay=uart4` ≠ `uart4-pi5`

```
Name: uart4        -> GPIOs 8-11.  BCM2711 only.   (RPi 4)
Name: uart4-pi5    -> GPIOs 12-13. Pi 5 only.      (RPi 5)
```

`/dev/ttyAMA4` **vardı** ama yanlış pinlere bakıyordu. Kablolama doğruydu,
overlay yanlıştı. RPi 5 UART yerleşimi: Pixhawk GPIO14/15 → `/dev/ttyAMA0`
@115200, ESP32 GPIO12/13 → `/dev/ttyAMA4` @460800. *(20 Temmuz 2026)*

### 5.2 CP2102 portunu açmak ESP'yi resette TUTAR

pyserial **açılış sırasında** RTS'yi çekiyor ve bırakmıyor → EN low → ESP
resette kalıyor. İlk denemede kart 12 sn sessizdi; bozuk değildi, resette
tutuluyordu. Doğrusu — aç, sonra **hemen** temizle:

```python
s = serial.Serial('/dev/ttyUSB1', 115200, timeout=0.4)
s.setDTR(False); s.setRTS(False)      # EN'i birak - kart calissin
```

Portu tekrar tekrar açıp kapatmak kartı sürekli resetler ve 10 sn'lik
istatistik periyoduna hiç ulaşamazsın: **bir kez aç, bırakma.**
*(29 Temmuz 2026)*

### 5.3 `cmdline.txt`'de `console=serial0,115200` Pixhawk'ın UART'ını işgal eder

Seri konsol UART0'ı tutuyor; kaldırılmazsa **MAVROS hiç bağlanamaz.** Yeni
bir Pi hazırlanırken en kritik adım — `deploy/rpi/pi_hazirla.sh`'ta yazılı.
*(30 Temmuz 2026)*

### 5.4 Bir seri portu tek süreç açar

Portu isteyen üç taraf vardı: `esp32_bridge` (sahibi), `yki_rtcm_reader`,
**ve QGC** (autoconnect ile kapıyor — sahada `Device or resource busy`).

Yapısal çözüm: RTCM doğrudan porta değil **ROS topic'ine** gidiyor
(`/swarm/internal/rtcm`); `esp32_bridge` abone olup çerçeveleyerek yazıyor.
Port sahipliği tek elde. Yeni bir şey porta yazmak istiyorsa **topic'ten
geçir.** *(28 Temmuz 2026)*

---

## 6. RTK / u-blox

### 6.1 QGroundControl açıkken u-blox takmak ayarları BOZAR

QGC'nin RTK oto-bağlanması modülü **RAM'e yazarak** yeniden yapılandırıyor:
1 Hz → **10 Hz**, `1005` ve `1230` **kapalı**, survey-in 300 → 180 s. RTCM
5 msg/s'ten **40 msg/s**'e fırlıyor (mesh bütçesini aşar) ve baz konumu hiç
gelmiyor.

Kalıcı katmanlar bozulmuyor → **u-blox'u çıkarıp takmak düzeltir.** Kalıcı
önlem, QGC **kapalıyken**: `~/.config/QGroundControl.org/QGroundControl.ini`
→ `[LinkManager]` altına `autoConnectRTKGPS=false`.

> Bir ara ylp01'de %8.7 CRC hata oranı ölçülüp anten yerleşimi şüphelenmişti;
> o ölçüm tam bu 40 msg/s seline denk geliyormuş. 1 Hz'e dönünce iki uçak da
> `crc_fail=0`. **Anten şüphesi desteklenmiyor.** *(30 Temmuz 2026)*

### 6.6 QGC'nin `AutoConnect → RTK GPS`'i u-blox PORTUNU kapıyor — RTCM hiç akmaz

§6.1 QGC'nin ayarları bozmasını anlatıyor; bu ondan **ayrı** ve daha sinsi:
QGC seri portu **açık tutuyor**, dolayısıyla `yki_rtcm_reader` portu hiç
açamıyor. Seri port tek sahipli.

```
$ lsof /dev/cu.usbmodem1301
COMMAND     PID USER   FD   TYPE  NAME
QGroundCo  6245 berk   72u   CHR  /dev/cu.usbmodem1301     ← QGC tutuyor

/tmp/yki_rtcm.log:
⚠ GPS PORTU AÇILAMADI — [Errno 16] Resource busy
```

**Belirti sessiz:** telemetri normal akıyor, YKİ arayüzü sağlıklı görünüyor,
tek işaret uçakların `gps_fix_type`'ının 6 (RTK-FIXED) yerine **3-5'te
takılması** ve kimsenin bakmadığı `/tmp/yki_rtcm.log`.

**Çözüm:** QGC → Application Settings → General → *AutoConnect to the
following devices* → **RTK GPS kapalı**. Okuyucu 2 sn'de bir yeniden deniyor,
kapatır kapatmaz kendiliğinden bağlanıyor.

⚠️ Bu, QGC'yi kapatmakla çözülmez sanılmasın — QGC **açık kalmalı** (§7.1:
`udp-b` yayın tuzağı). İkisi birlikte: QGC açık, RTK GPS oto-bağlanması
kapalı. *(18 Ağustos 2026'da ölçüldü; port sahibi `lsof` ile bulundu)*

### 6.2 Katman kontrolü RAM/FLASH ile YETMEZ — BBR de okunmalı

F9P açılışta `Default → Flash → BBR` sırasıyla yükler, yani **BBR Flash'ı
ezer.** Yalnız RAM/FLASH karşılaştırmak "ayarlar kalıcı" yanılgısı verir.
`--kalici` üç katmana birden yazıyor (bitmask 7); doğrulama da üçünü birden
okumalı.

İlgili: ayarlar `--gecici` ile **yalnız RAM'e** yazılırsa güç kesintisinde
uçar — RTK Fixed → Float, 2 cm → 30 cm olarak yaşandı. *(29 Temmuz 2026)*

### 6.3 `fix_type=4` (DGPS) RTK kanıtı DEĞİLDİR

Bu filoda SBAS/EGNOS kaynaklı — ölçüldü: RTCM 95 sn kesildi, `fix_type` 4'te
kaldı. RTK'nın tek kanıtı **5 (Float)** veya **6 (Fixed)**.
Ayrıntı: `YELPENCE_RTCM_SPEC.md`.

### 6.4 Rover baz konumunu önbelleğe alır — "1005 yok → Fixed yok" YANLIŞ

1005 tamamen kesildikten sonra da ylp02 RTK Fixed'de kaldı; rover son aldığı
baz ARP'sini saklıyor ve gözlem mesajları aktığı sürece çözüm üretiyor. Bu
iddia kuruldu ve **ölçümle çürütüldü.** 1005 eksikliği ancak rover sıfırdan
başladığında vurur. *(29 Temmuz 2026)*

### 6.5 Survey-in modu her açılışta baştan başlar

Modun doğası bu, ve **survey bitmeden 1005 yayınlanmaz.** Survey bitince
`--sabitle` ile sabit moda al; o zaman açılışta survey beklemeden 1005 akar.

> Baz konumundaki mutlak hata **tüm dronlara ortak** kayma olarak biner;
> formasyon için önemli olan göreli doğruluk etkilenmez. Yani survey
> doğruluğu makul bir seviyede kesilebilir.

---

## 7. YKİ ağı ve WiFi

### 7.1 `gcs_url` yayını telefon hotspot'unu boğuyor — internet "kopar", wifi kopmaz

Semptom: dron ağa girdikten ~10 sn sonra laptopta internet ölür, wifi
simgesinde soru işareti çıkar. Dronun gücü kesilince anında düzelir.
**Wifi hiç kopmaz** — teşhisi zorlaştıran şey bu.

Sebep: `~/yelpence_ws/gcs_url` = `udp-b://…` **yayın** demek. QGC açık
değilken MAVROS karşı taraf keşfedemez ve durmadan `255.255.255.255:14550`'ye
yayın yapar. Telefon hotspot'u bu akış altında **tüm istemcilere** teslimatı
saniyede ~1.25 pakete düşürür; ağ geçidine (telefonun kendisine, tek atlama)
ping 3→6→9→14 sn diye büyüyüp tavan yapar.

**Yanlış yola sapmamak için — bunlar ölçüldü ve hepsi TEMİZ çıktı:**

| Baktığın yer | Kopma anındaki değer |
|---|---|
| NetworkManager | tek olay: rutin DHCP yenilemesi (kopma yok) |
| IP / rota / ARP tablosu | hiç değişmedi |
| `iw … station dump` | hava %0.1-2.8, yeniden gönderim 0-3/s, **72.2 Mbit sabit** |
| sinyal | -35…-43 dBm |
| ARP fırtınası | yok (tüm yakalamada 52 istek) |
| laptop wifi güç tasarrufu | kapatıldı, **birebir aynı koptu** |

Yani "tıkanıklık" arayan kaybeder: **radyo boştur.** Trafik de küçüktür
(14 paket/s, 0.8 KB/s) — sorun hacim değil, **yayın olması**.

Kanıt iki yönlü: QGC açılıp MAVROS tekil gönderime geçince, **20 kat daha
fazla veriyle** (320 paket/s) sorun anında biter.

**Kural:** dronlara güç vermeden **önce** QGC'yi aç.

> 🔴 **"QGC açık" YETMEZ — 14550'yi DİNLEYEN bir link olmalı.** 22 Ağustos'ta
> aynı arıza tekrar yaşandı ve sebebi buydu: QGC çalışıyordu ama
> `~/.config/QGroundControl/QGroundControl.ini` içinde `[LinkConfigurations]`
> bölümü **hiç yoktu** ve `autoConnectUDP=false` idi. Yani 14550'yi kimse
> tutmuyordu, MAVROS karşı tarafı hiç bulamadı ve **süresiz** yayın yaptı.
>
> Bu, taze bir QGC kurulumunun **varsayılan hâli** — yani kuralı uygulayan
> biri, hiçbir şey yanlış yapmadan bu tuzağa düşer. Ekle:
> **Comm Links → Add → UDP, Listening Port 14550 → Connect.**
>
> Tek satırlık doğrulama — QGC açıkken bile **boş çıkabilir**:
> ```bash
> ss -ulnp | grep 14550        # QGroundControl gorunmuyorsa link YOK/kopuk
> ```

**Pencere ne kadar sürer — 22 Ağustos'ta ölçüldü:**

| durum | tepe gecikme | süre |
|---|---|---|
| **Soğuk açılış**, QGC o uçağı hiç duymamış | **14.500 ms** | **~60 sn** |
| `docker restart`, QGC bağlı ve uçağı **tanıyor** | **333 ms** | çöküş yok |

Fark, QGC'nin hedef listesinde: bir kez paket aldığı adrese sürekli heartbeat
göndermeye devam ediyor, MAVROS yeniden kalkınca ilk saniyede kilitleniyor.
Soğuk açılışta ise QGC önce bir yayın paketi **almak** zorunda ve o paketler
yayının kendi yarattığı kuyrukta bekliyor — **yayın kendi kurtuluşunu
geciktiriyor.** Yani maliyet oturum başına bir kez, restart başına değil.

⚠️ Bunun şartı QGC link'inin **bağlı kalması**. Kapanırsa uçak hedef
listesinden düşer ve bir sonraki restart yine soğuk açılış gibi davranır.

Kalıcı çözüm `gcs_url` = `udp://:14555@` — uçak yayın yapmaz, yalnız dinler.
Denendi ve doğrulandı (ylp00, 100 sn: 31779 paket **tekil**, **0 yayın**, ping
200/200, ağ geçidi ortancası **5.2 ms**), ama **operatör kararıyla
uygulanmadı**: bağlantıyı QGC kurmak zorunda kalır, yani her takım üyesinin
QGC link'ine uçak IP'lerini (`<ip>:14555`) girmesi gerekir ve giren yoksa
telemetri **sessizce** gelmez. İki uçakta birden yapılmadıkça da anlamsız —
düzeltilmemiş olan tek başına ağı boğmaya devam eder.
*(17 Ağustos 2026'da ölçüldü, 22 Ağustos'ta karar teyit edildi)*

### 7.2 `mt7921e` kanal meşguliyeti sayaçlarını doldurmuyor

`iw dev <arayuz> survey dump` bu sürücüde **hep 0** verir — "kanal boş"
sanırsın, ölçüm yoktur. Hava kullanımını `station dump`'ın `tx duration` /
`rx duration` alanlarından hesapla. *(17 Ağustos 2026)*

### 7.3 Konteynerden `iw` ile ayar yazmak `-u 0` ister

`--network host` konteyner host'un kablosuz arayüzünü **görür**, ama
`iw … set` için hem `--cap-add=NET_ADMIN` hem **kök** gerekir. İmajın
varsayılan kullanıcısı kök değilse `Operation not permitted` alırsın ve
ayarın değiştiğini sanıp yanlış sonuç çıkarırsın — okuma çalıştığı için
tuzak sinsi. *(17 Ağustos 2026)*

---

## 8. Ölçülmüş referans sayılar — tahmin etme, buradan bak

Bunlar bir kez ölçüldü ve tekrar ölçmeye değmez.

| Ne | Değer | Ne zaman |
|---|---|---|
| Mesh yük dayanımı | yük 35× arttı, **gelen telemetri etkilenmedi** (14.8 → 14.7/sn), CRC 0, drop 0 | 28 Tem |
| Base UART tavanı | ~35 çerçeve/sn | 28 Tem |
| RTCM uçtan uca | 125 gönderildi / **125 alındı**, iki uçakta da kayıp 0 | 28 Tem |
| RTCM fragment sınırları | 106 B→1 · 238 B→1 · 239 B→2 · 406 B→2 · 1029 B→5 | 28 Tem |
| Komşu konum tazeliği (mesh) | **7.24 Hz**, en büyük boşluk **203 ms** → 4 m/s'te ~0.8 m kör alan | 2 Ağu |
| Lider seçiminin mesh'te yayılması | 109 ms · 22 ms (iki ayrı ölçüm) | 30 Tem |
| Formasyon geometrisi | mesh'te **taşınmıyor**, alıcı kendi türetiyor (V: 2.8284 = 4.0×cos45°) | 30 Tem |
| 30° roll'un dikey yayılımı | `dz = 0.408 × ARALIK_M` → 10 m aralıkta **±4.1 m** | 2 Ağu |
| OFFBOARD tek adım goto | hız talebi anında `MPC_XY_VEL_MAX`'a fırlar; PX4 OFFBOARD'da setpoint'i **yumuşatmaz** | 1 Ağu |

**Not:** hız/ivme/aralık gibi *ayarlanabilir* sayılar burada değil —
tek kaynak `src/gcs/ucus_ayarlari.py` (bkz. `CLAUDE.md` §8).

---

## 9. YKİ makinesi — platform farkları (Ubuntu / Arch / macOS)

18 Ağustos'ta YKİ ilk kez bir **macOS** makinede (Apple Silicon) çalıştırıldı.
Aşağıdakiler o gün ölçüldü; hepsi **hata vermeden yanlış sonuç** üreten türden.

### 9.1 `arp -an` macOS'ta MAC sekizlilerinin baştaki sıfırını ATIYOR

```
gerçek MAC : 88:a2:9e:da:04:2d          ← docs/cihazlar.md (ylp01)
arp -an    : 88:a2:9e:da:4:2d           ← macOS böyle yazıyor
```

Düz metin karşılaştırması yapan bir betik o cihazı **sessizce kaçırır**:
"ağda yok" der, oysa vardır. `drone_bul.sh` bundan etkileniyordu ve
**yalnız ylp01'i** kaçıracaktı — ylp00/ylp02'nin MAC'inde sıfırlı sekizli
yok, o yüzden ylp01 onarılıp dönene kadar kimse fark etmeyecekti.
✅ Düzeltildi: iki taraf da normalize ediliyor (`mac_sadelestir`).

### 9.2 `/dev/tcp` **zsh'te YOKTUR** — port testi yanlış "kapalı" der

`/dev/tcp/host/port` bash'e özgü bir sanal cihaz. macOS'un varsayılan kabuğu
zsh ve orada bu yol yok; test sessizce başarısız olur.

```
zsh  : (echo > /dev/tcp/172.20.10.2/22)  → "kapali"   ← YALAN
nc   : nc -z -G 3 172.20.10.2 22         → "SSH ACIK" ← doğru
```

Bu tam olarak §1'in konusu: **ölçüm aracının kendisi yalan söylüyor.**
`drone_bul.sh` macOS'ta `nc` kullanıyor artık.

### 9.3 Loopback arayüzünün adı `lo` değil `lo0`

CycloneDDS yapılandırmasında `<NetworkInterface name="lo">` macOS'ta arayüzü
bulamaz → laptop-içi DDS hiç kurulmaz → base_bridge veri okur ama backend'e
ulaşmaz. Sessiz arıza. macOS için ayrı config kullanılıyor
(`DDS_URI` env ile). `name` yerine `address="127.0.0.1"` iki platformda da
çalışır ama saha makinesinde sınanmadan değiştirilmedi.

### 9.4 `setsid` ve `getent` macOS'ta yok, `ip` komutu da yok

`yki_baslat.sh` ve `drone_bul.sh` bunların hepsini kullanıyordu. Karşılıkları:
`setsid → nohup`, `getent hosts → dscacheutil -q host`, `ip route → route -n
get default` + `ipconfig getifaddr`, `ip neigh → arp -an`, `timeout → gtimeout`
(yoksa çıplak çalıştır). Hepsi tek yerden sarmalandı; Linux yolu değişmedi.

### 9.6 macOS'un bash'i 3.2 — `declare -A` SESSİZCE yanlış uçağa eşler

`dagit.sh` ve benzeri betikler drone tablosunu **ilişkisel dizi** ile tutuyor.
macOS hâlâ **bash 3.2** ile geliyor (2007 sürümü, lisans yüzünden) ve orada
`declare -A` yok. Kötüsü: sessizce yanlış sonuç veriyor.

```
$ /bin/bash -c 'declare -A x=([ylp00]="yelpence00" [ylp02]="yelpence02")
                echo "${x[ylp00]}"'
declare: -A: invalid option          ← uyarı basar ama DEVAM EDER
yelpence02                            ← ylp00 soruldu, ylp02 geldi
```

Sebep: `[ylp00]` ve `[ylp02]` **aritmetik** değerlendiriliyor, ikisi de `0`
çıkıyor, ikisi de aynı indise yazıyor ve **sonuncusu kazanıyor**.

**Bugün bizi `set -u` kurtardı** (`ylp00: unbound variable` deyip durdu). O
olmasaydı `dagit.sh` **ylp00'a bağlanmaya çalışırken ylp02'nin kullanıcı adını**
kullanacaktı — ve "Permission denied" hatası anahtar sorunu sanılacaktı.

**Çözüm:** `brew install bash` (bash 5 `/opt/homebrew/bin/bash`'e kurulur;
sistemdeki 3.2 yerinde kalır) ve betiği onunla çalıştır:

```bash
/opt/homebrew/bin/bash deploy/rpi/dagit.sh ylp00
```

Kalıcı düzeltme, tabloyu `drone_bul.sh`'e (düz dizi kullanıyor) delege etmek
olurdu — `dagit.sh` IP aramasını zaten oraya delege ediyor.
*(18 Ağustos 2026'da ölçüldü)*

### 9.5 ROS 2 Jazzy macOS'ta apt'ta değil — pixi/RoboStack ortamında

`/opt/ros/jazzy/setup.bash` yok. `yki_baslat.sh` doğrudan çalıştırılırsa
`source` sessizce başarısız oluyor ve betik **düğümleri ROS'suz başlatmaya
devam ediyordu**: ekranda bir hata satırı, arkasından normal görünen dört
satır. Sonraki kişi YKİ'yi ayakta sanıyor.
✅ Düzeltildi: `ROS_SETUP` yoksa betik **erken patlıyor** ve macOS'ta
sarmalayıcıyı (`yki_mac.sh`) gösteriyor.


### 9.7 🔴 macOS seri port ADI DEĞİŞİYOR — süreç ölü porta bağlı kalır, HATA VERMEZ

31 Ağustos gecesi bu **iki farklı cihazda peş peşe** ısırdı ve toplam
~1,5 saat kaybettirdi.

```
base ESP :  süreç bekliyor  /dev/cu.usbserial-11340   gerçek: -1340
RTK      :  süreç bekliyor  /dev/cu.usbmodem113301    gerçek: 13301
                                          ↑ fazladan bir '1'
```

**Kök sebep:** `yki_baslat.sh`'in varsayılanları Linux `/dev/serial/by-id/...`
yolları — takıldığı porttan **bağımsız, kararlı** adlar. macOS'ta öyle bir
dizin **yok**; ham `cu.usbserial-XXXX` adının rakamları **USB yolunu**
kodluyor, yani cihaz başka porta/hub'a takılınca **ad değişiyor.**
Operatör RTK'yı çıkarıp taktığı anda okuyucu onu kaybetti.

🔴 **Belirti sinsi: süreç ayakta, port yok, hiçbir hata yok, sadece veri
yok.** Teşhis sırasında önce uçaklar suçlandı, sonra QGC. Görünen tek iz:

```
/api/health          → "connected": 0
px4_bridge logu      → rtk: msg=0        (sayaç donuk)
lsof /dev/cu.usb*    → hiçbir süreç tutmuyor    ← EN NET iz
```

✅ **Düzeltildi:** `yki_baslat.sh`'e `seri_port_bul()` eklendi. Yapılandırılan
port yoksa desenle arar (`cu.usbmodem*` = u-blox CDC-ACM, `cu.usbserial-*` =
CH340 ESP). **Belirsizlikte TAHMİN ETMEZ** — birden çok aday varsa hiçbirini
seçmez ve adayları listeleyerek bağırır. Gerekçe: yanlış port **sessiz**
arıza, eksik port en azından görünür.

⚠️ **Kalan belirsizlik:** CH340'ın benzersiz seri numarası yok, o yüzden iki
`cu.usbserial-*` cihazı varsa hangisinin ESP olduğu ayırt edilemiyor.
Kalıcı çözüm: **ESP'yi hep aynı USB portuna tak** ve bunu `cihazlar.md`'ye
yaz — ad o zaman sabit kalır.

---
