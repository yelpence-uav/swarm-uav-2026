#!/bin/bash
# Hata durumunda betiğin çalışmasını durdur
set -e

echo -e "\n [YELPENÇE] Görev Bilgisayarı Kurulum ve Derleme Betiği Başlıyor...\n"

# ==========================================
# 1. KÖK DİZİNE GEÇİŞ (ÇOK ÖNEMLİ)
# ==========================================
# Betik nereden çağrılırsa çağrılsın, kendini bulup 2 üst klasöre (proje köküne) gider.
cd "$(dirname "$0")/../.."
echo " Proje kök dizinine geçildi: $(pwd)"

# ==========================================
# 2. REPO VE SUBMODULE GÜNCELLEMESİ
# ==========================================
echo " Repo güncelleniyor (pull)..."
# Mevcut repoyu son değişikliklerle sığ (tarihçesiz) bir şekilde güncelle
git pull --depth 1

echo " Alt modüller (submodules) ayarlanıyor..."
# DİKKAT: px4_autopilot modülünün çekilmesini/güncellenmesini tamamen engelle
git config submodule."src/px4_autopilot".update none

# Kalan alt modülleri minimal derinlikte çek (XRCE/px4_msgs kaldirildi)
git submodule update --init --recursive --depth 1

echo " Kod tabanı en hafif haliyle hazırlandı."

# ==========================================
# 3. DOCKERIGNORE DEĞİŞİMİ
# ==========================================
echo " RPi için agresif .dockerignore filtreleri devreye alınıyor..."
# Masaüstü geliştirme ortamının orijinal .dockerignore dosyasını yedekle
if [ -f ".dockerignore" ]; then
  mv .dockerignore .dockerignore.backup
fi

# RPi için hazırladığımız kısıtlamaları kopyala
cp docker/rpi/rpi-ignore.txt .dockerignore

# ==========================================
# 4. DOCKER İMAJ DERLEMESİ
# ==========================================
echo " Docker imajı derleniyor (Multi-Stage Build)..."
# Konumumuz zaten kök dizin olduğu için build komutu sorunsuz çalışacaktır
docker build -t yelpence-flight-system -f docker/rpi/Dockerfile.rpi .

# ==========================================
# 5. ÇEVRE TEMİZLİĞİ
# ==========================================
echo " Derleme bitti, orijinal geliştirme ortamı geri yükleniyor..."
# İşlem bitince geliştirme ortamının .dockerignore dosyasını geri getir
if [ -f ".dockerignore.backup" ]; then
  mv .dockerignore.backup .dockerignore
fi

echo -e "\n [BAŞARILI] Yelpençe Uçuş İmajı (yelpence-flight-system) RPi 4 üzerinde uçuşa hazır!\n"
