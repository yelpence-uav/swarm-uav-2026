#!/bin/bash
# HOVER TESTİ — öneri maddesi: "hedefleri aynıysa/kaçacak yer yoksa,
# itme=çekme dengesinde güvenli mesafede DURUP hover kalmalıdırlar."
#
# drone1 + drone2 AYNI noktaya (center) çekilir; drone3 uzakta park eder.
# İki drone aynı hedefe gidince CA onları güvenli mesafede DURDURUP hover
# ettirmeli — kaçmaya/dönmeye/çökmeye DEĞİL. converge'de (3 drone) çökmüştü;
# bu 2-drone temiz testi gerçek hover kapasitesini ölçer.
#
# Başarı: drone1-2 mesafesi ~güvenli mesafede SABİT (hover), salınım≈0,
#         çöküş yok (min≥1.5m), uzun süre kararlı.
#
# Kullanım: bash hover_test.sh [park_mesafesi]
source /opt/ros/jazzy/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null

PARK="${1:-8.0}"     # drone3 ne kadar uzakta park etsin
LAT=41.04418990; LON=29.00170000

echo ">>> HOVER: drone1+drone2 → AYNI nokta, drone3 ${PARK}m uzakta park"
echo ">>> Beklenen: drone1-2 güvenli mesafede SABİT hover (salınım yok, çöküş yok)"
echo ""

pkill -f formation_test_publisher 2>/dev/null
pkill -f disturbance_publisher 2>/dev/null; sleep 0.5
python3 ~/ros2_ws/scripts/test/collision/disturbance_publisher.py --ros-args \
  -p agent_ids:="[1,2,3]" -p formation_type:=3 -p spacing_m:=5.0 \
  -p heading_deg:=0.0 -p center_z:=-15.0 -p center_lat:=$LAT -p center_lon:=$LON \
  -p max_speed_mps:=2.0 -p mode:=rendezvous -p group_b_ids:="[3]" \
  -p rdv_gap_m:=1.0 -p separation_m:=$PARK >/tmp/dist.log 2>&1 &

# 30s izle — hover kararlılığı (mesafe sabit mi, salınım var mı, çöküş var mı)
for i in $(seq 1 30); do
  sleep 1
  LOG=$(tail -1 /tmp/sm_manual.log 2>/dev/null)
  MIN=$(echo "$LOG"|grep -oP 'min=\K[0-9.]+'|head -1)
  VIOL=$(echo "$LOG"|grep -oP 'ihlal=\K[0-9]+')
  SAL=$(echo "$LOG"|grep -oP 'salınım=\K[0-9]+')
  ALT=$(echo "$LOG"|grep -oP 'irtifaΔ=\K[0-9.]+')
  echo "   t=${i}s  min=${MIN}m  ihlal=${VIOL}  salınım=${SAL}  irtifaΔ=${ALT}m"
done

echo ""
echo ">>> Hover bitti. Mesafe sabit + salınım≈0 + çöküş yok ise BAŞARI."
echo ">>> Özet + jüri grafiği:  bash report.sh"
