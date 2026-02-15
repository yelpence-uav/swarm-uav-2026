#!/bin/bash
set -e

# ---------------------------------------------------------
# YELPENÇE SÜRÜ İHA - BAŞLANGIÇ SCRİPTİ
# Bu script her yeni terminal açılışında otomatik çalışır.
# ---------------------------------------------------------

# 1. ROS 2 Jazzy Global Ortamını Yükle
# Bu sayede 'ros2 topic list' gibi komutlar çalışır.
source /opt/ros/jazzy/setup.bash

# 2. Yelpençe Çalışma Alanını (Workspace) Yükle
# Eğer proje daha önce derlenmişse (colcon build), sizin kodlarınızı sisteme tanıtır.
if [ -f "/home/yelpence/ros2_ws/install/setup.bash" ]; then
    source "/home/yelpence/ros2_ws/install/setup.bash"
else
    # İlk açılışta bilgilendirme mesajı
    echo "Yelpençe Workspace henüz derlenmemiş. Kodlarınızı derlemek için:"
    echo "    cd ~/ros2_ws && colcon build --symlink-install"
fi

# 3. İstenilen Komutu Çalıştır
# Dockerfile'ın sonundaki CMD ["/bin/bash"] komutunu burası tetikler.
exec "$@"
