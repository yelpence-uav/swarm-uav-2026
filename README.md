# Yelpençe Sürü İHA Projesi - TEKNOFEST 2026

> Bu depo, Yelpençe takımının TEKNOFEST 2026 Sürü İHA Yarışması için geliştirdiği tüm yazılım mimarisini, algoritma setlerini ve dokümantasyon süreçlerini barındıran ana merkezdir. Proje; dinamik sürü formasyonları, otonom görev icrası ve gelişmiş yer kontrol istasyonu entegrasyonuna odaklanmaktadır.


# Kurulum ve Başlangıç 
Bu projenin test, geliştirme ve simülasyon süreçleri izole bir Docker ortamında takip edilmektedir. Kurulum başlığını sonuna kadar uyguladığınızda uçtan uca hazır bir Docker ortamınız olacaktır. 

## 1. Git LFS 
Ağır veri setleri ve simülasyon modelleri Git LFS ile takip edilmektedir.

```bash
# Git LFS'i indirelim
sudo apt install git-lfs

# Etkinleştirmeyi unutmayalım
git lfs install
```

## 2. Repoyu Klonlama
```bash
git clone https://github.com/yelpence-uav/yelpence-2026-swarm

# Tüm submodule'leri çekelim
git submodule update --init --recursive
```

## 3. Geliştirme Ortamı Kurulumu
Bu aşama tümüyle hazır Docker ortamını baştan sona hazır hale getirecektir. Tüm işlemleri ```sudo``` yetkisine sahip bir kullanıcı ile yapmalısınız.

```bash
# Öncelikle docker dizinine gidelim
cd docker

# Gerekli betiklere çalıştırma izni verelim
chmod +x create-docker.sh entrypoint.sh start-docker.sh

# Kurulum betiğini çalıştıralım
./create-docker.sh
```

> Kurulum betiği ilk çalıştırmada internet hızınıza bağlı olarak 10-15 dakika kadar sürebilir. Docker'nın ön bellek yeteneği sayesinde sonraki çalıştırmalar çok daha kısa sürecektir.

> Betik başarıyla tamamlandığında host makineye gerekli paketler kurulur, Docker servisleri hazır hale getirilir, Nvidia Toolkit yapılandırması tamamlanır, Dockerfile referansına göre sanal ortam kurulur ve host makineye gerekli aliaslar tanımlanır.

# Sanal Ortamın Kullanımı 
Bu noktada sanal ortam kullanmak için hazırdır. Aşağıdaki yönergelere uyarak sistemi kullanabilirsiniz.

## 1. Temel Kullanım 
* ```docker ps``` komutu size aktif olarak çalışan ve kaynak tüketen imajları listeler.
* Eğer ```yelpence_swarm_container``` imajını listede göremiyorsanız ```./start-docker.sh``` komutunu kullanarak ortamı ayağa kaldırın. 
* ```./start-docker.sh``` betiği docker dizini içinde çalıştırılır. Bu betik eğer sistem ayaktaysa (```docker ps``` çıktısında listeleniyorsa) çalışmaz ve hata verir.
* Ortam zaten ayaktaysa ```yelpence_gir``` (AMD kullanıyorsanız ```yelpence_gir_amd```) komutu ile sanal ortama girebilirsiniz. docker dizininde olmanız şart değildir sistemin herhangi bir noktasında çalışır.
* Sanal ortam ile işiniz bittiğinde ```yelpence_dur``` komutu ile kapatabilirsiniz. Kapatmadığınız takdirde kaynak tüketmeye devam eder. Eğer Linux ortamını günlük olarak kullanmıyorsanız açık kalabilir. Sistemi çok yük altına sokmaz, oyun gibi sistem isteyen işler yapmadığınız sürece size engel çıkarmaz. 
* Eğer ```yelpence_dur``` komutu ile sistemi durdurduysanız tekrar docker dizinine gidip ```./start-docker.sh``` kodunu çalıştırmanız gerekir.

## 2. Geliştirme Rehberi
* Sanal ortama ilk girişinizde ```entrypoint.sh``` betiği gerekli derlemeleri yapacaktır. ```colcon build``` komutu tüm ortamı tekrar derler ancak önceden derlenmiş kodlar çok kısa sürer. 
* Geliştirme yapmak için sanal ortama SSH kullanarak bağlanmanız gerekir. Host makinede birçok gerekli bağımlılık yoktur dolayısıyla hataları takip etmekte zorlanırsınız.
* SSH bağlantısı için farklı yöntemler vardır. VS Code kullanıyorsanız en iyi çözüm Dev Containers eklentisidir. Jetbrains IDE'leri yerleşik olarak tam donanımlı ve tak çalıştır bir SSH ortamı sunar. Diğer IDE'ler ve editörler bunlar kadar başarılı bir deneyim sunamayabilir. VS Code veya Jetbrains önerilir.
* SSH bilgileri: Kullanıcı Adı: yelpence - Şifre: yelpence2026 - Port: 2222:22
* SSH bağlantısı için hazır ortam sunulmuştur. Her IDE ve yöntemin doğası farklıdır, sorumluluk size aittir.
* Eğer SSH istemiyorsanız Dockerfile da kurulan tüm paket ve bağımlılıkları host makineye de kurmanız gerekir. Bu yöntem kesinlikle önerilmez, problem doğurabilir ve sorumluluk size aittir.
* Sanal ortam ve host makine arasında "volume binding" mevcuttur. Yani siz iki ortam arasında bağlı olan dizinlerde değişiklik yaparsanız anında diğer tarafa yansır. Örneğin sanal ortam içinde src/swarm dizini içinde yaptığınız bir değişiklik anında host makinede uygulanır. Bunun tersi de aynı şekilde çalışmaktadır.
* Hangi dizinlerin bağlı olduğunu docker-compose.yml dosyasında bulabilirsiniz. İhtiyaç halinde ekleme yapabilirsiniz. Bu çok hassas bir işlemdir, yanlış bir ekleme çalışma ortamınızı kötü etkileyebilir. Lütfen dikkatli olun ve docker-compose.yml dosyasındaki talimatlara uyun.
* docker-compose.yml dosyasında yaptığınız bir değişikliğin aynısını docker-compose-amd.yml dosyasına da eklemeniz gerekir.
* Eğer .yml dosyalarında değişiklik yaptıysanız aktif olması için ```yelpence_dur``` ile sanal ortamı durdurup ```start-docker.sh``` betiği ile tekrar ayağa kaldırmalısınız.
* Python bağımlılıkları src/requirements.txt dosyası ile takip edilir. Yeni bir paket gerektiği takdirde talimatlara uyarak ekleme yapabilirsiniz.
* Yeni bir bağımlılık eklediğinize sanal ortamı durdurmanıza gerek yoktur. ```yelpence_gir``` komutu ile girdiğinizde yeni eklenen bağımlılık otomatik olarak kurulur.
* Sanal ortama bir sistem bağımlılığı eklemeniz gerekiyorsa Dockerfile üzerinde değişiklik yapmanız gerekir. Burada yapılan değişikliklerin uygulanması için ```create-docker.sh``` betiği tekrar çalıştırılmalıdır. 


# 🎮 FlySky FS-i6X Kumanda Yapılandırması (Görev 2 - Yarı Otonom Sürü Kontrolü)

TEKNOFEST 2026 Görev 2 kapsamındaki Yarı Otonom Sürü Kontrolü için **FlySky FS-i6X** kumanda kanal ve switch yapılandırması aşağıda belirtilmiştir:

## 1. Kanal ve AUX Eşleştirme Tablosu

| Kanal | Kumanda Elemanı | İşlevi | Değer / Konum Mantığı |
| :--- | :--- | :--- | :--- |
| **Kanal 1** | **Right Stick (X)** | **Roll** (Sağ/Sol Hareket) | Normalize `[-1.0, +1.0]` |
| **Kanal 2** | **Right Stick (Y)** | **Pitch** (İleri/Geri Hareket) | Normalize `[-1.0, +1.0]` |
| **Kanal 3** | **Left Stick (Y)** | **Throttle** (Yükselme/Alçalma) | Normalize `[-1.0, +1.0]` |
| **Kanal 4** | **Left Stick (X)** | **Yaw** (Yönelim / Rotasyon) | Normalize `[-1.0, +1.0]` |
| **Kanal 5 (AUX 1)** | **SwA** (2 Konumlu) | **Deadman Switch (Emniyet Mandalı)** | **Çekili / OFF (0):** Pasif (`command_valid=False` -> `HOLD`)<br>**Basılı / ON (1):** Aktif (`command_valid=True`) |
| **Kanal 6 (AUX 2)** | **SwB** (2 Konumlu) | **Mod Seçimi** | **Konum 0 (OFF):** Sürü Hareket Modu (`MODE_SWARM_MOVEMENT`)<br>**Konum 1 (ON):** Manevra Modu (`MODE_MANEUVER`) |
| **Kanal 7 (AUX 3)** | **SwC** (3 Konumlu) | **Formasyon Seçimi** | **Yukarı (`<-300`):** Ok Başı Formasyonu (`FORMATION_OKBASI`)<br>**Orta (`-300..300`):** V Formasyonu (`FORMATION_V`)<br>**Aşağı (`>300`):** Çizgi Formasyonu (`FORMATION_CIZGI`) |
| **Kanal 8 (AUX 4)** | **SwD** (2 Konumlu) | **Kalkış / İniş Tetikleyici** | **Yukarı Kaldırma (`>300`):** Otonom Kalkış (`Takeoff`)<br>**Aşağı İndirme (`<-300`):** Otonom İniş (`Land`) |

## 2. Kumanda Üzerinden Menü Ayarları

1. **Functions Setup -> Aux. Channels**:
   - `Channel 5`: `SwA`
   - `Channel 6`: `SwB`
   - `Channel 7`: `SwC`
   - `Channel 8`: `SwD`
   - (`OK` tuşuna basılı tutarak kaydedin).
2. **System Setup -> RX Setup -> Output Mode**:
   - Kanal modunu `10 CH` ve `i-BUS` / `PPM` seçin.

> **Kod İçi Değişiklik Konumu**: Kanal ve eşik değerlerini değiştirmek için `src/swarm_state_machine/swarm_state_machine/mode_manager/joystick_interpreter_node.py` içerisindeki `AUX_MODE_CHANNEL`, `AUX_FORMATION_CHANNEL`, `AUX_TAKEOFF_LAND_CHANNEL` sabitlerini güncelleyebilirsiniz.


