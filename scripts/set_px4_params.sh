#!/bin/bash
# PX4 SITL parametrelerini tmux konsoluna gönderir.
# launch_swarm.py çalıştırıldıktan ~12-15 saniye sonra bu scripti çalıştır.

TMUX_SESSION="yelpence_swarm"
DRONE_COUNT="${DRONE_COUNT:-3}"

PARAMS=(
    # --- Manyetometre (yaw/pusula) ---
    # Gercek mag kullaniliyor (launch_swarm.py sahte mag'i kaldirdi). x500
    # modelinde manyetometre sensoru + world'de manyetik alan zaten var.
    # SYS_HAS_MAG=1: PX4'e "bu araclarda pusula var" der.
    "param set SYS_HAS_MAG 1"
    # EKF mag kalite kontrolleri kapali. Coklu-drone Gazebo'da EKF gercek mag'i
    # yanlislikla "interference" diye reddediyordu (sim'e ozgu, gercek parazit
    # yok). Kapatinca EKF mag'i kabul eder, mutlak kuzeyi gorur; uc dron da ayni
    # dogru yaw'a oturur, kalkista savrulma biter.
    "param set EKF2_MAG_CHECK 0"
    # Mag'i heading kaynagi olarak kullan (otomatik fuzyon).
    "param set EKF2_MAG_TYPE 0"

    # --- RC / failsafe (SITL'de kumanda yok, arm engellenmesin) ---
    "param set COM_RCL_EXCEPT 4"
    "param set NAV_RCL_ACT 0"
    "param set SIM_BAT_ENABLE 0"
    "param set COM_OF_LOSS_T 10"
    "param set COM_DISARM_PRFLT 0"
    "param set NAV_DLL_ACT 0"

    # --- ARM ONCESI EKF KAPILARINI GEVSET (kalkis blokajini onle) ---
    # ekf2 restart yaw'i duzeltir ama yukseklik/yaw kestirimi bir sure "unstable"
    # kalir; varsayilan esikler (HGT 1.0, YAW 0.5) bu marjinal durumda arm'i
    # ENGELLIYOR ("height estimate not stable" / "Yaw estimate error") ve dron
    # kalkamiyordu. Esikleri yukseltince EKF marjinal kestirimle de arm olur;
    # kestirim havada oturur. SITL'de guvenli, gercek testte de kalkisi kurtarir.
    "param set COM_ARM_EKF_HGT 5.0"
    "param set COM_ARM_EKF_POS 5.0"
    "param set COM_ARM_EKF_VEL 5.0"
    "param set COM_ARM_EKF_YAW 5.0"

    # --- GPS (SITL kalite esiklerini gevset) ---
    "param set EKF2_GPS_CHECK 0"
    "param set EKF2_GPS_DELAY 110"

    # --- Ucus kontrolu (yumusak kalkis/hover) ---
    "param set EKF2_GND_EFF_DZ 0.0"
    "param set MPC_TILTMAX_AIR 10"
    "param set MPC_ACC_HOR 3.0"
    "param set MPC_Z_P 1.5"
    "param set MPC_Z_VEL_P_ACC 6.0"

    "param save"
    # NOT: ekf2 stop/start (restart) KALDIRILDI. Restart, EKF yüksekliğini
    # sıfırlıyor ve güvenilir geri oturmuyordu → "height estimate not stable"
    # arm anında titriyor, 3 dron aynı anda stabil pencereyi yakalayamıyordu
    # (biri kalkıyor, ikisi ARMING→IDLE düşüyordu). Restart yaw'ı düzeltmek
    # için eklenmişti; artık yaw'ı EKF2_MAG_CHECK=0 + gevşek COM_ARM_EKF_YAW=5
    # zaten yutuyor. Restart yok → EKF bir kez yerde ilklenir, yükseklik oturur
    # ve STABİL kalır → 3 dron da aynı anda arm olur.
)

for i in $(seq 1 $DRONE_COUNT); do
    WINDOW="PX4_${i}"
    echo ">> Drone ${i} parametreleri gönderiliyor..."

    for cmd in "${PARAMS[@]}"; do
        tmux send-keys -t "${TMUX_SESSION}:${WINDOW}" "$cmd" Enter
        sleep 0.4
    done
done

echo ">> Tamamlandı. EKF ilk ilklenmeden yükseklik+GPS oturması için 40 sn..."
sleep 40
echo ">> Hazır. Şimdi bridge ve FSM başlatılabilir."
