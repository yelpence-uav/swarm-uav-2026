#!/bin/bash
# Drone tarafi tam zincir: Pixhawk -> MAVROS -> px4_bridge -> agent_fsm -> esp32_bridge -> mesh
# AGENT_ID env ile parametrik (verilmezse 1 = eski ylp00 davranisi). ns=/drone_${AGENT_ID}.
# Konteynere run_drone.sh ile -e AGENT_ID=<N> gecilir. Drone'da /ws/baslat.sh olarak durur.
AGENT_ID="${AGENT_ID:-1}"
echo "[baslat] AGENT_ID=$AGENT_ID"
source /opt/ros/jazzy/setup.bash && source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1  # saha: DDS loopback-only, dis ag bagimsiz
ros2 run mavros mavros_node --ros-args -r __ns:=/drone_${AGENT_ID}/mavros -p fcu_url:=/dev/ttyAMA0:921600 > /tmp/mavros.log 2>&1 &
sleep 15
ros2 run swarm_control px4_bridge --ros-args -p agent_id:=${AGENT_ID} > /tmp/px4b.log 2>&1 &
sleep 5
ros2 run swarm_state_machine agent_fsm_node --ros-args -p agent_id:=${AGENT_ID} > /tmp/fsm.log 2>&1 &
sleep 5
# MAVLink yayin hizlari: FCU her resetlendiginde sifirlanir, her aciliste yeniden istenir
python3 /ws/mesaj_hizlari.py > /tmp/hizlar.log 2>&1
sleep 2
ros2 run swarm_control esp32_bridge --ros-args -p serial_port:=/dev/ttyAMA4 -p baud:=460800 -p agent_id:=${AGENT_ID} > /tmp/esp.log 2>&1 &

# --- Ucus kaydi (PX4 ULog'unun yerine gecen kayit) --------------------------
# Pixhawk'ta RAM sinirda oldugu icin FCU tarafinda logger ACILMIYOR. Onun
# yerine MAVROS'un ZATEN aldigi veriyi burada diske yaziyoruz: Pixhawk'a ek
# yuk binmez, veri hatta nasilsa akiyor.
#
# ULog'dan eksigi: PX4'un ic uORB konulari (kestirimci innovation'lari,
# aktuator ciktilari, ham sensor 250 Hz+) MAVLink'ten gecmez. Mevcut yayin
# hizlariyla (ATTITUDE_QUAT 20 Hz, ODOMETRY 20 Hz) 10 Hz'e kadar olan olaylar
# yakalanir — kaza/olay analizi icin yeter, EKF/kontrol ayari icin yetmez.
#
# 30 sn'lik parcalar: ucus 13-14 dk suruyor. Kaza aninda ACIK olan parca
# risk altindadir; 30 sn'de en fazla 30 sn kaybedilir. ros2 bag klasorun
# tamamini metadata.yaml uzerinden TEK kayit olarak gorur, parcalanma
# analizi zorlastirmaz.
# zstd: diskte ~3 kat tasarruf, Pi 5'te CPU maliyeti onemsiz.
# Konteyner UTC'de calisir, host Europe/Istanbul'da. TZ verilmezse kayit
# klasoru UTC damgasi alir ve sistem gunlukleriyle 3 saat kayar — bugun
# laptop/Pi arasinda yasadigimiz kayma sorununun aynisi. tzdata konteynerde
# mevcut, TZ calisiyor (dogrulandi).
export TZ=Europe/Istanbul
mkdir -p /ws/kayit
KAYIT_DIZIN="/ws/kayit/$(hostname)_$(date +%Y%m%d_%H%M%S)"
ros2 bag record \
    -e "^(/drone_${AGENT_ID}/|/swarm/)" \
    -o "$KAYIT_DIZIN" \
    --max-bag-duration 30 \
    --compression-mode file --compression-format zstd \
    > /tmp/kayit.log 2>&1 &
KAYIT_PID=$!

# Konteyner durdurulurken bag'i DUZGUN kapat.
# Docker yalniz PID 1'e (bu script) SIGTERM yollar, cocuklara yollamaz; ayrica
# ros2 bag'in bag'i kapatip indekslemesi icin SIGINT gerekir. Ikisi de
# yapilmazsa kayit yarim/indekssiz kalir ve acilmaz.
kapat() {
    kill -INT "$KAYIT_PID" 2>/dev/null
    wait "$KAYIT_PID" 2>/dev/null
    kill -TERM 0 2>/dev/null
}
trap kapat TERM INT

echo "tum dugumler basladi (kayit: $KAYIT_DIZIN)"
wait
