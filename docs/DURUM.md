# DURUM — şu an ne çalışıyor, ne bozuk

**Son güncelleme:** 8 Eylül 2026, 07:05 — 🔴 **CUSTOM formasyon 3 uçakta mesh'ten HİÇ GEÇMİYORMUŞ** — kök neden bulundu, Pi tarafı düzeltmesi yazıldı, **yerde doğrulanmadı** (blok aşağıda) · 🎯 Görev 1 uçuş profili değişti (blok aşağıda) · 7 Eylül 11:57 RC-kayıp failsafe LAND · 5 Eylül 07:56 Görev 2



> ## 🔴 8 EYLÜL — CUSTOM FORMASYON MESH'TEN HİÇ GEÇMİYORMUŞ (3 uçakta)
>
> **Belirti (operatör):** *"ilk QR'a gittikten sonra sadece lider irtifa
> değişimi yapmıştı."* Kök neden ölçülmedi, **koddan çıkarıldı** ve
> deterministik:
>
> CUSTOM ofsetleri formülden türetilemez, `TIP_FORM_OFSET` çerçeveleriyle
> açıkça taşınır — paket başına 2 slot, **3 uçakta iki çerçeve.**
> `esp32_bridge` ikisini de **ara vermeden** UART'a yazıyordu. Firmware ise
> **tip başına** hız limiti uyguluyor (`MESH_GONDERIM_MIN_MS 50`,
> `TX DRONE/src/main.cpp:306,420`). İki çerçeve **aynı tip** →
> **ikincisi her seferinde düşüyordu.** Alıcıda montaj tamamlanmıyor,
> 200 ms sonraki başlık yarım montajı siliyor →
> **slot 2'nin ofseti mesh'e hiç çıkmıyor; takipçiler formasyon komutunu
> HİÇ almıyor.** Lider etkilenmiyor (loopback seri porta uğramıyor).
>
> 🔴 **`GOREV_FORMASYON=3` iken de geçerliydi.** `_gorev_formasyonunu_uygula`
> yalnız `_on_rotate`'te — yani **ilk QR'dan SONRA** — çağrılıyor; QR1'e
> kadar formasyon tipi zaten CUSTOM'du. Kusur 2 uçakla **görünmüyor**
> (tek ofset paketi), 3 uçakta çıkıyor.
>
> **Yazılan — Pi tarafı, firmware'e DOKUNULMADI:**
>
> | Ne | Değer | Nerede |
> |---|---|---|
> | Ofset çerçeveleri arası en küçük aralık | **60 ms** (50 + %20 pay) | `esp32_bridge._FORM_OFSET_ARALIK_S` |
> | Formasyon hedefinin mesh'e çıkış hızı | 5 Hz → **2 Hz** | `FORMASYON_MESH_HZ` (0 = kapalı) |
>
> Ofsetler kuyruğa alınıp 20 ms'lik bir timer ile aralıklı gönderiliyor.
> Yeni tur gelince kuyruktaki **bayat çerçeve atılıyor** — geç giden bir
> çerçeve yeni montaja ESKİ değerlerle yazılırdı (sessiz bozulma).
> Hız kapısı **loopback'i de** durduruyor: yoksa lider 5 Hz, takipçiler
> 2 Hz hedef görür ve sistematik kayma olurdu.
>
> ⚠️ **Görev 2 de bu yoldan geçiyor.** 5 Hz ile uçmuş bir yol 2 Hz'e indi;
> hedef gecikmesi en kötü 500 ms (formation_node kendi 20 Hz döngüsünde
> son hedefe rampalamaya devam ediyor). Sorun çıkarsa
> `ucus_ayarlari.py`'de `FORMASYON_MESH_HZ = 5.0` — tek satır, env ile gider.
>
> - 🔬 **YERDE DOĞRULANMADI.** Üç uçak açıkken takipçide `form_rx` artmalı,
>   `form_yarim` **artmamalı**; liderde `form_ofs_kuyruk=0`. Sayaçların
>   hepsi `esp32_bridge` teşhis satırında. **Doğrulanmadan uçulmaz.**

> ## 🎯 8 EYLÜL SABAH — GÖREV 1 UÇUŞ PROFİLİ: FORMASYON YOK, QR1'DE ALÇALARAK ARAMA
>
> Operatör kararı. İki ayar değişti, **ikisi de `src/gcs/ucus_ayarlari.py`'de**;
> uçaklara `ucus_ayarlari.env` ile gidiyor.
>
> | Ayar | Eski | Yeni | Etkisi |
> |---|---|---|---|
> | `GOREV_FORMASYON` | 3 (ÇİZGİ) | **0 (kapalı)** | Kalkıştan sonra hiçbir formasyon tipi dayatılmaz. Hakemin yere koyduğu **rastgele diziliş** snapshot'lanıp donduruluyor (CUSTOM/99) ve QR1'e o dizilişle gidiliyor. Formasyon yalnız QR'ın `frm` komutuyla değişir. |
> | `GOREV_QR_OKUMA_IRTIFA_M` | 10.0 m | **15.0 m** | Sürü QR1'e artık 15 m'de varıyor (kalkış irtifasıyla aynı → yolda irtifa değişimi YOK). QR okunamazsa **inerek** arıyor: 15 → 12.5 → 10 → başa. |
>
> **Kurtarma merdiveni artık iniyor.** Eskiden (12 → 10 → 18) yönsüzdü ve
> 18 m basamağı **ölçülen okuma tavanının (16.64 m, KAMERA.md §13) üstündeydi**
> — her turda 18 saniye kesin okunamayacak bir irtifada harcanıyordu, hata da
> vermiyordu. Yeni merdiven varış irtifası ile tabandan **türetiliyor**, ayrı
> sabit yok. **Taban 10 m yerinde** (`_SEARCH_ALT_FLOOR_M`); sürü hiçbir yolda
> altına inmez.
>
> `ucus_ayarlari.py` artık bu ilişkiyi **denetliyor**: varış tabanın altındaysa
> HATA, tabana eşit/çok yakınsa UYARI (merdiven tek basamağa çöker ve
> "alçalarak arama" sessizce kaybolurdu — 8 Eylül'e kadar tam olarak öyleydi).
>
> - 🔴 **Uçaklara HENÜZ GİTMEDİ.** Değişiklik yalnız depoda. `ucus_ayarlari.env`
>   yeniden üretilip üç uçağa atılmalı (⚠️ `dagit.sh` bu dosyayı **taşımıyor**).
> - 🔴 **CUSTOM formasyonun mesh bedeli var:** ofsetler formülden türetilemediği
>   için `TIP_FORM_OFSET` paketleriyle açıkça taşınıyor — 3 uçakta komut başına
>   1 değil **3 çerçeve**. Uçuştan önce `form_yarim` / `form_rx` sayaçları
>   yerde okunacak (YAPILACAKLAR P0).
> - ⚠️ YKİ MissionPanel'deki **"Başlangıç formasyonu" kutusu BOŞ bırakılmalı** —
>   bir tip seçilirse G1 BAŞLAT paketiyle gider ve bu 0'ı **ezer**.

> ## 📻 7 EYLÜL ÖĞLEN — KUMANDA-KAYBI FAILSAFE: RTL → LAND (üç uçak)
>
> Operatör kararı (KARAR-18): kumanda kapanınca uçaklar **olduğu yerde
> LAND** yapar (RTL değil) ve bunu **3-4 sn içinde** başlatır. Yazılan
> (MAVLink'ten, QGC kapalıyken; üçünde geri-okumayla doğrulandı, PX4
> kalıcı saklar — restart'a dayanır):
>
> | Parametre | Eski | Yeni | ylp00 | ylp01 | ylp02 |
> |---|---|---|---|---|---|
> | `NAV_RCL_ACT` | 2 (RTL) | **3 (LAND)** | ✅ | ✅ | ✅ |
> | `COM_FAIL_ACT_T` | 5.0 | **2.5 sn** | ✅ | ✅ | ✅ |
>
> Zaman zinciri: alıcı failsafe'i (~0.5-1 sn, CH3=2100) + kayıp ilanı
> 0.5 sn (`COM_RC_LOSS_T`) + bekleme 2.5 sn (HOLD) = **kapanıştan
> ~3.5-4 sn sonra LAND.** Bekleme penceresinde kumanda geri açılırsa
> failsafe iptal olur, uçuş sürer. `COM_RCL_EXCEPT=0` üçünde ölçüldü →
> **OFFBOARD'da da tetiklenir**; tespit zinciri (`RC_MAP_FAILSAFE=3`,
> `RC_FAILS_THR=2050`, `COM_RC_LOSS_T=0.5`) üçünde de doğrulandı.
>
> - 🟢 RC-kayıp yolu artık HOME kullanmıyor → HOME kayması BU failsafe
>   için risk olmaktan çıktı.
> - ⚠️ Hakem §5.4 failsafe'i belirler; **RTL derse** `NAV_RCL_ACT=2`
>   geri yazılır (KARAR-18) — HOME kayması riski o zaman geri gelir.
> - 🟠 Havada doğrulanmadı: alçak askıda kumanda kapat → ~4 sn'de iniş
>   başlamalı (19 Ağu RTL testinin LAND karşılığı). YAPILACAKLAR'da.
> - ⚠️ Yol notları: `udp-b` cevapları yalnız :14550'ye gider — QGC
>   açıkken MAVLink param eko'ları kaybolur; yazma QGC kapatılarak
>   yapıldı. Ayrıca ylp02'de konteynerde YENİ süreç ROS grafını
>   göremiyor (`px4_param.py` yolu tıkalı) — YAPILACAKLAR 🟡.

> ## 🌅 5 EYLÜL SABAHI — GÖREV 2: SABİT LİDER + YEDİ SESSİZ KUSUR KAPANDI
>
> **Ayrıntı `GUNLUK.md` 07:56 kaydı. Uçakta 17 yeni commit:
> `7c7ef98` → `4387554`, hepsi pushlandı.**
>
> Oturum **iki uçakla** yapıldı (ylp00 + ylp01). Kapatılan yedi kusurun
> hepsi "hata vermeden yanlış sonuç" sınıfındaydı.
>
> - 🟢 **ylp00 KALICI LİDER, sistem geneli** (Görev 1 + Görev 2, operatör
>   kararı). Her zaman **slot 0 = formasyonun ortası**. Ek olarak
>   **en-yakın-slot ataması (Macar)** yazıldı: lider slot 0'a çivili,
>   kalanlar Macar ile. Çizgide ölçüldü: toplam yol **0.00 m**
>   (kimlik sırası 24.00 m).
> - 🟢 **Kalkışta "hafif sola dönme" KAPANDI** — iki kök neden: başlık
>   dairesel ortalamadan alınıyordu (artık liderden) ve **tırmanış
>   geçicisinde** örnekleniyordu (yerde 331.16°, kapıda 313.8° = **17.4°
>   sola**). Başlık artık **yerde mandallanıyor**, READY'de tüketiliyor.
> - 🟢 **"Formasyonu almadılar" KAPANDI** — istek B15 kalkış kapısında
>   sessizce düşüyordu; kapı açılırken tarif yeniden isteniyor.
> - 🟢 **"10 m istedim 8.5 uçtu" KAPANDI** — `%80` bir geçiş ölçütüydü,
>   fiili son irtifa olmuştu. READY'de z artık **komut edilenden**.
> - 🟢 **`command_valid` MESH'TE YOKTU** — lider tarifi düşürüyor, takipçi
>   kabul ediyordu. `KOMUT_FLAG_COMMAND_VALID` eklendi.
> - 🟢 **HAREKETTE SAĞA-SOLA YALPA KAPANDI** — kök neden `v_ff` türevinin
>   payla paydayı farklı aralıktan alması: hedef ~10 Hz'de güncellenirken
>   yayın 20 Hz, türev sırayla **2× ve 0** okuyordu. Sabit pencereli türev
>   (`vff_pencere_s = 0.25`). Uçuşta doğrulandı: ylp00 komut roll dalgası
>   **2.332° → 0.748°** (−68%), ylp01 gerçek roll **1.29–1.39° → 0.806°**
>   (−40%). ⚠️ **Operatörün gözle teyidi ALINMADI** — sonraki kişi sorsun.
> - 🔴 **ylp02 ESKİ KODDA.** Oturum boyunca ulaşılamadı (son bilinen IP'de
>   yok, subnet taraması da bulamadı). **Üç uçak uçmadan önce dağıtılmalı.**
> - 🟠 **AÇIK, ölçüldü ama düzeltilmedi:** duruş aşımı **0.38–0.47 m**
>   (çubuk bırakılınca setpoint aşılıyor, ~2 sn'de dönüyor; mekanizma hız
>   takibi gecikmesi ~0.3 sn × 1.5 m/s). Yerinde gezinme **~0.15 m @
>   0.2 Hz** — komut kusursuz sabitken, yani PX4'ün kendi konum tutuşu.
> - 🔴 **4 Eylül'ün üç P0'ı ELE ALINMADI:** mesh kaybı · 1 Hz seyreltme ·
>   lens/QR. Aynen duruyor.
>
> ### 🔧 UÇAKTA KALICI DEĞİŞEN AYARLAR — sonraki kişi uçağı böyle bulacak
>
> | Ayar | Değer | Nerede |
> |---|---|---|
> | `SURU_SABIT_LIDER` | **1** (ylp00) | `ucus_ayarlari.py` → `.env` |
> | `UCAN_KADRO` | **(1, 2)** — ylp02 kadro dışı | `ucus_ayarlari.py` |
> | kaçınma `d0_m` / `hard_m` / `hist_m` | **3.0 / 2.0 / 0.5** | canlı doğrulandı |
> | kaçınma dönüş bekleme / hız / soğuma | **0.5 sn / 1.2 m/s / 2.0 sn** | canlı doğrulandı |
> | `MOD_MORF_HIZ_MPS` | **1.30** (1.34 denetimden geçmedi) | `ucus_ayarlari.py` |
> | `vff_pencere_s` | **0.25** (`0.0` = eski davranış) | `formation_node` varsayılanı |
> | ylp00 `MAV_SYS_ID` | **2 → 1**, `/ws/tgt_system` **SİLİNDİ** | uçakta |
> | ylp01 `tgt_system` bayrağı | **DURUYOR**, uçuş sorunsuz — dokunulmadı | uçakta |
> | YKİ paneli | aralık **6 m**, irtifa **10 m** | arayüz |
>
> ⚠️ **`MIN_AYRIM_M` (4.0) ile `d0` (3.0) bilerek AYRIŞTI.** `d0` kaçınmanın
> devreye girdiği yumuşak eşik, `MIN_AYRIM_M` kuru testin çarpışma payı.
> Kaçınmayı atikleştirmek kuru testin payını düşürmek anlamına gelmesin diye
> ikisi ayrı bırakıldı — bu bir unutkanlık değil, karar.
>
> ### 🔴 DAĞITIM ARTIK ANA MAKİNEDEN ÇALIŞMIYOR
>
> `rsync` **ana makinede yok**; `dagit.sh` `rsync: command not found` ile
> düşüyor. Dağıtım `yki` konteynerinden koşuluyor (orada `rsync` + `ssh` +
> anahtarlar var, depo aynı yola bağlı):
>
> ```bash
> docker exec yki bash -lc '\
>     ./deploy/rpi/dagit.sh --paket swarm_core ylp02'
> ```
>
> ⚠️ Konteyner **yeniden yaratılırsa `rsync` gider** — tekrar kurmak gerekir.

> ## 🌆 4 EYLÜL AKŞAMI — B5 GEÇTİ, GÖREV 1 ZİNCİRİ UÇTAN UCA UÇTU
>
> **İki uçuş yapıldı, ikisi de hedefine ulaştı. Ayrıntı `GUNLUK.md`
> 21:47 kaydı. Uçakta 18 yeni commit var: `7707698` → `63f9870`.**
>
> - 🟢 **B5 KAPANDI — formasyon İLK KEZ havada kuruldu.** Sabahki tek P0
>   soruydu, cevap ylp02'nin `formation.log`'undan geldi:
>   `FormationCommand alindi: type=3, atama=[1, 2, 3]`. Sabah bomboştu.
>   Tarif artık takipçilere mesh'ten ULAŞIYOR. Üç uçak İLK KEZ birlikte
>   arm oldu (önceki tek-uçak kalkışın sebebi `PILOT OVERRIDE: mod=POSCTL`
>   idi — donanım değil, kumanda modu; kod değişmedi).
> - 🟢 **Görev 1 zinciri uçtan uca ölçüldü:** ilk irtifa **15 m** ✅ ·
>   toplanma merdiveni **13.0 / 15.6 / 18.2 m** ✅ · NAVIGATE başlığı
>   **−33.3° sabit** ✅ · NAVIGATE irtifası komut **tam −10.0 m** ✅ ·
>   dikey alçalma **0.43 m/s** (tavan 0.5) ✅ · **QR'a 0.11 m** ✅ ·
>   seyirde formasyon aralığı **6.97 m** (hedef 7) ✅.
>   **İrtifa süzülmesi KAPANDI** (sabah ylp00 10.7 → 2.7 m iniyordu).
> - 🔴 **KUSUR 1 — seyirde titreme: komut 1 Hz'e düşüyor.** `mission1_node`
>   5 Hz basıyor, `formation_node`'a **~1.0–1.2 s** aralıkla varıyor (hem
>   liderde hem takipçide). 1 Hz = 2.5–3 m sıçrama → rampa 0.97 s'de bitiyor
>   → `v_ff` darbeli. **Seyreltmenin yeri BULUNAMADI**; Python tarafında
>   throttle YOK (`mission1_node._tick` · `esp32_bridge:3082` · `:2304`).
>   Liderdeki loopback de 1 Hz olduğu için darboğaz mesh'ten ÖNCE.
>   **Sıradaki ölçüm YERDE yapılır, uçuş gerekmez** (GUNLUK'ta tarif).
> - 🔴 **KUSUR 2 — aşağı-yukarıyı yalnız lider yaptı. Mesh kaybı geri
>   geldi:** d2 %6.7 · d3 %21.7 → `Stale ajanlar: [2]` →
>   `[SWARM FAILSAFE] Sağlıklı ajan oranı düşük: 1/3` → tarif `agent_ids=[1]`
>   → takipçiler komutu **sessizce** eledi. **Pil değişiminde uçaklar yer
>   değiştirdikten SONRA başladı** — `TUZAKLAR.md` §4.14 konum bağımlılığı.
>   ⛔ **Uçmadan önce `deploy/yki/mesh_kayip.py` ile ÖLÇ.** %5 üstündeyse
>   uçma, önce uçakları eski yerlerine/anten yönlerine koy.
> - 🟢 **KUSUR 3 — QR okunmadı: sebep LENS, yazılım değil.** Boru hattı
>   sağlam ölçüldü (`image_raw/compressed` **27.3 Hz**, 1 yayıncı 1 abone,
>   `lz=VAR`); kareyi çekip **gözle baktım, tamamen odak dışı.** Operatör
>   doğruladı: *"kameraya lens ayarı yapmadım"*. Lens ayarı için yayın
>   açıldı. ⚠️ **Sonuç BİLİNMİYOR** — uçaklar kapandı. Sonraki oturumun ilk
>   ölçümü: ylp00'da `~/yelpence_ws/algi_durum.json` → `qr_sayaci > 0` mı.
> - 🟢 **ylp00 kamerası artık ylp02'nin dengi:** algı imajı eşit
>   (`ea2c1b1e`), `cv2 4.6.0` + `pyzbar` var, zincir kare üretiyor.
>   🔴 **PIL yoktu** → yayın küçültme çalışmıyordu; ylp02'den kopyalandı,
>   ölçüldü: `128105 → 21869 bayt` (**%83**). `dagit.sh` bunu TAŞIMAZ.
> - ⚠️ **ylp00'da PİL ÖLÇÜMÜ YOK.** `PIL OLCUMU YOK` diyor, sabit
>   `%100 / 12.6 V` yayınlıyor — bu bir ÖLÇÜM DEĞİL. Eski "Kritik batarya:
>   12.6V" hayaleti buydu. **ylp00'ın pili ELLE ölçülecek.**
> - ⚠️ **`ucus_ayarlari.env` `dagit.sh` ile TAŞINMIYOR.** Yeni değerler
>   (`GOREV_KALKIS_IRTIFA=15.0` · `GOREV_QR_OKUMA_IRTIFA=10.0` ·
>   `ROTA_DIKEY_HIZ=0.5`) uçaklara ELLE `scp` edildi.
> - 🔌 **Üç uçak da KAPALI**, üçünde de `63f9870` yüklü + restart edilmiş.
>   Piller şarj edilecek.


> ## ☀️ 4 EYLÜL SABAHI — FORMASYONLARI ÖLDÜREN İKİ KÖK NEDEN KAPANDI
>
> **Üç uçuş yapıldı; formasyonlar üçünde de kurulamadı, iki ayrı kök neden
> ölçülerek bulundu ve kapatıldı. Ayrıntı `GUNLUK.md` 07:15 kaydı.**
>
> - 🟢 **Lider seçimi ÇALIŞIYOR (uçuş 3'te kanıt):** agent_fsm havada IDLE
>   yayınlıyordu (arming talebi yolu 2 Eylül'de kalkmıştı) → `_from_idle`
>   artık PX4'ün arm'ını tanıyor (IDLE→ARMED, bbc732c). Uçuş 3: seçim
>   0.4 sn, lider **ylp00**, kilit uçuş boyunca tuttu. Operatörün "kesin
>   lider ylp00" isteğini mevcut kural zaten sağlıyor (min id + tam kadro).
> - ✅ **B5 süzgeci KALDIRILDI (3b64e68) — 4 Eylül akşamı HAVADA GEÇTİ**
>   (yukarıdaki akşam kutusuna bak; aşağısı o günkü kayıt olarak duruyor). Uçuş 3'te
>   lider tarif bastı ama tarif mesh'e çıkmıyordu (B5 × tek-yayıncı
>   çatışması) → takipçi formation_node'ları boş kaldı. B5 + ic_dis_kopru
>   `formation/target` köprüsü kaldırıldı; artık tek üretici liderde
>   loopback, takipçide mesh RX. ⛔ **Sonraki uçuşun TEK sorusu bu:**
>   kilit aç + çizgi → ylp02 formation.log'da `FormationCommand alindi`
>   düşecek ve formasyon gözle kurulacak.
> - ⚠️ **Konteyner restart görev durumunu sıfırlıyor** — uçuştan önce
>   YKİ'den görev başlat, yoksa SwD "YETKİ YOK" der.
> - ⚠️ **Slot ataması hâlâ kimlik sırası** (Macar yok): uçakları yere
>   kimlik sırasına göre diz (d1 orta, d2 kuzeydoğu tarafı, d3 güneybatı —
>   ya da kuru testin dediğine uy). En-yakın-slot P2'de.
> - 🔌 Uçaklar KAPALI, üçünde de **3b64e68** yüklü + restart edilmiş +
>   `inspect` doğrulanmış. Piller %35/%41/%31 → şarj. Pi günlükleri
>   uçaklarda duruyor (çekilemedi — kapatılmışlardı), `loglar/20260904/`'te
>   yalnız yerel YKİ logu var.



> ## 🌅 2 EYLÜL SABAHI — OTONOM ZİNCİR AÇILDI, TEK KUSUR EVE DÖNÜŞTE
>
> **Beş uçuş yapıldı. Ayrıntı `GUNLUK.md` 09:10 kaydı.**
>
> - 🟢 **Görev 1 zinciri ilk kez uçtu:** tetik → arm → offboard →
>   `takeoff:10` → 10 m → `IN_SWARM` → `ROTATE` → `NAVIGATE` →
>   `RETURN_HOME`. Kanıt: **`passthrough` 0 → 677** (20 Hz setpoint akışı).
>   Önceki üç uçuşta 0'dı — formasyon zinciri hiç konuşmamıştı.
> - 🟢 **Beş sessiz arıza kapatıldı:** kalkış izni yoktu · `LANDED` tetiği
>   yutuyordu · irtifa çerçevesi uyuşmuyordu (1,06 m açık) · `_from_takeoff`
>   `pending_state` okumuyordu · hedefsizken setpoint boşluğu vardı.
>   Hiçbiri log'da görünmüyordu; **FAILSAFE artık sebebini yazıyor.**
> - 🔴 **RETURN_HOME'da başlık dönüyor — ÇÖZÜLMEDİ.**
>   `heading = bearing(centroid → home)`; sürü eve yaklaşınca vektör
>   kısalıp yön tanımsızlaşıyor. Ölçüldü: **5 saniyede 63°.** Slotlar
>   döndüğü için ylp00 komşusunun üzerine sürüklendi, operatör PosCtl'e
>   alıp elle indirdi, **az kalsın bahçe teline konuyordu.**
>   ⛔ **Bu kapanmadan RETURN_HOME'lu otonom uçuş YOK.** Düzeltme önerisi
>   ve yer testi sonucu GUNLUK'ta; kod YAZILMADI (RPi'ler kapalıydı).
> - 🔴 **QR tablosu uçaklara ULAŞMIYOR.** ROS tarafı bitti ve kanıtlandı;
>   baz ESP32 firmware'inin beyaz listesinde `TIP_QR_COORDS` yok, sessizce
>   atılıyor. **Firmware flash gerekiyor.**
> - ⚙️ **Pil kesmesi KAPALI** (`BATARYA_KESME=false`, operatör talimatı).
>   Pil ölçülüyor ve uyarı veriyor, ama uçağı FAILSAFE'e DÜŞÜRMÜYOR.
>   Kill switch, EKF, PX4 link ve **PX4'ün kendi pil failsafe'i** duruyor.
>   🔴 **Yarışma günü `true` yapılacak.**
> - ⚙️ Hedefsiz bekleme 30 → **10 sn** (`GOREV_ROTA_BILINMEYEN_S`).
>   🔴 Yarışma günü 30'a alınacak.
> - 🔌 **RPi'ler KAPALI.** Piller: ylp00 %38 · ylp02 %60 (kullanılmış).
> - ⚠️ Uçakların `/ws/ucus_ayarlari.env`'inde **elle eklenmiş dört satır**
>   var (`RPI_ESITLEME` B25/B29/B30). `dagit.sh` bu dosyayı TAŞIMAZ —
>   yeni bir Pi'de ya da temiz kurulumda tekrar eklenmeli.

> ## 🌙 2 EYLÜL GECESİ — HOME DOĞRULANDI, GÖREV 1 ZİNCİRİ KURULDU
>
> **Uçuş yok, gece boyu yer işi.** Ayrıntı `GUNLUK.md` 04:20 kaydı.
>
> - 🟢 **HOME artık ÖLÇÜLEREK doğrulanıyor** — `px4_bridge` 2 sn'de bir
>   home'u uçağın kendi GPS'iyle karşılaştırıyor, bozuksa **RTL'i
>   REDDEDİYOR** ve YKİ'ye kritik olay basıyor. Uçakta geçti:
>   **ylp00 0,33 m · ylp02 0,17 m.** Elle inceleme: `/ws/home_denetle.py`
>   ⚠️ **Eşik RTK'ya bağlı: RTK'siz 6,0/5,0 m · RTK'li 1,0/2,0 m.** İlk
>   sürüm 3,0/2,0 ile sahada yanlış alarm verdi (RTK yokken gezinme
>   3,75 m ölçüldü). **Otomatik düzeltme varsayılan KAPALI** — gürültülü
>   kaynakta düzeltmiyor, kovalıyordu (`TUZAKLAR` §2.29).
>   (⚠️ `/ws/` **kökünde**, `teshis/` altında değil).
>   🔴 Kök neden HÂLÂ BİLİNMİYOR — bu bir **dedektör**, çözüm değil.
>   Denetimin gerçek bir kaymayı yakaladığı sahada görülmedi.
> - 🟢 **`maneuver_executor` + `mission1` İLK KEZ AYAKTA** (ikisi de iki
>   uçakta, log temiz). `manevra` ve `gorev1` bayrakları açıldı.
> - 🟢 **Üç sessiz kilitlenme kapatıldı** — hepsi Görev 1 yolunda,
>   hiçbiri log'da görünmüyordu: formasyon susturmasında bayat-bırakma
>   yokluğu · `expected_agent_count=3` iken 2 uçak · `mission1`'e kadro
>   geçirilmemesi. Ayrıntı `TUZAKLAR` §2.28 ve GUNLUK.
> - 🔧 **ylp02'nin MAVROS'u DÜZELDİ** (`connected: true`). ylp00'da aynı
>   belirti çıktığında **donanım olmadığı ölçüldü** — seri hat 921600'de
>   882 geçerli çerçeve/3 sn; `docker restart` çözdü (`TUZAKLAR` §2.24).
> - 🔋 **Pil ölçeği operatör kararıyla değişti: 14,2 V = %0 · 16,8 V = %100.**
>   `BATARYA_KRITIK_V` **ilk kez etkin: 13,8 V** (önce 0,0 = izleme kapalı).
>   YKİ uyarıları açıldı — `Pil azaldı` %25, `Pil kritik` %10. Gerilim
>   dalgalanmasında tekrar bildirim yok (0,5 V eşiği).
>
> 🔴 **UÇAKTA DEĞİŞENLER — sonraki kişi böyle bulacak:**
>
> | | ylp00 | ylp02 | ylp01 |
> |---|---|---|---|
> | kod | `24e890d` | `24e890d` | 🔴 **hiçbir şey dağıtılmadı** |
> | `suru_dugumleri` | `... pil manevra gorev1` (+`joystick`) | `... pil manevra gorev1` | — |
> | `SURU_KADRO` | `1 3` | `1 3` | — |
> | `SURU_BEKLENEN_UCAK` | **2** (3'tü) | **2** | — |
> | kaçınma `rutbe` | 0 = ÇAPA | **1 = YUKARI** (2'ydi) | — |
> | `BATARYA_KRITIK_V` | **13,8** (0,0'dı) | **13,8** | — |
> | düğüm sayısı | 18 | 16 | — |
>
> 🔴 **ylp02'nin kaçış yönü AŞAĞI'dan YUKARI'ya döndü** — iki uçaklı
> kadroda rütbe yeniden türedi. Bilinçli, ama uçuştan önce bilinmeli.
>
> 🔴 **ylp01 her şeyde geride.** Üç uçakla teste geçmeden `RPI_ESITLEME`
> B20-B23 uygulanmalı **ve** `ucus_ayarlari.UCAN_KADRO` `(1,2,3)` yapılmalı
> — yoksa ylp01 kadroda yok sayılır.
>
> ⚠️ **Görev 1 zinciri yerde tamamlanamaz:** manevra adımına
> (`EXECUTE_QR_TASK`) ancak `SYNCHRONIZED_TAKEOFF`'tan geçilerek gelinir
> ve o durumun girişi sürüyü **ARM eder**. Otonom manevrayı `mission1`
> olmadan sınamak mümkün ve daha doğru — GUNLUK'ta tarif var.
>
> 🔋 **Piller şarjda** (oturum sonunda alındı). ylp00 %14'e inmişti.

> ## 📷 1 EYLÜL AKŞAMI — KAMERA ONARILDI, JÖLE ARTIK BİR SAYI
>
> **Uçuş yapıldı ama karanlıkta**, jöle ölçülemedi. Ayrıntı `KAMERA.md` §12.
>
> - 🔧 **ylp02'nin kamerası çalışıyor** — 4K dahil her kip, 30,1 fps, sapmasız.
>   Arıza **yeni takılan moduldeydi** (I²C'ye cevap veriyor, CSI verisi yok).
>   **Eski modül sağlam, düşüşten zarar görmemiş.** Flex de sağlam.
> - 📏 **Jöle ölçülüyor:** `deploy/rpi/teshis/jole_olc.py`. Doğrusal
>   makaslamayı (zararsız) artık dalgalanmadan (QR'ı öldüren) ayırıyor.
>   **28 Ağu yalıtımsız 6,0-12,0 px · yalıtımlı 1,0-2,1 px · motorsuz taban
>   0,73 px.** Hedef uçuşta ≤ 0,8.
> - 🔴 **Karanlıkta ölçüm YAPILMAZ** — kontrast < 12 ise betik "GEÇERSİZ"
>   diyor. Akşam kaydında metrik 4,02 px uydurmuştu; operatör kaydı izledi,
>   dalgalanma yoktu.
> - 🔧 **YKİ RPi butonu düzeltildi** — `drone_bul.sh ip_bul()` tek isim
>   hızlı yolu. **8,0 sn → 0,3-0,5 sn.** Filo listelerindeki 26 Ağustos
>   koruması bozulmadı.
> - 📶 **Ağ yavaş (0,8 MB/s) ama uçakla ilgisi yok** — `rpissid` 2,4 GHz
>   kanal 6, airtime çekişmesi (RTT ort 43,8 / tepe 163 ms). CPU, disk,
>   sinyal temiz.
>
> **ylp02'de dikkat edilecekler:**
>
> - ⚠️ **Kamera servisi kendiliğinden BAŞLAMIYOR:**
>   `setsid nohup python3 ~/yelpence_ws/kamera_yayin.py > /tmp/kamera_yayin.log 2>&1 < /dev/null &`
> - ⚠️ **`kamera_yayin.py` `dagit.sh` ile taşınmıyor**; uçakta **iki kopya**
>   var — `~/yelpence_ws/` doğru olan, `~/kamera_yayin.py` bayat (28 Ağu).
> - ⚠️ **Kamera modülü değişirse KAPAT-AÇ şart** (sürücü yalnız açılışta bağlar).
> - ⚠️ 4K'da tarayıcı sekmesi açıkken CPU %91, arayüz cevap vermiyor.
>
> ✅ **ÇÖZÜLDÜ (2 Eylül): ylp02'de MAVROS `connected: true`.** Aşağıdaki
> kayıt tarihçe — ve ylp00'da aynı belirti çıktığında **donanım olmadığı
> ölçüldü**, `docker restart` çözdü (`TUZAKLAR` §2.24). Eski kayıt:
>
> ~~🔴 **ylp02'de MAVROS PX4'E BAĞLI DEĞİL**~~ (1 Eylül 22:30 ölçümü):
> `connected:false` · `mode:"?"` · `imu_healthy`/`baro_healthy`/`mag_healthy`
> **üçü de False** · `imu/mag` ve `raw/fix` yayını yok. Barometre ve IMU iç
> mekânda da çalışır — bu "GPS yok" değil, **FCU ile konuşulmuyor.** Açık
> P0 olan **gevşek güç soketiyle** aynı sınıf; uçak bugün çok elden geçti.
> *Operatör çözeceğini söyledi, açık bırakıldı.*

> ### 🔴 UÇMADAN ÖNCE OKU — 1 Eylül
>
> | uçak | durum |
> |---|---|
> | **ylp00** | 🔴 **UÇMASIN.** İki bağımsız denemede PX4 `Attitude failure (roll)` → failsafe. Uçak fiziksel olarak yattı. Önce **şarjlı pil** (kalkışta 15,29 → 14,72 V çöktü, %58'di), sonra pervane/motor/kol kontrolü. |
> | **ylp01** | 🟢 sağlam · pil %58 (15,32 V) |
> | **ylp02** | 🟠 düştü, **kırık yok**, şu an sağlıklı (pusula 10 Hz, RTK). Havadaki `Failsafe activated` → ALTCTL sebebi **BİLİNMİYOR**. Here4 konnektörü elle sarsıldı, arıza tekrar üretilemedi. Tekrar uçurmak operatör kararı. |
>
> **Uçaklardaki ayarlar (üçünde de `ros2 param get` ile doğrulandı):**
> `morf_hiz_mps=0.6` · `morf_sure_s=25.0` · `deadman_zaman_asimi_s=0.5`
> `max_yaw_rate_deg_s=14.7` · `max_speed_mps=2.0` · `default_spacing_m=7.0`
> `kalkis_irtifa_m=5.0` · CA `dikey_bekle_orani=0.8` · `test_hazir_atla=False`
>
> 🔴 **`/ws/mod_test` SİLİNDİ** — görev YKİ'den BAŞLAT'a basılmadan sürü
> READY olmuyor (G2-K10'un üçüncü kapısı artık gerçekten çalışıyor).
>
> 🔴 **Manevra modu düzeltildi ama UÇAKTA DOĞRULANMADI** — hiçbir uçuş
> manevra moduna ulaşamadı. Tek soru: "manevraya geçince irtifa korunuyor mu?"
>
> ⚠️ **Kaçınmanın dikey katmanı 5 m'de sığmıyor** (dikey iniş tabanı 4,0 m).
> Kaçınmaya güvenilecek uçuşta irtifa ≥ 8 m olmalı — YKİ'de "İrtifa (m)"
> kutusuna 8 yazmak yeterli, dağıtım gerekmez.
>
> ⚠️ **KARAR-14 açık**: varsayılan aralık 7 m mi 9 m mi. Şu an **7**.
>
> 🟠 **Şartname örnek aralığı 5 m**, kaçınmanın çıkış eşiği 6,5 m — hakem
> "5 metre" derse kaçınma bir kez açılınca kapanmaz. Görev günü riski.
>
> 🟢 ylp02 diski %66 (9,6 GB boş). Uçuş kayıtlarına dokunulmadı.

## 1. Filo

**Üçü de uçuyor.** 28 Ağustos akşamı üç uçak birlikte, tek uçuşta formasyon
geçiş sekansını tamamladı.

| İHA | agent_id | Konteyner | Kadro rütbesi (CA) | Durum |
|-----|----------|-----------|--------------------|-------|
| ylp00 | 1 | `drone1` | **0 = ÇAPA** — dikeyde kaçmaz | Uçar. CA testlerinde yaklaştıran uçak bu olmalı |
| ylp01 | 2 | `drone2` | 1 = YUKARI kaçar | Uçar. 25 Ağu'da onarım zinciri kapandı (yeni Pi + ESP + Pixhawk). ⏳ Pil sensör kartı yok — tok pil + süre sınırıyla uçuluyor |
| ylp02 | 3 | `drone3` | 2 = birincil AŞAĞI | Uçar. **Kamera bu uçakta** (IMX477). 4,8 m altında taban aynası YUKARI'ya çevirir |

> ⚠️ **İsim ile numara aynı değil:** ylp00 → drone**1**, ylp02 → drone**3**.

> 🔴 **ylp02 PX4 güç soketi — kabul testi HENÜZ kayda geçmedi.** Operatör
> 28 Ağustos akşamı "halledildi" dedi. Uçuş sabahı: **kabloyu bilerek 3 kez
> oynat, üçünde de reboot gelmemeli.** Gevşek temas yerde kusursuz, titreşimde
> bozuk — ve güç kesilirse uçuş kontrolcüsü ölür.
>
> ⚠️ 2 Ağustos'ta ylp01'in düşüşü **hâlâ tam aydınlanmadı** (sebep elektrikseldi:
> ESC güç/sinyal hattı; log'da yalnız motorlar durmuştu). Aynı sınıf arıza.

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

### 🖥 QGC — operatörün kendi işi

**29 Ağustos 2026 operatör kararı:** QGC kurulumu ve 14550 link kontrolü
**uçuş öncesi listede değil.** Operatör bu süreci kendi makinesinde kendisi
yönetiyor; Claude sormaz, uçuşu bunun için durdurmaz.

Yine de bilinmesi gereken üç ayar — bir şey ters giderse buraya bak:

| Ayar | Doğrusu | Yanlışsa belirtisi |
|---|---|---|
| Comm Links → UDP, **dinleme portu 14550** | elle eklenmiş, bağlı | Uçaklar `udp-b` ile **süresiz yayında** kalır; telefon hotspot'unda laptopun interneti ölür (ölçülen tepe 14,5 sn). Tek link üç uçağı birden taşır |
| AutoConnect → **RTK GPS kapalı** | kapalı | QGC u-blox baz istasyonunun seri portunu kapar, `yki_rtcm_reader` açamaz (`Resource busy`), **RTCM hiç akmaz** — tek işaret `fix_type`'ın 6 yerine 3-5'te takılması |
| AutoConnect → **UDP kapalı** | kapalı | Otomatik link elle eklenenle çakışır |

```bash
ss -ulnp | grep 14550     # QGroundControl gorunmuyorsa link YOK/kopuk
```

⚠️ QGC'nin **açık olması yetmez** — `[LinkConfigurations]` boş ve
`autoConnectUDP=false` bir QGC kurulumunun **varsayılan hâlidir.**
Keşfedilen karşı taraf unutulmadığı için QGC'yi **sonradan kapatmak sorun
değil**; ama her `docker restart` MAVROS'u yeniden başlatıp pencereyi
yeniden açar. Tam ölçümler ve kök neden: `TUZAKLAR.md` §7.1 · §6.6.


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

**Bu sınır KALKTI (27 Ağustos 2026).** Eskiden burada "diğer `SystemEvent`'ler
YKİ'ye ulaşmıyor, mesh'te `TIP_EVENT` yok" yazıyordu; **artık yanlış** —
`TIP_OLAY` (0x16) eklendi ve uçağın **kendi ürettiği bütün** olaylarını
YKİ'ye taşıyor (`esp32_bridge._on_olay_out`). Alıcı taraf komşunun olayını
`/swarm/public/events/system`'e düşürüyor, YKİ oradan okuyor.

İki bilinçli süzgeç var:
- `EVENT_UNKNOWN` (0) mesh'e **çıkmaz** — `_diag_yayinla` saniyede bir bu
  tiple yerel sağlık sayacı yayınlıyor, mesh'i boşuna doldururdu (27 Ağustos
  canlı testinde bulundu).
- Yalnız **kendi** olayımız gider (`source_agent_id` ∈ {0, kendi id}); biri
  public'i internal'a köprülerse geri besleme döngüsü kurulmasın diye.

⚠️ Mesh 16 bayt taşıdığı için olayın **metni gitmiyor**, yalnız kodu. YKİ
etiketi enum'dan kuruyor (`SYSTEM_EVENT_LABELS`, 29 etiket) ve `value` +
`source_module` alanlarını ekliyor. Yani YKİ'de gördüğün olay metni uçakta
yazılmış cümle değil, YKİ'nin kod karşılığı.

---
## 3. Uçakta açık olan bayraklar

> ### 🔴🔴 UÇAKLARDA ARTIK OLMAMASI GEREKEN BİR ŞEY VAR
>
> `~/yelpence_ws/pil_testi.py`, `pil_testi_calistir.sh` ve
> `~/yelpence_ws/pil_testi/` (CSV'ler). 3 Eylül gecesi pil testi için
> yazıldı, denendi, **depodan geri alındı** — ama uçaklardan silinemedi:
> oturum kapanırken üçü de ağda değildi. **İlk iş bu** (`YAPILACAKLAR.md`
> en üstteki P0; silme komutu orada).
>
> ⚠️ ylp01'de kayıt sürecinin durup durmadığı **doğrulanamadı** — uçak o
> sırada ağdan düştü. Sürüyorsa disk ve CPU yiyor.


Bunlar **dosya varlığıyla** çalışıyor; uçağı bulan kişi böyle bulacak.
Aksi yazmıyorsa **üç uçakta da aynı.**

| Bayrak | Değer | Anlamı |
|--------|-------|--------|
| `~/yelpence_ws/suru_dugumleri` | 🔴 **ÜÇÜNDE DE + `mod`** · ylp01·ylp02: `origin consensus fsm formasyon ca mod` · **ylp00: + `joystick`** (30 Ağu 13:45, G0 madde 16 için açıldı — `rc_ibus_kopru` + `joystick_interpreter` koşuyor, mesh'e `TIP_KOMUT` basıyor. `mod` kapalı olduğu için **tüketicisi yok**. Uçuştan önce bilinçli karar ver) | Varsa `SURU_DUGUMLERI` env'ini ezer. Düğüm açmak: `echo ... > dosya` + `docker restart`. `sekans` anahtarı 28 Ağu testinden sonra SİLİNDİ |
| `~/yelpence_ws/gozlem` | **YOK** | Formasyon uçağı **DOĞRUDAN SÜRER**. Bu yüzden mesh `goto` uçağa gitmez (tek-üretici geçişi). Eski düzen için `touch /ws/gozlem` + restart |
| `~/yelpence_ws/yer_testi` | **YOK** | Uçaklar kalkış komutunu **ALIR**. Yer testine dönüş: `touch` + restart |
| `~/yelpence_ws/origin` | **var** | `38.6904758 39.1610188 1216.96` — tek kaynak `deploy/saha_origin.env`. Elle yazma, `dagit.sh` dağıtır. **Üçünde de AYNI olmalı**, yoksa formasyonlar uçaktan uçağa kayar |
| `~/yelpence_ws/ucus_ayarlari.env` | **var** | Seyir 3.0 m/s. `ucus_ayarlari.py --kabuk` üretir — elle yazma 🔴 **3 Eylül'de üç yeni alan geldi**, üçü de dağıtıldı ve canlı ölçüldü: `SURU_LIDER_KILIDI=true`, `SURU_LIDER_KILIT_TAM_KADRO_S=8.0`, **`GOREV_DONUS_YAW=0.0`** (eskiden 180 — artık dönüş açısı ev yönünden türüyor, bu alan yalnız EK ofset). Konteyner yeniden başlatılmadan geçerli olmaz |
| `~/yelpence_ws/gcs_url` | var | MAVLink QGC'ye iletiliyor (`udp-b://:14555@14550`) |
| `~/yelpence_ws/tgt_system` | ylp02'de `3` | ylp02'nin FCU sysid'i 3 |
| `BATARYA_KRITIK_V` | 🔋 **`13.8`** (2 Eyl) | **Pil izleme AÇIK** — INA226 gerçek ölçüm veriyor (KARAR-03'ün koşulu gerçekleşti). Gösterge %0'ı 14,2 V; eşik bilerek altında, çünkü `healthy` ANLIK gerilime bakıyor ve tek bir çöküş dikeni tüm sürüyü acil inişe sokabilirdi |
| `~/yelpence_ws/gps_saat_kapali` | yok | Varsa GPS'ten saat düzeltmesi yapılmaz |
| `~/yelpence_ws/mod_test` | 🔴 **ÜÇÜNDE DE VAR** (30 Ağu 13:55, G0 için) | Görev 2 G0 bayrağı: `mission_fsm` kapalıyken `mode_manager` FSM'ini READY'ye ulaştırır (`test_hazir_atla`). **Kalkış kapısını BAYPAS ETMEZ.** Uçuş öncesi kaldırılması operatör kararı |
| ~~`~/yelpence_ws/kacinma`~~ | **kaldırıldı** | 🔴 `basit_kacinma` 29 Ağu'da silindi. Dosya bir uçakta duruyorsa **`baslat.sh` hata verip durur** — sessizce korumasız kalmasın diye |


### 🔴 UÇMADAN ÖNCE: `yer_testi` bayrağını kaldır

```bash
./deploy/yki/drone_bul.sh ylp00 'rm -f ~/yelpence_ws/yer_testi ~/yelpence_ws/gozlem && docker restart drone1'
./deploy/yki/drone_bul.sh ylp02 'rm -f ~/yelpence_ws/yer_testi ~/yelpence_ws/gozlem && docker restart drone3'
```

Açık kaldığı sürece "görev başladı" komutu uçağı ARM eder ve **orada
bırakır** — kalkış komutu gönderilmez. Yer testleri için var.

### 🔴 Yer testinden çıkış: **kumandadan kill switch** — 20 Ağu · **30 Ağu'da ÜÇÜNCÜ KEZ**

> **30 Ağustos 2026:** Görev 2 G0'ında SwD sürüyü ARM etti, pervanesiz OFFBOARD'da
> integral sardı, PX4 "flying" dedi ve **YKİ'nin disarm'ı reddedildi**
> (`MAV_RESULT=1`). Kill kumandaları kapalıydı; olay `agent_fsm`'in kendi zaman
> aşımıyla bitti. Kök neden `mode_manager`'ın `EVENT_MISSION_STARTED`
> yayınlaması — kaldırıldı. Tam kayıt: `gorev2.md` §2.
> **Ders: `mod` açıkken kill pilotları başında olmalı.**

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

### ✅ Pil izleme AÇIK (2 Eylül 2026) — eskiden üç yerde birden kapalıydı

**Üçü de açıldı (2 Eylül):**

1. `BATARYA_KRITIK_V` = **13,8 V** — `ucus_ayarlari.PIL_KRITIK_V`'den env'e
2. `PIL_GOSTER = true` (zaten açıktı)
3. `config.yaml` → `alerts.pil: true`, `susturulan`'da yalnız `link_timeout`

**Kaynak INA226'dır, PX4 DEĞİL.** 2 Eylül'de ölçüldü: MAVROS
`voltage: 65.535` (0xFFFF sentinel), `percentage: -0.01` — yani PX4'ten pil
okuması **yok**. INA226 → `AgentStatus` yolu çalışıyor.

**Gösterge: 14,2 V = %0 · 16,8 V = %100** (4S). Eşikler: `Pil azaldı` %25
(14,85 V) · `Pil kritik` %10 (14,46 V).

⚠️ **Yüzde yük altında ~%22 puan düşer** — ölçüldü: dururken 15,29 V (%42),
motorlar kalkışta 14,72 V (%20). Yüzde göstergedir; koruma gerilim tabanlı.

---
### ⚠️ ylp01 pil gerilimi ŞÜPHELİ (3 Eylül, ölçüldü)

```
ylp00  16.60 V  %92      ylp01  12.50 V  %0      ylp02  14.60 V  %13
```
4S'te 12.50 V = hücre başına **3.12 V**, derin deşarj bölgesi. Kalibrasyon
çarpanı bunu açıklamıyor (ylp01'inki 0.95061, değeri **aşağı** çekiyor;
16.6 V okumak için ham ~17.5 V gerekirdi). İki ihtimal: **boş/farklı pil
takılı** ya da **INA226 kablosu/kalibrasyonu bozuk**. 🔴 Uçurmadan önce
multimetreyle bak; ölçülen değerle `python3 src/gcs/pil_kalibre.py`.

---

## 4. Kod senkronu

```
ucaklarda (uc de) : .surum -> bc42d00 (main) +KIRLI
                    paketler = swarm_state_machine + swarm_control
                    31 Agustos 06:00, uc ucaga da dagitildi ve DOGRULANDI
repoda            : bc42d00 + calisma agacinda ayni degisiklikler
                    (mesh home_set + gorev yayilimi dahil)
tam recreate      : 193c224, 30 Agustos 13:30 (restart degil, recreate)
```

> ✅ **DAGITIM YAPILDI (31 Agustos 06:00).** Asagidaki uyari KAPANDI ama
> gerekcesi ogretici oldugu icin duruyor:
>
> ~~🔴 **UCAKLARDAKI KOD ARTIK BIR TUR DAHA ESKI — ve bu sefer TEHLIKELI.**~~
> 31 Agustos'ta suru kumandasi degisti ve `rc_eksen.TERS_YAW` **True'dan
> False'a** cekildi (yeni kumandada yaw sagi UST uca veriyor). Ucaklardaki
> kod hala `TERS_YAW = True`:
>
> **Bugun dagitim yapilmadan ucusulursa pilot SAGA cevirir, suru SOLA
> doner** — ve hicbir yerde hata gorunmez. Dagitim ZORUNLU.
>
> Dagitilacak paket: `swarm_state_machine` (tek paket yeter; `swarm_core`
> ve mesajlar degismedi). Ayrica `/ws/suru_dugumleri`'ne **`gorevfsm`**
> eklenecek (ucune) ve `MOD_SWC_DEBOUNCE_MS=1300` env'e gecmeli.

> 🔴 **`.surum` burada YANILTIYOR ve nedeni öğretici.** `+KIRLI`, dağıtımın
> commit'lenmemiş bir çalışma ağacından yapıldığını söylüyor: `.surum`
> `5515c20` yazıyor ama uçaktaki dosyalar **`a48ca98`'in içeriğini** taşıyor
> (saha olayı düzeltmesi). **Ölçerek doğrulandı, 30 Ağu 15:50** — dosyada
> imza arandı, `.surum`'a güvenilmedi:
>
> | | ylp00 | ylp01 | ylp02 |
> |---|---|---|---|
> | `EVENT_MISSION_STARTED` kaldırıldı (olay düzeltmesi) | ✅ | ✅ | ✅ |
> | madde 24 (`_inis_komutu_gonder`) | ❌ | ❌ | ❌ |
>
> Yani **saha olayının kökü üç uçakta da kapalı**; kumandadan iniş **henüz
> uçakta yok.** Sürüm kontrolü yaparken `.surum` yerine **dosyada imza ara.**

### ✅ 30 Ağustos recreate — üç uçakta doğrulandı

| | ylp00 | ylp01 | ylp02 |
|---|---|---|---|
| `baslat.sh` md5 | depo ile AYNI | AYNI | AYNI |
| **`ROS_LOCALHOST_ONLY=1`** | ✅ | ✅ | ✅ |
| `--device /dev/ttyAMA2` | ✅ **var** | yok (alıcı yok) | yok (alıcı yok) |
| bizim düğümler | 11 | 11 | 11 |
| `TEK-URETICI (ADIM 3)` | ✅ | ✅ | ✅ |
| disk boş | 17 G | 18 G | **5,7 G (%80)** |

> **A19 kapandı.** Artık `docker exec ... ros2 node list` düğümleri
> güvenilir görüyor; öncesinde **sessizce boş** dönüyordu (`TUZAKLAR` §1.25).

> ⚠️ Açılış logunda **`CARPISMA KACINMASI ACIK` YOK, `TEK-URETICI` VAR** —
> bu **doğru**. `baslat.sh`'te ikisi birbirini dışlayan dallar: formasyon
> sürerken TEK-URETICI basılır. Kaçınma yine koşuyor (düğüm listesinde).
> `YAPILACAKLAR` "ikisi de görülmeli" diyordu, **yanlıştı.**

> ⚠️ **ylp02 diski %80 dolu.** Diğer ikisi %39-42. 14 Ağustos'ta iki uçağın
> diski %100 dolup uçuş kaydını öldürmüştü — göz önünde tutulmalı.

### 🔴 Uçaklar artık UÇAK TARAFI KODA DA geride

29 Ağustos'ta fark yalnız YKİ + belgeydi. **30 Ağustos'ta Görev 2 çalışması
uçakta koşan koda girdi.** Dağıtılmamış olanlar:

| Dosya | Ne değişti | Bugün koşan davranışa etkisi |
|---|---|---|
| `deploy/rpi/baslat.sh` | `joystick` iki düğüm açıyor, remap'ler, `mod` param'ları, `/ws/mod_test`, `fsm` uyarısı | Görev 2 anahtarları kapalı → **etki yok** |
| `deploy/rpi/run_drone.sh` | koşullu `--device` (suru RC alıcısı) | konteyner recreate'te geçerli |
| `swarm_control/rc_ibus/` | **YENİ düğüm** + testleri | anahtar kapalı → etki yok |
| `esp32_bridge_node.py` | B5 süzgeci (`source_module == 'mode_manager'`) | `mode_manager` kapalı → **etki yok** |
| `mode_manager/*` | B3/B4/B5/B7/B8/B10/B15 + G2-K6 | düğüm kapalı → etki yok |
| `swarm_core/manual_kinematics.py` | `dairesel_ortalama_deg` **eklendi** (`apply_tilt` değişmedi) | Görev 1 davranışı **aynı** |
| 🔴 `swarm_fsm/*` | **B17: `formation_heading_deg` artık HESAPLANIYOR** | **`swarm_fsm` ŞU AN KOŞAN 11 DÜĞÜMDEN BİRİ** |
| 🆕 `mode_manager/*` + `swd_mandal.py` | **madde 24 — kumandadan iniş** (`land` doğrudan `px4_bridge`'e, 1 Hz tekrarlı) | `mode_manager` açık ama **iniş yolu uçakta YOK** — commit edildi, **dağıtılmadı** |

> 🔴 **Tek gerçek davranış değişikliği `swarm_fsm`.** Bugüne kadar
> `SwarmState.formation_heading_deg` kalıcı `0.0` gidiyordu; dağıtımdan
> sonra uçakların yaw ortalamasını taşıyacak. Tüketicileri: `mode_manager`
> (kapalı) ve **YKİ arayüzü** (bugün 0 gösteriyordu, gerçek değer görecek).
> Uçuşu süren zincirde tüketicisi **yok** — ama sonraki dağıtımdan sonra
> YKİ'de bu alanın değişmesi **beklenen** bir şeydir, arıza değil.

⚠️ `swarm_core` ve `swarm_state_machine` değiştiği için dağıtımda
`--paket` ile tek paket derlemek **yetmez**; ikisi de derlenmeli.

**29 Ağustos dağıtımının doğrulanmış hâli** (üç uçakta da aynı):

| | ylp00 | ylp01 | ylp02 |
|---|---|---|---|
| `baslat.sh` md5 | depo ile AYNI | AYNI | AYNI |
| `ros2 node list` | 79 | 79 | 79 |
| bizim düğümler | 11 | 11 | 11 |
| mesh komşu tazeleme | 10,7 / 10,8 Hz | 10,7 / 11,9 Hz | 10,8 / 11,7 Hz |
| `basit_kacinma` · `kinematic_fusion` | silindi | silindi | silindi |

⚠️ **`.surum` dosyasına tek başına güvenme** — `dagit.sh` derleme başarısız
olsa bile `.surum` yazıyor (`TUZAKLAR.md` §1.14). Senkron kontrolü artık
`drone_bul.sh --durum` içinde (md5 + düğüm sayısı).

### ⚡ Kod değişikliğinde tam restart gerekmiyor (29 Ağustos)

```bash
./deploy/rpi/dagit.sh --paket swarm_core ylp00          # yalnız o paket derlenir
./deploy/yki/drone_bul.sh ylp00 \
    'docker exec -d drone1 bash /ws/baslat.sh --yalniz ca'   # yalnız o düğüm
```

`--yalniz` **mavros, px4_bridge, agent_fsm, esp32_bridge, uçuş kaydı ve
günlük bekçisine dokunmaz**; yeni günlük dizini de açmaz (mevcut `son`
dizinine yazar). Gating değişkenleri (`SP_REMAP`, `VELOCITY_ONLY`, boş yuva
kapısı) normal açılıştaki gibi `/ws/suru_dugumleri`'nden hesaplanır — yani
`--yalniz formasyon` derken CA kapalı sanılmaz.

| | Tam `docker restart` | `--yalniz <düğüm>` |
|---|---|---|
| Sabit `sleep` | ~50 sn | ~2 sn |
| MAVROS / PX4 el sıkışması | yeniden | dokunulmaz |
| RTK kilidi · consensus seçimi | yeniden | korunur |
| `colcon build` | 6 paket | `--paket` ile 1 |

> 🔴 **Uçuş sırasında kullanma.** Düğüm saniyelerce yok olur; kaçınma ya da
> formasyon o pencerede sessizce devre dışı kalır.
>
> ⚠️ Bir `.msg`/`.srv`/`.action` değiştiyse `--paket` **kullanma** — arayüz
> değişip bağımlılar yeniden derlenmezse eski başlıklarla koşarlar ve hata
> yerine **yanlış veri** alırsın.

🔴 **29 Ağustos sadeleştirmesi `baslat.sh`'i değiştirdi** (`basit_kacinma` ve
`fusion` blokları kalktı). Dağıtımdan sonra açılış logunda şu satırlar
görülmeli: `CARPISMA KACINMASI ACIK (collision_avoidance)` ve
`TEK-URETICI (ADIM 3)`.

---

## 5. Sahada koşan düğümler

```
mavros_node · px4_bridge · agent_fsm_node · esp32_bridge
+ collision_avoidance · ic_dis_kopru · swarm_origin_publisher
+ consensus_node · swarm_fsm_node · formation_node · path_planner
```

**11 düğüm.** (`ros2 node list` toplam ~80 gösterir; fazlası MAVROS'un
eklenti alt düğümleri, normal.)

`ic_dis_kopru` herhangi bir sürü düğümü açıksa kendiliğinden kalkıyor —
sözleşmenin `internal → public` yerel döngüsünü o kuruyor.

**Görev düğümleri KAPALI** — Görev 1'in tamamı bunlara bağlı:
`mission1`, `mission_fsm`, `camera_driver`, `vision_node`,
`precision_landing`, `task_reallocator`, `maneuver_executor`.
Görev 2 için: `mode_manager`, `joystick_interpreter`.

### Lider seçimi — ölçülmüş davranış

Consensus hem yerde hem havada çalışıyor. Yerde iki uçak **aynı lideri**
101 ms arayla seçti; kill switch lideri FAILSAFE'e düşürünce devir
**82 ms**'de oldu. Havada 21 Ağustos'ta ölçüldü: split-brain sıfır, kalp
atışı boşluğu maks **218 ms** (eşik 1000), DURUM maks **408 ms** (eşik 5000).

⚠️ Guided yolda ajan `agent_fsm`'i atlıyordu ve consensus hiç seçim
yapamıyordu; `esp32_bridge` guided ARM'da yerel `EVENT_MISSION_STARTED`
üretince kapandı. Kalkış otoritesi guided'da (`kalkis_olayla=false`).

⚠️ **P1.14 açık:** lider kimliği mesh'e kalp atışıyla taşınıyor, seçim
çerçevesiyle değil → **asimetrik kopmada iki lider kalıcı olabilir.**
Bugün zararsız değil — formasyon uçağı sürüyor. Görev düğümleri açılmadan
önce çözülmeli.

---


## 6. Kanıtlanmış / doğrulanmış olanlar

Bunlar sahada ölçüldü, tekrar sorgulanmasın:

- **Uçuş kanıtı videosu geçildi.**
- **Üç uçaklı formasyon geçiş sekansı uçtu** (28 Ağustos): çizgi→ok→V→çizgi→EVE,
  tamamen uçakta, tek YKİ butonuyla. `avoid=0`, en yakın çift ~8,0 m, 123 s.
- **Otonom çarpışma önleme havada** (22-26 Ağustos): dikey yol verme, üç uçaklı
  testte 4/4 kaçış-dönüş, taban aynası ×2, sıfır körlük.
- **Görev koşucusu** `--senaryo saha`: 5 nokta, 8→15 m, çizgi↔okbaşı formasyon
  değişimi, rotasyonlar, 135° güneydoğuya dönüp iniş. ~187 s görev / ~222 s video.
- **Kuru test** kritik ayrım **8.41 m** (eşik 4.0 m) — `SONUÇ: GEÇTİ`
- 🟢 **KUMANDADAN ÜÇ UÇAKLI KALKIŞ/İNİŞ** (31 Ağustos 15:52, pervaneli):
  SwD ile üçü birlikte kalktı (**0,24 sn** içinde ARM), 5 m'de 20 sn asılı
  durdu, SwD ile birlikte indi (**0,14 sn** içinde COMPLETED). Ölçülen:
  en dar uçak arası **6,70 m sabit** · gerçek roll/pitch tepe **3,3° / 5,3°**
  · **sıfır** mod kavgası · sürüye giden dikey komut **+0,00** (ham gaz
  kanalı uçuş boyunca dipteyken). Uçuş 122 sn, tek müdahale yok.
- **B19 çıkışı**: üçü de `COMPLETED → IDLE → PREFLIGHT`'e döndü (0,14 sn
  içinde) — ikinci deneme için konteyner yeniden başlatmak GEREKMİYOR.
- **VrB formasyon ana anahtarı** (31 Ağustos): kapalıyken sürüye giden
  formasyon `0`, SwC bir formasyon konumunda dursa bile. Yerde ve havada
  doğrulandı. Kanal: VrB → ch10 → `aux6`, eşik aux 800 (~PWM 1900).
  (aralık 12 m'ye çıkınca 7.07'den yükseldi)
- **RTK-FIX üç uçakta birden** (25 Ağustos, taze survey, 1005 canlı); baz
  `1005` dahil tam RTCM seti yayınlıyor.
  **18 Ağustos'ta baz MSM4'e alındı** — akış artık `1005, 1074, 1084, 1094,
  1124, 1230` @ ~1 Hz, `crc_err=0` (öncesinde MSM7 vardı ve okuyucu uyarıyordu;
  `YELPENCE_RTCM_SPEC.md` §401 MSM4 bekliyor).
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
| 1 | 🟠 **HOME kayması — kök neden hâlâ bilinmiyor, ama artık GÖRÜNÜR** | RTL üç uçağı kalkışa değil aynı yanlış civara indirdi (~9 m KD). 2 Eylül'de **dedektör eklendi**: home ölçülerek doğrulanıyor, bozuksa RTL reddediliyor + YKİ'ye kritik olay. Uçakta geçti (0,48 / 0,83 m). 🔴 **Yakalama yolu sahada sınanmadı**; RTL'li uçuş hâlâ operatör kararı | `YAPILACAKLAR` P0 |
| 2 | 🔴 **MAVROS GCS denetimi yalnız açılışa bakıyor** | Taşkın sonradan başlıyor: 27 Ağu'da üçü de "temiz" raporlanmışken 5 M hata / 522 MB. Otomatik onarım **yalnız Pi uptime < 15 dk**; sonrası operatörde (SSH + restart) | `YAPILACAKLAR` P0 |
| 3 | 🟠 Görev düğümleri hiç uçmadı | Görev 1'in tamamı bunlara bağlı: `mission1`, `mission_fsm`, `vision_node`, `precision_landing`, `task_reallocator`, `maneuver_executor` | `PLAN.md` §8 |
| 4 | 🟡 Görev 2 **yerde koştu, havada koşmadı** | Aşama D dağıtıldı ve doğrulandı: iniş · görev başlatma · kapılar. **Pervaneli uçuş YAPILMADI** | `gorev2.md` §7.13 |
| 4f | 🔴 **`MOD_ARALIK=9.0` uçaklara GİTMEDİ** | Formasyon geçişi için aralık 7→9 m çıkarıldı (ölçümle, `ucus_ayarlari.py`), ama uçuş sonrası yapıldı ve uçaklar kapalıydı. **Formasyon uçuşundan önce env dağıt + konteyner restart** — yoksa uçakta 7 m geçerli ve okbaşı→V morfunda kaçınmaya pay 0,95 m kalır | 31 Ağu |
| 4d | 🔴 **Üçünde de `mission_state=8`** | Üçüncü kapı AÇIK: **SwD-yukarı üç uçağı birden armlar.** Konteyner restart'ı ya da ABORT ile sıfırlanır | 31 Ağu |
| 4e | ⚠️ `active_formation` **ÇİZGİ**'de kaldı | SwC denenirken ayarlandı; READY'ye geçilirse sürü çizgi slotlarına koşar. **Uçuştan önce restart** | 31 Ağu |
| 4b | 🔴 **ylp00: mavros SEGFAULT** | 31 Ağu 21:12 yeniden başlatmasından sonra `[ros2run]: Segmentation fault`; yığın 11 yerine 2 düğümle kaldı. RC ölçümlerini engellemedi ama **px4_bridge mavros'suz iş göremez** | 31 Ağu, `gunluk/…/mavros.log` |
| 4c | 🟡 ylp00'da `kumanda_web.py` koşuyor | Port 8090, salt okur, `docker exec -d` ile elle başlatıldı — `baslat.sh` bilmiyor, restart'ta kaybolur. Durdurmak: `docker exec drone1 pkill -f kumanda_web.py` | `src/gcs/kumanda_web.py` |
| 5 | 🟡 Drone'larda repoda olmayan betikler | Bilgi versiyonsuz, kaybolabilir | `YAPILACAKLAR` P2 |
| 6 | 🟡 ESC telemetrisi kapalı | ylp01'in 2 Ağustos düşüşünün sebebini doğrudan verirdi | `YAPILACAKLAR` P2 |
| 7 | 🟡 Wi-Fi düşünce MAVROS log patlıyor | Bekçi kırpıyor ama **kök neden hâlâ bilinmiyor** | `TUZAKLAR` §2.23 |
| 8 | 🟡 Pi saati açılışta geriden | Çapraz uçak log karşılaştırması bozulur | aşağıda |
| 9 | ⚪ `iPhone` SSID'si doğrulanmadı | Telefon açılınca teyit gerekir | `RPI_ESITLEME.md` §7 |

### 🟡 #8 — Pi saati: kök neden bulundu, düzeltme dağıtıldı, **henüz etkin değil**

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

**Ne zaman çalıştır:** bir PX4 parametresi **yazıldıktan sonra** ve saha
gününde bir kez — *uçuş başına değil* (29 Ağu operatör kararı, `CLAUDE.md` §9).
Ayrışma ancak biri parametre yazdığında oluşur; 14 Ağustos'tan beri tekrarı
görülmedi.

```bash
./deploy/yki/param_karsilastir.py
```

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