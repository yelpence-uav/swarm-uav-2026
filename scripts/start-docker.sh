#!/bin/bash
# Yelpençe Sürü İHA - Docker Başlatma Scripti (Arch Linux Optimize Edilmiş)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJE_KOK="$(dirname "$SCRIPT_DIR")"

echo "=================================================="
echo "YELPENCE SURU IHA SİSTEMİ HAZIRLANIYOR"
echo "=================================================="

# 1. GUI İzinlerini Ayarla
xhost +local:root >/dev/null 2>&1 || true

# 2. Host Makinedeki GPU GID'lerini Tespit Et
# Arch Linux'ta 'render' grubu genelde 107'dir.
VIDEO_GID_HOST=$(getent group video | cut -d: -f3 2>/dev/null || echo "44")
RENDER_GID_HOST=$(getent group render | cut -d: -f3 2>/dev/null || echo "107")

export VIDEO_GID=${VIDEO_GID_HOST:-44}
export RENDER_GID=${RENDER_GID_HOST:-107}

# 3. Ekran Kartı Seçimi ve Başlatma
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
    echo "Geçersiz seçim. Çıkılıyor..."
    exit 1
    ;;
esac

echo "--------------------------------------------------"
echo "Grup izinleri ve dosya yetkileri optimize ediliyor..."
echo "--------------------------------------------------"

# 4. Kritik Yetki Düzeltmeleri (ROOT olarak çalıştırılır)
# Bu kısım 'groups: cannot find name' ve 'Permission denied' hatalarını çözer.
docker exec -u root yelpence_swarm_container bash -c "
    # Eksik grupları isimle tanımla
    getent group $VIDEO_GID >/dev/null || groupadd -g $VIDEO_GID host_video 2>/dev/null;
    getent group $RENDER_GID >/dev/null || groupadd -g $RENDER_GID host_render 2>/dev/null;
    
    # Kullanıcıyı bu gruplara ekle
    usermod -aG $VIDEO_GID yelpence 2>/dev/null || true
    usermod -aG $RENDER_GID yelpence 2>/dev/null || true

    # Dosya sahipliğini zorla yelpence kullanıcısına ver (Permission Denied: log hatası çözümü)
    chown -R yelpence:yelpence /home/yelpence/ros2_ws
" || true

# 5. Çalışma Alanını Derle (YELPENCE kullanıcısı olarak)
echo "Çalışma alanı derleniyor (colcon build)..."
docker exec -u yelpence -it yelpence_swarm_container bash -c "
    source /opt/ros/jazzy/setup.bash && \
    cd ~/ros2_ws && \
    colcon build --symlink-install --cmake-args -DPX4_VERSION_CHECK=OFF"

echo "=================================================="
echo "SİSTEM HAZIR. Konteynere giriş yapılıyor..."
echo "=================================================="
docker exec -it yelpence_swarm_container bash
