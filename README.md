# Yelpençe Sürü İHA Projesi - TEKNOFEST 2026

> Bu depo, Yelpençe takımının TEKNOFEST 2026 Sürü İHA Yarışması için geliştirdiği tüm yazılım mimarisini, algoritma setlerini ve dokümantasyon süreçlerini barındıran ana merkezdir. Proje; dinamik sürü formasyonları, otonom görev icrası ve gelişmiş yer kontrol istasyonu entegrasyonuna odaklanmaktadır.

---

# Takım Yapısı ve Görev Dağılımı

Yelpençe ekibinin yazılım geliştirme süreçleri, aşağıdaki uzmanlık alanlarına göre dağıtılmıştır:

## **Osman Çevik**
Osman, projenin yazılım mimarisini uçtan uca tasarlayan ve sürünün dijital ikizini yöneten stratejik liderdir. Fiziksel donanım montajından ziyade, sistemin "nasıl çalışması gerektiğine" dair kuralları koyan ve bu kuralların koda dökülmesini sağlayan yönetici rolündedir.

- **Dijital İkiz Kurulumu:** Yarışma şartnamesindeki görevlerin tamamının test edilebileceği ROS tabanlı bir simülasyon ortamı inşa etmek.
- **Algoritma Doğrulama:** Emirhan ve Berk’in yazdığı kodları gerçek İHA’lara yüklemeden önce simülasyonda stres testine sokmak ve hata paylarını raporlamak.
- **Senaryo Testleri:** Yarışma sahasındaki olası aksilikleri (bir İHA'nın düşmesi, sinyal kesilmesi vb.) simüle ederek "Fail-Safe" algoritmalarını denetlemek.
- **Konteynerizasyon:** Tüm geliştirme ortamını Docker imajları haline getirerek; Berk, Emirhan ve Muhammed’in aynı kütüphane versiyonlarıyla çalışmasını sağlamak. Sahadaki RPi'lara tek komutla hatasız kurulum yapılmasını garanti etmek.
- **Versiyon Kontrol Yönetimi:** Takımın ana kod deposunu yönetmek. Kod incelemeleri yaparak standart dışı veya hatalı kodun ana sisteme dahil edilmesini engellemek.
- **CI/CD Süreçleri:** Kod GitHub'a yüklendiğinde otomatik testlerin çalışmasını sağlayacak bir yapı kurgulamak.
- **Düğüm  Tasarımı:** Sistemdeki tüm yazılım bileşenlerinin (görüntü işleme, sürü mantığı, YKİ haberleşmesi) ROS düğümleri arasındaki veri akışını (Topics, Services, Actions) kurgulamak.
- **Veri Standardizasyonu:** İHA’lar arası ve İHA-YKİ arası mesajlaşma formatlarını (.msg, .srv) belirlemek.
- **Namespace ve Hiyerarşi:** Çoklu İHA operasyonunda veri çakışmasını önlemek için sistem hiyerarşisini (örn: /uav1/.., /uav2/..) yapılandırmak.
- **Companion Computer (RPi) Konfigürasyonu:** RPi üzerinde çalışacak Linux dağıtımının (Ubuntu Server vb.) kernel optimizasyonunu, gereksiz servislerin kapatılmasını ve otopilot ile haberleşme köprülerinin (MAVROS/DDS) kurulumunu yönetmek.
- **SD Kart İmaj Yönetimi:** Tüm yazılım katmanlarının kurulu ve konfigüre edilmiş olduğu bir "Master Image" hazırlayarak takıma iletmek.
- **Sistem Sağlığı Takibi:** Uçuş sırasında işlemci yükü, bellek kullanımı ve sıcaklık gibi kritik metrikleri izleyen izleme (monitoring) araçlarını sisteme dahil etmek.
- **Rapor Liderliği:** Ön Tasarım Raporu (ÖTR) ve Kritik Tasarım Raporu (KTR) süreçlerinde teknik mimariyi dokümante etmek ve raporun bilimsel/teknik dilini denetlemek.

## **Eyüp Gök**
Eyüp, sürünün kolektif hareket edebilmesi için gereken kesintisiz veri akışını sağlayan ağ mimarisinin kurucusudur. Araçtan Araca (V2V) ve Araçtan Yer Kontrol İstasyonu’na (V2G) olan tüm dijital köprülerin kurulması, güvenliği ve optimizasyonu onun sorumluluğundadır.

- **Ağ Mimarisi ve Topoloji Yönetimi:** Yarışma sahasında sürünün kullanacağı yerel ağın (Wi-Fi, Telemetri veya RF) kurulumunu yapmak. IP adresleme, port yapılandırması ve veri çakışmalarını önleyen bir ağ hiyerarşisi oluşturmak.
- **İHA-YKİ Haberleşme Protokolü:** Yer Kontrol İstasyonu ile sürü arasındaki veri trafiğini yönetmek. MAVLink paketlerinin veya ROS2 (DDS) mesajlarının kayıpsız bir şekilde Muhammed’in geliştirdiği arayüze ulaşmasını ve arayüzden gelen komutların doğru İHA’lara yönlendirilmesini sağlamak.
- **V2V (Vehicle-to-Vehicle) Haberleşme:** Sürü algoritmalarının çalışabilmesi için İHA’ların birbirlerinin konum ve durum bilgilerini anlık olarak paylaşabileceği düşük gecikmeli (low-latency) haberleşme kanalını stabilize etmek.
- **Sinyal Kalitesi ve RF Yönetimi:** Yarışma alanındaki frekans kirliliğini takip ederek sinyal kopmalarını önlemek. RSSI (Sinyal Gücü) değerlerini izlemek ve sinyal kaybı durumunda devreye girecek haberleşme tabanlı acil durum protokollerini tanımlamak.
- **Veri Güvenliği ve Paket Optimizasyonu:** Şartnamede yer alan otonom görevler sırasında ağ trafiğinin şişmesini önlemek amacıyla, gönderilen veri paketlerini optimize etmek ve sistemin dış müdahalelere karşı güvenliğini sağlamak.
- **Donanımsal Anten ve Modül Entegrasyonu:** Melih ile koordineli çalışarak; telemetri modülleri, Wi-Fi antenleri ve diğer haberleşme birimlerinin en yüksek verimle çalışacağı fiziksel konumlandırmayı ve bağlantıları kontrol etmek.

## **Muhammed Emir Seçer** 
Muhammed, sürü operasyonunun tek bir merkezden izlenmesini, yönetilmesini ve şartnamede belirtilen "Yarı Otonom Kontrol" görevlerinin icra edilmesini sağlayan yazılım platformunun mimarıdır. Python ve Qt (PyQt/PySide) kütüphanelerini kullanarak takımın özgün Yer Kontrol İstasyonu (YKİ) yazılımını geliştirmekle yükümlüdür.

- **Özgün GUI Tasarımı ve Geliştirme:** Yarışma sahasında operatörün (Kaptan) ve hakemlerin sürünün durumunu anlık olarak izleyebileceği, kullanıcı dostu ve performans odaklı bir grafik arayüz (GUI) tasarlamak.
- **Telemetri Görselleştirme:** Eyüp’ün kurduğu haberleşme altyapısından gelen ham verileri (irtifa, hız, batarya seviyesi, GPS koordinatları, bağlantı kalitesi vb.) her bir İHA özelinde ve sürü genelinde anlamlı grafiklere/göstergelere dönüştürmek.
- **Görev 2: Yarı Otonom Sürü Kontrol Modülü:** Şartnamede yer alan "tek bir kontrol birimi üzerinden tüm sürünün yönetilmesi" kuralı gereği, YKİ'ye bağlı joystick veya klavye girdilerini alarak bu komutları sürüdeki tüm araçlara eş zamanlı olarak dağıtacak yazılım mantığını kurmak.
- **Durum Takibi (State Machine) Ekranı:** Sürünün o an hangi aşamada olduğunu (Kalkış yapıldı, QR aranıyor, Formasyon 1 uygulandı, İniş bölgesine yönelindi vb.) görselleştiren bir akış diyagramı/panel hazırlamak.
- **Hata Yönetimi ve Operatör Uyarıları:** Kritik eşiklerin (düşük batarya, sinyal kaybı, otonom rotadan sapma) aşılması durumunda operatörü görsel ve sesli olarak uyaran "Dashboard" sistemini hayata geçirmek.
- **Veri Loglama ve Analiz:** Test uçuşları ve yarışma anındaki tüm telemetri verilerini, daha sonra Osman (Kaptan) tarafından simülasyon doğrulaması ve raporlama için kullanılabilecek standart formatlarda (CSV, JSON veya SQLite) kayıt altına almak.

## **Ahmet Berk Yıldız ve Emirhan Yentur**
İHA’ların çevresel farkındalığından ve şartnamede belirtilen görsel verilerin dijital talimatlara dönüştürülmesinden sorumludur. Sistemin "Gören Gözü" olarak, karmaşık görüntü işleme süreçlerini sürü navigasyonuna girdi sağlayacak şekilde kurgular. Sürünün kolektif hareket stratejilerini belirleyen ve verileri fiziksel uçuş hareketine dönüştüren "Merkezi Akıl" katmanından sorumludur. Dağıtık sürü mimarisinin kararlılığı onun yönetimindedir.

- **QR Kod Tanımlama ve Dekodlama:** Yarışma sahasındaki QR kodların farklı irtifa ve açılardan otonom olarak tespit edilmesi, okunması ve içindeki görev talimatlarının (formasyon değişikliği, manevra vb.) ayıklanması.
- **Hassas İniş (Precision Landing) Algoritmaları:** İHA’ların belirlenen renkli (mavi, kırmızı, sarı) iniş alanlarını yüksek doğrulukla tespit etmesi ve iniş sırasında merkeze olan sapma miktarını (pixel-to-meter) hesaplayarak sisteme iletmesi.
- **Görüntü Ön İşleme ve Optimizasyon:** Sahadaki ışık değişimleri, sarsıntı veya bulanıklık gibi olumsuz etkileri minimize edecek filtreleme tekniklerini (OpenCV/Cuda vb.) uygulamak.
- **Kamera ve Sensör Kalibrasyonu:** Kamera FOV değerlerini şartnameye uygun tutmak ve lens bozulmalarını (distortion) yazılımsal olarak gidermek.
- **Dağıtık Sürü ve Formasyon Kontrolü:** İHA’ların birbirlerine göre konumlanarak istenilen geometrik şekilleri (V, Çizgi, Daire vb.) otonom olarak almasını ve korumasını sağlayan algoritmaları geliştirmek.
- **Dinamik Rota Planlama:** Berk tarafından iletilen görev talimatlarına göre sürünün yeni rotasını anlık olarak hesaplamak ve tüm birimlere paylaştırmak.
- **Çarpışma Önleme ve Güvenlik Zarfları:** Sürü üyelerinin birbirleriyle veya engellerle temasını önleyen matematiksel modelleri (Sanal Potansiyel Alanlar vb.) sisteme entegre etmek.
- **Sürü Üyesi Yönetimi:** Şartnamede istenen "sürüye yeni birey ekleme/çıkarma" senaryolarında, sürünün kararlılığını bozmadan otonom yeniden yapılandırmayı (reconfiguration) sağlamak.
- **Görev Durum Makinesi (Mission State Machine):** İHA'nın "Kalkış -> QR Arama -> Görev İcrası -> İniş" döngüsündeki tüm geçiş mantığını beraber kurgularlar.
- **ROS Mesaj Yapılandırması:** Görüntü işleme düğümü (node) ile sürü kontrol düğümü arasındaki haberleşme protokollerini Osman'ın (Kaptan) belirlediği mimari çerçevesinde ortaklaşa optimize ederler.
- **Hata Yönetimi (Fail-Safe):** Görsel temasın kaybolması veya sürü bütünlüğünün bozulması durumunda devreye girecek olan "Yazılımsal Acil Durum" senaryolarını birlikte test ederler.

---

# Dizin Yapisi

```text
yelpence-2026-swarm/
├── docs/                   # Şartname, raporlar ve teknik dokümantasyon
├── src/                    # Kaynak kodların ana dizini
│   ├── gcs/                # Yer Kontrol istasyonu modülleri
│   ├── swarm/              # Sürü yönetim ve formasyon mantığı
│   ├── vision/             # QR kod ve görüntü işleme algoritmalari
│   ├── network/            # MAVLink ve haberleşme köprüleri
│   └── msgs/               # Özel ROS2 mesaj tanımları
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

## 3. Geliştirme Ortamı Kurulumu
Projemiz, "Bende çalışıyor sende çalışmıyor" sorununu önlemek için Docker konteynerleri üzerinde çalışmaktadır. Aşağıdaki adımları sırasıyla uygulayarak kurulumu tamamlayınız.

> Not: Bu komutlar Ubuntu 22.04 ve 24.04 ile uyumludur.

### 3.1. Docker Engine Kurulumu
Docker'ı kurmak ve sudo kullanmadan çalıştırabilmek için:

```bash
# 1. Gerekli başlangıç paketlerini kurun
sudo apt-get update
sudo apt-get install ca-certificates curl

# 2. Docker'ın resmi GPG anahtarını ekleyin
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# 3. Docker deposunu kaynaklara ekleyin
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 4. Docker'ı yükleyin
sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 5. Kullanıcınızı 'docker' grubuna ekleyin
# Bu işlem sayesinde her seferinde 'sudo' yazmak zorunda kalmazsınız.
sudo usermod -aG docker $USER

# 6. Grup değişikliğini aktif edin
newgrp docker
```

### 3.2. NVIDIA Container Toolkit Kurulumu (Sadece Nvidia İçin)
Simülasyonun ekran kartını kullanabilmesi ve "Siyah Ekran" hatası vermemesi için bu adım zorunludur. AMD kullanıcıları **3.3. Dosya İzinleri**  bölümüne geçebilir.

```bash
# 1. Nvidia deposunu ekleyin
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 2. Toolkit'i yükleyin
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 3. Docker'ı Nvidia sürücüsüyle yapılandırın
sudo nvidia-ctk runtime configure --runtime=docker

# 4. Docker servisini yeniden başlatın
sudo systemctl restart docker

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
> Not: İnternet hızınıza bağlı olarak ilk kurulum 5-10 dakika sürebilir.

### 3.5. Sanal Ortamı Başlatma
Kurulum bittikten sonra sistemi ayağa kaldırın:
```Bash
# 1. GUI izinlerini tazeleyin
xhost +local:root

# 2. Konteyneri başlatın
# Nvidia Kullanıcıları: 
docker compose up -d

# AMD Kullanıcıları:
docker compose -f docker-compose-amd.yml up -d
```
## 4. Kullanım ve Simülasyon
### 4.1. Geliştirme Ortamına Giriş
Sanal bilgisayarın içine girmek için:

```bash
docker exec -it yelpence_swarm_container bash
```
> Artık içeridesiniz! ros2 topic list gibi komutlar çalışacaktır.

### 4.2. Simülasyonu Başlatma
Gazebo'yu doğru grafik ayarlarıyla başlatmak için hazırladığımız otomatik başlatıcıyı kullanın.

Konteynerin içindeyken:

```bash
./scripts/sim_start.sh  
```

Bu komut:

- Fizik motorunu (Server) başlatır.
- ROS 2 köprülerini kurar.
- 3D Grafik Arayüzü (GUI) açar.
- Kapatıldığında tüm süreçleri temizler.

### 4.3. Çalışmayı Durdurma
İşiniz bittiğinde bilgisayarınızı yormaması için sistemi kapatın:

```bash
# Host terminalinde (docker klasöründe):
# Nvidia Kullanıcıları:
docker compose down

# AMD Kullanıcıları:
docker compose -f docker-compose-amd.yml down
```

## 5. Sorun Giderme

| Sorun | Çözüm |
| :--- | :--- |
| `permission denied` hatası | `chmod +x` komutunu (Bölüm 3.3) tekrar uygulayın. |
| Gazebo Siyah Ekran | Host makinede `xhost +local:root` komutunu çalıştırın. |
| "Docker command not found" | `newgrp docker` komutunu çalıştırın veya bilgisayarı yeniden başlatın. |
| GPU Görünmüyor | `nvidia-smi` komutunu host makinede deneyin, Bölüm 3.2'yi tekrarlayın. |
