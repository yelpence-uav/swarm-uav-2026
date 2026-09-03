# GÜNLÜK — oturum devir teslim kaydı

**Son güncelleme:** 3 Eylül 2026, 05:15 — uçuş YOK · lider kilidi açıldı · eve dönüş 180°'si aslında 2.1° imiş, düzeltildi · 🔴🔴 pil log betiği uçaklardan SİLİNECEK

Tek bilgisayar, sırayla çalışıyoruz. Biri kalkıp diğeri oturduğunda **hem
kişi hem Claude** nerede kalındığını buradan anlar.

**En yeni kayıt en üstte.** Her oturumun sonunda yeni bir kayıt ekle —
atlanırsa sistem çöker, çünkü sohbet geçmişi sonraki kişiye geçmiyor.

Claude'a **"oturumu kapat"** dersen bu kaydı o yazar.

---

## 2026-09-03 05:15 — gece, uçuş YOK · lider kilidi + eve dönüş açısı

**Ne yapıldı**

- 🟢 **LİDER KİLİDİ — operatör kararı, üç uçakta açık.** Lider bir kez
  seçilir, bir daha değişmez. Sebep ölçüldü: 3 Eylül uçuşunda liderlik
  **beş kez** el değiştirdi (1→2, 2→1, 1→2, 2→1, 1→3). Kök neden liderin
  ölmesi değil, **DURUM paketinin bayatlaması** — uçak başına 7-8 kez
  "5.0–5.1 sn gelmedi" (eşik 5.0). Her değişimde yeni lider slot atamasını
  baştan hesapladı, ylp01 ile ylp02 **slot değiştirdi**, birbirinin üstünden
  geçtiler, kaçınma binlerce kare devrede kaldı (`avoid=1136/1614`,
  `yatay_tut=48/52`). 🔴 **Bedeli bilerek kabul edildi:** lider gerçekten
  düşerse **devir olmaz**, takipçiler son formasyon komutunda kalır; çıkış
  yolu kill switch. Parametre olduğu için yarışma günü tek satırla kapanır
  (`SURU_LIDER_KILIDI`).
- 🟢 **Kilidin içindeki sessiz tuzak da kapatıldı.** Kilit değişimi
  kapattığı için **ilk seçim artık nihai**; oysa o dal `grace_s`=**1.5 sn**
  sonra o an uygun olan kimse onunla seçim yapıyordu. Uygunluk ARM ile
  başlıyor ve uçaklar arası **evre kayması 25 sn** ölçülmüştü — yani yanlış
  lider **kalıcı** olurdu. Artık kilit açıkken ilk seçim **tam kadro**
  bekliyor (aday deterministik `min(1,2,3)=1`); `SURU_LIDER_KILIT_TAM_KADRO_S`
  = 8 sn dolunca eski davranışa düşüyor, yani kilitlenme yok.
- 🟢 **EVE DÖNÜŞ AÇISI ARTIK EV YÖNÜNDEN TÜRÜYOR.** 🔴 Ölçüldü ve manevra
  **hiç yapılmıyordu**: temel açı **liderin kalkış pusulası** idi ve üzerine
  sabit 180 ekleniyordu. Sahadaki gerçek değerlerle: bacak yönü 325.6°,
  lider ylp00 147.7°, komut 327.7° → **QR1'de fiilen dönülen açı 2.1°**
  (tasarım 180°). Hata da vermiyordu. Kanatlar takas etmediği için eve
  dönüşte iç içe geçiş de olmuyordu; dikey merdiven ve 1 m/s dağılma hızı
  boşa çalışıyordu. Artık RETURN_HOME'a girerken `bearing(centroid → home)`
  **bir kez** mandallanıyor → dönüş miktarı kendiliğinden çıkıyor (ev
  arkadaysa 180, 90 sağdaysa 90). `GOREV_DONUS_YAW` 180 → **0** (artık
  yalnız ek ofset). 2 Eylül'deki "63°/5 sn" felaketi geri gelmiyor: o, başlığın
  **her tick** yeniden hesaplanmasındandı; burada tek seferlik mandal var ve
  vektör **en uzunken** (QR1'de ~31 m) ölçülüyor, 3 m altındaysa hiç
  türetilmiyor.
- 🟢 **Dönüş fazları süreyle değil YAKINSAMAYLA ilerliyor.** Yaw fazına 12 sn
  ayrılmıştı; koddaki gerekçe 25°/s varsayıyordu ama o tavana hiç
  çıkılmıyor — kanat teğet hızı tavanı (1.5 m/s) 7 m yarıçapta açısal hızı
  **12.28°/s**'de bağlıyor ve 180° **16.7 sn** sürüyor. Sürü 135°'de kesilip
  eve gitmeye başlıyordu. Yakınsama ölçeri (`_maybe_formation_settled`)
  zaten bu durumda koşuyordu; tek eksik çıktısının fazı ilerletmek için
  kullanılmamasıydı. Süreler artık **zaman aşımı** (30/45/20/45).
- 🔴 **Bir de gerçek bir uçuş riski kapandı:** `_maybe_formation_settled`
  RETURN_HOME'un **her** alt fazında `FormationReachedCmd` üretiyordu ve
  `mission_fsm` bunu görünce **doğrudan LANDING**'e geçiyor. Yani yaw fazı
  oturur oturmaz sürü **hâlâ QR1'in üstünde, evden 31 m uzakta** inişe
  geçerdi. Sinyal artık yalnız son fazda.
- 🟢 **Kaçınma körlüğü testleri sessizce kırmızıydı** — dokuz test. Elle
  kurulan düğüm nesnesi koda sonradan eklenen alanları taşımıyordu
  (`_irtifa_ok`, `_korluk_yer_esigi_m`, dikey tanı sayaçları, `gps_fix_type`)
  ve `_tick`'in geniş `except`'i AttributeError'ı yutuyordu; belirti
  "setpoint yayınlanmadı" oluyordu. Fikstür tazelendi, koruma yeniden test
  altında.
- ⚪ **Pil test logu yazıldı, denendi ve GERİ ALINDI** (aşağıya bak).

**Ölçülen, kalıcı olarak not edilmeye değer**
- **Lider seçimi id'ye göre**, konuma göre değil: depoda tek aday hesabı var
  (`election.py:134`, `candidate = min(effective)`). "Ortadaki drone lider
  olur" **doğru değil** — Dijkstra da yok (tüm depoda tek satır geçmiyor).
  Karışıklığın kaynağı bulundu: slot dağıtımında **Macar algoritması** var
  (`formation_cmd.build_slot_assignment`), yani *ortadaki uçak orta slota*
  gidiyor. Nedensellik ters.
- **Sürünün başlığı = liderin kendi pusulası** (`_kalkis_heading`), çünkü
  `decide()` yalnız liderde koşuyor. Slotu değil, **burnunun yönü** önemli.
- **Dönüş yay çiziyor, kestirmeden gitmiyor** — `path_planner._step_heading_deg`
  yamuk profille süzüyor, açısal hız formasyon boyutundan türüyor
  (`min(25°/s, derece(1.5/r_max))`). Kestirme olsaydı iki kanat merkezdeki
  uçağın tam üstünden geçerdi (hesaplandı: kirişin ortası liderin noktası).
- **Akım hiçbir yerden ölçülmüyor:** `sont_ohm = 0.0` → `ina226.akim_a()`
  0.0 döndürüyor. FCU'nun kendi pil ölçümü de yok (`mavros/battery`
  **65.535 V** = MAVLink "bilinmiyor"). Elimizde yalnız INA226 **gerilimi**
  var. ESC telemetrisi de veri taşımıyor → **motor devri ölçülemiyor**,
  yalnız PWM komutu var.
- **ylp01 pili 12.50 V okuyor** (%0). ylp00 16.60, ylp02 14.60. Kalibrasyon
  çarpanı bunu açıklamıyor (ylp01'inki 0.95061, değeri **aşağı** çekiyor).
  Ya pil derin deşarj ya INA226 kablosu/kalibrasyonu bozuk — **uçmadan önce
  multimetreyle bak.**

**Uçakta değişenler** (üçünde de, `ucus_ayarlari.env`)
`SURU_LIDER_KILIDI=true` · `SURU_LIDER_KILIT_TAM_KADRO_S=8.0` ·
`GOREV_DONUS_YAW=0.0`. Konteynerler yeniden başlatıldı, parametreler
**canlı ölçüldü**. QR tablosu gönderildi ve üç uçakta **konudan** doğrulandı
(`qr_id=1 · 38.69076, 39.16075`).

**Sınandı / sınanmadı**
- Testler: swarm_core 261 · swarm_state_machine 377 · swarm_missions 52
  (7 test yeni davranışa göre yeniden yazıldı, 9 yeni test eklendi).
  flake8'te yeni bulgu yok.
- 🔴 **UÇUŞ YAPILMADI.** Yukarıdakilerin hiçbiri havada doğrulanmadı.
- Kuru test GEÇTİ, en dar an 5.00 m; tek harita `/tmp/yelpence_rota.html`
  (yaw dahil) üretildi ama **operatör onayı alınmadı** — uçuş olmadı.

**Nerede bırakıldı / sıradaki kişi**
1. 🔴🔴 **İLK İŞ: pil log betiğini uçaklardan sil** — `YAPILACAKLAR.md` en
   üstteki P0. Depodan kaldırıldı, uçaklarda duruyor, oturum kapanırken
   hiçbiri ağda değildi.
2. Operatör bu oturumdan sonra **bir Görev 1 testi** yapacak. **Sıradaki
   kişi o testin sonucundan devam eder** — önce operatöre "test ne oldu"
   diye sor, uçuş kaydına ve `docs/DURUM.md`'ye bak.
3. Uçuşta ölçülecekler: ① lider değişimi gerçekten oldu mu (olmamalı)
   ② QR1'de dönülen açı 180°'ye yakın mı ③ faz geçişleri "yakınsadı" mı
   yoksa "zaman aşımı" mı diyor (log satırı: `donus faz N -> N+1`)
   ④ uçaklar arası evre kayması (25 sn idi).

---

## 2026-09-02 09:10 — gece boyu, 5 uçuş

**Ne yapıldı**
- 🟢 **Görev 1 otonom zinciri İLK KEZ uçtu.** Beş uçuşta altı gerçek arıza
  bulundu ve beşi kapatıldı. Zincir artık şuraya kadar çalışıyor:
  `tetik → arm → offboard → takeoff:10 → 10 m → IN_SWARM → ROTATE →
  NAVIGATE → RETURN_HOME`. Aradığımız kanıt geldi:
  **`passthrough` 0'dan 677'ye çıktı** (20 Hz setpoint akışı) — önceki üç
  uçuşta 0'dı, yani formasyon zinciri hiç konuşmamıştı.
- 🔴 **Kapatılan arızalar (hepsi ölçümle):**
  1. `SURU_KALKIS_OLAYLA=false` — görev başlayınca `agent_fsm` ARM ediyor
     ama `takeoff` göndermiyordu; kalkış emrini verecek KİMSE yoktu
     (YKİ'nin guided yolu dağıtıklık için kaldırılmıştı). Ölçüldü: ylp00
     25 sn `ARMED bekliyor: mission_start=False` yazıp yerde bekledi.
  2. **`LANDED` durumu görev tetiğini sessizce yutuyor** — ylp02 11 dk önceki
     bir kill switch'ten LANDED'da mandallanmıştı, tetik geldi, `IDLE`/`ARMED`
     olmadığı için hiçbir şey olmadan çöpe gitti. Log yok, uyarı yok.
  3. **İrtifa çerçeve uyuşmazlığı** — `px4_bridge` hedefi ARM noktasına
     göreli kuruyor (`mevcut_z - 10`), `agent_health_monitor` ise NED
     origin'e mutlak bakıyordu. Origin yerde değil: ylp00 arm z=1,56 →
     **1,06 m açık**, ylp02 0,80 m. Uçaklar 10,0 m'ye çıkıp stabil durdu
     ama "ulaştım" hiç diyemedi → 30 sn timeout → FAILSAFE.
     **Aynı hatanın 3. kopyası** (esp32_bridge POSE ve collision_avoidance
     irtifa kapısında daha önce düzeltilmiş).
  4. **`_from_takeoff` `pending_state` okumuyordu** — on durumun dokuzu
     okuyor, TAKEOFF okumayan tek durumdu. Görev node'unun kalkış sinyali
     yazıldı, LOGLANDI, tick sonunda koşulsuz silindi. Log "oldu" diyordu.
  5. **Hedefsiz setpoint boşluğu** — `_on_rotate`/`_on_navigate` QR konumu
     çözülemeyince `return None` diyordu; komut üreten kimse kalmıyor,
     `passthrough=0`, PX4 OFFBOARD'ı bırakıyor. **Üç uçuş böyle bitti.**
  6. **QR tablosunun mesh yolu yoktu** — alıcı 30 Temmuz'dan beri hazır,
     paketleyici hiç yazılmamış; YKİ tabloyu latched yayınlıyor ve o konuya
     ABONE KİMSE YOK. "Drone'lara Gönder" boşluğa basıyordu.
- 🔧 **ESP32 seri hattı** — ylp00'da `crc_fail=129287` / `alim_ok=4189`
  (%97 çöp) ölçüldü; operatör kabloyla oynadı, sayaç **dondu** ve mesh
  düzeldi. Belirti: uçak ağda ve sağlıklı ama YKİ'ye paket gelmiyor,
  RTCM içeri akmaya devam ediyor (tek yönlü arıza).
- ⚙️ **Pil kesmesi operatör talimatıyla kapatıldı** (B29). İzleme DEĞİL,
  yalnız FSM kesmesi. Sebep ölçüldü: 13,8 V eşiği SAĞLAM pilde ölçülen
  0,57 V çöküşe göre ayarlanmış; **boşalmış pilde çöküş 1,26-1,31 V**
  (ylp00 %33=15,06 V → uçarken 13,80 V). Yarım pille her uçuş kendini
  kesiyordu.

**Ne değişti**
- kod: `agent_fsm_node.py` + `agent_transitions.py` + `agent_context.py` +
  `agent_health_monitor.py` — kalkış kanalı, `pending_state`, pil kesme
  anahtarı, **FAILSAFE sebep logu** (`healthy/offboard/pil/px4_link/xy/z/vxy`)
- kod: `mission1_node.py` `_kalkis_denetle()` · `orchestrator.py`
  `_hedefsiz_tut()` · `mission_transitions.py` `rota_bilinmeyen_s`
- kod: `packet_parser.py` `qr_koord_paketle()` · `esp32_bridge_node.py`
  `_on_qr_coords_out()`
- uçakta: `/ws/ucus_ayarlari.env`'e **dört satır elle eklendi** —
  `SURU_KALKIS_OLAYLA=true` · `GOREV_KALKIS_IRTIFA=10.0` ·
  `BATARYA_KESME=false` · `GOREV_ROTA_BILINMEYEN_S=10.0`
  ⚠️ Bu dosya `dagit.sh` ile GİTMEZ. Ayrıntı `RPI_ESITLEME` B25/B29/B30.
- belge: `RPI_ESITLEME.md` B25-B30 · `DURUM.md` · `YAPILACAKLAR.md`

**Yarım kalan / tuzak**
- 🔴 **RETURN_HOME'da başlık DÖNÜYOR — uçuş elle kesildi, tel riski.**
  `_on_return_home`: `heading = bearing(centroid → home)`. Sürü eve
  yaklaştıkça vektör kısalıyor, sıfıra giderken yön tanımsızlaşıp dönüyor.
  Ölçüldü: merkez (4,4;0,6)→(0,0;0,0) giderken başlık **-106° → -169°,
  5 saniyede 63°**. Slotlar başlığa göre döndüğü için 7 m yarıçaptaki uçak
  yay çizerek süpürüldü: **ylp00 ylp02'nin üstüne gitti**, operatör PosCtl'e
  alıp elle indirdi, uçak az kalsın bahçe teline konuyordu.
  *Öneri (yazıldı, operatör talimatıyla GERİ ALINDI, uygulanmadı):* kalkış
  yönelimini snapshot'la ve RETURN_HOME'da onu kullan → başlık sabit kalır,
  iniş noktaları kalkış dizilişine sabitlenir. Yerde denendi: sapma 63° → 0°.
  **RPi'ler kapalıydı, test edilemedi; sıradaki oturumun ilk işi.**
- 🔴 **QR tablosu firmware'de duruyor.** ROS tarafı bitti ve kanıtlandı
  (`esp32_base`: "QR KONUM TABLOSU mesh'e yayınlandı: 5/5 nokta"), ama baz
  ESP32 firmware'inin **açık beyaz listesinde `TIP_QR_COORDS` yok** →
  sessizce atılıyor. Uçaklarda `bilinmeyen=0, crc_fail=0` (çerçeve hiç
  gelmedi). `mesh_config.h:71` zaten *"0x0F: TIP_QR_COORDS'a rezerve"*
  diyor — slot ayrılmış, iş bitirilmemiş. **Firmware flash gerekiyor.**
  Ayrıca tip başına 50 ms limit var (`MESH_GONDERIM_MIN_MS`); beş QR aynı
  tiple gidiyor, flash'tan sonra aralık gerekebilir — ölçülmeli.
- ⚠️ **Lider ≠ formasyonun ucu.** Bu oturumda karıştırıldı ve yanlış harita
  üretildi. Liderlik `min(effective)` ile agent 1'e gidiyor (doğru çalıştı),
  ama slot ataması **Macar algoritmasıyla en yakın slota** göre. Formasyon
  konumunu tahmin ederken liderliğe bakma.
- ⚠️ **Uçuş öncesi harita:** okbaşı formasyonunda uç MERKEZDE durur, kanat
  **7 m dışarıda** — temiz alan yarıçapı 8,5 m. İlk haritada 5 m demiştim,
  simetrik bölünme varsaymıştım, **yanlıştı.**
- ⚠️ YKİ'yi yeniden başlatırken `yki_durdur.sh` sonrası `pgrep` ile
  **boş olduğunu doğrula**. `ros2 run` sarmalayıcısı ölünce çocuk öksüz
  kalıyor ve `yki_baslat.sh:149` "zaten koşuyor" deyip atlıyor — bu gece
  bir kez yaşandı, kod eski sürümle koşmaya devam etti.
- ⚠️ Baz köprüsü `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` + özel
  `CYCLONEDDS_URI` ile koşuyor; düz `ros2 node info` onu **görmüyor**.
  Sorgularken sürecin ortamını kopyala.

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

## 2026-09-02 04:20 — Eyüp + Claude (HOME DOĞRULAMASI · Görev 1 zinciri kuruldu · pil ölçeği · ÜÇ SESSİZ KİLİTLENME)

> **Uçuş yok — gece boyu yer işi.** Üç commit (`c82ace1`, `abae603`,
> `24e890d`). Kapatılan her şey "hata vermeden yanlış sonuç" sınıfı: hiçbiri
> log'a bakarak görünmüyordu, hepsi ancak uçarken sebebi belirsiz bir
> davranış olarak ortaya çıkardı. Oturum sonunda piller şarja alındı.

**Ne yapıldı**

- 🟢 **HOME DOĞRULAMASI YAZILDI ve UÇAKTA GEÇTİ** (26 Ağustos P0). Home o
  güne kadar hiçbir yerde denetlenmiyordu — `map_home` geleni koşulsuz
  kopyalayıp `home_set=True` yazıyordu. Artık `px4_bridge` 2 sn'de bir
  home'un global kaydını uçağın kendi GPS'iyle karşılaştırıyor, bozuksa
  **RTL'i reddediyor** ve YKİ'ye kritik olay basıyor. Ölçülen: **ylp00
  0,33 m · ylp02 0,17 m**.
  🔴 **04:40 DÜZELTMESİ — ilk sürüm sahada yanlış alarm verdi.** Eşikler
  gürültü bandının içindeydi (RTK YOK!) ve otomatik düzeltme gürültüyü
  kovalıyordu. Üçü birden düzeltildi: eşik **RTK'siz 6,0/5,0 m**
  (RTK'li 1,0/2,0) · **otomatik düzeltme varsayılan KAPALI** · olay
  değeri artık hükmü veren sayı. Ayrıntı `TUZAKLAR` §2.27/§2.29/§2.30.
- 🔴 **İlk sürüm UÇAKTA ÜÇ KUSUR VERDİ, üçü de düzeltildi.** Yerelde 293
  test geçiyordu; hiçbiri bunları yakalayamazdı — dağıtıp koşturmasak
  göremezdik. Ayrıntı `TUZAKLAR` §2.26/§2.27.
- 🟢 **`maneuver_executor` ve `mission1` İLK KEZ AYAĞA KALKTI.** İkisi de
  iki uçakta koşuyor, log temiz. `mission1` belgelere göre bugüne kadar
  hiç çalışmamıştı.
- 🟢 **Pil göstergesi ve uyarıları operatör kararıyla yeniden kuruldu**
  (14,2 V = %0 · 16,8 V = %100). `BATARYA_KRITIK_V` **ilk kez etkin**
  (0,0 → 13,8 V) — KARAR-03'ün koşulu gerçekleşti.
- 🔧 **ylp00'ın MAVROS arızası donanım DEĞİLDİ.** `connected:false` +
  `mavros_router`'da rastgele `remote address`. İki hipotez (baud
  uyuşmazlığı, elektriksel gürültü) **ölçülerek çürütüldü**: 921600'de
  **882 kendini doğrulayan MAVLink çerçevesi/3 sn, sysid 1**, %23,2 sıfır
  baytı. `docker restart` kapattı. 🔴 **ylp02'de aynı belirti görülürse
  ÖNCE restart denenmeli** (`TUZAKLAR` §2.24).

**🔴 ÜÇ SESSİZ KİLİTLENME — hepsi Görev 1 yolunun üzerindeydi**

| # | ne | belirtisi ne olurdu |
|---|---|---|
| 1 | `formation_node`'un **Görev 1** susturma kapısında bayat-bırakma YOKTU (Görev 2 kapısında vardı, aynı fonksiyon 6 satır arayla) | `mission_fsm` manevra adımında ölürse formasyon **süresiz** susar; `maneuver_executor` de yalnız goal aktifken yazdığı için `/raw`'a **hiç kimse** yazmaz. Uçak düşmez, sürü formasyonu **sessizce bırakır** |
| 2 | `expected_agent_count = 3` iken 2 uçak | `formation_reached: 2 ≥ 3` FALSE → sürü **FORMING'de takılır**, `mission1` hiç komut üretmez. 15 Ağustos'ta ölçülmüş, unutulmuş |
| 3 | `baslat.sh` `mission1`'e **kadro geçirmiyordu** | `_snapshot_offsets` `2 < 3` diye `None` döner, `FormationTargetCmd` **hiç üretilmez** |

**Ölçülenler (hepsi uçakta, tahmin yok)**

| ne | değer |
|---|---|
| ylp00 seri hat @921600 | 882 zincirli çerçeve/3 sn · sysid 1 · %23,2 sıfır baytı |
| HOME ↔ kendi GPS | ylp00 **0,48 m** · ylp02 **0,83 m** |
| `HomePosition.position` çerçeve farkı | **19,34 m** ve **0,01 m** — aynı uçak, arka arkaya iki restart |
| `CommandHome` float32 yuvarlaması | **0,180 m** (teorik tavan 0,42 m) |
| RTK'siz konum gezinmesi | **1,17 – 1,27 m** (30 sn arayla, hareketsiz) |
| Pil | ylp00 **14,630 V → %16,2** · ylp02 **15,064 V → %33,2** |
| Kaçınma rütbesi | ylp00 **0 (ÇAPA)** · ylp02 **2 → 1 (YUKARI)** |

**Ne değişti**

- kod: `px4_interface/home_dogrulama.py` **(yeni)** · `px4_bridge`
  (`_home_dogrula` + RTL kapısı + SystemEvent 38/39; otomatik
  düzeltme yazıldı ama **varsayılan KAPALI** — bkz. TUZAKLAR §2.29) · `mavros_command_sender.set_home()` **(yeni yol)** ·
  `formation_control/formation_node.py` (qr_step bayat-bırakma) ·
  `pil/ina226.py` + `ina226_node.py` (gösterge uçları parametreli) ·
  `backend/core/alert_manager.py` (eşikler + dalgalanma bastırması +
  ölçüm-yok kapısı) · `backend/config.yaml` (`alerts.pil: true`) ·
  `deploy/rpi/baslat.sh` (mission1 kadrosu, pil uçları, BATARYA_KRITIK_V) ·
  `src/gcs/ucus_ayarlari.py` (`UCAN_KADRO` + `PIL_*` tek kaynak)
- test: **+46** — `test_home_dogrulama` (17) · `test_formation_node` (10) ·
  `test_ina226` (7) · `backend/tests/test_alert_manager_pil` (12, **YKİ
  backend'inin ilk testleri**)
- 🔴 **uçakta (ylp00 + ylp02, ikisi de `24e890d` seviyesinde):**
  - `/ws/suru_dugumleri`'ne **`manevra`** ve **`gorev1`** eklendi
  - `ucus_ayarlari.env`: `SURU_KADRO="1 3"` · `SURU_BEKLENEN_UCAK=2` ·
    `PIL_BOS_V=14.2` · `PIL_DOLU_V=16.8` · **`BATARYA_KRITIK_V=13.8`**
  - `home_denetle.py` `/ws/` **köküne** kuruldu (`teshis/` altına değil)
  - konteynerler defalarca yeniden başlatıldı
- belge: `TUZAKLAR` §2.24–§2.28 · `RPI_ESITLEME` B7/B20–B23 + kadro notu

**Yarım kalan / tuzak**

- 🔴 **ylp00 roll arızası HÂLÂ AÇIK.** Pil/pervane/motor kontrolü kayda
  geçmedi. Piller şu an şarjda — o ilk maddeyi kapatır, kalan üçü kaldı.
- 🔴 **ylp02'nin havadaki ALTCTL failsafe sebebi hâlâ bilinmiyor.**
- 🔴 **Manevra modu hâlâ uçakta doğrulanmadı** — açık P0, bu oturumda da
  uçulmadı.
- 🔴 **HOME denetiminin GERÇEK bir kaymayı yakaladığı sahada görülmedi.**
  Yalnız "geçti" hâli görüldü; yakalama yolu birim testlerle kanıtlı.
- 🔴 **Görev 1 zinciri yerde tamamlanamaz.** `EXECUTE_QR_TASK`'a (manevra
  adımı) ancak `SYNCHRONIZED_TAKEOFF`'tan geçerek gelinir ve o durumun
  girişi `EVENT_MISSION_STARTED` yayınlayıp sürüyü **ARM eder**. Yani
  BAŞLAT'a basmak = kalkış.
- ⚠️ **Otonom manevrayı `mission1` olmadan sınamak MÜMKÜN ve daha doğru:**
  `gorevfsm`/`gorev1` kapat → `form_yayinla.sh` → `qr_step=2` bas →
  her uçakta `ros2 action send_goal /drone_N/maneuver/execute`. Aynı
  `apply_tilt` matematiği, aynı `/raw` yolu, aynı `px4_bridge:838` datumu.
  🔴 `gorevfsm` AÇIKKEN yapılmaz: `mission_fsm` 5 Hz'de `qr_step=0` basar,
  formasyon susmaz ve `/raw`'a **iki yazıcı** olur.
- 🔴 **ylp01'e HİÇBİR ŞEY dağıtılmadı** — kapalıydı. Üç uçakla teste
  geçmeden önce `RPI_ESITLEME` B20-B23'teki adımlar uygulanmalı, ve
  `UCAN_KADRO` `(1, 2, 3)`'e çevrilmeli (yoksa ylp01 kadroda yok).
- ⚠️ **Gece iniş noktası doğrulaması çözülmedi** (CLAUDE.md §9 kırmızı
  çizgi). Saha aydınlatması sorusu cevapsız.
- ⚠️ İki uçakta **INA226 gerilim çarpanı farklı**: ylp00 `0,98765`,
  ylp02 `1,0`. ~%1,2 ≈ 15 V'ta 0,18 V. Hangisinin doğru olduğu ölçülmedi.
- ⚠️ `.surum` **`+KIRLI`** diyor, oysa ağaç temiz — sebebi izlenmeyen
  `src/px4_autopilot/` (yalnız `COLCON_IGNORE`). Commit'lemek ya da
  `.gitignore`'a almak damgayı dürüst yapar.
- 🟡 ylp00'da `Pi yükü yüksek (5,5)` — gece boyu derleme/restart sonrası.
  Uçuştan önce yerleşmesi beklenmeli.

**Sıradaki adım**

Piller dolunca: **ylp00'ın roll arızasını kapat** (şarjlı pil + pervane/
motor/kol) → `--kuru --harita` → haritayı gözle doğrula → **doğrudan
`ExecuteManeuver` ile manevra uçuşu** (`gorevfsm`/`gorev1` kapalı).
Tek soru: *"manevraya geçince sürü irtifasını koruyor mu?"*

**Uçakların bırakıldığı hâl**

- **ylp00 · ylp02:** açık, ağda, **DISARM**, `AUTO.LOITER`, MAVROS bağlı.
  Kod `24e890d`, bayraklar `origin consensus fsm formasyon ca mod gorevfsm
  pil manevra gorev1` (+ `joystick` yalnız ylp00). Düğüm sayısı 18 / 16.
  🔋 **Piller şarjda** — ylp00 %14 ve düşüyordu, ylp02 %33.
- **ylp01:** kapalı, hiç dokunulmadı, **her şeyde geride.**
- YKİ backend `04:16`'da yeniden başlatıldı, pil uyarıları doğrulandı.

---

## 2026-09-01 22:47 — Eyüp + Claude (KAMERA ONARIMI · jöle ÖLÇÜLÜYOR · RPi paneli düzeltildi)

> **Uçuş yapıldı ama ölçülemedi** (akşam, karanlık). Gün kamera arızasıyla
> geçti; sonunda jöle nitel bir gözlem olmaktan çıkıp **sayıya** dönüştü.
> Operatör 4 gün yoktu, depo 34 commit geride kalmıştı — ileri sarıldı.

**Ne yapıldı**

- 🔧 **Kamera arızası çözüldü.** ylp02'de `No cameras available!`. Teşhis
  yöntemi: **kontrol hattı (I²C) ile veri hattını (MIPI CSI) ayırmak.**
  Yeni takılan modül I²C'ye cevap veriyor ama CSI verisi vermiyordu —
  **modül arızalı.** Eski modül aynı kablo üzerinde 4K dahil her kipte
  kusursuz çalıştı (30,1 fps, sapmasız). Düşüşten zarar görmemişti.
  Flex ve Pi konnektörü de sağlam. Ayrıntı: `KAMERA.md` §12.1.
- 📏 **JÖLE ARTIK ÖLÇÜLÜYOR** — `deploy/rpi/teshis/jole_olc.py` (yeni).
  Doğrusal makaslama (zararsız) ile artık dalgalanmayı (QR'ı öldüren)
  ayırıyor. 28 Ağustos'un dört uçuşu geriye dönük ölçüldü: **yalıtımın
  5-7 kat kazandırdığı bağımsız olarak doğrulandı** (6,0-12,0 → 1,0-2,1 px).
  Motorsuz taban ölçüldü: **0,73 px**.
- 🔴 **Karanlık kayıt tuzağı** — akşam kaydında metrik 4,02 px "dalgalanma"
  uydurdu (kontrast 5,4; gündüz 19-22). Operatör kaydı izledi, dalgalanma
  yoktu. Metriğe **geçerlilik kapısı** eklendi: kontrast < 12 ise sayı
  vermez, "GEÇERSİZ" der. `KAMERA.md` §12.3.
- 🔧 **YKİ RPi paneli düzeltildi.** `ssh_ok:false` veriyordu; sebep SSH
  değil **zaman aşımıydı**. `drone_bul.sh` önbelleği ancak kadronun tamamı
  içindeyse kabul ediyor (26 Ağustos hatası, haklı kural) — ylp01 kapalı
  olduğu için her çağrıda `/24` taranıyordu. Ölçüm: `rpi_durum.sh` 0,8 sn,
  tarama 8 sn, backend sınırı 12 sn, üstelik tarama iki kez ödeniyordu.
  `ip_bul()`'a **tek isim hızlı yolu** eklendi → **8,0 sn → 0,3-0,5 sn.**
- 📶 **Ağ yavaşlığının sebebi ölçüldü** (3 MB/s → 1 MB/s). CPU, disk ve
  sinyal temiz; sebep **airtime çekişmesi**: `rpissid` 2,4 GHz kanal 6,
  aynı kanalda 4 ağ, RTT ort 43,8 ms / tepe 163 ms / jitter 35,8.
  Ham hız 0,86 MB/s, şifre değiştirmek etkilemedi. Uçakla ilgisi yok.
- 🆕 `deploy/rpi/teshis/kamera_teshis.sh` — tek komutluk kamera teşhisi.

**Ne değişti**

- kod: `deploy/yki/drone_bul.sh` — `ip_bul()` hızlı yolu (8 satır + gerekçe);
  `deploy/rpi/teshis/jole_olc.py` (yeni); `deploy/rpi/teshis/kamera_teshis.sh` (yeni);
  `deploy/rpi/dagit.sh` — **`kamera_yayin.py` artık dağıtımda** (elle
  kopyalanıyordu, uçakta iki kopya oluşmuştu). ⚠️ Sadece TAŞINIYOR,
  başlatılmıyor: 4K'da ~1,4 çekirdek yiyor, açılışta kalkması uçuş
  düğümlerini sıkıştırır — bilinçli karar.
- uçakta (**ylp02**): **eski kamera modülü geri takıldı** · `~/kamera_teshis.sh`
  kuruldu · kamera servisi **elle** başlatılıyor (otomatik değil) ·
  28 Ağustos kalibrasyonu korundu (`sport`, `2.5923,1.2225`)
- belge: `KAMERA.md` (§12 yeni, §10 ve §11 genişledi), `DURUM.md`,
  `YAPILACAKLAR.md`, `GUNLUK.md`

**Yarım kalan / tuzak**

- 🔴 **ylp02'de MAVROS PX4'e BAĞLI DEĞİL.** `connected:false`, `mode:"?"`,
  `imu/baro/mag_healthy` **üçü de False**, `imu/mag` ve `raw/fix`
  konularında yayın yok. Barometre ve IMU iç mekânda da çalışır — bu
  "GPS yok" değil, **FCU ile konuşulmuyor.** Açık P0 olan **gevşek PX4
  güç soketiyle** aynı sınıf ve uçak bugün çok elden geçti.
  *Operatör: "GPS'i ben çözerim" dedi, oturum sonunda açık bırakıldı.*
- ✅ ~~`kamera_yayin.py` dağıtımda değil, uçakta iki kopya~~ → **KAPANDI.**
  `dagit.sh`'e eklendi; bayat kopya `~/kamera_yayin.py.bayat_28agu` adına
  alındı (silinmedi).
- ⚠️ **Kamera servisi kendiliğinden başlamıyor.** Açılıştan sonra:
  `ssh yelpence02@<ip> 'setsid nohup python3 ~/yelpence_ws/kamera_yayin.py > /tmp/kamera_yayin.log 2>&1 < /dev/null &'`
- ⚠️ **Modül değişince KAPAT-AÇ şart.** `imx477` sürücüsü sensörü yalnız
  açılışta bağlıyor; çalışan Pi'de değiştirmek ölçümlerin hepsini
  yanıltıyor. Elle `bind` de çözüm değil (denendi, akış kırık geldi).
- ⚠️ **`dmesg` taşabiliyor**, açılış satırları siliniyor → yanlış sonuç.
  Doğrusu `journalctl -k -b 0`.
- ⚠️ 4K'da tarayıcı sekmesi açıkken CPU %91, arayüz cevap veremiyor.
  Kayıt alırken sekme kapalı olmalı.
- 🔴 Uçuş kaydı **karanlıkta** çekildi, jöle hakkında hiçbir şey söylemiyor.
  Flex hipotezi **sınanmadı**.

**Sıradaki adım**

- **Gündüz** bir uçuş + flex servis kıvrımı denemesi. Ölçüt `jole_olc.py`;
  28 Ağustos seviyesi **1,04 px**, motorsuz taban **0,73**, hedef **≤ 0,8**.

**Uçakların bırakıldığı hâl**

- ylp00: açık, ağda (`10.38.209.134`), mesh'te, GPS **28 uydu** fix 3,
  pil %55, konteyner 9 saattir ayakta, sağlıklı
- ylp01: **kapalı**, ağda değil
- ylp02: açık, ağda (`10.38.209.189`), **kamera çalışıyor**, pil %53,
  🔴 **MAVROS PX4'e bağlı değil**, disk %75

---

## 2026-09-01 11:30 — Operatör + Claude (🟢 sürü hareketi UÇTU · 🔴 iki saha olayı)

> **Uzun saha oturumu.** Dört kod düzeltmesi yazıldı, test edildi, dağıtıldı ve
> üçü uçakta doğrulandı. İki uçak olayı yaşandı; ikisi de ölçüldü, biri
> yazılım kaynaklıydı ve düzeltildi, diğeri **hâlâ açık.**

**Ne yapıldı**

- 🟢 **SÜRÜ HAREKETİ ARTIK ÇALIŞIYOR.** Önceki uçuşta çubuk verilince yalnız
  pilot uçağı hareket ediyordu (ölçüldü: ylp00 2,82 m, ylp01 0,40 m,
  ylp02 0,25 m). Sebep: mesh `deadman_timeout_s` taşımıyor, komşulara 0.0
  gidiyordu → `command_active` hep False → `READY → MOVEMENT` hiç olmuyordu.
  Düzeltildi; bu oturumdaki uçuşta formasyon geçişleri ve sürü hareketi
  **operatör onayıyla "güzel çalışıyor"**, kalkış/iniş de sorunsuz.
- 🟢 **Morf hızı seyirden ayrıldı** (`MOD_MORF_HIZ=0,6 m/s`). 31 Ağustos'ta
  iki uçak 1,65 m'ye yaklaşmıştı; kapanma 4,13 m/s idi ve 4 m'lik eşiğin
  2,38 m'si frenlemeye gidiyordu (teori ile ölçüm 3 cm uyuştu). 0,6 m/s ile
  frenleme 0,20 m, kaçınmaya 3,80 m kalıyor.
- 🟢 **Kaçınmaya "dikey ayrım kurulana kadar yaklaşma yok" eklendi**
  (`KACINMA_DIKEY_BEKLE=0,8`) — operatör önerisi. `ca_core`'un kendi ölçüm
  tablosu dikey kipin yüksek kapanma hızlarında çöktüğünü gösteriyordu;
  sebep ayar değil ZAMAN. Yaklaşma bileşeni silinince dikey kaçış aradığı
  zamanı buluyor. Tüm yatay hız değil, **yalnız komşuya doğru olan bileşen**
  siliniyor (yoksa sürü çubukla ilerlerken uçak formasyondan kopar).
- 🟢 **Yaw hızı türetildi** (25 → **14,7 °/s**). Tutarsızdı: 25°/s, 7 m slot
  yarıçapında 3,05 m/s teğet hız istiyordu, seyir tavanı 2,0 m/s. Formasyon
  dönüş boyunca dağılırdı. Artık PX4 tavanı ile formasyon geometrisinin
  küçüğü alınıyor — hakem 12 m derse kendiliğinden düşer.
- 🟢 **Madde 29 (aralık/irtifa girişi) uçakta doğrulandı**, YKİ'den mesh
  üzerinden görev başlatma çalıştı (`mod_test` silindikten sonra G2-K10'un
  üçüncü kapısı gerçekten işledi).
- 🟢 **ylp02 diski temizlendi:** %90 → %66 (3,0 → 9,6 GB). Uçuş kayıtlarına
  dokunulmadı; kamera ham videoları (4,7 GB, hepsi 28 Ağu) operatör onayıyla
  silindi. Kaçak `mavros.log` silinmedi, **gzip'lendi** (557 MB → 2,7 MB).

**🔴 İKİ SAHA OLAYI**

**① ylp02 saha dışına düştü (manevra modu) — SEBEP KISMEN AÇIK**

İki ayrı şey üst üste geldi:

*(a) BİZİM HATA — düzeltildi.* Manevraya geçişte üç uçak da ~1,7 m alçaldı.
`px4_bridge.py:838` zemin ofsetini **tüm** setpoint'lere uyguluyordu; oysa o
kural guided goto için doğru, formasyon/manevra **mutlak NED** gönderiyor.
Ölçüm: `sp.z = −6,97` + zemin `1,68` → PX4'e giden hedef **−5,29**.
Hareket modunda görünmüyordu çünkü maske hız modundaydı ve PX4 konumu hiç
kullanmıyordu — **gizli hata**, manevra maskeyi konuma çevirince gerçekleşti.

*(b) AÇIKLANAMAYAN — HÂLÂ AÇIK.* ylp02'de PX4 `Failsafe activated` verdi ve
**ALTCTL**'e düştü (konum kestirimi geçersiz → PX4'ün geri düşüş modu).
ALTCTL'de yatay tutma yok, uçak sürüklendi. Elenenler: RC kanalları sabit ve
rssi 41 (kimse switch'e dokunmadı, link kopmadı) · setpoint 50 Hz akıyordu ·
kaçınma hiç devreye girmedi (`avoid=0`). `px4_bridge` modu geri zorlamadı —
o kapı doğru çalıştı. Düşüş sonrası `Found 0 compass`; Here4 konnektörü
**elle sarsıldı, arıza tekrar üretilemedi** (pusula 10 Hz sabit, kopma 0).
**Sebep bilinmiyor.**

**② ylp00 kalkışta kendini yere bıraktı — YAZILIM DEĞİL**

PX4: `Takeoff detected` → 5,6 sn sonra **`Attitude failure (roll)`** →
`Failsafe activated`. **İkinci denemede birebir tekrarladı.** Uçak fiziksel
olarak yattı. Kill switch 168 sn SONRA, uçak zaten yerde ve disarm'ken
basıldı — sebep değil. Not: motor kalkışında pil **15,29 → 14,72 V** çöktü
(0,57 V, 3,68 V/hücre) — uçuş öncesi uyarılmıştı, pil %58'di.
🔴 **Manevra düzeltmesi bu uçuşta HİÇ SINANMADI** (uçak READY'ye ulaşmadı).

**Ne değişti**

- kod: `px4_bridge.py:838` — zemin ofseti yalnız guided goto'ya
  (`not sp.heading_valid`); `mode_manager_node._on_control_command` —
  `deadman_timeout_s` 0 gelirse yerel politika (0,5 sn);
  `mode_manager_node._morf_hizini_uygula` + yeni saf modül `morf_kilidi.py`;
  `ca_core._dikey_bekleme_projeksiyonu` + `dikey_bekle_orani` parametresi;
  `ucus_ayarlari.py` — `MOD_MORF_HIZ=0,6`, `MOD_YAW_HIZI` türetildi,
  `KACINMA_DIKEY_BEKLE=0,8`, `MOD_ARALIK` 9→7 (KARAR-14), üç yeni tutarlılık
  denetimi. Ayrıca `hatalar`→`hata` (çalışmayan bir denetim, NameError atardı).
- uçakta: **`/ws/mod_test` SİLİNDİ** (üçünde de) — görev YKİ'den
  başlatılmadan sürü READY olmuyor. Yeni parametreler: `morf_hiz_mps=0.6`,
  `morf_sure_s=25.0`, `deadman_zaman_asimi_s=0.5`, `max_yaw_rate_deg_s=14.7`,
  `dikey_bekle_orani=0.8`, `default_spacing_m=7.0`, `kalkis_irtifa_m=5.0`.
  `md5` üç uçakta da depoyla birebir aynı.
- belge: `gorev2.md` §7.16/§7.17/§7.18, `DURUM.md`, `RPI_ESITLEME.md`
  §4 (B10/B12/B13), `KARARLAR.md` (KARAR-14), `YAPILACAKLAR.md`.

**Yarım kalan / tuzak**

- 🔴 **ylp00 uçmasın**: iki bağımsız denemede aynı roll arızası. Önce şarjlı
  pil, sonra pervane/motor/kol kontrolü.
- 🔴 **ylp02'nin failsafe sebebi bilinmiyor.** PX4 ulog'u kapalı
  (`CLAUDE.md`: Pixhawk'ta log açma), o yüzden gerekçe okunamıyor.
- 🔴 **Manevra düzeltmesi UÇAKTA DOĞRULANMADI.** Kod ve testler hazır,
  dağıtıldı, ama hiçbir uçuş manevra moduna ulaşmadı.
- 🟠 `test_kacinma_korlugu.py`'de **9 test kırık** — benim işimle ilgisiz:
  test dosyası 21 Ağu, düğüm 25 Ağu commit'li, düğüm değişmiş testler
  güncellenmemiş. Kırıklar uçuşta kapalı olan tutma mekanizmasını kapsıyor.
- 🟠 **KARAR-14 açık**: varsayılan aralık 7 m (operatör) mü 9 m (ölçüm) mü.
  Şu an 7. Formasyon geçişli uçuşta YKİ kutusuna 9 yazmak yeterli.
- 🟠 **Şartname örnek aralığı 5 m** ama kaçınmanın çıkış eşiği 6,5 m — hakem
  "5 metre" derse kaçınma bir kez açılınca **hiç kapanmaz.** Eşikler Görev 2
  için gözden geçirilmeli (KARAR-12 ile ilişkili).
- 🟢 KARAR-03'ün koşulu gerçekleşti: INA226 üçünde de çalışıyor, pil
  failsafe'i artık açılabilir.
- Bugünün hiçbir değişikliği **commit edilmedi** (`.surum` = `bc42d00+KIRLI`).

**Sıradaki adım**

- ylp00'ın roll arızasını kapat (pil + mekanik), sonra **manevra modunu
  doğrula** — tek soru: "manevraya geçince sürü irtifasını koruyor mu?"

**Uçakların bırakıldığı hâl**

- ylp00: **yerde, roll arızalı, uçmaya hazır DEĞİL.** Pil %58 (15,26 V).
  Konteyner ayakta, kod güncel.
- ylp01: sağlam, pil %58 (15,32 V), konteyner ayakta, kod güncel.
- ylp02: **düştü ama kırık yok**, şu an sağlıklı (pusula 10 Hz, RTK).
  Pil yeni (%91, 16,49 V). Havadaki failsafe sebebi bilinmiyor — tekrar
  uçurmadan önce karar verilmeli. Disk %66.

---

## 2026-08-31 16:24 — Osman + Claude (🟢 ÜÇ UÇAKLI KALKIŞ/İNİŞ BAŞARILI + formasyon hazırlığı)

> **Uçuş yapıldı, pervaneli, üç uçak.** Dört kusur kapatıldı, dördü de
> sahada doğrulandı. Uçuş sonrası uçaklar kapatılıp şarja alındı.

**Ne yapıldı**
- 30 Ağustos yalpalamasının kökü bulundu: **px4_bridge emniyet pilotuyla
  kavga ediyordu.** PX4 statustext'inde 13 kez "Pilot took over using
  sticks"; 20 sn içinde 6 mod değişimi (AUTO.LAND↔POSCTL); istenen roll
  ±19,5°, **gerçek pitch −27,4°**. Sebep: `land` dalında pilot kapısı yoktu
  ve mode_manager 1 Hz'de inişi tekrarlıyordu.
- Üç uçaklı ilk denemede (12:50) sürü **8,38 m'den 0,36 m'ye** kapandı.
  Rosbag'den kök sebep: `mode_manager` FORMATION_UNKNOWN dalı ofsetleri
  **her yayında** (~19 Hz) yeniden ölçüyor, `formation_node` ise onları
  heading ile **döndürüyordu** → içe doğru sarmal.
- Ayrı bir kusur: gaz çubuğu yaylı değil, dipte duruyor → `throttle_cmd =
  −1,00` sabit → `vz = +2,00 m/s` doyumda. B18 kapısı tek atışlık mandal
  olduğu için tutmuyordu.
- Operatör kararı: **VrB formasyon ANA ANAHTARI** olsun (yalnız değişim
  kilidi değil). Ölçüldü: VrB → ch10 → `aux6`, PWM 1000..2000, çapraz
  karışma yok.
- 15:52 uçuşu: **üç uçak birlikte kalktı (0,24 sn), 5 m'de 20 sn asılı
  durdu, birlikte indi (0,14 sn).** Dört düzeltmenin dördü de doğrulandı.
- Uçuş sonrası: tırmanış sürüklenmesi araştırıldı, formasyon geçişi için
  aralık ölçümle 9 m'ye çıkarıldı, kuru testteki geometri boşluğu kapatıldı.

**Ölçülen — dünle yan yana**

| | 30 Ağustos | 31 Ağustos 15:52 |
|---|---|---|
| Kalkan uçak | 1 / 3 | **3 / 3** |
| En dar uçak arası | **0,36 m** | **6,70 m** (sabit) |
| Gerçek roll / pitch tepe | 19,5° / **−27,4°** | **3,3° / 5,3°** |
| Mod kavgası | 6 geçiş | **0** |
| Sürüye giden dikey komut | **−1,00** | **+0,00** |

🔴 **Dikey mandalın kanıtı kontrollü:** ham gaz kanalı (ch3) uçuşun
tamamında **1000 (dipte)** ölçüldü — yani dünkü arıza koşulu birebir
tekrarlandı — ama sürüye giden değer 0,00 kaldı.

**Ne değişti**
- kod: `px4_bridge.py` — `land`/`rtl` dallarına `PILOT_FLIGHT_MODES` kapısı
  (ilk `land` geçer, tekrarlar pilota boyun eğer); `_kalkis_kilidi_aktif`
  docstring'i **ölçümle düzeltildi** ("birkaç santim" → 0,18–2,17 m)
- kod: `mode_manager_node.py` — FORMATION_UNKNOWN dalı: ofsetler bir kez
  ölçülüp **donduruluyor** + heading ile **ters döndürülerek** gömülüyor
- kod: `joystick_interpreter_node.py` — VrB ana anahtarı + **dikey yetki
  mandalı** (`command_valid`'e dokunmaz, o G2-K10 kapısı)
- kod (yeni): `mode_manager/formasyon_kilidi.py` — saf mantık + `talep_hesapla`
- kod: `packet_parser.py` + `esp32_bridge_node.py` — `formasyon=0` artık
  **meşru** ("formasyon yok"); düşürme koşulu *iki alan da sıfır*a daraltıldı
- kod: `ucus_ayarlari.py` — `MOD_KALKIS_IRTIFA_M` 8→5, **`MOD_ARALIK_M` 7→9**
- kod: `gorev_kanit_ucus.py` — **`--aralik` bayrağı** (kuru testin geometrisi
  uçulan geometriyle eşleşmiyordu)
- kod: `kumanda_web.py` — "ŞU AN NE OLUR" senaryo paneli
- test: `test_formasyon_kilidi.py`, `test_formasyon_sarmali.py` (yeni, 26 test)
- uçakta: üç uçağa `swarm_control` + `swarm_state_machine` dağıtıldı,
  konteynerler yeniden başlatıldı, md5'ler yerelle **birebir** doğrulandı.
  `/ws/ucus_ayarlari.env` → `MOD_KALKIS_IRTIFA=5.0`
- belge: GUNLUK · DURUM · YAPILACAKLAR · TUZAKLAR (§3.16–3.18) · KARARLAR

**Yarım kalan / tuzak**
- 🔴 **`MOD_ARALIK=9.0` uçaklara HENÜZ GİTMEDİ.** Uçuştan sonra değiştirildi,
  uçaklar o sırada kapalıydı. Formasyon uçuşundan önce env dağıtılmalı ve
  konteynerler yeniden başlatılmalı — yoksa uçakta 7 m geçerli kalır.
- 🟡 `kumanda: None` — YKİ'deki sanal kumanda paneli hâlâ boş. Yerine
  `http://<pi>:8090` kullanıldı.
- 🟡 ylp02 diski **%88** (3,6 GB) — finalden önce temizlenmeli.
- ⚪ Titreşim ölçümü **atlandı** (operatör kararı) — pervane balansı sınanmadı.
- ⚪ Kaçınma 3 m altında kör (`altitude_gate_m=3.0`); bu uçuşta karşılaşma
  olmadığı için devreye girmedi. Ayrı karar.

**Sıradaki adım**
- Kumandadan formasyon: kalk → VrB aç (formasyon oluşsun) → SwC ile geç →
  VrB kapat (uçaklar dursun) → in. Ön koşullar YAPILACAKLAR P0'da.

**Uçakların bırakıldığı hâl**
- ylp00 · ylp01 · ylp02: **kapalı, şarjda.** Pervaneler takılı. Konteynerler
  kapalı (Pi'ler kapalı). Kod üçünde de güncel; **env'de aralık eski (7 m).**

---

## 2026-08-31 06:20 — Osman + Claude (DAĞITIM + YER DOĞRULAMASI, üç uçak)

> **Uçuş yok, pervaneler sökük.** 🔴 **Kill switch hiç aktif değildi** —
> bu, ylp00'ın gerçekten armlanmasına yol açtı ve beklenmedik biçimde
> madde 24'ün kanıtı oldu. Üç uçak da açıktı, hepsine dağıtım yapıldı.

**Ne yapıldı**

- **Aşama D üç uçağa dağıtıldı** (`swarm_state_machine` + `swarm_control`),
  `/ws/suru_dugumleri`'ne **`gorevfsm`** eklendi, `ucus_ayarlari.env`
  güncellendi. Parametreler doğrulandı: `kalkis_irtifa_m=8.0`,
  `swc_debounce_ms=1300`, `mission_fsm.agent_id=1`,
  `gaz_merkez_pay` artık **joystick**'te (yanlış düğümdeydi).
- 🔴 **İKİ GİZLİ KİLİTLENME bulundu ve kapatıldı — ikisi de "hata vermeden
  yanlış sonuç" sınıfı:**
  - **`home_set` mesh'te taşınmıyordu.** `mission_fsm` PREFLIGHT için
    `all_agents_home_set()` istiyor ama komşuların durumunu mesh'ten
    okuyor; alan pakette yoktu, hep `false` geliyordu.
    **Görev 2 hiç başlayamazdı.** Ölçüm: ylp01 kendi içinde `true`,
    ylp00'ın mesh kopyasında `false`.
  - **Görev başlatma tek uçağa ulaşıyordu.** `TriggerMission` bir ROS
    servisi, `ROS_LOCALHOST_ONLY=1`. Ölçüldü: ylp00 armlandı, ylp01/ylp02
    *"YETKI YOK (mission_state=1)"* deyip reddetti — **sürü bölündü.**
  - İkisi de `bayraklar2`'deki boş bitlerle çözüldü; **paket 16 bayt
    kaldı**, firmware'e dokunulmadı, geriye dönük uyumlu.
- **G2-K11 (operatör kararı): görev başlatma MESH'ten yayılır.** Ölçülen:
  tek tetikten üç uçağa **~1 sn**. Her uçak KENDİ preflight'ını koşuyor —
  komşu "sen de geç" demiyor, "ben geçtim" diyor. ⚠️
  `EVENT_MISSION_STARTED` **kullanılmadı**: `agent_fsm` onu ARM'a çeviriyor.
- ✅ **MADDE 24 GERÇEK KOŞULDA DOĞRULANDI (kazara).** Kill switch aktif
  olmadığı için ylp00 pervanesiz armlandı ve `takeoff:8.0` hedefine girdi —
  30 Ağustos'un birebir aynısı. Fark: **SwD-aşağı anında indirdi**
  (`land` 1 Hz → `AUTO.LAND` → DISARM). 30 Ağustos'ta pilot hiçbir tuşla
  durduramamış, olay 42-95 sn sürmüştü.
- ✅ **G2-K10 üçüncü kapı çalıştı** — bölünmüş sürü kalkışını önledi.
- **Kuru test uçuşu DURDURDU ve haklıydı:** ilk dizilimde en yakın çift
  **0,98 m** (eşik 4,0). Uçaklar açıldıktan sonra **4,53 m → GEÇTİ**.
  Kullanılan senaryo: `--senaryo asili --dronelar 1,2,3 --irtifa 8`
  (yeni senaryo gerekmedi; `plan_kur_asili` zaten N uçağa genelleştirilmiş).
- **Tarayıcı arayüzü yazıldı** (`src/gcs/kumanda_web.py`) — terminal
  ölçümleri üst üste boşa gitmişti ve sebebi teknikti: `grep` boru ucunda
  **blok tamponluyor**, talimat operatöre kayıt bittikten sonra ulaşıyordu.

**Ne değişti**

- kod: `packet_parser` (+2 bit) · `esp32_bridge` (görev durumu abonesi +
  yayılım yayıncısı) · `mission_fsm_node` (yayılım tetiği + `agent_id`) ·
  `rc_eksen` (**TERS_YAW=False**) · `swc_debounce` (1300 ms)
- **uçakta:** üçüne de dağıtım + `gorevfsm` bayrağı + yeni env.
  ⚠️ ylp00'da `kumanda_web.py` elle koşuyor (port 8090, restart'ta ölür)
- belge: `gorev2.md` §7.13 + G2-K11 · `DURUM.md` · `YAPILACAKLAR.md`

**Yarım kalan / tuzak**

- 🔴 **Pervaneli uçuş YAPILMADI** — kalkış zincirinin son halkası bu.
- ⚠️ **`active_formation` ÇİZGİ'de kaldı** (SwC denenirken ayarlandı).
  Uçuştan önce **konteynerleri yeniden başlat**, yoksa READY'de sürü
  çizgi slotlarına koşar ve iniş noktaları değişir.
- ⚠️ **Görev ABORT'unun yayılıp yayılmadığı ÖLÇÜLMEDİ.** Başlatma yayılıyor;
  iptal muhtemelen her uçakta ayrı gerekiyor.
- 🔴 **SwA bu kumandada AŞAĞI = AÇIK**, kill kumandasıyla ters. Reverse
  denendi, o kanala işlemedi. Değiştirilmedi — çünkü *kilitli = 1000 =
  failsafe* hizası korunmak zorunda. **Pilot brifingine yazılacak.**
- **madde 29 taşıma yolu kararı** hâlâ operatörde.

**Sıradaki adım**

Pervaneleri tak, uçakları **7 m** aralıkla aynı yöne diz, **kill pilotunun
kumandasını AÇ**, konteynerleri yeniden başlat, `--kuru --harita` tekrarla,
haritayı gözle doğrula → **kalk · asılı dur · in.**

**Uçakların bırakıldığı hâl**

- Üçü de ağda, **DISARM**, pervaneler **sökük**, üçünde de
  `mission_state = 8` (**üçüncü kapı AÇIK — SwD üç uçağı birden armlar**).
- ylp00 son olarak `AUTO.LAND` modunda disarm oldu; SwD aşağıdaydı.
- Bayraklar: `origin consensus fsm formasyon ca mod gorevfsm` (+ `joystick`
  yalnız ylp00), `/ws/mod_test` üçünde de takılı.
- ylp02 diski **%82**.

---

## 2026-08-31 03:40 — Osman + Claude (Görev 2 AŞAMA D BİTTİ + kumanda değişti)

> **Uçuş yok, pervaneler sökük, kill pilotu hazırdı.** Uçaklara **hiçbir kod
> dağıtılmadı.** Yalnız ylp00 açıktı; bütün ölçümler onunla yapıldı.
> 🔴 **Sürü kumandası değişti** — kumandaya özgü üç sabit yeniden ölçüldü.

**Ne yapıldı**

- **Kritik yolun kod tarafı bitti:** madde **24 → 25 → 27 → 28**, artı **B19**.
  - **25 (kumandadan kalkış):** G2-K10 kararı alındı — SwD tek harekette
    `arm` + `takeoff:H`, **üç kapıyla** (SwA açık · gaz merkezde · görev
    YKİ'den başlatılmış). Komut `agent_fsm`'e değil **doğrudan
    px4_bridge**'e; iniş yolunun (madde 24) aynısı, aynı gerekçe.
  - **27 (`mission_fsm`):** açılmadan önce **üç engel** bulundu ve kapatıldı
    (§7.8). En ağırı: düğüm **kendi durumunu public konudan** bekliyordu —
    G0 madde 18'in birebir aynısı, PREFLIGHT hiç geçilmezdi.
  - **28 (YKİ BAŞLAT):** panel Görev 2 için **yanlış bilgi gösteriyordu**
    (*"kumandadan başlatılır"*), buton açıldı. `_call_trigger_mission`
    kaldırıldı — ölçülen sebep: `ROS_LOCALHOST_ONLY=1` yüzünden o servis
    **yalnız ylp00'ın** mission_fsm'ine ulaşıyor, ikinci denemede iki uçak
    kalkıp biri yerde kalırdı.
  - **B19:** COMPLETED → IDLE çıkışı yazıldı; görev başına 3 hak var,
    eskiden ikinci kalkış konteyner restart istiyordu.
- 🔴 **SÜRÜ KUMANDASI DEĞİŞTİ.** Eski alıcı link kaybında i-BUS'ta **son
  çerçeveyi tutuyordu** ve deadman düşmüyordu (B20, dört bağımsız teyit) —
  yani kumanda kaybında sürü durmuyor, **son çubuk komutuyla uçmaya devam
  ediyordu**. Uçuş engeliydi. Operatör yeni kumanda bind etti; **yeni alıcı
  failsafe'i i-BUS'a uyguluyor** → CH5 1000'e düşüyor ve kalıcı kalıyor.
  **B20 kapandı.**
- **Kumandaya özgü üç ölçüm yenilendi** (§7.12):
  - 🔴 **madde 17 — `TERS_YAW` True → False.** Yeni kumandada yaw sağa
    **2000** (üst uç) veriyor; eskisinde 1014'tü. Güncellenmeseydi **pilot
    sağa çevirir, sürü sola dönerdi.** Regresyon testi eklendi.
  - **madde 26 — SwC debounce 500 → 1300 ms.** İki kayıt çelişti (tavan 852
    vs 321). 852'nin geçiş mi duraklama mı olduğu **çözülmedi**; hata yönü
    asimetrik olduğu için (düşük eşik → sahte V morfu → −20×N) güvenli taraf
    seçildi.
  - **madde 30 — kapandı** (yukarıda).
- **İki ölçüm aracı yazıldı:** `src/gcs/kumanda_olc.py` (terminal) ve
  🔴 **`src/gcs/kumanda_web.py`** — uçakta koşan, tarayıcıdan kullanılan
  arayüz. Terminal ölçümleri üst üste boşa gitti ve sebep teknikti:
  **`grep` boru ucunda blok tamponluyor**, "şimdi başla" talimatı operatöre
  kayıt bittikten sonra ulaşıyordu. Arayüz o sorunu tamamen kaldırdı;
  sonuçlar uçakta `/tmp/kumanda_sonuc.jsonl`'e yazılıyor.
- **madde 29'un enabling yarısı:** `ros2 param set` bu düğümlerde **sessiz
  bir no-op'tu** (parametre geri çağrısı yoktu, değer `__init__`'te
  kopyalanıyordu). Kapı `canli_param.py`'ye yazıldı: canlı olan yalnız
  `default_spacing_m` ve `kalkis_irtifa_m`; kapılar ve kimlik reddediliyor.

**Ne değişti**

- kod: `mode_manager_node` (kalkış komutu + 1 Hz tekrar + READY'de centroid
  tazeleme) · `mode_context` · `mode_transitions` · `joystick_interpreter` ·
  `mission_fsm_node` + `mission_transitions` · `MissionPanel.tsx`
- **YENİ dosyalar:** `canli_param.py` · `swc_debounce.py` ·
  `test_swc_debounce.py` · `kumanda_olc.py` · `kumanda_web.py`
- 🔴 `rc_eksen.py` — **`TERS_YAW = False`** (yeni kumanda ölçümü)
- `ucus_ayarlari`: `MOD_KALKIS_IRTIFA_M=8.0` · `MOD_SWC_DEBOUNCE_MS=1300`
  (+ iki tutarlılık denetimi) · `baslat.sh` buna göre
- test: 243 → **276**. `gaz_merkez_pay` yanlış düğüme veriliyordu, düzeltildi
- **uçakta: HİÇBİR KOD DEĞİŞMEDİ** — dağıtım yapılmadı

**Yarım kalan / tuzak**

- 🔴 **DAĞITIM ZORUNLU VE ARTIK TEHLİKELİ SEVİYEDE.** Uçaklardaki kod hâlâ
  `TERS_YAW = True`. Dağıtmadan uçulursa **yaw ters çalışır.**
  Tek paket yeter (`swarm_state_machine`); `/ws/suru_dugumleri`'ne
  **`gorevfsm`** eklenecek (üçüne) ve `MOD_SWC_DEBOUNCE_MS=1300` env'e.
- 🔴 **ylp00'da mavros SEGFAULT verdi** (21:12 yeniden başlatması sonrası).
  Yığın 11 yerine 2 düğümle kaldı. RC ölçümlerini engellemedi ama
  px4_bridge mavros'suz iş göremez — **dağıtımdan önce bakılmalı.**
- ⚠️ ylp00'da `kumanda_web.py` elle başlatıldı (port 8090, salt okur).
  `baslat.sh` bilmiyor; konteyner restart'ında kaybolur.
- **madde 29'un taşıma yolu kararı OPERATÖRDE:** (a) `aralik_ayarla.sh`
  betiği *(öneri)* ya da (b) YKİ alanı + backend SSH. `gorev2.md` §5.
- ⚠️ ylp02 diski **%81** (30 Ağustos ölçümü).

**Sıradaki adım**

**DAĞITIM + YERDE DOĞRULAMA.** Üç uçak da açılınca tek dağıtım, sonra
`gorev2.md` §4 Aşama E: uçuş A (madde 31). Kritik yolun kod tarafı bitti.

**Uçakların bırakıldığı hâl**

- **Yalnız ylp00 açıktı**, DISARM, pervaneler **sökük**, kill pilotu hazırdı.
- ylp00 oturum sırasında **yeniden başladı** (Pi uptime sıfırlandı);
  `baslat.sh` koştu ama **mavros çöktü**.
- Bayraklar değişmedi: `origin consensus fsm formasyon ca joystick mod`,
  `/ws/mod_test` takılı.
- ylp01 ve ylp02 **kapalı** — bugün hiç dokunulmadı.

---

## 2026-08-30 15:52 — Osman + Claude (madde 24 kodu + `gorev2.md` devir teslim)

> **Uçuş yok, uçaklara kod DAĞITILMADI.** Şartname G6 doğrulandı, madde 24
> (kumandadan iniş) yazıldı ve birim testle kilitlendi, `gorev2.md` devretmek
> için sadeleştirildi. 🔴 **Görev 2 başka arkadaşlara devrediliyor.**

**Ne yapıldı**

- **Şartname §5.2 PDF'ten yeniden okundu** (operatör sorusu: "geri kalkışın
  kumandayla olması gerekmiyor muydu?"). **Doğru hatırlanmış, iki yerde geçiyor:**
  §5.2.2 *"Takeoff ve land komutları da kumanda üzerinden yapılır"* ve senaryo
  madde 5 *"Kumanda üzerinden kalkış komutu ile sürü, **başlangıç formasyonunu
  koruyarak** belirlenen irtifaya yükselir"*.
  → Planımız uygun (madde 25, kritik yolda). Altyapı da hazır: `px4_bridge`
  `takeoff:H` kabul ediyor ve kalkışta **yatay çapayı donduruyor**, yani
  tırmanış dikey. Kalkış kapısı da ofsetleri **ölçülen** konumdan tohumluyor —
  senaryo madde 1 (*"hakemler yerde dizer"*) ile örtüşüyor.
- 🔴 **G1'in teşhisi YANLIŞTI, ölçülerek düzeltildi.** Belgede *"olay
  yayınlanıyor, tüketicisi yok"* yazıyordu. **Tüketici var:**
  `LANDING → EVENT_EMERGENCY_LAND → agent_fsm.pending_state = LANDING`.
  Ama `agent_transitions` bunu **yalnız 3 durumdan** kabul ediyor
  (`IN_SWARM:207`, `RETURN_HOME:316`, `FAILSAFE:387`) ve olay sırasında
  uçaklar **ARMED**'daydı; `agent_fsm_node.py:232` tick sonunda isteği
  **koşulsuz siliyor** → istek tek tick yaşayıp **sessizce kayboluyor.**
  *"Kumandanın hiçbir tuşuyla iniş veremedim"*in birebir açıklaması bu.
- **Madde 24 yazıldı — dört ayrı kusur kapandı:**

  | | Neydi | Sonucu olurdu |
  |---|---|---|
  | a | LANDING yalnız olay yayınlıyordu | ARMED'dayken iniş **hiç gitmiyordu** |
  | b | İniş bayrağı **tek tick** yaşıyordu | mesh'in 200 ms kapısı iptali **tamamen** yutardı |
  | c | SwA kapalıyken `cmd.land` **siliniyordu** | pilot önce SwA'yı kapatırsa **bir daha inemezdi** |
  | d | LANDING'de `formation_node` susmuyordu | biri offboard'ı geri açarsa uçak slota **fırlardı** |

  Ayrıca RTL durumu artık `EVENT_RTL_TRIGGERED` **yayınlamıyor** —
  `agent_fsm` onu RETURN_HOME'a çevirip `offboard` yolluyordu ve bu
  **inişi iptal ederdi.**
- **Uçaklardaki kod ÖLÇÜLDÜ** (`.surum`'a güvenilmedi, dosyada imza arandı):
  olay düzeltmesi **üçünde de var**, madde 24 **hiçbirinde yok.**
  `.surum` `5515c20 +KIRLI` diyor ama dosyalar `a48ca98` içeriğinde —
  `+KIRLI` dağıtımın commit'siz ağaçtan yapıldığını söylüyor. `DURUM.md` §4.
- **Yeni boşluk B19 bulundu:** `COMPLETED` terminal ve **çıkışı yok**. İniş
  bitince `mode_manager` orada kalıyor → **ikinci kalkış konteyner restart
  istiyor**, oysa görev başına **3 hakkımız var.** ~6 satır, karar verilmedi.

**Ne değişti**

- kod: `mode_manager_node.py` — `_inis_komutu_gonder()`, LANDING/RTL/EMERGENCY
  girişlerinde `px4_bridge`'e doğrudan `land`, tick'te **1 Hz tekrar**,
  iniş durumlarında `formasyon_sustur`
- kod: `swd_mandal.py` **YENİ** (saf modül, rclpy'siz test edilebilir) —
  kalkış **tek atış**, iniş **mandal**, iniş SwA'dan **bağımsız**,
  ilk çerçeve kenar sayılmaz
- kod: `joystick_interpreter_node.py` — `SwdMandal` kullanıyor; emniyet
  kapalıyken `cmd.land` artık **silinmiyor**
- test: `test_swd_mandal.py` **YENİ** (17 test) · `test_mode_manager.py`
  40 → **44** (iniş her havada durumdan ulaşılabilir mi)
- **uçakta: HİÇBİR ŞEY DEĞİŞMEDİ** — dağıtım yapılmadı, bayraklar aynı
- belge: `gorev2.md` **766 → 566 satır**, devir teslim için yeniden kuruldu ·
  `DURUM.md` §4 (ölçülen sürüm) · `YAPILACAKLAR.md`

**Yarım kalan / tuzak**

- 🔴 **Madde 24 UÇAKTA DOĞRULANMADI.** Kod ve testler geçiyor, ama dağıtım
  yapılmadı. Yerde doğrulanabilir: `mod` aç, LANDING'e sok,
  `/swarm/agent/droneN/commands`'a `land` gitti mi bak.
  ⚠️ `swarm_state_machine` **tek paket yetmez mi?** Bu sefer yeter — yalnız
  o paket değişti (`swarm_core` ve mesajlar **değişmedi**).
- 🔴 **Madde 25 (kalkış) ARM YETKİSİ KARARINI bekliyor.** `gorev2.md` §3'te
  iki seçenek ve öneri duruyor: **SwD → `arm` + `takeoff:H` atomik**, üç
  koşulla kapılı (SwA açık · gaz merkezde · görev YKİ'den başlatılmış).
  Alternatifi uçakları **pervaneleri dönerken** belirsiz süre bekletiyor.
- **`.surum` yanıltıcı.** Sürüm kontrolünde `.surum`'a değil, **dosyadaki
  imzaya** bak (`TUZAKLAR.md` §1.14'ün canlı örneği).

**Sıradaki adım**

`YAPILACAKLAR` Aşama D ①: madde 24'ü dağıt ve **yerde doğrula**, sonra
ARM yetkisi kararını al ve madde 25'i yaz. Kritik yol: `24 → 25 → 27 → 28 → 31`.

**Uçakların bırakıldığı hâl**

- **Üçü de ağda, DISARM, dışarıda.** Konteynerler ayakta (~2 sa),
  11 düğüm, `baslat.sh` md5 üçünde de depo ile aynı.
- Bayraklar: `origin consensus fsm formasyon ca mod` üçünde ·
  **`joystick` yalnız ylp00** · **`/ws/mod_test` üçünde de takılı**
- 🔴 **`mod` açık** → SwD'ye dokunmak sürüyü ARM edebilir.
  **Kill pilotları başında olmadan kumandayı açma.**
- ⚠️ ylp02 diski **%81 dolu** (diğerleri %40-42)

---

## 2026-08-30 03:29 — Osman + Claude (GÖREV 2 — Aşama A: kod tarafı BİTTİ)

> **Uçuş yok, uçaklara HİÇ DOKUNULMADI.** Gece boyu Görev 2 çalışıldı:
> şartname çözümlendi, `docs/gorev2.md` açıldı, 17 boşluk bulundu, kod
> tarafının tamamı (Aşama A, madde 1-10 + B17) kapatıldı. 4 commit.

**Ne yapıldı**

- **Şartname §5.2 PDF'ten okundu.** Görev 2 = 100 puan, 3 hak. Ceza:
  çarpışma −20×N · kalkışta hata −5 · düşme −5 · **osilasyon −10**.
  🔴 Şartname **iki kumanda zorunlu** kılıyor: *"suruyu yoneten kumanda
  DISINDA, kill switch icin AYRI bir kumanda ve ayri yetkili pilot"*.
  Yani ikinci alıcı kararı tercih değil, **şart**.
- **17 boşluk bulundu, hepsi kodda `dosya:satır` ile doğrulandı.** En ağır üçü:
  - **B1** — `joystick_interpreter` RC'yi yalnız Pixhawk'tan okuyordu, ama
    ylp00'ın tek RC girişi **kill pilotuna ait** (CH5 kill, CH8 arm).
    Remap tekilleştirilmeseydi **kill switch'i kaldırmak sürü komutlarını
    AÇAR**, arm switch'i kalkış tetiklerdi.
  - **B15** — `mode_manager` READY'de tarif yayınlıyor, centroid ise
    `compute_centroid():129` aktif ajan yoksa **yazmadan dönüyor** →
    `(0,0,0)`. B3'ün düzeltmesi tek başına uygulansaydı **uçak NED
    origin'e giderdi.**
  - **B17** — `swarm_fsm` `formation_heading_deg`'i tanımlıyor, yayınlıyor,
    **arada atama yok** → kalıcı `0.0`. Kontrolün pilota geçtiği anda sürü
    kuzeye dönerdi (~10 m/uçak).
- **293 birim testi geçiyor** (27 yeni). `tsc` + `vite build` temiz.
- **Mesh ölçüldü:** Görev 2 mesh'e **+20 çerçeve/s** ekliyor (~53 → ~73).
  **Yapısal mesh değişikliği GEREKMİYOR** — `TIP_KOMUT` her şeyi taşıyor,
  paket 13 bayt dolu / **3 bayt boş**.

**Ne değişti**

- kod (uçak tarafı, **DAĞITILMADI**): `mode_manager/*` (B3/B4/B5/B7/B8/B10/
  B15 + G2-K6) · `swarm_fsm/*` (B17) · `esp32_bridge` (B5 süzgeci) ·
  `manual_kinematics` (`dairesel_ortalama_deg` **eklendi**, `apply_tilt`
  değişmedi) · **YENİ** `swarm_control/rc_ibus/` · `baslat.sh` · `run_drone.sh`
- kod (YKİ): `--senaryo manevra` (`gorev_kanit_ucus.py`) ·
  `ucus_ayarlari` `MOD_KALKIS_ESIK` + `MOD_TEST_*` ·
  **YKİ joystick zinciri KOMPLE SİLİNDİ** (panel + gamepad + `api.ts` +
  `POST /api/swarm/control` + `publish_swarm_control`) — −1.430 satır,
  derleme 357,56 → 344,03 kB
- **uçakta: HİÇBİR ŞEY.** Üç uçak 29 Ağustos 19:15 dağıtımından beri aynı
  hâlde, bugün açılmadılar bile.
- belge: **`docs/gorev2.md` YENİ** (Görev 2'nin tek toplanma noktası) ·
  `README` + `KARARLAR` ondan haberdar edildi · `DURUM` §3/§4 ·
  `YAPILACAKLAR` Görev 2 bloğu devredildi

**Yarım kalan / tuzak**

- 🔴 **UÇAKLAR ARTIK UÇAK TARAFI KODA DA GERİDE.** 29 Ağustos'ta fark yalnız
  YKİ+belgeydi; bugün `baslat.sh`, `swarm_core`, `swarm_state_machine`,
  `swarm_control` değişti. Ayrıntı `DURUM.md` §4 tablosunda.
  ⚠️ Dağıtımda `--paket` ile **tek paket yetmez** — `swarm_core` ve
  `swarm_state_machine` ikisi de derlenmeli.
- 🔴 **Dağıtımdan sonra YKİ'de `formation_heading_deg` DEĞİŞECEK.** Bugüne
  kadar kalıcı `0.0` gidiyordu, artık uçakların yaw ortalamasını taşıyacak.
  `swarm_fsm` şu an koşan 11 düğümden biri — **bu beklenen bir değişiklik,
  arıza değil.** Uçuşu süren zincirde tüketicisi yok.
- ⚠️ **Düğüm katmanı yalnız SÖZDİZİMİ doğrulandı.** `rclpy`/`swarm_interfaces`
  konteynerde olduğu için `mode_manager_node`, `joystick_interpreter_node`,
  `rc_ibus_kopru`, `esp32_bridge` bu laptopta **çalıştırılamadı**. Saf-Python
  katmanı (context/transitions/çözücü/kinematik) 293 testle kapalı, ama
  **düğümlerin gerçek doğrulaması G0'da.**
- 🔴 **i-BUS gerilimi ÖLÇÜLMEDİ.** FS-iA6B 5 V ile besleniyor, i-BUS çıkışı
  yaygın olarak 3,3 V bildiriliyor **ama garanti değil** ve **Pi 5 GPIO'su
  5 V toleranslı DEĞİL.** Multimetresiz bağlanmaz.
- ⚠️ **Uçakların yerdeki YÖNÜ artık önemli** (B17 sonrası): formasyon
  burunların baktığı yöne göre kuruluyor. Aynı yöne dizin; `--kuru`
  tutarlılık < 0,90 ise uyarıyor.
- 🟡 `--senaryo manevra` telemetrisiz **"SONUÇ: KALDI"** der — doğru
  davranış, `formasyon_gecis` de aynısını yapıyor. Uçaklar açıkken tekrarla.
- 🟡 Plan iki kez yanlış çıktı, ikisi de kod okunarak yakalandı: **B16**
  ("`fsm` kapısı koy" → gerekçe çürüdü, **uyarı** yapıldı) ve **B8**
  ("land kapısına RTL ekle" → pilotun iniş komutunu engellerdi, **kök
  nedene** inildi). `PLAN.md` §8 kuralı iki kez işe yaradı.

**Sıradaki adım**

- **AŞAMA B — donanım** (`YAPILACAKLAR` Görev 2 bloğu · `gorev2.md` §4
  madde 11-15). İlk iş 🔴 **i-BUS gerilim ölçümü**, sonra kumanda #2
  (10 kanal + failsafe SwA=KİLİTLİ), konteyner recreate ×3, dağıtım.

**Uçakların bırakıldığı hâl**

- ylp00 · ylp01 · ylp02: **üçü de 29 Ağustos'tan beri DOKUNULMADI.**
  Bugün açılmadılar. Kod `e4eceb9`, bayraklar
  `suru_dugumleri = origin consensus fsm formasyon ca`, `/ws/gozlem` YOK,
  `/ws/yer_testi` YOK, 11 düğüm. Yeni `/ws/mod_test` bayrağı **henüz hiçbir
  uçakta yok** (dağıtılmadı).

---

## 2026-08-30 00:05 — Osman + Claude (YKİ: ölü kartlar temizlendi · KARAR-12)

> **Uçuş yok, hava muhalefeti — günün üçüncü oturumu.** YKİ'de görev paneli
> genişledi, acil iniş haritaya taşındı ve **hiç çalışmamış iki kart**
> kaldırıldı. Uçaklara bugün de dokunulmadı.

**Ne yapıldı — YKİ**

- **Görev paneli yatayda genişledi** (operatör: "çok dar"); harita bir tık daraldı.
- **ACİL İNİŞ görev kartından haritanın alt ortasına** taşındı. Görev sürerken
  operatörün gözü haritada; butonu kenar çubuğunda aramak acil anda kayıp zaman.
  `z-index 1002` — takip butonu (1000) ve "buraya git" çubuğu (1001) örtmesin.
  🔴 Komut **`LAND`, `ABORT` DEĞİL** — bilerek: koda bakıldı, `ABORT` yalnız
  `MissionState.ABORTED`'a geçiriyor ve sürünün **zaten inmiş** olmasını
  bekliyor, hiçbir yerde iniş komutu üretmiyor.
- **Test Görevi slotu** (id **90**, şartname kimlikleriyle çakışmasın diye 90+).
  Dinamik: o an yazılan test buraya bağlanacak. **Şu an bağlı değil**, panel
  bunu açıkça yazıyor.
- Görev seçme listesi okunmuyordu (beyaz üstüne beyaz) — `option` renkleri
  açıkça verildi, `:root`'a `color-scheme: dark`.

**Kaldırılan iki kart**

- **KosucuPanel** — operatör "artık ihtiyacımız yok". `api.ts` istemcisi ve arka
  uçtaki `/api/kosucu` **bilerek duruyor**: KARAR-11 test merdiveni adım 1
  koşucu senaryosu istiyor, günler içinde geri gelecek.
- **SwarmStatePanel** — kart **hiç çalışmamıştı**. Ölçüldü: `swarm_fsm`
  `/swarm/public/state`'i uçakta 5 Hz yayınlıyor ama ① `swarm_state_paketle`
  **yok** ② `esp32_bridge` o konuya **abone değil** ③ alıcı taraf
  `TIP_SWARM_STATE`'i `SystemEvent`'e çeviriyor, `SwarmState`'e değil. Yani
  mesh taşıyıcısı **hiç kurulmamış**; kart kalıcı boştu.

**QR kartı — kaldırılMADI, sebebi farklı**

Aynı yöntemle bakıldı: QR zinciri **baştan sona eksiksiz** —
`vision_node` → `/swarm/internal/perception/qr_data` → `esp32_bridge` abone ✅ →
`TIP_QR_GOREV` (0x14) paketleyici ✅ → alıcı `QRMissionData` yayını ✅ →
backend abone ✅. Ayrıştırma patlarsa `TIP_QR_HAM` (0x15) yedeği bile var.
**Kart boş çünkü `goru` anahtarı uçaklarda açık değil** (`suru_dugumleri =
origin consensus fsm formasyon ca`). ADIM 5 açılınca kendiliğinden dolar.

**KARAR-12 — `mission_active` YKİ'ye lider kalp atışıyla (mesh'e 0 bayt)**

`SwarmState` gidince `payload.swarm_state` üç yerde varsayılana düştü; sonucu
**arayüzde beş kapı kalıcı `false`**: ACİL İNİŞ butonu **hiç aktifleşmiyor** ve
görev sırasında tekil komutlar **kilitlenmiyor** (şartname: müdahale görevi
BAŞARISIZ sayar).

Ölçüldü — çözümün boru hattı **zaten kurulu, yalnız kaynağı boş**:
`LeaderHeartbeat.msg`'de `mission_active` alanı var, paketleyici koyuyor,
`TIP_LEADER_HB` 10 Hz gidiyor, alıcı çözüyor, baz köprü
`/swarm/public/leader/heartbeat`'e yayınlıyor. **Tek kopukluk:**
`consensus_context.py:86` `mission_active = False` yapıp bir daha **hiç** set
etmiyor — bayt saniyede 10 kez sıfır taşıyor. (Doğru değeri tutan aynı isimli
alan **başka düğümde**: `swarm_fsm_node.py:586/590`.)

```
TIP_LEADER_HB payload = 16 bayt (mesh sabit)
  kullanılan  8   <- mission_active bunun İÇİNDE, zaten uçuyor
  boş dolgu   8   <- ileride mission_id (uint8) için yer var
```

Olay yolu (`SystemEvent`) elenmedi, **teyit katmanı** olarak alındı: olay
**kenar** tetikli, kalp atışı **seviye** tetikli. Şartname "hakem YKİ
bağlantısını kesecek" diyor — yeniden bağlanan YKİ'de kenar tetikli bayrak
`false` başlar, yani buton tam gerektiği anda pasif kalır.

🔴 **Karara yazılan tuzak:** kalp atışını **yalnız lider** yayınlıyor. Zaman
aşımında durumu **sıfırlarsak lider düştüğü saniyede ACİL İNİŞ butonu ölür.**
Doğrusu son değeri **korumak**.

**Ne değişti**

- kod: `MissionPanel` (Test slotu, option renkleri), `AcilSonlandirma/` (yeni),
  `App.tsx`/`App.css`, `index.css`, `api.ts`; `KosucuPanel/` + `SwarmStatePanel/`
  silindi. `tsc` temiz, derleme 357,56 kB.
- belge: `KARARLAR.md` **KARAR-12** (yeni), `YAPILACAKLAR.md` ADIM 6'ya bağlantı,
  **`DURUM.md` §2 DÜZELTİLDİ** (aşağıda).
- uçakta: **hiçbir şey.** Üç uçağa 29 Ağustos'tan beri dokunulmadı.

**Yarım kalan / tuzak**

- ⚠️ **`DURUM.md` 3 gündür yanlış bilgi taşıyordu, düzeltildi:** §2'de "diğer
  `SystemEvent`'ler YKİ'ye ulaşmıyor, mesh'te `TIP_EVENT` yok" yazıyordu.
  `TIP_OLAY` (0x16) **27 Ağustos'ta eklenmiş**, olaylar ulaşıyor. Belge
  güncellenmemiş, işaret ettiği `YAPILACAKLAR` P2 maddesi de artık yok.
  **Aynı hata başka yerde de olabilir — belge kodun gerisinde.**
- ⚠️ **Verdiğim mesh sayısı yanlıştı, düzeltildi:** üç uçak için "~43
  çerçeve/s" demiştim; `TIP_LEADER_HB`'yi saymamışım (lider `tick_hz=10` ile
  10 Hz yolluyor). Doğrusu **~53**. "Mesh sade kalsın" kararını değiştirmiyor,
  güçlendiriyor.
- 🟡 **YKİ denetimi yarıda kesildi** (operatör: "şimdilik bu kadar yeter,
  sırası gelince"). Ölçülenler — **YAPILACAKLAR'a yazılmadı, operatör istemedi:**
  `DroneState`'in **52 alanından 31'i arayüzde hiç kullanılmıyor**; bir kısmı
  zaten gösterilmemeli (ham NED, `sysid`) ama içlerinde `failsafe_active`,
  `oscillation_detected`/`unstable_flight`, `origin_synced`, `estimator_ok`,
  `pilot_override_active` ve **`status_text`** (PX4'ün kendi mesajları, arka
  uçta dolu) var. Uyarı sistemi (`alert_manager.evaluate`) yalnız **4 koşul**
  izliyor: bağlantı, pil, GPS fix, RTK kaybı. Haritada **HOME işareti yok**
  (CLAUDE.md §9 "HOME kayması çözülmeden RTL yok" kırmızı çizgisi var ama
  operatör kaymayı arayüzden göremiyor) ve **uçuş alanı sınırı yok**.
  Denetim `Map.tsx` incelemesinde kesildi, tamamlanmadı.

**Sıradaki adım**

- Değişmedi: Görev 2 manevra modu — **KARAR-11'deki 3 onay sorusu → test kodu.**
  Kod 28 Ağustos'tan beri hazır, uçaklara **dağıtılmadı**; 29 Ağustos'un
  `baslat.sh` değişiklikleri de uçaklarda yok.

**Uçakların bırakıldığı hâl**

- Üçü de açık, ağda, **disarm**, 11 düğüm. **Bugün hiç dokunulmadı** — 29
  Ağustos sabahki dağıtımdan beri aynı hâlde.

---

## 2026-08-29 21:54 — Osman + Claude (YKİ SADELEŞTİRME + RPi SAĞLIK PANELİ)

> **Uçuş yok, hava muhalefeti.** Gün boyu YKİ arayüzü elden geçti, yeni bir
> özellik eklendi (RPi paneli) ve Arch konteyneri yeniden kuruldu.

**Ne yapıldı — arayüz**

- **Başlık:** SÜRÜ sayacı, ARM ve GÖREV kutuları kaldırıldı; bağlantı durumu
  başlığın altına küçük rozet, RTK sağa yaslandı. **Açık tema tamamen
  kaldırıldı** (`useTheme` silindi, `index.html`'de `data-theme="dark"`
  SABİT — `Map.css`'in leaflet karo filtresi o attribute'a bağlı).
- **Bildirim paneli (YENİ):** başlıkta zil butonu + okunmamış sayacı. Tüm
  olaylar zaman damgalı, **şiddet ve drone süzgeçleriyle**. Kaynak zaten
  vardı (`useGunluk` → `yki_olaylar.jsonl`); eksik olan görünürlüktü.
- **Drone kartı:** renkli nokta gitti; UÇAMAZ/BOŞTA/YERDE rozetleri başlığa;
  LOG/Kontrol/RPi butonları alt şeride SOLA, konum+mesafe sağa (çubukla
  ayrık); puntolar 1-2 birim büyüdü (ham px yerine token'a bağlandı).
  **Kart içi log katmanı KALDIRILDI** — kart kısa, defter sığmıyordu; LOG
  artık bildirim panelini o drone'a süzülmüş açıyor. `DroneLog` silindi.
- **Kontrol paneli** sağ kenar çubuğundan **haritanın sağ altına** taşındı.
  Komut butonlarından ikonlar kalktı; onay metinleri "emin misin" yerine
  **operatörün bakması gereken şeyi** soruyor ("Pervanelerin çevresi boş mu?").
- Ayarlar paneli ve bildirim metinleri sade Türkçeye çevrildi (İngilizce
  kalıntılar, iç jargon, kısaltmalar). 29 olay etiketi + 5 uyarı mesajı.

**Ne yapıldı — RPi sağlık paneli (YENİ ÖZELLİK)**

🔴 **Veri MESH'TEN GEÇMİYOR — yalnız SSH.** Operatör kararı. Mesh 16 baytlık
paketler taşıyor ve görev telemetrisi için; teşhis verisi oraya konmuyor.
SSH yoksa `ssh_ok:false` döner, arayüz "bilinmiyor" gösterir — **değer
uydurulmaz.**

```
RPi butonu -> GET /api/rpi/{id} -> drone_bul.sh ylpXX 'bash -s' < rpi_durum.sh
           -> SSH -> Pi: sicaklik, throttle, CPU, bellek, disk, Wi-Fi, ROS
```

Ölçüm betiği **stdin'den** geçiyor: uçağa dağıtım GEREKMEZ, uçaklardaki kod
sürümünden bağımsız. Kimlik/IP `drone_bul.sh --tablo`'dan (ikinci tablo yok).
Eşikler ölçümden: Pi 5 boşta 56-64 °C → uyarı 70, kritik 80.

**Ne değişti**

- kod: `backend/api/rpi.py` (yeni), `deploy/rpi/teshis/rpi_durum.sh` (yeni),
  `components/BildirimPanel/` + `RpiPanel/` (yeni), 20 dosya düzenlendi,
  `DroneLog` + `useTheme` silindi
- **YKİ makinesi (Osman/Arch):** konteyner YENİDEN KURULDU —
  `arch-docker/Dockerfile`'a `openssh-client iproute2 iputils-ping net-tools
  nmap`, `yki_konteyner.sh`'e `~/.ssh` (ro) + drone önbelleği bağları ve
  `~/.cache` sahiplik düzeltmesi. (Bu dosyalar gitignore'da, kişisel.)
- uçakta: **hiçbir şey** — RPi özelliği uçak tarafına dokunmuyor

**Yarım kalan / tuzak**

- 🔴 **`kur_yki.sh` 6/8'de bir kez düştü** (pip PyPI zaman aşımı, hotspot).
  YKİ o sürede kapalı kaldı. `PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10` ile
  tekrar koşunca geçti. Dalgalı ağda yeniden kurulum riskli.
- ✅ **TUZAKLAR §2.11b burada da vuracaktı:** yerel `install/`'da silinmiş
  `ExecuteFormation`'dan 18 artık vardı; `kur`'un artımlı derlemesi aynı
  `undefined symbol` hatasını üretecekti. Derlemeden ÖNCE
  `build/`+`install/swarm_interfaces` silindi → temiz derleme 24,3 sn
  (artımlı ~5 sn sürer ve bozuk çıkar — süre farkı tek başına işaret).
- ⚠️ **ylp01'in RAM'i yarısı: 4049 MB** (diğer ikisi 8062). 24 Ağustos klon
  yeni Pi'ye yapılmıştı. Bugün sorun değil, görü zinciri açılınca üçü aynı
  davranmayabilir. `RPI_ESITLEME`'ye YAZILMADI (operatör: "şimdilik kalsın").
- ⚠️ `yelpence/yki:araclar` imajı 323 MB'lık hazır venv içeriyor — kurulum
  yine düşerse kurtarma yolu.

**Sıradaki adım**

- Görev 2 manevra modu: KARAR-11'deki 3 onay sorusu → test kodu.

**Uçakların bırakıldığı hâl**

- Üçü de açık, ağda, **disarm**, 11 düğüm, kod `04f3828 +KIRLI`. Uçaklara
  bugün hiç dokunulmadı.

---

## 2026-08-29 19:16 — Osman + Claude (REPO SADELEŞTİRMESİ + HIZLI DÖNGÜ · üç uçağa dağıtıldı)

> **Uçuş yok, yer işi.** Repo sadeleştirildi, uçuş öncesi kontroller
> gevşetildi, kod değişikliği döngüsü kısaltıldı. Üç uçağa dağıtıldı —
> **dağıtım sırasında üç uçak da düştü ve düzeltildi** (aşağıda).

**Ne yapıldı**

- **Ölü kod silindi** (`04f3828`): `basit_kacinma` (sürü zincirinde zaten
  ölüydü — yalnız `position_valid=True` setpoint'lerde çalışıyordu),
  `kinematic_fusion` (KARAR-01 ile elenmişti), `backend/test_tools`,
  `ExecuteFormation.action`, `px4_autopilot` submodule, `ca_benzetim.py`,
  `kacinma_testi.py`, `on_ucus_kontrol.py` (IP'leri/eşikleri bayattı),
  `pusula_olc.py`, `CA.md`, `WORKFLOW_BULGULAR.md`. **−11.655 satır.**
- **Belgeler kesildi:** 16.102 → 8.775 satır. Açılış ritüeli
  (DURUM+GUNLUK+YAPILACAKLAR) **5.866 → 768 satır**. Arşiv git'te
  (`git show 783afab:docs/<dosya>`).
- **Uçuş öncesi kontroller gevşetildi** (operatör kararı): `param_karsilastir`
  ve `titresim_olc` uçuş başınadan **saha gününe** indi · `uptime`/md5/düğüm
  sayısı `drone_bul.sh --durum` içinde birleşti · **QGC 14550 link kontrolü
  tamamen operatöre bırakıldı** · G2 yalnız *uçağı süren* düğümler için ·
  KARAR-02'nin ultracode hatırlatma görevi kaldırıldı.
- **Hızlı döngü araçları yazıldı ve SAHADA DOĞRULANDI:**
  `dagit.sh --paket <ad>` (yalnız değişen paketi derle) ve
  `baslat.sh --yalniz <düğüm>` (altyapıya dokunmadan tek düğüm yenile).

**🔴 Dağıtımda yaşanan arıza — kök neden bulundu, TUZAKLAR §2.11b**

`ExecuteFormation.action` silinince artımlı `colcon build` C kütüphanesini
yeniden üretti ama **Python typesupport uzantısını üretmedi**; eski uzantı
`undefined symbol: ...execute_formation...` verdi ve **on düğümün hepsi
açılışta öldü.** `colcon` "6 packages finished" diyerek BAŞARILI raporladı.
Ayırt edici işaret: artımlı **4,7 sn**, temiz derleme **1 dk 19 sn**.
Çözüm: üç uçakta `build/`+`install/swarm_interfaces` silinip temiz derlendi.

Ayrıca `colcon` silinen entry-point'leri kaldırmıyor — `basit_kacinma` ve
`kinematic_fusion` üç uçakta da **çalıştırılabilir** duruyordu; konteyner
içinden temizlendi (host kullanıcısı silemiyor, dosyalar root'a ait).

**Ne değişti**

- kod: `baslat.sh` (`--yalniz`, `basit_kacinma`/`fusion` blokları kalktı),
  `dagit.sh` (`--paket`), `drone_bul.sh` (`--durum`'a md5 + düğüm sayısı)
- uçakta: üçü de **`04f3828 +KIRLI`**, konteynerler yeniden başlatıldı,
  `swarm_interfaces` temiz derlendi, ölü düğüm artıkları silindi
- belge: CLAUDE, README, DURUM, PLAN, KARARLAR, TUZAKLAR (§2.11b yeni),
  RPI_ESITLEME (§3'e A20/A21/A22), YAPILACAKLAR, GUNLUK

**Doğrulanan hâl (üç uçakta da aynı)**

```
baslat.sh md5 : depo ile AYNI      ros2 dugum : 79 (11'i bizim)
mesh komsu    : 10,7-11,9 Hz       CA         : avoid=0, saglikli
telemetri     : bagli, DISARM, 31-32 uydu, Auto.Loiter
--yalniz ca   : ca PID 270->1249 (12 sn) · mavros/px4/esp/fsm/formasyon PID DEGISMEDI
```

**Yarım kalan / tuzak**

- **RTK yok (`fix=3`)** — baz istasyonu RTCM yayınlamıyor. Uçuştan önce ayrı iş.
- **ylp02 diski %79 dolu** (5,9 GB boş); ylp00 %42, ylp01 %36.
- ylp01'in SSH host anahtarı `known_hosts`'a eklendi (24 Ağu klonlamasında
  yeniden üretilmişti; üç anahtarın da farklı olduğu doğrulandı).
- `baslat.sh` **644'tür, çalıştırılabilir değil** — çağrı `bash /ws/baslat.sh`.
  `docker exec -d drone1 /ws/baslat.sh` "permission denied" verir.
- ⚠️ `--yalniz` **uçuş sırasında kullanılmaz** — düğüm saniyelerce yok olur.

**Sıradaki adım**

- Görev 2 manevra modu: KARAR-11'deki **3 onay sorusu** → test kodu.

**Uçakların bırakıldığı hâl**

- Üçü de açık, ağda, **disarm**, Auto.Loiter, 11 düğüm ayakta.
  `suru_dugumleri = origin consensus fsm formasyon ca`, `gozlem` YOK
  (formasyon-sürer mod), `kacinma` YOK.

---

## 2026-08-28 21:40 — Berk + Claude (GÖREV 2 MANEVRA MODU: şartname incelendi, 4 boşluk kapatıldı, test PLANLANDI — yarına)

**Ne yapıldı**

- Şartname 5.1/5.2 tam okundu (pdf → metin, `pdfenv` scratchpad'de).
  Üç ayrı "pitch/roll/yaw" bağlamı ayrıştırıldı: Görev 1 QR-eğim /
  Görev 2 hareket modu (öteleme) / **Görev 2 MANEVRA modu** (merkez
  sabit eğim+rotasyon — test edilecek olan). Rapor sohbette; özet ve
  puan/ceza notları **KARAR-11**'de.
- Zincir HAZIR ÇIKTI: mode_manager (605) + joystick_interpreter (534,
  FlySky FS-i6X eşlemeli) + köprü TIP_KOMUT iki yönde. Ama hiç koşmamış
  ve 4 boşluğu vardı → **kapatıldı, commit `f6f8498`** (KARAR-11):
  joystick anahtarı+remap · çıkış /raw'a + formasyon susturması
  (3 sn bayat-bırakma) · eğim matematiği apply_tilt'e (merkez-kayması
  ve ters roll işareti düzeldi, 2 regresyon testi) · MOD_* tek kaynak
  (yaw 25°/s = PX4'ten türetme). Testler 11/11.
- **Manevra testi planlandı** (tek buton, SSH'siz, kumandasız sürücü) ve
  plan sırasında koddan **2 yeni engel** çıktı (formation_change ofset
  güncellemiyor → ışınlanma; FSM READY'ye ulaşamıyor) — KARAR-11'de.

**Ne değişti**

- kod: `f6f8498` (repo'da; ⚠️ **uçaklara DAĞITILMADI** — şarjdalar)
- uçakta: hiçbir şey (19:50 kaydındaki hâl geçerli)
- belge: KARARLAR (KARAR-11 + test planı), YAPILACAKLAR (P1.31-33)

**Yarım kalan / tuzak**

- Manevra testi kodu YAZILMADI — operatör "yarına kalsın" dedi.
  🔴 Yarın İLK İŞ: KARAR-11'deki **3 onay sorusu** (sürücü uçağı? /
  genlikler ±10°, yaw 12,5°/s? / iniş slot üstüne?) → sonra kod.
- mode_manager HOLD'da 5 sn komutsuz kalınca kendiliğinden LANDING'e
  geçiyor (bugün etkisiz ama sürücü tasarımını belirledi — yayın sonda
  kesilmeyecek).

**Sıradaki adım**

- Onay soruları → manevra test kodu (KARAR-11 merdiveni 1) → uçaklar
  açılınca dağıtım + G0 (P1.31).

**Uçakların bırakıldığı hâl**

- Üçü de kapalı, piller şarjda. Kod `403b99f` (f6f8498 dağıtılmadı),
  `sekans` anahtarı YOK, gozlem YOK.

---

## 2026-08-28 19:50 — Berk + Claude (FORMASYON GEÇİŞ TESTİ UÇTU ✅ — sekans UÇAKTA, YKİ butonuyla)

> **Üç uçak, tek uçuş, tek buton.** Çizgi→ok başı→V→çizgi→EVE sekansı
> tamamen uçakta koştu (yeni `formasyon_sekans` düğümü, KARAR-10); YKİ
> yalnız arm+takeoff verdi, izledi, sonda kalkış noktalarına indirdi.
> Operatör: *"çalıştı, gayet de iyiydi."*

**Ne yapıldı (uçuş, ölçülmüş)**

- Sekans logu (ylp00, lider d2): merkez (+6.5,-3.2), heading 310.6°
  (dizilimden otomatik), atama [2,1,3] — çizgi t0 → ok t0+26 → V t0+51 →
  çizgi t0+76 → EVE t0+97 → **BITTI t0+123 s** (plan 120).
- **Kaçınma hiç tetiklenmedi: `avoid=0` üç uçakta** — 7 m aralıkta
  geçişler nominal kaldı (kuru öngörüsü: en dar an 4,95 m > d0 4,0).
- İzleme: en yakın çift uçuş boyunca ~8,0 m; irtifa ~9,0-9,2 m
  (hedef 8 + bilinen ~1 m EKF/origin farkı, 26 Ağu ile aynı).
- Kayıtlar dizüstünde: **`~/yelpence-kayitlar/20260828_formasyon_gecis/`**
  (uçak başına rosbag ~34 MB + uçuş açılışının tüm günlükleri + YKİ
  kosucu çıktısı + haritalar).

**Gün içinde G0'ın yakaladığı 4 gerçek hata** (uçuşa çıkmadan düzeltildi):
kopru'nun lider-kapısı baypası → kapı üreticiye; iç veriyolu RELIABLE;
YAML param tip tuzağı ×2 → string+dynamic_typing; AgentStatus yayıncısı
agent_fsm'miş (FSM'siz G0 imkânsız). Kuru test de gerçek yerleşimde iki
atama kuralını eledi → çizgi dönüş koridoru + ilk-faz-Macar sabit sahiplik.

**Ne değişti**

- kod: `formasyon_sekans_cekirdek/node` (yeni), `ucus_ayarlari` SEKANS_*,
  `gorev_kanit_ucus` formasyon_gecis senaryosu + `harita_yaz_sekans`
  (okunaklı harita), `baslat.sh` `sekans` anahtarı, kosucu+KosucuPanel
  GEÇİCİ buton. Commit'ler `36531c4..403b99f`, uçaklarda `403b99f`.
- uçakta: **`sekans` anahtarı test sonrası SİLİNDİ** (`suru_dugumleri` =
  `origin consensus fsm formasyon ca` — normal düzen); `/ws/gozlem` YOK
  (formasyon-sürer mod). Konteynerler restart EDİLMEDİ — bir sonraki
  açılışta sekanssız kalkacaklar. `ucus_ayarlari.env` yenilendi (SEKANS_*).
- belge: KARARLAR (KARAR-10), YAPILACAKLAR, DURUM.

**Yarım kalan / tuzak**

- ⚠️ ros2 `-p x:=90` tam sayıyı INTEGER yapar, double declare düğümü
  ÖLDÜRÜR — iki kez yaşandı; yeni düğüm yazan `dynamic_typing` kullansın
  (TUZAKLAR'a aday).
- ⚠️ ylp01 paralel dagit'te ilk denemede düşüyor, tekli geçiyor (Wi-Fi).
- İrtifa ~1 m yüksek oturuyor (EKF/origin) — bilinen, analiz P0 HOME ile.
- 🔴 HOME kayması P0 HÂLÂ AÇIK (bu uçuş RTL kullanmadı, EVE fazı çözdü).

**Sıradaki adım**

- Uçuş kaydı analizi (isteğe bağlı): slot oturma hataları + faz geçiş
  temizliği mcap'ten. Aparat, mission1 sahaya alınınca silinecek (KARAR-10).

**Uçakların bırakıldığı hâl**

- Üçü de uçuştan sonra kalkış noktalarında, disarm; operatör şarj için
  kapatıyor. `sekans` anahtarı YOK, gozlem YOK, kod `403b99f`.

---
## Daha eski kayıtlar

21 oturum kaydı (2 → 28 Ağustos) 29 Ağustos 2026'da bu dosyadan çıkarıldı.
Silinmediler — git'te tam hâlleriyle duruyorlar:

```bash
git show 783afab:docs/GUNLUK.md          # kesimden önceki tam defter
git log --follow -- docs/GUNLUK.md       # dosyanın bütün geçmişi
```

Sebep: finale 8 gün kala açılış ritüeli 5.866 satırdı; devir teslim için
gereken son iki kayıt, geri kalanı arşiv.
