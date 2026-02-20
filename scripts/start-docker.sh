#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJE_KOK="$(dirname "$SCRIPT_DIR")"

echo "GUI izinleri tanımlanıyor..."
xhost +local:root

if [ ! -d "$PROJE_KOK/docker" ]; then
    echo "Hata: docker klasorü bulunamadı."
    exit 1
fi

echo "=================================================="
echo "YELPENCE SURU IHA SİSTEMİ BAŞLATILIYOR"
echo "=================================================="
echo "Ekran kartı tipinizi seçin:"
echo "1) NVIDIA "
echo "2) AMD / INTEL"
read -p "Seçiminiz [1-2]: " SECIM

case $SECIM in
    1)
        echo "NVIDIA yapılandırılmasıyla başlatılıyor..."
        docker compose -f "$PROJE_KOK/docker/docker-compose.yml" up -d
        ;;
    2)
        echo "AMD/INTEL yapılandırılmasıyla başlatılıyor..."
        docker compose -f "$PROJE_KOK/docker/docker-compose-amd.yml" up -d
        ;;
    *)
        echo "Geçersiz seçim. İşlem iptal edildi."
        exit 1
        ;;
esac

echo "Çalışma alanı derleniyor (colcon build)..."
docker exec -it yelpence_swarm_container bash -c "source /opt/ros/jazzy/setup.bash && cd ~/ros2_ws && colcon build --symlink-install"

docker exec -it yelpence_swarm_container bash

