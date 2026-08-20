#!/bin/bash
# Konteyner icinde kosar. $1 = agent_id
#
# consensus_node'u baslat.sh:152-154'un KULLANDIGI KOMUTLA baslatir. Konteyneri
# yeniden yaratmak yerine bu yol secildi: calisan yigina (mavros/px4_bridge/
# esp32_bridge/kayit) dokunmuyoruz, sadece bir dugum ekliyoruz.
#
# agent_count KASTEN verilmiyor -> varsayilan 3 kaliyor, yani baslat.sh ile
# birebir ayni. Onemli: consensus_node ajan durumlarina 1..agent_count
# araliginda abone oluyor (consensus_node.py:124); 3 olmasa ylp02 (id=3) hic
# gorulmezdi.
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1

# Zaten kosuyorsa ikinci kopya baslatma (iki consensus ayni topic'e yayin
# yapar, secim sonuclari carpisir).
VAR=0
for p in $(ls /proc | grep -E '^[0-9]+$'); do
    c=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null) || continue
    case "$c" in
        *consensus_node*)
            case "$c" in *consensus_baslat.sh*) continue ;; esac
            VAR=1 ;;
    esac
done
if [ "$VAR" = 1 ]; then
    echo "   consensus_node ZATEN kosuyor, ikinci kopya baslatilmadi"
    exit 0
fi

LOG="/ws/gunluk/son/consensus.log"
# battery_min_v:=0.0 SART (21 Agustos'ta olculdu): parametresiz varsayilan
# 14.0, ama px4_bridge PX4 pil bildirmeyince 12.6 V SAHTESI basiyor ->
# 12.6 < 14.0 -> HERKES aday disi, sifir secim, sifir hata. baslat.sh:748
# ile birebir ayni parametreler kullanilmali.
setsid ros2 run swarm_core consensus_node --ros-args -p agent_id:="${AID}" \
    -p agent_count:=3 -p battery_min_v:=0.0 \
    > "$LOG" 2>&1 < /dev/null &
echo "   consensus_node baslatildi (agent_id=$AID), log: $LOG"
sleep 6
echo "   --- log ---"
grep -vE "^\s*$" "$LOG" 2>/dev/null | tail -6 | sed 's/^/      /'
