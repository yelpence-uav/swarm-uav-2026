#!/bin/bash
set -e

# Sadece ROS 2 ve Yelpençe çalışma alanını yükle
source /opt/ros/jazzy/setup.bash

if [ -f "/home/yelpence/ros2_ws/install/setup.bash" ]; then
  source "/home/yelpence/ros2_ws/install/setup.bash"
fi

# Sanal ortamı aktif et
if [ -f "/home/yelpence/venv/bin/activate" ]; then
  source /home/yelpence/venv/bin/activate
fi

echo -e "\n\e[32m[YELPENÇE] Görev Bilgisayarı Konteyneri Hazır. İyi uçuşlar!\e[0m\n"

# İletilen komutu (ros2 launch vb.) çalıştır
exec "$@"
