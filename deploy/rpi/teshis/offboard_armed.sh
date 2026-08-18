#!/bin/bash
# ylp00 konteynerinde kosar. $1 = agent_id
#
# TEK DEGISKEN: ARMED. Onceki iki deneyde dron DISARM idi ve 'offboard'
# komutu her seferinde tuttu (kumanda acikken de, kapaliyken de). tam_zincir
# testinde ise dron ARMED idi ve OFFBOARD tutmadi (offboard=False 9.3 sn).
# Burada disarm->arm disinda HICBIR SEY degismiyor.
#
# GUVENLIK: pervaneler cikarik. Sonda kosulsuz disarm (trap).
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1
KOMUT="/swarm/agent/drone${AID}/commands"

kapat() {
    timeout -s INT 20 ros2 service call "/drone_${AID}/mavros/cmd/arming" \
        mavros_msgs/srv/CommandBool '{value: false}' 2>&1 \
        | grep -E "success" | sed 's/^/      DISARM: /'
}
trap kapat EXIT

durum() {
    timeout -s INT 12 ros2 topic echo "/drone_${AID}/mavros/state" --once 2>/dev/null \
        | grep -E "^(armed|mode):" | tr -d ' ' | tr '\n' ' '
}
komut_gonder() {
    timeout -s INT 6 ros2 topic pub -1 "$KOMUT" std_msgs/msg/String \
        "{data: '$1'}" >/dev/null 2>&1
}

echo "   --- sifirlama: streaming kapat + AUTO.LOITER ---"
komut_gonder disarm
sleep 2
timeout -s INT 20 ros2 service call "/drone_${AID}/mavros/set_mode" \
    mavros_msgs/srv/SetMode '{base_mode: 0, custom_mode: "AUTO.LOITER"}' >/dev/null 2>&1
sleep 4
echo "      $(durum)"

echo "   --- ARM (tek degisken) ---"
timeout -s INT 25 ros2 service call "/drone_${AID}/mavros/cmd/arming" \
    mavros_msgs/srv/CommandBool '{value: true}' 2>&1 | grep -E "success" | sed 's/^/      /'
sleep 3
echo "      $(durum)"

echo "   --- ARMED iken 'offboard' komutu ---"
komut_gonder offboard
for i in 1 2 3; do
    sleep 3
    echo "      +$((i*3)) sn: $(durum)"
done

echo
echo "   BEKLENEN: disarm iken tutuyordu; armed iken TUTMUYORSA sebep bu."
