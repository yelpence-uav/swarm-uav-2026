#!/bin/bash
# ylp00 konteynerinde kosar. $1 = agent_id
#
# TAM ZINCIR, engel kaldirilarak:
#   PX4 POSCTL'de oldugu icin pilot_override_active=true idi ve
#   evaluate_transitions'in basindaki
#       if ctx.autonomous_control_paused or ctx.hold_active: return None
#   kapisi TUM gecisleri sessizce blokluyordu (olculdu: status_text = "Pilot
#   override active", state IDLE'da donmus).
#
#   PILOT_FLIGHT_MODES = {1,2,3,9,10} = MANUAL/ALTCTL/POSCTL/ACRO/STABILIZED.
#   AUTO.LOITER(6) pilot modu DEGIL - kumanda acilmadan once PX4 zaten
#   oradaydi. Moda geri alinca otonomi devam eder.
#
# GUVENLIK: pervaneler cikarik, kullanici kalkisi onayladi, kumanda elinde.
# trap ile kosulsuz disarm.
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1
LOG="/ws/gunluk/son/consensus.log"

kapat() {
    timeout -s INT 20 ros2 service call "/drone_${AID}/mavros/cmd/arming" \
        mavros_msgs/srv/CommandBool '{value: false}' 2>&1 \
        | grep -E "success" | sed 's/^/      DISARM: /'
}
trap kapat EXIT

echo "   --- 1) PX4 AUTO.LOITER'a aliniyor (pilot override kalksin) ---"
timeout -s INT 20 ros2 service call "/drone_${AID}/mavros/set_mode" \
    mavros_msgs/srv/SetMode '{base_mode: 0, custom_mode: "AUTO.LOITER"}' 2>&1 \
    | grep -E "mode_sent" | sed 's/^/      /'
sleep 5
echo "   --- override kalkti mi ---"
timeout -s INT 15 ros2 topic echo "/swarm/internal/drone${AID}/status" --once 2>/dev/null \
    | grep -E "^(state|flight_mode|pilot_override_active|status_text):" | sed 's/^/      /'

echo "   --- 2) consensus sifirlaniyor (lider=0) ---"
benim=$$
for p in $(ls /proc | grep -E '^[0-9]+$'); do
    [ "$p" = "$benim" ] && continue
    c=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null) || continue
    case "$c" in
        *consensus_node*) case "$c" in *tam_zincir.sh*) continue ;; esac
            kill "$p" 2>/dev/null ;;
    esac
done
sleep 3
ISARET=$(wc -l < "$LOG")
setsid ros2 run swarm_core consensus_node --ros-args -p agent_id:="${AID}" \
    >> "$LOG" 2>&1 < /dev/null &
sleep 8
grep "incarnation=" "$LOG" | tail -1 | sed 's/^/      /'

# izleyiciler
timeout -s INT 55 ros2 topic echo "/swarm/internal/drone${AID}/status" \
    --field state > /tmp/st.txt 2>&1 &
timeout -s INT 55 ros2 topic echo "/drone_${AID}/mavros/state" \
    --field mode > /tmp/md.txt 2>&1 &
timeout -s INT 55 ros2 topic echo "/swarm/internal/leader/heartbeat" \
    --field leader_id > /tmp/hb.txt 2>&1 &
sleep 4

echo "   --- 3) GOREV BASLATMA ---"
timeout -s INT 8 ros2 topic pub -r 2 /swarm/public/events/system \
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
echo "   --- LIDER KALP ATISI (ilk kez calismasi beklenen yol) ---"
N=$(grep -cE "^[0-9]+$" /tmp/hb.txt 2>/dev/null)
echo "      hb mesaj sayisi: ${N:-0}"
grep -oE "^[0-9]+$" /tmp/hb.txt 2>/dev/null | uniq | head -3 | sed 's/^/      lider_id: /'
echo "   --- fsm.log son satirlar ---"
grep -viE "^\s*$|ROS_LOCALHOST|localhost_only" "$(readlink -f /ws/gunluk/son)/fsm.log" 2>/dev/null \
    | tail -8 | sed 's/^/      /'
