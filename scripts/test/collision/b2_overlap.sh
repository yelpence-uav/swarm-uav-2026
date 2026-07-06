#!/bin/bash
# B2 — DİKEY / ÜST-ÜSTE SÜRÜKLEME (downwash + dikey CA).
# drone2 komşusunun (drone1) TAM ÜSTÜNE yatay sürüklenir (hedef mesafe ~0).
# Saf dikey itiş çarpışma yaratmaz (yatay 5m ayrım 3D mesafeyi korur); asıl
# dikey/downwash testi drone'u komşunun üstüne getirip CA'yı dikey ayırmaya
# ZORLAMAKTIR. CA ya dikey kaçışla ayırır ya çarpışır + gerçek downwash.
#
# Slot oyunu DEĞİL: drone2 fiziksel olarak komşu pozisyonuna uçar.
# Önce setup_only.sh çalışmış olmalı.
#
# Kullanım: bash b2_overlap.sh [spacing] [sapma]
source /opt/ros/jazzy/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null

SPACING="${1:-5.0}"
MAG="${2:-5.0}"          # spacing kadar → drone2 komşunun tam üstüne
LAT=41.04418990; LON=29.00170000
DSTART=8; DDUR=5

echo ">>> B2 ÜST-ÜSTE/DOWNWASH: drone2 → drone1'in üstüne (sapma=${MAG}m)"
echo ">>> CA dikey ayırmalı (min≥1.5m) + downwash gerçek etkisi izlenir"
echo ""

pkill -f formation_test_publisher 2>/dev/null
pkill -f disturbance_publisher 2>/dev/null; sleep 0.5
python3 ~/ros2_ws/scripts/test/collision/disturbance_publisher.py --ros-args \
  -p agent_ids:="[1,2,3]" -p formation_type:=3 -p spacing_m:=$SPACING \
  -p heading_deg:=0.0 -p center_z:=-15.0 -p center_lat:=$LAT -p center_lon:=$LON \
  -p max_speed_mps:=2.0 -p mode:=breakaway -p disturb_id:=2 \
  -p disturb_axis:=lateral -p disturb_mag_m:=$MAG \
  -p disturb_start_s:=${DSTART}.0 -p disturb_dur_s:=${DDUR}.0 >/tmp/dist.log 2>&1 &

BIAS_END=$((DSTART + DDUR))
rec_time="—"
for i in $(seq 1 26); do
  sleep 1
  LOG=$(tail -1 /tmp/sm_manual.log 2>/dev/null)
  MIN=$(echo "$LOG"|grep -oP 'min=\K[0-9.]+'|head -1)
  VIOL=$(echo "$LOG"|grep -oP 'ihlal=\K[0-9]+')
  SAL=$(echo "$LOG"|grep -oP 'salınım=\K[0-9]+')
  ALT=$(echo "$LOG"|grep -oP 'irtifaΔ=\K[0-9.]+')
  phase="normal"
  [ "$i" -ge "$DSTART" ] && [ "$i" -lt "$BIAS_END" ] && phase="ÜST-ÜSTE"
  [ "$i" -ge "$BIAS_END" ] && phase="recovery"
  echo "   t=${i}s [$phase]  min=${MIN}m  ihlal=${VIOL}  salınım=${SAL}  irtifaΔ=${ALT}m"
  if [ "$i" -ge "$BIAS_END" ] && [ "$rec_time" = "—" ] && [ -n "$MIN" ]; then
    awk "BEGIN{exit !($MIN>=4.0)}" && rec_time="$((i - BIAS_END))s"
  fi
done

echo ""
echo ">>> SVT toparlama (min≥4m): ${rec_time}"
echo ">>> Özet + jüri grafiği:  bash report.sh"
