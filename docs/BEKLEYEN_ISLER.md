# Bekleyen İşler — Yapılmayanlar ve İleride Yapılacaklar

**Son güncelleme:** 30 Temmuz 2026
**Takım:** Yelpence (752825) — ylp00, ylp01, ylp02

Bu belge "neyi henüz yapmadık" sorusunun tek cevabı olsun diye tutuluyor.
Sohbet geçmişi kaybolduğunda buraya bakılır. Her madde **niye bekliyor** ve
**ne zaman açılır** bilgisiyle yazılıdır.

Durum işaretleri:
`[ ]` yapılmadı · `[~]` kısmen · `[B]` başka bir şeye bağlı · `[!]` uçuş izni engeli

---

## 1. Sahada yapılacaklar (kapalı mekânda imkânsız)

- `[!]` **RC failsafe zinciri.** Uçuş izninin kapısı, en yüksek öncelik.
  - `NAV_RCL_ACT=2` üç dronda da **etkisiz** — ölçüldü.
  - ylp00'ın alıcısı sinyal kesilince **RTL değil kill** tetikliyor. Bu haliyle
    uçmak, link kaybında düşmek demek.
  - ylp02'nin vericisi hâlâ **End Points %120** — kanal kalibrasyonu bozuk.
  - Kabul ölçütü: verici kapatıldığında dron RTL'e geçmeli, kill olmamalı.

- `[!]` **İÇERİDE ARM MÜMKÜN DEĞİL — EKF, GPS'i doğruluk yetersizliğinden
  reddediyor. Ölçüldü (30 Temmuz).** "Neden arm olmuyor" sorusunun cevabı.

  | | eşik | ylp00 | ylp01 |
  |---|---|---|---|
  | `EKF2_REQ_EPH` | **3.0 m** | `h_acc` **3.09 m** ✗ | `h_acc` **3.43 m** ✗ |

  `EstimatorStatus` bayrakları: `attitude_status_flag: true`,
  `pos_vert_abs: true`, ama **`pos_horiz_abs`, `pos_horiz_rel`,
  `velocity_horiz` hepsi false** — EKF yatay GPS'i hiç füzyona sokmuyor.
  `gps_glitch_status_flag: false`, yani **arıza değil**, sadece yeterince
  doğru değil.

  Zinciri: `h_acc > EKF2_REQ_EPH` → EKF GPS'i reddeder → `estimator_ok=false`
  → preflight'ta "Konum tahmini (EKF2) hazır değil" → `ready_to_arm=false`.

  Sabah ylp00 `h_acc=2.14 m` iken armlanabiliyordu; içeride doğruluk 3 m'nin
  üstüne çıkınca kapandı. **Çözüm açık alana çıkmak** (ve RTK survey-in ile
  doğruluğu santimetreye indirmek) — kod/parametre sorunu değil.

  > `EKF2_REQ_EPH`'i büyütmek arm'ı açar ama **kötü konumla uçmak demektir**;
  > otonom formasyonda çarpışma riski doğurur. Eşiği gevşetmeyin.

- `[ ]` **RTK survey-in tamamlama.** Açık gökyüzü şart.
  - u-blox şu an `1074/1084/1094/1124/1230` yayınlıyor; **`1005` YOK**.
  - `1005` = baz istasyonu konumu. O akmadan rover baseline kuramaz, yani
    **RTK Float/Fixed imkânsız** — MSM gözlemleri tek başına yetmez.
  - Survey-in bitince `--sabitle` ile konum flash'a yazılmalı.
  - 1 Hz ayarı zaten flash'ta (RAM/FLASH tutarlılığı doğrulandı).

- `[B]` **`MAVROS -> PX4 -> DroneCAN -> Here4` halkası.** RTK survey-in'e bağlı.
  - Zincirin geri kalanı ölçüldü ve kayıpsız (bkz. §5).
  - Bu son halkanın tek kanıtı `fix_type` **5 (Float)** veya **6 (Fixed)**.
  - **`fix_type=4` (DGPS) kanıt DEĞİLDİR** — bu filoda SBAS/EGNOS kaynaklı,
    ölçüldü (RTCM 95 sn kesildi, `fix_type` 4'te kaldı). Ayrıntı:
    `YELPENCE_RTCM_SPEC.md`.

- `[ ]` **ylp02 GPS standı.** Kabul ölçütü `h_acc < 3.0 m`. Stand değiştiriliyor.

- `[x]` **ÇÖZÜLDÜ — ylp01'in ESP32'si eski firmware'deydi, flaşlandı
  (30 Temmuz).** Önce/sonra ölçümü:

  | | flash öncesi | flash sonrası |
  |---|---|---|
  | ylp00 `form_tx` | 11 | 21 (+10) |
  | ylp01 `form_rx` | **0** | **10** (+10, kayıpsız) |

  Teşhis şöyle daraltılmıştı: ylp01 aynı turda `lider=1`'i öğreniyordu, yani
  `TIP_ELECTION` geçiyor ve mesh sağlam — ama `TIP_FORMASYON` (0x11) eski
  firmware'in beyaz listesinde olmadığı için paket **ESP'de** düşüyordu.

  > **Doğru cihaza yüklediğinden emin ol.** Dizüstünde birden fazla USB seri
  > cihaz olur (base'in CH340 veri hattı, base'in CP2102'si, dron ESP'si) ve
  > `by-id` adları aynı olabilir (`CP2102_..._0001`). Tahmin etme, MAC oku:
  >
  >     python3 ~/.platformio/packages/tool-esptoolpy/esptool.py \
  >         --port /dev/ttyUSBx --no-stub read_mac
  >
  > Ortam **`esp32dev_serial0`** olmalı (RPi hattı Serial0'a alınır):
  > `pio run -e esp32dev_serial0 -t upload --upload-port /dev/ttyUSBx`

- `[ ]` **ylp01'de pil izleme KAPALI — düşük pil koruması YOK.**
  PX4'ün güç konnektörü akım/voltaj ölçüm katı arızalı, izleme komple
  kapatıldı (30 Temmuz, kullanıcı; ileride onarılacak).

  Ölçüldü: `battery_voltage_v = 65.535` — bu **`0xFFFF`**, MAVLink'in
  "geçersiz" sentinel'i, sıfır değil. Kodun `<= 0.0` koruması bunu
  **yakalamıyor**; şans eseri zarar vermiyor çünkü 65.5 V hiçbir "çok düşük"
  eşiğinin altında değil, yani lider seçimi ve preflight çalışmaya devam
  ediyor (`election.py:29`, `preflight_checker.py:37`,
  `agent_health_monitor.py:219` — üçü de geçiyor).

  **Asıl risk:** ne PX4'ün `COM_LOW_BAT_ACT=2`'si ne sürü yazılımının
  kontrolleri tetiklenebilir — ölçüm yok. Onarılana kadar **ylp01 süreye
  göre uçurulmalı, pil elle takip edilmeli.**

  Küçük düzeltme adayı: telemetri eşleyicide `65.535`'i de "bilinmiyor"
  saymak, böylece YKİ 65.5 V yerine boş/bilinmiyor gösterir.

- `[x]` **GERİ ÇEKİLDİ — ylp01'de "yüksek CRC hata oranı" anten sorunu
  değilmiş.** Bir ara 6253 pakette 542 (%8.7) ölçülmüştü ve anten yerleşimi
  şüphelenmişti. Ama o ölçüm **QGC'nin yol açtığı 40 msg/s RTCM seliyle
  aynı ana denk geliyor** — sel mesh'i boğuyordu. u-blox 1 Hz'e dönünce
  ylp01 ve ylp00 **ikisi de `crc_fail=0`**. Anten şüphesi desteklenmiyor.

- `[x]` **ylp01 ayağa kalktı (30 Temmuz)** — ESP firmware'i hariç diğer
  ikisiyle tam eşit. Kurulum artık `deploy/rpi/pi_hazirla.sh`'ta yazılı
  (önceden hiçbir yerde yoktu, ylp00'dan geri mühendislikle çıkarıldı).
  Doğrulandı: Pixhawk bağlı (`connected: true`), mesh `komsu=2`, 8 süreç,
  günlük dosyaları + uçuş kaydı çalışıyor, PX4 RTK parametreleri **zaten
  doğruydu** (`UAVCAN_PUB_RTCM=1`), `.surum` takibi kuruldu.

  En kritik eksik `cmdline.txt`'deki **`console=serial0,115200`** idi —
  seri konsol Pixhawk'ın UART0'ını işgal ediyordu; kaldırılmasaydı MAVROS
  hiç bağlanamazdı.

- `[ ]` **Uçuşta formasyon testi.** Mesh aktarımı masada doğrulandı (§5) ama
  havada, gerçek konum/EKF ile hiç denenmedi.

---

## 2. Doğrulanmamış kod yolları

Kod yazıldı, birim testleri geçiyor, ama **gerçek meshte/donanımda hiç
çalışmadı**. Her biri sessizce bozuk olabilir.

- `[~]` **Gerçek lider seçimi (`consensus_node`).** 30 Temmuz'da **gerçekten
  arm olmuş dronla, sıfır sahte girdiyle doğrulandı** (bkz. §5). Kalan
  parçalar:
  - `[~]` **TAKEOFF'un önündeki engel bulundu ve DÜZELTİLDİ** (`ea80852`,
    bkz. §3). Kök sebep "setpoint üreten düğüm yok" değildi — o ilk
    tahminim yanlıştı, `px4_bridge` kendi hold setpoint'ini yayınlıyor.
    Gerçek sebep: **PX4 armlıyken yerde OFFBOARD'a geçmiyor.**
    Arm+OFFBOARD zinciri artık donanımda doğrulandı; **görev başlatmadan
    TAKEOFF'a kadar tam akış henüz koşturulmadı.**
  - `[~]` **Lider kalp atışı ÇALIŞTI** (30 Temmuz, bkz. §5) — `TAKEOFF`
    durumuna ulaşılınca `own_airborne` True oldu ve **300 heartbeat**
    yayınlandı. Kalan: bu heartbeat'in **mesh üzerinden ylp02'ye** ulaştığı
    ve heartbeat timeout'una dayalı lider düşmesi tespitinin
    (`effective_set`'teki `hb_age` dalı) çalıştığı doğrulanmadı — ikisi de
    yeni bir armlı koşum ister.
  - `[ ]` 3 dronlu seçim (ylp01 yok).
  - `[ ]` `_apply_role` / `AssignRole` servis çağrısı — seçim sonrası rol
    ataması gözlenmedi.
- `[ ]` **`formation_node` / `path_planner` hedef üretimi.** Test hedefi elle
  basıldı. Gerçek görev durumundan hedef üretme yolu çalıştırılmadı.
- `[ ]` **3 dron ile formasyon.** Test 2 dronla yapıldı (ylp01 yok).
- `[ ]` **`TIP_FORMASYON_DEVAM` (>4 ajan).** Başlık paketi 4 slot taşıyor;
  5+ ajanla devam paketi gerekir. Hiç gönderilmedi — 3 İHA'da gerekmiyor ama
  kod yolu ölü kalıyor.
- `[ ]` **`TIP_FORM_OFSET` (CUSTOM formasyon).** Jüri dizilişi bu yoldan
  taşınacak. Hiç gönderilmedi.
- `[ ]` **QR yolu (`TIP_QR_GOREV`, `TIP_QR_HAM`).** Kod ve testler var, gerçek
  meshte hiç denenmedi. Kamera + QR okuma da denenmedi.
- `[ ]` **RC ile formasyon değiştirme.** Görev 2 şartı. 4 açık nokta
  belgelenmiş durumda (`MESH_PROTOKOL_KARARLARI.md`), hiçbiri kapatılmadı.
- `[ ]` **YKİ'den formasyon seçme.** Köprü tarafı hazır (`talep_formasyon`,
  `talep_spacing_dm` alanları eklendi); arayüz butonundan uçtan uca hiç
  denenmedi.
- `[ ]` **`mission1_dynamic_swarm` her dronda.** Mesh yükü açısından
  tartışıldı, çalıştırılmadı.
- `[ ]` **Lider düşmesi / sıcak yedek.** `path_planner` her dronda koşuyor ki
  lider düşünce yeni lider gecikmeden yayına geçsin. Bu geçiş test edilmedi.
- `[ ]` **Uçuş kaydı (ros2 bag) gerçek uçuşta.** Güç kesintisine dayanıklılık
  SIGKILL ile doğrulandı, ama gerçek uçuş verisiyle okunabilirlik denenmedi.

---

## 3. Bilinen açıklar ve riskler

- `[x]` **DÜZELTİLDİ (30 Temmuz, `66c4786`) — `consensus_node` yeniden
  başlarsa seçimleri sessizce yok sayılıyordu.** Kayıt olarak bırakılıyor;
  doğrulaması §5'te.

  `_on_election` (`consensus_node.py`) eskimiş mesaj filtresi:

      if msg.sequence_num <= ctx.max_seen_seq:
          return

  `_publish_election_result` ise `ctx.out_seq`'i **0'dan** başlatıyor. Lider
  dronun `consensus_node`'u yeniden başlarsa (çökme, konteyner restart,
  elle restart) `out_seq` 1'e döner; takipçilerin `max_seen_seq`'i yüksek
  kalır → **liderin bütün yeni seçim sonuçları düşürülür.** Ne log, ne
  uyarı, ne sayaç.

  `election_round` kontrolü kurtarmıyor: seq kontrolü **önce** geliyor ve
  `return` ediyor. Yeniden başlayan düğümün round'u da 0'dan başladığı için
  o dal da tıkanır.

  **İki kollu deneyle ölçüldü** (ylp00, tek değişken seq):

  | kol | `sequence_num` | `election_round` | sonuç |
  |---|---|---|---|
  | A | 100 (yüksek) | 5 | **kabul** → `Lider: 3 -> 1 (round=6)` loglandı |
  | B | 5 (düşük) | **9 (yüksek)** | **reddedildi**, hiç log yok |

  B kolunda round bilerek yüksek tutuldu (9 > 6), yani onu reddeden **tek
  şey seq filtresiydi.**

  **Uygulanan çözüm — (c): protokole kimlik eklemek.** `ElectionResult`'a
  `uint16 incarnation` eklendi (yayıncının o açılışına özgü rastgele kimlik,
  `SystemRandom`, 0 = bilinmiyor). `max_seen_seq` tek int'ten
  `seen_seq: {kaynak: (incarnation, max_seq)}` sözlüğüne çevrildi — **kaynak
  başına** sayaç lider devri sorununu, incarnation karşılaştırması restart
  sorununu çözüyor. Filtre `election.seq_kabul()` saf fonksiyonuna ayrıldı
  (repo düzeni: saf mantık `election.py`, ROS bağlantısı node'da), böylece
  ROS'suz test edilebiliyor.

  Mesh'te yer: `election_veri_t`'de `rezerv[4]` → `incarnation(2)` +
  `rezerv[2]`. **Struct hâlâ 16 bayt**, firmware yalnız `sizeof()` kullanıyor
  ve alanların içine bakmıyor → **ESP'leri yeniden flaşlamak gerekmedi.**

  incarnation değişimi artık **loglanıyor** — sahada "seçim neden
  uygulanmadı" sorusunun cevabı sessiz kalmasın diye.

- `[x]` **DÜZELTİLDİ (`ea80852`) — PX4 ARMLIYKEN yerde OFFBOARD'a geçmiyor;
  FSM'in sırası tersti ve dron hiç kalkamıyordu.**

  Tek değişkenli deney (30 Temmuz):

  | durum | `offboard` komutu | sonuç |
  |---|---|---|
  | disarm + kumanda kapalı | tek sefer | OFFBOARD ✓ |
  | disarm + kumanda açık | tek sefer | OFFBOARD ✓ |
  | **armlı** | tek sefer | **reddedildi** ✗ |

  FSM `ARMING → 'arm'`, `ARMED → 'offboard'` sırasıyla çalıştığı için önce
  armlıyor sonra mod istiyordu → PX4 reddediyor → dron `ARMED`'da sonsuza
  kadar takılıyordu (`ARMED bekliyor: offboard=False sure=9.3s`).

  **Düzeltme `px4_bridge`'de** (sıralama kısıtı PX4'e özgü, FSM'e sızmamalı):
  `arm` komutu geldiğinde önce OFFBOARD isteniyor, `offboard_active` olunca
  ARM gönderiliyor. Zaten armlıysa **hiçbir şey yapılmıyor** (uçuyor olabilir;
  mod değiştirip kontrolü habersiz devralmayalım). 8 sn'de aktifleşmezse ARM
  **gönderilmiyor** ve hata loglanıyor — FSM'in ARMING timeout'u temiz şekilde
  IDLE'a döndürüyor.

  Donanımda doğrulandı: `OFFBOARD isteniyor` → `OFFBOARD aktif → ARM
  gönderildi` arası **72 ms**, sonra 12+ sn armlı ve OFFBOARD'da kaldı.

- `[x]` **DÜZELTİLDİ (`ea80852`) — `disarm` bayat kalkış hedefi bırakıyordu.**
  `precision_landing` görev sonunda `land` DEĞİL doğrudan `disarm` gönderiyor
  (`precision_landing_node.py:214`), `disarm` dalı ise `_target_altitude_ned`
  ve çapaları temizlemiyordu. Sonraki `offboard`'da taze formasyon setpoint'i
  henüz yokken "kalkış/irtifa-hold" dalı devreye girip dronu **önceki görevin
  irtifasına ve önceki çapa konumuna** sürüyordu — FSM daha TAKEOFF demeden.
  Komut verilmemiş kalkış; dron yeri değiştiyse yatay kaçış. Artık `land`/`rtl`
  ile aynı şekilde temizleniyor.

- `[!]` **KUMANDA AÇIKKEN SÜRÜ OTONOMİSİ TAMAMEN DURUR — ÖLÇÜLDÜ
  (30 Temmuz). Uçuş prosedürünü doğrudan belirler.**

  Kumanda açıkken PX4 **POSCTL**'e geçiyor. `PILOT_FLIGHT_MODES = {1,2,3,9,10}`
  (MANUAL/ALTCTL/POSCTL/ACRO/STABILIZED) olduğu için
  `pilot_override_active = true` oluyor, o da `autonomous_control_paused = true`
  yapıyor (`agent_fsm_node.py:525`). Sonuç `evaluate_transitions`'ın ilk
  satırında:

      if ctx.autonomous_control_paused or ctx.hold_active:
          return None

  **Hiçbir geçiş olmuyor — ve hiçbir yere loglanmıyor.** Ölçüm:
  `status_text: Pilot override active`, `state` IDLE'da donmuş, görev başlatma
  olayı 14 kez teslim edildiği hâlde etkisiz.

  Tasarım doğru (pilotla kavga etmesin) ama **operasyonel sonucu net: otonom
  uçuş için PX4 pilot olmayan bir modda olmalı** — OFFBOARD(4),
  AUTO_MISSION(5), AUTO_LOITER(6). Test sırasında `AUTO.LOITER`'a alınca
  otonomi anında devam etti.

  > Kumandayı **kapatmak** çözüm değil: RC kayıp failsafe'i devreye girer ve
  > ylp00'da o failsafe **kill** tetikliyor (§1). Doğru yol kumandanın mod
  > switch'ini pilot olmayan bir moda almak.

- `[ ]` **`status_text` bayat kalıyor.** `pilot_override_active` false'a
  döndükten sonra da `status_text: Pilot override active` okunuyor; alan
  yalnız belirli olaylarda üzerine yazılıyor. Sahada yanıltıcı — bayrağın
  kendisine bakmak lazım.

- `[!]` **FCU'yu doğrudan arm etmek sürü FSM'ini ARMED yapmaz — ÖLÇÜLDÜ
  (30 Temmuz). Yarışma açısından en kritik operasyonel bulgu.**

  ylp00 MAVROS'tan gerçekten arm edildi (`success=True`, `armed: true`) ama
  `AgentStatus.state` **1 (IDLE) olarak kaldı** ve **lider seçimi olmadı.**

  Sebep tasarımda: `_from_idle` geçişi `ctx.pending_state == ARMING` istiyor
  ve bunu **yalnız `EVENT_MISSION_STARTED` olayı** kuruyor
  (`agent_fsm_node.py:277`). FCU'yu QGC'den, MAVROS'tan **veya kumandayla**
  arm etmek FSM'i atlar.

  Sonuç: **pilot kumandayla arm ederse sürü yığını kendini armlı saymaz →
  `ELIGIBLE_STATES` sağlanmaz → lider seçilmez → formasyon mesh'e çıkmaz.**
  Uçuş prosedürü buna göre yazılmalı: arm **görev başlatma olayı üzerinden**
  gelmeli.

  > **DİKKAT — tezgâhta görev başlatmak kalkış denemesidir.**
  > FSM `ARMED`'a girince PX4'e `offboard` komutu veriyor
  > (`_dispatch_px4_command`), `px4_bridge` de sürekli offboard setpoint
  > yayınlıyor, yani PX4 OFFBOARD'ı kabul eder. Ardından `ARMED → TAKEOFF`
  > koşulu sağlanır ve `takeoff:<irtifa>` gider. Pervane takılıyken bu
  > gerçek bir kalkıştır.

- `[x]` **ÇÖZÜLDÜ — `healthy=false` neden geliyordu.** 30 Temmuz sabahı
  `healthy: false` ölçülmüştü (pil 14.48 V, kumanda kapalı). Pil
  değiştirilip (16.61 V) kumanda açıldıktan sonra **`healthy: true`**
  ölçüldü. Yani düşük pil ve/veya RC bağlantısızlığı kaynaklıydı, kalıcı
  bir arıza değil.

- `[ ]` **RTK yeniden birleştirme tek slotlu ve yalnız `paket_id` ile
  anahtarlı.** İki farklı kaynak aynı anda RTK gönderirse parçalar karışabilir.
  Şu an tek kaynak var (base), o yüzden **bugün zararsız** — ama ikinci bir
  RTCM kaynağı eklenirse (örn. yedek baz) bu bir hata olur.
- `[ ]` **`px4_bridge`'de `frag` sayacı ölü.** Parçalamayı artık MAVROS yapıyor,
  `_rtk_yayinlanan_frag` hiç artmıyor ama tanı satırında görünüyor. Yanıltıcı;
  ya kaldırılmalı ya `msg` ile eşitlendiği not edilmeli.
- `[ ]` **`ROS_LOCALHOST_ONLY` Jazzy'de deprecated.** Her düğüm açılışta uyarı
  basıyor. İleride `ROS_AUTOMATIC_DISCOVERY_RANGE` + `ROS_STATIC_PEERS`'a
  geçilmeli. Şimdilik çalışıyor.
- `[ ]` **GitHub PAT hâlâ geçerli.** `~/.git-credentials` içinde (chmod 600).
  İş bitince **iptal/rotasyon** yapılmalı. Bu bir güvenlik borcu.
- `[ ]` **`src/gcs/frontend/tsconfig.tsbuildinfo` takip ediliyor.** Derleme
  çıktısı; her build'de kirli görünüyor. `.gitignore`'a alınıp takipten
  çıkarılmalı.
- `[ ]` **QGC ini'de `autoConnectRTKGPS=false`.** u-blox'u QGC kapıyorsa
  çakışma olur; kararlaştırılmadı.
- `[ ]` **`main`'deki 54 dosyanın dronlara senkronu.** Karar verilmedi. Şu an
  dronlarda `feature/mesh-suru-entegrasyon` var ve kod HEAD ile aynı.
- `[ ]` **`/tools` `.gitignore`'da (satır 352).** Oraya konan dosyalar sessizce
  commit edilmiyor. Farkında olunmalı.
- `[ ]` **PX4 log kapalı ve açılmayacak** (RAM yetmiyor). Yani FCU içi teşhis
  için log yok; teşhis MAVLink + Pi logları üzerinden yapılmak zorunda.

---

## 4. Tuzaklar (bir daha aynı yere düşmemek için)

Bunlar **hata değil**, sessizce yanlış sonuç ürettikleri için yazılıyor.

- **`ros2 topic pub` ile `ElectionResult` yayınlamak çalışmaz.** Köprünün
  aboneliği `_ELECTION_QOS` = RELIABLE + **TRANSIENT_LOCAL**
  (`esp32_bridge_node.py:110`); `ros2 topic pub` varsayılanı VOLATILE.
  DURABILITY uyumsuzluğundan mesaj **hiç ulaşmaz**, hata da çıkmaz — yalnız
  `lider=0` kalır. Elle yayında şart:
  `--qos-reliability reliable --qos-durability transient_local`.
  Gerçek `consensus_node` aynı TRANSIENT_LOCAL'i kullanıyor
  (`consensus_node.py:118`), yani **sistemde uyumsuzluk yok**.
- **OFFBOARD'dayken disarm REDDEDİLEBİLİR.** OFFBOARD konum-tutmak hover gazı
  ister (~%40-50, rölantiden çok hızlı); PX4 bunu görünce iniş dedektörüyle
  "havadayım" der ve normal disarm'ı reddeder. Ölçüldü: `success=False,
  result=1`. **Önce `AUTO.LOITER`'a al, sonra disarm et** — o zaman kabul
  ediyor. Son çare zorla disarm (`param2=21196`), ama o YALNIZ YKİ'nin
  operatör yolunda var; otonom yığın asla kullanmıyor.
  > Pervanesiz tezgâh testinde bu şaşırtıcı: dron "uçuyor" sanılır, motorlar
  > hızlanır, disarm tutmaz. Kumandayı elde tutun.
- **Motor kesme yolları (senaryo: "dron düşmesin") — ölçüldü.**
  Dron tarafındaki tek disarm yolu normal `CommandBool value=False` ve PX4
  bunu uçarken reddediyor. Zorla disarm (21196) dron kodunda **hiç yok**.
  Offboard kaybında `COM_OBL_RC_ACT = 0` → **POSCTL**, yani kumanda pilota
  geçer, motor kesilmez. `COM_LOW_BAT_ACT = 2` (dönüş),
  `COM_DISARM_LAND = 2.0 sn` (yalnız iniş dedektörü "indim" dedikten sonra).
- **`kill_switch_active` karttaki fiziksel güvenlik/kill switch'i GÖRMEZ.**
  O alan RC kanalından türetiliyor. 30 Temmuz'da `kill_switch_active: false`
  okunurken arm reddediliyordu; gerçek sebep dronun üzerindeki switch'ti.
  Yani bu alana bakıp "kill sorunu yok" demek yanlış.
- **PX4 1.16 arm reddini `STATUSTEXT` ile değil MAVLink Events ile bildirir.**
  MAVROS metadata olmadığı için `FCU: EVENT 3087815 with args ...` gibi çıplak
  ID basar; `statustext/recv` boş kalır. **Gerekçeyi düz metin görmek için
  QGroundControl** kullanılmalı (event metadata'yı çözüyor). Bunu bilmeden
  MAVROS logunda saatler harcanır.
- **Yerde disarm haldeyken lider seçimi OLMAZ — ve bu doğru davranıştır.**
  `ELIGIBLE_STATES = {ARMED, TAKEOFF, IN_SWARM, EXECUTING_TASK}`; yerdeki
  dron `STATE_IDLE`. Ölçüldü: iki dronda da `consensus_node` 12 saniye
  koştu, **seçim sayısı 0**. "Consensus bozuk" diye aramaya başlamadan önce
  bu hatırlanmalı. Yerde test için tek yol `AgentStatus` enjekte etmek.
- **`_on_election` HİÇBİR ŞEY loglamaz.** `ctx.leader_id`'yi doğrudan yazıyor,
  `_set_leader`'ı çağırmıyor — dolayısıyla ne log ne event çıkar. Bir
  takipçinin lideri öğrenip öğrenmediği consensus logundan **anlaşılamaz**;
  ilk denemede tam bunu yanlış okudum. Dolaylı gözlem: yanlış lider enjekte
  edilirse bir sonraki tick `REASON_LEADER_FAULT` ile geri alır ve o
  **loglanır**.
- **Formasyon paketinde `sequence_num` mesh üzerinden TAŞINMAZ.** 16 baytlık
  yükte yer yok (`formasyon_veri_t` tam 16 bayt dolu); alıcı kendi sayacını
  üretir. Test: 42 gönderildi, 12 alındı. Hata değil — ama hiçbir tüketici
  formasyonun `sequence_num`'ını dronlar arası karşılaştırmak için
  kullanmamalı.
- **`STATE_ARMED` mesh'te ayrı kod taşımaz**, `KALKIS`'a eşlenir ve karşı
  tarafta `STATE_TAKEOFF` olarak çözülür. İkisi de `ELIGIBLE_STATES` içinde
  olduğu için **uygunluk korunur** (split-brain riski yok). Yan etki:
  komşular, yerde arm olmuş bir dronu `AIRBORNE_STATES` içinde görür. Lider
  yerde armlı, takipçi havadaysa takipçi lideri "havada ama heartbeat yok"
  sayıp düşürür — savunulabilir bir davranış, ama bilinmesi gerekir.
- **`esp32_bridge` tanısı log dosyasına yazmaz.** `/swarm/internal/events/system`
  topic'ine `mesh_diag ...` olarak gider. `esp.log`'da yalnız açılış satırları
  vardır; oraya bakmak "sayaç yok" yanılgısı yaratır.
- **QGroundControl açıkken u-blox takmak ayarları BOZAR — ölçüldü
  (30 Temmuz).** QGC'nin RTK oto-bağlanması modülü **RAM'e yazarak**
  yeniden yapılandırıyor: 1 Hz → **10 Hz**, `1005` ve `1230` **kapalı**,
  survey-in süresi 300 → 180 s. Sonuç: RTCM 5 msg/s'ten **40 msg/s**'e
  fırlıyor (mesh bütçesini aşar) ve baz konumu hiç gelmiyor.

  Kalıcı katmanlar (Flash **ve** BBR) bozulmuyor, yalnız RAM eziliyor →
  **u-blox'u çıkarıp takmak düzeltir.** Tekrarlamaması için QGC ini'sine
  eklendi: `~/.config/QGroundControl.org/QGroundControl.ini`,
  `[LinkManager]` altında `autoConnectRTKGPS=false` (yedek:
  `QGroundControl.ini.yelpence-yedek`).

- **u-blox'ta katman kontrolü RAM/FLASH ile YETMEZ — BBR de okunmalı.**
  F9P açılışta `Default → Flash → BBR` sırasıyla yükler, yani **BBR, Flash'ı
  ezer.** Yalnız RAM/FLASH karşılaştırmak "ayarlar kalıcı" yanılgısı verir.
  `--kalici` yazımı üç katmana birden yazıyor (bitmask 7 = RAM|BBR|Flash),
  doğrulama da üçünü birden okumalı.

- **YKİ tarafında `RMW_IMPLEMENTATION` + `CYCLONEDDS_URI` vermeden düğüm
  başlatmak.** Topic hiç bağlanmaz, sayaç 0 kalır, **hata çıkmaz**. RTCM
  okuyucusunda tam bunu yaşadık.
- **`timeout` ile `ros2` komutu kesmek.** SIGTERM ile ölen Python'u Ubuntu
  apport "uygulama çöktü" popup'ı olarak gösteriyor. `timeout -s INT`
  kullanılmalı — SIGINT temiz kapatıyor.
- **Dron Pi'lerinin IP'leri DHCP ve değişiyor.** 30 Temmuz'da ylp00
  `10.158.16.166` → `10.158.16.134` oldu. ARP'ta Raspberry Pi MAC öneki
  `88:a2:9e` ile bulunabilir.
- **`UAVCAN_*` parametreleri reboot ister** ve FCU reboot'u **MAVLink yayın
  hızlarını sıfırlar** → `mesaj_hizlari.py` tekrar koşmalı (konteyner restart
  bunu sırayla yapıyor).

---

## 5. Doğrulanmış olanlar (tekrar yapılmasın)

Bunlar ölçüldü. Yeniden kurcalamak gereksiz.

- **RTCM zinciri, u-blox'tan MAVROS'a kadar** — 30 Temmuz.
  `u-blox 5 msg/s -> YKİ okuyucu -> ROS -> base ESP -> mesh -> dron ESP
  -> esp32_bridge -> px4_bridge -> MAVROS`.
  Her iki dronda `tampon=0B`, `sync_kayip=0`, `cb_hata=0`, `rtcm_red=0`.
- **`UAVCAN_PUB_RTCM=1` ylp02'de kalıcı** — FCU reboot sonrası korundu.
- **u-blox ayarları güç kesintisine dayanıklı** — RAM ve FLASH katmanları
  ayrı ayrı okundu, tutarlı.
- **Mesh formasyon aktarımı (ylp00 -> ylp02)** — 30 Temmuz. İki tur:
  - V formasyonu (elle bildirilen liderle): `form_tx=11` / `form_rx=11`.
    center 12.3/-45.6/-8.0, heading 137.5, spacing 4.0, max_speed 3.5.
  - ÇİZGİ formasyonu (**gerçek seçilmiş liderle**): `form_tx` 11→21,
    `form_rx` 11→21, `form_lider_degil` 9'da **sabit** (tek mesaj kapıda
    reddedilmedi). center 5.0/10.0/-6.0, heading 90.0, spacing 6.0.
  Her iki turda `form_yarim=0`, `form_sahipsiz=0`, `gonderim_drop=0`.
- **Formasyon geometrisi tipe duyarlı ve iki tarafta aynı.** V'de offset
  `2.8284` (= 4.0 × cos45°, çapraz), ÇİZGİ'de `[0, 6.0]` (doğu boyunca).
  Alıcı kendi türetiyor, mesh'te taşınmıyor.
- **Gerçek lider seçimi (`consensus_node`)** — 30 Temmuz.
  `[CONSENSUS] Lider: 0 -> 1 (round=1, ben=1)`. `is_eligible` →
  `eligible_ids` → `effective_set` → `decide_change` → bootstrap grace →
  `_set_leader` → `ElectionResult` yayını zincirinin tamamı gerçek koştu.
- **TAM ZİNCİR, SIFIR SAHTE GİRDİ (pervaneler çıkarık)** — 30 Temmuz.
  ylp00 gerçekten arm edildi ve seçim gerçek `STATE_ARMED` ile oldu:

      durum izi:  1 -> 2 -> 3 -> 1   (IDLE -> ARMING -> ARMED -> IDLE)
      fsm.log:    ARMING -> ARMED  /  Rol: LEADER
      consensus:  [CONSENSUS] Lider: 0 -> 1 (round=1, ben=1)

  Sıra: `EVENT_MISSION_STARTED` → `pending_state=ARMING` → **gerçek
  preflight geçti** (`origin_synced`, `home_set`, EKF, GPS fix 4, pil
  16.6 V) → FSM PX4'e `arm` komutu → ARMED → seçim.
  ylp02'ye ulaşma süresi **109 ms** (`...667.014` → `...667.123`) ve
  incarnation düzeltmesi orada **üçüncü kez** çalıştı.
  Sonunda PX4 kendiliğinden disarm etti, FSM `ARMED -> IDLE` döndü.
- **Lider devralma / `REASON_LEADER_FAULT` dalı** — 30 Temmuz. Yanlış lider
  (3) enjekte edildi, `decide_change` "lider effective kümede yok" deyip
  liderliği geri aldı: `Lider: 3 -> 1 (round=6, ben=1)`.
- **incarnation düzeltmesi uçtan uca (gerçek donanım)** — 30 Temmuz.
  ylp00'ın `consensus_node`'u yeniden başlatıldı (`incarnation 11724 ->
  33991`), yeni seçim **yine `seq=1`** ile yayınlandı, mesh'ten ylp02'ye
  gitti ve ylp02 kabul edip logladı:

      [CONSENSUS] ajan 1 yeniden baslamis (incarnation -> 33991),
      seq sayaci sifirlandi

  ylp00 seçimi `...842.890`, ylp02 kaydı `...842.912` — **22 ms.**
  Düzeltme öncesi bu mesaj sessizce düşüyordu.
- **TAM AKIŞ: görev başlat → arm → offboard → TAKEOFF** — 30 Temmuz,
  pervaneler çıkarık. Düzeltmelerden (`ea80852`) sonra:

      durum izi:  1 -> 2 -> 3 -> 4 -> 14   (IDLE/ARMING/ARMED/TAKEOFF/FAILSAFE)
      PX4 mod:    AUTO.LOITER -> OFFBOARD
      seçim:      [CONSENSUS] Lider: 0 -> 1

  FSM logundaki belirleyici satır — düzeltmeden önce burada `offboard=False`
  yazıyor ve dron sonsuza kadar takılıyordu:

      ARMED bekliyor: mission_start=True offboard=True sure=0.1s armed=True

  `TAKEOFF -> FAILSAFE` geçişi tam 30 sn'de oldu = `_TAKEOFF_TIMEOUT_S`.
  **Beklenen ve doğru davranış:** pervanesiz irtifaya ulaşılamaz, FSM de
  doğru şekilde failsafe'e düşer. Hata değil.
- **LİDER KALP ATIŞI İLK KEZ YAYINLANDI** — 30 Temmuz. `TAKEOFF` durumu
  `AIRBORNE_STATES` içinde olduğu için `own_airborne` True oldu ve
  `_publish_heartbeat` çalıştı: **300 mesaj**, `leader_id: 1`,
  `sequence_num` monoton artıyor, `active_agent_count: 1`.
  Bu yol daha önce hiç çalışmamıştı.
- **`.msg` değişikliği iki dronda da derlendi** (`swarm_interfaces`, 1dk 24s).
  Host PC'de colcon/CMake çöküyor ve `ament_flake8` yok — **host ROS
  geliştirme ortamı eksik**, ayrı bir sorun; derleme dronların
  konteynerinde yapılıyor ve orada sağlam.
- **Lider loopback** — liderin kendi `/swarm/public/formation/target` çıktısı
  takipçininkiyle **birebir aynı**. Loopback olmasa lider tam hassasiyetli,
  takipçi kuantize hedefe uçardı.
- **Lider bilgisi mesh üzerinden yayılıyor** — ylp02 `lider=1`'i
  `TIP_ELECTION` paketinden öğrendi.
- **ESP firmware'lerinde yeni TIP'ler whitelist'te** — `form_rx=11` paketlerin
  havadan geçtiğini kanıtlıyor (base + ylp00 + ylp02 flaşlandı).
- **V formasyon geometrisi iki tarafta aynı** — offset `2.8284` = 4.0 × cos45°,
  alıcı kendi türetiyor, mesh'te taşınmıyor.
- **Uçuş kaydı güç kesintisine dayanıklı** — mcap yerel sıkıştırma, SIGKILL
  testiyle doğrulandı.
- **Düğüm logları yeniden başlatmada silinmiyor.**
- **Dronlardaki kod HEAD ile aynı** — `dagit.sh` + `.surum` izlemesi çalışıyor.

---

## 6. Sıradaki mantıklı adım

1. **`healthy=false` kaynağını bul** (§3) — arm edildikten sonra da false
   kalırsa lider seçimi hiç olmaz. Masada, arm edilerek test edilebilir.
2. **ylp01'i ayağa kaldır** — şartname 3 İHA istiyor, en büyük tek eksik.
3. **RC failsafe** — uçuş izninin kapısı; masada yapılabilir (verici + alıcı).
4. **Açık alana çık:** RTK survey-in + `1005` + `fix_type` 5/6 doğrulaması.
5. **CUSTOM formasyon + `TIP_FORM_OFSET`** — jüri dizilişi bu yoldan gelecek.
