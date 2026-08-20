#!/bin/bash
# ylp00 konteynerinde kosar. $1 = agent_id
#
# TAMAMEN GERCEK lider secimi: hicbir sahte AgentStatus yok. Dron gercekten
# arm edilir, state STATE_ARMED(3) olur ve consensus kendi kendine secer.
#
# NEDEN ONCE consensus RESTART: _lider_id yapiskan. decide_change,
# ctx.leader_id == candidate ise None doner. Onceki sentetik testlerden
# leader_id=1 kalmis; sifirlamadan yeni bir secim GOZLENEMEZ.
#
# GUVENLIK: pervaneler cikarik (teyit edildi). PX4 COM_DISARM_PRENOTAKEOFF
# ile kendiliginden de disarm eder; yine de sonunda ACIKCA disarm ediyoruz.
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1
LOG="/ws/gunluk/son/consensus.log"

echo "   --- otomatik disarm penceresi ---"
printf "      COM_DISARM_PRENOTAKEOFF = "
timeout -s INT 20 ros2 param get "/drone_${AID}/mavros/param" \
    COM_DISARM_PRENOTAKEOFF 2>&1 | tail -1

echo "   --- consensus yeniden baslatiliyor (lider=0 olsun) ---"
benim=$$
for p in $(ls /proc | grep -E '^[0-9]+$'); do
    [ "$p" = "$benim" ] && continue
    c=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null) || continue
    case "$c" in
        *consensus_node*)
            case "$c" in *arm_secim.sh*) continue ;; esac
            kill "$p" 2>/dev/null && echo "      durduruldu PID $p" ;;
    esac
done
sleep 3
ISARET=$(wc -l < "$LOG")
# battery_min_v:=0.0 SART (21 Agustos'ta olculdu): parametresiz varsayilan
# 14.0, ama px4_bridge PX4 pil bildirmeyince 12.6 V SAHTESI basiyor ->
# 12.6 < 14.0 -> HERKES aday disi, sifir secim, sifir hata. baslat.sh:748
# ile birebir ayni parametreler kullanilmali.
setsid ros2 run swarm_core consensus_node --ros-args -p agent_id:="${AID}" \
    -p agent_count:=3 -p battery_min_v:=0.0 \
    >> "$LOG" 2>&1 < /dev/null &
sleep 8
grep "incarnation=" "$LOG" | tail -1 | sed 's/^/      /'

echo "   --- arm ONCESI: secim var mi (olmamali, state=IDLE) ---"
S=$(tail -n +$((ISARET+1)) "$LOG" | grep -c "CONSENSUS. Lider")
echo "      yeni secim satiri: $S"

echo "   --- ready_to_arm + ARM ---"
timeout -s INT 12 ros2 topic echo "/swarm/internal/drone${AID}/status" --once 2>/dev/null \
    | grep -E "^(state|armed|healthy|ready_to_arm):" | tr -d ' ' | tr '\n' ' ' | sed 's/^/      /'
echo
timeout -s INT 25 ros2 service call "/drone_${AID}/mavros/cmd/arming" \
    mavros_msgs/srv/CommandBool '{value: true}' 2>&1 \
    | grep -E "success|result" | sed 's/^/      /'

echo "   --- arm SONRASI ornekler ---"
for i in 1 2 3 4; do
    S=$(timeout -s INT 6 ros2 topic echo "/swarm/internal/drone${AID}/status" \
        --once 2>/dev/null | grep -E "^(state|armed|healthy):" | tr -d ' ' | tr '\n' ' ')
    echo "      ornek $i: $S"
done

echo "   --- GERCEK SECIM (arm sonrasi yeni satirlar) ---"
tail -n +$((ISARET+1)) "$LOG" | grep "CONSENSUS" | sed 's/^/      /'

echo "   --- DISARM ---"
timeout -s INT 20 ros2 service call "/drone_${AID}/mavros/cmd/arming" \
    mavros_msgs/srv/CommandBool '{value: false}' 2>&1 \
    | grep -E "success|result" | sed 's/^/      /'
