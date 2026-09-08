#!/bin/bash
# Konteyner icinde LIDER dronda kosar. $1 = agent_id
# $2 = agent_ids listesi (varsayilan "[1,2,3]")
#
# AMAC: CUSTOM (juri dizilisi) formasyonunun mesh'ten GECIP GECMEDIGINI
# olcmek. `form_yayinla.sh` FORMATION_V yayinliyor ve V formulden
# turetildigi icin TEK cerceve gidiyor — yani CUSTOM yolunu HIC sinamiyor.
#
# 🔴 NEDEN AYRI BETIK (8 Eylul 2026)
# CUSTOM ofsetleri formulden turetilemez, `TIP_FORM_OFSET` cerceveleriyle
# ACIKCA tasinir: paket basina 2 slot, yani 3 ucakta IKI cerceve. Firmware
# TIP BASINA 50 ms hiz limiti uyguluyor (MESH_GONDERIM_MIN_MS) ve iki
# cerceve AYNI TIP oldugu icin ikincisi HER SEFERINDE dusuyordu. Alicida
# montaj tamamlanmiyor -> takipciler formasyon komutunu HIC ALMIYOR.
# Lider etkilenmiyor (loopback seri porta ugramiyor), yani disaridan
# "sadece lider hareket ediyor" gibi gorunuyor ve hicbir yerde hata yok.
#
# Duzeltme Pi tarafinda: ofset cerceveleri kuyruga alinip aralarinda 60 ms
# birakiliyor. BU BETIK O DUZELTMEYI OLCER.
#
# NASIL OKUNUR — takipcide `form_sayac.sh` ile:
#     form_rx     ARTMALI      (duzeltmeden once HIC artmiyordu)
#     form_yarim  ARTMAMALI    (duzeltmeden once saniyede ~5 artiyordu)
# Liderde:
#     form_ofs_kuyruk = 0      (kuyruk bosaliyor)
#     form_ofs_iptal  sabit    (surekli artiyorsa mesh hizi cok yuksek)
#
# ⚠️ SETPOINT URETIR. `formation_node` bu hedefi alip /raw'a yazar. Uclerin
# de DISARM ve OFFBOARD DISINDA olmasi gerekir; kill switch acikken motor
# donmez. Ucus komutu DEGILDIR ama zararsiz da degildir — once durum kontrol.
#
# Degerler kuantizasyona TAM oturacak sekilde secildi (karsi tarafta en ufak
# sapma = gercek hata, kuantizasyon degil):
#   center 12.3 / -45.6 / -8.0 m -> int16 dm  123 / -456 / -80
#   heading 137.5 deg            -> int16 ddeg 1375
#   ofsetler 0.0 / 5.0 / -5.0 m  -> int16 dm  0 / 50 / -50
AID="$1"
AGENTS="${2:-[1,2,3]}"
SURE="${3:-8}"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1

# 1) Lideri bildir — formasyon yayin kapisi (KARAR 11) bununla acilir.
#    QoS SART: kopru _ELECTION_QOS = RELIABLE + TRANSIENT_LOCAL kullaniyor;
#    `ros2 topic pub` varsayilani VOLATILE ve bayraksiz yayin HIC ULASMAZ
#    (form_yayinla.sh'teki nota bak, ayni tuzak).
echo "   [yayin] ElectionResult new_leader_id=$AID (TRANSIENT_LOCAL, 3 sn)"
timeout -s INT 4 ros2 topic pub -r 2 \
    --qos-reliability reliable --qos-durability transient_local \
    /swarm/internal/election/result \
    swarm_interfaces/msg/ElectionResult \
    "{sequence_num: 1, new_leader_id: $AID, election_round: 1, triggered_by_agent_id: 0, reason: 3, confirmed_by_agent_ids: $AGENTS, message: custom_mesh_testi}" \
    2>&1 | grep -iE "incompatible|error" | head -3
sleep 1

# 2) CUSTOM formasyon hedefi + ACIK ofsetler.
#    formation_type 99 = FORMATION_CUSTOM. Ofset dizileri agent_ids ile
#    PARALEL ve dolu olmak ZORUNDA: bos birakilirsa kopru "CUSTOM formasyon
#    ama offset YOK" deyip turu atlar (esp32_bridge_node.py).
echo "   [yayin] FormationCommand CUSTOM(99), 3 ofset, ${SURE} sn"
timeout -s INT "$SURE" ros2 topic pub -r 2 /swarm/internal/formation/target \
    swarm_interfaces/msg/FormationCommand \
    "{sequence_num: 11, formation_type: 99, center_x: 12.3, center_y: -45.6, center_z: -8.0, heading_deg: 137.5, spacing_m: 7.0, agent_ids: $AGENTS, offset_x: [0.0, 5.0, -5.0], offset_y: [0.0, 0.0, 0.0], offset_z: [0.0, 0.0, 0.0], max_speed_mps: 3.5, source_module: custom_mesh_testi}" \
    2>&1 | grep -iE "incompatible|error" | head -3
echo "   [yayin] bitti"
