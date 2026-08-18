#!/bin/bash
# Konteyner icinde kosar. $1 = agent_id (1 veya 3), $2 = "oku" | "yaz"
# set -u KULLANILMIYOR: ROS setup.bash icinde tanimsiz degisken
# referanslari var (AMENT_TRACE_SETUP_FILES) ve source patliyor.
AID="$1"
MOD="$2"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1
NODE="/drone_${AID}/mavros/param"

echo "   --- FCU parametreleri cekiliyor (force_pull) ---"
timeout 90 ros2 service call "${NODE}/pull" mavros_msgs/srv/ParamPull \
    '{force_pull: true}' 2>&1 | grep -E "success|param_received" | sed 's/^/      /'

oku() {
    for p in UAVCAN_PUB_RTCM UAVCAN_SUB_GPS_R UAVCAN_ENABLE GPS_1_CONFIG; do
        printf "      %-18s = " "$p"
        timeout 25 ros2 param get "$NODE" "$p" 2>&1 | tail -1
    done
}

echo "   --- MEVCUT ---"
oku

if [ "$MOD" = "yaz" ]; then
    echo "   --- UAVCAN_PUB_RTCM = 1 yaziliyor ---"
    timeout 30 ros2 param set "$NODE" UAVCAN_PUB_RTCM 1 2>&1 | sed 's/^/      /'
    sleep 3
    echo "   --- FCU'ya kalici yazim (param/push) ---"
    timeout 60 ros2 service call "${NODE}/push" mavros_msgs/srv/ParamPush \
        '{}' 2>&1 | grep -E "success|param_transfered" | sed 's/^/      /'
    sleep 2
    echo "   --- GERI OKUMA (FCU'dan tekrar cekerek) ---"
    timeout 90 ros2 service call "${NODE}/pull" mavros_msgs/srv/ParamPull \
        '{force_pull: true}' 2>&1 | grep -E "success" | sed 's/^/      /'
    sleep 2
    oku
fi
