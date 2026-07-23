cmake_minimum_required(VERSION 3.8)
project(swarm_interfaces)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(action_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  # Mesajlar
  "msg/AgentStatus.msg"
  "msg/SwarmState.msg"
  "msg/SwarmOrigin.msg"
  "msg/FormationCommand.msg"
  "msg/AgentSetpoint.msg"
  "msg/QRMissionData.msg"
  "msg/QRCoordinates.msg"
  "msg/MissionTarget.msg"
  "msg/NeighborInfo.msg"
  "msg/SwarmControlCommand.msg"
  "msg/SystemEvent.msg"
  "msg/LandingZoneDetection.msg"
  "msg/ZoneMap.msg"
  "msg/LeaderHeartbeat.msg"
  "msg/ElectionResult.msg"

  # Servisler
  "srv/AssignRole.srv"
  "srv/TriggerMission.srv"
  "srv/ManageSwarmMember.srv"

  # Actions
  "action/ExecuteFormation.action"
  "action/ExecuteManeuver.action"
  "action/ManageSwarmMember.action"

  DEPENDENCIES builtin_interfaces action_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
