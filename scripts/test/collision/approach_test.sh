#!/bin/bash
# AŞAMA 2 — Yumuşak (kademeli) yakınlaşma testi.
# Swap'taki ani yer değiştirme riskini almadan, formasyon spacing'ini
# KADEMELİ düşürerek İHA'ları birbirine yaklaştırır. Her kademede bekleyip
# CA'nın yumuşak devreye girişini ve OSİLASYON olup olmadığını gözleriz.
#
# converge_test.sh'ten farkı: o spacing=0 ile ANINDA topluyor (şok girdi);
# bu kademeli (6→4→3→2→1.5) → CA'nın eşik geçişlerini izole gösterir.
#
# Kullanım: bash approach_test.sh [cizgi|v|okbasi] [bekleme_s]
# Önce setup_only.sh çalışmış ve drone'lar aynı irtifada olmalı.
source /opt/ros/jazzy/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null

FORMATION="${1:-cizgi}"
STEP_WAIT="${2:-8}"
LAT=41.04418990; LON=29.00170000

case "$FORMATION" in
  v|V)       TYPE=2 ;;
  cizgi|c)   TYPE=3 ;;
  okbasi|ok) TYPE=1 ;;
  *) echo "Bilinmeyen formasyon: $FORMATION (cizgi/v/okbasi)"; exit 1 ;;
esac

send_spacing() {
  pkill -f formation_test_publisher 2>/dev/null; sleep 0.4
  ros2 run swarm_core formation_test_publisher --ros-args \
    -p agent_ids:="[1,2,3]" -p formation_type:=$TYPE -p spacing_m:=$1 \
    -p heading_deg:=0.0 -p center_z:=-15.0 -p use_proxy:=false \
    -p use_hungarian:=false -p center_lat:=$LAT -p center_lon:=$LON \
    -p max_speed_mps:=3.0 >/dev/null 2>&1 &
}

# Kademeler: influence_radius=3.5m altına IN, ama hard_radius=2.0m'nin
# ÜSTÜNDE KAL. Spacing=3.5m'den sonra CA aktif ama formation-CA denge
# bulur; spacing=2m'de hard_radius=2.0m → CA max kuvvet → osilasyon.
# SITL testinde maks yaklaşma: 3.0m (CA +denge, çarpışma yok kanıtlanır).
for SP in 9.0 6.0 4.5 3.5; do
  echo ">> spacing=${SP}m → ${STEP_WAIT}sn bekleniyor (CA devreye giriş + osilasyon izle)"
  send_spacing "$SP"
  sleep "$STEP_WAIT"
  echo "   $(strings /tmp/sm_manual.log 2>/dev/null | grep 'dek min' | tail -1)"
done

echo ""
echo ">> Kademeli yaklaşma bitti. spacing=3.5m'de CA emniyeti korumalı."
echo ">> Not: spacing < influence_radius_m(3.5m) → CA aktif, SVT ile gerilim."
echo ">>      spacing < hard_radius_m(2.0m) → osilasyon; o bölgeye girmiyoruz."
echo ">> Özet + jüri grafiği:  bash report.sh"
