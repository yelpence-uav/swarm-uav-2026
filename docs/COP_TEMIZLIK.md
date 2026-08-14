# ÇÖP TESPİTİ — sim döneminden kalanlar ve dağınıklık

**Son güncelleme:** 15 Ağustos 2026, 01:28

Son haftalarda simülasyon sürü kodları yerine uçuş kanıtını geçirecek kodlar
yazıldı. Bu belge, geride ne kaldığını **gerekçesiyle** listeliyor.

**Hiçbir şey silinmedi.** Silme kararı operatörün; burada yalnız tespit ve
öneri var. Kararlar `YAPILACAKLAR.md` §6'da izleniyor.

---

## A. Kesinlikle çöp — güvenle taşınır/silinir

### A1. Depo kökündeki görseller

```
Pasted image.png          1.5 MB
Pasted image (2).png      2.9 MB
Pasted image (3).png      2.0 MB
ekran görüntüsü.png        21 KB
```

Saha noktalarını seçmek için yapıştırılan ekran görüntüleri. İşleri bitti —
noktalar `gorev_kanit_ucus.py`'deki `SAHA_NOKTALAR_GPS`'e geçti.
**6.4 MB.** Git'e hiç girmemişler (untracked).

→ **Öneri:** sil. Gerekirse `ss/` altına anlamlı adla taşı.

### A2. Üretilen harita HTML'leri

```
src/gcs/saha_rota.html            35 KB
src/gcs/nokta_sec.html             4 KB
src/gcs/nokta3_secenekleri.html    6 KB
```

`gorev_kanit_ucus.py --harita` çıktısı. **Her koşuda yeniden üretiliyor** ve
uçakların o anki konumuna bağlı. Commit'lemek yanıltıcı olur — birkaç gün
sonra gerçeği göstermez.

→ **Yapıldı:** `.gitignore`'a eklendi. Dosyalar kalabilir, git'e girmez.

### A3. Kök dizindeki PDF'ler

```
Şartname 2026.pdf                                    2.0 MB
SÜRÜ_İHA_YARIŞMASI_UÇUŞ_KANIT_ve_YAZILIM_VİDEOSU...pdf  755 KB
```

Bunlar **çöp değil** — yarışmanın resmî belgeleri ve final görevi için hâlâ
gerekli. Ama depo kökü yerleri değil.

→ **Öneri:** `docs/sartname/` altına taşı.

---

## B. Sim dönemi — kullanılmayacak ama karar operatörün

Operatör kararı: **"Bir daha simülasyon kullanmak istemiyoruz."**
Aşağıdakiler yalnız simülasyon için var.

### B1. `sim/` klasörü — Gazebo dünyaları ve modelleri

```
sim/worlds/base_world.sdf
sim/models/x500/          (mesh, texture, thumbnail)
sim/models/x500_base/
sim/models/rtk_base_station/
```

Git LFS ile izleniyor, boyutu ciddi. Gazebo olmadan hiçbir işe yaramıyor.

→ **Öneri:** silme, **ayrı bir dala al** (`git branch arsiv/sim`) ve ana
daldan çıkar. Sim'e dönme ihtimali sıfır değil; LFS geçmişi zaten kalır.

### B2. `scripts/` — sim başlatıcıları

| Dosya | Ne yapar | Durum |
|-------|----------|-------|
| `launch_swarm.py` (467 satır) | Gazebo Harmonic + PX4 SITL + tüm ROS düğümleri | Sim'siz işlevsiz |
| `video_scenario_director.py` (511 satır) | Sim'de video senaryosu sürücüsü | Sim'siz işlevsiz |
| `start_video_scenario.sh` | `launch_swarm.py`'ı gerektiriyor (tmux oturumu arıyor) | Sim'siz işlevsiz |
| `_run_consensus.sh`, `_run_director.sh`, `_run_kinfusion.sh`, `_run_mission1.sh` | `start_video_scenario.sh` yardımcıları | Sim'siz işlevsiz |
| `swarm_config.py` | Sim hız/geometri sabitleri | Sim'siz işlevsiz |
| `generate_task_world.py` | Gazebo dünyası üretir | Sim'siz işlevsiz |
| `generate_qr_content.py` | QR içeriği üretir | **KALSIN** — final görevinde QR var |

→ **Öneri:** `generate_qr_content.py` hariç hepsini `arsiv/sim` dalına.
**Ama önce oku**: `launch_swarm.py` ve `video_scenario_director.py`, sürü
düğümlerinin hangi parametrelerle ve hangi sırayla başlatılacağını biliyor.
Bu bilgi Faz 0'ın G0 taramasında işe yarar — silmeden önce çıkar.

### B3. Sim ROS paketleri

| Paket | Ne yapar | Not |
|-------|----------|-----|
| `src/network_proxy/` (1403 satır) | Sim'de ESP-NOW'ı taklit eder (paket kaybı, gecikme) | Sahada yerini `esp32_bridge` alıyor |
| `src/sim_rtcm_source/` (591 satır) | Sim'de RTCM üretir | Sahada yerini gerçek F9P alıyor |

**Bunlar zaten drone'lara dağıtılmıyor** — `deploy/rpi/dagit.sh` ikisini de
bilerek dışarıda bırakıyor ve sebebini yazıyor. Repo bu konuda kendini biliyor.

→ **Öneri:** **DOKUNMA.** Zararsızlar (dağıtılmıyorlar) ve
`INTERFACE_CONTRACT.md` topic adlandırmasını `network_proxy` sözleşmesine
dayandırıyor — silmek belgeyi kırar.

### B4. `src/px4_autopilot/` submodule

İçinde `COLCON_IGNORE` var, yani derlemeye girmiyor. PX4 SITL için gerekliydi.
Uçaklardaki PX4 önceden yüklü (1.16.1).

→ **Öneri:** submodule olarak kalsın, maliyeti yok. Klonlamada
`--recursive` kullanılmazsa zaten inmiyor.

---

## C. Yanıltıcı belge — çöpten kötü

### C1. `ARCHITECTURE.md`

Sim dönemine ait ve **kodla çelişiyor**:

- `scripts/launch_real_hardware.py` diye bir dosyadan bahsediyor — **yok**
- Sürü akışını Gazebo üzerinden anlatıyor
- Sahada koşan gerçek zinciri (`esp32_bridge → basit_kacinma → px4_bridge`)
  hiç anlatmıyor

Yeni gelen biri bunu okuyup sistemi yanlış anlar. Çöpten kötü çünkü
**güvenilir görünüyor**.

→ **Öneri:** başına açık bir uyarı koy ("Bu belge simülasyon mimarisini
anlatır; sahada koşan yapı için `CLAUDE.md` ve `DURUM.md`") ya da güncelle.

### C2. `README.md` kurulum bölümü

Docker + Gazebo + NVIDIA Toolkit kurulumu anlatıyor. Sim kullanılmayacağına
göre yeni bir takım üyesi için yanlış yol.

→ **Öneri:** saha kurulumunu anlat (Pi'ye dağıtım, YKİ başlatma, SSH).

---

## D. Drone'larda olup repoda olmayanlar

`~/yelpence_ws/` altında **repoda bulunmayan 21 betik** var. Sahada, teşhis
sırasında yazılmışlar. Versiyonsuzlar, yedeksizler, ne yaptıklarını yalnız
yazan biliyor.

```
arm_dene.sh          arm_secim.sh         consensus_baslat.sh
durum_enjekte.sh     form_izle.sh         form_sayac.sh
form_yayinla.sh      gorev_baslat.sh      gps_led_teshis.sh
gps_ornek.sh         inc_dogrula.sh       inc_kanit.sh
offboard_armed.sh    offboard_deney.sh    offboard_once.sh
prearm_teshis.sh     rtk_param.sh         rtk_zincir.sh
seq_deney.sh         tam_kalkis.sh        tam_zincir.sh
```

Adlarından anlaşıldığı kadarıyla değerli olanlar var:
`prearm_teshis.sh`, `rtk_zincir.sh`, `tam_zincir.sh`, `gps_led_teshis.sh` —
bunlar teşhis araçları ve sürü entegrasyonunda tekrar lazım olacak.

Ayrıca:
- `~/yelpence_ws/baslat.sh.yedek_20260802_184714` — eski sürüm yedeği
- `~/yelpence_ws/bozuk_223218/` — adı "bozuk", içeriği bilinmiyor

→ **Öneri:** hepsini indir, oku, **işe yarayanları `deploy/rpi/teshis/`
altına al**, gerisini sil. Bir oturumluk iş ve bilgi kaybını önler.

---

## E. Dokunulmayacaklar (yanlışlıkla çöp sanılmasın)

| Şey | Neden kalmalı |
|-----|---------------|
| `docs/20-temmuz.md`, `28-29-temmuz.md`, `31temmuz-1agustos.md` | Saha günlükleri — ölçümler ve kaza analizleri burada |
| `docs/BEKLEYEN_ISLER.md` | Arşiv; §4 "Tuzaklar" ve §5 "Doğrulanmış olanlar" hâlâ değerli |
| `docs/MESH_PROTOKOL_KARARLARI.md` | Mesh paket formatının tek kaynağı |
| `docs/YELPENCE_RTCM_SPEC.md` | RTK zincirinin tek kaynağı |
| `src/gcs/*.py` teşhis araçları | `titresim_olc.py`, `pusula_olc.py`, `rtk_baz_survey.py`, `on_ucus_kontrol.py` — hepsi sahada kullanılıyor |
| `firmware/esp32_mesh/.pio/libdeps/` | PlatformIO bağımlılıkları, derleme için gerekli |
| Kod yorumlarındaki uzun gerekçeler | Sahada acıyla öğrenilenler; silmek aynı hatayı tekrar ettirir |

### `src/gcs/qgc_proxy.py`

`cihazlar.md` açıkça **"KULLANILMIYOR"** diyor ve sebebini yazıyor (MAVROS'un
`udp-b` uçnoktası karşı taraf keşfedince yayını bırakıyor, proxy ölünce
telemetri tamamen kesiliyor).

→ **Öneri:** sil. Gerekçe zaten `cihazlar.md`'de kayıtlı, bilgi kaybolmaz.
Duran ölü kod bir gün birinin onu açmasına yol açar.
