#!/bin/bash
set -e

echo -e "\n [YELPENÇE] Görev Bilgisayarı Kurulum ve Derleme Betiği Başlıyor...\n"

# Proje kök dizinine geçiş
cd "$(dirname "$0")/../.."
echo " Proje kök dizinine geçildi: $(pwd)"

# Repo ve alt modül güncellemesi
echo " Repo güncelleniyor..."
git pull --depth 1

echo " Alt modüller ayarlanıyor..."
git config submodule."src/px4_autopilot".update none
git submodule update --init --recursive --depth 1

echo " Kod tabanı hazırlandı."

# Dockerignore ayarlaması
echo " RPi için .dockerignore filtreleri devreye alınıyor..."
if [ -f ".dockerignore" ]; then
  mv .dockerignore .dockerignore.backup
fi

cp docker/rpi/rpi-ignore.txt .dockerignore

# Docker imaj derlemesi
echo " Docker imajı derleniyor..."
docker build -t yelpence-flight-system -f docker/rpi/Dockerfile.rpi .

# Çevre temizliği
echo " Orijinal geliştirme ortamı geri yükleniyor..."
if [ -f ".dockerignore.backup" ]; then
  mv .dockerignore.backup .dockerignore
fi

echo -e "\n [BAŞARILI] Yelpençe Uçuş İmajı (yelpence-flight-system) RPi üzerinde uçuşa hazır!\n"
