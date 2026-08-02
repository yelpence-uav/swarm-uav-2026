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
echo 'tum dugumler basladi'
wait
