#!/bin/bash
# Tüm süreçleri kapat
echo "Kapatılıyor..."
pkill -9 -f "gz sim"
pkill -9 -f px4
pkill -9 -f MicroXRCEAgent
pkill -9 -f ros_gz_bridge
pkill -9 -f parameter_bridge
pkill -9 -f px4_bridge
pkill -9 -f agent_fsm
pkill -9 -f formation_node
pkill -9 -f kinematic_fusion
pkill -9 -f collision_avoidance
tmux kill-server
echo "Temizlendi."
