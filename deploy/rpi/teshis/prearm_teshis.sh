#!/bin/bash
# ylp00 konteynerinde kosar. $1 = agent_id
#
# PX4 1.16 arm reddini MAVLink Events ile bildiriyor; MAVROS metadata olmadigi
# icin ciplak EVENT ID basiyor. Gerekceyi parametrelerden ve saglik
# bayraklarindan cikaracagiz.
#
# ANA HIPOTEZ: bu sabah baska bir karttan parametre dosyasi yuklendi. CAL_*_ID
# alanlari o kartin sensor ID'lerini tasiyorsa (ya da 0 ise) PX4 sensorleri
# "kalibre degil" sayar ve arm'i reddeder. system_status=0 (UNINIT) bunu
# destekliyor - sagliklı yerdeki PX4 STANDBY(3) olmali.
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1
NODE="/drone_${AID}/mavros/param"

echo "   --- kalibrasyon kimlikleri (0 = KALIBRE DEGIL) ---"
for p in CAL_ACC0_ID CAL_GYRO0_ID CAL_MAG0_ID CAL_BARO0_ID; do
    printf "      %-14s = " "$p"
    timeout -s INT 20 ros2 param get "$NODE" "$p" 2>&1 | tail -1
done

echo "   --- arm kontrol devre kesicileri / esikler ---"
for p in CBRK_SUPPLY_CHK CBRK_USB_CHK COM_ARM_WO_GPS COM_ARM_EKF_HGT COM_ARM_MAG_STR COM_ARM_IMU_ACC COM_ARM_IMU_GYR; do
    printf "      %-16s = " "$p"
    timeout -s INT 20 ros2 param get "$NODE" "$p" 2>&1 | tail -1
done

echo "   --- sensor / EKF saglik bayraklari ---"
timeout -s INT 15 ros2 topic echo "/swarm/internal/drone${AID}/status" --once 2>/dev/null \
    | grep -E "^(imu_healthy|mag_healthy|baro_healthy|estimator_ok|xy_valid|z_valid|v_xy_valid|failsafe_active|pilot_override_active|flight_mode):" \
    | sed 's/^/      /'

echo "   --- MAVROS diagnostics: PX4 saglik ozeti ---"
timeout -s INT 15 ros2 topic echo "/diagnostics" --once 2>/dev/null \
    | grep -A 3 -iE "name:.*(sys|heartbeat|system)" | head -20 | sed 's/^/      /'
