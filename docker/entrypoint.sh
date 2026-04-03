#!/bin/bash
set -e

# Parmak izlerinin saklanacağı gizli klasör
HASH_DIR="/home/yelpence/.config/yelpence_hashes"
mkdir -p "$HASH_DIR"

REQ_FILE="/home/yelpence/ros2_ws/src/requirements.txt"
DOCKERFILE_PATH="/home/yelpence/ros2_ws/src/yelpence-src/docker/Dockerfile"

# --- Fonksiyon: Değişiklik Kontrolü ---
check_and_update_deps() {
    if [ -f "$REQ_FILE" ]; then
        current_hash=$(md5sum "$REQ_FILE" | awk '{ print $1 }')
        old_hash_file="$HASH_DIR/req.hash"

        if [ ! -f "$old_hash_file" ] || [ "$current_hash" != "$(cat "$old_hash_file")" ]; then
            echo -e "\n\e[33m[BİLGİ] requirements.txt değişikliği saptandı. Bağımlılıklar güncelleniyor...\e[0m"
            # Sanal ortam aktif mi kontrol et ve yükle
            source /home/yelpence/venv/bin/activate
            pip install --no-cache-dir -r "$REQ_FILE"

            # Yeni hash'i kaydet
            echo "$current_hash" >"$old_hash_file"
            echo -e "\e[32m[TAMAM] Bağımlılıklar güncel.\e[0m\n"
        fi
    fi
}

check_dockerfile() {
    # Not: Dockerfile'ı volume ile içeri bağlamış olmanız gerekir
    if [ -f "$DOCKERFILE_PATH" ]; then
        current_hash=$(md5sum "$DOCKERFILE_PATH" | awk '{ print $1 }')
        old_hash_file="$HASH_DIR/dockerfile.hash"

        if [ -f "$old_hash_file" ] && [ "$current_hash" != "$(cat "$old_hash_file")" ]; then
            echo -e "\n\e[31m[UYARI] Dockerfile değiştirilmiş! \e[0m"
            echo -e "\e[31mEn iyi performans ve uyumluluk için lütfen imajı yeniden oluşturun:\e[0m"
            echo -e "\e[31m./create-docker.sh\e[0m\n"
        fi
        echo "$current_hash" >"$old_hash_file"
    fi
}

# --- Başlangıç İşlemleri ---
sudo service ssh start >/dev/null 2>&1

# Bağımlılık kontrollerini çalıştır
check_and_update_deps
# check_dockerfile # Dockerfile mount edildiyse aktif edin

# 1. ROS 2 Jazzy Global Ortamını Yükle
source /opt/ros/jazzy/setup.bash

# 2. Yelpençe Çalışma Alanını Yükle
if [ -f "/home/yelpence/ros2_ws/install/setup.bash" ]; then
    source "/home/yelpence/ros2_ws/install/setup.bash"
fi

# 3. Python Sanal Ortamını Aktif Et
source /home/yelpence/venv/bin/activate

# Komutu çalıştır
exec "$@"
