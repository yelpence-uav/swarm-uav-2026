#!/bin/bash
# 3 drone durumunu ve setpoint'leri sürekli izle
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash

echo "3 drone izleniyor... (Ctrl+C ile dur)"
echo "Beklenen: IDLE -> ARMING -> ARMED -> TAKEOFF -> IN_SWARM"
echo "---"

while true; do
    echo "=== $(date '+%H:%M:%S') ==="
    for id in 1 2 3; do
        echo "--- drone${id} ---"
        ros2 topic echo /swarm/agent/drone${id}/telemetry \
            --once --no-daemon 2>/dev/null \
            | grep -E "state:|armed:|status_text:"
    done
    echo ""
    sleep 2
done
