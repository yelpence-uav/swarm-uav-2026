# Yelpençe — TEKNOFEST 2026 Sürü İHA

Takım **Yelpençe** · Takım no **752825**

Üç çok rotorlu İHA'nın sürü hâlinde otonom görev yaptığı sistem: uçuş
yazılımı, mesh haberleşme, RTK konumlandırma ve yer kontrol istasyonu.

---

## 🚀 Buraya yeni mi geldin?

**[`docs/PLAN.md`](docs/PLAN.md)** ile başla. 10 dakikada ne yaptığımızı,
nerede olduğumuzu ve yolun tamamını anlatıyor.

Sonra oturmadan önce üç dosya:

| | |
|---|---|
| [`docs/DURUM.md`](docs/DURUM.md) | Şu an ne çalışıyor, ne bozuk |
| [`docs/GUNLUK.md`](docs/GUNLUK.md) | Son kişi ne yaptı, nerede bıraktı |
| [`docs/YAPILACAKLAR.md`](docs/YAPILACAKLAR.md) | Sıradaki iş |

Claude Code ile çalışıyorsan [`CLAUDE.md`](CLAUDE.md) **kendiliğinden**
okunuyor — bir şey söylemene gerek yok.

**Oturumdan kalkarken Claude'a "oturumu kapat" de.** Devir teslim kaydını
o yazar. Bu adım atlanırsa sonraki kişi nerede kalındığını bilemez.

---

## Sistem

```
YKİ (dizüstü)                    Her İHA
┌──────────────┐                 ┌────────────────────────────┐
│ Arayüz :5173 │                 │ Raspberry Pi 5             │
│ Backend :8000│                 │  ROS 2 Jazzy (Docker)      │
│ RTK bazı     │◄──ESP-NOW mesh─►│  ESP32  ─ mesh             │
└──────────────┘                 │  Pixhawk FMUv3 ─ PX4 1.16  │
                                 │  Here4 GPS (RTK)           │
                                 └────────────────────────────┘
```

| İHA | agent_id | Konteyner | ROS ns | Durum |
|-----|----------|-----------|--------|-------|
| ylp00 | 1 | `drone1` | `/drone_1` | uçuyor |
| ylp01 | 2 | `drone2` | `/drone_2` | **yerde** (onarımda) |
| ylp02 | 3 | `drone3` | `/drone_3` | uçuyor |

> **İsimdeki sayı bir eksik:** ylp00 → drone**1**. Sürekli hata kaynağı,
> komut yazmadan önce bak.

---

## Sık kullanılanlar

```bash
# Drone bul ve bağlan — IP her ağda değişiyor, ezberleme
./deploy/yki/drone_bul.sh                 # menü: seç, bağlan
./deploy/yki/drone_bul.sh --durum         # disk, konteyner, bayraklar
./deploy/yki/drone_bul.sh ylp00 'komut'

# Uçuştan ÖNCE (ikisi de bedava, saniyeler sürer)
./deploy/yki/param_karsilastir.py         # uçaklar aynı ayarda mı
python3 src/gcs/gorev_kanit_ucus.py --kuru --senaryo saha --dronelar 1,3 --lider 3

# Uçuş ayarları — hız, ivme, formasyon aralığı, açılar (TEK KAYNAK)
python3 src/gcs/ucus_ayarlari.py

# YKİ
src/gcs/yki_baslat.sh · src/gcs/yki_durdur.sh
```

---

## Depo düzeni

```
src/swarm_control/        px4_bridge, esp32_bridge, kaçınma
src/swarm_core/           formasyon, konsensüs, manevra, hassas iniş
src/swarm_state_machine/  ajan/sürü/görev durum makineleri
src/swarm_missions/       görev orkestratörü
src/swarm_perception/     kamera, görü, komşu füzyonu
src/swarm_interfaces/     ROS mesaj sözleşmesi
src/gcs/                  yer kontrol istasyonu + saha araçları
deploy/rpi/               drone'a dağıtım (baslat.sh, dagit.sh)
deploy/yki/               yer istasyonu araçları
firmware/esp32_mesh/      ESP-NOW mesh firmware
docs/                     belgeler — PLAN.md ile başla
ss/                       ekran görüntüsü panosu
```

---

## Kurulum

**Simülasyon kullanılmıyor.** Geliştirme ve test doğrudan sahada, gerçek
uçaklarla yapılıyor.

- **Drone'a dağıtım:** `deploy/rpi/README.md`
- **Yeni Pi hazırlama:** `deploy/rpi/pi_hazirla.sh`
- **Erişim, IP, MAC, portlar:** `docs/cihazlar.md`

> `docker/` altındaki Gazebo/SITL kurulumu ve `sim/` klasörü **simülasyon
> dönemine ait**. Artık kullanılmıyor — bkz. `docs/COP_TEMIZLIK.md`.

---

## Lisans

[LICENSE](LICENSE)
