#!/bin/bash
# Yelpençe GUI Startup Script
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash

# Kill old processes
pkill -9 -f web_gui_server
pkill -9 -f MicroXRCEAgent
pkill -9 -f ros_gz_bridge

sleep 2

# Start DDS Agent on 8889
nohup MicroXRCEAgent udp4 -p 8889 > /tmp/dds_agent.log 2>&1 &

# Start LiDAR bridge
nohup ros2 run ros_gz_bridge parameter_bridge '/world/base_world/model/x500_lidar_down_0/link/LIDAR/sensor/lidar/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan' > /tmp/lidar_bridge.log 2>&1 &

# Start PX4 Client (restart)
/home/yelpence/ros2_ws/src/PX4-Autopilot/build/px4_sitl_default/bin/px4-uxrce_dds_client stop
sleep 1
/home/yelpence/ros2_ws/src/PX4-Autopilot/build/px4_sitl_default/bin/px4-uxrce_dds_client start -t udp -p 8889

# Start Web Server
if ! ros2 pkg list 2>/dev/null | grep -q "^px4_msgs$"; then
    echo ">> 'px4_msgs' bulunamadı. Derleme başlatılıyor..."
    cd /home/yelpence/ros2_ws && colcon build --symlink-install --packages-select px4_msgs
    source /home/yelpence/ros2_ws/install/setup.bash
fi

if ! ros2 pkg list 2>/dev/null | grep -q "^gcs$"; then
    echo ">> 'gcs' paketi bulunamadı. Derleme başlatılıyor..."
    cd /home/yelpence/ros2_ws && colcon build --symlink-install --packages-select gcs
    source /home/yelpence/ros2_ws/install/setup.bash
fi

ros2 run gcs web_gui_server > /tmp/web_gui.log 2>&1
