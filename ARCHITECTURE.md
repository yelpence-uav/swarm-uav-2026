# Yelpençe 2026 Sürü İHA Projesi - Mimari Dosya Yapısı

Aşağıdaki ağaç yapısı, yelpence-2026-swarm/ ana dizini altındaki kritik mimari dosyalarını göstermektedir.

```
yelpence-2026-swarm/
├── .github/
│   └── workflows/
├── docker/
│   └── patches/
├── scripts/
├── sim/
│   ├── models/
│   │   ├── rtk_base_station/
│   │   ├── x500/
│   │   └── x500_base/
│   └── worlds/
├── src/
│   ├── swarm_interfaces/
│   ├── swarm_control/
│   │   └── *failsafe_executor/
│   ├── swarm_state_machine/
│   │   ├── agent_fsm/
│   │   ├── *mission_fsm/ # Görev seviyesi durum makinesi 
│   │   ├── *swarm_fsm/ # Sürü seviyesi durum makinesi
│   │   ├── *mode_manager/ # Görev 2 için mod yöneticisi
│   │   ├── *failsafe_fsm/ # Acil durum durum makinesi 
│   │   ├── *events/ # Olay tanımları (durum geçişleri için)
│   │   └── *health_monitor/ # Sensör verilerini ve watchdog sürelerini denetleyip FSM'i tetikleyen düğüm
│   ├── *swarm_core/ # Çekirdek sürü algoritmaları
│   │   ├── *formation_control/ # Formasyon oluşturma/değişim
│   │   ├── *consensus/ # Dağıtık karar alma (lider seçimi, senkronizasyon)
│   │   ├── *collision_avoidance/ # Çarpışma önleme (APF, ORCA, vb.)
│   │   ├── *path_planning/  # Rota planlama (A*, RRT)
│   │   ├── *maneuver_executor/  # Pitch/Roll/Yaw sürü manevraları
│   │   └── *task_reallocator/
│   ├── *swarm_perception/ # Algılama katmanı
│   │   ├── *qr_detector/ # QR kod tespit ve çözümleme
│   │   ├── *landing_zone_detector/ # Kırmızı/mavi iniş bölgesi tespiti
│   │   ├── *kinematic_fusion/ # DDS üzerinden gelen komşu ajan verilerini filtreleyip anlık konum tahmini
│   │   └── *camera_driver/  # Kamera sürücüsü
│   ├── *swarm_missions/ # Görev modülleri
│   │   ├── *mission1_dynamic_swarm/  # Görev 1: Dinamik Sürü Kabiliyeti
│   │   └── *mission2_semi_autonomous/ # Görev 2: Yarı Otonom Kontrol

```

# Dizin ve Dosya Detayları

Aşağıda mimari ağaçta belirtilen dizinlerin detaylı açıklamaları yer almaktadır:

#### .github
Bu dizin, GitHub deposunun CI/CD süreçlerini ve genel depo otomasyon ayarlarını barındırır.

#### .github/workflows
GitHub Actions kullanılarak yapılandırılmış otomasyon iş akışlarını içerir. Repoya yapılan kod eklemelerinde ROS 2 paketlerinin otomatik derlenmesi, test edilmesi ve güvenlik taramalarının yapılması gibi CI/CD süreçlerini yürüten betikler burada bulunur.

#### docker
Sürü İHA sisteminin hem görev bilgisayarı üzerinde hem de geliştirici ortamlarında donanım bağımsız, izole ve tekrarlanabilir bir ROS 2 çevresinde çalışmasını sağlayan Docker altyapısıdır. Geliştiricilerin sistemi kolayca ayağa kaldırması için gereken imaj yapılandırmalarını ve yardımcı başlatma betiklerini barındırır.

#### docker/patches
Açık kaynaklı sistem kütüphanelerine, simülasyon eklentilerine veya sürücülere dışarıdan müdahale edilerek projenin özel gereksinimlerine uydurulması gereken yamaları (patch) barındırır. Bu yamalar, Docker imajı inşa edilirken otomatik olarak ilgili kod kaynaklarına uygulanır.

#### scripts
Sistemin başlatılması ve test senaryolarının oluşturulması için kullanılan yardımcı Python betiklerini içerir. Simülasyon dünyalarını dinamik olarak oluşturmak (generate_task_world.py) ve birden fazla ajanı içeren sürüyü tek bir komutla ayağa kaldırmak için yazılmış araçları barındırır.

#### sim
Projenin otonomi ve sürü algoritmalarının sahaya çıkmadan önce güvenli bir şekilde test edildiği yüksek sadakatli Gazebo Harmonic simülasyon ortamının ana dizinidir.

#### sim/models
Simülasyonda kullanılan araçların, sensörlerin, çevre objelerinin 3D modellerini, fiziksel ve kinematik özelliklerini tanımlayan Simulation Description Format dosyalarını barındırır.

#### sim/models/rtk_base_station
Sistemdeki araçların hassas konumlandırma yapabilmesi için gerekli olan ve simülasyon ortamında referans noktası olarak kullanılan RTK GNSS baz istasyonunun model dosyalarını içerir.

#### sim/models/x500 & sim/models/x500_base
Sürüdeki her bir fiziksel İHA'yı temsil eden x500 quadcopter modellerini barındırır. Bu dizinlerde aracın pervaneleri, gövdesi, ağırlık merkezi ve görsel dokuları ile uçuş dinamiklerini belirten SDF yapılandırmaları yer alır.

#### sim/worlds
Simülasyonun gerçekleşeceği sanal çevreyi tanımlayan dünya dosyalarını içerir. Işıklandırma, yerçekimi parametreleri ve fizik motoru yapılandırmaları bu dizindeki SDF dosyalarında belirtilir.

#### src
Projenin ROS 2 tabanlı otonomi, haberleşme ve kontrol yazılımlarının kaynak kodlarını barındıran ana çalışma alanı dizinidir. Tüm sürü algoritmaları, donanım köprüleri ve özel mesaj tipleri bu dizin altında bağımsız ROS 2 paketleri olarak yer alır.

#### swarm_control
İHA'ların uçuş kontrolcüsü ile üst düzey ROS 2 karar mekanizmaları arasındaki köprüyü kuran temel pakettir. Yüksek seviyeli ROS 2 formasyon komutlarını MAVLink/MAVSDK üzerinden PX4'ün anlayacağı sinyallere dönüştüren ve uçuş kontrolcüsünden gelen telemetri verilerini sisteme aktaran yapıları içerir.

#### swarm_interfaces
Sürüdeki İHA'ların birbirleriyle ve yer istasyonuyla haberleşmesi için gereken özel ROS 2 iletişim arayüzlerini barındıran pakettir. Ajan durum bilgileri, formasyon yönetim eylemleri, sistem içi liderlik seçimi konsensüsleri ve QR/İniş alanı tespiti gibi sürü otonomisinin tüm veri yapıları ve haberleşme kontratları burada tanımlanmıştır. Sistemdeki tüm diğer paketler tarafından bağımlılık olarak kullanılır.

#### swarm_state_machine
Sürüdeki araçların yüksek seviyeli karar alma algoritmalarını ve durum makinelerini yöneten ana ROS 2 paketidir.

#### swarm_state_machine/agent_fsm
Bu dizin, sürüdeki her bir İHA'nın bireysel otonomisini, hayatta kalma mantığını ve karar alma mekanizmalarını yöneten çekirdek durum makinesi altyapısıdır. Bir ajanın sistem başlatılıp göreve hazırlanmasından, uçuş öncesi kritik güvenlik kontrollerine, uçuş sırasındaki anlık sensör ve batarya denetimlerine kadar tüm yaşam döngüsünü kontrol eder. Ajanın bekleme, kalkış, formasyona dâhil olma, otonom seyir veya olası bir acil durumda güvenli moda geçiş gibi farklı uçuş durumları arasındaki mantıksal kurallar ve geçişler bu dizindeki modüller üzerinden işletilir. Böylece her bir araç, hem kendi iç bağlamını yöneterek tutarlı kararlar alır hem de sistemin geneline hata toleranslı ve güvenli bir uçuş profili sunar.
