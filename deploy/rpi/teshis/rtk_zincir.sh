#!/bin/bash
# Konteyner icinde kosar. $1 = agent_id
# RTCM zincirinin DRONE tarafindaki iki adimini olcer:
#   mesh -> esp32_bridge -> /drone_N/rtcm/in -> px4_bridge -> MAVROS send_rtcm
#
# px4_bridge tanisini get_logger().info ile basiyor, o yuzden ROS topic degil
# DUGUM LOGUNDAN okunur (bu oturumda kalici hale getirdigimiz /ws/gunluk).
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1

echo "   --- px4_bridge RTK tanisi (dugum logu, son 3 satir) ---"
LOGD=$(readlink -f /ws/gunluk/son 2>/dev/null)
if [ -n "$LOGD" ] && [ -d "$LOGD" ]; then
    grep -h "rtk: msg=" "$LOGD"/*px4* 2>/dev/null | tail -3 | sed 's/^/      /'
    [ -z "$(grep -h 'rtk: msg=' "$LOGD"/*px4* 2>/dev/null)" ] && echo "      (px4 logunda rtk satiri yok)"
else
    echo "      /ws/gunluk/son cozulemedi: '$LOGD'"
fi

echo "   --- MAVROS send_rtcm topic'ine YAYIN var mi ---"
timeout 15 ros2 topic info "/drone_${AID}/mavros/gps_rtk/send_rtcm" 2>&1 \
    | grep -E "Publisher count|Subscription count" | sed 's/^/      /'

echo "   --- GPS ham durumu (fix_type: 3=3D 4=DGPS 5=RTK_Float 6=RTK_Fixed) ---"
timeout 20 ros2 topic echo "/drone_${AID}/mavros/gpsstatus/gps1/raw" --once 2>/dev/null \
    | grep -E "fix_type|satellites_visible|h_acc|v_acc" | sed 's/^/      /'
