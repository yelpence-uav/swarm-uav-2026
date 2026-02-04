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

# Yazilim Ekibi Görev Dagilimi

Yelpence ekibinin yazilim gelistirme süreçleri, asagidaki uzmanlik alanlarina göre dagitilmistir:

## manager
**Osman (Kaptan ve Sistem Mimari)**
* Projenin genel yazilim mimarisinin tasarlanmasi ve ROS2 tabanli SITL (Software-in-the-Loop) simülasyon ortamlarinin kurgulanmasi.
* GitHub organizasyon yönetimi, kod standartlarinin belirlenmesi ve Pull Request (PR) süreçlerinin denetlenmesi.
* Docker konteynerizasyon stratejilerinin olusturulmasi ve CI/CD süreçlerinin takibi.
* Görev Durum Makinesi (Mission State Machine) yapisinin üst seviye kontrolü.

## gcs-developer
**Muhammed (YKİ Geliştiricisi)**
* Python ve Qt kütüphaneleri kullanilarak özgün Yer Kontrol Istasyonu (YKI) arayüzünün gelistirilmesi.
* Telemetri verilerinin gerçek zamanli olarak görsellestirilmesi ve veri kaydi mekanizmalarinin kurulmasi.
* Sürünün tek bir merkezden (joystick veya arayüz üzerinden) yönlendirilmesini saglayan HMI (Human-Machine Interface) biriminin kodlanmasi.

## network-developer
**Eyüp (Haberleşme Sorumlusu)**
* İHA'lar arasi (V2V) ve İHA-Yer Istasyonu arasi (V2G) haberlesme protokollerinin (MAVLink, ROS2 DDS) optimizasyonu.
* Ag topolojisinin yönetimi, paket kayiplarinin minimize edilmesi ve haberlesme güvenliginin saglanmasi.
* Telemetri modülleri ve Companion Computer arasindaki veri akisinin yazilimsal denetimi.

## swarm-developer
**Berk ve Emirhan (Sürü Algoritmaları Geliştiricisi)**
* **Sürü Algoritmalari:** Dinamik formasyon kontrolü (V, Okbasi, Çizgi), çarpisma önleme sistemleri ve sürüye otonom birey ekleme/çıkarma mantiginin gelistirilmesi.
* **Bilgisayar Görü:** OpenCV ve derin ögrenme tabanli QR kod tespiti, hedef takibi ve renkli alan tanima algoritmalarinin kodlanmasi.
* **Otonom Görev Yönetimi:** Hassas inis sistemleri ve görüntü isleme hattindan (pipeline) gelen verilerin sürünün karar mekanizmasina entegre edilmesi.

---

# Dizin Yapisi

```text
yelpence-2026-swarm/
├── docs/                   # Şartname, raporlar ve teknik dokümantasyon
├── src/                    # Kaynak kodların ana dizini
│   ├── yelpence_gcs/       # Yer Kontrol istasyonu modülleri
│   ├── yelpence_swarm/     # Sürü yönetim ve formasyon mantığı
│   ├── yelpence_vision/    # QR kod ve görüntü işleme algoritmalari
│   ├── yelpence_network/   # MAVLink ve haberleşme köprüleri
│   └── yelpence_msgs/      # Özel ROS2 mesaj tanımları
├── sim/                    # Gazebo dünyaları ve IHA modelleri
├── config/                 # Parametre ve uçuş konfigürasyonları
├── docker/                 # Geliştirme ortamı
├── scripts/                # Kurulum ve çarlıştırma yardımcı betikleri
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

