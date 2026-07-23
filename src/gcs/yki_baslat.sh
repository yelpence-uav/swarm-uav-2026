#!/bin/bash
# =============================================================================
# YKİ (yer istasyonu) başlatma — base bridge + backend + frontend.
#
# Sahada WiFi YOK: drone verisi ESP mesh'ten (base ESP seri portu) gelir.
# base_bridge, backend, frontend hepsi bu laptopta çalışır ve aralarında ROS 2
# (DDS) ile konuşur. DDS'i LOOPBACK'e sabitleriz (ROS_LOCALHOST_ONLY=1) — WiFi
# durumundan bağımsız. Bu olmadan CycloneDDS WiFi arayüzünü seçer ve WiFi
# kapanınca laptop-içi DDS bile kopar.
#
# Kullanım:  ./yki_baslat.sh
# Durdurma:  ./yki_durdur.sh
# =============================================================================
# NOT: 'set -u' KULLANMA — ROS setup.bash bağlanmamış değişken referanslar,
# set -u ile source patlar (AMENT_TRACE_SETUP_FILES).

REPO=/home/yentur/yelpence-2026-swarm
VENV=/home/yentur/gcs-venv
BASE_ESP_PORT="${BASE_ESP_PORT:-/dev/ttyUSB0}"   # base ESP seri portu (değişirse: BASE_ESP_PORT=/dev/ttyUSB1 ./yki_baslat.sh)
BASE_ESP_BAUD=460800

# Loopback multicast — boot'ta yki-lo-multicast.service açar. Değilse burada dene.
if ip -brief link show lo 2>/dev/null | grep -q MULTICAST; then
  echo "[YKİ] lo multicast zaten açık (systemd)"
else
  echo "[YKİ] lo multicast açılıyor..."
  sudo ip link set lo multicast on || { echo "HATA: lo multicast açılamadı (sudo?)"; exit 1; }
fi

# --- ROS 2 ortamı: loopback-only ---
source /opt/ros/jazzy/setup.bash
source "$REPO/install/setup.bash"
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_LOCALHOST_ONLY=1

# --- 1) Base bridge (mesh <-> ROS): telemetri alır, guided komut gönderir ---
echo "[YKİ] base bridge başlatılıyor ($BASE_ESP_PORT @ $BASE_ESP_BAUD)..."
setsid bash -c "source /opt/ros/jazzy/setup.bash && source '$REPO/install/setup.bash' && \
  export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1 && \
  exec ros2 run swarm_control esp32_bridge --ros-args -r __node:=esp32_base \
  -p serial_port:=$BASE_ESP_PORT -p baud:=$BASE_ESP_BAUD -p agent_id:=10" \
  > /tmp/yki_base_bridge.log 2>&1 < /dev/null &
disown

# --- 2) Backend (REST + WebSocket, ros2 modu) ---
echo "[YKİ] backend başlatılıyor (:8000)..."
setsid bash -c "source /opt/ros/jazzy/setup.bash && source '$REPO/install/setup.bash' && \
  source '$VENV/bin/activate' && cd '$REPO/src/gcs' && \
  export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1 && \
  exec uvicorn backend.main:app --host 0.0.0.0 --port 8000" \
  > /tmp/yki_backend.log 2>&1 < /dev/null &
disown

# --- 3) Frontend (Vite dev server) ---
echo "[YKİ] frontend başlatılıyor (:5173)..."
setsid bash -c "cd '$REPO/src/gcs/frontend' && exec npm run dev" \
  > /tmp/yki_frontend.log 2>&1 < /dev/null &
disown

sleep 8
echo ""
echo "[YKİ] Hazır:"
echo "   Arayüz : http://localhost:5173/"
echo "   Backend: http://localhost:8000/"
echo "   Loglar : /tmp/yki_base_bridge.log  /tmp/yki_backend.log  /tmp/yki_frontend.log"
echo ""
echo "   Backend sağlık:"; curl -s -o /dev/null -w "     HTTP %{http_code}\n" http://localhost:8000/api/health 2>/dev/null || echo "     (henüz açılıyor)"
