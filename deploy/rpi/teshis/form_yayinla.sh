#!/bin/bash
# Konteyner icinde LIDER dronda kosar. $1 = agent_id
#
# AMAC: mesh formasyon aktarimini consensus/formation_node'a bagimli OLMADAN
# test etmek. O dugumler GPS/poz/gorev durumu istiyor; ylp02'de GPS yok. Bu
# yuzden lideri elle bildirip formasyon hedefini elle basiyoruz - boylece
# basarisizlik olursa sebebi kesin olarak MESH yolunda olur.
#
# Degerler KASTEN kuantizasyona tam oturacak sekilde secildi:
#   center 12.3 / -45.6 / -8.0 m  -> int16 desimetre  123 / -456 / -80  (tam)
#   heading 137.5 deg             -> int16 deci-derece 1375             (tam)
#   spacing 4.0 m                 -> uint8 desimetre  40                (tam)
#   max_speed 3.5 m/s             -> uint8 x10        35                (tam)
# Yani karsi tarafta EN UFAK sapma = gercek hata, kuantizasyon degil.
AID="$1"
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1

# 1) Lideri bildir. _on_election_out -> _lider_kaydet(new_leader_id) yani
#    bu drone kendini lider bilecek ve formasyon yayin kapisi acilacak.
#    Ayrica TIP_ELECTION mesh'e cikar, digerleri de lideri ogrenir.
#
# QoS SART: koprunun bu aboneligi _ELECTION_QOS = RELIABLE + TRANSIENT_LOCAL
# (esp32_bridge_node.py:110). `ros2 topic pub` varsayilani VOLATILE oldugu icin
# bayraksiz yayin DURABILITY uyumsuzlugundan HIC ULASMIYOR - ilk denemede
# tam bunu yasadik (form_lider_degil=9, lider=0). Gercek consensus_node ayni
# TRANSIENT_LOCAL'i kullaniyor (consensus_node.py:118), yani bu yalniz elle
# yayinda cikan bir tuzak, sistemde uyumsuzluk yok.
echo "   [yayin] ElectionResult new_leader_id=$AID (TRANSIENT_LOCAL, 3 sn)"
timeout -s INT 4 ros2 topic pub -r 2 \
    --qos-reliability reliable --qos-durability transient_local \
    /swarm/internal/election/result \
    swarm_interfaces/msg/ElectionResult \
    "{sequence_num: 1, new_leader_id: $AID, election_round: 1, triggered_by_agent_id: 0, reason: 3, confirmed_by_agent_ids: [1,3], message: mesh_testi}" \
    2>&1 | grep -iE "incompatible|error" | head -3
sleep 1

# 2) Formasyon hedefi. FORMATION_V(2) + 2 ajan -> devam paketi YOK, ofset
#    paketi YOK => tam olarak 1 mesh paketi (TIP_FORMASYON).
# Bu aboneligin QoS'u _MESH_QOS = BEST_EFFORT + VOLATILE, yani `ros2 topic pub`
# varsayilaniyla uyumlu (ilk denemede zaten 9 mesaj ulasti).
echo "   [yayin] FormationCommand V, merkez 12.3/-45.6/-8.0, hdg 137.5 (5 sn)"
timeout -s INT 6 ros2 topic pub -r 2 /swarm/internal/formation/target \
    swarm_interfaces/msg/FormationCommand \
    "{sequence_num: 7, formation_type: 2, center_x: 12.3, center_y: -45.6, center_z: -8.0, heading_deg: 137.5, spacing_m: 4.0, agent_ids: [1,3], max_speed_mps: 3.5, source_module: mesh_testi}" \
    2>&1 | grep -iE "incompatible|error" | head -3
echo "   [yayin] bitti"
