#!/usr/bin/env bash
# kinematic_fusion'ı başlatır. Kullanım: _run_kinfusion.sh <agent_id>
#
# NEDEN KRİTİK: her drona komşularının konumunu (NeighborInfo) verir.
#   kinematic_fusion → /swarm/agent/drone{i}/neighbor/drone{j}
#   formation_node / collision_avoidance ← aynı topic
# Bu düğüm yoksa formation_node komşularını GÖRMEZ → sürü formasyonu tutamaz
# (dronlar tek tek uçar). launch_swarm.py bunu başlatmaz; gorev1.launch.py başlatır.
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=10
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/yelpence/ros2_ws/cyclonedds.xml
i="$1"
case "$i" in
  1) NB="[2,3]" ;;
  2) NB="[1,3]" ;;
  3) NB="[1,2]" ;;
  *) echo "gecersiz agent_id: $i"; exit 1 ;;
esac
exec ros2 run swarm_perception kinematic_fusion --ros-args \
  -p agent_id:=${i} -p neighbor_ids:="${NB}" \
  -r __node:=kinematic_fusion_${i}
