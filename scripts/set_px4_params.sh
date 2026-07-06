#!/bin/bash
# PX4 SITL parametrelerini tmux konsoluna gönderir.
# launch_swarm.py çalıştırıldıktan ~12-15 saniye sonra bu scripti çalıştır.

TMUX_SESSION="yelpence_swarm"
DRONE_COUNT=3

PARAMS=(
    "param set COM_RCL_EXCEPT 4"
    "param set NAV_RCL_ACT 0"
    "param set SIM_BAT_ENABLE 0"
    "param set COM_OF_LOSS_T 10"
    "param set COM_DISARM_PRFLT 0"
    "param set EKF2_GPS_CHECK 0"
    "param set NAV_DLL_ACT 0"
    "param set EKF2_GPS_DELAY 110"

    "param set EKF2_GND_EFF_DZ 0.0"
    "param set MPC_TILTMAX_AIR 10"
    "param set MPC_ACC_HOR 3.0"
    "param set MPC_Z_P 1.5"
    "param set MPC_Z_VEL_P_ACC 6.0"
    "param save"
)

for i in $(seq 1 $DRONE_COUNT); do
    WINDOW="PX4_${i}"
    echo ">> Drone ${i} parametreleri gönderiliyor..."

    for cmd in "${PARAMS[@]}"; do
        tmux send-keys -t "${TMUX_SESSION}:${WINDOW}" "$cmd" Enter
        sleep 0.4
    done
done

echo ">> Tamamlandı. EKF2'nin oturması için 30 saniye bekleniyor..."
sleep 30
echo ">> Hazır. Şimdi bridge ve FSM başlatılabilir."
