# Yelpençe Sürü İHA Projesi - TEKNOFEST 2026

> Bu depo, Yelpençe takımının TEKNOFEST 2026 Sürü İHA Yarışması için geliştirdiği tüm yazılım mimarisini, algoritma setlerini ve dokümantasyon süreçlerini barındıran ana merkezdir. Proje; dinamik sürü formasyonları, otonom görev icrası ve gelişmiş yer kontrol istasyonu entegrasyonuna odaklanmaktadır.

# Dizin Yapısı

```text
yelpence-2026-swarm/
├── .github/                # CI/CD otomatik test ve kalite kontrol süreçleri (Actions)
├── docs/                   # Şartname, raporlar ve teknik dokümantasyon
├── src/                    # Kaynak kodların ana dizini
│   ├── gcs/                # Yer Kontrol istasyonu modülleri
│   ├── swarm/              # Sürü yönetim ve formasyon mantığı
│   ├── vision/             # QR kod ve görüntü işleme algoritmaları
│   ├── network/            # MAVLink ve haberleşme köprüleri
│   └── yelpence_msgs/      # Özel ROS 2 sürü haberleşme mesaj tanımları
├── sim/                    # Gazebo dünyaları ve İHA modelleri
├── config/                 # Parametre ve uçuş konfigürasyonları
├── docker/                 # Geliştirme ortamı yapılandırması
├── scripts/                # Kurulum ve çalıştırma yardımcı betikleri
└── tests/                  # Birim ve entegrasyon testleri
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
Projemiz Docker konteynerleri üzerinde çalışmaktadır. Aşağıdaki adımları sırasıyla uygulayarak kurulumu tamamlayınız.

### 3.1. Docker Engine Kurulumu
Docker'ı kurmak ve sudo kullanmadan çalıştırabilmek için:

```bash
# Gerekli başlangıç paketlerini kurun
sudo apt-get update
sudo apt-get install ca-certificates curl

# Docker'ın resmi GPG anahtarını ekleyin
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Docker deposunu kaynaklara ekleyin
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker'ı yükleyin
sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Kullanıcınızı 'docker' grubuna ekleyin
# Bu işlem sayesinde her seferinde 'sudo' yazmak zorunda kalmazsınız.
sudo usermod -aG docker $USER

# Grup değişikliğini aktif edin
newgrp docker
```

### 3.2. NVIDIA Container Toolkit Kurulumu
Simülasyonun ekran kartını kullanabilmesi ve siyah ekran hatası vermemesi için bu adım zorunludur. AMD kullanıcıları **3.3. Dosya İzinlerinin Ayarlanması**  bölümüne geçebilir.

```bash
# Nvidia deposunu ekleyin
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Toolkit'i yükleyin
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Docker'ı Nvidia sürücüsüyle yapılandırın
sudo nvidia-ctk runtime configure --runtime=docker

# Docker servisini yeniden başlatın
sudo systemctl restart docker
```

### 3.3. Dosya İzinlerinin Ayarlanması
Proje içindeki yardımcı scriptlerin çalışabilmesi için izinleri verin:

```bash
cd docker
chmod +x build.bash entrypoint.sh ../scripts/sim_start.sh
```

### 3.4. Docker İmajının İnşası
Takım üyelerinin farklı kullanıcı ID'leri (UID) sebebiyle dosya izin hatası yaşamaması için özel inşa scriptini çalıştırın. Bu script, imajı size özel paketler.

```bash
# docker klasörü içerisindeyken:
./build.bash
```

### 3.5. Sanal Ortamı Başlatma
Kurulum bittikten sonra sistemi ayağa kaldırın:
```Bash
# GUI izinlerini tazeleyin
xhost +local:root

# Konteyneri başlatın
# Nvidia Kullanıcıları: 
docker compose up -d

# AMD Kullanıcıları:
docker compose -f docker-compose-amd.yml up -d
```
### 3.1. Geliştirme Ortamına Giriş
Sanal bilgisayarın içine girmek için:

```bash
docker exec -it yelpence_swarm_container bash
```

## 4. Yazılım Mimarisi ve ROS 2 Altyapısı

### 4.1. Amaç ve Mantık
ROS 2 projelerinde kodların derlenebilmesi ve sistem tarafından tanınabilmesi için belirli bir paket yapısına sahip olması gerekir. Projemizin başlangıç aşamasında oluşturulan hiyerarşik klasörler, içlerine `package.xml` ve `setup.py` / `CMakeLists.txt` dosyaları eklenerek resmi birer ROS 2 yazılım modülüne dönüştürülmüştür. 

Bu sayede modüler, görev dağılımına uygun ve birindeki hata diğerinin çalışmasını engellemeyen bir çalışma alanı altyapısı kurulmuştur.

Ayrıca, sürü İHA'lar arasındaki yüksek frekanslı haberleşme trafiğini en düşük gecikmeyle ve en stabil şekilde yönetebilmek adına, ROS 2'nin varsayılan haberleşme protokolü yerine çoklu otonom sistemler için endüstri standardı olan **CycloneDDS** altyapısı sisteme entegre edilmiş ve Docker ortamımıza kalıcı olarak dahil edilmiştir.

### 4.2. Paket Mimarisi ve Görev Dağılımı
Projemizin `src` dizini altındaki yazılım modülleri ve görev tanımları şu şekildedir:

* **`swarm`:** Sürü İHA formasyon kontrolü, otonom karar alma mekanizmaları ve dinamik görev paylaşımı algoritmalarını barındırır.
* **`vision`:** Kamera verilerinin işlenmesi, sahada yer alan QR kodların okunup çözümlenmesi ve hedef alanlara hassas iniş görevlerini yönetir.
* **`network`:** İHA'ların kendi aralarındaki ve Yer İstasyonu ile olan ağ haberleşmesinin mantıksal döngülerini kontrol eder.
* **`gcs`:** Yer Kontrol İstasyonu kullanıcı arayüzünü, telemetri takibini ve yarışmadaki "Yarı Otonom Sürü Kontrolü" görevi için joystick/kumanda entegrasyonunu içerir.
* **`yelpence_msgs`**: Sürü algoritmalarının ihtiyaç duyduğu özel ROS 2 mesaj tiplerini barındırır. Şartnamede geçen görevlerin icrası için İHA'ların kimlik ve konumlarını bildiren SwarmState, okunan şifreleri ileten QRData ve sürüye yeni dizilim komutları veren FormationCommand mesajlarını içerir.

### 4.3. Geliştirme Ortamını Hazırlama
Repoyu bilgisayarınıza klonladıktan sonra projeyi geliştirmeye başlamak için aşağıdaki standart adımları izlemeniz yeterlidir:

**1. Docker Ortamını Başlatma:**
Projeyi VS Code üzerinden açın ve sol alt köşedeki yeşil butona tıklayarak (veya komut paletini kullanarak) "Reopen in Container" seçeneğini seçin. Bu işlem, Ubuntu 24.04, ROS 2 Jazzy, Gazebo ve CycloneDDS barındıran geliştirme ortamımızı otomatik olarak ayağa kaldıracaktır.

**2. Çalışma Alanını Derleme:**
Docker içindeki terminalde çalışma alanının kök dizinine giderek tüm paketleri derleyin:
```bash
cd ~/ros2_ws
colcon build
```

### 4.4. Ortamı Aktif Etme:
Derleme işlemi başarıyla tamamlandıktan sonra, ROS 2'nin paketlerimizi sistemde çalıştırılabilir olarak görmesi için ortamı güncelleyin:

```Bash
source install/setup.bash
```
> source komutunu terminali her yeniden açtığınızda çalıştırmalısınız.

# 5. CI/CD ve Otomatik Test Süreçleri
Yelpençe takımı, kod kalitesini standartlaştırmak ve sisteme hatalı modüllerin dahil edilmesini önlemek amacıyla GitHub Actions destekli Sürekli Entegrasyon (CI) mimarisi kullanmaktadır.

Projeye gönderilen her yeni kod (push veya pull_request işlemi) otomatik olarak aşağıdaki denetimlerden geçer:

- Docker Image Build Test: Eklenen yeni bir kodun veya kütüphanenin, takımın ortak Docker imajının derlenmesini bozup bozmadığı test edilir.
- ROS 2 Build Test: Tüm çalışma alanı (colcon build) Ubuntu 24.04 ve ROS 2 Jazzy standartlarında sıfırdan derlenerek paket çakışmaları denetlenir.
- Birim Testler (Unit Tests): colcon test komutu çalıştırılarak önceden yazılmış özel senaryo testlerinin başarı durumu kontrol edilir.
- Linter ve Stil Denetimleri: Ekip içi tutarlılık için PEP 8 standartları (ament_flake8) ve yorum satırı / dokümantasyon kuralları (ament_pep257) analiz edilir. Kurallara uymayan kodların ana yapıya (main) birleşmesi engellenir.

## 6. Simülasyonu Başlatma
Gazebo'yu doğru grafik ayarlarıyla başlatmak için hazırladığımız otomatik başlatıcıyı kullanın.

Konteynerin içindeyken:

```bash
./scripts/sim_start.sh  
```

Bu komut:

- Fizik motorunu başlatır.
- ROS 2 köprülerini kurar.
- 3D Grafik Arayüzü açar.
- Kapatıldığında tüm süreçleri temizler.

### 6.1. Çalışmayı Durdurma
İşiniz bittiğinde bilgisayarınızı yormaması için sistemi kapatın:

```bash
# Host terminalinde (docker klasöründe):
# Nvidia Kullanıcıları:
docker compose down

# AMD Kullanıcıları:
docker compose -f docker-compose-amd.yml down
```
