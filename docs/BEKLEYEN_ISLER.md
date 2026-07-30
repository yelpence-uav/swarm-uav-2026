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

- `[ ]` **ylp01 hiç ayağa kalkmadı.** Şartname **3 İHA** istiyor. Kurulum,
  dağıtım (`dagit.sh`), ESP flash, parametre seti — hiçbiri yapılmadı.

- `[ ]` **Uçuşta formasyon testi.** Mesh aktarımı masada doğrulandı (§5) ama
  havada, gerçek konum/EKF ile hiç denenmedi.

---

## 2. Doğrulanmamış kod yolları

Kod yazıldı, birim testleri geçiyor, ama **gerçek meshte/donanımda hiç
çalışmadı**. Her biri sessizce bozuk olabilir.

- `[~]` **Gerçek lider seçimi (`consensus_node`).** 30 Temmuz'da **doğrulandı**
  (bkz. §5), ama şu parçalar hâlâ denenmedi:
  - `[ ]` Gerçekten arm olmuş dronla otomatik seçim (test `AgentStatus`
    enjekte edilerek yapıldı; yerde arm etmek pervane riski).
  - `[ ]` **Lider kalp atışı (`_publish_heartbeat`) hiç çalışmadı.**
    `if ctx.is_leader and own_airborne` koşulu var; yerde `own_airborne`
    False olduğu için tek heartbeat yayınlanmadı. Yani heartbeat timeout'a
    dayalı lider düşmesi tespiti (`effective_set`'teki `hb_age` dalı) hiç
    sınanmadı. **Bu yalnız uçuşta test edilebilir.**
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

- `[ ]` **`healthy=false` geliyor.** ylp00'ın gerçek `AgentStatus`'unda
  `healthy: false` — `is_eligible` kapılarından biri. Yerde `state=IDLE`
  zaten uygunluğu engellediği için bugün fark etmiyor, ama **arm edildiğinde
  bu hâlâ false ise seçim yine olmaz.** Kaynağı araştırılmalı (`agent_fsm`
  hangi koşulda true yapıyor).

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
  Tek sahte girdi `AgentStatus` idi (yerde arm etmek pervane riski).
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
