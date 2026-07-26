#!/usr/bin/env bash
# mission1_dynamic_swarm'ı başlatır. Kullanım: _run_mission1.sh <agent_id>
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=10
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/yelpence/ros2_ws/cyclonedds.xml
i="$1"
exec ros2 run swarm_missions mission1_dynamic_swarm --ros-args \
  -p agent_id:=${i} -p agent_ids:="[1,2,3]" -p team_id:="'752825'" \
  -r __node:=mission1_${i}
