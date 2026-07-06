#!/bin/bash
# Dronlar yerde veya havada olabilir — direkt formation komutu gönderir.
# İlk argüman formasyon tipi: v | okbasi | cizgi  (default: v)
#
# Kullanım:
#   bash 05_formation_gonder.sh          # V formasyonu
#   bash 05_formation_gonder.sh okbasi   # Ok Başı formasyonu
#   bash 05_formation_gonder.sh cizgi    # Çizgi formasyonu

source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash

case "${1:-v}" in
    okbasi) TYPE=1 ;;
    v)      TYPE=2 ;;
    cizgi)  TYPE=3 ;;
    *)      echo "Bilinmeyen tip: $1 (okbasi | v | cizgi)"; exit 1 ;;
esac

pkill -f "formation_test_publisher" 2>/dev/null && sleep 1

echo "Formasyon tipi: ${1:-v} (type=$TYPE), 3 drone, spacing=8m, z=-15m"
echo "Durdurmak için Ctrl+C"

ros2 run swarm_core formation_test_publisher \
    --ros-args \
    -p agent_ids:=[1,2,3] \
    -p formation_type:=$TYPE \
    -p spacing_m:=8.0 \
    -p heading_deg:=0.0 \
    -p center_z:=-15.0 \
    -p use_current_centroid:=false \
    -p use_current_altitude:=false \
    -p use_proxy:=false
