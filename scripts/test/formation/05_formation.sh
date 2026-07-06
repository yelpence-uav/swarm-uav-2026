#!/bin/bash
# Formation başlat — takeoff sonrası çağrılır.
# Kullanım: bash 05_formation.sh [v|cizgi|okbasi] [spacing_m] [heading_deg]
# Örnek:    bash 05_formation.sh v 8 0
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash

FORMATION="${1:-v}"
SPACING="${2:-8.0}"
HEADING="${3:-0.0}"
# Ensure float format for ROS2 double parameters
SPACING=$(python3 -c "print(float('$SPACING'))")
HEADING=$(python3 -c "print(float('$HEADING'))")

case "$FORMATION" in
  v|V)       TYPE=2 ;;
  cizgi|c)   TYPE=3 ;;
  okbasi|ok) TYPE=1 ;;
  *)         echo "Bilinmeyen formasyon: $FORMATION (v/cizgi/okbasi)"; exit 1 ;;
esac

echo "Formation: $FORMATION (type=$TYPE), spacing=${SPACING}m, heading=${HEADING}°"

# Önceki publisher'ı kapat
pkill -f formation_test_publisher 2>/dev/null
sleep 0.5

ros2 run swarm_core formation_test_publisher \
  --ros-args \
  -p agent_ids:="[1,2,3]" \
  -p formation_type:=$TYPE \
  -p spacing_m:=$SPACING \
  -p heading_deg:=$HEADING \
  -p center_z:=-15.0 \
  -p use_proxy:=false \
  -p center_lat:=41.04418990 \
  -p center_lon:=29.00170000 \
  -p max_speed_mps:=4.0
