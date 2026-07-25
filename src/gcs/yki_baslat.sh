#!/bin/bash
# =============================================================================
# YKİ (yer istasyonu) başlatma — base bridge + backend + frontend.
#
# Sahada WiFi YOK: drone verisi TAMAMEN ESP mesh'ten (base ESP seri portu) gelir.
# base_bridge, backend, frontend hepsi bu laptopta çalışır ve aralarında ROS 2
# (DDS) ile konuşur. DDS'i tek bir kesin yolla LOOPBACK'e sabitleriz:
#
#     CYCLONEDDS_URI -> cyclonedds_yki.xml  (lo arayüzü + 127.0.0.1 unicast peer)
#
# Bu config unicast peer kullanır; 'lo' multicast flag'ine İHTİYACI YOK, deprecated
# ROS_LOCALHOST_ONLY'ye de gerek yok. WiFi açık/kapalı fark etmez — laptop-içi DDS
# her zaman loopback üzerinden gider. Tek bağ mesh; DDS sadece laptop-içi taşıma.
#
# Kullanım:  ./yki_baslat.sh
# Durdurma:  ./yki_durdur.sh
# =============================================================================
# NOT: 'set -u' KULLANMA — ROS setup.bash bağlanmamış değişken referanslar,
# set -u ile source patlar (AMENT_TRACE_SETUP_FILES).

REPO=/home/yentur/yelpence-2026-swarm
VENV=/home/yentur/gcs-venv
# base ESP seri portu — kalici by-id yolu (ttyUSB numarasi yeniden takinca degisir, by-id degismez).
# Base ESP = Silicon Labs CP2102. Farkli kart/port icin: BASE_ESP_PORT=/dev/ttyUSB0 ./yki_baslat.sh
BASE_ESP_PORT="${BASE_ESP_PORT:-/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0}"
BASE_ESP_BAUD=460800

# --- DDS: loopback (WiFi'den bağımsız) — tek kesin mekanizma ---
DDS_URI="file://$REPO/src/gcs/cyclonedds_yki.xml"

# --- ROS 2 ortamı ---
source /opt/ros/jazzy/setup.bash
source "$REPO/install/setup.bash"
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="$DDS_URI"

# --- 1) Base bridge (mesh <-> ROS): telemetri alır, guided komut gönderir ---
echo "[YKİ] base bridge başlatılıyor ($BASE_ESP_PORT @ $BASE_ESP_BAUD)..."
setsid bash -c "source /opt/ros/jazzy/setup.bash && source '$REPO/install/setup.bash' && \
  export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp CYCLONEDDS_URI='$DDS_URI' && \
  exec ros2 run swarm_control esp32_bridge --ros-args -r __node:=esp32_base \
  -p serial_port:=$BASE_ESP_PORT -p baud:=$BASE_ESP_BAUD -p agent_id:=10" \
  > /tmp/yki_base_bridge.log 2>&1 < /dev/null &
disown

# --- 2) Backend (REST + WebSocket, ros2 modu) ---
echo "[YKİ] backend başlatılıyor (:8000)..."
setsid bash -c "source /opt/ros/jazzy/setup.bash && source '$REPO/install/setup.bash' && \
  source '$VENV/bin/activate' && cd '$REPO/src/gcs' && \
  export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp CYCLONEDDS_URI='$DDS_URI' && \
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
