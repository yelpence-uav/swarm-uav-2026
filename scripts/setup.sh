#!/bin/bash

# Yelpençe Sürü İHA - Konteyner İçi Kurulum Scripti
# PX4, QGroundControl, DDS Agent, ROS 2 workspace ve tüm bağımlılıkları kurar.
# Bu script konteyner içinde çalıştırılmalıdır.

set -e

WORKSPACE_DIR="/home/yelpence/ros2_ws"
PX4_DIR="$WORKSPACE_DIR/src/PX4-Autopilot"

echo "=================================================="
echo " YELPENÇE SÜRÜ İHA - TAM KURULUM BAŞLIYOR"
echo "=================================================="

# 0. Sistem Gereksinimlerini Kur
echo ">> Sistem bileşenleri kuruluyor (xterm vb.)..."
sudo apt-get update
sudo apt-get install -y xterm libzbar0

# 1. Kullanıcı İzinlerini Düzenle (GPU Erişimi İçin)
echo ">> Kullanıcı izinleri düzenleniyor..."
sudo usermod -aG video yelpence || true
sudo usermod -aG render yelpence || true
# Bazı sistemlerde /dev/dri izinleri katı olabilir, garantiye alalım
sudo chmod 666 /dev/dri/* 2>/dev/null || true

# 2. Python Bağımlılıklarını Yükle
echo ">> Python bağımlılıkları yükleniyor..."
pip3 install -r "$WORKSPACE_DIR/scripts/requirements.txt" --break-system-packages

# NumPy Header Fix (ROS 2 Python bindings build fails without this in some environments)
echo ">> NumPy headerları sisteme tanıtılıyor..."
NUMPY_INCLUDE=$(python3 -c "import numpy; print(numpy.get_include())")
sudo ln -sf "$NUMPY_INCLUDE/numpy" /usr/include/numpy

# 3. PX4-Autopilot Kurulumu
if [ ! -d "$PX4_DIR/.git" ]; then
    echo ">> PX4-Autopilot klonlanıyor (branch: main)..."
    # Eğer klasör varsa ama git deposu değilse temizle (volume mount boş olabilir)
    [ -d "$PX4_DIR" ] && rm -rf "${PX4_DIR:?}"/*
    git clone --recursive https://github.com/PX4/PX4-Autopilot.git "$PX4_DIR"
else
    echo ">> PX4-Autopilot zaten mevcut. Alt modüller güncelleniyor..."
    cd "$PX4_DIR"
    git submodule update --init --recursive
fi

# Motor Telemetry Yama (dds_topics.yaml düzenleme)
DDS_TOPICS_FILE="$PX4_DIR/src/modules/uxrce_dds_client/dds_topics.yaml"
if [ -f "$DDS_TOPICS_FILE" ] && ! grep -q "/fmu/out/actuator_motors" "$DDS_TOPICS_FILE"; then
    echo ">> PX4 Motor Telemetrisi için dds_topics.yaml yamalanıyor..."
    # 'gimbal_device_attitude_status' satırından sonra motorları ekle
    sed -i '/type: px4_msgs::msg::GimbalDeviceAttitudeStatus/a \
\
  - topic: /fmu/out/actuator_outputs\
    type: px4_msgs::msg::ActuatorOutputs\
\
  - topic: /fmu/out/actuator_motors\
    type: px4_msgs::msg::ActuatorMotors\
    rate_limit: 20.' "$DDS_TOPICS_FILE"
fi

# Colcon yoksayma dosyası (Güvenlik amaçlı eklendi)
if [ ! -f "$PX4_DIR/COLCON_IGNORE" ]; then
    touch "$PX4_DIR/COLCON_IGNORE"
fi

echo ">> PX4 bağımlılıkları kuruluyor..."
bash "$PX4_DIR/Tools/setup/ubuntu.sh" --no-nuttx --no-sim-tools

# 4. PX4 x500 Dronu İçin Otonom Uçuş İzinlerini Kalıcı Olarak Ayarla
X500_FILE="$PX4_DIR/ROMFS/px4fmu_common/init.d-posix/airframes/4001_gz_x500"
if [ -f "$X500_FILE" ] && ! grep -q "COM_RCL_EXCEPT" "$X500_FILE"; then
    echo ">> x500 modeli için otonom uçuş parametreleri ayarlanıyor..."
    echo "" >> "$X500_FILE"
    echo "# YELPENCE SURU IHA - Otonom Ucus Izinleri" >> "$X500_FILE"
    echo "param set-default NAV_DLL_ACT 0" >> "$X500_FILE"
    echo "param set-default NAV_RCL_ACT 0" >> "$X500_FILE"
    echo "param set-default COM_RCL_EXCEPT 4" >> "$X500_FILE"
    echo "# SITL Health Check Bypass (QGC arm icin gerekli)" >> "$X500_FILE"
    echo "param set-default CBRK_SUPPLY_CHK 894281" >> "$X500_FILE"
    echo "param set-default CBRK_USB_CHK 197848" >> "$X500_FILE"
    echo "param set-default COM_ARM_WO_GPS 1" >> "$X500_FILE"
    echo "param set-default COM_ARM_CHK_ESCS 0" >> "$X500_FILE"
    echo "param set-default COM_RC_IN_MODE 4" >> "$X500_FILE"
fi

# 5. PX4 ve ROS 2 arasındaki mesaj sözlüğünü (px4_msgs) indir
if [ ! -d "$WORKSPACE_DIR/src/px4_msgs" ]; then
    echo ">> PX4 ROS 2 Mesaj Sözlüğü (px4_msgs) indiriliyor (branch: main)..."
    git clone -b main https://github.com/PX4/px4_msgs.git "$WORKSPACE_DIR/src/px4_msgs"
else
    echo ">> px4_msgs klasörü zaten mevcut. Branch kontrol ediliyor (main olmalı)..."
    cd "$WORKSPACE_DIR/src/px4_msgs"
    git checkout main || echo ">> Uyarı: px4_msgs main branchine geçilemedi."
fi

# 6. Micro-XRCE-DDS-Agent Kurulumu
if ! command -v MicroXRCEAgent &> /dev/null; then
    echo ">> Micro-XRCE-DDS-Agent kaynaktan kuruluyor..."
    cd /tmp
    git clone https://github.com/eProsima/Micro-XRCE-DDS-Agent.git
    cd Micro-XRCE-DDS-Agent
    mkdir build && cd build
    cmake ..
    make
    sudo make install
    sudo ldconfig
else
    echo ">> Micro-XRCE-DDS-Agent zaten kurulu."
fi

# 7. PX4 SITL Build
echo ">> PX4 SITL inşa ediliyor..."
cd "$PX4_DIR"
make px4_sitl_default

# 8. Çalışma Alanı Derleme
echo ">> ROS 2 çalışma alanı derleniyor..."
cd "$WORKSPACE_DIR"
# Hatalı build'lerden kurtulmak için temizlik
rm -rf build/px4 install/px4
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install

# 9. QGroundControl İndirme
QGC_FILE="$WORKSPACE_DIR/tools/QGroundControl.AppImage"
mkdir -p "$WORKSPACE_DIR/tools"
sudo chown -R "$(id -u):$(id -g)" "$WORKSPACE_DIR/tools"
if [ ! -f "$QGC_FILE" ] || [ "$(stat -c%s "$QGC_FILE" 2>/dev/null)" -lt 1000000 ]; then
    rm -f "$QGC_FILE"
    echo ">> QGroundControl indiriliyor (~180MB)..."
    curl -L --fail -o "$QGC_FILE" \
      https://github.com/mavlink/qgroundcontrol/releases/download/v5.0.8/QGroundControl-x86_64.AppImage && \
    chmod +x "$QGC_FILE" && echo ">> QGroundControl indirildi." || \
    { rm -f "$QGC_FILE"; echo ">> UYARI: QGroundControl indirilemedi."; }
else
    echo ">> QGroundControl zaten mevcut."
fi

echo "=================================================="
echo " KURULUM TAMAMLANDI!"
echo " Artik 'ros2 run swarm swarm_launch' ile sistemi baslatabilirsiniz."
echo "=================================================="
