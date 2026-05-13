# Raspberry Pi Host İşletim Sistemi Kurulum ve Optimizasyon Kılavuzu

Bu talimatname, kısıtlı donanım kaynaklarımızı en verimli şekilde kullanmak ve arka planda gereksiz RAM/CPU tüketen hiçbir servis barındırmayan temiz bir ana sistem oluşturmak amacıyla hazırlanmıştır. Cihaz tamamen kafasız ve grafik arayüzsüz çalışacaktır.

## Aşama 1: İmaj Yazdırma ve İlk Ayarlar
1. Bilgisayarınıza Raspberry Pi Imager uygulamasını indirin ve açın.
2. OS Seçimi: Other general-purpose OS -> Ubuntu -> Ubuntu Server 24.04 LTS (64-bit) seçeneğini seçin. (Masaüstü/GUI barındıran imajlara kıyasla doğrudan 400-500 MB RAM kazancımız olacaktır).
3. Yazdırma işlemine geçmeden önce sağ alttaki Gelişmiş Ayarlar (Çark simgesi) menüsüne tıklayın:
    * SSH'ı aktif edin.
    * Sahanın/laboratuvarın Wi-Fi bilgilerini girin.
    * Sürü koordinasyonu için standart bir kullanıcı adı ve şifre belirleyin.

4. İmajı SD karta yazdırın. Bu ayarlar sayesinde cihazı monitöre bağlamadan doğrudan ağ üzerinden kontrol edebileceğiz.

## Aşama 2: Donanımsal Kaynakların Kısılması (config.txt)
Yazdırma işlemi bittikten sonra SD kartı bilgisayarınızdan çıkarmadan önce boot dizinine girin ve config.txt (veya Ubuntu altındaki adıyla usercfg.txt) dosyasını bir metin editörüyle açarak en altına şu satırları ekleyin:

```
# Grafik birimine (GPU) ayrılan RAM'i minimuma çekerek ana sisteme bırakıyoruz
gpu_mem=16

# İHA üzerinde kullanmayacağımız donanımları kapatıp CPU ve RAM kazanıyoruz
dtoverlay=disable-bt
dtparam=audio=off
```
SD kartı güvenle çıkarıp Raspberry Pi 4'e takın ve cihazı başlatın.

## Aşama 3: zram Kurulumu (Sıkıştırılmış Takas Alanı)
Pi 4 ayağa kalktıktan sonra SSH ile terminaline bağlanın. Fiziksel RAM sınırına takılmamak ve geleneksel SD kart tabanlı yavaş swap alanından kurtulmak için bellekte sıkıştırma yapan zram mekanizmasını kurun:

```bash
sudo apt update && sudo apt install zram-config -y
```
Bu paket, RAM yüklerini arka planda otomatik sıkıştırarak 4GB'lık alanımızı çok daha efektif kullanmamızı sağlayacaktır.

## Aşama 4: Ağ ve CycloneDDS Ara Bellek Ayarları
Sürü içi haberleşmede kullandığımız CycloneDDS altyapısının, Docker katmanları arasından geçerken yüksek veri hızlarında Linux çekirdeğinin ara bellek limitlerine takılmasını engellemek için şu optimizasyonu uygulayın:

1. Terminalde /etc/sysctl.conf dosyasını açın:

```bash
sudo nano /etc/sysctl.conf
```

2. Dosyanın en altına şu iki satırı ekleyin ve kaydedip çıkın:

```
net.core.rmem_max=2147483647
net.core.wmem_max=2147483647
```

3. Ayarları hemen aktif etmek için şu komutu koşturun:

```bash
sudo sysctl -p
```

# Aşama 5: Minimal Docker Kurulumu ve Log Sınırlandırması
1. Sisteme Docker motorunu kurun:

```bash
sudo apt install docker.io -y
```

2. Docker konteynerlerinin çalışma anında ürettiği logların belleği ve diski şişirmemesi için log limit kuralı eklememiz gerekiyor. /etc/docker/daemon.json dosyasını oluşturun:


```bash
sudo nano /etc/docker/daemon.json
```

3. İçerisine aynen şu konfigürasyonu yapıştırıp kaydedin:

```JSON
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

4. Docker servisini yeniden başlatarak ayarları uygulayın:

```bash
sudo systemctl restart docker
```

Not: Bu adımlar tamamlandığında elinizde sadece sürü görevlerine odaklanmış kararlı ve tertemiz bir ana işletim sistemi kalacaktır. Bu aşamada SD kartın yedeğini (.img veya .iso olarak) bilgisayarınıza alırsanız, sürüdeki diğer 2 İHA'nın işletim sistemini saniyeler içinde bu imajı klonlayarak hazır hale getirebilirsiniz. Burada tarif edilen yapı kararsız olabilir veya eksikler olabilir. Kurulum sırasında oluşan hatalar tamamlanmalıdır.

# Aşama 6: Yelpençe Uçuş İmajının (Docker) Derlenmesi
İmajın uçtan uca hazır hale gelmesi için aşağıdaki kodları çalıştırın.

```bash
git clone https://github.com/yelpence-uav/yelpence-2026-swarm

cd yelpence-2026-swarm/docker/rpi

chmod +x build_rpi.sh

./build_rpi.sh
```

Not: Bu işlem çok aşamalı derleme yaptığı için Pi 4 üzerinde biraz vakit alacaktır. Sadece ilk kurulumda yapılır.

# Aşama 7: Sahada Konteyneri Çalıştırma (Production Run)
Derleme tamamlandığında elimizde yelpence-flight-system adında uçuşa hazır bir imaj olacak. İHA'ya güç verildiğinde donanımlarla (Pixhawk ve Kamera) konuşabilmesi ve gecikmesiz haberleşebilmesi için konteyneri şu komutla başlatın:

```bash
docker run -it --rm \
  --network host \
  --device=/dev/ttyAMA0 \
  --device=/dev/video0 \
  yelpence-flight-system
```

Parametrelerin Anlamları:

* --network host: CycloneDDS'in RPi'nin Wi-Fi/ESP arayüzünü gecikmesiz kullanmasını sağlar (NAT izolasyonunu kaldırır).
* --device=/dev/ttyAMA0: Pixhawk (Telemetry) UART pinlerini konteynere doğrudan bağlar. (Not: TTY portu sizin bağlantı şeklinize göre ttyUSB0 vs. olarak değişebilir).
* --device=/dev/video0: Görüntü işleme ve QR tespiti için Arducam HQ kamerayı konteynere bağlar.

Ekranda yeşil renkte "[YELPENÇE] Görev Bilgisayarı Konteyneri Hazır. İyi uçuşlar!" yazısını gördüğünüzde sistem otonom görev için emrinizi bekliyor demektir.
