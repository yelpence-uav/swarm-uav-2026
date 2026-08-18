#!/bin/bash
# Konteyner icinde kosar. $1 = agent_id
# Here4 LED'i PX4'un DroneCAN uzerinden surdugu bir gosterge; iki dron
# arasindaki fark parametrede ya da DroneCAN sagliginda olmali. Tahmin
# yerine ikisini de ayni sekilde okuyup karsilastiriyoruz.
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1
N="/drone_${AID}/mavros/param"

echo "   --- GPS / sensor durumu ---"
timeout -s INT 20 ros2 topic echo "/swarm/internal/drone${AID}/status" --once 2>/dev/null \
    | grep -E "^(gps_fix_type|gps_satellites|gps_hdop|estimator_ok|xy_valid|z_valid|imu_healthy|mag_healthy|baro_healthy|home_set|ready_to_arm|healthy|failsafe_active):" \
    | sed 's/^/      /'

echo "   --- ham GPS (Here4 dogrudan) ---"
timeout -s INT 20 ros2 topic echo "/drone_${AID}/mavros/gpsstatus/gps1/raw" --once 2>/dev/null \
    | grep -E "^(fix_type|satellites_visible|h_acc|v_acc|dgps_numch):" | sed 's/^/      /'

echo "   --- UAVCAN / LED parametreleri ---"
for p in UAVCAN_ENABLE UAVCAN_PUB_RGB UAVCAN_SUB_GPS UAVCAN_SUB_GPS_R \
         UAVCAN_PUB_RTCM UAVCAN_BITRATE UAVCAN_NODE_ID \
         SENS_EN_LED SYS_MC_EST_GROUP CBRK_BUZZER; do
    printf "      %-18s = " "$p"
    timeout -s INT 15 ros2 param get "$N" "$p" 2>&1 | tail -1
done
