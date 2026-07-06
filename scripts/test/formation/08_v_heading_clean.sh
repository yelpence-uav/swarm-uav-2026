#!/bin/bash
set -e
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash

BAG=~/test_v_heading3
rm -rf "$BAG"

pkill -9 -f "formation_test_publisher" 2>/dev/null || true
sleep 1

echo "[BAG] Kayıt başlıyor..."
ros2 bag record \
  /drone_1/control/setpoint/raw \
  /drone_2/control/setpoint/raw \
  /drone_3/control/setpoint/raw \
  /swarm/internal/drone1/status \
  /swarm/internal/drone2/status \
  /swarm/internal/drone3/status \
  -o "$BAG" &
BAG_PID=$!
sleep 3

run_pub() {
  local heading=$1
  echo "[PUB] V formasyon heading=${heading}° başlıyor (type=2)..."
  pkill -9 -f "formation_test_publisher" 2>/dev/null || true
  sleep 1
  ros2 run swarm_core formation_test_publisher --ros-args \
    -p agent_ids:=[1,2,3] \
    -p formation_type:=2 \
    -p spacing_m:=6.0 \
    -p heading_deg:="${heading}" \
    -p center_z:=-15.0 \
    -p use_proxy:=false \
    -p center_lat:=41.04418990 \
    -p center_lon:=29.00170000 \
    -p max_speed_mps:=2.0 &
  echo "  PID=$!"
}

run_pub 0.0
sleep 25

run_pub 90.0
sleep 25

run_pub 180.0
sleep 25

echo "[BİTTİ] Kayıt kapatılıyor..."
pkill -9 -f "formation_test_publisher" 2>/dev/null || true
sleep 2
kill -SIGINT "$BAG_PID" 2>/dev/null || true
sleep 4
echo "=== TAMAMLANDI ==="
ls "$BAG"/
