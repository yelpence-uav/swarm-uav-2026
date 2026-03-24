# Yelpençe Sürü İHA Projesi - TEKNOFEST 2026

> Bu depo, Yelpençe takımının TEKNOFEST 2026 Sürü İHA Yarışması için geliştirdiği tüm yazılım mimarisini, algoritma setlerini ve dokümantasyon süreçlerini barındıran ana merkezdir. Proje; dinamik sürü formasyonları, otonom görev icrası ve gelişmiş yer kontrol istasyonu entegrasyonuna odaklanmaktadır. 

****İLK ÇALIŞTIRMA İÇİN YOL HARİTASI EN AŞAĞIDA BULUNMAKTADIR.****

# Proje Dizin Yapısı ve Dosya Açıklamaları

Yelpençe 2026 Sürü İHA projesi, modüler bir ROS 2 altyapısı ve simülasyon ortamı kullanmaktadır. Projemizin ana dizin ve dosya yapısı aşağıdaki gibidir:

```text
yelpence-2026-swarm/
├── .github/
│   └── workflows/
│       └── ros2_build.yml           # GitHub Actions için ROS 2 otomatik test ve CI/CD yapılandırması
│-------------------------------------------------------------------------------------------------------------------------------------
├── config/                          # İHA uçuş parametreleri ve sistem konfigürasyonları için ayrılmış dizin
│-------------------------------------------------------------------------------------------------------------------------------------
├── docker/                          # Geliştirme ve Gazebo simülasyon ortamı için Docker dosyaları
│   ├── Dockerfile                   # ROS 2 Jazzy, Gazebo Harmonic ve sistem bağımlılıklarını içeren imaj tanımı
│   ├── build.bash                   # Kullanıcı izinlerini (UID/GID) otomatik ayarlayarak imajı inşa eden betik
│   ├── docker-compose-amd.yml       # AMD/Intel grafik birimleri için donanım hızlandırmalı Compose yapılandırması
│   ├── docker-compose.yml           # Nvidia ekran kartları için GPU destekli Compose yapılandırması
│   └── entrypoint.sh                # Konteyner başlatıldığında ROS çalışma alanını aktif eden başlangıç betiği
│-------------------------------------------------------------------------------------------------------------------------------------
├── docs/                            # Şartname, teknik raporlar ve detaylı proje dokümantasyonu dizini
│-------------------------------------------------------------------------------------------------------------------------------------
├── scripts/                         # Simülasyon dünyası üretimi ve sistem başlatma betikleri
│   ├── generate_task1_world.py      # Görev 1 (Dinamik Sürü) için sahada rastgele QR ve iniş pedleri üreten betik
│   ├── generate_task2_worlds.py     # Görev 2 için formasyon, navigasyon ve çarpışmadan kaçınma dünyalarını üreten betik
│   ├── install.sh                   # Tüm kurulumları tamamlayıp ortamı hazır hale getiren betik (NVIDIA)
│   ├── install-amd.sh               # Tüm kurulumları tamamlayıp ortamı hazır hale getiren betik (AMD/INTEL)
│   ├── start-docker.sh              # Kullanıcının GPU seçimine göre Docker'ı ayağa kaldıran ve içine girilmesini sağlayan betik
│   ├── setup.sh                      # Konteyner içinde PX4, QGC ve tüm bağımlılıkları kuran ana kurulum betiği
│   └── start_swarm.sh               # Tüm sistemleri (Gazebo, PX4, Chaos, GUI) tek seferde başlatan betik
│-------------------------------------------------------------------------------------------------------------------------------------
├── sim/                             # Gazebo Harmonic simülasyon ortamları ve 3D modeller
│   └── worlds/
│       ├── base_world.sdf           # Ortak futbol sahası ve temel fizik/ışık ortamını barındıran şablon dünya
│       ├── task1_dynamic_swarm.sdf  # Üretilmiş Görev 1 simülasyon dünyası dosyası
│       ├── task2_collision.sdf      # Üretilmiş Görev 2 (Çarpışma) simülasyon dünyası dosyası
│       ├── task2_formation.sdf      # Üretilmiş Görev 2 (Formasyon) simülasyon dünyası dosyası
│       └── task2_navigation.sdf     # Üretilmiş Görev 2 (Navigasyon/İniş) simülasyon dünyası dosyası
│-------------------------------------------------------------------------------------------------------------------------------------
├── src/                             # ROS 2 paketlerinin ve kaynak kodların bulunduğu ana çalışma alanı
│   ├── gcs/                         # Yer Kontrol İstasyonu (GCS) paketi
│   │   ├── gcs/web_gui_server.py    # Flask-SocketIO tabanlı gelişmiş web arayüzü ve telemetri köprüsü
│   │   ├── package.xml              # GCS paketi ROS 2 bağımlılık tanımları
│   │   └── setup.py                 # Paket kurulum ve çalıştırılabilir komut tanımları
│   ├── network/                     # İHA'lar arası iletişim ve telemetri trafiğini yöneten paket
│   │   ├── network/network_manager.py # Sürü içi ve GCS haberleşme altyapısını yöneten ROS 2 düğümü
│   │   ├── package.xml              # Ağ paketi bağımlılık tanımları
│   │   └── setup.py                 # Paket kurulum ve komut tanımları
│   ├── swarm/                       # Sürü zekası, formasyon kontrolü ve otonom karar mekanizmaları paketi
│   │   ├── swarm/swarm_launch.py    # Tüm sürü sistemini (Gazebo, PX4, Lidar, Agent) orkestre eden ana başlatıcı
│   │   ├── swarm/lidar_relay.py     # Gazebo LiDAR verilerini PX4 DistanceSensor formatına çeviren köprü
│   │   ├── swarm/chaos_network.py   # Ağ gecikmesi ve paket kaybı simüle eden test düğümü
│   │   ├── package.xml              # Sürü paketi bağımlılık tanımları
│   │   └── setup.py                 # Paket kurulum ve komut tanımları
│   ├── vision/                      # Kamera verisi, QR tespiti ve hassas konumlandırma paketi
│   │   ├── vision/qr_detector.py    # Görüntü işleyen ve elde edilen QRData mesajlarını yayınlayan ROS 2 düğümü
│   │   ├── package.xml              # Görüntü işleme paketi bağımlılık tanımları
│   │   └── setup.py                 # Paket kurulum ve komut tanımları
│   └── yelpence_msgs/               # Sürü sistemine özel tanımlanmış veri yapıları (ROS 2 mesaj tipleri)
│       ├── msg/
│       │   ├── FormationCommand.msg # Sürü dizilim komutlarını taşıyan mesaj tipi (formasyon tipi, irtifa, aralık)
│       │   ├── QRData.msg           # Görüntüden çözümlenen QR içeriğini ve hedef bilgileri taşıyan mesaj tipi
│       │   └── SwarmState.msg       # Her bir İHA'nın konum, batarya ve görev durumunu taşıyan telemetri mesaj tipi
│       ├── CMakeLists.txt           # C++ tabanlı mesaj derleme konfigürasyonu
│       └── package.xml              # Mesaj paketi bağımlılık tanımları
│-------------------------------------------------------------------------------------------------------------------------------------
├── tests/                           # Yazılım bileşenleri için birim (unit) ve entegrasyon testlerinin ekleneceği dizin
├── .gitattributes                   # Git LFS ile (.world, .mp4, .onnx) büyük simülasyon dosyalarını takip eden konfigürasyon
├── .gitignore                       # Derleme çıktıları, IDE klasörleri ve önbellek dosyalarının Git'e eklenmesini engelleyen yapılandırma
├── LICENSE                          # Yazılımın kullanım haklarını belirleyen Unlicense (Kamu Malı) sözleşmesi
└── README.md                        # Projenin amacını, mimarisini ve Docker kurulum adımlarını içeren ana bilgi dokümanı
```

# Kurulum ve Başlangıç

## 1. Git LFS (Large File Storage) Yapılandırması

Ağır veri setleri ve simülasyon modelleri LFS ile takip edilmektedir. Repoyu kopyalamadan önce LFS'yi bilgisayarınıza kurmanız zorunludur:

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

## 3. Geliştirme Ortamı Kurulumu
Projemiz Docker konteynerleri üzerinde çalışmaktadır. Aşağıdaki betikleri uygulayarak kurulumu tamamlayınız. Bu aşamanın sonunda; Docker kurulur, Nvidia Toolkit kurulumu ve ayarları yapılır, Docker kullanıcı grubu ayarları yapılır, dosya izinleri verilir ve Docker imajı inşa edilir.

```bash
# Proje dosyasındaki sciprits/ dizinine gidin
cd scripts/

# Kurulum betiğine çalıştırma izni verin
chmod +x install.sh # NVIDIA GPU
chmod +x install-amd.sh # AMD/INTEL GPU

# Kurulum betiğini çalıştırın
./install.sh # NVIDIA GPU
./install-amd.sh # AMD/INTEL GPU
```

> [!NOTE]
> Eğer kullanıcı ID'niz standart dışıysa (1000 değilse), kurulumdan önce `export USER_UID=$(id -u)` ve `export USER_GID=$(id -g)` komutlarını çalıştırınız.

## 4. Sanal Ortamı Başlatma ve Ortama Giriş
Kurulum bittikten sonra aşağıdaki betiği kullanarak sistemi ayağa kaldırın. Docker konteyneri aktif hale gelir ve betik sonunda oluşan konteynerin içine girersiniz. Kurulum sırasında yönergeleri takip edin.

```Bash
# scripts/ dizininde olduğunuza emin olun
chmod +x start-docker.sh

# Betiği çalıştırın
./start-docker.sh
```

> Bundan sonra konteyneri çalıştırmak ve içine girmek için her zaman "./start-docker.sh" betiğini kullanabilirsiniz. Çalıştırma izinlerinin bir kere verilmesi yeterlidir.

## 5. PX4 ve Mesaj Altyapısının Kurulması (Konteyner İçi İlk Kurulum)
Konteynerin içine girdikten sonra, PX4 uçuş kodlarını ve ROS 2 mesaj setlerini kurmanız gerekir. Bu işlem bir kereye mahsustur:

1. Konteyner içinde scripts dizinine gidin: `cd scripts`
2. Kurulum betiğini çalıştırın:
```bash
chmod +x setup.sh
./setup.sh
```

> **NOT:** Bu işlem internet hızınıza bağlı olarak 15-20 dakika sürebilir. Kurulum tamamlandığında `ros2_ws` dizininiz otomatik olarak derlenecektir.

## 6. Sürü Simülasyonunu Başlatma (Hızlı Başlangıç)

Simülasyonu, tüm alt bileşenleriyle (DDS, PX4, Kaos Ağı, GUI) tek bir komutla başlatabilirsiniz:

1. Konteyner içinde `scripts` dizinine gidin: `cd scripts`
2. Ana başlatıcıyı çalıştırın:
```bash
./start_swarm.sh
```
3. Karşınıza gelen menüden **Dünya Dosyası** (1-5) ve **İHA Sayısı** seçin.

> **NOT:** Sistem arka planda Web GUI sunucusunu (`localhost:5000`) ve gerçekçi ağ gecikmelerini taklit eden Kaos Ağı modülünü otomatik olarak başlatacaktır.

## 7. Çalışmayı Durdurma
İşiniz bittiğinde bilgisayarınızı yormaması için sistemi kapatın:

```bash
# Host terminalinde docker dizinine gidin:
cd ../docker

# Nvidia Kullanıcıları:
docker compose down

# AMD Kullanıcıları:
docker compose -f docker-compose-amd.yml down

```

> docker ps komutunu kullanarak hali hazırda aktif olan konteynerleri listeleyebilirsiniz. Bu listede bulunanlar kaynak tüketirler.

## 8. Simülasyon Ortamının Kullanımı
Aşağıdaki python scriptleri base_world.sdf dünyasını şablon alarak task1_dynamic_swarm.sdf, task2_collision.sdf, task2_formation.sdf, task2_navigation.sdf dünyalarını inşa eder.

```python
python3 scripts/generate_task1_world.py     # task1_dynamic_swarm.sdf
python3 scripts/generate_task2_worlds.py    # task2 dünyaları
```

> DİKKAT! Dünyalar üzerinde yaptığınız değişiklikler bu komutların çalışması ile kaybolabilir.

İstediğiniz bir dünyayı Gazebo ile başlatmak için aşağıdaki komutu kullanabilirsiniz.

```bash
gz sim /sim/worlds/[DÜNYANIN ADI]
```

## 9. Yazılım Mimarisi ve ROS 2 Altyapısı

### 9.1. Amaç ve Mantık
ROS 2 projelerinde kodların derlenebilmesi ve sistem tarafından tanınabilmesi için belirli bir paket yapısına sahip olması gerekir. Projemizin başlangıç aşamasında oluşturulan hiyerarşik klasörler, içlerine `package.xml` ve `setup.py` / `CMakeLists.txt` dosyaları eklenerek resmi birer ROS 2 yazılım modülüne dönüştürülmüştür. 

Bu sayede modüler, görev dağılımına uygun ve birindeki hata diğerinin çalışmasını engellemeyen bir çalışma alanı altyapısı kurulmuştur.

Ayrıca, sürü İHA'lar arasındaki yüksek frekanslı haberleşme trafiğini en düşük gecikmeyle ve en stabil şekilde yönetebilmek adına, ROS 2'nin varsayılan haberleşme protokolü yerine çoklu otonom sistemler için endüstri standardı olan **FastDDS (rmw_fastrtps_cpp)** altyapısı sisteme entegre edilmiş ve Docker ortamımıza kalıcı olarak dahil edilmiştir.

### 7.2. Paket Mimarisi ve Görev Dağılımı
Projemizin `src` dizini altındaki yazılım modülleri ve görev tanımları şu şekildedir:

* **`swarm`:** Sürü İHA formasyon kontrolü, otonom karar alma mekanizmaları ve dinamik görev paylaşımı algoritmalarını barındırır.
* **`vision`:** Kamera verilerinin işlenmesi, sahada yer alan QR kodların okunup çözümlenmesi ve hedef alanlara hassas iniş görevlerini yönetir.
* **`network`:** İHA'ların kendi aralarındaki ve Yer İstasyonu ile olan ağ haberleşmesinin mantıksal döngülerini kontrol eder.
* **`gcs`:** Yer Kontrol İstasyonu kullanıcı arayüzünü, telemetri takibini ve yarışmadaki "Yarı Otonom Sürü Kontrolü" görevi için joystick/kumanda entegrasyonunu içerir.
* **`yelpence_msgs`**: Sürü algoritmalarının ihtiyaç duyduğu özel ROS 2 mesaj tiplerini barındırır. Şartnamede geçen görevlerin icrası için İHA'ların kimlik ve konumlarını bildiren SwarmState, okunan şifreleri ileten QRData ve sürüye yeni dizilim komutları veren FormationCommand mesajlarını içerir.

# 8. CI/CD ve Otomatik Test Süreçleri
Yelpençe takımı, kod kalitesini standartlaştırmak ve sisteme hatalı modüllerin dahil edilmesini önlemek amacıyla GitHub Actions destekli Sürekli Entegrasyon (CI) mimarisi kullanmaktadır.

Projeye gönderilen her yeni kod (push veya pull_request işlemi) otomatik olarak aşağıdaki denetimlerden geçer:

- Docker Image Build Test: Eklenen yeni bir kodun veya kütüphanenin, takımın ortak Docker imajının derlenmesini bozup bozmadığı test edilir.
- ROS 2 Build Test: Tüm çalışma alanı (colcon build) Ubuntu 24.04 ve ROS 2 Jazzy standartlarında sıfırdan derlenerek paket çakışmaları denetlenir.
- Birim Testler (Unit Tests): colcon test komutu çalıştırılarak önceden yazılmış özel senaryo testlerinin başarı durumu kontrol edilir.
- Linter ve Stil Denetimleri: Ekip içi tutarlılık için PEP 8 standartları (ament_flake8) ve yorum satırı / dokümantasyon kuralları (ament_pep257) analiz edilir. Kurallara uymayan kodların ana yapıya (main) birleşmesi engellenir.


****************************************************

İLK ÇALIŞTIRMA YOL HARİTASI:
1. NVIDIA GPU için ./scripts/install.sh 
   AMD/INTEL GPU için ./scripts/install-amd.sh
2. ./scripts/start-docker.sh
3. ./scripts/setup.sh
4. ./scripts/start_swarm.sh

SONRAKİ ÇALIŞTIRMALAR
(Kurulum bittikten sonra pc yeniden başlatıldığında 
ya da konteyner kapatılıp açıldığında):
1. ./scripts/start-docker.sh
2. ./scripts/start_swarm.sh

GUİ için localhost:5000 adresine gidiniz.

****************************************************