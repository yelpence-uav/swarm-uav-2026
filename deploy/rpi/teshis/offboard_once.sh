#!/bin/bash
# ylp00 konteynerinde kosar. $1 = agent_id
#
# ONERILEN DUZELTMENIN DOGRULAMASI: once OFFBOARD, sonra ARM.
#
# Olculen kok sebep: PX4 ARMLIYKEN yerde OFFBOARD'a gecmiyor. FSM ise
# _dispatch_px4_command'da ARMING->'arm', ARMED->'offboard' yapiyor; yani
# once armliyor sonra mod degistirmeye calisiyor -> PX4 reddediyor -> FSM
# ARMED'da sonsuza kadar takiliyor (olculdu: offboard=False 9.3 sn).
#
# Burada sirayi TERSINE cevirip PX4'un armli halde OFFBOARD'da KALIP
# kalmadigini olcuyoruz. Tutuyorsa duzeltme nettir: OFFBOARD arm'dan ONCE.
#
# GUVENLIK: pervaneler cikarik. Kalkis hedefi verilmiyor, yani setpoint
# "anlik konumda bekle" (px4_bridge.py:565-570) -> tirmanma komutu YOK.
# Trap ile kosulsuz disarm.
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

echo "   --- sifirlama ---"
komut_gonder disarm
sleep 2
timeout -s INT 20 ros2 service call "/drone_${AID}/mavros/set_mode" \
    mavros_msgs/srv/SetMode '{base_mode: 0, custom_mode: "AUTO.LOITER"}' >/dev/null 2>&1
sleep 4
echo "      $(durum)"

echo "   --- ADIM 1: DISARM iken OFFBOARD ---"
komut_gonder offboard
sleep 6
echo "      $(durum)"

echo "   --- ADIM 2: simdi ARM (OFFBOARD'da kalmali) ---"
timeout -s INT 25 ros2 service call "/drone_${AID}/mavros/cmd/arming" \
    mavros_msgs/srv/CommandBool '{value: true}' 2>&1 | grep -E "success" | sed 's/^/      /'
for i in 1 2 3 4; do
    sleep 3
    echo "      +$((i*3)) sn: $(durum)"
done

echo
echo "   BEKLENEN: adim 2 boyunca mode=OFFBOARD ve armed=true kalmali."
echo "   Tutarsa duzeltme kesin: OFFBOARD arm'dan ONCE istenmeli."
