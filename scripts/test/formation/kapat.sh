#!/bin/bash
# === TAM KAPATMA — sürü test yığınının 3 katmanını da öldürür ===
# Gazebo penceresini kapatmak YETMEZ: ROS düğümleri (tmux) + bag recorder'lar
# yaşamaya devam eder ve oturumlar arası BİRİKİR. Bu script hepsini temizler.
#
# Self-kill koruması: pkill -f kendi komut satırını da eşler. Bunu önlemek için
# "bracket trick" kullanılır — "[f]ormation" regex'i "formation" process'ini
# eşler ama bu scriptin komut satırındaki "[f]ormation" literalini EŞLEMEZ.
#
# Kullanım:  bash ~/ros2_ws/scripts/test/formation/kapat.sh

echo "=== Sürü test yığını kapatılıyor ==="

# --- Katman 3: bag recorder'lar (en sık öksüz kalan) ---
pkill -9 -f "[r]os2 bag record" 2>/dev/null
pkill -9 -f "[r]osbag2" 2>/dev/null

# --- Katman 2: ROS uygulama düğümleri ---
pkill -9 -f "[f]ormation_" 2>/dev/null         # formation_node + test_publisher
pkill -9 -f "[a]gent_fsm_node" 2>/dev/null
pkill -9 -f "[s]warm_fsm_node" 2>/dev/null
pkill -9 -f "[c]ollision_avoidance" 2>/dev/null
pkill -9 -f "[k]inematic_fusion" 2>/dev/null
pkill -9 -f "[s]warm_origin_publisher" 2>/dev/null
pkill -9 -f "[p]x4_bridge" 2>/dev/null
pkill -9 -f "[n]etwork_proxy" 2>/dev/null
pkill -9 -f "[m]ission_fsm" 2>/dev/null
pkill -9 -f "[r]os_gz_bridge" 2>/dev/null
pkill -9 -f "[p]arameter_bridge" 2>/dev/null

# --- tmux oturumu (düğümler burada arka planda yaşıyor) ---
tmux kill-session -t formation_test 2>/dev/null && echo "  tmux formation_test kapatıldı" || true

# --- Katman 1: PX4 SITL + Gazebo ---
pkill -9 -f "[b]in/px4" 2>/dev/null
pkill -9 -f "[p]x4_sitl" 2>/dev/null
pkill -9 -f "[g]z sim" 2>/dev/null
pkill -9 -f "[g]zserver" 2>/dev/null

sleep 4

# --- Doğrulama (ros2 node list = otorite; pgrep self-match'e dikkat) ---
source /opt/ros/jazzy/setup.bash 2>/dev/null
source ~/ros2_ws/install/setup.bash 2>/dev/null
NODES=$(timeout 6 ros2 node list 2>/dev/null | wc -l)
PX4=$(pgrep -f "[b]in/px4" | wc -l)
GZ=$(pgrep -f "[g]z sim" | wc -l)
REC=$(pgrep -f "[r]os2 bag record" | wc -l)

echo ""
echo "=== SON DURUM (hepsi 0 olmalı) ==="
echo "  ROS düğümü : $NODES"
echo "  px4 SITL   : $PX4"
echo "  gz sim     : $GZ"
echo "  bag record : $REC"
if [ "$NODES" -eq 0 ] && [ "$PX4" -eq 0 ] && [ "$GZ" -eq 0 ] && [ "$REC" -eq 0 ]; then
  echo "[OK] Tertemiz — yeni oturuma hazır."
else
  echo "[UYARI] Kalan process var, tekrar çalıştır veya elle kontrol et."
fi
true
