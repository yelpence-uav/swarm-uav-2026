#!/usr/bin/env bash
# Yelpence suru - drone konteynerini baslatir.
# yelpence-ros image'i (ROS+mavros ORTAMI) + host'taki ~/yelpence_ws kodunu (/ws)
# CANLI mount eder. Kod image'a GOMULU DEGIL -> degistirince image rebuild yok,
# sadece konteyner icinde `colcon build` (saniyeler).
#
# Kullanim:  ./run_drone.sh <AGENT_ID>          (orn: ./run_drone.sh 2)
# Durdur:    docker rm -f drone<AGENT_ID>
# Log:       docker logs -f drone<AGENT_ID>
#
# baslat.sh AGENT_ID ortam degiskenini okur (yoksa 1). ns=/drone_<AGENT_ID>.
set -euo pipefail

AGENT_ID="${1:?Kullanim: run_drone.sh <AGENT_ID>  (orn: 2)}"
WS_DIR="${WS_DIR:-$HOME/yelpence_ws}"
IMAGE="${IMAGE:-yelpence-ros:latest}"
NAME="drone${AGENT_ID}"
# Suru koordinasyonu env'leri (30 Temmuz). Konteynere GECMEZSE baslat.sh
# varsayilanlarini kullanir: SURU_DUGUMLERI bos (hicbir suru dugumu acilmaz),
# TAKIM_ID bos (kopru uyarir, QR gorevleri reddedilir), KANAT_ALFA 45.
#
#   SURU_DUGUMLERI="consensus"     -> kademeli acma, bkz baslat.sh
#   TAKIM_ID="YLP26"               -> QR takim filtresi icin ZORUNLU
SURU_DUGUMLERI="${SURU_DUGUMLERI:-}"
TAKIM_ID="${TAKIM_ID:-}"
KANAT_ALFA_DEG="${KANAT_ALFA_DEG:-45.0}"

if ! [[ "$AGENT_ID" =~ ^[0-9]+$ ]]; then
  echo "[HATA] AGENT_ID sayi olmali (orn: 2)"; exit 1
fi
if [ ! -d "$WS_DIR" ]; then
  echo "[HATA] Workspace yok: $WS_DIR (once rsync)"; exit 1
fi
if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "[HATA] '$NAME' zaten var. Sil:  docker rm -f $NAME"; exit 1
fi

echo "==> $NAME baslatiliyor (agent_id=$AGENT_ID, ws=$WS_DIR, image=$IMAGE)..."
docker run -d --name "$NAME" \
  --network host \
  --restart unless-stopped \
  --device /dev/ttyAMA0 \
  --device /dev/ttyAMA4 \
  --cap-add SYS_TIME \
  -v "$WS_DIR:/ws" \
  -e ROS_DOMAIN_ID=0 \
  -e AGENT_ID="$AGENT_ID" \
  -e SURU_DUGUMLERI="$SURU_DUGUMLERI" \
  -e TAKIM_ID="$TAKIM_ID" \
  -e KANAT_ALFA_DEG="$KANAT_ALFA_DEG" \
  "$IMAGE" \
  bash /ws/baslat.sh

echo "[TAMAM] $NAME basladi.  Log:  docker logs -f $NAME"
