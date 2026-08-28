# GÜNLÜK — oturum devir teslim kaydı

**Son güncelleme:** 28 Ağustos 2026, 11:45 — kamera sahada çalışıyor, QR 6-9 m'de okunuyor (rolling shutter çözüldü)

Tek bilgisayar, sırayla çalışıyoruz. Biri kalkıp diğeri oturduğunda **hem
kişi hem Claude** nerede kalındığını buradan anlar.

**En yeni kayıt en üstte.** Her oturumun sonunda yeni bir kayıt ekle —
atlanırsa sistem çöker, çünkü sohbet geçmişi sonraki kişiye geçmiyor.

Claude'a **"oturumu kapat"** dersen bu kaydı o yazar.

---

## Şablon (kopyala, en üste yapıştır)

```markdown
## YYYY-AA-GG SS:DD — <isim>

**Ne yapıldı**
- (somut, ölçülmüş sonuçlarla; "denedik" değil "şu çıktı")

**Ne değişti**
- kod: `dosya:satır` — ne, neden
- uçakta: hangi bayrak/parametre/dosya değişti (SONRAKİ KİŞİ ÖYLE BULACAK)
- belge: hangi md güncellendi

**Yarım kalan / tuzak**
- (bir sonraki kişinin bilmediğinde zaman kaybedeceği her şey)

**Sıradaki adım**
- (tek cümle, net; YAPILACAKLAR.md'deki madde numarasıyla)

**Uçakların bırakıldığı hâl**
- ylp00: (kill switch? pil? nerede? konteyner ayakta mı?)
- ylp02:
```

---

## 2026-08-28 11:20 — Eyüp + Claude (KAMERA: kurulum, kalibrasyon, QR tespiti çalışıyor)

> **Dört uçuş yapıldı** (ylp02, elle/RC). Kamera hiç çalışmıyordan
> "6-9 m'de QR okunuyor"a geldi. Tam ölçüm dökümü: **`docs/KAMERA.md`**.

**Ne yapıldı**

- **Arducam IMX477 ylp02'ye takıldı.** İlk "güç gelmiyor" sorunu flex'in
  **ters takılmasıydı** — kablo yanlış değildi.
- **`deploy/rpi/kamera_yayin.py` yazıldı** (~1600 satır, saf stdlib):
  MJPEG yayın, yerel kayıt (.mjpeg + .idx), foto çekme, keskinlik ölçümü,
  sistem sağlığı, tarayıcı arayüzü.
- **Kayıt tam çözünürlükte, yayın küçültülerek** — operatör isteği. Tek
  rpicam çıkışı üç tüketiciye dağıtılıyor; küçültme yalnız
  `/akis?kucult=1` yolunda. PIL Pi'ye **sudo'suz** kuruldu.
- **Pozlama kalibrasyonu.** Sabit 1/250 kareleri DOYURUYORDU (ort. 240/255,
  %37-45 tam beyaz kırpık) — ölçümü gölgede almıştım, sahne güneşte 15 kat
  parlaktı. `sport` otomatik kipe geçildi: kırpık %0.
- **Beyaz dengesi kalibrasyonu.** AWB ön ayarlarının **hiçbiri** düzeltmiyor
  (hepsi %25 sapma, magenta). Beyaz kâğıtla kapalı döngü ölçüm →
  sabit `[2.5923, 1.2225]`, sapma %0.
- **Dört uçuşluk QR testi** — sonuç tablosu `KAMERA.md` §5'te.
- **`kayit_coz.py`** çoklu mcap + `--irtifa-csv` desteği kazandı; çözümleme
  artık ROS'suz laptopta koşuyor.

**Ne bulundu — asıl mesele rolling shutter**

- Aynı QR **durağan fotoğrafta okunuyor**, motorlar dönerken **200 karede
  sıfır**. Operatör: "kaldırım taşlarında bile dalgalanma var."
- **Kare hızı jöleyi değiştirmiyor** — sürücü fps'i VBLANK ile ayarlıyor,
  satır okuma süresi sabit. 10→30 fps denendi, faydası olmadı.
- Kip değiştirmek okuma süresini gerçekten değiştiriyor (2K = yarı okuma).
- **Yalıtım 3-4 kat kazandırdı** (2K'da %4-25 → %62-76).
- Tavan (11 m) hâlâ **titreşimden**, boyuttan değil: 11-15 m'de QR'ın
  %67-78'i bulunuyor ama okunamıyor.

**Ne değişti**

- kod: `deploy/rpi/kamera_yayin.py` — yeni; `deploy/rpi/teshis/kayit_coz.py`
  — yeni; `swarm_perception` (camera_driver HTTP kaynağı, QR iki aşamalı
  tarama, LZ dairesellik) — daha önceki oturumdan
- uçakta (**ylp02**): kip `tamfov` varsayılan, pozlama `sport`, beyaz
  dengesi sabit `[2.5923,1.2225]`, kare hızı 30, yayın 640 px.
  **PIL `~/yelpence_ws/pylib`'de** (ylp00/ylp01'de YOK).
- belge: `docs/KAMERA.md` (yeni), `DURUM.md`, `YAPILACAKLAR.md`,
  `RPI_ESITLEME.md`

**Yarım kalan / tuzak**

- 🔴 **Uçuşta tarayıcı sekmesini kapat.** Açıkken CPU %90,7, mavros %74'te
  yarışıyor. Kapalıyken %67,5.
- **Konteynerdeki `swarm_perception` eski derleme** — `min_zone_area_frac`
  yok, canlı renk eşiği ayarı çalışmıyor. Yeniden derlenmeli.
- Renk eşikleri **magenta tondayken** kalibre edildi, artık geçersiz.
- Renk hedefi son üç uçuşta kadrajda değildi — renk irtifa eğrisi yok.
- Beyaz dengesi gün ışığına bağlı; akşam/kapalı havada yeniden ölçülmeli.
- ylp02'nin **PX4 güç soketi P0'ı** ve **HOME kayması P0'ı** bu oturumda
  ele alınmadı, ikisi de açık.

**Sıradaki adım**

- Yalıtımı derinleştir (P1.22). 🔒 **QR büyütülemez** — boyutu yarışma
  tarafından sabit, çözünürlük de tükendi. Tavanı açacak tek eksen
  titreşim: teorik tavan 34 m, gerçek 11 m, aradaki farkın tamamı jöle.

**Laptopta kurulanlar (yeni oturum bunları tekrar kurmaya kalkmasın)**

- `~/pylib_laptop` — `opencv-python-headless`, `zxing-cpp`,
  `imageio-ffmpeg` (statik ffmpeg 7.0.2 + libx264). Hepsi **wheel
  açılarak** kuruldu; laptopta `pip` YOK, `ensurepip` Debian'da kapalı.
  Kullanım: `export PYTHONPATH=$HOME/pylib_laptop`
- `~/yelpence_kayitlar/` — yedi uçuş kaydı (.mjpeg + .idx), `100509`'un
  irtifa CSV'si, iki MP4 (2K ve 4K yalıtımlı).
- Çözümleme **ROS'suz** koşuyor: `kayit_coz.py --irtifa-csv`.

**Uçakların bırakıldığı hâl**

- ylp00: kapalı, ağda değil. 3S 8000 mAh + 1045 pervane takılı.
- ylp01: kapalı, ağda değil.
- ylp02: kamera takılı ve **yalıtımlı**, kamera servisi ayakta (:8080),
  sürü düğümleri koşuyor, rosbag kayıtta. Oturum sonunda ağdan düştü.

---

## 2026-08-27 04:30 — Eyüp + Claude (OLAY DEFTERİ: YKİ paneli + mesh taşıması; 🔴 ylp02 güç soketi P0)

> Uzun bir gece: 26 Ağustos akşamı depoyu tanımakla başladı, olay defterinin
> uçtan uca çalışmasıyla bitti. **Uçuş yapılmadı, tamamı yer işi.**
> 11 commit.

**Ne yapıldı**

*1 — Devir teslim: 4 günün açığı kapatıldı*
- Yerel `main` 4 gün geriydi; iş `saha` uzağındaydı (28 commit). İlerletildi.
- 4 günün özeti okundu: dikey kaçınma, ilk formasyon uçuşu, ylp01'in
  dirilişi, P0.15'in kök nedeni (ESP↔Pi jumper konnektörü).

*2 — 🔴 ylp02'nin PX4 GÜÇ SOKETİ GEVŞEK — uçuş engeli*
- Operatör buldu: **sokete dokununca FCU yeniden başlıyor.** Daha önce iki
  kez görülüp ikisi de yanlış yorumlanmıştı ("Pi düğmesine bastım, PX de
  rebootlandı" → el kabloya çarpmış; "durduk yere rebootlandı" → aynı temas).
- Ölçüldü ve **elendi**: üç Pi'de de `get_throttled = 0x0`, EXT5V 5,13-5,18 V.
  Yani arıza PX'in KENDİ hattında, Pi ile paylaşmıyor — **Pi izlemesi bunu
  asla yakalayamaz**, ayrı bir sinyal gerekiyor.
- `TUZAKLAR` §2.19'daki ESP jumper'ıyla aynı sınıf ama sonucu kıyaslanamaz:
  jumper VERİ kaybettiriyordu, güç kesilince **uçuş kontrolcüsü ölür**.
  ⚠️ 2 Ağustos'ta ylp01'in düşüşü hâlâ aydınlanmadı — aday sebep.

*3 — YKİ OLAY DEFTERİ (Adım 1): panel + kalıcı kayıt + disk*
- `AlertManager` uyarıları 10 sn sonra siliyordu; defter AYRI tutuldu, uyarı
  motorunun davranışı değişmedi. **P1.16 KAPANDI** (uyarılar artık diske).
- Panel drone kartında: `▤ LOG` basınca kart **komple deftere dönüşüyor**,
  kritik olayda buton kırmızı yanıp sönüyor.
- Operatör iki kusur yakaladı ve ikisi de düzeltildi: üç kart birden log
  kipindeyken şerit çöküyordu; olaylar birikince kart yukarı büyüyordu.
  Çözüm sihirli sayı değil — telemetri akışta kalıp boyu belirliyor, defter
  mutlak konumlandırmayla akıştan çıkıyor.
- Pil değerlendirmesi **kapatıldı** (`alerts.pil`, varsayılan false): sahada
  ölçüm yok, PX4 tezgâhta sabit 12,6 V/%100 sentinel'i veriyor. Susturmadık,
  hiç üretmiyoruz — susturma GERÇEK bir sinyali gizlemektir.
- Mesafe üst başlıktan kartlara taşındı (yatay mesafe — çarpışma ölçütü de
  yatay, `TUZAKLAR` §3.12).

*4 — TIP_OLAY (Adım 3): olaylar mesh'ten akıyor*
- Protokolde olay tipi YOKTU; körlük alarmı DURUM bitine sıkıştırılmıştı.
  Artık `TIP_OLAY = 0x16`, **paket BÜYÜMEDİ** (16 bayta oturdu, `mesh_paket_t`
  25 bayt, UART tamponu 32 aynı). Flash %56,2 → %56,7.
- Metin taşınmıyor, **kod** taşınıyor; metni YKİ üretiyor.
- Bütçe drone başına 1/sn, her olay 3 kez tekrar. Operatör kararıyla
  **düşürme → KUYRUK**: "ilk gelen hemen gider, diğeri sırada bekler."
  Yan fayda: tepe yük = sürekli hâl, yani öngörülebilir (baz→YKİ UART'ı
  ~35 çerçeve/sn ve olay yolu en kötü 9 = %26).
- `sira_no` ile YKİ **boşluk görebiliyor**. Tekrarlar sıra dışı vardığı için
  gecikmeli onay kullanılıyor — naif sayaç uydurma kayıp raporlardı.
- Mimari: bütçe/kuyruk/boşluk ve eşik/histerezis **ROS'suz saf modüllerde**
  (`olay_kuyrugu.py`, `sistem_sagligi.py`), `rtk_pure.h` kalıbı.

*5 — Pi sistem sağlığı olayları (kod 60-68), histerezisli*
- Veri zaten toplanıyordu (`yelpence_izle.sh`); ikinci izleme kurulmadı.
- Eşikler ÖLÇÜME dayanıyor: Pi 5 boşta **56-64 °C**. Operatörün önerdiği
  50 °C alınmadı — sürekli alarm verirdi. Uyarı 70/65, kritik 80/75.

*6 — MAVROS onarım politikası (operatör kararı)*
- Otomatik onarım artık **Pi uptime kapısında** (<15 dk). Ölçüt konteyner
  uptime'ı DEĞİL — o her restart'ta sıfırlanıp sahte "ilk açılış" yaratırdı.
- Kapının dışında onarım YOK; köprü KRİTİK olay basıyor, karar operatörde.

*7 — Firmware DÖRT karta, kablo sökülmeden*
- `eabe59f` üç drone + baz. Yöntem: konteyner durdur → operatör **BOOT+EN**
  → `esptool --before no-reset` → EN → konteyner başlat. Baz USB'den
  (`--no-stub` şart; `TUZAKLAR` §4.4 aynen tetiklendi).
- Dördünde de **hash doğrulandı**. Provenans boşluğu kapandı (öncesinde
  ylp01'in `.bin`'i commit'ten eskiydi).
- ⚠️ `.bin` dosya boyutu hizalama yüzünden yuvarlanıyor — **provenans
  göstergesi olarak kullanılamaz**. Doğrulama davranıştan.

*8 — Uçtan uca doğrulama (iki kez, iki uçaktan)*
```
04:23:34  d1 [KRITIK]  Carpisma riski (2, collision_avoidance)   <- MESH
04:23:34  d3 [KRITIK]  Carpisma riski (2, collision_avoidance)   <- MESH
04:23:35  d2 [KRITIK]  Baglanti koptu                            <- YKI telemetrisi
04:23:37  d3 [bilgi ]  [yedek tespit] ...                        <- bazin yedegi
```
Ayırt etme ölçütü: **mesaj alanı boşsa mesh'ten gelmiştir.**

**Canlı testin yakaladığı, birim testlerin göremeyeceği dört kusur**

1. 🔴 `_diag_yayinla` saniyede bir olay yayıyordu; aktarılınca **bütçenin
   tamamını yiyor** ve GERÇEK olayların düşmesine yol açıyordu. Olay yolu
   tam da iş görmesi gereken anda susardı. (3,0 çerçeve/sn → 0,00)
2. Aynı olgu **üç bağımsız dedektörden** bildiriliyordu. Bazın tespiti
   INFO'ya indirildi ve `[yedek tespit]` etiketlendi — silinmedi, çünkü
   bütçe tıkanırsa ya da bir uçak eski firmware'deyse tek gören o olur.
3. `dagit.sh` **`izleme_kur.sh`'i taşımıyordu**; uçaklarda 22 Ağustos'tan
   kalma sürüm duruyordu. Tam da o dosyanın uyardığı sessiz kayma.
4. `drone_bul.sh` sudo'lu komutlara TTY ayırmıyordu (iki kez tökezlendi).

**Ne değişti**
- kod: `dd5a1e6 8f21515 f5649a0 73e06e1 eabe59f d8ae3df 3c21e6a ff148f3
  59a7c53 38be7da 1219837 61ba6c9`
- uçakta: Python `61ba6c9`, ESP firmware `eabe59f` (üç drone + baz)
- belge: TUZAKLAR §1.25-1.27 §2.23, RPI_ESITLEME D4/D5 + defter kaydı,
  YAPILACAKLAR iki P0, DURUM, bu kayıt

**Yarım kalan / tuzak**
- 🔴 ylp02 güç soketi — **düzeltilmeden ylp02 UÇMAZ**
- 🔴 26 Ağustos'un HOME kayması P0'ı **hâlâ açık** (bu gece dokunulmadı)
- 🟠 MAVROS taşkınının **kök nedeni** hâlâ bilinmiyor (`mavconn/udp.cpp:325`)
- 🟡 `EVENT_PX4_REBOOT` (kod 69) yazılmadı — taşıma yolu artık hazır
- Görev düğümleri kapalı olduğu için defter bugün yalnız körlük görüyor;
  görev zinciri açılınca **kod tarafında ek iş olmadan** zenginleşecek

**Uçakların bırakıldığı hâl**
- Üçü de açık, disarm, mesh'te (`komsu_veri=2/2`), Python `61ba6c9`,
  firmware `eabe59f`. Formasyon-sürer modda (`/ws/gozlem` YOK).
- YKİ açık (backend + RTCM reader + baz köprüsü). Pil ölçümü kapalı.

---

## 2026-08-26 02:37 — Berk + Claude (gece: İLK FORMASYON UÇUŞU + OTONOM CA GEÇİŞİ; 🔴 HOME kayması bulundu)

> Akşam kapanışından (21:56) sonra devam edildi: ADIM 3 hazırlıkları,
> hub kazası, ve İKİ TARİHİ UÇUŞ. Kod: `db58414..89a16cf` + belgeler.

**Ne yapıldı**

*1 — ADIM 3 hazırlıkları (uçaklar kapalıyken)*
- PLAN "Engel 3 açık" diyordu; kod okununca `velocity_only`'nin 21 Ağu'dan
  beri OTOMATİK olduğu görüldü (CA açıkken zaten true) — belge koda
  eşitlendi (`db58414`).
- **Tek-üretici geçişi `baslat.sh`'e kondu (`20c2b01`):** formasyon
  SÜRERKEN esp32_bridge çıkışı `/gozlem/.../mesh_goto`ya (uçağı süremez;
  `/raw`'ın tek üreticisi formation_node). Boş-yuva kapısının ARKASINA
  kondu (kapı gözlemi zorlayabiliyor). Üç senaryo sahte /ws ile masada
  doğrulandı; formasyon sürmüyorken davranış birebir eski.

*2 — USB hub kazası ve kalıcı DTR/RTS düzeltmesi*
- Operatör hub ekledi → port adları değişti → RTK reader ESKİ portta,
  backend'in ESP köprüsü KOPUK (lsof boş). `yki_mac.sh` ile (VID:PID)
  yeniden başlatıldı.
- Köprünün ilk açılışı base ESP'yi BOOTLOADER'a kilitledi (bilinen
  DTR/RTS tuzağı) → **kalıcı düzeltme `89a16cf`:** esp32_bridge seri
  portu artık dtr=False rts=False ile açıyor (nesne portsuz kurulur,
  hatlar çekilir, sonra open). Uçakta zararsız (ttyAMA4). Kilit, log
  portunun tetiklediği temiz boot'la kırıldı; akış geri geldi.
- Dağıtım: `20c2b01`+`89a16cf` üç uçağa (kopya+build+restart), açılış
  doğrulamalı (`b38b652`). Bulgu: **drone1'in docker json logu KORUPT**
  (docker logs hata veriyor) — doğrulama canlı topolojiden yapıldı
  (mesh_goto konusu + param). rosbag etkilenmez.

*3 — G0: üç-uçaklı formasyon hesabı YERDE doğrulandı*
- `form_yayinla.sh` üç-uçak varsayılanına çevrildi ([1,2,3], spacing 12).
- Mesh'ten V tarifi → üç uçağın formation_node'u DOĞRU slotları hesapladı:
  merkez ~1 cm, kanatlar tam 12,0 m, kanatlar arası 90°, z=-8 ✓.

*4 — 🎯 İLK FORMASYON UÇUŞU (ADIM 3 HAVADA) — 3 uçak, ok başı/V*
- Operatör kararıyla tek-uçak ara adımı atlandı; ultracode İSTENDİ,
  operatör ATLADI (KARAR-02 notu).
- Hareket-minimize tarif (merkez/heading optimizasyonu): hareketler
  2,1-4,6 m; geçişte araları ≥7,2 m.
- Kalkış 8 m (tarifsiz → pozisyon-hold), 5 sn, V tarifi (tip 2, spacing 8,
  hız 1,0): üçü ~15 sn'de slotlarına oturdu — **hedeflere ~1 m, yaw üçünde
  330° senkron, 20+ sn milimetrik sabit, salınım YOK**. RTL ile üçü kendi
  kalkış noktasına NOKTA ATIŞI indi (o uçuşta home'lar doğruydu).
- İrtifa notu: tarif z=-8'e karşın gerçek ~8,8-9,3 m (origin/EKF z farkı
  ~1 m) — zararsız, kayda geçti.

*5 — 🎯 OTONOM CA GEÇİŞ TESTİ (ÇİZGİ tip 3) + İKİ AÇIK SORU*
- Kurgu: ylp00 8 m'de ÇAKILI lider (tarif dışı); ylp01+ylp02 ÇİZGİ
  formasyonuyla liderin 15 m gerisinde toplandı (hatlar ±3,0 m — şablon
  koddan doğrulandı: 2 ajanda merkez+yan), sonra merkez 30 m güneye
  taşındı → düz geçiş.
- **Sahada gözlenen (operatör):** ylp01 liderin ÜSTÜNDEN (~11 m), ylp02
  ALTINDAN geçti (⚡ **rütbe-AŞAĞI kaçışın İLK gerçek uçuşu** — 8 m'de
  aşağı hedef ~5 m > taban 4) ve geçişi tamamladılar; lider kıpırdamadı.
- ⚠️ AÇIK 1: ylp02 geçiş sonrası nominale dönüşte 6,4 m'de TUTUK kaldı
  (körlük yok — sebep bag/ca.log analizinde; SSH o an kopuktu).
- 🔴 AÇIK 2 (P0): **HOME KAYMASI** — RTL basılınca d1/d2 (ve görünüşe
  göre d3 de) kalkış yerlerine değil, ÜÇÜ AYNI CİVARA (kalkışların ~9 m
  KD'si, birbirine 1-2 m) indi. Ölçüm: PX4 home kayıtları TAM iniş
  noktaları — yani RTL doğru uçtu, HOME'LAR YANLIŞTI. Kök (ARM anı
  konumu mu, eski home mu, origin/EKF mi) rosbag'deki home_position +
  statustext geçmişinden çıkarılacak. **ÇÖZÜLMEDEN RTL'Lİ UÇUŞ YOK.**
- Not: kumandalar bu uçuşta hep KAPALIYMIŞ (operatör beyanı) — OFFBOARD
  RC'siz uçtu; RC-loss failsafe'in OFFBOARD istisnası da ayrıca
  incelenmeli (P1).

*6 — Saha pratikleri*
- iPhone hotspot MESAFE hassas: uçak güneye uçunca ylp02 SSH koptu
  ("host down") — mesh ETKİLENMEZ. Kural: telefon uçak grubunun ortasında.
- YKİ paneli "sürekli KRİTİK körlük" toast'ları: iki alıcının drone2'yi
  21 ms arayla kaybetmesiyle teşhis edildi — ELDE TAŞIMA gölgelenmesi
  (TUZAKLAR §4.12'ye yazılmıştı; bir kez daha yaşandı, kural işledi).

**Ne değişti**
- kod: `db58414` `20c2b01` `b38b652` `89a16cf` (+ form_yayinla üç-uçak)
- uçakta: üçü `89a16cf` seviyesinde (build'li); formasyon-sürer modda
  bırakıldı mı → HAYIR: uçuş bitti, konteynerler formasyon-sürer modda
  AMA uçaklar disarm/kapatılacak. ⚠️ SONRAKİ AÇILIŞTA: `/ws/gozlem` YOK
  → yine formasyon-sürer modda açılırlar (mesh goto uçağa gitmez!).
  Eski goto düzeni istenirse `touch /ws/gozlem` + restart.
- belge: GUNLUK, DURUM, YAPILACAKLAR, KARARLAR (KARAR-02 notu), CA §6.7,
  PLAN (ADIM 3 uçtu)

**Yarım kalan / tuzak**
- 🔴 HOME kayması P0 (yukarıda) — bag analizi: `/drone_N/mavros/
  home_position/home` zaman serisi + statustext "home" mesajları.
- 🟠 ylp02 dönüş tutukluğu — aynı bag'den + ca.log.
- 🟡 drone1 docker json log korupt — `docker logs` çalışmıyor; kalıcı
  çözüm konteyner recreate (docker save imajından) ya da log dosyasını
  sıfırlamak. Rosbag'ler sağlam.
- Formasyon tip kodu notu: FORMATION_OKBASI=1 ile FORMATION_V=2 AYRI —
  "ilk formasyon uçuşu" tip 2 (V) ile uçtu; OKBASI şablonu henüz uçmadı.

**Sıradaki adım**
- P0 HOME analizini yap → temizse ikinci formasyon tipi/OKBASI ve ADIM 3
  kalanları (mission zinciri) planlanır.

**Uçakların bırakıldığı hâl**
- Üçü disarm, kalkışların ~9 m KD'sindeki iniş noktalarında yan yana;
  kapatma operatörde. Pil gerçek durumu BİLİNMİYOR (sensör yok) — gece
  4 uçuş yapıldı, şarj önerilir.
- YKİ: backend+reader+köprü açık bırakıldı (`yki_durdur.sh` ile kapanır).

---

## 2026-08-25 21:56 — Berk + Claude (akşam sahası: 8 test/uçuş 8'i GEÇTİ, İLK ÜÇ UÇAKLI UÇUŞ)

**Ne yapıldı**

*1 — RTK: taze survey + reader doğru porta (akşam açılışı)*
- u-blox takılınca reader hâlâ sabahki `-YOK` portundaydı → doğru portla
  yeniden başlatıldı; **dünkü hafıza-survey tuzağına karşı** rover→survey-in
  ile SIFIRDAN survey (60 sn, 2 m hedef) → 1005 akışta.
- **Filo ilki: ÜÇ uçak aynı anda RTK-Fix** (31-32 uydu).
- Ders: paneldeki "reset" düğmesi survey SIFIRLAMAZ (cihaz reboot'u; üstelik
  donuk bırakabiliyor). Saha değişince taze survey Claude'dan istenir.

*2 — TEST 0: KARAR-04 ARM'lı yer testi (pervaneler SÖKÜLÜ)*
- **Tur A:** üç uçak sürü yolundan AYNI ANDA ARM — 3/3 `success` (safety
  button'lar basılınca `ready_to_arm` üçünde true; PX4 ~10 sn'de oto-disarm).
  Bulgu: FSM görev başlamadan FORMING'e geçmiyor (`mission_active=false`) —
  FORMING doğrulaması üç uçaklı ilk göreve entegre olacak, yerde görülmez.
- **Tur B:** ylp02 konteyneri durduruldu (kayıp simülasyonu): 2 sn'de CA
  körlük alarmı, ~3 sn'de `active_agent_count` 3→2, **ACİL İNİŞ YOK**
  (2/3=%67 > %50), ESP komşu tablosu tutarlı düştü; geri gelince 3'e döndü.
  **KARAR-04 dayanıklılık beklentisi sahada doğrulandı.**
- Not: ARM servis komutunu Claude'un kabuğu gönderemiyor (güvenlik
  sınıflandırıcısı); operatör `!` ile çalıştırdı — iş bölümü: izleme Claude,
  ARM satırı operatör.

*3 — TEST 1: ylp01 kazadan 24 saat sonra İLK GÖREV UÇUŞU*
- `asili` 4,8 m / 60 sn: arm teyit 2,5 s, tırmanış temiz, oturma 4,60 m
  (vz=-0,12), sapma 0,4 m, land düzgün. **Mesh→CA→px4_bridge zinciri yeni
  Pi+Pixhawk+ESP ile uçuşta doğrulandı.**

*4 — TEST 2 + GÜNÜN BULGUSU: körlükte dönüş 34 sn bloke*
- ylp01 asılı + ylp00 elde: kaçış girişi tam 4,0 m'de, tırmanış 7,9'a ✓ —
  ama operatör çekildikten sonra **dönüş gelmedi**; 60 sn dolunca 7,4 m'den
  land. Bag analizi: çıkış eşiği (6,5 m) t=37'de aşıldı, kaçış t=71'e dek
  tutuldu (**34 sn**), d_xy 13,5 m'ye çıkmıştı.
- **Kök neden ARIZA DEĞİL:** 23 Ağu'da eklenen körlükte-dönme koruması.
  Sabah açık olan ylp02 test öncesi KAPATILINCA "görülmüş-ama-kayıp" =
  körlük kuruldu (`kor_komsu=[3]`), koruma dönüşü bilerek tuttu. Dün aynı
  test dönmüştü çünkü ylp01 mesh'e HİÇ girmemişti (hiç görülmemiş komşu
  körlük sayılmaz).

*5 — Çözüm: körlük yerde-pasif muafiyeti (`6258eab`) + doğrulama*
- `komsu_yerde_pasif()` (ca_core, saf): kayıp komşunun SON durumu
  **yerde + disarm + z geçerli** ise dönüş tutması UYGULANMAZ (kapalı/düşmüş
  uçak); havada/arm'lı kayıp AYNEN korunur (46,4 sn mesh vakası sınıfı).
  Alarm her durumda basılır. Tanıya `kor_tutan=` alanı eklendi.
- `korluk_yer_esigi_m=1.5` (ucus_ayarlari + baslat.sh `KACINMA_KORLUK_YER`).
  5 yeni birim test, **35/35**. Canlı yerdeki uçak hâlâ kaçış tetikler
  (elde-taşıma test yöntemi ve kalkış koruması bilerek korundu).
- **Üç uçağa dağıtıldı** (dosya + colcon build + restart; üçünde param 1.5).
- **Yer doğrulaması:** ylp02 bilerek aç-kapat → alarm geldi, muafiyet logu
  düştü, `kor_komsu=[3] kor_tutan=-`.
- **Uçuş doğrulaması:** aynı körlük koşulunda ylp01 ile tekrar: ÜÇ tam
  yaklaş-kaç-çekil-DÖN çevrimi (tepe 8,5/7,9/7,1 → hep 4,5'e, ~0,5 m/s);
  `donus_kor=0`. ylp02 açılınca körlük kendiliğinden temizlendi.

*6 — FİNAL: İLK ÜÇ UÇAKLI EŞZAMANLI UÇUŞ + çok-komşulu CA (147 sn)*
- Düzen (operatör fikri, doğrusu buydu): **manuel uçak = ÇAPA (ylp00)** —
  çapa zaten kaçmaz, hiçbir davranış kaybolmaz; ylp01+ylp02 görevle asılı
  (4,8 m, 120 sn, aralarında ~10 m).
- Operatör ylp00'ı iki uçağa da İKİŞER kez yaklaştırdı — 4/4 çevrim temiz:
  ylp01 tepe **9,6 m** ("2 komşu etkide" — merdiven üst basamağı) ve 8,8;
  ylp02 tepe 8,7 ve 7,7, ikisinde de **`dikey_yetersiz` → taban aynası
  YUKARI** (rütbe-AŞAĞI uçağın taban davranışının ilk saha kanıtı).
  Dönüşler hep 4,5'e; sıfır körlük, sıfır yatay son çare; inişler nokta.
- Uçuş sırasında YKİ KRİTİK körlük uyarıları görüldü (uçuş ÖNCESİ):
  drone1 ve drone3, drone2'yi **aynı anda** (21 ms arayla) kaybetmişti →
  suçlu alıcılar değil, **elde taşınan uçağın ESP'sinin gölgelenmesi**
  (uçak taşınırken 2 sn'lik kesintiler normal). Canlı kural: uçuşta körlük
  KRİTİĞİ ekrandayken yaklaştırma YAPILMAZ.

**Ne değişti**
- kod: `6258eab` — ca_core `komsu_yerde_pasif`, node `_korluk_tutanlar`
  filtresi + muafiyet logu + `kor_tutan` tanısı; baslat.sh + ucus_ayarlari
  `KACINMA_KORLUK_YER=1.5`; test_ca_dikey +5 test.
- uçakta: **üçü de `6258eab`** (build + restart, 25 Ağu ~21:00); başka
  parametre/bayrak değişmedi. RPI_ESITLEME güncellendi.
- belge: DURUM, YAPILACAKLAR, KARARLAR (KARAR-07), CA §6.6, TUZAKLAR §4,
  RPI_ESITLEME, GUNLUK (bu kayıt).

**Yarım kalan / tuzak**
- Muafiyetin "havada kayıp → tutma sürer" dalı yalnız birim testli (sahada
  üretmek tehlikeli — bilinçli sınır).
- Berk'in sabah gözlemleri: TEST 2 tekrarının ilki boşa gitti (uçaklar
  yanlış yerde, yaklaşılamadı) — test öncesi konum teyidi şart.
- KARAR-02 denetimi bu CA değişikliği için soruldu, operatör ultracode
  YAZMADI → kendi denetim + 35 test + kademeli doğrulamayla uçuldu.

**Sıradaki adım**
- ADIM 3 (formasyon) — ilk uçuş öncesi `KARAR-02` ultracode + tek-üretici
  geçişi (YAPILACAKLAR "SONRAKİ OPERATÖRE").

**Uçakların bırakıldığı hâl**
- Üçü de sahada kendi noktalarına indi, disarm; kapatma/pil operatörde.
- YKİ backend + RTCM reader Mac'te açık bırakıldı (kapatılacaksa operatör).

---

## 2026-08-25 02:30 — Berk + Claude (12 saatlik maraton: hist_m UÇTU-GEÇTİ, ylp01 DİRİLDİ)

> 24 Ağu öğlen 14:00'ten 25 Ağu gece 02:30'a tek oturum. Dört perde:
> masa başı (hist_m) → ylp01'in yeni Pi'si → gece YKİ/ESP kurtarmaları →
> gece uçuşu. **11 commit, hepsi ölçüm kanıtlı.**

**Ne yapıldı**

*1 — `hist_m` 0,5 → 2,5 + birleşik dağıtım (öğlen)*

- Zincir HİÇ yokmuş: env'de değişken yok, `baslat.sh` geçmiyor, düğüm
  gömülü 0,5'te. Kuruldu: `ucus_ayarlari.py` → env → `-p hist_m` → düğüm.
  Denetime "çıkış ≥ kritik yaklaşma = HATA" koşulu. Birim 82/82.
- **Operatör kararı:** `tatmin` düzeltmesiyle BİRLİKTE dağıtıldı (tek
  değişiklik kuralından bilinçli sapma — gerekçe `KARARLAR`). İki uçakta
  canlı doğrulama: `hist_m=2.5`, rütbe 0/1.
- Harita artık **kaçış zarfını çiziyor** (sarı kesikli, iniş dış halkası,
  ayak izinde zarflı kutu) — P1 kapandı.
- Kumanda-uçak eşleşmesi ÖLÇÜLDÜ: 1.→ylp00, 2.→ylp02, çapraz karışma yok
  (`teshis/rc_izle.py` kalıcı araç).

*2 — ylp01'in YENİ Pi'si (öğlen/akşam)*

- ylp02'nin SD imajı klonlanıp yeni Pi'ye takıldı; `ylp01_donusum.sh`
  kimliği çevirdi (kullanıcı/hostname/SSH anahtarları/tgt_system=2).
  `drone2` yeni oluşturuldu → log döndürme A12 ✅. RPI_ESITLEME'nin tüm
  "ylp01 döndüğünde" listesi klonla tek seferde kapandı; A/K tabloları
  güncellendi. Yeni wlan0 MAC `88:a2:9e:67:6e:ff`.

*3 — Gece kurtarmaları (YKİ + ylp01 ESP + Pixhawk)*

- **RTK reader** eski port adını bekliyordu (USB yeniden numaralandı) +
  QGC'nin RTK autoconnect'i u-blox'u kapmıştı → port düzeltildi, QGC
  ayarı kapatıldı. u-blox gece 3 KEZ USB askısına düştü (tak-çıkarlara
  hassas) — her seferinde çek-tak düzeltti.
- **Base ESP donmuştu** (ne veri ne log) → RST düğmesi diriltti; köprü
  doğru portla yeniden başlatıldı → ylp00/ylp02 panele döndü.
- **ylp01 ESP'si üç katmanlı sorun çıkardı** (hepsi ölçümle):
  (a) 2 Ağu öncesi ESKİ firmware (UART düzeni+kanal farklı),
  (b) ESP DEĞİŞMİŞ — fiziksel MAC `...0A:B4`, tablodaki `...13:88`,
  (c) Pi→ESP RX teli KOPUK. Çözüm: **MAC takma adı** mekanizması
  (`mac_takma_tablo`, `esp_wifi_set_mac` — ilk deneme
  `esp_base_mac_addr_set` TUTMADI, sahada ölçüldü) + güncel
  `esp32dev_serial0` derlemesi **Pi üzerinden flash** (`esptool
  --no-stub`, Ubuntu paketinde stub eksik) + tel takıldı. Boot:
  `[MAC] takma ad (OK) ... [MESH] MAC: ...13:88`. Diğer üç cihaza
  DOKUNULMADI.
- **Pixhawk (yeni FC):** Here4 CAN sorunu kablo/port işiyle çözüldü
  (pusula+GPS geldi), `MAV_SYS_ID` 3→2, uçağa takıldı → MAVROS bağlandı
  → **panelde "Drone 2 | yerde | gps=3D→RTK-Fix"**. Zincir uçtan uca.
- RTK survey **3,5 saatlik içeride-zehirlenmiş ortalamada 3,6 m'de
  takılıydı** → TMODE rover'a çekilip yeniden başlatıldı → açık gökte
  60 sn'de bitti, 1005 aktı, iki uçak **RTK-Fix**.

*4 — 🎯 GECE UÇUŞU (02:03): dönüş davranışı DOĞRULANDI*

Kuru test + zarflı harita + operatör onayı + RTK-Fix ile. ylp02 4,8 m
asılı 120 sn; operatör ylp00'ı 3 kez yaklaştırıp uzaklaştırdı:

```
inis baslarken d_xy : 7,19 / 8,25 / 7,46 m   (hedef >=6,5 — dun 4,9)
iceride dalis       : YOK          donus hizi : 0,50-0,51 m/s
tirmanma tepe hizi  : 1,27-1,32    en yakin   : 3,52 m
```

Tırmanma +4,6 m (dün +3,1) hata değil: operatör yüksekte uçtu, hedef
"komşu irtifası + katman" onu izledi (9,1 m AGL). **Yo-yo kapandı;
ADIM 4 İKİ UÇUŞLA TAM.**

**Ne değişti**

- kod: `ucus_ayarlari.py`/`baslat.sh`/`ca_core`/düğüm (hist zinciri) ·
  `gorev_kanit_ucus.py` (zarf haritası) · `teshis/rc_izle.py` (yeni) ·
  `deploy/rpi/ylp01_donusum.sh` (yeni) · `firmware TX DRONE main.cpp` +
  `mesh_shared/mesh_config.h` (MAC takma adı; `esp_wifi_get_mac`)
- uçakta: ylp00+ylp02 **`7645d83`** ve `hist_m=2,5` (canlı doğrulandı) ·
  ylp01: yeni Pi + yeni ESP firmware'i + FC sysid=2 · ylp01'de
  `/usr/local/bin/ylp01_donusum.sh` kaldı (zararsız) ve `kayit/` altında
  ylp02'nin eski kayıtları duruyor (klon kalıntısı)
- belge: `CA` §7 · `PLAN` "SIRADAKİ UÇUŞ" ✅ · `DURUM` · `YAPILACAKLAR` ·
  `KARARLAR` · `RPI_ESITLEME` · `cihazlar` (ESP MAC takma notu)

**Yarım kalan / tuzak**

- 🟠 02:03 uçuşunun **gaz-doyum analizi yapılmadı** (tırmanma +4,6 m =
  doyum uzamış olabilir; kayıt ylp02'de, `vfr_hud`dan bakılacak)
- 🟠 u-blox USB askısı gece 3 kez — reader'a kendini-toparlama + panel
  alarmı eklenecek (YAPILACAKLAR)
- ⚠️ Panel reset butonu u-blox'u DONUK bırakabiliyor (çek-tak gerekti)
- ⚠️ Firmware derleme ortamı GEÇİCİ venv'de (job tmp) — kalıcılaştır
- ⚠️ ylp01 uçuş İZNİ YOK: ESC güç hattı onarımı + ivme/jiro/seviye
  kalibrasyonları + RC failsafe + param karşılaştırma + jumper (A16)
  duruyor. Kadroya girince `SURU_KADRO="1 2 3"` üç uçakta (KARAR-04).

**Sıradaki adım**

ADIM 4 tamamen kapandı. Operatörle seçilecek: **ADIM 3'e (formasyon)
geçiş** — ilk uçuş öncesi `KARAR-02` gereği **ultracode** istenir — ya da
ylp01'in uçuşa hazırlanması (ESC hattı + kalibrasyonlar).

**Uçakların bırakıldığı hâl** (02:23 ölçüldü)

- ylp00: KAPALI (uçuş sonrası kapatıldı)
- ylp01: KAPALI (uçuş öncesi bilerek kapatıldı — mesh'te komşu olmasın)
- ylp02: KAPALI (uçuş sonrası kapatıldı)
- YKİ (Mac): **TÜM süreçler KAPATILDI** (02:35 — backend, base köprüsü,
  rtcm reader, origin yayıncıları, frontend; `pgrep` ile doğrulandı).
  u-blox + base ESP fiziksel olarak USB'de takılı duruyor. Yarın açmak
  için: `src/gcs/yki_baslat.sh` (macOS notu betiğin başında)

---

## 2026-08-23 22:15 — Osman + Claude (DİKEY kaçınma HAVADA ÇALIŞTI)

> Aynı günün ikinci oturumu. Sabah yazılan dikey kaçınma akşam uçtu ve
> çalıştı. Uçuş iki gerçek bulgu çıkardı ve **bir teşhisimi çürüttü.**

**Ne yapıldı**

*1 — Uçuş öncesi tam kontrol dizisi*

Batarya değişimi sonrası: QGC 14550 ✅ · canlı düğüm parametreleri
doğrulandı (`rutbe` 0/1, tüm dikey ayarlar) · RTK ikisi de fix=6/32 uydu
(ylp00 ~15 dk FLOAT'ta kaldı, RTCM 6/s akıyordu, kendiliğinden oturdu) ·
parametre ayrışması yok · titreşim **ylp00 armed 0,021 m, ylp02 0,014 m**
(eşik 0,25; 1 Ağustos'ta devrilen kalkışta 0,111 m'ydi) · kuru test + harita.

⚠️ `docker logs` (tail'siz) ylp00 için **eski açılışı** gösterdi — `TUZAKLAR`
§1.18'in canlı hâli. Canlı düğüme `ros2 param get` ile sorulunca doğru çıktı.
**Log'a değil düğüme sor.**

*2 — 🎯 DİKEY KAÇINMA UÇTU VE ÇALIŞTI*

ylp02 4,8 m'de asılı, operatör ylp00'ı kumandayla üzerine sürdü.

```
tirmanma       : +3,1 m ve +2,8 m      (tasarim hedefi 3,0 m)
tepe hiz       : 1,25 m/s              (PX4 tavani 1,2 — doygun)
donus          : 0,50 m/s -> nominale 4,79 m (iki kez)
yatay itme     : HIC ACILMADI (vx=vy=0,00 bastan sona)
en yakin yatay : 3,20 m
alarmlar       : dikey_yetersiz=0 donus_kor=0 korluk=0
```

*3 — 🔴 Bir teşhisim ÇÜRÜTÜLDÜ*

Operatör yo-yo gözledi. "CA ayrım sağlanınca yetkiyi bırakıyor" diye teşhis
koydum ve düzeltme yazdım. **İki ayrı benzetim denemesi de yo-yo'yu
üretemedi** (genlik 0,00 ve 0,05 m).

Kayıttan yatay mesafe çıkarılınca gerçek çıktı: **4,5 m sınırından tam 4
geçiş** var, yani iki tam giriş-çıkış. ylp00 içerideyken ylp02 irtifasını
**tuttu** (t=18,7-22,1: 7,70 → 7,50 m); inişler yalnız `d_xy > 4,5 m`
olduktan sonra başladı.

Sistem doğru davranmış. Yo-yo gerçek ama **operatör kaynaklı**: "içerideyim"
ile "çıktım" arasındaki fark **1,2 m** ve gözle ayırt edilemiyor.

**Ders:** ölçmeden teşhis koydum, düzeltme bile yazdım. Doğrulama adımı
olmasa yanlış bir hikâye belgeye girecekti.

*4 — İki gerçek bulgu*

- 🔴 **İtki payı ince.** Askı gazı **%72** (belgede %66'ydı — `TUZAKLAR`
  §0.3 kapandı). Kaçış geçişlerinde gaz **%100'e doyuyor**: toplam ~2,5 sn,
  en uzun kesintisiz blok 0,7 sn. `MPC_Z_VEL_MAX_UP` yükseltme fikri
  **ölçümle kapandı.**
- 🟠 **Dönüş fazla aceleci.** Çıkış 4,5 m + 2 sn; komşu hâlâ yakınken ayrım
  6 sn'de geri veriliyor. Öneri `hist_m` 0,5 → 2,5-3,0.

**Ne değişti**

- kod (**COMMIT'Lİ, dağıtıldı**): sabahki dikey kaçınma paketi (`1d1048e`)
  + `cbf948c` (benzetim TABAN eşitleme, `asili` senaryo uyarısı)
- kod (**COMMIT'Lİ, DAĞITILMADI**): `ca_core` — `tatmin` durumunda dikey
  yetki bırakılmıyor + 3 yo-yo regresyon testi. **Uçuştaki davranışı
  düzeltmiyor**, ayrı bir durumu sertleştiriyor.
- uçakta: batarya değişimi dışında değişiklik YOK. Uçaklar `1d1048e`.
- yeni araçlar: `teshis/g0_dikey_datum.py` · `g0_dikey_gozlem.sh` ·
  `g0_korluk_tutma.sh`
- belge: `CA.md` §6.5 + §7 · `TUZAKLAR` §0.3 (cevaplandı) §3.13 §3.14 ·
  `KARARLAR` (KARAR-06 uçtu, `MPC_Z_VEL_MAX_UP` vazgeçildi) · `DURUM` ·
  `YAPILACAKLAR` · `PLAN`

**Yarım kalan / tuzak**

- 🔴🔴 **DEPO UÇAKLARDAN İLERİDE.** Uçaklar `1d1048e`, depo daha yeni.
  Sonraki oturumun ilk işi: dağıt ya da farkı bilinçli olarak belgele.
- 🟠 `hist_m` düzeltmesi yapılmadı — sıradaki uçuşun konusu.
- 🔴 İtki payı ince; dikey ivme artırılmamalı.
- 🟠 Kuru testin haritası **kaçış zarfını göstermiyor** (~5 m yanal + 3 m
  dikey). Operatöre elle söylendi; araca eklenmeli (~20 satır).
- 🟠 Kumanda hangi uçağa bağlı hâlâ netleşmedi.
- ⚠️ `KARAR-02` denetimi operatör kararıyla **atlandı**; gerekçesi
  `KARARLAR`'da. Sonraki düğümlerde (ADIM 3) yeniden geçerli.
- ⚠️ PX4 titreşim/clipping konusu akmıyor; ölçüt konum sıçraması.

**Sıradaki adım**

Yine **çarpışma önleme** (operatör kararı): `hist_m` genişletilip dönüş
davranışı doğrulanacak. Tam tarif `PLAN.md` "SIRADAKİ UÇUŞ" ve
`YAPILACAKLAR` "SONRAKİ OPERATÖRE" bloğunda.

**Uçakların bırakıldığı hâl**

- **ylp00:** yerde, disarm, pervaneler **TAKILI**, 11 düğüm, `rutbe=0`
  (ÇAPA). Kod `1d1048e`.
- **ylp02:** yerde, disarm, pervaneler **TAKILI**, 11 düğüm, `rutbe=1`
  (YUKARI +3 m). Kod `1d1048e`. Bu oturumda uçan uçak bu.
- İkisinde de: `d0=4.0 hard=2.5 katman=3.0 v=1.2 a=2.0 kp=2.0` ·
  yatay SON ÇARE · `crc_fail=0` · test kancaları temiz ·
  `/control/setpoint` tek yayıncı · `/ws/gozlem` YOK · RTK fix=6
- Eski ayar dosyası: `~/yelpence_ws/ucus_ayarlari.env.23agu_oncesi`
- **ylp01:** yerde. Dönünce `RPI_ESITLEME` A13-A17 + K1-K16 **ve
  `SURU_KADRO="1 2 3"`**.
- 🔴 **Laptop:** QGC'de 14550 link'i bağlı kalmalı.

---

## 2026-08-23 20:30 — Osman + Claude (DİKEY çarpışma önleme: yazıldı, dağıtıldı, 5 yer testi)

> Gün tamamen çarpışma önlemeye ayrıldı. Kaçınmanın birincil kaçış yönü
> **dikey** oldu; yatay itme son çareye indi. Yol boyunca **üç sessiz hata**
> ve **beş tasarım kusuru** çıktı — hepsi ölçümle bulundu.

**Ne yapıldı**

*1 — Mesh "%30 kayıp" efsanesi çürüdü: kaynağı radyo değil KENDİ KAPIMIZ*

Operatör "%28 kayıp saçma, dün o sorunu çözmüştük" dedi ve haklı çıktı.
Ölçüldü: kaynak (agent_fsm iç durum) tam **10,00 Hz**, ama POSE kapısı da
10 Hz — jitter yüzünden boşlukların **%51,4'ü eşiğin altında** kalıyor ve o
örnekler tamamen düşüyor.

```
                    ONCE              SONRA (_pose_periyot_s 0.100 -> 0.095)
Pi->ESP yazilan   8,08 / 8,44 /s      11,91 / 11,94 /s
karsi taraf alan  7,09 / 7,11 Hz      10,89 / 10,46 Hz
en buyuk bosluk   0,41 s              0,31 s
gercek HAVA kaybi                     %1-5   (radyo neredeyse kusursuz)
```

Dağıtıldı ve uçakta doğrulandı. `gonderim_drop=0`, `crc_fail=0`.

*2 — Dikey yol verme yazıldı (KARAR-06)*

Kural: çatışan uçaklardan **kimliği büyük olan**, küçüğün **ölçülen**
irtifasından `katman` kadar uzağa gider. Rütbe **kadrodan** (`SURU_KADRO`),
merdiven **dönüşümlü** (+k, −k, +2k…). Yatay itme yalnız `hard` içinde.

**Testler beş tasarım kusuru yakaladı** — hepsi düzeltildi, gerekçeleri koda
yazıldı:
- çapa görev tırmanışını kesiyordu (QR "20 m'ye çık" merdiveni dondururdu)
- saf dikey kip görev **yatay** hızını sessizce frenliyordu (2,0 → 0,2 m/s)
- yön kararı manevranın ortasında dönüyordu (ivme rampası yüzünden)
- 🔴 drone2 ile drone3 **tam aynı irtifaya** çıkıyordu (yarış durumu)
- dikey müdahale görevin dikey komutunu tamamen eziyordu

*3 — İki sessiz hata daha (ikisi de uykudaydı)*

- 🔴 **Dikey datum:** kendi `pos_z`'m EKF yerel (boot'a bağlı ~10 m kayar),
  komşununki mesh'ten gelen kalkış-göreli. İkisi çıkarılıyordu. Dikey kaçış
  için bu **doğrudan kumanda sinyali** — düzeltildi (`TUZAKLAR` §2.21).
  Aynı sebeple **irtifa kapısı** da sağlam kaynağa alındı.
- 🔴 **PX4 sessiz kırpma:** `MPC_Z_VEL_MAX_UP = 1,2` çıktı. Kaçınmaya 3,0
  yazılsaydı ayar ve log 3,0 gösterirken uçak 1,2 tırmanacaktı. Dört PX4
  dikey tavanı `ucus_ayarlari.py`'ye girdi + **denetim** eklendi.

*4 — Dağıtım ve BEŞ YER TESTİ (hepsi geçti)*

| test | sonuç |
|---|---|
| G0-1 datum | `rel_z` iki uçaktan zıt işaretli, 3 cm farkla (−0,428 / +0,397) |
| G0-2 rütbe+işaret | çapa 0,000 · rütbe 1 → −1,184 (PX4 tavanında doyuyor) |
| G0-3 yatay son çare | 0,6 m arayla açıldı, **zıt yönlerde** (+3,74 / −3,65) |
| G0-4 geçirgenlik | çatışma yokken çıktı girdiyle **birebir** |
| G0-5 körlükte tutma | `donus_kor=1`, ayrım bırakılmadı |

**Ne değişti**

- kod: `ca_core.py` — dikey yol verme, `xy_guard` kör noktası, yatay son
  çare kapısı, `slew_emergency` 30 → 5,66
- kod: `komsu_adaptoru.py` — dikey datum düzeltmesi + `agent_id`
- kod: `collision_avoidance_node.py` — parametreler, irtifa kapısı, tanılar
- kod: `esp32_bridge_node.py` — POSE kapısı 0,100 → 0,095
- kod: `ucus_ayarlari.py` — CA eşikleri + PX4 dikey tavanları + denetimler
- kod: `baslat.sh` — dikey parametreler, `SURU_KADRO`'dan rütbe
- kod: `ca_benzetim.py` — gerçek `ca_core` dikeyi + ölçülen mesh modeli
- yeni: `test_ca_dikey.py` (26 test) · `teshis/g0_dikey_datum.py` ·
  `teshis/g0_dikey_gozlem.sh` · `teshis/g0_korluk_tutma.sh`
- **uçakta:** kod dağıtıldı (`9e8ee4f +KIRLI`), `ucus_ayarlari.env` yeniden
  üretildi (**K2 kapandı**: `d0` 10→4,0, `hard` 6→2,5), konteynerler restart
- belge: `CA.md` yeniden yazıldı · `TUZAKLAR` §1.23 §1.24 §2.20 §2.21 §2.22
  §3.12 · `KARARLAR` KARAR-06 + KARAR-01 düzeltmesi + KARAR-04'e `SURU_KADRO`
  · `RPI_ESITLEME` K13-K16 + A17 · `DURUM` · `YAPILACAKLAR` · `PLAN` ·
  `CLAUDE.md`

**Yarım kalan / tuzak**

- 🔴 **Havada hiç uçmadı.** İlk uçuş operatörün tarif ettiği iki uçaklı test.
- 🔴 **Tırmanma itki payı ölçülmedi** — o uçuşta kayıttan çıkarılacak
  (`vfr_hud.throttle` tepesi). Askı gazı %66, `a=2.0` ~1,20× itki istiyor.
- 🔴 **`KARAR-02`: `ultracode`** — yeni CA'nın ilk uçuşu.
- 🟠 Yanal kayma **~4,8 m** bekleniyor; haritaya işlenmeli.
- 🟠 Kumanda hangi uçağa bağlı hâlâ netleşmedi; ylp02'yi de yakalarsa test
  boş çıkar.
- ⚠️ **İki belge bayattı, düzeltildi:** `/ws/gozlem` "VAR" yazıyordu — **YOK**.
  `basit_kacinma` koşuyor yazıyordu — 21 Ağustos'ta kapanmış.
- ⚠️ Üç uçağın **aynı noktadan geçtiği** çapraz slot değişiminde hiçbir ayar
  kabul eşiğini tutturmuyor (1,76 m). `formation_node` o geometriyi
  üretmemeli.
- ⚠️ Test betikleri artık düğüm bıraktı (`kill` sarmalayıcıyı öldürüp çocuğu
  öksüz bırakıyor) — temizlendi, tek yayıncı doğrulandı, `TUZAKLAR` §1.24.

**Sıradaki adım**

Operatörün iki uçaklı dikey kaçınma testi — `PLAN.md` "SIRADAKİ UÇUŞ" ve
`YAPILACAKLAR` "SONRAKİ OPERATÖRE" bloğunda tam tarifi var.

**Uçakların bırakıldığı hâl**

- **ylp00:** yerde, disarm, pervaneler **TAKILI**, 11 düğüm.
  `rutbe=0` (**ÇAPA** — dikeyde kıpırdamaz).
- **ylp02:** yerde, disarm, pervaneler **TAKILI**, 11 düğüm.
  `rutbe=1` (**YUKARI +3 m** — testte asılı duracak olan bu).
- İkisinde de: `d0=4.0 hard=2.5 katman=3.0 v=1.2 a=2.0 kp=2.0` ·
  yatay **SON ÇARE** · `crc_fail=0` · test kancaları **temiz** ·
  `/control/setpoint` **tek yayıncı** · `/ws/gozlem` **YOK**
- Eski ayar dosyası: `~/yelpence_ws/ucus_ayarlari.env.23agu_oncesi`
- **ylp01:** yerde. Dönünce `RPI_ESITLEME` A13-A17 + K1-K16, **ve
  `SURU_KADRO="1 2 3"`** (yoksa kaçış yönü ters döner).
- 🔴 **Laptop:** QGC'de 14550 link'i bağlı kalmalı.

---

## 2026-08-23 01:30 — Osman + Claude (P0.15'in KÖK NEDENİ bulundu ve doğrulandı)

> Uzun bir oturum. Üç ayrı iş yapıldı: laptopun ağ sorunu çözüldü, ylp00'a
> bekleyen restart atıldı, ve **21 Ağustos'tan beri açık olan mesh körlüğünün
> kök nedeni bulunup iki uçuşla doğrulandı.**

**Ne yapıldı**

*1 — "RPi'ler bağlanınca laptopun interneti çöküyor" ÇÖZÜLDÜ*

- Kök neden ölçüldü: **QGC'de 14550'yi dinleyen link YOKTU.**
  `~/.config/QGroundControl/QGroundControl.ini` içinde `[LinkConfigurations]`
  bölümü hiç yok, `autoConnectUDP=false`. Yani QGC **açıkken bile** kimse
  14550'yi tutmuyordu → MAVROS `udp-b` ile **süresiz** yayın yapıyordu.
- *"Dronlara güç vermeden önce QGC'yi aç"* kuralı bu yüzden Osman'ın
  makinesinde hiç çalışmamış — kuralın gizli ön koşulu belgede yazmıyordu.
- Ölçüldü: **soğuk açılışta 60 sn çöküş, ağ geçidine ping tepe 14,5 sn**
  (17 Ağustos'un imzasının birebir tekrarı). QGC link'i eklenince bitti.
- İkinci ölçüm: **QGC bağlıyken `docker restart` maliyeti 333 ms**, çöküş yok.
  Yani pencere **oturum başına bir kez**, restart başına değil.
- Operatör kararıyla uçak tarafı değiştirilmedi (P1.7 kaldırıldı).

*2 — ylp00'a bekleyen restart atıldı*

`docker restart drone1` → **K10-K12 etkin**, açılışta
`ivme normal=3.58 acil=5.66 donus=0.50`. İki uçak artık aynı ivme sınırlarında.

*3 — 🎯 P0.15'in KÖK NEDENİ: ESP↔Pi UART'ının ESP ucundaki JUMPER konnektörü*

Akşam boyunca **on hipotez elendi**, hepsi ölçümle: anten yönelimi · LiPo
pilin araya girmesi · mesafe (3,7/6/16 m) · ESC rölanti · FlySky vericisi ·
besleme gerilimi · ısınma · irtifa farkı · CPU yükü · `collision_avoidance`.

Belirleyici ölçüm:

```
ylp00 : 19.007 paket -> crc_fail = 868   (hepsi UCUS sirasinda)
ylp02 : 19.505 paket -> crc_fail =   0   (ayni ucus, ayni kod)
yerde : ~19.000      -> crc_fail =   0   (her iki ucakta)
```

Firmware okundu: mesh'te **iki bağımsız CRC katmanı** var (ESP-NOW donanım
FCS + mesh CRC16, ve UART CRC16) ve ikisini de ESP doğruluyor. Dolayısıyla
Pi'de sayılan `crc_fail` **yalnızca o uçağın kendi ESP→Pi UART hattından**
gelebilir — bu çıkarım şüpheliyi tek kabloya indirdi.

Yerde **hiçbir test üretmedi** (kablo bükme, pervanesiz motor, pervaneli
kalkış-eşiği-altı gaz, gövde/kol bükme). Arıza yalnız uçuş titreşiminde
çıkıyor. Konnektöre elle dokunulunca **171 hata + iki tel çıktı** — orada
bulundu.

**Doğrulama (iki uçuş):** konnektör oturtuldu →
tek uçaklı 10 m askı **crc_fail 0** · iki uçaklı 10 m askı **crc_fail 0**
(ylp02 de 0). `alim_ok` hiç düşmedi; önce 13,5 → 7,6 düşüyordu.

*Yan bulgular*

- **Körlük alarmı YKİ'ye ULAŞMIYOR.** 24 sn benzetim + ylp02 fiilen 114 sn
  kapalı → bayrak hiç kurulmadı, baz logu boş, YKİ 0 uyarı. Elenenler: kod
  uçakta var · `build` taze · eşik 5,0 · kanca doğru yerde · baz kodu var ·
  md5 birebir · havada olma şartı yok · uçağa özgü değil. **Sebep bulunamadı.**
- Havada link **yerdekinden iyi** (16 m'de 5,5 → 7,2 paket/s) — yer yansıması.
- Üç olayda da **aynı yön** öldü: ylp02 → ylp00.
- `swarm_fsm`'in acil iniş dalı gerçek körlükte **ateşlemedi**
  (`active_agent_count` 2→1→2) — 15 Ağustos'taki `agent_id` düzeltmesi tutuyor.

**Ne değişti**

- kod: `gorev_kanit_ucus.py` — **yeni `--senaryo irtifa`** (üç eşit bacak:
  10 m → biri 5 m → 10 m, sonuncusu **sürüklenme kontrolü**) + `--alcak`
- kod: `gorev_kanit_ucus.py` — **`asili` N uçağa genelleştirildi**
  (her uçak kendi yerinin üstünde; tek uçaklı kullanım bozulmadı)
- uçakta: **ylp00 ESP↔Pi jumper'ı elle oturtuldu** (geçici) · K10-K12 etkin
- laptop: QGC'ye 14550 dinleyen UDP link eklendi
- belge: `TUZAKLAR` §2.19 / §1.21 / §1.22 · `YAPILACAKLAR` P0.15 kapandı,
  P1.18 / P2.12 / P2.13 açıldı · `RPI_ESITLEME` A16

**Yarım kalan / tuzak**

- 🔴 **Jumper düzeltmesi GEÇİCİ.** Kilit ve gerilim boşaltma yok, yeniden
  gevşer. Kalıcı yol lehim ya da JST-GH. **ylp02 ve ylp01'in aynı konnektörü
  kontrol edilmedi** — ylp02'nin 0 hatası "sağlam" değil "henüz gevşememiş".
- 🔴 **Körlük alarmı YKİ'ye ulaşmıyor** — kopma olursa havada haberin olmaz,
  yalnız kayıttan görülür.
- 🟡 **Agresif düzeltme** araştırıldı, ölçülmedi. Çift konum döngüsü **elendi**
  (`guided_konum_kp` PX4'ün terimini geri çıkarıyor). Kalan üç aday:
  ① varışta hız tek tikte sıfırlanıyor → ivme komutu tavana kırpılmış
  **basamak** olarak gidiyor (en güçlü aday) ② `guided_tasma_m=3.0`
  ③ askıda gecikme telafisi `if vx or vy` ile **kapalı**, PX4'ün tam 0,95'i
  çalışıyor. Ölçüm bu geceki kayıtlardan yapılabilir, uçuş gerekmez.
- ⚠️ **Operatörün eklediği kural belgede yok:** arm'dan sonra 5 sn içinde
  kalkış olmazsa **otomatik disarm**. Yer testlerini bu süreye göre kurmak
  gerekiyor (parametre adı doğrulanmadı).
- ⚠️ `d0=10 hard=6` **hâlâ geçici** — formasyon uçuşundan önce geri alınacak.
- ⚠️ Aktif kayıt `metadata.yaml` taşımadığı için `ros2 bag` açamıyor; kopyala
  + `reindex` yolu kullanıldı (canlı kayda dokunmadan).

**Sıradaki adım**

Jumper'ın kalıcı çözümü (lehim/JST-GH) ve ylp02 + ylp01'in aynı
konnektörünün kontrolü. Ardından `PLAN.md`'de bekleyen kaçınma eğim testi.

**Uçakların bırakıldığı hâl**

- **ylp00:** yerde, disarm, pervaneler **TAKILI**, 11 düğüm.
  ESP↔Pi jumper'ı **elle oturtulmuş (geçici)**. `crc_fail = 0`.
  K10-K12 etkin (`ivme normal=3.58 acil=5.66 donus=0.50`).
- **ylp02:** yerde, disarm, pervaneler **TAKILI**. `crc_fail = 0`.
  Jumper'ı **kontrol edilmedi**.
- **ylp01:** yerde (2 Ağustos'tan beri). Dönünce `RPI_ESITLEME` A13-A16 + K1-K12.
- Uçaklardaki kalıcı ayarlar: `d0=10 hard=6` **(GEÇİCİ)** · `korluk_tut_s=0` ·
  `kernel.panic=10` · ramoops · izleme 10 sn · `/ws/gozlem` var ·
  `/ws/suru_dugumleri = origin consensus fsm formasyon ca`
- 🔴 **Laptop:** QGC'de 14550 link'i **bağlı kalmalı** — koparsa uçak
  açılışında ağ yine 60 sn çöker. Kontrol: `ss -ulnp | grep 14550`

---

## 2026-08-22 07:10 — Eyüp + Claude

**Ne yapıldı**
- 🔴 **Kaçınma, uçağın YAPAMAYACAĞI ivme istiyormuş.** Operatör "devrilecek
  gibi sağ sol yaptı" dedi; ben konuma/hıza bakıp "sakin" demiştim.
  **Operatör eğim açılarına bakmamı söyledi ve haklı çıktı:**

  ```
  asili (once)  roll -5.0..+6.1    MAKS EGIM 11.6 deg
  KACIS         roll -24.7..+28.3  MAKS EGIM 34.0 deg   <<<
  DONUS                            MAKS EGIM 22.0 deg
  ```

  Kök neden: `ca_core` ivme sınırları `ucus_ayarlari.py`'ye **hiç
  bağlanmamış** — `slew_emergency = 30 m/s²` = **71,9° eğim**, imkânsız.
- 🔴 **Pilot devralma açığı kapatıldı.** Operatör kumandadan LAND dedi,
  uçak inip **geri tırmandı** — her seferinde. Ölçüldü: 120 goto'ya karşı
  124 `offboard` komutu, 3-5 Hz. Benim eklediğim bekleme-tekrarı deliği
  0,75 sn'den **sürekliye** çıkarmış.
- **Çökme kaydı kuruldu ve sahada sınandı** (`sysrq` paniği yakalandı,
  çağrı yığını okundu). İzleme 10 sn'ye çekildi.
- **Körlük alarmları doğrulandı:** 4 olayın dördü de gerçek — ylp02'nin
  kapalı olduğu anlarla birebir örtüşüyor, **sıfır yanlış alarm**.

**Ne değişti**
- kod: `ucus_ayarlari.py` — `KACINMA_IVME_ACIL/NORMAL/DONUS` türetildi
  (`a = g·tan(θ)`): **30 → 5,66 m/s²**
- kod: `ca_core.py` — `hard` sınırındaki basamak giderildi (sıçrama
  3,19 → 1,80 m/s), sönümleme tabanı (uzaklaşan komşuya çekim yok)
- kod: `collision_avoidance_node.py` — dönüş yumuşatma (4 sn pencerede
  `max_acc_mps2=0.5`)
- kod: `px4_bridge.py` — **pilot moddayken mod geri alınmaz** + setpoint
  hız/ivme tavanları bağlandı
- kod: `esp32_bridge_node.py` — körlük biti, baz olay üretimi, test kancası
- uçakta: `ivme normal=3.58 acil=5.66 donus=0.50` · `kernel.panic=10` ·
  ramoops · izleme 10 sn · `yelpence-cokme.service`
- belge: `TUZAKLAR` 2.15-2.18 · `YAPILACAKLAR` P0.15-P0.17, P1.15 ·
  `RPI_ESITLEME` A13-A15 + K1-K12 · `DURUM` · `KARARLAR`

**Yarım kalan / tuzak**
- 🔴 **ylp00'da K10-K12 ETKİN DEĞİL.** Kod dağıtıldı, konteyner yeniden
  başlatılmadı (MAVROS cevapsızdı, uçuş pili kapalı olabilir).
  **Uçuştan önce `docker restart drone1` ŞART** — yoksa eski `30 m/s²`
  ile uçar. Doğrulama: açılışta `ivme normal=3.58 acil=5.66 donus=0.50`.
- 🔴 **P0.17 açık:** ylp00'ın Pi'si bir kez öldü ve öyle kaldı. Uçuştan
  önce `uptime -s` bak; son 10 dk'da açılmışsa uçma.
- 🔴 **`d0=10 hard=6` GEÇİCİ** — formasyon öncesi geri alınacak
  (`RPI_ESITLEME` K2).
- 🟠 Üç düzeltme de **henüz uçmadı**: ivme tavanı, kapı sürekliliği,
  dönüş yumuşatma.
- 🟡 Kaçınmanın bilinen iki zayıflığı duruyor: asılı dururken **teğet
  bileşen sıfır**, **tepeden yaklaşmada koruma yok** (`xy_guard=0.3`).
- Kumanda ylp00'a bağlı görünüyor (`rc_link_ok: true`). ylp02'yi
  kaldırırken ylp00'ın modunun alınıp alınmadığı **netleşmedi** — yerde
  30 saniyelik çubuk testiyle kesinleşir.

**Sıradaki adım**
- ylp00'ı yeniden başlat, kuru test + harita, kaçınma testini tekrarla:
  **eğim genliği düştü mü** (34° → beklenen ~20°) ve dönüş yumuşadı mı.

**Ne yapıldı — devamı (oturum sonu)**
- **Sıradaki uçuş `PLAN.md`'ye yazıldı:** tek soru *"kaçınma artık uçağın
  yapabileceği sınırlar içinde mi"*, ölçüt **eğim genliği** (34° → ≤20°),
  ve kritik kabul ölçütü: **kaçışın gücü zayıflamamalı** (3,88 m).
- **P1.16 açıldı — YKİ uyarılarının kalıcı kaydı YOK.** Operatör "senin
  verdiklerin dışında da bildirim geldi" dedi, sayınca **~32** çıktı
  (11 körlük döngüsü + 21 DURUM bayatlığı); ben 4 sanıyordum çünkü yalnız
  ylp00'ın kendi logundan saymıştım. **Baz istasyonu ayrıca kendi
  olaylarını üretiyor.** `AlertManager` yalnız bellekte tutuyor —
  `alert_manager.py`'de sıfır dosya işlemi, `yki_backend.log`'da 4,6 MB'da
  sıfır uyarı izi.
- **`YAPILACAKLAR.md`'nin en üstüne "SONRAKİ OPERATÖRE" bloğu** — sıralı
  altı madde, ilk ikisi uçuş engeli.

**Uçakların bırakıldığı hâl**
- 🔴 **İKİSİNİN DE PİLİ SÖKÜLDÜ, kapalılar** (operatör, oturum sonu).
- ylp00: **yeni kaçınma parametreleri ETKİN DEĞİL** — kod dağıtıldı ama
  konteyner yeniden başlatılamadı (MAVROS cevapsızdı). Açılışta
  **`docker restart drone1` ŞART**, yoksa eski `30 m/s²` ile uçar.
  Doğrulama: `ivme normal=3.58 acil=5.66 donus=0.50`.
- ylp02: yeni parametreler **etkin ve doğrulandı**. Pil bu oturumda bir kez
  bitti ve değiştirildi.
- ylp01: yerde (2 Ağustos'tan beri). Dönünce `RPI_ESITLEME` A13-A15 + K1-K12
- Uçaklardaki kalıcı ayarlar (pil takılınca öyle bulunacak):
  `d0=10 hard=6` **(GEÇİCİ — formasyon öncesi geri al)** · `korluk_tut_s=0` ·
  `kernel.panic=10` · ramoops · izleme 10 sn · `/ws/gozlem` var ·
  `/ws/suru_dugumleri = origin consensus fsm formasyon ca`

---

## 2026-08-22 03:40 — Eyüp + Claude

**Ne yapıldı**
- 🎯 **ÇARPIŞMA ÖNLEME SAHADA ÇALIŞTI, ilk ölçülü kanıt.** Operatör ylp02'yi
  kumandayla 6,5 m'ye yaklaştırdı → ylp00 kendi noktasından **3,88 m kaçtı**,
  mesafe 2 saniyede 6,6 → 9,1 m açıldı. `avoid=375`, 20 kaçış satırı.
  Yatayda hiçbir komut almıyordu; hareket tamamen kaçınmanın eseri.
- **P0.16 çözüldü** — kaçınma körlüğü artık YKİ'ye ulaşıyor. Uçtan uca
  doğrulandı: mesh kesildi → 2 sn'de YKİ'de `sev=critical` + sesli alarm +
  masaüstü bildirimi. Kök neden: mesh'te `TIP_EVENT` **yok**, uçakta üretilen
  hiçbir `SystemEvent` YKİ'ye ulaşmıyordu.
- **P0.15 kapatıldı** — körlük artık birinci sınıf durum (alarm + isteğe bağlı
  yatay tutma). 21 Ağustos'ta 47 saniye sessiz kalan durum artık 2 saniyede
  haber veriyor.
- **Çökme kaydı kuruldu ve SAHADA SINANDI** (`sysrq` paniği): Pi 10 sn'de
  döndü, `dmesg-ramoops-0` (13,3 KB) kopyalandı ve **okundu** — çağrı yığını
  net. Artık yazılım ölümü ile güç kesilmesi ayırt edilebiliyor.
- İzleme aralığı 60 → **10 sn** (ylp00'ın ölümünde en yakın ölçüm 40 sn
  öncesineydi, arası kör kalmıştı).

**Ne değişti**
- kod: `collision_avoidance_node.py` — körlük taraması (`_korluk_tara`),
  `SystemEvent` yayını, `korluk_alarm_s=2.0`, `korluk_tut_s=0.0` (operatör
  kararı: durma, haber ver)
- kod: `ca_core.py:~123` — **sönümleme tabanı** `max(0.0, c)`. Öncesinde
  uzaklaşan komşuya **1,34 m/s çekim** üretiyordu (ölçüldü)
- kod: `px4_bridge.py:_yurutucu_ilerlet` — setpoint `max_speed_mps` /
  `max_acc_mps2` **bağlandı**. Dört düğüm dolduruyordu, hiçbiri okunmuyordu
- kod: `packet_parser.py` — `DURUM2_BAYRAK_KACINMA_KORU=0x04` (firmware
  değişmedi; DURUM paketini Pi kuruyor)
- kod: `esp32_bridge_node.py` — körlük biti + baz tarafı olay üretimi +
  `sahte_kayip_ajanlar` test kancası
- kod: `gorev_kanit_ucus.py` — **bekleme evresinde hedef tekrarlanıyor**
  (öncesinde `/raw` boş kalıyordu, kaçınma ATIL'dı)
- kod: `AlertList.tsx` — ses kilidi açma + masaüstü bildirimi
- uçakta: **`d0=10 hard=6`** (test değerleri, `ucus_ayarlari.env` sonuna elle
  eklendi) · `korluk_tut_s=0` · `kernel.panic=10` · ramoops · izleme 10 sn ·
  `yelpence-cokme.service`
- belge: `TUZAKLAR` 2.15/2.16/2.17 · `YAPILACAKLAR` P0.15/P0.16/P0.17/P1.15 ·
  `RPI_ESITLEME` A13-A15 + K1-K8 · `KARARLAR` (CA algoritma incelemesi) ·
  `DURUM` (körlük alarmı bölümü)

**Yarım kalan / tuzak**
- 🔴 **P0.17 açık:** ylp00'ın Pi'si uçuştan sonra **öldü ve öyle kaldı**
  (kırmızı ışık, elle açıldı). Sebep bilinmiyor; bilinen adayların hepsi
  elendi. **Uçuş öncesi `uptime -s` bak** — Pi son 10 dk'da açılmışsa uçma.
- 🔴 **`d0=10 hard=6` GEÇİCİ.** Formasyon uçuşundan önce geri alınmalı:
  12 m aralıkta planlı en yakın yaklaşma 8,49 m, `d0=10` normal geçişte
  tetiklenir. Geri alma komutu `RPI_ESITLEME` K2'de.
- 🟠 **Sönümleme tabanı ve setpoint tavanları HENÜZ UÇMADI.** Sonraki uçuşta
  iki soru: kaçış eskisi kadar güçlü mü, sert dönüş yumuşadı mı.
- Kaçınma algoritmasında bilinen üç zayıflık (`KARARLAR`, CA incelemesi):
  asılı dururken **teğet bileşen sıfır**, **tepeden yaklaşmada koruma yok**
  (`xy_guard=0.3`), yavaş yaklaşmada koruma `d0`'da değil `hard`'da başlıyor.
- Uçakta üretilen diğer `SystemEvent`'ler (FSM, consensus lider değişimi)
  **hâlâ YKİ'ye ulaşmıyor** — mesh'te `TIP_EVENT` yok (P1.15, 👤 Eyüp).

**Sıradaki adım**
- Kaçınma testini tekrarla (sönümleme tabanı + setpoint tavanları uçmadı);
  sonra **P0.15**'in kalan maddesi ve **P0.17** kök neden.

**Uçakların bırakıldığı hâl**
- ylp00: yerde, disarm, 11 düğüm, `collision_avoidance` (`d0=10 hard=6`),
  `korluk_tut_s=0`, ramoops+panic=10 aktif, izleme 10 sn, gerilim 5,19 V
- ylp02: aynı ayarlar, yerde, disarm, gerilim 5,16 V
- ylp01: yerde (2 Ağustos'tan beri). Dönünce: `RPI_ESITLEME` A13-A15 + K1-K8

---

## 2026-08-21 15:00 — Eyüp + Claude (İKİ UÇUŞ: P0.12 kapandı, sürü kalbi havada ölçüldü)

> Günün ilk uçuşları. İkisi de yerde hazırlanıp haritayla onaylandı,
> ikisi de sorunsuz indi. **Sürü yazılımı ilk kez havada aktif çalıştı.**

**Ne yapıldı**

*Sabah hazırlığı — titreşim ölçümü (uçuş yok)*

Operatör STABILIZED'da arm edip gazı kalkış eşiğinin altında tuttu.
**223 örnek, konum sıçraması 0.000 m — SAĞLAM.** 1 Ağustos'ta ylp00'ı
deviren hastalık (motorlar dönerken kestirimin sıçraması) yok. OFFBOARD
kalkış bu uçakta güvenli.

*🔴 Kuru test iki kez uçuşu durdurdu — ikisi de gerçek*

1. ylp02 bacak koridoruna **4,9 m** idi (kaçınmanın itme bölgesi içi).
   `basit_kacinma` komşunun **yalnız konumuna** bakıyor; disarm, motorsuz,
   yerde bile **engel sayılıyor** (kodda armed/state kontrolü YOK).
2. Titreşim testindeki zıplama uçağı **~100° döndürdü** (244° → 344°) ve
   yeni bacak ucu ylp02'ye **1,2 m** kaldı. Taze kuru test yakaladı.

Ders: **her fiziksel dokunuştan sonra kuru test + harita yeniden.**

*UÇUŞ 1 — P0.12(b) iptal doğrulaması (ylp00, tek bacak)*

İlk deneme **tetikleme hatasıyla** boşa gitti: görev çıktısı dosyaya
yönlendirilince python **blok tamponluyor**, "bacak başladı" satırı geç
düştü, iptal ölü sürece gitti. Uçak B planını uygulayıp temiz indi.
(Ders: dosyadan an yakalayacaksan `python3 -u`.)

İkinci deneme **GEÇTİ** — üç kanıt birden:

```
KOPRU  : iptal komutu: drone1 icin bekleyen 1 kayit / 3 gonderilmemis
         kopya (GOTO/ARM/TAKEOFF) dusuruldu
UCAK   : 818.601 goto -> 818.603 land -> sonra SIFIR goto
DAVRANIS: AUTO.LAND kesintisiz, t+24 sn yerde ve disarm, geri tirmanma YOK
```

İlk goto kopyası iptalden **2 ms önce** varmıştı — düşürülen 3 kopya
gitseydi hata kesin tetiklenirdi. **P0.12 tamamen kapandı.**

*UÇUŞ 2 — sürü kalbi havada (iki uçak, 10 m, g2)*

Uçuş öncesi KARAR-02 denetimi yapıldı (çok ajanlı koşu oturum limitinde
öldü; tek kanalda tamamlandı). **Git kararı ölçüme dayandı:**
`setpoint/raw`'ın tek yayıncısı `esp32_bridge`, `formation_control`
`/gozlem`'e gidiyor, `form_yayinla.sh` koşmuyor → sürünün aktüatöre
**kablosu yok**. FSM'in gönderebildiği tüm komutlar sayıldı (`arm`
armlıyken yok sayılıyor, `offboard` no-op, `takeoff` iki kilitle kapalı).

Havada görev olayı gönderildi, **seçim havada oldu**, ikisi de `lider=1`'de
anlaştı, `Split-brain` **sıfır**, uçuş boyunca **sahte seçim yok**.

| | bench | **UÇUŞTA** | eşik | pay | aşan |
|---|---|---|---|---|---|
| HB boşluğu | maks 301 ms | **maks 218 ms** | 1000 ms | 4,6× | **0** |
| DURUM boşluğu | — | **maks 408 ms** | 5000 ms | 12,3× | **0** |

595 HB / 59,7 sn · 858 DURUM / 119,8 sn. **Uçuştaki boşluklar bench'ten
daha iyi** — motor ve mesafe eşiği zorlamadı. İki eşik de kalıyor.

Bonus: inişte ylp00 uygunluğunu yitirince `Lider: 1 -> 3` yazdı — P0.12(a)
liderlik bırakma **hava→yer geçişinde canlı** doğrulandı.

**Ne değişti**

- belge: `YAPILACAKLAR` — P0.12 tamamen kapandı, P0.14 eşikleri uçuşta
  ölçüldü, **P1.14 eklendi** (tek yönlü kopmada kalıcı iki lider)
- uçakta: kod/ayar değişmedi; iki uçuş yapıldı, ikisi de temiz indi
- `/tmp/yelpence_rota.html` son hâli: g2, 10 m

**Yarım kalan / tuzak**

- 🟠 **P1.14** — lider kimliği mesh'e **kalp atışıyla** taşındı (80 ms),
  seçim çerçevesiyle değil (`election/result` kaydında **0 mesaj**).
  `_on_heartbeat` split-brain'i yalnız tek yönde çözüyor → asimetrik
  kopmada iki lider kalıcı olabilir. Bugün zararsız (kablo yok).
- 🟠 P1.13 pil sahtesi duruyor (KARAR-03 kapsamında)
- Uçuş öncesi denetim **tek kanalda** yapıldı; çok ajanlı tarama hiç
  tamamlanmadı — istenirse tekrarlanabilir
- Mod etiketi iki uçakta OFFBOARD kalıntısı (disarm hâlde zararsız)

**Sıradaki adım**

Operatör seçer: P1.14 düzeltmesi · P1.13 sahtesinin kaldırılması ·
`PLAN.md` §8 ADIM 3 (formation_node'un gözlemden çıkarılması) yolunda
bir sonraki kademe.

**Uçakların bırakıldığı hâl**

- ylp00: 11 düğüm, `armed=false`, pervaneler **TAKILI**, disk %43.
  Kod `db828ab`. İki uçuş yaptı, sağlıklı indi.
- ylp02: 11 düğüm, `armed=false`, pervaneler **TAKILI**. Bir uçuş yaptı.
- **Operatör oturum sonunda pilleri değiştiriyor** — güç kesilecek, yani
  o anki kayıt metadata'sız kalacak. **Açılışta `kayit_onar.sh`
  kendiliğinden onaracak**, elle bir şey gerekmiyor (TUZAKLAR 1.19).
- ylp01: yerde; dönünce `RPI_ESITLEME.md` bölüm 2 listesi.

---

## 2026-08-21 01:45 — Eyüp + Claude (P0.14 yer testi GEÇTİ: lider kaybı 1.063 sn'de devralındı)

> Uçuş yok. Tek iş: P0.14 lider kaybı yer testi — dört koşu sürdü, her koşu
> gerçek bir tuzak çıkardı, dördü de ölçülüp kapatıldı. Ağ koşulu: drone'lar
> telefona uzak, arada duvar (ylp00 ping ort. 41 ms / tepe 213 ms) — ölçüm
> bu yüzden bilerek uçağın KENDİ saatine taşındı, SSH gecikmesi sonuca
> giremedi.

**Ne yapıldı**

*Asıl sonuç (koşu 4, 00:59):* iki uçak görev olayıyla **gerçekten** arm
oldu (FSM: IDLE→ARMING→ARMED), `Lider: 3 -> 1` seçildi, liderin
consensus'u `kill -9` ile öldürüldü → takipçi **1.063 sn** sonra kendini
seçti (`Lider: 1 -> 3`, sebep=LEADER_FAULT), ilk kalp atışı **+6 ms**.
Bonus: inişle uygunluğunu yitiren yeni lider liderliği **BIRAKTI** (P0.12
canlı kanıt), incarnation sıfırlama doğru işledi. Mesh HB boşlukları
(61 atış, bench): ortanca 101 / p90 104 / **maks 301 ms** → 1000 ms eşik
görülen en büyük boşluğun 3.3 katı. Eskiden bu yol HİÇ çalışmıyordu.

*Koşuların çıkardığı tuzaklar (hepsi ölçüldü):*

1. **Pil sahtesi** — koşu 2'de sıfır seçim/sıfır hata. PX4 pili bildirmiyor
   (`/mavros/battery` 65.535 V = "geçersiz"; **operatör bilerek kapatmış**,
   bkz. KARAR-03) ama `px4_bridge.py:546` bunu görünce **12.6 V / %100
   uyduruyor**; consensus varsayılan `battery_min_v=14.0` ile açılınca
   sahte 12.6 herkesi aday dışı bıraktı. → TUZAKLAR 1.20, P1.13,
   KARAR-03 adım 2'ye eklendi. Üç teşhis betiği artık `baslat.sh:748` ile
   birebir parametre kullanıyor.
2. **FSM UNKNOWN** — koşu 3 boş geçti: konteyner açılışından ~4 dk sonra
   bile ylp00 `agent_fsm`'i state=0'daydı; görev olayı UNKNOWN'da sessizce
   boşa gidiyor. → hazırlık kapısı + TUZAKLAR 2.13.
3. **OFFBOARD'da disarm reddi** — koşu 2'de `Disarming denied: not landed`;
   operatör kill switch'le durdurdu, QGC "flight termination active" dedi.
   Switch kapatılınca temizlendi — **FMU reboot GEREKMEDİ** (Pi'ler hiç
   yeniden başlamadı, ölçüldü). Bitiş artık önce `land`: iki uçak da
   `Disarmed by landing` ile kendi kendine temiz kapandı.
4. **mavros'tan arm FSM'i kımıldatmıyor** — koşu 1 bunun kanıtı: PX4 arm
   oldu, `agent_fsm` IDLE'da kaldı, IDLE aday değil. ARMED'a tek yol görev
   olayı (`agent_fsm_node.py:345`).

*Ayrıca:* mesh'in ARMED'ı karşıda TAKEOFF(4) göstermesi yarım saat "hata"
diye kovalandı — **TUZAKLAR 4.9'da zaten yazılıymış**; ölçüm notu eklendi.
Önce TUZAKLAR'a bakma dersi bir kez daha.

**Ne değişti**

- kod: `teshis/lider_kaybi_test.sh` + `teshis/lider_kaybi_izle.py` **yeni**
  (tek saatte ölçüm; hazırlık kapısı; land-önce-disarm; kendi kendini
  temizleyen consensus geri getirme)
- kod: `teshis/arm_secim.sh`, `teshis/consensus_baslat.sh` — consensus artık
  `agent_count:=3 battery_min_v:=0.0` ile (sahte-12.6 tuzağı)
- kod: `dagit.sh` — teşhisten artık `*.py` de taşınıyor (izle.py yalnız
  elle konmuştu; ylp01'de test sessizce kırılırdı)
- uçakta: konteynerler birkaç kez yeniden başlatıldı; son hal temiz
- belge: TUZAKLAR 1.20 + 2.13 + 4.9 notu · YAPILACAKLAR P0.14 kapandı,
  eşik maddesi yarı-ölçüldü, P1.13 eklendi · KARAR-03 adım 2 güncellendi

**Yarım kalan / tuzak**

- 🟠 P1.13: sahte 12.6 duruyor (kaldırma = uçuş yolu kodu, ayrı yer testi)
- 🟡 DURUM bayatlık eşiği (5 sn) hâlâ ölçülmedi; HB eşiği yalnız bench'te
  ölçüldü — uçuşta/mesafede tekrar
- 🟡 P0.12(b) uçuş doğrulaması G2'ye kalmış durumda
- Mod etiketi iki uçakta OFFBOARD kalıntısı — disarm hâlde zararsız,
  kumandadan mod değişince ya da sonraki açılışta gider

**Sıradaki adım**

P1.13 sahtesinin kaldırılması ya da YAPILACAKLAR'daki sıradaki P0 —
operatör seçer. Pil izlemenin bütünü modül alınınca KARAR-03'ün altı adımı.

**Uçakların bırakıldığı hâl**

- ylp00: konteyner taze (~01:30), **11 düğüm**, `armed=false`, pervaneler
  **ÇIKIK**, kill switch kapalı. Kod `db828ab`.
- ylp02: aynı — 11 düğüm, disarm, pervanesiz, kill switch kapalı. Kod
  `db828ab`. (docker log döndürmesi hâlâ yalnız ylp00'da — P2.11.)
- ylp01: yerde; dönünce `RPI_ESITLEME.md` bölüm 2 listesi.

---

## 2026-08-20 23:40 — Eyüp + Claude (üç P0 kapandı; **bütün uçuş kayıtları okunamıyormuş**, kurtarıldı)

> Uçuş yok, hepsi yerde. Uçaklar pervanesiz, arm testleri yapıldı.
> Oturumun yarısı planlanmış işti (P0.12 → P0.14 → P0.13), yarısı bir
> `docker logs` arızasını kovalarken çıkan **çok daha büyük bir bulguydu.**

**Ne yapıldı**

*P0.12 — hayalet lider ve inişi iptal eden bayat GOTO*

- **Ölçüldü:** 12 saniyelik sahte durum enjeksiyonundan **2,8 dakika sonra**
  hâlâ 10,0 Hz `LeaderHeartbeat` geliyordu, `state=1 armed=false` iken.
  Lider hiç bırakmıyordu. `consensus_node`'a `_liderligi_birak()` + histerezis
  eklendi.
- **İki uçakla doğrulandı** (tek uçak bunu yapısal olarak sınayamaz):
  ikisinde de `Lider: 1 -> 3`, **ylp00'da `BIRAKILDI` YOK** — yani yeni dal
  devir yolunun dışında kalıyor. Kimse uygun değilken `liderlik BIRAKILDI`.
- İkinci yarısı: `land` sonrası kuyrukta bekleyen `takeoff` uçağı tekrar
  kaldırıyordu. **Ölçüldü:** `land` 784.475'te, `takeoff` 784.779 ve
  785.182'de. Düzeltmeden sonra `land` sonrası **sıfır** takeoff.

*P0.14 — lider kaybı tespiti ölüydü*

İki ölü kapı vardı; ikisi de yalnız lider **hâlâ yayın yaparken** çalışıyordu,
yani gerçek kayıpta hiç tetiklenmiyordu. Eşikler aritmetikle seçildi (mesh
~%30 paket kaybı): kalp atışı 300 → **1000 ms** (0,3³ = %2,7 yanlış alarm →
0,3¹⁰ ≈ 6e-6), komşu DURUM bayatlığı **5 sn** (%0,24).

*P0.13 — açılışta iki sessiz takılma*

- mavros'tan önce ağ bekleniyor (en fazla 30 sn, **gelmezse devam**).
- `gps_saat.py` artık `timeout -s INT -k 15 200` ile sarılı. **`-k 15` şart:**
  `-s INT` tek başına denendi ve tam da önlemeye çalıştığı şekilde takıldı —
  süreç SIGINT'i yutunca boru `tee`'ye açık kalıyor ve `baslat.sh` yine
  bloke oluyor. Üç vakayla doğrulandı.

*🔴 Asıl bulgu — BÜTÜN uçuş kayıtları `ros2 bag` ile açılamıyormuş*

`docker logs`'un çökmesini kovalarken çıktı. Kök neden **pil değişimi**:
güç kesilince rosbag2 `metadata.yaml`'ı yazamıyor.

**Ölçüldü: ylp00'da 60/60, ylp02'da 50/50 kayıtta metadata YOK.** Yani
15 Ağustos'tan beri hiçbir uçuş kaydı standart yoldan okunamıyordu ve
**hiçbir hata vermiyordu.**

Veri kayıp değildi, sarmalayıcı eksikti. `deploy/rpi/teshis/kayit_onar.sh`
yazıldı: bozuk parçayı reindex'in **hata metninden** buluyor (boyuta bakarak
elenemiyor — bozuk parça 0 bayt da olabiliyor, 831488 bayt "dolu" da),
`mcap recover` ile içindekini kurtarıyor, sonra reindex ediyor.

**Sonuç: ylp00 59/60, ylp02 49/50 okunur.** Kalanlar: o an kayıtta olan ve
16 Ağustos'ta hiç parça yazamamış boş dizin.

*Düşüşte kayıp penceresi ~30 sn → ~4 sn*

`RPI_ESITLEME` tablosu A8 sysctl'i için "ylp00 ✅" diyordu — **ölçtük, yoktu.**
`dirty_expire_centisecs` 3000 (30 sn) idi. Operatör uyguladı, ikisi de 100.
Üstüne `mcap recover` bozuk son parçadan **10588 mesaj / 25,8 saniye**
kurtarıyor. Böylece `--max-bag-duration`'a hiç dokunmadan pencere daraldı.

**Ne değişti**

- kod: `consensus_node.py`, `election.py` — P0.12(a) + P0.14(a)
- kod: `esp32_bridge_node.py` — P0.12(b), bayat kalkış, P0.14(b)
- kod: `deploy/rpi/baslat.sh` — ağ beklemesi, `gps_saat` sert zaman aşımı,
  **sonuna arka planda kayıt onarımı** (üç korumalı: `&`, `timeout 600`,
  aktif+taze dizin atlanır)
- kod: `deploy/rpi/teshis/kayit_onar.sh` **yeni**
- kod: `deploy/rpi/run_drone.sh` — docker log döndürme (`10m × 3`)
- uçakta: **A8 sysctl** ylp00'a eklendi (writeback 30 sn → 1 sn)
- uçakta: **`~/yelpence_ws/bin/mcap`** ikisine de kondu — **`dagit.sh`
  taşımıyor, elle konuldu**, depoda yok
- uçakta: **ylp00 konteyneri yeniden OLUŞTURULDU** (log döndürmesi ancak
  öyle devreye giriyor); ylp02'de yapılmadı
- belge: `TUZAKLAR` §1.18 + §1.19, `RPI_ESITLEME` (A8/A11/A12/B7/B8 +
  "`dagit.sh` neyi taşır" tablosu + ylp01 için adım adım liste),
  `YAPILACAKLAR`, `KARARLAR` (KARAR-05), `CLAUDE.md` §9 test kuralları

**Yarım kalan / tuzak**

- 🔴 **`mcap` ikilisi depoda DEĞİL.** Yoksa onarım sessizce eski davranışına
  döner ve daha çok veri kaybettirir — **hata vermez.** ylp01 dönünce elle
  konulacak; depoya koyup koymamaya karar verilmedi.
- **docker log döndürmesi ylp02'de yok** — orada bozukluk olmadığı için
  yeniden oluşturulmadı.
- **Kayıt diski tavanda:** ylp00'da 4,9 GB / 5,0 GB. Saatlik timer **en eski
  kaydı sürekli siliyor.** Saklanacak bir uçuş varsa dizüstüne kopyalanmalı.
- `mcap recover` **başarılı** kısmi kurtarmada çıkış kodu **3** dönüyor.
  Koda bakıp elemek kurtarılan veriyi çöpe atar — `kayit_onar.sh` sonuca
  bakıyor. (İlk yazımda bu hatayı yaptım, test yakaladı.)
- `sudo` gereken işler `drone_bul.sh <ad> '<komut>'` ile **çalışmaz** (`-t`
  yok). Komut vermeden çağır, etkileşimli kabuk açılır.
- Kayıt düğümü normal çalışırken her 30 sn `Writing remaining messages from
  cache` basıyor — `--max-cache-size 100000` küçük olabilir, **ölçülmedi.**

**Sıradaki adım**

P0.14 yer testi: liderin `consensus_node`'unu öldür (uçak ayakta kalsın),
takipçi ~1 sn'de yeni seçim yapmalı. Bkz. `YAPILACAKLAR.md` P0.14.

**Uçakların bırakıldığı hâl**

- **ylp00:** konteyner ayakta (23:22 sonrası), **11 düğüm**, `connected=true
  armed=false`, `AUTO.LOITER`. Pervaneler **ÇIKIK**. A8 var, `mcap` var,
  log döndürme var. Kayıt diski tavanda (4,9/5,0 GB).
- **ylp02:** konteyner ayakta (23:22'de yeniden başlatıldı), **11 düğüm**,
  `connected=true armed=false`, `AUTO.LOITER`. Pervaneler **ÇIKIK**.
  A8 var, `mcap` var, **log döndürme YOK**.
- **ylp01:** yerde. `RPI_ESITLEME.md` bölüm 2'de dönünce yapılacak 5 adım.

---

## 2026-08-20 18:05 — Eyüp + Claude (Berk'in işi ölçümle doğrulandı, ADIM 4 adaptörü saha'ya alındı, belgeler sadeleştirildi)

> Uçuş yok. Üç iş: **arkadaşların 52 commit'ini doğrulamak**, **yetim kalan
> kendi commit'lerimi `saha`'ya almak**, **belge yığınını sadeleştirmek.**

**Ne yapıldı**

*Uçaklara bağlanma — MAC değişmemiş, `known_hosts` takılmıştı*

- Ağ `10.205.4.x`; ylp00 `.134`, ylp02 `.189`. **MAC'ler tabloyla birebir
  aynı**, değişen tek şey IP. Bağlantıyı kıran `known_hosts`'tu: yeni IP →
  `Host key verification failed`. Canlı anahtarlar eski IP kayıtlarıyla
  karşılaştırıldı (4 ve 3 eşleşme) → aynı Pi'ler, MITM değil. Yeni IP'ler
  eklendi. **Bu YKİ dizüstünde bir değişiklik, uçakta değil.**

*🔴 İki uçak da ölüydü — ağdan önce kalkmışlar*

Ölçüldü (ylp00): Pi açılış **15:51**, konteyner + mavros **15:52:41**, wlan0
DHCP kirası **15:56:32** — dört dakika sonra. NetworkManager günlüğünde iki
kez `no lease`, sonra `new lease, address=10.205.4.134`.

Sonucu: her düğüm **eski** adrese yazmaya çalışıyordu
(`ddsi_udp_conn_write to udp/172.19.167.x failed`) ve `mavros.log` **442 MB**
olmuştu. Üstüne ylp00'da `baslat.sh:211` `gps_saat.py`'yi **arka plana
atmadan** çağırıyor; süreç `--bekle 150`'ye rağmen 25+ dakika takıldı ve
`baslat.sh`'in geri kalanı **hiç çalışmadı** — yalnız mavros vardı,
px4_bridge/esp32_bridge/agent_fsm yoktu. ylp02'de yığın ayaktaydı ama o da
eski adrese yazıyordu.

`docker restart` ikisini de düzeltti: **12 düğüm, 0 ddsi hatası, log 20 KB.**
Yeni madde **P0.13**.

> ⚠️ Yolda bir teşhis hatası yaptım: `ros2 node list` boş dönünce "DDS keşfi
> bozuk" dedim. Değildi — benim istemcimde `ROS_LOCALHOST_ONLY` yoktu, düğümler
> loopback'teydi. Graf sağlamdı, bakışım kördü. Doğru komut:
> `ROS_LOCALHOST_ONLY=1 ros2 node list --no-daemon`.

*✅ Berk'in işi doğrulandı — belgeye değil ölçüme bakarak*

- **Kod gerçekten uçakta:** beş kritik dosyanın md5'i `d9be7c9` ile **5/5
  birebir** (`formation_node` = `bd40492c`, YAPILACAKLAR'da yazan değerin aynısı).
- **Uçuşlar gerçekten olmuş:** kayıtlar duruyor (20 Ağu 01:27 37 MB · 01:47
  172 MB · 02:57 86 MB · 03:32 15 MB).
- **A/B ölçümünü kendim tekrarladım** — `kayma_coz.py` ile ham bag'lerden:

  | | ylp02 (FF kapalı) | ylp00 (FF açık) |
  |---|---|---|
  | tepe hata | 1.177 / 1.026 m | **0.551 / 0.324 m** |
  | ortalama | **1.10 m** | **0.44 m → −60 %** |

  Commit mesajındaki "1.10 → 0.44" **birebir çıktı.** Uydurma değil.
- **Parametreler canlı okundu, ikisinde de:** `guided_ivme_ff=1.0`,
  `kalkis_olayla=False`, `formation sitl_mode=False`, `yer_testi=False`.
- Testleri koştu (5 geçti, 7 ROS gerektirdiği için atlandı).

> 🔎 Tek çekince: ylp00'ın 1. bacağında kalıcı kayma 0.254 m, ylp02'de 0.073 m.
> 2. bacakta ikisi eşit (0.092 / 0.083). Muhtemelen oturma penceresi seyir
> ortalamasına karışıyor. Özetlerde bu sayı yok — sonraki uçuşta bakılsın.

*Yetim commit'ler `saha/main`'e alındı*

15 Ağustos'ta yazdığım üç commit hiçbir uzakta yoktu (PR #118 squash olduğu
için dal atası değil; düz push 123 commit gönderirdi). Cherry-pick denendi:
**beş kod dosyası temiz uyguladı**, yalnız `.md`'ler çakıştı.

- `komsu_adaptoru.py` (129) + testi (198) + `collision_avoidance_node` (85)
  + `ucus_ayarlari.py` eşikleri + `baslat.sh` → **KARAR-01 Seçenek C'nin
  uygulaması.** Test 10/10, `saha/main` üzerinde koşturuldu.
- **Kaçınma eşikleri karara bağlandı.** 15 Ağu `8.0/4.0` demişti, 18 Ağu
  `6.0/3.0`'a düzeltilmişti; **ikisi de ayrı bir arıza biçiminde haklıydı**
  (`hard < MIN_AYRIM` → koruma geç · `d0 ≈ formasyon` → koruma fazla).
  Operatör kararı: **`hard=4.0` (sınıra bağlı) + `d0=6.0` (formasyona bağlı)**.
  `ucus_ayarlari.py` artık `Yapilandirma tutarli` diyor.
- `CLAUDE.md` **uçuş öncesi kırmızı çizgiler** geri geldi — saha'da hiç yoktu.

*🔴 Denetimin doğrulanmamış iki P0'ı KODDA DURUYOR*

`WORKFLOW_BULGULAR.md`'de 42 bulgu var, 7'si doğrulanabilmiş. Bu ikisini kod
okuyarak **ben doğruladım** → **P0.12**:

1. `consensus_node.py:183` — `ctx.is_leader` hiçbir yerde geri alınmıyor
   (`election.decide_change` `effective` boşsa hemen `None` dönüyor). İniş
   sonrası yerde duran **disarm uçak 10 Hz kalp atışı basmaya devam eder**.
2. `esp32_bridge_node.py:1688` — kuyruk ayıklaması yalnız aynı hedefe giden
   `TIP_GOTO` için; `land` bekleyen GOTO'ları temizlemiyor. **İniş iptal olur**
   ve 10 Hz tekrar hedefi sonsuza kadar tazeler.

Ayrıca denetimin **2/2 doğrulanmış** iki bulgusu hiçbir iş listesinde yoktu →
**P0.14**: lider kaybı tespiti tamamen ölü (birincil 300 ms yol `own_airborne`
hiç true olmadığı için çalışmıyor, yedek 3 sn bayatlık **yanlış akışı**
ölçüyor). Düşmüş bir lider süresiz olarak sürünün lideri kalabilir.

*Belge sadeleştirmesi (`ultracode` ile korumalı)*

13 canlı belge okundu. Tekrar ölçüldü: `ucus_ayarlari.py` **10 dosyada**,
gözlem merdiveni **7** — `SURU_ENTEGRASYON` kendi içinde **iki kez**.

`PLAN` + `SURU_ENTEGRASYON` + `NAVIGASYON_KAYMA` → tek `PLAN.md`. Eski iki ad
**yönlendirme** olarak duruyor (5 koddan atıf var).

🔴 **12 "TAMAMLANDI" bölümü silinmeden önce 12 bağımsız ajan her birinin
içeriğinin başka belgede durup durmadığını doğruladı.** Sonuç: **3 bölüm
güvenle silinebilir, 9'unda başka hiçbir yerde olmayan bilgi vardı ve
10 işaretlenmemiş açık iş "TAMAMLANDI" başlığının altında saklıydı.**
Hepsi taşındı. Kendi kontrolümde 4'ü yine de düşmüştü, geri kondu.

**Ne değişti**

- kod: **yok** — bu oturumda uçuş koduna hiç dokunulmadı
- **uçakta:** `docker restart drone1` + `drone3` (16:37). Bayraklar
  değişmedi (`kacinma` VAR, `gozlem` VAR, `yer_testi` YOK, `ucus_ayarlari.env`
  VAR). **Kod hâlâ `d9be7c9`** — bugün push edilen 4 commit **dağıtılmadı**.
- YKİ dizüstü: `~/.ssh/known_hosts`'a iki IP eklendi (yedek:
  `known_hosts.yedek-20260820-1558`)
- belge: `PLAN` (birleşik), `README` (bozuk sonu yeniden yazıldı), `CLAUDE`,
  `DURUM`, `YAPILACAKLAR`, `KARARLAR` (KARAR-04 eklendi), `TUZAKLAR`
  (§2.10-2.12), `RPI_ESITLEME`, `cihazlar`, `WORKFLOW_BULGULAR`,
  `INTERFACE_CONTRACT`, `deploy/rpi/README`

**Yarım kalan / tuzak**

- 🔴 **P0.12, P0.13, P0.14 düzeltilmedi** — üçü de bir sonraki uçuştan önce
  kapanmalı. P0.12'nin ikisi toplam ~4 satır.
- 🔴 **Uçaklardaki kod bugünkü `main` değil.** `dagit.sh` çalıştırılmadı;
  ADIM 4 adaptörü uçakta **yok**.
- 🟠 **`RPI_ESITLEME` yanlış bir olguyu canlı belge olarak yazıyordu:**
  *"`--symlink-install` sayesinde `/ws/src`'e kopyalamak yeterli"* — **tersi
  doğru**, `colcon build` şart. Düzeltildi (`TUZAKLAR` §2.11), ama biri o
  cümleye bakıp yalnız `rsync` ile dağıtmış olabilir.
- 🟠 **`WORKFLOW_BULGULAR`'da tek nokta arızası:** 16 bulgunun mekanizma metni
  kesik, tam hâli yalnız **Berk'in Mac'indeki** `journal.jsonl`'de. Depoda yok.
  **Berk: o dosyayı depoya al.**
- 🟡 Belge sadeleşmesi %36 hedeflenmişti, **%9 çıktı** (7854 → 7183). Tekrar
  sanılanın çoğu yanlış yerde duran tek nüsha bilgiymiş.
- 🟡 `docker/rpi/` silinmiş ve imajın tek tarifi oydu — **karar verilmedi**,
  YAPILACAKLAR'a madde açılmadı (operatör onaylamadı). ylp01 dönünce ve
  `cv2`+`pyzbar` eklenirken gerekecek. CI'da flake8 kapalı — o da cevapsız.

*Konteyner imajı kararı — KARAR-05 (18:20)*

Operatör kararı: **`docker/rpi/` geri gelmeyecek**, imaj `docker save`
kopyasıyla korunacak. Gerekçe yeniden üretilebilirlik değil **birebir
çoğaltma** — yeniden derleme `apt`'tan güncel paket çekip ortamı kaydırırdı,
oysa elimizdeki bilinen-iyi bir ortam (uçuş kanıtını o geçirdi).

Ölçüldü: `yelpence-ros:latest` **1.26 GB**, ID `661296d759c2`, **iki Pi'de de
aynı** (ayrışma yok). Yedek alındı, dizüstüne çekildi, doğrulandı:
378 MB · md5 `98c7f7c9…` · 13 katman · `gzip -t` sağlam · 1m34s.
Uçaktaki geçici kopya silindi.

> 🔎 **Düzeltme:** "yedek hiç alınmamış, tek risk bu" demiştim — **yanlıştı.**
> `~/yelpence-yedek/`'te **30 Temmuz'dan** bir kopya zaten varmış ve config
> hash'i aynı (`661296d…`). İmaj 4 haftadır değişmemiş. Eksik olan yedek
> değil **kaydıydı** — hiçbir belgede yazmıyordu. Klasöre `README.md` konuldu.

**Sıradaki adım**

**P0.12'nin iki düzeltmesini yap (~4 satır), sonra G2 tekrarı** —
`YAPILACAKLAR` P0.11. ⚠️ KARAR-02: consensus'un ilk gerçek hava görevi,
uçuştan önce `ultracode` önerilecek.

**Uçakların bırakıldığı hâl**

- **ylp00** (drone1, `10.205.4.134`): konteyner **ayakta** (16:37 restart,
  12 düğüm, 0 hata). Pervaneler **TAKILI**. Kod `d9be7c9`. Bayraklar:
  `kacinma` VAR · `gozlem` VAR ⚠️ · `yer_testi` YOK → **kalkış komutunu ALIR**.
  Disk 17 GB boş.
- **ylp02** (drone3, `10.205.4.189`): aynısı, kod ylp00 ile senkron.
  Disk 17 GB boş.
- **ylp01**: yerde, onarılmadı.

⚠️ **Uçuştan önce `/ws/gozlem` SİLİNMELİ** — duruyorken `formation_node`
çıktısı uçağa ulaşmıyor.

---

## 2026-08-20 03:21 — Berk + Claude (RC failsafe HAVADA, P0.9 + P0.11 kapandı, kayma ÖLÇÜLDÜ, ivme ileri-beslemesi A/B)

> Uzun bir gece: **bir düşüş**, üç uçuş, iki P0 kapanışı ve ölçülmüş bir
> kontrol iyileştirmesi. Sıra önemli — düşüş, failsafe işini yarıda
> yakaladı ve dersi belgeye girdi.

**Ne yapıldı**

*🔴 RC-kayıp failsafe'i — ve yolda bir düşüş*

- Sorun: FS-iA6B kumanda kapanınca **susmuyor**, failsafe çerçevesi basıyor;
  PX4 kaybı göremiyordu. Gün içinde iki yöntem denendi, **Ch3 üst-uç** tuttu:
  alıcı kayıpta gaz kanalına **2100** basar, canlı tavan 2000, eşik **2050**.
  Parametreler: `RC_FAILS_THR=2050`, `RC_MAP_FAILSAFE=3` (iki uçakta da).
- **HAVADA doğrulandı (ylp00):** alçak askıda kumanda kapatıldı →
  **1-2 sn içinde RTL**, motor kesilmedi.
- 🔴 **DÜŞÜŞ:** ölçüm yapılmadan yapılan bir hava denemesinde kumandanın
  CH5 (kill) failsafe'i **+100%** kayıtlıydı → kumanda kapanınca alıcı
  "kill'e bas" çerçevesi bastı → **motorlar anında kesildi, ylp00 alçaktan
  düştü.** RTL ayarlı olması kurtarmadı: kill her şeyi ezer. Hasar kontrolü
  yapıldı — pervane/gövde/motor temiz, GPS **RTK-FIXED 30 uydu**,
  clipping **0/0/0**. Ders `TUZAKLAR` §0.4'e yazıldı.
- **P0.9 KAPANDI:** ylp02'nin kill failsafe'i deneyle kanıtlandı (switch
  konumundan bağımsız `CH5=2000` → kayıtlı kill), `-100%`'e çekildi,
  `CH5=1000` ölçüldü. İki uçağın failsafe davranışı artık aynı.

*🔴 P0.11 — sürü yığını guided uçuşta ölüydü, KAPANDI*

- **Uçak-içi köprü yazıldı:** `esp32_bridge` guided ARM'ı işlerken yerel
  `EVENT_MISSION_STARTED` üretiyor. Firmware'e dokunulmadı (mesh whitelist'e
  çarpmaz), teslimatı kanıtlanmış guided yolun aynısı.
- `agent_fsm`'e **`kalkis_olayla`** parametresi: olay ajanı yalnız ARMED'a
  taşır, TAKEOFF'u tetiklemez — kalkış otoritesi guided yolda kalır.
- **Yerde iki uçakla geçti**, sonra **HAVADA ölçüldü:** iki uçak
  **251 ms** arayla aynı lideri seçti (`0→1`, round=1); ylp00 inip IDLE'a
  düşünce liderlik **749 ms** içinde ajan 3'e devredildi. Split-brain yok.
  Kalp atışı yerde de yayınlansın diye `own_airborne` şartı kaldırıldı;
  mesh üzerinden komşuya ulaştığı ölçüldü (499 mesaj).
  ⚠️ Devir **düzgün** devirdi (ayrılan lider duyurdu). **Ani** lider kaybı
  hâlâ sınanmadı — o yol kalp atışı zaman aşımına dayanıyor ve denetim onun
  `own_airborne=false` iken ölü olduğunu 2/2 onayla gösterdi.

*🧠 Çok ajanlı denetim (KARAR-02 `ultracode`)*

- 5 avcı, **42 bulgu** → yeni belge **`docs/WORKFLOW_BULGULAR.md`**.
  Doğrulama aşaması operatör kararıyla yarıda kesildi (7 karar tamamlandı).
- **En değerli sonuç bir ÇÜRÜTME:** "her GOTO çerçevesi RC failsafe RTL'ini
  geri alıyor" iddiası yanlış çıktı — görev koşucusu her tikte `flight_mode`
  denetliyor ve OFFBOARD dışında görevi kesiyor
  (`gorev_kanit_ucus.py:2177-2186`). Tek kanalda kalsaydı bu "uçuş engeli"
  diye yazılacaktı.
- Bulgu üzerine **`kalkis_olayla` varsayılanı `True → False`** yapıldı
  (emniyet varsayılanı güvenli tarafta olmalı), dağıtıldı, iki uçakta da
  `ros2 param get` ile doğrulandı.

*📏 Navigasyon kayması ÖLÇÜLDÜ (P0.4 Adım 1) — ve düzeltildi*

- **30 m bacak, iki uçak, 3.0 m/s:** kalıcı kayma **≈0.10 m**, tepe geçici
  hata **≈1.12 m**, oturma **≈3.5 s**. **Eski 0.44 m rakamı geçersizdi**
  (7 m'lik bacakta geçici rejim ölçülmüş). Sonuç: hız artırmanın önündeki
  engel kayma DEĞİL.
- Operatör iki davranış fark etti, ikisi de ölçümle doğrulandı:
  (a) kalkıştan sonra ~0.5 m geri hareket — plan anındaki konum ile ARM
  anındaki çapa arasındaki EKF kayması (1 Ağustos'ta 1.42 m'ydi);
  (b) bacak sonunda **1.18 m aşım**, ~3 sn'de düzeliyor.
- **İvme ileri-beslemesi yazıldı** (`guided_ivme_ff`, varsayılan KAPALI) ve
  **aynı uçuşta A/B ölçüldü** — ylp00 açık, ylp02 kapalı:

  | | FF kapalı | FF açık | kazanç |
  |---|---|---|---|
  | tepe geçici hata | 1.177 / 1.026 m | 0.551 / 0.324 m | **−60 %** |
  | varış aşımı | 1.18 m | 0.46 m | **−61 %** |
  | oturma | 3.88 / 3.36 s | 3.1 / 1.0 s | daha hızlı |

  ylp02 kendi tabanını birebir tekrarladı (1.173/1.053 → 1.177/1.026),
  yani fark **koddan** geliyor.

**Ne değişti**

- kod (8 commit, `3547d7b`…`c1e3f27`): `agent_fsm_node` (kalkis_olayla) ·
  `esp32_bridge_node` (guided köprüsü) · `consensus_node` (kalp atışı yerde
  de) · `px4_bridge` + `mavros_command_sender` (ivme ileri-beslemesi, 12 test)
  · `baslat.sh` · `gorev_kanit_ucus.py` (`--mesafe`, g2 için `--irtifa`) ·
  `deploy/rpi/teshis/` (3 kayıt çözümleme betiği)
- **uçakta:**
  - kod **`b46a258`** (ikisinde de; `.surum`'daki `+KIRLI` YKİ tarafındaki
    dosyadandı, o da artık commit'li)
  - 🔴 **`yer_testi` bayrağı İKİSİNDEN DE SİLİNDİ** — uçaklar kalkış
    komutunu alır durumda
  - ✅ **`guided_ivme_ff=1.0` İKİ UÇAKTA DA ve KALICI** (03:45, operatör
    kararı): varsayılan 1.0 yapıldı + `baslat.sh`'e `GUIDED_IVME_FF` env'i
    eklendi; restart sonrası ikisinde de doğrulandı. Uçaklardaki kod
    **`d9be7c9`**. Geri alma tek satır: `GUIDED_IVME_FF=0.0`
  - PX4: `RC_FAILS_THR=2050`, `RC_MAP_FAILSAFE=3` (ikisinde de);
    ylp00'da `RC6_MAX/TRIM` fabrikaya döndü; **ylp00'ın RC kalibrasyonu
    yenilendi** (`RC3_MIN` 1016→906)
  - **kumandalar:** ikisinde de `Ch3` failsafe 2100'e kaydedildi;
    ylp02'de `Ch5` +100 → **-100** (kill kapatıldı), `Ch7` -100
  - ylp00'da **`core.50` silindi** (337 MB), disk %40
- belge: `DURUM` · `YAPILACAKLAR` · `RPI_ESITLEME` · `TUZAKLAR` (§0.4 düşüş
  dersi, §0.5 FlySky 900-2100 tabanı, §1.16 YKİ rc_link_ok tuzağı) ·
  `NAVIGASYON_KAYMA` (Adım 1 ölçüm + Adım 2 A/B) · **yeni**
  `WORKFLOW_BULGULAR.md`

**Yarım kalan / tuzak**

- 🟡 **İvme FF artık varsayılan AÇIK ve iki uçakta kalıcı** — ikinci
  doğrulama uçuşu beklenmeden, operatör kararıyla. Bir sonraki uçuşta
  kayıttan tepe hata/aşım teyit edilmeli (0.44 / 0.46 m civarı).
  Geri alma tek satır: `GUIDED_IVME_FF=0.0`.
- 🟠 **4 m/s kayma ölçümü yapılmadı** — 40 m bacak ister (28 m oturma +
  pencere). Kuru testi geçmişti, pil bitti.
- 🟠 **Denetimin doğrulama aşaması yarım** — 42 bulgunun 7'si karara
  bağlandı. Etiketsiz bulgular *iddia* düzeyinde; uygulamadan önce koddan
  teyit edilmeli (`WORKFLOW_BULGULAR.md` başındaki uyarı).
- 🟠 **"Bayat GOTO iniş komutunu geri alıyor" bulgusu doğrulanmadı.**
  Mekanizmayı ben koddan gördüm (`esp32_bridge_node.py:1204` her GOTO'da
  koşulsuz `offboard` yolluyor; kuyruk ayıklaması LAND'de GOTO kopyalarını
  temizlemiyor) ama penceresi dar (~0.75 sn) ve ikinci `land` ile kurtarılıyor.
- 🟡 **`titresim_olc.py` hiç koşulmadı** — operatör kararıyla atlandı.
  Clipping sayaçları uçuşlardan sonra yine de **0/0/0** ölçüldü.
- 🟡 **ylp02 her inişte PosCtl'e geçiyor** (ylp00 Auto.Land'de kalırken).
  Pilot son metrelerde devralıyor olabilir; doğrulanmadı, zararsız görünüyor.
- 🟡 `ros2 bag info` çalışmıyor (kayıt hâlâ yazılıyor, metadata kapanmamış).
  Çözümleme betikleri parça `.mcap`'leri tek tek okuyor — `deploy/rpi/teshis/`.
- 🟡 **Bazın anteni** son survey'den beri taşındı mı hâlâ bilinmiyor
  (18 Ağustos'tan kalan soru).

**Sıradaki adım**

1. 🟠 **İkinci ivme-FF doğrulama uçuşu** → geçerse `guided_ivme_ff`
   varsayılanı 1.0 + `baslat.sh` env. Kazanç ölçüldü, kalan iş tekrar.
2. 🟠 **4 m/s kayma ölçümü** (40 m bacak) — hız artışının bedelini
   sayıyla verir.
3. 🟠 `WORKFLOW_BULGULAR.md`'deki açık P0/P1'leri koddan teyit et; özellikle
   bayat-GOTO maddesi.
4. ⚪ Ani lider kaybı senaryosu (kalp atışı zaman aşımı) — ADIM 3 işi,
   `kalkis_olayla=true` ister.

**Uçakların bırakıldığı hâl**

- **İkisi de yerde, disarm, kill yok, sağlıklı**, RTK-FIXED 32 uydu,
  konteynerler ayakta, kod `b46a258` (senkron).
- **Pervaneler TAKILI** (son uçuştan sonra sökülmedi).
- `yer_testi` **YOK** (kalkış komutunu alırlar) · `gozlem` ve `kacinma`
  bayrakları **VAR** (ikisinde de).
- ylp00'da `guided_ivme_ff=1.0` canlı — restart'ta sıfırlanır.
- Uçuş kayıtları uçaklarda: `ylp00_20260820_025641`, `ylp02_20260820_025701`
  (ivme FF A/B) ve bir önceki 30 m kayma uçuşununkiler.

---

## 2026-08-18 → 19 00:12 — Berk + Claude (YKİ macOS'ta ayağa kalktı, G2 uçuşu yapıldı, sürü yığınının FSM kopukluğu bulundu)

> Uçuş **yapılmadı**, uçak yazılımına **dokunulmadı**. Gün YKİ tarafında geçti
> ama uçakları ilgilendiren üç ölçüm çıktı — biri uçuş engeli.

**Ne yapıldı**

*YKİ ilk kez macOS'ta çalıştı*

- Base ESP ve RTK bazı Berk'in MacBook'una takılıydı, ama YKİ yazılımı ROS 2
  istiyor ve macOS'ta apt yok. Üç yol araştırıldı, **ölçümle** karar verildi:
  - UTM sanal makine + USB passthrough → **elendi.** UTM belgesi: macOS
    çekirdeğinin sahiplendiği cihazlarda düzgün reset yapılamıyor; CH340'ı
    Mojave'den beri Apple sürücüsü sahipleniyor. Üstelik makine 8 GB M1,
    VM 3-4 GB alıp QGC + tarayıcı + Vite + backend'e yer bırakmıyor.
  - Colima + konteyner + seri köprü → çalışır ama üç fazladan parça.
  - **RoboStack/pixi ile native ROS 2 → seçildi.** Gerekli paketlerin hepsi
    osx-arm64'te var (`ros-base` 0.11.0, `mavros-msgs` 2.14.0,
    `rmw-cyclonedds-cpp` 2.2.3) ve YKİ yolunda `numpy` hiç kullanılmıyor.
- **Seri port native ölçüldü:** CH340 @460800, ROS'suz ham mesh çözümü —
  6 saniyede **79 POSE + 12 DURUM, 0 bozuk çerçeve**. Köprüye gerek kalmadı.
- `colcon build` macOS'ta **48 saniyede** geçti (3 paket). `swarm_control`
  testleri: **140 geçti**, 1 atlandı.
- `yki_baslat.sh` env ile parametrelendi (`ROS_SETUP`, `DDS_URI`,
  `BASE_ESP_PORT`, `RTK_GPS_PORT`) — **ikinci betik yazılmadı**, Ubuntu
  davranışı birebir aynı. macOS'a özgü dosyalar `~/yelpence-yki-mac/`
  altında ve depoya girmiyor (Osman'ın `arch-docker/`'ı gibi).

*🔴 Dört sessiz arıza*

1. **QGC, RTK bazının portunu kapıyordu.** `AutoConnect → RTK GPS` açıkken
   QGC u-blox'u tutuyor, `yki_rtcm_reader` `Resource busy` alıyor ve **RTCM
   hiç akmıyor**. Belirti sessiz: telemetri normal, tek işaret `fix_type`'ın
   6 yerine 3-5'te takılması. Port sahibi `lsof` ile bulundu
   (`QGroundControl PID 6245`). Kapatılınca akış 9-10 msg/s'e döndü, iki uçak
   da **RTK-FIXED**. → `TUZAKLAR` §6.6, `DURUM` §2
2. **YKİ'de `/swarm/public/origin`'e kimse yazmıyordu.** Haritaya tıklayınca
   backend 409 *"Origin henüz yok"* dönüyordu. Kök neden: 15 Ağustos'ta
   `swarm_origin_publisher`'ın varsayılan konusu `/public` → `/internal`
   değiştirilmiş, uçaktaki `baslat.sh` güncellenmiş ama **`yki_baslat.sh`
   atlanmış**. İki yayıncı da `internal`'a yazıyordu (`Publisher count: 2`),
   `public` boştu. **Bu macOS'a özgü değil — Ubuntu YKİ'de de vardı.**
   ✅ Düzeltildi, doğrulandı: `seq=1 lat=38.6904758 lon=39.1610188 alt=1216.96`.
3. **`drone_bul.sh` macOS'ta ylp01'i sessizce kaçıracaktı.** `arp -an`
   MAC sekizlilerinin baştaki sıfırını atıyor (`…:da:04:2d` → `…:da:4:2d`);
   ylp00/ylp02'de sıfırlı sekizli yok, o yüzden **yalnız ylp01** etkilenecek
   ve ancak o dönünce fark edilecekti. → `TUZAKLAR` §9.1
4. **`yki_baslat.sh` macOS'ta yarım YKİ bırakıyordu.** ROS bulunamıyor,
   `source` sessizce düşüyor, betik dört düğüm başlatmaya devam ediyor ve
   ekran normal görünüyor. ✅ Erken-patlama kapısı eklendi.

*🔴 ylp02'nin alıcı failsafe'i kill tetikliyor — `TUZAKLAR` §0.2 CEVAPLANDI*

Kumanda kapalı/açık iki kez ölçüldü:

```
                 ylp00 (drone1)            ylp02 (drone3)
kumanda kapalı   kill=False healthy=True   kill=True  healthy=False
kumanda açık     kill=False healthy=True   kill=False healthy=True
```

`rc_link_ok` iki durumda da `True`, diğer bütün sağlık bayrakları temiz.
Belgede sanık **ylp00**'dı; ölçüm **ylp02**'yi gösteriyor. Havada karşılığı:
RC kaybı → RTL değil **anında motor kesme**. Ayrıca `healthy=False` olan ajan
`election.py`'de lider adayı olamıyor — G2'nin tek sorusu tam da bu.
→ `YAPILACAKLAR` **P0.9**

*🔴 G2 bu hâliyle boş kayıt üretecekti — ve YKİ'den beslemek firmware'de kapalı*

- `formation_node` uçaklarda koşuyor ama **girdisi yok**: tarifi üreten
  `mission1_node` kapalı. Girdi olmadan hiçbir şey yayınlamıyor
  (`formation_node.py:878`). Gözlem uçuşu boş kayıt üretirdi.
- Denendi: YKİ tarifi mesh'ten yollasın. ROS tarafı yazıldı, uçtan uca
  çalıştı — base `form_tx=4`, `gonderim_drop=0`; ofset matematiği gerçek
  `rotate_offset` ile gidiş-dönüş test edildi (**hata 0.00e+00 m**), codec
  kuantizasyonu ölçüldü (**merkez ≤4 cm, ofset ≤5 cm**).
- **Ama uçak `form_rx=0`.** Sebep RX BASE firmware whitelist'i: 0x11-0x15
  **bilerek** dışarıda — *"formasyonu LİDER üretir (KARAR 3); YKİ'nin aynı
  tipi yayınlaması ÇİFT KAYNAK olur"*. Firmware doğru yolu da yazmış:
  YKİ **talep** gönderir, lider tarifi üretir.
- **Yazılan kod tamamen geri alındı** (operatör kararı). Çalışmayan bir
  `--gozlem-formasyon` bayrağı bırakmak, sonraki kişi için tuzak olurdu.
  → `YAPILACAKLAR` **P0.10**

*✅ `formation_node` ilk kez gerçek komutla ölçüldü — ve çözüm uçakta hazırmış*

- P0.10 için `mission1_node`'u açmaya hazırlanırken ylp00'daki betikler
  listelendi ve **`form_yayinla.sh`** bulundu: bir takım arkadaşı, formasyon
  komutunu **uçakta** üretip mesh'e veren betiği çoktan yazmış. Lideri
  `/swarm/internal/election/result`'a bildirip formasyonu
  `/swarm/internal/formation/target`'a basıyor; köprü loopback ile yerel
  `/swarm/public/formation/target`'a koyuyor. **Firmware whitelist sorununa
  hiç çarpmıyor**, çünkü yer→hava yönünü kullanmıyor. Bugün YKİ'den zorlamaya
  çalıştığım şeyin doğru katmandaki hâli buymuş.
- Konteyner yeniden başlatılmadan, yeni düğüm açılmadan ölçüm yapıldı
  (`gozlem` bayrağı açık, çıktı uçağa ulaşmıyor). 383 örnek ≈ 14 Hz:
  ```
  komut : merkez 12.3 / -45.6 / -8.0  heading 137.5  max_speed 3.5
  cikti : x=12.2990 y=-45.6019 z=-8.000   (merkeze 0.9 mm)
          |v| = 3.500 m/s  (tam tavan)    position_valid: FALSE
  ```
  Slot hesabı doğru (V'de ajan 1 tepe), rampa oturuyor, hız doygunlukta —
  uçak yerde olduğu için 44 m hata var, beklenen davranış.
  **`position_valid=false`** yani saf hız kipi; ADIM 3'ün açık maddesi ilk kez
  gerçek telemetriyle doğrulandı.
- Gözlem modu bir kez daha kendini ödedi: bağlı olsaydı yerdeki uçağa 3.5 m/s
  ile 44 m ötesine gitme komutu giderdi.
- Betiğin içinde belgelerde olmayan bir QoS tuzağı da yazılıydı →
  `TUZAKLAR` §2.9. Kayıp betik listesi de geri çekildi → `YAPILACAKLAR` P2.5.

*Akşam — kurtarma ve küçük düzeltmeler*

- ✅ **21 saha teşhis betiği repoya alındı** → `deploy/rpi/teshis/` + README.
  Yalnız ylp00'ın SD kartında, versiyonsuz duruyorlardı; listeleri
  `COP_TEMIZLIK.md` silinince kaybolmuştu (P2.5). Parola/anahtar/sabit IP
  taraması yapıldı, temiz. README onları **ARM eden / sahte veri enjekte eden /
  güvenli** diye ayırıyor — sekizi gerçekten motor döndürüyor.
- ✅ `dagit.sh` artık bu betikleri de dağıtıyor (uçağın `~/yelpence_ws/`
  köküne, alt dizine değil ki iki kopya oluşmasın). ⚠️ **Uçakta sınanmadı**,
  sebebi aşağıda.
- ✅ **`has_origin()` ölü koddan çıkarıldı** — `/api/health` artık
  `origin: true/false` döndürüyor. Bugün gerçek bir arıza (origin remap hatası)
  tam bunun arkasına saklanmıştı: telemetri normal akarken harita 409 veriyordu.
- 🔴 **`dagit.sh` bu Mac'te ÇALIŞMIYOR — ve sessizce yanlış uçağa eşliyor.**
  macOS bash 3.2 ile geliyor, `declare -A` yok; "invalid option" deyip
  **devam ediyor**, sonra `[ylp00]`/`[ylp02]` aritmetik olarak ikisi de `0`'a
  çözülüp aynı indise yazıyor:
  ```
  ${x[ylp00]}  ->  "yelpence02"      ← ylp00 soruldu, ylp02 geldi
  ```
  Bugün `set -u` kurtardı. Olmasaydı ylp00'a ylp02'nin kullanıcı adıyla
  bağlanmaya çalışacak, "Permission denied" anahtar sorunu sanılacaktı.
  Çözüm `brew install bash` + `/opt/homebrew/bin/bash`. → `TUZAKLAR` §9.6
- `[!]` **`mission1_node` yerde test EDİLEMEZ** (kod okundu): tarif üretmesi
  için `mission_fsm`'in `ROTATE_TO_NEXT`'e gelmesi, o da uçağın gerçekten
  kalkıp sürüde olması gerekiyor. `PREFLIGHT` ayrıca `home_set` istiyor (arm
  anında set ediliyor) ve tek uçakla `all_agents_seen` sağlanmıyor.
  → P0.10'a yazıldı; bu adım **2 uçak + uçuş** ister.

*🟠 QR koordinat zinciri uçtan uca kopuk (firmware işi)*

`mesh_config.h`: *"0x0F: TIP_QR_COORDS'a rezerve"* — **rezerve edilmiş, hiç
tanımlanmamış.** Arayüz ✅, backend ✅, uçak ROS tarafı ✅; ama base bridge'in
gönderim yolu **yok** ve RX BASE whitelist'inde 0x0F **yok**. İki ucu yazılmış,
ortası yazılmamış. Kamera takılıp Aşama 3'e geçilince çıkacak.
→ `YAPILACAKLAR` **P1.8**

*Yapılan düzeltmeler ve yeni özellik*

- `dagit.sh`: `set -o pipefail` — derleme çökse bile "başarılı" diyordu
  (`TUZAKLAR` §1.14). Mekanizma kabukta doğrulandı. + `hostname` yedeği (§1.15).
- `drone_bul.sh`: macOS desteği (`getent`/`ip`/`timeout`/`/dev/tcp` yok) ve
  MAC normalizasyonu. Linux yolu değişmedi.
- **u-blox reset butonu** (operatör isteği): `⚙ Ayarlar → RTK baz istasyonu`,
  iki adımlı onaylı. Komut seri porta doğrudan gitmiyor — port tek sahipli,
  sahibi `yki_rtcm_reader`; komut ROS'tan ona gidiyor, UBX-CFG-RST'i o yazıyor.
  UBX baytları ve Fletcher sağlaması doğrulandı, uçlar sınandı
  (`kipler` ✅, geçersiz kip → 400 ✅, konu Publisher 1/Subscription 1 ✅).
  **Gerçek reset atılmadı** — baz survey-in modundaysa toparlanma dakikalar
  sürebilir, operatör kararına bırakıldı.
- SSH: Berk'in anahtarı iki uçağa kuruldu (`YAPILACAKLAR` P1.2).

*🔴 G2 GÖZLEM UÇUŞU YAPILDI (21:45) — 62 saniye, ve baş soruyu cevaplayamadı*

- Operatör `saha`'nın 187 saniyelik koreografisini reddetti (pil). Yerine
  **yeni `--senaryo g2`** yazıldı: formasyonsuz, kalk 20 m → 15 m ileri →
  herkes kendi kalkış noktasına → in. `takip`'e dokunulmadı.
  Kuru test: en kritik ayrım **9.63 m** (eşik 4.0) — GEÇTİ.
- **Uçuş kusursuz:** 62 s, üç adım da tamam, dört noktada da varış hatası
  **< 1 m**, ölçülen en dar ayrım **9.41 m** (kuru testin öngördüğü 9.63 ile
  birebir). Pilot müdahalesi yok, kill yok, eğim yok, kaçış kesicisi
  tetiklenmedi. Kayıt: ylp00 288.427 / ylp02 234.460 mesaj,
  `~/yelpence-kayitlar/g2_20260818/` (26 + 21 MB, yerel).
- 🔴 **AMA: `/swarm/*/election/result` = 0, `/swarm/*/leader/heartbeat` = 0**
  — iki uçakta da, 638 saniyede. **consensus hiç lider seçmedi.**
- **Kök neden ölçüldü:** ajan durumu uçuş boyunca **IDLE(1)**, armed=True
  olan 90 saniye dahil.
  ```
  state=1 IDLE armed=True   899 mesaj (ylp00)   880 (ylp02)   <- ucus
  ELIGIBLE_STATES = { ARMED, TAKEOFF, IN_SWARM, EXECUTING_TASK }   IDLE YOK
  ```
  `IDLE → ARMING` geçişi `EVENT_MISSION_STARTED` istiyor
  (`agent_fsm_node.py:314`); YKİ'nin guided yolu (`/api/guided/arm` → mesh →
  `px4_bridge` → MAVROS) `agent_fsm`'i **hiç görmüyor**.
- **Anlamı:** kanıtlanmış komut yolu ile sürü yığını **FSM katmanında kopuk**.
  Guided uçuşta consensus'un çalışması yapısal olarak imkânsız — bu uçuşu on
  kez tekrarlasak sonuç değişmezdi. → `YAPILACAKLAR` **P0.11** (yeni P0)
- **Uçuş boşa gitmedi, tersine:** gözlem uçuşunun yakalaması gereken tam da
  buydu. G3'te keşfedilseydi uçak formasyon düğümünün emrindeyken
  "lider yok" durumuyla karşılaşacaktık.
- **Çözüm aracı elimizde:** bugün kurtarılan `deploy/rpi/teshis/tam_kalkis.sh`
  — *"TAM AKIS: EVENT_MISSION_STARTED → ARMING → ARMED → TAKEOFF"*. Önce
  yerde, pervanesiz denenecek.
- ✅ Yan doğrulama: `swarm_fsm` çalıştı (3154 / 2559 `SwarmState`), mesh komşu
  telemetrisi akıyor (ylp00 ylp02'yi 4309, ylp02 ylp00'ı 3712 kez gördü),
  `ros2 bag reindex` **çalışıyor** (metadata'sız kayıt okunabildi).

**Ne değişti**

- kod: `deploy/rpi/dagit.sh` · `deploy/yki/drone_bul.sh` · `src/gcs/yki_baslat.sh`
  · `src/gcs/backend/connections/ros_bridge.py` · **yeni** `src/gcs/backend/api/rtk.py`
  · `src/gcs/backend/main.py` · `src/gcs/backend/rtcm/yki_rtcm_reader.py`
  · `src/gcs/frontend/src/services/api.ts` · `SettingsPanel.tsx` + `.css`
  · `src/gcs/gorev_kanit_ucus.py` (**yeni `--senaryo g2`**)
  · `src/gcs/backend/api/telemetry.py` (`/api/health` → `origin`)
  · **yeni** `deploy/rpi/teshis/` — 21 kurtarılmış saha betiği + README
- **uçakta:**
  - `~/.ssh/authorized_keys` — Berk'in anahtarı (iki uçak)
  - 🔴 **`~/yelpence_ws/yer_testi` SİLİNDİ** (iki uçak) + konteynerler yeniden
    başlatıldı. **Uçaklar artık kalkış komutunu alıyor.** → `RPI_ESITLEME`
  - ylp02'nin **alıcı failsafe'i** iki kez elle değiştirildi (düzeltildi →
    kumanda sıfırlaması geri aldı → operatör tekrar düzelttiğini bildirdi,
    **doğrulanmadı**)
  - `gozlem` ve `kacinma` bayraklarına dokunulmadı
- laptopta (depo dışı): `~/.pixi`, `~/yelpence-yki-mac/` (pixi ortamı, mac DDS
  config, `port_bul.py`, `yki_mac.sh`, README).
- belge: `DURUM`, `YAPILACAKLAR`, `TUZAKLAR` (§6.6 + yeni §9), `RPI_ESITLEME`, `GUNLUK`.

**Yarım kalan / tuzak**

- 🔴 **ylp02 kill failsafe'i GERİ GELDİ — uçak bu hâlde bırakıldı.** 17:30'da
  düzeltildi ve doğrulandı; 18:40'ta operatör kumandayı **fabrika ayarlarına
  döndürünce** alıcıya varsayılan failsafe geri yazıldı ve `CH5` tekrar `2000`
  oldu. Ayrıca kumandanın model ayarlarının tamamı (reverse, End Points, switch
  atamaları) sıfırlandı — PX4'ün RC kalibrasyonu eskisine göreydi, uçuştan önce
  çubuk yönleri / ARM / KILL / gaz uçları `rc/in`'den doğrulanmalı.
  → `YAPILACAKLAR` **P0.9** (yeniden açıldı)
- ✅ ~~ylp02'nin alıcı failsafe'i~~ → **aynı gün 17:30'da düzeltildi.**
  Kumandada `RX Setup → Failsafe → Ch5` **`+100%`** yazılıydı (failsafe kapalı
  değil, kill değeriyle kayıtlı); `-100%` yapıldı. Kumanda kapalıyken
  `CH5: 2001 → 1000`, `kill=False`, `healthy=True`. Uçuş gerekmedi.
  **Kalan:** CH6 hâlâ 2000 (Görev 2 öncesi), ve ylp00'ınki tanımlı mı
  tesadüfen mi emniyetli — bilinmiyor.
- 🟠 **Bazın anteni son survey'den beri taşındı mı bilinmiyor.** Taşındıysa
  bütün uçaklar haritada aynı yöne kayar. Operatöre soruldu, cevap gelmedi.
  Ölçülen: baz `38.6905395 39.1610681 1217.58`, origin'den 8.29 m.
- 🟠 **u-blox reset butonu gerçek donanımda hiç ateşlenmedi.** Uçlar ve UBX
  paketi doğrulandı ama alıcı hiç resetlenmedi.
- 🟡 `ros_bridge.py:527` `has_origin()` **hiçbir yerde kullanılmıyor** ve
  origin durumunu gösteren uç nokta yok — operatör "harita çalışacak mı"yı
  ancak tıklayıp 409 yiyerek öğreniyor. ~3 satırlık iş.
- 🟡 macOS'ta `pytest` **7.x'e sabitlendi**; 9.x ROS'un `launch_testing`
  eklentisiyle uyumsuz (eski hook imzası).
- ℹ️ Bugün `docs/YAPILACAKLAR.md`'de istemsiz bir karakter değişikliği oldu
  (`[ ]` → `[a]`), fark edildi ve geri alındı. Sebebi bulunamadı.

**Sıradaki adım**

🔴 **P0.11 — `agent_fsm`'i sürü yolundan ARMED'a sürmek.** G2 uçtu ama baş
sorusunu cevaplayamadı: guided yol `agent_fsm`'i atladığı için ajan IDLE'da
kalıyor ve consensus hiç seçim yapmıyor. Araç elimizde:
`deploy/rpi/teshis/tam_kalkis.sh`. **Önce yerde, pervanesiz** — ajan ARMED'a
geçiyor mu, consensus lider seçiyor mu. Geçerse **G2 tekrar uçulur** ve bu
sefer lider seçimi gerçekten ölçülür.

Bekleyen diğerleri: **ylp02 failsafe doğrulaması** (operatör düzelttiğini
söyledi, ölçülmedi), **ylp00 clipping ölçümü**, ve `formation_node`'un havada
gözlemi için `form_yayinla.sh` ile besleme. Paralelde `mission1_node` yerde açılıp ne ürettiğine
bakılacak.

**Uçakların bırakıldığı hâl**

- **İkisi de AÇIK ve yerde, disarm.** 21:45'te G2 uçuşu yapıldı (62 s),
  ikisi de kendi kalkış noktasına inip disarm oldu. Pil %100 okunuyor ama
  bu ölçüm anlamsız — uçaklar regülatörden besleniyor, `BAT1_SOURCE` kapalı.
- **ylp00:** kod `600ca65`, 11 düğüm ayaktaydı, bayraklar 17 Ağustos'taki gibi
  (`yer_testi`, `gozlem`, `kacinma`, `origin`, `suru_dugumleri`, `gcs_url`).
  Uçuş sonrası `kill=False`, `healthy=True`, RTK-FIXED, 32 uydu.
  Alıcı failsafe'i **tanımlı ve emniyetli** (`CH5=1000` ölçüldü).
  🔴 **`yer_testi` bayrağı SİLİNDİ** — uçak kalkış komutunu alır durumda.
  ⚠️ `~/yelpence_ws/core.50` — **353 MB core dump**, silinmeli.
- **ylp02:** 🔴 **`yer_testi` SİLİNDİ**, kalkış komutunu alır durumda.
  Alıcı failsafe'i gün içinde iki kez ele alındı: düzeltildi → kumanda
  fabrika sıfırlaması geri aldı → operatör **tekrar düzelttiğini bildirdi
  ama doğrulama ölçümü YAPILMADI**. Sonraki kişi kumandayı kapatıp
  `rc/in`'den `CH5`'i okusun: `1000` ise tamam, `2000` ise P0.9 hâlâ açık. Ayrıca kumandanın model
  ayarlarının tamamı sıfırlandı — çubuk yönleri, ARM (CH8), KILL (CH5) ve gaz
  uçları uçuştan önce `rc/in`'den doğrulanmalı.
- **YKİ:** Berk'in MacBook'unda koşuyor (`bash ~/yelpence-yki-mac/yki_mac.sh`),
  base ESP + RTK bazı ona takılı, RTCM 6 msg/s akıyor (MSM4, `crc_err=0`).
  QGC açık; **UDP ve RTK GPS oto-bağlanması kapalı** — RTK GPS açılırsa
  u-blox portunu kapıyor ve RTCM kesiliyor (`TUZAKLAR` §6.6).
- **Depoda commit YOK** — bugünkü değişiklikler (6 düzeltme, u-blox reset
  butonu, `--senaryo g2`, 21 kurtarılmış betik, 5 belge) çalışma ağacında
  duruyor. Sonraki kişi `git status` ile görür.
- **Uçuş kayıtları** `~/yelpence-kayitlar/g2_20260818/` — depoda değil, yerel.

---

## 2026-08-17 15:53 — Beyza + Osman + Claude (depo devri, belge sadeleştirme, YKİ Arch kurulumu, ağ teşhisi, **uçaklar `main`'e alındı**)

> **Dört oturum tek kayıtta birleştirildi:** 16 Ağustos 19:50 ve 21:32 (depo ve
> belge düzeni, uçağa dokunulmadı) + 16/17 Ağustos gecesi (YKİ laptopunun
> sıfırdan kurulumu ve "RPi bağlanınca internet kopuyor" arızasının teşhisi)
> + 17 Ağustos gündüz (SSH, saat teşhisi, uçakların `main`'e alınması, P0.8).
>
> **En taze bilgi için doğrudan aşağıdaki 17 Ağustos gündüz bölümlerine bak** —
> gecenin bazı bulguları gündüz değişti, değişenler yerinde işaretlendi.

**Ne yapıldı**

*Depo devri ve sim temizliği (Beyza)*

- ✅ **PR #118 merge edildi** (squash). Eyüp'ün 121 commit'i `main`'de.
  Çakışmalar `-X ours` ile çözüldü — uçuş kodunda Eyüp'ün tarafı kazandı,
  #117'nin Görev 2 katkısı çakışmayan yerlerden geldi.
- ✅ **Yeni repo: `yelpence-2026-saha`** (kaptan kararı). Sim'siz saha
  sürümü. Eski repo (`yelpence-2026-swarm`) arşiv, dokunulmadı.
- ✅ **83 dosya kaldırıldı**, 427 → 344. `sim/` (27 MB), `docker/`,
  `network_proxy`, `sim_rtcm_source`, `scripts/`, `qgc_proxy.py`,
  `gorev1.launch.py`, `ARCHITECTURE.md`, `COP_TEMIZLIK.md`.
- ✅ CI sadeleştirildi: Bandit ve docker testi kaldırıldı, `colcon test`
  flake8'i atlıyor. Derleme + ~340 birim test kapı olarak duruyor.
- ✅ README yeniden yazıldı — ölü atıflar gitti, mesh/WiFi ayrımı eklendi.

*Belge sadeleştirme (Osman)*

- ✅ **Arşiv tamamen silindi.** 5 saha günlüğü, 2322 satır. Silmeden önce
  içindekiler madde madde tarandı: 16 bilgi kaleminin tamamı başka yerde
  çıktı (`cihazlar.md`, `MESH_PROTOKOL_KARARLARI.md`, `kur_yki.sh`,
  `izleme_kur.sh`, `YUKLEME_PROSEDURU.md`…). Geriye benzersiz bilgi kalmadı.
- ✅ **`docs/TUZAKLAR.md` doğdu** (638 satır) — arşivdeki hâlâ geçerli her
  şey: 30+ tuzak (ölçüm aracı yalan söylüyor / ROS-DDS / PX4 / mesh-ESP32 /
  Pi-seri / RTK), ölçülmüş referans sayılar, ve **§0'da çözülmemiş üç
  güvenlik maddesi**. Maddelerin tamamı koda bakılarak doğrulandı;
  **7 tanesinin geçersizleştiği ölçüldü** ve alınmadı (`/tools` gitignore,
  `tsbuildinfo`, rosbag reindex, `MAKS_EGIM` sabiti, `gunluk/son` bağı,
  `ORIGIN_ALT` 1218.5, ylp01 durumu).
- ✅ **Arşive giden 15 `git show` işaretçisi 8 dosyadan tamamen kaldırıldı.**
  Gerekçe: commit hash'i kırılgan (depo zaten bir kez bölündü, ikincisinde
  işaretçi yalana döner) ve dostane bir komut bayat malzemeyi okumaya
  davettir. Köken bildirimleri düz tarihe çevrildi ("28 Temmuz'da ölçüldü").
- ✅ **`COP_TEMIZLIK.md`'nin 7 kırık referansı** temizlendi (`CLAUDE.md`,
  `PLAN.md`, `DURUM.md` ×2, `RPI_ESITLEME.md`, `YAPILACAKLAR.md` ×2).
- 📉 `docs/`: **17 md → 12 md.**

*YKİ laptopu sıfırdan kuruldu — makine **Arch Linux**, Ubuntu değil (Osman)*

- ✅ `deploy/yki/kur_yki.sh` 26. satırda Ubuntu (noble) değilse **bilerek
  duruyor**. İkinci bir kurulum betiği yazılmadı: `ros:jazzy` imajı zaten
  noble olduğu için depo bir konteynere bağlanıp `kur_yki.sh` **içeride,
  değişmeden** koşturuldu. `colcon build` ✓ `node_modules` ✓ `venv` ✓
  `mavros_msgs` ✓. Konteynerden seri porta erişim de doğrulandı (host'un
  `uucp` gid'i 984 `--group-add` ile geçiriliyor).
- ✅ Konteyner dosyaları **`arch-docker/`** altında ve **`.gitignore`'da** —
  kişisel, depoya girmiyor. Neden ve nasıl: `arch-docker/README.md`.
- ✅ `~/.zshrc`'ye alias: **`yki`** (başlatır) ve **`ykidur`** (durdurur).
  `yki` önce `docker start yki` çağırıyor — konteyner `--restart` almadığı
  için makine yeniden başlayınca duruyor. Tamamen durmuş konteynerden tek
  komutla ayağa kalktığı **ölçüldü**: backend 200, arayüz 200, seri port açık.
- ✅ **QGroundControl v5.0.8** (AppImage, `~/QGroundControl-x86_64.AppImage`)
  + uygulama menüsü kısayolu. Makinede iki QGC vardı (bir flatpak v4.4.4 +
  bir AppImage), ikisi de tamamen kaldırılıp tek sürüme indirildi.
- ✅ **Base ESP ölçüldü, iki hattı da sağlam.** CP2102 = log hattı
  (`[MESH] Hazir.`, **MAC `A4:F0:0F:64:B5:34`**), CH340 = veri hattı
  (460800'de COBS+CRC çerçevesi okundu). `yki_baslat.sh`'in beklediği
  `usb-1a86_USB_Serial-if00-port0` yolu mevcut, ayar değişikliği gerekmedi.
- ✅ `drone_bul.sh` **Arch'ta çalışıyor** — `arp`/`nmap` gerektirmiyor
  (`ip neigh` + bash `/dev/tcp` kullanıyor). ⚠️ **mDNS çalışmıyor**
  (`nss-mdns` yok, avahi kapalı); MAC taraması yedeği sorunsuz, engel değil.
- ✅ Osman'ın SSH anahtarı **ylp00'a** kuruldu (`YAPILACAKLAR` P1.2).

*🔴 "RPi bağlanınca laptopun interneti kopuyor" — sebep bulundu (Osman)*

- Semptom **üç kez tekrarlandı ve ölçüldü**: dron ağa girdikten ~10 sn sonra
  ağ geçidine — yani telefonun kendisine, tek wifi atlaması — ping
  **3 → 6 → 9 → 14 sn** diye doğrusal büyüyüp tavana oturuyor; dronun gücü
  kesilince anında 3 ms'ye dönüyor.
- **Ölçümle elenenler** (bir daha araştırılmasın): wifi kopması yok
  (NetworkManager'da tek olay rutin DHCP yenilemesi) · IP/rota/ARP hiç
  değişmedi · hava %0.1-2.8, yeniden gönderim 0-3/s, bit hızı sabit
  72.2 Mbit — **tıkanıklık yok, radyo boştaydı** · sinyal -35…-43 dBm ·
  ARP fırtınası yok (tüm yakalamada 52 istek) · **laptop wifi güç tasarrufu
  değil** — kapatılıp tekrar denendi, birebir aynı koptu.
- **Sebep:** `~/yelpence_ws/gcs_url` = `udp-b://:14555@14550`. `udp-b`
  **yayın** demek. QGC açık değilken MAVROS karşı taraf keşfedemiyor ve
  durmadan `255.255.255.255:14550`'ye yayın yapıyor (14 paket/s, 0.8 KB/s).
  Telefon hotspot'u bu akış altında tüm istemcilere teslimatı **saniyede
  ~1.25 pakete** düşürüyor; tampon ~18 pakette doluyor. Hız sınırı imzası,
  tıkanıklık değil — trafiğin **hacmi değil, yayın olması** sorun.
- **İki yönlü kanıt:** QGC açılıp MAVROS **tekil** gönderime geçince, 20 kat
  daha fazla veriyle (320 paket/s) sorun **anında** bitiyor. Takımın bunu
  daha önce yaşamamasının sebebi de bu: hep QGC açık çalışılmış.
- **Denenen çözüm:** `gcs_url` = `udp://:14555@` — uçak kimseye yayın yapmaz,
  **sadece dinler**; bağlantıyı QGC kurar. Doğrulandı (dron açık + QGC bağlı,
  100 sn): 31779 paket tekil, **0 yayın**; ping 200/200, ağ geçidi ortanca
  **5.2 ms**, 1 sn üstü hiç yok. **Sonra operatör kararıyla GERİ ALINDI** —
  uçak `udp-b`'de bırakıldı (aşağıya bak).

*Yan bulgular*

- ✅ **Pi saat düzeltmesi sahada ilk kez çalışırken görüldü** (`YAPILACAKLAR`
  P1.4). `docker inspect` konteyner başlangıcını 23:53 gösterdi ama komut
  00:57'de çalıştırılmıştı: Pi ~1 saat geriden açılmış, `gps_saat.py` sonra
  düzeltmiş. Ölçüm sonrası Pi saati laptopla saniyesi saniyesine aynı.
- 🔴 **`DURUM.md` origin satırı bir sürüm geriydi** — tam da 15 Ağustos'ta
  olay çıkaran eski değeri gösteriyordu (18.2 m yatay, 0.93 m dikey fark).
  ylp00 `deploy/saha_origin.env` ile **birebir aynı**: uçak doğru, belge
  yanlıştı. Düzeltildi.
- ⛔ *Bu maddedeki "Pi saat düzeltmesi sahada ilk kez çalışırken görüldü"
  sonucu **gündüz çürütüldü** — `gps_saat.log` okunmamıştı, okununca
  düzeltmenin aslında **çalışmadığı** çıktı. Aşağıya bak.*

---

### 🌤 17 Ağustos gündüz — SSH, saat teşhisi, uçaklar `main`'e alındı (Osman)

*İki uçağa da SSH*

- ✅ ylp02'nin **host key**'i `known_hosts`'ta hiç yoktu; `BatchMode` soru
  soramadığı için `--durum` "SSH cevap vermedi" diyordu — **anahtar sorunu
  değil**. ARP'taki MAC (`88:a2:9e:71:60:24`) `cihazlar.md` ile doğrulanıp
  eklendi, sonra `ssh-copy-id` ile Osman'ın anahtarı kuruldu. **P1.2 kapandı**
  (ylp01 dönünce tekrarlanacak).
- ✅ `tgt_system` farkı (ylp02'de `3`, ylp00'da yok) **doğru** —
  `baslat.sh:168` zaten öyle olmasını yazıyor. Ayrışma değil.

*🔴 Uçak saatleri tutmuyordu — kök neden bulundu ve düzeltildi*

- Ölçüm (GPS Pixhawk'tan, dizüstü Cloudflare `Date` başlığıyla doğrulandı):
  **ylp00 7 sa 58 dk, ylp02 10 sa 15 dk geride, aralarında 2 sa 17 dk fark.**
- Sebep, ikisinin de son açılış logunda aynı satır:
  `[gps_saat] GPS zamani 25 sn icinde gelmedi. Saat DEGISMEDI.`
  Zincir: Pi açılışı `01:52:36` → konteyner `01:52:49` → mavros + `sleep 15`
  → `gps_saat --bekle 25` pes ediyor `~01:53:30`. GPS'e güç verildikten sonra
  topu topu **~54 sn** tanınıyor; Here4 soğuk başlangıçta o sürede
  kilitlenmiyor. **Sıcak açılışta çalıştığı için aylarca görülmedi**
  (bir önceki açılışın logunda `fark=+0.151 sn`).
- **Uçuşu bozmuyor** — `consensus_node` bütün tazelik/zaman aşımı hesabını
  `time.monotonic()` ile ve komşunun **yerel alım anına** göre yapıyor
  (`consensus_context.py:29`). Bozduğu şey çapraz uçak kayıt karşılaştırması,
  yani `gps_saat.py`'nin var olma sebebi.
- ✅ **Düzeltildi:** `baslat.sh` → `--bekle 150`. Bedeli yok, betik ilk geçerli
  örneği alınca hemen çıkıyor; 150 sn yalnız gerçekten soğuksa harcanır.
  (`gps_saat.py`'nin kendi varsayılanı zaten 40'tı, `baslat.sh` 25'e kısmıştı.)
- ⚠️ **Hâlâ sınanmadı.** Gün içinde saatler düzeldi ama düzelten **NTP** oldu,
  GPS değil (o sırada Pi'lerin interneti gelmişti). Asıl sınav **internetsiz
  soğuk açılış** — `YAPILACAKLAR` P1.4.

*🔴 P0.7 — uçaklardaki kod bu depodan üretilemiyordu, kapandı*

- İki Pi'nin de `.surum` dosyası: `commit=0dfa0ad +KIRLI`,
  `dal=feature/dagitik-suru`, `dagitan=egUbuntu`. `git cat-file -t 0dfa0ad`
  → **yok**; `git ls-remote --heads origin` → **yalnız `main`**. Yani uçan
  yazılımı okuyabildiğimiz tek yer Pi'lerin SD kartlarıydı ve `dagit.sh`
  `--delete` ile çalıştığı için dağıtım onu geri dönüşsüz silecekti.
- ✅ **Silinmeden önce git'e alındı:** **`saha/pi-kod-15agustos`** (`52ff027`,
  `origin`'de) — uçaklarda gerçekten koşan `src/` ağacının birebir kopyası
  (176 dosya). ylp00'dan alındı, ylp02 ile md5'i aynı çıktı. Çalıştırılabilir
  sürüm değil, **karşılaştırma referansı**.
- Operatörün açıklaması ölçümle doğrulandı: o dal eski depoda `main`'e
  alınmış, oradan yeni bir dal açılmış ve bu depo onunla kurulmuş. `main`
  her dosyada daha uzun; Pi'deki fazlalıklar eski sürüm kalıntısı — en net
  kanıtı `INTERFACE_CONTRACT.md`'de duran sim dönemi "Network Proxy" bölümü.
- ✅ `dagit.sh ylp00 ylp02` → `.surum` = `e012dba (main)`, **`+KIRLI` yok**;
  `src/` 176 dosya `main` ile birebir (md5). Konteynerler yeniden başlatıldı;
  sonrasında ikisinde de 11 düğüm ayakta, setpoint konularında **tek üretici**,
  MAVROS `connected:true` / `armed:false`.

*Dağıtım araçlarında iki tuzak çıktı*

- 🔴 **`dagit.sh` derleme çökse bile "başarılı" diyor.** `swarm_missions`
  **iki uçakta da çöktü**, betik `basarili: 2` yazdı ve `.surum`'u yine de
  güncelledi. Sebep `colcon build ... | tail -15` — boru hattının çıkış kodu
  `tail`'inki, `if ! ssh` hiç tetiklenmiyor. Çıktıyı okumasaydık bir paket
  **eski `install/`** ile kalacaktı ve `.surum` "main" dediği için kimse
  sorgulamayacaktı. → `TUZAKLAR.md` §1.14
- 🔴 Çökmenin sebebi **bayat `build/` dizini**: `gorev1.launch.py` `main`'den
  silinmişti ama `--symlink-install` ile oluşan `build/swarm_missions/` hâlâ
  kaydını tutup kopyalamaya çalışıyordu. `setup.py` glob kullandığı için
  **depoda hata yok**. İkisinde de temizlenip derlendi. → `TUZAKLAR.md` §2.8
- 🟡 `dagitan=$(hostname)` Arch'ta **sessizce boş** kalıyor (`hostname` kurulu
  değil). → `TUZAKLAR.md` §1.15

*🔴 P0.8 — `formation_node` güvenlik kapıları varsayılan kapalıydı, düzeltildi*

- `main` dağıtılınca `declare_parameter('sitl_mode', True)` uçaklara girdi —
  depodaki **tek** `True`. O bayrak iki kapıyı atlatıyor:
  `origin_synced` ve `(xy_valid ve z_valid)`. `baslat.sh` parametreyi
  **hiç geçmiyordu**. 15 Ağustos'a kadar koşan sürümde (bugünkü yedek dalda)
  aynı kapılar **koşulsuzdu** — yani `main` onları zayıflatmıştı.
- ✅ **İki yerden bağlandı:** `formation_node.py` varsayılanı `False`,
  `baslat.sh:707` ayrıca `-p sitl_mode:=false`. Dağıtıldı (`600ca65`) ve
  uçtan uca doğrulandı: repo = Pi `src/` = konteynerdeki `build/` kopyası,
  üçü de md5 `bd40492c`; komut satırında `sitl_mode:=false`; gözlem remap
  yerinde.
- 🔎 Yan bulgu: `--symlink-install`'a rağmen Python kaynağı `build/` altına
  **kopyalanıyor**, sembolik bağ değil → `rsync` tek başına koşan kodu
  değiştirmiyor, `colcon build` şart.

*İnternet — Pi'lerde gerçekten yoktu, gün içinde kendiliğinden düzeldi*

- Sabah ölçüm: **TCP el sıkışması dizüstü kadar hızlı tamamlanıyor
  (0.06–0.24 sn, RTT 102 ms) ama tek bayt veri gelmiyor.** Soket
  istatistiği: `bytes_sent:164 bytes_retrans:123 bytes_acked:1 cwnd:1
  backoff:2`. TLS, UDP DNS, UDP NTP — hepsi zaman aşımı. Aynısı iki Pi'de
  birebir; dizüstü aynı ağda, aynı geçitte kusursuz.
- **Ölçümle elenenler** (bir daha araştırılmasın): Pi ağ yapılandırması
  (IP/rota/geçit/DNS doğru, DHCP'den) · yerel güvenlik duvarı (`iptables`
  ve `nft` **kurulu bile değil**) · yerel proxy · MTU (düşen paket 41 bayt,
  `pmtu:1500`) · araya giren sahte cevaplayıcı (yönlendirilemez adresler ve
  kapalı portlar **doğru şekilde** zaman aşımına düşüyor) · TTL tabanlı
  tethering tespiti (dizüstünün TTL'i de 64 ve çalışıyor) · **MAVLink
  yayını** (tekil dinleyici ile hepsini dinleyen birebir aynı: 324 vs 325
  pkt/s → broadcast **yok**, MAVROS iki uçakta da QGC'yi eş olarak öğrenmiş).
- 11:35'te tekrar ölçüldü: **ikisinde de tam çalışıyor**, DNS çözüyor,
  `NTPSynchronized=yes` (`194.27.222.5`). Pi'nin ağ yapılandırmasında hiçbir
  şey değiştirilmedi → değişen şey **Pi'nin dışında**, telefonda ya da
  operatörde. **Sebep bilinmiyor, uydurulmadı.**
- Tekrarlarsa aranacak parmak izi: *TCP el sıkışması tamam, sıfır veri.*

*Sıradaki aşama belirlendi*

- Belgeler okundu (`PLAN`, `SURU_ENTEGRASYON`, `KARARLAR`, `YAPILACAKLAR`) ve
  uçakta koşan düğümlerle çakıştırıldı: `suru_dugumleri` =
  `origin consensus fsm formasyon`, yani ADIM 0/0.5/1/2/3'ün düğümleri açık
  — **ama hepsi yalnız yerde sınandı.** Merdivende G0 ✅ · G1 ✅ ·
  **G2 ❌ buradayız** · G3 = ADIM 3.
- ✅ `PLAN.md` §10 gerçek duruma getirildi (eskiden hâlâ "Aşama 0" diyordu).

*Gün sonu*

- Plan pil değişimi + dışarıda GPS kilidi + iki yer testiydi;
  **yağmur nedeniyle iptal edildi.** Uçaklara dokunulmadı.

**Ne değişti**

*16 Ağustos + gece*

- kod: yok. O üç oturumda yalnız dosya silme, belge düzeni ve laptop kurulumu.
- laptopta (depo dışı): YKİ konteyneri `yki`, `arch-docker/`, QGC v5.0.8,
  `yki`/`ykidur` alias'ları.
- belge: `README.md`, `CLAUDE.md`, `PLAN.md`, `DURUM.md`, `YAPILACAKLAR.md`,
  `RPI_ESITLEME.md`, `INTERFACE_CONTRACT.md` §3.0, `GUNLUK.md`.
  **YENİ:** `docs/TUZAKLAR.md`. **SİLİNDİ:** `docs/arsiv/` (5 dosya).
  `.gitignore`'a `arch-docker/` eklendi.

*17 Ağustos gündüz*

- kod: `deploy/rpi/baslat.sh` — `gps_saat --bekle` **25 → 150**, ve
  `formation_node` çağrısına **`-p sitl_mode:=false`**.
  `src/swarm_core/.../formation_node.py:189` — `sitl_mode` varsayılanı
  **`True` → `False`**.
- **uçakta (ylp00 VE ylp02, ikisi de):**
  - `~/yelpence_ws/src/` **tamamen yenilendi** — artık repo `main`'i
    (`600ca65`), `.surum` doğru ve **`+KIRLI` değil**. Öncesi eski depodan
    kalma erişilemez bir daldı.
  - `baslat.sh` yeni sürüm (md5 `0dacdf44` → sonra `dagit.sh` ile `600ca65`).
  - `swarm_missions`'ın `build/` + `install/` dizinleri **elle silinip**
    yeniden derlendi (bayat `gorev1.launch.py` kaydı yüzünden).
  - Konteynerler yeniden başlatıldı (11:35 / 11:41, sonra 14:30 civarı).
  - ylp02'ye **Osman'ın SSH anahtarı** eklendi.
  - **Bayraklara dokunulmadı:** `yer_testi`, `gozlem`, `kacinma`, `origin`,
    `suru_dugumleri`, `gcs_url` hepsi bulundukları gibi.
- git: **yeni dal `saha/pi-kod-15agustos`** (`52ff027`, `origin`'de) —
  uçaklarda koşan eski kodun yedeği. Silme, karşılaştırma referansı.
- laptopta: `~/.ssh/known_hosts`'a ylp02'nin host key'i (IP tabanlı —
  IP değişirse `ssh-keygen -R <ip>` gerekir).
- belge: `DURUM.md`, `YAPILACAKLAR.md`, `TUZAKLAR.md`, `RPI_ESITLEME.md`,
  `PLAN.md` §10, `GUNLUK.md`.

**Yarım kalan / tuzak**

- 🔴 **Dronlara güç vermeden ÖNCE QGC açık olsun** — yoksa YKİ laptopunun
  interneti ölür (yukarıdaki teşhis). Sebep düzeltilmedi, **kural olarak
  yaşıyoruz**: MAVROS karşı tarafı bir kez keşfettikten sonra unutmuyor,
  yani QGC'yi sonradan kapatmak sorun çıkarmıyor — **ölçüldü**. Ama her
  `docker restart droneN` MAVROS'u yeniden başlatıp pencereyi tekrar açıyor,
  ve ikinci uçak sonradan açılırsa o yayın yapıyor. Kalıcı çözüm tek satır
  (`gcs_url` = `udp://:14555@`), denendi ve çalıştı, uygulanmadı.
- 🟡 `YAPILACAKLAR` P1.5 (konteyner ağdan önce kalkıyor → QGC bağlantısı ölü
  kalıyor) yukarıdaki tek satırlık değişiklikle **kendiliğinden çözülebilir**:
  `udp://:14555@` ile başlangıçta kurulacak bir karşı taraf yok, dolayısıyla
  `removed stale remote address` de olmaz. Doğrulanmadı.
- 🟡 **Laptopta mDNS kapalı** (`nss-mdns` yok, avahi kapalı) — `ylp00.local`
  çözülmüyor. `drone_bul.sh` MAC taramasıyla buluyor, engel değil.
  İstenirse: `sudo pacman -S nss-mdns avahi` + `nsswitch.conf`'a `mdns_minimal`.
- 🟡 **YKİ konteynerinde `<defunct>` uvicorn birikiyor** — PID 1 `sleep
  infinity` ve çocuklarını toplamıyor; her başlat/durdur çevrimi bir zombi
  bırakıyor. Zararsız. Düzgün çözümü konteyneri `docker run --init` ile
  yaratmak (`arch-docker/README.md`).
- ✅ ~~🔴 `formation_node.py:189` — `sitl_mode` varsayılanı `True`~~ →
  **17 Ağustos gündüz DÜZELTİLDİ** (P0.8), iki yerden bağlandı ve iki uçağa
  dağıtıldı. Kalan tek doğrulama G2 uçuşunda: origin senkronsuzken
  `/gozlem/…/formation/raw` **susmalı**.
- 🟠 **`--bekle 150` daha sınanmadı.** Gün içinde saatleri NTP düzeltti, GPS
  değil. Asıl sınav **internetsiz soğuk açılış**: bir sonraki sıfırdan
  açılışta `gunluk/son/gps_saat.log` **"kaydirildi"** demeli. Demezse sıradaki
  seçenek GPS kilidini beklemek. → `YAPILACAKLAR` P1.4
- 🔴 **`dagit.sh` çıktısını GÖZLE OKU.** Derleme çökse bile `basarili` diyor
  ve `.surum`'u güncelliyor (`TUZAKLAR.md` §1.14). `Summary:` satırında
  `failed` varsa dağıtım tamam **değildir** — o paket eski `install/` ile
  kalır. Kalıcı düzeltme (`PIPESTATUS`) yapılmadı → `YAPILACAKLAR` P0.7 son
  maddesi.
- 🟠 **Pi internetinin neden kesildiği bilinmiyor.** Sabah iki Pi'de de veri
  hiç akmıyordu, 11:35'te kendiliğinden düzeldi; Pi tarafında hiçbir şey
  değişmedi. Tekrarlarsa parmak izi: *TCP el sıkışması tamam, sıfır veri.*
  Ölçüm betiği oturumla birlikte kayboldu, yeniden yazılabilir (~80 satır).
  Kesin deney: dizüstünü hotspottan düşür, Pi'den dene.
- 🔴 **`TUZAKLAR.md` §0 — durumu BİLİNMEYEN üç güvenlik maddesi.** Arşivden
  çıktılar, hiçbir canlı belgede yoklardı, bugünkü halleri bilinmiyor:
  ylp00'ın **clipping ölçüm kuralı** (`titresim_olc.py` repoda duruyor ama
  hiçbir uçuş öncesi listesinde yok), ylp00 **alıcı failsafe'inin kill
  tetiklemesi** (uçuş izninin kapısıydı), **hover gazı %66**.
  Cevaplanınca doğru bölüme taşınacak ya da `YAPILACAKLAR`'a girecek.
- ⚠️ **`px4_bridge.py:528`** — `if sitl_mode or battery_percent <= 0.0:`
  `or`'un ikinci yarısı sahada **aktif** (BAT1_SOURCE kapalı). Temizlik
  yapan biri satırı silerse sahayı bozar.
- 🟡 **21 teşhis betiğinin listesi kayboldu.** `COP_TEMIZLIK.md` §D'deydi,
  belge silinince gitti; hangi betikler olduğu artık hiçbir yerde yazmıyor.
  `YAPILACAKLAR` P2.5 — ilk adım listeyi uçaktan çekmek.
- 🟡 **Kırık referans taraması yapıldı, tamamı temizlenmedi.** `ARCHITECTURE.md`
  (5), `qgc_proxy.py` (3), `INTERFACE_CONTRACT.md`'de iki düğümün yanlış
  pakette gösterilmesi (12), `YELPENCE_RTCM_SPEC.md`'de hiç yazılmamış modül
  adları (5) hâlâ kırık. Kapsam bilerek dar tutuldu.
- 🟡 `sitl_mode` hâlâ 58 yerde, 20 dosyada. G2 öncesi dokunulmadı.
- 🟡 2 stil hatası (`formation_node.py:5` ölü `import time`;
  `swarm_state_machine` import sırası). CI'da atlanıyor.
- 🟡 Eyüp'ün dalına merge commit gitti — **`git pull` yapmadan push edemez.**
- ℹ️ Arşiv silindi ve **depoda ona giden hiçbir işaretçi bırakılmadı** —
  bilinçli karar. Ham günlükler git geçmişinde duruyor.

**Sıradaki adım**

**G2 — havada gözlem uçuşu.** `PLAN.md` §10 bu tabloyla güncellendi.
Aşama 1'in **uçuş yarısı**; yer yarısı 15 Ağustos'ta geçti. Uçaklarda
ADIM 0/0.5/1/2/3'ün düğümleri açık ama hepsi yalnız yerde sınandı
(G0 ✅ · G1 ✅ · **G2 ❌** · G3 = ADIM 3).

**Uçmadan önce iki iş — ikisi de yerde, uçuş yok, ~10'ar dakika:**

1. **Devir teslim testi** (ADIM 1'in kalanı, operatör bununla başlamak
   istiyor): iki uçak yerde **pervanesiz**, ARM'lı; birini kill'le,
   **diğerini armlı bırak** — ikincisi liderliği devralıyor mu?
   15 Ağustos'ta ylp02 ikinci turu göremeden o da kill'lenmişti.
   *Artık iki uçağın saati aynı, yani çapraz uçak log karşılaştırması
   bu testte ilk kez gerçekten çalışacak.*
2. **`TUZAKLAR.md` §0** — üç bilinmeyenden ikisi doğrudan uçuş izni kapısı:
   ylp00 clipping kuralı (`titresim_olc.py`, ~10 dk) ve alıcı failsafe'i
   (kumanda kapalıyken CH5=2000 → **kill**).

Aynı uçuşa **P0.4 navigasyon kayması ölçümü** binebilir (≥40 m düz bacak,
2 ve 4 m/s) — komut yolunda hiçbir şey değiştirmiyor. ADIM 3'e geçerken
`KARARLAR.md` **KARAR-02** gereği `ultracode` istenecek.

⚠️ **Güç verirken: önce QGC'yi aç** (aşağıdaki kural hâlâ geçerli).

**Uçakların bırakıldığı hâl**

Bugün **ikisi de açık ve ayakta**, ikisi de aynı yapılandırmada:

- **ylp00 ve ylp02** — konteynerler ayakta, `.surum` = **`600ca65` / `main`**
  (`+KIRLI` yok), `src/` repo ile birebir, 11 düğüm koşuyor, setpoint
  konularında **tek üretici**, MAVROS bağlı ve **disarm**, saatler doğru
  (`NTPSynchronized=yes`). Disk ~%41-42.
- Bayraklar (ikisinde de, **değiştirilmedi**): `yer_testi` VAR (ARM olur,
  **KALKMAZ**) · `gozlem` VAR (formasyon çıktısı uçağa **ulaşmıyor**) ·
  `kacinma` VAR · `suru_dugumleri` = `origin consensus fsm formasyon` ·
  `origin` = `38.6904758 39.1610188 1216.96` (repo ile aynı) ·
  `gcs_url` = `udp-b://:14555@14550` (**yayın** — QGC açık değilse laptopun
  interneti ölebilir). ylp02'de ayrıca `tgt_system` = `3` (doğru, uçağa özgü).
- Kalıcı elle değişiklikler: Osman'ın SSH anahtarı **ikisinde de** ·
  `swarm_missions` `build/`+`install/` elle temizlenip derlendi.
- **ylp01:** yerde (2 Ağustos'ta düştü), değişiklik yok. Dönünce
  `RPI_ESITLEME.md` §8'deki üç kaydı da yürüt.


## 2026-08-15 17:19 — Eyüp + Claude (ikinci yarı: ADIM 2 + ADIM 3)

**Ne yapıldı**

- ✅ **ADIM 2 açıldı ve kararlı.** `swarm_fsm` iki uçakta koşuyor:
  ```
  SwarmFsmNode baslatildi: kimlik araligi 1..3, beklenen ucak 2
  swarm_state: 1 (IDLE)   active_agent_count: 2   ← IKI UCAGI DA GORUYOR
  60 sn gozlem: FAILSAFE 0 · QoS uyusmazligi 0 · durum degisimi 1
  ```
- ✅ **`ic_dis_kopru` yazıldı — internal/public köprüsü kalıcı çözüldü.**
  12 konu taşıyor. `drone{N}/status` **bilerek hariç** (uçak kendini komşu
  sanıp kendinden kaçardı). Doğrulandı: `state=1027` (5 Hz, kesintisiz),
  `/swarm/public/state` yayıncı sayısı 0 → 1. Origin'in geçici remap'i
  kaldırıldı; origin artık hem yerel düğümlere hem mesh'e gidiyor.
- ✅ **ADIM 3: G0 + G1 geçti.** `formation_node` + `path_planner` gözlem
  modunda açıldı, gerçek telemetriyle gerçek setpoint üretti:
  ```
  vx: 2.048  vy: 1.589  vz: 1.510   position_valid: false
  ```
  **`vz = 1.51 m/s` — uçak YERDE.** Gerçek olsaydı tırmanma komutuydu.
  Gözlem modunun neden zorunlu olduğu tek ölçümle görüldü.

**Ne değişti**

- kod:
  - `swarm_control/ic_dis_kopru.py` **yeni**
  - `swarm_fsm_node.py`: `agent_count` ikiye ayrıldı · `FormationCommand`
    aboneliği + sıfır ortalamalı ofsetler · kaynak başına election seq ·
    `agent_id` ile kendi durumunu okuma
  - `esp32_bridge_node.py`: `healthy` türetimi (sabahki)
  - **QoS sınıf hatası: 5 abonelik** `_RELIABLE_QOS` → `_BEST_EFFORT_QOS`
    (`formation_node`, `collision_avoidance`, `maneuver_executor`,
    `mission1_node`, `mission_fsm_node`)
  - `baslat.sh`: `fsm` → `fsm`/`gorevfsm`/`mod` · `formasyon` → `formasyon`/`ca`
    · gözlem modu · `/gozlem/` kayda eklendi · `ic_dis_kopru` en önce
- **uçakta (SONRAKİ KİŞİ ÖYLE BULACAK):**
  ```
  bayraklar : gcs_url gozlem kacinma origin suru_dugumleri yer_testi
              (ylp02'de ayrica tgt_system)
  dugumler  : origin consensus fsm formasyon
  origin    : 38.6905999 39.1611543 1216.03
  surum     : 18679dc
  ```
  Koşan sürü düğümleri: `ic_dis_kopru · swarm_origin_publisher ·
  consensus_node · swarm_fsm_node · formation_node · path_planner`
  (+ eski beşli). `collision_avoidance` **kapalı** — `basit_kacinma` açık.

**Yarım kalan / tuzak**

- 🔴 **`yer_testi` ve `gozlem` bayrakları AÇIK.** Uçuştan önce ikisi de
  silinmeli + `docker restart`. `gozlem` açıkken `formation_node`'un
  setpoint'i uçağa **ulaşmıyor**; `yer_testi` açıkken uçak arm olur ama
  **kalkmaz**.
- 🔴 **`formation_node` slot ofseti çözemiyor:** *"slot ofseti yok
  (yerel/komut); setpoint atlandı"*. Sebep `rel_enable` kapalı → komşu
  konumları yok → dağıtık atama yapılamıyor. Komuta gömülü ofset verilince
  çalışıyor (G1 böyle geçti). **Sıradaki iş bu bayrağı ikiye ayırmak.**
- 🟠 `formation_node` **saf hız kipinde** (`position_valid: false`).
  G3'e (komuta) geçmeden `px4_bridge velocity_only` ile birlikte
  karara bağlanmalı — bkz. `NAVIGASYON_KAYMA.md`.
- 🟡 `formation_stable: true` şu an **boş bir doğruluk** — uçaklar
  `FORMATION_ACTIVE_STATES` dışında olduğu için kalite hesabı boş kümede
  çalışıp 0.0 hata döndürüyor. "Hiç ajan yoksa formasyon mükemmel"
  davranışı ileride tuzak olabilir.

**Akşam eklenenler (17:19 → 20:15)**

- ✅ **YKİ ilk kez açıldı.** Base ESP mesh'te (`agent_id=10`), backend
  drone 1 ve 3'ü bağlı görüyor. Açar açmaz bir QoS hatası daha çıkardı:
  backend `qr_data`'yı **kasıtlı** RELIABLE dinliyordu (*"QR mesajı en az
  1 kez görünmeli, −20 ceza"*) — niyet doğru, etki tam tersi; BEST_EFFORT
  yayıncıdan **hiçbir şey** almıyordu. Sınıf hatası 6'ya çıktı.
- ✅ **Origin tek kaynağa bağlandı** — `deploy/saha_origin.env`.
  Bugün ben uçaklara ayrı bir origin koymuştum; YKİ'ninkiyle **18.2 m**
  farklıydı ve ikisi birlikte çalışsa `origin_synced` düşüp arm'ı
  engelleyecekti. Artık `yki_baslat.sh` ve `dagit.sh` aynı dosyadan besleniyor.
- ✅ **ADIM 3 dağıtık atama sahada doğrulandı:**
  ```
  dagitik atama: yerel hesap lider ile UYUSTU -> yerel kullaniliyor
  TAM ATAMA: a1->(+0.0,+0.0)  a3->(+0.0,+12.0)
  ```
  `rel_enable` ikiye ayrıldı, komşu konumu mesh `AgentStatus`'tan geliyor.
  Öncesinde yerel hesap hiç çalışmıyordu → düğüm lideri kopyalıyordu →
  fiilen **merkezi**. Şartname merkezi olanı eksik puan sayıyor.

**Sıradaki adım**

ADIM 3 **G2** — havada gözlem. `formation_node` uçarken arka planda koşar,
çıktısı `/gozlem/`'e gider, kanıtlanmış zincir uçurur. Öncesinde karara
bağlanacak: `position_valid: false` (saf hız kipi) + `px4_bridge
velocity_only` — bkz. `NAVIGASYON_KAYMA.md`.

> ⚠️ **KARAR-02:** G2'den önce operatöre çok ajanlı denetim önerilecek.

> ⚠️ **KARAR-02:** ADIM 3'ü **havaya** çıkarmadan önce operatöre çok ajanlı
> denetim önerilecek — mesaja `ultracode` yazması istenecek.

**Uçakların bırakıldığı hâl**

- ylp00: IDLE, disarm, kill switch serbest, kumanda HOLD, atölyede
- ylp02: aynı

---

## 2026-08-15 16:10 — Eyüp + Claude

**Ne yapıldı**

- 🎉 **ADIM 1 GEÇTİ — sürü kodlarının ilk düğümü sahada çalıştı.**
  İki uçak pervanesiz, ARM'lı, yerde: ikisi de **aynı lideri** seçti.
  ```
  ylp00: [CONSENSUS] Lider: 0 -> 1 (round=1, ben=1)
  ylp02: [CONSENSUS] Lider: 0 -> 1 (round=1, ben=3)     101 ms arayla
  ylp00: esp32_bridge  lider 0 -> 1 (BEN)  ← formasyon kapisi ACIK
  ```
- **Lider arıza devri gözlendi (planlanmamıştı):** kill switch ylp00'ı
  FAILSAFE'e düşürdükten **82 ms sonra** kendi consensus'u
  `Lider: 1 -> 3 (round=2)` dedi. `REASON_LEADER_FAULT` çalışıyor.
- **ylp02 QGC'ye gelmiyordu, çözüldü.** Sahaya götürülüp WiFi kopunca
  Pi tuştan yeniden başlatıldı; konteyner ağdan önce kalktı ve MAVROS'un
  `gcs_url` ucu kurulamadı. `docker restart` düzeltti.
  **Ölçülüp elenen suçlular:** seri çerçeveleme @921600 (67 ardışık geçerli
  çerçeve), FCU `sysid=3 compid=1`, sıcaklık 54.3 °C / throttle `0x0`,
  UDP tekil **ve** yayın. Hiçbiri arızalı değildi.
- Sabah: `agent_fsm` preflight eşiği, GPS'ten saat düzeltme,
  `/ws/suru_dugumleri` dosya anahtarı, `dagit.sh` IP tablosu, `run_drone.sh`
  dağıtımı, konteynerlere `--cap-add SYS_TIME`.

**Ne değişti**

- kod: `preflight_checker.py` (eşik bağlamdan) · `agent_fsm_node.py`
  (`yer_testi` bayrağı + ARMING reddi artık loglanıyor) ·
  `esp32_bridge_node.py` (`healthy` türetiliyor) · `baslat.sh`
  (origin düğümü, consensus parametreleri, dosyadan düğüm açma, GPS saat) ·
  `dagit.sh` · `run_drone.sh` · yeni `deploy/rpi/gps_saat.py`
- **uçakta (SONRAKİ KİŞİ ÖYLE BULACAK):**
  - `~/yelpence_ws/yer_testi` — **AÇIK** ⚠️
  - `~/yelpence_ws/suru_dugumleri` = `origin consensus`
  - `~/yelpence_ws/origin` = `38.6905999 39.1611543 1216.03`
  - konteynerler **yeniden yaratıldı** (`--cap-add SYS_TIME`)
- belge: `SURU_ENTEGRASYON` (sıra düzeltildi), `DURUM`, `YAPILACAKLAR`,
  `KARARLAR` (KARAR-02, KARAR-03), `cihazlar.md`, `RPI_ESITLEME`

**Yarım kalan / tuzak**

- 🔴 **`yer_testi` iki uçakta da AÇIK.** Bu haldeyken uçak arm olur ama
  **kalkmaz**. Uçuştan önce `rm ~/yelpence_ws/yer_testi` + `docker restart`.
- **Yazılım disarm'ı OFFBOARD'dayken reddediliyor** (`result=1`).
  Sebep ölçüldü: pervanesiz OFFBOARD'da PX4 irtifayı tutmaya çalışıp
  integrali sarıyor, gaz tırmanıyor, PX4 kendini "yerde" saymıyor.
  **Yer testinden çıkış: kumandadan kill switch.** Ayrıca armlı bekleme
  süresini kısa tut — 140 sn bekletildi, gereksizdi.
- **İki uçaklı tam devir teslim testi yapılmadı** — birini kill'leyip
  diğerini armlı bırakmak gerekiyor.
- Origin şu an `/public`'e **remap** ile gidiyor; mesh yolu denenmedi.
- `mesh healthy` **türetim**, gönderenin kendi değeri değil. Pil izleme
  açılınca (KARAR-03) pil düşüşü buraya yansımaz.

**Sıradaki adım**

ADIM 2 — `swarm_fsm_node`. Ama önce P0.6a'daki iki düzeltme:
sabit formasyon ofsetleri ve tek global election seq sayacı. **`agent_count`
için "2 yap" notuna uymadan önce kodu oku** — consensus'ta aynı not
yanlıştı ve uygulansaydı ylp02 sürüden düşerdi.

**Uçakların bırakıldığı hâl**

- ylp00: IDLE, disarm, kill switch serbest, kumanda HOLD, atölyede
- ylp02: aynı — bugün sahaya çıkıp döndü, QGC bağlantısı çalışıyor

---

## 2026-08-14 20:15 — Eyüp + Claude

**Ne yapıldı**
- Takım çalışma sistemi kuruldu: `CLAUDE.md`, `docs/DURUM.md`,
  `docs/GUNLUK.md`, `docs/YAPILACAKLAR.md`, `docs/SURU_ENTEGRASYON.md`,
  `docs/COP_TEMIZLIK.md`, `ss/` klasörü.
- **ylp00 ve ylp02 SSH ile denetlendi.** Sonuç: kod drift'i **yok**.
  `baslat.sh` md5 `c99462c3...` repo = her iki uçak, birebir aynı.
  Python kaynakları 131/131 ve 132/132 dosya repo ile aynı.
- Sahada koşan düğümler `ps` ile doğrulandı: **mavros, px4_bridge,
  agent_fsm_node, esp32_bridge, basit_kacinma** — beş düğüm.
  14 sürü düğümünün hiçbiri açık değil.
- **Kritik bulgu:** `basit_kacinma` ve `collision_avoidance` **birebir aynı
  topic yuvasını** kullanıyor (`/control/setpoint/raw` → `/control/setpoint`).
  Aynı anda açılırlarsa px4_bridge iki farklı algoritmadan çelişkili setpoint
  alır. Aynı çakışma `esp32_bridge` ile `formation_node` arasında da var.
  Sürü entegrasyonunun tamamı bu çakışmayı çözmek üzerine kuruldu.
- Ağ değişmiş: `10.158.16.x` → `10.188.209.x`. Son oktetler sabit kaldı
  (134 / 189 / 115) — hotspot MAC'e göre adres veriyor.
- `~/yelpence_ws/.surum` dosyasının **eskimiş** olduğu görüldü; senkron
  kontrolünde ona güvenilmemeli.

**Ne değişti**
- kod: değişmedi
- uçakta: **hiçbir şey değiştirilmedi** — yalnız okundu
- belge: yukarıdaki altı dosya yeni; `.gitignore`'a `ss/` ve üretilen
  harita HTML'leri eklendi

- **`deploy/yki/drone_bul.sh` yazıldı ve test edildi.** MAC'ten IP bulup SSH
  bağlıyor. Dört kip de doğrulandı: `--liste`, `--ip`, komut kipi, `--durum`;
  ayrıca mDNS devre dışı bırakılıp MAC tarama yolu ayrıca test edildi.
  **mDNS bu hotspot'ta çalışıyor** (`ylp00.local` çözüldü).
- **🔴 `--durum` ilk çalıştırmada kritik arıza yakaladı: İKİ DRONE'DA DA DİSK
  %100 DOLU.** Sebep `mavros.log` — ylp00'da 18.64 GB, ylp02'de 21.57 GB
  (29 GB disk). Uçuş kayıtları suçlu değil (`kayit/` 4.6 / 3.0 GB).
  ylp02'de şu anki açılışın logu 1 saatte 1.56 GB. **`ros2 bag` yazamaz →
  bir sonraki uçuş kaydedilmez.**
- Parola girişinin **açık** olduğu doğrulandı (sshd varsayılanı, override yok)
  → arkadaşlar kendi anahtarlarını kendileri kurabilir.
- Her iki Pi'de **tek kayıtlı Wi-Fi ağı** (`rpissid`) ve `authorized_keys`'te
  **tek satır** olduğu görüldü.

- **Disk sorunu ÇÖZÜLDÜ.** Loglar temizlendi (konteyner içinden root olarak —
  dizinler `root` sahipli, SSH kullanıcısı silemiyor). `baslat.sh`'e günlük
  bekçisi eklendi: 60 sn'de bir tarar, 100 MB'ı aşanın **son 25 MB'ını**
  korur, kırpmayı `bekci.log`'a zaman damgasıyla yazar. 21 yönlendirme
  `>` → `>>` çevrildi (O_APPEND olmadan kırpma seyrek dosya üretiyor —
  mekanizma yerelde test edildi: 10.7 MB → 100 KB, sonraki yazma yeni sona gitti).
  Açılış dizini 10 → 5. İki drone'a dağıtıldı, md5 `51d97b3e...` üçünde de aynı.
  **Sonuç: ylp00 19 GB boş (%34), ylp02 21 GB boş (%27).**
- **`docs/RPI_ESITLEME.md` oluşturuldu** — Pi'lerde yapılan her değişikliğin
  hangi uçakta olduğunu tutan defter. Geri gelen drone'u hizaya getirmek için.
- **PX4 parametre okuma ÇÖZÜLDÜ.** Önce "okunamıyor" sandım — yanlıştı.
  Gerçek sebep: `/drone_N/mavros/param/get` diye bir servis **yok**;
  MAVROS 2 parametreleri **yerel ROS 2 parametresi** olarak sunuyor.
  Doğrusu `ros2 param get /drone_N/mavros/param <AD>` — ama her çağrı yeni
  düğüm açıp DDS keşfi yaptığı ve düğümde 1007 parametre olduğu için
  ard arda çağrıların yarısı zaman aşımına düşüyor (4 istekten 2'si).
  **Çözüm:** tek düğüm + toplu `get_parameters` isteği.
  Araçlar: `src/gcs/px4_param.py` (drone üzerinde koşar) ve
  `deploy/yki/param_karsilastir.py` (uçakları yan yana koyar).
  `drone_bul.sh`'e `--tablo` kipi eklendi ki drone listesi tek kaynaktan gelsin.
- **🔴 Araç ilk çalıştırmada gerçek ayrışma buldu:**
  `MPC_TILTMAX_AIR` ylp00=**45** / ylp02=30, `MPC_YAWRAUTO_MAX` ylp00=**45** /
  ylp02=25. Diğer 10 uçuş parametresi eşit, `MAV_SYS_ID` doğru şekilde farklı.
  **Tehlikeli olan:** `gorev_kanit_ucus.py:1980`'deki `MAKS_EGIM_DEG = 35.0`
  gerekçesi "`MPC_TILTMAX_AIR=30`" — ylp00 45°'ye eğilebildiği için normal
  uçuşta bunu geçip görevi boş yere iptal ettirebilir. Kimse bilmiyordu.
- **`YAPILACAKLAR.md` öncelik şemasıyla yeniden yazıldı** (🔴P0 / 🟠P1 / 🟡P2 / ⚪P3).
- **`src/gcs/ucus_ayarlari.py` kuruldu — hız/ivme/aralık/açı tek kaynak.**
  Açılar artık elle yazılmıyor, ivmeden türetiliyor (`a = g·tan θ`) ve
  dedektör eşiği tavandan. `gorev_kanit_ucus.py`'deki 7 sabit oradan okuyor
  (`ARALIK_M`, `KANAT_ACISI_DEG`, `TOLERANS_M`, `MIN_AYRIM_M`,
  `GOREV_HIZ_MPS`, `GOREV_DIKEY_HIZ_MPS`, `MAKS_EGIM_DEG`).
  Kipler: çözümleme · `--px4` · `--kabuk`.
- **Yeni yapılandırma:** seyir 2.0 → **3.0 m/s**, aralık 10 → **12 m**,
  PX4 tavanı 4.0 → **5.0**, eğim tavanı **30°**, dedektör **35°**.
  Kuru testle doğrulandı: kritik ayrım 7.07 → **8.41 m**, eşiğe pay
  3.07 → **4.41 m**, `SONUÇ: GEÇTİ`.
- **Bir ayrışma daha:** `MPC_VEL_MANUAL` ylp00=**4**, ylp02=**2** —
  kumandayla POSCTL hızı. Aynı çubuk hareketi iki uçakta farklı hız
  üretiyor; operatörün kas hafızası biri için yanlış.
- **5 m/s incelendi.** İlk analizim yanlıştı (frenleme mesafesini ayrım
  payına ekleyip 17 m aralık çıkardım — gerçek izleme gecikmesinin yedi
  katı). Düzeltildi: model artık izleme gecikmesine dayanıyor ve **12 m
  aralık 6 m/s'e kadar yetiyor.** 5 m/s'in tek gerçek şartı hız tavanının
  7.5'e çıkarılması (doygunluk payı).

- **Navigasyon kayması incelendi** (`docs/NAVIGASYON_KAYMA.md` yazıldı).
  Sonuç: sistem doğru yerde — `px4_bridge` yürütücüsü PX4'e hız
  ileri-beslemesi veriyor, yani `v = Kp·hata + v_ff` ve `v_ff = v` olduğu
  için **kalıcı kayma teorik olarak 0 ve hızla büyümüyor.**
  Kalan kayma yalnız hızlanma fazında.
- **İvme ileri-beslemesi kanalı var ama kapalı:** `AgentSetpoint`'te
  `ax/ay/az` + `acceleration_valid` alanları mevcut, ama `px4_bridge` hiç
  dokunmuyor ve `mavros_command_sender`'ın **dört type_mask'ında da**
  `IGNORE_AFX|AFY|AFZ` var. Açılırsa geçici rejimdeki kayma da kalkar.
- **`formation_node`'un SVT'si Durum 1** — saf oransal (`v = −0.8 × hata`),
  ileri-besleme yok. Kalıcı kayma `v/0.8`, PX4'ün 0.95'inden bile kötü.
  Bu, "formation_node'u konum kipine al" önerisini kayma açısından da
  destekliyor.
- **Doygunluk payı denetimi eklendi:** `tavan ≥ seyir × 1.5` artık **hata**.
  Seyir tavanla eşitse konum düzeltmesine yer kalmaz, PX4 kırpar ve kayma
  geri gelir. 5 m/s denendiğinde config "tavanı 7.5 yap" diyor.

- **Uçuş ayarları uçaklara UYGULANDI ve canlıda doğrulandı.**
  `baslat.sh` artık `/ws/ucus_ayarlari.env` okuyor; env dosyası dağıtıldı.
  PX4 parametreleri `px4_param.py --yaz` ile eşitlendi (tek düğüm/tek istek —
  `ros2 param set` 5 istekten 3'ünde zaman aşımına düşüyordu).
  Konteynerler yeniden başlatıldı, açılış çıktısı doğrulandı:
  `guided_hiz_yatay_mps:=3.0`,
  `[baslat] gunluk bekcisi: dosya 500 MB (son 125 MB korunur), dizin 3000 MB`,
  `[baslat] ucus ayarlari dosyadan: yatay=3.0`.
  `param_karsilastir.py` → **"Uçaklar arası ayrışma yok (16 parametre)"**.
- **`px4_param.py`'ye `--yaz` kipi eklendi** — toplu `set_parameters`.
- **Günlük bekçisi büyütüldü ve ikinci kapı eklendi.** 100/25 → **500/125**
  (normal log KB mertebesinde, tavan yalnız patlamada devreye giriyor;
  korunan oranı %25'te kalınca I/O yükü aynı ama beş kat geçmiş). Ayrıca
  **dizin geneli 3 GB tavanı** — sürü düğümleri açılınca 14 log olacak ve
  dosya başına tavan tek başına 35 GB'a izin verirdi. Dizin silme mantığı
  yerelde sahte açılış dizinleriyle test edildi (1201 MB → 401 MB, en yeni
  iki açılış ve `son` bağı korundu).
- **Kök dizin toparlandı:** PDF'ler `docs/sartname/`'ye, görseller `ss/`'ye.

- **CANLI PARAMETRE eklendi (`px4_bridge`).** Yürütücü ayarları artık uçak
  havadayken değiştirilebiliyor — yeniden başlatma gerekmiyor.
  Canlı olanlar: `guided_hiz_yatay_mps`, `guided_hiz_dikey_mps`,
  `guided_ivme_yatay_mps2`, `guided_ivme_dikey_mps2`, `guided_tasma_m`,
  `guided_konum_kp`, `guided_telafi_orani`.
  Kimlik (`agent_id`), kill/arm kanalları ve kalkış kilidi **bilerek dışarıda**.
  Doğrulama: sınır dışı değer (99) reddedildi, listede olmayan (`agent_id`)
  reddedildi, geçerli değişiklik `CANLI PARAMETRE: guided_hiz_yatay_mps
  3.0 -> 4.0` diye loglandı. İkisinde de 3.0'a geri alındı.
- **🪤 Bulunan tuzak (eski davranış):** `ros2 param set` "Set parameter
  successful" diyordu, `ros2 param get` yeni değeri gösteriyordu, **ama uçak
  eski hızda uçuyordu** — değerler `__init__`'te bir kez okunup örnek
  değişkenine yazılıyordu. Komut başarılı, gösterge doğru, davranış yanlış.
- **🪤 Uygularken düştüğüm tuzak:** geri çağrı `declare_parameter`'da **da**
  tetikleniyor. Geri çağrıyı `__init__` ortasında kaydedince, sonrasında
  `_setup_rtk()`'in tanımladığı `rtk_makul_payload` beyaz listede olmadığı
  için reddedildi ve **düğüm açılışta çöktü**
  (`InvalidParameterValueException`). Çözüm: `_parametre_kurulumu_bitti`
  bayrağı, `__init__`'in sonunda açılıyor — ileride biri yeni bir
  `declare_parameter` eklerse de kırılmaz.

**Yarım kalan / tuzak**
- ~~Konteynerler yeniden başlatılmadı~~ — bekçi bir sonraki açılışta devreye
  girer. Disk boş olduğu için acele yoktu, ama çalıştığı doğrulanmalı.
- **Bekçi belirtiyi kesiyor, kök nedeni değil.** WiFi düşünce MAVROS
  `gcs_url` uçnoktasına her mesaj için uyarı basmaya devam edecek.
- **Arkadaşların SSID + şifreleri Pi'lere eklenmedi** — Eyüp getirecek.
  Bu olmadan hiç kimse bağlanamaz.
- **`yelpence00`/`yelpence02` parolaları biliniyor mu?** Bilinmiyorsa
  anahtarlar erişim varken ŞİMDİ kurulmalı.
- **Repo hâlâ commit'siz.**

- **⚠️ `IZLEME_GECIKME_S = 0.22` DOĞRULANMAMIŞ.** Tek ölçümden türetildi ve
  o ölçüm 7 m'lik bir bacakta, yani geçici rejimde alındı. Teori kalıcı
  kaymanın ≈0 olduğunu söylüyor; sabit ölçüm yapılana kadar güvenli tarafta
  duruyor (ayrım payını gereğinden geniş tutuyor). Config'de işaretlendi.
  **40 m'lik bacakta ölçüm yapılmalı** — `NAVIGASYON_KAYMA.md` Adım 1.
- **🔴 `MPC_TILTMAX_AIR` / `MPC_YAWRAUTO_MAX` ayrışması KARARA BAĞLI.**
  Hangisi referans olacak (ylp02'nin 30/25 değerleri PX4 varsayılanı ve kodun
  varsaydığı değerler)? Eşitlenmeden ya da `MAKS_EGIM_DEG` düzeltilmeden
  uçulmamalı — `YAPILACAKLAR.md` P0.1/P0.2.

**Sıradaki adım**
- P0'ları kapat (parametre ayrışması), sonra SSID'ler (P1.1), sonra commit (P1.3).

**Uçakların bırakıldığı hâl**
- ylp00: ağda, konteyner `drone1` ayakta (3 saattir), `/ws/kacinma` var
- ylp02: ağda, konteyner `drone3` ayakta (3 saattir), `/ws/kacinma` var
- Son bilinen durumda **iki uçakta da kill switch AÇIK** idi (2 Ağu kuru testi)

---

## 2026-08-02 — Eyüp (kanıt uçuşu, geriye dönük yazıldı)

> Bu kayıt sonradan, sohbet özetinden derlendi. Ayrıntı:
> `docs/arsiv/31temmuz-1agustos.md` ve `docs/arsiv/BEKLEYEN_ISLER.md`.

**Ne yapıldı**
- **Uçuş kanıtı videosu çekildi ve geçildi.**
- ylp01 (drone 2) 20 m'den düştü. Kaza analizi: yalnız motorlar durdu, FC
  düşerken bile yayın yapıyordu → ESC güç/sinyal hattı, yazılım değil.
- Üç ciddi arıza kapatıldı:
  1. **Devrilme** — d1'de eski `esp32_bridge_node.py`/`basit_kacinma_node.py`
     vardı; bayat setpoint yerdeyken yatay konum kontrolü tetikliyordu.
     Ayrıca yatay kilit yalnız takeoff sonrası devredeydi, ölçülen 6.2 sn'lik
     arm→takeoff penceresi korumasızdı.
  2. **"Kalktılar, alçaldılar, asılı kaldılar"** — `takeoff` yere göreli,
     `goto` mutlaktı. Zemin NED −1.4'te olunca uçak 1.4 m alçalıyor, hata
     `TOLERANS_M`'i aşıyor ve adım 70 sn zaman aşımına kadar dönmüyordu.
  3. **d1 hiç ayarlanmamış** — `MPC_XY_VEL_MAX` 12.0 iken d3'te 4.0.
- Uçuş kaydı sertleştirildi (üç tampon katmanı kapatıldı).
- FSM pil failsafe'i kapatıldı (regülatörden besleme).

**Uçakların bırakıldığı hâl**
- ylp00, ylp02: uçar; ylp01: yerde
