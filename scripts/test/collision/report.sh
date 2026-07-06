#!/bin/bash
# RAPOR: senaryo bittikten sonra çalıştır. safety_monitor'ü DÜZGÜN kapatır
# (SIGINT → ozet_bas: min mesafe + ihlal + osilasyon özeti + events CSV),
# sonra jüri grafiğini (min-mesafe–zaman PNG) üretir.
#
# Kullanım: bash report.sh [run_label]   (varsayılan: collision_run)
source /opt/ros/jazzy/setup.bash; source ~/ros2_ws/install/setup.bash 2>/dev/null

RUN="${1:-collision_run}"
OUTDIR=~/ros2_ws/analysis/collision_sitl
CSV="$OUTDIR/$RUN.csv"

echo ">>> 1) Formasyon yayıncısı durduruluyor"
pkill -f formation_test_publisher 2>/dev/null; sleep 0.5

echo ">>> 2) Monitor'e kapanış sinyali (özet + events CSV yazsın)"
pkill -INT -f safety_monitor 2>/dev/null
sleep 2

echo ">>> 3) Monitor özeti (min mesafe / ihlal / osilasyon):"
grep -E "ÖZET|KRİTİK|İHLAL" /tmp/sm_manual.log | tail -15

if [ ! -f "$CSV" ]; then
  echo ">>> CSV bulunamadı: $CSV (monitor çalıştı mı?)"
  exit 1
fi

echo ">>> 4) Jüri grafiği üretiliyor"
python3 ~/ros2_ws/scripts/test/collision/plot_min_distance.py "$CSV"

echo ""
echo ">>> Veriler: $CSV"
echo ">>> Grafik : $OUTDIR/$RUN.png"
