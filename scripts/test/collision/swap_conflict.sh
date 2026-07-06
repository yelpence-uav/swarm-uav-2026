#!/bin/bash
# Çakışma testi: formasyon ver → otur → agent sırasını TERS çevir → swap.
# Drone'lar yer değiştirmek için yollarını keserler → collision_avoidance
# (APF) gerçek fizikte test edilir. safety_monitor min mesafeyi kaydeder.
#
# Kullanım: bash swap_conflict.sh [cizgi|v|okbasi] [spacing_m] [bekleme_s]
# Örnek:    bash swap_conflict.sh cizgi 6 14
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash

FORMATION="${1:-cizgi}"
SPACING="${2:-6.0}"
WAIT="${3:-14}"
SPACING=$(python3 -c "print(float('$SPACING'))")

case "$FORMATION" in
  v|V)       TYPE=2 ;;
  cizgi|c)   TYPE=3 ;;
  okbasi|ok) TYPE=1 ;;
  *) echo "Bilinmeyen formasyon: $FORMATION (cizgi/v/okbasi)"; exit 1 ;;
esac

LAT=41.04418990
LON=29.00170000

send_formation() {
  pkill -f formation_test_publisher 2>/dev/null
  sleep 0.5
  ros2 run swarm_core formation_test_publisher --ros-args \
    -p agent_ids:="$1" \
    -p formation_type:=$TYPE \
    -p spacing_m:=$SPACING \
    -p heading_deg:=0.0 \
    -p center_z:=-15.0 \
    -p use_proxy:=false \
    -p use_hungarian:=false \
    -p center_lat:=$LAT -p center_lon:=$LON \
    -p max_speed_mps:=3.0 &
}

echo ">> [1/2] Formasyon [1,2,3] ($FORMATION, ${SPACING}m) — otursunlar ${WAIT}sn..."
send_formation "[1,2,3]"
sleep "$WAIT"

echo ">> [2/2] SWAP: sıra TERS [3,2,1] → drone1 ↔ drone3 yer değiştirir → ÇAKIŞMA"
echo ">>        safety_monitor'da min mesafeyi izle (CA devrede)."
send_formation "[3,2,1]"
echo ""
echo ">> Yayıncı arka planda. Canlı izleme: tail -f /tmp/sm_manual.log"
echo ">> Swap tamamlanınca özet + jüri grafiği:  bash report.sh"
