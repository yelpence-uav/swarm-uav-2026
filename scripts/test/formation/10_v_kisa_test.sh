#!/bin/bash
# V formasyon kısa test — bag kaydı formasyon yerleştikten SONRA başlar
# Toplam kayıt süresi: ~50s
set -e
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash

BAG=~/test_v_kisa
rm -rf "$BAG"

pkill -9 -f "formation_test_publisher" 2>/dev/null || true
sleep 1

run_pub() {
  local heading=$1
  echo "[PUB] heading=${heading}° başlatılıyor..."
  pkill -9 -f "formation_test_publisher" 2>/dev/null || true
  sleep 0.8
  ros2 run swarm_core formation_test_publisher --ros-args \
    -p agent_ids:=[1,2,3] \
    -p formation_type:=2 \
    -p spacing_m:=8.0 \
    -p heading_deg:="${heading}" \
    -p center_z:=-15.0 \
    -p use_proxy:=false \
    -p center_lat:=41.04418990 \
    -p center_lon:=29.00170000 \
    -p max_speed_mps:=1.0 &
}

# 1) Formasyon başlat, yerleşmesini bekle (BAG YOK)
echo "[1/4] V formasyon heading=0° başlatılıyor, yerleşme bekleniyor (45s)..."
run_pub 0.0
sleep 45

# 2) Formasyon kararlıyken bag kaydını başlat
echo "[2/4] Formasyon kararlı — kayıt başlıyor..."
ros2 bag record \
  /drone_1/control/setpoint/raw \
  /drone_2/control/setpoint/raw \
  /drone_3/control/setpoint/raw \
  /swarm/internal/drone1/status \
  /swarm/internal/drone2/status \
  /swarm/internal/drone3/status \
  -o "$BAG" &
BAG_PID=$!
sleep 15

# 3) Keskin dönüş 0°→90°
echo "[3/4] Heading 0°→90°..."
run_pub 90.0
sleep 20

# 4) Keskin dönüş 90°→180°
echo "[4/4] Heading 90°→180°..."
run_pub 180.0
sleep 15

echo "[BİTTİ] Kayıt kapatılıyor..."
pkill -9 -f "formation_test_publisher" 2>/dev/null || true
sleep 1
kill -SIGINT "$BAG_PID" 2>/dev/null || true
sleep 4

echo "=== TAMAMLANDI ==="
ls "$BAG"/
