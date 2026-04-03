#!/bin/bash

# ---------------------------------------------------------
# YELPENÇE SÜRÜ İHA - KONTEYNER BAŞLATICI
# ---------------------------------------------------------

CONTAINER_NAME="yelpence_swarm_container"
CONTAINER_NAME_AMD="yelpence_swarm_container_amd"

# Çalışan konteyner kontrolü
if [ "$(docker ps -q -f name=^/${CONTAINER_NAME}$ -f status=running)" ] ||
    [ "$(docker ps -q -f name=^/${CONTAINER_NAME_AMD}$ -f status=running)" ]; then
    echo -e "\e[31m[HATA] Yelpençe konteyneri zaten çalışıyor!\e[0m"
    echo -e "İçeri girmek için: \e[32mdocker exec -it <konteyner_adi> /usr/local/bin/entrypoint.sh /bin/bash\e[0m"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJE_KOK="$(dirname "$SCRIPT_DIR")"

# GUI izinlerini ver
xhost +local:root >/dev/null 2>&1

echo -e "\n=================================================="
echo -e "   YELPENÇE SÜRÜ İHA SİSTEMİ BAŞLATILIYOR"
echo -e "=================================================="

while true; do
    echo -e "\nEkran kartı tipinizi seçin:"
    echo -e "1) NVIDIA"
    echo -e "2) AMD / INTEL"
    echo -e "3) İptal ve Çıkış"
    read -p "Seçiminiz [1-3]: " SECIM

    case $SECIM in
    1)
        echo -e "\e[34mNVIDIA yapılandırılmasıyla başlatılıyor...\e[0m"
        docker compose -f "$PROJE_KOK/docker/docker-compose.yml" up -d
        TARGET_NAME=$CONTAINER_NAME
        break
        ;;
    2)
        echo -e "\e[34mAMD/INTEL yapılandırılmasıyla başlatılıyor...\e[0m"
        docker compose -f "$PROJE_KOK/docker/docker-compose-amd.yml" up -d
        TARGET_NAME=$CONTAINER_NAME_AMD
        break
        ;;
    3)
        echo "Çıkış yapılıyor."
        exit 0
        ;;
    *)
        echo -e "\e[31mGeçersiz seçim!\e[0m"
        ;;
    esac
done

echo -e "\n\e[32m[BAŞARILI] Konteyner arka planda başlatıldı.\e[0m"
echo -e "--------------------------------------------------"
echo -e "İçeri girmek için şu komutu kullanın (Entrypoint otomatik tetiklenir):"
echo -e "\e[33m  docker exec -it $TARGET_NAME /usr/local/bin/entrypoint.sh /bin/bash\e[0m"
echo -e "--------------------------------------------------\n"
