# Architecture Overview
Bu doküman, geliştiricilerin kod tabanının mimarisini hızlı ve kapsamlı bir şekilde anlamalarını sağlamak, ilk günden itibaren projede verimli bir şekilde gezinmeyi ve etkili katkıda bulunmayı mümkün kılmak için tasarlanmış kritik ve sürekli güncellenen bir rehber görevi görür. Kod tabanı ve sistem geliştikçe bu dokümanın güncel tutulması esastır.

Ayrıca bu doküman, Yelpençe Sürü İHA projesinin yazılım mimarisini, dizin hiyerarşisini ve her bir bileşenin sistem içerisindeki operasyonel görevlerini detaylandırmaktadır. Projemiz; ROS 2 Jazzy, Eclipse CycloneDDS ve ESP-NOW protokolleri üzerinde koşan hiyerarşik ve dağıtık bir yapıya sahiptir.

## 1. Project Structure
Bu bölüm, projenin dizin ve dosya yapısının mimari katmanlara veya temel işlevsel alanlara göre kategorize edilmiş üst düzey bir genel bakışını sunar. Kod tabanında hızlıca gezinmek, ilgili dosyaları bulmak, genel organizasyonu ve sorumlulukların ayrımını anlamak için kritik öneme sahiptir.

```
yelpence-2026-swarm/
│
├── .github/workflows/                        # Sürekli entegrasyon (CI) iş akışları; ROS 2 derleme testleri, Docker imaj doğrulama ve Python Bandit statik güvenlik analizleri.
│
├── docker/                                   # Konteynerleştirilmiş geliştirme ve dağıtım ortamı yapılandırmaları.
│   ├── patches/                              # PX4 Autopilot kaynak koduna uygulanan projeye özel performans ve kararlılık yamaları.
│   └── rpi/                                  # Raspberry Pi 5 görev bilgisayarları için optimize edilmiş hazır Dockerfile yapılandırması ve kurulum talimatları.
│
├── config/                                   # Yazılım kodunu değiştirmeden sistem kararlılığını ve parametrelerini yöneten YAML konfigürasyon dosyaları.
│   ├── swarm_params.yaml                     # Sürü ortak parametreleri; İHA benzersiz kimlik listesi, takım ID, varsayılan irtifa ve emniyet mesafeleri.
│   ├── formations.yaml                       # Ok Başı, V ve Çizgi formasyon geometrileri için İHA'ların göreli ofset koordinat matrisleri.
│   └── competition_overrides.yaml            # Yarışma günü hakem heyetinden gelebilecek dinamik kural ve parametre güncellemelerini tek bir dosyadan geçersiz kılma aracı.
│
├── firmware/                                 # Gömülü sistemler ve mikrodenetleyiciler için geliştirilen donanım yazılımları.
│   └── esp32_mesh/                           # İHA'lar ve Yer Kontrol İstasyonu üzerindeki ESP32 modüllerine yüklenen, ESP-NOW tabanlı örgüsel haberleşme yazılımı.
│
├── gcs/                                      # Yer Kontrol İstasyonu kullanıcı arayüzü ve telemetri veri işleme kaynak kodları.
│
├── scripts/                                  # Simülasyon ve gerçek donanım ortamını tek tuşla başlatan betikler.
│   ├── launch_swarm.py                       # Yazılımsal simülasyon (SITL) ortamı başlatıcısı; Gazebo Harmonic, PX4 SITL ve tüm ROS 2 düğümlerini entegre çalıştırır.
│   └── launch_real_hardware.py               # Gerçek donanım başlatıcı betik; her İHA üzerindeki Docker konteynerlerini ve fiziksel düğümleri eş zamanlı ayağa kaldırır.
│
├── sim/                                      # Gazebo simülasyon ortamına ait fiziksel dünyalar ve 3B donanım modelleri.
│   ├── models/                               # Simülasyon içerisinde kullanılan tüm 3B fiziksel nesne ve İHA modelleri.
│   │   ├── rtk_base_station/                 # Gazebo ortamında modellenen RTK baz istasyonu; fiziksel görünüm ve düzeltme verisi sensör simülasyonunu içerir.
│   │   ├── x500/                             # Fiziksel uçuş dinamiklerini simüle eden Holybro x500 yarış drone modeli.
│   │   └── x500_base/                        # Holybro x500 modelinin fizik motorunu optimize etmek için kullanılan temel iskelet ve kütle/atalet şablonu.
│   └── worlds/                               # Yarışma alanının dijital ikizi; QR kod yerleşimleri, iniş pedleri ve ışık koşullarını barındıran simülasyon sahnesi.
│
└── src/                                      # ROS 2 tabanlı sürü yazılımı çekirdek kaynak kodları (ROS 2 Workspace).
    │
    ├── swarm_interfaces/                     # ROS 2 düğümleri arasındaki veri takasını standartlaştıran projeye özel mesaj (msg), servis (srv) ve aksiyon (action) tanımları.
    │
    ├── swarm_control/                        # RPi görev bilgisayarının alt seviye otopilot (PX4) ve haberleşme modülü (ESP32) ile veri alışverişini sağlayan köprü katmanı.
    │   ├── px4_bridge/                       # PX4 telemetri verilerini okuyan ve Offboard modunda otopilota anlık hareket/hız setpoint komutları gönderen ROS 2 düğümü.
    │   ├── rtk_bridge/                       # ESP32 üzerinden gelen RTCM3 düzeltme verilerini yakalayan ve santimetre altı hassasiyet için PX4 otopilotuna enjekte eden RTK köprüsü.
    │   ├── esp32_bridge/                     # RPi ile ESP32 arasında UART haberleşme köprüsü; komşu İHA'lardan gelen ağ paketlerini çözerek ROS 2 ekosistemine aktarır.
    │   └── sensor_drivers/                   # PX4 otopilotundan bağımsız olarak çalışan ToF ve TF-Luna Lidar gibi ek sensörlerin sürücüleri; hassas inişin son aşamasında kullanılır.
    │
    ├── network_proxy/                        # Simülasyon ortamında (SITL) gerçekçi ESP-NOW haberleşmesini taklit eden; paket kaybı, sinyal gürültüsü ve gecikme test aracı.
    │
    ├── swarm_state_machine/                  # Sistemin karar alma mekanizmasını yöneten, hiyerarşik yapılandırılmış üç katmanlı durum makinesi.
    │   ├── agent_fsm/                        # Bireysel İHA seviyesinde durum makinesi; İHA'nın anlık durumunu (arm, kalkış, uçuş, hata modu vb.) yönetir.
    │   ├── mission_fsm/                      # Görev seviyesinde durum makinesi; yarışma senaryosundaki alt görevlerin (QR tarama, formasyon, iniş) akışını kontrol eder.
    │   ├── swarm_fsm/                        # Sürü seviyesinde durum makinesi; tüm sürünün koordinasyonunu, uzlaşma (consensus) durumlarını ve kolektif kararları yönetir.
    │   └── mode_manager/                     # Görev 1 (tam otonom otonom sürü uçuşu) ve Görev 2 (yarı otonom joystick/RC kontrolü) modları arasındaki emniyetli geçiş mekanizması.
    │
    ├── swarm_core/                           # Sürü yönetiminin matematiksel modellerini, yörünge planlamasını ve kontrol teorisi algoritmalarını barındıran çekirdek kütüphane.
    │   ├── formation_control/                # Ok Başı, V ve Çizgi formasyonlarını koruyan ve tüm yapıyı döndüren kontrolcü; her İHA kendi setpoint'ini dağıtık olarak hesaplar.
    │   ├── consensus/                        # Dağıtık karar mekanizması; lider seçimi, zaman senkronizasyonu ve QR okuma sırası senkronizasyonu için Bully/Raft tabanlı algoritma.
    │   ├── collision_avoidance/              # APF/ORCA tabanlı çarpışma önleme algoritması; hesaplanan hareket setpoint'lerinin son emniyet filtresidir.
    │   ├── path_planning/                    # Yarışma sahasında QR noktaları ve engeller arasında otonom rota planlayan doğrusal yörünge oluşturucu.
    │   ├── maneuver_executor/                # Sürünün pitch/roll/yaw eksenlerindeki kolektif manevralarını yöneten birim; sürü merkezini sabit tutarak tüm formasyonu eğer/döndürür.
    │   ├── precision_landing/                # Belirlenen kırmızı veya mavi alanlara hassas iniş algoritması; kamera tabanlı görsel konumlandırma ile ToF/Lidar verilerini füzyonlar.
    │   └── task_reallocator/                 # Sürüden ayrılan veya yedek durumdan sürüye katılan İHA'ların rollerini ve formasyon koordinatlarını otonom olarak yeniden dağıtır.
    │
    ├── swarm_perception/                     # Algılama ve çevre modelleme katmanı; kamera verilerinin işlenmesini ve kinematik veri füzyonunu yönetir.
    │   ├── camera_driver/                    # Arducam HQ kameradan görüntü karelerini (frame) alan ve container içi pointer paylaşımıyla bellek yükünü azaltan sürücü.
    │   ├── vision_node/                      # Tek bir OpenCV düğüm üzerinde çalışan entegre görüntü işleme; QR kod tespiti, çözümlenmesi ve renkli iniş bölgelerinin tespitini yapar.
    │   └── kinematic_fusion/                 # Komşu İHA'lardan gelen telemetri verilerini filtreleyen ve sönümleyen kinematik füzyon; formasyon ve çarpışma önleme için girdi sağlar.
    │
    └── swarm_missions/                       # Geliştirilen tüm otonom yetenekleri ve durum makinelerini yarışma görev senaryolarına göre sıraya koyan orkestrasyon katmanı.
        ├── mission1_dynamic_swarm/           # Görev 1; tam otonom kalkış, QR rotası takibi, formasyon değişimi, manevralar, dinamik üye ekleme/çıkarma, eve dönme ve otonom iniş.
        └── mission2_semi_autonomous/         # Görev 2; tek bir joystick veya kumandadan gelen hareket girdilerini tüm sürüye senkronize şekilde dağıtan yarı otonom uçuş katmanı.
```

## 2. High-Level System Diagram
Bu bölüm, sistemin ana donanım ve yazılım bileşenlerini, aralarındaki etkileşimleri ve veri akış yönlerini gösteren temel bir sistem bağlam diyagramı sunar. Özellikle görev bilgisayarı (Raspberry Pi), otopilot (Pixhawk) ve ağ birimleri (ESP32, YKİ) arasındaki mimari sınırlara ve iletişim protokollerine odaklanmaktadır.

```
       [Yer Kontrol İstasyonu] <----------------------+ (Yarı Otonom Uçuş & Kılavuzluk)
                    |                                 |
                    | ESP-NOW                         | RC Kumanda (FLYSKY)
                    | (Telemetri & Görevler)          | (Güvenlik / Manuel Override)
                    v                                 v
  +-------------------------------------------------------------------------+
  |                             İHA PLATFORMU (x3)                          |
  |                                                                         |
  |  [Arducam HQ]                         [Here4 RTK GNSS]                  |
  |       | (CSI)                               | (CAN/UART)                |
  |       v                                     v                           |
  |  +-------------------------------------------------------------------+  |
  |  |                          Raspberry Pi 5                           |  |
  |  |  (Görüntü İşleme, ROS 2, Karar Mekanizması, Sürü Algoritmaları)   |  |
  |  +-------------------------------------------------------------------+  |
  |       ^                                       ^                         |
  |       | MAVLink / UART                        | UART / SPI              |
  |       | Telemetri                             | ESP-NOW Veri Paketi     |
  |       | RTCM Düzeltme                         |                         |
  |       v Offboard Komutları                    v                         |
  |  +---------------------------+       +-------------------------------+  |
  |  | Pixhawk 2.4.8 (Otopilot)  |       | ESP32-WROOM-32U (Mesh Node)   |  |
  |  | (Sensör Füzyonu / EKF2)   |       | (2.4 GHz Kanal Atlama)        |  |
  |  +---------------------------+       +-------------------------------+  |
  |       |                                       ^                         |
  |       | PWM                                   |                         |
  |       v                                       |                         |
  |  [Motorlar (Emax) & ESC (Hobbywing)]          |                         |
  +-----------------------------------------------|-------------------------+
                                                  |
                                                  | Dağıtık Mesh Ağı (ESP-NOW)
                                                  | (İHA'lar Arası Vektörel Konum, 
                                                  | Consensus ve Çarpışma Uyarıları)
                                                  v
                                        [Komşu Sürü İHA'ları]
```

## 3. Core Components

Bu bölüm, sistemin otonom sürü operasyonlarını gerçekleştirmesini sağlayan ana donanım ve yazılım bileşenlerini listeler. Her biri için temel sorumluluk alanı ve kullanılan kritik teknolojiler/donanımlar belirtilmiştir.

### 3.1. Görev Bilgisayarı ve Yüksek Seviye Otonomi

**Raspberry Pi 4 4GB Edge Bilgisayar**
* **Açıklama:** İHA'nın ana beyni olarak görev yapar. Merkeziyetsiz karar mekanizmasının kalbidir. Görüntü işleme, dinamik formasyon hesaplamaları, APF/ORCA tabanlı çarpışma önleme algoritmaları ve ROS 2 düğümlerinin eşzamanlı çalışmasını yönetir. Görev planlamaları ve uzlaşma kararları bu birimde alınır.
* **Teknolojiler:** ROS 2 Jazzy, Python 3, C++, OpenCV, Eclipse CycloneDDS.
* **Dağıtım/Ortam:** Ubuntu 24.04 tabanlı izole Docker Container'ları.

### 3.2. Uçuş Kontrol Sistemi

**Pixhawk PX 2.4.8 Otopilot**
* **Açıklama:** Alt seviye uçuş dinamiklerini yöneten, stabilitesini sağlayan ve motorları süren aviyonik katmandır. Üzerindeki dahili sensörlerden ve GNSS'ten aldığı verileri Genişletilmiş Kalman Filtresi ile füzyonlar. Görev bilgisayarından "Offboard" modda gelen asenkron hareket/hız komutlarını yorumlayarak ESC'lere PWM sinyalleri olarak dağıtır.
* **Teknolojiler:** PX4 Autopilot Firmware, MAVLink v2, EKF2 Sensör Füzyonu, PID Kontrol.
* **Donanım Temeli:** STM32F427 Ana İşlemci, yedekli fail-safe işlemci (STM32F103).

### 3.3. Algılama ve Konumlandırma

**Çevresel Görüş ve Uzamsal Navigasyon Modülleri**
* **Açıklama:** Otonom uçuş, hedef tespiti ve milimetrik pozisyonlama için çevre verisini toplar. Görev 1 kapsamında; kamera, yerdeki QR kodları ve mavi/kırmızı iniş alanlarını işleyerek hedef koordinatlarına dönüştürür. RTK sistemi, GPS zafiyetlerini önleyerek santimetre altı hassasiyet sağlarken; Lidar sensörü iniş anında zemine olan yüksekliği doğrular.
* **Teknolojiler:** OpenCV (Dinamik Maskeleme ve QR Çözümleme), RTCM3 (Düzeltme Verisi).
* **Donanım Temeli:** Arducam HQ Kamera (12.3 MP, 6mm CS Lens), CubePilot Here4 RTK GNSS.

### 3.4. Dağıtık Haberleşme Ağı

**ESP-NOW Sürü İçi Mesh Ağ**
* **Açıklama:** Sürü İHA'ların kendi aralarında "Peer-to-Peer" olarak haberleşmesini sağlayan kritik ağ katmanıdır. Her bir İHA, anlık konumunu, yönelimini ve bulduğu QR görevlerini, merkezi bir YKİ'ye gitmeden doğrudan komşularına çok düşük gecikmeyle iletir. "Self-healing" mimarisi sayesinde ağdan kopan üyenin boşluğunu saniyesinde tolere eder.
* **Teknolojiler:** ESP-NOW Protokolü, Dinamik Kanal Atlama, Bully/Raft benzeri Lider Seçimi.
* **Donanım Temeli:** ESP32-WROOM-32U Mikrodenetleyici, 2.4G U.FL Kablolu SMA Anten.

### 3.5. Yer Kontrol İstasyonu

**Modüler Yelpençe YKİ**
* **Açıklama:** Pilotların tüm sürünün telemetri verilerini, canlı konumlarını, batarya seviyelerini ve sistem sağlığını harita üzerinden anlık olarak takip etmesini sağlayan dış denetim arayüzüdür. Görev 2'deki "Yarı Otonom Uçuş" senaryoları için, kumandadan (FLYSKY) alınan pitch/roll/yaw direktiflerinin tek merkezden tüm sürüye eş zamanlı aktarıldığı kontrol noktasıdır.
* **Teknolojiler:** MAVSDK-Python, ROS 2 GCS Düğümleri.
* **Donanım Temeli:** Kontrol Merkezi Bilgisayarı, CubePilot Here4 Base (RTK Baz İstasyonu ve Ground Plate), FLYSKY FS-i6X RC Kumanda.

## 4. Data Stores

Geleneksel web/yazılım projelerinden farklı olarak, sürü İHA sistemimizde veritabanı mimarisi; milisaniyelik uçuş dinamiklerinin kaydedilmesi, ROS 2 haberleşme geçmişinin tutulması ve kalıcı sistem parametrelerinin yönetilmesi üzerine inşa edilmiştir.

### 4.1. Uçuş Kontrol Logları

**Pixhawk ULog & Uçuş Veri Kayıtları**
* **Tip:** .ulog formatı (Pixhawk üzerindeki 16GB Sandisk Ultra MicroSD tabanlı yerel depolama)
* **Kullanım Amacı:** Otopilotun anlık sensör verilerini (IMU, Barometre, Lidar), EKF2 tahminlerini, motor PWM çıktılarını ve otonom görev/failsafe tetiklemelerini kaydeder. Olası kaza/kırım durumlarında (post-flight analysis) ve PID optimizasyon süreçlerinde başvurulan en kritik "kara kutu" veri deposudur.
* **Temel Veri Setleri:** Sensor Raw Data, Actuator Outputs, Vehicle Local/Global Position, EKF Innovations.

4.2. Otonomi ve Sürü Haberleşme Kayıtları

**ROS 2 Bag Deposu**
* **Tip:** SQLite3 Veritabanı (.db3 formatı, RPi üzerindeki 32GB Sandisk Extreme MicroSD tabanlı yerel depolama)
* **Kullanım Amacı:** Görev bilgisayarı (RPi 4) üzerinde koşan düğümlerin ürettiği ROS mesajlarını kaydeder. Görüntü işleme verileri, ESP-NOW üzerinden komşu İHA'lardan gelen sürü telemetrileri ve "Consensus" (Uzlaşma) kararlarının kronolojik kayıtlarını barındırır. Simülasyon ve analiz için verilerin laboratuvar ortamında tekrar oynatılmasında (playback) kullanılır.
* **Temel Şemalar/Topic'ler:** /tf (Transformasyonlar), /camera/image_raw (Örneklenmiş kamera kareleri), /swarm_state, /mavros/local_position/pose.

### 4.3. Sistem Konfigürasyon ve Görev Parametreleri

**YAML Konfigürasyon Deposu**
* **Tip:** .yaml dosyaları (Github reposu ve RPi dosya sistemi üzerinde statik yapılandırma deposu)
* **Kullanım Amacı:** Sistemin her başlatılışında okuduğu, donanıma gömülü olmayan değişken parametreleri saklar. Sistemin kod yapısını değiştirmeden sürü davranışının (örneğin İHA ID'si, formasyon şekilleri veya emniyet sınırları) modifiye edilmesini sağlar.
* **Temel Dosyalar:** swarm_params.yaml (ID'ler, genel irtifa), formations.yaml (Geometrik ofset matrisleri), competition_overrides.yaml.

### 4.4. Yer Kontrol İstasyonu (GCS) Telemetri Geçmişi 

**YKİ Görev ve Analiz Veritabanı**
* **Tip:** SQLite / JSON (Kontrol Merkezi Bilgisayarı üzerinde)
* **Kullanım Amacı:** Yarışma görevi sırasında havadan gelen verilerin arşivlenmesi. Çözümlenen QR kod içeriklerini, mavi/kırmızı alan koordinatlarını ve sürünün genel sağlık/batarya durumlarını anlık olarak kaydeder ve arayüze sunar.
* **Temel Şemalar:** qr_records, landing_zones_coordinates, fleet_telemetry_history.

## 5. External Integrations / APIs

Projemiz büyük ölçüde kapalı ve yerel bir uç bilişim ağı üzerinde koşsa da, sistemin çalışması için hayati önem taşıyan bazı dış kaynak kod entegrasyonları (Submodule'ler) ve Yer Kontrol İstasyonunun kendi içinde sunduğu servis API'leri bulunmaktadır.

### 5.1. Uçuş Yığını ve Middleware

Sistemin otopilot ile ROS 2 arasında MAVLink darboğazına takılmadan, doğrudan donanım seviyesinde (RTPS/DDS) haberleşmesini sağlamak amacıyla projeye entegre edilen kritik repolar şunlardır:

**PX4 Autopilot**
* **Amaç:** İHA'nın tüm alt seviye uçuş, stabilizasyon ve EKF algoritmalarını barındıran temel otopilot yığınıdır. Orijinal kaynak kod projeye "submodule" olarak çekilir, proje kökündeki docker/patches/ klasöründe yer alan Yelpençe'ye özel yamalar ile modifiye edilerek derlenir.
* **Entegrasyon Yöntemi:** Git Submodule, Özelleştirilmiş C++ Firmware Derlemesi.

**Micro XRCE-DDS Agent**
* **Amaç:** Otopilotun iç dünyasındaki veri yollarını (uORB) görev bilgisayarındaki ROS 2 DDS ağına köprüleyen ajan yazılımıdır. MAVLink tabanlı kısıtlı iletişimi by-pass ederek yüksek frekanslı otonom kontrol imkânı sağlar.
* **Entegrasyon Yöntemi:** ROS 2 Middleware, UXRCE-DDS Köprüsü.

**PX4 ROS 2 Mesajları**
* **Amaç:** Görev bilgisayarındaki ROS düğümleri ile Pixhawk arasındaki ortak dili sağlayan statik tip sözlüğüdür. C++ ve Python düğümlerinin uçuş kontrolcüsüne ait VehicleLocalPosition, TrajectorySetpoint gibi spesifik mesajları tanımasını ve bu formatta yayın yapmasını sağlar.
* **Entegrasyon Yöntemi:** Git Submodule, ROS 2 Message paketleri.

### 5.2. Yer Kontrol İstasyonu API Mimarisi

Yer Kontrol İstasyonumuz, arka ucu Python tabanlı ve ön ucu React tabanlı ayrık bir mimariyle geliştirilmiştir. Arka uçtaki gcs/backend/api/ dizini altındaki API'ler, sistem durumunun kontrol edilmesini sağlar.

**Yelpençe GCS Backend APIs**
* **Amaç:** Sürüden gelen telemetri verilerini derleyip pilot arayüzüne aktarmak; aynı zamanda pilotun arayüz üzerinden verdiği "Görev Başlat", "RTL", "Formasyon Değiştir" gibi kritik komutları işleyerek sürüye iletmektir. Arayüzün İHA'ların anlık sağlığını (batarya, GPS durumu, aktif mod) asenkron olarak okuyabilmesi bu arayüzler üzerinden gerçekleşir.
* **Entegrasyon Yöntemi:** RESTful API (HTTP Metotları ile durum/komut yönetimi) ve WebSockets (Gecikmesiz canlı telemetri ve harita verisi akışı için).

## 6. Deployment & Infrastructure
Bu bölüm, yazılımın geliştirme ortamından çıkarak gerçek dünya donanımlarına nasıl dağıtıldığını, sistemin nasıl ayağa kaldırıldığını ve proje kalitesini koruyan sürekli entegrasyon süreçlerini açıklar.

* **Dağıtım Ortamı:** Uç Bilişim / On-Premise. Sistemin beyni bulut sunucularında değil, izole bir yerel ağ üzerinde ve fiziksel İHA'ların gövdesine entegre edilmiş Raspberry Pi 4 donanımlarında koşar.
* **Kullanılan Temel Servisler:** Docker & Docker Compose; Geliştiricinin kendi bilgisayarı (SITL simülasyon) ile gerçek İHA üzerindeki ortam farklılıklarını tamamen ortadan kaldırmak için kullanılır. Tüm ROS 2 düğümleri, bağımlılıkları ve OpenCV kütüphaneleri docker/rpi/ altındaki imajlar aracılığıyla konteynerize edilmiştir.
* **ROS 2 Launch System:** Sürü davranışını başlatmak, çoklu düğümleri argümanlarla ayağa kaldırmak için scripts/launch_swarm.py ve scripts/launch_real_hardware.py yapıları kullanılır.

* **Sürekli Entegrasyon ve Dağıtım (GitHub Actions):** Proje deposuna yapılan her push ve pull_request işleminde .github/workflows/ altındaki otomasyon betikleri tetiklenir:
    * **ros2_build.yml:** Tüm C++ ve Python paketlerinin (colcon build) bağımlılık hatası vermeden derlenebildiğini test eder.
    * **security_scan.yml:** Python kodlarındaki statik güvenlik açıklarını tespit etmek için "Bandit" taraması yürütür.

## 7. Development & Testing Environment 
Bu proje, kodun hem donanımsal hem de yazılımsal zafiyetlere karşı dirençli olmasını sağlamak için sağlam bir simülasyon ve test altyapısı üzerine kurulmuştur. Yeni geliştiricilerin sisteme hızla adapte olması hedeflenmiştir.

**Geliştirme Ortamı Kurulumu:**

Geliştiricilerin kendi makinelerinde (Linux/Ubuntu) izole bir ortamda çalışabilmesi için tüm yapı Docker ile paketlenmiştir. Projeye katkıda bulunmaya başlamak için gerekli adımlar depo kökündeki CONTRIBUTING.md dosyasında detaylandırılmıştır. Geliştirmeler tamamlandığında simülasyon ortamını ayağa kaldırmak için scripts/launch_swarm.py betiği kullanılır; bu sayede Gazebo Harmonic fizik motorunda kodlar güvenle denenebilir.

**Test Çerçeveleri:**
* **Python Testleri:** Otonomi karar mekanizmaları ve matematiksel sürü algoritmaları için pytest altyapısı kullanılmaktadır.
* **C++ Testleri:** ROS 2 köprüleri ve performans kritik görevler GTest ile ament_cmake standartlarına uygun olarak test edilir.
* **Yazılım Döngüsü:** Tüm entegrasyon ve fiziksel davranış/sürü algoritması testleri, gerçek İHA kodunun birebir simüle edildiği Gazebo Harmonic ortamında yapılır.

**Kod Kalite ve Analiz Araçları**
 
Proje genelinde ROS 2 standartlarını ve güvenliği korumak için CI/CD süreçlerine aşağıdaki toollar entegre edilmiştir:

* **Statik Kod Analizi:** Python kodlarında sözdizimi doğruluğu için flake8 ve ament_lint, C++ kodlarında ise cpplint kullanılır.
* **Güvenlik Taraması:** Sürü haberleşmesi ve API kodlarında zafiyet olup olmadığını kontrol etmek amacıyla Python odaklı bandit aracı her bir commit işleminde (GitHub Actions üzerinden) otomatik çalışır.

