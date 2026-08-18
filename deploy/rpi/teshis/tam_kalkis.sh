#!/bin/bash
# ylp00 konteynerinde kosar. $1 = agent_id
#
# TAM AKIS: EVENT_MISSION_STARTED -> ARMING -> ARMED -> TAKEOFF
# Hedef: TAKEOFF durumuna ulasmak. Cunku AIRBORNE_STATES = {TAKEOFF,
# IN_SWARM, EXECUTING_TASK} ve consensus_node'daki
#     if ctx.is_leader and own_airborne: self._publish_heartbeat(...)
# satiri yalnizca o zaman kosuyor. LIDER KALP ATISI HIC CALISMADI; bu testin
# asil kazanimi o.
#
# PERVANE GEREKMIYOR: TAKEOFF'a gecis gercek irtifaya degil, _from_armed'in
# kosullarina bagli (armed + healthy + mission_start + offboard_active +
# 2 sn). Pervane takmak bunu kapali mekanda gercek ucusa cevirirdi.
#
# GUVENLIK: trap ile AUTO.LOITER -> normal disarm -> gerekirse zorla disarm.
# Armli pencere ~35 sn ile sinirli.
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1
LOG="/ws/gunluk/son/consensus.log"

indir() {
    echo "   --- GUVENLI INDIRME ---"
    # OFFBOARD'dayken disarm reddediliyor (bugun olculdu): once LOITER.
    timeout -s INT 15 ros2 service call "/drone_${AID}/mavros/set_mode" \
        mavros_msgs/srv/SetMode '{base_mode: 0, custom_mode: "AUTO.LOITER"}' \
        >/dev/null 2>&1
    sleep 2
    timeout -s INT 15 ros2 service call "/drone_${AID}/mavros/cmd/arming" \
        mavros_msgs/srv/CommandBool '{value: false}' 2>&1 \
        | grep success | sed 's/^/      normal disarm: /'
    sleep 2
    A=$(timeout -s INT 10 ros2 topic echo "/drone_${AID}/mavros/state" \
        --field armed --once 2>/dev/null | head -1)
    if [ "$A" = "True" ]; then
        timeout -s INT 15 ros2 service call "/drone_${AID}/mavros/cmd/command" \
            mavros_msgs/srv/CommandLong \
            '{broadcast: false, command: 400, confirmation: 0, param1: 0.0, param2: 21196.0, param3: 0.0, param4: 0.0, param5: 0.0, param6: 0.0, param7: 0.0}' \
            2>&1 | grep success | sed 's/^/      ZORLA disarm: /'
    fi
    sleep 2
    echo "      son: $(timeout -s INT 10 ros2 topic echo "/drone_${AID}/mavros/state" --once 2>/dev/null | grep -E '^(armed|mode):' | tr -d ' ' | tr '\n' ' ')"
}
trap indir EXIT

echo "   --- 1) pilot override kalksin (AUTO.LOITER) ---"
timeout -s INT 15 ros2 service call "/drone_${AID}/mavros/set_mode" \
    mavros_msgs/srv/SetMode '{base_mode: 0, custom_mode: "AUTO.LOITER"}' \
    >/dev/null 2>&1
sleep 4
timeout -s INT 12 ros2 topic echo "/swarm/internal/drone${AID}/status" --once 2>/dev/null \
    | grep -E "^(state|pilot_override_active|status_text):" | sed 's/^/      /'

echo "   --- 2) consensus sifirlaniyor (lider=0) ---"
benim=$$
for p in $(ls /proc | grep -E '^[0-9]+$'); do
    [ "$p" = "$benim" ] && continue
    c=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null) || continue
    case "$c" in
        *consensus_node*) case "$c" in *tam_kalkis.sh*) continue ;; esac
            kill "$p" 2>/dev/null ;;
    esac
done
sleep 3
ISARET=$(wc -l < "$LOG")
setsid ros2 run swarm_core consensus_node --ros-args -p agent_id:="${AID}" \
    >> "$LOG" 2>&1 < /dev/null &
sleep 8
grep "incarnation=" "$LOG" | tail -1 | sed 's/^/      /'

# --- izleyiciler ---
timeout -s INT 60 ros2 topic echo "/swarm/internal/drone${AID}/status" \
    --field state > /tmp/st.txt 2>&1 &
timeout -s INT 60 ros2 topic echo "/drone_${AID}/mavros/state" \
    --field mode > /tmp/md.txt 2>&1 &
timeout -s INT 60 ros2 topic echo "/swarm/internal/leader/heartbeat" \
    > /tmp/hb.txt 2>&1 &
sleep 4

echo "   --- 3) GOREV BASLATMA ---"
timeout -s INT 6 ros2 topic pub -r 2 /swarm/public/events/system \
    swarm_interfaces/msg/SystemEvent \
    "{event_type: 24, source_agent_id: 0, target_agent_id: 0, value: 0.0, has_position: false, source_module: bench, message: gorev}" \
    >/dev/null 2>&1

echo "   --- 4) 30 sn izleniyor ---"
sleep 30

echo "   --- DURUM IZI (1=IDLE 2=ARMING 3=ARMED 4=TAKEOFF 5=IN_SWARM 14=FAILSAFE) ---"
grep -oE "^[0-9]+$" /tmp/st.txt 2>/dev/null | uniq | tr '\n' ' ' | sed 's/^/      /'; echo
echo "   --- PX4 MOD IZI ---"
grep -vE "^---$|^\s*$|WARN|^\[" /tmp/md.txt 2>/dev/null | uniq | tr '\n' ' ' | sed 's/^/      /'; echo
echo "   --- SECIM ---"
tail -n +$((ISARET+1)) "$LOG" | grep "CONSENSUS" | sed 's/^/      /'
echo "   --- LIDER KALP ATISI (ILK KEZ calismasi beklenen yol) ---"
N=$(grep -c "leader_id" /tmp/hb.txt 2>/dev/null)
echo "      hb mesaj sayisi: ${N:-0}"
grep -E "leader_id|sequence_num|active_agent_count|mission_active" /tmp/hb.txt 2>/dev/null \
    | head -8 | sed 's/^/      /'
echo "   --- fsm.log ---"
grep -viE "^\s*$|ROS_LOCALHOST|localhost_only" "$(readlink -f /ws/gunluk/son)/fsm.log" 2>/dev/null \
    | tail -10 | sed 's/^/      /'
