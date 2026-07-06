#!/bin/bash
# İki fazlı yaklaşma duvarı testi:
#   Faz 1 (0-20s)  : spacing=9m — dronlar 9m üçgen köşelerine yayılır
#   Faz 2 (20-50s) : spacing=0.5m — CA olmasa çarpışacakları hedefe komut ver
# Beklenti: APF hard_radius=2.0m sınırında dengeli tutsun, ihlal=0, salınım<3
source /opt/ros/jazzy/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null
LAT=41.04418990; LON=29.00170000

echo ">>> FAZ 1 — spacing=9m, dronlar yayılıyor (20 saniye)"
pkill -f formation_test_publisher 2>/dev/null; sleep 0.5

ros2 run swarm_core formation_test_publisher --ros-args \
  -p agent_ids:="[1,2,3]" -p formation_type:=3 -p spacing_m:=9.0 \
  -p heading_deg:=0.0 -p center_z:=-15.0 -p use_proxy:=false \
  -p use_hungarian:=true -p center_lat:=$LAT -p center_lon:=$LON \
  -p max_speed_mps:=2.0 >/dev/null 2>&1 &

sleep 20
echo ">>> FAZ 1 bitti — dronlar ~9m üçgende olmalı"
echo ""

echo ">>> FAZ 2 — spacing=0.5m, CA sınırda tutmalı (30 saniye)"
pkill -f formation_test_publisher 2>/dev/null; sleep 0.3

ros2 run swarm_core formation_test_publisher --ros-args \
  -p agent_ids:="[1,2,3]" -p formation_type:=3 -p spacing_m:=0.5 \
  -p heading_deg:=0.0 -p center_z:=-15.0 -p use_proxy:=false \
  -p use_hungarian:=true -p center_lat:=$LAT -p center_lon:=$LON \
  -p max_speed_mps:=1.0 >/dev/null 2>&1 &

echo ">>> FAZ 2 aktif. 30 saniye izleniyor..."
sleep 30

echo ">>> Ara sonuç:"
strings /tmp/sm_manual.log | grep -E "dek min|salınım" | tail -4
echo ""
echo ">>> Bitince özet + jüri grafiği:  bash report.sh"
