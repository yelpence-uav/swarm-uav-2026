#!/bin/bash
# ylp00 konteynerinde kosar. $1 = agent_id (1)
#
# DUZELTMENIN UCTAN UCA KANITI.
#
# Once: lider secim yapar, seq=1 ile yayinlar. ylp02 kaydeder (kaynak 1, inc X,
#        seq 1).
# Sonra: liderin consensus_node'u YENIDEN BASLATILIR -> out_seq 0'a doner,
#        incarnation degisir. Yeni secim yine seq=1 ile cikar.
#
# ESKI KODDA: ylp02 "seq 1 <= gorulen 1" deyip SESSIZCE duserdi.
# YENI KODDA: incarnation degistigi icin sayac sifirlanir ve ylp02 loglar:
#             "ajan 1 yeniden baslamis (incarnation -> Y), seq sayaci sifirlandi"
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1
LOG="/ws/gunluk/son/consensus.log"

consensus_durdur() {
    local benim=$$
    for p in $(ls /proc | grep -E '^[0-9]+$'); do
        [ "$p" = "$benim" ] && continue
        local c
        c=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null) || continue
        case "$c" in
            *consensus_node*)
                case "$c" in *inc_dogrula.sh*|*consensus_baslat.sh*) continue ;; esac
                kill "$p" 2>/dev/null && echo "      consensus durduruldu (PID $p)"
                ;;
        esac
    done
}

echo "   --- 1) ILK SECIM (mevcut incarnation) ---"
timeout -s INT 12 bash /ws/durum_enjekte.sh "$AID" 12 >/dev/null 2>&1
grep "CONSENSUS" "$LOG" 2>/dev/null | tail -2 | sed 's/^/      /'

echo "   --- 2) LIDERIN consensus_node'u YENIDEN BASLATILIYOR ---"
consensus_durdur
sleep 3
setsid ros2 run swarm_core consensus_node --ros-args -p agent_id:="${AID}" \
    >> "$LOG" 2>&1 < /dev/null &
sleep 7
grep "incarnation=" "$LOG" 2>/dev/null | tail -2 | sed 's/^/      /'

echo "   --- 3) IKINCI SECIM (yeni incarnation, seq YINE 1'den) ---"
timeout -s INT 12 bash /ws/durum_enjekte.sh "$AID" 12 >/dev/null 2>&1
grep "CONSENSUS" "$LOG" 2>/dev/null | tail -2 | sed 's/^/      /'
