#!/usr/bin/env bash
# consensus_node'u başlatır (lider seçimi). Kullanım: _run_consensus.sh <agent_id>
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=10
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/yelpence/ros2_ws/cyclonedds.xml
i="$1"
exec ros2 run swarm_core consensus_node --ros-args \
  -p agent_id:=${i} -p agent_count:=3 -r __node:=consensus_${i}
