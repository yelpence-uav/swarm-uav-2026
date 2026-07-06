#!/bin/bash
# Formasyon testi için gerekli paketleri derle
source /opt/ros/jazzy/setup.bash

cd ~/ros2_ws
colcon build --packages-select \
    swarm_interfaces \
    swarm_state_machine \
    swarm_control \
    swarm_core \
    swarm_perception \
    network_proxy

source install/setup.bash
echo "Build tamamlandı."
