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
# GOREV 2 — SURU kumandasinin i-BUS alicisi (YALNIZ pilot ucaginda takili).
# Sartname 5.2 kill switch icin AYRI kumanda + AYRI pilot zorunlu kiliyor,
# yani Pixhawk'in tek RC girisi ONA ait; suru kumandasinin alicisi Pi'ye
# i-BUS ile baglaniyor (gorev2.md B1).
SURU_RC_PORT="${SURU_RC_PORT:-/dev/ttyUSB0}"

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

# --- Suru RC alicisi: VARSA konteynere ver, YOKSA sessizce gec -------------
# Bu ucak pilot ucagi degilse alici takili olmaz ve `--device` OLMAYAN bir
# yol icin `docker run` HATA verip konteyneri hic acmaz. O yuzden kosullu.
#
# by-id yolu COZULUYOR: `docker --device` sembolik bagi degil gercek dugumu
# ister. Bedeli su — alici baska bir USB portuna takilirsa ttyUSB numarasi
# degisir ve KONTEYNER YENIDEN OLUSTURULMALIDIR (restart yetmez). Bu
# `--device`in dogasi, kacisi yok; alicinin portunu sabit tut.
RC_DEVICE=()
if [ -e "$SURU_RC_PORT" ]; then
  _rc_gercek="$(readlink -f "$SURU_RC_PORT")"
  RC_DEVICE=(--device "$_rc_gercek")
  SURU_RC_PORT="$_rc_gercek"
  echo "==> suru RC alicisi: $SURU_RC_PORT (konteynere veriliyor)"
else
  echo "==> suru RC alicisi YOK ($SURU_RC_PORT) — bu ucak PILOT UCAGI DEGIL."
  echo "    Pilot ucagiysa: alici takili mi, /ws/suru_dugumleri'nde 'joystick' var mi?"
fi

# LOG DONDURME — 20 Agustos 2026.
#
# OLCULDU (ylp00): docker'in json-file logu 16 Agustos 23:34'te iki NUL
# bosluguna (1602 + 433 bayt) sahip oldu; `docker logs` TAM okumada
# "invalid character '\x00'" ile cokuyor. `--tail N` calisiyor cunku sondan
# okuyor, `--since` ve bayraksiz cagri BASTAN tarayip bosluga carpiyor.
# Ayni gun olusturulan drone3'te 0 NUL — yani sistemik degil, tekil olay.
#
# Dondurme olmadan bozuk segment ORADA KALIYOR: dosya hic donmedigi icin
# konteyner yeniden olusturulana kadar `docker logs` kalici sakat. max-file
# ile bozuk parca zamanla kendiliginden dusuyor.
#
# Yerinde `truncate` COZUM DEGIL, daha kotu: docker dosyayi O_APPEND ile
# acik tutuyor, kesilince eski ofsetten yazmaya devam eder ve basinda dev
# bir NUL blogu olan seyrek dosya olusur.
#
# 10m x 3 secildi: ylp00'da 5 gunde 693 KB birikti (drone3'te 147 KB), yani
# 30 MB tavan aylarca yetiyor ve 29 GB kartta yer sorunu degil.
# ROS_LOCALHOST_ONLY NEDEN BURADA (26 Agustos 2026)
# baslat.sh de export ediyor, ama orasi konteynerin KOMUTU — `docker exec` onu
# MIRAS ALMIYOR. Belirti sessiz ve kotu: `docker exec ... ros2 topic echo`
# dugumleri HIC goremez, hata da vermez, bos doner. O gun canli uctan armed
# durumu okunamadi ve once "MAVROS olmus" sanildi. `docker run -e` ile verilince
# konteyner yapilandirmasina yazilir ve her `docker exec` otomatik alir.
# DIKKAT: yalniz konteyner YENIDEN OLUSTURULUNCA gecerli olur; restart yetmez.
docker run -d --name "$NAME" \
  --network host \
  --restart unless-stopped \
  --log-opt max-size=10m --log-opt max-file=3 \
  --device /dev/ttyAMA0 \
  --device /dev/ttyAMA4 \
  ${RC_DEVICE[@]+"${RC_DEVICE[@]}"} \
  --cap-add SYS_TIME \
  -v "$WS_DIR:/ws" \
  -e ROS_DOMAIN_ID=0 \
  -e ROS_LOCALHOST_ONLY=1 \
  -e AGENT_ID="$AGENT_ID" \
  -e SURU_DUGUMLERI="$SURU_DUGUMLERI" \
  -e TAKIM_ID="$TAKIM_ID" \
  -e KANAT_ALFA_DEG="$KANAT_ALFA_DEG" \
  -e SURU_RC_PORT="$SURU_RC_PORT" \
  "$IMAGE" \
  bash /ws/baslat.sh

echo "[TAMAM] $NAME basladi.  Log:  docker logs -f $NAME"
