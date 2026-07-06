#!/bin/bash
# TERMİNAL 3 — FSM başlat (drone 1, sitl_mode açık)
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash

echo "AgentFsmNode başlatılıyor: drone1 (sitl_mode=true)..."
echo "UNKNOWN -> IDLE geçişini gör, sonra devam et."
ros2 run swarm_state_machine agent_fsm_node \
  --ros-args -p agent_id:=1 -p sitl_mode:=true
