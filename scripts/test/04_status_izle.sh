#!/bin/bash
# TERMİNAL 4 — drone1 FSM durumunu sürekli izle
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash

echo "Drone1 FSM durumu izleniyor... (Ctrl+C ile dur)"
echo "Beklenen: IDLE -> ARMING -> ARMED -> TAKEOFF -> IN_SWARM"
echo "---"

while true; do
    echo "=== $(date '+%H:%M:%S') ==="
    ros2 topic echo /swarm/agent/drone1/telemetry --once --no-daemon 2>/dev/null \
      | grep -E "state:|armed:|flight_mode:|status_text:|px4_link_ok:"
    echo ""
    sleep 2
done
