# Yelpençe 2026 Sürü İHA Projesi - Mimari Dosya Yapısı

Aşağıdaki ağaç yapısı, yelpence-2026-swarm/ ana dizini altındaki kritik mimari dosyalarını göstermektedir. Dosya isimlerine tıklayarak ilgili bileşenin detaylı açıklamasına ulaşabilirsiniz. 

yelpence-2026-swarm/
├── [.github/](#.github/)
│   └── [workflows/](#.github/workflows/)
├── [docker/](#docker)
│   └── [patches/](#docker-patches)
├── [scripts/](#scripts)
├── [sim/](#sim)
│   ├── [models/](#sim-models)
│   │   ├── [rtk_base_station/](#sim-models-rtk-base-station)
│   │   ├── [x500/](#sim-models-x500-ve-sim-models-x500-base)
│   │   └── [x500_base/](#sim-models-x500-ve-sim-models-x500-base)
│   └── [worlds/](#sim-worlds)
├── [src/](#src)
│   ├── [swarm_interfaces/](#swarm-interfaces)
│   ├── [swarm_control/](#swarm-control)
│   └── [swarm_state_machine/](#swarm_state_machine/)
│       ├── [agent_fsm/](#swarm-state-machine-agent-fsm)
│       └── [mission_fsm/](#dizin-ve-dosya-detayları)

# Dizin ve Dosya Detayları

Aşağıda mimari ağaçta belirtilen dizinlerin detaylı açıklamaları yer almaktadır:


#### .github/

Bu dizin, GitHub deposunun CI/CD (Sürekli Entegrasyon ve Sürekli Dağıtım) süreçlerini ve genel depo otomasyon ayarlarını barındırır.


#### .github/workflows/

GitHub Actions kullanılarak yapılandırılmış otomasyon iş akışlarını (workflows) içerir. Repoya yapılan kod eklemelerinde ROS 2 paketlerinin otomatik derlenmesi, test edilmesi ve güvenlik taramalarının yapılması gibi CI/CD süreçlerini yürüten betikler burada bulunur.


#### docker/

Sürü İHA sisteminin hem görev bilgisayarı (Raspberry Pi 5) üzerinde hem de geliştirici ortamlarında (Simülasyon/Gazebo) donanım bağımsız, izole ve tekrarlanabilir bir ROS 2 çevresinde çalışmasını sağlayan Docker altyapısıdır. Geliştiricilerin sistemi kolayca ayağa kaldırması için gereken imaj yapılandırmalarını ve yardımcı başlatma betiklerini barındırır.


#### docker/patches/

Açık kaynaklı sistem kütüphanelerine, simülasyon eklentilerine veya sürücülere dışarıdan müdahale edilerek projenin özel gereksinimlerine uydurulması gereken yamaları (patch) barındırır. Bu yamalar, Docker imajı inşa edilirken otomatik olarak ilgili kod kaynaklarına uygulanır.


```scripts/```

Sistemin başlatılması ve test senaryolarının oluşturulması için kullanılan yardımcı Python betiklerini içerir. Simülasyon dünyalarını dinamik olarak oluşturmak (generate_task_world.py) ve birden fazla ajanı içeren sürüyü tek bir komutla ayağa kaldırmak (launch_swarm.py) için yazılmış araçları barındırır.


```sim/```

Projenin otonomi ve sürü algoritmalarının sahaya çıkmadan önce güvenli bir şekilde test edildiği yüksek sadakatli Gazebo Harmonic simülasyon ortamının ana dizinidir.


```sim/models/```

Simülasyonda kullanılan araçların, sensörlerin, çevre objelerinin 3D modellerini, fiziksel ve kinematik özelliklerini tanımlayan Simulation Description Format (SDF) dosyalarını barındırır.


```sim/models/rtk_base_station/```

Sistemdeki araçların hassas konumlandırma yapabilmesi için gerekli olan ve simülasyon ortamında referans noktası olarak kullanılan RTK (Real-Time Kinematic) GNSS baz istasyonunun model dosyalarını içerir.


```sim/models/x500/ & sim/models/x500_base/```

Sürüdeki her bir fiziksel İHA'yı temsil eden x500 (F450 sınıfına denk) quadcopter modellerini barındırır. Bu dizinlerde aracın pervaneleri, gövdesi, ağırlık merkezi ve görsel dokuları (meshes/textures) ile uçuş dinamiklerini belirten SDF yapılandırmaları yer alır.


```sim/worlds/```

Simülasyonun gerçekleşeceği sanal çevreyi tanımlayan dünya dosyalarını içerir. Işıklandırma, yerçekimi parametreleri ve fizik motoru yapılandırmaları bu dizindeki SDF dosyalarında (base_world.sdf vb.) belirtilir.


```src/```

Projenin ROS 2 tabanlı otonomi, haberleşme ve kontrol yazılımlarının kaynak kodlarını barındıran ana çalışma alanı (workspace) dizinidir. Tüm sürü algoritmaları, donanım köprüleri ve özel mesaj tipleri bu dizin altında bağımsız ROS 2 paketleri olarak yer alır.


```swarm_control/```

İHA'ların uçuş kontrolcüsü (Pixhawk/PX4) ile üst düzey ROS 2 karar mekanizmaları arasındaki köprüyü kuran temel pakettir. Yüksek seviyeli ROS 2 formasyon komutlarını MAVLink/MAVSDK üzerinden PX4'ün anlayacağı sinyallere dönüştüren (command_sender.py) ve uçuş kontrolcüsünden gelen telemetri verilerini sisteme aktaran (telemetry_mapper.py) yapıları içerir.


```swarm_interfaces/```

Sürüdeki İHA'ların (ajanların) birbirleriyle ve yer istasyonuyla haberleşmesi için gereken özel ROS 2 iletişim arayüzlerini (Action, Message, Service) barındıran pakettir. Ajan durum bilgileri (AgentStatus.msg), formasyon yönetim eylemleri (ExecuteFormation.action), sistem içi liderlik seçimi konsensüsleri (ElectionResult.msg, LeaderHeartbeat.msg) ve QR/İniş alanı tespiti (LandingZoneDetection.msg, QRMissionData.msg) gibi sürü otonomisinin tüm veri yapıları ve haberleşme kontratları burada tanımlanmıştır. Sistemdeki tüm diğer paketler tarafından bağımlılık olarak kullanılır.


#### swarm_state_machine/

Sürüdeki araçların yüksek seviyeli karar alma algoritmalarını ve durum makinelerini (Finite State Machine - FSM) yöneten ana ROS 2 paketidir.


```swarm_state_machine/agent_fsm/```

Bu dizin, sürüdeki her bir İHA'nın (ajanın) bireysel otonomisini, hayatta kalma mantığını ve karar alma mekanizmalarını yöneten çekirdek durum makinesi (Finite State Machine) altyapısıdır. Bir ajanın sistem başlatılıp göreve hazırlanmasından, uçuş öncesi kritik güvenlik kontrollerine (RTK düzeltmesi, donanım sağlığı), uçuş sırasındaki anlık sensör ve batarya denetimlerine kadar tüm yaşam döngüsünü kontrol eder. Ajanın bekleme, kalkış, formasyona dâhil olma, otonom seyir veya olası bir acil durumda (iletişim kopukluğu, GPS kaybı) güvenli moda geçiş gibi farklı uçuş durumları arasındaki mantıksal kurallar ve geçişler bu dizindeki modüller üzerinden işletilir. Böylece her bir araç, hem kendi iç bağlamını (context) yöneterek tutarlı kararlar alır hem de sistemin geneline hata toleranslı ve güvenli bir uçuş profili sunar.
