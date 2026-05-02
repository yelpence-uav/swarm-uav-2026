# FormationCommand.msg
# Swarm-level formation request.
# Producer: mission_fsm (single writer during task execution).
# Inputs that may lead to this command: QRMissionData from qr_mission_parser, TriggerMission from GCS bridge.
# Consumer: swarm_core/formation_control / ExecuteFormation action server.
# Coordinate convention: local NED frame.

builtin_interfaces/Time stamp

uint32 sequence_num

# Formation types
uint8 FORMATION_UNKNOWN=0
uint8 FORMATION_OKBASI=1
uint8 FORMATION_V=2
uint8 FORMATION_CIZGI=3
uint8 FORMATION_CUSTOM=99

uint8 formation_type

# Formation center in local NED frame
float32 center_x
float32 center_y
float32 center_z

# Direction of formation in degrees
float32 heading_deg

# Default spacing between agents
float32 spacing_m

# If true, formation_control uses current swarm centroid XY as reference.
bool use_current_centroid

# If true, formation_control preserves current average altitude / NED Z.
# Use this when a QR command changes formation but does not request altitude change.
bool use_current_altitude

bool rotate_towards_target
bool hold_after_reached

# Optional custom formation fields.
# If formation_type == FORMATION_CUSTOM, agent_ids, offset_x, offset_y, offset_z must have equal length.
# Each index describes the offset of one agent from the formation center.
uint8[] agent_ids
float32[] offset_x
float32[] offset_y
float32[] offset_z

float32 position_tolerance_m
float32 heading_tolerance_deg

# Timeout for formation convergence. 0.0 = no timeout (wait forever).
# Used by formation_control when NOT driven through ExecuteFormation.action.
# ExecuteFormation.action has its own timeout_sec field.
float32 timeout_sec

# Speed limit for this formation move. 0.0 = use formation_control default.
float32 max_speed_mps

string source_module
