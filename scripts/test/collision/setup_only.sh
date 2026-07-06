#!/bin/bash
# KURULUM (otomatik): stack + GPS + monitor + kalkış + form-up.
# Drone'ları havada formasyonda bırakır ve DURUR — çarpışma senaryosunu
# BAŞLATMAZ. Sen Gazebo'da hepsinin aynı irtifaya geldiğini görünce
# senaryo scriptini (swap_conflict.sh / converge_test.sh) elle çalıştır.
# (Drone'lar kalkışta aynı anda aynı irtifaya gelmediği için tetik manuel.)
source /opt/ros/jazzy/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null
LAT=41.04418990; LON=29.00170000

echo ">>> 0) Önceki test publisher'ları temizle"
pkill -f disturbance_publisher 2>/dev/null
pkill -f formation_test_publisher 2>/dev/null
sleep 1

echo ">>> 1) Kontrol stack"
bash ~/ros2_ws/scripts/test/formation/02_start_all.sh >/dev/null 2>&1

echo ">>> 2) GPS bekleniyor (3/3 fix)..."
for i in $(seq 1 25); do
  ok=0
  for d in 1 2 3; do
    fix=$(timeout 3 ros2 topic echo /swarm/agent/drone$d/telemetry --once 2>/dev/null | grep '^gps_fix_type:' | awk '{print $2}')
    [ "$fix" = "3" ] && ok=$((ok+1))
  done
  echo "    GPS $ok/3"
  [ "$ok" = "3" ] && break
  sleep 3
done

echo ">>> 3) Monitor başlıyor (emniyet=1.5m, osilasyon takibi açık)"
pkill -f safety_monitor 2>/dev/null; sleep 1
python3 ~/ros2_ws/scripts/test/collision/safety_monitor.py --ros-args \
  -p agent_ids:="[1,2,3]" -p safety_radius_m:=1.5 -p warn_radius_m:=2.0 \
  -p run_label:=collision_run >/tmp/sm_manual.log 2>&1 &
sleep 2

echo ">>> 4) Kalkış"
python3 ~/ros2_ws/scripts/test/formation/sync_takeoff.py 2>&1 | grep -iE "arm|offboard|kalkış|HATA" | tail -4
sleep 3

echo ">>> 5) Form-up [1,2,3] @2 m/s (irtifa -15 m)"
pkill -f formation_test_publisher 2>/dev/null; sleep 0.5
ros2 run swarm_core formation_test_publisher --ros-args \
  -p agent_ids:="[1,2,3]" -p formation_type:=3 -p spacing_m:=6.0 \
  -p heading_deg:=0.0 -p center_z:=-15.0 -p use_proxy:=false \
  -p use_hungarian:=false -p center_lat:=$LAT -p center_lon:=$LON \
  -p max_speed_mps:=2.0 >/dev/null 2>&1 &

echo ""
echo "════════════════════════════════════════════════════════════════"
echo ">>> HAZIR. Drone'lar formasyona oturuyor (CSV: collision_run)."
echo ">>> Gazebo'da HEPSİ AYNI İRTİFAYA gelince TEK senaryoyu SEN başlat:"
echo "    (izole test: her senaryo için bu setup'ı baştan çalıştır)"
echo ""
echo "    # AŞAMA 2 — Kademeli yaklaşma (CA yumuşak girişi + osilasyon):"
echo "    bash ~/ros2_ws/scripts/test/collision/approach_test.sh cizgi"
echo ""
echo "    # AŞAMA 4 — Swap worst-case (kafa-kafaya + irtifa kaybı):"
echo "    bash ~/ros2_ws/scripts/test/collision/do_swap.sh"
echo ""
echo ">>> Senaryo bitince özet + jüri grafiği:"
echo "    bash ~/ros2_ws/scripts/test/collision/report.sh"
echo ">>> Canlı izleme: tail -f /tmp/sm_manual.log"
echo "════════════════════════════════════════════════════════════════"
