#!/bin/bash
# Formasyonlar arasında otomatik döngü.
# V → OkBaşı → Çizgi → V → ...
#
# Kullanım:
#   bash 06_formation_dongu.sh          # 15sn aralık (default)
#   bash 06_formation_dongu.sh 10       # 10sn aralık
#   bash 06_formation_dongu.sh 20       # 20sn aralık

source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash

WAIT=${1:-15}
FORMATIONS=("v" "okbasi" "cizgi")
NAMES=("V" "Ok Başı" "Çizgi")

declare -A TYPES=( ["v"]=2 ["okbasi"]=1 ["cizgi"]=3 )

echo "Formasyon döngüsü başlıyor — ${WAIT}sn aralık"
echo "Durdurmak için Ctrl+C"
echo ""

cleanup() {
    echo ""
    echo "Döngü durduruldu, publisher kapatılıyor..."
    pkill -f "formation_test_publisher" 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

IDX=0
while true; do
    F=${FORMATIONS[$IDX]}
    TYPE=${TYPES[$F]}
    NAME=${NAMES[$IDX]}

    echo ">>> $(date '+%H:%M:%S') — ${NAME} formasyonu (${WAIT}sn)"

    pkill -f "formation_test_publisher" 2>/dev/null
    sleep 1

    ros2 run swarm_core formation_test_publisher \
        --ros-args \
        -p agent_ids:=[1,2,3] \
        -p formation_type:=$TYPE \
        -p spacing_m:=8.0 \
        -p heading_deg:=0.0 \
        -p center_x:=0.0 \
        -p center_y:=0.0 \
        -p center_z:=-15.0 \
        -p use_current_centroid:=false \
        -p use_current_altitude:=false \
        -p use_proxy:=false &

    sleep $WAIT

    IDX=$(( (IDX + 1) % ${#FORMATIONS[@]} ))
done
