# SystemEvent.msg
# Event bus message for mission, safety, perception, consensus and GCS logging.
# This message makes event flow explicit instead of overloading SwarmState.last_event_* only.
# Coordinate convention: local NED frame.

builtin_interfaces/Time stamp

# Mission events
uint8 EVENT_UNKNOWN=0
uint8 EVENT_AGENT_READY=1
uint8 EVENT_AGENT_REACHED_POS=2
uint8 EVENT_AGENT_DETACHED=3
uint8 EVENT_AGENT_LANDED=4
uint8 EVENT_AGENT_REJOINED=5
uint8 EVENT_AGENT_FAULT=6
uint8 EVENT_AGENT_JOIN_REQUEST=7
uint8 EVENT_AGENT_PILOT_OVERRIDE=8

# Perception / task events
uint8 EVENT_QR_DETECTED=20
uint8 EVENT_QR_PARSED=21
uint8 EVENT_FORMATION_REACHED=22
uint8 EVENT_FORMATION_FAILED=23
uint8 EVENT_MISSION_STARTED=24
uint8 EVENT_MISSION_COMPLETED=25
uint8 EVENT_COLOR_ZONE_DETECTED=26
uint8 EVENT_QR_SEQUENCE_REJECTED=27
uint8 EVENT_PRECISION_LANDING_STARTED=28    # source=detaching agent; value=COLOR_* enum
uint8 EVENT_PRECISION_LANDING_COMPLETED=29  # source=detaching agent; value=COLOR_* enum
uint8 EVENT_ROTATION_STARTED=30             # formation rotation toward next target started
uint8 EVENT_ROTATION_COMPLETED=31           # formation rotation completed
uint8 EVENT_MANEUVER_STARTED=32             # pitch/roll/yaw maneuver started
uint8 EVENT_MANEUVER_COMPLETED=33           # maneuver completed successfully
uint8 EVENT_MANEUVER_FAILED=34              # maneuver failed or timed out
uint8 EVENT_MEMBER_DETACH_STARTED=35        # QR detach/remove flow started
uint8 EVENT_MEMBER_REJOIN_STARTED=36        # rejoin flow started
uint8 EVENT_MEMBER_MANAGEMENT_FAILED=37     # detach/rejoin/replacement failed

# System / safety events
uint8 EVENT_GCS_LINK_LOST=40
uint8 EVENT_GCS_LINK_RESTORED=41
uint8 EVENT_BATTERY_LOW=42
uint8 EVENT_COLLISION_RISK=43
uint8 EVENT_OFFBOARD_LOST=44
uint8 EVENT_RTL_TRIGGERED=45
uint8 EVENT_EMERGENCY_LAND=46
uint8 EVENT_PX4_LINK_LOST=47
uint8 EVENT_LEADER_CHANGED=48
uint8 EVENT_SAFETY_HOLD=49
uint8 EVENT_FAILSAFE_CLEARED=50
uint8 EVENT_ORIGIN_READY=51      # shared origin candidate is available
uint8 EVENT_ORIGIN_SYNCED=52     # all required agents applied SwarmOrigin
uint8 EVENT_ORIGIN_FAILED=53     # origin sync failed or timed out

# Event severity
uint8 SEVERITY_INFO=0
uint8 SEVERITY_WARNING=1
uint8 SEVERITY_CRITICAL=2
uint8 SEVERITY_EMERGENCY=3

uint8 event_type
uint8 severity

# 0 means system/global event. Otherwise source agent ID.
uint8 source_agent_id

# Optional target agent, e.g. detached/landed agent. 0 means not applicable.
uint8 target_agent_id

# Optional numeric value: battery %, distance, COLOR_* enum, error metric, etc.
float32 value

# Optional event position in local NED frame.
bool has_position
float32 pos_x
float32 pos_y
float32 pos_z

string source_module
string message
