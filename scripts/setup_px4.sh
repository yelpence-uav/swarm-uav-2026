#!/bin/bash
# Yelpençe Sürü İHA - PX4 Autopilot Hazırlık Betiği

echo "=================================================="
echo " PX4 Autopilot Kurulumu Başlıyor..."
echo "=================================================="

# Projenin ana dizininde olduğumuzdan emin olalım
cd "$(dirname "$0")/.."

# 1. PX4'ü src dizinine indir (Eğer daha önce indirilmediyse)
if [ ! -d "src/PX4-Autopilot" ]; then
    echo "PX4-Autopilot kaynak kodları indiriliyor (Bu işlem biraz sürebilir)..."
    git clone https://github.com/PX4/PX4-Autopilot.git --recursive src/PX4-Autopilot
else
    echo "PX4-Autopilot klasörü 'src' dizininde zaten mevcut. İndirme atlanıyor."
fi

# 2. ROS 2 çakışmalarını önlemek için COLCON_IGNORE kalkanını oluştur
if [ ! -f "src/PX4-Autopilot/COLCON_IGNORE" ]; then
    touch src/PX4-Autopilot/COLCON_IGNORE
    echo "ROS 2 (colcon) derleme koruması başarıyla eklendi."
fi

# 3. PX4 ve ROS 2 arasındaki mesaj sözlüğünü (px4_msgs) indir
if [ ! -d "src/px4_msgs" ]; then
    echo "PX4 ROS 2 Mesaj Sözlüğü (px4_msgs) indiriliyor..."
    git clone https://github.com/PX4/px4_msgs.git src/px4_msgs
else
    echo "px4_msgs klasörü 'src' dizininde zaten mevcut. İndirme atlanıyor."
fi

# 4. PX4 x500 Dronu İçin Otonom Uçuş (Offboard) İzinlerini Kalıcı Olarak Ayarla
X500_FILE="src/PX4-Autopilot/ROMFS/px4fmu_common/init.d-posix/airframes/4001_gz_x500"

if [ -f "$X500_FILE" ] && ! grep -q "COM_RCL_EXCEPT" "$X500_FILE"; then
    echo "x500 modeli için otonom uçuş parametreleri ayarlanıyor..."
    echo "" >> "$X500_FILE"
    echo "# YELPENCE SURU IHA - Otonom Ucus Izinleri" >> "$X500_FILE"
    echo "param set-default NAV_DLL_ACT 0" >> "$X500_FILE"
    echo "param set-default NAV_RCL_ACT 0" >> "$X500_FILE"
    echo "param set-default COM_RCL_EXCEPT 4" >> "$X500_FILE"
fi

echo "=================================================="
echo " Kurulum Tamamlandı! Artık Docker'ı başlatabilirsiniz."
echo "=================================================="
