#!/bin/bash
# record_and_plot.sh — Herhangi bir test sırasında CA verisi kaydet + grafik üret
#
# KULLANIM: İki terminalden:
#   Terminal 1: bash record_and_plot.sh [test_adı] [drone_ids]
#   Terminal 2: test scriptini çalıştır (b1_lateral.sh, swap vs.)
#
#   Örnekler:
#     bash record_and_plot.sh b2_overlap "1,2,3"
#     bash record_and_plot.sh swap_test  "1,2,3"
#
# Ctrl+C ile durdur → grafik otomatik üretilir.

source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash 2>/dev/null

TEST_NAME="${1:-ca_test}"
DRONE_IDS="${2:-1,2,3}"
OUT_DIR=~/ros2_ws/analysis/collision_sitl/${TEST_NAME}
mkdir -p "$OUT_DIR"

echo ">>> KAYIT BAŞLIYOR: $TEST_NAME"
echo ">>> Çıktı: $OUT_DIR"
echo ">>> Durdurmak için Ctrl+C → grafik otomatik üretilir"
echo ""

# Logger başlat (arka planda değil — Ctrl+C ile birlikte duracak)
python3 ~/ros2_ws/scripts/test/collision/ca_logger.py --ros-args \
  -p agent_ids:="[$DRONE_IDS]" \
  -p out_dir:="$OUT_DIR" \
  -p rate_hz:=10.0 &
LOGGER_PID=$!

trap "kill $LOGGER_PID 2>/dev/null; sleep 0.5; echo ''; echo '>>> Grafik üretiliyor...';\
  python3 ~/ros2_ws/scripts/test/collision/plot_ca_analysis.py \
    $OUT_DIR --title '$TEST_NAME' --out $OUT_DIR/ca_analysis.png;\
  echo '>>> Grafik: $OUT_DIR/ca_analysis.png'" INT TERM

wait $LOGGER_PID
