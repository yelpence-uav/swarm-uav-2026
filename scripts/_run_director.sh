#!/usr/bin/env bash
source /opt/ros/jazzy/setup.bash
source /home/yelpence/ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=10
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/yelpence/ros2_ws/cyclonedds.xml
cd /home/yelpence/ros2_ws
exec python3 scripts/video_scenario_director.py --team 752825 \
  --origin-lat 41.0441 --origin-lon 29.0017
