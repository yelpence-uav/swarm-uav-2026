#!/usr/bin/env bash
# Yelpence suru - RPi (Pi5 / Debian 13 trixie) host provizyonu.
# Taze bir Pi'yi drone calistirmaya hazir "temiz docker ortami"na getirir.
# YALNIZCA HOST'u hazirlar; ROS ortami (image) ve kod (workspace) ayri gelir:
#   1) sudo bash provision_pi.sh
#   2) sudo reboot                         # UART overlay + docker grubu icin SART
#   3) docker load < ~/yelpence-ros.tar.gz # ROS+mavros ortami (image)
#   4) rsync ile ~/yelpence_ws             # kod (host'ta, /ws'e mount edilir)
#   5) ./run_drone.sh <AGENT_ID>           # konteyneri baslat
#
# Not: ylp00 ile birebir parite. zram + DDS buffer'lari Debian imajinda ZATEN var,
# tekrar kurulmaz. Eklenen tek ekstra: docker log limiti (SD dolmasin).
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "[HATA] sudo ile calistir: sudo bash $0"
  exit 1
fi

TARGET_USER="${SUDO_USER:-yelpence}"
CFG="/boot/firmware/config.txt"

echo "==> [1/4] docker.io + socat kuruluyor..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io socat

echo "==> [2/4] '$TARGET_USER' -> docker + dialout gruplari..."
usermod -aG docker "$TARGET_USER"
usermod -aG dialout "$TARGET_USER"

echo "==> [3/4] UART overlay (ESP -> /dev/ttyAMA4) config.txt'e ekleniyor..."
if [ -f "$CFG" ]; then
  grep -q '^enable_uart=1'       "$CFG" || echo 'enable_uart=1'       >> "$CFG"
  grep -q '^dtoverlay=uart4-pi5' "$CFG" || echo 'dtoverlay=uart4-pi5' >> "$CFG"
  echo "    (enable_uart=1 + dtoverlay=uart4-pi5)"
else
  echo "[UYARI] $CFG yok; UART overlay elle eklenmeli."
fi

echo "==> [4/4] Docker log limiti (daemon.json)..."
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
JSON
systemctl restart docker || true

echo
echo "==> BITTI. REBOOT gerekli (UART overlay + docker grubu icin):"
echo "      sudo reboot"
echo "   Reboot sonrasi: docker load < ~/yelpence-ros.tar.gz && ./run_drone.sh <AGENT_ID>"
