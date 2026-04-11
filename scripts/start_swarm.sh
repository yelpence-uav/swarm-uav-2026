#!/bin/bash
# Yelpençe Sürü Simülasyonu Başlatıcı
# Tüm sistemi tek komutla temizleyip başlatır.

echo "--- Yelpençe Sürü Simülasyonu Hazırlanıyor ---"
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export GZ_SIM_RENDER_ENGINE_BACKEND=ogre
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:$(pwd)/sim/models
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash

# ROS 2 Paket kontrolü ve otomatik derleme (Eğer paket bulunamazsa)
if ! ros2 pkg list 2>/dev/null | grep -q "^px4_msgs$"; then
    echo ">> 'px4_msgs' bulunamadı. Derleme başlatılıyor..."
    cd /home/yelpence/ros2_ws && colcon build --symlink-install --packages-select px4_msgs
    source /home/yelpence/ros2_ws/install/setup.bash
fi

if [ ! -f /home/yelpence/ros2_ws/src/PX4-Autopilot/build/px4_sitl_default/bin/px4 ]; then
    echo ">> PX4 SITL bin dosyası bulunamadı. Derleme başlatılıyor..."
    cd /home/yelpence/ros2_ws/src/PX4-Autopilot && make px4_sitl_default
fi

if ! ros2 pkg list 2>/dev/null | grep -q "^swarm$"; then
    echo ">> 'swarm' paketi bulunamadı. Derleme başlatılıyor..."
    cd /home/yelpence/ros2_ws && colcon build --symlink-install --packages-select swarm
    source /home/yelpence/ros2_ws/install/setup.bash
fi

# Python scriptini çalıştır (ros2 run)
ros2 run swarm swarm_launch
