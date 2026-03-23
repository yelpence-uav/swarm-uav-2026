#!/bin/bash
set -e

# --- YELPENÇE ENTRYPOINT v9.4 ---

# 1. GUI Dizin Hazırlığı
if [ -n "$XDG_RUNTIME_DIR" ]; then
    sudo mkdir -p "$XDG_RUNTIME_DIR" >/dev/null 2>&1 || true
    sudo chmod 700 "$XDG_RUNTIME_DIR" >/dev/null 2>&1 || true
    sudo chown yelpence:yelpence "$XDG_RUNTIME_DIR" >/dev/null 2>&1 || true
fi

# 2. ROS Ortamını Yükle
source /opt/ros/jazzy/setup.bash
if [ -f "/home/yelpence/ros2_ws/install/setup.bash" ]; then
    source "/home/yelpence/ros2_ws/install/setup.bash"
fi

# 3. Devam Et
exec "$@"
