#!/bin/bash
# SAF SWAP TETİĞİ (manuel): setup_only.sh sonrası, drone'lar aynı irtifaya
# gelince çalıştır. Sıra TERS [3,2,1] → drone1 ↔ drone3 yer değiştirir →
# yolları kesişir → collision_avoidance (APF) gerçek fizikte test edilir.
# Tek manevra gönderir, form-up tekrarı YOK (setup zaten formasyonda bıraktı).
source /opt/ros/jazzy/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null
LAT=41.04418990; LON=29.00170000

echo ">>> SWAP: [3,2,1] @1.5 m/s — drone1 ↔ drone3"
pkill -f formation_test_publisher 2>/dev/null; sleep 0.5
ros2 run swarm_core formation_test_publisher --ros-args \
  -p agent_ids:="[3,2,1]" -p formation_type:=3 -p spacing_m:=6.0 \
  -p heading_deg:=0.0 -p center_z:=-15.0 -p use_proxy:=false \
  -p use_hungarian:=false -p center_lat:=$LAT -p center_lon:=$LON \
  -p max_speed_mps:=1.5 >/dev/null 2>&1 &
echo ">>> Swap gönderildi. Canlı izleme: tail -f /tmp/sm_manual.log"
echo ">>> Swap tamamlanınca özet + jüri grafiği:  bash report.sh"
