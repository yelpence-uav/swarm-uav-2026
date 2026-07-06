#!/bin/bash
# HAREKETLİ FORMASYON + SPACING ZORLAMASI
# Formasyon 2 m/s ileri giderken spacing 6m→3m'ye düşürülür.
# Gerçek yarışma senaryosu: swarm hedefe uçarken CA aktif.
#
# Kullanım: bash moving_formation_test.sh [cizgi|v|okbasi] [ileri_hiz_mps]
# Önce setup_only.sh çalışmış olmalı.
source /opt/ros/jazzy/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null

FORMATION="${1:-cizgi}"
MOVE_SPEED="${2:-2.0}"
LAT=41.04418990; LON=29.00170000

case "$FORMATION" in
  v|V)       TYPE=2 ;;
  cizgi|c)   TYPE=3 ;;
  okbasi|ok) TYPE=1 ;;
  *) echo "Bilinmeyen formasyon: $FORMATION (cizgi/v/okbasi)"; exit 1 ;;
esac

echo ">>> HAREKETLİ FORMASYON: $FORMATION @ ${MOVE_SPEED} m/s ileri"
echo ">>> irtifa senkronu için 20s bekleniyor..."

# 1) Önce sabit merkez, irtifa senkronu için bekle
pkill -f formation_test_publisher 2>/dev/null; sleep 0.5
ros2 run swarm_core formation_test_publisher --ros-args \
  -p agent_ids:="[1,2,3]" -p formation_type:=$TYPE -p spacing_m:=6.0 \
  -p heading_deg:=0.0 -p center_z:=-15.0 -p use_proxy:=false \
  -p use_hungarian:=false -p center_lat:=$LAT -p center_lon:=$LON \
  -p max_speed_mps:=2.0 -p move_speed_mps:=0.0 >/dev/null 2>&1 &

# İrtifa senkronunu bekle
for i in $(seq 1 20); do
  sleep 1
  ALT=$(tail -1 /tmp/sm_manual.log 2>/dev/null | grep -oP 'irtifaΔ=\K[0-9.]+')
  echo "   t=${i}s | irtifaΔ=${ALT}m"
  [ "$(echo "${ALT:-99} < 0.25" | bc -l 2>/dev/null)" = "1" ] && break
done

echo ""
# Güney yönü: heading_deg=180
# Her adımda yeni publisher başlatılınca merkez sıfırdan başlar →
# kısa mesafe (STEP_WAIT × MOVE_SPEED ≈ 10s × 2m/s = 20m) hareket eder.
echo ">>> ADIM 1: spacing=6m, formasyon ${MOVE_SPEED} m/s GÜNEY yönünde hareket ediyor..."
pkill -f formation_test_publisher 2>/dev/null; sleep 0.5
ros2 run swarm_core formation_test_publisher --ros-args \
  -p agent_ids:="[1,2,3]" -p formation_type:=$TYPE -p spacing_m:=6.0 \
  -p heading_deg:=0.0 -p center_z:=-15.0 -p use_proxy:=false \
  -p use_hungarian:=false -p center_lat:=$LAT -p center_lon:=$LON \
  -p max_speed_mps:=3.0 -p move_speed_mps:=$MOVE_SPEED \
  -p move_heading_deg:=180.0 >/dev/null 2>&1 &
sleep 10
echo "   $(tail -1 /tmp/sm_manual.log 2>/dev/null | grep -oP 'min=\K[0-9.]+')"

echo ""
echo ">>> ADIM 2: spacing=3m, formasyon hâlâ ${MOVE_SPEED} m/s güney, CA devrede..."
pkill -f formation_test_publisher 2>/dev/null; sleep 0.5
ros2 run swarm_core formation_test_publisher --ros-args \
  -p agent_ids:="[1,2,3]" -p formation_type:=$TYPE -p spacing_m:=3.0 \
  -p heading_deg:=0.0 -p center_z:=-15.0 -p use_proxy:=false \
  -p use_hungarian:=false -p center_lat:=$LAT -p center_lon:=$LON \
  -p max_speed_mps:=3.0 -p move_speed_mps:=$MOVE_SPEED \
  -p move_heading_deg:=180.0 >/dev/null 2>&1 &
sleep 10
echo "   $(tail -1 /tmp/sm_manual.log 2>/dev/null | grep -oP 'min=\K[0-9.]+')"

echo ""
echo ">>> ADIM 3: spacing=6m geri aç, formasyon toparlanıyor..."
pkill -f formation_test_publisher 2>/dev/null; sleep 0.5
ros2 run swarm_core formation_test_publisher --ros-args \
  -p agent_ids:="[1,2,3]" -p formation_type:=$TYPE -p spacing_m:=6.0 \
  -p heading_deg:=0.0 -p center_z:=-15.0 -p use_proxy:=false \
  -p use_hungarian:=false -p center_lat:=$LAT -p center_lon:=$LON \
  -p max_speed_mps:=3.0 -p move_speed_mps:=0.0 \
  -p move_heading_deg:=180.0 >/dev/null 2>&1 &
sleep 8
echo "   $(tail -1 /tmp/sm_manual.log 2>/dev/null | grep -oP 'min=\K[0-9.]+')"

echo ""
echo ">>> Hareketli formasyon testi bitti."
echo ">>> Özet + jüri grafiği:  bash report.sh"
