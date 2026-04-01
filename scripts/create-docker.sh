#!/bin/bash

# Bu betik Docker ortamını baştan sona hazır hale getirir. Bağımlılıklar ve gerekli paketler kurulur, donanıma ve dağıtıma özel ayarlar yapılır.

set -e

echo -e "YELPENÇE DOCKER ORTAMI KURULUMU BAŞLIYOR..."
sleep 1

while true; do

    echo -e "\nDAĞITIMINIZI SEÇİN:"
    echo -e "-------------------"
    echo -e "1) Arch Linux"
    echo -e "2) Ubuntu"
    echo -e "-------------------"
    read -p "Seçiminiz [1-2]: " SECIM

    case $SECIM in
    1)
        echo -e "\nArch Linux seçildi. Kuruluma devam ediliyor..."
        sleep 1

        echo -e "\nDOCKER ENGINE VE NVIDIA TOOLKIT KURULUMU BAŞLIYOR"

        sudo pacman -S --noconfirm docker docker-compose
        sudo systemctl enable --now docker.service
        sudo usermod -aG docker $USER
        sudo pacman -S --noconfirm nvidia-container-toolkit
        sudo nvidia-ctk runtime configure --runtime=docker
        sudo systemctl restart docker

        break
        ;;
    2)
        echo -e "\nUbuntu seçildi. Kuruluma devam ediliyor..."
        sleep 1

        sudo apt-get update
        sudo apt-get install -y ca-certificates curl gpg
        sudo install -m 0755 -d /etc/apt/keyrings
        sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
        sudo chmod a+r /etc/apt/keyrings/docker.asc

        echo \
            "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
            $(. /etc/os-release && echo "$VERSION_CODENAME") stable" |
            sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

        sudo apt-get update
        sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        sudo usermod -aG docker $USER
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list |
            sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' |
            sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
        sudo apt-get update
        sudo apt-get install -y nvidia-container-toolkit
        sudo nvidia-ctk runtime configure --runtime=docker
        sudo systemctl restart docker

        break
        ;;
    *)
        echo -e "\nGeçersiz seçim. Lütfen tekrar deneyin."
        sleep 3
        ;;
    esac
done

echo -e "\nPaket indirmeleri ve docker servis ayarları başarıyla tamamlandı. Kuruluma devam ediliyor..."
sleep 1

echo -e "\nDOCKER İMAJININ İNŞASI BAŞLIYOR"
sleep 1

sg docker -c '
cd ../docker/

CURRENT_UID=$(id -u)
CURRENT_GID=$(id -g)
CURRENT_USER=$(whoami)

echo -e "\n---------------------------------------"
echo -e "Tespit Edilen Kullanıcı : $CURRENT_USER"
echo -e "Kullanıcı ID (UID)      : $CURRENT_UID"
echo -e "Grup ID (GID)           : $CURRENT_GID"
echo -e "---------------------------------------"
sleep 1

docker compose build \
    --build-arg USER_UID=$CURRENT_UID \
    --build-arg USER_GID=$CURRENT_GID

echo -e "\nKURULUM BAŞARIYLA TAMAMLANDI"
sleep 1
echo -e "Değişikliklerin geçerli olması için mevcut terminali kapatıp yenisini açın."
'
