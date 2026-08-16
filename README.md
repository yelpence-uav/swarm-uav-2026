
**Son güncelleme:** 16 Ağustos 2026

Takım **Yelpençe** · Takım no **752825**

Üç çok rotorlu İHA'nın sürü hâlinde otonom görev yaptığı sistem.
Kararlar uçağın kendi içinde verilir; yer istasyonunun tek işi görevi
başlatmaktır. (Şartname dağıtık algoritma istiyor, merkezi olan eksik puan.)

---

## 🚀 Yeni misin? Şu sırayla oku

| Sıra | Dosya | Ne verir |
|---|---|---|
| 1 | [`docs/PLAN.md`](docs/PLAN.md) | Büyük resim — 10 dakikada tamamı |
| 2 | [`docs/DURUM.md`](docs/DURUM.md) | Şu an ne çalışıyor, ne bozuk, uçakta hangi ayar açık |
| 3 | [`docs/GUNLUK.md`](docs/GUNLUK.md) | Son kişi nerede bıraktı (**en üstteki** kayıt) |
| 4 | [`docs/YAPILACAKLAR.md`](docs/YAPILACAKLAR.md) | Sıradaki iş — 🔴P0 / 🟠P1 / 🟡P2 / ⚪P3 |

Diğer belgeler: `KARARLAR.md` (verilmiş kararlar), `SURU_ENTEGRASYON.md`
(teknik yol haritası), `RPI_ESITLEME.md` (uçaklarda ne var),
`cihazlar.md` (IP, MAC, SSH, portlar).

`docs/arsiv/` geçmiş dönemlere ait — ölçümler ve kaza analizleri değerli,
ama bugünü anlatmaz.

Claude Code kullanıyorsan [`CLAUDE.md`](CLAUDE.md) kendiliğinden okunur.

> **Kalkarken `docs/GUNLUK.md`'ye devir teslim kaydı yaz** — şablon dosyanın
> içinde. Ne yaptın, ne değişti, yarım kalan ne, uçakları hangi hâlde
> bıraktın. Atlanırsa sonraki kişi nerede kalındığını bilemez.

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
| ylp01 | 2 | `drone2` | `/drone_2` | **yerde** — ESC güç hattı onarımı |
| ylp02 | 3 | `drone3` | `/drone_3` | uçuyor |

> ⚠️ **İsimdeki sayı bir eksik:** ylp00 → drone**1**. En sık yapılan hata,
> komut yazmadan önce bak.

---

## Dronlara bağlanmak

Laptop ve dronlar **aynı WiFi'de** olmalı — atölyede `rpissid`, sahada
telefon hotspot'u. Şifreler repoda yok, takım içinde paylaşılıyor.

```bash
./deploy/yki/drone_bul.sh              # menü: bul, seç, bağlan
./deploy/yki/drone_bul.sh --durum      # disk, konteyner, açık bayraklar
./deploy/yki/drone_bul.sh ylp00 'komut'
```
IP'ler her ağda değişir — ezberleme, betiği kullan.
SSH kullanıcıları drone başına ayrı: yelpence00, yelpence02.

Dron ağda ama QGC/YKİ'de görünmüyorsa: konteyner WiFi hazır olmadan
kalkmıştır. ./deploy/yki/drone_bul.sh ylp00 'docker restart drone1' çözer.

Sık kullanılanlar

```bash
# Uçuştan ÖNCE — ikisi de bedava, saniyeler sürer, atlanmaz
./deploy/yki/param_karsilastir.py         # uçaklar aynı ayarda mı
python3 src/gcs/gorev_kanit_ucus.py --kuru --senaryo saha --dronelar 1,3 --lider 3

# Uçuş ayarları — hız, ivme, formasyon aralığı, açılar (TEK KAYNAK)
python3 src/gcs/ucus_ayarlari.py

# Kodu dronlara dağıt (rsync + konteynerde derleme + sürüm kaydı)
./deploy/rpi/dagit.sh

# Yer istasyonu
src/gcs/yki_baslat.sh · src/gcs/yki_durdur.sh
```
Depo düzeni

```
src/swarm_control/        px4_bridge, esp32_bridge, kaçınma, mesh köprüsü
src/swarm_core/           formasyon, konsensüs, manevra, hassas iniş, rota
src/swarm_state_machine/  ajan / sürü / görev durum makineleri
src/swarm_missions/       Görev 1 orkestratörü
src/swarm_perception/     kamera, QR, renkli bölge, komşu füzyonu
src/swarm_interfaces/     ROS mesaj sözleşmesi
src/gcs/                  yer istasyonu + saha ölçüm araçları
deploy/rpi/               dronlara dağıtım (baslat.sh, dagit.sh)
deploy/yki/               yer istasyonu araçları
firmware/esp32_mesh/      ESP-NOW mesh firmware
docs/                     belgeler — PLAN.md ile başla
```
Kurulum
Simülasyon kullanılmıyor. Geliştirme ve test doğrudan sahada,
gerçek uçaklarla yapılıyor.

Ne	Nerede
Drona kod dağıtımı	deploy/rpi/README.md
Yeni Pi hazırlama	deploy/rpi/pi_hazirla.sh
Erişim, IP, MAC, portlar, QGC	docs/cihazlar.md
Yer istasyonu	ROS 2 Jazzy + colcon build + base ESP32'nin USB'si gerekir
Lisans
LICENSE
READMEEOF
