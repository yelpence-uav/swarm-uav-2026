# Yelpençe Sürü İHA Projesi - TEKNOFEST 2026

> Bu depo, Yelpençe takımının TEKNOFEST 2026 Sürü İHA Yarışması için geliştirdiği tüm yazılım mimarisini, algoritma setlerini ve dokümantasyon süreçlerini barındıran ana merkezdir. Proje; dinamik sürü formasyonları, otonom görev icrası ve gelişmiş yer kontrol istasyonu entegrasyonuna odaklanmaktadır.

# İçindekiler Tablosu
* [Dizin Yapısı](#dizin-yapısı)
* [Kurulum ve Başlangıç](#kurulum-ve-başlangıç)
* [Sanal Ortamın Kullanımı](#sanal-ortamın-kullanımı)

# Dizin Yapısı
yelpence-2026-swarm
├── .github/        # CI/CD süreçlerini ve kod kalitesini denetleyen otomatik iş akışlarını içerir.
├── docker/         # Geliştirme ortamının tüm platformlarda izole ve tutarlı çalışmasını sağlayan yapılandırmaları barındırır.
├── scripts/        # Görev senaryoları üretme ve sistemi hızlıca ayağa kaldırma gibi operasyonel yardımcı betikleri içerir.
├── sim/            # İHA'ların fiziksel modellerini ve yarışma görevlerinin icra edileceği simülasyon dünyalarını barındırır.
└── src/            # Sürü zekası, haberleşme protokolleri ve otonom kontrol algoritmalarımızın bulunduğu ana kaynak kod dizinidir.

# Kurulum ve Başlangıç 
Bu projenin test, geliştirme ve simülasyon süreçleri izole bir Docker ortamında takip edilmektedir. Kurulum başlığını sonuna kadar uyguladığınızda uçtan uca hazır bir Docker ortamınız olacaktır. 

> Projede tam verimle çalışabilmek için Ubuntu 22.04 veya üstü bir sistem sahip olmalısınız. Herhangi Debian veya Arch temelli bir dağıtım da uygundur ancak en hızlı ve etkili sonuç için Ubuntu'yu tercih ediniz.

## 1. Git LFS 
Ağır veri setleri ve simülasyon modelleri Git LFS ile takip edilmektedir.

```bash
# Git LFS'i indirelim
sudo apt install git-lfs

# Etkinleştirmeyi unutmayalım
git lfs install
```
> "Git LFS initialized" yazısını görmeniz lazım.

## 2. Repoyu Klonlama
```bash
git clone https://github.com/yelpence-uav/yelpence-2026-swarm
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
* Sanal ortama ilk girişinizde hiçbir kod derlenmiş vaziyette değildir. ```colcon build``` komutu ile tüm düğümleri derlemeniz gerekir. Yeni bir kod eklediğinizde çalışması için derlemeniz gerekir. ```colcon build``` komutu tüm ortamı tekrar derler ancak önceden derlenmiş kodlar çok kısa sürer. 
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

## Simülasyon Rehberi
* Sanal ortamda Gazebo Harmonic tüm yapılandırması hazır şekilde gelmektedir. Simülasyon ile ilgili proje dosyaları sim/ dizini içinde bulunur.
* Simülasyon dünyaları hazır şekilde gelmez. Her biri scripts/ içerisindeki scriptler ile ```base_world.sdf``` dosyasını temel alarak üretilir.

Yeni kurulmuş bir ortamda aşağıdaki komutları çalıştırarak dünyaları hazır hale getirebilirsiniz.
```bash
python3 scripts/generate_task1_world.py     # task1_dynamic_swarm.sdf
python3 sctipts/generate_task2_worlds.py    # task2 dünyaları
```
> DİKKAT! Dünyalar üzerinde yaptığınız değişiklikler bu komutların çalışması ile kaybolabilir. Eğer dünyalar üzerinde kalıcı değişiklik yapmak istiyorsanız buradaki scriptleri güncellemeniz gerekir.

Bu dünyaları Gazebo ortamında çalıştırmak için aşağıdaki komutları kullanabilirsiniz.
```bash
gz sim /sim/worlds/[DÜNYANIN ADI]
```

