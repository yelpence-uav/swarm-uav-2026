#!/bin/bash
# ylp00 konteynerinde kosar. $1 = agent_id
#
# AMAC: gercekten arm edip lider secimini SIFIR sahte girdiyle test etmek.
# ready_to_arm=false geldigi icin PX4 reddedebilir; o zaman STATUSTEXT'ten
# GEREKCEYI okuyacagiz - tahmin etmeyecegiz.
#
# GUVENLIK: pervaneler cikarik (kullanici teyit etti). PX4
# COM_DISARM_PRENOTAKEOFF varsayilani ~10 sn, yani arm olursa kendiliginden
# de disarm olur; yine de sonunda ACIKCA disarm ediyoruz.
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1
LOG="/ws/gunluk/son/consensus.log"
ST=/tmp/statustext.txt

# 1) PX4'un aciklamalarini yakala (arm reddi gerekcesi buradan gelir)
timeout -s INT 45 ros2 topic echo "/drone_${AID}/mavros/statustext/recv" \
    --field text > "$ST" 2>&1 &
sleep 4

echo "   --- ARM denemesi ---"
timeout -s INT 25 ros2 service call "/drone_${AID}/mavros/cmd/arming" \
    mavros_msgs/srv/CommandBool '{value: true}' 2>&1 \
    | grep -E "success|result" | sed 's/^/      /'

# 2) Arm penceresi kisa (~10 sn); durumu hizli ornekle
for i in 1 2 3; do
    S=$(timeout -s INT 8 ros2 topic echo "/swarm/internal/drone${AID}/status" \
        --once 2>/dev/null \
        | grep -E "^(state|armed|healthy|ready_to_arm):" | tr -d ' ' | tr '\n' ' ')
    echo "      ornek $i: $S"
done

echo "   --- consensus: GERCEK secim oldu mu ---"
grep "CONSENSUS. Lider" "$LOG" 2>/dev/null | tail -3 | sed 's/^/      /'

echo "   --- DISARM ---"
timeout -s INT 20 ros2 service call "/drone_${AID}/mavros/cmd/arming" \
    mavros_msgs/srv/CommandBool '{value: false}' 2>&1 \
    | grep -E "success|result" | sed 's/^/      /'

echo "   --- PX4 STATUSTEXT (arm reddi gerekcesi) ---"
sort -u "$ST" 2>/dev/null | grep -viE "^---$|^\s*$" | head -12 | sed 's/^/      /'
