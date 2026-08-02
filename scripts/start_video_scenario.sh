#!/usr/bin/env bash
# start_video_scenario.sh — Uçuş kanıt videosu üçgen senaryosunu başlatır.
#
# launch_swarm.py'ın başlatmadığı düğümleri ekler: kinematic_fusion ×3
# (komşu konumları), consensus ×3 (lider seçimi), mission1 ×3, path_planner,
# director.
#
# Kullanım (sırayla):
#   1) python3 scripts/launch_swarm.py
#   2) Dronlar spawn olup GPS fix alsın
#   3) bash scripts/start_video_scenario.sh
#
# Her uçuştan önce tam sim restart gerekir: PX4 görev sonrası yeniden arm
# etmez. 'set -u' kullanılmaz — ROS setup.bash'i tanımsız değişkene dokunur.

WS="/home/yelpence/ros2_ws"
SESSION="yelpence_swarm"
TEAM="752825"
ORIGIN_LAT="41.0441"
ORIGIN_LON="29.0017"

source /opt/ros/jazzy/setup.bash 2>/dev/null
source "${WS}/install/setup.bash" 2>/dev/null
export ROS_DOMAIN_ID=10
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
# MaxAutoParticipantIndex=120 — bu olmadan yeni düğüm "failed to find a free
# participant index for domain 10" ile açılmaz (domain dolu görünür).
export CYCLONEDDS_URI="file://${WS}/cyclonedds.xml"

if ! tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "HATA: '${SESSION}' tmux oturumu yok. Önce: python3 scripts/launch_swarm.py"
  exit 1
fi

echo "── eski senaryo düğümleri temizleniyor ──"
pkill -f "video_scenario_director" 2>/dev/null || true
pkill -f "consensus_node" 2>/dev/null || true
pkill -f "mission1_dynamic_swarm" 2>/dev/null || true
pkill -f "kinematic_fusion" 2>/dev/null || true
pkill -f "maneuver_executor" 2>/dev/null || true
pkill -f "swarm_core path_planner" 2>/dev/null || true
sleep 2

_win() {  # _win <pencere_adı> <komut>
  tmux kill-window -t "${SESSION}:$1" 2>/dev/null || true
  tmux new-window -t "${SESSION}" -n "$1" 2>/dev/null
  sleep 0.5
  tmux send-keys -t "${SESSION}:$1" "$2 2>&1 | tee ${WS}/logs/$1.log" Enter
  sleep 1
}

echo "── kinematic_fusion ×3 (komşu konumları → formasyon) ──"
for i in 1 2 3; do
  _win "KinFusion_$i" "bash ${WS}/scripts/_run_kinfusion.sh $i"
done

echo "── consensus ×3 (lider seçimi) ──"
for i in 1 2 3; do
  _win "Consensus_$i" "bash ${WS}/scripts/_run_consensus.sh $i"
done

echo "── maneuver_executor ×3 (mission1 action client'ı bekler) ──"
for i in 1 2 3; do
  _win "Maneuver_$i" "bash -c 'source /opt/ros/jazzy/setup.bash && source ${WS}/install/setup.bash && export ROS_DOMAIN_ID=10 && export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp && export CYCLONEDDS_URI=file://${WS}/cyclonedds.xml && ros2 run swarm_core maneuver_executor --ros-args -p agent_id:=$i -r __node:=maneuver_executor_$i'"
done

echo "── path_planner ──"
# Merkezin seyir hızı swarm_config.py'dan TÜRETİLİR (dron tavanı × oran).
# Elle yazılmaz: merkez ile dron tavanı ayrı ayrı tutulduğunda birbirinden
# kopuyor ve sürü merkezin gerisinde kalıyordu.
MERKEZ_HIZ=$(cd "${WS}/scripts" && python3 -c 'import swarm_config; print(swarm_config.MERKEZ_HIZ_MPS)')
echo "   merkez seyir hızı: ${MERKEZ_HIZ} m/s (swarm_config.py)"
_win "PathPlanner" "bash -c 'source /opt/ros/jazzy/setup.bash && source ${WS}/install/setup.bash && export ROS_DOMAIN_ID=10 && export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp && export CYCLONEDDS_URI=file://${WS}/cyclonedds.xml && ros2 run swarm_core path_planner --ros-args -p max_speed_mps:=${MERKEZ_HIZ}'"

echo "── mission1 ×3 (video modu) ──"
for i in 1 2 3; do
  _win "Mission1_$i" "bash ${WS}/scripts/_run_mission1.sh $i"
done

echo "── düğümler yerleşiyor (10 sn) ──"
sleep 10

echo "── senaryo sürücüsü (koordinat + kalkış + rota besleme) ──"
_win "VideoDirector" "bash ${WS}/scripts/_run_director.sh"

echo
echo "Hazır. İzlemek için:"
echo "  tmux attach -t ${SESSION}"
echo "  tail -f ${WS}/logs/VideoDirector.log | grep -E 'Mission durumu|enjekte'"
echo
echo "Lider seçildi mi (kalkıştan sonra 1 olmalı):"
echo "  ros2 topic echo /swarm/public/state --once | grep leader_id"
