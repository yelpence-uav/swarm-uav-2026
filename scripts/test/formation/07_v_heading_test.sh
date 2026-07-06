#!/bin/bash
# V formasyonu + heading dönüş testi
# Kalkış → V(0°) → V(90°) → V(180°) → bag kapat
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash

BAG=~/test_v_heading3
rm -rf $BAG

echo "[1/5] Bag kaydı başlatılıyor..."
ros2 bag record \
  /drone_1/control/setpoint/raw \
  /drone_2/control/setpoint/raw \
  /drone_3/control/setpoint/raw \
  /swarm/internal/drone1/status \
  /swarm/internal/drone2/status \
  /swarm/internal/drone3/status \
  -o $BAG &
BAG_PID=$!
sleep 3

echo "[2/5] V formasyon heading=0° (20sn)..."
pkill -f formation_test_publisher 2>/dev/null; sleep 1
ros2 run swarm_core formation_test_publisher --ros-args \
  -p agent_ids:=[1,2,3] -p formation_type:=2 -p spacing_m:=8.0 \
  -p heading_deg:=0.0 -p center_z:=-15.0 -p use_proxy:=false \
  -p center_lat:=41.04418990 -p center_lon:=29.00170000 -p max_speed_mps:=2.0 &
sleep 20

echo "[3/5] Keskin dönüş: heading=90° (20sn)..."
pkill -f formation_test_publisher 2>/dev/null; sleep 1
ros2 run swarm_core formation_test_publisher --ros-args \
  -p agent_ids:=[1,2,3] -p formation_type:=2 -p spacing_m:=8.0 \
  -p heading_deg:=90.0 -p center_z:=-15.0 -p use_proxy:=false \
  -p center_lat:=41.04418990 -p center_lon:=29.00170000 -p max_speed_mps:=2.0 &
sleep 20

echo "[4/5] Keskin dönüş: heading=180° (20sn)..."
pkill -f formation_test_publisher 2>/dev/null; sleep 1
ros2 run swarm_core formation_test_publisher --ros-args \
  -p agent_ids:=[1,2,3] -p formation_type:=2 -p spacing_m:=8.0 \
  -p heading_deg:=180.0 -p center_z:=-15.0 -p use_proxy:=false \
  -p center_lat:=41.04418990 -p center_lon:=29.00170000 -p max_speed_mps:=2.0 &
sleep 20

echo "[5/5] Test bitti, kayıt kapatılıyor..."
pkill -f formation_test_publisher 2>/dev/null
sleep 2
kill -SIGINT $BAG_PID
sleep 3
echo "Bag kaydedildi: $BAG"
ls $BAG/
