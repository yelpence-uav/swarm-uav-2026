# TUZAKLAR — hata vermeden yanlış sonuç üretenler

**Son güncelleme:** 19 Ağustos 2026, 00:12

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

> Her uçuştan önce `python3 src/gcs/titresim_olc.py ylp00` — clipping
> artıyorsa **UÇMA.** Fiziksel kontrol sırası: motor yatakları → uçuş kartı
> montaj köpüğü → kol/gövde vidaları.

**Araç hâlâ repoda** (`src/gcs/titresim_olc.py`) ama bu kural hiçbir uçuş
öncesi listesinde yok. `DURUM.md` §7 yalnız `param_karsilastir.py` diyor.
*(1 Ağustos 2026'da ölçüldü)*

### ✅ 0.2 CEVAPLANDI (18 Ağustos) — sorun ylp00'da DEĞİL, **ylp02'de**

YKİ telemetrisinden ölçüldü, iki kez tekrarlandı:

| | ylp00 (drone1) | ylp02 (drone3) |
|---|---|---|
| kumanda **kapalı** | `kill=False` `healthy=True` | **`kill=True` `healthy=False`** |
| kumanda **açık** | `kill=False` `healthy=True` | `kill=False` `healthy=True` |

`rc_link_ok` iki durumda da `True`; diğer bütün sağlık bayrakları temiz.
Yani ylp00 bir noktada düzelmiş (kimse yazmamış), **ylp02 bozuk**.

**✅ ylp02 aynı gün düzeltildi (17:30).** Kumandanın `RX Setup → Failsafe`
ekranında **Ch5 `+100%`** yazılıydı — failsafe kapalı değil, **kill değeriyle
kayıtlı**. `-100%`'e çevrilip kaydedildi:

```
önce : 1488 1496 1017 1500  2001  2000 1000 1000     ← kumanda KAPALI
sonra: 1488 1496 1018 1500  1000  2000 1000 1000     ← kumanda KAPALI
```

⚠️ Dikkat çekici: 29 Temmuz'da "ylp00" diye kaydedilen sekiz kanal, bugün
ylp02'de **birebir** çıktı (`1488 1496 1017 1500 200x 2000 1000 1000`).
Ya o gün ölçüm ylp02'de yapılıp nota yanlış uçak yazıldı, ya da iki alıcı da
aynı ayarlıydı ve ylp00 sonradan düzeltildi. Ayırt edilemedi.

**Düzeltmeden sonraki kill semantiği** (18 Ağu'da ölçüldü, LED ile de görüldü):

| Durum | PX4 | Pixhawk LED |
|-------|-----|-------------|
| Kumanda AÇIK + SwA kill konumunda | kill aktif | kırmızı |
| Kumanda KAPALI (failsafe `CH5=1000`) | kill **bırakılır** | yeşil |

Yani kill artık **yalnız kumanda açıkken** var. `COM_KILL_DISARM=5.0` sayesinde
kill 5 sn'den uzun tutulursa PX4 kendiliğinden **disarm** ediyor; kill sonradan
kalksa bile motorlar geri gelmiyor.
⚠️ **Uç durum:** kill 5 sn'den KISA tutulup bırakılırsa uçak hâlâ armlı olduğu
için motorlar geri gelir ("pilot kill'ledi, 2 sn sonra kumanda öldü").
Bilerek kabul edildi — alternatifi kumanda ölünce garantili kill'di.

⚠️ **CH6 hâlâ 2000** (aux2 = Görev 2 mod seçimi) — bugün zararsız,
`mode_manager` kapalı. Görev 2 öncesi kaydedilmeli.
Kalan maddeler: `YAPILACAKLAR.md` **P0.9**.

Aşağıdaki 29 Temmuz ölçümü tarihçe olarak duruyor — mekanizma aynı, yalnız
uçak farklı:

Kumanda **kapalıyken** ylp00'ın alıcısı susmuyor, hafızasındaki failsafe
değerlerini göndermeye devam ediyordu; içlerinden biri CH5'i kill'e atıyordu:

```
rc/in (ylp00, kumanda KAPALI): [1488, 1496, 1017, 1500, 2000, 2000, 1000, 1000]
                                                        ^CH5 = 2000 -> +1.0
RC_MAP_KILL_SW=5, RC_KILLSWITCH_TH=0.75  ->  KILL AÇIK
```

Ayar **alıcının flash'ında** duruyor: QGC göstermez, RC kalibrasyonu
dokunmaz, PX4 parametre karşılaştırması bulamaz — iki uçakta parametreler
birebir aynıydı. Kumandayı değiştirmek de çözmezdi.

Havada karşılığı: RC kaybı → RTL **değil**, anında motor kesme.
`NAV_RCL_ACT=2` yazılıydı ama hiç devreye girmiyordu, çünkü alıcı yayına
devam ettiği için PX4 kaybı hiç görmüyordu (`RC_FAILS_THR=0`).

Yarım kalan prosedür: kumandada End Points ile gaz failsafe'ine ayrım
yaratmak (Ch3 alt uç geçici %120 → çubuk aşağıdayken failsafe kaydet →
Ch5/6/7 Off → %100'e dön → `RC_FAILS_THR=960`). ylp02'de %120 uygulandı,
908 ölçüldü. **Açık soru:** alıcı 908'i ham PWM olarak mı yüzde olarak mı
saklıyor? Yüzde ise End Points geri alınınca numara boşa gider.
*(29 Temmuz 2026'da ölçüldü)*

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

### 0.3 ylp00 hover gazı %66 — hâlâ öyle mi?

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

---

## 2. ROS 2 / DDS / kabuk

### 2.1 QoS uyumsuzluğu SESSİZDİR — bu belgedeki en pahalı tek kural

BEST_EFFORT yayıncı ↔ RELIABLE abone, ya da VOLATILE ↔ TRANSIENT_LOCAL:
**hiç bağlanmazlar ve hata da vermezler.** Panel boş kalır, sayaç 0 kalır,
hiçbir yerde bir satır çıkmaz.

Bu projede en az üç kez yaşandı: `SwarmState` publisher'ı (YKİ paneli boş
kalıyordu), yük testi üreteci, RTCM okuyucusu. Yeni bir publisher/subscriber
eklerken **karşı ucun QoS'unu oku.** *(20 ve 28 Temmuz 2026)*

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
**Yan etki:** komşular yerde armlı bir dronu `AIRBORNE_STATES` içinde görür;
lider yerde armlı, takipçi havadaysa takipçi lideri "havada ama heartbeat
yok" sayıp düşürür. Savunulabilir ama bilinmesi gerekir.

### 4.10 Base ESP'yi çıkarıp taktıysan RESETLE

Köprü portu geri açıyor (`fd 32 → /dev/ttyUSB0`) ama telemetri gelmiyor, üç
drone da `connected=False`. ESP resetlenince mesh anında geri geldi.
**Köprünün portu geri açması yeterli değil.** *(29 Temmuz 2026)*

---

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

**Kural:** dronlara güç vermeden **önce** QGC'yi aç. MAVROS keşfettiği karşı
tarafı unutmaz, o yüzden sonradan kapatmak sorun değil — ama her
`docker restart droneN` pencereyi yeniden açar.

Kalıcı çözüm `gcs_url` = `udp://:14555@` (denendi, doğrulandı, uygulanmadı):
`YAPILACAKLAR.md` P1.7. *(17 Ağustos 2026)*

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

---

## Artık geçerli olmayanlar — arşivde var, burada yok

16 Ağustos'ta koda bakıldı, bu maddeler **kapanmış**; arşivde okursan
şaşırma:

| Arşivdeki iddia | Bugünkü durum |
|---|---|
| `/tools` toptan `.gitignore`'da, dosyalar sessizce commit'lenmiyor | Kalktı — yalnız `tools/aes_key.txt` yoksayılıyor |
| `tsconfig.tsbuildinfo` takip ediliyor | Takipten çıkmış (`git ls-files` = 0) |
| rosbag `--compression-mode file` → `reindex` kurtarmıyor | Düzeltildi: `--storage-config-file` ile mcap kendi sıkıştırıyor |
| `MAKS_EGIM_DEG` kodda sabit 35, `MPC_TILTMAX_AIR` varsayımı | `ucus_ayarlari.py` eğimi ivmeden türetiyor ve tutarsızlığı söylüyor |
| `gunluk/son` sembolik bağı kırık (mutlak yol) | `baslat.sh` göreli bağ kuruyor, iki Pi'de doğrulandı |
| `ORIGIN_ALT` yanlış (1218.5) | Kalkış irtifa çerçevesi düzeltildi; origin dosyası `1216.03` |
| ylp01'in ESP'si eski firmware'de / ylp01 ağda yok | ylp01 **yerde** — 2 Ağustos'ta düştü (`DURUM.md` §1) |
