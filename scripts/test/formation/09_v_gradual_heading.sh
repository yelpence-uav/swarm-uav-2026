#!/bin/bash
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash

BAG=~/test_v_gradual
rm -rf "$BAG"

pub() {
  pkill -9 -f "formation_test_publisher" 2>/dev/null; sleep 0.5
  ros2 run swarm_core formation_test_publisher --ros-args \
    -p agent_ids:=[1,2,3] -p formation_type:=2 -p spacing_m:=8.0 \
    -p heading_deg:="$1" -p center_z:=-15.0 -p use_proxy:=false \
    -p max_speed_mps:=2.0 > /dev/null 2>&1 &
  echo "  heading=$1°"
}

echo "[BAG] Başlıyor..."
ros2 bag record \
  /drone_1/control/setpoint/raw /drone_2/control/setpoint/raw /drone_3/control/setpoint/raw \
  /swarm/internal/drone1/status /swarm/internal/drone2/status /swarm/internal/drone3/status \
  -o "$BAG" > /dev/null 2>&1 &
BAG_PID=$!
sleep 3

echo "[1] Kararlı: heading=0° (20s)"
pub 0.0;   sleep 20

echo "[2] Kademeli 0→90°"
pub 30.0;  sleep 8
pub 60.0;  sleep 8
pub 90.0;  sleep 8

echo "[3] Kararlı: heading=90° (20s)"
sleep 20

echo "[4] Kademeli 90→180°"
pub 120.0; sleep 8
pub 150.0; sleep 8
pub 180.0; sleep 8

echo "[5] Kararlı: heading=180° (20s)"
sleep 20

echo "[BİTTİ] Bag kapatılıyor..."
pkill -9 -f "formation_test_publisher" 2>/dev/null
sleep 2
kill -SIGINT "$BAG_PID"
sleep 4
echo "=== TAMAMLANDI ===" && ls "$BAG"/
