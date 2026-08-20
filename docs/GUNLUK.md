# GÜNLÜK — oturum devir teslim kaydı

**Son güncelleme:** 20 Ağustos 2026, 03:21

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
  - 🔴 **ylp00'da `guided_ivme_ff=1.0` CANLI** — **kalıcı DEĞİL**, konteyner
    yeniden başlayınca 0.0'a döner (ylp02 zaten 0.0)
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

- 🔴 **`guided_ivme_ff` ylp00'da açık ama KALICI DEĞİL.** Konteyner restart'ı
  onu 0.0'a döndürür. Kalıcı istenirse: ikinci doğrulama uçuşundan sonra
  varsayılan 1.0 yapılıp `baslat.sh`'e env eklenmeli.
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
