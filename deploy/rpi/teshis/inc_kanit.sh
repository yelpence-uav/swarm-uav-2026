#!/bin/bash
# ylp00 konteynerinde kosar. $1 = agent_id
#
# ylp02'de simdi (ajan 1, incarnation 11724, seq 1) kaydi var. Bu betik:
#   1. ylp00'in consensus_node'unu yeniden baslatir -> YENI incarnation,
#      out_seq 0'a doner
#   2. Yeni secim tetikler -> seq YINE 1 ile yayinlanir
# ESKI KODDA ylp02 "seq 1 <= gorulen 1" deyip sessizce duserdi.
# YENI KODDA incarnation degistigi icin kabul eder ve LOGLAR.
#
# Onceki denemede secim olmamasinin sebebi ic ice timeout'tu: durum_enjekte.sh
# kendi icinde 12 sn timeout kullaniyor, ben onu 12 sn'lik ikinci bir timeout
# ile sarmisim; ROS setup + discovery gecikmesi eklenince yayin bootstrap
# grace'i (1.5 sn) doldurmaya yetmeden kesilmis. Burada TEK timeout var ve
# sure 25 sn.
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1
LOG="/ws/gunluk/son/consensus.log"

benim=$$
for p in $(ls /proc | grep -E '^[0-9]+$'); do
    [ "$p" = "$benim" ] && continue
    c=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null) || continue
    case "$c" in
        *consensus_node*)
            case "$c" in *inc_kanit.sh*) continue ;; esac
            kill "$p" 2>/dev/null && echo "   consensus durduruldu (PID $p)"
            ;;
    esac
done
sleep 3

setsid ros2 run swarm_core consensus_node --ros-args -p agent_id:="${AID}" \
    >> "$LOG" 2>&1 < /dev/null &
sleep 8
echo "   yeni incarnation:"
grep "incarnation=" "$LOG" | tail -1 | sed 's/^/      /'

echo "   ARMED enjekte ediliyor (25 sn, TEK timeout)..."
timeout -s INT 25 ros2 topic pub -r 20 \
    "/swarm/internal/drone${AID}/status" \
    swarm_interfaces/msg/AgentStatus \
    "{agent_id: ${AID}, role: 0, state: 3, px4_link_ok: true, armed: true, healthy: true, battery_voltage_v: 15.0, estimator_ok: true, xy_valid: true, z_valid: true, v_xy_valid: true, origin_synced: true, rc_link_ok: true, status_text: inc_kaniti}" \
    >/dev/null 2>&1

echo "   ylp00 secim sonucu:"
grep "CONSENSUS. Lider" "$LOG" | tail -2 | sed 's/^/      /'
