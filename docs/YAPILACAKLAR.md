# YAPILACAKLAR

**Son güncelleme:** 15 Ağustos 2026, 01:42

## Önem dereceleri

Her madde bir seviyeyle işaretlenir. **Seviye vermeden madde ekleme** —
seviyesiz liste bir süre sonra kimsenin okumadığı bir yığına dönüşüyor.

| | Seviye | Anlamı | Kural |
|---|--------|--------|-------|
| 🔴 | **P0 — UÇUŞ ENGELİ** | Uçağı, görevi veya kanıtı doğrudan riske atar | **Çözülmeden uçulmaz** |
| 🟠 | **P1 — ACİL** | Takımı bloke ediyor ya da kısa sürede P0'a dönüşecek | Bu hafta |
| 🟡 | **P2 — ÖNEMLİ** | Gerçek iş, ama bekleyebilir | Planla |
| ⚪ | **P3 — İLERİDE** | İyileştirme | Vakit olursa |

Durum: `[ ]` yapılmadı · `[~]` kısmen · `[B]` başka işe bağlı · `[?]` karar bekliyor · `[x]` bitti

> Uçuş kanıtı dönemine ait uzun liste `BEKLEYEN_ISLER.md`'de **arşiv**.
> Oraya artık yazma.

---

## 🔴 P0 — UÇUŞ ENGELİ

### ✅ P0.1 — TAMAMLANDI (14 Ağustos)

`MAKS_EGIM_DEG` artık sabit değil, `ucus_ayarlari.py`'de **ivmeden
türetiliyor** (`MPC_TILTMAX_AIR + 5°`). Ayrıca `MPC_TILTMAX_AIR` iki uçakta
da 30'a eşitlendi, yani eşik (35°) tavanın 5° üstünde — dedektör geçerli.

- `[x]` 🔴 `gorev_kanit_ucus.py` sabiti kaldırıldı, config'den okuyor
- `[x]` 🔴 `MPC_TILTMAX_AIR` ylp00'da 45 → 30

### ✅ P0.2 / P0.3 — TAMAMLANDI (14 Ağustos)

PX4 parametreleri eşitlendi ve uçuş ayarları tek kaynağa bağlandı.
`param_karsilastir.py` → *"Uçaklar arası ayrışma yok"*. Ayrıntı:
`RPI_ESITLEME.md` §8.

- `[x]` 🔴 `MPC_TILTMAX_AIR` 45→30, `MPC_YAWRAUTO_MAX` 45→25,
  `MPC_VEL_MANUAL` 4/2→3.0, `MPC_XY_VEL_MAX` 4.0→5.0 (iki uçakta da)
- `[x]` 🔴 `baslat.sh` artık `/ws/ucus_ayarlari.env` okuyor; hız 3.0 canlıda
- `[x]` 🔴 Konteynerler yeniden başlatıldı, günlük bekçisi de devrede
- `[ ]` 🟠 **ylp01 döndüğünde aynısını uygula** — `RPI_ESITLEME.md` §8

### P0.4 Navigasyon kayması — ölçülmedi

Tam plan: **`NAVIGASYON_KAYMA.md`**. Özet:

Sistem teorik olarak doğru yerde (konum + hız ileri-beslemesi → kalıcı
kayma ≈ 0, hızla büyümez). **Ama bunu doğrulayan ölçüm yok.** Elimizdeki
tek sayı 7 m'lik bir bacaktan geldi, yani geçici rejimi ölçüyor.

- `[ ]` 🔴 **ÖLÇ:** tek uçak, **en az 40 m düz bacak**, iki hızda (2 ve 4 m/s).
  Kayıttan `setpoint_raw/local` ile `local_position/pose` farkını çıkar.
  Üç sayı: kalıcı kayma · tepe geçici hata · oturma süresi.
  Bu ölçüm hızı yükseltmenin önünü açar ya da kapatır.
- `[x]` 🔴 ~~Doygunluk payı denetimi~~ → `ucus_ayarlari.py` artık
  `tavan ≥ seyir × 1.5` şartını **hata** olarak veriyor
- `[ ]` 🟠 **İvme ileri-beslemesini aç** — kanal mesajda var
  (`ax/ay/az`, `acceleration_valid`) ama `mavros_command_sender`'ın
  **dört type_mask'ında da** `IGNORE_AFX|AFY|AFZ` var. Geçici rejimdeki
  kaymayı kaldırır. Adım 1'in ölçümü değip değmeyeceğini söyleyecek.
- `[ ]` 🟠 **Sürü tarafı Durum 1'e düşmesin** — `formation_node`'un SVT'si
  saf oransal (`v = −0.8 × hata`), yani ileri-besleme YOK. Kalıcı kayma
  `v/0.8`, PX4'ün 0.95'inden bile kötü. Çözüm: `formation_node`'u
  konum kipine al (`position_valid=True`).

---

### P0.5 Final görevi donanım şartları

Şartname okundu (15 Ağustos). Üç şart yazılımla çözülemez:

- `[x]` ✅ Her İHA için ayrı pilot + kumanda — **var**
- `[ ]` 🟠 **Kamera** takılacak. FOV ≤ 90°. QR 120×120 cm; hangi irtifadan
  okunduğu **ölçülmeli** (Aşama 3'ün ön koşulu, diğer aşamaları engellemez)
- `[ ]` 🟡 **ylp01** — final görevinde **3 İHA şart**, ama entegrasyonu
  engellemiyor. Yalnız Aşama 5'teki üyelik testi üç uçak istiyor

### P0.6 Sürü entegrasyonunun iki yapısal engeli

Tam analiz: `SURU_ENTEGRASYON.md` §2 ve §3.

- `[x]` ✅ **Çarpışma önleme seçimi KARARA BAĞLANDI** → `KARARLAR.md` KARAR-01
  (Seçenek C: `collision_avoidance` + ham `AgentStatus`, `d0=8 m` ile başla).
  Uygulama Aşama 1B'de.
- `[?]` 🔴 **internal/public köprüsü eksik.** `SwarmState` ve `MissionTarget`
  `esp32_bridge` tarafından **taşınmıyor** → `swarm_fsm` ve `mission_fsm`
  çıktıları boşluğa yayınlanıyor, `mission1` onları asla göremiyor.
  Karar: yerel remap mı, mesh'e eklemek mi?
- `[ ]` 🔴 **`px4_bridge` öncelik hakemliği yok.** `AgentSetpoint`'te
  `priority` alanı var (FAILSAFE 100 > CA 80 > POSITION 30 > MANEUVER 20 >
  FORMATION 10) ama `px4_bridge` **kullanmıyor** — son geleni alıyor.
  Dört ayrı düğüm setpoint yazacak; hakemlik olmadan hiçbiri güvenle açılamaz.

---

## 🟠 P1 — ACİL

### ✅ P1.1 — TAMAMLANDI (15 Ağustos)

`iPhone` hotspot'u iki uçağa da eklendi, güç tasarrufu kapalı,
`rpissid` öncelikli (10) kalacak şekilde. Ayrıntı: `RPI_ESITLEME.md` §7.

- `[x]` 🟠 iPhone hotspot eklendi (ylp00 + ylp02)
- `[ ]` 🟠 **SSID doğrulanmadı** — telefon kapalıydı. Açıldığında bir kez
  bağlanıp teyit et; farklıysa `nmcli connection modify iphone-hotspot
  wifi.ssid "..."`
- `[ ]` 🟠 ylp01 döndüğünde aynısını uygula

### P1.2 SSH anahtarları

Parola girişi **açık** (doğrulandı), kullanıcı adları `yelpence00/01/02`,
parola takım içinde paylaşılıyor (**repoya yazılmadı, yazılmayacak**).
Yani her üye kendi anahtarını **kendisi** kurabilir, Eyüp'ün orada olması
gerekmiyor.

- `[ ]` 🟠 Her üye kendi bilgisayarında bir kez:
  ```bash
  ssh-keygen -t ed25519
  ssh-copy-id yelpence00@<ip>    # üç drone için de
  ```
- `[ ]` 🟡 Anahtarlar dağıtıldıktan sonra parola girişini kapatmayı düşün
  (ama sahada kilitli kalma riskine karşı acil çıkış olarak bırakmak da savunulabilir)

### P1.3 Repo commit edilmemiş

Uçuş kanıtını geçiren kodun **tamamı** tek diskte, git'te değil.
Disk arızası = her şey gider.

- `[ ]` 🟠 Anlamlı parçalara böl ve commit et: px4_bridge irtifa düzeltmesi /
  FSM pil guard'ı / kayıt sertleştirme + günlük bekçisi / YKİ koşucu paneli /
  saha senaryosu / takım belge sistemi

---

## 🟡 P2 — ÖNEMLİ

### P2.1 Log patlamasının kök nedeni duruyor

Günlük bekçisi eklendi ve disk açıldı, ama bekçi **belirtiyi** kesiyor.
WiFi düşünce MAVROS `gcs_url` uçnoktasına her MAVLink mesajı için
`Network is unreachable` basmaya devam edecek.

- `[ ]` 🟡 QGC kullanılmadığında `gcs_url` dosyasını kaldır, ya da mavconn
  stderr'ini ayrı dosyaya ayır
- `[ ]` 🟡 Konteyner yeniden başlatılınca bekçinin çalıştığını doğrula
  (`gunluk/son/bekci.log`)
- `[ ]` 🟡 `izleme_kur.sh`'teki disk bekçisi bunu neden yakalamadı?

### P2.2 ylp01 onarımı

- `[ ]` 🟡 Güç modülü çıkışı → PDB → ESC güç lehimleri
- `[ ]` 🟡 ESC sinyal kablo demeti
- `[ ]` 🟡 RPi neden açılmıyor (SD kart sağlam)
- `[ ]` 🟡 Onarım sonrası **`RPI_ESITLEME.md`'yi baştan sona yürüt** —
  düştüğünde üzerinde eski `esp32_bridge_node.py` ve `basit_kacinma_node.py`
  vardı, kalkışta devrilmeye yol açan düzeltme yoktu. **Kod senkronu ilk iş.**

Üç uçak olmadan n=3 okbaşı geometrisi ve rol dağıtımı denenemez.

### P2.3 Sürü entegrasyonu — Faz 0

Tamamı `SURU_ENTEGRASYON.md`'de. Uçuşsuz hazırlık:

- `[ ]` 🟡 Kayıt filtresine `/gozlem/` ekle (`baslat.sh`)
- `[ ]` 🟡 `SURU_DUGUMLERI`'ni `/ws/suru_dugumleri` dosyasından okunur yap
  (env değiştirmek konteyneri yeniden yaratmak demek; `/ws/kacinma` gibi olsun)
- `[B]` 🟡 Faz 1 (`kinematic_fusion`) — Faz 0'a bağlı

### P2.4 Güvenlik ve dayanıklılık

- `[ ]` 🟡 **ESC telemetrisini aç** — 2 Ağustos kazasının sebebini doğrudan
  cevaplardı. Kayıt filtresi `esc_status/*` ve `esc_telemetry/*`'yi zaten
  bilerek tutuyor, veri akınca otomatik kaydedilir.
- `[ ]` 🟡 Kill switch kontrolünü ön kontrole taşı — şu an operatör bunu
  ancak arm denemesinde görüyor

### P2.5 Belge borcu

- `[ ]` 🟡 Drone'lardaki **21 betiği** repoya al ya da sil
  (`COP_TEMIZLIK.md` §D). Sahada yazılmış teşhis araçları — versiyonsuz,
  kaybolabilir, kimse ne olduklarını bilmiyor.
- `[x]` 🟡 ~~`README.md` sim kurulumu anlatıyor~~ → giriş noktası olarak yeniden yazıldı
- `[x]` 🟡 ~~`ARCHITECTURE.md` yanıltıcı~~ → başına uyarı kondu

---

## ⚪ P3 — İLERİDE

- `[ ]` ⚪ Kalkış öncesi **otomatik ön kontrol listesi** — pil, RTK, kill,
  parametre eşitliği tek komutta. Parçaları var (`on_ucus_kontrol.py`,
  `param_karsilastir.py`), birleştirilmedi.
- `[ ]` ⚪ Uçuş kaydı çözümleme aracı (rosbag2 → grafik). Her kazadan sonra
  elle sorgu yazılıyor.
- `[?]` ⚪ `sim/` klasörü ve `scripts/` sim betikleri — sil mi, arşiv dalına mı
  (`COP_TEMIZLIK.md` §B). **Karar operatörün.**
- `[ ]` ⚪ `src/gcs/qgc_proxy.py` sil — `cihazlar.md` "KULLANILMIYOR" diyor
- `[ ]` ⚪ Kök dizindeki 4 görsel ve 2 PDF'i yerleştir (`ss/` ve `docs/sartname/`)
- `[ ]` ⚪ `.surum` dosyasını güvenilir yap — `dagit.sh` senkron sonrası yazmıyor,
  bu yüzden senkron kontrolü md5 gerektiriyor

---

## ✅ Yakında bitenler

- `[x]` 🔴 **Disk %100 doluydu** → temizlendi + günlük bekçisi
  (100 MB tavan, son 25 MB korunur). ylp00 19 GB boş, ylp02 21 GB boş.
- `[x]` 🟠 **Drone bulma** → `deploy/yki/drone_bul.sh` (mDNS + MAC taraması)
- `[x]` 🔴 **PX4 parametresi okunamıyor** → `src/gcs/px4_param.py` +
  `deploy/yki/param_karsilastir.py`. Sorun `param/get` servisinin var
  olmamasıydı; doğrusu yerel `ros2 param get`, ama tek tek çağırınca zaman
  aşımına düşüyor — araç toplu `get_parameters` kullanıyor.
