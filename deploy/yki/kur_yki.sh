#!/bin/bash
# =============================================================================
# YKİ laptopu sıfırdan kurulum — Ubuntu 24.04 (noble) / ROS 2 Jazzy
#
# 20 Temmuz'da elle yapılan saha kurulumunun tekrarlanabilir
# hali. Tek fark: ROS apt deposu HTTP üzerinden eklenir, çünkü packages.ros.org
# şu an adını kapsamayan bir sertifika sunuyor (*.osuosl.org). Paketler GPG ile
# imzalı olduğu için bütünlük/kimlik doğrulaması aynen korunur; HTTPS'in tek
# kaybı hangi paketi indirdiğinin dışarıdan görünmesi.
#
# Kullanım:  bash deploy/yki/kur_yki.sh
# (sudo şifresi bir kez sorulur, sonrası cache'lenir)
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="${VENV:-$HOME/gcs-venv}"
ROS_DISTRO=jazzy

kirmizi() { printf '\033[31m%s\033[0m\n' "$*"; }
yesil()   { printf '\033[32m%s\033[0m\n' "$*"; }
mavi()    { printf '\033[36m\n=== %s ===\033[0m\n' "$*"; }

mavi "0/8  Ön kontrol"
. /etc/os-release
[ "${VERSION_CODENAME:-}" = "noble" ] || { kirmizi "Ubuntu 24.04 (noble) bekleniyordu, bulunan: ${VERSION_CODENAME:-?}"; exit 1; }
echo "repo : $REPO"
echo "venv : $VENV"
sudo -v   # şifreyi burada bir kez al

mavi "1/8  ROS 2 apt deposu (HTTP + GPG imzalı)"
sudo apt-get update -qq
sudo apt-get install -y -qq curl gnupg ca-certificates
curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  | sudo gpg --dearmor --yes -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $VERSION_CODENAME main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt-get update -qq
yesil "  depo eklendi"

mavi "2/8  ROS 2 $ROS_DISTRO (ros-base) + derleme araçları"
sudo apt-get install -y \
  ros-$ROS_DISTRO-ros-base \
  ros-$ROS_DISTRO-rmw-cyclonedds-cpp \
  python3-colcon-common-extensions python3-rosdep python3-venv \
  python3-serial git-lfs
yesil "  ros-base kuruldu"

mavi "3/8  MAVROS (swarm_control + swarm_state_machine bağımlılığı)"
sudo apt-get install -y \
  ros-$ROS_DISTRO-mavros ros-$ROS_DISTRO-mavros-extras \
  ros-$ROS_DISTRO-mavros-msgs ros-$ROS_DISTRO-geographic-msgs
yesil "  mavros kuruldu"

mavi "4/8  GeographicLib veri setleri"
# Bu laptopta mavros_node ÇALIŞMIYOR (o drone'larda) — burada sadece mavros_msgs
# import ediliyor. Veri setleri yine de kuruluyor ki ileride SITL/QGC köprüsü
# gerekirse hazır olsun. İndirme başarısız olursa kurulum DURMAZ.
if sudo /opt/ros/$ROS_DISTRO/lib/mavros/install_geographiclib_datasets.sh; then
  yesil "  veri setleri kuruldu"
else
  kirmizi "  UYARI: veri setleri kurulamadı — bu laptopta mavros_node çalışmadığı"
  kirmizi "         için YKİ'yi etkilemez. Drone'larda ise ZORUNLU."
fi

mavi "5/8  Node.js + npm (frontend Vite 5 için, Node 18+ yeterli)"
sudo apt-get install -y nodejs npm
echo "  node $(node --version)  npm $(npm --version)"

mavi "6/8  Python venv (GCS backend)"
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$REPO/src/gcs/backend/requirements.txt"
# numpy<2 ve lark backend requirements'ta yok, projenin genel src/requirements.txt'inden
# geliyorlar (20 Temmuz'da saptandı). Native kurulumda elle ekleniyor.
"$VENV/bin/pip" install --quiet "numpy<2.0.0" pytest lark flake8 pyserial
yesil "  venv hazır: $VENV"

mavi "7/8  colcon build"
# px4_autopilot boş bir submodule; colcon tarayıp uyarmasın.
[ -d "$REPO/src/px4_autopilot" ] && touch "$REPO/src/px4_autopilot/COLCON_IGNORE"
cd "$REPO"
set +u                                   # ROS setup.bash bağlanmamış değişken kullanır
source /opt/ros/$ROS_DISTRO/setup.bash
set -u
colcon build --symlink-install
yesil "  build tamam"

mavi "8/8  Frontend bağımlılıkları"
cd "$REPO/src/gcs/frontend"
npm install --no-fund --no-audit
yesil "  npm install tamam"

mavi "KURULUM TAMAM"
cat <<EOF
Sıradaki adım:

    bash $REPO/src/gcs/yki_baslat.sh

Arayüz  : http://localhost:5173/
Backend : http://localhost:8000/
Loglar  : /tmp/yki_base_bridge.log  /tmp/yki_backend.log  /tmp/yki_frontend.log
Durdur  : bash $REPO/src/gcs/yki_durdur.sh
EOF
