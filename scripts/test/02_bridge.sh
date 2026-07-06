#!/bin/bash
# TERMİNAL 2 — px4_bridge başlat (drone 1)
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash

echo "Px4BridgeNode başlatılıyor: drone1..."
ros2 run swarm_control px4_bridge --ros-args -p agent_id:=1 -p sitl_mode:=true
