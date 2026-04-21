#!/bin/bash
# Konteyner her sıfırdan başlatıldığında veya varolan konteynerin içine girildiğinde çalışan betik.

set -e

echo "--- Yelpençe Simülasyon Ortamı Başlatılıyor ---"

# Parmak izlerinin saklanacağı gizli klasör
HASH_DIR="/home/yelpence/.config/yelpence_hashes"
mkdir -p "$HASH_DIR"
REQ_FILE="/home/yelpence/ros2_ws/src/requirements.txt"

# Python bağımlılık kontrolü; her açılışta requirements.txt dosyasını kontrol eder.
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

# 1. ROS 2 Jazzy Global Ortamını Yükle
source /opt/ros/jazzy/setup.bash

# 2. Python Sanal Ortamını Aktif Et
source /home/yelpence/venv/bin/activate

# 3. Bağımlılık kontrollerini çalıştır
check_and_update_deps

# 4. Çalışma Alanına Geçiş Yap
cd /home/yelpence/ros2_ws

# 5. PX4 Otonom Uçuş İzinlerinin (Parametrelerin) Ayarlanması
# Eğer src dizini volume olarak dışarıdan bağlandıysa, bu değişiklik host makinedeki dosyaya da yansır.
AIRFRAME_FILE="src/PX4-Autopilot/ROMFS/px4fmu_common/init.d-posix/airframes/4001_gz_x500"
if [ -f "$AIRFRAME_FILE" ]; then
    # Dosyaya daha önce eklenip eklenmediğini kontrol et (Dosyanın şişmesini engellemek için)
    if ! grep -q "NAV_DLL_ACT 0" "$AIRFRAME_FILE"; then
        echo -e "\n# YELPENCE SURU IHA - Otonom Ucus Izinleri (SIMULASYON)" >>"$AIRFRAME_FILE"
        echo "param set-default NAV_DLL_ACT 0" >>"$AIRFRAME_FILE"
        echo "param set-default NAV_RCL_ACT 0" >>"$AIRFRAME_FILE"
        echo "param set-default COM_RCL_EXCEPT 4" >>"$AIRFRAME_FILE"
        echo -e "\e[32m--- Otonom uçuş parametreleri x500 modeline başarıyla eklendi! ---\e[0m"
    fi
fi

# 6. İlk Kurulum ve Derleme Kontrolü
# Eğer 'install' klasörü yoksa sıfırdan derleme yapılır.
if [ ! -d "install" ]; then
    echo -e "\e[33m--- [İLK KURULUM] Derlenmiş paket bulunamadı. Kurulum başlatılıyor... ---\e[0m"

    # PX4-Autopilot Derlemesi (SITL Gazebo Simülasyonu için)
    if [ -d "src/PX4-Autopilot" ]; then
        echo "--- 1/2: PX4-Autopilot derleniyor ---"
        make -C src/PX4-Autopilot px4_sitl_default gz_x500
    else
        echo -e "\e[31m[HATA] src/PX4-Autopilot klasörü bulunamadı! Submodülleri çektiğinizden emin olun.\e[0m"
    fi

    # ROS 2 Paketlerinin Derlenmesi (px4_msgs, swarm vb.)
    echo "--- 2/2: ROS 2 çalışma alanı derleniyor (colcon) ---"
    colcon build --symlink-install

    echo -e "\e[32m--- İlk kurulum ve derleme başarıyla tamamlandı! ---\e[0m"
else
    echo "--- Mevcut derleme bulundu. Hazır sistem üzerinden başlatılıyor... ---"
fi

# 7. Yelpençe Çalışma Alanını Yükle
if [ -f "/home/yelpence/ros2_ws/install/setup.bash" ]; then
    source "/home/yelpence/ros2_ws/install/setup.bash"
fi

echo -e "\n\e[32m--- Sistem Hazır. İyi uçuşlar! ---\e[0m\n"

# Komutu çalıştır
exec "$@"
