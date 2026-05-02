# QRMissionData.msg
# QR detection + parsed QR mission data in one message.
# Producer: qr_detector / qr_mission_parser.
# Consumers: mission_fsm, consensus_fsm.
# Coordinate convention for target_x/y/z: local NED frame.
# altitude_agl_m is human-readable positive-up altitude above ground level.

# QR FORMAT EXAMPLE / PARSING REFERENCE:
# The final competition QR format may change, but qr_mission_parser should map the
# decoded team-specific section into this message. A QR may contain multiple active
# sections at once, for example:
#   team_id=YELPENCE; qr_id=1; next_qr=4; formation=OKBASI; spacing_m=6;
#   altitude_agl_m=20; wait_s=3; pitch_deg=-15; detach_agent=2; detach_color=BLUE
# Mission FSM must ignore QR sections belonging to other team_id values and must reject
# stale/out-of-order qr_seq values.
#
# MANOEUVRE SIGN CONVENTION:
# Formation local axes: +forward points toward the next QR, +left is left of the formation,
# +up is physically upward. AgentSetpoint still uses local NED, so upward motion means z decreases.
# pitch_deg > 0: forward side of the formation rises, rear side lowers.
# roll_deg  > 0: left side of the formation rises, right side lowers.

builtin_interfaces/Time stamp

# Parsed QR command hints. Kept for backward compatibility, but QR can contain
# multiple active sections at the same time; use *_active flags below as source of truth.
uint8 COMMAND_UNKNOWN=0
uint8 COMMAND_SET_FORMATION=1
uint8 COMMAND_GOTO_TARGET=2
uint8 COMMAND_ROTATE_FORMATION=3
uint8 COMMAND_REMOVE_AGENT=4
uint8 COMMAND_ADD_AGENT=5
uint8 COMMAND_LAND_AGENT=6
uint8 COMMAND_COMPLETE_MISSION=7

# Formation types
uint8 FORMATION_UNKNOWN=0
uint8 FORMATION_OKBASI=1
uint8 FORMATION_V=2
uint8 FORMATION_CIZGI=3
uint8 FORMATION_CUSTOM=99

# Landing/detach zone colors
uint8 COLOR_UNKNOWN=0
uint8 COLOR_RED=1
uint8 COLOR_BLUE=2

uint8 detector_agent_id
uint32 qr_id
uint32 qr_seq          # monotonically increasing; mission_fsm drops out-of-order/stale QRs
uint8 command_type
string team_id         # competition team ID; ignore QR tasks for other teams

# Raw detection status
bool detected
bool decoded
bool valid

string raw_text
string error_message

float32 confidence

# QR bounding box in image coordinates
float32 image_x
float32 image_y
float32 image_width
float32 image_height

# Parsed mission section activation flags.
# One QR may request more than one operation: formation + altitude + manoeuvre + next QR, etc.
bool formation_active
bool target_active
bool maneuver_active
bool altitude_active
bool detach_active
bool complete_mission

# Parsed mission fields — formation
uint8 formation_type
float32 spacing_m

# Target / next waypoint in local NED frame
float32 target_x
float32 target_y
float32 target_z
float32 target_heading_deg

# Pitch/Roll manoeuvre.
# Formation tilts as a unit; swarm centroid stays fixed.
float32 pitch_deg       # signed; see MANOEUVRE SIGN CONVENTION above
float32 roll_deg        # signed; see MANOEUVRE SIGN CONVENTION above
float32 yaw_deg         # signed; clockwise positive in NED frame

# Altitude change from QR text. Positive upward, e.g. QR says 20 m -> altitude_agl_m = 20.0.
float32 altitude_agl_m

# Wait at QR point before proceeding to next waypoint
float32 wait_s          # seconds; 0 = no wait

# Next QR — 0 means this is the last waypoint; swarm returns home after executing this QR task.
uint32 next_qr

# Detach / add-remove section
uint8 target_agent_id
uint8 detach_color
float32 detach_wait_s   # seconds to wait at landing zone before rejoining

# NOTE:
# This message carries only the QR mission request, including requested detach_color.
# Real-time red/blue landing-zone detections are NOT carried here.
# They are published separately as LandingZoneDetection.msg on:
#   /drone_{id}/perception/landing_zone
