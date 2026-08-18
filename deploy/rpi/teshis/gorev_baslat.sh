#!/bin/bash
# ylp00 konteynerinde kosar. $1 = agent_id
#
# TAM ZINCIR TESTI (pervaneler cikarik, kullanici onayli):
#   EVENT_MISSION_STARTED -> preflight -> arm -> ARMED -> offboard -> TAKEOFF
# Kazanimlar:
#   1. Lider secimi SIFIR sahte girdiyle (state gercekten ARMED/TAKEOFF)
#   2. Lider kalp atisi ILK KEZ yayinlanir: _publish_heartbeat yalniz
#      is_leader && own_airborne iken kosuyor, TAKEOFF ise AIRBORNE_STATES'te
#   3. OFFBOARD'a gecis ve takeoff komutunun gonderilmesi
#
# GUVENLIK: sonda KOSULSUZ disarm var (trap ile de). Kullanici kumandayi elinde
# tutuyor. Pervanesiz motor yuk gormez, akim dusuk kalir.
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1
LOG="/ws/gunluk/son/consensus.log"

disarm_et() {
    timeout -s INT 20 ros2 service call "/drone_${AID}/mavros/cmd/arming" \
        mavros_msgs/srv/CommandBool '{value: false}' 2>&1 \
        | grep -E "success" | sed 's/^/      DISARM: /'
}
# Betik hangi sebeple biterse bitsin disarm calissin.
trap disarm_et EXIT

echo "   --- consensus yeniden baslatiliyor (lider=0 olsun ki secim gozlenebilsin) ---"
benim=$$
for p in $(ls /proc | grep -E '^[0-9]+$'); do
    [ "$p" = "$benim" ] && continue
    c=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null) || continue
    case "$c" in
        *consensus_node*)
            case "$c" in *gorev_baslat.sh*) continue ;; esac
            kill "$p" 2>/dev/null ;;
    esac
done
sleep 3
ISARET=$(wc -l < "$LOG")
setsid ros2 run swarm_core consensus_node --ros-args -p agent_id:="${AID}" \
    >> "$LOG" 2>&1 < /dev/null &
sleep 8
grep "incarnation=" "$LOG" | tail -1 | sed 's/^/      /'

# --- durum gecislerini KACIRMAMAK icin surekli kayit ---
timeout -s INT 40 ros2 topic echo "/swarm/internal/drone${AID}/status" \
    --field state > /tmp/state_izi.txt 2>&1 &
timeout -s INT 40 ros2 topic echo "/drone_${AID}/mavros/state" \
    --field mode > /tmp/mode_izi.txt 2>&1 &
# --- lider kalp atisi: ILK KEZ calisacak yol ---
timeout -s INT 40 ros2 topic echo "/swarm/internal/leader/heartbeat" \
    > /tmp/hb_izi.txt 2>&1 &
sleep 4

echo "   --- GOREV BASLATMA olayi yayinlaniyor (EVENT_MISSION_STARTED=24) ---"
timeout -s INT 5 ros2 topic pub -r 2 --qos-reliability reliable \
    /swarm/public/events/system swarm_interfaces/msg/SystemEvent \
    "{event_type: 24, source_agent_id: 0, target_agent_id: 0, value: 0.0, has_position: false, source_module: bench_testi, message: gorev_baslat}" \
    2>&1 | grep -iE "incompatible|error" | head -3

echo "   --- 22 sn izleniyor ---"
sleep 22

echo "   --- DURUM IZI (1=IDLE 2=ARMING 3=ARMED 4=TAKEOFF) ---"
grep -oE "^[0-9]+$" /tmp/state_izi.txt 2>/dev/null | uniq | tr '\n' ' ' | sed 's/^/      /'
echo
echo "   --- PX4 MOD IZI ---"
grep -vE "^---$|^\s*$|WARN" /tmp/mode_izi.txt 2>/dev/null | uniq | tr '\n' ' ' | sed 's/^/      /'
echo
echo "   --- SECIM (yeni satirlar) ---"
tail -n +$((ISARET+1)) "$LOG" | grep "CONSENSUS" | sed 's/^/      /'
echo "   --- LIDER KALP ATISI (ilk kez calismasi beklenen yol) ---"
grep -cE "leader_id" /tmp/hb_izi.txt 2>/dev/null | sed 's/^/      hb mesaj sayisi: /'
grep -A 1 "leader_id" /tmp/hb_izi.txt 2>/dev/null | head -6 | sed 's/^/      /'
