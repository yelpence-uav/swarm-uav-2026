#!/bin/bash
# Konteyner icinde kosar. $1 = agent_id, $2 = kac saniye izlenecek
# /swarm/public/formation/target'i izler; sonucu /tmp/form_izle.txt'e yazar.
# Arka planda baslatilir; yayin baslamadan ONCE kosmasi sart (kacirmamak icin).
AID="$1"
SURE="${2:-30}"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1

timeout "$SURE" ros2 topic echo /swarm/public/formation/target \
    > /tmp/form_izle.txt 2>&1
echo "izleme bitti" >> /tmp/form_izle.txt
