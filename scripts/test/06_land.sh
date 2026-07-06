#!/bin/bash
# TERMİNAL 5 — Acil iniş komutu gönder (FSM üzerinden)
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash

echo "EVENT_EMERGENCY_LAND gönderiliyor (event_type=46)..."

ros2 topic pub --once /swarm/events/system swarm_interfaces/msg/SystemEvent \
  '{event_type: 46, severity: 2, source_agent_id: 0, target_agent_id: 1, source_module: "test", message: "FSM test land"}'

echo "İniş komutu gönderildi. FSM LANDING -> LANDED geçişini yapacak."
