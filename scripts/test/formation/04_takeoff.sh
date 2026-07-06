#!/bin/bash
# 3 drona senkronize arm + offboard + takeoff — tek Python process.
# Tek process içinde tüm publisher'lar önceden init edilir, sonra aynı anda publish.
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash

python3 ~/ros2_ws/scripts/test/formation/sync_takeoff.py
