#!/bin/bash
# Konteyner icinde kosar. $1 = etiket
#
# esp32_bridge tanisi LOG'A DEGIL /swarm/internal/events/system topic'ine
# gidiyor (esp32_bridge_node.py:601). esp.log'a bakmak yanlis yol - orada
# yalniz acilis satirlari var.
#
# NEDEN `timeout -s INT`: duz `timeout` SIGTERM gonderiyor, Ubuntu apport da
# SIGTERM ile olen Python'u "uygulama cokta" diye kullaniciya popup olarak
# gosteriyor (bu oturumda yasandi). SIGINT Python'da KeyboardInterrupt olup
# temiz kapaniyor, apport kaydi olusmuyor.
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1

SATIR=$(timeout -s INT 20 ros2 topic echo /swarm/internal/events/system \
        --field message 2>/dev/null | grep -m1 "mesh_diag")
if [ -z "$SATIR" ]; then
    echo "   [$1] mesh_diag alinamadi (kopru yayin yapmiyor olabilir)"
    exit 0
fi
echo "   [$1] $(echo "$SATIR" | grep -oE '(lider|form_tx|form_rx|form_lider_degil|form_yarim|form_sahipsiz|form_seyrelt|form_ofs_kuyruk|form_ofs_iptal|form_ofs_onbellek|bilinmeyen|gonderim_drop)=[0-9]+' | tr '\n' ' ')"
