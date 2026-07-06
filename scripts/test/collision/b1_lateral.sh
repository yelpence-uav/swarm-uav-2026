#!/bin/bash
# B1 — TEK DRONE YANAL İTİŞ (rüzgar/GPS sapması) → CA + SVT recovery.
# drone2'ye GEÇİCİ olarak komşusuna (drone1) doğru gerçek hedef verilir;
# drone2 oraya FİZİKSEL uçar → CA komşuya çarptırmamalı (min≥1.5m) → itiş
# kalkınca SVT drone2'yi gerçek slota geri toplamalı (recovery).
#
# Slot oyunu DEĞİL: çakışma atama değil, drone'un fiziksel hareketinden doğar.
# Önce setup_only.sh çalışmış olmalı (drone'lar formasyonda).
#
# Kullanım: bash b1_lateral.sh [spacing] [itiş_m]
source /opt/ros/jazzy/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null

SPACING="${1:-5.0}"
MAG="${2:-4.0}"          # komşuya doğru sapma (spacing-MAG = hedef mesafe)
LAT=41.04418990; LON=29.00170000
DSTART=8; DDUR=4         # itiş t=8s'de başlar, 4s sürer

echo ">>> B1 YANAL İTİŞ: drone2, spacing=${SPACING}m, sapma=${MAG}m"
echo ">>> hedef mesafe itiş anında ~$(awk "BEGIN{print $SPACING-$MAG}")m (< 1.5m emniyet) → CA tutmalı"
echo ""

pkill -f formation_test_publisher 2>/dev/null
pkill -f disturbance_publisher 2>/dev/null; sleep 0.5
python3 ~/ros2_ws/scripts/test/collision/disturbance_publisher.py --ros-args \
  -p agent_ids:="[1,2,3]" -p formation_type:=3 -p spacing_m:=$SPACING \
  -p heading_deg:=0.0 -p center_z:=-15.0 -p center_lat:=$LAT -p center_lon:=$LON \
  -p max_speed_mps:=2.0 -p mode:=breakaway -p disturb_id:=2 \
  -p disturb_axis:=lateral -p disturb_mag_m:=$MAG \
  -p disturb_start_s:=${DSTART}.0 -p disturb_dur_s:=${DDUR}.0 >/tmp/dist.log 2>&1 &

# 24s izle: 0-8 normal, 8-12 itiş, 12+ recovery
BIAS_END=$((DSTART + DDUR))
rec_start=0; rec_time="—"
for i in $(seq 1 24); do
  sleep 1
  LOG=$(tail -1 /tmp/sm_manual.log 2>/dev/null)
  MIN=$(echo "$LOG"|grep -oP 'min=\K[0-9.]+'|head -1)
  VIOL=$(echo "$LOG"|grep -oP 'ihlal=\K[0-9]+')
  SAL=$(echo "$LOG"|grep -oP 'salınım=\K[0-9]+')
  phase="normal"
  [ "$i" -ge "$DSTART" ] && [ "$i" -lt "$BIAS_END" ] && phase="İTİŞ"
  [ "$i" -ge "$BIAS_END" ] && phase="recovery"
  echo "   t=${i}s [$phase]  min=${MIN}m  ihlal=${VIOL}  salınım=${SAL}"
  # recovery süresi: itiş bittikten sonra min≥4m'e ilk dönüş
  if [ "$i" -ge "$BIAS_END" ] && [ "$rec_time" = "—" ] && [ -n "$MIN" ]; then
    awk "BEGIN{exit !($MIN>=4.0)}" && rec_time="$((i - BIAS_END))s"
  fi
done

echo ""
echo ">>> İtiş bitişinden SVT toparlamasına (min≥4m): ${rec_time}"
echo ">>> Özet + jüri grafiği:  bash report.sh"
