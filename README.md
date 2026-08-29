# Yelpençe — TEKNOFEST 2026 Sürü İHA

**Son güncelleme:** 29 Ağustos 2026, 18:55 — belge sadeleştirmesi; filo üç uçak

Takım **Yelpençe** · Takım no **752825**

Üç çok rotorlu İHA'nın sürü hâlinde otonom görev yaptığı sistem. Kararlar
uçağın kendi içinde verilir; yer istasyonunun tek işi görevi başlatmaktır.
(Şartname dağıtık algoritma istiyor, merkezi olan eksik puan — ayrıntı
[`docs/PLAN.md`](docs/PLAN.md) §3.)

---

## 🚀 Yeni misin? Şu sırayla oku

| Sıra | Dosya | Ne verir |
|---|---|---|
| 1 | [`docs/DURUM.md`](docs/DURUM.md) | Şu an ne çalışıyor, uçakta hangi ayar açık |
| 2 | [`docs/YAPILACAKLAR.md`](docs/YAPILACAKLAR.md) | **8 günde yapılacak iş** — 🔴P0 / 🟠P1 / 🟡P2 / ⚪P3 |
| 3 | [`docs/GUNLUK.md`](docs/GUNLUK.md) | Son kişi nerede bıraktı (**en üstteki** kayıt) |
| 4 | [`docs/PLAN.md`](docs/PLAN.md) | Neden böyle yapıldı — şartname, test kademeleri, kalan ADIM'lar |
| 5 | [`docs/KAMERA.md`](docs/KAMERA.md) | Kamera ayarları + QR/renk tespit menzilleri |

Claude Code kullanıyorsan [`CLAUDE.md`](CLAUDE.md) kendiliğinden okunur.

### Hangi soruya hangi belge

| Soru | Belge |
|---|---|
| Nereye gidiyoruz, hangi düğüm ne zaman açılacak? | `docs/PLAN.md` |
| Uçaklarda ne var, hangisinde eksik? | `docs/RPI_ESITLEME.md` §3 |
| Şu an ne çalışıyor, uçaklar hangi hâlde? | `docs/DURUM.md` |
| Son kişi ne yaptı? | `docs/GUNLUK.md` |
| Sırada ne var? | `docs/YAPILACAKLAR.md` |
| Bu konuda karar verilmiş miydi? | `docs/KARARLAR.md` |
| **Çalışmıyor ama hata da vermiyor** | `docs/TUZAKLAR.md` |
| **Kamera, QR ve renk tespiti — ölçülmüş menziller** | **`docs/KAMERA.md`** |
| Uçaklarda ne var, geri gelen drone'a ne yapmalı? | `docs/RPI_ESITLEME.md` |
| SSH, IP, MAC, portlar, QGC, sysid | `docs/cihazlar.md` |
| Mesh paket formatı | `docs/MESH_PROTOKOL_KARARLARI.md` |
| RTK/RTCM zinciri | `docs/YELPENCE_RTCM_SPEC.md` |
| ROS mesaj sözleşmesi | `src/swarm_interfaces/INTERFACE_CONTRACT.md` |

**Çelişki varsa:** canlı belge referans belgeyi yener, **kod ikisini de yener.**

> **Kalkarken `docs/GUNLUK.md`'ye devir teslim kaydı yaz** — şablon dosyanın
> içinde. Atlanırsa sonraki kişi nerede kalındığını bilemez. Claude'a
> **"oturumu kapat"** dersen bunu o yazar (`CLAUDE.md` §5).

---

## Sistem

Uçak ile yer istasyonu **iki ayrı yoldan** konuşur — karıştırması kolay:

```
    LAPTOP (YKİ)                              İHA
┌──────────────────┐                  ┌──────────────────────┐
│ Arayüz  :5173    │                  │ Raspberry Pi 5       │
│ Backend :8000    │                  │  ROS 2 Jazzy         │
│ u-blox F9P (RTK) │                  │  ESP32   ── mesh     │
│                  │                  │  Pixhawk ── PX4 1.16 │
│ base ESP32 ──USB─┼═══ ESP-NOW ══════┤  Here4   ── RTK GPS  │
│                  │  telemetri+komut │                      │
│                  │  + RTCM düzeltme │                      │
│            WiFi ─┼─── SSH, QGC ─────┤                      │
└──────────────────┘                  └──────────────────────┘
```

| Yol | Ne taşır | Uçuş buna bağlı mı |
|---|---|---|
| **ESP-NOW mesh** (radyo) | Telemetri, komut, RTK düzeltmesi | ✅ **evet** — WiFi'siz çalışır |
| **WiFi** | SSH, QGroundControl | ❌ hayır — koparsa uçuş sürer |

Mesh 16 baytlık paketler taşır. Her uçağın ROS ağı kendi içinde kapalıdır
(`ROS_LOCALHOST_ONLY=1`), yani laptoptan `ros2 topic list` ile dronun
konularını göremezsin — SSH ile içine girmen gerekir.

| İHA | agent_id | Konteyner | ROS ns | Durum |
|-----|----------|-----------|--------|-------|
| ylp00 | 1 | `drone1` | `/drone_1` | uçuyor |
| ylp01 | 2 | `drone2` | `/drone_2` | uçuyor |
| ylp02 | 3 | `drone3` | `/drone_3` | uçuyor · **kamera bu uçakta** |

> ⚠️ **İsimdeki sayı bir eksik:** ylp00 → drone**1**. En sık yapılan hata;
> komut yazmadan önce bak. Tam kimlik tablosu: `docs/cihazlar.md`.

---

## Dronlara bağlanmak

Laptop ve dronlar **aynı WiFi'de** olmalı — atölyede `rpissid`, sahada telefon
hotspot'u. Şifreler repoda yok, takım içinde paylaşılıyor.

```bash
./deploy/yki/drone_bul.sh              # menü: bul, seç, bağlan
./deploy/yki/drone_bul.sh --durum      # disk, konteyner, açık bayraklar
./deploy/yki/drone_bul.sh ylp00 'komut'
```

IP'ler her ağda değişir — ezberleme, betiği kullan. Önbellek → mDNS → MAC
taraması sırasıyla dener; sonuncusu her zaman çalışır.

> **Dron ağda ama QGC/YKİ'de görünmüyorsa:** konteyner WiFi hazır olmadan
> kalkmıştır. `./deploy/yki/drone_bul.sh ylp00 'docker restart drone1'` çözer.
> Kalıcı düzeltme `YAPILACAKLAR.md`'de (konteyner recreate maddesi).

---

## Sık kullanılan komutlar

```bash
# HER UÇUŞTAN ÖNCE — saniyeler sürer, ATLANMAZ
python3 src/gcs/gorev_kanit_ucus.py --kuru --harita \
    --senaryo saha --dronelar 1,2,3 --lider 3
#   --kuru   : plan + çarpışma denetimi, HİÇBİR komut gitmez → "SONUÇ: GEÇTİ" şart
#   --harita : /tmp/yelpence_rota.html — uydu görüntüsünde yeşil=rota,
#              mavi=her drone'un İNECEĞİ yer. OPERATÖR GÖZÜYLE DOĞRULAR.

# SAHA GÜNÜ BİR KEZ — uçuş başına DEĞİL (29 Ağu operatör kararı)
./deploy/yki/param_karsilastir.py         # uçaklar aynı ayarda mı
./deploy/yki/drone_bul.sh --durum         # disk, konteyner, bayraklar, Pi ayakta mı

# Uçuş ayarları — hız, ivme, formasyon aralığı, açılar (TEK KAYNAK)
python3 src/gcs/ucus_ayarlari.py          # çözümle + tutarlılık denetle
python3 src/gcs/ucus_ayarlari.py --px4    # uçaklara yazılacak parametreler
python3 src/gcs/ucus_ayarlari.py --kabuk  # baslat.sh için env satırları

# Kodu dronlara dağıt (rsync + konteynerde derleme + sürüm kaydı)
./deploy/rpi/dagit.sh                          # hepsi, altı paket birden

# ⚡ HIZLI DÖNGÜ — bir Python satırı değiştiğinde (29 Ağustos)
#    Tam docker restart ~50 sn sabit sleep + MAVROS/PX4/RTK yeniden kilit
#    istiyordu. Değişen tek düğümse ikisi de gereksiz:
./deploy/rpi/dagit.sh --paket swarm_core ylp00         # 1) yalnız o paketi derle
./deploy/yki/drone_bul.sh ylp00 \
    'docker exec -d drone1 bash /ws/baslat.sh --yalniz ca'   # 2) yalnız o düğüm
#    --yalniz mavros/px4_bridge/agent_fsm/esp32_bridge/uçuş kaydına DOKUNMAZ.
#    🔴 UÇUŞ SIRASINDA KULLANMA — düğüm saniyelerce yok olur.
#    ⚠️ Bir .msg/.srv değiştiyse --paket kullanma, hepsini derle.

# Yer istasyonu
src/gcs/yki_baslat.sh · src/gcs/yki_durdur.sh
```

🔴 **Uçuş öncesi zorunlu SEKİZ madde:** `CLAUDE.md` §9. Harita kontrolü ve
iniş yeri güvenliği **devredilemez** — kod bina/ağaç/tel göremez.

🔴 **En küçük yeterli manevra:** bir düğümü sınamak için soruyu cevaplayan
**en kısa** uçuş yapılır. Git-gel yetiyorsa git-gel, tek formasyon yetiyorsa
tek formasyon. Uzun uçuş bir değer değil, bir **risk**. Ayrıntı: `PLAN.md` §5.

---

## Depo düzeni

```
src/swarm_control/        px4_bridge, esp32_bridge, mesh köprüsü
src/swarm_core/           formasyon, konsensüs, kaçınma, manevra, hassas iniş
src/swarm_state_machine/  ajan / sürü / görev durum makineleri
src/swarm_missions/       Görev 1 orkestratörü
src/swarm_perception/     kamera, QR, renkli bölge
src/swarm_interfaces/     ROS mesaj sözleşmesi
src/gcs/                  yer istasyonu + saha ölçüm araçları
deploy/rpi/               dronlara dağıtım (baslat.sh, dagit.sh, teshis/)
deploy/yki/               yer istasyonu araçları
firmware/esp32_mesh/      ESP-NOW mesh firmware
docs/                     belgeler — PLAN.md ile başla
```

---

## Kurulum

**Simülasyon kullanılmıyor.** Geliştirme ve test doğrudan sahada, gerçek
uçaklarla yapılıyor.

| Ne | Nerede |
|---|---|
| Drona kod dağıtımı | `deploy/rpi/README.md` |
| Yeni Pi hazırlama | `deploy/rpi/pi_hazirla.sh` |
| Erişim, IP, MAC, portlar, QGC | `docs/cihazlar.md` |
| Yer istasyonu | ROS 2 Jazzy + `colcon build` + base ESP32'nin USB'si |

**Ekran görüntüsü:** `ss/` klasörüne at, sohbette söyle (`ss/README.md`).

## Lisans

[`LICENSE`](LICENSE)
