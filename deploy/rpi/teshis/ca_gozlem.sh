#!/bin/bash
# Konteyner icinde kosar. $1 = agent_id, $2 = "dur" ise kapatir.
#
#   docker exec droneN bash /ws/ca_gozlem.sh N        # baslat + besle + olc
#   docker exec droneN bash /ws/ca_gozlem.sh N dur    # kapat
#
# ADIM 3+4 GOZLEM ZINCIRI — UCAN YOLA DOKUNMAZ.
#
#   formation_node (zaten kosuyor, ciktisi /gozlem/.../formation/raw)
#        -> gozlem_ca  (collision_avoidance kopyasi, GERCEK mesh komsu verisi)
#        -> /gozlem/drone_N/ca/out
#
# Sahadaki basit_kacinma ve esp32_bridge yoluna HIC karisilmaz; kopya dugum
# ayri konulara remap'li. Boylece ADIM 4 ucmadan once canli telemetriyle
# sinanabiliyor (PLAN.md §5 gozlem modu).
#
# NEDEN GEREKLI: KARAR-01'in 10/10 testi adaptorun ISARET yonunu DIZUSTUNDE
# dogruluyor. Adaptorun GERCEK mesh AgentStatus'unu kabul edip etmedigi
# baska bir soru ve ancak uctaki canli veriyle olculur. Sayac bunu veriyor:
# skip_adaptor ARTIYORSA adaptor mesh verisini reddediyor demektir.
AID="${1:?kullanim: ca_gozlem.sh <agent_id> [dur]}"
source /opt/ros/jazzy/setup.bash; source /ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_LOCALHOST_ONLY=1
LOG=/ws/gunluk/son/gozlem_ca.log

if [ "${2:-}" = "dur" ]; then
    pkill -f 'gozlem_ca' && echo "  gozlem_ca durduruldu" || echo "  zaten kapali"
    exit 0
fi

KOMSULAR=$(echo "1 2 3" | tr ' ' '\n' | grep -v "^${AID}$" | paste -sd, -)
if ! pgrep -f 'gozlem_ca' >/dev/null; then
    setsid ros2 run swarm_core collision_avoidance --ros-args \
      -r __node:=gozlem_ca \
      -r /drone_${AID}/control/setpoint/raw:=/gozlem/drone_${AID}/formation/raw \
      -r /drone_${AID}/control/setpoint:=/gozlem/drone_${AID}/ca/out \
      -p agent_id:=${AID} -p neighbor_ids:="[$KOMSULAR]" \
      -p d0_m:=${KACINMA_D0:-6.0} -p hard_m:=${KACINMA_HARD:-4.0} \
      -p neighbor_rx_stale_s:=${KACINMA_BAYAT_S:-1.5} \
      >> "$LOG" 2>&1 < /dev/null &
    sleep 4
fi
echo "  gozlem_ca surec: $(pgrep -fc gozlem_ca)"

# --- formation_node'u besle ---------------------------------------------
# UC OFSET DIZISI DE SART: _slot_offset (formation_node.py:851) x,y,z'nin
# UCUNU de ayni uzunlukta istiyor. offset_z atlanirsa sessizce
# "slot ofseti yok (yerel/komut); setpoint atlandi"ya duser — 21 Agustos'ta
# olculdu, yarim saat kaybettirdi.
#
# Ofsetler ACIKCA veriliyor: normalde koprunun _on_formation_out'u bunlari
# hesaplayip mesh paketine koyar, ama o yol LIDER KAPISINDAN geciyor ve
# acmak icin sahte ElectionResult enjekte etmek gerekirdi (form_yayinla.sh
# oyle yapiyor). Gozlem zinciri tamamen YEREL oldugu icin o kapiyi hic
# acmiyoruz — GERCEK consensus durumuna dokunulmuyor.
echo "  [besle] FormationCommand cizgi 12 m, 20 sn"
timeout -s INT 20 ros2 topic pub -r 2 --qos-reliability reliable \
  --qos-durability transient_local \
  /swarm/public/formation/target swarm_interfaces/msg/FormationCommand \
  "{sequence_num: 21, formation_type: 3, center_x: -2.5, center_y: -1.0,
    center_z: -10.0, heading_deg: 0.0, spacing_m: 12.0,
    agent_ids: [1,3], offset_x: [-6.0, 6.0], offset_y: [0.0, 0.0],
    offset_z: [0.0, 0.0], max_speed_mps: 3.0, source_module: ca_gozlem}" \
  >/dev/null 2>&1

echo "  --- SONUC ---"
grep -a "tani:" "$LOG" | tail -2 | sed 's/^/    /'
echo "  OKUMA: skip_adaptor artiyorsa adaptor mesh verisini REDDEDIYOR."
echo "         gate_alt: 3 m altinda kacinma KAPALI (tasarim, altitude_gate_m)."
echo "         avoid: komsu d0 (6 m) icine girmedikce 0 kalir."
