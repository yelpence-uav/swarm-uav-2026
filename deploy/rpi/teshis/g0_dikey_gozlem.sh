#!/usr/bin/env bash
# =============================================================================
# G0-2..G0-5 · DIKEY YOL VERME — YERDE, GOZLEM MODUNDA
#
# NEDEN GOZLEM MODU: dugumun kendisi ucus komut yolunun ICINDE
# (/control/setpoint/raw -> /control/setpoint -> px4_bridge). Onu yerde
# durturmak icin kurcalamak, ucaga giden gercek zinciri bozma riski tasir.
#
# Bunun yerine IKINCI bir collision_avoidance ornegi acilir; girdisi ve
# ciktisi /g0/... altina yonlendirilir. GERCEK mesh komsusunu, GERCEK kendi
# telemetrisini okur, ama ciktisi hicbir yere baglanmaz. Depo bu deseni
# zaten "gozlem modu" olarak kullaniyor (PLAN.md §5).
#
# IRTIFA KAPISI 0'a cekilir — yoksa yerde (irtifa ~0) dugum hicbir sey
# yapmaz ve test bos gecer. Bu YALNIZ gozlem ornegi icin; ucan dugum
# 3.0 m kapisiyla kalir.
#
# KULLANIM (konteyner icinde):
#     bash g0_dikey_gozlem.sh <agent_id> <komsu_listesi> <rutbe> [saniye]
#     ornek:  bash g0_dikey_gozlem.sh 3 1,2 1 20
# =============================================================================
# 🔴 `set -u` YOK — BILEREK. ROS'un setup.bash'i tanimsiz degiskenlere
# dokunuyor (AMENT_TRACE_SETUP_FILES, COLCON_TRACE...) ve `set -u` altinda
# script TAM ORADA, SESSIZCE oluyor: tek satir cikti bile vermiyor.
# 23 Agustos 2026'da bu betikte yasandi, `bash -x` ile bulundu.
set -o pipefail
AID="${1:-1}"
KOMSULAR="${2:-2,3}"
RUTBE="${3:-0}"
SURE="${4:-20}"

export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_LOCALHOST_ONLY=1
source /opt/ros/jazzy/setup.bash >/dev/null 2>&1
source /ws/install/setup.bash  >/dev/null 2>&1

echo "G0 DIKEY GOZLEM · drone${AID} · komsular ${KOMSULAR} · rutbe ${RUTBE}"
echo "   girdi : /g0/drone${AID}/raw     cikti : /g0/drone${AID}/out"
echo "   (ucan dugume DOKUNULMUYOR)"
echo

ros2 run swarm_core collision_avoidance --ros-args \
    -p agent_id:="${AID}" \
    -p neighbor_ids:="[${KOMSULAR}]" \
    -p rutbe:="${RUTBE}" \
    -p altitude_gate_m:=0.0 \
    -p d0_m:=4.0 -p hard_m:=2.5 -p katman_m:=3.0 \
    -p v_dikey_max_mps:=1.2 -p a_dikey_max_mps2:=2.0 -p kp_dikey:=2.0 \
    -r "/drone_${AID}/control/setpoint/raw:=/g0/drone${AID}/raw" \
    -r "/drone_${AID}/control/setpoint:=/g0/drone${AID}/out" \
    > /tmp/g0_ca.log 2>&1 &
CA_PID=$!
sleep 4

# Ham setpoint: ASILI DURUYOR (sifir hiz). Kacinma ne uretirse tamamen
# kendi karari olur — 22 Agustos saha testindeki kosulun aynisi.
ros2 topic pub -r 20 "/g0/drone${AID}/raw" swarm_interfaces/msg/AgentSetpoint \
    "{agent_id: ${AID}, source: 1, priority: 10,
      vx: 0.0, vy: 0.0, vz: 0.0,
      position_valid: false, velocity_valid: true,
      acceleration_valid: false, max_speed_mps: 4.0}" \
    > /dev/null 2>&1 &
PUB_PID=$!

echo "--- ${SURE} sn boyunca CIKTI ornekleniyor ---"
timeout -s INT "${SURE}" ros2 topic echo --qos-reliability best_effort \
    "/g0/drone${AID}/out" --field vz 2>/dev/null \
    | grep -v '^---' | awk 'NF' > /tmp/g0_vz.txt
timeout -s INT 3 ros2 topic echo --qos-reliability best_effort \
    "/g0/drone${AID}/out" --field vx 2>/dev/null \
    | grep -v '^---' | awk 'NF' > /tmp/g0_vx.txt

kill "$PUB_PID" "$CA_PID" 2>/dev/null
wait "$PUB_PID" "$CA_PID" 2>/dev/null

python3 - "$AID" "$RUTBE" <<'PY'
import statistics
import sys
aid, rutbe = sys.argv[1], int(sys.argv[2])


def oku(p):
    try:
        return [float(x) for x in open(p) if x.strip()]
    except Exception:
        return []


vz, vx = oku('/tmp/g0_vz.txt'), oku('/tmp/g0_vx.txt')
if not vz:
    print('🔴 CIKTI YOK — /tmp/g0_ca.log bak')
    sys.exit(1)
ovz, ovx = statistics.mean(vz), (statistics.mean(vx) if vx else 0.0)
print(f'\n  ornek: {len(vz)}   vz ort {ovz:+.3f} m/s '
      f'(min {min(vz):+.3f} maks {max(vz):+.3f})   vx ort {ovx:+.3f} m/s')
print('  NED: vz NEGATIF = TIRMANMA\n')
if rutbe == 0:
    if abs(ovz) < 0.02:
        print('  ✅ G0-2 GECTI — CAPA dikeyde kipirdamiyor (rutbe 0)')
    else:
        print(f'  🔴 G0-2 KALDI — capa dikey komut uretti: {ovz:+.3f} m/s')
        sys.exit(1)
else:
    yon = 'YUKARI' if rutbe % 2 == 1 else 'ASAGI'
    ok = (ovz < -0.05) if rutbe % 2 == 1 else (ovz > 0.05)
    if ok:
        print(f'  ✅ G0-2 GECTI — rutbe {rutbe} -> {yon} kacis ({ovz:+.3f})')
    else:
        print(f'  🔴 G0-2 KALDI — rutbe {rutbe} icin {yon} bekleniyordu, '
              f'vz={ovz:+.3f}')
        sys.exit(1)
if abs(ovx) > 0.05:
    print(f'  ✅ G0-3 — sert kabuk icinde YATAY son care de acildi '
          f'({ovx:+.3f} m/s); ucaklar 0.6 m arayla, hard=2.5 m')
else:
    print(f'  ⚠ yatay itme yok ({ovx:+.3f}) — 0.6 m arayla beklenirdi')
PY
