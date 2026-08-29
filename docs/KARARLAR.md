# KARARLAR — verilmiş ama henüz uygulanmamış kararlar

**Son güncelleme:** 29 Ağustos 2026, 18:00 — uygulanmış 6 karar özete indi (gerekçeler git'te); açık kalanlar: 11, 09, 02, 03

Sohbette verilen kararlar oturum bitince kayboluyor. Bu defter onları
tutuyor: **ne karar verildi, neden, ne zaman uygulanacak, nasıl test edilecek.**

---

## ⚠️ CLAUDE İÇİN KURAL

**Bir aşamaya/işe geldiğinde ÖNCE buraya bak.**

O işle ilgili bir karar varsa:

1. **Operatöre söyle** — "bu konuda şu karar verilmişti"
2. **Önerilen seçeneği belirt** ve gerekçesini hatırlat
3. Operatör farklı bir seçenek isterse **o an detaylıca konuşulur**

Kararı sessizce uygulama, ama her seferinde sıfırdan da tartışma. Karar
zaten verilmiş; işin senin tarafın onu **hatırlatmak** ve **uygulamak**.

Yeni bir önemli karar verilirse **buraya yaz** — özellikle "şimdi değil,
sırası gelince" denilen şeyleri. Onlar en kolay kaybolanlar.

---

## Durum işaretleri

`🟡 BEKLİYOR` — karar verildi, sırası gelmedi
`🔵 SIRASI GELDİ` — aşamaya ulaşıldı, uygulanacak
`✅ UYGULANDI` — bitti, sonucu yazıldı
`❌ VAZGEÇİLDİ` — gerekçesiyle

---

# KARAR-11 — Görev 2 manevra modu: dört boşluk kapatıldı, devreye alma bekliyor

**Durum:** 🔵 **KOD HAZIR (28 Ağustos 2026, 20:40) — dağıtım + G0 + uçuş operatör komutu bekliyor**
**Ne zaman:** Operatör "başla" deyince (uçaklar şarjda, dağıtım yapılamadı)
**Karar veren:** Operatör (28 Ağustos 2026): şartname incelemesi + "4 boşluğu kapat sonra benden komut bekle"

## Bağlam

Şartname 5.2 (Görev 2, 100 puan) iki mod tanımlıyor: **Sürü Hareket Modu**
(çubuklar = öteleme) ve **MANEVRA MODU** (merkez sabit; pitch/roll =
formasyon DÜZLEMİ eğimi, yaw = formasyon rotasyonu + heading, throttle =
toplu irtifa). Görev 1'in QR-tetikli pitch/roll eğim manevrası AYNI hareket
ama otonom; karıştırılmayacak. "Eğim" uçağın gövdesini yatırmak DEĞİL —
slot irtifa modülasyonu (Şekil 4). Ceza: osilasyon -10, çarpışma -20×N.

Zincir zaten yazılmıştı (1685 satır mode_manager paketi + köprü TIP_KOMUT
iki yönde + FlySky FS-i6X kanal eşlemeli joystick_interpreter) ama hiç
koşmamıştı ve dört boşluğu vardı. 28 Ağu akşamı kapatıldı:

## Kapatılan dört boşluk

1. **`joystick` anahtarı eklendi** (`baslat.sh`) — 🔴 YALNIZ PİLOT
   UÇAĞINDA açılır (üç uçakta açılırsa üç kumanda birden sürüye komut
   basar). Düğümün KÖKSÜZ `/mavros/*` abonelikleri `/drone_N/mavros/*`'a
   remap'lendi (remapsız sessizce veri gelmiyordu).
2. **mode_manager çıkışı `/control/setpoint` → `/control/setpoint/raw`** —
   eskisi kaçınmanın ÇIKIŞ konusuna yazıyordu (iki üretici + CA baypası).
   Artık CA zorunlu aktarım katı olarak arada (formasyon zinciriyle aynı).
   **+ formasyon susturması:** MANEVRA'da (ve eğik HOLD'da) mode_manager
   `/swarm/internal/mode/formasyon_sustur` (Bool, 20 Hz) basar;
   formation_node susar. 3 sn tazelenmezse bayrak DÜŞER (yayıncı ölürse
   formasyon sürücülüğe döner — sahipsiz uçak yok). Görev 1'deki
   qr_step=MANEUVER kapısının Görev 2 karşılığı.
3. **Eğim matematiği tek kaynağa bağlandı:** `maneuver_mode` artık
   `manual_kinematics.apply_tilt` kullanıyor. Eski kopya (a) ortalama
   çıkarmıyordu → asimetrik formasyonda (okbaşı/V) bütün sürü kayıyordu —
   Görev 1'de sahada ölçülmüş hatanın aynısı (14→10,5 m); (b) roll işareti
   Görev 1 sözleşmesinin TERSİYDİ. İki regresyon testi kilitledi
   (merkez-sabitliği + roll işareti); kumanda-çubuk yönünün son sözü
   G0 işaret testinde.
4. **Limitler `ucus_ayarlari` MOD_* bölümünde** (KARAR gerekçeleriyle):
   eğim 15° · yaw **25°/s = PX4_DONUS_HIZI'ndan türetildi** (iki gömülü
   kopya 30 ve 45 idi; PX4 MPC_YAWRAUTO_MAX üstünü sessizce kırpar) ·
   hız 2,0 m/s · varsayılan aralık 7,0 m · deadman 0,5 s. `--kabuk` →
   env → baslat.sh → her iki düğüm. `wing_alpha_deg` de paramlandı
   (45.0 gömülüydü). Sayısal skalerler dynamic_typing (sekans dersi).

`mod` anahtarına `formasyon` bağımlılık kapısı kondu (hareket modu tarifi
formation_node uçurur). Testler: 11/11 (2 yeni regresyon dahil), denetim
0 hata, bash -n temiz. Commit: bkz. git.

## Bilinen açık uçlar (test planına girecek, kod değil)

- Hareket modunda her uçağın mode_manager'ı centroid'i KENDİ tik'inde
  entegre ediyor — uçaklar arası yavaş sürüklenme olasılığı G0/uçuşta
  ölçülecek (sekanstaki gibi tek-yayıncı değil, hesap-herkeste deseni).
- Kumanda→PX4→MAVROS→interpreter zincirinde `manual_control` mü `rc/in`
  mi gerçekte akıyor — pilot uçağında G0'da ölçülecek (rc/in kanıtlı,
  19 Hz; manual_control hiç ölçülmedi).
- İşaret yönleri (çubuk ileri = ?) G0'da kilitlenecek.

## MANEVRA TESTİ PLANI — 🟡 YARINA KALDI (operatör, 28 Ağu 21:35; plan sunuldu, ONAY BEKLİYOR)

Tek buton, SSH'siz, kumandasız otomatik test: sekans deseninin kardeşi
**`manevra_test_surucusu`** (GEÇİCİ, yalnız BİR uçakta yayın — pilot-uçağı
deseni) zamanlanmış SwarmControlCommand basar → mesh → üç mode_manager.
Akış: kalkış 8 m → ÇİZGİ 7 m kur (MOVEMENT, 10 sn) → **ROLL** ±%66
4+4 sn → **PITCH** aynı profil (çizgide dz üretmez — MERKEZ-KAYMASI
regresyon ölçümü) → **YAW** ~45° sola-geri (%50 çubuk = 12,5°/s) →
düzle → YKİ land (slot üstüne). Genlik: eğim ±10°, toplam ~2 dk. Eğim
yalnız z'yi modüle eder — yatay 7 m ayrım hiç değişmez.

### Plan sırasında koddan çıkan İKİ YENİ ENGEL (kod yazılırken kapatılacak)

5. 🔴 `_handle_formation_change` kendi `_formation_offsets`'ini
   GÜNCELLEMİYOR → formasyon değiştirip manevraya geçince gömülü okbaşı
   ofsetleri eğilir ve x-y de ona göre basılır — uçaklar çizgiden okbaşı
   konumlarına IŞINLANMAYA kalkardı (~10 satır düzeltme).
6. 🔴 mode_manager FSM'i sahada READY'ye ULAŞAMAZ: IDLE→PREFLIGHT kapısı
   mission_fsm'in SEMI_AUTONOMOUS'unu (düğüm kapalı), TAKEOFF→READY
   kapısı IN_SWARM'ı (ajanlar ARMED'da kalıyor) istiyor. Çözüm:
   sekans deseninde `test_hazir_atla` parametresi (varsayılan false).
   Tam Görev 2 akışı (kumandadan kalkış + mission_fsm) ADIM 6'nın işi.
   ⚠️ Ayrıca: komut akışı kesilip 5 sn geçince FSM kendiliğinden
   LANDING'e geçip iniş OLAYI basıyor (bugün etkisiz — agent_fsm
   ARMED'da işlemiyor) — sürücü bu yüzden sonda yayını kesmeyip
   çubukları sıfırda tutacak.

Atama notu: mode_manager slotları KİMLİK SIRASIYLA dağıtıyor (Macar yok)
— kuru denetim aynı kuralla çizer, çapraz yerleşimde KALIR der; Macar
iyileştirmesi ayrı P2.

### Operatöre ONAY SORULARI (yarın ilk iş)

1. Sürücü uçağı hangisi? (öneri: ylp00)
2. Genlikler: eğim ±10°, yaw ~45°/12,5°/s — uygun mu?
3. İniş slot üstüne land (EVE fazı YOK) — uygun mu?

### Test merdiveni (onaydan sonra)

1. ⏳ Kod: 5+6 düzeltmeleri + sürücü düğümü + kosucu `manevra` senaryosu
   (kuru: çizgi + eğim zarfı + harita) + panel butonu + birim testler
2. ⏳ Dağıtım (dagit.sh ×3 + env) — uçaklar açılınca
3. ⏳ G0: `/ws/gozlem` + `mod`(3 uçak) + `manevratest`(yalnız sürücü
   uçağı): işaret yönleri, merkez sabitliği, susturma, deadman
4. ⏳ Uçuş A: yukarıdaki çizelge (ÇİZGİ'de roll/pitch/yaw)
5. ⏳ Uçuş B: OKBAŞI/V eğim (asimetri) + tam yaw · ayrıca gerçek
   kumandayla `joystick` zinciri (G0'dan sonra)

---

# KARAR-09 — Kamera hangi uçaklarda, konteynerler eşitlensin mi

**Durum:** 🔵 **İKİSİ DE KARARA BAĞLANDI — (B) kısmen uygulandı, (A) mimari zaten hazır**
**Ne zaman:** ylp00 ve ylp01 ağa geldiğinde tek komut
**Karar veren:** Operatör (28 Ağustos 2026): *"hepsinin konteynerini eşitle"*
**Soruyu soran:** Operatör (28 Ağustos 2026) — *"Bütün dronelara kamera
takmayabiliriz... Ama eğer hepsi eşit olsun dersen hepsinin konteynerini
eşitleyebiliriz."*

## Ayrılması gereken iki soru

Bunlar **bağımsız** ve karıştırılırsa gereksiz iş çıkar:

| | Soru | Bugün |
|---|---|---|
| **A** | Hangi uçaklarda **kamera donanımı** olacak | yalnız ylp02 |
| **B** | Hangi uçaklarda **konteyner ortamı** algı paketlerini taşıyacak | yalnız ylp02 |

Kamerası olmayan bir uçakta `opencv`+`pyzbar`+`zxing` bulunması **hiçbir
şeye mal olmuyor**: 760 MB disk (Pi'lerde 18-19 GB boş) ve o kadar. Düğümler
zaten açılmıyor — `SURU_DUGUMLERI` listesinde yoklar.

## Öneri: B'yi EŞİTLE, A'yı ayrı karar ver

**Gerekçe — bu deponun kendi geçmişi.** `RPI_ESITLEME.md` tam olarak
ayrışma yüzünden var ve `CLAUDE.md` şunu yazıyor: *"Yazılmayan değişiklik,
sonradan saatlerce süren 'neden bunda çalışmıyor' arayışına dönüşüyor."*
28 Ağustos'ta ayrışma **başladı**: 20 Ağustos'ta ylp00 ve ylp02'de imaj
kimliği aynıydı (`661296d…`), artık değil (ylp02 `ea2c1b1e…`).

Eşitlemenin bedeli **uçak başına tek komut**:

```bash
scp ~/yelpence-yedek/yelpence-ros-algi-20260828.tar.gz ylpNN:~/
./deploy/yki/drone_bul.sh ylpNN 'docker load < ~/yelpence-ros-algi-20260828.tar.gz'
```

Kazandırdığı: hangi uçağa kamera takılırsa takılsın ortam hazır; bir uçak
düşüp yerine başkası girdiğinde imaj derdi çıkmıyor; hata ayıklarken
"bunda var, ötekinde yok" sorusu hiç doğmuyor.

## Karşı görüş

Disk ve 628 MB'lık transfer. Bir de imajı güncellersek **üç uçakta birden**
güncellemek gerekir — bugün tek uçakta.

## Kamera donanımı (A) için ayrı düşünce

Şartname üç uçağın da QR okumasını **gerektirmiyorsa**, tek kameralı bir
sürü çalışabilir: kamerası olan uçak QR'ı okur, sonucu mesh'ten paylaşır.
Ama o zaman **o uçak tek hata noktası** olur — düşerse görev biter.
Bu, mesh protokolü ve görev mantığıyla birlikte konuşulmalı; şu an
`QRMissionData` yalnız yerel yayınlanıyor, mesh'e çıkmıyor.

- `[x]` ~~Operatör: B eşitlensin mi?~~ → **EVET, eşitlensin** (28 Ağu).
  `deploy/yki/imaj_esitle.sh` yazıldı ve ylp02'de sınandı. ylp00 ve ylp01
  **kapalı olduğu için yapılamadı** — açılınca uçak başına tek komut:
  `./deploy/yki/imaj_esitle.sh ylp00`
- `[x]` ~~Operatör: A — kaç uçağa kamera?~~ → **Sayı önemli değil.**
  Operatör (28 Ağu): *"kamera tek droneda da olsa birden fazla droneda da
  olsa, hangi drone QR'ı okursa diğer dronelara görevi söyleyecek
  meshten."*
- `[x]` ~~A birden azsa: QR sonucu mesh'ten paylaşılacak mı?~~ → **EVET, ve
  mimari BUNU ZATEN YAPIYOR.** 28 Ağu'da kod okunarak doğrulandı:

  ```
  qr_detector (okuyan drone)
     → /swarm/internal/perception/qr_data
     → esp32_bridge · qr_gorev_paketle()  →  TIP_QR_GOREV (0x14), 16 bayt
     → ESP-NOW yayın (tüm sürü duyar)
     → diğer dronelarda esp32_bridge · _isle_qr_gorev()
     → /swarm/internal/perception/qr_data   ← yerel okumuş gibi
  ```

  204 baytlık QR 16 bayta sığıyor çünkü **ham JSON gönderilmiyor**: okuyan
  drone çözüp yapısal alanları yolluyor (`qr_gorev_veri_t`, static_assert
  ile 16 bayta kilitli). Geçmeyen alanların gerekçesi `mesh_config.h`'de
  satır satır yazılı.

  Ayrıca `TIP_QR_HAM` (0x15) düşünülmüş: **ayrıştırma hatasında** ham metnin
  ilk 52 karakteri gidiyor. Şartname *"QR içeriği örnektir, nihai format
  sonra paylaşılacaktır"* dediği için — format değişirse `json.loads`
  patlar ve sahada elinde hiçbir şey kalmaz; o dilim en azından formatı
  gösterir.

  Firmware her iki tarafta tanıyor (`TX DRONE/main.cpp:238`,
  `RX BASE/main.cpp:242`), köprüde TX (`:2672`) ve RX (`:2459`) var,
  sayaçlar bile duruyor (`qr_tx=`, `qr_rx=`).

  ⚠️ **AMA SAHADA HİÇ KOŞMADI** — bkz. `YAPILACAKLAR` — Görev 1 bloğu, ADIM 5.

---

# KARAR-02 — Claude effort seviyesi: hep `max`, ultracode noktasal

**Durum:** 🟡 BEKLİYOR — kural yürürlükte, hatırlatma anları henüz gelmedi
**Ne zaman:** Her oturum (kural) + `PLAN.md` §8 **ADIM 1, 3, 4** (hatırlatma)
**Karar veren:** Operatör (15 Ağustos 2026)

## Karar

**`/effort` menüsü daima `max` kalır. Ultracode menüden AÇILMAZ.**

Çok ajanlı denetim gerektiğinde operatör **o mesajın içine `ultracode`
kelimesini yazar** — o tur çok ajanlı çalışılır, sonraki tur kendiliğinden
`max`'a döner. Menü hiç kurcalanmaz.

## Neden

`/effort` menüsünde ikisi **aynı listede ve birbirini dışlıyor.** Ultracode
seçilince effort `xhigh`'a düşüyor (ayar şemasındaki tanımı birebir:
*"xhigh effort plus standing dynamic-workflow orchestration"*). Yani ultracode
açmak, düşünme derinliğinden bir kademe feragat etmek demek.

| | Düşünme derinliği | Ajan sayısı |
|---|---|---|
| `max` | en derin | 1 |
| `ultracode` | xhigh (bir kademe altı) | çok + karşıt doğrulama |

**Günlük iş neden `max`:** entegrasyon işi sıralı ve cerrahi — üç satırlık
düzeltme, telemetriden teşhis, komut çalıştırma. Bunlar *derinlik* problemi.
Ayrıca ultracode arka planda dakikalarca sürüyor; sahada pervaneler dönerken
beklenecek şey değil, ve alt ajanlar sohbet bağlamını görmüyor.

**Denetimler neden ultracode:** "%30 paket kaybında hangi senaryoda iki lider
çıkar" bir *kapsama* problemi. Orada 8 bağımsız avcı, 1 derin düşünenden iyi.
Gerekçe somut: Claude bu depoda üç kez çapalama hatası yaptı —
`formation_node`'da ileri-besleme yok dedi (vardı), ylp02'nin eğim değerleri
PX4 varsayılanı dedi (tersiydi), çoklu üretici çakışması çözülmemiş dedi
(susturma ile çözülmüştü). Üçü de tek kanalda bulunamadı. Onu hiç duymamış
bağımsız bir ajan o çapayı miras almıyor.

## 🔴 Claude'un yapacağı — hatırlatma anları

Şu üç adıma gelindiğinde, **uçmadan önce** operatöre söyle:

| Adım | Düğüm | Neden fan-out gerekli |
|------|-------|------------------------|
| **ADIM 1** | `consensus_node` | Kayıplı mesh'te lider seçimi; iki lider senaryosu aranmalı |
| **ADIM 3** | `formation_node` | 50 Hz'de uçağa setpoint yazıyor |
| **ADIM 4** | `collision_avoidance` | İki uçak arasındaki tek koruma katmanı |

Söylenecek cümle: *"Bu düğüm ilk kez havaya kalkacak. KARAR-02 gereği burada
çok ajanlı denetim öneriliyor — bu mesaja `ultracode` yazar mısın?"*

Operatör istemezse tartışılmaz, tek kanalda ilerlenir.

**Genel kural:** havaya kalkacak bir düğüm **ilk kez** açılmadan önce denetim
önerilir. Belge, config, kurulum, düzeltme işlerinde önerilmez — orada israf.

## Ayrıca — Claude effort'unu kendi okuyabilir

```bash
echo $CLAUDE_EFFORT      # max / xhigh / high / ...
```

Ultracode'un açık olup olmadığı Claude'a zaten her turda sistem tarafından
bildiriliyor, komut gerekmiyor.

## ✅ Uygulandı — otomatik uyarı (Claude'un hatırlamasına bağlı değil)

`.claude/settings.json` → `UserPromptSubmit` hook'u → `.claude/effort_bekcisi.sh`.
Effort `max` değilse **her mesajda** operatöre uyarı basıyor, `max` iken
tamamen sessiz. Dosya repoda, yani takımdaki herkeste çalışıyor.

**15 Ağustos'ta ölçülenler** (betiğin başında da yazılı, silme):

| Bulgu | Sonuç |
|-------|-------|
| `$CLAUDE_EFFORT` hook ortamında **yok** (68 değişkene bakıldı) | Oradan okunamaz. İlk deneme bunu varsaymıştı ve max'tayken bile bağırıyordu |
| `$CLAUDE_EFFORT` **Bash aracında canlı ve doğru** | Kesin doğrulama yolu bu |
| Seviye transkriptte her `assistant` kaydında yazılı | Hook oradan okuyor |
| Transkript **bir tur geriden** geliyor | Uyarı bir mesaj gecikmeli çıkabilir |
| Hook'ta `$CLAUDE_PROJECT_DIR` ve `$CLAUDE_CODE_SESSION_ID` **var** | Transkript tahminle değil kesin bulunuyor |

Bu yüzden iki katmanlı: **hook** hızlı ama gecikmeli tripwire (operatöre
ekranda uyarı), **Claude** `echo $CLAUDE_EFFORT` ile kesin doğrulama.
Betik okuyamadığında operatörü rahatsız etmiyor, yalnız Claude'a
"doğrula ve bildir" diyor — bozuk okuma kurt masalına dönüşmesin.

Hook çalışmıyorsa: bir kez `/hooks` menüsünü aç (ayar dosyasını yeniden
okutuyor) ya da oturumu yeniden başlat.

## Diğer seçenekler (operatör isterse)

| | Ne | Neden seçilmedi |
|---|----|-----------------|
| A | Menüde hep ultracode | Her turda xhigh; sahada arka plan beklemesi; belge işinde israf |
| B | Aşamaya göre menüden gidip gel | Aynı sonucu veriyor ama elle iş; tek kelime yazmak daha ucuz |
| C | Hiç fan-out yok | Denetimler tek kanalda kalır — çapalama riski karşılıksız |

---

# KARAR-03 — Pil failsafe'i, ölçer modül gelince açılacak

**Durum:** 🟡 BEKLİYOR — donanım alınmadı
**Ne zaman:** LiPo pil ölçer modül alınıp RPi'ye bağlandığında
**Karar veren:** Operatör (15 Ağustos 2026)

## Karar

**Pil failsafe'i şimdi açılmayacak.** İleride bir **LiPo pil ölçer modül**
alınacak, voltaj verisi doğrudan **RPi'ye** verilecek. O zaman:

1. Pil değerleri YKİ arayüzünde görünecek
2. Pil failsafe'i o zaman devreye alınacak

## Neden şimdi değil

Uçaklar **regülatörden** besleniyor, PX4'te `BAT1_SOURCE` disabled. Okunan
3.1 V gerçek pil voltajı değil. Bu yüzden pil izleme **üç yerde birden**
kapalı (`BATARYA_KRITIK_V=0.0`). Olmayan bir ölçüme dayanarak failsafe
açmak, uçağı yerde tutan sahte bir alarm üretir.

## Nasıl uygulanacak — açılması artık TEK parametre

15 Ağustos'taki `preflight_checker` düzeltmesinden sonra eşik üç yerde de
`ctx.battery_critical_voltage_v`'den geliyor. Modül gelince yapılacak:

| Adım | Ne |
|------|-----|
| 1 | Modülün voltajını yayınlayan küçük bir düğüm (I2C/UART, ~60 satır) |
| 2 | `AgentStatus.battery_voltage_v` bu kaynaktan beslensin (şu an MAVROS'tan) — **ve `px4_bridge.py:546`'daki 12.6 V sahtesi kaldırılsın**: 21 Ağustos'ta ölçüldü, PX4 "bilmiyorum" (65.535 V) derken AgentStatus'a 12.6/%100 basılıyor ve pil "dolu" görünüyor (TUZAKLAR 1.20) |
| 3 | `deploy/rpi/baslat.sh` → `BATARYA_KRITIK_V=13.6` |
| 4 | `src/gcs/frontend/src/services/gorunum.ts` → `PIL_GOSTER = true` |
| 5 | `src/gcs/backend/config.yaml` → `alerts.susturulan`'dan batarya kodlarını çıkar |
| 6 | 🔴 **`esp32_bridge`'in `healthy` türetimine pil eşiğini ekle** — aşağıya bak |

> 🔴 **6. adım kolayca atlanır ve sessizce yanlış sonuç verir.** Mesh'te
> `healthy` bir **bit olarak taşınmıyor**; alıcı tarafta türetiliyor:
> `ekf_ok ∧ ¬kill_switch ∧ state≠FAILSAFE` (`esp32_bridge_node.py:974`).
> Pil izleme açıldığında **pil düşüşü bu türetime yansımaz** — komşular pili
> bitmiş bir uçağı `healthy=True` görmeye devam eder ve o uçak lider adayı
> kalır. İki seçenek: ya mesh paketine bir bit eklenecek (firmware
> değişikliği) ya da eşik **alıcı tarafta da** uygulanacak (yalnız ROS,
> firmware'e dokunmaz — tercih edilen).

⚠️ **3, 4, 5 birlikte yapılmazsa** sistem tutarsız davranır: biri pili
umursar, diğeri umursamaz. `DURUM.md` §3'te de yazılı.

## Test

- **Yerde:** modül takılı, pil takılı → okunan voltaj çok metreyle uyuşuyor mu
- **Yerde:** eşiği geçici olarak okunan voltajın üstüne çek → preflight
  arming'i engelliyor mu (`test_esik_baglamdan_gelir` bunu zaten kilitliyor)
- **Yerde:** eşiği 0.0'a çek → engel kalkıyor mu
- Uçuş testi **gerekmiyor**; failsafe yolu zaten ölçülmüş kod

---

# Uygulanmış kararlar — özet

Bunlar **bitti ve sahada doğrulandı.** Gerekçeleri, ölçümleri ve elenen
seçenekleri git'te duruyor: `git show 783afab:docs/KARARLAR.md`

| Karar | Ne | Durum |
|---|---|---|
| **KARAR-01** | Çarpışma önleme **Seçenek C** — `collision_avoidance`, komşu verisi ham `AgentStatus`'tan (yumuşatma yok) | ✅ 21 Ağu açıldı, 22 Ağu'dan beri her uçuşta çalışıyor |
| **KARAR-04** | Üç uçak birden uçunca değişecek parametreler (`SURU_BEKLENEN_UCAK=3`, kadro `1 2 3`) | ✅ 25 Ağu, ylp01 dönünce uygulandı |
| **KARAR-05** | Konteyner imajı: Dockerfile geri gelmeyecek, `docker save` yeter | ✅ 20 Ağu, yedek alındı ve doğrulandı |
| **KARAR-06** | Kaçınmada kaçış yönü: **DİKEY birincil**, yatay itme yalnız sert kabukta | ✅ 23 Ağu uygulandı, aynı akşam uçtu |
| **KARAR-07** | Körlükte dönüş tutması: **yerde + disarm** kayıp komşu MUAF | ✅ 25 Ağu (`6258eab`), uçuşla doğrulandı |
| **KARAR-10** | Formasyon geçiş testi: sekans **UÇAKTA**, YKİ yalnız başlatır | ✅ 28 Ağu uçtu (5 faz, `avoid=0`). Aparat geçici — `mission1` sahaya alınınca silinecek (`YAPILACAKLAR` P3) |

---

# Karar şablonu (yeni karar eklerken kopyala)

```markdown
# KARAR-NN — <konu>

**Durum:** 🟡 BEKLİYOR
**Ne zaman:** <hangi aşama / hangi iş>
**Karar veren:** <kim> (<tarih>)

## Karar
<tek cümle: ne yapılacak>

## Neden
<gerekçe, ölçüm varsa sayılarla>

## Nasıl uygulanacak
<adımlar, maliyet>

## Test
<zorunlu testler>

## Diğer seçenekler (operatör isterse)
<tablo: seçenek, neden seçilmedi>
```
