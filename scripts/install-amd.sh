#!/bin/bash

# Hata oluştuğunda scriptin durmasını sağlar
set -e

echo "=================================================="
echo "1. DOCKER ENGINE KURULUMU BAŞLIYOR (AMD/INTEL)..."
echo "=================================================="
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "Kullanıcı docker grubuna ekleniyor..."
sudo usermod -aG docker $USER

echo "=================================================="
echo "3. DOSYA İZİNLERİNİN AYARLANMASI VE İMAJ İNŞASI..."
echo "=================================================="
# Distrobox içinde systemctl çalışmayacağı için servis yeniden başlatma adımı atlanmıştır.
# Grup değişikliğinin bu oturumda geçerli olması için 'sg docker' kullanılır.
sg docker -c '
cd docker
chmod +x build.bash entrypoint.sh ../scripts/sim_start.sh
./build.bash
'

echo "=================================================="
echo "AMD/Intel için Kurulum ve İmaj İnşası Tamamlandı!"
echo "Simülasyonu AMD yapılandırmasıyla başlatmak için:"
echo "docker compose -f docker/docker-compose-amd.yml up -d"
echo "=================================================="
