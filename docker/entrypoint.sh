#!/bin/bash
# Konteyner her sıfırdan başlatıldığında veya varolan konteynerin içine girildiğinde çalışan betik.

set -e

# Parmak izlerinin saklanacağı gizli klasör
HASH_DIR="/home/yelpence/.config/yelpence_hashes"
mkdir -p "$HASH_DIR"
REQ_FILE="/home/yelpence/ros2_ws/src/requirements.txt"

# Python bağımlılık kontrolü; her açlışta requirements.txt dosyasını kontrol eder.
check_and_update_deps() {
    if [ -f "$REQ_FILE" ]; then
        current_hash=$(md5sum "$REQ_FILE" | awk '{ print $1 }')
        old_hash_file="$HASH_DIR/req.hash"

        if [ ! -f "$old_hash_file" ] || [ "$current_hash" != "$(cat "$old_hash_file")" ]; then
            echo -e "\n\e[33m[UYARI] DEĞİŞİKLİK SAPTANDI. BAĞIMLILIKLAR GÜNCELLENİYOR...\e[0m"
            # Sanal ortam aktif mi kontrol et ve yükle
            source /home/yelpence/venv/bin/activate
            pip install --no-cache-dir -r "$REQ_FILE"

            # Yeni hash'i kaydet
            echo "$current_hash" >"$old_hash_file"
            echo -e "\e[32m[TAMAM] BAĞIMLILIKLAR GÜNCEL.\e[0m\n"
        fi
    fi
}

# --- Başlangıç İşlemleri ---
sudo service ssh start >/dev/null 2>&1

# Bağımlılık kontrollerini çalıştır
check_and_update_deps

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
