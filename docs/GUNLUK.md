# GÜNLÜK — oturum devir teslim kaydı

**Son güncelleme:** 17 Ağustos 2026, 04:11

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

## 2026-08-17 04:11 — Beyza + Osman + Claude (depo devri, belge sadeleştirme, YKİ Arch kurulumu, ağ teşhisi)

> **Üç oturum tek kayıtta birleştirildi:** 16 Ağustos 19:50 ve 21:32 (depo ve
> belge düzeni, uçağa dokunulmadı) + 16/17 Ağustos gecesi (YKİ laptopunun
> sıfırdan kurulumu ve "RPi bağlanınca internet kopuyor" arızasının teşhisi).

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

**Ne değişti**

- kod: yok. Üç oturumda da yalnız dosya silme, belge düzeni ve laptop kurulumu.
- **uçakta (ylp00):** yalnız **SSH anahtarı** eklendi. `gcs_url` denendi ve
  **eski hâline geri alındı**; diğer bayrakların (`yer_testi`, `gozlem`,
  `kacinma`, `origin`, `suru_dugumleri`) hiçbirine dokunulmadı, uçak
  bulunduğu gibi bırakıldı. **ylp02'ye hiç bağlanılmadı.**
- laptopta (depo dışı): YKİ konteyneri `yki`, `arch-docker/`, QGC v5.0.8,
  `yki`/`ykidur` alias'ları.
- belge: `README.md`, `CLAUDE.md`, `PLAN.md`, `DURUM.md`, `YAPILACAKLAR.md`,
  `RPI_ESITLEME.md`, `INTERFACE_CONTRACT.md` §3.0, `GUNLUK.md`.
  **YENİ:** `docs/TUZAKLAR.md`. **SİLİNDİ:** `docs/arsiv/` (5 dosya).
  `.gitignore`'a `arch-docker/` eklendi.

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
- 🔴 **`formation_node.py:189` — `sitl_mode` varsayılanı `True`,
  `baslat.sh` geçmiyor.** İki kapı sahada atlanıyor:

      if not self._sitl_mode and not self._origin_synced:
      if not self._sitl_mode and not (self._xy_valid and self._z_valid):

  `gozlem` açık olduğu için şimdilik zararsız. **G3'te canlı olur** —
  1 Ağustos'ta ylp00'ı deviren zincir buydu.
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

`ADIM 3 · G2` — öncesinde `formation_node` kip kararı
(`NAVIGASYON_KAYMA.md`). YKİ laptopu artık hazır: `yki` yazıp arayüzü açmak
yetiyor.

**Uçakların bırakıldığı hâl**

- ylp00: **açık bırakıldı**, konteyner ayakta. Bayraklar bulunduğu gibi —
  `yer_testi` VAR (ARM olur, **KALKMAZ**) · `gozlem` VAR · `kacinma` VAR ·
  `gcs_url` = `udp-b://:14555@14550` (**yayın** — QGC açık değilse laptopun
  interneti ölür) · `suru_dugumleri` = `origin consensus fsm formasyon` ·
  `origin` = `38.6904758 39.1610188 1216.96` (repo ile aynı). Disk %41 dolu.
  Tek kalıcı değişiklik: Osman'ın SSH anahtarı eklendi.
- ylp02: kapalı, **hiç bağlanılmadı.**
- ylp01: yerde (2 Ağustos'ta düştü), değişiklik yok.


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
