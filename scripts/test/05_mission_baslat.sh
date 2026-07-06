#!/bin/bash
# TERMİNAL 5 — FSM üzerinden görevi başlat (IDLE -> ARMING -> ARMED -> TAKEOFF)
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash

echo "EVENT_MISSION_STARTED gönderiliyor (event_type=24)..."
echo "FSM kendi kendine: ARMING komutu -> ARMED -> offboard -> TAKEOFF yapacak."
echo ""

ros2 topic pub --once /swarm/internal/events/system swarm_interfaces/msg/SystemEvent \
  '{event_type: 24, severity: 0, source_agent_id: 0, target_agent_id: 0, source_module: "test", message: "FSM test"}'

echo ""
echo "Komut gönderildi. Terminal 4'ten state geçişlerini izle."
