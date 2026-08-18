#!/bin/bash
# Konteyner icinde kosar. $1 = agent_id, $2 = sure_s
#
# NEDEN SAHTE AgentStatus: consensus_node'un ELIGIBLE_STATES kumesi
# {ARMED, TAKEOFF, IN_SWARM, EXECUTING_TASK}. Yerde disarm haldeki dron
# STATE_IDLE'dir, yani HICBIR ajan lider adayi olamaz - olcerek dogrulandi
# (secim sayisi 0). Yerde arm etmek pervane riski demek. Bu yuzden tek sahte
# girdi AgentStatus; secim mantiginin TAMAMI (is_eligible, effective_set,
# decide_change, bootstrap grace, _set_leader, ElectionResult yayini, mesh
# aktarimi) GERCEK kosuyor.
#
# 20 Hz yayinliyoruz cunku agent_fsm ayni topige GERCEK durumu (IDLE)
# basiyor; kayit "son yazan kazanir" mantiginda guncelleniyor. 20 Hz ile
# tick'lerin cogunda bizim ARMED kaydi en gunceldir. Secim bir kez olunca
# yapiskandir: decide_change, lider zaten aday ise None doner, effective
# bosalsa da lideri DUSURMEZ.
#
# healthy=true ve estimator_ok=true sart: ikisi de is_eligible kapisinda.
# Gercek ylp00 su an healthy=false bildiriyor (ayrica arastirilmali).
AID="$1"
SURE="${2:-10}"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1

echo "   [enjekte] agent ${AID}: STATE_ARMED(3) healthy estimator_ok 15.0V, ${SURE} sn @20Hz"
timeout -s INT "$SURE" ros2 topic pub -r 20 \
    "/swarm/internal/drone${AID}/status" \
    swarm_interfaces/msg/AgentStatus \
    "{agent_id: ${AID}, role: 0, state: 3, px4_link_ok: true, armed: true, healthy: true, battery_voltage_v: 15.0, estimator_ok: true, xy_valid: true, z_valid: true, v_xy_valid: true, origin_synced: true, rc_link_ok: true, status_text: secim_testi}" \
    2>&1 | grep -iE "incompatible|error" | head -3
echo "   [enjekte] bitti"
