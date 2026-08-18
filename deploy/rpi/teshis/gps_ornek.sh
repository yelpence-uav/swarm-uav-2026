#!/bin/bash
# Konteyner icinde kosar. $1 = agent_id, $2 = etiket
# GPS ham durumunu tek satirda ozetler (fix_type / uydu / h_acc).
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1

V=$(timeout 20 ros2 topic echo "/drone_${AID}/mavros/gpsstatus/gps1/raw" --once 2>/dev/null \
    | grep -E "^(fix_type|satellites_visible|h_acc):" | tr -d ' ' | tr '\n' ' ')
echo "   [$2] $V"
