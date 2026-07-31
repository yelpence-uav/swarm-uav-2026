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

# Repo kokunu scriptin KENDI konumundan bul: farkli kullanici/makinede (yentur,
# eyup, ...) elle duzenleme gerekmesin. Ikisi de env ile ezilebilir.
REPO="${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
VENV="${VENV:-$HOME/gcs-venv}"
# base ESP VERI portu — kalici by-id yolu (ttyUSB numarasi degisir, by-id degismez).
# RX BASE 'esp32dev' (default/loglu) env: VERI Serial2 -> USB-TTL (CH340) @460800.
#   LOG hatti ayri: ESP'nin CP2102'si @115200 ([MESH] ciktilari) — izlemek icin:
#   screen /dev/serial/by-id/usb-Silicon_Labs_CP2102...  115200  (veya pio device monitor)
# Farkli port icin: BASE_ESP_PORT=/dev/ttyUSB1 ./yki_baslat.sh
BASE_ESP_PORT="${BASE_ESP_PORT:-/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0}"
BASE_ESP_BAUD=460800

# --- Ortak NED origin (sabit çapa) — SAHAYA göre güncelle ---
# Origin İKİ topic'te gerekir:
#   /swarm/public/origin   -> backend (harita tıklaması lat/lon -> NED çevirisi)
#   /swarm/internal/origin -> base esp32_bridge -> mesh -> drone px4_bridge
#                             (SET_GPS_GLOBAL_ORIGIN; formation_node origin gelmeden setpoint üretmez)
# base esp32_bridge public'i mesh'e İLETMEZ (yalnız /internal dinler) -> İKİ yayıncı gerekir.
# Değeri sahanın referans noktasıyla değiştir (env ile: ORIGIN_LAT=... ./yki_baslat.sh).
# RTK baz istasyonu gelince: swarm_origin_publisher'ı origin_source:=rtk_base'e çevir.
ORIGIN_LAT="${ORIGIN_LAT:-38.6904758}"
ORIGIN_LON="${ORIGIN_LON:-39.1610188}"
ORIGIN_ALT="${ORIGIN_ALT:-1218.5}"

# --- DDS: loopback (WiFi'den bağımsız) — tek kesin mekanizma ---
DDS_URI="file://$REPO/src/gcs/cyclonedds_yki.xml"

# --- Önce çalışan örnekleri durdur (IDEMPOTENT) ---
# Bu script eskiden mevcut süreçleri kontrol etmiyordu: her çalıştırmada
# yenilerini başlatıp eskilerini bırakıyordu. Sonuç, aynı seri portu isteyen
# N tane esp32_base ve N tane origin yayıncısı — biri portu tutar, diğerleri
# saniyede bir "Device or resource busy" döngüsüne girer. Ölçüldü: art arda
# birkaç başlatmadan sonra 12 esp32_base, 22 origin yayıncısı.
# Sahada bu, teşhisi çok zor bir "bazen çalışıyor" arızası olurdu.
if pgrep -f "esp32_base|swarm_origin_pub|yki_rtcm_reader|uvicorn backend" > /dev/null 2>&1; then
  echo "[YKİ] çalışan örnekler bulundu, önce durduruluyor..."
  bash "$(dirname "${BASH_SOURCE[0]}")/yki_durdur.sh"
  sleep 2
fi

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

# --- 1.5) Ortak origin yayıncıları — İKİ tane (bkz. yukarıdaki açıklama) ---
echo "[YKİ] origin yayıncıları başlatılıyor (lat=$ORIGIN_LAT lon=$ORIGIN_LON alt=$ORIGIN_ALT)..."
# (a) public -> backend harita->NED
setsid bash -c "source /opt/ros/jazzy/setup.bash && source '$REPO/install/setup.bash' && \
  export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp CYCLONEDDS_URI='$DDS_URI' && \
  exec ros2 run swarm_control swarm_origin_publisher --ros-args -r __node:=swarm_origin_pub_public \
  -p origin_source:=fixed -p fixed_lat:=$ORIGIN_LAT -p fixed_lon:=$ORIGIN_LON -p fixed_alt:=$ORIGIN_ALT -p rate_hz:=1.0" \
  > /tmp/yki_origin_public.log 2>&1 < /dev/null &
disown
# (b) internal -> base bridge -> mesh -> drone (SET_GPS_GLOBAL_ORIGIN)
setsid bash -c "source /opt/ros/jazzy/setup.bash && source '$REPO/install/setup.bash' && \
  export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp CYCLONEDDS_URI='$DDS_URI' && \
  exec ros2 run swarm_control swarm_origin_publisher --ros-args -r __node:=swarm_origin_pub_internal \
  -r /swarm/public/origin:=/swarm/internal/origin \
  -p origin_source:=fixed -p fixed_lat:=$ORIGIN_LAT -p fixed_lon:=$ORIGIN_LON -p fixed_alt:=$ORIGIN_ALT -p rate_hz:=1.0" \
  > /tmp/yki_origin_internal.log 2>&1 < /dev/null &
disown

# --- 1.7) RTK okuyucu: u-blox -> ROS -> base bridge -> mesh ---
# Seri portun sahibi esp32_bridge'dir (aynı portu iki süreç açamaz), o yüzden
# RTCM doğrudan porta değil ROS topic'ine gider. Okuyucu AYRI süreç: çökerse
# telemetri ve komut yolu etkilenmez.
# GPS portu takılı değilse okuyucu 2 sn'de bir yeniden dener, YKİ'yi bloke etmez.
#
# BU YÜZDEN KOŞULSUZ BAŞLATILIYOR. Eskiden "port var mı" diye bakılıp yoksa
# HİÇ başlatılmıyordu — okuyucunun kendi tekrar-deneme yeteneğine sıra bile
# gelmiyordu. 31 Temmuz'da tam bu ısırdı: u-blox YKİ açıldıktan SONRA takıldı,
# RTCM hiç akmadı, ve bu ancak drone'a SSH atıp px4_bridge logundaki
# 'rtk: msg=0' sayacına bakınca fark edildi. Artık okuyucu her hâlükârda
# başlar, port gelince kendiliğinden bağlanır.
RTK_GPS_PORT="${RTK_GPS_PORT:-/dev/serial/by-id/usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00}"
RTK_TOPIC="${RTK_TOPIC:-/swarm/internal/rtcm}"
if [ -e "$RTK_GPS_PORT" ]; then
  echo "[YKİ] RTK okuyucu başlatılıyor ($RTK_GPS_PORT -> $RTK_TOPIC)..."
else
  echo "[YKİ] RTK okuyucu başlatılıyor — GPS portu HENÜZ YOK, takılınca bağlanacak"
fi
setsid bash -c "source /opt/ros/jazzy/setup.bash && source '$REPO/install/setup.bash' && \
  source '$VENV/bin/activate' && \
  export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp CYCLONEDDS_URI='$DDS_URI' && \
  exec python3 '$REPO/src/gcs/backend/rtcm/yki_rtcm_reader.py' \
    --gps-port '$RTK_GPS_PORT' --ros-topic '$RTK_TOPIC'" \
  > /tmp/yki_rtcm.log 2>&1 < /dev/null &
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
