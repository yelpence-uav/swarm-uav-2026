# DURUM — şu an ne çalışıyor, ne bozuk

**Son güncelleme:** 28 Ağustos 2026, 11:45 — kamera sahada çalışıyor, QR **6-9 m KISITI**; 🔴 ylp02 güç soketi UÇUŞ ENGELİ; 🔴 HOME kayması hâlâ açık


> ## 📷 28 AĞUSTOS 11:20 — KAMERA SAHADA ÇALIŞIYOR, QR OKUNUYOR
>
> **Dört uçuş yapıldı (ylp02, elle/RC).** Kamera kuruldu, kalibre edildi,
> QR tespiti sıfırdan çalışır hâle geldi. Ayrıntı: **`docs/KAMERA.md`**.
>
> - ✅ **QR okunuyor: 5-11 m'de karelerin %38-69'u, tepe 7-8 m'de %69.**
>   Saha kuralı: **QR gerekiyorsa 6-9 m'de uç.**
> - 🔒 **QR BÜYÜTÜLEMEZ** — boyutu (1,5 m, 74 modül) yarışma tarafından
>   sabit, çözünürlük de tükendi (4K en yükseği). Yani **6-9 m bir tercih
>   değil KISIT**; görev planı QR'ın üstünden bu irtifada geçmek zorunda.
>   Tavanı açacak tek eksen titreşim: teorik tavan 34 m, gerçek 11 m.
> - 🔴 **ASIL BULGU: rolling shutter jölesi.** Motor titreşimi kare içinde
>   satır kaymasına yol açıyor, QR modül ızgarası bozuluyordu. Yalıtımsız
>   4K'da **200 karede sıfır** okuma vardı. Operatör yalıtım ekledi →
>   3-4 kat kazanç.
> - ⚠️ **KARE HIZI JÖLEYİ DEĞİŞTİRMEZ** — sürücü fps'i VBLANK ile ayarlar,
>   satır okuma süresi sabit. 10→30 fps denendi, hiçbir faydası olmadı.
>   Okuma süresini **kip** değiştirir (2028x1520 = yarı okuma).
> - ⚠️ **Tavanı belirleyen şey çözünürlük değil, kalan titreşim.** 11-15
>   m'de px/modül 5-6 (taban 2,25) ve QR'ın %67-78'i BULUNUYOR ama veri
>   okunamıyor.
>
> **Uçakta değişen ayarlar (ylp02) — sonraki kişi böyle bulacak:**
>
> | ayar | değer | neden |
> |---|---|---|
> | Kip | `tamfov` 2028x1520 varsayılan; **uçuşta 4K seçildi** | jöle |
> | Pozlama | `sport` (otomatik, kısa) | sabit 1/250 kareyi DOYURUYORDU (%37-45 kırpık) |
> | Beyaz dengesi | sabit `[2.5923, 1.2225]` | AWB %25 kayıktı (magenta) |
> | Kare hızı | 30 | jöleye faydası yok, sadece daha çok deneme |
> | Yayın (tarayıcı) | 640 px | 1920'de küçültme 3,46 çekirdek yiyordu |
>
> - 🔴 **UÇUŞTA TARAYICI SEKMESİNİ KAPAT.** Açıkken toplam CPU %90,7,
>   yük 8,11 ve **mavros %74'te CPU için yarışıyor**. Kapalıyken %67,5.
>   Kayıt sunucu tarafında sürer, sekme kapanınca kesilmez.
> - 🆕 **PIL Pi'ye sudo'suz kuruldu** (`~/yelpence_ws/pylib`) — tarayıcı
>   küçültmesi için. `docs/RPI_ESITLEME.md`'de, ylp00/ylp01'de YOK.
> - 🆕 **`kayit_coz.py --irtifa-csv`** — çözümleme artık ROS'suz, laptopta
>   koşuyor.
> - ⚠️ **Konteynerdeki `swarm_perception` eski derleme** —
>   `min_zone_area_frac` yok, canlı renk eşiği ayarı çalışmıyor.
> - ⚠️ Renk dedektörü çalışıyor (5-15 m'de %20-30) ama eşikleri **magenta
>   tondayken** kalibre edilmişti; yeni renk dengesinde yeniden ölçülmeli.

> ## 📓 27 AĞUSTOS 04:30 — OLAY DEFTERİ ÇALIŞIYOR + 🔴 ylp02 UÇMAZ
>
> **Uçuş yok, yer işi.** Üç uçak açık, disarm, mesh'te (`komsu_veri=2/2`).
> Python **`61ba6c9`**, ESP firmware **`eabe59f`** (üç drone + baz, hash
> doğrulandı — kablo sökülmeden, Pi üzerinden yakıldı).
>
> - 🔴🔴 **ylp02 UÇMAZ — PX4 güç soketi gevşek.** Sokete dokununca FCU
>   yeniden başlıyor. Pi tarafında düşük gerilim izi YOK (`get_throttled=0x0`),
>   yani arıza PX'in kendi hattında. Kabul ölçütü: bant DEĞİL lehim/kilitli
>   konnektör, sonra kabloyu bilerek üç kez oynat. `YAPILACAKLAR` P0.
> - 🆕 **YKİ olay defteri:** drone kartında `▤ LOG` → kart komple deftere
>   dönüşüyor. Kritik olayda buton kırmızı yanıp söner. Kayıtlar **diske**
>   yazılıyor (`src/gcs/gunluk/yki_olaylar.jsonl`) — **P1.16 kapandı**.
> - 🆕 **Olaylar mesh'ten akıyor** (`TIP_OLAY = 0x16`). Paket BÜYÜMEDİ.
>   Bütçe drone başına 1/sn, 3 tekrar, aşınca **kuyrukta bekler** (düşmez).
>   Ayırt etme: **mesaj alanı boşsa mesh'ten gelmiştir.**
> - 🆕 **Pi sistem sağlığı olayları** (60-68, histerezisli). Eşikler ölçüme
>   dayanıyor: Pi 5 boşta 56-64 °C, uyarı 70/65, kritik 80/75.
> - ⚠️ **Pil değerlendirmesi KAPALI** (`alerts.pil=false`): sahada ölçüm yok,
>   PX4 tezgâhta sabit 12,6 V/%100 sentinel'i veriyor. Kart gelince açılacak.
> - ⚠️ **MAVROS otomatik onarımı yalnız Pi uptime < 15 dk.** Sonrasında
>   onarım YOK; köprü KRİTİK olay basar, karar operatörde (SSH + restart).
> - ⚠️ Uçaklar **formasyon-sürer modda** (`/ws/gozlem` YOK) — mesh goto
>   uçağa gitmez. Eski düzen için `touch /ws/gozlem` + restart.
> - 🔴 **26 Ağustos'un HOME kayması P0'ı HÂLÂ AÇIK** — bu gece dokunulmadı.
>   Çözülmeden RTL'li uçuş YOK.

> ## 🔧 26 AĞUSTOS 23:10 — `dd5a1e6` ÜÇ UÇAĞA DAĞITILDI + ESP FLASH YOLU AÇILDI
>
> **Uçuş yapılmadı, yer işi.** Üçü de `dd5a1e6`; `baslat.sh` ve `run_drone.sh`
> md5 olarak depoyla eşit, **9 düğüm ayakta**, MAVROS GCS hattı üçünde de
> **sağlıklı** (yeni denetim canlı, `/ws/mavros_gcs_bozuk` yok).
>
> - 🆕 **`baslat.sh` MAVROS GCS hattını artık doğruluyor**, bozuksa mavros'u
>   **bir kez** yeniden başlatıyor; yine bozuksa `/ws/mavros_gcs_bozuk`
>   bırakıyor ve `drone_bul.sh --durum` onu `>> SORUN` olarak gösteriyor.
>   Bu, tek oturumda 876 MB'a varan sessiz log taşkınını bitiriyor
>   (`TUZAKLAR` §2.23 — **kök neden hâlâ bilinmiyor**).
> - 🆕 **ESP32 artık kablo sökülmeden, Pi üzerinden flash'lanabilir** —
>   ylp00'da kanıtlandı (`chip-id` okundu, MAC tabloyla birebir, stub yüklendi).
>   esptool **v5.3.1** üç Pi'nin **host'unda** (`~/esptool_venv/bin/esptool`).
>   Yöntem: konteyner durdur → **BOOT basılı tut + EN'e dokun** → esptool →
>   EN'e tek dokunuş → konteyner başlat. USB-TTL ve jumper sökme **gerekmiyor**.
> - ⏳ **`-e ROS_LOCALHOST_ONLY=1` HENÜZ ETKİN DEĞİL** — konteyner recreate
>   istiyor (A19, `YAPILACAKLAR` P1). O ana kadar `docker exec` ile ROS sorgusu
>   yaparken **elle** `-e ROS_LOCALHOST_ONLY=1` verilmeli; yoksa düğümler
>   görünmez ve **hata da alınmaz** (`TUZAKLAR` §1.25).
> - ⚠️ **`--restart unless-stopped` elle durdurulanı geri getirmez.** Bugün
>   ylp00'ın `drone1`'i Pi kapa-aç sonrası 43 dk `Exited` kaldı ve tabloda
>   görünmüyordu; `--durum` artık `docker ps -a` kullanıyor (`TUZAKLAR` §1.26).
> - ⚠️ Uçaklar hâlâ **formasyon-sürer modda** (`/ws/gozlem` YOK) — mesh goto
>   uçağa gitmez. Eski düzen için `touch /ws/gozlem` + restart.

> ## 🌙 26 AĞUSTOS GECESİ — İKİ TARİHİ UÇUŞ + BİR P0
>
> - **İLK FORMASYON UÇUŞU (ADIM 3 HAVADA):** üç uçak, V (tip 2), slotlara
>   ~1 m, yaw 330° senkron, 20+ sn salınımsız; RTL nokta iniş. ✅
> - **OTONOM CA GEÇİŞİ:** çakılı liderin ±3 m yanından düz geçiş —
>   ylp01 ÜSTTEN (~11 m), ylp02 ALTTAN (⚡ aşağı-kaçışın ilk uçuşu);
>   lider kıpırdamadı. ✅
> - 🔴 **P0 — HOME KAYMASI:** RTL'de üçü kalkışa değil AYNI yanlış civara
>   indi (~9 m KD). PX4 home kayıtları = iniş noktaları (RTL doğru uçtu,
>   home'lar yanlıştı). **Çözülmeden RTL'li uçuş YOK** — bag analizi.
> - ⚠️ ylp02 geçiş sonrası dönüşte 6,4 m'de tutuk kaldı — analiz bekliyor.
> - ⚠️ Uçaklar **formasyon-sürer modda** bırakıldı (`/ws/gozlem` yok):
>   sonraki açılışta mesh goto UÇAĞA GİTMEZ. Eski düzen için
>   `touch /ws/gozlem` + restart.
> - 🟡 drone1 docker json logu korupt (`docker logs` bozuk; rosbag sağlam).

> ## 🎯 25 AĞUSTOS AKŞAMI — İLK ÜÇ UÇAKLI UÇUŞ, 8 TEST 8'İ GEÇTİ
>
> - **TEST 0 (KARAR-04 yer testi):** üçlü eşzamanlı ARM sürü yolundan 3/3;
>   uçak kaybında sayaç 3→2, **acil iniş YOK** — dayanıklılık doğrulandı.
>   (FORMING görev başlatılmadan görülmez — üç uçaklı ilk göreve entegre.)
> - **ylp01 üç görev uçuşu uçtu** (asılı + 2 CA testi) — tamir tamamen kapandı.
> - **Günün bulgusu:** kapalı ylp02 körlük sayılıp dönüşü 34 sn blokladı →
>   `6258eab` **körlük yerde-pasif muafiyeti** (yerde+disarm kayıp komşu
>   dönüşü tutmaz; havada/arm'lı kayıp AYNEN korunur). Üç uçağa dağıtıldı,
>   yerde VE uçuşta doğrulandı (3 tam kaçış-dönüş çevrimi).
> - **FİNAL: üç uçak aynı anda havada** (filo ilki) — manuel ÇAPA (ylp00)
>   ile ylp01/ylp02'ye ikişer yaklaşma: 4/4 kaçış-dönüş, taban aynası ×2
>   (`dikey_yetersiz` → rütbe-AŞAĞI uçak yukarı aynalar), merdiven tepesi
>   9,6 m, sıfır körlük, inişler nokta atışı.
> - Filo ilki #2: **üç uçak aynı anda RTK-Fix** (taze survey, 1005 canlı).
> - ⚠️ Canlı kural: uçak ELDE taşınırken ESP gölgelenir → 2 sn'lik körlük
>   KRİTİK'leri normaldir; uçuş sırasında görülürse yaklaştırma KESİLİR.

> Bu belge **şimdiki hâli** anlatır, tarihçe değil. Bir şey değişince burayı
> güncelle, eskisini sil. Ne olduğunun hikâyesi `GUNLUK.md`'de kalır.

---

## 1. Filo

| İHA | agent_id | Durum | Not |
|-----|----------|-------|-----|
| ylp00 | 1 | **Uçar** | Kod **`6258eab`** (25 Ağu ~21:00 — körlük yerde-pasif muafiyeti; öncesi 7645d83 tatmin+hist 2,5). Kadro rütbesi 0 = **ÇAPA (dikeyde kaçmaz)** — CA testlerinde manuel/yaklaştıran uçak bu olmalı (25 Ağu dersi). Pervaneler **TAKILI**. **RC-kayıp tespiti kuruldu ve HAVADA doğrulandı (19 Ağu):** kumanda kapanınca 1-2 sn'de RTL — Ch3 üst-uç yöntemi, bkz. `RPI_ESITLEME.md` §5. **P0.11 yer testi GEÇTİ:** sürü yolundan ARMED + lider seçimi + kalp atışı 399 msj @ 10 Hz. ✅ `yer_testi` bayrağı **YOK** (20 Ağu 16:20 ölçüldü) — uçak kalkış komutunu ALIR. ✅ Düşme (19 Ağu kill kazası) sonrası kontrol TAMAM (23:50): pervane/gövde/motorlar elle temiz, GPS ölçüldü — **RTK-FIXED, 30 uydu, sensör bitleri tam** (akşamki "bit yok" okuması geçiciymiş). ⏳ Titreşim ölçümü uçuş sabahı pervane takılınca (`titresim_olc.py` — pervanesiz ölçüm yanıltır). ⚠️ RC kalibrasyonu yenilendi (`RC3_MIN` 1016→906). ✅ `core.50` silindi (20 Ağu 00:05, 337 MB; disk %40) |
| ylp01 | 2 | **Uçar — 3 görev uçuşu geçti (25 Ağu akşam)** | Kod **`6258eab`**. Tamir zinciri TAMAMEN kapandı: yeni Pi + yeni ESP (MAC takma adı `...13:88` — `cihazlar.md`) + yeni Pixhawk (`MAV_SYS_ID=2`). 25 Ağu akşam: **asılı görev uçuşu** (4,8 m/60 sn, sapma 0,4 m) + **iki CA doğrulama uçuşu** (kaçış 4,0 m'de giriş, 3 tam kaçış-dönüş çevrimi) + üç uçaklı final testte kaçan taraf. Kadro rütbesi 1 = YUKARI kaçar. Pi içeriği diğerleriyle md5-eşit (25 Ağu öğlen). ⏳ Pil sensör kartı hâlâ yok — uçuşlar tok pil + süre sınırıyla | |
| ylp02 | 3 | **Uçar** | Kod **`6258eab`** (25 Ağu ~21:00, filo senkron). Kadro rütbesi 2 = birincil AŞAĞI; **4,8 m altında taban aynası YUKARI'ya çevirir — 25 Ağu'da iki kez sahada doğrulandı** (`dikey_yetersiz` tanısı). `guided_ivme_ff=1.0` açık. Pervaneler **TAKILI**. **İki uçaklı P0.11 yer testi GEÇTİ:** sürü yolundan ARMED + lider mutabakatı + mesh'ten 499 kalp atışı aldı. ✅ `yer_testi` bayrağı **YOK** (20 Ağu 16:20 ölçüldü). ✅ Alıcı failsafe'i düzeltildi ve ölçüldü (**P0.9 KAPANDI**, 19 Ağu gece: kayıtlı +100 bulundu → -100 kaydedildi → `CH5=1000`). ✅ RC-kayıp tespiti KURULU, bit iki yönde doğrulandı — kumanda kaybında RTL |

> ✅ **22 Ağustos 17:31 — İKİ UÇAK DA AÇIK, ylp00 restart edildi.**
>
> Bekleyen `docker restart drone1` yapıldı; kaçınmanın ivme sınırları
> (`30 → 5,66 m/s²`) artık **ylp00'da da etkin** — açılış logunda
> `ivme normal=3.58 acil=5.66 donus=0.50`. **İki uçakta da aynı**, ayrışma yok.
> İkisi de 11 düğüm, `armed=false`, YKİ ve QGC bağlı.
>
> Kalan sıralı işler: `YAPILACAKLAR.md` **"SONRAKİ OPERATÖRE"** bloğu.



> ## 🎯 23 AĞUSTOS AKŞAMI — DİKEY KAÇINMA HAVADA ÇALIŞTI
>
> ylp02 4,8 m'de asılı, ylp00 operatör kumandasında üzerine sürüldü.
> **İki tam kaçış-dönüş çevrimi**, ikisi de temiz:
>
> ```
> tirmanma       : +3,1 m ve +2,8 m      (tasarim hedefi 3,0 m)
> tepe hiz       : 1,25 m/s              (PX4 tavani 1,2 — doygun)
> donus          : 0,50 m/s, nominale 4,79 m (iki kez)
> yatay itme     : HIC ACILMADI (vx=vy=0,00)
> en yakin yatay : 3,20 m
> alarmlar       : dikey_yetersiz=0 donus_kor=0 korluk=0
> ```
>
> Ayrıntı, zaman çizelgesi ve "yo-yo" gözleminin çözümü: **`docs/CA.md` §6.5**.
>
> ### 🔴 Uçuştan çıkan iki bulgu
>
> **1. İtki payı ince.** Askı gazı **%72** (belgede %66 yazıyordu, düzeltildi).
> Kaçış geçişlerinde gaz **%100'e doyuyor** — toplam ~2,5 sn, en uzun
> kesintisiz blok 0,7 sn. Uçak düşmez ama o anlarda rezerv yok.
> **`MPC_Z_VEL_MAX_UP` yükseltilemez** — o karar ölçümle kapandı.
>
> **2. Dönüş fazla aceleci.** Çıkış eşiği 4,5 m + 2 sn bekleme; komşu hâlâ
> yakınken 3 m'lik ayrım 6 saniyede geri veriliyor. Öneri `hist_m`
> 0,5 → 2,5-3,0 (`CA.md` §7.2) — **henüz yapılmadı.**
>
> ### ✅ 24 AĞUSTOS 14:45 — DAĞITIM YAPILDI: iki uçak da `7645d83`
>
> ```
> ucaklarda = depoda : 7645d83  (tatmin duzeltmesi + hist_m 2,5; cikis 6,5 m)
>                      sonraki commit'ler (f93c3dd, ffafaae) yalniz docs +
>                      YKI tarafi — ucak paketlerini DEGISTIRMEZ, fark yok
> G1 dogrulama       : CANLI dugumden — ikisinde de hist_m=2.5
>                      ylp00 rutbe=0 (capa) · ylp02 rutbe=1 (+3 m) · 11 dugum
> env                : ucus_ayarlari.env yeniden uretildi, iki Pi'ye yazildi
> ```
>
> Operatör kararı (24 Ağu): `tatmin` düzeltmesi ile `hist_m` **birlikte**
> dağıtıldı — yalnız `hist_m` dağıtmak, uçağı eski kodun hatalı olduğu
> "ayrım kurulu + çatışma sürüyor" durumunda daha uzun tutup ölçülmüş
> dalışı (-1,48 m/s) sıklaştırırdı.
>
> ## 🎯🎯 25 AĞUSTOS 02:03 — GECE UÇUŞU: DÖNÜŞ DAVRANIŞI DOĞRULANDI
>
> ylp02 4,8 m asılı, operatör ylp00'ı 3 kez yaklaştırıp uzaklaştırdı:
>
> ```
> inis baslarken d_xy : 7,19 / 8,25 / 7,46 m  (hedef >=6,5 — onceki 4,9)
> iceride dalis       : YOK        donus : 0,50-0,51 m/s
> tirmanma tepe hizi  : 1,27-1,32  en yakin yaklasma : 3,52 m
> ```
>
> **Yo-yo kapandı; ADIM 4 iki uçuşla TAM.** Tırmanma +4,6 m (önceki +3,1)
> hata değil: operatör yüksek uçtu, hedef "komşu + katman" izledi.
> Ayrıntı `CA.md` §7.2 · gaz-doyum analizi henüz yapılmadı (`YAPILACAKLAR`).
>
> ⚠️ `docker logs` ylp00'da yine ESKİ açılışı gösterdi (TUZAKLAR §1.18) —
> doğrulama bu yüzden canlı düğümden. Düğüm adları KÖKSÜZ: doğru sorgu
> `ros2 param get /collision_avoidance hist_m` (`/drone_N/...` DEĞİL).

> ## 🔀 23 AĞUSTOS — DİKEY KAÇINMA DEVREYE ALINDI (yapılandırma)
>
> Kaçınmanın birincil kaçış yönü **dikey** oldu. Yatay itme yalnız sert
> kabuğun içinde açılıyor. Sonraki kişi uçakları böyle bulacak.
>
> | | eski | **şimdi** |
> |---|---|---|
> | birincil kaçış | yatay itme | **DİKEY yol verme** |
> | yatay itme | `d0` içinde her zaman | **yalnız `hard` içinde (son çare)** |
> | `d0` / `hard` | 10,0 / 6,0 *(geçici test)* | **4,0 / 2,5** ← K2 KAPANDI |
> | katman | — | **3,0 m** |
> | dikey hız / ivme / kp | — | **1,2 / 2,0 / 2,0** |
> | rütbe | — | ylp00 **0 (ÇAPA)** · ylp02 **1 (YUKARI +3 m)** |
> | `k_tan` | 0,9 | **0** (dikeyle birlikte kötüleştiriyor) |
>
> **Rütbe kuralı:** en küçük kimlik çapadır, dikeyde kıpırdamaz. Merdiven
> dönüşümlü (+katman, −katman, +2×katman…) ve **kadrodan** türetiliyor
> (`SURU_KADRO="1 3"`, `baslat.sh`). ylp01 dönünce **"1 2 3"** yapılacak —
> yoksa yerdeki uçak, uçanların kaçış yönünü belirler.
>
> **Beş yer testi geçti** (datum · rütbe/işaret · son çare · geçirgenlik ·
> körlükte tutma). Ayrıntı ve sayılar: `docs/CA.md` §6.
>
> ✅ **Aynı akşam uçtu ve çalıştı** — yukarıdaki bloğa bak.
> `KARAR-02` denetimi operatör kararıyla atlandı (`KARARLAR.md`).

> ## 📡 23 AĞUSTOS — MESH KAYBI %29 DEĞİL, %1-5 ÇIKTI
>
> "Mesh %30 kaybediyor" varsayımının kaynağı radyo değil **kendi
> köprümüzdü**: 10 Hz'lik kaynağı 10 Hz'lik bir kapıdan geçiriyorduk ve
> jitter yüzünden örneklerin ~%26'sı yutuluyordu (`TUZAKLAR` §2.20).
>
> `_pose_periyot_s` 0,100 → **0,095**. Ölçülen sonuç:
>
> ```
> komsu tazeleme  7,1 Hz -> 10,5 Hz     en buyuk bosluk 0,41 -> 0,31 s
> Pi->ESP yazilan 8,1 /s -> 11,9 /s     gonderim_drop = 0   crc_fail = 0
> ```
>
> Kaçınmanın gördüğü dünya bu kadar tazelendi. `korluk_alarm_s=2,0` ve
> `neighbor_rx_stale_s=1,5` eşiklerinin payı **arttı**, değiştirmeye gerek yok.

> ### 🔴 QGC'de 14550'yi DİNLEYEN link olmadan uçaklara güç verme
>
> **22 Ağustos'ta yaşandı ve ölçüldü.** Uçaklar `gcs_url = udp-b://…` ile
> **yayın** yapıyor; 14550'yi dinleyen kimse yoksa MAVROS karşı tarafı hiç
> bulamaz ve **süresiz** yayında kalır → telefon hotspot'unda laptopun
> interneti ölür (ölçülen tepe **14,5 sn**, süre **~60 sn**).
>
> 🔴 **QGC'nin açık olması YETMEZ.** Osman'ın makinesinde QGC çalışıyordu ama
> `[LinkConfigurations]` **boştu** ve `autoConnectUDP=false` idi — bu, taze
> bir QGC kurulumunun **varsayılan hâli.**
>
> **Kurulum:** QGC → Comm Links → Add → UDP, Listening Port **14550** → Connect.
> Tek link iki uçağı birden taşır (sysid 1 = ylp00, sysid 3 = ylp02).
>
> ```bash
> ss -ulnp | grep 14550     # QGroundControl gorunmuyorsa link YOK/kopuk
> ```
>
> Link bağlıyken `docker restart` maliyeti **333 ms** (ölçüldü) — pencere
> oturum başına bir kez, restart başına değil. Ayrıntı: `TUZAKLAR.md` §7.1.

> ✅ **22 Ağustos — ÇARPIŞMA ÖNLEME SAHADA ÇALIŞTI, ölçüldü.**
>
> Operatör ylp02'yi kumandayla ylp00'a **6,5 m** yaklaştırdı → ylp00 kendi
> asılı noktasından **3,88 m kaçtı**, aradaki mesafe 2 saniyede
> **6,6 → 9,1 m** açıldı. Yatayda hiçbir komut almıyordu; hareket tamamen
> kaçınmanın eseri. `avoid=375`, 20 kaçış satırı, `skip_adaptor=-`.
>
> Aynı uçuşta **körlük alarmı da çalıştı** (`korluk=3`, komşu dönünce
> kendiliğinden temizlendi).
>
> ⚠️ Bunu mümkün kılan üç düzeltme aynı gün yapıldı: bekleme evresinde
> setpoint akışı, büyütülmüş eşikler (`d0=10 hard=6`, **geçici**), körlük
> görünürlüğü. Öncesinde üç deneme boş çıkmıştı ve sebepleri farklıydı.
>
> 🟠 **Sonrasında yapılan iki düzeltme HENÜZ UÇMADI:** sönümleme tabanı
> (uzaklaşan komşuya çekim yok) ve setpoint hız/ivme tavanları.

> 🔀 **21 Ağustos akşamı — ADIM 4 AÇILDI (yerde): kaçınma düğümü değişti.**
>
> `basit_kacinma` **KAPALI**, yerine **`collision_avoidance`** koşuyor
> (`d0=6.0 hard=4.0`). Sonraki kişi uçakları böyle bulacak.
>
> | | eski | **şimdi** |
> |---|---|---|
> | kaçınma düğümü | `basit_kacinma` | **`collision_avoidance`** |
> | `/ws/kacinma` | vardı | **`kacinma.adim4_oncesi`** (kenara alındı) |
> | `suru_dugumleri` | `... formasyon` | `... formasyon **ca**` |
> | `/ws/gozlem` | var | **var** (değişmedi — formasyon hâlâ sürmüyor) |
> | `velocity_only` | false | **false** (değişmedi) |
>
> Tek değişken bilerek kaçınma düğümü. **Uçuşta doğrulanmadı** — ilk uçuşta
> tek soru: guided yolda şeffaf mı? Geri alma tek komut, `KARAR-01` adım 2.
>
> ⚠️ `basit_kacinma` yalnız `position_valid` setpoint'lerde çalışıyordu
> (sürü zincirinde ölüydü). `collision_avoidance`'ın girdi kapısı **yok** —
> hem guided hem sürü zincirinde çalışır, üstüne yaklaşma hızı ve dikey
> bileşen ekler.

> ✈️ **21 Ağustos — İKİ UÇUŞ YAPILDI, ikisi de temiz indi.**
> **P0.12 kapandı** (bayat komut inişi iptal edemiyor — uçuşta doğrulandı)
> ve **sürü kalbi havada ölçüldü**: seçim havada oldu, split-brain sıfır,
> HB boşluğu maks **218 ms** (eşik 1000), DURUM maks **408 ms** (eşik 5000).
> Ayrıntı: `GUNLUK` 15:00 kaydı.
>
> Uçakların hâli: ikisi de **11 düğüm**, `armed=false`, **pervaneler TAKILI**.
> Kod değişmedi (`db828ab`). Mod etiketi OFFBOARD kalıntısı — disarm hâlde
> zararsız.
>
> ⚠️ **Yeni bilinen sorun (P1.14):** lider kimliği mesh'e kalp atışıyla
> taşınıyor, seçim çerçevesiyle değil; `_on_heartbeat` split-brain'i yalnız
> tek yönde çözüyor → **asimetrik kopmada iki lider kalıcı olabilir.**
> Bugün zararsız: sürünün aktüatöre kablosu yok (`setpoint/raw` tek
> yayıncısı `esp32_bridge` — ölçüldü). Sürü uçakları sürmeden önce çözülmeli.
>
> 🔄 **21 Ağustos 01:30 — iki konteyner de temiz, 11 düğüm, `armed=false`.**
> Pervaneler **ÇIKIK**, kill switch'ler kapalı. Mod etiketi ikisinde de
> OFFBOARD kalıntısı (P0.14 yer testinden; disarm hâlde zararsız, mod
> değişince gider). **P0.14 sahada doğrulandı:** lider kaybı takipçi
> tarafından **1.063 sn**'de devralınıyor — `GUNLUK` 01:45 kaydı.
>
> ⚠️ **Pil:** PX4 pil okuması **bilerek kapalı** (KARAR-03) ama
> `px4_bridge` bilinmeyen pili **12.6 V / %100 sahtesiyle** yayınlıyor —
> YKİ'de pil görürsen inanma (TUZAKLAR 1.20, P1.13).
>
> **Bu oturumda uçakta ne değişti — sonraki kişi öyle bulacak:**
>
> | | ylp00 | ylp02 |
> |---|---|---|
> | açılışta kayıt onarımı (`kayit_onar.sh`) | ✅ aktif | ✅ aktif |
> | `mcap` kurtarma aracı (`/ws/bin/mcap`) | ✅ | ✅ |
> | sysctl writeback 1 sn (A8) | ✅ *(23:15 eklendi)* | ✅ |
> | docker log döndürme (10m × 3) | ✅ | ❌ |
> | konteyner yeniden **oluşturuldu** | ✅ | ❌ (yalnız restart) |
>
> ⚠️ **`mcap` ikilisi `dagit.sh` ile GİTMİYOR**, elle konuldu ve depoda yok.
> Yeni bir uçakta yoksa onarım **sessizce** eski davranışına döner.
>
> ⚠️ **ylp00 kayıt diski tavanda: 4,9 GB / 5,0 GB.** Saatlik timer en eski
> kaydı sürekli siliyor — saklanacak uçuş varsa dizüstüne kopyala.
>
> P0.13 (ağ beklemesi + `gps_saat` sert zaman aşımı) **kapandı**, ikisinde de
> etkin.

**Uçuş yapılandırması:** drone **1 ve 3**, lider **3**.
YKİ koşucu paneli varsayılanı buna ayarlı (`backend/api/kosucu.py`).

### ylp01 (drone 2) — düşme durumu

Kaza analizi bitti, **sebep elektriksel**. Log kanıtı: serbest düşüş boyunca
pil 15.4→16.0 V (yükseliyor), RTK-FIX 31 uydu, EKF sağlam, `armed=1`,
`failsafe=0`, `kill=0`. Uçuş kontrolcüsü düşerken bile yayın yapıyordu.
**Yalnız motorlar durdu** → ESC güç/sinyal hattı. Yazılım kusuru değil,
hiçbir yazılım kontrolü bunu yakalayamazdı.

**Kalan fiziksel iş** (yapılmadı):
- Güç modülü çıkışı → PDB → ESC güç lehimleri
- ESC sinyal kablo demeti
- RPi neden açılmıyor (SD kart okunuyor, kart sağlam)

Motorların sağlam olduğu operatör tarafından doğrulandı.

---

## ✅ Disk sorunu çözüldü (14 Ağustos)

Sabah iki drone'un da diski **%100 doluydu** (0 bayt boş). Sebep tek dosya:
`gunluk/mavros.log` — ylp00'da 18.64 GB, ylp02'de 21.57 GB.

Kök neden `gcs_url` uçnoktası: WiFi düştüğünde MAVROS **her MAVLink mesajı
için** `Network is unreachable` uyarısı basıyor, 20 Hz'de saniyede yüzlerce satır.

**Yapıldı:** loglar temizlendi, `baslat.sh`'e **iki kapılı** günlük bekçisi
eklendi — dosya başına 500 MB tavan (son 125 MB korunur) **ve** dizin geneli
3 GB tavan (aşılırsa en eski açılışlar silinir, en yeni iki tanesi kalır).
Açılış dizini 10 → 5, 21 yönlendirme `>>`'ye çevrildi.

Dizin tavanı sürü entegrasyonu için: 14 düğüm açılınca 14 log olacak ve
dosya başına tavan tek başına `14 × 500 MB × 5 = 35 GB`'a izin verirdi.

```
ylp00: 19 GB boş (%34)      ylp02: 21 GB boş (%27)
```

✅ **Konteynerler yeniden başlatıldı, bekçi canlıda:**
`[baslat] gunluk bekcisi: dosya 500 MB (son 125 MB korunur), dizin 3000 MB`. Ayrıntı ve kök neden:
`RPI_ESITLEME.md` §8.

---

## 2. Ağ ve erişim

**IP'ler her ağda değişiyor — ezberleme, `drone_bul.sh` kullan.**
Son ölçülen: **20 Ağustos, `10.205.4.x`** — ylp00 `.134`, ylp02 `.189`.
(17 Ağustos'ta telefon hotspot'u `172.19.167.x` idi.)

**MAC'ler sabit** ve betik onlardan buluyor — 20 Ağustos'ta doğrulandı,
`cihazlar.md` kimlik tablosundakiyle birebir aynı.

> ⚠️ **Yeni ağa geçişte SSH host key uyarısı normaldir** — yeni IP,
> `known_hosts`'ta yok. Panik yapma: canlı anahtarı eski IP kayıtlarıyla
> karşılaştır (`ssh-keygen -F` hash'li olduğu için anahtar gövdesini
> `grep -F` ile ara); aynıysa MITM değil, yalnız yeni IP'dir.

### IP ezberleme — betik var

```bash
./deploy/yki/drone_bul.sh            # menü, seç, bağlan
./deploy/yki/drone_bul.sh ylp00 'komut'
./deploy/yki/drone_bul.sh --durum    # disk, konteyner, bayraklar
```

Önbellek → mDNS (`ylp00.local`) → MAC taraması sırasıyla dener.

⚠️ **mDNS makineye bağlı.** Eyüp'ün Ubuntu'sunda çalışıyordu; Osman'ın
Arch'ında **çalışmıyor** (`nss-mdns` kurulu değil, avahi kapalı). MAC
taraması yedeği her iki makinede de sorunsuz — engel değil, sadece birkaç
saniye yavaş. İstenirse: `sudo pacman -S nss-mdns avahi` +
`nsswitch.conf`'a `mdns_minimal`.

**Kayıtlı Wi-Fi ağları** (ikisinde de): `rpissid` (öncelik 10, tercih edilen)
ve `iPhone` (öncelik 0, yedek). İkisinde de güç tasarrufu kapalı.
⚠️ `iPhone` SSID'si henüz **doğrulanmadı** — eklerken telefon kapalıydı.

**Parola girişi AÇIK** (sshd varsayılanı, override yok) → arkadaşlar kendi
anahtarlarını kendileri kurabilir. **Osman'ın anahtarı 17 Ağustos'ta, Berk'in (MacBook)
anahtarı 18 Ağustos'ta ikisine de kuruldu.**

⚠️ ylp02 **mDNS'e cevap vermiyor** ve host key'i IP tabanlı kaydedildi. IP
değişip aynı adresi başka cihaz alırsa SSH *"REMOTE HOST IDENTIFICATION HAS
CHANGED"* diye bağırır — panik yapma, `ssh-keygen -R <ip>` ile temizlenir.

### 🔴 QGC'de `AutoConnect → RTK GPS` KAPALI olmalı

**18 Ağustos'ta ölçüldü.** QGC'nin RTK oto-bağlanması u-blox baz istasyonunun
seri portunu **kapıyor**; `yki_rtcm_reader` portu açamıyor (`Resource busy`)
ve **RTCM hiç akmıyor**. Belirti sessiz: telemetri normal, arayüz sağlıklı,
tek işaret uçakların `fix_type`'ının 6 yerine 3-5'te takılması.

Port sahibi `lsof` ile bulundu (`QGroundControl PID 6245`). Kapatılınca RTCM
9-10 msg/s'e döndü ve iki uçak da **RTK-FIXED (fix=6)** oldu.

QGC → Application Settings → General → *AutoConnect* → **RTK GPS kapalı**,
**UDP kapalı**. MAVLink bağlantısı elle eklenen 14550 UDP link'inden.
Ayrıntı: `TUZAKLAR.md` §6.6.

### 🔴 Dronlara güç vermeden ÖNCE QGC'yi aç

**17 Ağustos'ta ölçüldü.** `gcs_url` = `udp-b://…` **yayın** demek ve QGC
açık değilken MAVROS durmadan `255.255.255.255:14550`'ye yayın yapıyor.
Telefon hotspot'u bu akış altında **tüm istemcilere** teslimatı saniyede
~1.25 pakete düşürüyor: ağ geçidine ping 14 saniyeye çıkıyor, laptopta
internet ölüyor. Trafik küçük (14 paket/s) — sorun hacim değil, **yayın
olması**. Radyo tarafı tamamen sağlıklıydı: hava %0-3, yeniden gönderim ~0,
hız sabit 72.2 Mbit.

QGC bağlanınca MAVROS **tekil** gönderime geçiyor ve sorun anında bitiyor.
Keşfettiği karşı tarafı unutmadığı için QGC'yi **sonradan kapatmak sorun
değil** (ölçüldü). Ama her `docker restart droneN` MAVROS'u yeniden başlatıp
pencereyi tekrar açıyor.

Kalıcı çözüm tek satır — `gcs_url` = `udp://:14555@` (uçak yayın yapmaz,
sadece dinler; bağlantıyı QGC kurar, uçakta IP yazılı olmaz). Denendi ve
doğrulandı, **uygulanmadı**: operatör kararıyla uçak `udp-b`'de bırakıldı.
Ayrıntı: `GUNLUK.md` 17 Ağustos kaydı.

---

## 🛡️ KAÇINMA KÖRLÜĞÜ ALARMI — 21-22 Ağustos'ta eklendi, ÇALIŞIYOR

**Ne işe yarıyor:** çarpışma önleme uçağın *gözü değil kulağıdır* — komşusunu
ancak mesh yayınından bilir. Yayın kesilirse gökyüzü **boş görünür** ve
kaçınma sessizce devre dışı kalır. Bu alarm o sessizliği bitiriyor.

**Neden var:** 21 Ağustos uçuşunda operatör ylp02'yi ylp00'a **3 metreye**
kadar yaklaştırdı, kaçınma **hiç tetiklenmedi**. Sebep algoritma değildi:
ylp00 komşusunu **46,4 saniye** hiç görmedi — mesh linki **tek yönlü** ölmüştü
(ters yön aynı anda kusursuz çalışıyordu, YKİ ylp02'yi sağlıklı görüyordu).
O 47 saniye boyunca **hiçbir alarm yoktu.**

**Nasıl çalışıyor:**

```
komsu 2 sn goremiyor  ->  ucak kendi DURUM paketinde bayragi kurar
                          (DURUM2_BAYRAK_KACINMA_KORU = 0x04)
                      ->  baz kopru bayragi cozer, SystemEvent yayinlar
                      ->  YKI: KRITIK uyari + SESLI alarm + masaustu bildirimi
```

Ekranda görünen: **"Çarpışma riski: droneN KOMŞUSUNU GÖREMİYOR — o komşuya
karşı çarpışma koruması YOK"**. Düzelince kendiliğinden temizleniyor.

| ayar | değer | anlamı |
|---|---|---|
| `korluk_alarm_s` | **2,0 sn** | bu kadar görmezse alarm |
| `korluk_tut_s` | **0,0 = KAPALI** | operatör kararı: uçak durmasın, haber versin |
| `komsu_durum_bayat_s` | 5,0 sn | mesh bayrağının eşiği |

> `korluk_tut_s` açılırsa (örn. `5.0`) uçak körlükte **yatay hareketi
> durdurur**, dikey serbest kalır. Otonom finalde operatör müdahalesi
> olmayacaksa düşünülmeli. Mekanizma yazılı ve testli, tek parametre.

**Eşikler ölçümden:** sağlıklı linkte komşu verisi boşluğu maks **0,4 sn**
(21 Ağustos uçuş kaydı). 2 sn alarm eşiği bunun 5 katı — geçici mesh
sarsıntısı yanlış alarm üretmez.

### Test etme — uçmadan, konteyner yeniden başlatmadan

```bash
# ylp00 ylp02'yi DUYMASIN (ylp02 YKİ'de görünmeye devam eder)
docker exec drone1 ros2 param set /esp32_bridge sahte_kayip_ajanlar "[3]"
# geri al
docker exec drone1 ros2 param set /esp32_bridge sahte_kayip_ajanlar "[0]"
```

🔴 **Bir düğümü öldürmek bu testi KARŞILAMAZ** — uçak YKİ'den de kaybolur ve
gerçek arızanın en önemli yanı (*ekranda sağlıklı görünen uçak*) hiç oluşmaz.
Bkz. `TUZAKLAR.md` §2.16.

⚠️ **YKİ tarafında iki şart:** tarayıcı sesi için sayfaya **bir kez tıklamak**
(otomatik-oynatma politikası), masaüstü bildirimi için **izin vermek**. İkisi
de 22 Ağustos'ta sahada doğrulandı.

**Sınırı:** bu bayrak yalnız kaçınma körlüğünü taşıyor. Uçakta üretilen diğer
`SystemEvent`'ler (FSM durum geçişleri, consensus lider değişimi) **hâlâ
YKİ'ye ulaşmıyor** — mesh'te `TIP_EVENT` yok. Bkz. `YAPILACAKLAR` P0.16 sonu.

---

## 3. Uçakta açık olan bayraklar

Bunlar **dosya varlığıyla** çalışıyor; uçağı bulan kişi böyle bulacak.

| Bayrak | ylp00 | ylp02 | Anlamı |
|--------|-------|-------|--------|
| `~/yelpence_ws/kacinma` | **YOK** | **YOK** | `kacinma.adim4_oncesi` olarak kenarda. Koşan: **`collision_avoidance`** (21 Ağu ADIM 4) |
| `~/yelpence_ws/gcs_url` | var | var | MAVLink QGC'ye iletiliyor (`udp-b://:14555@14550`) |
| `~/yelpence_ws/tgt_system` | yok | `3` | ylp02'nin FCU sysid'i 3 |
| `BATARYA_KRITIK_V` | `0.0` | `0.0` | FSM bataryaya bakmıyor (regülatörden besleme) |
| `~/yelpence_ws/ucus_ayarlari.env` | **var** | **var** | seyir 3.0 m/s, ivme 1.5 — `ucus_ayarlari.py --kabuk` üretti |
| `~/yelpence_ws/suru_dugumleri` | **`origin consensus fsm formasyon`** | **`origin consensus fsm formasyon`** | 17 Ağu'da ikisinde de ölçüldü, **aynı**. Varsa `SURU_DUGUMLERI` env'ini ezer. Düğüm açmak: `echo ... > dosya` + `docker restart` |
| `~/yelpence_ws/origin` | **var** | **var** | `38.6904758 39.1610188 1216.96` — tek kaynak `deploy/saha_origin.env`, ylp00'da doğrulandı (17 Ağu). Elle yazma, `dagit.sh` dağıtır |
| `~/yelpence_ws/yer_testi` | **YOK** | **YOK** | 19 Ağu 23:57'de ikisinden de silindi — **uçaklar kalkış komutunu ALIR.** Yer testine dönüş: `touch` + restart. (Not: yeni `kalkis_olayla=false` sayesinde "görev başladı" olayı tek başına kalkış tetiklemez; kalkış yalnız guided takeoff'la) |
| `~/yelpence_ws/gozlem` | **YOK** ⚠️ | **YOK** ⚠️ | 23 Ağu'da ölçüldü — belgede "VAR" yazıyordu, **bayattı**. Şu an zararsız (`formation_node`'a tarif gelmiyor) ama tarif gelirse formasyon uçağı **DOĞRUDAN SÜRER** |
| `~/yelpence_ws/gps_saat_kapali` | yok | yok | Varsa GPS'ten saat düzeltmesi yapılmaz |

### 🔴 UÇMADAN ÖNCE: `yer_testi` bayrağını kaldır

```bash
./deploy/yki/drone_bul.sh ylp00 'rm -f ~/yelpence_ws/yer_testi ~/yelpence_ws/gozlem && docker restart drone1'
./deploy/yki/drone_bul.sh ylp02 'rm -f ~/yelpence_ws/yer_testi ~/yelpence_ws/gozlem && docker restart drone3'
```

Açık kaldığı sürece "görev başladı" komutu uçağı ARM eder ve **orada
bırakır** — kalkış komutu gönderilmez. Yer testleri için var.

### 🔴 Yer testinden çıkış: **kumandadan kill switch** — 20 Ağu'da yeniden yaşandı

Yazılım disarm'ı OFFBOARD'dayken PX4 tarafından reddediliyor (`result=1`).
**20 Ağustos yer testinde tekrar oldu:** `guided/3/disarm` tuttu sanıldı,
ylp02 disarm olmadı, operatör kumandadan kesti. `guided arm` uçağı OFFBOARD'a
sokuyor — ayrıntı `TUZAKLAR.md` §3.11.
Sebep ölçüldü: pervanesiz OFFBOARD'da konum denetleyicisi irtifayı tutmaya
çalışıp integrali sarıyor, gaz tırmanıyor ve PX4 kendini "yerde" saymıyor.
**Armlı bekleme süresini kısa tut.**

⚠️ `ucus_ayarlari.env` **dosya öncelikli** — `docker run -e` ile verilen
değeri **ezer**. (`baslat.sh`'te bunun tersi yazıyordu, 15 Ağustos'ta ölçülüp
düzeltildi.) Tek uçakta hızlı deneme için `-e` değil, canlı parametre yolunu
kullan — bkz. `CLAUDE.md` §8.

### Pil izleme KAPALI — üç yerde birden

Uçaklar regülatörden besleniyor, PX4'te `BAT1_SOURCE` disabled. Pil geri
takılınca **üçünü birden** aç, biri unutulursa tutarsız davranır:

1. `deploy/rpi/baslat.sh` → `BATARYA_KRITIK_V=13.6`
2. `src/gcs/frontend/src/services/gorunum.ts` → `PIL_GOSTER = true`
3. `src/gcs/backend/config.yaml` → `alerts.susturulan`'dan batarya kodlarını çıkar

---

## 🔴 DEPO DEĞİŞTİ (16 Ağustos)

Sim'siz saha sürümü ayrı bir repoya taşındı:

| Repo | İçerik | Rol |
|------|--------|-----|
| **`yelpence-2026-saha`** | Sim'siz, 344 dosya | **Çalışılacak repo** |
| `yelpence-2026-swarm` | Her şey, sim dahil | Arşiv — dokunulmadı |

Yeni repoda olmayanlar: `sim/`, `docker/`, `network_proxy`,
`sim_rtcm_source`, `scripts/`, `ARCHITECTURE.md`, `COP_TEMIZLIK.md`.
Hepsi eski repoda ve git geçmişinde duruyor.

⚠️ **`dagit.sh` ile kod dağıtmadan önce hangi repoda olduğunu doğrula.**

### Belge düzeni sadeleşti (16 Ağustos akşamı)

Temmuz–Ağustos saha günlükleri (`docs/arsiv/`, 5 dosya) **silindi**; hâlâ
geçerli olan her şey yeni **`docs/TUZAKLAR.md`**'ye çıkarıldı ve koda
bakılarak doğrulandı. `docs/`: 17 md → **12 md**.

🔴 `TUZAKLAR.md` **§0'da durumu bilinmeyen üç güvenlik maddesi** var
(ylp00 clipping ölçüm kuralı, alıcı failsafe'inin kill tetiklemesi,
hover gazı %66). Uçuş öncesi cevaplanmalı — `YAPILACAKLAR.md` P1.6.

---


## 4. Kod senkronu

### ✅ Uçaklar `main`'de — 17 Ağustos'ta dağıtıldı ve doğrulandı

```
ylp00 / ylp02   .surum:  commit=600ca65   dal=main   (+KIRLI YOK)
                src/  :  176 dosya, repo main ile BIREBIR (md5)
                install/: 6 paketin hepsi
```

İki dağıtım yapıldı: `e012dba` (11:35, kod devri) ve `600ca65` (14:30,
P0.8 `sitl_mode` düzeltmesi). İkisinde de konteynerler yeniden başlatıldı.

Bundan önce iki Pi de `commit=0dfa0ad +KIRLI dal=feature/dagitik-suru`
diyordu; o commit ve dal bu depoda **yoktu** (eski depodan, Eyüp'ün
makinesinden). Yani uçan yazılımı okuyabildiğimiz tek yer Pi'lerin SD
kartlarıydı. `dagit.sh` `--delete` ile çalıştığı için dağıtım o kodu geri
dönüşsüz silecekti.

> 🗄️ **Silinmeden önce git'e alındı:** `saha/pi-kod-15agustos` dalı
> (`52ff027`, `origin`'de). 17 Ağustos sabahı uçaklarda **gerçekten koşan**
> `src/` ağacının birebir kopyası — ylp00'dan alındı, ylp02 ile md5'i aynı.
> Çalıştırılabilir sürüm değil, **karşılaştırma referansı**: "saha böyle
> davranıyordu" sorusunun cevabı burada.

`baslat.sh` md5 `0dacdf44...` : repo = ylp00 = ylp02.

`/ws/src`'te 6 paket var; `network_proxy` ve `sim_rtcm_source` **bilerek yok**
(ikisi de simülasyon bileşeni, bkz. `deploy/rpi/dagit.sh`).

⚠️ Senkron kontrolü için `.surum`'a tek başına **güvenme**, md5 karşılaştır —
`dagit.sh` derleme başarısız olsa bile `.surum` yazıyor (bkz. `TUZAKLAR.md` §1.14).

---

## 5. Sahada koşan düğümler

```
mavros_node · px4_bridge · agent_fsm_node · esp32_bridge
+ collision_avoidance · ic_dis_kopru · swarm_origin_publisher
+ consensus_node · swarm_fsm_node · formation_node · path_planner
```

**11 düğüm** — 23 Ağustos'ta `ros2 node list` ile ikisinde de doğrulandı.
(`ros2 node list` toplam ~80 gösterir; fazlası MAVROS'un eklenti alt
düğümleri, normal.)

`basit_kacinma` **KAPALI** (21 Ağustos, ADIM 4). Silinmedi — beklenmedik
davranışta tek dosya değişikliğiyle geri dönülür.

**İlk sürü düğümleri sahada koşuyor.** `ic_dis_kopru` herhangi bir sürü
düğümü açıksa kendiliğinden açılıyor — sözleşmenin `internal → public`
yerel döngüsünü o kuruyor (bkz. `YAPILACAKLAR` P0.6).

> ✅ **19 Ağu gece — P0.11 YER AYAĞI TAMAMEN KAPANDI:** ① olay verilince
> zincir çalışıyor (iki uçakla: ikisi de ARMED, lider mutabakatı, mesh'ten
> 499 kalp atışı); ② **uçak-içi köprü kuruldu ve YKİ'nin GERÇEK guided
> arm'ıyla doğrulandı** (`b469871`): API → mesh → köprü olayı → ARMED →
> seçim → 535 hb. Ajan TAKEOFF'a geçmiyor (`kalkis_olayla=false`) — kalkış
> guided'da. **G2 tekrarının önünde yazılım engeli yok**; kalan uçuş-öncesi
> işler: `yer_testi` bayraklarını SİL, ylp02 RC-kayıp kurulumu + P0.9,
> ylp00 düşme kontrolü. Ayrıntı: `YAPILACAKLAR` P0.11.

### 🔴 ADIM 1'in HAVADAKİ karşılığı çalışmıyor — G2'de ölçüldü (18 Ağustos)

15 Ağustos'taki test uçakları **elle ARM ederek** yapılmıştı. G2 gözlem
uçuşunda ölçüldü ki **guided uçuşta ajan durumu IDLE'da kalıyor**;
`ELIGIBLE_STATES` IDLE'ı içermediği için consensus hiç seçim yapmıyor.
638 saniyelik kayıtta iki uçakta da `election/result` = 0,
`leader/heartbeat` = 0. Sebep: YKİ'nin guided yolu `agent_fsm`'i atlıyor.
Ayrıntı ve çözüm: `YAPILACAKLAR.md` **P0.11**. ADIM 3'ün ön koşulu.

### ✅ ADIM 1 YERDE geçti — consensus çalışıyor (15 Ağustos)

Pervanesiz, yerde, ARM'lı yapılan testte iki uçak da **aynı lideri** seçti:

```
ylp00: [CONSENSUS] Lider: 0 -> 1 (round=1, ben=1)
ylp02: [CONSENSUS] Lider: 0 -> 1 (round=1, ben=3)      101 ms arayla
ylp00: esp32_bridge  lider 0 -> 1 (BEN)   ← formasyon kapisi ACIK
```

Ayrıca **lider arıza devri** gözlendi: kill switch ylp00'ı FAILSAFE'e
düşürdükten 82 ms sonra `Lider: 1 -> 3 (round=2)`.

Ayrıntı ve sınırlar: `PLAN.md` §8 ADIM 1.

---

## 6. Kanıtlanmış / doğrulanmış olanlar

Bunlar sahada ölçüldü, tekrar sorgulanmasın:

- **Uçuş kanıtı videosu geçildi.**
- **Görev koşucusu** `--senaryo saha`: 5 nokta, 8→15 m, çizgi↔okbaşı formasyon
  değişimi, rotasyonlar, 135° güneydoğuya dönüp iniş. ~187 s görev / ~222 s video.
- **Kuru test** kritik ayrım **8.41 m** (eşik 4.0 m) — `SONUÇ: GEÇTİ`
  (aralık 12 m'ye çıkınca 7.07'den yükseldi)
- **RTK-FIX** iki uçakta 32 uydu; baz `1005` dahil tam RTCM seti yayınlıyor.
  **18 Ağustos'ta baz MSM4'e alındı** — akış artık `1005, 1074, 1084, 1094,
  1124, 1230` @ ~1 Hz, `crc_err=0` (öncesinde MSM7 vardı ve okuyucu uyarıyordu;
  `YELPENCE_RTCM_SPEC.md` §401 MSM4 bekliyor). İki uçak da `fix=6` (RTK-FIXED).
- **Bazın kendi konumu** RTCM 1005'ten okundu (18 Ağu):
  `38.6905395 39.1610681 1217.58` — origin'den **8.29 m yatay, +0.62 m dikey**.
  Fiziksel ayrım olarak makul. ⚠️ Ama RTK, **bazın mutlak konum hatasını
  bütün uçaklara aynen aktarır**: harita üzerinde hepsi aynı yöne kayar.
  Anten son survey'den beri taşındıysa `src/gcs/rtk_baz_survey.py` çalıştırılmalı
  (betiğin başlığı: *"anteni her taşıdığında bunu koştur"*). **Bugün taşınıp
  taşınmadığı bilinmiyor — operatöre soruldu, cevap bekleniyor.**
- **Kalkış irtifa çerçevesi** düzeltildi: goto artık kalkış zeminine göreli
- **Yatay kilit** arm'dan başlıyor (2.5 m'ye kadar yatay konum tutma yok)
- **Uçuş kaydı sertleştirildi**: en kötü kayıp ~14.7 sn → ~2-3 sn
- **Ölçülen hızlar**: yatay 1.83 m/s, dikey 0.85 m/s (komut 2.0/1.0 iken).
  Seyir 14 Ağu'da **3.0**'a çıkarıldı, bu hızda henüz ölçüm YOK —
  bkz. `PLAN.md` §9

---

## 7. Bilinen açık sorunlar

| # | Sorun | Etki | Nerede |
|---|-------|------|--------|
| 1 | `iPhone` SSID'si doğrulanmadı | Telefon açılınca teyit gerekir | `RPI_ESITLEME.md` §7 |
| 2 | ~~Repo commit'siz ve push'suz~~ | ✅ 15 Ağu commit'lendi | — |
| 3 | ylp01 yerde | Üç değil iki uçakla çalışıyoruz | bu belge §1 |
| 4 | Sürü düğümleri hiç uçmadı | Final görevi bunlara bağlı | `PLAN.md` §8 |
| 5 | Drone'larda repoda olmayan 21 betik | Bilgi versiyonsuz, kaybolabilir | `YAPILACAKLAR.md` P2.5 |
| 6 | ~~PX4 parametreleri ayrışmış~~ | ✅ 14 Ağu eşitlendi | `RPI_ESITLEME.md` §8 |
| 7 | ESC telemetrisi kapalı | Kaza sebebini doğrudan verirdi | `YAPILACAKLAR.md` P2.4 |
| 8 | ~~`ARCHITECTURE.md` yanıltıcı~~ | ✅ depodan kaldırıldı (16 Ağu) | — |
| 9 | Wi-Fi düşünce MAVROS log patlıyor | Bekçi kırpıyor ama kök neden duruyor | `RPI_ESITLEME.md` §8 |
| 10 | Pi saati açılışta ~11 saat geriden | Çapraz uçak log karşılaştırması bozulur | `cihazlar.md` ⏰ |

### 🟠 #10 — Pi saati: kök neden bulundu, düzeltme dağıtıldı, **henüz etkin değil**

Pi 5'in RTC'sinde yedek pil yok; açılışta saat bayat geliyor. `gps_saat.py`
açılışta PX4'ün GPS zamanından düzeltiyor — internet gerekmiyor.

**17 Ağustos'ta ölçüldü:** iki uçakta da düzeltme **çalışmamıştı**. Her
ikisinin son açılış logunda aynı satır:
`[gps_saat] GPS zamani 25 sn icinde gelmedi. Saat DEGISMEDI.`
GPS'e güç verildikten sonra topu topu ~54 sn tanınıyor (Pi açılışı → konteyner
13 sn → mavros + `sleep 15` → bekleme 25 sn) ve Here4 soğukta o sürede
kilitlenmiyor. Sonuç: **ylp00 7 sa 58 dk, ylp02 10 sa 15 dk geride, aralarında
2 sa 17 dk fark.**

**Uçuşu bozmuyor** — `consensus_node` bütün tazelik hesabını
`time.monotonic()` ile ve komşunun yerel alım anına göre yapıyor
(`consensus_context.py:29`). Bozduğu şey çapraz uçak kayıt karşılaştırması.

**Yapıldı:** `baslat.sh` → `--bekle 150`, iki uçağa da dağıtıldı, md5
doğrulandı, konteynerler 11:35–11:41'de yeniden başlatıldı.

**Şu anki hâl (11:41):** her iki uçağın saati dizüstüyle **saniyesi saniyesine
aynı**, `NTPSynchronized=yes`. Yeni açılış logları:
`fark=+0.487 sn` (ylp00) / `+0.438 sn` (ylp02) → eşiğin altında, `gps_saat`
saate haklı olarak dokunmadı.

⚠️ Bu sefer saati NTP düzeltti, GPS değil — o sırada Pi'lerin interneti
gelmişti. **`--bekle 150` hâlâ sınanmadı:** asıl sınav internetsiz bir soğuk
açılış. Takip: `YAPILACAKLAR.md` P1.4.

### ✅ #6 — Parametre ayrışması giderildi (14 Ağustos)

`param_karsilastir.py` üç ayrışma buldu, üçü de eşitlendi:

| Parametre | önce (ylp00/ylp02) | şimdi |
|-----------|--------------------|-------|
| `MPC_TILTMAX_AIR` | 45 / 30 | **30** |
| `MPC_YAWRAUTO_MAX` | 45 / 25 | **25** |
| `MPC_VEL_MANUAL` | 4 / 2 | **3.0** |
| `MPC_XY_VEL_MAX` | 4.0 / 4.0 | **5.0** (ikisi de) |

Doğrulama: *"Uçaklar arası ayrışma yok (16 parametre)"* — yalnız
`MAV_SYS_ID` farklı, doğru.

**Uçuş ayarları artık tek kaynakta:** `src/gcs/ucus_ayarlari.py`.
`baslat.sh` `/ws/ucus_ayarlari.env`'i okuyor, seyir hızı **3.0 m/s** canlıda.

**Her uçuştan önce çalıştır:** `./deploy/yki/param_karsilastir.py`

## 8. Yerel servisler (YKİ laptop)

| Servis | Adres | Log |
|--------|-------|-----|
| Arayüz | http://localhost:5173/ | `/tmp/yki_frontend.log` |
| Backend | http://localhost:8000/ | `/tmp/yki_backend.log` |
| Base köprü | — | `/tmp/yki_base_bridge.log` |

Başlat/durdur: `src/gcs/yki_baslat.sh` · `src/gcs/yki_durdur.sh`
**Elle başlatma** — ROS ortamı kaybolur, backend telemetri alamaz.

### YKİ üç makinede koşuyor — kurulum yolu makineye göre değişiyor

| Makine | ROS nereden | Başlatma |
|--------|-------------|----------|
| Ubuntu 24.04 | apt (`/opt/ros/jazzy`) | `src/gcs/yki_baslat.sh` |
| Arch | `ros:jazzy` konteyneri | `yki` alias (bkz. `arch-docker/`) |
| **macOS (Apple Silicon)** | **pixi/RoboStack** | **`~/yelpence-yki-mac/yki_mac.sh`** |

**macOS 18 Ağustos'ta eklendi.** Sanal makine/konteyner **kullanılmadı**:
makine 8 GB M1, VM 3-4 GB RAM alıp QGC + tarayıcı + Vite + backend'e yer
bırakmıyordu. Seri port native çalışıyor — CH340 @460800'de 6 saniyede
79 POSE + 12 DURUM çerçevesi, **0 bozuk**. Kurulum, ölçümler ve geri alma
adımları makinedeki `~/yelpence-yki-mac/README.md`'de (kişisel, depoya girmiyor).

`yki_baslat.sh` bunun için **env ile parametrelendi** (`ROS_SETUP`, `DDS_URI`,
`BASE_ESP_PORT`, `RTK_GPS_PORT`) — ikinci bir başlatma betiği yazılmadı,
Ubuntu davranışı birebir aynı kaldı. Platform tuzakları: `TUZAKLAR.md` §9.

Kurulum `deploy/yki/kur_yki.sh`, **Ubuntu 24.04 (noble) ister** ve başka
dağıtımda bilerek durur. Ubuntu olmayan bir laptopta çalışıyorsan yol,
`ros:jazzy` konteynerinin içinde aynı betiği koşturmak — ikinci bir kurulum
betiği yazma. (17 Ağustos'ta Arch'ta yapıldı ve çalıştı; o makinenin
konteyner dosyaları kişisel olduğu için depoya girmiyor.)

Telemetri: `curl -s http://localhost:8000/api/telemetry/snapshot`

### 🛰 u-blox reset butonu (18 Ağustos)

Arayüzde `⚙ Ayarlar` → **RTK baz istasyonu** bölümünde, iki adımlı onaylı.
Komut seri porta doğrudan gitmiyor — port tek sahipli ve sahibi
`yki_rtcm_reader.py`; komut ROS'tan (`/swarm/internal/rtk/komut`) ona gidiyor,
UBX-CFG-RST'i o yazıyor.

⚠️ **Reset RTCM'i keser**, uçaklar RTK-FIX düşürüp yeniden yakalar. Baz
survey-in modundaysa toparlanma **dakikalar** sürebilir. Havadayken kullanma.

```bash
curl -X POST 'http://localhost:8000/api/rtk/reset?kip=sicak'   # ilik | soguk
```
