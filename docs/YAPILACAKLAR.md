# YAPILACAKLAR

**Son güncelleme:** 8 Eylül 2026, 07:05 — 🔴 **CUSTOM formasyon 3 uçakta mesh'ten HİÇ GEÇMİYORMUŞ** (firmware tip başına 50 ms hız limiti ikinci ofset çerçevesini her seferinde düşürüyordu) — kök neden bulundu, **Pi tarafı düzeltmesi yazıldı**, yerde doğrulanacak · eski: 8 Eylül 05:40 — 🎯 **Görev 1 uçuş profili değişti:** başlangıç formasyonu KAPATILDI (jüri dizilişi korunuyor) · QR1 varışı 10 → **15 m**, kurtarma merdiveni artık **iniyor** (15 → 12.5 → 10) · 🔴 iki yeni P0 (bayat formasyon hedefi · CUSTOM mesh yükü) · eski: 7 Eylül 11:57 — 📻 RC-kayıp failsafe üç uçakta **LAND**'e alındı (~3.5-4 sn; `COM_RCL_EXCEPT` maddesi kapandı, iki yeni madde) · eski: 5 Eylül 18:34 — 🔴🔴 **ylp02 DÜŞTÜ** (`docs/YLP02_DUSME.md`) · 🟢 üç uçağa kod dağıtıldı (`39c78d3`) · 🟢 Görev 1 okuyucu dron artık KAMERALI uçak

> **Finale 5 gün.** Bu liste artık "her fikir" değil, **bu 8 günde
> yapılacak iş.** Bir madde buraya giriyorsa birinin onu yapması planlanıyor
> demektir. 135 maddelik eski liste 29 Ağustos'ta kesildi — tamamı git'te:
> `git show 783afab:docs/YAPILACAKLAR.md`

**Önem:** 🔴P0 uçuş engeli · 🟠P1 finalde puan kaybı · 🟡P2 önemli · ⚪P3 ileride

---

## 🔴 P0 — bunlar kapanmadan ilgili uçuş yapılmaz

- `[ ]` 🔴🔴 **ylp02 DÜŞTÜ (5 Eylül 17:21). UÇMADAN ÖNCE
  [`docs/YLP02_DUSME.md`](YLP02_DUSME.md) OKUNACAK.**
  13 metrede asılıyken itkisini kaybetti, **serbest düşüşle** (13.47 m/s)
  yere çarptı. Kök neden ölçüldü: **motorlara giden güç kesildi** — düşüş
  anında pil gerilimi 14.80 → 15.70 V **yükseldi**, yani yük kalktı.
  Pixhawk'ın kendisi canlıydı (1.6 m'ye kadar taze irtifa bastı), yazılım
  disarm göndermedi (`armed` hep `True`), PX4 hiçbir failsafe ilan etmedi.
  Şüpheli hat: **pil konnektörü → PDB → ESC.**
  🔴 **Fiziksel kontrol listesi ve yerde doğrulama testi o dosyanın §6'sında.**
  Kanıt (bag + loglar) `/tmp/.../scratchpad/kanit/` altında ve **makine
  yeniden başlayınca silinir** — kalıcı saklanacaksa taşınmalı.

- `[ ]` 🔴 **TAKİPÇİ BAYAT FORMASYON HEDEFİNİ FARK ETMİYOR — ölç ve kapat.**
  **Belirti (operatör, son test):** *"ilk QR'a gittikten sonra sadece lider
  irtifa değişimi yapmıştı."*
  **Koddan çıkan:** `formation_node._current_formation` bir kez set edilip
  (satır ~468) her tick okunuyor (~954) ve **hiç yaşlandırılmıyor.** Mesh'ten
  yeni hedef gelmeyi keserse takipçi **son hedefi sonsuza kadar uçurur** —
  ne uyarı basar ne de sürücülüğü bırakır. Aynı düğüm `qr_step` ve
  `mod_sustur` için bayat-bırakma yapıyor; **asıl sürücü olan formasyon
  hedefinde yok.** Bu, "lider alçaldı, takipçi 15 m'de asılı kaldı"
  görüntüsünün birebir imzası.
  **Komut yolu simetrik**, yani kuantizasyon/ofset farkı bunu açıklayamaz:
  liderin kendi komutu da `esp32_bridge._on_formation_out` loopback'i ile
  **aynı codec'ten** geçiyor.
  🔬 **ÖLÇÜM ZATEN VAR, uçmaya gerek yok** — `esp32_bridge` teşhis satırı:
  `form_tx` (lider yayınladı mı) · `form_rx` (takipçi aldı mı) ·
  `form_yarim` (çok parçalı montaj tamamlanmıyor) · `form_sahipsiz`.
  Son uçuşun bag'lerinde bunlara bakılacak; `form_rx` durmuşsa teşhis kesin.
  **Çözüm (ölçümden sonra):** hedefe tazelik damgası + eşik aşılınca
  **gürültülü uyarı ve SystemEvent** — sürücülüğü BIRAKMADAN (bırakmak
  OFFBOARD'dan düşürür). ~15 satır, geri alınabilir.

- `[~]` 🔴 **CUSTOM formasyon 3 uçakta mesh'ten HİÇ GEÇMİYORDU — düzeltildi,
  YERDE DOĞRULANACAK.** *(kök neden 8 Eylül'de bulundu; düzeltme `?????`)*
  CUSTOM ofsetleri formülden türetilemediği için `TIP_FORM_OFSET`
  çerçeveleriyle açıkça taşınıyor — paket başına 2 slot, 3 uçakta **iki
  çerçeve**. `esp32_bridge` ikisini de **ara vermeden** UART'a yazıyordu.
  Firmware ise **tip başına** hız limiti uyguluyor
  (`TX DRONE/src/main.cpp:306` `MESH_GONDERIM_MIN_MS 50`,
  `:420` `mesh_tip_gecebilir`). İki çerçeve **aynı tip**, aralarında
  mikrosaniye → **ikincisi her seferinde düşüyordu.** Alıcıda montaj
  tamamlanmıyor (3 slotun 2'si), 200 ms sonraki başlık yarım montajı
  bilerek siliyor → **slot 2'nin ofseti mesh'e hiç çıkmıyor, takipçiler
  formasyon komutunu HİÇ ALMIYOR.** Lider etkilenmiyor (loopback seri porta
  uğramıyor). Firmware bu varsayımı zaten yazmıştı: *"TIP_FORM_OFSET:
  YALNIZ CUSTOM'da, kalkışta bir kez… Periyodik DEĞİL"* (`mesh_config.h:1102`).
  🔴 **`GOREV_FORMASYON=3` iken de geçerliydi** — `_gorev_formasyonunu_uygula`
  yalnız `_on_rotate`'te (ilk QR'dan SONRA) çağrılıyor, yani QR1'e kadar tip
  zaten CUSTOM'du. **"Sadece lider irtifa değişimi yaptı"nın açıklaması bu.**
  ✅ **Yazılan (Pi tarafı, firmware'e dokunulmadı):** ofset çerçeveleri kuyruğa
  alınıp aralarında **60 ms** bırakılarak gönderiliyor (`_FORM_OFSET_ARALIK_S`,
  50 ms + %20 pay; test firmware kaynağından okuyor) + formasyon mesh çıkışı
  **2 Hz**'e seyreltildi (`FORMASYON_MESH_HZ`, 0 = kapalı).
  🔬 **Yerde doğrulanacak (uçuş YOK):** üç uçak açıkken takipçide `form_rx`
  artmalı, `form_yarim` **artmamalı**; liderde `form_ofs_kuyruk=0`,
  `form_ofs_iptal` sabit. Doğrulama yapılmadan uçulmaz.


- `[x]` ✅ **ylp02'ye KOD DAĞITILDI (5 Eylül 17:0x).** Üç uçakta da `.surum` = `39c78d3`, `baslat.sh` md5 depo ile aynı, `kamera_ajan_id:=1` ve `sabit_lider:=1` düğümlere ulaştı (`/proc/<pid>/cmdline` ile doğrulandı). ⚠️ `dagit.sh` **`ucus_ayarlari.env` taşımıyor** — elle atıldı, sonraki dağıtımda unutulmasın. ~~Eski madde:~~
  5 Eylül oturumu boyunca ulaşılamadı (son bilinen IP'de yok, subnet
  taraması da bulamadı), yani **17 commit geride**: sabit lider, lider
  merkez + Macar slot, kalkış kapısı formasyonu, READY irtifası,
  `command_valid` mesh alanı, B19 yutucu sıfırlaması, yalpa düzeltmesi —
  hiçbiri onda yok. `command_valid` ve sabit lider **mesh sözleşmesine**
  dokunuyor; karışık kodla üç uçak uçurmak sessiz bölünme üretir
  (bkz. `GUNLUK.md` 07:56, kusur 4: lider düşürüyor takipçi kabul ediyordu).
  🔴 **`rsync` ana makinede YOK** — dağıtım `yki` konteynerinden:
  ```bash
  docker exec yki bash -lc './deploy/rpi/dagit.sh --paket swarm_core ylp02'
  ```
  Sonra `docker restart drone3`. Ardından `./deploy/yki/drone_bul.sh --durum`
  ile üç uçakta da `.surum` aynı mı bak. Maliyet: 5 dk, uçuş yok.

- `[ ]` 🔴 **MESH KAYBI GERİ GELDİ — uçuştan önce ÖLÇÜLECEK (4 Eylül akşamı).**
  Son 30 sn: **d2 %6.7 · d3 %21.7**. Sonucu görünmez bir sessiz arıza:
  `Stale ajanlar: [2]` → `[SWARM FAILSAFE] Sağlıklı ajan oranı düşük: 1/3`
  → formasyon tarifi `agent_ids=[1]` ile çıktı → takipçiler
  `if int(self._agent_id) not in [...]: return` ile komutu **sessizce
  eledi.** Uçuşta gözlenen belirti: *"aşağı-yukarıyı yalnız lider yaptı."*
  Hata da uyarı da yok — sistem açısından her şey normaldi.
  🔴 **Zamanlaması kritik: pil değişiminde uçaklar YER DEĞİŞTİRDİKTEN
  SONRA başladı.** `TUZAKLAR.md` §4.14'ün tarif ettiği konum/anten
  bağımlılığı. **Çözüm sırası:** ① uçakları eski yerlerine ve anten
  yönlerine koy ② `python3 deploy/yki/mesh_kayip.py` ile ÖLÇ
  ③ %5 altına inmeden UÇMA. Tahmini maliyet: kod 0 satır, saha 10 dk.
  Ölçmeden yer değiştirmek daha önce işe yaramadı.

- `[ ]` 🔴 **KOMUT 1 Hz'e SEYRELİYOR — sürü seyirde TİTRİYOR (4 Eylül, ölçüldü).**
  Operatör: *"ylp00 titreyerek gitti"*; zamanlama netleştirildi — kaçınma
  olayından SONRA, **navigasyon sırasında** (kaçınma DEĞİL: seyirde 4 m altı
  ayrım oranı **%0** ölçüldü). Zincirin iki ucu:

  ```
  mission1_node tick     : 5 Hz   (tick_hz=5.0, gate YOK — _tick her turda basar)
  formation_node'a varış : ~1.0–1.2 s   (HEM liderde HEM takipçide)
  ```

  1 Hz = **2.5–3 m sıçrama**. `formation_node` rampası
  (`ramp_rate = max_speed = 3 m/s`, eksen başına) bunu ~0.97 s'de bitiriyor,
  `v_ff` **1 Hz'de darbe** oluyor → gözle görülen titreme. Yarışma etkisi:
  formasyon bozulmaz ama görüntü kötü, pil yer ve kamera bulanıklaşır
  (QR okumayı doğrudan vurur).

  ⚠️ **Seyreltmenin YERİ HENÜZ BULUNAMADI** — Python tarafında throttle YOK:
  `mission1_node._tick` (`mission1_node.py:463`) her turda `FormationTargetCmd`
  basıyor · `esp32_bridge._on_formation_out` (`esp32_bridge_node.py:3082`)
  her mesajı gönderiyor · `_uart_yaz` (`:2304`) yalnız boyut denetliyor.
  **Liderdeki loopback de 1 Hz** olduğuna göre darboğaz mesh'ten ÖNCE —
  `path_planner` / `mode_manager` hattında.

  **Sıradaki tek ölçüm — YERDE yapılır, UÇUŞ GEREKMEZ:** 30 sn boyunca
  `mission1_node`'un yayın sayısı ile `esp32_bridge._formasyon_gonderilen`
  sayacını yan yana say. **Eşitse** seyreltme esp32_bridge'in ARDINDA
  (mesh/firmware), **farklıysa** ÖNÜNDE (path_planner/mode_manager). Bu tek
  sayım arama alanını yarıya indiriyor. Maliyet: ~20 dk yer işi, uçuş yok.

- `[ ]` 🔴 **LENS ODAĞI SONRASI QR OKUMA — YERDE doğrulanacak, uçmadan.**
  4 Eylül uçuşunda QR okunmadı; boru hattı sağlam ölçüldü
  (`image_raw/compressed` **27.3 Hz**, 1 yayıncı 1 abone, `vision_node`
  ayakta, `lz=VAR`) ve kare **çekilip gözle bakıldı: tamamen odak dışı.**
  Operatör doğruladı: *"kameraya lens ayarı yapmadım ondan okumadı"*.
  Lens ayarı için yayın açıldı, ylp00'ın QR okuyucusu başlatıldı
  (`vision_node baslatildi: agent_id=1`, kare akıyor, `qr_sayaci=0`,
  4056×3040 @ 10.4 fps) — **ama uçaklar kapandığı için SONUÇ BİLİNMİYOR.**
  **Ölçüm:** elde kağıt QR, ylp00'da
  `cat ~/yelpence_ws/algi_durum.json` → `qr_sayaci` **> 0** mı.
  ⚠️ **Ders (TUZAKLAR'a da yazıldı): `qr_sayaci=0` tek başına yazılım
  arızası DEĞİLDİR.** Kareyi gözle görmeden teşhis koyulmaz — bu oturumda
  boru hattını üç kez ölçtüm, hepsi temizdi, sorun optikti.

- `[~]` 🔴 **İRTİFA REFERANSI YOK — sürü uçarken süzülüyor (4 Eylül, ölçüldü).**
  `use_current_altitude` yazılıyor ama **hiçbir tüketici okumuyor**; merkez
  z'si her yerde `inp.centroid[2]` — yani komut, ölçümün kopyası. Referans
  olmayınca süzülme kendini besliyor: ylp00 10.7 → 2.7 m, ~0.13 m/s, hatasız.
  **NAVIGATE bacağı düzeltildi** (bacak başında mandallama). **AÇIK KALAN:**
  tutma fazları (`_hold_centroid`) ve bayrağın kendisi — ya bir tüketicide
  uygulanmalı ya kaldırılmalı. Bkz. `TUZAKLAR.md` §3.x.
  🟢 **NAVIGATE düzeltmesi 4 Eylül akşamı HAVADA GEÇTİ:** komut z uçuş
  boyunca **tam −10.0 m** kaldı, alçalma 0.43 m/s, QR'a 0.11 m. Süzülme
  (10.7 → 2.7 m) bir daha görülmedi.
  🔴 **AÇIK KALAN AYNEN DURUYOR:** tutma fazları. `_hold_centroid`
  (`orchestrator.py:898`) hâlâ `inp.centroid[2]`yi geri veriyor ve
  `_on_rotate` onu `use_current_altitude=True` ile basıyor
  (`orchestrator.py:1086-1094`) — yani **rotasyon ve tutma fazlarında
  referans hâlâ ölçümün kopyası.** NAVIGATE kısa sürüyor, ROTATE ve
  QR görevleri arası bekleme UZUN; süzülme oralarda birikir.
  İki yol var: ① `seyir_irtifa_ned` mandalını tutma fazlarına da uygula
  (NAVIGATE'teki desenin aynısı, ~10 satır) ② `use_current_altitude`
  bayrağını bir tüketicide gerçekten UYGULA. Bayrak bugün **ölü**:
  `FormationCommand`'a yazılıyor, hiçbir abone okumuyor. Üçüncü seçenek
  bayrağı KALDIRMAK — okunmayan bayrak yanlış güven veriyor.


- `[ ]` 🟠 **DURUŞ AŞIMI 0.38–0.47 m — ölçüldü, DÜZELTİLMEDİ (5 Eylül).**
  Çubuk bırakılınca uçak setpoint'i aşıp ~2 sn'de geri sürünüyor; iki uçakta
  da aynı imza (ylp00 **0.47 m**, ylp01 **0.38 m**). Mekanizma ölçüldü:
  setpoint dururken uçak **1.51 m/s** gidiyor, hız takibi ~0.3 sn geriden
  geliyor → `1.51 × 0.3 = 0.45 m`; ölçülen 0.47. Yani geometri hatası değil,
  **hız döngüsü gecikmesi.** Şartname "Osilasyon gözlemlenmesi −10" için
  görünen bileşen büyük ihtimalle budur (yalpa kapandıktan sonra).
  **Seçenekler:** ① `MOD_HIZ_MPS` 2.0 → 1.4 (aşım hızla orantılı, ~0.33 m;
  panel değeri, sıfır kod, ama hareket yavaşlar) ② yürütücüde freni hız
  gecikmesi kadar erken başlat — **ama dikkat**: Görev 2 hareket modunda
  px4_bridge **dal A**'yı seçiyor (konum + hız ileri-beslemesi), yerel
  yürütücü devrede DEĞİL; bu seçenek Görev 1 guided yolunu etkiler, Görev 2'yi
  değil. Ölçmeden uygulama.

- `[ ]` 🟡 **YERİNDE GEZİNME ~0.15 m @ 0.2 Hz — bizim kodumuz DEĞİL (5 Eyl).**
  Komut kusursuz sabitken (setpoint ±0.01 m, `kyn=1` boyunca) uçak 0.14–0.35 m
  tepe-tepe geziyor, ~5 sn periyot. Kaynak PX4'ün kendi konum tutuşu /
  kestirici. Kayıt için: 10 m'den gözle zor görülür, **öncelik duruş
  aşımından sonra.** Buraya el atmadan önce yukarıdaki maddeyi kapat.

- `[ ]` 🟡 **YALPA DÜZELTMESİNİN GÖZLE TEYİDİ ALINMADI (5 Eylül).**
  Sayılar iyi (ylp00 komut roll dalgası −68%, ylp01 gerçek roll −40%) ama
  oturum operatörün "hâlâ görünüyor mu?" cevabı alınmadan kapandı.
  **Sonraki kişi sorsun.** Hâlâ görünüyorsa aranan şey bu değil, duruş
  aşımı ya da PX4 tabanı — ayrı kusur, ayrı ölçüm.

- `[ ]` 🟡 **KAÇINMA FORMASYON KURULURKEN TETİKLENİYOR (5 Eylül, ölçüldü).**
  ylp01 çizgi slotuna giderken lidere **2.24 m**'ye kadar yaklaştı
  (`d0=3.0` altı), dikey yol verme devreye girdi, formasyon irtifasının 2 m
  üstüne çıkıp ~11 sn sonra geri indi. Kararlı hâlde sorun yok (ayrım
  5.76–6.18 m, 4 m altına hiç inmedi). Yani **kaçınma doğru çalıştı**, ama
  slota giden yol liderin yanından geçiyor. Üç uçakla geometri değişir;
  önce 3 uçakla ölç, sonra karar ver.

- `[x]` ✅ **QR `mnv` eşlemesi DOĞRUYMUŞ — sabah yanlış kaydedilmişti (4 Eyl).**
  Bu madde "eksenler yanlış eşleniyor" diye 🔴🔴 açılmıştı; **şartname
  okununca çürüdü.** Kayıt bilerek duruyor: aynı yanlış iki kez
  kurulmasın ve kimse doğru kodu "düzeltmeye" kalkmasın.

  **Şartname (`docs/Şartname 2026.pdf`, Görev 1 QR komutları):**
  > *"QR içerisinde yer alabilecek görev komutları: Formasyon değişikliği ·
  > Formasyonu **pitch veya roll** ekseni etrafında belirli bir açı ile eğim
  > verme manevrası · İrtifa değişimi · Sürüden birey ekleme/çıkarma"*

  **Görev 1'in QR manevrasında YAW YOKTUR.** Yaw yalnız Görev 2'nin Manevra
  Modu'nda ve **kumanda üzerinden** geçiyor. Görev 1'de yaw, QR'dan QR'a
  giderken formasyon rotasyonu olarak zaten oluyor — ayrı bir komut değil.
  Dolayısıyla `qr_detector.py`'deki `mnv -> (pitch, roll)` eşlemesi doğru.

  **"Çizgide pitch yok" DOĞRU ama eksik özellik değil, GEOMETRİ:**
  `apply_tilt` içinde `dz = −dx·tan(pitch) + dy·tan(roll)`. ÇİZGİ slotlarının
  hepsinde `dx=0` olduğu için pitch terimi sıfırlanıyor. Hesaplandı
  (aralık 7 m, açı 15°):

  ```
  ÇİZGİ   pitch +15° -> dz [0.000, 0.000, 0.000]      ← etki YOK
          roll  +15° -> dz [0.000, +1.876, −1.876]
  OKBAŞI  pitch +15° -> dz [−1.250, +0.625, +0.625]   ← ön aşağı, kanat yukarı
  ```

  Okbaşı+pitch sonucu şartnamedeki örneğin birebir karşılığı. Yani çizgi
  formasyonuna pitch komutu gelirse sürü hiçbir şey yapmaz — bu **doğru
  davranış**, hata değil.

- `[ ]` 🟡 **`mnv` UZUNLUK DENETİMİ yok — fazla değer SESSİZCE düşüyor.**
  `qr_detector.py:395` yalnız `command[1]` ve `command[2]`'ye bakıyor.
  Üç değerli bir `mnv` gelirse üçüncüsü hiç okunmuyor ve **hata da
  verilmiyor.** Şartname *"QR içeriği ÖRNEKTİR, nihai format sonrasında
  paylaşılacaktır"* diyor; format değişirse bunu uçuşta değil YERDE
  öğrenmek isteriz. Uzunluk 3 değilse `ValueError` at — `TIP_QR_HAM` zaten
  ayrıştırma hatasında ham metni YKİ'ye gönderiyor (KARAR 8), yani o anda
  gerçek formatı görebiliriz. Birkaç satır + birim test.

- `[x]` ✅ **QR içeriği YKİ'ye ULAŞIYOR — uçtan uca doğrulandı (4 Eylül).**
  `/api/telemetry/snapshot` → `qr` alanı: `detector_agent_id=3, qr_id=2,
  next_qr=3, team_id=752825, valid=true, formation_type=3, spacing_m=6.0,
  pitch/roll/yaw, altitude_agl_m=18.0, wait_s=4.0`. Zincir: kamera →
  vision_node → esp32_bridge → mesh **broadcast** → baz ESP → laptop
  `esp32_base` → backend. `raw_text` boş gelmesi **normal**: YKİ okunabilir
  metni yapısal alanlardan kendi kuruyor (KARAR 8, ham metin yalnız
  ayrıştırma hatasında `TIP_QR_HAM` ile gider).


- `[x]` ✅ **B5 DOĞRULAMA UÇUŞU GEÇTİ — formasyon İLK KEZ havada kuruldu
  (4 Eylül akşamı).** Tek soru "tarif takipçiye mesh'ten ulaşıyor mu?"ydu;
  cevap ylp02 `formation.log`'undan geldi:
  `FormationCommand alindi: type=3, atama=[1, 2, 3]` (sabah BOMBOŞTU).
  Formasyon üç uçakta da kuruldu, gözle görüldü. `3b64e68` doğruymuş.
  Yan kazanç: **üç uçak ilk kez birlikte arm oldu** — önceki tek-uçak
  kalkışın sebebi donanım değil `PILOT OVERRIDE: mod=POSCTL` idi.

- `[x]` ✅ **Push yapıldı** — sabahki 6'lık paket `1cf6331` ile gitti.
  ⚠️ Uzak `saha/main`, `origin` DEĞİL (`origin` 16 Ağustos'ta kalmış).

- `[x]` ✅ **En-yakın-slot ataması (Macar) — YAZILDI (5 Eylül, `6ab6466`).**
  `slot_atama.py`: lider slot 0'a **çivili**, kalanlar Macar ile en yakın
  slota. Çizgide ölçüldü: toplam yol **0.00 m** (kimlik sırası 24.00 m).
  13 birim test. Özgün madde:
  lider slot 0'a sabit, kalan iki uçak en yakın slota (2 uçak = tek
  karşılaştırma). Bugün d2-d3 çapraz geçişi (kuru 1.94 m KALDI) fiziksel
  takasla çözüldü; **finalde dizilişi biz seçemiyorsak bu kod ŞART.**
  Değişecek yerler: mode_manager ofset gömme noktası (~1320) + kuru test
  aracı aynı kural + birim test. KARAR-11 notu: "Macar iyileştirmesi ayrı
  P2" — reddedilmedi, ertelendi.

- `[x]` ✅ **PİL LOG BETİĞİ — asıl risk kapandı (3 Eylül, operatör + ölçüm).**
  **Çalışan kayıt süreci ÜÇ UÇAKTA DA YOK** (`pgrep pil_testi` = 0 ölçüldü)
  — yani disk+CPU yiyen tehlike gitti, uçuşu engellemiyor. ⚠️ Betik
  DOSYALARI (`pil_testi.py`, `pil_testi_calistir.sh`, `pil_testi/` CSV'leri)
  hâlâ üç uçakta pasif duruyor; süreç çalışmadığı için zararsız ama disk
  yeri kaplıyor. **İstenirse temizlik komutu aşağıda; aciliyeti kalmadı.**
  Depodan kaldırıldı ama **üç uçakta da duruyor**. Silinecekler:

  ```bash
  # her uçakta, konteynerden ÖNCE süreç durdurulur:
  ./deploy/yki/drone_bul.sh ylpXX "
      docker exec droneN sh -c 'kill -INT \$(cat /ws/pil_testi/.pid 2>/dev/null) 2>/dev/null; true'
      rm -rf ~/yelpence_ws/pil_testi ~/yelpence_ws/pil_testi.py \
             ~/yelpence_ws/pil_testi_calistir.sh"
  ```
  **Neden acil:** ① uçaklarda **çalışır durumda bırakılmış bir kayıt süreci
  kalmış olabilir** — ylp01 ağdan düşerken durumu doğrulanamadı, kayıt
  sürüyorsa disk ve CPU yiyor ② `~/yelpence_ws/pil_testi/` altında CSV'ler
  birikti (ylp00'da 1917 satırlık dosya dahil), disk bekçisi bunları
  **temizlemiyor** (yalnız `kayit/` dizinine bakıyor) ③ betik depodan
  silindiği için `dagit.sh` artık **geri kopyalamaz**, yani elle silinmezse
  uçakta sonsuza kadar kalır.

  *Geri isteyen olursa kod git'te duruyor:* `git show 71e0b59` (son hâli),
  `db6568d`→`71e0b59` arası dört commit.

- `[x]` ✅ **`swarm_fsm` sayı/liste ayrımı — SÖZLEŞME NETLEŞTİRİLDİ (3 Eyl).**
  Ölçüldü: `active_agent_count: 3` iken `active_agent_ids: []`,
  `centroid: (0,0)`. **Hata değil, iki farklı tanım:** `count` = CANLILIK
  (tek şart: bayat değil — yerde IDLE'da bile 3), `ids` = FORMASYONA
  UYGUNLUK (healthy + origin_synced + taze + `FORMATION_ACTIVE_STATES`).
  ⚠️ **İkisini eşitlemek çözüm DEĞİL:** `count` bir failsafe'i besliyor
  (`count==0 and total>0` → `EMERGENCY_LAND`); listeye eşitlenirse yerde
  bekleyen sürü "iletişim kesildi" sanılıp indirilir.
  *Yapılan:* davranış değişmedi; `SwarmState.msg` ve `swarm_fsm_node`'un
  iki üretim noktasına ayrımı ve 3 Eylül olayını anlatan not kondu.
  Tek yanlış tüketici `mission1`'di (`8fbfec0` ile düzeltildi); ölçüldü,
  `active_agent_ids`'i okuyan başka yer yok, `count`'u okuyanlar
  (`swarm_transitions` oranları, YKİ göstergesi) canlılık anlamıyla
  tutarlı. **Konum lazımsa `active_agent_ids`/`agent_pos_*` kullanılacak.**

- `[ ]` 🟠 **GÖREV FAZLARI UÇAKLAR ARASINDA KAYIYOR — 25 sn ölçüldü.**
  3 Eylül uçuşu: ylp00 rotasyonu 385177'de bitirdi, ylp01/ylp02 385202'de;
  ylp00 RETURN_HOME'a 25 sn önce geçti. Her uçağın `mission_fsm`'i kendi
  saatiyle ilerliyor (dağıtık tasarım gereği) ama faz sınırları ortak
  değil. O uçuşta asıl tetik hedefsizlikti (tablo yoktu) ve o kapandı;
  **kayma yine de ölçülmeli.** Sonraki uçuşta üç uçağın
  `mission_fsm` geçiş zamanları karşılaştırılacak; fark > 5 sn ise ortak
  bir faz senkronu (liderin fazını mesh'ten yayması) gerekiyor demektir.

- `[~]` 🟠 **ylp01'DE RAM DAR — 4 GB, diğerleri 8 GB.** *(3 Eylül: en büyük
  kalem kapandı, madde açık kalıyor.)*
  **Yapıldı:** `ros2 run` sarmalayıcıları kaldırıldı (B36) — 18 süreç,
  **1451 MB PSS**, yani kullanılan 3,8 GB'ın %38'i. `available`:
  **260 → 736 MB** (2,8 kat). ylp00/ylp02'de de 1656→4279 / 2308→4509 MB.
  **Kalan seçenekler** (ölçülen maliyet: düğüm başına ~120 MB PSS):
  ① Görev 1'de `mod` (mode_manager, Görev 2'nin kumanda sürüşü) kapatılabilir
     → ~120 MB. ⚠️ Görev 2'ye dönerken `suru_dugumleri`'ne GERİ KONMALI.
     *(2 Eylül gecesi operatör "şimdilik elleme" dedi.)*
  ② `pil` (ina226) kapatılabilir → ~120 MB, ama pil telemetrisi gider.
  ③ MAVROS eklenti beyaz listesi — `mavros_node` en büyük tek tüketici;
     kullanılmayan eklentiler kapatılırsa ciddi kazanç, ama **ölçülmedi**.
  ④ `ros2 bag record` 211 MB — kayıt bizim tek teşhis kaynağımız,
     kapatılması ancak son çare.
  🔴 **ylp01'de 2 GB swap var ve 124 MB'ı kullanılmıştı.** Swap'a düşen bir
  ROS düğümü gecikme üretir; uçuşta `free -m` ile bakılmalı.
  🟢 `goru` bayrağı hiçbir uçakta açık değil — kamera düğümleri **hiç
  çalışmıyor**, orada boşa giden RAM yok (2 Eyl doğrulandı).

- `[ ]` 🟠 **İLK FORMASYON SEÇİMİ YKİ'DEN GELSİN** (operatör, 2 Eylül gecesi).
  Bugün görev kodunda **sabit ÇİZGİ**; hakem başka formasyon söylerse kod
  değiştirip yeniden dağıtmak gerekiyor — saha gününde dakikalar.
  *İstenen:* YKİ'de görev başlatma formuna formasyon seçici (okbaşı / V /
  çizgi) + aralık alanı; değer `BAŞLAT` paketiyle mesh'ten gitsin.
  ⚠️ **Yol zaten var:** Görev 2'de aralık/irtifa için açılan `g2_ayar`
  kanalı (`gorev2.md` §5, madde 29) birebir aynı deseni kullanıyor —
  `_GOREV_FMT` rezervinden alan yeniliyor, paket 16 bayt kalıyor, firmware
  değişmiyor. Formasyon 1 bayt; aynı pakete sığar.
  ⚠️ Şartname Görev 1'de YKİ müdahalesini yasaklıyor **ama** bu görev
  ÖNCESİ ayar (G2-K9 ile aynı gerekçe), görev sırasında değil.

- `[ ]` 🔴 **RETURN_HOME'DA BAŞLIK DÖNÜYOR — SIRADAKİ İŞ, uçuş engeli.**
  `orchestrator.py::_on_return_home` başlığı `bearing(centroid → home)`
  ile kuruyor; sürü eve yaklaştıkça vektör kısalıyor ve yön tanımsızlaşıp
  dönüyor. **Ölçüldü (2 Eyl 09:00, iki uçak havada):** merkez
  (4,4;0,6)→(0,0;0,0) giderken başlık **-106° → -169°, 5 saniyede 63°.**
  Slot ofsetleri başlığa göre döndüğü için 7 m yarıçaptaki uçak yay çizerek
  süpürüldü: **ylp00 ylp02'nin üstüne gitti**, operatör PosCtl'e alıp elle
  indirdi, uçak az kalsın bahçe teline konuyordu.
  *Çözüm (yazıldı, yerde denendi, operatör talimatıyla GERİ ALINDI):*
  `_State`'e `kalkis_heading_deg` ekle, `_on_takeoff`/`_hedefsiz_tut`'ta
  bir kez snapshot'la, `_on_return_home`'da onu kullan; snapshot yoksa eski
  yola düş. **Yer testi sonucu: başlık sapması 63° → 0,0°.**
  *Maliyet:* 1 dosya, ~15 satır + yorum. `dagit.sh --paket swarm_missions`.
  *Sonra:* uçuşla doğrula — uçaklar kalkış dizilişini koruyarak inmeli.

- `[ ]` 🔴 **QR TABLOSU FIRMWARE'DE TAKILI — Görev 1 gerçek hedefle uçamaz.**
  ROS tarafı bitti ve kanıtlandı (`esp32_base`: *"QR KONUM TABLOSU mesh'e
  yayınlandı: 5/5 nokta"*), ama baz ESP32'nin **açık beyaz listesinde**
  (`RX BASE/src/main.cpp`, `tip_byte == TIP_RENK || ...` zinciri)
  `TIP_QR_COORDS` yok → sessizce atılıyor. Uçaklarda `bilinmeyen=0,
  crc_fail=0`, yani çerçeve hiç gelmedi. `mesh_config.h:71` zaten
  *"0x0F: packet_parser.py::TIP_QR_COORDS'a rezerve"* diyor.
  *Yapılacak:* `#define TIP_QR_COORDS 0x0F` + beyaz listeye ekle →
  **baz ESP32'yi USB'den flash'la** → tabloyu gönder → uçaklarda
  `/swarm/public/mission/qr_coords` geldi mi ölç.
  ⚠️ Tip başına **50 ms** limit var (`MESH_GONDERIM_MIN_MS`); beş QR aynı
  tiple arka arkaya gidiyor, flash sonrası kaçının ulaştığını ÖLÇ, gerekirse
  `_on_qr_coords_out`'a aralık koy.

- `[~]` 🔴 **OTONOM MANEVRA UÇUŞU** — *2 Eyl: kalkış+formasyon zinciri
  AÇILDI (`passthrough` 0→677), manevra kısmı HÂLÂ UÇMADI.* Zincir kuruldu
  (`maneuver_executor` + `mission1` iki uçakta ayakta), kalan tek şey uçmak.
  *Tek soru:* **"manevraya geçince sürü irtifasını koruyor mu?"** — 1
  Eylül'de üç uçağı 1,7 m alçaltan ve ylp02'yi saha dışına çıkaran şey.
  *Yol:* `gorevfsm`/`gorev1` **KAPAT** → `form_yayinla.sh` → `qr_step=2`
  bas → her uçakta `ros2 action send_goal /drone_N/maneuver/execute`
  (`maneuver_type: 2, roll_deg: 10, duration_s: 4`) → `qr_step=0`.
  🔴 `gorevfsm` açıkken YAPILMAZ: `mission_fsm` 5 Hz'de `qr_step=0` basar,
  formasyon susmaz, `/raw`'a **iki yazıcı** olur.
  *Ön koşul:* ylp00 roll arızası + gece iniş noktası doğrulaması.

- `[ ]` 🔴 **GECE İNİŞ NOKTASI DOĞRULAMASI — cevapsız.** CLAUDE.md §9:
  her uçağın **muhtemel iniş noktası** haritada işaretlenip **operatör
  gözüyle** doğrulanacak. Formasyonda uçaklar kalktıkları yere inmiyor.
  Saha aydınlatması var mı? Yoksa gündüz uçulur.

- `[ ]` 🔴 **ylp01 HER ŞEYDE GERİDE.** Kapalıydı, hiçbir şey dağıtılmadı.
  Üç uçakla teste geçmeden: `RPI_ESITLEME` B20-B23 adımları **ve**
  `ucus_ayarlari.UCAN_KADRO` → `(1, 2, 3)` (yoksa ylp01 kadroda yok
  sayılır, rütbeler de yeniden türer).

- `[x]` ✅ **ylp02 MAVROS ÇÖZÜLDÜ (2 Eylül).** `connected: true`, AUTO.LOITER.
  🔴 **Ders kayda değer:** ylp00'da aynı belirti çıkınca donanım sanıldı;
  ölçüldü ve **donanım DEĞİLDİ** — seri hat 921600'de 882 geçerli MAVLink
  çerçevesi/3 sn, sysid 1. `docker restart` kapattı (`TUZAKLAR` §2.24).
  **Bu belirtide önce restart denenecek.** Eski madde:
- `[x]` ~~🔴 **ylp02'de MAVROS PX4'E BAĞLI DEĞİL.**~~ 1 Eylül 22:30 ölçümü:
  `/drone_3/mavros/state` → `connected:false`, `mode:""`; snapshot'ta
  `imu_healthy`/`baro_healthy`/`mag_healthy` **üçü de False**, `mode:"?"`;
  `imu/mag` ve `global_position/raw/fix` konularında **yayın yok**.
  Karşılaştırma: ylp00 aynı anda fix 3, 28 uydu, hepsi True.
  ⚠️ Barometre ve IMU **iç mekânda da çalışır** — bu "GPS yok" değil,
  **FCU ile hiç konuşulmuyor.** `/dev/ttyAMA0` yerinde.
  *Şüpheli:* açık P0 olan **gevşek PX4 güç soketi** (aynı sınıf arıza) —
  uçak 1 Eylül'de çok elden geçti (ters çevrildi, kamera 2 kez söküldü,
  defalarca kapatılıp açıldı). *Operatör çözeceğini söyledi.*
  **Bu kapanmadan ylp02 UÇMAZ.**

- `[ ]` 🔴 **ylp00 ROLL ARIZASI — uçmadan önce kapat.** PX4 iki bağımsız
  denemede `Attitude failure (roll)` → `Failsafe activated` verdi (kalkıştan
  5,6 sn sonra, ikisinde de). Uçak fiziksel olarak yattı, motorlar kesildi.
  Kill switch 168 sn sonra, uçak zaten yerdeyken basıldı — sebep değil.
  *Yapılacak:* ① **şarjlı pil** — kalkışta 15,29 → **14,72 V** çöktü (%58'di)
  ② pervaneler: gevşek/ters/hasarlı mı ③ motor yatakları ④ kollarda çatlak.
  Ayrıntı `GUNLUK.md` 1 Eylül kaydı.

- `[ ]` 🔴 **ylp02'nin havadaki failsafe sebebi BİLİNMİYOR.** `Failsafe
  activated` → **ALTCTL** (konum kestirimi geçersiz). Elenenler: RC sabit ve
  rssi 41 · setpoint 50 Hz · kaçınma hiç girmedi (`avoid=0`) · Here4
  konnektörü sarsıldı, arıza tekrar üretilemedi. PX4 ulog kapalı olduğu için
  gerekçe okunamıyor. *Karar gerekiyor:* ylp02 tekrar uçsun mu, yoksa önce
  ulog'u geçici açıp mı uçalım (`CLAUDE.md` "Pixhawk'ta log açma" diyor —
  RAM sınırı; geçici istisna operatör kararı).

- `[ ]` 🔴 **MANEVRA MODU DÜZELTİLDİ, UÇAKTA DOĞRULANMADI.** `px4_bridge:838`
  zemin ofseti artık yalnız guided goto'ya uygulanıyor; dağıtıldı, md5 üçünde
  de aynı, 4 regresyon testi var. Ama hiçbir uçuş manevraya ulaşmadı.
  *Tek soru:* "manevraya geçince sürü irtifasını koruyor mu?" *En kısa test:*
  kalkış → 5 m → **SwB manevra, çubuklar merkezde, 10 sn irtifayı izle** →
  hareket moduna dön → in. ~90 sn.


- `[x]` ✅ **DAĞITIM YAPILDI (31 Ağu 06:00)** — üç uçağa `swarm_state_machine`
  + `swarm_control`, `gorevfsm` bayrağı, yeni env. Parametreler doğrulandı.
  Eski madde:
- `[x]` ~~🔴 **DAĞITIM — uçaklardaki `TERS_YAW` YANLIŞ.**~~ 31 Ağustos'ta sürü
  kumandası değişti ve `rc_eksen.TERS_YAW` True→False çekildi (yeni kumandada
  yaw sağı ÜST uca veriyor). Uçaklardaki kod hâlâ eski hâlde: **dağıtmadan
  uçulursa pilot sağa çevirir, sürü SOLA döner** ve hiçbir yerde hata
  görünmez.
  *Yapılacak:* `swarm_state_machine` dağıt (tek paket yeter) ·
  `/ws/suru_dugumleri`'ne **`gorevfsm`** ekle (üçüne) ·
  `MOD_SWC_DEBOUNCE_MS=1300` env'e geçsin · `RPI_ESITLEME.md` §3'e yaz.
  Aynı dağıtımda madde 24·25·26·27·28 + B19 de gider.

- `[x]` ✅ **PERVANELİ UÇUŞ — kalk · asılı dur · in. (31 Ağu 15:52)**
  Üç uçak birlikte kalktı (0,24 sn), 5 m'de 20 sn asılı durdu, birlikte
  indi (0,14 sn). En dar ayrım 6,70 m sabit; roll/pitch tepe 3,3°/5,3°;
  mod kavgası sıfır; dikey komut +0,00. Ayrıntı `GUNLUK.md` 16:24 kaydı.

- `[x]` ✅ **DAĞITIM YAPILDI (1 Eylül).** B6 + madde 29 + morf hızı +
  kaçınma dikey beklemesi + deadman düzeltmesi + manevra datumu. md5 üç
  uçakta da depoyla aynı, parametreler `ros2 param get` ile doğrulandı.
  Eski madde:
- `[ ]` ~~🔴 DAĞITIM — B6 + MADDE 29 + yeni env~~
  31 Ağustos gecesi yazıldı, yerelde 350+270 test geçti, uçaklar **kapalı**
  olduğu için dağıtılamadı (`drone_bul.sh --durum` → "hiçbir drone
  bulunamadı"). *Yapılacak:* `swarm_state_machine` **ve** `swarm_control`
  (ikisi de değişti, tek paket yetmez) → `ucus_ayarlari.py --kabuk >
  ucus_ayarlari.env` üç Pi'ye → `docker restart` → doğrula:
  `ros2 param get /mode_manager_node default_spacing_m` (**7.0**) ·
  `... max_accel_mps2` (**1.3**) · `... kalkis_irtifa_m` (**5.0**).
  ⚠️ Aralık **7 mi 9 mu — KARAR-14 açık.** Formasyon geçişli uçuşta YKİ'de
  "Aralık (m)" kutusuna **9** yazmak yeterli, dağıtım değişmiyor.

- `[x]` ✅ **KUMANDADAN FORMASYON GEÇİŞİ — UÇTU (5 Eylül).**
  Çizgi ile kalkış → V → okbaşı geçişleri kumandadan yapıldı, formasyon
  havada kuruldu ve korundu. Yol boyunca **beş kusur** çıktı ve kapandı
  (kalkış kapısı · READY irtifası · `command_valid` · B19 yutucu · yalpa);
  ayrıntı `GUNLUK.md` 07:56. Özgün plan:
  Sıra: kalk (VrB KAPALI, formasyon yok) → 5 m'de asılı dur → **VrB aç**
  (SwC'nin gösterdiği formasyon oluşsun) → SwC ile bir geçiş → **VrB kapat**
  (uçaklar olduğu yerde donsun) → in.
  Ön koşullar:
  · `MOD_ARALIK=9.0` dağıtılmış olmalı (üstteki madde)
  · 🔴 **Uçakları hedef formasyonun ŞEKLİNDE diz** — ölçüldü: rastgele
    dizilimde ilk morf 4,83 m'ye kadar yaklaşıyor (pay 0,83 m), formasyon
    şeklinde dizilirse darboğaz okbaşı→V morfuna kayıyor ve 9 m'de
    **6,36 m** (pay 2,36 m) oluyor. Aralık büyütmek ilk morfu DÜZELTMEZ.
  · Kuru test **yeni bayrakla**: `--senaryo formasyon_gecis --aralik 9
    --kuru --harita` — bayrak 31 Ağu'da eklendi çünkü senaryolar
    `MOD_ARALIK`'ı kullanmıyordu, yani doğrulanan geometri uçulanla
    aynı DEĞİLDİ.
  · Harita gözle doğrulanmalı (formasyon kutusu ~18 × 18 m + kaçış zarfı)

- `[ ]` 🟡 **ylp02 diski %88 (3,6 GB).** Rosbag ~190 MB/saat yazıyor.
  Finalden önce eski kayıtlar temizlenmeli; uzun görev kaydı dolduruyor.

- `[~]` 🟡 **ylp00 — mavros SEGFAULT.** 31 Ağu 21:12'de bir kez görüldü;
  sonraki üç restart'ta TEKRARLAMADI. İzlemede kalsın.
  Eski madde:
- `[ ]` ~~🔴 **ylp00 — mavros SEGFAULT.**~~ 31 Ağu 21:12 yeniden başlatmasından
  sonra `[ros2run]: Segmentation fault`; yığın 11 yerine 2 düğümle kaldı.
  px4_bridge mavros'suz iş göremez. **Dağıtımdan önce bakılmalı** —
  tekrarlanıyor mu, yoksa o açılışa özgü müydü?

- `[~]` 🟠 **HOME kayması — DEDEKTÖR EKLENDİ (2 Eylül), kök neden AÇIK.**
  `px4_bridge._home_dogrula` 2 sn'de bir home'u uçağın kendi GPS'iyle
  karşılaştırıyor; bozuksa **RTL reddediliyor** + YKİ'ye kritik olay
  (kod 38/39). Uçakta geçti: ylp00 **0,33 m**, ylp02 **0,17 m**.
  Elle inceleme `/ws/home_denetle.py`.
  ⚠️ **Eşik RTK'ya bağlı: RTK'siz 6,0/5,0 m · RTK'li 1,0/2,0 m.** İlk iki
  eşik (1,0 ve 3,0) gürültü bandının içinde kaldı ve sahada yanlış alarm
  verdi — RTK yokken gezinme **3,75 m** ölçüldü (`TUZAKLAR` §2.27).
  ⚠️ **Otomatik düzeltme varsayılan KAPALI** — gürültülü kaynakta
  düzeltmiyor, kovalıyor (3,07 → 3,51 → 3,75 m, `TUZAKLAR` §2.29).
  🔴 **RTK gelince yeniden bakılmalı:** eşik 1,0 m'ye iner, denetim çok
  daha keskinleşir ve otomatik düzeltme anlamlı hâle gelebilir
  (`-p home_otomatik_duzelt:=true`).
  🔴 **Kalan iş:** ① dedektörün GERÇEK bir kaymayı yakaladığı sahada
  görülmedi ② kök neden hâlâ bilinmiyor — 31 Ağu/1 Eyl bag'lerinden
  `home_position` zaman serisi + `GPS origin GONDERILDI` damgaları
  karşılaştırılacak ③ RTL'li uçuş hâlâ operatör kararı.
  Eski madde:
- `[ ]` ~~🔴 **HOME kayması — RTL'e güvenilmez.**~~ 26 Ağustos gece testinde RTL
  üç uçağı kalkış yerine değil **aynı yanlış civara** indirdi (~9 m KD,
  birbirine 1-2 m). PX4 home kayıtları = iniş noktaları → RTL doğru uçtu,
  **home'lar yanlıştı.**
  *Yapılacak:* o uçuşun rosbag'inden `/drone_N/mavros/home_position/home`
  zaman serisi + statustext "home" mesajları → home NE ZAMAN, HANGİ konumla
  set edilmiş? Şüpheliler: ARM anında EKF/origin oturmamış konum · önceki
  uçuştan kalma home · `set_gp_origin` etkileşimi.
  *Bu kapanana kadar:* **RTL'li uçuş YOK.** İniş `land` + göz önü alanla.

- `[ ]` 🔴 **MAVROS GCS denetimi yalnız açılışa bakıyor.** Taşkın sonradan da
  başlıyor: 27 Ağustos'ta üç uçak da açılışta TEMİZ raporlanmışken
  ylp00 1,2 M hata/131 MB · ylp01 4,5 M/467 MB · ylp02 5,0 M/522 MB, bayrak
  üçünde de YOK.
  *Yapılacak:* denetimi `yelpence-izle`'ye taşı (zaten 10 sn'de bir koşuyor).
  ⚠️ Otomatik onarım **yalnız yerde + disarm** iken; havada mavros'u yeniden
  başlatmak px4_bridge'i keser — havada SADECE uyarı.
  *Yan zarar:* `mavros.log`'un başı siliniyor, teşhis kaynağı yok oluyor.

- `[~]` 🔴 **ylp02 PX4 güç soketi — kabul testi.** Operatör 28 Ağustos akşamı
  "halledildi" dedi, test kayda geçmedi. **Uçuş sabahı: kabloyu bilerek 3 kez
  oynat, üçünde de reboot GELMEMELİ.** Kabul ölçütü bant DEĞİL, lehim ya da
  kilitli konnektör.

---

## 🔴 P0 — YARIŞMA GÜNÜ GERİ ALINACAKLAR (geliştirme ayarları)

- `[ ]` 🔴 `PIL_KESME_AKTIF = True` — şu an `False`, pil uçağı FAILSAFE'e
  düşürmüyor (B29). Kalıcı doğru çözüm: anlık gerilim yerine **N saniyelik
  debounce** — çöküş dikenini yutar, gerçekten biten pili yakalar.
- `[ ]` 🔴 `GOREV_NAVIGATE_TIMEOUT_S = 300.0` — şu an 30.
- `[ ]` 🔴 `GOREV_ROTA_BILINMEYEN_S = 30.0` — şu an 10 (B30).
- `[ ]` 🟠 `UCAN_KADRO = (1, 2, 3)` + `SURU_KADRO`/`BEKLENEN` — ylp01 dönünce.

---

## 🟠 P1 — GÖREV 2 · **ayrıntılı liste `docs/gorev2.md` §4'te**

> Bu blok 30 Ağustos'ta **`docs/gorev2.md`'ye devredildi** — orada 29 maddelik,
> aşamalara bölünmüş, kapılı liste var. Burada yalnız **özet ve sıradaki iş**.

**✅ AŞAMA A BİTTİ (30 Ağustos, madde 1-10 + B17).** Kod tarafı tamam:
V formasyonu kumandadan seçilebiliyor · kalkış kapısı (uçak artık origin'e
gidemez) · `rc_ibus_kopru` (ikinci RC alıcısı) · `--senaryo manevra` ·
YKİ joystick zinciri silindi · heading artık hesaplanıyor. **293 birim testi.**
⚠️ Düğüm katmanı yalnız **sözdizimi** doğrulandı — gerçek doğrulama G0'da.

- `[x]` ✅ **AŞAMA B — donanım BİTTİ (30 Ağu).** i-BUS 130 Hz / 0 hata ·
  işaret yönleri ölçüldü (**pitch + yaw TERSTİ, düzeltildi**) · kod
  `193c224` üç uçağa dağıtıldı · **üç konteyner yeniden oluşturuldu**
  (A19 kapandı, ylp00'a `/dev/ttyAMA2`).
- `[~]` 🔴 ~~**AŞAMA B — donanım (SIRADAKİ İŞ).**~~ `gorev2.md` §4 madde 11-15:
  ① 🔴 **i-BUS gerilim ölçümü** — Pi 5 GPIO **5 V toleranslı DEĞİL**,
  multimetresiz bağlanmaz ② kumanda #2: bind + **10 kanal modu** +
  **failsafe SwA=KİLİTLİ** ③ kablolama + `SURU_RC_PORT`
  ④ **konteyner recreate ×3** (`--device` + A19 + A12 + korupt log, tek işlem)
  ⑤ dağıtım — ⚠️ `swarm_core` ve `swarm_state_machine` ikisi de değişti,
  `--paket` ile tek paket **yetmez**.
- `[x]` ✅ **AŞAMA C — G0'ın yerde yapılabilen kısmı BİTTİ.** 16 (RC + kill
  izolasyonu) · 17 (işaretler — **pitch ve yaw TERSTİ**, düzeltildi) ·
  18 (kalkış kapısı) · 22 (deadman) · 23 (mesh). Kalan 19-21 **uçuş ister.**
- `[x]` ✅ **AŞAMA D — KOD TARAFI BİTTİ (31 Ağustos).** `gorev2.md` §4 madde
  24-30 + B19. **Hiçbiri uçakta doğrulanmadı** — dağıtım yukarıdaki P0.
  ✅ **Madde 29'un taşıma yolu ÇÖZÜLDÜ:** ne betik ne SSH — değerler
  **BAŞLAT paketinin içinde** mesh'ten gidiyor, paket hâlâ 16 bayt
  (`gorev2.md` §5, seçenek (c)). YKİ'de iki kutu; boş bırakmak geçerli.
  Aşağıdaki eski liste tarihçe:
  ① 🔧 **G1** LANDING gerçekten indirsin — **kod yazıldı, uçakta
  DOĞRULANMADI.** (Teşhis düzeltildi: olayın *tüketicisi vardı*, ama
  `agent_transitions` `pending_state=LANDING`'i **yalnız 3 durumdan** kabul
  ediyor ve uçaklar ARMED'daydı → istek tek tick yaşayıp kayboluyordu.
  Artık `land` **doğrudan `px4_bridge`'e, 1 Hz tekrarlı**.)
  ② 🔴 **B2** kumandadan kalkış AÇIKÇA (30 Ağu olayının kökü)
  ⚠️ **önce ARM yetkisi kararı** — `gorev2.md` §3'te iki seçenek + öneri
  ③ 🟠 SwC debounce (önce ÖLÇ) ④ 🟠 ADIM 6 `mission_fsm`
  ⑤ 🟠 YKİ Görev 2 BAŞLAT butonu ⑥ ✅ YKİ aralık alanı (+ irtifa) — bitti
  ⑦ 🟠 alıcı failsafe kaydı SwA=1000
- `[x]` ✅ **B19 — `COMPLETED` çıkışı YAZILDI (31 Ağu).** COMPLETED→IDLE:
  SwD iniş konumundan çıkmış **ve** hepsi disarm. Dönüşte uçuş defteri
  sıfırlanıyor (`kalkis_tamam` mandalı dâhil). Uçakta doğrulanmadı.
- `[ ]` 🟠 **AŞAMA E — uçuşlar** (31-33): A (çizgi, pitch/roll) → B (manevra)
  → C (asimetri + kumandadan kalkış/iniş). G0 19-21 Uçuş A'da ölçülür.
  🔴 **`mod` açıkken kill pilotları başında olmalı.**
- `[ ]` 🟡 **`_on_control_out` hız limiti** — ölçüldü: UART'a yazdığımızın
  **%75'i** ESP'de atılıyor. ~8 satır. **Operatör kararı: G0 madde 23
  ölçümünden SONRA** (`gorev2.md` §5).
- `[ ]` 🟡 **ACİL İNİŞ butonu Görev 2'de hâlâ gizli** — gizlenme sebebi
  joystick paneliydi, panel silindi, **sebep kalktı**. Gösterilsin mi:
  operatör kararı.
- `[ ]` 🟡 **`--durum` gibi başka eskimiş liste var mı?** 30 Ağustos'ta
  `drone_bul.sh --durum`'un bayrak listesinde `gozlem`/`yer_testi`/`origin`
  eksikti (kırmızı çizgi olmalarına rağmen). Benzeri aranmadı.

---

## 🟠 P1 — GÖREV 1 (görev zinciri hiç koşmadı)

**Şartname dağıtık algoritma dayatıyor ve hakem YKİ bağlantısını kesecek.**
Bugünkü komut yolu (YKİ → mesh → goto) finali GEÇEMEZ. Bu blok o yüzden var.

- `[ ]` 🟠 **ylp00'DA PİL ÖLÇÜMÜ YOK — YKİ o uçak için YALAN SÖYLÜYOR (4 Eylül).**
  Log: `PIL OLCUMU YOK — ... Yayinlanan %100 / 12.6 V bir OLCUM DEGIL, sabit.`
  Yani YKİ'de ylp00 daima %100 görünüyor; **pil bitse de aynı görünecek.**
  Daha önce sahayı meşgul eden *"Kritik batarya: 12.6V"* hayaletinin kaynağı
  da buydu. **Etkisi:** ylp00'ın pili YKİ'den izlenemez → uçuş süresi kararı
  körlemesine veriliyor. **Çözüm:** ① INA226 kablosu/adresi kontrol (ylp02'de
  çalışıyor, karşılaştır) ② düzelene kadar **elle voltmetre**, ve YKİ'de
  ylp00'ın pil göstergesine güvenilmediği operatöre söylenmeli.
  ⚠️ Sabit değer yayınlamak yayınlamamaktan KÖTÜ: yanlış güven veriyor.

- `[ ]` 🟠 **KURTARMA MERDİVENİNİN 18 m BASAMAĞI OKUMA TAVANININ ÜSTÜNDE.**
  Basamaklar `(qr_read_altitude_m=12, _SEARCH_ALT_FLOOR_M=10,
  qr_search_high_m→18)`; ama ölçülen QR okuma tavanı **16.6 m**
  (`KAMERA.md` §13). Yani üçüncü basamak **tanım gereği okuyamaz** ve her
  arama turunda ~18 sn boşa harcanıyor. Şartname süre puanı veriyor.
  **Çözüm:** üst basamağı 16 m'ye indir (tek sabit, `orchestrator.py:709`
  çevresi) + birim testi güncelle. ~5 satır, geri alınabilir, uçuş gerekmez.

- `[ ]` 🟡 **ylp01'de `cv2` YOK — görüntü eşitlemesi yapılamıyor (KARAR-09).**
  ylp00 ve ylp02'de `cv2 4.6.0` + `pyzbar` var, ylp01'de yok. Bugün kamera
  yalnız ylp02'de (yedeği ylp00) olduğu için uçuşu engellemiyor, ama
  kamera ylp01'e taşınırsa **sessizce** okumaz. Ya kur ya da
  `RPI_ESITLEME` matrisinde ❌ olarak görünür kalsın (şu an görünüyor).

- `[ ]` 🟡 **`dagit.sh` iki kritik dosyayı TAŞIMIYOR — temiz kurulumda
  SESSİZCE eksik kalırlar.** ① `ucus_ayarlari.env` (hız/ivme/irtifa —
  yoksa varsayılanlar devreye girer, örn. toplanma merdiveni 0.0'a düşer)
  ② `~/yelpence_ws/pylib` altındaki PIL ağacı (yoksa kamera yayını
  küçültme YAPMAZ, 4K kare olduğu gibi gider — 4 Eylül'de ylp00'da
  yaşandı, `128105 → 21869 bayt` kazancı kaybediliyordu).
  **Çözüm:** ikisini `dagit.sh`'a ekle ya da `drone_bul.sh --durum`
  denetimine "bu iki dosya var mı" satırı koy. İkincisi daha ucuz.

- `[ ]` 🟠 **ADIM 5 — görü zinciri sahaya.** `camera_driver` + `vision_node`
  ylp02'de koşuyor ama sürü zincirine bağlı değil.
  *En küçük test, uçuş gerekmez:* iki uçak yerde, mesh açık, QR'ı ylp02'ye
  göster → ylp00 mesh'ten `QRMissionData` alsın.
- `[ ]` 🟠 **Takım slot numarasını öğren** (şartname/düzenleyici) ve
  `vision_params.yaml`'a `team_slot` yaz. **Tek satır ama bilinmeden QR
  görevleri filtrelenemez.**
- `[ ]` 🟠 **ADIM 6 — `mission_fsm`.** QR görev sırası. Görev 2 de buna bağlı.
  ↳ Açılınca **KARAR-12** sırası gelir: `mission_active` YKİ'ye lider kalp
  atışıyla (mesh'e **0 bayt** — bayt zaten uçuyor, hep `0` yazıyor).
  Bugün YKİ'de **beş kapı** kalıcı `false`; en görünürü **ACİL İNİŞ butonu
  hiç aktifleşmiyor**, en önemlisi görev sırasında tekil komutların
  kilitlenmemesi (şartname: müdahale görevi BAŞARISIZ sayar). ~23 satır.
- `[ ]` 🟠 **ADIM 7 — `mission1_dynamic_swarm`.** YKİ'nin yerini alan
  orkestratör; **dağıtıklık şartının karşılığı bu.**
  ⚠️ Yerde test edilemez: `decide()` ancak `SYNCHRONIZED_TAKEOFF` → tüm
  ajanlar `IN_SWARM` olduktan sonra komut üretiyor. **En az 2 uçak + UÇUŞ.**
- `[ ]` 🟠 **ADIM 9 — `maneuver_executor`.** QR görevlerinden biri açıkça
  pitch/roll manevrası.
- `[ ]` 🟠 **ADIM 10 — `precision_landing`.** Renkli bölgeye hassas iniş;
  toleransın dışı = 0 puan. `ZoneMap` gerekli (ADIM 5'e bağlı).
  🔴 En riskli adım — yere temas ediyor, kademeli git (önce 3 m).
- `[ ]` 🟠 **ADIM 11 — `task_reallocator`.** Sürüden birey ayrılma/katılma.
  `min_active_for_formation:=2`, üç uçak ister.

### Kamera / QR — Görev 1'in fiziksel kısıtı

- `[ ]` 🟠 **P1.27 — Flex servis kıvrımı denemesi (GÜNDÜZ uçuşu).**
  Operatör hipotezi: flex uçuşta sallanıp **yalıtımı köprülüyor**, gövde
  titreşimi yumuşak göbeği atlayıp kabloyla kameraya giriyor.
  *Yapılacak:* kameraya yakın bol servis kıvrımı, iki yakada ayrı
  sabitleme, aradaki kıvrım serbest. **Bantla gövdeye yapıştırma** — kabloyu
  tekrar sert köprüye çevirir.
  *Ölçüt:* `deploy/rpi/teshis/jole_olc.py` — 28 Ağustos seviyesi **1,04 px**,
  motorsuz taban **0,73 px**, hedef **≤ 0,8**.
  🔴 **Kayıt GÜNDÜZ olmalı** — karanlıkta metrik geçersiz (`KAMERA.md` §12.3).

- `[x]` ✅ ~~`kamera_yayin.py` `dagit.sh`'e eklenmeli~~ → **KAPANDI (1 Eylül).**
  Dağıtıma girdi; ylp02'deki bayat kopya `~/kamera_yayin.py.bayat_28agu`
  adına alındı.

- `[ ]` ⚪ **Kamera servisi açılışta başlamıyor — BİLİNÇLİ, acele yok.**
  Otomatik başlatmak cazip ama riskli: 4K'da `rpicam-vid` ~1,4 çekirdek
  yiyor (1 Eylül: yük 5,08, `mavros` %52-55'te yarışıyor). Açılışta kalkması
  uçuş düğümlerini sıkıştırır. Yapılacaksa **düşük kiple ve kapalı
  varsayılanla** yapılmalı, karar operatörün.

- `[ ]` 🟠 **P1.22 — Yalıtımı derinleştir. QR tavanını açacak TEK eksen bu.**
  🔒 QR büyütülemez (1,5 m, 74 modül — yarışma sabitliyor), çözünürlük de
  tükendi (4K en yükseği). Teorik tavan 34 m, **gerçek tavan 11 m** ve
  aradaki farkın tamamı titreşim.
  *Denenecek:* daha yumuşak/ağır göbek, jel ped, kademeli yalıtım,
  **pervane balansı**. *Ölçüt:* 11-15 m'de okuma sıfırdan farklı olmalı —
  o bantta QR'ın %67-78'i zaten BULUNUYOR, yalnız veri okunamıyor.
- `[ ]` 🟠 **P1.26 — Görev planı 6-9 m kısıtına uymalı.** QR bandı tercih
  değil **kısıt**: altında kadraj taşıyor, üstünde titreşim kesiyor. Şu anki
  `ucus_ayarlari` irtifaları bu bandı gözetmiyor.
- `[ ]` 🟠 **P1.23 — Renk eşiklerini yeni renk dengesinde kalibre et.**
  Mevcut eşikler **magenta tondayken** ölçülmüştü; beyaz dengesi sabit
  kazanca alındı. *Ölçüt:* kırmızı ve mavi daire, 5-15 m, sahte pozitif yok.
- `[ ]` 🟡 **P1.25 — Renk hedefini kadraja alan bir uçuş.** Son dört uçuşta
  yalnız QR üzerinde uçuldu; rengin irtifa eğrisi **yok**.

---

## 🟠 P1 — altyapı (uçuşları engellemiyor ama biriktikçe pahalı)
- `[ ]` 🟠 **QR KONUM TABLOSU RESTART SONRASI KENDİLİĞİNDEN TAZELENSİN.**
  *(4 Eylül, çözülen sorunun kalan yarısı.)* Tablo yalnız her uçağın
  köprüsünün RAM'inde duruyor; `docker restart` onu siliyor ve mesh'te
  "geç katılana tekrar yolla" diye bir şey yok. Şu an tek çare operatörün
  **elle tekrar göndermesi** — kalkıştan önce unutulmaya birebir aday.
  **Öneri:** baz köprüsü mandalladığı tabloyu, bir uçağın DURUM'unda
  "yeni açıldı" görünce (ya da en basiti: 60 sn'de bir, görev başlamadan
  önce) yeniden yayınlasın. Maliyet ~20 satır, tek dosya (`esp32_bridge`),
  geri alınabilir; mesh yükü 6 çerçeve/dk — POSE'un binde biri.
  **OPERATÖR KARARI (4 Eylül): otomatikleştirme YOK — tabloyu arayüzden
  kendisi yeniden gönderecek.** Madde bu yüzden açık bırakıldı, kapatılmadı:
  otomatik tazeleme yerine **kalkış öncesi kontrol listesi** şartı geçerli —
  `grep -a 'QR KONUM TABLOSU' /ws/gunluk/*/esp.log` → `TAMAM: 6/6`.
  Bkz. `TUZAKLAR.md` §4.15.


- `[ ]` 🟠 **29 Ağustos değişikliklerini dağıt.** `baslat.sh` iki kez değişti:
  ① `basit_kacinma` + `fusion` blokları kalktı ② **`--yalniz <düğüm>`** eklendi.
  ⚠️ **DÜZELTME (30 Ağu):** "ikisi de görülmeli" YANLIŞTI — `baslat.sh`'te
  bunlar **birbirini dışlayan dallar**. Formasyon sürerken yalnız
  `TEK-URETICI (ADIM 3)` basılır; kaçınma yine koşar (düğüm listesinde
  `collision_avoidance` görünür). 30 Ağustos dağıtımında üçünde de böyle.
  *Sonra bir kez sahada doğrula:* `docker exec -d drone1 bash /ws/baslat.sh --yalniz ca`
  → `ca.log`'da düğüm yeniden kalkmalı, `mavros`/`px4_bridge` **kesintisiz**
  kalmalı (`ros2 node list` sayısı düşmemeli). Masada konteynerde doğrulandı,
  **gerçek uçakta koşmadı.**
- `[ ]` 🟡 `drone_bul.sh --durum`'un yeni iki satırı (md5 senkronu, düğüm
  sayısı) canlı uçakta hiç koşmadı — ilk fırsatta bak.
- `[x]` ✅ **Konteyner recreate ×3 — YAPILDI 30 Ağustos 13:30.**
  A19 üçünde de kapandı, A12 zaten ✅'ti (belge yanlıştı), ylp00'a
  `--device /dev/ttyAMA2` eklendi. Eski madde:
  `docker rm -f <kon>` + `~/yelpence_ws/run_drone.sh`. Kapattıkları:
  **A19** `-e ROS_LOCALHOST_ONLY=1` (üçünde de ❌; olmadan `docker exec ros2`
  düğümleri **sessizce göremiyor**, `TUZAKLAR` §1.25) · **A12** docker log
  döndürme (ylp02'de ❌) · drone1'in korupt json logu.
  ⚠️ Öncesinde `docker inspect` ile mevcut ayarları not al.
- `[ ]` 🟠 **Algı imajını eşitle** — `./deploy/yki/imaj_esitle.sh ylp00` ve
  `ylp01`. KARAR-09 (B); şu an opencv/zxing yalnız ylp02'de.
- `[ ]` 🟠 **Körlükte davranış kararı — finale kadar verilmeli.**
  `korluk_tut_s = 0` (kapalı): uçak körken durmuyor, haber veriyor. Otonom
  finalde operatör müdahalesi olmayacak. Mekanizma yazılı ve testli, **tek
  parametre** — açılsın mı, operatör kararı.

---

## 🟡 P2

- `[ ]` 🟡 **INA226 gerilim çarpanı iki uçakta FARKLI** — ylp00 `0,98765`,
  ylp02 `1,0`. ~%1,2 ≈ 15 V'ta 0,18 V. Hangisinin doğru olduğu ölçülmedi;
  aynı pili iki uçağa sırayla takıp karşılaştırmak yeter.
- `[ ]` 🟡 **`.surum` yalancı `+KIRLI` diyor** — ağaç temiz olduğu hâlde.
  Sebep izlenmeyen `src/px4_autopilot/` (yalnız `COLCON_IGNORE`).
  Commit'lemek ya da `.gitignore`'a almak damgayı dürüst yapar
  (`TUZAKLAR` §1.14 bu damgaya güvenmemeyi zaten söylüyor).
- `[ ]` 🟡 **HOME denetiminde artık kullanılmayan iki parametre** —
  `home_yerel_yukari` ve `origin_alt_amsl` (dikey çerçeve denetimi
  hükümden çıkınca boşta kaldı). Zararsız ama okuyucuyu yanıltır.

- `[ ]` 🟡 `collision_avoidance_node` birim testlerinin 10'u düşüyor
  (`_korluk_muaf_bildirildi` test kurgusunda yok). Kod sahada çalışıyor,
  testler kodun gerisinde kalmış. 29 Ağustos'ta görüldü.
- `[ ]` 🟡 **ylp02 geçiş sonrası dönüş tutukluğu:** 26 Ağustos'ta 6,4 m'de
  bekledi (körlük yok). Aynı bag + `ca.log`'dan sebep çıkarılacak.
- `[x]` 🟡 **OFFBOARD'da RC'siz uçuş** — 7 Eylül'de ölçüldü ve karara
  bağlandı: `COM_RCL_EXCEPT=0` (üç uçak) → RC-loss failsafe OFFBOARD'da da
  tetiklenir. Aksiyon LAND'e alındı: `NAV_RCL_ACT=3`, `COM_FAIL_ACT_T=2.5`
  → kapanıştan ~3.5-4 sn sonra iniş. `DURUM.md` 7 Eylül bloğu, KARAR-18.
- `[ ]` 🟠 **LAND failsafe'ini havada doğrula** — alçak askıda kumanda
  kapat → ~4 sn'de iniş başlamalı (19 Ağu RTL testinin LAND karşılığı).
  Tek soru, tek manevra; başka şey eklenmez.
- `[ ]` 🟡 **ylp02: konteynerde YENİ süreç ROS grafını göremiyor** —
  7 Eylül: `ros2 node list` boş, `px4_param.py` "servis yok" diyor; koşan
  düğümler sağlıklı (bag akıyor, mavros yayında). PX4 param işleri o gün
  MAVLink'ten yapıldı. Kök bulunmalı (daemon? shm? katılımcı limiti?).
  ylp00/ylp01'de denenmedi — orada da olabilir.
- `[ ]` 🟡 **Hareket modunda centroid sürüklenmesi** (KARAR-11 açık ucu):
  her uçağın mode_manager'ı centroid'i KENDİ tik'inde entegre ediyor —
  uçaklar arası yavaş sürüklenme olasılığı G0/uçuşta ölçülecek.
- `[ ]` 🟡 **`path_planner`'da yavaşlama rampası yok** — ivmelenme var,
  yavaşlama yok; bacak sonunda aşım.
- `[ ]` 🟡 **Pil sentinel'i:** `px4_bridge` bilinmeyen pili **12,6 V / %100**
  sahtesiyle yayınlıyor. YKİ'de pil görürsen inanma. Sahteyi kaldır,
  "bilinmiyor" olarak aksın.
- `[ ]` 🟡 **TUZAKLAR'a yaz:** ros2 `-p x:=90` tam sayıyı INTEGER yapar,
  double declare edilmiş düğümü **açılışta öldürür**. İki kez yaşandı.
- `[ ]` 🟡 **MAVROS taşkınının kök nedeni** (`mavconn/udp.cpp:325`, yayın
  soketinde ENETUNREACH). Kendini onarıyor, acil değil — ama tek oturumda
  876 MB yiyen şeyin sebebi bilinmiyor.
- `[ ]` 🟡 28 Ağustos formasyon uçuşunun kaydı: slot oturma hataları + faz
  geçiş temizliği (mcap → metrik; kayıtlar dizüstünde).

---

## ⚪ P3

- `[ ]` ⚪ `mission1` sahaya alınınca **sekans aparatını sil** (KARAR-10 §5).
- `[ ]` ⚪ PIL'i ylp00 ve ylp01'e de kur (şu an yalnız ylp02'de).
- `[ ]` ⚪ `EVENT_PX4_REBOOT` (kod 69) yazılmadı — taşıma yolu hazır.
- `[ ]` ⚪ Belge sadeleştirmesinin 2. adımı: `TUZAKLAR` · `PLAN` · `CLAUDE.md`.
