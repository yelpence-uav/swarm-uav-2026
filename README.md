# Yelpençe Sürü İHA Projesi - TEKNOFEST 2026

Bu depo, Yelpençe takımının TEKNOFEST 2026 Sürü İHA Yarışması için geliştirdiği tüm yazılım mimarisini, algoritma setlerini ve dokümantasyon süreçlerini barındıran ana merkezdir. Proje; dinamik sürü formasyonları, otonom görev icrası ve gelişmiş yer kontrol istasyonu entegrasyonuna odaklanmaktadır.

---

# Takım Yapısı ve Görev Dagilimi

Yelpençe ekibinin yazılım geliştirme süreçleri, aşağıdaki uzmanlık alanlarına göre dağıtılmıştır:

## **Osman Çevik (manager)**
Osman, projenin yazılım mimarisini uçtan uca tasarlayan ve sürünün dijital ikizini (simülasyon) yöneten stratejik liderdir. Fiziksel donanım montajından ziyade, sistemin "nasıl çalışması gerektiğine" dair kuralları koyan ve bu kuralların koda dökülmesini sağlayan yönetici rolündedir.

1. **SITL ve Simülasyon Yönetimi**
* **Dijital İkiz Kurulumu:** Yarışma şartnamesindeki görevlerin tamamının test edilebileceği ROS tabanlı bir simülasyon ortamı inşa etmek.
* **Algoritma Doğrulama:** Emirhan ve Berk’in yazdığı kodları gerçek İHA’lara yüklemeden önce simülasyonda stres testine sokmak ve hata paylarını raporlamak.
* **Senaryo Testleri:** Yarışma sahasındaki olası aksilikleri (bir İHA'nın düşmesi, sinyal kesilmesi vb.) simüle ederek "Fail-Safe" algoritmalarını denetlemek.

2. **DevOps ve Yazılım Standartları**
* **Konteynerizasyon:** Tüm geliştirme ortamını Docker imajları haline getirerek; Berk, Emirhan ve Muhammed’in aynı kütüphane versiyonlarıyla çalışmasını sağlamak. Sahadaki RPi'lara tek komutla hatasız kurulum yapılmasını garanti etmek.
* **Versiyon Kontrol Yönetimi:** Takımın ana kod deposunu yönetmek. Kod incelemeleri yaparak standart dışı veya hatalı kodun ana sisteme dahil edilmesini engellemek.
* **CI/CD Süreçleri:** Kod GitHub'a yüklendiğinde otomatik testlerin çalışmasını sağlayacak bir yapı kurgulamak.




**Muhammed (gcs-developer)**
* Python ve Qt kütüphaneleri kullanilarak özgün Yer Kontrol Istasyonu (YKI) arayüzünün gelistirilmesi.
* Telemetri verilerinin gerçek zamanli olarak görsellestirilmesi ve veri kaydi mekanizmalarinin kurulmasi.
* Sürünün tek bir merkezden (joystick veya arayüz üzerinden) yönlendirilmesini saglayan HMI (Human-Machine Interface) biriminin kodlanmasi.

**Eyüp (network-developer)**
* İHA'lar arasi (V2V) ve İHA-Yer Istasyonu arasi (V2G) haberlesme protokollerinin (MAVLink, ROS2 DDS) optimizasyonu.
* Ag topolojisinin yönetimi, paket kayiplarinin minimize edilmesi ve haberlesme güvenliginin saglanmasi.
* Telemetri modülleri ve Companion Computer arasindaki veri akisinin yazilimsal denetimi.

**Berk ve Emirhan (swarm-developer)**
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
