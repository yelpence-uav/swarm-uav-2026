#!/bin/bash
# FORMASYON DEĞİŞİMİ — gerçek görev senaryosu.
# spacing SABİT (5m); formasyon TİPİ değişir: çizgi→V→okbaşı→çizgi.
# Her geçişte drone'lar yeni slot geometrisine koşar → bazı yollar geçici
# yakınlaşır/kesişir → CA gerçek görevde devreye giriyor mu test edilir.
#
# Macar AÇIK (use_hungarian=true): gerçek sistemde atama optimaldir
# (her drone en yakın slota gider, gereksiz yol yok). Kapalı/ters sıra
# sadece swap'ı YAPAY zorlamak içindi; burada gerçekçi davranış isteniyor.
#
# Kullanım: bash formation_change_test.sh [spacing] [kademe_s]
source /opt/ros/jazzy/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null

SPACING="${1:-5.0}"
STEP_WAIT="${2:-12}"
LAT=41.04418990; LON=29.00170000

send() {  # $1=formation_type  $2=isim
  pkill -f formation_test_publisher 2>/dev/null; sleep 0.4
  ros2 run swarm_core formation_test_publisher --ros-args \
    -p agent_ids:="[1,2,3]" -p formation_type:=$1 -p spacing_m:=$SPACING \
    -p heading_deg:=0.0 -p center_z:=-15.0 -p use_proxy:=false \
    -p use_hungarian:=true -p center_lat:=$LAT -p center_lon:=$LON \
    -p max_speed_mps:=1.5 >/dev/null 2>&1 &
}

# Geçiş anını yakından izle (drone'lar yeni slota koşarken min düşer)
watch_transition() {  # $1=isim
  local lo=99
  for i in $(seq 1 "$STEP_WAIT"); do
    sleep 1
    m=$(tail -1 /tmp/sm_manual.log 2>/dev/null | grep -oP 'min=\K[0-9.]+')
    [ -n "$m" ] && awk "BEGIN{exit !($m<$lo)}" && lo=$m
  done
  LOG=$(tail -1 /tmp/sm_manual.log 2>/dev/null)
  echo "   [$1] geçiş-min=${lo}m  şimdi=$(echo "$LOG"|grep -oP 'min=\K[0-9.]+')m  ihlal=$(echo "$LOG"|grep -oP 'ihlal=\K[0-9]+')  salınım=$(echo "$LOG"|grep -oP 'salınım=\K[0-9]+')  irtifaΔ=$(echo "$LOG"|grep -oP 'irtifaΔ=\K[0-9.]+')m"
}

echo ">>> FORMASYON DEĞİŞİMİ: spacing=${SPACING}m SABİT, Macar açık"
echo ">>> çizgi → V → okbaşı → çizgi  (her geçiş ${STEP_WAIT}s)"
echo ""

echo ">> 1) ÇİZGİ (başlangıç, otursun)"
send 3 cizgi; watch_transition cizgi

echo ">> 2) → V (drone'lar V slotuna koşar)"
send 2 v; watch_transition V

echo ">> 3) → OKBAŞI"
send 1 okbasi; watch_transition okbasi

echo ">> 4) → ÇİZGİ (geri dön)"
send 3 cizgi; watch_transition cizgi

echo ""
echo ">>> Özet + jüri grafiği:  bash report.sh"
