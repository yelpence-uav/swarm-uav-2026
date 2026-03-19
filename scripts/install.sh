#!/bin/bash

# Hata oluştuğunda scriptin durmasını sağlar
set -e

echo "=================================================="
echo "1. DOCKER ENGINE KURULUMU BAŞLIYOR..."
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
echo "2. NVIDIA CONTAINER TOOLKIT KURULUMU BAŞLIYOR..."
echo "=================================================="
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

echo "=================================================="
echo "3. DOSYA İZİNLERİNİN AYARLANMASI VE DOCKER İMAJININ İNŞASI..."
echo "=================================================="
sg docker -c '
cd docker
chmod +x build.bash entrypoint.sh ../scripts/start_swarm.sh
./build.bash
'

echo "=================================================="
echo "Tüm kurulum ve imaj inşa işlemleri başarıyla tamamlandı."
echo "Terminalinizin grup yetkilerini tam olarak algılaması için lütfen mevcut terminali kapatıp yeni bir terminal açın veya 'newgrp docker' komutunu çalıştırın."
echo "=================================================="
