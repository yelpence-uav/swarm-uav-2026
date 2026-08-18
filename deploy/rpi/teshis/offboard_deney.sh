#!/bin/bash
# ylp00 konteynerinde kosar. $1 = agent_id
#
# HIPOTEZ: px4_bridge 'offboard' komutunda _offboard_streaming=True ile
# set_offboard_mode()'u AYNI ANDA cagiriyor (px4_bridge.py:698-699). PX4 ise
# OFFBOARD'a gecmeden once ~1 sn setpoint akisi gormek ister. Yani ILK talep
# daima erken gidiyor ve sessizce reddediliyor. Yeniden deneme dongusu
# `if self._sitl_mode:` ile korunuyor -> GERCEK DONANIMDA HIC TEKRAR YOK.
#
# Log yaniltici: "MOD(OFFBOARD) KABUL edildi" MAVROS'un mode_sent=True
# yanitini yaziyor; bu yalniz "komut gonderildi" demek, "PX4 moda gecti"
# demek DEGIL.
#
# DENEY (dron DISARM kalir, guvenli):
#   A kolu: streaming KAPALI iken TEK 'offboard' -> mod OFFBOARD olmamali
#   B kolu: streaming ACIK iken tekrar 'offboard' -> mod OFFBOARD olmali
# Tek degisken: komut oncesi setpoint akisinin sure olarak var olup olmamasi.
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1
KOMUT="/swarm/agent/drone${AID}/commands"

mod_oku() {
    timeout -s INT 12 ros2 topic echo "/drone_${AID}/mavros/state" --field mode --once 2>/dev/null \
        | grep -vE "^\s*$|WARN|^\[" | head -1
}
armed_oku() {
    timeout -s INT 12 ros2 topic echo "/drone_${AID}/mavros/state" --field armed --once 2>/dev/null \
        | grep -vE "^\s*$|WARN|^\[" | head -1
}
komut_gonder() {  # $1 = komut metni
    timeout -s INT 6 ros2 topic pub -1 "$KOMUT" std_msgs/msg/String \
        "{data: '$1'}" >/dev/null 2>&1
}

echo "   --- SIFIRLAMA: streaming kapat + AUTO.LOITER ---"
komut_gonder disarm          # _offboard_streaming = False
sleep 2
timeout -s INT 20 ros2 service call "/drone_${AID}/mavros/set_mode" \
    mavros_msgs/srv/SetMode '{base_mode: 0, custom_mode: "AUTO.LOITER"}' \
    >/dev/null 2>&1
sleep 5
echo "      armed: $(armed_oku)   mod: $(mod_oku)"

echo "   --- A KOLU: streaming KAPALI iken TEK 'offboard' ---"
komut_gonder offboard
sleep 7
MOD_A=$(mod_oku)
echo "      6 sn sonra mod: $MOD_A"

echo "   --- B KOLU: streaming ARTIK ACIK, ayni komut tekrar ---"
komut_gonder offboard
sleep 7
MOD_B=$(mod_oku)
echo "      6 sn sonra mod: $MOD_B"

echo
echo "   SONUC:  A='$MOD_A'  B='$MOD_B'"
echo "   BEKLENEN: A OFFBOARD DEGIL, B OFFBOARD  -> tek talep yetmiyor, tekrar sart"
echo "   --- guvenlik: armed durumu ---"
echo "      armed: $(armed_oku)"
