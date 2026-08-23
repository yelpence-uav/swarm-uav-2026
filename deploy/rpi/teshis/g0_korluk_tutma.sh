#!/usr/bin/env bash
# =============================================================================
# G0-5 · KORLUKTE DIKEY AYRIM BIRAKILMIYOR MU
#
# NE SINANIYOR (23 Agustos 2026'da eklendi)
# "Catisma bitti" karari komsunun UZAKTA olmasina dayaniyor. Komsuyu
# KAYBETMEK de ayni gorunuyordu: bayat veri listeden duser, catisma false
# olur ve ucak 2 saniye sonra kazandigi dikey ayrimi GERI VERIR — hem de
# komsusunun nerede oldugunu bilmedigi anda. 21 Agustos'ta mesh 46.4 saniye
# TEK YONLU olmustu (TUZAKLAR 2.15); o sirada bu davranis olsaydi ucak
# ayrimi birakirdi.
#
# Beklenen: korluk bayragi kalkinca dugum irtifayi TUTAR, `donus_kor`
# sayaci artar ve "DIKEY AYRIM TUTULUYOR" uyarisi cikar.
#
# ⚠️ GERCEK esp32_bridge'in test kancasi kullaniliyor, yani UCAGIN KENDISI
# de o komsuyu kaybeder ve YKI'de KORLUK ALARMI CALAR. Beklenen davranis.
# Betik kancayi her cikista temizler (trap).
#
# 🔴 Bir dugumu OLDURMEK bu testi karsilamaz — TUZAKLAR §2.16.
#
# KULLANIM (konteyner icinde):
#     bash g0_korluk_tutma.sh <agent_id> <komsu_listesi> <rutbe> <kaybolacak_id>
#     ornek:  bash g0_korluk_tutma.sh 3 1,2 1 1
# =============================================================================
set -o pipefail            # `set -u` YOK: ROS setup.bash onunla oluyor
AID="${1:-3}"
KOMSULAR="${2:-1,2}"
RUTBE="${3:-1}"
KAYIP="${4:-1}"

export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_LOCALHOST_ONLY=1
source /opt/ros/jazzy/setup.bash >/dev/null 2>&1
source /ws/install/setup.bash  >/dev/null 2>&1

temizle() {
    ros2 param set /esp32_bridge sahte_kayip_ajanlar "[0]" >/dev/null 2>&1
    kill "${PUB_PID:-}" "${CA_PID:-}" 2>/dev/null
    echo "   [temizlik] test kancasi KAPATILDI, gozlem dugumu durduruldu"
}
trap temizle EXIT

echo "G0-5 KORLUK TUTMASI · drone${AID} · rutbe ${RUTBE} · kaybolacak: drone${KAYIP}"
echo

ros2 run swarm_core collision_avoidance --ros-args \
    -p agent_id:="${AID}" -p neighbor_ids:="[${KOMSULAR}]" \
    -p rutbe:="${RUTBE}" -p altitude_gate_m:=0.0 \
    -p d0_m:=4.0 -p hard_m:=2.5 -p katman_m:=3.0 \
    -p v_dikey_max_mps:=1.2 -p a_dikey_max_mps2:=2.0 -p kp_dikey:=2.0 \
    -r "/drone_${AID}/control/setpoint/raw:=/g05/drone${AID}/raw" \
    -r "/drone_${AID}/control/setpoint:=/g05/drone${AID}/out" \
    > /tmp/g05_ca.log 2>&1 &
CA_PID=$!
sleep 4

ros2 topic pub -r 20 "/g05/drone${AID}/raw" \
    swarm_interfaces/msg/AgentSetpoint \
    "{agent_id: ${AID}, source: 1, priority: 10, vx: 0.0, vy: 0.0, vz: 0.0,
      position_valid: false, velocity_valid: true, max_speed_mps: 4.0}" \
    > /dev/null 2>&1 &
PUB_PID=$!

echo "1) 8 sn: komsu GORULUYOR -> catisma, dikey kacis kuruluyor"
sleep 8

echo "2) TEST KANCASI ACILIYOR — drone${KAYIP} paketleri dusurulecek"
ros2 param set /esp32_bridge sahte_kayip_ajanlar "[${KAYIP}]" | sed 's/^/   /'

echo "3) 16 sn: komsu KAYIP. Beklenen: irtifa TUTULUYOR, donus YOK"
sleep 16

echo "4) kanca kapatiliyor"
ros2 param set /esp32_bridge sahte_kayip_ajanlar "[0]" | sed 's/^/   /'
sleep 4
kill "$PUB_PID" 2>/dev/null
sleep 1
kill "$CA_PID" 2>/dev/null
sleep 2

echo
echo "=============== SONUC ==============="
grep -c 'DIKEY AYRIM TUTULUYOR' /tmp/g05_ca.log > /tmp/g05_n 2>/dev/null
TUT=$(cat /tmp/g05_n 2>/dev/null || echo 0)
echo "  'DIKEY AYRIM TUTULUYOR' uyarisi : ${TUT} kez"
echo "  KACINMA KORU alarmi             : $(grep -c 'KACINMA KORU' /tmp/g05_ca.log) kez"
echo
echo "  son tani satiri:"
grep 'tani:' /tmp/g05_ca.log | tail -1 | sed 's/^.*tani:/    /'
echo
DK=$(grep 'tani:' /tmp/g05_ca.log | tail -1 \
     | grep -o 'donus_kor=[0-9]*' | cut -d= -f2)
DK="${DK:-0}"
if [ "$TUT" -ge 1 ] && [ "$DK" -ge 1 ]; then
    echo "  ✅ G0-5 GECTI — korlukte ayrim BIRAKILMADI (donus_kor=${DK})"
else
    echo "  🔴 G0-5 KALDI — uyari=${TUT} donus_kor=${DK}."
    echo "     Komsu gercekten kayboldu mu? /tmp/g05_ca.log bak."
fi
