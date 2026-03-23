#!/bin/bash
# Yelpençe Sürü İHA - Docker Başlatma Scripti v9.4
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJE_KOK="$(dirname "$SCRIPT_DIR")"

echo "GUI izinleri tanımlanıyor..."
xhost +local:root > /dev/null 2>&1 || true

# GPU GID Tespit ve Atama
VIDEO_GID_HOST=$(getent group video | cut -d: -f3 2>/dev/null || echo "44")
RENDER_GID_HOST=$(getent group render | cut -d: -f3 2>/dev/null || echo "107")
export VIDEO_GID=${VIDEO_GID_HOST:-44}
export RENDER_GID=${RENDER_GID_HOST:-107}
[ "$VIDEO_GID" = "0" ] && export VIDEO_GID=999
[ "$RENDER_GID" = "0" ] && export RENDER_GID=998

echo "=================================================="
echo "YELPENCE SURU IHA SİSTEMİ BAŞLATILIYOR"
echo "=================================================="
echo "Ekran kartı tipinizi seçin:"
echo "1) NVIDIA"
echo "2) AMD / INTEL"
read -p "Seçiminiz [1-2]: " SECIM

case "$SECIM" in
    1)
        echo "NVIDIA yapılandırılmasıyla başlatılıyor..."
        docker compose -f "$PROJE_KOK/docker/docker-compose.yml" up -d
        ;;
    2)
        echo "AMD/INTEL yapılandırılmasıyla başlatılıyor..."
        docker compose -f "$PROJE_KOK/docker/docker-compose-amd.yml" up -d
        ;;
    *)
        echo "Geçersiz seçim."
        exit 1
        ;;
esac

# ── DIŞARIDAN MÜDAHALE: Grup Hatasını Kökten Çöz ──
# Konteyner içine girmeden önce ROOT yetkisiyle grupları tanımlıyoruz.
# Bu sayede kullanıcı girdiğinde 'groups' hatası asla oluşmaz.
echo "Grup izinleri optimize ediliyor..."
docker exec -u root yelpence_swarm_container bash -c "
    getent group $VIDEO_GID >/dev/null || groupadd -g $VIDEO_GID host_video 2>/dev/null;
    getent group $RENDER_GID >/dev/null || groupadd -g $RENDER_GID host_render 2>/dev/null;
" || true

echo "Çalışma alanı derleniyor..."
docker exec -it yelpence_swarm_container bash -c "source /opt/ros/jazzy/setup.bash && cd ~/ros2_ws && colcon build --symlink-install"

echo "Sisteme giriş yapılıyor..."
docker exec -it yelpence_swarm_container bash
