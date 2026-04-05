#!/bin/bash

# Bu betik Docker ortamını baştan sona hazır hale getirir. Bağımlılıklar ve gerekli paketler kurulur, donanıma ve dağıtıma özel ayarlar yapılır.

set -e

echo -e "\033[0;36m[BİLGİ] YELPENÇE DOCKER ORTAMI KURULUMU BAŞLIYOR...\033[0m"
sleep 1

SCRIPT_DIR="$(pwd)"
PROJE_KOK="$(dirname "$SCRIPT_DIR")"

while true; do

    echo -e "DAĞITIMINIZI SEÇİN:"
    echo -e "-------------------"
    echo -e "1) Arch Linux"
    echo -e "2) Ubuntu"
    echo -e "-------------------"
    read -p "Seçiminiz [1-2]: " SECIM

    case $SECIM in
    1)
        echo -e "\033[0;36m[BİLGİ] ARCH LINUX SEÇİLDİ. KURULUMA DEVAM EDİLİYOR...\033[0m"
        sleep 1

        echo -e "\033[0;36m[BİLGİ] DOCKER ENGINE VE NVIDIA TOOLKIT KURULUMU BAŞLIYOR...\033[0m"

        sudo pacman -S --noconfirm --needed docker docker-compose python-pip git
        sudo systemctl enable --now docker.service
        sudo usermod -aG docker $USER
        sudo pacman -S --noconfirm --needed nvidia-container-toolkit
        sudo nvidia-ctk runtime configure --runtime=docker
        sudo systemctl restart docker

        break
        ;;
    2)
        echo -e "\033[0;36m[BİLGİ] UBUNTU SEÇİLDİ. KURULUMA DEVAM EDİLİYOR...\033[0m"
        sleep 1

        sudo apt-get update
        sudo apt-get install -y ca-certificates curl gpg python3-pip python3-venv git
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
        echo -e "\033[0;31m[HATA] GEÇERSİZ SEÇİM. LÜTFEN TEKRAR DENEYİN.\033[0m"
        sleep 1
        ;;
    esac
done

echo -e "\033[0;36m[BİLGİ] PAKETLER İNDİRİLDİ. KURULUMA DEVAM EDİLİYOR...\033[0m"
sleep 1

sg docker -c '
cd ../docker/

CURRENT_UID=$(id -u)
CURRENT_GID=$(id -g)
CURRENT_USER=$(whoami)

echo -e "\033[0;36m[BİLGİ] KULLANICI YAPILANDIRMASI UYGULANDI. KURULUMA DEVAM EDİLİYOR...\033[0m"
sleep 1

docker compose build \
    --build-arg USER_UID=$CURRENT_UID \
    --build-arg USER_GID=$CURRENT_GID

echo -e "\033[0;36m[BİLGİ] KISAYOLLAR .bashrc DOSYASINA EKLENİYOR...\033[0m"
sleep 1
BASHRC_PATH="$HOME/.bashrc"
sed -i '/# YELPENCE_START/,/# YELPENCE_END/d' "$BASHRC_PATH"

cat << EOF >> "$BASHRC_PATH"
# YELPENCE_START
alias yelpence_durdur='docker compose -f $PROJE_KOK/docker/docker-compose.yml down && docker compose -f $PROJE_KOK/docker/docker-compose-amd.yml down'
alias yelpence_gir='docker exec -it yelpence_swarm_container /usr/local/bin/entrypoint.sh /bin/bash'
alias yelpence_gir_amd='docker exec -it yelpence_swarm_container_amd /usr/local/bin/entrypoint.sh /bin/bash'
# YELPENCE_END
EOF

echo -e "\033[0;32m [TAMAM] KURULUM BAŞARIYLA TAMAMLANDI. DEVAM ETMEK İÇİN MEVCUT TERMİNALİNİZİ KAPATIP YENİSİNİ AÇIN.\033[0m"
'
