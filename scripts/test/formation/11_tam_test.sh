#!/bin/bash
# Tam misyon testi — kalkıştan itibaren kayıt
# Bag: kalkış + V formasyon geçişi + heading dönüşleri
# Toplam ~70s
set -e
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash

BAG=~/test_v_tam
rm -rf "$BAG"

pkill -9 -f "formation_test_publisher" 2>/dev/null || true
sleep 1

run_pub() {
  local heading=$1
  echo "[PUB] heading=${heading}° ..."
  pkill -9 -f "formation_test_publisher" 2>/dev/null || true
  sleep 0.5
  ros2 run swarm_core formation_test_publisher --ros-args \
    -p agent_ids:=[1,2,3] \
    -p formation_type:=2 \
    -p spacing_m:=8.0 \
    -p heading_deg:="${heading}" \
    -p center_z:=-15.0 \
    -p use_proxy:=false \
    -p center_lat:=41.04418990 \
    -p center_lon:=29.00170000 \
    -p max_speed_mps:=1.5 &
}

# Bag kaydını HEMEN başlat
echo "[1/5] Kayıt başlıyor..."
ros2 bag record \
  /drone_1/control/setpoint/raw \
  /drone_2/control/setpoint/raw \
  /drone_3/control/setpoint/raw \
  /swarm/internal/drone1/status \
  /swarm/internal/drone2/status \
  /swarm/internal/drone3/status \
  -o "$BAG" &
BAG_PID=$!
sleep 2

# Kalkış komutu
echo "[2/5] Kalkış komutu gönderiliyor..."
bash ~/ros2_ws/scripts/test/formation/04_takeoff.sh &
sleep 18  # Dronlar 15m'ye ulaşsın

# V Formasyon başlat — yerleşme beklenmeden hemen
echo "[3/5] V Formasyon heading=0° başlatılıyor..."
run_pub 0.0
sleep 25  # Formasyon yerleşsin + kararlı hal

# Keskin dönüş 1
echo "[4/5] Heading 0°→90°..."
run_pub 90.0
sleep 20

# Keskin dönüş 2
echo "[5/5] Heading 90°→180°..."
run_pub 180.0
sleep 15

echo "[BİTTİ] Kayıt kapatılıyor..."
pkill -9 -f "formation_test_publisher" 2>/dev/null || true
sleep 1
kill -SIGINT "$BAG_PID" 2>/dev/null || true
sleep 4

echo "=== TAMAMLANDI ==="
ls "$BAG"/
