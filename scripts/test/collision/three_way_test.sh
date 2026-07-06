#!/bin/bash
# 3-YÖNLÜ SİMETRİK GEÇİŞ (offline three_way_symmetric'in SITL karşılığı).
# 3 drone okbaşı üçgeninde; heading 0°→180° döndürülür → her drone karşı
# köşeye geçer → MERKEZDE simetrik buluşma (deadlock riski). Offline'da
# tangent escape bunu 1.97m'de tutuyordu; gerçek dinamikte tutuyor mu?
#
# converge_test'ten farkı: orada 3 drone TEK noktaya SÜREKLİ sıkışıyordu
# (gerçekçi değil). Burada anlık simetrik geçiş — offline senaryoyla birebir.
#
# Kullanım: bash three_way_test.sh [spacing_m] [max_speed_mps]
source /opt/ros/jazzy/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null

SPACING="${1:-5.0}"
SPEED="${2:-1.5}"
LAT=41.04418990; LON=29.00170000

send() {  # $1=heading  $2=agent_ids
  pkill -f formation_test_publisher 2>/dev/null; sleep 0.4
  ros2 run swarm_core formation_test_publisher --ros-args \
    -p agent_ids:="$2" -p formation_type:=1 -p spacing_m:=$SPACING \
    -p heading_deg:=$1 -p center_z:=-15.0 -p use_proxy:=false \
    -p use_hungarian:=false -p center_lat:=$LAT -p center_lon:=$LON \
    -p max_speed_mps:=$SPEED >/dev/null 2>&1 &
}

echo ">>> 3-YÖNLÜ GEÇİŞ: okbaşı spacing=${SPACING}m, hız=${SPEED} m/s"
echo ""
echo ">>> ADIM 1: heading=0° üçgen otursun (10s)"
send 0.0 "[1,2,3]"
sleep 10
echo "   $(tail -1 /tmp/sm_manual.log 2>/dev/null | grep -oP 'min=\K[0-9.]+')m  irtifaΔ=$(tail -1 /tmp/sm_manual.log 2>/dev/null | grep -oP 'irtifaΔ=\K[0-9.]+')m"

echo ""
echo ">>> ADIM 2: heading=180° — 3 drone MERKEZDEN karşıya geçer (deadlock anı)"
send 180.0 "[1,2,3]"
for i in $(seq 1 15); do
  sleep 1
  LOG=$(tail -1 /tmp/sm_manual.log 2>/dev/null)
  echo "   t=${i}s  min=$(echo "$LOG" | grep -oP 'min=\K[0-9.]+')m  ihlal=$(echo "$LOG" | grep -oP 'ihlal=\K[0-9]+')  salınım=$(echo "$LOG" | grep -oP 'salınım=\K[0-9]+')  irtifaΔ=$(echo "$LOG" | grep -oP 'irtifaΔ=\K[0-9.]+')m"
done

echo ""
echo ">>> Özet + jüri grafiği:  bash report.sh"
