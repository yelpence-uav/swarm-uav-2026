# Yelpençe Sürü İHA Projesi - TEKNOFEST 2026

Bu depo, Yelpençe takımının TEKNOFEST 2026 Sürü İHA Yarışması için geliştirdiği tüm yazılım mimarisini, algoritma setlerini ve dokümantasyon süreçlerini barındıran ana merkezdir. Proje; dinamik sürü formasyonları, otonom görev icrası ve gelişmiş yer kontrol istasyonu entegrasyonuna odaklanmaktadır.

---

# Organizasyon ve Takım Yapısı

Proje, GitHub üzerinde fonksiyonel sorumluluklara bölünmüş 4 ana takım tarafından yürütülmektedir:

- **manager:** Proje yönetimi, raporlama ve sistem mimarisi.
- **gcs-developer:** Yer Kontrol İstasyonu (GCS) ve kullanıcı arayüzü geliştirme.
- **network-developer:** V2V/V2G haberleşme protokolleri ve ağ güvenliği.
- **swarm-developer:** Sürü algoritmaları, otonom karar mekanizmaları ve bilgisayar görü.

---

# Dizin Yapisi

```text
yelpence-2026-swarm/
├── docs/                   # Sartname, raporlar ve teknik dokümantasyon
├── src/                    # Kaynak kodlarin ana dizini
│   ├── yelpence_gcs/       # Yer Kontrol Istasyonu modülleri (Muhammed)
│   ├── yelpence_swarm/     # Sürü yönetim ve formasyon mantigi (Emirhan & Berk)
│   ├── yelpence_vision/    # QR kod ve görüntü isleme algoritmalari (Berk)
│   ├── yelpence_network/   # MAVLink ve haberlesme köprüleri (Eyüp)
│   └── yelpence_msgs/      # Özel ROS2 mesaj tanimlari (Ortak)
├── sim/                    # Gazebo dünyalari ve IHA modelleri (SITL)
├── config/                 # Parametre ve uçus konfigürasyonlari
├── docker/                 # Gelistirme ortami (Dockerfile ve Compose)
├── scripts/                # Kurulum ve çalistirma yardimci betikleri
└── tests/                  # Birim ve entegrasyon testleri
```
---

# Kurulum ve Başlangıç

## 1. Git LFS (Large File Storage) Yapılandırması

Bu projede ağır veri setleri ve simülasyon modelleri LFS ile takip edilmektedir. Repoyu kopyalamadan önce LFS'yi bilgisayarınıza kurmanız zorunludur:

```bash
# Ubuntu için:
sudo apt-get install git-lfs

# LFS desteğini aktifleştirin:
git lfs install
```

## 2. Repoyu Kopyalama

```bash
git clone https://github.com/yelpence-uav/yelpence-2026-swarm.git
```

